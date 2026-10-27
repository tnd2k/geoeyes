"""Vertical and east-west motion from two or more viewing geometries (docs/en/research/
two-geometries-and-soft-soil.md §2).

One line of sight sees d_LOS = e·l_e + n·l_n + u·l_u. Its vertical projection d_LOS / l_u is the vertical motion
only if the ground does not move sideways. An ascending and a descending track look at the ground from the east
and from the west (l_e of opposite signs): together they separate the east-west and the vertical motion. The
north component is assumed zero: near-polar orbits are almost blind to it (|l_n| ≲ 0.15 for Sentinel-1).

1. Partners: the products of the workspace (latest version of each track) whose area and period overlap the
   product and whose look direction differs (|Δl_e| ≥ ``min_east_contrast``), unless given.
2. Common support. The two products see different scatterers, at different places: they are paired either
   * ``support = "cells"``: on a common grid of ``cell_m`` cells (in degrees, so that it is also a GeoTIFF), per
     product and cell the median LOS velocity and LOS vector of its points; or
   * ``support = "points"``: at every point of the product, per product the median of its points within
     ``radius_m`` (up to ``max_neighbours``): no grid, the resolution of the points where both products have some;
   in both cases when there are at least ``min_points``.
3. Common reference: every product is re-referenced to the median of its own velocities over the cells seen by
   all, so that the result is relative to the median motion of the common area. A plane fitted to each product's
   velocities is reported: a ground signal appears in every line of sight alike (l_u ≈ 0.7–0.8 for all), so a tilt
   seen by one product only is a ramp (orbit, atmosphere) that the decomposition would turn into east-west motion.
   ``deramp = "plane"`` removes the fitted plane of every product first (it also removes any real tilt of the area:
   tie to GNSS for that).
4. Per cell, weighted least squares of [l_e, l_u]·[e, u] = v_LOS over the products, with the covariance of (e, u).
"""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.decompose/1"
M_LAT = 110_540.0
M_LON = 111_320.0
COLS = ["lon", "lat", "vel_los_mm_yr", "vel_std_mm_yr", "los_e", "los_n", "los_u"]


@dataclass(frozen=True)
class DecomposeParams:
    """``[postprocess.decompose]`` of project.toml (every key optional)."""

    support: str = "cells"            # "cells" (grid of cell_m) or "points" (neighbourhood of every point)
    cell_m: float = 100.0
    radius_m: float = 20.0            # support "points": neighbourhood radius
    max_neighbours: int = 16
    min_points: int = 3
    min_east_contrast: float = 0.5    # partners must differ this much in l_e (opposite look directions: ~1.2)
    min_overlap_share: float = 0.5    # common period / the shorter period
    sigma_floor_mm_yr: float = 0.5    # lowest uncertainty of a cell velocity
    horizontal_mm_yr: float = 5.0     # east-west motion reported as significant beyond this and 2 σ
    deramp: str = "none"              # "plane": remove a plane fitted to each product's velocities first
    ramp_warning_mm_yr: float = 5.0   # warn when a product's plane spans more than this over the common area

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> DecomposeParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.decompose]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = cls(**{k: type(getattr(cls, k))(v) for k, v in d.items()})
        if out.support not in ("cells", "points"):
            raise ConfigError(f"[postprocess.decompose] support: cells | points, not {out.support!r}")
        if out.deramp not in ("none", "plane"):
            raise ConfigError(f"[postprocess.decompose] deramp: none | plane, not {out.deramp!r}")
        return out


# ---------------------------------------------------------------- products and partners
def describe(product: Path) -> dict:
    """Id, track, period, extent and median LOS vector of a product (from item.json and the points)."""
    it = json.loads((product / "item.json").read_text(encoding="utf-8"))
    p = it["properties"]
    los = pq.read_table(product / "points.parquet", columns=["los_e", "los_n", "los_u"]).to_pandas().median()
    return {"id": it["id"], "path": str(product), "project": p.get("geoeyes:project"), "track": p.get("geoeyes:track"),
            "sensor": p.get("geoeyes:sensor"), "first": p.get("geoeyes:first_date"), "last": p.get("geoeyes:last_date"),
            "bbox": it["bbox"], "los": [round(float(los[k]), 3) for k in ("los_e", "los_n", "los_u")]}


