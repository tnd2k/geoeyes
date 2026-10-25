"""Phase ``acquire``: Sentinel-1 bursts covering the AOI from the ASF archive into the workspace archive.

Enabled for Sentinel-1 tracks using the workspace archive with an ``[acquire] date_range``.
The fingerprint is the ASF catalogue (burst file ids) for the track, AOI and ``[acquire] date_range``: a new
acquisition on ASF re-runs the phase, and ``build_stack`` then extends the stack with the new date
(incremental build). Offline, the catalogue recorded by the last run is used, so a missing network never blocks
processing of data already in the archive. CSK / Capella / TSX are commercial: no download (phase disabled).
"""
from __future__ import annotations

import logging
from collections import defaultdict

from geoeyes.config.schema import Sensor
from geoeyes.core.hashing import sha256_params

log = logging.getLogger(__name__)


def enabled(ctx) -> bool:
    """Sentinel-1, workspace archive, and a ``[acquire] date_range`` to search (without one: use the archive as
    it is)."""
    a = ctx.cfg.acquire
    return ctx.track.sensor is Sensor.SENTINEL1 and not a.archive and a.date_range is not None


def problem(ctx) -> str | None:
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
        ctx.cache["acquire"] = _thin(refs, c.acquire.max_per_month)
        log.info("%s: %d bursts in %d acquisitions on ASF (%s..%s)", ctx.track_id, len(ctx.cache["acquire"]),
                 len({r.date for r in ctx.cache["acquire"]}), start, end)
    return ctx.cache["acquire"]


def _previous(ctx) -> dict:
    from geoeyes.controller.phase import ProjectState
    rec = ProjectState(ctx.project).get(ctx.track_id, "acquire") or {}
    return rec if rec.get("status") == "done" else {}


def fingerprint(ctx) -> str:
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
    if ctx.cache.get("acquire_offline"):
        return True
    refs = catalogue(ctx)
    return bool(refs) and all(_complete(p) for r in refs for p in burst_paths(ctx.workspace, r))


def changes(ctx) -> str:
    """New acquisitions on ASF since the last run ('' when none or no previous run)."""
    from geoeyes.processing.acquire.s1_bursts import _complete, burst_paths
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


def run(ctx) -> dict:
    from geoeyes.config.settings import load_settings
    from geoeyes.processing.acquire.s1_bursts import download
    refs = catalogue(ctx)
    files = download(refs, ctx.workspace, token=load_settings().earthdata_token or None)
    dates = sorted({str(r.date) for r in refs})
    return {"acquisitions": len(dates), "bursts": len(files), "dates": dates}
