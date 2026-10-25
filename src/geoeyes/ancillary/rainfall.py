"""Monthly rainfall over an AOI from CHIRPS v3 (Climate Hazards Center, 0.05°, global land), read from the
cloud-optimized GeoTIFFs over HTTP (only the AOI window), cached per AOI under ``<workspace>/cache/rainfall``.

Rainfall helps reading seasonal motion (clay swelling / shrinking, groundwater recharge) against the time series.
CHIRPS is published about a month after the month ends; later months are simply absent.

``monthly`` gives the AOI mean (the time-series panel); ``monthly_grid`` / ``annual_grid`` keep every CHIRPS pixel
(the hazard analysis, ``geoeyes.hazard``: rainfall coupling per pixel and the annual climatology). ``era5_grid`` is
the fallback (ERA5 reanalysis through the Open-Meteo archive API) when the CHIRPS server refuses: it throttles
clients that read many files.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/monthly/global/cogs/chirps-v3.0.{y}.{m:02d}.cog"
SOURCE = "CHIRPS v3.0 monthly (Climate Hazards Center, UC Santa Barbara)"


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _read_month(y: int, m: int, bbox: list[float]) -> float | None:
    """Mean monthly rainfall (mm) over the bbox (at least the pixel holding its centre)."""
    import rasterio
    from rasterio.windows import from_bounds
    w, s, e, n = bbox
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".cog",
           "GDAL_HTTP_TIMEOUT": "60"}
    try:
        with rasterio.Env(**env), rasterio.open(f"/vsicurl/{URL.format(y=y, m=m)}") as src:
            px = src.res[0]
            cx, cy = (w + e) / 2, (s + n) / 2
            w, e = min(w, cx - px / 2), max(e, cx + px / 2)          # never smaller than one pixel
            s, n = min(s, cy - px / 2), max(n, cy + px / 2)
            win = from_bounds(w, s, e, n, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win, masked=True).astype(np.float64)
            a = np.ma.masked_less(a, 0)                               # -9999: ocean / no data
            return None if a.count() == 0 else round(float(a.mean()), 1)
    except Exception as exc:                                         # a month not published yet, or no network
        if re.search(r"HTTP response code: (403|429)", str(exc)):
            raise Refused(str(exc)) from None
        log.debug("CHIRPS %d-%02d unavailable: %s", y, m, exc)
        return None


ANNUAL_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/annual/global/tifs/chirps-v3.0.{y}.tif"
RES = 0.05                       # CHIRPS pixel (deg); pixel edges on multiples of 0.05 from -180 / 50 S
_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".cog,.tif",
        "GDAL_HTTP_TIMEOUT": "60", "GDAL_HTTP_USERAGENT": "GeoEyes (InSAR rainfall analysis)"}


class Refused(Exception):
    """The CHIRPS server refused a request (HTTP 403 / 429): it throttles clients that ask too much at once."""


@dataclass
class RainGrid:
    """Rainfall on the CHIRPS pixels covering an AOI: ``mm[t, row, col]`` (NaN = not published / no data);
    row 0 = north. ``periods`` are ``YYYY-MM`` (monthly) or ``YYYY`` (annual)."""

    periods: list[str]
    mm: np.ndarray
    west: float                  # outer edges of the pixel block
    north: float
    res: float = RES
    refused: str = ""            # why some periods could not be read (server throttling), "" if none
    source: str = SOURCE

    @property
    def shape(self) -> tuple[int, int]:
        return self.mm.shape[1], self.mm.shape[2]

    def pixel(self, lon, lat) -> tuple[np.ndarray, np.ndarray]:
        """(row, col) of the pixel holding each location, clipped to the block."""
        ny, nx = self.shape
        r = np.clip(np.floor((self.north - np.asarray(lat, float)) / self.res).astype(int), 0, ny - 1)
        c = np.clip(np.floor((np.asarray(lon, float) - self.west) / self.res).astype(int), 0, nx - 1)
        return r, c

    def centre(self, row: int, col: int) -> tuple[float, float]:
        return self.west + (col + 0.5) * self.res, self.north - (row + 0.5) * self.res


def _snap(bbox: list[float]) -> tuple[float, float, float, float]:
    """The bbox grown to whole CHIRPS pixels (at least one)."""
    w, s, e, n = bbox
    f = 1 / RES
    w, s = np.floor(w * f + 1e-9) / f, np.floor(s * f + 1e-9) / f
    e, n = np.ceil(e * f - 1e-9) / f, np.ceil(n * f - 1e-9) / f
    return (round(float(w), 2), round(float(s), 2), round(float(max(e, w + RES)), 2),
            round(float(max(n, s + RES)), 2))


def _read_block(url: str, box: tuple[float, float, float, float]) -> np.ndarray | None:
    import rasterio
    from rasterio.windows import from_bounds
    w, s, e, n = box
    quiet = logging.getLogger("rasterio._env")                       # GDAL's own message would repeat ours
    level = quiet.level
    quiet.setLevel(logging.CRITICAL)
    try:
        with rasterio.Env(**_ENV), rasterio.open(f"/vsicurl/{url}") as src:
            win = from_bounds(w, s, e, n, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win, boundless=True, fill_value=-9999).astype(np.float32)
            a[a < 0] = np.nan                                         # -9999: ocean / no data
            return a
    except Exception as exc:                                         # not published yet, or no network
        if re.search(r"HTTP response code: (403|429)", str(exc)):
            raise Refused(str(exc)) from None
        log.debug("CHIRPS %s unavailable: %s", url, exc)
        return None
    finally:
        quiet.setLevel(level)


def _grid(cache: Path, kind: str, url_of, keys: list[str], bbox: list[float]) -> RainGrid:
    """Pixel blocks of ``keys`` (months or years), cached per snapped bbox in ``<cache>/chirps3_<kind>_<box>.npz``;
    published periods are kept for good, missing ones are asked again next time.

    One request at a time: the Climate Hazards Center server blocks clients that read many files in parallel;
    a refusal stops the reading (what was read is kept) and is reported in ``RainGrid.refused``."""
    box = _snap(bbox)
    ny, nx = round((box[3] - box[1]) / RES), round((box[2] - box[0]) / RES)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"chirps3_{kind}_{'_'.join(f'{v:.2f}' for v in box)}.npz"
    known: dict[str, np.ndarray] = {}
    if f.exists():
        with np.load(f) as z:
            known = {str(k): z["mm"][i] for i, k in enumerate(z["keys"])}
    todo = [k for k in keys if k not in known]
    refused = ""
    if todo:
        log.info("CHIRPS %s: reading %d period(s) over %s", kind, len(todo), box)
        before = len(known)
        for k in todo:
            try:
                a = _read_block(url_of(k), box)
            except Refused as exc:
                refused = f"CHIRPS server refused the request ({exc}); try again later"
                log.warning("%s", refused)
                break
            if a is not None and a.shape == (ny, nx):
                known[k] = a
        if len(known) > before:
            ks = sorted(known)
            np.savez(f, keys=np.array(ks), mm=np.stack([known[k] for k in ks]))
    mm = np.stack([known.get(k, np.full((ny, nx), np.nan, np.float32)) for k in keys]) if keys else \
        np.zeros((0, ny, nx), np.float32)
    return RainGrid(list(keys), mm.astype(np.float32), box[0], box[3], refused=refused)


def monthly_grid(cache: Path, bbox: list[float], start: date, end: date) -> RainGrid:
    """Monthly rainfall (mm) per CHIRPS pixel over the bbox, months from ``start`` to ``end``."""
    keys = [f"{y}-{m:02d}" for y, m in _months(start, end)]
    return _grid(cache, "monthly", lambda k: URL.format(y=int(k[:4]), m=int(k[5:])), keys, bbox)


def annual_grid(cache: Path, bbox: list[float], first: int, last: int) -> RainGrid:
    """Annual rainfall totals (mm) per CHIRPS pixel, years ``first`` to ``last``."""
    keys = [str(y) for y in range(first, last + 1)]
    return _grid(cache, "annual", lambda k: ANNUAL_URL.format(y=int(k)), keys, bbox)


ERA5_URL = "https://archive-api.open-meteo.com/v1/archive"
ERA5_SOURCE = "ERA5 reanalysis daily precipitation (ECMWF / Copernicus), via the Open-Meteo archive API"
ERA5_RES = 0.25


def era5_grid(cache: Path, bbox: list[float], start: date, end: date) -> tuple[RainGrid, RainGrid]:
    """(monthly, annual) rainfall from ERA5 on its 0.25° grid over the bbox, from daily sums (one request for
    every grid point; months with a missing day are NaN). The fallback when CHIRPS cannot be read: a reanalysis
    smooths convective peaks, so monthly extremes are lower than CHIRPS."""
    import urllib.parse
    import urllib.request
    w, s, e, n = bbox
    f = 1 / ERA5_RES
    lons = np.arange(np.round(w * f), np.round(e * f) + 1) / f
    lats = np.arange(np.round(n * f), np.round(s * f) - 1, -1) / f
    key = f"era5_{lons[0]:.2f}_{lats[-1]:.2f}_{lons[-1]:.2f}_{lats[0]:.2f}_{start}_{end}"
    cache.mkdir(parents=True, exist_ok=True)
    cf = cache / f"{key}.json"
    if cf.exists():
        data = json.loads(cf.read_text(encoding="utf-8"))
    else:
        grid = [(la, lo) for la in lats for lo in lons]
        q = urllib.parse.urlencode({"latitude": ",".join(f"{la:.2f}" for la, _ in grid),
                                    "longitude": ",".join(f"{lo:.2f}" for _, lo in grid),
                                    "start_date": str(start), "end_date": str(end), "daily": "precipitation_sum",
                                    "models": "era5", "timezone": "UTC"})
        req = urllib.request.Request(f"{ERA5_URL}?{q}", headers={"User-Agent": "GeoEyes (InSAR rainfall analysis)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        data = data if isinstance(data, list) else [data]
        if end < date.today().replace(day=1):                      # complete past period: cache for good
            cf.write_text(json.dumps(data), encoding="utf-8")
    import pandas as pd
    months = [f"{y}-{m:02d}" for y, m in _months(start, end)]
    years = sorted({k[:4] for k in months})
    mm = np.full((len(months), lats.size, lons.size), np.nan, np.float32)
    ann = np.full((len(years), lats.size, lons.size), np.nan, np.float32)
    for i, d in enumerate(data):
        r_, c_ = divmod(i, lons.size)
        sr = pd.Series(d["daily"]["precipitation_sum"], index=pd.to_datetime(d["daily"]["time"]), dtype=float)
        mo = sr.resample("MS").agg(lambda x: x.sum() if len(x) and x.notna().all()
                                   and len(x) == x.index[0].days_in_month else np.nan)       # whole months only
        mo.index = mo.index.strftime("%Y-%m")
        mm[:, r_, c_] = mo.reindex(months).to_numpy(np.float32)
        yr = sr.resample("YS").agg(lambda x: x.sum() if x.notna().sum() >= 360 else np.nan)
        yr.index = yr.index.strftime("%Y")
        ann[:, r_, c_] = yr.reindex(years).to_numpy(np.float32)
    west, north = lons[0] - ERA5_RES / 2, lats[0] + ERA5_RES / 2
    return (RainGrid(months, mm, west, north, ERA5_RES, source=ERA5_SOURCE),
            RainGrid(years, ann, west, north, ERA5_RES, source=ERA5_SOURCE))


def monthly(cache: Path, bbox: list[float], start: date, end: date) -> dict:
    """``{"source", "bbox", "months": [{"month": "YYYY-MM", "mm": value or None}]}``; published months are cached
    for good, missing recent ones are asked again next time. When CHIRPS gives nothing (the server refuses, or no
    network to it), the ERA5 mean over the bbox is returned instead, with its source."""
    cache.mkdir(parents=True, exist_ok=True)
    key = "_".join(f"{v:.3f}" for v in bbox)
    f = cache / f"chirps3_{key}.json"
    known: dict[str, float] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    out = []
    changed = False
    refused = False
    for y, m in _months(start, end):
        k = f"{y}-{m:02d}"
        if k not in known and not refused:
            try:
                v = _read_month(y, m, bbox)
            except Refused as exc:
                log.warning("CHIRPS server refused the request (%s)", exc)
                refused, v = True, None
            if v is not None:
                known[k] = v
                changed = True
        out.append({"month": k, "mm": known.get(k)})
    if changed:
        f.write_text(json.dumps(known, indent=0), encoding="utf-8")
    if out and all(o["mm"] is None for o in out):
        try:
            last = (np.datetime64(f"{end:%Y-%m}") + 1).astype("datetime64[D]") - 1      # whole months
            grid, _ = era5_grid(cache, bbox, start.replace(day=1), min(last.astype(date), date.today()))
            means = np.nanmean(grid.mm.reshape(len(grid.periods), -1), axis=1) if grid.periods else []
            by = {k: (None if not np.isfinite(v) else round(float(v), 1)) for k, v in zip(grid.periods, means,
                                                                                            strict=True)}
            return {"source": ERA5_SOURCE, "bbox": bbox,
                    "months": [{"month": o["month"], "mm": by.get(o["month"])} for o in out]}
        except Exception as exc:                                     # no network at all: the empty CHIRPS answer
            log.warning("ERA5 fallback unavailable: %s", exc)
    return {"source": SOURCE, "bbox": bbox, "months": out}
