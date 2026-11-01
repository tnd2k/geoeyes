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
    mats = {"disp_mm": disp}
    if disp_std_mm is not None:
        mats["disp_std_mm"] = np.asarray(disp_std_mm, dtype=np.float32)
    if flags is not None:
        mats["flags"] = np.asarray(flags, dtype=np.uint8)
    if disp_scn_mm is not None:
        mats["disp_scn_mm"] = np.asarray(disp_scn_mm, dtype=np.float32)
    # sorted by (point_uid, date), written one block of points at a time: the long table of a few million points
    # does not fit in memory at once (Tenerife ICEYE: 3.9M PS x 16 dates)
    rows = np.argsort(uid, kind="stable")
    cols_t = np.argsort(d, kind="stable")
    d32 = pa.array(d[cols_t], pa.date32())
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    block = max(1, 1_000_000 // max(t, 1))
    writer = None
    try:
        for s in range(0, max(n, 1), block):
            r = rows[s:s + block]
            cols = {POINT_UID: pa.array(np.repeat(uid[r], t)), "date": pa.concat_arrays([d32] * r.size)
                    if r.size else pa.array([], pa.date32())}
            for k, m in mats.items():
                cols[k] = pa.array(m[r][:, cols_t].ravel())
            table = pa.table(cols)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=1_000_000)
    finally:
        if writer is not None:
            writer.close()
    return path


def read_timeseries(path: str | Path, point_uids=None) -> pd.DataFrame:
    filters = [(POINT_UID, "in", list(point_uids))] if point_uids is not None else None
    try:
        return pq.read_table(path, filters=filters).to_pandas()
    except FileNotFoundError:
        raise StoreError(f"{path}: not found") from None


def timeseries_arrays(path: str | Path, point_uid, columns=("disp_mm",)) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """(dates[T], {column: float32 (N, T)}) with row i = ``point_uid[i]``, read column by column without a pivot
    (the file holds every point at every date, sorted by point then date)."""
    path = Path(path)
    if not path.exists():
        raise StoreError(f"{path}: not found")
    uid = np.asarray(point_uid).astype(str)
    n = uid.size
    meta = pq.ParquetFile(path).metadata
    dates = np.unique(pq.read_table(path, columns=["date"])["date"].to_numpy().astype("datetime64[D]"))
    t = dates.size
    if meta.num_rows != n * t:
        raise StoreError(f"{path.parent.name}: timeseries has {meta.num_rows} rows, expected {n} x {t}")
    order = np.argsort(uid, kind="stable")                         # row k of the file block = point order[k]
    # the first row of each point, read a batch at a time (millions of points x dates: the whole string column is
    # several GB and past the 2 GB offsets of an Arrow string array once concatenated)
    heads, off = [], 0
    for b in pq.ParquetFile(path).iter_batches(columns=[POINT_UID], batch_size=4_000_000):
        col = b.column(0)
        k0 = -(-off // t) * t                                     # first multiple of t at or after off
        if k0 < off + len(col):
            heads.append(col.take(np.arange(k0 - off, len(col), t)).to_numpy(zero_copy_only=False))
        off += len(col)
    if not np.array_equal(np.concatenate(heads).astype(str) if heads else np.array([], str), uid[order]):
        raise StoreError(f"{path.parent.name}: timeseries points do not match points.parquet")
    out = {}
    for c in columns:
        a = pq.read_table(path, columns=[c])[c].to_numpy().astype(np.float32).reshape(n, t)
        out[c] = np.empty_like(a)
        out[c][order] = a
    return dates, out


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
