"""ERA5 pressure-level files from the Copernicus Climate Data Store (``cdsapi``, credentials in ~/.cdsapirc;
the dataset licence must be accepted on the CDS website once).

Cache: ``<cache>/<YYYYMMDD>/era5_pl_<YYYYMMDD>_<HH>00.nc`` (the legacy layout, so old caches are reused).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

DATASET = "reanalysis-era5-pressure-levels"
LEVELS = ("1000", "975", "950", "925", "900", "875", "850", "800", "750", "700", "650", "600", "550", "500",
          "400", "300", "250", "200", "150", "100")


def nc_path(cache: Path, day: date, hour: int) -> Path:
    ymd = day.strftime("%Y%m%d")
    return Path(cache) / ymd / f"era5_pl_{ymd}_{int(hour) % 24:02d}00.nc"


def area_nwse(lon, lat, buffer_deg: float) -> tuple[float, float, float, float]:
    """CDS ``area`` (north, west, south, east) around the points."""
    import numpy as np
    return (float(np.nanmax(lat) + buffer_deg), float(np.nanmin(lon) - buffer_deg),
            float(np.nanmin(lat) - buffer_deg), float(np.nanmax(lon) + buffer_deg))


def covers(path: Path, area: tuple[float, float, float, float], tol: float = 0.5) -> bool:
    """The cached file's grid contains ``area`` (within ``tol`` degrees)."""
    import xarray as xr
    with xr.open_dataset(path) as ds:
        la = ds["latitude" if "latitude" in ds.coords else "lat"].values
        lo = ds["longitude" if "longitude" in ds.coords else "lon"].values
    lo = (lo + 180.0) % 360.0 - 180.0
    n, w, s, e = area
    return la.max() + tol >= n and la.min() - tol <= s and lo.min() - tol <= w and lo.max() + tol >= e


def download(cache: Path, day: date, hour: int, area, levels=LEVELS) -> Path:
    out = nc_path(cache, day, hour)
    if out.exists() and out.stat().st_size > 0:
        return out
    import cdsapi
    out.parent.mkdir(parents=True, exist_ok=True)
    req = {"product_type": "reanalysis", "data_format": "netcdf",
           "variable": ["geopotential", "temperature", "relative_humidity"], "pressure_level": list(levels),
           "year": f"{day.year}", "month": f"{day.month:02d}", "day": f"{day.day:02d}",
           "time": f"{int(hour) % 24:02d}:00", "area": [round(v, 3) for v in area]}
    tmp = out.with_suffix(".part")
    cdsapi.Client(quiet=True).retrieve(DATASET, req, str(tmp))
    tmp.replace(out)
    return out


def fetch(cache: Path, requests: list[tuple[date, int]], area, *, auto_download: bool, levels=LEVELS,
          workers: int = 4) -> dict[tuple[date, int], Path | None]:
    """Path of every (day, hour) file, downloading the missing ones when ``auto_download``; None if unavailable.
    A cached file not covering ``area`` (another project) is downloaded again."""
    out: dict[tuple[date, int], Path | None] = {}
    missing = []
    for d, h in sorted(set(requests)):
        p = nc_path(cache, d, h)
        if p.exists() and p.stat().st_size > 0 and covers(p, area):
            out[(d, h)] = p
        else:
            out[(d, h)] = None
            missing.append((d, h))
    if missing and auto_download:
        log.info("ERA5: downloading %d file(s) from CDS", len(missing))

        def one(k):
            d, h = k
            p = nc_path(cache, d, h)
            if p.exists():
                p.unlink()                           # stale (does not cover the area)
            try:
                return k, download(cache, d, h, area, levels)
            except Exception as exc:                 # one failed date falls back to the linear APS
                log.warning("ERA5 %s %02d:00: download failed (%s: %s)", d, h, type(exc).__name__, exc)
                return k, None

        with ThreadPoolExecutor(max(1, workers)) as pool:
            for k, p in pool.map(one, missing):
                out[k] = p
    elif missing:
        log.warning("ERA5: %d file(s) not in the cache %s and auto_download is off", len(missing), cache)
    return out