def _latest_products(projects_root: Path) -> list[Path]:
    """The latest version of every (project, track) product of the workspace."""
    best: dict[tuple[str, str], tuple[int, Path]] = {}
    for item in projects_root.glob("*/products/*/item.json"):
        m = re.match(r"^(.*)_v(\d+)$", item.parent.name)
        if not m or not (item.parent / "points.parquet").exists():
            continue
        key = (item.parent.parent.parent.name, m.group(1))
        if key not in best or int(m.group(2)) > best[key][0]:
            best[key] = (int(m.group(2)), item.parent)
    return [p for _, p in best.values()]


def _overlap_days(a: dict, b: dict) -> tuple[int, float]:
    lo = max(date.fromisoformat(a["first"]), date.fromisoformat(b["first"]))
    hi = min(date.fromisoformat(a["last"]), date.fromisoformat(b["last"]))
    days = (hi - lo).days
    shorter = min((date.fromisoformat(x["last"]) - date.fromisoformat(x["first"])).days for x in (a, b))
    return days, (days / shorter if shorter > 0 else 0.0)


def _bbox_overlap(a: list[float], b: list[float]) -> list[float] | None:
    box = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return box if box[0] < box[2] and box[1] < box[3] else None


def partners(product: Path, projects_root: Path, params: DecomposeParams) -> list[dict]:
    """Products that see the area of ``product`` from another direction over an overlapping period."""
    me = describe(product)
    out = []
    for p in _latest_products(projects_root):
        if p.resolve() == product.resolve():
            continue
        try:
            d = describe(p)
        except (OSError, KeyError, ValueError):
            continue
        if d["track"] == me["track"] and d["project"] == me["project"]:
            continue
        if not _bbox_overlap(me["bbox"], d["bbox"]) or abs(d["los"][0] - me["los"][0]) < params.min_east_contrast:
            continue
        days, share = _overlap_days(me, d)
        if days <= 0 or share < params.min_overlap_share:
            continue
        out.append({**d, "overlap_days": days, "overlap_share": round(share, 3)})
    return sorted(out, key=lambda d: -d["overlap_days"])


# ---------------------------------------------------------------- the decomposition
def cell_velocities(pts: pd.DataFrame, grid: dict, params: DecomposeParams) -> pd.DataFrame:
    """Per cell of ``grid``: median LOS velocity and LOS vector, robust uncertainty and number of points."""
    ix = np.floor((pts.lon.to_numpy() - grid["lon0"]) / grid["dlon"]).astype(np.int64)
    iy = np.floor((pts.lat.to_numpy() - grid["lat0"]) / grid["dlat"]).astype(np.int64)
    ok = (ix >= 0) & (ix < grid["nx"]) & (iy >= 0) & (iy < grid["ny"]) & np.isfinite(pts.vel_los_mm_yr.to_numpy())
    df = pts[ok].assign(cell=iy[ok] * grid["nx"] + ix[ok])
    g = df.groupby("cell")
    out = g.agg(v=("vel_los_mm_yr", "median"), l_e=("los_e", "median"), l_n=("los_n", "median"),
                l_u=("los_u", "median"), n=("vel_los_mm_yr", "size"), std=("vel_std_mm_yr", "median"))
    mad = g["vel_los_mm_yr"].apply(lambda x: float(np.median(np.abs(x - np.median(x)))))
    root_n = np.sqrt(out.n)
    out["sigma"] = np.maximum.reduce([1.4826 * mad / root_n, out["std"].fillna(0) / root_n,
                                      np.full(len(out), params.sigma_floor_mm_yr)])
    return out[out.n >= params.min_points].drop(columns="std")


