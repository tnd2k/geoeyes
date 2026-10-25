"""DEM access: ellipsoidal heights at lat/lon (port of ``modules/utils/dem.py``).

Sources:
  * SRTM 1" tiles ``N19W099.SRTMGL1.hgt(.zip)`` in a folder — by default SNAP's cache
    ``~/.snap/auxdata/dem/SRTM 1Sec HGT`` (heights above the EGM96 geoid), missing tiles downloaded from
    the ESA mirror SNAP uses;
  * Copernicus GLO-30 (``copernicus-30``, EGM2008), tiles downloaded from AWS open data into the workspace
    cache — also covers latitudes above 60 deg where SRTM has no data;
  * any single-band GeoTIFF in EPSG:4326 (pass ``datum``).

Orthometric heights become ellipsoidal with the EGM96 15' grid shipped with SNAP
(``~/.snap/auxdata/dem/egm96/ww15mgh_b.zip``). EGM96 and EGM2008 differ by well under a metre over
most land, so EGM96 is also used for EGM2008 DEMs.
"""
from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

from geoeyes.core.errors import DataError

log = logging.getLogger(__name__)

SNAP_DEM_ROOT = Path.home() / ".snap" / "auxdata" / "dem"
SRTM1_DIR = SNAP_DEM_ROOT / "SRTM 1Sec HGT"
EGM96_ZIP = SNAP_DEM_ROOT / "egm96" / "ww15mgh_b.zip"
SRTM1_URL = "https://step.esa.int/auxdata/dem/SRTMGL1/"           # the mirror SNAP downloads from
GLO30_URL = "https://copernicus-dem-30m.s3.amazonaws.com/"        # Copernicus GLO-30 COGs (AWS open data)


def _sample(grid: np.ndarray, r: np.ndarray, c: np.ndarray, order: int = 1, **kw) -> np.ndarray:
    """Spline sample of ``grid`` at fractional (row, col) of any shape."""
    shape = np.shape(r)
    r, c = np.ravel(r).astype(float), np.ravel(c).astype(float)
    for v, n in ((r, grid.shape[0] - 1), (c, grid.shape[1] - 1)):
        cl = np.clip(v, 0, n)
        near = np.abs(v - cl) < 1e-6
        v[near] = cl[near]
    out = map_coordinates(grid, [r, c], order=order, **kw)
    return out.reshape(shape) if shape else out[0]


class Geoid:
    """EGM96 undulation N (m) from the NGA 15' text grid (north-to-south rows, lon 0..360)."""

    def __init__(self, path: Path = EGM96_ZIP):
        path = Path(path)
        if not path.exists():
            raise DataError(f"geoid grid not found: {path}")
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                text = zf.read(zf.namelist()[0]).decode("ascii")
        else:
            text = path.read_text(encoding="ascii")
        vals = np.array(text.split(), dtype=float)
        self.lat_min, self.lat_max, self.lon_min, self.lon_max, self.dlat, self.dlon = vals[:6]
        ny = int(round((self.lat_max - self.lat_min) / self.dlat)) + 1
        nx = int(round((self.lon_max - self.lon_min) / self.dlon)) + 1
        self.grid = vals[6:6 + ny * nx].reshape(ny, nx)

    def undulation(self, lat, lon) -> np.ndarray:
        lat, lon = np.broadcast_arrays(np.asarray(lat, float), np.asarray(lon, float))
        r = (self.lat_max - lat) / self.dlat
        c = np.mod(lon - self.lon_min, 360.0) / self.dlon
        return _sample(self.grid, r, c, mode="nearest")


