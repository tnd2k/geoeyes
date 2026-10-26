"""Thematic layers on the analysis grid of a product (docs/en/research/ai-susceptibility.md §3).

The grid is the hazard analysis's grid (same cell size and origin), extended to every cell of the product's
extent, with or without InSAR points. Each layer is a column:

* terrain       ``height_m``, ``slope_deg``             DEM of the project (SRTM 1″ / Copernicus GLO-30)
* land cover    ``lc_built``, ``lc_crop``, ``lc_tree``, ``lc_grass``, ``lc_water``, ``lc_bare``, ``lc_wetland``
                (fraction of the cell)                  ESA WorldCover 10 m 2021 v200
                ``dist_water_m``                        distance to permanent water, from the same map
* buildings     ``bld_count``, ``bld_cover`` (roof fraction), ``bld_height_m`` (area-weighted, where known)
                                                        Overture Maps buildings
* soil          ``soil_clay``  (g/kg, 0–5 cm)            SoilGrids 2.0
* climate       ``rain_annual_mm``                      the rainfall climatology of the hazard analysis

A layer that cannot be read is left empty (NaN) and named in the warnings: the models skip empty columns.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON = 111_320.0
WORLDCOVER = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
SOILGRIDS_CLAY = "https://files.isric.org/soilgrids/latest/data/clay/clay_0-5cm_mean.vrt"
LC_CLASSES = {"lc_tree": 10, "lc_grass": 30, "lc_crop": 40, "lc_built": 50, "lc_bare": 60, "lc_water": 80,
              "lc_wetland": 90}
_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.vrt,.ovr",
        "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_USERAGENT": "GeoEyes (InSAR analysis)"}
LAYERS = {   # column -> (group, label, unit) — the web app shows them as thematic maps
    "height_m": ("terrain", "Elevation", "m"), "slope_deg": ("terrain", "Slope", "°"),
    "lc_built": ("land cover", "Built-up", "fraction"), "lc_crop": ("land cover", "Cropland", "fraction"),
    "lc_tree": ("land cover", "Tree cover", "fraction"), "lc_grass": ("land cover", "Grassland", "fraction"),
    "lc_water": ("land cover", "Water", "fraction"), "lc_bare": ("land cover", "Bare ground", "fraction"),
    "lc_wetland": ("land cover", "Wetland", "fraction"), "dist_water_m": ("land cover", "Distance to water", "m"),
    "bld_count": ("buildings", "Buildings per cell", "count"), "bld_cover": ("buildings", "Roof cover", "fraction"),
    "bld_height_m": ("buildings", "Building height", "m"), "soil_clay": ("soil", "Clay content (0–5 cm)", "g/kg"),
    "rain_annual_mm": ("climate", "Annual rainfall", "mm"),
}


class Grid:
    """Square cells of ``cell_m`` on the local metric grid of latitude ``lat0`` (as the hazard analysis)."""

    def __init__(self, bounds: list[float], cell_m: float, lat0: float):
        self.cell_m, self.lat0 = cell_m, lat0
        self.kx_m = M_PER_DEG_LON * math.cos(math.radians(lat0))
        w, s, e, n = bounds
        x0, x1 = math.floor(w * self.kx_m / cell_m), math.floor(e * self.kx_m / cell_m)
        y0, y1 = math.floor(s * M_PER_DEG_LAT / cell_m), math.floor(n * M_PER_DEG_LAT / cell_m)
        self.x0, self.y0, self.nx, self.ny = x0, y0, x1 - x0 + 1, y1 - y0 + 1
        kx, ky = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        self.kx, self.ky = kx.ravel(), ky.ravel()
        self.lon = (self.kx + 0.5) * cell_m / self.kx_m
        self.lat = (self.ky + 0.5) * cell_m / M_PER_DEG_LAT
        hx, hy = 0.5 * cell_m / self.kx_m, 0.5 * cell_m / M_PER_DEG_LAT
        self.bounds = [float(self.lon.min() - hx), float(self.lat.min() - hy), float(self.lon.max() + hx),
                       float(self.lat.max() + hy)]

    def __len__(self) -> int:
        return len(self.kx)

    def cell_of(self, lon, lat) -> np.ndarray:
        """Grid index of each location (-1 outside); the grid is a full rectangle, row-major from (x0, y0)."""
        kx = np.floor(np.asarray(lon) * self.kx_m / self.cell_m).astype(np.int64) - self.x0
        ky = np.floor(np.asarray(lat) * M_PER_DEG_LAT / self.cell_m).astype(np.int64) - self.y0
        inside = (kx >= 0) & (kx < self.nx) & (ky >= 0) & (ky < self.ny)
        return np.where(inside, ky * self.nx + kx, -1)


# ---------------------------------------------------------------- layers
def terrain(grid: Grid, dem_source: str, cache: Path) -> dict[str, np.ndarray]:
    from geoeyes.hazard.terrain import load_terrain_dem, slope_aspect
    dem = load_terrain_dem(dem_source, grid.bounds, cache, grid.cell_m)
    t = slope_aspect(dem, grid.lon, grid.lat, grid.cell_m)
    return {"height_m": np.asarray(t["height_m"], np.float32), "slope_deg": t["slope_deg"]}


def worldcover(grid: Grid) -> dict[str, np.ndarray]:
    """Land-cover fractions per cell and the mean distance to permanent water (m)."""
    import rasterio
    from rasterio.windows import from_bounds
    from scipy.ndimage import distance_transform_edt
    w, s, e, n = grid.bounds
    out = {k: np.zeros(len(grid), np.float64) for k in LC_CLASSES}
    count = np.zeros(len(grid))
    dist_sum = np.zeros(len(grid))
    tiles = {(la, lo) for la in range(int(math.floor(s / 3) * 3), int(math.floor(n / 3) * 3) + 1, 3)
             for lo in range(int(math.floor(w / 3) * 3), int(math.floor(e / 3) * 3) + 1, 3)}
    for la, lo in sorted(tiles):
        name = f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"
        with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + WORLDCOVER.format(tile=name)) as src:
            win = from_bounds(max(w, lo), max(s, la), min(e, lo + 3), min(n, la + 3), src.transform)
            win = win.round_offsets().round_lengths()
            a = src.read(1, window=win)
            tr = src.window_transform(win)
        if a.size == 0:
            continue
        rows, cols = np.indices(a.shape)
        plon = tr.c + (cols + 0.5) * tr.a
        plat = tr.f + (rows + 0.5) * tr.e
        idx = grid.cell_of(plon.ravel(), plat.ravel())
        ok = idx >= 0
        cls = a.ravel()[ok]
        ii = idx[ok]
        count += np.bincount(ii, minlength=len(grid))
        for k, v in LC_CLASSES.items():
            out[k] += np.bincount(ii, weights=(cls == v).astype(float), minlength=len(grid))
        px_x = abs(tr.a) * grid.kx_m
        px_y = abs(tr.e) * M_PER_DEG_LAT
        dist = distance_transform_edt(a != 80, sampling=(px_y, px_x)) if (a == 80).any() else np.full(a.shape, np.nan)
        dist_sum += np.bincount(ii, weights=np.nan_to_num(dist.ravel()[ok], nan=0.0), minlength=len(grid))
    with np.errstate(invalid="ignore", divide="ignore"):
        res = {k: (v / count).astype(np.float32) for k, v in out.items()}
        res["dist_water_m"] = (dist_sum / count).astype(np.float32)
    return res


def building_layers(grid: Grid, cache: Path, progress=None) -> dict[str, np.ndarray]:
    from geoeyes.ml.overture import buildings
    b = buildings(grid.bounds, cache, progress=progress)
    n = len(grid)
    if not b:
        return {"bld_count": np.zeros(n, np.float32), "bld_cover": np.zeros(n, np.float32),
                "bld_height_m": np.full(n, np.nan, np.float32)}
    lon = np.array([x["lon"] for x in b])
    lat = np.array([x["lat"] for x in b])
    area = np.array([x["area_m2"] for x in b])
    height = np.array([x["height_m"] for x in b])
    idx = grid.cell_of(lon, lat)
    ok = idx >= 0
    cnt = np.bincount(idx[ok], minlength=n)
    cover = np.bincount(idx[ok], weights=area[ok], minlength=n) / grid.cell_m ** 2
    known = ok & np.isfinite(height)
    wsum = np.bincount(idx[known], weights=area[known], minlength=n)
    hsum = np.bincount(idx[known], weights=(area * np.nan_to_num(height))[known], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        hmean = np.where(wsum > 0, hsum / wsum, np.nan)
    return {"bld_count": cnt.astype(np.float32), "bld_cover": np.clip(cover, 0, 1).astype(np.float32),
            "bld_height_m": hmean.astype(np.float32)}


def soil_clay(grid: Grid) -> dict[str, np.ndarray]:
    """SoilGrids 2.0 clay content (g/kg) at 0–5 cm, nearest 250 m pixel of each cell."""
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.windows import from_bounds
    with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + SOILGRIDS_CLAY) as src, \
            WarpedVRT(src, crs="EPSG:4326") as vrt:
        win = from_bounds(*grid.bounds, vrt.transform).round_offsets().round_lengths()
        a = vrt.read(1, window=win).astype(np.float32)
        tr = vrt.window_transform(win)
    a[a <= 0] = np.nan
    r = np.clip(((grid.lat - tr.f) / tr.e).astype(int), 0, a.shape[0] - 1)
    c = np.clip(((grid.lon - tr.c) / tr.a).astype(int), 0, a.shape[1] - 1)
    return {"soil_clay": a[r, c]}


def rainfall_layer(grid: Grid, hazard_dir: Path | None) -> dict[str, np.ndarray]:
    if hazard_dir is None or not (hazard_dir / "rain.npz").exists():
        return {"rain_annual_mm": np.full(len(grid), np.nan, np.float32)}
    with np.load(hazard_dir / "rain.npz") as z:
        ann = np.nanmean(z["annual"], axis=0) if z["annual"].size else None
        west, north, res = float(z["west"]), float(z["north"]), float(z["res"])
    if ann is None:
        return {"rain_annual_mm": np.full(len(grid), np.nan, np.float32)}
    r = np.clip(((north - grid.lat) / res).astype(int), 0, ann.shape[0] - 1)
    c = np.clip(((grid.lon - west) / res).astype(int), 0, ann.shape[1] - 1)
    return {"rain_annual_mm": ann[r, c].astype(np.float32)}


def build_layers(grid: Grid, *, dem_source: str, dem_cache: Path, overture_cache: Path, hazard_dir: Path | None,
                 progress=None) -> tuple[pd.DataFrame, list[str]]:
    """Every layer on the grid; returns the table and the warnings (layers that could not be read)."""
    say = progress or (lambda m: log.info("%s", m))
    table = pd.DataFrame({"kx": grid.kx, "ky": grid.ky, "lon": grid.lon, "lat": grid.lat})
    warnings: list[str] = []
    steps = [("terrain (DEM)", lambda: terrain(grid, dem_source, dem_cache)),
             ("land cover (ESA WorldCover)", lambda: worldcover(grid)),
             ("buildings (Overture Maps)", lambda: building_layers(grid, overture_cache, progress=say)),
             ("soil clay (SoilGrids)", lambda: soil_clay(grid)),
             ("rainfall climatology", lambda: rainfall_layer(grid, hazard_dir))]
    for name, fn in steps:
        say(f"layer: {name}")
        try:
            cols = fn()
        except Exception as exc:                               # a missing source leaves its columns empty
            warnings.append(f"layer {name} not read ({exc})")
            log.warning("layer %s not read: %s", name, exc)
            continue
        for k, v in cols.items():
            table[k] = v
    for k in LAYERS:
        if k not in table:
            table[k] = np.float32(np.nan)
    return table, warnings
