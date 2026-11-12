"""Phase ``build_stack``: raw scenes of a track -> native StackStore over the AOI (S1 bursts or stripmap scenes).

Scenes: ``[acquire] archive`` when set, else ``<workspace>/archive/<sensor>/<track_id>/``. Sentinel-1: scene
folders with ``bursts.json`` (any depth below the root); Capella / COSMO-SkyMed / ICEYE / Umbra (SICD): folders named
``YYYYMMDD``
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
# sensors whose stack builder takes [stack] resample_kernel (stripmap builder; TOPS and SICD: K2 of
# docs/en/research/resampling-kernel.md)
STRIPMAP_KERNEL_SENSORS = (Sensor.COSMO_SKYMED, Sensor.CAPELLA, Sensor.ICEYE)
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
    """``[acquire] max_per_month`` or a track ``frame``: the archive is shared, other projects may have added dates.
    The dates the project's own acquire phase selected win; without an acquire record, the first N dates of each
    month."""
    from collections import defaultdict

    from geoeyes.controller.phase import ProjectState
    per = ctx.cfg.acquire.max_per_month
    if per <= 0 and getattr(getattr(ctx, "track", None), "frame", None) is None:
        return scenes
    rec = ProjectState(ctx.project).get(ctx.track_id, "acquire") or {}
    chosen = (rec.get("result") or {}).get("dates") if rec.get("status") == "done" else None
    if chosen:                       # also a [[tracks]] frame: the archive may hold other frames' dates
        keep = set(chosen)
        return {d: p for d, p in scenes.items() if str(d) in keep}
    if per <= 0:
        return scenes
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


def reference_date(ctx, dates: list[date], scenes: dict | None = None) -> date:
    ref = ctx.cfg.network.reference
    if ref == "auto":
        # keep the reference of the previous build while it is still an acquisition (new scenes extend the
        # stack instead of moving its reference); first build: the median date (Umbra: the central incidence)
        prev = previous(ctx).get("reference")
        if prev and date.fromisoformat(prev) in dates:
            return date.fromisoformat(prev)
        if ctx.track.sensor is Sensor.UMBRA and scenes:
            return _umbra_reference(scenes)
        return sorted(dates)[(len(dates) - 1) // 2]
    if ref not in dates:
        raise ConfigError(f"[network] reference {ref} is not an acquisition date of {ctx.track_id}")
    return ref


def _umbra_reference(scenes: dict) -> date:
    """Spotlight scenes of one stack come at several incidences: the reference is the scene at their centre
    (``sicd_stack.central_reference``), read from the SICD metadata."""
    from geoeyes.processing.stack.native.sicd_stack import central_reference, incidence_deg
    from geoeyes.sensors.sicd import slc as sicd
    inc = {}
    for d, p in scenes.items():
        data, xml = sicd.find_files(p)
        inc[d] = incidence_deg(sicd.read_metadata(data, xml))
    return central_reference(inc)


def target(ctx) -> dict:
    """Scenes, reference date, stack id and store path of the track (cached in the context)."""
    if "stack" not in ctx.cache:
        try:
            scenes = find_scenes(ctx)
        except DataError:
            kept = _kept_stack(ctx)
            if kept is None:
                raise
            ctx.cache["stack"] = kept
            return kept
        ref = reference_date(ctx, list(scenes), scenes)
        sid = f"{ctx.track_id}-ref{ref:%Y%m%d}"
        ctx.cache["stack"] = {"scenes": scenes, "reference": ref, "stack_id": sid,
                              "path": ctx.project.stack_store(sid)}
    return ctx.cache["stack"]


def _kept_stack(ctx) -> dict | None:
    """The raw scenes were removed after the stack was built (to free disk): the last completed build and its store,
    when it still exists, so the later phases run on it. ``scenes`` maps its dates to None (no raw folder); a
    rebuild needs the raw scenes again."""
    from geoeyes.io.stack import StackStore
    prev = previous(ctx)
    if not prev.get("reference"):
        return None
    ref = date.fromisoformat(prev["reference"])
    sid = f"{ctx.track_id}-ref{ref:%Y%m%d}"
    path = ctx.project.stack_store(sid)
    st = StackStore(path)
    if not st.exists():
        return None
    dates = [date.fromisoformat(str(d)[:10]) for d in st.open()["date"].values]
    log.info("%s: raw scenes not found, using the kept stack %s (%d dates)", ctx.track_id, sid, len(dates))
    return {"scenes": dict.fromkeys(dates), "reference": ref, "stack_id": sid, "path": path, "raw_removed": True}


def problem(ctx) -> str | None:
    if ctx.cfg.stack.engine != "native":
        return "[stack] engine = 'snap' is not available in GeoEyes (set engine = 'native')"
    if ctx.cfg.aoi.bbox is None:
        return "[aoi] bbox is required to build a native stack"
    from geoeyes.geometry.corridor import problem as corridor_problem
    if p := corridor_problem(ctx.cfg, ctx.project.root):
        return p
    if ctx.track.sensor not in (Sensor.SENTINEL1, Sensor.CAPELLA, Sensor.COSMO_SKYMED, Sensor.ICEYE, Sensor.UMBRA):
        return f"no native stack builder for {ctx.track.sensor.value} yet"
    return None


def scene_files(folder: Path, burst_ids: set[str] | None = None) -> list[Path]:
    """The files of a scene a stack reads. ``burst_ids`` (Sentinel-1): only those bursts and the annotation, as the
    archive is shared and a scene folder gains the bursts other projects download (another AOI or subswath)."""
    files = [p for p in folder.rglob("*") if p.is_file() and not p.name.endswith(".done")]
    if burst_ids is None or not (folder / "bursts.json").exists():
        return files
    import json
    used = {f"{b['subswath']}_{b['polarization']}_{b['burst_index']}.tiff"
            for b in json.loads((folder / "bursts.json").read_text()) if b.get("full_burst_id") in burst_ids}
    return [p for p in files if p.name in used or p.suffix == ".xml"]


def scene_signature(folder: Path, burst_ids: set[str] | None = None) -> str:
    """Names and sizes of the files of a scene the stack reads: a re-delivered or repaired product changes it."""
    files = sorted((p.relative_to(folder).as_posix(), p.stat().st_size) for p in scene_files(folder, burst_ids))
    return sha256_params(files)[:16]


def _corridor(ctx):
    """The project corridor polygon (``[aoi] corridor``), read once per track, or None."""
    if "corridor" not in ctx.cache:
        from geoeyes.geometry.corridor import of_project
        ctx.cache["corridor"] = of_project(ctx.cfg, ctx.project.root)
    return ctx.cache["corridor"]


def stack_burst_ids(ctx) -> set[str] | None:
    """Sentinel-1 bursts of the stack (those of the reference acquisition over the AOI, in the track's subswaths)."""
    if ctx.track.sensor is not Sensor.SENTINEL1 or ctx.cfg.aoi.bbox is None:
        return None
    from geoeyes.core.types import BBox
    t = target(ctx)
    ids = aoi_burst_ids(t["scenes"][t["reference"]], BBox.from_sequence(list(ctx.cfg.aoi.bbox)),
                        corridor=_corridor(ctx))
    if ctx.track.subswaths:
        ids = [i for i in ids if any(i.endswith(sw) or f"_{sw}" in i for sw in ctx.track.subswaths)]
    return set(ids)


def signatures(ctx) -> dict[str, str]:
    """Per date, the signature of the files the stack reads. A date the stored stack already has keeps its stored
    signature while none of those files changed after the stack was written (stacks signed before the
    signatures were limited to the stack's bursts stay valid)."""
    t = target(ctx)
    if "signatures" not in t and t.get("raw_removed"):      # nothing to re-read: the stack's own record
        from geoeyes.io.stack import StackStore
        t["signatures"] = StackStore(t["path"]).attrs.get(SIGNATURES_ATTR) or previous(ctx).get("signatures") or {}
    if "signatures" not in t:
        from geoeyes.io.stack import StackStore
        ids = stack_burst_ids(ctx)
        st = StackStore(t["path"])
        stored, built = {}, 0.0
        if st.exists() and (Path(t["path"]) / "zarr.json").exists():
            stored = st.attrs.get(SIGNATURES_ATTR) or {}
            built = (Path(t["path"]) / "zarr.json").stat().st_mtime
        out = {}
        for d, p in t["scenes"].items():
            files = scene_files(p, ids)
            if str(d) in stored and files and max(f.stat().st_mtime for f in files) <= built:
                out[str(d)] = stored[str(d)]
            else:
                out[str(d)] = scene_signature(p, ids)
        t["signatures"] = out
    return t["signatures"]


def _fingerprint(ctx, sigs: dict[str, str]) -> str:
    p = {"sensor": ctx.track.sensor.value, "scenes": sigs, "reference": str(target(ctx)["reference"]),
         "aoi": list(ctx.cfg.aoi.bbox), "dem": ctx.cfg.stack.dem, "subswaths": list(ctx.track.subswaths)}
    if (corr := _corridor(ctx)) is not None:         # stacks without a corridor keep their fingerprint
        from geoeyes.geometry.corridor import digest
        p["corridor"] = digest(corr)
    if ctx.cfg.stack.coreg_model != "constant":      # stacks built before the option keep their fingerprint
        p["coreg_model"] = ctx.cfg.stack.coreg_model
    if ctx.cfg.stack.resample_kernel != "spline" and ctx.track.sensor in STRIPMAP_KERNEL_SENSORS:
        p["resample"] = [ctx.cfg.stack.resample_kernel, ctx.cfg.stack.resample_radius]
    if ctx.track.sensor is Sensor.UMBRA:              # a coregistration change of the SICD engine rebuilds its stacks
        from geoeyes.processing.stack.native.sicd_stack import ENGINE
        p["engine"] = ENGINE
    return sha256_params(p)


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
                   w - 0.2, e + 0.2, cache=ctx.workspace.cache_dir("dem"), focus=(s, n, w, e))
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
    if ctx.track.sensor is not Sensor.SENTINEL1:     # the Stack tab's check (a minute; Sentinel-1 stacks are large)
        try:
            from geoeyes.processing.stack.qc import stack_qc
            s = stack_qc(out)
            worst = max((max(abs(r.get("offset_lines", 0)), abs(r.get("offset_samples", 0))) for r in s["dates"]),
                        default=0.0)
            log.info("stack check: coherence %s, largest offset left %.2f px -> %s",
                     "/".join(f"{r['coherence_mean']:.2f}" for r in s["dates"] if not r["reference"]), worst,
                     out.parent / "qc")
            if worst > 1.0:
                log.warning("stack check: an offset of %.1f pixels is left between dates: the coregistration failed "
                            "for some of them (see the Stack tab)", worst)
        except Exception as exc:                     # the check never fails the build
            log.warning("stack check failed: %s", exc)
    return {"stack": str(out), "dates": len(t["scenes"]), "reference": str(t["reference"]),
            "reused": len(keep & set(t["scenes"])), "signatures": signatures(ctx)}


