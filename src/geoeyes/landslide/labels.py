"""Labels of a landslide study on a metric grid (docs/en/research/landslide-susceptibility.md §5 L1).

Positives, per mapped polygon (the initiation zone, not the runout: Steger et al. 2016):

    a  ``scarp``     the cell of the highest point of the polygon (cell centres inside it and its vertices)
    b  ``upper``     the cells whose centre is inside the polygon, in the upper ``upper_fraction`` of its height
                     range (the scarp cell when none)
    c  ``centroid``  the cell of the centroid (of a point inside the polygon when the centroid is outside);
                     comparison only: it mixes source and runout

One positive per cell and variant (several polygons in a cell: the first one is kept, ``n_polygons`` counts them).

Negatives, per footprint variant: cells whose centre is inside the footprint and the study area, farther than
``negative_buffer_m`` from every polygon of the event, and not a positive of any variant; ``ratio`` × positives
drawn ``draws`` times, each draw from its own seeded generator. ``reactivated``: the polygon intersects a polygon
of an earlier event of the study.

Output, one table per event: ``event, footprint, variant, draw, label, cell, lon, lat, height_m, slope_deg, src_fid,
area_m2, n_polygons, reactivated`` (positives: ``footprint`` empty and ``draw`` = -1).
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.core.errors import DataError
from geoeyes.landslide.study import LabelParams, Study
from geoeyes.ml.layers import M_PER_DEG_LAT, Grid

log = logging.getLogger(__name__)

VARIANTS = ("scarp", "upper", "centroid")
FLAT_DEG = 5.0


def grid_for(bounds, cell_m: float) -> Grid:
    return Grid(list(bounds), cell_m, 0.5 * (bounds[1] + bounds[3]))


def grid_slope(grid: Grid, height: np.ndarray) -> np.ndarray:
    """Slope (degrees) of cell heights on the grid (rows go north)."""
    h = height.reshape(grid.ny, grid.nx).astype(np.float64)
    gy, gx = np.gradient(h, grid.cell_m)
    return np.degrees(np.arctan(np.hypot(gx, gy))).ravel()


def cells_in(grid: Grid, geom) -> np.ndarray:
    """Indices of the cells whose centre lies inside ``geom`` (lon / lat)."""
    import shapely
    w, s, e, n = geom.bounds
    kx0 = max(math.floor(w * grid.kx_m / grid.cell_m) - grid.x0, 0)
    kx1 = min(math.floor(e * grid.kx_m / grid.cell_m) - grid.x0, grid.nx - 1)
    ky0 = max(math.floor(s * M_PER_DEG_LAT / grid.cell_m) - grid.y0, 0)
    ky1 = min(math.floor(n * M_PER_DEG_LAT / grid.cell_m) - grid.y0, grid.ny - 1)
    if kx1 < kx0 or ky1 < ky0:
        return np.empty(0, np.int64)
    kx, ky = np.meshgrid(np.arange(kx0, kx1 + 1), np.arange(ky0, ky1 + 1))
    idx = (ky * grid.nx + kx).ravel()
    return idx[shapely.contains_xy(geom, grid.lon[idx], grid.lat[idx])]


def positives(polys, grid: Grid, height: np.ndarray, dem, earlier=None,
              upper_fraction: float = 1 / 3) -> pd.DataFrame:
    """One row per polygon and variant (before the per-cell deduplication); ``polys`` in lon / lat."""
    import shapely
    react = np.zeros(len(polys), bool)
    if earlier is not None and len(earlier):
        tree = shapely.STRtree(earlier.geometry.values)
        hits = tree.query(polys.geometry.values, predicate="intersects")
        react[np.unique(hits[0])] = True
    rows = []
    for i, (fid, area, g) in enumerate(zip(polys["src_fid"], polys["area_m2"], polys.geometry, strict=True)):
        inside = cells_in(grid, g)
        vx, vy = shapely.get_coordinates(shapely.boundary(g)).T
        hv = dem.orthometric(vy, vx)
        hi = height[inside]
        cand_h = np.concatenate([hi, hv])
        if not np.isfinite(cand_h).any():
            continue
        k = int(np.nanargmax(cand_h))
        top = inside[k] if k < len(inside) else int(grid.cell_of(vx[k - len(inside)], vy[k - len(inside)]))
        lo, hi_max = np.nanmin(cand_h), np.nanmax(cand_h)
        upper = inside[hi >= hi_max - upper_fraction * (hi_max - lo)] if len(inside) else np.empty(0, np.int64)
        if not len(upper):
            upper = np.array([top])
        c = g.centroid if g.contains(g.centroid) else g.representative_point()
        cen = int(grid.cell_of(c.x, c.y))
        for variant, cells in (("scarp", [top]), ("upper", upper), ("centroid", [cen])):
            for cell in cells:
                if cell >= 0:
                    rows.append((variant, int(cell), int(fid), float(area), bool(react[i])))
    return pd.DataFrame(rows, columns=["variant", "cell", "src_fid", "area_m2", "reactivated"])


def exclusion(polys, buffer_m: float):
    """The polygons grown by ``buffer_m`` (metres), back in lon / lat."""
    import geopandas as gpd
    import shapely
    crs = polys.estimate_utm_crs()
    grown = shapely.union_all(polys.to_crs(crs).geometry.buffer(buffer_m, 4).values)
    return gpd.GeoSeries([grown], crs=crs).to_crs(4326).iloc[0]


def make_labels(polys, footprints: dict, area, grid: Grid, height: np.ndarray, slope: np.ndarray, dem,
                params: LabelParams, event: str, earlier=None) -> tuple[pd.DataFrame, dict]:
    """Labels of one event: ``polys`` (its polygons, lon / lat, with ``src_fid``, ``area_m2``), ``footprints``
    {variant: geometry}, ``area`` the study area; ``height`` / ``slope`` per grid cell."""
    import shapely
    in_area = np.zeros(len(grid), bool)
    in_area[cells_in(grid, area)] = True
    pos = positives(polys, grid, height, dem, earlier, params.upper_fraction)
    pos = pos[in_area[pos["cell"].to_numpy()]]
    n_poly = pos.groupby(["variant", "cell"]).size().rename("n_polygons")
    pos = pos.drop_duplicates(["variant", "cell"]).join(n_poly, on=["variant", "cell"])
    pos = pos.assign(event=event, footprint="", draw=-1, label=1)

    blocked = np.zeros(len(grid), bool)
    blocked[cells_in(grid, exclusion(polys, params.negative_buffer_m))] = True
    blocked[pos["cell"].to_numpy()] = True
    neg_parts, summary = [], {"polygons": int(len(polys)), "positives": {}, "candidates": {}, "short": []}
    for v in VARIANTS:
        summary["positives"][v] = int((pos.variant == v).sum())
    for fi, (fname, fgeom) in enumerate(footprints.items()):
        cand = np.zeros(len(grid), bool)
        cand[cells_in(grid, shapely.intersection(fgeom, area))] = True
        cand &= ~blocked & np.isfinite(height)
        pool = np.flatnonzero(cand)
        summary["candidates"][fname] = int(len(pool))
        for vi, v in enumerate(VARIANTS):
            n = int(round(params.ratio * summary["positives"][v]))
            if n > len(pool):
                summary["short"].append(f"{fname}/{v}: {len(pool)} candidates for {n} negatives")
                n = len(pool)
            for d in range(params.draws):
                rng = np.random.default_rng([params.seed, d, vi, fi])
                pick = np.sort(rng.choice(pool, n, replace=False))
                neg_parts.append(pd.DataFrame({"event": event, "footprint": fname, "variant": v, "draw": d,
                                               "label": 0, "cell": pick}))
    out = pd.concat([pos, *neg_parts], ignore_index=True)
    c = out["cell"].to_numpy()
    out = out.assign(lon=grid.lon[c], lat=grid.lat[c], height_m=height[c].round(1), slope_deg=slope[c].round(2))
    out[["src_fid", "n_polygons"]] = out[["src_fid", "n_polygons"]].fillna(-1).astype(int)
    out["area_m2"] = out["area_m2"].fillna(0.0)
    out["reactivated"] = out["reactivated"].astype("boolean").fillna(False).astype(bool)
    cols = ["event", "footprint", "variant", "draw", "label", "cell", "lon", "lat", "height_m", "slope_deg",
            "src_fid", "area_m2", "n_polygons", "reactivated"]
    out = out[cols]
    summary["reactivated_positives"] = int(out[(out.label == 1) & (out.variant == "scarp")]["reactivated"].sum())
    summary["slope_deg"] = _slope_summary(out)
    return out, summary


def _slope_summary(t: pd.DataFrame) -> dict:
    def s(x):
        x = x.dropna()
        return {"n": int(len(x)), "p5": round(float(np.percentile(x, 5)), 1), "median": round(float(np.median(x)), 1),
                "p95": round(float(np.percentile(x, 95)), 1), "below_5deg": round(float((x < FLAT_DEG).mean()), 3)}
    out = {f"positive/{v}": s(g["slope_deg"]) for v, g in t[t.label == 1].groupby("variant")}
    for f, g in t[(t.label == 0) & (t.draw == 0) & (t.variant == "scarp")].groupby("footprint"):
        out[f"negative/{f}"] = s(g["slope_deg"])
    return out


# ---------------------------------------------------------------- the study step
def study_area(study: Study):
    """The study area (lon / lat): the row of ``[area]``."""
    import geopandas as gpd
    a = gpd.read_file(study.area_file, layer=study.area_layer)
    row = a[a["name"] == study.area_name]
    if row.empty:
        raise DataError(f"{study.area_file}: no row named {study.area_name!r} in layer {study.area_layer!r}")
    return row.to_crs(4326).geometry.iloc[0]


def run_labels(study: Study, dem_cache: Path) -> dict:
    """L1 of a study: ``labels/labels_<event>.parquet``, ``labels.json``, quicklook maps, manifest."""
    import geopandas as gpd

    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    p = study.labels
    area = study_area(study)
    fps = gpd.read_file(study.footprints, layer="footprints")
    polys_all = gpd.read_file(study.inventory, layer="polygons").to_crs(4326)
    w, s, e, n = area.bounds
    dem = load_copernicus30(s - 0.02, n + 0.02, w - 0.02, e + 0.02, dem_cache)
    grid = grid_for(area.bounds, p.cell_m)
    height = dem.orthometric(grid.lat, grid.lon)
    slope = grid_slope(grid, height)
    log.info("grid %d x %d cells of %.0f m over %s", grid.nx, grid.ny, p.cell_m, [round(v, 3) for v in area.bounds])

    out_dir = study.step_dir("labels")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"study": study.name, "citation": study.citation, "params": asdict(p), "area": study.area_name,
               "area_bounds": [round(v, 4) for v in area.bounds], "grid": {"nx": grid.nx, "ny": grid.ny},
               "footprints": {"main": study.footprint_main, "sensitivity": study.footprint_sensitivity},
               "events": {}}
    tables, done = {}, []
    for name, date in study.events:
        ev = polys_all[polys_all.event == name]
        ev = ev[ev.geometry.intersects(area)]
        if ev.empty:
            raise DataError(f"event {name}: no polygon in the study area")
        f = fps[fps.event == name].set_index("variant").geometry
        footprints = {v: f[v] for v in (study.footprint_main, study.footprint_sensitivity)}
        earlier = polys_all[polys_all.event.isin(done)] if done else None
        t, smy = make_labels(ev, footprints, area, grid, height, slope, dem, p, name, earlier)
        smy["date"] = date
        t.to_parquet(out_dir / f"labels_{name}.parquet", index=False)
        tables[name] = t
        summary["events"][name] = smy
        done.append(name)
        log.info("%s: %d polygons, positives %s", name, smy["polygons"], smy["positives"])

    maps = quicklook(tables, polys_all, area, dem, out_dir)
    atomic_write_json(out_dir / "labels.json", summary)
    m = Manifest(kind="landslide_labels", id=f"{study.name}/labels", engine="geoeyes.landslide.labels",
                 inputs=[InputRef("inventory", str(study.inventory)), InputRef("footprints", str(study.footprints)),
                         InputRef("area", f"{study.area_file}#{study.area_layer}/{study.area_name}"),
                         InputRef("dem", "Copernicus GLO-30")],
                 params={"labels": asdict(p)}, metrics={k: v["positives"] for k, v in summary["events"].items()})
    m.add_outputs(out_dir, [f"labels_{e}.parquet" for e in tables] + ["labels.json"] + maps)
    m.write(out_dir)
    return summary


def quicklook(tables: dict, polys, area, dem, out_dir: Path, n_windows: int = 3, half_m: float = 750.0) -> list[str]:
    """Maps of a few 1.5 km windows per event: polygons, positives of each variant, negatives of the first draw."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = []
    for ev, t in tables.items():
        pos = t[(t.label == 1) & (t.variant == "scarp")].sort_values("lon")
        if pos.empty:
            continue
        # windows on the busiest cells at a few longitudes (deterministic)
        picks = [pos.iloc[int(q * (len(pos) - 1))] for q in np.linspace(0.2, 0.8, n_windows)]
        fig, axs = plt.subplots(1, n_windows, figsize=(5 * n_windows, 5.2))
        for ax, c in zip(np.atleast_1d(axs), picks, strict=True):
            dlat = half_m / M_PER_DEG_LAT
            dlon = half_m / (111_320.0 * math.cos(math.radians(c.lat)))
            box = (c.lon - dlon, c.lat - dlat, c.lon + dlon, c.lat + dlat)
            r0 = int((dem.lat0 - box[3]) / dem.dlat)
            r1 = int((dem.lat0 - box[1]) / dem.dlat) + 1
            c0 = int((box[0] - dem.lon0) / dem.dlon)
            c1 = int((box[2] - dem.lon0) / dem.dlon) + 1
            sub = dem.height[r0:r1, c0:c1]
            hs = matplotlib.colors.LightSource(azdeg=315, altdeg=45).hillshade(
                sub, dx=dem.dlon * 111_320 * math.cos(math.radians(c.lat)), dy=dem.dlat * M_PER_DEG_LAT)
            ext = (dem.lon0 + c0 * dem.dlon, dem.lon0 + c1 * dem.dlon,
                   dem.lat0 - r1 * dem.dlat, dem.lat0 - r0 * dem.dlat)
            ax.imshow(hs, cmap="gray", extent=ext, vmin=0, vmax=1)
            ax.contour(np.linspace(ext[0], ext[1], sub.shape[1]), np.linspace(ext[3], ext[2], sub.shape[0]), sub,
                       levels=12, colors="white", linewidths=0.3, alpha=0.6)
            pv = polys[(polys.event == ev)].cx[box[0]:box[2], box[1]:box[3]]
            pv.boundary.plot(ax=ax, color="yellow", lw=0.9)
            inb = t[(t.lon > box[0]) & (t.lon < box[2]) & (t.lat > box[1]) & (t.lat < box[3])]
            for v, kw in (("upper", dict(marker="s", s=10, c="orange", alpha=0.7, label="b upper third")),
                          ("centroid", dict(marker="x", s=25, c="deepskyblue", label="c centroid")),
                          ("scarp", dict(marker="^", s=30, c="red", edgecolors="k", lw=0.4, label="a scarp"))):
                q = inb[(inb.label == 1) & (inb.variant == v)]
                ax.scatter(q.lon, q.lat, **kw)
            neg = inb[(inb.label == 0) & (inb.draw == 0) & (inb.variant == "scarp")]
            for f, (mk, col) in zip(dict.fromkeys(neg.footprint), (("o", "lime"), ("+", "magenta")), strict=False):
                q = neg[neg.footprint == f]
                ax.scatter(q.lon, q.lat, marker=mk, s=12, c=col, label=f"negative ({f}, draw 0)")
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_title(f"{ev} near {c.lon:.3f}°E {c.lat:.3f}°N", fontsize=9)
            ax.tick_params(labelsize=7)
        np.atleast_1d(axs)[0].legend(fontsize=7, loc="lower left")
        fig.suptitle(f"L1 labels, {ev} (30 m cells; contours = GLO-30). Data: Das (2024), CC-BY-4.0", fontsize=10)
        fig.tight_layout()
        name = f"labels_{ev}.png"
        fig.savefig(out_dir / name, dpi=110)
        plt.close(fig)
        out.append(name)
    return out
