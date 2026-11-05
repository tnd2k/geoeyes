"""Susceptibility models of a landslide study (docs/en/research/landslide-susceptibility.md §5 L3).

Per event, on the L1 labels and the L2 predictors (the screened sets of ``predictors.json``: the trees' and the
logistic model's; ``[models] exclude`` and, unless ``[models] aspect``, the aspect layers left out — L2 / L2a / L2b
gates):

* models: logistic regression, random forest, gradient boosting (``ml.susceptibility``), and gradient boosting with
  monotonic constraints (slope +, TWI −: the directions of L2) as a plausibility check;
* validation: spatial block cross-validation (``[models] blocks_m``, grouped folds) and random cross-validation
  beside it; ROC AUC, average precision, Brier score; mean ± sd over the negative draws; the semivariogram range of
  the residuals against the block sizes (Brenning 2005);
* variants (first block size, 5 draws): label variants upper / centroid, without the road distance, without the
  reactivations, without negatives flatter than 5°, with aspect, the sensitivity footprint, positives ≥
  ``min_area_m2``;
* transfer: trained on one event, tested on the other inside the overlap of their main footprints (also with the
  positives ≥ ``min_area_m2`` only), against the within-event spatial cross-validation on the same cells;
* interpretation: permutation importance on the held-out blocks, logistic odds ratios per standard deviation, partial
  dependence of the main layers, calibration of the spatial out-of-fold probabilities;
* map: the best model by spatial AUC, fitted on every draw, averaged over the main footprint: ``susceptibility.tif``
  (balanced probability, classes at 0.2 / 0.4 / 0.6 / 0.8 as ``ml.susceptibility``) and the probability brought back
  to the real prevalence (prior correction).
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

ASPECT = ("aspect_sin", "aspect_cos")
FLAT_DEG = 5.0
VARIANT_DRAWS = 5
TEST_DRAWS = 5
CLASSES = (0.2, 0.4, 0.6, 0.8)
MONOTONIC = {"slope_deg": 1, "twi": -1}
PD_LAYERS = ("slope_deg", "relief_300", "twi", "profile_curv", "soil_clay", "height_m", "hand_m",
             "upslope_slope_deg")
SOIL = ("soil_clay", "soil_sand", "soil_thick_m")
HILLSLOPE = ("slope_s90", "profile_curv_s150", "plan_curv_s150", "hand_m", "upslope_slope_deg", "spi", "tpi_1000",
             "relief_1000")                                     # L3b.2
NOT_TERRAIN_FOREST = (*SOIL, "lith_*", "height_m", "dist_road_m")
FOREST_LAYERS = ("tree_cover_2000", "loss_before", "loss_before_300m", "tree_cover_event")   # Hansen
TEST_SPECS = ("main", "with_roads", "no_soil", "no_height", "terrain_forest", "l2_terrain", "dem_aw3d30",
              "no_forest", "terrain_only")


@dataclass(frozen=True)
class Spec:
    """One configuration of the data: which positives, which negatives, which layers."""

    label: str = "scarp"
    footprint: str = ""              # "" = the study's main footprint
    roads: bool = True
    reactivated: bool = True
    flat_negatives: bool = True
    aspect: bool = False
    min_area_m2: float = 0.0
    drop: tuple[str, ...] = ()       # layers left out (``prefix*`` patterns allowed)
    dem: str = ""                    # "" = Copernicus GLO-30; "aw3d30": the terrain layers from JAXA AW3D30
    reliable: bool = False           # positives of polygons classed reliable only (L3b.6)
    domain_deg: float = 0.0          # positives and negatives on cells at least this steep (0: every cell)


def variants(main: Spec, min_area: float, sensitivity: str) -> dict[str, Spec]:
    roads = {"with_roads": replace(main, roads=True)} if not main.roads else {"no_roads": replace(main, roads=False)}
    return {"upper": replace(main, label="upper"), "centroid": replace(main, label="centroid"), **roads,
            "no_reactivated": replace(main, reactivated=False),
            "no_flat_negatives": replace(main, flat_negatives=False), "with_aspect": replace(main, aspect=True),
            "sensitivity_footprint": replace(main, footprint=sensitivity),
            f"area_ge_{min_area:g}": replace(main, min_area_m2=min_area),
            "no_soil": replace(main, drop=main.drop + SOIL), "no_height": replace(main, drop=(*main.drop, "height_m")),
            "terrain_forest": replace(main, drop=main.drop + NOT_TERRAIN_FOREST, roads=False),
            "l2_terrain": replace(main, drop=main.drop + HILLSLOPE), "dem_aw3d30": replace(main, dem="aw3d30"),
            "no_forest": replace(main, drop=main.drop + FOREST_LAYERS),
            "terrain_only": replace(main, drop=main.drop + NOT_TERRAIN_FOREST + FOREST_LAYERS, roads=False),
            **({"all_positives": replace(main, reliable=False)} if main.reliable else {}),
            **({"full_domain": replace(main, reliable=False, domain_deg=0.0)} if main.domain_deg else {})}


def _dropped(c: str, drop: tuple[str, ...]) -> bool:
    return any(c == d or (d.endswith("*") and c.startswith(d[:-1])) for d in drop)


# ---------------------------------------------------------------- data
class EventData:
    """Labels, predictors and screened layer sets of one event."""

    def __init__(self, study, event: str, nx: int):
        import json
        self.study, self.event, self.nx = study, event, nx
        self.labels = pd.read_parquet(study.step_dir("labels") / f"labels_{event}.parquet")
        self.pred = pd.read_parquet(study.step_dir("predictors") / f"predictors_{event}.parquet")
        scr = json.loads((study.step_dir("predictors") / "predictors.json").read_text(encoding="utf-8"))
        self.screen = scr["events"][event]["screen"]
        self.draws = int(self.labels.draw.max()) + 1
        rf = study.step_dir("labels") / f"reliability_{event}.parquet"
        self.reliability = pd.read_parquet(rf)[["src_fid", "reliability"]] if rf.exists() else None

    def columns(self, spec: Spec, kind: str) -> list[str]:
        """Layer set of ``kind`` (``trees`` | ``logistic``) for a spec."""
        p = self.study.models
        cols = [c for c in self.screen[kind] if c not in p.exclude and c not in ASPECT and not _dropped(c, spec.drop)]
        if not spec.roads:
            cols = [c for c in cols if c != "dist_road_m"]
        if spec.aspect:
            cols += [c for c in ASPECT if c in self.pred]
        return cols

    def rows(self, spec: Spec, draw: int) -> pd.DataFrame:
        lab = self.labels
        fp = spec.footprint or self.study.footprint_main
        pos = lab[(lab.label == 1) & (lab.variant == spec.label)]
        if not spec.reactivated:
            pos = pos[~pos.reactivated]
        if spec.min_area_m2:
            pos = pos[pos.area_m2 >= spec.min_area_m2]
        if spec.reliable:
            if self.reliability is None:
                raise KeyError(f"no reliability flags for {self.event}: run `geoeyes landslide reliability`")
            ok = self.reliability.src_fid[self.reliability.reliability == "reliable"]
            pos = pos[pos.src_fid.isin(ok)]
        neg = lab[(lab.label == 0) & (lab.variant == spec.label) & (lab.footprint == fp) & (lab.draw == draw)]
        if not spec.flat_negatives:
            neg = neg[neg.slope_deg >= FLAT_DEG]
        t = pd.concat([pos, neg])[["cell", "label", "area_m2"]].merge(self.pred, on="cell", how="inner")
        if spec.domain_deg:
            t = t[t.slope_deg >= spec.domain_deg].copy()           # on GLO-30, whatever the DEM of the layers
        if spec.dem:
            alt_dem(t, spec.dem)
        add_blocks(t, self.nx, self.study)
        return t.assign(event=self.event).reset_index(drop=True)


def alt_dem(t: pd.DataFrame, dem: str) -> pd.DataFrame:
    """The terrain columns replaced, in place, by those computed on another DEM (``<dem>_<column>``)."""
    pre = f"{dem}_"
    alt = [c for c in t.columns if c.startswith(pre)]
    if not alt:
        raise KeyError(f"no {pre}* columns: re-run the L2 layers")
    for c in alt:
        t[c[len(pre):]] = t[c]
    return t


def add_blocks(t: pd.DataFrame, nx: int, study) -> pd.DataFrame:
    """Spatial block id of every row for each block size (from the cell index: the same blocks for every event)."""
    ky, kx = np.divmod(t.cell.to_numpy(), nx)
    for bm in study.models.blocks_m:
        k = max(1, round(bm / study.labels.cell_m))
        t[f"block_{bm:g}"] = (ky // k) * 100_000 + kx // k
    return t


class PooledData:
    """The samples of several events together (L3b.3): each row keeps the forest state before its own event; the
    blocks are the same cells for every event, so a block is never in training for one event and in test for
    another."""

    def __init__(self, events: list[EventData]):
        self.parts = events
        self.study, self.event, self.nx = events[0].study, "pooled", events[0].nx
        self.draws = min(e.draws for e in events)

    def columns(self, spec: Spec, kind: str) -> list[str]:
        sets = [e.columns(spec, kind) for e in self.parts]
        return [c for c in sets[0] if all(c in s for s in sets[1:])]

    def rows(self, spec: Spec, draw: int) -> pd.DataFrame:
        return pd.concat([e.rows(spec, draw) for e in self.parts], ignore_index=True)


def model_set(seed: int, single_thread: bool = False) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier

    from geoeyes.ml.susceptibility import _models
    m = _models(seed)
    m["gradient_boosting_monotonic"] = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=1.0,
        class_weight="balanced", random_state=seed, monotonic_cst=MONOTONIC)
    if single_thread:                                   # many small fits run side by side (``run_jobs``)
        m["random_forest"].set_params(randomforestclassifier__n_jobs=1)
    return m


# ---------------------------------------------------------------- parallel fits
N_JOBS = -1     # every core: the fits are small (thousands of rows), so many single-threaded fits side by side beat
#                 one multi-threaded fit at a time; seeds are fixed, so the results do not depend on it (L9 R1, R2)


def run_jobs(jobs: list) -> list:
    """``joblib`` delayed calls on worker processes, one thread each."""
    from joblib import Parallel, parallel_config
    if not jobs:
        return []
    with parallel_config(backend="loky", inner_max_num_threads=1):
        return Parallel(n_jobs=N_JOBS)(jobs)


def _oof_job(name: str, seed: int, x: pd.DataFrame, y: np.ndarray, groups, folds: int) -> np.ndarray:
    return oof(model_set(seed, True)[name], x, y, groups, folds, seed)


def _fit_predict_job(name: str, seed: int, trains: list[tuple[pd.DataFrame, np.ndarray]],
                     x: pd.DataFrame) -> np.ndarray:
    """Mean probability on ``x`` of the model fitted on each training table."""
    from sklearn.base import clone
    base = model_set(seed, True)[name]
    return np.mean([clone(base).fit(xt, yt).predict_proba(x)[:, 1] for xt, yt in trains], axis=0)


def _xcols(ed: EventData, spec: Spec, name: str) -> list[str]:
    cols = ed.columns(spec, "logistic" if name == "logistic" else "trees")
    if name == "gradient_boosting_monotonic":
        missing = [c for c in MONOTONIC if c not in cols]
        cols = cols + missing
    return cols


def scores(y, p) -> dict:
    from geoeyes.ml.susceptibility import _scores
    return _scores(np.asarray(y), np.asarray(p))


def oof(model, x: pd.DataFrame, y: np.ndarray, groups: np.ndarray | None, folds: int, seed: int) -> np.ndarray:
    """Out-of-fold probabilities: grouped (spatial) folds when ``groups`` is given, else stratified random ones."""
    from sklearn.base import clone
    from sklearn.model_selection import GroupKFold, StratifiedKFold
    p = np.full(len(y), np.nan)
    if groups is not None:
        split = GroupKFold(min(folds, len(np.unique(groups)))).split(x, y, groups)
    else:
        split = StratifiedKFold(folds, shuffle=True, random_state=seed).split(x, y)
    for tr, te in split:
        p[te] = clone(model).fit(x.iloc[tr], y[tr]).predict_proba(x.iloc[te])[:, 1]
    return p


def _agg(rows: list[dict]) -> dict:
    out = {}
    for k in ("auc", "ap", "brier"):
        v = np.array([r[k] for r in rows if r.get(k) is not None], float)
        if len(v):
            out[k] = round(float(v.mean()), 4)
            out[f"{k}_sd"] = round(float(v.std(ddof=1)), 4) if len(v) > 1 else 0.0
    out["draws"] = len(rows)
    return out


# ---------------------------------------------------------------- evaluation
def evaluate(ed: EventData, spec: Spec, draws: int, blocks: tuple[float, ...], random_cv: bool,
             keep_oof: bool = False) -> dict:
    from joblib import delayed
    p = ed.study.models
    tabs = [ed.rows(spec, d) for d in range(min(draws, ed.draws))]
    jobs, keys = [], []
    for name in model_set(p.seed):
        cols = _xcols(ed, spec, name)
        for d, t in enumerate(tabs):
            x, y = t[cols], t.label.to_numpy()
            for bm in blocks:
                jobs.append(delayed(_oof_job)(name, p.seed, x, y, t[f"block_{bm:g}"].to_numpy(), p.folds))
                keys.append((name, f"spatial_{bm:g}", d))
            if random_cv:
                jobs.append(delayed(_oof_job)(name, p.seed, x, y, None, p.folds))
                keys.append((name, "random", d))
    preds = run_jobs(jobs)
    res: dict = {}
    oofs: dict = {}
    by: dict = {}
    for (name, kind, d), pr in zip(keys, preds, strict=True):
        by.setdefault((name, kind), []).append(scores(tabs[d].label.to_numpy(), pr))
        if keep_oof and kind == f"spatial_{blocks[0]:g}":
            oofs.setdefault(name, []).append(tabs[d][["cell", "label", "event"]].assign(p=pr, draw=d))
    for (name, kind), rows in by.items():
        res.setdefault(name, {})[kind] = _agg(rows)
    if keep_oof:
        res["_oof"] = {k: pd.concat(v, ignore_index=True) for k, v in oofs.items()}
    return res


def by_event(oofs: dict[str, pd.DataFrame]) -> dict:
    """Spatial out-of-fold AUC of a pooled model on the rows of each event (mean ± sd over the draws)."""
    out: dict = {}
    for name, o in oofs.items():
        for ev, g in o.groupby("event"):
            out.setdefault(ev, {})[name] = _agg([scores(x.label, x.p) for _, x in g.groupby("draw")])
    return out


def importance(ed: EventData, spec: Spec, draws: int = 3) -> dict:
    """Permutation importance (loss of AUC) on the held-out blocks of the first block size."""
    from joblib import delayed
    p = ed.study.models
    bm = p.blocks_m[0]
    jobs, names = [], []
    for name in model_set(p.seed):
        cols = _xcols(ed, spec, name)
        for d in range(min(draws, ed.draws)):
            t = ed.rows(spec, d)
            jobs.append(delayed(_importance_job)(name, p.seed, t[cols], t.label.to_numpy(),
                                                 t[f"block_{bm:g}"].to_numpy(), p.folds))
            names.append(name)
    out: dict = {}
    tot: dict = {}
    for name, (acc, n) in zip(names, run_jobs(jobs), strict=True):
        a = out.setdefault(name, {})
        for c, v in acc.items():
            a[c] = a.get(c, 0.0) + v
        tot[name] = tot.get(name, 0) + n
    return {name: dict(sorted(((c, round(v / tot[name], 5)) for c, v in a.items()), key=lambda kv: -kv[1]))
            for name, a in out.items()}


def _importance_job(name: str, seed: int, x: pd.DataFrame, y: np.ndarray, g: np.ndarray,
                    folds: int) -> tuple[dict, int]:
    from sklearn.base import clone
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import GroupKFold
    model = model_set(seed, True)[name]
    acc: dict[str, float] = {}
    n = 0
    for tr, te in GroupKFold(min(folds, len(np.unique(g)))).split(x, y, g):
        if len(np.unique(y[te])) < 2:
            continue
        m = clone(model).fit(x.iloc[tr], y[tr])
        r = permutation_importance(m, x.iloc[te], y[te], scoring="roc_auc", n_repeats=5, random_state=seed,
                                   n_jobs=1)
        for c, v in zip(x.columns, r.importances_mean, strict=True):
            acc[c] = acc.get(c, 0.0) + float(v) * len(te)
        n += len(te)
    return acc, n


def odds_ratios(ed: EventData, spec: Spec) -> dict:
    """Logistic odds ratio per standard deviation, mean and sd over the draws."""
    from sklearn.base import clone
    model = model_set(ed.study.models.seed)["logistic"]
    cols = ed.columns(spec, "logistic")
    coefs = []
    for d in range(ed.draws):
        t = ed.rows(spec, d)
        m = clone(model).fit(t[cols], t.label.to_numpy())
        coefs.append(m[-1].coef_[0])
    c = np.array(coefs)
    return {k: {"or": round(float(np.exp(c[:, i].mean())), 3), "log_sd": round(float(c[:, i].std(ddof=1)), 3)}
            for i, k in enumerate(cols)}


def calibration(o: pd.DataFrame, bins: int = 10) -> dict:
    """Reliability of the spatial out-of-fold probabilities (all draws pooled)."""
    o = o.dropna(subset=["p"])
    q = np.clip((o.p * bins).astype(int), 0, bins - 1)
    g = o.groupby(q)
    return {"bin_mean_p": g.p.mean().round(3).tolist(), "observed": g.label.mean().round(3).tolist(),
            "n": g.size().tolist()}


def residual_range(ed: EventData, spec: Spec, max_km: float = 10.0, n: int = 3000) -> dict:
    """Empirical semivariogram of the random-CV residuals of the logistic model (draw 0) and the distance where it
    reaches 95 % of its sill (mean over 6–10 km)."""
    t = ed.rows(spec, 0)
    m = model_set(ed.study.models.seed)["logistic"]
    y = t.label.to_numpy()
    r = y - oof(m, t[ed.columns(spec, "logistic")], y, None, ed.study.models.folds, 0)
    rng = np.random.default_rng(0)
    k = rng.choice(len(t), min(n, len(t)), replace=False)
    kx = 111.32 * math.cos(math.radians(float(t.lat.mean())))
    xy = np.column_stack([t.lon.to_numpy()[k] * kx, t.lat.to_numpy()[k] * 110.54])
    rr = r[k]
    i, j = np.triu_indices(len(k), 1)
    dist = np.hypot(*(xy[i] - xy[j]).T)
    gam = 0.5 * (rr[i] - rr[j]) ** 2
    edges = np.arange(0, max_km + 0.25, 0.25)
    b = np.digitize(dist, edges) - 1
    ok = (b >= 0) & (b < len(edges) - 1)
    sv = np.bincount(b[ok], weights=gam[ok], minlength=len(edges) - 1) / np.maximum(
        np.bincount(b[ok], minlength=len(edges) - 1), 1)
    centres = (edges[:-1] + edges[1:]) / 2
    sill = float(sv[(centres >= 6) & (centres <= max_km)].mean())
    reach = centres[np.flatnonzero(sv >= 0.95 * sill)]
    return {"lag_km": centres.round(3).tolist(), "semivariance": sv.round(4).tolist(), "sill": round(sill, 4),
            "range_km": round(float(reach[0]), 2) if len(reach) else None}


def partial_dependence(ed: EventData, spec: Spec, name: str) -> dict:
    from sklearn.base import clone
    from sklearn.inspection import partial_dependence as pdp
    t = ed.rows(spec, 0)
    cols = _xcols(ed, spec, name)
    m = clone(model_set(ed.study.models.seed)[name]).fit(t[cols], t.label.to_numpy())
    out = {}
    for c in PD_LAYERS:
        if c in cols:
            r = pdp(m, t[cols], [c], grid_resolution=30, kind="average")
            out[c] = {"x": np.round(r["grid_values"][0], 3).tolist(), "p": np.round(r["average"][0], 4).tolist()}
    return out


# ---------------------------------------------------------------- transfer
def transfer(a: EventData, b: EventData, spec: Spec, draws: int, oof_b: dict | None) -> dict:
    """Trained on event ``a`` (whole pilot), tested on ``b`` inside the overlap of their main footprints."""
    from joblib import delayed
    p = a.study.models
    fa, fb = f"in_{a.study.footprint_main}_{a.event}", f"in_{a.study.footprint_main}_{b.event}"
    pairs = []
    for d in range(min(draws, a.draws, b.draws)):
        ta, tb = a.rows(spec, d), b.rows(spec, d)
        tb = tb[tb[fa] & tb[fb]]
        if tb.label.nunique() >= 2:
            pairs.append((d, ta, tb))
    jobs, keys = [], []
    for name in model_set(p.seed):
        cols = [c for c in _xcols(a, spec, name) if c in set(_xcols(b, spec, name))]
        for d, ta, tb in pairs:
            jobs.append(delayed(_fit_predict_job)(name, p.seed, [(ta[cols], ta.label.to_numpy())], tb[cols]))
            keys.append((name, d, tb))
    preds = run_jobs(jobs)
    out = {}
    for name in model_set(p.seed):
        rows, within, npos = [], [], 0
        for (nm, d, tb), pr in zip(keys, preds, strict=True):
            if nm != name:
                continue
            rows.append(scores(tb.label, pr))
            npos = int(tb.label.sum())
            if oof_b is not None and name in oof_b:
                o = oof_b[name]
                o = o[(o.draw == d) & o.cell.isin(tb.cell)]
                within.append(scores(o.label, o.p))
        out[name] = {"transfer": _agg(rows), "within_same_cells": _agg(within) if within else None,
                     "test_positives": npos}
    return out


# ---------------------------------------------------------------- map
def susceptibility_map(ed: EventData, spec: Spec, name: str, grid, out_dir: Path) -> dict:
    """The model fitted on every draw, averaged over the cells of the main footprint; GeoTIFF of the balanced
    probability and of the probability brought back to the real prevalence."""
    import rasterio
    from rasterio.transform import from_origin
    from sklearn.base import clone

    from geoeyes.ml.layers import M_PER_DEG_LAT
    fp = f"in_{ed.study.footprint_main}_{ed.event}"
    cells = ed.pred[ed.pred[fp]]
    cols = _xcols(ed, spec, name)
    p = np.zeros(len(cells))
    for d in range(ed.draws):
        t = ed.rows(spec, d)
        m = clone(model_set(ed.study.models.seed)[name]).fit(t[cols], t.label.to_numpy())
        p += m.predict_proba(cells[cols])[:, 1]
    p /= ed.draws
    if spec.domain_deg:
        p[cells.slope_deg.to_numpy() < spec.domain_deg] = 0.0      # outside the warning domain: very low
    n_pos = int(ed.rows(spec, 0).label.sum())
    prev = n_pos / len(cells)
    with np.errstate(divide="ignore"):
        p_true = 1 / (1 + (1 - p) / np.maximum(p, 1e-9) * (1 - prev) / prev)
    out = {}
    for tag, v in (("balanced", p), ("prevalence", p_true)):
        a = np.full(len(grid), np.nan, np.float32)
        a[cells.cell.to_numpy()] = v
        a = a.reshape(grid.ny, grid.nx)[::-1]                       # rows north first
        tr = from_origin(grid.x0 * grid.cell_m / grid.kx_m, (grid.y0 + grid.ny) * grid.cell_m / M_PER_DEG_LAT,
                         grid.cell_m / grid.kx_m, grid.cell_m / M_PER_DEG_LAT)
        f = out_dir / f"susceptibility_{tag}.tif"
        with rasterio.open(f, "w", driver="GTiff", width=grid.nx, height=grid.ny, count=1, dtype="float32",
                           crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate") as dst:
            dst.write(a, 1)
        out[tag] = f.name
    cls = np.digitize(p, CLASSES)
    share = np.bincount(cls, minlength=len(CLASSES) + 1) / len(cls)
    lab = ed.rows(spec, 0)
    pos_cls = np.digitize(pd.Series(p, index=cells.cell).reindex(lab[lab.label == 1].cell).dropna(), CLASSES)
    hit = np.bincount(pos_cls, minlength=len(CLASSES) + 1) / max(1, len(pos_cls))
    return {"model": name, "cells": int(len(cells)), "prevalence": round(prev, 5), "files": out,
            "class_area_share": np.round(share, 4).tolist(), "class_landslide_share": np.round(hit, 4).tolist(),
            "_p": p, "_cells": cells.cell.to_numpy()}


# ---------------------------------------------------------------- independent test (L3b.5)
FOREST = ("tree_cover_2000", "loss_before", "loss_before_300m", "tree_cover_event")


def test_set(study, grid, static: pd.DataFrame, event: str, year: int, cache_root: Path,
             earlier) -> pd.DataFrame | None:
    """Labels of a Sentinel-2 event (``scars/scars_<event>.gpkg``: polygons, extent) on the study grid, joined with
    the static layers and the forest state before ``year``; positives carry ``in_inventory`` when the file has it."""
    import geopandas as gpd

    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.landslide.labels import grid_slope, make_labels, study_area
    from geoeyes.landslide.predictors import hansen
    f = study.step_dir("scars") / f"scars_{event}.gpkg"
    if not f.exists():
        return None
    polys = gpd.read_file(f, layer="polygons")
    ext = gpd.read_file(f, layer="extent").geometry.iloc[0]
    area = study_area(study)
    w, s, e, n = area.bounds
    dem = load_copernicus30(s - 0.02, n + 0.02, w - 0.02, e + 0.02, cache_root / "dem" / "copernicus-30")
    height = dem.orthometric(grid.lat, grid.lon)
    lab, _ = make_labels(polys, {"extent": ext}, area, grid, height, grid_slope(grid, height), dem, study.labels,
                         event, earlier)
    lab = lab[lab.variant == "scarp"]
    from geoeyes.landslide.reliability import flags
    polys = polys.merge(flags(polys, grid, static, dem, year)[["src_fid", "reliability"]], on="src_fid", how="left")
    dfile = study.step_dir("scars") / f"dating_{event}.parquet"     # L3b.7 step 1: when the vegetation went
    if dfile.exists():
        dd = pd.read_parquet(dfile)
        polys = polys.merge(dd[["src_fid", *[c for c in ("timing", "persistent") if c in dd]]], on="src_fid",
                            how="left")
    extra = [c for c in ("in_inventory", "strict", "reliability", "timing", "persistent") if c in polys]
    lab = lab.merge(polys[["src_fid", *extra]], on="src_fid", how="left")
    forest = hansen(grid, year)
    t = lab[["cell", "label", "draw", "area_m2", "reactivated", *extra]]
    t = t.merge(static, on="cell", how="inner")
    for k, v in forest.items():
        t[k] = v[t.cell.to_numpy()]
    return t.reset_index(drop=True)


def fit_draws(ed, spec: Spec, name: str, draws: int):
    """The model fitted on each of the first ``draws`` draws (a list), with its columns."""
    from sklearn.base import clone
    cols = _xcols(ed, spec, name)
    out = []
    for d in range(min(draws, ed.draws)):
        t = ed.rows(spec, d)
        out.append(clone(model_set(ed.study.models.seed)[name]).fit(t[cols], t.label.to_numpy()))
    return out, cols


def predict_mean(models: list, cols: list[str], x: pd.DataFrame) -> np.ndarray:
    return np.mean([m.predict_proba(x[cols])[:, 1] for m in models], axis=0)


def score_test(test: pd.DataFrame, p: pd.Series, subsets: dict[str, pd.Series]) -> dict:
    """AUC of the probabilities ``p`` (indexed by cell) on each subset of positives against every draw of the
    negatives."""
    out = {}
    neg = test[test.label == 0]
    for k, mask in subsets.items():
        pos = test[(test.label == 1) & mask.reindex(test.index, fill_value=False)]
        if len(pos) < 10:
            out[k] = {"positives": int(len(pos))}
            continue
        rows = []
        for _, g in neg.groupby("draw"):
            g = g.sample(min(len(g), len(pos)), random_state=0)
            y = np.r_[np.ones(len(pos)), np.zeros(len(g))]
            rows.append(scores(y, np.r_[p.reindex(pos.cell).to_numpy(), p.reindex(g.cell).to_numpy()]))
        out[k] = {**_agg(rows), "positives": int(len(pos))}
    return out


def independent_test(sources: dict, specs: dict[str, Spec], test: pd.DataFrame, models=None, say=None) -> dict:
    """Every source (event or pooled) × spec × model, fitted on TEST_DRAWS draws, scored on the test event."""
    from joblib import delayed
    say = say or (lambda m: None)
    cells = test.drop_duplicates("cell").set_index("cell")
    pos = test.label == 1
    strict = test["strict"].fillna(False).astype(bool) if "strict" in test else pd.Series(False, index=test.index)
    reliable = test["reliability"].eq("reliable") if "reliability" in test else pd.Series(False, index=test.index)
    rain = test["timing"].eq("rain_season") if "timing" in test else pd.Series(False, index=test.index)
    lasting = (test["persistent"].astype("boolean").fillna(False).astype(bool) if "persistent" in test
               else pd.Series(False, index=test.index))
    subsets = {"all": pos, "reliable": pos & reliable, "rain_dated": pos & rain, "rain_dated_reliable":
               pos & rain & reliable, "persistent": pos & lasting, "rain_dated_persistent": pos & rain & lasting,
               "strict": pos & strict,
               "area_ge_1000": pos & (test.area_m2 >= 1000),
               "new_sites": pos & ~test.reactivated, "reactivated": pos & test.reactivated}
    seed = next(iter(sources.values())).study.models.seed
    jobs, keys = [], []
    for src, ed in sources.items():
        for sname, spec in specs.items():
            say(f"  test: {src} / {sname}")
            x = alt_dem(cells.copy(), spec.dem) if spec.dem else cells
            tabs = [ed.rows(spec, d) for d in range(min(TEST_DRAWS, ed.draws))]
            for name in models or model_set(0):
                cols = _xcols(ed, spec, name)
                if not all(c in x for c in cols):
                    continue
                jobs.append(delayed(_fit_predict_job)(name, seed, [(t[cols], t.label.to_numpy()) for t in tabs],
                                                      x[cols]))
                keys.append((src, sname, name))
    out: dict = {}
    for (src, sname, name), pr in zip(keys, run_jobs(jobs), strict=True):
        out.setdefault(src, {}).setdefault(sname, {})[name] = score_test(test, pd.Series(pr, index=cells.index),
                                                                         subsets)
    return out


def aspect_check(t: pd.DataFrame) -> dict:
    """Does aspect add to slope? Logistic model of the labels on a slope spline, then with the aspect harmonics
    (``landslide.aspect``): likelihood ratio, p-value, amplitude and azimuth of the highest odds."""
    from scipy.stats import chi2
    from sklearn.preprocessing import SplineTransformer

    from geoeyes.landslide.aspect import first_harmonic, harmonics, logit
    t = t.dropna(subset=["slope_deg", "aspect_sin", "aspect_cos"])
    if t.label.nunique() < 2 or (t.label == 1).sum() < 30:
        return {"positives": int((t.label == 1).sum())}
    y, w = t.label.to_numpy(float), np.ones(len(t))
    base = SplineTransformer(n_knots=5, degree=3, include_bias=False).fit_transform(t[["slope_deg"]].to_numpy())
    theta = np.degrees(np.arctan2(t.aspect_sin.to_numpy(), t.aspect_cos.to_numpy())) % 360
    _, d0 = logit(base, y, w)
    beta, d1 = logit(np.column_stack([base, harmonics(theta)]), y, w)
    amp, az = first_harmonic(beta[-4:])
    return {"positives": int(y.sum()), "negatives": int(len(y) - y.sum()), "lr": round(d0 - d1, 1),
            "p": float(chi2.sf(d0 - d1, 4)), "odds_ratio_amplitude": round(float(np.exp(2 * amp)), 2),
            "azimuth_deg": round(az, 1)}


def inventory_split(ed, spec: Spec, test: pd.DataFrame) -> dict:
    """Sentinel-2 objects of the calibration event that touch an inventory polygon and those that do not, scored by
    a model of another event: if both score alike, the unmatched objects behave as landslides, not as clearing."""
    pos = test.label == 1
    inv = test.get("in_inventory", pd.Series(False, index=test.index)).fillna(False).astype(bool)
    cells = test.drop_duplicates("cell").set_index("cell")
    out = {}
    for name in ("logistic", "random_forest"):
        ms, cols = fit_draws(ed, spec, name, TEST_DRAWS)
        p = pd.Series(predict_mean(ms, cols, cells), index=cells.index)
        out[name] = score_test(test, p, {"in_inventory": pos & inv, "not_in_inventory": pos & ~inv})
    return out


def write_tif(grid, cells: np.ndarray, values: np.ndarray, path: Path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    from geoeyes.ml.layers import M_PER_DEG_LAT
    a = np.full(len(grid), np.nan, np.float32)
    a[cells] = values
    a = a.reshape(grid.ny, grid.nx)[::-1]                       # rows north first
    tr = from_origin(grid.x0 * grid.cell_m / grid.kx_m, (grid.y0 + grid.ny) * grid.cell_m / M_PER_DEG_LAT,
                     grid.cell_m / grid.kx_m, grid.cell_m / M_PER_DEG_LAT)
    with rasterio.open(path, "w", driver="GTiff", width=grid.nx, height=grid.ny, count=1, dtype="float32",
                       crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate") as dst:
        dst.write(a, 1)


def reported_points(study, grid, cells: np.ndarray, p: np.ndarray, since: str = "2015-01-01",
                    max_accuracy_m: float = 3000.0, n_random: int = 1000) -> dict:
    """Reported landslides (``inventories/landslide/vietnam.csv``, located within ``max_accuracy_m``) scored by the
    highest susceptibility within their accuracy radius, as a percentile among random points with the same radius."""
    import shapely

    from geoeyes.landslide.labels import study_area
    f = study.workspace / "inventories" / "landslide" / "vietnam.csv"
    if not f.exists():
        return {}
    d = pd.read_csv(f)
    area = study_area(study)
    d = d[(d.date.astype(str) >= since) & d.lat.notna() & (d.accuracy_m.fillna(1e9) <= max_accuracy_m)]
    d = d[shapely.contains_xy(area, d.lon.to_numpy(), d.lat.to_numpy())]
    full = np.full(len(grid), np.nan)
    full[cells] = p
    img = full.reshape(grid.ny, grid.nx)

    def best(lon, lat, r_m):
        c = int(grid.cell_of(lon, lat))
        if c < 0:
            return np.nan
        ky, kx = divmod(c, grid.nx)
        k = max(1, round(r_m / grid.cell_m))
        win = img[max(ky - k, 0):ky + k + 1, max(kx - k, 0):kx + k + 1]
        return float(np.nanmax(win)) if np.isfinite(win).any() else np.nan

    rng = np.random.default_rng(0)
    pick = rng.choice(cells, min(n_random, len(cells)), replace=False)
    out = []
    for _, r in d.iterrows():
        rad = float(r.accuracy_m) if pd.notna(r.accuracy_m) else max_accuracy_m
        v = best(r.lon, r.lat, rad)
        ref = np.array([best(grid.lon[c], grid.lat[c], rad) for c in pick])
        ref = ref[np.isfinite(ref)]
        out.append({"date": str(r.date), "place": str(r.place), "accuracy_m": rad, "max_p": None if np.isnan(v)
                    else round(v, 3), "percentile": None if np.isnan(v) or not len(ref)
                    else round(float((ref < v).mean() * 100), 1)})
    return {"points": out, "median_percentile": round(float(np.median([o["percentile"] for o in out
                                                                       if o["percentile"] is not None])), 1)
            if any(o["percentile"] is not None for o in out) else None}


# ---------------------------------------------------------------- the study step
def run_fit(study, progress=None, cache_root: Path | None = None) -> dict:
    """L3 of a study: ``models/<event>/`` (metrics.json, maps), ``models/models.json``, ``l3_report.md``, manifest."""
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.landslide.labels import grid_for, study_area
    say = progress or (lambda m: log.info("%s", m))
    p = study.models
    grid = grid_for(study_area(study).bounds, study.labels.cell_m)
    main = Spec(aspect=p.aspect, roads=p.roads, reliable=p.reliable, domain_deg=p.domain_deg)
    data = {name: EventData(study, name, grid.nx) for name, _ in study.events}
    out_dir = study.step_dir("models")
    out_dir.mkdir(parents=True, exist_ok=True)
    res: dict = {"study": study.name, "citation": study.citation, "params": asdict(p), "main": asdict(main),
                 "events": {}}
    oofs, maps = {}, {}
    for ev, ed in data.items():
        say(f"L3 {ev}: main models ({ed.draws} draws, blocks {list(p.blocks_m)} m, random CV)")
        r: dict = {"layers": {"trees": ed.columns(main, "trees"), "logistic": ed.columns(main, "logistic")}}
        m = evaluate(ed, main, ed.draws, p.blocks_m, True, keep_oof=True)
        oofs[ev] = m.pop("_oof")
        r["main"] = m
        b0 = f"spatial_{p.blocks_m[0]:g}"
        best = max(m, key=lambda k: m[k][b0].get("auc", 0))
        r["best_model"] = best
        say(f"L3 {ev}: variants")
        r["variants"] = {k: evaluate(ed, s, VARIANT_DRAWS, (p.blocks_m[0],), False)
                         for k, s in variants(main, p.min_area_m2, study.footprint_sensitivity).items()}
        say(f"L3 {ev}: interpretation")
        r["importance"] = importance(ed, main)
        r["odds_ratio_per_sd"] = odds_ratios(ed, main)
        r["calibration"] = {k: calibration(v) for k, v in oofs[ev].items()}
        r["residual_semivariogram"] = residual_range(ed, main)
        r["partial_dependence"] = partial_dependence(ed, main, best if best != "logistic" else "gradient_boosting")
        say(f"L3 {ev}: map ({best})")
        ev_dir = out_dir / ev
        ev_dir.mkdir(exist_ok=True)
        mp = susceptibility_map(ed, main, best, grid, ev_dir)
        maps[ev] = (mp.pop("_p"), mp.pop("_cells"))
        r["map"] = mp
        atomic_write_json(ev_dir / "metrics.json", r)
        res["events"][ev] = r
    b0 = f"spatial_{p.blocks_m[0]:g}"
    if len(data) >= 2:
        names = list(data)
        res["transfer"] = {}
        for a, b in ((names[0], names[1]), (names[1], names[0])):
            say(f"L3 transfer {a} -> {b}")
            res["transfer"][f"{a}->{b}"] = {
                "all": transfer(data[a], data[b], main, data[a].draws, oofs[b]),
                f"area_ge_{p.min_area_m2:g}": transfer(data[a], data[b], replace(main, min_area_m2=p.min_area_m2),
                                                       data[a].draws, oofs[b])}
        pooled = PooledData(list(data.values()))
        say(f"L3b pooled model ({' + '.join(names)})")
        m = evaluate(pooled, main, pooled.draws, p.blocks_m, True, keep_oof=True)
        po = m.pop("_oof")
        var = variants(main, p.min_area_m2, study.footprint_sensitivity)
        res["pooled"] = {"main": m, "by_event": by_event(po),
                         "best_model": max(m, key=lambda k: m[k][b0].get("auc", 0)),
                         "variants": {k: evaluate(pooled, var[k], VARIANT_DRAWS, (p.blocks_m[0],), False)
                                      for k in TEST_SPECS if k in var},
                         "importance": importance(pooled, main)}
        data_all = {**data, "pooled": pooled}
    else:
        data_all = dict(data)
    if cache_root is not None:
        res["test"] = run_test(study, data_all, main, grid, cache_root, res, out_dir, maps, say)
    files = plot_maps(res, maps, grid, out_dir) + plot_diagnostics(res, out_dir)
    atomic_write_json(out_dir / "models.json", res)
    (out_dir / "l3_report.md").write_text(report_md(res), encoding="utf-8")
    m = Manifest(kind="landslide_models", id=f"{study.name}/models", engine="geoeyes.landslide.model",
                 inputs=[InputRef("labels", str(study.step_dir("labels"))),
                         InputRef("predictors", str(study.step_dir("predictors")))],
                 params={"models": asdict(p), "main": asdict(main), "variant_draws": VARIANT_DRAWS,
                         "monotonic": MONOTONIC},
                 metrics={ev: {"best": r["best_model"],
                               "auc": r["main"][r["best_model"]][f"spatial_{p.blocks_m[0]:g}"].get("auc")}
                          for ev, r in res["events"].items()})
    m.add_outputs(out_dir, files + ["models.json", "l3_report.md"]
                  + [f"{ev}/{f}" for ev, r in res["events"].items() for f in [*r["map"]["files"].values(),
                                                                              "metrics.json"]]
                  + [v["map"]["file"] for v in res.get("test", {}).get("events", {}).values() if "map" in v])
    m.write(out_dir)
    return res


def rerun_test(study, cache_root: Path, progress=None) -> dict:
    """L3b.5 alone, after ``scars/`` changed: the models of the last ``fit`` (models.json) tested again; models.json
    and the report updated."""
    import json

    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide.labels import grid_for, study_area
    say = progress or (lambda m: log.info("%s", m))
    out_dir = study.step_dir("models")
    res = json.loads((out_dir / "models.json").read_text(encoding="utf-8"))
    grid = grid_for(study_area(study).bounds, study.labels.cell_m)
    main = Spec(**{k: tuple(v) if isinstance(v, list) else v for k, v in res["main"].items()})
    data = {name: EventData(study, name, grid.nx) for name, _ in study.events}
    if len(data) >= 2:
        data["pooled"] = PooledData(list(data.values()))
    res["test"] = run_test(study, data, main, grid, cache_root, res, out_dir, {}, say)
    atomic_write_json(out_dir / "models.json", res)
    (out_dir / "l3_report.md").write_text(report_md(res), encoding="utf-8")
    return res


def run_test(study, data: dict, main: Spec, grid, cache_root: Path, res: dict, out_dir: Path, maps: dict,
             say) -> dict:
    """L3b.5: the Sentinel-2 events of ``scars/`` as an independent test; the map of the pooled model with the
    forest of the test year; the reported landslides on it."""
    import geopandas as gpd

    from geoeyes.landslide.scars import CALIBRATION, TEST_EVENTS
    p = study.models
    first = next(iter(data.values()))
    first = first.parts[0] if isinstance(first, PooledData) else first
    static = first.pred.drop(columns=[c for c in FOREST if c in first.pred])
    polys = gpd.read_file(study.inventory, layer="polygons")
    earlier = polys[polys.event.isin([e for e, _ in study.events])].to_crs(4326)
    var = variants(main, p.min_area_m2, study.footprint_sensitivity)
    specs = {k: (main if k == "main" else var[k]) for k in TEST_SPECS if k == "main" or k in var}
    out: dict = {"draws": TEST_DRAWS, "events": {}}
    for ev, date in TEST_EVENTS.items():
        say(f"L3b test on {ev}")
        t = test_set(study, grid, static, ev, int(date[:4]), cache_root, earlier)
        if t is None:
            continue
        shares = t[t.label == 1].reliability.value_counts(normalize=True).round(4).to_dict()
        if main.domain_deg:
            t = t[t.slope_deg >= main.domain_deg].reset_index(drop=True)
        r: dict = {"positives": int((t.label == 1).sum()), "reactivated": int(t[t.label == 1].reactivated.sum()),
                   "reliability_share": shares, "domain_deg": main.domain_deg,
                   "scores": independent_test(data, specs, t, say=say)}
        r["aspect"] = {"S2 " + ev: aspect_check(t[(t.label == 0) | t.reliability.eq("reliable")])}
        for e, ed in data.items():
            if e != "pooled":
                r["aspect"]["Das " + e] = aspect_check(ed.rows(main, 0))
        if "pooled" in data:
            src, _, name = (study.models.champion or "").partition(":")
            # the champion of the gate when it is a pooled model, else the best pooled model by spatial CV
            pm = name if src == "pooled" and name else res["pooled"]["best_model"]
            ms, cols = fit_draws(data["pooled"], main, pm, data["pooled"].draws)
            x = static.copy()
            from geoeyes.landslide.predictors import hansen
            for k, v in hansen(grid, int(date[:4])).items():
                x[k] = v[x.cell.to_numpy()]
            pr = predict_mean(ms, cols, x)
            if main.domain_deg:
                pr[x.slope_deg.to_numpy() < main.domain_deg] = 0.0
            f = f"susceptibility_{ev}_pooled.tif"
            write_tif(grid, x.cell.to_numpy(), pr, out_dir / f)
            maps[f"pooled ({pm}), {ev}"] = (pr, x.cell.to_numpy())
            r["map"] = {"model": pm, "file": f, "reported": reported_points(study, grid, x.cell.to_numpy(), pr)}
        out["events"][ev] = r
    if CALIBRATION in data:
        other = [e for e in data if e not in (CALIBRATION, "pooled")]
        t = test_set(study, grid, static, CALIBRATION, 2020, cache_root, None)
        if t is not None and other:
            say(f"L3b: Sentinel-2 {CALIBRATION} objects in / not in the inventory, scored by {other[0]}")
            out["inventory_split"] = {"model_of": other[0], **inventory_split(data[other[0]], main, t)}
    return out


# ---------------------------------------------------------------- figures and report
def plot_maps(res: dict, maps: dict, grid, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    fig, axs = plt.subplots(len(maps), 1, figsize=(14, 3.6 * len(maps)), squeeze=False)
    cmap = ListedColormap(["#1a9850", "#a6d96a", "#fee08b", "#fc8d59", "#d73027"])
    norm = BoundaryNorm([0, *CLASSES, 1], cmap.N)
    ext = grid.bounds[0], grid.bounds[2], grid.bounds[1], grid.bounds[3]
    for ax, (ev, (p, cells)) in zip(axs[:, 0], maps.items(), strict=True):
        a = np.full(len(grid), np.nan)
        a[cells] = p
        im = ax.imshow(a.reshape(grid.ny, grid.nx), origin="lower", extent=ext, cmap=cmap, norm=norm,
                       interpolation="nearest")
        b0 = res["params"]["blocks_m"][0]
        if ev in res["events"]:
            r = res["events"][ev]
            auc = r["main"][r["best_model"]][f"spatial_{b0:g}"]["auc"]
            title = f"{ev}: susceptibility ({r['best_model']}, spatial AUC {auc}, blocks {b0 / 1000:g} km)"
        else:
            title = f"{ev}: susceptibility, independent test year"
        ax.set_title(title + "; classes 0.2 / 0.4 / 0.6 / 0.8", fontsize=10)
        fig.colorbar(im, ax=ax, fraction=0.02)
    fig.tight_layout()
    fig.savefig(out_dir / "susceptibility_maps.png", dpi=100)
    plt.close(fig)
    return ["susceptibility_maps.png"]


def plot_diagnostics(res: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    evs = list(res["events"])
    fig, axs = plt.subplots(len(evs), 3, figsize=(16, 4.2 * len(evs)), squeeze=False)
    for i, ev in enumerate(evs):
        r = res["events"][ev]
        best = r["best_model"]
        imp = r["importance"][best]
        k = list(imp)[:15][::-1]
        axs[i, 0].barh(k, [imp[c] for c in k], color="#4c72b0")
        axs[i, 0].set_title(f"{ev}: permutation importance ({best}, held-out "
                            f"{res['params']['blocks_m'][0] / 1000:g} km blocks)", fontsize=9)
        for name, c in r["calibration"].items():
            axs[i, 1].plot(c["bin_mean_p"], c["observed"], "o-", ms=3, label=name)
        axs[i, 1].plot([0, 1], [0, 1], "k--", lw=0.6)
        axs[i, 1].set_title(f"{ev}: calibration (spatial out-of-fold)", fontsize=9)
        axs[i, 1].legend(fontsize=7)
        sv = r["residual_semivariogram"]
        axs[i, 2].plot(sv["lag_km"], sv["semivariance"], "o-", ms=3)
        axs[i, 2].axhline(0.95 * sv["sill"], color="grey", ls=":")
        for bm in res["params"]["blocks_m"]:
            axs[i, 2].axvline(bm / 1000, color="r", ls="--", lw=0.7)
        axs[i, 2].set_title(f"{ev}: residual semivariogram (range {sv['range_km']} km; red: blocks)", fontsize=9)
        axs[i, 2].set_xlabel("lag (km)")
    fig.tight_layout()
    fig.savefig(out_dir / "diagnostics.png", dpi=100)
    plt.close(fig)
    return ["diagnostics.png"]


def _fmt(s: dict | None) -> str:
    if not s or "auc" not in s:
        return "—"
    return f"{s['auc']:.3f} ± {s.get('auc_sd', 0):.3f}"


def report_md(res: dict) -> str:
    bk = [f"spatial_{b:g}" for b in res["params"]["blocks_m"]]
    L = [f"# L3 susceptibility models — {res['study']}", "", f"Inventory: {res['citation']}", "",
         f"Main configuration: {res['main']}; excluded layers {res['params']['exclude']}; aspect "
         f"{'in' if res['params']['aspect'] else 'out'}.", ""]
    for ev, r in res["events"].items():
        L += [f"## {ev}", "", f"Layers (trees): {', '.join(r['layers']['trees'])}", "",
              "| Model | " + " | ".join(f"AUC blocks {b.split('_')[1]} m" for b in bk) + " | AUC random | AP "
              f"({bk[0].split('_')[1]} m) | Brier |", "|---|" + "---|" * (len(bk) + 3)]
        for name, m in r["main"].items():
            s0 = m[bk[0]]
            L.append(f"| {name}{' (best)' if name == r['best_model'] else ''} | "
                     + " | ".join(_fmt(m[b]) for b in bk) + f" | {_fmt(m.get('random'))} | "
                     f"{s0.get('ap', '—')} | {s0.get('brier', '—')} |")
        sv = r["residual_semivariogram"]
        L += ["", f"Residual semivariogram range: {sv['range_km']} km (blocks {res['params']['blocks_m']} m).", "",
              f"### Variants (AUC, blocks {bk[0].split('_')[1]} m, {VARIANT_DRAWS} draws)", "",
              "| Variant | " + " | ".join(r["main"]) + " |", "|---|" + "---|" * len(r["main"])]
        L.append("| main | " + " | ".join(_fmt(m[bk[0]]) for m in r["main"].values()) + " |")
        for k, v in r["variants"].items():
            L.append(f"| {k} | " + " | ".join(_fmt(v[n][bk[0]]) for n in r["main"]) + " |")
        imp = r["importance"][r["best_model"]]
        L += ["", f"### Permutation importance ({r['best_model']})", "",
              ", ".join(f"{k} {v:.4f}" for k, v in list(imp.items())[:12]), "", "### Logistic odds ratio per SD", "",
              ", ".join(f"{k} {v['or']}" for k, v in sorted(r["odds_ratio_per_sd"].items(),
                                                             key=lambda kv: -abs(math.log(kv[1]["or"]))))]
        mp = r["map"]
        L += ["", f"### Map ({mp['model']})", "",
              f"- cells {mp['cells']}, prevalence {mp['prevalence']:.3%}",
              f"- area share by class (very low → very high): {mp['class_area_share']}",
              f"- landslide (scarp) share by class: {mp['class_landslide_share']}", ""]
    if "transfer" in res:
        L += ["## Transfer between events (overlap of the main footprints)", "",
              "| Direction | Positives | Model | Transfer AUC | Within-event spatial AUC, same cells |",
              "|---|---|---|---|---|"]
        for k, v in res["transfer"].items():
            for sub, t in v.items():
                for name, x in t.items():
                    L.append(f"| {k} ({sub}) | {x['test_positives']} | {name} | {_fmt(x['transfer'])} | "
                             f"{_fmt(x['within_same_cells'])} |")
    if "pooled" in res:
        po = res["pooled"]
        L += ["", "## Pooled model (L3b.3)", "",
              "| Model | " + " | ".join(f"AUC blocks {b.split('_')[1]} m" for b in bk) + " | AUC random | "
              + " | ".join(f"{ev} rows ({bk[0].split('_')[1]} m)" for ev in po["by_event"]) + " |",
              "|---|" + "---|" * (len(bk) + 1 + len(po["by_event"]))]
        for name, m in po["main"].items():
            L.append(f"| {name}{' (best)' if name == po['best_model'] else ''} | "
                     + " | ".join(_fmt(m[b]) for b in bk) + f" | {_fmt(m.get('random'))} | "
                     + " | ".join(_fmt(po["by_event"][ev].get(name)) for ev in po["by_event"]) + " |")
        L += ["", f"Variants (blocks {bk[0].split('_')[1]} m):", "", "| Variant | " + " | ".join(po["main"]) + " |",
              "|---|" + "---|" * len(po["main"])]
        for k, v in po["variants"].items():
            L.append(f"| {k} | " + " | ".join(_fmt(v[n][bk[0]]) for n in po["main"]) + " |")
        imp = po["importance"][po["best_model"]]
        L += ["", f"Permutation importance ({po['best_model']}): "
              + ", ".join(f"{k} {v:.4f}" for k, v in list(imp.items())[:12])]
    if res.get("test", {}).get("events"):
        L += ["", "## Independent test: Sentinel-2 scars of a later rain event (L3b.5)", "",
              f"Each model fitted on {res['test']['draws']} draws of its training data; AUC of the scarp cells of "
              "the Sentinel-2 objects against negatives in the mapped extent (every draw), mean ± sd.", ""]
        for ev, r in res["test"]["events"].items():
            L += [f"### {ev}: {r['positives']} positives ({r['reactivated']} on a mapped polygon of the inventory)",
                  "", f"Domain: slope ≥ {r.get('domain_deg', 0)}°; reliability of the objects (before the domain): "
                  f"{r.get('reliability_share')}", "",
                  "| Trained on | Layers | Model | all | reliable | rain-dated | rain-dated reliable | persistent | "
                  "rain-dated persistent | strict | ≥ 1000 m² | new sites | reactivated |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            keys = ("all", "reliable", "rain_dated", "rain_dated_reliable", "persistent", "rain_dated_persistent",
                    "strict", "area_ge_1000", "new_sites", "reactivated")
            for src, by_spec in r["scores"].items():
                for sname, by_model in by_spec.items():
                    for name, s in by_model.items():
                        L.append(f"| {src} | {sname} | {name} | " + " | ".join(_fmt(s.get(k)) for k in keys) + " |")
            if r.get("aspect"):
                L += ["", "Aspect beyond slope (reliable positives in the domain; LR test of the harmonics, 4 df):",
                      "", "| Inventory | positives | LR | p | max / min odds | towards |", "|---|---|---|---|---|---|"]
                for k, a in r["aspect"].items():
                    L.append(f"| {k} | {a.get('positives')} | {a.get('lr', '—')} | "
                             f"{a['p']:.2g} | {a.get('odds_ratio_amplitude', '—')} | {a.get('azimuth_deg', '—')}° |"
                             if "p" in a else f"| {k} | {a.get('positives')} | — | — | — | — |")
            if "map" in r:
                rp = r["map"]["reported"]
                L += ["", f"Map: `{r['map']['file']}` (pooled {r['map']['model']}, the layers of {ev}).",
                      f"Reported landslides located within 3 km: {len(rp.get('points', []))}, median percentile of "
                      f"the highest susceptibility in their radius among random points: {rp.get('median_percentile')}"]
                for o in rp.get("points", []):
                    L.append(f"- {o['date']} {o['place']} (±{o['accuracy_m']:g} m): max p {o['max_p']}, percentile "
                             f"{o['percentile']}")
            L.append("")
        if "inventory_split" in res["test"]:
            s = res["test"]["inventory_split"]
            L += ["### Sentinel-2 objects of the calibration event, in / not in the inventory", "",
                  f"Scored by the model of {s['model_of']}.", "", "| Model | in inventory | not in inventory |",
                  "|---|---|---|"]
            for name in ("logistic", "random_forest"):
                L.append(f"| {name} | {_fmt(s[name]['in_inventory'])} ({s[name]['in_inventory'].get('positives')}) "
                         f"| {_fmt(s[name]['not_in_inventory'])} "
                         f"({s[name]['not_in_inventory'].get('positives')}) |")
    return "\n".join(L) + "\n"
