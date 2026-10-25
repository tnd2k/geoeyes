"""ERA5 zenith delays at the PS for every acquisition, linearly interpolated in time between the two hourly
analyses that bracket the acquisition (the legacy code used one interpolation weight for all dates)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from geoeyes.processing.atmosphere.era5 import cds
from geoeyes.processing.atmosphere.era5.delays import delays_at_points

log = logging.getLogger(__name__)


def _bracket(t: datetime) -> tuple[tuple[date, int], tuple[date, int], float]:
    h0 = t.replace(minute=0, second=0, microsecond=0)
    w = (t - h0).total_seconds() / 3600.0
    h1 = h0 + timedelta(hours=1)
    return (h0.date(), h0.hour), (h1.date(), h1.hour), w


def zenith_delays(lon, lat, hgt, times: dict[date, datetime], cache: Path, *, buffer_deg: float = 2.0,
                  auto_download: bool = True, levels=cds.LEVELS, workers: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Hydrostatic and wet zenith delays (m), each (n, n_epoch) in the order of ``times``; NaN for epochs (or
    points) without ERA5."""
    dates = list(times)
    area = cds.area_nwse(lon, lat, buffer_deg)
    brackets = {d: _bracket(times[d]) for d in dates}
    need = []
    for d in dates:
        a, b, w = brackets[d]
        need.append(a)
        if w > 0.02:                                 # ~1 minute: one analysis is enough
            need.append(b)
    files = cds.fetch(Path(cache), need, area, auto_download=auto_download, levels=levels, workers=workers)
    n = np.asarray(lon).size
    zhd = np.full((n, len(dates)), np.nan)
    zwd = np.full((n, len(dates)), np.nan)
    cache_d: dict[Path, tuple[np.ndarray, np.ndarray]] = {}

    def at(p):
        if p not in cache_d:
            cache_d[p] = delays_at_points(p, lon, lat, hgt)
        return cache_d[p]

    missing = []
    for k, d in enumerate(dates):
        a, b, w = brackets[d]
        pa = files.get(a)
        if pa is None:
            missing.append(d)
            continue
        h0, w0 = at(pa)
        pb = files.get(b) if w > 0.02 else None
        if pb is not None:
            h1, w1 = at(pb)
            h1, w1 = np.where(np.isnan(h1), h0, h1), np.where(np.isnan(w1), w0, w1)
            h0, w0 = h0 * (1 - w) + h1 * w, w0 * (1 - w) + w1 * w
        elif w > 0.02:
            log.warning("ERA5 %s: no analysis at %s, using %02d:00 only", d, b, a[1])
        zhd[:, k], zwd[:, k] = h0, w0
    if missing:
        log.warning("ERA5: no data for %d date(s) (%s): the linear APS is used for them",
                    len(missing), ", ".join(map(str, missing)))
    return zhd, zwd


__all__ = ["zenith_delays"]
