"""Phase ``build_stack``: raw scenes of a track -> native StackStore over the AOI (S1 bursts or stripmap scenes).

Scenes: ``[acquire] archive`` when set, else ``<workspace>/archive/<sensor>/<track_id>/``. Sentinel-1: scene
folders with ``bursts.json`` (any depth below the root); Capella / COSMO-SkyMed: folders named ``YYYYMMDD``
holding the product. ``[network] reference`` ``auto`` = the median acquisition date.
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import date
from functools import partial
from pathlib import Path

from geoeyes.config.schema import Sensor
from geoeyes.core.errors import ConfigError, DataError
from geoeyes.core.hashing import sha256_params

log = logging.getLogger(__name__)
FINGERPRINT_ATTR = "build_fingerprint"
SIGNATURES_ATTR = "scene_signatures"
_DATE_DIR = re.compile(r"^(\d{8})")


def scenes_root(ctx) -> Path:
    if ctx.cfg.acquire.archive:
        return Path(ctx.cfg.acquire.archive)
    return ctx.workspace.archive / ctx.track.sensor.value / ctx.track_id


def find_scenes(ctx) -> dict[date, Path]:
    """Acquisition date -> scene folder, within ``[acquire] date_range``."""
    root = scenes_root(ctx)
    if not root.exists():
        raise DataError(f"{ctx.track_id}: raw scene folder {root} not found ([acquire] archive)")
    out: dict[date, Path] = {}
    if ctx.track.sensor is Sensor.SENTINEL1:
        for bj in sorted(root.rglob("bursts.json")):
            d = bj.parent.name.split("_")[5][:8]
            out[date(int(d[:4]), int(d[4:6]), int(d[6:8]))] = bj.parent
    else:
        for p in sorted(root.rglob("*")):
            m = _DATE_DIR.match(p.name)
            if p.is_dir() and m and len(p.name) == 8:
                d = m.group(1)
                out[date(int(d[:4]), int(d[4:6]), int(d[6:8]))] = p
    rng = ctx.cfg.acquire.date_range
    if rng:
        out = {d: p for d, p in out.items() if rng[0] <= d <= rng[1]}
    out = _per_month(ctx, out)
    if len(out) < 3:
        raise DataError(f"{ctx.track_id}: {len(out)} scene(s) in {root}, at least 3 needed")
    return dict(sorted(out.items()))


def _per_month(ctx, scenes: dict[date, Path]) -> dict[date, Path]:
    """``[acquire] max_per_month``: the archive is shared, other projects may have added dates. The dates the
    project's own acquire phase selected win; without an acquire record, the first N dates of each month."""
    from collections import defaultdict

    from geoeyes.controller.phase import ProjectState
    per = ctx.cfg.acquire.max_per_month
    if per <= 0:
        return scenes
    rec = ProjectState(ctx.project).get(ctx.track_id, "acquire") or {}
    chosen = (rec.get("result") or {}).get("dates") if rec.get("status") == "done" else None
    if chosen:
        keep = set(chosen)
        return {d: p for d, p in scenes.items() if str(d) in keep}
    by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for d in sorted(scenes):
        by_month[(d.year, d.month)].append(d)
    keep_d = {d for days in by_month.values() for d in days[:per]}
    return {d: p for d, p in scenes.items() if d in keep_d}


