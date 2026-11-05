"""L3c of the landslide study: improving the random forest of the susceptibility layer.

One protocol for every step (docs/en/research/landslide-susceptibility.md, L3c): the champion's data (pooled,
reliable polygons, slope domain, terrain layers), all draws of negatives; out-of-fold AUC on 5 km blocks (pooled
and per event), transfer between the two events, and a paired block bootstrap of the pooled AUC difference
against the baseline. A change is kept when the gain is ≥ ``KEEP_GAIN`` with a 95 % interval above 0 and neither
transfer falls by more than ``KEEP_TRANSFER_LOSS``.

C1 (this module's ``run_c1``): RF settings by nested spatial CV, and the table of every setting.
"""
from __future__ import annotations

import itertools
import json
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

BLOCK_M = 5000.0
N_BOOT = 1000
KEEP_GAIN = 0.01
KEEP_TRANSFER_LOSS = 0.01
BASE_RF = {"n_estimators": 300, "min_samples_leaf": 5, "max_features": "sqrt", "max_samples": None, "max_depth": None}
GRID = {"max_features": ["sqrt", 0.33, 0.5], "min_samples_leaf": [1, 5, 10, 20, 40], "max_samples": [None, 0.5],
        "n_estimators": [500]}
INNER_FOLDS = 4


def rf(params: dict, seed: int):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    return make_pipeline(SimpleImputer(strategy="median"),
                         RandomForestClassifier(class_weight="balanced_subsample", n_jobs=1, random_state=seed,
                                                **params))


def configs(grid: dict = GRID) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, v, strict=True)) for v in itertools.product(*(grid[k] for k in keys))]


def key(params: dict) -> str:
    return ",".join(f"{k}={params[k]}" for k in sorted(params))


# ---------------------------------------------------------------- data
@dataclass
class Tables:
    """The champion rows of every draw, pooled (``event`` column), with the 5 km block of each row."""

    draws: list[pd.DataFrame]
    cols: list[str]
    footprints: dict = field(default_factory=dict)   # event -> name of its main-footprint column


def load_tables(study, extra: dict[str, pd.DataFrame] | None = None, cols: list[str] | None = None) -> Tables:
    """``extra``: per event a table (``cell`` + new layers) merged into the rows; ``cols``: the layer set
    (default: the champion's)."""
    from geoeyes.landslide.labels import grid_for, study_area
    from geoeyes.landslide.model import EventData, PooledData, Spec
    p = study.models
    grid = grid_for(study_area(study).bounds, study.labels.cell_m)
    main = Spec(aspect=p.aspect, roads=p.roads, reliable=p.reliable, domain_deg=p.domain_deg)
    data = [EventData(study, ev, grid.nx) for ev, _ in study.events]
    pooled = PooledData(data)
    base = pooled.columns(main, "trees")
    tabs = []
    for d in range(pooled.draws):
        t = pooled.rows(main, d)
        if extra:
            t = pd.concat([g.merge(extra[ev], on="cell", how="left") if ev in extra else g
                           for ev, g in t.groupby("event")], ignore_index=True)
        tabs.append(t)
    fp = {ev: f"in_{study.footprint_main}_{ev}" for ev, _ in study.events}
    return Tables(tabs, cols or base, fp)


# ---------------------------------------------------------------- scoring
def _oof(params: dict, seed: int, x: pd.DataFrame, y: np.ndarray, groups: np.ndarray, folds: int) -> np.ndarray:
    from sklearn.model_selection import GroupKFold
    p = np.full(len(y), np.nan)
    for tr, te in GroupKFold(min(folds, len(np.unique(groups)))).split(x, y, groups):
        p[te] = rf(params, seed).fit(x.iloc[tr], y[tr]).predict_proba(x.iloc[te])[:, 1]
    return p


def _fit_predict(params: dict, seed: int, xa, ya, xb) -> np.ndarray:
    return rf(params, seed).fit(xa, ya).predict_proba(xb)[:, 1]


