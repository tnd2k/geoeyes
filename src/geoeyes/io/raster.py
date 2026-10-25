"""RasterStore: product rasters as Cloud-Optimized GeoTIFF (ARCHITECTURE §10.5)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from geoeyes.core.errors import StoreError


def write_cog(path: str | Path, data: np.ndarray, transform, crs: str = "EPSG:4326", *,
              nodata: float = np.nan, description: str = "", units: str = "") -> Path:
    """Write a single-band float32 COG (DEFLATE, overviews, explicit nodata)."""
    import rasterio
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim != 2:
        raise StoreError(f"COG writer expects 2-D data, got {arr.shape}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {"driver": "COG", "height": arr.shape[0], "width": arr.shape[1], "count": 1,
               "dtype": "float32", "crs": crs, "transform": transform, "nodata": nodata,
               "compress": "DEFLATE", "predictor": 3, "blocksize": 512, "overview_resampling": "average"}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)
        if description:
            dst.set_band_description(1, description)
        if units:
            dst.update_tags(1, units=units)
    return path


def read_raster(path: str | Path, window=None) -> tuple[np.ndarray, dict]:
    import rasterio
    try:
        with rasterio.open(path) as src:
            return src.read(1, window=window), {"transform": src.transform, "crs": str(src.crs),
                                                "nodata": src.nodata, "units": src.tags(1).get("units", "")}
    except rasterio.errors.RasterioIOError as exc:
        raise StoreError(f"{path}: {exc}") from None
