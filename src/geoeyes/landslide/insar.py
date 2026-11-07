"""L5 — pre-event InSAR as a susceptibility predictor (Q3, H3).

The hazard cells (100 m) of a pre-event product are attached to the 30 m study cells (the 100 m cell that holds
each one); then:

1. coverage of the main footprint's slope cells, by forest class (the gate of the plan: below 10 % H3 is answered
   only for the covered subset, and labelled as such);
2. H3: the champion model on the covered rows of the event, with and without the InSAR features (paired 5 km block
   bootstrap of Δ AUC, the L3c machinery);
3. the share of landslide cells and of negative cells that sat on a "moving" cell (|downslope rate| above the
   stability threshold of the hazard analysis).

Only images before the event enter (the product's last date is checked against the event date).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

FEATURES = ("insar_rate_mm_yr", "insar_abs_rate_mm_yr", "insar_moving", "insar_coherence", "insar_points")
COVERAGE_GATE = 0.10
SLOPE_MIN_DEG = 10.0            # the hazard analysis' landslide mode starts here
FOREST_PCT = 50.0               # tree_cover_2000 at or above: forest
MIN_ROWS = 100                  # covered rows needed for the H3 test (low power below a few hundred: reported)
MIN_POSITIVES = 30


def hazard_cells(folder: Path) -> tuple[pd.DataFrame, dict]:
    from geoeyes.hazard.assess import read_cells, read_summary
    s = read_summary(folder) or {}
    return read_cells(folder, s), s


def attach(lon: np.ndarray, lat: np.ndarray, cells: pd.DataFrame, cell_m: float) -> pd.DataFrame:
    """The InSAR features at points (lon, lat): those of the hazard cell holding each point (its nearest centre
    within half a diagonal), NaN where no cell; ``insar_covered`` 0 / 1."""
    from scipy.spatial import cKDTree

    from geoeyes.ml.layers import M_PER_DEG_LAT, M_PER_DEG_LON
    lat0 = float(np.median(cells["lat"]))
    kx = M_PER_DEG_LON * math.cos(math.radians(lat0))
    tree = cKDTree(np.column_stack([cells["lon"].to_numpy() * kx, cells["lat"].to_numpy() * M_PER_DEG_LAT]))
    d, k = tree.query(np.column_stack([lon * kx, lat * M_PER_DEG_LAT]), distance_upper_bound=cell_m / math.sqrt(2))
    hit = np.isfinite(d)
    k = np.where(hit, k, 0)
    land = cells["mode"].to_numpy() == "landslide"
    meas = land & (cells["sensitivity"].to_numpy() >= 0.3)
    rate = np.where(meas, cells["rate_mm_yr"].to_numpy(np.float64), np.nan)
    stable = cells["stable_mm_yr"].to_numpy(np.float64)
    moving = np.where(meas, (np.abs(rate) >= stable).astype(float), np.nan)
    out = pd.DataFrame({
        "insar_rate_mm_yr": rate[k], "insar_abs_rate_mm_yr": np.abs(rate)[k], "insar_moving": moving[k],
        "insar_coherence": cells["coherence"].to_numpy(np.float64)[k],
        "insar_points": cells["n_points"].to_numpy(np.float64)[k]})
    out[~hit] = np.nan
    out["insar_covered"] = (hit & np.isfinite(out["insar_rate_mm_yr"].to_numpy())).astype(np.int8)
    return out


def coverage(pred: pd.DataFrame, feats: pd.DataFrame, footprint: str) -> dict:
    """Share of the footprint's slope cells (≥ 10°) covered, overall and by forest class."""
    m = pred[footprint].to_numpy(bool) & (pred["slope_deg"].to_numpy() >= SLOPE_MIN_DEG)
    cov = feats["insar_covered"].to_numpy(bool)
    forest = pred["tree_cover_2000"].to_numpy() >= FOREST_PCT
    out = {"slope_cells": int(m.sum()), "covered": int((m & cov).sum()),
           "share": round(float((m & cov).sum() / max(m.sum(), 1)), 4), "by_forest": {}}
    for name, f in (("forest", forest), ("open", ~forest)):
        mm = m & f
        out["by_forest"][name] = {"slope_cells": int(mm.sum()),
                                  "share": round(float((mm & cov).sum() / max(mm.sum(), 1)), 4)}
    out["gate_passed"] = out["share"] >= COVERAGE_GATE
    return out


