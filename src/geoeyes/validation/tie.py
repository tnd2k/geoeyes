"""Tie of a product to another one over their common ground, for a product with no GNSS station inside it.

Two products of the same ground differ by their reference (each is zero at its own reference area or scene mean),
by their line of sight and by their period. The tie compares like with like:

1. period: the reference product's rate is fitted over the target's dates only (its acquisitions around them);
2. line of sight: both rates are turned into vertical rates (v / los_u), as the GNSS ``vertical`` mode does (the
   horizontal motion is taken as uniform, part of each reference);
3. space: medians on ``cell_m`` cells, the cells with at least ``min_points`` points of each product.

The correction is one rate (``offset``): the median over the cells of (reference − target), vertical, put back in
the target's line of sight. When the reference product has a GNSS calibration it is applied first, so the target
is tied to the GNSS through it. A gain (slope) between the two is reported, not corrected: it mixes the period and
the geometry, not an error of either product.

Written to ``<project>/analyses/tie/<product>/tie.json``; its ``calibration`` has the keys of a GNSS calibration
(``geoeyes.validation.gnss.correction`` applies it).
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from geoeyes.core.errors import DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.validation.gnss.compare import DAYS_PER_YEAR, M_PER_DEG_LAT, M_PER_DEG_LON, correction, read_comparison

SCHEMA = "geoeyes.tie/1"
COLS = ["point_uid", "lon", "lat", "los_u", "vel_los_mm_yr"]


def _points(product: Path, bbox=None):
    d = ds.dataset(product / "points.parquet")
    f = None
    if bbox is not None:
        w, s, e, n = bbox
        f = (pc.field("lon") >= w) & (pc.field("lon") <= e) & (pc.field("lat") >= s) & (pc.field("lat") <= n)
    return d.to_table(columns=COLS, filter=f).to_pandas()


def _series(product: Path, uids: np.ndarray, d0, d1) -> tuple[np.ndarray, np.ndarray]:
    """(dates within [d0, d1], (points, dates) displacement mm in the order of ``uids``)."""
    t = ds.dataset(product / "timeseries.parquet").to_table(
        columns=["point_uid", "date", "disp_mm"], filter=pc.field("point_uid").isin(uids)).to_pandas()
    day = t["date"].to_numpy().astype("datetime64[D]")
    t = t[(day >= d0) & (day <= d1)].assign(date=day[(day >= d0) & (day <= d1)].astype(str))
    wide = t.pivot(index="point_uid", columns="date", values="disp_mm").reindex(uids)
    return np.asarray(wide.columns, dtype="datetime64[D]"), wide.to_numpy(np.float64)


def _rate(dates: np.ndarray, y: np.ndarray) -> np.ndarray:
    t = (dates - dates[0]).astype(np.float64) / DAYS_PER_YEAR
    a = np.column_stack([t, np.ones_like(t)])
    ok = np.isfinite(y).all(axis=1)
    out = np.full(y.shape[0], np.nan)
    if ok.any():
        out[ok] = np.linalg.lstsq(a, y[ok].T, rcond=None)[0][0]
    return out


def _cells(lon, lat, w, s, lat0, cell_m) -> np.ndarray:
    i = np.floor((lat - s) * M_PER_DEG_LAT / cell_m).astype(np.int64)
    j = np.floor((lon - w) * M_PER_DEG_LON * math.cos(math.radians(lat0)) / cell_m).astype(np.int64)
    return i * 1_000_000 + j


def _median_by(key: np.ndarray, v: np.ndarray, min_points: int) -> dict[int, float]:
    ok = np.isfinite(v)
    key, v = key[ok], v[ok]
    o = np.argsort(key, kind="stable")
    key, v = key[o], v[o]
    u, start, cnt = np.unique(key, return_index=True, return_counts=True)
    return {int(k): float(np.median(v[a:a + c])) for k, a, c in zip(u, start, cnt, strict=True) if c >= min_points}


def tie(target: Path, reference: Path, out: Path, *, reference_calibration: dict | None = None,
        cell_m: float = 100.0, min_points: int = 3) -> dict:
    """Tie ``target`` to ``reference`` (product folders); the summary is written to ``out/tie.json``."""
    warnings: list[str] = []
    tp = _points(target)
    if tp.empty:
        raise DataError(f"{target.name}: no points")
    w, s, e, n = float(tp.lon.min()), float(tp.lat.min()), float(tp.lon.max()), float(tp.lat.max())
    rp = _points(reference, (w, s, e, n))
    if len(rp) < min_points:
        raise DataError(f"{reference.name} has no points over {target.name}")
    t_dates = np.unique(pq.read_table(target / "timeseries.parquet", columns=["date"])["date"].to_numpy()
                        .astype("datetime64[D]"))
    r_dates = np.unique(pq.read_table(reference / "timeseries.parquet", columns=["date"])["date"].to_numpy()
                        .astype("datetime64[D]"))
    # the reference's acquisitions around the target's period: the last one at or before its first date and the
    # first one at or after its last date (those inside when the reference does not reach that far)
    before, after = r_dates[r_dates <= t_dates[0]], r_dates[r_dates >= t_dates[-1]]
    d0 = before[-1] if before.size else r_dates[0]
    d1 = after[0] if after.size else r_dates[-1]
    if not before.size or not after.size:
        warnings.append(f"{reference.name} covers {r_dates[0]}..{r_dates[-1]}, not the whole target period "
                        f"{t_dates[0]}..{t_dates[-1]}: its rate is taken over the overlap only")
    dates, ys = _series(reference, rp.point_uid.to_numpy(), d0, d1)
    if dates.size < 3:
        raise DataError(f"{reference.name}: {dates.size} acquisition(s) over {t_dates[0]}..{t_dates[-1]} "
                        "(at least 3 are needed for a rate)")
    if reference_calibration:
        ys = ys + correction(reference_calibration, dates, rp.lon.to_numpy(), rp.lat.to_numpy())
    r_vel = _rate(dates, ys)
    lat0 = float(tp.lat.median())
    # vertical rates (los_u > 0: the line of sight points up towards the satellite)
    tv = tp.vel_los_mm_yr.to_numpy(np.float64) / tp.los_u.to_numpy(np.float64)
    rv = r_vel / rp.los_u.to_numpy(np.float64)
    tc = _median_by(_cells(tp.lon.to_numpy(), tp.lat.to_numpy(), w, s, lat0, cell_m), tv, min_points)
    rc = _median_by(_cells(rp.lon.to_numpy(), rp.lat.to_numpy(), w, s, lat0, cell_m), rv, min_points)
    common = sorted(set(tc) & set(rc))
    if len(common) < 10:
        raise DataError(f"{len(common)} common {cell_m:g} m cells between the two products (at least 10 needed)")
    a = np.array([rc[k] for k in common])
    b = np.array([tc[k] for k in common])
    diff = a - b
    dv = float(np.median(diff))
    spread = float(1.4826 * np.median(np.abs(diff - dv)))
    slope, intercept = np.polyfit(a, b, 1)
    corr = float(np.corrcoef(a, b)[0, 1])
    los_u = float(np.median(tp.los_u))
    if corr < 0.5:
        warnings.append(f"the two products agree poorly over the common cells (correlation {corr:.2f}): "
                        "the tie is uncertain")
    if abs(slope - 1.0) > 0.25:
        warnings.append(f"gain {slope:.2f} between the products: the periods or the geometries differ (horizontal "
                        "motion, seasonal rate); only the offset is corrected")
    rate = dv * los_u
    ref_label = None
    if reference_calibration:
        st = reference_calibration.get("stations") or []
        ref_label = f"GNSS {', '.join(st)}" if st else reference_calibration.get("source", "calibrated")
    calib = {"kind": "offset", "source": "tie", "los_mode": "vertical", "gnss_rate": "window", "stations": [],
             "reference_product": reference.name, "reference_calibration": ref_label,
             "rate_coef": [round(rate, 4)], "rate_offset_mm_yr": round(rate, 2),
             "vertical_offset_mm_yr": round(dv, 2), "centre": [(w + e) / 2, (s + n) / 2], "lat0": lat0}
    summary = {"schema": SCHEMA, "product_id": target.name, "reference_product": reference.name,
               "created": datetime.now(UTC).isoformat(timespec="seconds"),
               "params": {"cell_m": cell_m, "min_points": min_points},
               "window": [str(d0), str(d1)], "reference_dates": [str(d) for d in dates],
               "target_period": [str(t_dates[0]), str(t_dates[-1])],
               "n_cells": len(common), "corr": round(corr, 3), "slope": round(float(slope), 3),
               "intercept_mm_yr": round(float(intercept), 2), "spread_mm_yr": round(spread, 2),
               "median_reference_mm_yr": round(float(np.median(a)), 2),
               "median_target_mm_yr": round(float(np.median(b)), 2),
               "calibration": calib, "warnings": warnings, "method": "geoeyes.validation.tie"}
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "tie.json", summary)
    m = Manifest(kind="tie", id=target.name, engine=SCHEMA,
                 inputs=[InputRef("product", str(target)), InputRef("reference", str(reference))],
                 params=summary["params"], metrics={"n_cells": len(common), "offset_mm_yr": calib["rate_offset_mm_yr"]})
    m.add_outputs(out, ["tie.json"])
    m.write(out)
    return summary


def read_tie(folder: Path) -> dict | None:
    f = folder / "tie.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def active_calibration(project, product_id: str) -> dict | None:
    """The calibration applied to a product: its GNSS calibration, else its tie to another product, else None.
    ``project``: a ``ProjectLayout``. The dict carries ``source`` (gnss | tie)."""
    comp = read_comparison(project.analysis("gnss", product_id))
    c = (comp or {}).get("calibration")
    if c:
        return {**c, "source": "gnss"}
    t = read_tie(project.analysis("tie", product_id))
    return (t or {}).get("calibration")