def _nested(grid: list[dict], seed: int, x: pd.DataFrame, y: np.ndarray, groups: np.ndarray,
            folds: int) -> tuple[np.ndarray, list[str]]:
    """Out-of-fold probabilities of the tuned procedure: in each outer fold, the setting of best inner spatial-CV
    AUC is chosen on the training blocks only."""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    p = np.full(len(y), np.nan)
    chosen = []
    for tr, te in GroupKFold(min(folds, len(np.unique(groups)))).split(x, y, groups):
        xt, yt, gt = x.iloc[tr], y[tr], groups[tr]
        best, best_auc = grid[0], -1.0
        for prm in grid:
            o = _oof(prm, seed, xt, yt, gt, INNER_FOLDS)
            a = roc_auc_score(yt, o)
            if a > best_auc:
                best, best_auc = prm, a
        chosen.append(key(best))
        p[te] = rf(best, seed).fit(xt, yt).predict_proba(x.iloc[te])[:, 1]
    return p, chosen


def auc(y, p) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p))


def paired_bootstrap(tabs: list[pd.DataFrame], base: list[np.ndarray], new: list[np.ndarray], n: int = N_BOOT,
                     seed: int = 0) -> dict:
    """Δ AUC (new − base), mean over the draws, with a 95 % interval from resampling the 5 km blocks (the same
    blocks for both, so the comparison is paired)."""
    rng = np.random.default_rng(seed)
    col = f"block_{BLOCK_M:g}"
    delta = float(np.mean([auc(t.label, b2) - auc(t.label, b1) for t, b1, b2 in zip(tabs, base, new, strict=True)]))
    boots = []
    prepared = []
    for t, b1, b2 in zip(tabs, base, new, strict=True):
        blocks = t[col].to_numpy()
        ub, inv = np.unique(blocks, return_inverse=True)
        idx = [np.flatnonzero(inv == k) for k in range(len(ub))]
        prepared.append((t.label.to_numpy(), b1, b2, idx))
    for _ in range(n):
        ds = []
        for y, b1, b2, idx in prepared:
            pick = np.concatenate([idx[k] for k in rng.integers(0, len(idx), len(idx))])
            if y[pick].min() == y[pick].max():
                continue
            ds.append(auc(y[pick], b2[pick]) - auc(y[pick], b1[pick]))
        if ds:
            boots.append(np.mean(ds))
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"delta": round(delta, 4), "ci95": [round(float(lo), 4), round(float(hi), 4)]}


def evaluate(tb: Tables, params: dict, seed: int, folds: int, cols: list[str] | None = None,
             transfer: bool = True) -> dict:
    """Pooled / per-event spatial OOF AUC and the two transfers of one RF setting; keeps the OOF predictions."""
    from joblib import delayed

    from geoeyes.landslide.model import run_jobs
    cols = cols or tb.cols
    col = f"block_{BLOCK_M:g}"
    jobs = [delayed(_oof)(params, seed, t[cols], t.label.to_numpy(), t[col].to_numpy(), folds) for t in tb.draws]
    evs = sorted(tb.draws[0].event.unique())
    pairs = []
    if transfer and len(evs) == 2:
        for a, b in ((evs[0], evs[1]), (evs[1], evs[0])):
            for t in tb.draws:
                ta, tt = t[t.event == a], t[t.event == b]
                tt = tt[tt[tb.footprints[a]] & tt[tb.footprints[b]]]
                if tt.label.nunique() == 2:
                    pairs.append((f"{a}->{b}", tt.label.to_numpy()))
                    jobs.append(delayed(_fit_predict)(params, seed, ta[cols], ta.label.to_numpy(), tt[cols]))
    preds = run_jobs(jobs)
    oof, rest = preds[:len(tb.draws)], preds[len(tb.draws):]
    res = {"pooled": float(np.mean([auc(t.label, p) for t, p in zip(tb.draws, oof, strict=True)])),
           "by_event": {ev: float(np.mean([auc(t.label[t.event == ev], p[(t.event == ev).to_numpy()])
                                           for t, p in zip(tb.draws, oof, strict=True)])) for ev in evs},
           "transfer": {}}
    for (k, y), p in zip(pairs, rest, strict=True):
        res["transfer"].setdefault(k, []).append(auc(y, p))
    res["transfer"] = {k: float(np.mean(v)) for k, v in res["transfer"].items()}
    res = {k: (round(v, 4) if isinstance(v, float) else {a: round(b, 4) for a, b in v.items()})
           for k, v in res.items()}
    res["_oof"] = oof
    return res