def aoi_burst_ids(reference_scene: Path, aoi, margin_deg: float = 0.01, corridor=None) -> list[str]:
    """Bursts of the reference acquisition that cover the AOI (footprints from ``bursts.json``); with ``corridor``
    (shapely polygon), only those that also touch it.

    The archive is shared: a scene folder can hold bursts another project downloaded (another AOI, another
    subswath); taking every burst found would make the dates without them look incomplete and drop them."""
    import json

    from shapely import wkt
    from shapely.geometry import box

    from geoeyes.geometry.corridor import footprint_hits
    from geoeyes.processing.stack.native.s1_stack import datatake_slices
    area = box(*aoi.as_tuple()).buffer(margin_deg)
    # the reference date can lie in two slices of its datatake: their bursts together
    bursts = [b for d in datatake_slices(reference_scene)
              for b in json.loads((d / "bursts.json").read_text())]
    ids = sorted({b["full_burst_id"] for b in bursts
                  if (not b.get("footprint_wkt") or wkt.loads(b["footprint_wkt"]).intersects(area))
                  and (corridor is None or footprint_hits(b.get("footprint_wkt"), corridor))})
    if not ids:
        raise DataError(f"{reference_scene.name}: no burst of the reference acquisition covers the AOI")
    return ids


def _build(ctx, t, dem, aoi, out, prev, keep):
    if ctx.track.sensor is Sensor.SENTINEL1:
        from geoeyes.config.settings import load_settings
        from geoeyes.processing.stack.native.s1_stack import build_s1_stack
        from geoeyes.sensors.sentinel1.orbits import PoeorbProvider
        ids = aoi_burst_ids(t["scenes"][t["reference"]], aoi, corridor=_corridor(ctx))
        if ctx.track.subswaths:
            ids = [i for i in ids if any(i.endswith(sw) or f"_{sw}" in i for sw in ctx.track.subswaths)]
        orbits = PoeorbProvider(ctx.workspace.cache_dir("orbits"), token=load_settings().earthdata_token or None)
        return build_s1_stack(t["scenes"], ids, t["reference"], dem, out, aoi=aoi, track_id=ctx.track_id,
                              orbits=orbits, overwrite=True, previous=prev, reuse_dates=keep,
                              ionosphere=ctx.cfg.stack.ionosphere, ionosphere_model=ctx.cfg.stack.ionosphere_model,
                              ionosphere_smooth_m=ctx.cfg.stack.ionosphere_smooth_m)
    if ctx.track.sensor is Sensor.UMBRA:
        from geoeyes.processing.stack.native.sicd_stack import SicdScene, build_sicd_stack
        from geoeyes.sensors.sicd import slc as sicd
        sicd_scenes = {}
        for d, p in t["scenes"].items():
            data, xml = sicd.find_files(p)
            m = sicd.read_metadata(data, xml)
            sicd_scenes[d] = SicdScene(m, partial(sicd.read_slc, data, m), m.core_name or data.stem)
        r = sicd_scenes[t["reference"]].meta
        if r.pass_direction != ctx.track.direction.value:
            raise DataError(f"{ctx.track_id}: the reference scene {t['reference']} is a {r.pass_direction} pass, the "
                            f"track is declared {ctx.track.direction.value}: check [[tracks]] direction")
        return build_sicd_stack(sicd_scenes, t["reference"], dem, out, aoi=aoi, track_id=ctx.track_id,
                                overwrite=True, sensor="umbra", previous=prev, reuse_dates=keep)
    from geoeyes.processing.stack.native.stripmap import Scene, build_stripmap_stack
    scenes = {}
    for d, p in t["scenes"].items():
        if ctx.track.sensor is Sensor.CAPELLA:
            from geoeyes.sensors.capella import slc as rdr
            tif, js = rdr.find_files(p)
            scenes[d] = Scene(rdr.read_metadata(js), partial(rdr.read_slc, tif))
        elif ctx.track.sensor is Sensor.ICEYE:
            from geoeyes.sensors.iceye import slc_cog as rdr
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
                                previous=prev, reuse_dates=keep, coreg_model=ctx.cfg.stack.coreg_model,
                                kernel=ctx.cfg.stack.resample_kernel, radius=ctx.cfg.stack.resample_radius)


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