def point_velocities(pts: pd.DataFrame, xy: np.ndarray, kx: float, params: DecomposeParams) -> pd.DataFrame:
    """At each location ``xy`` (local metres): median LOS velocity and LOS vector of the points of ``pts`` within
    ``radius_m``, robust uncertainty and number of points (NaN velocity below ``min_points``)."""
    import warnings

    from scipy.spatial import cKDTree
    tree = cKDTree(np.column_stack([pts.lon.to_numpy() * kx, pts.lat.to_numpy() * M_LAT]))
    k = max(1, min(params.max_neighbours, len(pts)))
    d, i = tree.query(xy, k=k, distance_upper_bound=params.radius_m)
    d, i = d.reshape(len(xy), k), i.reshape(len(xy), k)
    n = np.isfinite(d).sum(1)

    def gather(col):                                   # missing neighbours have the index len(pts): NaN
        return np.append(pts[col].to_numpy(np.float64), np.nan)[i]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # locations without neighbours
        v = gather("vel_los_mm_yr")
        med = np.nanmedian(v, axis=1)
        mad = np.nanmedian(np.abs(v - med[:, None]), axis=1)
        out = pd.DataFrame({"v": med, "l_e": np.nanmedian(gather("los_e"), 1), "l_n": np.nanmedian(gather("los_n"), 1),
                            "l_u": np.nanmedian(gather("los_u"), 1), "n": n})
        std = np.nanmedian(gather("vel_std_mm_yr"), 1)
    root_n = np.sqrt(np.maximum(n, 1))
    out["sigma"] = np.maximum.reduce([1.4826 * mad / root_n, np.nan_to_num(std) / root_n,
                                      np.full(len(out), params.sigma_floor_mm_yr)])
    out.loc[n < params.min_points, "v"] = np.nan
    return out


