"""CERRA zenith delays: the Copernicus European Regional ReAnalysis (SMHI / C3S), 5.5 km Lambert conformal grid
over Europe (North Africa to beyond Scandinavia, far into the Atlantic: the Canary Islands and the Azores are in),
analyses every 3 hours, pressure levels, September 1984 to present (monthly updates).

Same physics as ERA5 (``era5.delays``): profiles integrated per model column, interpolated bilinearly to every point
at its height, and linearly in time between the two analyses around the acquisition. Files come from the Climate
Data Store with the ERA5 credentials (``~/.cdsapirc``; the CERRA licence accepted once on the CDS website), one
GRIB per analysis time for the whole domain (CDS does not cut the Lambert grid): ~125 MB each, shared by every
project in Europe. Cache: ``<cache>/<YYYYMMDD>/cerra_pl_<YYYYMMDD>_<HH>00.grib``.
GRIB is read with GDAL (``ReadRaster``, without ``gdal_array``), units kept as stored (K, %, m²/s²).
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import numpy as np

from geoeyes.core import netrate
from geoeyes.processing.atmosphere.era5 import time_interpolated
from geoeyes.processing.atmosphere.era5.delays import grid_delays

log = logging.getLogger(__name__)

DATASET = "reanalysis-cerra-pressure-levels"
STEP_H = 3
# up to 100 hPa as ERA5 (CERRA has no 650 / 550 hPa, but 825 hPa)
LEVELS = ("1000", "975", "950", "925", "900", "875", "850", "825", "800", "750", "700", "600", "500", "400", "300",
          "250", "200", "150", "100")
PROJ = "+proj=lcc +lat_0=50 +lon_0=8 +lat_1=50 +lat_2=50 +x_0=0 +y_0=0 +R=6371229 +units=m +no_defs"
N = 1069                                          # columns = rows
DX = 5500.0
X0, Y0 = -2939750.0, 2939750.0                    # outer corner (west, north) of the grid
MARGIN = 3                                        # cells around the points read from the file


def _transformer(inverse: bool = False):
    from pyproj import Transformer
    return Transformer.from_crs(PROJ, "EPSG:4326", always_xy=True) if inverse else \
        Transformer.from_crs("EPSG:4326", PROJ, always_xy=True)


def to_grid(lon, lat) -> tuple[np.ndarray, np.ndarray]:
    """Fractional (column, row) of points, row 0 = north; pixel centres at integers."""
    lon, lat = np.atleast_1d(np.asarray(lon, np.float64)), np.atleast_1d(np.asarray(lat, np.float64))
    n = lon.size                                       # pyproj takes a 1-element array for a scalar: pad it
    x, y = _transformer().transform(np.r_[lon, lon[:1]], np.r_[lat, lat[:1]])
    return (np.asarray(x)[:n] - X0) / DX - 0.5, (Y0 - np.asarray(y)[:n]) / DX - 0.5


def covers(lon, lat) -> bool:
    """Every point inside the grid, ``MARGIN`` cells away from its edge."""
    c, r = to_grid(np.atleast_1d(lon), np.atleast_1d(lat))
    return bool(np.all((c >= MARGIN) & (c <= N - 1 - MARGIN) & (r >= MARGIN) & (r <= N - 1 - MARGIN)))


def outline(step: int = 24) -> list[list[float]]:
    """The grid edge as a lon/lat ring (for the coverage map)."""
    e = np.arange(0, N + step, step).clip(0, N)
    cols = np.r_[e, np.full(e.size, N), e[::-1], np.zeros(e.size)]
    rows = np.r_[np.zeros(e.size), e, np.full(e.size, N), e[::-1]]
    lon, lat = _transformer(inverse=True).transform(X0 + cols * DX, Y0 - rows * DX)
    return [[round(float(a), 3), round(float(b), 3)] for a, b in zip(lon, lat, strict=True)]


def grib_path(cache: Path, day: date, hour: int) -> Path:
    ymd = day.strftime("%Y%m%d")
    return Path(cache) / ymd / f"cerra_pl_{ymd}_{int(hour) % 24:02d}00.grib"


def _request(day: date, hour: int, levels=LEVELS) -> dict:
    return {"variable": ["geopotential", "temperature", "relative_humidity"], "pressure_level": list(levels),
            "data_type": ["reanalysis"], "product_type": ["analysis"], "year": [f"{day.year}"],
            "month": [f"{day.month:02d}"], "day": [f"{day.day:02d}"], "time": [f"{int(hour) % 24:02d}:00"],
            "data_format": "grib"}


def _client():
    """CDS client from ~/.cdsapirc (the ``cdsapi`` credentials)."""
    import re

    from ecmwf.datastores import Client
    text = (Path.home() / ".cdsapirc").read_text(encoding="utf-8")
    return Client(url=re.search(r"url:\s*(\S+)", text).group(1), key=re.search(r"key:\s*(\S+)", text).group(1))


# CERRA comes from the ECMWF tape archive: a request can wait hours in the CDS queue. Requests are submitted
# without blocking and their ids kept in <cache>/pending.json, so a run that stops waiting (``max_wait_min``) does
# not lose its place: the next run (any project) collects the files instead of queueing again.
PENDING = "pending.json"


def _key(day: date, hour: int) -> str:
    return f"{day:%Y%m%d}_{int(hour) % 24:02d}"


def _load_pending(cache: Path) -> dict[str, str]:
    try:
        return dict(json.loads((Path(cache) / PENDING).read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return {}


def _save_pending(cache: Path, pending: dict[str, str]) -> None:
    p = Path(cache) / PENDING
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pending, indent=1), encoding="utf-8")


def download_all(cache: Path, keys: list[tuple[date, int]], *, levels=LEVELS, max_wait_min: float = 20,
                 poll_s: float = 30, client=None) -> dict[tuple[date, int], Path]:
    """Submit (or find again) one CDS request per analysis time and download those ready within ``max_wait_min``;
    the others stay queued at CDS for the next run. Returns the files obtained."""
    client = client or _client()
    pending = _load_pending(cache)
    remotes = {}
    for k in keys:
        rid = pending.get(_key(*k))
        r = None
        if rid:
            try:
                r = client.get_remote(rid)
                if r.status in ("failed", "rejected", "dismissed", "deleted"):
                    r = None
            except Exception:                         # expired or deleted at CDS: ask again
                r = None
        if r is None:
            r = client.submit(DATASET, _request(*k, levels))
            pending[_key(*k)] = r.request_id
        remotes[k] = r
    _save_pending(cache, pending)
    got: dict[tuple[date, int], Path] = {}
    t0, last_log = time.monotonic(), 0.0
    while remotes:
        for k, r in list(remotes.items()):
            try:
                status = r.status
            except Exception as exc:                  # a network hiccup: ask again next round
                log.debug("CERRA %s: status unknown (%s)", _key(*k), exc)
                continue
            if status == "successful":
                out = grib_path(cache, *k)
                out.parent.mkdir(parents=True, exist_ok=True)
                tmp = out.with_suffix(".part")
                try:
                    r.download(str(tmp))
                except Exception as exc:
                    log.warning("CERRA %s: download failed (%s), retried next round", _key(*k), exc)
                    tmp.unlink(missing_ok=True)
                    continue
                netrate.add(tmp.stat().st_size)
                tmp.replace(out)
                got[k] = out
            elif status in ("failed", "rejected", "dismissed", "deleted"):
                log.warning("CERRA %s: request %s at CDS", _key(*k), status)
            else:
                continue
            del remotes[k]
            pending.pop(_key(*k), None)
            _save_pending(cache, pending)
        waited = time.monotonic() - t0
        if not remotes:
            break
        if waited >= max_wait_min * 60:
            log.warning("CERRA: %d request(s) still queued at CDS after %.0f min; this run continues without them "
                        "(linear APS for those dates), the next run collects them", len(remotes), waited / 60)
            break
        if waited - last_log >= 300 or last_log == 0:
            states = [getattr(r, "status", "?") for r in remotes.values()]
            log.info("CERRA: %d/%d file(s) ready, %d running, %d queued at CDS (waiting up to %.0f min)",
                     len(got), len(keys), states.count("running"), states.count("accepted"), max_wait_min)
            last_log = max(waited, 1.0)
        time.sleep(poll_s)
    return got


def fetch(cache: Path, requests: list[tuple[date, int]], *, auto_download: bool, levels=LEVELS,
          max_wait_min: float = 20) -> dict[tuple[date, int], Path | None]:
    out: dict[tuple[date, int], Path | None] = {}
    missing = []
    for d, h in sorted(set(requests)):
        p = grib_path(cache, d, h)
        ok = p.exists() and p.stat().st_size > 0
        out[(d, h)] = p if ok else None
        if not ok:
            missing.append((d, h))
    if missing and auto_download:
        log.info("CERRA: requesting %d analysis file(s) from CDS (~125 MB each, whole domain; tape archive, the "
                 "queue can take hours)", len(missing))
        try:
            out.update(download_all(cache, missing, levels=levels, max_wait_min=max_wait_min))
        except Exception as exc:                     # CDS unreachable: every date falls back to the linear APS
            log.warning("CERRA: CDS request failed (%s: %s)", type(exc).__name__, exc)
    elif missing:
        log.warning("CERRA: %d file(s) not in the cache %s and auto_download is off", len(missing), cache)
    return out


@contextmanager
def gdal_option(key: str, value: str):
    """A GDAL configuration option for the duration of the block, the previous value restored after
    (``gdal.config_options`` exists only from GDAL 3.7; the conda environment has 3.6)."""
    from osgeo import gdal
    old = gdal.GetConfigOption(key)
    gdal.SetConfigOption(key, value)
    try:
        yield
    finally:
        gdal.SetConfigOption(key, old)


def read_window(path: Path, c0: int, c1: int, r0: int, r1: int):
    """(T K, RH %, geopotential m²/s², levels hPa) of the window rows r0:r1, columns c0:c1, arrays (row, col, level)
    with rows from north to south and levels from the surface up."""
    from osgeo import gdal
    gdal.UseExceptions()
    with gdal_option("GRIB_NORMALIZE_UNITS", "NO"):
        ds = gdal.Open(str(path))
        fields: dict[str, dict[float, np.ndarray]] = {"t": {}, "r": {}, "z": {}}
        names = {"TMP": "t", "RH": "r", "HGT": "z", "GP": "z", "FI": "z"}
        for b in range(1, ds.RasterCount + 1):
            band = ds.GetRasterBand(b)
            md = band.GetMetadata()
            var = names.get(md.get("GRIB_ELEMENT", ""))
            short = md.get("GRIB_SHORT_NAME", "")
            if var is None or not short.endswith("-ISBL"):
                continue
            lev = float(short.split("-")[0]) / 100.0            # Pa -> hPa
            raw = band.ReadRaster(c0, r0, c1 - c0, r1 - r0, buf_type=gdal.GDT_Float64)
            a = np.frombuffer(raw, np.float64).reshape(r1 - r0, c1 - c0)
            if var == "z" and md.get("GRIB_ELEMENT") == "HGT":
                a = a * 9.80665                                   # geopotential height -> geopotential
            fields[var][lev] = a
        ds = None
    levels = sorted(set(fields["t"]) & set(fields["r"]) & set(fields["z"]), reverse=True)
    if len(levels) < 3:
        raise ValueError(f"{path}: temperature / humidity / geopotential missing on pressure levels")
    stack = [np.stack([fields[v][lv] for lv in levels], axis=-1) for v in ("t", "r", "z")]
    return stack[0], stack[1], stack[2], np.asarray(levels, np.float64)


def delays_at_points(path: Path, lon, lat, h_m) -> tuple[np.ndarray, np.ndarray]:
    """Zenith hydrostatic and wet delays (m) at points (deg, height above the geoid); NaN outside the grid."""
    c, r = to_grid(lon, lat)
    far = (c < 0) | (c > N - 1) | (r < 0) | (r > N - 1)
    cc, rr = np.clip(c, 0, N - 1), np.clip(r, 0, N - 1)
    c0, c1 = max(int(np.floor(cc.min())) - MARGIN, 0), min(int(np.ceil(cc.max())) + MARGIN + 1, N)
    r0, r1 = max(int(np.floor(rr.min())) - MARGIN, 0), min(int(np.ceil(rr.max())) + MARGIN + 1, N)
    t, rh, z, levels = read_window(path, c0, c1, r0, r1)
    t, rh, z = t[::-1], rh[::-1], z[::-1]             # south to north: rows with increasing y
    ys = -np.arange(r1 - 1, r0 - 1, -1, dtype=np.float64)   # minus the row number: increasing northwards
    xs = np.arange(c0, c1, dtype=np.float64)
    gx, gy = np.meshgrid(X0 + (xs + 0.5) * DX, Y0 - (-ys + 0.5) * DX)
    lat_grid = _transformer(inverse=True).transform(gx, gy)[1]
    return grid_delays(t, rh, z, levels, ys, xs, lat_grid, -rr, cc, h_m, far)


def zenith_delays(lon, lat, hgt, times: dict[date, datetime], cache: Path, *, auto_download: bool = True,
                  levels=LEVELS, max_wait_min: float = 20) -> tuple[np.ndarray, np.ndarray]:
    """Hydrostatic and wet zenith delays (m), each (n, n_epoch) in the order of ``times``; NaN for epochs without
    CERRA (not yet published) and for points outside the domain."""
    if not covers(lon, lat):
        log.warning("CERRA: the points are outside the European domain (or within %d cells of its edge)", MARGIN)
    return time_interpolated(
        np.asarray(lon).size, times, STEP_H,
        lambda need: fetch(Path(cache), need, auto_download=auto_download, levels=levels, max_wait_min=max_wait_min),
        lambda p: delays_at_points(p, lon, lat, hgt), "CERRA")


__all__ = ["covers", "outline", "zenith_delays"]
