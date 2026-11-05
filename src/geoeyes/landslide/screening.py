"""Screening the Sentinel-2 objects: landslide or not (docs/en/research/landslide-susceptibility.md L3b.7).

NDVI thresholds alone keep the swidden fields, plantation clearings and flood deposits of a forest–field mosaic (a
blind visual check of 2025: 12 % landslides). The objects are therefore classified on what tells them apart by eye:

* spectrum: NDVI and SWIR before and after (a fresh scar is bare rock or soil, bright in SWIR; a field is a dry
  crop or burnt ground);
* shape: area, elongation of the rotated rectangle, compactness, drop ratio (a landslide runs down the slope);
* terrain (30 m study grid): slope, HAND, TPI at the head, distance to a stream (a scar starts high, a deposit lies
  low);
* context: forest share around the object before (fields come in mosaics), number of other objects within 500 m
  (storm landslides come in clusters).

Training: the objects of the calibration event, labelled by whether they touch an inventory polygon (Das 2024;
noisy: Das misses scars). The classifier is checked on the visual labels of another event, never trained on them.
Output: ``scars/screening_<event>.parquet`` (features, ``p_landslide``) and ``scars/screening.json``.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CONTEXT_PX = 31            # 310 m: forest share around an object
CLUSTER_M = 500.0
FEATURES = ("ndvi_pre", "ndvi_post", "dndvi", "swir_pre", "swir_post", "dswir", "area_m2", "elongation",
            "compactness", "drop_ratio", "slope_mean", "slope_max", "hand_max", "tpi150_head", "dist_stream_min",
            "profile_curv_mean", "forest_around", "neighbours_500m")


def features(polys, grid, comps: tuple, study) -> pd.DataFrame:
    """One row per polygon (row order) with FEATURES; ``comps`` = (before, after) composites of the event."""
    from scipy import ndimage
    from scipy.ndimage import uniform_filter
    from scipy.spatial import cKDTree

    from geoeyes.landslide.dating import label_raster
    from geoeyes.landslide.labels import cells_in, grid_for, study_area
    pre, post = comps
    lab = label_raster(polys, grid)
    idx = np.arange(1, len(polys) + 1)

    def mean(a):
        return np.asarray(ndimage.mean(np.nan_to_num(a), lab, idx))

    with np.errstate(invalid="ignore"):
        forest = uniform_filter((pre[0] >= 0.75).astype(np.float32), CONTEXT_PX, mode="nearest")
    t = pd.DataFrame({"ndvi_pre": mean(pre[0]), "ndvi_post": mean(post[0]), "swir_pre": mean(pre[1]),
                      "swir_post": mean(post[1]), "forest_around": mean(forest)})
    t["dndvi"], t["dswir"] = t.ndvi_pre - t.ndvi_post, t.swir_post - t.swir_pre
    u = polys.to_crs(grid.epsg)
    t["area_m2"] = u.area.to_numpy()
    rect = u.geometry.minimum_rotated_rectangle()
    sides = []
    for r in rect:
        x, y = r.exterior.coords.xy
        a, b = np.hypot(x[1] - x[0], y[1] - y[0]), np.hypot(x[2] - x[1], y[2] - y[1])
        sides.append(max(a, b) / max(min(a, b), 1.0))
    t["elongation"] = sides
    t["compactness"] = (4 * np.pi * u.area / u.length.clip(lower=1) ** 2).to_numpy()
    t["drop_ratio"] = polys["drop_ratio"].to_numpy() if "drop_ratio" in polys else np.nan
    c = np.column_stack([u.centroid.x, u.centroid.y])
    tree = cKDTree(c)
    t["neighbours_500m"] = [len(v) - 1 for v in tree.query_ball_point(c, CLUSTER_M)]
    g30 = grid_for(study_area(study).bounds, study.labels.cell_m)
    pred = pd.read_parquet(study.step_dir("predictors") / f"predictors_{study.events[-1][0]}.parquet",
                           columns=["cell", "slope_deg", "hand_m", "tpi_150", "dist_stream_m", "profile_curv",
                                    "height_m"]).set_index("cell")
    rows = []
    for g in polys.geometry:
        cells = cells_in(g30, g)
        rp = g.representative_point()
        c0 = int(g30.cell_of(rp.x, rp.y))
        if c0 >= 0:
            cells = np.union1d(cells, [c0])
        p = pred.reindex(cells).dropna(how="all")
        if p.empty:
            rows.append([np.nan] * 6)
            continue
        head = p.height_m.idxmax()
        rows.append([p.slope_deg.mean(), p.slope_deg.max(), p.hand_m.max(), p.tpi_150.loc[head],
                     p.dist_stream_m.min(), p.profile_curv.mean()])
    t[["slope_mean", "slope_max", "hand_max", "tpi150_head", "dist_stream_min", "profile_curv_mean"]] = rows
    return t


def classifier(seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
                                          l2_regularization=1.0, class_weight="balanced", random_state=seed)


def spatial_cv_auc(x: pd.DataFrame, y: np.ndarray, xy: np.ndarray, block_m: float = 5000.0, folds: int = 5) -> float:
    from sklearn.base import clone
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    g = (np.floor(xy[:, 0] / block_m) * 1e5 + np.floor(xy[:, 1] / block_m)).astype(np.int64)
    p = np.full(len(y), np.nan)
    for tr, te in GroupKFold(min(folds, len(np.unique(g)))).split(x, y, g):
        p[te] = clone(classifier()).fit(x.iloc[tr], y[tr]).predict_proba(x.iloc[te])[:, 1]
    return float(roc_auc_score(y, p))


def run_screening(study, visual_labels: pd.DataFrame | None = None, progress=None) -> dict:
    """Train on the calibration event (``in_inventory``), score every event's objects; with ``visual_labels``
    (columns ``event, src_fid, label`` in L / C / D / U), the AUC and the precision on them."""
    import geopandas as gpd

    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide.labels import study_area
    from geoeyes.landslide.scars import CALIBRATION, WINDOWS, UtmGrid, read_composite
    say = progress or (lambda m: log.info("%s", m))
    area = study_area(study)
    grid = UtmGrid.around(area.bounds)
    d = study.step_dir("scars")
    tables = {}
    for ev in WINDOWS:
        polys = gpd.read_file(d / f"scars_{ev}.gpkg", layer="polygons")
        comps = (read_composite(d / f"composite_{ev}_before.tif"), read_composite(d / f"composite_{ev}_after.tif"))
        say(f"screening: features of {len(polys)} {ev} objects")
        t = features(polys, grid, comps, study)
        t["src_fid"] = polys.src_fid.to_numpy()
        if "in_inventory" in polys:
            t["in_inventory"] = polys.in_inventory.to_numpy()
        u = polys.to_crs(grid.epsg).centroid
        t["x"], t["y"] = u.x.to_numpy(), u.y.to_numpy()
        tables[ev] = t
    tr = tables[CALIBRATION]
    x, y = tr[list(FEATURES)], tr.in_inventory.astype(int).to_numpy()
    res: dict = {"features": list(FEATURES), "train": CALIBRATION, "train_objects": int(len(tr)),
                 "train_positive": int(y.sum()),
                 "spatial_cv_auc_vs_inventory": round(spatial_cv_auc(x, y, tr[["x", "y"]].to_numpy()), 3)}
    model = classifier().fit(x, y)
    from sklearn.inspection import permutation_importance
    imp = permutation_importance(model, x, y, scoring="roc_auc", n_repeats=5, random_state=0)
    res["importance"] = dict(sorted(((f, round(float(v), 4)) for f, v in zip(FEATURES, imp.importances_mean,
                                                                              strict=True)), key=lambda kv: -kv[1]))
    for ev, t in tables.items():
        t["p_landslide"] = model.predict_proba(t[list(FEATURES)])[:, 1]
        t.to_parquet(d / f"screening_{ev}.parquet", index=False)
    if visual_labels is not None:
        from sklearn.metrics import roc_auc_score
        out = {}
        for ev, g in visual_labels.groupby("event"):
            m = g.merge(tables[ev][["src_fid", "p_landslide"]], on="src_fid")
            m = m[m.label != "U"]
            yy = (m.label == "L").astype(int).to_numpy()
            r = {"labelled": int(len(m)), "landslides": int(yy.sum())}
            if 0 < yy.sum() < len(yy):
                r["auc"] = round(float(roc_auc_score(yy, m.p_landslide)), 3)
                for thr in (0.5, 0.7, 0.8):
                    k = m.p_landslide >= thr
                    r[f"precision_at_{thr}"] = round(float(yy[k.to_numpy()].mean()), 3) if k.any() else None
                    r[f"kept_at_{thr}"] = int(k.sum())
            out[ev] = r
        res["visual_check"] = out
    res["share_above"] = {ev: {str(thr): round(float((t.p_landslide >= thr).mean()), 4) for thr in (0.5, 0.7, 0.8)}
                          for ev, t in tables.items()}
    atomic_write_json(d / "screening.json", res)
    return res
