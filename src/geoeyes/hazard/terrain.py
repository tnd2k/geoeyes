"""Terrain at the analysis cells: slope and downslope direction from a DEM smoothed to the cell size, and the
optional susceptibility raster of the user (docs/en/research/rainfall-insar-hazard.md §4.2).

The DEM is smoothed (Gaussian, σ = half a cell) before the slope is taken over one cell: the analysis is at cell
scale, and surface models (SRTM, Copernicus GLO-30) carry buildings and trees whose edges would otherwise read as
steep slopes in cities.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON = 111_320.0


def slope_aspect(dem, lon: np.ndarray, lat: np.ndarray, cell_m: float) -> dict[str, np.ndarray]:
    """``slope_deg``, ``down_e`` / ``down_n`` / ``down_u`` (unit vector of the steepest descent, ENU) and
    ``height_m`` at the cell centres; ``dem`` is a ``geoeyes.geometry.dem.Dem``."""
    from scipy.ndimage import gaussian_filter
    lat0 = float(np.nanmedian(lat))
    px_y = dem.dlat * M_PER_DEG_LAT
    px_x = dem.dlon * M_PER_DEG_LON * np.cos(np.radians(lat0))
    h = dem.height.astype(np.float64)
    void = ~np.isfinite(h)
    h = np.where(void, np.nanmean(h) if (~void).any() else 0.0, h)
    sigma = (0.5 * cell_m / px_y, 0.5 * cell_m / px_x)
    smooth = type(dem)(gaussian_filter(h, sigma, mode="nearest").astype(np.float32), dem.lat0, dem.lon0, dem.dlat,
                       dem.dlon, dem.datum, dem.source)
    dlon = 0.5 * cell_m / (M_PER_DEG_LON * np.cos(np.radians(lat0)))
    dlat = 0.5 * cell_m / M_PER_DEG_LAT
    gx = (smooth.orthometric(lat, lon + dlon) - smooth.orthometric(lat, lon - dlon)) / cell_m       # dh/dx east
    gy = (smooth.orthometric(lat + dlat, lon) - smooth.orthometric(lat - dlat, lon)) / cell_m       # dh/dy north
    g = np.hypot(gx, gy)
    slope = np.arctan(g)
    with np.errstate(invalid="ignore", divide="ignore"):
        ue, un = np.where(g > 0, -gx / g, 0.0), np.where(g > 0, -gy / g, 0.0)
    return {"slope_deg": np.degrees(slope).astype(np.float32), "height_m": smooth.orthometric(lat, lon),
            "down_e": (ue * np.cos(slope)).astype(np.float32), "down_n": (un * np.cos(slope)).astype(np.float32),
            "down_u": (-np.sin(slope)).astype(np.float32)}


# what a downslope rate needs from the acquisition geometry: a slope, a LOS that sees a fair share of the motion down
# it, and no layover / shadow (the position of a pixel there is not one place on the ground)
DOWNSLOPE_MIN_SLOPE_DEG = 10.0
DOWNSLOPE_MIN_SENSITIVITY = 0.3
DOWNSLOPE_LOCAL_INC_DEG = (5.0, 85.0)


def los_terrain(t: dict[str, np.ndarray], los_e, los_n, los_u) -> dict[str, np.ndarray]:
    """From ``slope_aspect`` (``t``) and the LOS unit vector ground -> satellite: ``sensitivity`` (LOS rate of a
    motion of 1 down the slope: + toward the satellite, so a downslope motion reads negative where the slope faces away
    and positive where it faces the satellite), ``local_inc_deg`` (angle between the LOS and the surface normal:
    near 0 or below = layover / strong foreshortening, near 90 or above = shadow) and ``visible`` (the downslope rate
    is measured: ``DOWNSLOPE_*``)."""
    slope = np.radians(np.asarray(t["slope_deg"], np.float64))
    de, dn, du = (np.asarray(t[k], np.float64) for k in ("down_e", "down_n", "down_u"))
    le, ln, lu = (np.asarray(x, np.float64) for x in (los_e, los_n, los_u))
    sens = de * le + dn * ln + du * lu
    c = np.cos(slope)
    with np.errstate(invalid="ignore", divide="ignore"):
        ue, un = np.where(c > 0, de / c, 0.0), np.where(c > 0, dn / c, 0.0)
    # local incidence in the range plane, signed: the incidence minus the slope's tilt toward the satellite (below 0 a
    # slope facing the satellite is steeper than the incidence: layover; above 90, one facing away hides: shadow)
    lh = np.hypot(le, ln)
    inc = np.arctan2(lh, lu)
    with np.errstate(invalid="ignore", divide="ignore"):
        toward = np.where(lh > 0, (ue * le + un * ln) / lh, 0.0)
    li = np.degrees(inc - np.arctan(np.tan(slope) * toward))
    lo, hi = DOWNSLOPE_LOCAL_INC_DEG
    visible = ((np.degrees(slope) >= DOWNSLOPE_MIN_SLOPE_DEG) & (np.abs(sens) >= DOWNSLOPE_MIN_SENSITIVITY)
               & (li >= lo) & (li <= hi) & np.isfinite(sens))
    return {"sensitivity": sens.astype(np.float32), "local_inc_deg": li.astype(np.float32), "visible": visible}


def downslope_rate(v_los, t: dict[str, np.ndarray], los_e, los_n, los_u) -> np.ndarray:
    """Rate down the slope (mm/yr, + = moving down) of a LOS rate (+ toward the satellite), NaN where the LOS does not
    measure it (``los_terrain``): the motion is assumed to be along the steepest descent."""
    g = los_terrain(t, los_e, los_n, los_u)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.asarray(v_los, np.float64) / g["sensitivity"]
    return np.where(g["visible"], r, np.nan).astype(np.float32)


def load_terrain_dem(source: str, bounds: list[float], cache: Path, cell_m: float):
    """The DEM over the product bounds (plus a margin of two cells): ``source`` as in ``[stack].dem``."""
    from geoeyes.geometry.dem import load_dem
    w, s, e, n = bounds
    pad = 2 * cell_m / M_PER_DEG_LAT + 0.005
    return load_dem(source or "srtm-1", s - pad, n + pad, w - pad, e + pad, cache=cache)


def sample_classes(path: Path, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Susceptibility classes (0..3, NaN outside / no data) of a user raster at the cell centres, any CRS."""
    import rasterio
    from rasterio.warp import transform
    with rasterio.open(path) as src:
        xs, ys = (lon, lat) if src.crs is None or src.crs.to_epsg() == 4326 else \
            transform("EPSG:4326", src.crs, list(lon), list(lat))
        vals = np.array([v[0] for v in src.sample(zip(xs, ys, strict=True), masked=True)], dtype=object)
        nodata = src.nodata
    out = np.array([np.nan if (v is np.ma.masked or (nodata is not None and v == nodata)) else float(v)
                    for v in vals], dtype=np.float32)
    out[(out < 0) | (out > 3)] = np.nan
    return np.floor(out)
