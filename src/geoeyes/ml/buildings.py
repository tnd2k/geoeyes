"""InSAR per building (docs/en/research/ai-susceptibility.md §7): the persistent scatterers on each Overture
building footprint give its velocity and, with enough of them, its tilt.

Per building with at least ``min_points`` points inside its footprint:

* ``v_los`` / ``v_vert``: median LOS velocity and its vertical projection (v / l_u), mm/yr;
* ``spread``: P90 − P10 of the vertical velocities on the building (differential motion);
* ``tilt``: a plane v = a + b·x + c·y fitted to the vertical velocities (at least ``min_points_tilt`` points over
  ``min_extent_m``), kept only when |∇v| ≥ ``tilt_t`` times its standard error (narrow buildings with a few noisy
  points otherwise show large spurious tilts): |∇v| in mm/yr per m, the rate of rigid-body tilt ω of the
  building; ``tilt_10yr`` = |∇v| · 10 / 1000 is the tilt reached in 10 years. A uniform tilt does not crack a
  building (Burland & Wroth 1974; Burland 1995): it is classed by the tilt limits of the risk step, not by the
  damage limits.
* ``beta_10yr``: the angular distortion β (relative rotation = slope between two points minus the rigid tilt;
  Burland & Wroth 1974; Boscardin & Cording 1989) reached in 10 years, from the residuals of the tilt plane — see
  :func:`tilt_and_distortion`. Comparable with 1/500 (Bjerrum) and 1/300 (Skempton & MacDonald); the
  building-level counterpart of the cell-level distortion of the hazard analysis (Peduto et al. 2017, 2019;
  Giardina et al. 2019).

The Overture (GERS) id of each building is kept: the web app colours the same tiles through it (feature state with
``promoteId``; the 64-bit MVT feature ids do not survive JavaScript numbers).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.ml import overture

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.buildings/2"        # /2: beta_10yr is the angular distortion (in /1 it was the rigid tilt)
MAX_PAIR_POINTS = 400                  # points per building used for the pairwise distortion (random subset beyond)
P90_HALF_NORMAL = 1.6449               # P90 of |N(0, 1)|


def tilt_and_distortion(x: np.ndarray, y: np.ndarray, vv: np.ndarray, sigma: np.ndarray | None = None, *,
                        tilt_t: float = 3.0, min_pair_m: float = 5.0, beta_q: float = 90.0, beta_t: float = 2.0,
                        min_sigma_mm_yr: float = 0.5) -> dict:
    """Rigid tilt and angular distortion of one building from its PS (x, y in m, vertical rates ``vv`` in mm/yr,
    optional per-PS standard errors ``sigma`` in mm/yr).

    * Tilt: |∇v| of the least-squares plane, kept when ≥ ``tilt_t`` × its standard error.
    * Distortion: residuals r = v − plane (the rigid tilt removed). For every pair at d_ij ≥ ``min_pair_m`` the
      relative rotation rate is |r_i − r_j| / d_ij; the distortion rate is its ``beta_q`` percentile (robust: a
      few odd PS do not set it). Noise floor: the same percentile of 1.645·√(σ_i² + σ_j²) / d_ij, the P90 of the
      rotation that pure PS noise gives each pair; σ from ``sigma`` when given, else the nearest-neighbour
      scatter of the residuals (1.4826·median|r_i − r_nn(i)| / √2, the nugget: smooth signal adds little over
      the shortest distances), never below ``min_sigma_mm_yr``. β is kept only when ≥ ``beta_t`` × the floor.

    Returns tilt, tilt_se (mm/yr per m), distortion (the percentile, mm/yr per m, NaN when no pair),
    distortion_noise (the floor) and the 10-year values tilt_10yr and beta_10yr (NaN when not significant).
    """
    nan = float("nan")
    out = {"tilt": nan, "tilt_se": nan, "tilt_10yr": nan, "distortion": nan, "distortion_noise": nan,
           "beta_10yr": nan}
    n = len(vv)
    if n < 4:
        return out
    a_ = np.column_stack([np.ones_like(x), x, y])
    coef, *_ = np.linalg.lstsq(a_, vv, rcond=None)
    res = vv - a_ @ coef
    s2 = float(res @ res) / max(n - 3, 1)
    cov = np.linalg.pinv(a_.T @ a_) * s2
    g = float(np.hypot(coef[1], coef[2]))
    # standard error of |∇v| (first order); a tilt is kept only when it stands out of the PS noise
    se = float(np.sqrt(max((coef[1] ** 2 * cov[1, 1] + coef[2] ** 2 * cov[2, 2]
                            + 2 * coef[1] * coef[2] * cov[1, 2]) / max(g * g, 1e-12), 0.0)))
    out["tilt_se"] = se
    if g >= tilt_t * se:
        out["tilt"], out["tilt_10yr"] = g, g * 10 / 1000
    # ---- angular distortion from the plane residuals
    keep = np.arange(n)
    if n > MAX_PAIR_POINTS:
        keep = np.sort(np.random.default_rng(0).choice(n, MAX_PAIR_POINTS, replace=False))
    xs, ys, rs = x[keep], y[keep], res[keep]
    d = np.hypot(xs[:, None] - xs[None, :], ys[:, None] - ys[None, :])
    dr = np.abs(rs[:, None] - rs[None, :])
    if sigma is not None and np.isfinite(sigma[keep]).all():
        sg = np.maximum(np.asarray(sigma, np.float64)[keep], min_sigma_mm_yr)
    else:
        dnn = np.where(d > 0, d, np.inf)
        nn = np.argmin(dnn, axis=1)
        sg_ = 1.4826 * float(np.median(np.abs(rs - rs[nn]))) / math.sqrt(2)
        sg = np.full(len(keep), max(sg_, min_sigma_mm_yr))
    iu = np.triu_indices(len(keep), 1)
    far = d[iu] >= min_pair_m
    if not far.any():
        return out
    dd = d[iu][far]
    rot = dr[iu][far] / dd
    noise = P90_HALF_NORMAL * np.sqrt(sg[iu[0]][far] ** 2 + sg[iu[1]][far] ** 2) / dd
    beta, floor = float(np.percentile(rot, beta_q)), float(np.percentile(noise, beta_q))
    out["distortion"], out["distortion_noise"] = beta, floor
    if beta >= beta_t * floor:
        out["beta_10yr"] = beta * 10 / 1000
    return out


def analyse(product: Path, out: Path, cache: Path, *, min_points: int = 3, min_points_tilt: int = 8,
            min_extent_m: float = 20.0, tilt_t: float = 3.0, min_pair_m: float = 5.0, beta_q: float = 90.0,
            beta_t: float = 2.0, progress=None) -> dict:
    import shapely
    say = progress or (lambda m: log.info("%s", m))
    cols = ["lon", "lat", "vel_los_mm_yr", "los_u"]
    have = set(pq.read_schema(product / "points.parquet").names)
    pts = pq.read_table(product / "points.parquet",
                        columns=cols + (["vel_std_mm_yr"] if "vel_std_mm_yr" in have else [])).to_pandas()
    w, s, e, n = pts.lon.min(), pts.lat.min(), pts.lon.max(), pts.lat.max()
    blds = overture.buildings([w, s, e, n], cache, progress=say)
    say(f"{len(blds)} buildings over the product, {len(pts)} points")
    blds = [b for b in blds if len(b["ring"]) >= 3]
    polys = np.array([shapely.Polygon(b["ring"]) for b in blds], dtype=object)
    tree = shapely.STRtree(polys)
    p_idx, b_idx = tree.query(shapely.points(pts.lon.to_numpy(), pts.lat.to_numpy()), predicate="within")
    say(f"{len(p_idx)} points on buildings")
    lat0 = float(np.median(pts.lat))
    kx = 111_320.0 * math.cos(math.radians(lat0))
    v_los = pts.vel_los_mm_yr.to_numpy(np.float64)
    v_vert = v_los / np.clip(pts.los_u.to_numpy(np.float64), 0.2, None)
    s_vert = (pts.vel_std_mm_yr.to_numpy(np.float64) / np.clip(pts.los_u.to_numpy(np.float64), 0.2, None)
              if "vel_std_mm_yr" in pts else None)
    order = np.argsort(b_idx, kind="stable")
    p_idx, b_idx = p_idx[order], b_idx[order]
    starts = np.flatnonzero(np.r_[True, b_idx[1:] != b_idx[:-1]])
    ends = np.r_[starts[1:], len(b_idx)]
    rows = []
    for a, z in zip(starts, ends, strict=True):
        k = p_idx[a:z]
        if len(k) < min_points:
            continue
        b = blds[int(b_idx[a])]
        vv = v_vert[k]
        row = {"id": str(b["gers"] or b["id"]), "lon": b["lon"], "lat": b["lat"],
               "area_m2": b["area_m2"], "height_m": b["height_m"], "n": len(k),
               "v_los": float(np.median(v_los[k])), "v_vert": float(np.median(vv)),
               "spread": float(np.percentile(vv, 90) - np.percentile(vv, 10)), "tilt": np.nan, "tilt_se": np.nan,
               "tilt_10yr": np.nan, "distortion": np.nan, "distortion_noise": np.nan, "beta_10yr": np.nan}
        if len(k) >= min_points_tilt:
            x = (pts.lon.to_numpy()[k] - b["lon"]) * kx
            y = (pts.lat.to_numpy()[k] - b["lat"]) * 110_540.0
            if max(np.ptp(x), np.ptp(y)) >= min_extent_m:
                row.update(tilt_and_distortion(x, y, vv, None if s_vert is None else s_vert[k], tilt_t=tilt_t,
                                               min_pair_m=min_pair_m, beta_q=beta_q, beta_t=beta_t))
        rows.append(row)
    table = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "buildings.parquet", index=False)
    summary = {"schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
               "buildings_total": len(blds), "buildings_with_points": len(table),
               "with_tilt": int(table["tilt"].notna().sum()) if len(table) else 0,
               "with_distortion": int(table["beta_10yr"].notna().sum()) if len(table) else 0,
               "beta_over_1_500": int((table["beta_10yr"] >= 1 / 500).sum()) if len(table) else 0,
               "tilt_over_1_250": int((table["tilt_10yr"] >= 1 / 250).sum()) if len(table) else 0,
               "release": overture.RELEASE, "credit": overture.CREDIT,
               "params": {"min_points": min_points, "min_points_tilt": min_points_tilt, "min_extent_m": min_extent_m,
                          "tilt_t": tilt_t, "min_pair_m": min_pair_m, "beta_q": beta_q, "beta_t": beta_t},
               "method": "docs/en/research/ai-susceptibility.md"}
    atomic_write_json(out / "buildings.json", summary)
    m = Manifest(kind="buildings", id=product.name, engine=SCHEMA, inputs=[InputRef("product", str(product))],
                 params=summary["params"], metrics={"buildings_with_points": len(table)})
    m.add_outputs(out, ["buildings.parquet", "buildings.json"])
    m.write(out)
    say(f"done: {len(table)} buildings with InSAR, {summary['with_tilt']} with a tilt, "
        f"{summary['with_distortion']} with an angular distortion")
    return summary


def read_summary(folder: Path) -> dict | None:
    f = folder / "buildings.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