@dataclass
class Dem:
    """Regular lat/lon grid; ``height`` is orthometric (datum != 'ellipsoid') or ellipsoidal."""

    height: np.ndarray           # (ny, nx), NaN = void; row 0 = north edge
    lat0: float                  # latitude of row 0 (pixel centre)
    lon0: float                  # longitude of column 0 (pixel centre)
    dlat: float                  # > 0, rows go south
    dlon: float
    datum: str                   # 'EGM96' | 'EGM2008' | 'ellipsoid'
    source: str
    geoid: Geoid | None = None

    def orthometric(self, lat, lon, order: int = 1) -> np.ndarray:
        lat, lon = np.broadcast_arrays(np.asarray(lat, float), np.asarray(lon, float))
        r = (self.lat0 - lat) / self.dlat
        c = (lon - self.lon0) / self.dlon
        h = _sample(np.nan_to_num(self.height, nan=-1e4), r, c, order=order, mode="constant", cval=np.nan)
        return np.where(h < -1e3, np.nan, h)       # a void in the neighbourhood -> NaN

    def ellipsoidal(self, lat, lon, order: int = 1) -> np.ndarray:
        h = self.orthometric(lat, lon, order)
        if self.datum == "ellipsoid":
            return h
        if self.geoid is None:
            self.geoid = Geoid()
        return h + self.geoid.undulation(lat, lon)

    def covers(self, lat, lon) -> bool:
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        s = self.lat0 - (self.height.shape[0] - 1) * self.dlat
        e = self.lon0 + (self.height.shape[1] - 1) * self.dlon
        return bool(np.all((lat <= self.lat0) & (lat >= s) & (lon >= self.lon0) & (lon <= e)))