def moving_shares(rows: pd.DataFrame) -> dict:
    """Share of positive and of negative rows on a moving cell (covered rows only), with a block bootstrap
    interval of the difference."""
    from geoeyes.landslide.improve import BLOCK_M
    r = rows[rows["insar_covered"] == 1]
    if r.empty or r.label.nunique() < 2:
        return {"rows": len(r)}
    pos, neg = r[r.label == 1].insar_moving.mean(), r[r.label == 0].insar_moving.mean()
    rng = np.random.default_rng(0)
    col = f"block_{BLOCK_M:g}"
    groups = [g for _, g in r.groupby(col)]
    diffs = []
    for _ in range(1000):
        b = pd.concat([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if b.label.nunique() == 2:
            diffs.append(b[b.label == 1].insar_moving.mean() - b[b.label == 0].insar_moving.mean())
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    return {"rows": len(r), "positives": int((r.label == 1).sum()), "moving_pos": round(float(pos), 4),
            "moving_neg": round(float(neg), 4), "diff": round(float(pos - neg), 4),
            "diff_ci95": [round(float(lo), 4), round(float(hi), 4)]}


def find_hazard(project_dir: Path) -> Path:
    found = sorted(Path(project_dir).rglob("hazard.json"), key=lambda p: p.stat().st_mtime)
    if not found:
        from geoeyes.errors import DataError
        raise DataError(f"{project_dir.name}: no hazard analysis (run `geoeyes hazard {project_dir.name}`)")
    return found[-1].parent


def run_l5(study, project_dir: Path, event: str = "Molave", progress=None) -> dict:
    """Coverage, H3 and the moving shares for one event; ``<study>/insar/l5_report.md``, ``l5.json``,
    ``insar_features_<event>.parquet``."""
    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide import improve as im
    say = progress or (lambda m: log.info("%s", m))
    folder = find_hazard(Path(project_dir))
    cells, summ = hazard_cells(folder)
    cell_m = float(summ.get("params", {}).get("cell_m", 100.0))
    ev_date = dict(study.events)[event]
    last = str(summ["dates"][-1])[:10] if summ.get("dates") else None
    if last and last >= str(ev_date)[:10]:
        from geoeyes.errors import DataError
        raise DataError(f"L5: the product ends {last}, not before the event ({ev_date}): post-event images leak")
    pred = pd.read_parquet(study.step_dir("predictors") / f"predictors_{event}.parquet",
                           columns=["cell", "lon", "lat", "slope_deg", "tree_cover_2000",
                                    f"in_{study.footprint_main}_{event}"])
    feats = attach(pred.lon.to_numpy(), pred.lat.to_numpy(), cells, cell_m)
    feats.insert(0, "cell", pred.cell.to_numpy())
    out_dir = study.step_dir("insar")
    out_dir.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(out_dir / f"insar_features_{event}.parquet", index=False)
    cov = coverage(pred, feats, f"in_{study.footprint_main}_{event}")
    say(f"L5 coverage: {cov['share']:.1%} of {cov['slope_cells']:,} slope cells (forest "
        f"{cov['by_forest']['forest']['share']:.1%}, open {cov['by_forest']['open']['share']:.1%})")
    res: dict = {"event": event, "event_date": str(ev_date), "hazard": str(folder), "product_last_date": last,
                 "hazard_cells": len(cells), "landslide_mode_cells": int((cells["mode"] == "landslide").sum()),
                 "coverage": cov, "subset_only": not cov["gate_passed"]}
    tb = im.load_tables(study, extra={event: feats})
    rows = [t[(t.event == event) & (t.insar_covered == 1)].reset_index(drop=True) for t in tb.draws]
    res["moving"] = moving_shares(rows[0])
    n_pos = int(rows[0].label.sum())
    res["h3_rows"], res["h3_positives"] = len(rows[0]), n_pos
    if len(rows[0]) < MIN_ROWS or n_pos < MIN_POSITIVES:
        res["h3"] = {"tested": False, "why": f"{len(rows[0])} covered rows, {n_pos} positives (need {MIN_ROWS}, "
                                              f"{MIN_POSITIVES})"}
    else:
        prm = im.current_params(study)
        sub = im.Tables(rows, tb.cols, tb.footprints)
        p = study.models
        base = im.evaluate(sub, prm, p.seed, p.folds, transfer=False)
        new = im.evaluate(sub, prm, p.seed, p.folds, cols=tb.cols + list(FEATURES), transfer=False)
        boot = im.paired_bootstrap(sub.draws, base["_oof"], new["_oof"])
        res["h3"] = {"tested": True, "params": prm, "base_auc": base["pooled"], "insar_auc": new["pooled"],
                     "paired": boot, "supported": bool(boot["delta"] >= im.KEEP_GAIN and boot["ci95"][0] > 0)}
        say(f"L5 H3: AUC {base['pooled']} -> {new['pooled']} (Δ {boot['delta']:+.4f}, 95 % {boot['ci95']})")
    atomic_write_json(out_dir / "l5.json", res)
    (out_dir / "l5_report.md").write_text(report_md(res), encoding="utf-8")
    return res


def report_md(r: dict) -> str:
    c = r["coverage"]
    L = [f"# L5 — pre-event InSAR against the {r['event']} landslides (H3)", "",
         f"Hazard analysis `{r['hazard']}`: {r['hazard_cells']:,} cells of 100 m, {r['landslide_mode_cells']:,} in "
         f"landslide mode. Event {r['event_date']}; product last date {r['product_last_date']}.", "",
         "## Coverage of the main footprint's slope cells (≥ 10°)", "",
         f"- all: **{c['share']:.1%}** of {c['slope_cells']:,} cells — gate {COVERAGE_GATE:.0%}: "
         f"{'passed' if c['gate_passed'] else '**not passed**: H3 holds for the covered subset only'}",
         f"- forest (tree cover 2000 ≥ {FOREST_PCT:g} %): {c['by_forest']['forest']['share']:.1%} of "
         f"{c['by_forest']['forest']['slope_cells']:,}",
         f"- open: {c['by_forest']['open']['share']:.1%} of {c['by_forest']['open']['slope_cells']:,}", ""]
    m = r["moving"]
    if "moving_pos" in m:
        L += ["## Landslide cells on a moving cell", "",
              f"{m['rows']:,} covered rows, {m['positives']} positives: moving **{m['moving_pos']:.1%}** of positives "
              f"against {m['moving_neg']:.1%} of negatives (difference {m['diff']:+.3f}, 95 % "
              f"{m['diff_ci95'][0]:+.3f} – {m['diff_ci95'][1]:+.3f}, 5 km blocks).", ""]
    h = r["h3"]
    L += ["## H3 — does pre-event InSAR add to terrain?", ""]
    if h["tested"]:
        b = h["paired"]
        word = "supported" if h["supported"] else "not supported"
        L.append(f"Champion layers AUC {h['base_auc']} → with InSAR {h['insar_auc']}: Δ **{b['delta']:+.4f}** (95 % "
                 f"{b['ci95'][0]:+.4f} – {b['ci95'][1]:+.4f}). H3 **{word}**"
                 f"{' (covered subset only)' if r['subset_only'] else ''}.")
    else:
        L.append(f"Not tested: {h['why']}.")
    return "\n".join(L) + "\n"
