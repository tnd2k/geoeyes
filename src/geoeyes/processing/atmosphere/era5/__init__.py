"""ERA5 zenith delays at the PS for every acquisition, linearly interpolated in time between the two hourly
analyses that bracket the acquisition (the legacy code used one interpolation weight for all dates)."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from geoeyes.processing.atmosphere.era5 import cds
from geoeyes.processing.atmosphere.era5.delays import delays_at_points

log = logging.getLogger(__name__)


def _bracket(t: datetime, step_h: int = 1) -> tuple[tuple[date, int], tuple[date, int], float]:
    """The analyses (day, hour) before and after ``t`` on a ``step_h``-hour cycle, and the weight of the second."""
    h0 = t.replace(hour=t.hour - t.hour % step_h, minute=0, second=0, microsecond=0)
    w = (t - h0).total_seconds() / (3600.0 * step_h)
    h1 = h0 + timedelta(hours=step_h)
    return (h0.date(), h0.hour), (h1.date(), h1.hour), w


def time_interpolated(n: int, times: dict[date, datetime], step_h: int, fetch: Callable, at: Callable,
                      label: str) -> tuple[np.ndarray, np.ndarray]:
    """Hydrostatic and wet zenith delays (n, n_epoch) of a weather model with analyses every ``step_h`` hours:
    ``fetch(list of (day, hour)) -> {(day, hour): path | None}``, ``at(path) -> (zhd, zwd)`` at the n points."""
    dates = list(times)
    brackets = {d: _bracket(times[d], step_h) for d in dates}
    need = []
    for d in dates:
        a, b, w = brackets[d]
        need.append(a)
        if w > 0.02 / step_h:                        # ~1 minute: one analysis is enough
            need.append(b)
    files = fetch(need)
    zhd = np.full((n, len(dates)), np.nan)
    zwd = np.full((n, len(dates)), np.nan)
    cache_d: dict[Path, tuple[np.ndarray, np.ndarray]] = {}

    def at_cached(p):
        if p not in cache_d:
            cache_d[p] = at(p)
        return cache_d[p]

    missing = []
    for k, d in enumerate(dates):
        a, b, w = brackets[d]
        pa = files.get(a)
        if pa is None:
            missing.append(d)
            continue
        h0, w0 = at_cached(pa)
        pb = files.get(b) if w > 0.02 / step_h else None
        if pb is not None:
            h1, w1 = at_cached(pb)
            h1, w1 = np.where(np.isnan(h1), h0, h1), np.where(np.isnan(w1), w0, w1)
            h0, w0 = h0 * (1 - w) + h1 * w, w0 * (1 - w) + w1 * w
        elif w > 0.02 / step_h:
            log.warning("%s %s: no analysis at %s, using %02d:00 only", label, d, b, a[1])
        zhd[:, k], zwd[:, k] = h0, w0
    if missing:
        log.warning("%s: no data for %d date(s) (%s): the linear APS is used for them",
                    label, len(missing), ", ".join(map(str, missing)))
    return zhd, zwd


def zenith_delays(lon, lat, hgt, times: dict[date, datetime], cache: Path, *, buffer_deg: float = 2.0,
                  auto_download: bool = True, levels=cds.LEVELS, workers: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Hydrostatic and wet zenith delays (m), each (n, n_epoch) in the order of ``times``; NaN for epochs (or
    points) without ERA5."""
    area = cds.area_nwse(lon, lat, buffer_deg)
    return time_interpolated(
        np.asarray(lon).size, times, 1,
        lambda need: cds.fetch(Path(cache), need, area, auto_download=auto_download, levels=levels, workers=workers),
        lambda p: delays_at_points(p, lon, lat, hgt), "ERA5")


__all__ = ["time_interpolated", "zenith_delays"]
