"""Reliability of the mapped landslides, from the terrain only (docs/en/research/landslide-susceptibility.md L3b.6).

An inventory is an interpretation of images: a patch of lost vegetation is not always a landslide. Every polygon
(Das 2024 and the Sentinel-2 scars alike) gets a class from thresholds of physical plausibility — not from the
model's continuous layers:

    implausible   its steepest cell < ``MIN_SLOPE`` on both GLO-30 and AW3D30, or wholly on a valley floor (every
                  cell's HAND < ``MAX_HAND_M``) within ``BANK_M`` of a stream draining ≥ 1 km² (bank erosion; a debris
                  flow that runs down to a stream from higher up is not flagged)
    doubtful      steepest cell < ``DOUBT_SLOPE``, or a vertical drop < ``MIN_DROP_M`` over the polygon, or forest
                  already lost on ≥ ``CLEARED`` of its cells in the ``PRE_YEARS`` years before the event (a clearing
                  mistaken for a scar)
    reliable      the rest

Output per event: ``labels/reliability_<event>.parquet`` (src_fid, the measures, ``reliability``) and
``labels/reliability.json`` (shares per class).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

MIN_SLOPE = 15.0
DOUBT_SLOPE = 20.0
MAX_HAND_M = 5.0
BANK_M = 30.0
MIN_DROP_M = 10.0
CLEARED = 0.5
PRE_YEARS = 3
CLASSES = ("reliable", "doubtful", "implausible")


def full(grid, table: pd.DataFrame, column: str) -> np.ndarray:
    """A per-cell layer of a predictor table on the whole grid (NaN outside its rows)."""
    a = np.full(len(grid), np.nan, np.float32)
    if column in table:
        a[table.cell.to_numpy()] = table[column].to_numpy(np.float32)
    return a


def polygon_terrain(polys, grid, layers: dict[str, np.ndarray], dem, loss_pre: np.ndarray | None) -> pd.DataFrame:
    """Per polygon (lon / lat, ``src_fid``): steepest cell on each DEM, lowest HAND, nearest 1 km² stream, vertical
    drop (cells and vertices), share of cells already cleared before the event."""
    import shapely

    from geoeyes.landslide.labels import cells_in
    rows = []
    for fid, g in zip(polys["src_fid"], polys.geometry, strict=True):
        cells = cells_in(grid, g)
        rp = g.representative_point()
        c0 = int(grid.cell_of(rp.x, rp.y))
        if c0 >= 0:
            cells = np.union1d(cells, [c0])
        vx, vy = shapely.get_coordinates(shapely.boundary(g)).T
        h = np.concatenate([dem.orthometric(grid.lat[cells], grid.lon[cells]), dem.orthometric(vy, vx)])

        def agg(name, fn, cells=cells):
            v = layers.get(name)
            if v is None or not len(cells):
                return np.nan
            x = v[cells]
            return float(fn(x)) if np.isfinite(x).any() else np.nan

        rows.append({"src_fid": int(fid), "cells": int(len(cells)),
                     "max_slope": agg("slope_deg", np.nanmax), "max_slope_aw3d30": agg("aw3d30_slope_deg", np.nanmax),
                     "max_hand_m": agg("hand_m", np.nanmax), "min_dist_stream_1km2_m": agg("dist_stream_1p0_m",
                                                                                          np.nanmin),
                     "drop_m": float(np.nanmax(h) - np.nanmin(h)) if np.isfinite(h).any() else np.nan,
                     "cleared_before": float(np.nanmean(loss_pre[cells] > 0)) if loss_pre is not None and len(cells)
                     else np.nan})
    return pd.DataFrame(rows)


def classify(t: pd.DataFrame) -> pd.Series:
    steep = np.fmax(t.max_slope.to_numpy(float), t.max_slope_aw3d30.to_numpy(float))
    bank = (t.max_hand_m < MAX_HAND_M) & (t.min_dist_stream_1km2_m <= BANK_M)    # the whole polygon on the floor
    implausible = (steep < MIN_SLOPE) | bank
    doubtful = (steep < DOUBT_SLOPE) | (t.drop_m < MIN_DROP_M) | (t.cleared_before >= CLEARED)
    return pd.Series(np.where(implausible, "implausible", np.where(doubtful, "doubtful", "reliable")), index=t.index)


def flags(polys, grid, table: pd.DataFrame, dem, event_year: int | None) -> pd.DataFrame:
    """The measures and the class of every polygon of one event; ``table``: a predictor table of the grid."""
    from geoeyes.landslide.verify import hansen_loss
    layers = {c: full(grid, table, c) for c in ("slope_deg", "aw3d30_slope_deg", "hand_m", "dist_stream_1p0_m")}
    loss_pre = None
    if event_year is not None:
        years = tuple(range(event_year - PRE_YEARS - 2000, event_year - 2000))
        try:
            loss_pre = hansen_loss(grid, years)
        except Exception as exc:                     # the clearing test is left out without Hansen
            log.warning("Hansen loss before %s not read: %s", event_year, exc)
    t = polygon_terrain(polys, grid, layers, dem, loss_pre)
    t["reliability"] = classify(t)
    return t


def run_reliability(study, cache_root) -> dict:
    """L3b.6: the class of every polygon of the study's events, ``labels/reliability_<event>.parquet``."""
    import geopandas as gpd

    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide.labels import grid_for, study_area
    area = study_area(study)
    grid = grid_for(area.bounds, study.labels.cell_m)
    w, s, e, n = area.bounds
    dem = load_copernicus30(s - 0.02, n + 0.02, w - 0.02, e + 0.02, cache_root / "dem" / "copernicus-30")
    polys = gpd.read_file(study.inventory, layer="polygons").to_crs(4326)
    out_dir = study.step_dir("labels")
    res: dict = {"thresholds": {"min_slope": MIN_SLOPE, "doubt_slope": DOUBT_SLOPE, "max_hand_m": MAX_HAND_M,
                                "bank_m": BANK_M, "min_drop_m": MIN_DROP_M, "cleared": CLEARED,
                                "pre_years": PRE_YEARS}, "events": {}}
    for name, date in study.events:
        ev = polys[(polys.event == name) & polys.geometry.intersects(area)]
        table = pd.read_parquet(study.step_dir("predictors") / f"predictors_{name}.parquet")
        t = flags(ev, grid, table, dem, int(date[:4]))
        t.to_parquet(out_dir / f"reliability_{name}.parquet", index=False)
        res["events"][name] = summary(t)
        log.info("%s: %s", name, res["events"][name]["share"])
    atomic_write_json(out_dir / "reliability.json", res)
    return res


def summary(t: pd.DataFrame) -> dict:
    share = t.reliability.value_counts(normalize=True)
    reasons = {"steepest < 15° (both DEMs)": float(np.mean(np.fmax(t.max_slope, t.max_slope_aw3d30) < MIN_SLOPE)),
               "valley floor near a stream": float(np.mean((t.max_hand_m < MAX_HAND_M)
                                                           & (t.min_dist_stream_1km2_m <= BANK_M))),
               "steepest 15–20°": float(np.mean((np.fmax(t.max_slope, t.max_slope_aw3d30) >= MIN_SLOPE)
                                                & (np.fmax(t.max_slope, t.max_slope_aw3d30) < DOUBT_SLOPE))),
               f"drop < {MIN_DROP_M:g} m": float(np.mean(t.drop_m < MIN_DROP_M)),
               "cleared before": float(np.mean(t.cleared_before >= CLEARED))}
    return {"polygons": int(len(t)), "share": {c: round(float(share.get(c, 0.0)), 4) for c in CLASSES},
            "reasons": {k: round(v, 4) for k, v in reasons.items()}}