def verdict(base: dict, new: dict, boot: dict) -> dict:
    loss = {k: round(base["transfer"][k] - new["transfer"].get(k, np.nan), 4) for k in base["transfer"]}
    keep = (boot["delta"] >= KEEP_GAIN and boot["ci95"][0] > 0
            and all(v <= KEEP_TRANSFER_LOSS for v in loss.values()))
    return {"keep": bool(keep), "transfer_loss": loss}


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


# ---------------------------------------------------------------- C1
def run_c1(study, progress=None) -> dict:
    """Grid of RF settings (spatial CV of each), the nested estimate of the tuned procedure, the chosen setting
    against the baseline (paired bootstrap, transfers). Writes ``models/improve/c1.json`` and ``c1.md``."""
    from joblib import delayed

    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide.model import run_jobs
    say = progress or (lambda m: log.info("%s", m))
    p = study.models
    out_dir = study.step_dir("models") / "improve"
    out_dir.mkdir(parents=True, exist_ok=True)
    tb = load_tables(study)
    say(f"L3c C1: {len(tb.draws)} draws, {len(tb.draws[0])} rows per draw, {len(tb.cols)} layers")
    base = evaluate(tb, BASE_RF, p.seed, p.folds)
    say(f"L3c C1: baseline pooled {base['pooled']}, by event {base['by_event']}, transfer {base['transfer']}")
    grid = configs()
    col = f"block_{BLOCK_M:g}"
    jobs, keys = [], []
    for prm in grid:
        for d, t in enumerate(tb.draws):
            jobs.append(delayed(_oof)(prm, p.seed, t[tb.cols], t.label.to_numpy(), t[col].to_numpy(), p.folds))
            keys.append((key(prm), d))
    say(f"L3c C1: grid of {len(grid)} settings x {len(tb.draws)} draws")
    preds = run_jobs(jobs)
    table: dict = {}
    for (k, d), pr in zip(keys, preds, strict=True):
        table.setdefault(k, []).append(auc(tb.draws[d].label, pr))
    table = {k: round(float(np.mean(v)), 4) for k, v in sorted(table.items(), key=lambda kv: -np.mean(kv[1]))}
    best_key = next(iter(table))
    best = next(prm for prm in grid if key(prm) == best_key)
    say(f"L3c C1: best of the grid {best_key}: {table[best_key]} (optimistic: chosen on the same folds)")
    say("L3c C1: nested spatial CV of the tuned procedure (honest estimate)")
    nested = run_jobs([delayed(_nested)(grid, p.seed, t[tb.cols], t.label.to_numpy(), t[col].to_numpy(), p.folds)
                       for t in tb.draws])
    nested_auc = float(np.mean([auc(t.label, pr) for t, (pr, _) in zip(tb.draws, nested, strict=True)]))
    chosen = pd.Series([c for _, ch in nested for c in ch]).value_counts().to_dict()
    say(f"L3c C1: nested AUC {nested_auc:.4f}; settings chosen in the outer folds {chosen}")
    new = evaluate(tb, best, p.seed, p.folds)
    boot = paired_bootstrap(tb.draws, base["_oof"], new["_oof"])
    nested_boot = paired_bootstrap(tb.draws, base["_oof"], [pr for pr, _ in nested])
    res = {"step": "C1", "rows_per_draw": len(tb.draws[0]), "draws": len(tb.draws), "layers": tb.cols,
           "baseline": {"params": BASE_RF, **strip(base)}, "grid": table,
           "best": {"params": best, **strip(new), "paired": boot, **verdict(base, new, boot)},
           "nested": {"auc": round(nested_auc, 4), "chosen": chosen, "paired": nested_boot}}
    atomic_write_json(out_dir / "c1.json", res)
    (out_dir / "c1.md").write_text(c1_md(res), encoding="utf-8")
    return res