def fit_plane(x_km: np.ndarray, y_km: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Plane a + b·x + c·y of ``v`` (outliers beyond 3 MAD left out, twice) and its value at every location."""
    a = np.column_stack([np.ones_like(x_km), x_km, y_km])
    keep = np.isfinite(v)
    coef = np.zeros(3)
    for _ in range(3):
        coef = np.linalg.lstsq(a[keep], v[keep], rcond=None)[0]
        r = v - a @ coef
        mad = np.median(np.abs(r[keep] - np.median(r[keep])))
        keep = np.isfinite(v) & (np.abs(r) <= 3 * 1.4826 * max(mad, 1e-6))
    return coef, a @ coef


def solve(v: np.ndarray, sigma: np.ndarray, le: np.ndarray, lu: np.ndarray) -> dict[str, np.ndarray]:
    """Weighted least squares of (east, up) per cell. Arrays are (cells, products)."""
    w = 1.0 / sigma ** 2
    a11 = (w * le * le).sum(1)
    a12 = (w * le * lu).sum(1)
    a22 = (w * lu * lu).sum(1)
    b1 = (w * le * v).sum(1)
    b2 = (w * lu * v).sum(1)
    det = a11 * a22 - a12 ** 2
    east = (a22 * b1 - a12 * b2) / det
    up = (a11 * b2 - a12 * b1) / det
    return {"east": east, "up": up, "sigma_east": np.sqrt(a22 / det), "sigma_up": np.sqrt(a11 / det)}


def _stats(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if not x.size:
        return {}
    q = np.percentile(x, [2, 50, 98])
    return {"min": round(float(x.min()), 2), "p02": round(float(q[0]), 2), "median": round(float(q[1]), 2),
            "p98": round(float(q[2]), 2), "max": round(float(x.max()), 2)}


def run(product: Path, out: Path, params: DecomposeParams, *, projects_root: Path,
        with_products: list[Path] | None = None, progress=None) -> dict:
    """Vertical and east-west motion over ``product`` and its partners into ``out``."""
    say = progress or (lambda m: log.info("%s", m))
    me = describe(product)
    if with_products:
        others = []
        for p in with_products:
            d = describe(p)
            days, share = _overlap_days(me, d)
            others.append({**d, "overlap_days": days, "overlap_share": round(share, 3)})
    else:
        others = partners(product, projects_root, params)
    if not others:
        raise DataError(f"{product.name}: no product of the workspace sees this area from another direction over "
                        "the same period (an ascending track for a descending one, or the reverse)")
    prods = [{**me, "overlap_days": None, "overlap_share": None}, *others]
    say("products: " + ", ".join(f"{p['id']} (l_e {p['los'][0]:+.2f})" for p in prods))
    warnings = []
    for p in others:
        if p["overlap_days"] <= 0:
            warnings.append(f"{p['id']}: no common period with {me['id']}; constant rates are assumed")
        elif p["overlap_share"] < params.min_overlap_share:
            warnings.append(f"{p['id']}: only {p['overlap_days']} common days")

    box = me["bbox"]
    for p in others:
        box = _bbox_overlap(box, p["bbox"]) or box
    lat0 = 0.5 * (box[1] + box[3])
    dlat = params.cell_m / M_LAT
    dlon = params.cell_m / (M_LON * math.cos(math.radians(lat0)))
    grid = {"lon0": box[0], "lat0": box[1], "dlon": dlon, "dlat": dlat,
            "nx": int(math.ceil((box[2] - box[0]) / dlon)), "ny": int(math.ceil((box[3] - box[1]) / dlat))}
    per = []
    pts_all = [pq.read_table(Path(p["path"]) / "points.parquet", columns=COLS).to_pandas() for p in prods]
    if params.support == "points":
        # the locations: the points of the product inside the common extent; per product, its neighbourhood there
        kx = M_LON * math.cos(math.radians(lat0))
        p0 = pts_all[0]
        inside = ((p0.lon >= box[0]) & (p0.lon <= box[2]) & (p0.lat >= box[1]) & (p0.lat <= box[3])).to_numpy()
        loc = p0.loc[inside, ["lon", "lat"]].to_numpy(np.float64)
        xy = np.column_stack([loc[:, 0] * kx, loc[:, 1] * M_LAT])
        for p, pts in zip(prods, pts_all, strict=True):
            per.append(point_velocities(pts, xy, kx, params))
            say(f"{p['id']}: {len(pts)} points, {int(per[-1].v.notna().sum())} of {len(xy)} locations with "
                f"≥ {params.min_points} within {params.radius_m:g} m")
        ok = np.all(np.column_stack([c.v.notna().to_numpy() for c in per]), axis=1)
        common = pd.Index(np.flatnonzero(ok))
        # drawn as squares of 10 m in the web app
        grid = {**grid, "dlon": 10.0 / kx, "dlat": 10.0 / M_LAT}
        lon_out, lat_out = loc[ok, 0], loc[ok, 1]
    else:
        for p, pts in zip(prods, pts_all, strict=True):
            per.append(cell_velocities(pts, grid, params))
            say(f"{p['id']}: {len(pts)} points in {len(per[-1])} cells")
        common = per[0].index
        for c in per[1:]:
            common = common.intersection(c.index)
    if len(common) < 10:
        raise DataError(f"only {len(common)} locations are seen by all the products")
    v = np.column_stack([c.loc[common, "v"].to_numpy() for c in per])
    # the plane of each product: the same ground tilt shows in every line of sight, a ramp in one only
    if params.support == "cells":
        cc = common.to_numpy()
        lon_c = grid["lon0"] + (cc % grid["nx"] + 0.5) * dlon
        lat_c = grid["lat0"] + (cc // grid["nx"] + 0.5) * dlat
    else:
        lon_c, lat_c = lon_out, lat_out
    x_km = (lon_c - lon_c.mean()) * M_LON * math.cos(math.radians(lat0)) / 1000
    y_km = (lat_c - lat_c.mean()) * M_LAT / 1000
    ramps = []
    for k, p in enumerate(prods):
        coef, plane = fit_plane(x_km, y_km, v[:, k])
        span = float(np.ptp(plane))
        ramps.append({"id": p["id"], "mm_yr_per_km": [round(float(coef[1]), 3), round(float(coef[2]), 3)],
                      "span_mm_yr": round(span, 1), "removed": params.deramp == "plane"})
        if params.deramp == "plane":
            v[:, k] -= plane - plane.mean()
    spans = [r["span_mm_yr"] for r in ramps]
    if params.deramp == "none" and max(spans) > params.ramp_warning_mm_yr and max(spans) > 2 * min(spans):
        worst = ramps[int(np.argmax(spans))]
        warnings.append(f"{worst['id']}: its velocities tilt by {worst['span_mm_yr']} mm/yr over the common area, "
                        "the other product's much less: likely a ramp, read as east-west motion (deramp = plane)")
    v = v - np.median(v, axis=0)                                  # common reference: median of the common area
    sig = np.column_stack([c.loc[common, "sigma"].to_numpy() for c in per])
    le = np.column_stack([c.loc[common, "l_e"].to_numpy() for c in per])
    lu = np.column_stack([c.loc[common, "l_u"].to_numpy() for c in per])
    r = solve(v, sig, le, lu)
    cell = common.to_numpy()
    if params.support == "cells":
        iy, ix = cell // grid["nx"], cell % grid["nx"]
        lon_out, lat_out = grid["lon0"] + (ix + 0.5) * dlon, grid["lat0"] + (iy + 0.5) * dlat
    table = pd.DataFrame({"cell": cell.astype(np.int64), "lon": lon_out, "lat": lat_out,
                          **{k: r[k].astype(np.float32) for k in ("up", "east", "sigma_up", "sigma_east")}})
    for k, c in enumerate(per):
        table[f"v_los_{k}"] = v[:, k].astype(np.float32)
        table[f"n_{k}"] = c.loc[common, "n"].to_numpy(np.int32)
        table[f"vert_only_{k}"] = (v[:, k] / lu[:, k]).astype(np.float32)   # what the single geometry would say
    horizontal = (np.abs(r["east"]) >= params.horizontal_mm_yr) & (np.abs(r["east"]) >= 2 * r["sigma_east"])
    table["horizontal"] = horizontal
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "decompose.parquet", index=False)
    if params.support == "cells":
        _write_rasters(out, grid, cell, r)
    bias = {}
    for k, p in enumerate(prods):
        dv = table[f"vert_only_{k}"].to_numpy() - r["up"]
        bias[p["id"]] = {"median_mm_yr": round(float(np.median(dv)), 2),
                         "p90_abs_mm_yr": round(float(np.percentile(np.abs(dv), 90)), 2)}
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": asdict(params), "products": [{k: p[k] for k in ("id", "project", "track", "sensor", "first", "last",
                                                                  "los", "overlap_days", "overlap_share")}
                                               for p in prods],
        "grid": grid, "n_cells": len(table), "up_mm_yr": _stats(r["up"]), "east_mm_yr": _stats(r["east"]),
        "sigma_up_median": round(float(np.median(r["sigma_up"])), 2),
        "sigma_east_median": round(float(np.median(r["sigma_east"])), 2),
        "horizontal_share": round(float(horizontal.mean()), 4), "vertical_only_bias": bias, "ramps": ramps,
        "reference": "median of the common area", "north": "assumed zero", "sign": "up positive, east positive",
        "warnings": warnings, "method": "docs/en/research/two-geometries-and-soft-soil.md",
    }
    atomic_write_json(out / "decompose.json", summary)
    m = Manifest(kind="decompose", id=product.name, engine=SCHEMA,
                 inputs=[InputRef("product", p["path"]) for p in prods], params=summary["params"],
                 metrics={"cells": len(table)})
    m.add_outputs(out, ["decompose.parquet", "decompose.json"]
                  + (["up.tif", "east.tif"] if params.support == "cells" else []))
    m.write(out)
    where = "cells" if params.support == "cells" else "locations"
    say(f"{len(table)} {where}: up {summary['up_mm_yr'].get('median')} mm/yr (median), east-west significant in "
        f"{100 * summary['horizontal_share']:.1f} % of the cells")
    return summary


def _write_rasters(out: Path, grid: dict, cell: np.ndarray, r: dict) -> None:
    import rasterio
    from rasterio.transform import from_origin
    top = grid["lat0"] + grid["ny"] * grid["dlat"]
    tr = from_origin(grid["lon0"], top, grid["dlon"], grid["dlat"])
    iy, ix = cell // grid["nx"], cell % grid["nx"]
    for name in ("up", "east"):
        a = np.full((grid["ny"], grid["nx"]), np.nan, np.float32)
        a[grid["ny"] - 1 - iy, ix] = r[name]
        with rasterio.open(out / f"{name}.tif", "w", driver="GTiff", width=grid["nx"], height=grid["ny"], count=1,
                           dtype="float32", crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate") as ds:
            ds.write(a, 1)
            ds.update_tags(units="mm/yr", sign="up positive" if name == "up" else "east positive")


def read_summary(folder: Path) -> dict | None:
    f = folder / "decompose.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
