"""Soft-soil thickness against the subsidence of the cells (docs/en/research/two-geometries-and-soft-soil.md §3).

The compressible layer is what sinks: under the same drop of the water table, the settlement grows with the
thickness of soft clay and peat, and the time a load takes to consolidate grows with the square of its drainage
path. Per hazard cell of the product:

* the thickness of the soft layer (``geoeyes.ancillary.geology``: project raster, boreholes, or the open grid);
* the rate of the sinking cells by thickness class, the share of moving cells, and the rank correlation between
  thickness and sinking (Spearman);
* for the consolidating cells (``geoeyes consolidation``), the coefficient of consolidation implied by their time
  constant: the first term of Terzaghi's solution gives τ = 4·H_dr² / (π²·c_v), hence c_v = 4·H_dr² / (π²·τ),
  with H_dr = H/2 when the layer drains on both faces. Values far from the usual 0.1–10 m²/yr of soft clays
  (Holtz & Kovacs 1981) mean that the thickness, or the reading of the cell as consolidation, is wrong.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.ancillary.geology import SOURCES, GeologyParams, thickness
from geoeyes.core.errors import DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.geology/1"
CV_RANGE = (0.1, 10.0)                # m²/yr, soft clays


def implied_cv(h_m: np.ndarray, tau_yr: np.ndarray, drainage: str = "double") -> np.ndarray:
    """Coefficient of consolidation (m²/yr) that a layer of thickness ``h_m`` needs to consolidate with ``tau_yr``."""
    h_dr = np.asarray(h_m, float) / (2.0 if drainage == "double" else 1.0)
    return 4.0 * h_dr ** 2 / (np.pi ** 2 * np.asarray(tau_yr, float))


def by_class(h: np.ndarray, rate: np.ndarray, sinking: np.ndarray, bins: int, moving: float) -> list[dict]:
    """Rate of the sinking cells and share of moving cells per thickness class (quantiles)."""
    ok = np.isfinite(h) & np.isfinite(rate)
    if ok.sum() < bins * 5:
        return []
    edges = np.unique(np.quantile(h[ok], np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        return []
    k = np.clip(np.searchsorted(edges, h, side="right") - 1, 0, len(edges) - 2)
    out = []
    for j in range(len(edges) - 1):
        sel = ok & (k == j)
        s = sel & sinking
        out.append({"from_m": round(float(edges[j]), 1), "to_m": round(float(edges[j + 1]), 1),
                    "cells": int(sel.sum()),
                    "median_rate_mm_yr": round(float(np.median(rate[s])), 2) if s.any() else None,
                    "moving_share": round(float(np.mean(rate[sel] <= -moving)), 3) if sel.any() else None})
    return out


def run(product: Path, out: Path, params: GeologyParams, *, hazard_dir: Path, consolidation_dir: Path,
        project_dir: Path, cache: Path, token: str = "", progress=None) -> dict:
    """Soft-soil thickness of the hazard cells of ``product`` and its relation to the subsidence, into ``out``."""
    from scipy.stats import spearmanr

    from geoeyes.hazard.assess import read_cells, read_summary
    say = progress or (lambda m: log.info("%s", m))
    hz = read_summary(hazard_dir)
    if hz is None:
        raise DataError(f"no hazard zoning of {product.name}: run geoeyes hazard first")
    cells = read_cells(hazard_dir, hz)
    t = thickness(cells["lon"].to_numpy(), cells["lat"].to_numpy(), params, project_dir=project_dir, cache=cache,
                  token=token)
    h = t["thickness_m"]
    say(f"soft-soil thickness from {SOURCES[t['source']]}: {int(np.isfinite(h).sum())} of {len(h)} cells")
    rate = cells["rate_mm_yr"].to_numpy(np.float64)
    sinking = (cells["mode"].to_numpy() == "subsidence") & (rate < 0)
    ok = np.isfinite(h) & np.isfinite(rate) & sinking
    rho = p = None
    if ok.sum() >= 20 and np.ptp(h[ok]) > 0:
        r = spearmanr(h[ok], -rate[ok])
        rho, p = round(float(r.statistic), 3), float(r.pvalue)

    table = pd.DataFrame({"cell": cells["cell"].to_numpy(np.int32), "lon": cells["lon"], "lat": cells["lat"],
                          "thickness_m": h.astype(np.float32)})
    if "nearest_km" in t:
        table["nearest_borehole_km"] = t["nearest_km"].astype(np.float32)
    cv = {}
    cf = consolidation_dir / "consolidation.parquet"
    if cf.exists():
        c = pd.read_parquet(cf)
        if len(c) == len(table):
            sel = c["consolidating"].to_numpy() & np.isfinite(h)
            if sel.any():
                v = implied_cv(h[sel], c["tau_yr"].to_numpy()[sel], params.drainage)
                table["cv_m2_yr"] = np.float32(np.nan)
                table.loc[sel, "cv_m2_yr"] = v.astype(np.float32)
                cv = {"cells": int(sel.sum()), "median_m2_yr": round(float(np.median(v)), 2),
                      "p10_m2_yr": round(float(np.percentile(v, 10)), 2),
                      "p90_m2_yr": round(float(np.percentile(v, 90)), 2),
                      "within_range_share": round(float(np.mean((v >= CV_RANGE[0]) & (v <= CV_RANGE[1]))), 3),
                      "range_m2_yr": list(CV_RANGE), "drainage": params.drainage}
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "geology.parquet", index=False)
    hv = h[np.isfinite(h)]
    warnings = []
    if t["source"] == "open":
        warnings.append("thickness from the open global grid (depth to bedrock, capped at 50 m), not the soft layer: "
                        "set [postprocess.geology] raster or boreholes for a real map")
    if hv.size and np.mean(hv >= 49.5) > 0.5:
        warnings.append(f"{round(100 * float(np.mean(hv >= 49.5)))} % of the cells at the 50 m cap: the grid cannot "
                        "tell them apart")
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": asdict(params), "source": t["source"], "source_label": SOURCES[t["source"]],
        "file": Path(t["file"]).name, "boreholes": t.get("boreholes"),
        "cells": len(table), "covered": int(hv.size),
        "thickness_m": {"min": round(float(hv.min()), 1), "median": round(float(np.median(hv)), 1),
                        "max": round(float(hv.max()), 1)} if hv.size else None,
        "spearman_rho": rho, "spearman_p": p, "sinking_cells": int(ok.sum()),
        "by_class": by_class(h, rate, sinking, params.bins, params.moving_mm_yr),
        "consolidation_cv": cv, "warnings": warnings, "method": "docs/en/research/two-geometries-and-soft-soil.md",
    }
    atomic_write_json(out / "geology.json", summary)
    m = Manifest(kind="geology", id=product.name, engine=SCHEMA, inputs=[InputRef("hazard", str(hazard_dir))],
                 params=summary["params"], metrics={"covered": int(hv.size)})
    m.add_outputs(out, ["geology.parquet", "geology.json"])
    m.write(out)
    say(f"thickness vs sinking: Spearman rho = {rho}"
        + (f"; implied c_v median {cv['median_m2_yr']} m²/yr" if cv else ""))
    return summary


def read_summary(folder: Path) -> dict | None:
    f = folder / "geology.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