def _srtm_tile_name(lat: int, lon: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


def _read_hgt(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".hgt"))
            raw = zf.read(name)
    else:
        raw = path.read_bytes()
    n = int(round(np.sqrt(len(raw) // 2)))
    a = np.frombuffer(raw, dtype=">i2").reshape(n, n).astype(np.float32)
    a[a == -32768] = np.nan
    return a


def _download(url: str, dest: Path, attempts: int = 3) -> bool:
    """``url`` -> ``dest`` (atomic); False when the server has no such file (404: an all-ocean tile)."""
    import time

    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    for k in range(1, attempts + 1):
        try:
            with requests.get(url, stream=True, timeout=300) as r:
                if r.status_code == 404:
                    return False
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
            log.info("downloaded DEM tile %s", dest.name)
            return True
        except requests.RequestException as exc:
            if k == attempts:
                raise DataError(f"DEM tile download failed: {url} ({exc})") from exc
            time.sleep(5 * k)
    return False


def load_srtm1(south: float, north: float, west: float, east: float, folder: Path = SRTM1_DIR, *,
               download: bool | None = None) -> Dem:
    """Mosaic the SRTM 1" tiles covering the box (tiles share their edge rows/columns). Missing tiles are
    downloaded from the ESA mirror SNAP uses (``download``, default: only into SNAP's own cache); a tile the
    server does not have is ocean (0 m)."""
    folder = Path(folder)
    if download is None:
        download = folder == SRTM1_DIR
    lats = range(int(np.floor(south)), int(np.floor(north)) + 1)
    lons = range(int(np.floor(west)), int(np.floor(east)) + 1)
    rows, missing = [], []
    for la in sorted(lats, reverse=True):
        row = []
        for lo in lons:
            name = _srtm_tile_name(la, lo)
            hits = list(folder.glob(f"{name}*.hgt*")) if folder.is_dir() else []
            if not hits and download:
                dest = folder / f"{name}.SRTMGL1.hgt.zip"
                if _download(f"{SRTM1_URL}{dest.name}", dest):
                    hits = [dest]
                else:
                    log.info("SRTM tile %s does not exist (ocean): 0 m", name)
                    row.append(np.zeros((3601, 3601), np.float32))
                    continue
            if not hits:
                missing.append(name)
                row.append(None)
                continue
            row.append(_read_hgt(hits[0]))
        rows.append(row)
    if missing:
        raise DataError(f"missing SRTM 1\" tiles in {folder}: {', '.join(missing)}")
    n = rows[0][0].shape[0]
    mosaic = np.vstack([np.hstack([t if j == 0 else t[:, 1:] for j, t in enumerate(r)]) if i == 0 else
                        np.hstack([t[1:] if j == 0 else t[1:, 1:] for j, t in enumerate(r)])
                        for i, r in enumerate(rows)])
    step = 1.0 / (n - 1)
    return Dem(mosaic, float(max(lats) + 1), float(min(lons)), step, step, "EGM96", f"SRTM 1\" ({folder})")


def load_geotiff(path: Path, datum: str = "EGM2008", bbox=None) -> Dem:
    """Single-band GeoTIFF in EPSG:4326, optionally windowed by bbox = (south, north, west, east)."""
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as ds:
        if ds.crs is not None and not ds.crs.is_geographic:
            raise DataError(f"{path}: DEM must be geographic (EPSG:4326), got {ds.crs}")
        win = None
        if bbox is not None:
            s, n, w, e = bbox
            pad = 0.01
            t = ds.transform
            c0 = max(int(np.floor((w - pad - t.c) / t.a)), 0)
            c1 = min(int(np.ceil((e + pad - t.c) / t.a)), ds.width)
            r0 = max(int(np.floor((t.f - (n + pad)) / -t.e)), 0)
            r1 = min(int(np.ceil((t.f - (s - pad)) / -t.e)), ds.height)
            if c1 <= c0 or r1 <= r0:
                raise DataError(f"{path}: DEM does not cover {bbox}")
            win = Window(c0, r0, c1 - c0, r1 - r0)
        h = ds.read(1, window=win, masked=True).astype(np.float32).filled(np.nan)
        t = ds.window_transform(win) if win is not None else ds.transform
    return Dem(h, t.f + t.e / 2, t.c + t.a / 2, -t.e, t.a, datum, str(path))


def _glo30_name(lat: int, lon: int) -> str:
    return (f"Copernicus_DSM_COG_10_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_"
            f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM")


def load_copernicus30(south: float, north: float, west: float, east: float, cache: Path) -> Dem:
    """Copernicus GLO-30 (EGM2008 heights) over the box: tiles downloaded once into ``cache`` and mosaicked
    (tiles absent from the archive are ocean, 0 m)."""
    import rasterio
    from rasterio.merge import merge
    cache = Path(cache)
    files = []
    for la in range(int(np.floor(south)), int(np.floor(north)) + 1):
        for lo in range(int(np.floor(west)), int(np.floor(east)) + 1):
            name = _glo30_name(la, lo)
            dest = cache / f"{name}.tif"
            if dest.exists() or _download(f"{GLO30_URL}{name}/{name}.tif", dest):
                files.append(dest)
            else:
                log.info("GLO-30 tile %s does not exist (ocean): 0 m", name)
    if not files:
        raise DataError(f"no Copernicus GLO-30 tile over {south}..{north}, {west}..{east}")
    srcs = [rasterio.open(f) for f in files]
    try:
        step = min(abs(s.transform.a) for s in srcs)     # tiles above 50 deg are coarser in longitude
        mosaic, transform = merge(srcs, bounds=(west - 0.01, south - 0.01, east + 0.01, north + 0.01),
                                  res=(step, step), nodata=np.nan, resampling=rasterio.enums.Resampling.bilinear)
    finally:
        for s in srcs:
            s.close()
    h = np.nan_to_num(mosaic[0].astype(np.float32), nan=0.0)   # outside the tiles = ocean
    return Dem(h, transform.f + transform.e / 2, transform.c + transform.a / 2, -transform.e, transform.a,
               "EGM2008", "Copernicus GLO-30")


def load_dem(source: str | Path | None, south: float, north: float, west: float, east: float,
             datum: str | None = None, cache: Path | None = None) -> Dem:
    """``source``: None/'' or ``srtm-1`` -> SNAP's SRTM 1" cache (missing tiles downloaded); ``copernicus-30`` ->
    Copernicus GLO-30 (downloaded into ``cache``, default ``<workspace>/cache/dem``); a folder -> SRTM tiles
    there; a file -> GeoTIFF."""
    if not source or source == "srtm-1":
        return load_srtm1(south, north, west, east)
    if source == "copernicus-30":
        if cache is None:
            from geoeyes.config.settings import load_settings
            cache = load_settings().workspace_layout().cache_dir("dem")
        return load_copernicus30(south, north, west, east, Path(cache) / "copernicus-30")
    p = Path(source)
    if p.is_dir():
        return load_srtm1(south, north, west, east, p)
    if re.search(r"\.hgt(\.zip)?$", p.name, re.I):
        return load_srtm1(south, north, west, east, p.parent)
    return load_geotiff(p, datum or "EGM2008", (south, north, west, east))
