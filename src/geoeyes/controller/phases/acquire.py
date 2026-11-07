"""Phase ``acquire``: Sentinel-1 bursts covering the AOI from the ASF archive into the workspace archive.

Enabled for Sentinel-1 tracks using the workspace archive with an ``[acquire] date_range``.
The fingerprint is the ASF catalogue (burst file ids) for the track, AOI and ``[acquire] date_range``: a new
acquisition on ASF re-runs the phase, and ``build_stack`` then extends the stack with the new date
(incremental build). Offline, the catalogue recorded by the last run is used, so a missing network never blocks
processing of data already in the archive. CSK / Capella / TSX are commercial: no download (phase disabled).

Open data (``[acquire] opendata`` = a stack id of ``geoeyes opendata stacks``, ICEYE or Capella): the stack's
scenes covering the AOI, from the local open-data index (``geoeyes opendata sync``), into
``<archive>/<sensor>/<track_id>/YYYYMMDD/``; ICEYE and Umbra scenes are cut to the AOI + ``opendata_margin_m``.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from geoeyes.config.schema import Sensor
from geoeyes.core.hashing import sha256_params

log = logging.getLogger(__name__)


def enabled(ctx) -> bool:
    """Sentinel-1, workspace archive, and a ``[acquire] date_range`` to search (without one: use the archive as
    it is); or an open-data stack."""
    a = ctx.cfg.acquire
    if a.opendata:
        return not a.archive
    return ctx.track.sensor is Sensor.SENTINEL1 and not a.archive and a.date_range is not None


def _opendata(ctx) -> bool:
    return bool(ctx.cfg.acquire.opendata)


def _od_stack(ctx) -> dict:
    """The open-data stack, restricted to the scenes covering the AOI, ``date_range`` and ``max_per_month``."""
    if "acquire" not in ctx.cache:
        from geoeyes.core.errors import DataError
        from geoeyes.opendata import find_stacks, load
        from geoeyes.opendata.stacks import get_stack
        a = ctx.cfg.acquire
        source = a.opendata.split(":", 1)[0]
        st = get_stack(find_stacks(load(ctx.workspace, [source]), aoi=tuple(ctx.cfg.aoi.bbox), min_scenes=1),
                       a.opendata)
        if st is None:
            raise DataError(f"open-data stack {a.opendata} has no scene covering the AOI in the local index "
                            "(run `geoeyes opendata sync`, check the id with `geoeyes opendata stacks --bbox ...`)")
        scenes = st["scenes"]
        if a.date_range:
            scenes = [s for s in scenes if str(a.date_range[0]) <= s["date"] <= str(a.date_range[1])]
        if a.max_per_month:
            by_month: dict[str, list] = defaultdict(list)
            for sc in scenes:
                by_month[sc["date"][:7]].append(sc)
            scenes = [sc for m in sorted(by_month) for sc in by_month[m][:a.max_per_month]]
        ctx.cache["acquire"] = {**st, "scenes": scenes}
        log.info("%s: open-data stack %s, %d scene(s) over the AOI", ctx.track_id, st["id"], len(scenes))
    return ctx.cache["acquire"]


def _od_problem(ctx) -> str | None:
    from geoeyes.opendata.sources import SOURCES
    source = ctx.cfg.acquire.opendata.split(":", 1)[0]
    if ctx.cfg.aoi.bbox is None:
        return "[aoi] bbox is required to fetch an open-data stack"
    if source not in SOURCES:
        return f"[acquire] opendata: unknown source {source!r} (known: {', '.join(sorted(SOURCES))})"
    if SOURCES[source].sensor != ctx.track.sensor.value:
        return (f"{ctx.track_id}: [acquire] opendata {ctx.cfg.acquire.opendata} needs a "
                f"{SOURCES[source].sensor or 'unsupported'} track, the track is {ctx.track.sensor.value}")
    return None


def _od_margin(ctx) -> float | None:
    """Margin around the AOI of a cut product ([acquire] opendata_margin_m, else the source default); None when the
    source is downloaded whole."""
    from geoeyes.opendata.fetch import CUT, MARGIN_M
    source = ctx.cfg.acquire.opendata.split(":", 1)[0]
    if source not in CUT:
        return None
    m = ctx.cfg.acquire.opendata_margin_m
    return float(m) if m is not None else MARGIN_M[source]


def _od_request(ctx, item: str) -> dict:
    a = ctx.cfg.acquire
    return {"stack": a.opendata, "aoi": list(ctx.cfg.aoi.bbox), "margin_m": _od_margin(ctx),
            "item": item}


def _od_missing(ctx) -> list[str]:
    import json

    from geoeyes.controller.phases.build_stack import scenes_root
    from geoeyes.opendata.fetch import MARKER
    root, out = scenes_root(ctx), []
    for s in _od_stack(ctx)["scenes"]:
        m = root / s["date"].replace("-", "") / MARKER
        rec = json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}
        want = _od_request(ctx, s["item"])
        if any(rec.get(k) != v for k, v in want.items()):
            out.append(s["date"])
    return out


def problem(ctx) -> str | None:
    if _opendata(ctx):
        return _od_problem(ctx)
    if ctx.cfg.aoi.bbox is None:
        return "[aoi] bbox is required to search Sentinel-1 bursts"
    if ctx.track.relative_orbit is None:
        return f"{ctx.track_id}: relative_orbit is required to search Sentinel-1 bursts"
    return None


def _thin(refs, per_month: int):
    """At most ``per_month`` acquisitions per calendar month (the earliest ones); 0 = all."""
    if per_month <= 0:
        return refs
    by_month: dict[tuple[int, int], list] = defaultdict(list)
    for d in sorted({r.date for r in refs}):
        by_month[(d.year, d.month)].append(d)
    keep = {d for days in by_month.values() for d in days[:per_month]}
    return [r for r in refs if r.date in keep]


def catalogue(ctx) -> list:
    """Bursts to have in the archive (``BurstRef``), cached in the context; raises when ASF is unreachable."""
    if "acquire" not in ctx.cache:
        from geoeyes.core.types import BBox
        from geoeyes.sensors.sentinel1.asf import burst_ids_for_aoi, search
        c = ctx.cfg
        aoi = BBox.from_sequence(list(c.aoi.bbox))
        start, end = c.acquire.date_range
        ids = burst_ids_for_aoi(aoi, relative_orbit=ctx.track.relative_orbit, start=start, end=end,
                                subswaths=ctx.track.subswaths or None)
        refs = search(start=start, end=end, full_burst_ids=ids, relative_orbit=ctx.track.relative_orbit)
        if ctx.track.frame is not None:              # only the bursts of the SLC products of that frame
            from geoeyes.core.errors import DataError
            from geoeyes.sensors.sentinel1.asf import slc_names_in_frame
            names = slc_names_in_frame(frame=ctx.track.frame, relative_orbit=ctx.track.relative_orbit,
                                       start=start, end=end)
            refs = [r for r in refs if r.slc_name in names]
            if not refs:
                raise DataError(f"no bursts over the AOI in frame {ctx.track.frame} of relative orbit "
                                f"{ctx.track.relative_orbit}")
        ctx.cache["acquire"] = _thin(refs, c.acquire.max_per_month)
        log.info("%s: %d bursts in %d acquisitions on ASF (%s..%s)", ctx.track_id, len(ctx.cache["acquire"]),
                 len({r.date for r in ctx.cache["acquire"]}), start, end)
    return ctx.cache["acquire"]


def _previous(ctx) -> dict:
    from geoeyes.controller.phase import ProjectState
    rec = ProjectState(ctx.project).get(ctx.track_id, "acquire") or {}
    return rec if rec.get("status") == "done" else {}


def fingerprint(ctx) -> str:
    if _opendata(ctx):
        return sha256_params({"items": sorted(s["item"] for s in _od_stack(ctx)["scenes"]),
                              "aoi": list(ctx.cfg.aoi.bbox), "margin_m": _od_margin(ctx)})
    try:
        refs = catalogue(ctx)
    except Exception as exc:                     # offline: keep what the last run downloaded
        prev = _previous(ctx).get("fingerprint")
        if prev:
            log.warning("%s: ASF search failed (%s); using the catalogue of the last acquire run", ctx.track_id, exc)
            ctx.cache["acquire_offline"] = True
            return prev
        raise
    return sha256_params(sorted(r.file_id for r in refs))


def outputs_exist(ctx) -> bool:
    from geoeyes.processing.acquire.s1_bursts import _complete, burst_paths
    if _opendata(ctx):
        return bool(_od_stack(ctx)["scenes"]) and not _od_missing(ctx)
    if ctx.cache.get("acquire_offline"):
        return True
    refs = catalogue(ctx)
    return bool(refs) and all(_complete(p) for r in refs for p in burst_paths(ctx.workspace, r))


def changes(ctx) -> str:
    """New acquisitions on ASF since the last run ('' when none or no previous run)."""
    from geoeyes.processing.acquire.s1_bursts import _complete, burst_paths
    if _opendata(ctx):
        missing = _od_missing(ctx)
        return f"{len(missing)} open-data scene(s) to fetch: {', '.join(missing)}" if missing else ""
    if ctx.cache.get("acquire_offline"):
        return ""
    refs = catalogue(ctx)
    prev = (_previous(ctx).get("result") or {}).get("dates")
    new = sorted({str(r.date) for r in refs} - set(prev or ()))
    if prev is not None and new:
        return f"{len(new)} new acquisition(s) on ASF: {', '.join(new)}"
    missing = sum(not _complete(p) for r in refs for p in burst_paths(ctx.workspace, r))
    n_acq = len({r.date for r in refs})
    return f"{missing} burst file(s) of {n_acq} acquisitions not in the archive" if missing else ""


def _od_run(ctx) -> dict:
    from geoeyes.controller.phases.build_stack import scenes_root
    from geoeyes.core.logging import event
    from geoeyes.geometry.dem import load_dem
    from geoeyes.opendata import load
    from geoeyes.opendata.fetch import fetch_stack
    st = _od_stack(ctx)
    w, s, e, n = ctx.cfg.aoi.bbox
    dem = None
    if ctx.track.sensor in (Sensor.ICEYE, Sensor.UMBRA):     # range window: lowest and highest ground of the AOI
        dem = load_dem(None if ctx.cfg.stack.dem in ("", "srtm-1") else ctx.cfg.stack.dem, s - 0.05, n + 0.05,
                       w - 0.05, e + 0.05, cache=ctx.workspace.cache_dir("dem"), focus=(s, n, w, e))
    got = fetch_stack(st, load(ctx.workspace, [st["source"]]), scenes_root(ctx), aoi=(w, s, e, n), dem=dem,
                      margin_m=_od_margin(ctx) or 0.0,
                      progress=lambda i, k, sid: event(log, "progress", f"fetch {sid}", stage="acquire",
                                                       done=i - 1, total=k))
    return {"acquisitions": len(got), "stack": st["id"], "dates": [g["date"] for g in got],
            "bytes": sum(g["bytes"] for g in got)}


def run(ctx) -> dict:
    if _opendata(ctx):
        return _od_run(ctx)
    from geoeyes.config.settings import load_settings
    from geoeyes.processing.acquire.s1_bursts import download
    refs = catalogue(ctx)
    files = download(refs, ctx.workspace, token=load_settings().earthdata_token or None)
    dates = sorted({str(r.date) for r in refs})
    return {"acquisitions": len(dates), "bursts": len(files), "dates": dates}
