"""Thickness of the soft soil under each cell (docs/en/research/two-geometries-and-soft-soil.md §3).

Sources, the first available wins:

* ``raster``: a GeoTIFF of the thickness of the soft (compressible) layer, metres, any CRS: e.g. a map of the
  Holocene clay and peat digitised from a geological survey;
* ``boreholes``: a CSV with ``lon``, ``lat``, ``thickness_m`` (and optionally ``name``): the depth of the base of
  the soft layer at each borehole, interpolated by inverse distance (``idw_power``, ``idw_neighbours``) up to
  ``max_borehole_km`` from the nearest borehole;
* ``open``: Pelletier et al. (2016), the thickness of the sedimentary deposits above bedrock on lowlands, 1 km,
  capped at 50 m (NASA ORNL DAAC, Earthdata login). It is a modelled depth to bedrock, not the soft layer: in a
  delta it mostly reads 50 m, and its pattern only hints at where the deposits thin out.

Paths are relative to the project folder.
"""
from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from geoeyes.core.errors import ConfigError, DataError

log = logging.getLogger(__name__)

PELLETIER = ("https://data.ornldaac.earthdata.nasa.gov/protected/global_soil/Global_Soil_Regolith_Sediment/data/"
             "upland_valley-bottom_and_lowland_sedimentary_deposit_thickness.tif")
PELLETIER_FILE = "pelletier2016_lowland_sediment_thickness.tif"
SOURCES = {"raster": "project raster", "boreholes": "boreholes (inverse distance)",
           "open": "Pelletier et al. 2016, sediment thickness above bedrock (1 km, capped at 50 m)"}


@dataclass(frozen=True)
class GeologyParams:
    """``[postprocess.geology]`` of project.toml (every key optional)."""

    raster: str = ""                  # GeoTIFF of the soft-soil thickness (m)
    boreholes: str = ""               # CSV: lon, lat, thickness_m
    open_fallback: bool = True        # Pelletier et al. 2016 when neither is given
    idw_power: float = 2.0
    idw_neighbours: int = 8
    max_borehole_km: float = 3.0
    drainage: str = "double"          # consolidation check: drained on both faces (H_dr = H/2) or "single"
    bins: int = 5                     # thickness classes (quantiles) of the comparison with the rates
    moving_mm_yr: float = 5.0         # a cell sinking this fast or faster counts as moving

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> GeologyParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.geology]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {k: (str(v).lower() in ("1", "true", "yes") if isinstance(getattr(cls, k), bool) and isinstance(v, str)
                   else type(getattr(cls, k))(v)) for k, v in d.items()}
        return cls(**out)


def _sample_raster(path: Path, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    import rasterio
    from rasterio.warp import transform
    with rasterio.open(path) as ds:
        xs, ys = (lon, lat) if ds.crs is None or ds.crs.to_epsg() == 4326 else transform("EPSG:4326", ds.crs, lon, lat)
        vals = np.array([v[0] for v in ds.sample(zip(xs, ys, strict=True))], dtype=np.float64)
        if ds.nodata is not None:
            vals[vals == ds.nodata] = np.nan
    vals[vals < 0] = np.nan
    return vals


def idw(lon: np.ndarray, lat: np.ndarray, blon: np.ndarray, blat: np.ndarray, val: np.ndarray, *, power: float,
        k: int, max_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Inverse-distance interpolation of the boreholes at the cells; NaN beyond ``max_km`` of the nearest one.
    Returns the values and the distance to the nearest borehole (km)."""
    from scipy.spatial import cKDTree
    kx = 111.32 * np.cos(np.radians(np.median(lat)))
    tree = cKDTree(np.column_stack([blon * kx, blat * 110.54]))
    kk = min(k, len(val))
    d, i = tree.query(np.column_stack([lon * kx, lat * 110.54]), k=kk)
    d, i = d.reshape(len(lon), kk), i.reshape(len(lon), kk)
    w = 1.0 / np.maximum(d, 1e-3) ** power
    out = (w * val[i]).sum(1) / w.sum(1)
    out[d[:, 0] > max_km] = np.nan
    return out, d[:, 0]


def _open_raster(cache: Path, token: str) -> Path:
    f = cache / PELLETIER_FILE
    if f.exists():
        return f
    if not token:
        raise DataError("EARTHDATA_TOKEN is required for the open sediment-thickness grid (Pelletier et al. 2016)")
    cache.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".part")
    req = urllib.request.Request(PELLETIER, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
    tmp.replace(f)
    return f


def thickness(lon: np.ndarray, lat: np.ndarray, params: GeologyParams, *, project_dir: Path, cache: Path,
              token: str = "") -> dict:
    """Soft-soil thickness (m) at each location, with its source and, for boreholes, the distance to the nearest."""
    lon, lat = np.asarray(lon, np.float64), np.asarray(lat, np.float64)
    if params.raster:
        p = (project_dir / params.raster).resolve()
        if not p.exists():
            raise DataError(f"[postprocess.geology] raster {p} not found")
        return {"thickness_m": _sample_raster(p, lon, lat), "source": "raster", "file": str(p)}
    if params.boreholes:
        p = (project_dir / params.boreholes).resolve()
        if not p.exists():
            raise DataError(f"[postprocess.geology] boreholes {p} not found")
        b = pd.read_csv(p)
        missing = {"lon", "lat", "thickness_m"} - set(b.columns)
        if missing:
            raise DataError(f"{p.name}: missing column(s) {sorted(missing)} (lon, lat, thickness_m)")
        b = b.dropna(subset=["lon", "lat", "thickness_m"])
        if len(b) < 3:
            raise DataError(f"{p.name}: {len(b)} boreholes, at least 3 are needed")
        v, dist = idw(lon, lat, b.lon.to_numpy(float), b.lat.to_numpy(float), b.thickness_m.to_numpy(float),
                      power=params.idw_power, k=params.idw_neighbours, max_km=params.max_borehole_km)
        return {"thickness_m": v, "source": "boreholes", "file": str(p), "boreholes": len(b), "nearest_km": dist}
    if params.open_fallback:
        return {"thickness_m": _sample_raster(_open_raster(cache, token), lon, lat), "source": "open",
                "file": PELLETIER_FILE}
    raise DataError("no soft-soil thickness: set [postprocess.geology] raster or boreholes")