def orbit_upgrades(ctx) -> list[str]:
    """Sentinel-1 dates of the existing store coregistered without a precise orbit (RESORB, annotation) for which a
    POEORB is now published (~20 days after the acquisition): their coregistration is redone."""
    from datetime import datetime, timedelta

    from geoeyes.io.stack import StackStore
    if ctx.track.sensor is not Sensor.SENTINEL1:
        return []
    if "orbit_upgrades" in ctx.cache:
        return ctx.cache["orbit_upgrades"]
    st = StackStore(target(ctx)["path"])
    per = (st.attrs.get("orbit_per_date") or {}) if st.exists() else {}
    old_enough = date.today() - timedelta(days=15)
    pending = [d for d, kind in per.items() if kind != "POEORB" and date.fromisoformat(d) <= old_enough]
    out: list[str] = []
    if pending:
        from geoeyes.config.settings import load_settings
        from geoeyes.sensors.sentinel1.orbits import PoeorbProvider
        prov = PoeorbProvider(ctx.workspace.cache_dir("orbits"), token=load_settings().earthdata_token or None,
                              kinds=("POEORB",))
        scenes = target(ctx)["scenes"]
        for d in pending:
            folder = scenes.get(date.fromisoformat(d))
            if folder is None:
                continue
            parts = folder.name.split("_")                       # S1D_IW_SLC__1SDV_<start>_<stop>_...
            try:
                t0, t1 = datetime.strptime(parts[5], "%Y%m%dT%H%M%S"), datetime.strptime(parts[6], "%Y%m%dT%H%M%S")
                prov.find(parts[0], t0, t1, kind="POEORB")
                out.append(d)
            except (DataError, ValueError, IndexError):
                continue
    ctx.cache["orbit_upgrades"] = sorted(out)
    return ctx.cache["orbit_upgrades"]


def previous(ctx) -> dict:
    """What the last completed build of this track recorded (dates, reference, scene signature)."""
    from geoeyes.controller.phase import ProjectState
    rec = ProjectState(ctx.project).get(ctx.track_id, "build_stack") or {}
    return (rec.get("result") or {}) if rec.get("status") == "done" else {}


