"""PointStore (GeoParquet) and TimeSeriesStore (long-format Parquet) — ARCHITECTURE §10.4.

``points.parquet``     one row per measurement point; must contain ``point_uid`` and a point
                       geometry in EPSG:4326 (column set versioned by ``geoeyes.products.schema``).
``timeseries.parquet`` rows (point_uid, date, disp_mm[, disp_std_mm, flags]) sorted by point then
                       date, so both "one point, all dates" and "all points, one date" are cheap.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from geoeyes.core.errors import StoreError

POINT_UID = "point_uid"


def write_points(path: str | Path, gdf, *, metadata: dict | None = None) -> Path:
    """Write a GeoDataFrame as GeoParquet (EPSG:4326, zstd)."""
    path = Path(path)
    if POINT_UID not in gdf.columns:
        raise StoreError("points need a 'point_uid' column")
    if gdf[POINT_UID].duplicated().any():
        raise StoreError("point_uid values must be unique")
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        raise StoreError(f"points must be in EPSG:4326, got {gdf.crs}")
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path, compression="zstd", index=False, schema_version="1.1.0",
                   write_covering_bbox=True)
    if metadata:
        _add_metadata(path, metadata)
    return path


def read_points(path: str | Path, *, columns=None, bbox=None):
    import geopandas as gpd
    try:
        return gpd.read_parquet(path, columns=columns, bbox=bbox)
    except FileNotFoundError:
        raise StoreError(f"{path}: not found") from None


def write_timeseries(path: str | Path, point_uid, dates, disp_mm, disp_std_mm=None, flags=None,
                     disp_scn_mm=None) -> Path:
    """``disp_mm`` is (N points, T dates); stored in long format sorted by (point_uid, date). ``disp_scn_mm``:
    the same series with the spatially correlated noise (residual atmosphere) removed, when the engine has it."""
    uid = np.asarray(point_uid)
    d = np.asarray(dates, dtype="datetime64[D]")
    disp = np.asarray(disp_mm, dtype=np.float32)
    n, t = disp.shape
    if uid.shape != (n,) or d.shape != (t,):
        raise StoreError(f"shape mismatch: uid {uid.shape}, dates {d.shape}, disp {disp.shape}")
    cols = {POINT_UID: np.repeat(uid, t), "date": np.tile(d, n), "disp_mm": disp.ravel()}
    if disp_std_mm is not None:
        cols["disp_std_mm"] = np.asarray(disp_std_mm, dtype=np.float32).ravel()
    if flags is not None:
        cols["flags"] = np.asarray(flags, dtype=np.uint8).ravel()
    if disp_scn_mm is not None:
        cols["disp_scn_mm"] = np.asarray(disp_scn_mm, dtype=np.float32).ravel()
    df = pd.DataFrame(cols).sort_values([POINT_UID, "date"], kind="stable")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.cast(table.schema.set(table.schema.get_field_index("date"), pa.field("date", pa.date32())))
    pq.write_table(table, path, compression="zstd", row_group_size=1_000_000)
    return path


def read_timeseries(path: str | Path, point_uids=None) -> pd.DataFrame:
    filters = [(POINT_UID, "in", list(point_uids))] if point_uids is not None else None
    try:
        return pq.read_table(path, filters=filters).to_pandas()
    except FileNotFoundError:
        raise StoreError(f"{path}: not found") from None


def timeseries_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Long table -> (point_uid[N], dates[T] datetime64[D], disp_mm[N, T])."""
    wide = df.pivot(index=POINT_UID, columns="date", values="disp_mm")
    return wide.index.to_numpy(), np.asarray(wide.columns, dtype="datetime64[D]"), wide.to_numpy(np.float32)


def _add_metadata(path: Path, metadata: dict) -> None:
    import json
    table = pq.read_table(path)
    meta = dict(table.schema.metadata or {})
    meta[b"geoeyes"] = json.dumps(metadata, default=str).encode()
    pq.write_table(table.replace_schema_metadata(meta), path, compression="zstd")
