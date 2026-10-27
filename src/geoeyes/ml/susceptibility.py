"""Ground-motion susceptibility from thematic layers (docs/en/research/ai-susceptibility.md).

Which combination of terrain, land cover, buildings, soil and climate explains where InSAR sees the ground move,
and where else could it move (cells without InSAR points, e.g. vegetation)?

* labels: the cells of the hazard analysis (InSAR), ``moving`` = sinking or downslope at ``label_rate`` or faster
  (their rates are negative: GeoEyes sign; only one mode, ``subsidence`` by default);
* predictors: the thematic layers (``geoeyes.ml.layers``), columns with values;
* models: logistic regression (standardised predictors: odds ratio per standard deviation), random forest,
  gradient boosting (scikit-learn), class weights balanced;
* evaluation: **spatial** block cross-validation (blocks of ``block_m``, grouped folds) — ROC AUC, average
  precision, Brier score; random cross-validation is reported beside it to show how much spatial autocorrelation
  inflates a naive score;
* interpretation: permutation importance on the held-out blocks (loss of AUC), logistic odds ratios;
* prediction: every cell of the grid, with an ``outside`` flag where a predictor lies outside the range seen in
  training (the model extrapolates there).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.hazard.assess import SIGN, read_cells
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.ml.layers import LAYERS, Grid, build_layers

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.susceptibility/1"
MODELS = ("logistic", "random_forest", "gradient_boosting")
CLASSES = (0.2, 0.4, 0.6, 0.8)          # probability limits of very low / low / moderate / high / very high


@dataclass(frozen=True)
class SusceptibilityParams:
    """``[postprocess.susceptibility]`` of project.toml (every key optional)."""

    label_rate: float = 5.0                  # mm/yr of sinking / downslope motion: at or above = moving
    mode: str = "subsidence"                 # subsidence | landslide | all
    block_m: float = 1000.0                  # spatial cross-validation blocks
    folds: int = 5
    min_points: int = 3                      # InSAR points in a labelled cell (as the hazard analysis)
    # layers left out of the predictors: the rainfall climatology is a 5–25 km grid, so within one city it only
    # encodes the position of a cell (a spatial proxy), not a process
    exclude: tuple[str, ...] = ("rain_annual_mm",)
    seed: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> SusceptibilityParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.susceptibility]: unknown key(s) {unknown}; known: {sorted(names)}")
        p = cls(**{f.name: tuple(d[f.name]) if isinstance(getattr(cls, f.name), tuple) else
                   type(getattr(cls, f.name))(d[f.name]) for f in fields(cls) if f.name in d})
        if p.mode not in ("subsidence", "landslide", "all"):
            raise ConfigError("[postprocess.susceptibility] mode: subsidence | landslide | all")
        return p


def _models(seed: int) -> dict[str, Any]:
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {
        "logistic": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                  LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0)),
        "random_forest": make_pipeline(SimpleImputer(strategy="median"),
                                       RandomForestClassifier(n_estimators=300, min_samples_leaf=5, max_features="sqrt",
                                                              class_weight="balanced_subsample", n_jobs=-1,
                                                              random_state=seed)),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                                            min_samples_leaf=30, l2_regularization=1.0,
                                                            class_weight="balanced", random_state=seed),
    }


def _scores(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    if len(np.unique(y)) < 2:
        return {"auc": None, "ap": None, "brier": None}
    return {"auc": round(float(roc_auc_score(y, p)), 4), "ap": round(float(average_precision_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4)}


def evaluate(x: pd.DataFrame, y: np.ndarray, blocks: np.ndarray, params: SusceptibilityParams) -> dict:
    """Spatial and random cross-validation of every model, permutation importance on the spatial folds."""
    from sklearn.base import clone
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import GroupKFold, StratifiedKFold
    folds = min(params.folds, len(np.unique(blocks)))
    if folds < 2:
        raise DataError("too few spatial blocks for cross-validation (make block_m smaller)")
    out: dict[str, dict] = {}
    for name, model in _models(params.seed).items():
        p_sp = np.full(len(y), np.nan)
        imp = np.zeros(x.shape[1])
        for tr, te in GroupKFold(folds).split(x, y, blocks):
            m = clone(model).fit(x.iloc[tr], y[tr])
            p_sp[te] = m.predict_proba(x.iloc[te])[:, 1]
            if len(np.unique(y[te])) == 2:
                r = permutation_importance(m, x.iloc[te], y[te], scoring="roc_auc", n_repeats=5,
                                           random_state=params.seed, n_jobs=1)
                imp += r.importances_mean * len(te)
        p_rd = np.full(len(y), np.nan)
        for tr, te in StratifiedKFold(folds, shuffle=True, random_state=params.seed).split(x, y):
            p_rd[te] = clone(model).fit(x.iloc[tr], y[tr]).predict_proba(x.iloc[te])[:, 1]
        out[name] = {"spatial_cv": _scores(y, p_sp), "random_cv": _scores(y, p_rd),
                     "importance": {c: round(float(v / len(y)), 5) for c, v in zip(x.columns, imp, strict=True)}}
    return out


def run(product: Path, out: Path, params: SusceptibilityParams, *, hazard_dir: Path, dem_source: str,
        dem_cache: Path, overture_cache: Path, geology: dict | None = None, progress=None) -> dict:
    """Layers, labels, models and the susceptibility map of a product into ``out``."""
    say = progress or (lambda m: log.info("%s", m))
    hz_file = hazard_dir / "hazard.json"
    if not hz_file.exists():
        raise DataError("susceptibility needs the hazard analysis of the product first (geoeyes hazard)")
    hz = json.loads(hz_file.read_text(encoding="utf-8"))
    cells = read_cells(hazard_dir, hz)
    grid = Grid(hz["bounds"], float(hz["params"]["cell_m"]), float(hz["lat0"]))
    say(f"grid of {len(grid)} cells ({grid.cell_m:g} m) over the product extent")

    layers_file = out / "layers.parquet"
    stamp = {"bounds": [round(v, 6) for v in grid.bounds], "cell_m": grid.cell_m, "lat0": round(grid.lat0, 8),
             # a new soft-soil source rebuilds the layers
             "geology": [geology["params"].raster, geology["params"].boreholes, geology["params"].open_fallback]
             if geology else None}
    if layers_file.exists() and (out / "layers.json").exists() and \
            json.loads((out / "layers.json").read_text(encoding="utf-8")).get("grid") == stamp:
        table = pd.read_parquet(layers_file)
        warnings = json.loads((out / "layers.json").read_text(encoding="utf-8")).get("warnings", [])
        say("layers: reused")
    else:
        table, warnings = build_layers(grid, dem_source=dem_source, dem_cache=dem_cache,
                                       overture_cache=overture_cache, hazard_dir=hazard_dir, geology=geology,
                                       progress=say)
        out.mkdir(parents=True, exist_ok=True)
        table.to_parquet(layers_file, index=False)
        atomic_write_json(out / "layers.json", {"grid": stamp, "warnings": warnings})

    # labels from the InSAR cells of the hazard analysis
    idx = grid.cell_of(cells["lon"].to_numpy(), cells["lat"].to_numpy())
    rate = np.full(len(grid), np.nan)
    mode = np.array([""] * len(grid), dtype=object)
    n_pts = cells["n_points"].to_numpy()
    good = (idx >= 0) & np.isfinite(cells["rate_mm_yr"].to_numpy()) & (n_pts >= params.min_points)
    rate[idx[good]] = cells["rate_mm_yr"].to_numpy()[good]
    mode[idx[good]] = cells["mode"].to_numpy()[good]
    keep_mode = np.ones(len(grid), bool) if params.mode == "all" else (mode == params.mode)
    labelled = np.isfinite(rate) & keep_mode
    # moving: sinking or downslope at label_rate or faster (negative rates with the GeoEyes sign)
    y_all = np.where(-rate >= params.label_rate, 1.0, 0.0)
    table["rate_mm_yr"] = rate.astype(np.float32)
    table["label"] = np.where(labelled, y_all, np.nan).astype(np.float32)

    cols = [c for c in LAYERS if c not in params.exclude and table[c].notna().any()
            and table[c].nunique(dropna=True) > 1]
    dropped = [c for c in LAYERS if c not in cols and c not in params.exclude]
    if dropped:
        warnings.append(f"layers without information here (empty or constant): {', '.join(dropped)}")
    x = table.loc[labelled, cols].reset_index(drop=True)
    y = y_all[labelled].astype(int)
    n_pos = int(y.sum())
    say(f"{len(y)} labelled cells, {n_pos} moving (≥ {params.label_rate:g} mm/yr), {len(cols)} predictors")
    if n_pos < 20 or len(y) - n_pos < 20:
        r = rate[labelled]
        se = cells["rate_se_mm_yr"].to_numpy()[good] if "rate_se_mm_yr" in cells else np.array([np.nan])
        noise = 2 * float(np.nanmedian(se))
        p5, p95 = (float(np.nanpercentile(r, q)) for q in (5, 95))
        p90 = float(np.nanpercentile(-r, 90))                      # sinking / downslope rate of the fastest 10 %
        hint = f"label_rate = {p90:.1f} labels 10 % of the cells as moving"
        if p90 < noise:
            hint += (f", but that is below the measurement noise (2σ ≈ {noise:.1f} mm/yr): the labels would be "
                     "mostly noise, and this area may simply be too stable for a susceptibility model")
        raise DataError(f"too few moving ({n_pos}) or stable ({len(y) - n_pos}) cells at {params.label_rate:g} mm/yr "
                        f"to train a model: the rates here span {p5:.1f} … {p95:.1f} mm/yr (P5–P95, "
                        f"reference: {hz.get('reference', {}).get('kind', '?')}); {hint}")
    bx = np.floor(table.loc[labelled, "kx"].to_numpy() * grid.cell_m / params.block_m).astype(np.int64)
    by = np.floor(table.loc[labelled, "ky"].to_numpy() * grid.cell_m / params.block_m).astype(np.int64)
    blocks = bx * 1_000_003 + by

    say("spatial cross-validation of logistic regression, random forest and gradient boosting")
    ev = evaluate(x, y, blocks, params)
    best = max(MODELS, key=lambda m: ev[m]["spatial_cv"]["auc"] or 0)

    # final models on every labelled cell, prediction on the whole grid
    models = _models(params.seed)
    for name in MODELS:
        models[name].fit(x, y)
        table[f"p_{name}"] = models[name].predict_proba(table[cols])[:, 1].astype(np.float32)
    table["probability"] = table[f"p_{best}"]
    table["class"] = np.searchsorted(np.asarray(CLASSES), table["probability"].to_numpy(), side="right").astype(np.int8)
    lo, hi = x.quantile(0.01), x.quantile(0.99)
    outside = np.zeros(len(table), bool)
    for c in cols:
        v = table[c].to_numpy()
        outside |= np.isfinite(v) & ((v < lo[c]) | (v > hi[c]))
    table["outside"] = outside
    coef = models["logistic"][-1].coef_[0]
    odds = {c: round(float(np.exp(b)), 3) for c, b in zip(cols, coef, strict=True)}

    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "grid.parquet", index=False)
    import joblib
    joblib.dump({"models": models, "columns": cols}, out / "models.joblib")
    summary = {
        "schema": SCHEMA, "sign": SIGN, "product_id": product.name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": asdict(params), "grid": {"cells": len(grid), "cell_m": grid.cell_m, "lat0": grid.lat0,
                                           "bounds": grid.bounds},
        "labels": {"cells": int(len(y)), "moving": n_pos, "share": round(n_pos / len(y), 4),
                   "reference": hz.get("reference")},
        "predictors": cols, "layers": {c: {"group": LAYERS[c][0], "label": LAYERS[c][1], "unit": LAYERS[c][2]}
                                       for c in LAYERS},
        "models": ev, "chosen": best, "odds_ratio_per_sd": odds, "classes": list(CLASSES),
        "outside_share": round(float(outside.mean()), 4), "warnings": warnings,
        "sources": ["Copernicus GLO-30 / SRTM (DEM)", "ESA WorldCover 10 m 2021 v200 (Zanaga et al. 2022)",
                    "Overture Maps buildings (ODbL; Google Open Buildings, Microsoft: CC BY 4.0)",
                    "SoilGrids 2.0 (Poggio et al. 2021)", "rainfall: the hazard analysis"],
        "method": "docs/en/research/ai-susceptibility.md",
    }
    atomic_write_json(out / "susceptibility.json", summary)
    m = Manifest(kind="susceptibility", id=product.name, engine=SCHEMA,
                 inputs=[InputRef("product", str(product)), InputRef("hazard", str(hazard_dir))],
                 params=summary["params"], metrics={"chosen": best, "auc": ev[best]["spatial_cv"]["auc"]})
    m.add_outputs(out, ["layers.parquet", "grid.parquet", "models.joblib", "susceptibility.json"])
    m.write(out)
    say(f"done: {best}, spatial AUC {ev[best]['spatial_cv']['auc']}")
    return summary


def read_summary(folder: Path) -> dict | None:
    f = folder / "susceptibility.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