def reference_date(ctx, dates: list[date]) -> date:
    ref = ctx.cfg.network.reference
    if ref == "auto":
        # keep the reference of the previous build while it is still an acquisition (new scenes extend the
        # stack instead of moving its reference); first build: the median date
        prev = previous(ctx).get("reference")
        if prev and date.fromisoformat(prev) in dates:
            return date.fromisoformat(prev)
        return sorted(dates)[(len(dates) - 1) // 2]
    if ref not in dates:
        raise ConfigError(f"[network] reference {ref} is not an acquisition date of {ctx.track_id}")
    return ref


def target(ctx) -> dict:
    """Scenes, reference date, stack id and store path of the track (cached in the context)."""
    if "stack" not in ctx.cache:
        scenes = find_scenes(ctx)
        ref = reference_date(ctx, list(scenes))
        sid = f"{ctx.track_id}-ref{ref:%Y%m%d}"
        ctx.cache["stack"] = {"scenes": scenes, "reference": ref, "stack_id": sid,
                              "path": ctx.project.stack_store(sid)}
    return ctx.cache["stack"]


def problem(ctx) -> str | None:
    if ctx.cfg.stack.engine != "native":
        return "[stack] engine = 'snap' is not available in GeoEyes (set engine = 'native')"
    if ctx.cfg.aoi.bbox is None:
        return "[aoi] bbox is required to build a native stack"
    if ctx.track.sensor not in (Sensor.SENTINEL1, Sensor.CAPELLA, Sensor.COSMO_SKYMED):
        return f"no native stack builder for {ctx.track.sensor.value} yet"
    return None


def scene_signature(folder: Path) -> str:
    """Names and sizes of the files of a scene: a re-delivered or repaired product changes it."""
    files = sorted((p.relative_to(folder).as_posix(), p.stat().st_size) for p in folder.rglob("*") if p.is_file()
                   and not p.name.endswith(".done"))
    return sha256_params(files)[:16]


def signatures(ctx) -> dict[str, str]:
    t = target(ctx)
    if "signatures" not in t:
        t["signatures"] = {str(d): scene_signature(p) for d, p in t["scenes"].items()}
    return t["signatures"]


def _fingerprint(ctx, sigs: dict[str, str]) -> str:
    return sha256_params({"sensor": ctx.track.sensor.value, "scenes": sigs,
                          "reference": str(target(ctx)["reference"]), "aoi": list(ctx.cfg.aoi.bbox),
                          "dem": ctx.cfg.stack.dem, "subswaths": list(ctx.track.subswaths)})


def fingerprint(ctx) -> str:
    return _fingerprint(ctx, signatures(ctx))


def reusable(ctx) -> set[date]:
    """Dates of the existing store that an incremental build can copy: the store was built with the same
    reference (master), AOI, DEM and subswaths (its fingerprint, recomputed with the scene signatures it was
    built from, matches) and the raw scene of the date is unchanged. A new reference = another store path:
    nothing is reused, every date is coregistered again."""
    from geoeyes.io.stack import StackStore
    if not ctx.cfg.stack.incremental:
        return set()
    st = StackStore(target(ctx)["path"])
    if not st.exists() or not st.has("slc"):
        return set()
    a = st.attrs
    old = a.get(SIGNATURES_ATTR) or previous(ctx).get("signatures") or {}
    if not old or a.get(FINGERPRINT_ATTR) != _fingerprint(ctx, old):
        return set()
    now = signatures(ctx)
    ref = str(target(ctx)["reference"])
    if now.get(ref) != old.get(ref):                 # the reference scene itself was re-delivered
        return set()
    upgrade = set(orbit_upgrades(ctx))
    if ref in upgrade:                               # the reference geometry itself changes: nothing to keep
        return set()
    return {date.fromisoformat(d) for d, s in old.items() if now.get(d) == s and d not in upgrade}


def changes(ctx) -> str:
    """What changed in the raw data since the last build ('' when nothing or no previous build)."""
    prev = previous(ctx).get("signatures")
    if not prev:
        return ""
    up = orbit_upgrades(ctx)
    now = signatures(ctx)
    new = sorted(set(now) - set(prev))
    gone = sorted(set(prev) - set(now))
    changed = sorted(d for d in set(now) & set(prev) if now[d] != prev[d])
    parts = []
    if new:
        parts.append(f"{len(new)} new scene(s): {', '.join(new)}")
    if changed:
        parts.append(f"{len(changed)} changed scene(s): {', '.join(changed)}")
    if gone:
        parts.append(f"{len(gone)} scene(s) no longer in the archive: {', '.join(gone)}")
    if up:
        parts.append(f"precise orbit (POEORB) now published for {len(up)} date(s): {', '.join(up)}")
    keep = reusable(ctx) if parts else set()
    if keep:
        parts.append(f"incremental: {len(keep)} coregistered date(s) kept")
    return "; ".join(parts)


def run(ctx) -> dict:
    from geoeyes.core.types import BBox
    from geoeyes.geometry.dem import load_dem
    from geoeyes.io.stack import StackStore
    t = target(ctx)
    w, s, e, n = ctx.cfg.aoi.bbox
    dem = load_dem(None if ctx.cfg.stack.dem in ("", "srtm-1") else ctx.cfg.stack.dem, s - 0.2, n + 0.2,
                   w - 0.2, e + 0.2, cache=ctx.workspace.cache_dir("dem"))
    aoi = BBox.from_sequence([w, s, e, n])
    out = t["path"]
    keep = reusable(ctx)
    prev = None
    if keep:                                         # incremental: the old store is moved aside and read from
        prev_path = out.with_name(out.name + ".prev")
        if prev_path.exists():
            shutil.rmtree(prev_path)
        out.rename(prev_path)
        prev = StackStore(prev_path)
        log.info("incremental build: %d of %d date(s) already coregistered", len(keep & set(t["scenes"])),
                 len(t["scenes"]))
    try:
        st = _build(ctx, t, dem, aoi, out, prev, keep)
    except BaseException:
        if prev is not None:                         # put the previous stack back
            if out.exists():
                shutil.rmtree(out)
            prev.path.rename(out)
        raise
    if prev is not None:
        shutil.rmtree(prev.path)
    st.update_attrs(
        **{FINGERPRINT_ATTR: fingerprint(ctx), SIGNATURES_ATTR: signatures(ctx)})
    return {"stack": str(out), "dates": len(t["scenes"]), "reference": str(t["reference"]),
            "reused": len(keep & set(t["scenes"])), "signatures": signatures(ctx)}


def aoi_burst_ids(reference_scene: Path, aoi, margin_deg: float = 0.01) -> list[str]:
    """Bursts of the reference acquisition that cover the AOI (footprints from ``bursts.json``).

    The archive is shared: a scene folder can hold bursts another project downloaded (another AOI, another
    subswath); taking every burst found would make the dates without them look incomplete and drop them."""
    import json

    from shapely import wkt
    from shapely.geometry import box
    area = box(*aoi.as_tuple()).buffer(margin_deg)
    bursts = json.loads((reference_scene / "bursts.json").read_text())
    ids = sorted({b["full_burst_id"] for b in bursts
                  if not b.get("footprint_wkt") or wkt.loads(b["footprint_wkt"]).intersects(area)})
    if not ids:
        raise DataError(f"{reference_scene.name}: no burst of the reference acquisition covers the AOI")
    return ids


def _build(ctx, t, dem, aoi, out, prev, keep):
    if ctx.track.sensor is Sensor.SENTINEL1:
        from geoeyes.config.settings import load_settings
        from geoeyes.processing.stack.native.s1_stack import build_s1_stack
        from geoeyes.sensors.sentinel1.orbits import PoeorbProvider
        ids = aoi_burst_ids(t["scenes"][t["reference"]], aoi)
        if ctx.track.subswaths:
            ids = [i for i in ids if any(i.endswith(sw) or f"_{sw}" in i for sw in ctx.track.subswaths)]
        orbits = PoeorbProvider(ctx.workspace.cache_dir("orbits"), token=load_settings().earthdata_token or None)
        return build_s1_stack(t["scenes"], ids, t["reference"], dem, out, aoi=aoi, track_id=ctx.track_id,
                              orbits=orbits, overwrite=True, previous=prev, reuse_dates=keep)
    from geoeyes.processing.stack.native.stripmap import Scene, build_stripmap_stack
    scenes = {}
    for d, p in t["scenes"].items():
        if ctx.track.sensor is Sensor.CAPELLA:
            from geoeyes.sensors.capella import slc as rdr
            tif, js = rdr.find_files(p)
            scenes[d] = Scene(rdr.read_metadata(js), partial(rdr.read_slc, tif))
        else:
            from geoeyes.sensors.cosmo_skymed import hdf5 as rdr
            h5 = rdr.find_h5(p)
            scenes[d] = Scene(rdr.read_metadata(h5), partial(rdr.read_slc, h5))
    r = scenes[t["reference"]].grid
    if r.pass_direction.lower() != ctx.track.direction.value:
        raise DataError(f"{ctx.track_id}: the reference scene {t['reference']} is a {r.pass_direction} pass, the track "
                        f"is declared {ctx.track.direction.value}: check [[tracks]] direction or the scene folders")
    return build_stripmap_stack(scenes, t["reference"], dem, out, aoi=aoi, track_id=ctx.track_id, overwrite=True,
                                previous=prev, reuse_dates=keep)


def outputs_exist(ctx) -> bool:
    """Store present, built from these inputs, and holding its reference date (a store that lost it is broken)."""
    import numpy as np

    from geoeyes.io.stack import StackStore
    st = StackStore(target(ctx)["path"])
    if not st.exists() or st.attrs.get(FINGERPRINT_ATTR) != fingerprint(ctx):
        return False
    dates = {str(d)[:10] for d in np.asarray(st.open()["date"].values, "datetime64[D]")}
    # a POEORB published for a date built with RESORB / annotation: same inputs, better orbit -> rebuild those
    return str(target(ctx)["reference"]) in dates and not orbit_upgrades(ctx)