def c1_md(r: dict) -> str:
    b, n = r["baseline"], r["best"]
    lines = ["# L3c C1 — random forest settings", "",
             f"{r['draws']} draws, {r['rows_per_draw']} rows per draw, {len(r['layers'])} layers; spatial CV on "
             f"{BLOCK_M / 1000:g} km blocks.", "",
             "| setting | pooled | " + " | ".join(b["by_event"]) + " | " + " | ".join(b["transfer"]) + " |",
             "|---|---|" + "---|" * (len(b["by_event"]) + len(b["transfer"]))]
    for name, x in (("baseline " + key(b["params"]), b), ("best " + key(n["params"]), n)):
        lines.append(f"| {name} | {x['pooled']} | " + " | ".join(str(v) for v in x["by_event"].values()) + " | "
                     + " | ".join(str(v) for v in x["transfer"].values()) + " |")
    lines += ["", f"- best vs baseline: Δ {n['paired']['delta']:+.4f}, 95 % {n['paired']['ci95']}; transfer loss "
              f"{n['transfer_loss']}; **{'keep' if n['keep'] else 'not kept'}**",
              f"- nested spatial CV of the tuned procedure (honest): {r['nested']['auc']} "
              f"(Δ {r['nested']['paired']['delta']:+.4f}, 95 % {r['nested']['paired']['ci95']}); chosen "
              f"{r['nested']['chosen']}", "", "## Grid (pooled spatial AUC, mean over draws)", "", "| setting | AUC |",
              "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in r["grid"].items()]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- C3
FAMILIES = {
    "roughness": ["tri_m", "vrm_150", "vrm_450"],
    "landform": ["geom_plus_150", "geom_minus_150", "geomorphon_150", "geom_plus_500", "geom_minus_500",
                 "geomorphon_500", "convergence"],
    "position": ["rsp_500", "rsp_1000", "flow_length_up_m"],
    "erosion": ["ls_factor"],
    "scale": ["slope_s150", "slope_s300", "profile_curv_s300", "plan_curv_s300"],
}


def current_params(study) -> dict:
    """The RF setting the earlier steps kept (C1), else the baseline."""
    f = study.step_dir("models") / "improve" / "c1.json"
    if f.exists():
        r = json.loads(f.read_text(encoding="utf-8"))
        if r.get("adopted"):
            return r["adopted"]
    return dict(BASE_RF)


def c3_table(study, cache_root, progress=None) -> pd.DataFrame:
    """The C3 terrain layers at the cells of the predictor tables (cached in ``models/improve/terrain_c3.parquet``)."""
    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.landslide.labels import grid_for, study_area
    from geoeyes.landslide.terrain import MARGIN_M, extra_layers
    from geoeyes.ml.layers import M_PER_DEG_LAT
    f = study.step_dir("models") / "improve" / "terrain_c3.parquet"
    if f.exists():
        return pd.read_parquet(f)
    grid = grid_for(study_area(study).bounds, study.labels.cell_m)
    pad = (MARGIN_M + 2000) / M_PER_DEG_LAT
    w, s, e, n = grid.bounds
    dem = load_copernicus30(s - pad, n + pad, w - pad, e + pad, cache_root / "dem" / "copernicus-30")
    lay = extra_layers(grid, dem, progress=progress)
    cells = pd.read_parquet(study.step_dir("predictors") / f"predictors_{study.events[0][0]}.parquet",
                            columns=["cell"]).cell.to_numpy()
    t = pd.DataFrame({"cell": cells, **{k: v[cells] for k, v in lay.items()}})
    f.parent.mkdir(parents=True, exist_ok=True)
    t.to_parquet(f, index=False)
    return t


def run_c3(study, cache_root, progress=None) -> dict:
    """Each C3 family added to the champion layers, scored against them (paired bootstrap, transfers), then all
    the kept families together. Writes ``models/improve/c3.json`` and ``c3.md``."""
    from geoeyes.io.manifest import atomic_write_json
    say = progress or (lambda m: log.info("%s", m))
    p = study.models
    out_dir = study.step_dir("models") / "improve"
    prm = current_params(study)
    extra = c3_table(study, cache_root, say)
    tb = load_tables(study, extra={ev: extra for ev, _ in study.events})
    say(f"L3c C3: RF {key(prm)}; {len(tb.draws)} draws; families {list(FAMILIES)}")
    base = evaluate(tb, prm, p.seed, p.folds)
    say(f"L3c C3: base pooled {base['pooled']}, transfer {base['transfer']}")
    res = {"step": "C3", "params": prm, "base": strip(base), "families": {}}
    kept = []
    for fam, cols in FAMILIES.items():
        r = evaluate(tb, prm, p.seed, p.folds, cols=tb.cols + cols)
        boot = paired_bootstrap(tb.draws, base["_oof"], r["_oof"])
        v = verdict(base, r, boot)
        res["families"][fam] = {"layers": cols, **strip(r), "paired": boot, **v}
        say(f"L3c C3 {fam}: pooled {r['pooled']} (Δ {boot['delta']:+.4f}, 95 % {boot['ci95']}), transfer "
            f"{r['transfer']}, keep {v['keep']}")
        if v["keep"]:
            kept += cols
    all_cols = [c for cols in FAMILIES.values() for c in cols]
    for name, cols in (("all", all_cols), ("kept", kept)):
        if not cols or (name == "kept" and cols == all_cols):
            continue
        r = evaluate(tb, prm, p.seed, p.folds, cols=tb.cols + cols)
        boot = paired_bootstrap(tb.draws, base["_oof"], r["_oof"])
        res[name] = {"layers": cols, **strip(r), "paired": boot, **verdict(base, r, boot)}
        say(f"L3c C3 {name}: pooled {r['pooled']} (Δ {boot['delta']:+.4f}, 95 % {boot['ci95']}), transfer "
            f"{r['transfer']}")
    atomic_write_json(out_dir / "c3.json", res)
    (out_dir / "c3.md").write_text(c3_md(res), encoding="utf-8")
    return res


def c3_md(r: dict) -> str:
    b = r["base"]
    tr = list(b["transfer"])
    lines = ["# L3c C3 — more terrain", "", f"RF {key(r['params'])}; each family added to the champion layers.", "",
             "| set | pooled | Δ (95 %) | " + " | ".join(b["by_event"]) + " | " + " | ".join(tr) + " | keep |",
             "|---|---|---|" + "---|" * (len(b["by_event"]) + len(tr)) + "---|",
             f"| champion layers | {b['pooled']} | — | " + " | ".join(str(v) for v in b["by_event"].values()) + " | "
             + " | ".join(str(b["transfer"][k]) for k in tr) + " | — |"]
    rows = [*r["families"].items(), *[(k, r[k]) for k in ("all", "kept") if k in r]]
    for name, x in rows:
        lines.append(f"| + {name} | {x['pooled']} | {x['paired']['delta']:+.4f} ({x['paired']['ci95'][0]:+.4f} – "
                     f"{x['paired']['ci95'][1]:+.4f}) | " + " | ".join(str(v) for v in x["by_event"].values())
                     + " | " + " | ".join(str(x["transfer"].get(k)) for k in tr) + f" | {x['keep']} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- C5
NEG_RATIOS = (3, 5)


def cross_oof(params: dict, seed: int, train: pd.DataFrame, test: pd.DataFrame, cols: list[str],
              folds: int) -> np.ndarray:
    """Spatial out-of-fold probabilities of the ``test`` rows from a model fitted on the ``train`` rows of the other
    blocks: the folds are those of ``test`` (``GroupKFold`` on its blocks; ``train`` blocks absent from ``test`` are
    always in training). ``train.weight``: sample weights when present. With ``train`` = ``test``, ``_oof``."""
    from sklearn.model_selection import GroupKFold
    col = f"block_{BLOCK_M:g}"
    g = test[col].to_numpy()
    y = test.label.to_numpy()
    p = np.full(len(test), np.nan)
    tb = train[col].to_numpy()
    w = train["weight"].to_numpy() if "weight" in train else None
    for _, te in GroupKFold(min(folds, len(np.unique(g)))).split(test, y, g):
        keep = ~np.isin(tb, np.unique(g[te]))
        fit = {"randomforestclassifier__sample_weight": w[keep]} if w is not None else {}
        m = rf(params, seed).fit(train[cols][keep], train.label.to_numpy()[keep], **fit)
        p[te] = m.predict_proba(test[cols].iloc[te])[:, 1]
    return p


def _fit_predict_w(params: dict, seed: int, train: pd.DataFrame, cols: list[str], xb: pd.DataFrame) -> np.ndarray:
    fit = {"randomforestclassifier__sample_weight": train["weight"].to_numpy()} if "weight" in train else {}
    return rf(params, seed).fit(train[cols], train.label.to_numpy(), **fit).predict_proba(xb[cols])[:, 1]


def evaluate_train(tb: Tables, trains: list[pd.DataFrame], params: dict, seed: int, folds: int) -> dict:
    """``evaluate`` with other training rows: each draw's model learnt on ``trains[d]`` and scored on the champion
    rows ``tb.draws[d]`` (the same test cells for every variant, so the AUC are comparable and paired)."""
    from joblib import delayed

    from geoeyes.landslide.model import run_jobs
    cols = tb.cols
    jobs = [delayed(cross_oof)(params, seed, tr, t, cols, folds) for tr, t in zip(trains, tb.draws, strict=True)]
    evs = sorted(tb.draws[0].event.unique())
    pairs = []
    if len(evs) == 2:
        for a, b in ((evs[0], evs[1]), (evs[1], evs[0])):
            for tr, t in zip(trains, tb.draws, strict=True):
                tt = t[(t.event == b) & t[tb.footprints[a]] & t[tb.footprints[b]]]
                if tt.label.nunique() == 2:
                    pairs.append((f"{a}->{b}", tt.label.to_numpy()))
                    jobs.append(delayed(_fit_predict_w)(params, seed, tr[tr.event == a], cols, tt))
    preds = run_jobs(jobs)
    oof, rest = preds[:len(tb.draws)], preds[len(tb.draws):]
    res = {"pooled": float(np.mean([auc(t.label, p) for t, p in zip(tb.draws, oof, strict=True)])),
           "by_event": {ev: float(np.mean([auc(t.label[t.event == ev], p[(t.event == ev).to_numpy()])
                                           for t, p in zip(tb.draws, oof, strict=True)])) for ev in evs},
           "transfer": {}}
    for (k, y), p in zip(pairs, rest, strict=True):
        res["transfer"].setdefault(k, []).append(auc(y, p))
    res["transfer"] = {k: float(np.mean(v)) for k, v in res["transfer"].items()}
    res = {k: (round(v, 4) if isinstance(v, float) else {a: round(b, 4) for a, b in v.items()})
           for k, v in res.items()}
    res["_oof"] = oof
    return res


class C5Data:
    """The rows each C5 variant trains on, per event and draw, built like the champion's (``EventData.rows``:
    reliable polygons, slope domain, main footprint, the predictors of the cell, 5 km blocks)."""

    def __init__(self, study):
        from geoeyes.landslide.labels import grid_for, study_area
        from geoeyes.landslide.model import EventData
        self.study = study
        self.area = study_area(study)
        self.grid = grid_for(self.area.bounds, study.labels.cell_m)
        self.ed = {ev: EventData(study, ev, self.grid.nx) for ev, _ in study.events}
        self.draws = min(e.draws for e in self.ed.values())

    def _ok_fids(self, ev: str) -> pd.Series:
        r = self.ed[ev].reliability
        return r.src_fid[r.reliability == "reliable"] if self.study.models.reliable and r is not None else None

    def table(self, ev: str, rows: pd.DataFrame) -> pd.DataFrame:
        """``rows`` (``cell``, ``label``, optional ``weight`` / ``area_m2``) with the predictors and the blocks."""
        from geoeyes.landslide.model import add_blocks
        e = self.ed[ev]
        keep = [c for c in ("cell", "label", "area_m2", "weight") if c in rows]
        t = rows[keep].merge(e.pred, on="cell", how="inner")
        if self.study.models.domain_deg:
            t = t[t.slope_deg >= self.study.models.domain_deg].copy()
        add_blocks(t, self.grid.nx, self.study)
        return t.assign(event=ev).reset_index(drop=True)

    def positives(self, ev: str, variant: str) -> pd.DataFrame:
        """Positives of a label variant (``scarp`` / ``upper`` / ``centroid``), reliable polygons, with ``weight``
        1 / (cells of its polygon) — 1 for one cell per polygon."""
        lab = self.ed[ev].labels
        pos = lab[(lab.label == 1) & (lab.variant == variant)]
        ok = self._ok_fids(ev)
        if ok is not None:
            pos = pos[pos.src_fid.isin(ok)]
        return pos.assign(weight=1.0 / pos.groupby("src_fid").cell.transform("size"))

    def polygon_positives(self, ev: str) -> pd.DataFrame:
        """Every cell whose centre is inside a (reliable) polygon of the event, weight 1 / its cells."""
        import geopandas as gpd

        from geoeyes.landslide.labels import cells_in
        polys = gpd.read_file(self.study.inventory, layer="polygons").to_crs(4326)
        polys = polys[(polys.event == ev) & polys.geometry.intersects(self.area)]
        ok = self._ok_fids(ev)
        if ok is not None:
            polys = polys[polys.src_fid.isin(ok)]
        parts = []
        for fid, area, g in zip(polys.src_fid, polys.area_m2, polys.geometry, strict=True):
            c = cells_in(self.grid, g)
            if len(c):
                parts.append(pd.DataFrame({"cell": c, "src_fid": int(fid), "area_m2": float(area)}))
        pos = pd.concat(parts, ignore_index=True).drop_duplicates("cell")
        return pos.assign(label=1, weight=1.0 / pos.groupby("src_fid").cell.transform("size"))

    def negatives(self, ev: str, draws: list[int], variant: str = "scarp") -> pd.DataFrame:
        """The negatives of several draws together (main footprint), each cell once."""
        lab = self.ed[ev].labels
        n = lab[(lab.label == 0) & (lab.variant == variant) & (lab.footprint == self.study.footprint_main)
                & lab.draw.isin(draws)]
        return n.drop_duplicates("cell").assign(weight=1.0)

    def unmapped_scar_cells(self) -> dict[str, np.ndarray]:
        """Cells on (or within the label buffer of) the Sentinel-2 objects of the calibration event that touch no
        inventory polygon (L3b.4): likely unmapped landslides, so not safe as negatives."""
        import geopandas as gpd

        from geoeyes.landslide.labels import cells_in, exclusion
        from geoeyes.landslide.scars import CALIBRATION
        f = self.study.step_dir("scars") / f"scars_{CALIBRATION}.gpkg"
        if not f.exists() or CALIBRATION not in self.ed:
            return {}
        g = gpd.read_file(f, layer="polygons").to_crs(4326)
        g = g[~g.in_inventory.astype(bool)]
        if g.empty:
            return {}
        return {CALIBRATION: cells_in(self.grid, exclusion(g, self.study.labels.negative_buffer_m))}


def c5_variants(data: C5Data) -> dict[str, list[pd.DataFrame]]:
    """Training rows of each C5 variant, one pooled table per draw (the champion's draw ``d`` and its neighbours)."""
    evs = [ev for ev, _ in data.study.events]
    nd = data.draws
    pos = {v: {ev: data.positives(ev, v) for ev in evs} for v in ("scarp", "upper", "centroid")}
    pos["polygon"] = {ev: data.polygon_positives(ev) for ev in evs}
    scars = data.unmapped_scar_cells()

    def pooled(pos_v: dict, d: int, k: int = 1, drop: dict | None = None) -> pd.DataFrame:
        out = []
        for ev in evs:
            neg = data.negatives(ev, [(d + i) % nd for i in range(k)])
            if drop and ev in drop:
                neg = neg[~neg.cell.isin(drop[ev])]
            out.append(data.table(ev, pd.concat([pos_v[ev].assign(label=1), neg.assign(label=0)])))
        return pd.concat(out, ignore_index=True)

    v = {
        "upper_w": [pooled(pos["upper"], d) for d in range(nd)],
        "centroid": [pooled(pos["centroid"], d) for d in range(nd)],
        "polygon_w": [pooled(pos["polygon"], d) for d in range(nd)],
        **{f"neg_1to{k}": [pooled(pos["scarp"], d, k) for d in range(nd)] for k in NEG_RATIOS},
    }
    if scars:
        v["no_unmapped_scars"] = [pooled(pos["scarp"], d, 1, scars) for d in range(nd)]
    return v


def run_c5(study, progress=None) -> dict:
    """Each C5 variant (other positives, more negatives, negatives off unmapped scars) trained instead of the
    champion rows and scored on them (spatial OOF, transfers, paired bootstrap). Writes ``models/improve/c5.json``
    and ``c5.md``."""
    from geoeyes.io.manifest import atomic_write_json
    say = progress or (lambda m: log.info("%s", m))
    p = study.models
    out_dir = study.step_dir("models") / "improve"
    out_dir.mkdir(parents=True, exist_ok=True)
    prm = current_params(study)
    tb = load_tables(study)
    data = C5Data(study)
    variants = c5_variants(data)
    say(f"L3c C5: RF {key(prm)}; {len(tb.draws)} draws; test rows per draw {len(tb.draws[0])}; variants "
        f"{list(variants)}")
    base = evaluate_train(tb, [t.assign(weight=1.0) for t in tb.draws], prm, p.seed, p.folds)
    say(f"L3c C5: champion rows pooled {base['pooled']}, transfer {base['transfer']}")
    scars = data.unmapped_scar_cells()
    res = {"step": "C5", "params": prm, "base": strip(base), "variants": {},
           "test_negatives_on_unmapped_scars": {ev: int(t[(t.event == ev) & (t.label == 0)].cell.isin(c).sum())
                                                for ev, c in scars.items() for t in tb.draws[:1]}}
    for name, trains in variants.items():
        r = evaluate_train(tb, trains, prm, p.seed, p.folds)
        boot = paired_bootstrap(tb.draws, base["_oof"], r["_oof"])
        v = verdict(base, r, boot)
        n_pos = int(np.mean([(t.label == 1).sum() for t in trains]))
        n_neg = int(np.mean([(t.label == 0).sum() for t in trains]))
        res["variants"][name] = {"train_positives": n_pos, "train_negatives": n_neg, **strip(r), "paired": boot, **v}
        say(f"L3c C5 {name} (train {n_pos} + / {n_neg} -): pooled {r['pooled']} (Δ {boot['delta']:+.4f}, 95 % "
            f"{boot['ci95']}), transfer {r['transfer']}, keep {v['keep']}")
    atomic_write_json(out_dir / "c5.json", res)
    (out_dir / "c5.md").write_text(c5_md(res), encoding="utf-8")
    return res


def c5_md(r: dict) -> str:
    b = r["base"]
    tr = list(b["transfer"])
    lines = ["# L3c C5 — labels and sampling", "",
             f"RF {key(r['params'])}. Every variant is trained on its own rows and scored on the champion rows (scarp "
             "cells of the reliable polygons and their 1 : 1 negatives), on the same 5 km blocks: the AUC are "
             "comparable and the bootstrap is paired.", "",
             "| training rows | + / − | pooled | Δ (95 %) | " + " | ".join(b["by_event"]) + " | " + " | ".join(tr)
             + " | keep |",
             "|---|---|---|---|" + "---|" * (len(b["by_event"]) + len(tr)) + "---|",
             f"| champion (scarp, 1 : 1) | — | {b['pooled']} | — | "
             + " | ".join(str(v) for v in b["by_event"].values()) + " | "
             + " | ".join(str(b["transfer"][k]) for k in tr) + " | — |"]
    for name, x in r["variants"].items():
        lines.append(f"| {name} | {x['train_positives']} / {x['train_negatives']} | {x['pooled']} | "
                     f"{x['paired']['delta']:+.4f} ({x['paired']['ci95'][0]:+.4f} – {x['paired']['ci95'][1]:+.4f}) | "
                     + " | ".join(str(v) for v in x["by_event"].values()) + " | "
                     + " | ".join(str(x["transfer"].get(k)) for k in tr) + f" | {x['keep']} |")
    if r.get("test_negatives_on_unmapped_scars"):
        lines += ["", f"Test negatives (draw 0) on unmapped Sentinel-2 scars: {r['test_negatives_on_unmapped_scars']}"]
    return "\n".join(lines) + "\n"


def summary(res: dict) -> str:
    return json.dumps({k: res[k] for k in ("baseline", "best", "nested")}, indent=1, default=str)

