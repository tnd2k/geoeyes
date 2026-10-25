"""GACOS zenith total delays (http://www.gacos.net/) at the PS.

GACOS products are ordered on its website (area, dates, time of day; delivered by e-mail) and unpacked into one
folder: ``<YYYYMMDD>.ztd`` + ``<YYYYMMDD>.ztd.rsc`` (binary float32 grid, ROI_PAC header) or
``<YYYYMMDD>.ztd.tif``. ``order`` returns what to enter in the order form; this module does not submit it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator

log = logging.getLogger(__name__)


def _read_rsc(path: Path) -> dict[str, str]:
    out = {}
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[0].upper()] = parts[1].strip()
    return out


def read_ztd(folder: Path, day: date) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """(ztd m (n_lat, n_lon), lat, lon) of ``day``, or None when the folder has no product for it."""
    base = Path(folder) / day.strftime("%Y%m%d")
    ztd, rsc, tif = base.with_suffix(".ztd"), Path(str(base) + ".ztd.rsc"), Path(str(base) + ".ztd.tif")
    if ztd.exists() and rsc.exists():
        h = _read_rsc(rsc)
        w, n = int(h["WIDTH"]), int(h["FILE_LENGTH"])
        grid = np.fromfile(ztd, np.float32)
        if grid.size != w * n:
            raise ValueError(f"{ztd}: {grid.size} values, header says {n} x {w}")
        lon = float(h["X_FIRST"]) + np.arange(w) * float(h["X_STEP"])
        lat = float(h["Y_FIRST"]) + np.arange(n) * float(h["Y_STEP"])
        return grid.reshape(n, w).astype(np.float64), lat, lon
    if tif.exists():
        import rasterio
        with rasterio.open(tif) as src:
            grid = src.read(1).astype(np.float64)
            t = src.transform
            lon = t.c + (np.arange(src.width) + 0.5) * t.a
            lat = t.f + (np.arange(src.height) + 0.5) * t.e
        return grid, lat, lon
    return None


def zenith_delays(lon, lat, dates: list[date], folder: Path) -> np.ndarray:
    """(n, n_epoch) zenith total delay (m) bilinearly interpolated at the points; NaN for dates without a
    product or points outside its grid."""
    lon, lat = np.asarray(lon, np.float64), np.asarray(lat, np.float64)
    out = np.full((lon.size, len(dates)), np.nan)
    missing = []
    for k, d in enumerate(dates):
        g = read_ztd(folder, d)
        if g is None:
            missing.append(d)
            continue
        z, la, lo = g
        if la[0] > la[-1]:
            z, la = z[::-1], la[::-1]
        z = np.where(z == 0, np.nan, z)              # GACOS no-data
        out[:, k] = RegularGridInterpolator((la, lo), z, bounds_error=False, fill_value=np.nan)(
            np.column_stack([lat, lon]))
    if missing:
        log.warning("GACOS: no product for %d date(s) in %s (%s): the linear APS is used for them",
                    len(missing), folder, ", ".join(map(str, missing)))
    return out


def order(lon, lat, times: dict[date, datetime], buffer_deg: float = 0.1) -> dict:
    """What to enter in the GACOS order form: area, time of day (UTC, mean over the dates) and dates."""
    lon, lat = np.asarray(lon, np.float64), np.asarray(lat, np.float64)
    secs = [t.hour * 3600 + t.minute * 60 + t.second for t in times.values()]
    m = int(round(float(np.mean(secs)) / 60))
    return {"north": round(float(lat.max() + buffer_deg), 3), "south": round(float(lat.min() - buffer_deg), 3),
            "west": round(float(lon.min() - buffer_deg), 3), "east": round(float(lon.max() + buffer_deg), 3),
            "time_utc": f"{m // 60:02d}:{m % 60:02d}", "dates": [d.strftime("%Y%m%d") for d in times]}
