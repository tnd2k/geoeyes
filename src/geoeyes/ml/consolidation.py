"""Consolidation settlement of the cells: how much more, and for how long (docs/en/research/
lines-and-consolidation.md §3).

Soft soil loaded by a new building or embankment settles fast at first, then slower and slower towards a final
settlement (primary consolidation). The first-order model

    s(t) = c + A · (1 − e^(−t/τ))

is what the Asaoka (1978) method fits on equally spaced readings (s_i = β₀ + β₁·s_(i−1), with β₁ = e^(−Δt/τ)):
the final settlement is c + A, the settlement still to come after the last date is A·e^(−T/τ) and 90 % of A is
reached at τ·ln 10. Here every sinking cell (GeoEyes sign: settlement s = −d) is fitted directly, τ on a grid and
(c, A) by least squares, and called consolidating when the curve beats a straight line by ``min_delta_bic``
(strong evidence) with A > 0 and τ within the reach of the data.

The check is a forecast: fitted on the first ``train_share`` of the epochs, both the curve and the line predict
the rest; their errors are reported side by side.
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
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.consolidation/1"
YEAR = 365.2425
TAUS_YR = np.geomspace(0.05, 30.0, 80)


@dataclass(frozen=True)
class ConsolidationParams:
    """``[postprocess.consolidation]`` of project.toml (every key optional)."""

    min_delta_bic: float = 6.0
    min_rate_mm_yr: float = 2.0       # cells sinking slower than this are left out
    max_tau_factor: float = 5.0       # τ up to this many times the span of the data (beyond: not determined)
    train_share: float = 0.7          # the check: fit on this share of the epochs, forecast the rest

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ConsolidationParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.consolidation]: unknown key(s) {unknown}; known: {sorted(names)}")
        return cls(**{k: type(getattr(cls, k))(v) for k, v in d.items()})


def fit(t_yr: np.ndarray, s: np.ndarray) -> dict[str, np.ndarray]:
    """Best (c, A, τ) per row of ``s`` (cells, T; settlement, mm, positive down) over the τ grid, and the line."""
    nc, n = s.shape
    ok = np.all(np.isfinite(s), axis=1)
    y = np.where(ok[:, None], s, 0.0)
    best = {"rss": np.full(nc, np.inf), "c": np.zeros(nc), "A": np.zeros(nc), "tau": np.full(nc, np.nan)}
    for tau in TAUS_YR:
        x = np.column_stack([np.ones(n), 1 - np.exp(-t_yr / tau)])
        coef = np.linalg.lstsq(x, y.T, rcond=None)[0].T
        rss = ((y - coef @ x.T) ** 2).sum(axis=1)
        better = rss < best["rss"]
        best["rss"] = np.where(better, rss, best["rss"])
        best["c"] = np.where(better, coef[:, 0], best["c"])
        best["A"] = np.where(better, coef[:, 1], best["A"])
        best["tau"] = np.where(better, tau, best["tau"])
    xl = np.column_stack([np.ones(n), t_yr])
    cl = np.linalg.lstsq(xl, y.T, rcond=None)[0].T
    best["rss_line"] = ((y - cl @ xl.T) ** 2).sum(axis=1)
    best["line"] = cl
    best["ok"] = ok
    return best


def _bic(rss, n, k):
    return n * np.log(np.maximum(rss, 1e-12) / n) + k * np.log(n)


def curve(c, A, tau, t_yr):
    return c + A * (1 - np.exp(-np.asarray(t_yr) / tau))


def run(product: Path, out: Path, params: ConsolidationParams, *, hazard_dir: Path, progress=None) -> dict:
    """Consolidation of the sinking cells of the hazard zoning of ``product`` into ``out``."""
    from geoeyes.hazard.assess import read_cells, read_summary, up_positive
    say = progress or (lambda m: log.info("%s", m))
    hz = read_summary(hazard_dir)
    if hz is None:
        raise DataError(f"no hazard zoning of {product.name}: run geoeyes hazard first")
    cells = read_cells(hazard_dir, hz)
    ts = np.load(hazard_dir / "cells_ts.npy").astype(np.float64)
    if not up_positive(hz):
        ts = -ts
    dates = np.array(hz["dates"], dtype="datetime64[D]")
    t = (dates - dates[0]).astype(np.float64) / YEAR
    n = len(t)
    if n < 8:
        raise DataError(f"{n} epochs: too few to fit a consolidation curve")
    s = -(ts - ts[:, :1])                                         # settlement, mm, positive down, 0 at the first date
    rate = cells["rate_mm_yr"].to_numpy(np.float64)
    sinking = (rate <= -params.min_rate_mm_yr) & (cells["mode"].to_numpy() == "subsidence")
    say(f"{int(sinking.sum())} sinking cells of {len(cells)}: fitting the consolidation curve")
    f = fit(t, s)
    gain = _bic(f["rss_line"], n, 2) - _bic(f["rss"], n, 3)
    span = t[-1]
    cons = (sinking & f["ok"] & (gain >= params.min_delta_bic) & (f["A"] > 0)
            & (f["tau"] < params.max_tau_factor * span) & (f["tau"] > TAUS_YR[0]))
    remaining = np.where(cons, f["A"] * np.exp(-span / f["tau"]), np.nan)
    total = np.where(cons, f["c"] + f["A"], np.nan)
    t90 = np.where(cons, np.maximum(0.0, f["tau"] * np.log(10) - span), np.nan)

    # the check: fit on the first epochs, forecast the last ones, curve against line
    m = max(6, int(round(params.train_share * n)))
    check = {}
    if n - m >= 3 and cons.any():
        fh = fit(t[:m], s[:, :m])
        sel = cons & fh["ok"]
        pc = curve(fh["c"][sel, None], fh["A"][sel, None], fh["tau"][sel, None], t[None, m:])
        pl = fh["line"][sel, :1] + fh["line"][sel, 1:] * t[None, m:]
        obs = s[sel][:, m:]
        check = {"cells": int(sel.sum()), "train_epochs": m, "test_epochs": n - m,
                 "mae_curve_mm": round(float(np.mean(np.abs(pc - obs))), 2),
                 "mae_line_mm": round(float(np.mean(np.abs(pl - obs))), 2),
                 "curve_better_share": round(float(np.mean(np.mean(np.abs(pc - obs), axis=1)
                                                          < np.mean(np.abs(pl - obs), axis=1))), 3)}
    table = pd.DataFrame({
        "cell": cells["cell"].to_numpy(np.int32), "lon": cells["lon"], "lat": cells["lat"],
        "consolidating": cons, "tau_yr": np.where(cons, f["tau"], np.nan).astype(np.float32),
        "settled_mm": np.where(cons, s[:, -1], np.nan).astype(np.float32),
        "final_mm": total.astype(np.float32), "remaining_mm": remaining.astype(np.float32),
        "t90_from_now_yr": t90.astype(np.float32), "c_mm": np.where(cons, f["c"], np.nan).astype(np.float32),
        "A_mm": np.where(cons, f["A"], np.nan).astype(np.float32), "delta_bic": gain.astype(np.float32),
    })
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "consolidation.parquet", index=False)
    rem = remaining[cons]
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "hazard_created": hz.get("created"), "params": asdict(params), "dates": hz["dates"],
        "n_cells": len(table), "sinking_cells": int(sinking.sum()), "consolidating": int(cons.sum()),
        "remaining_mm": {"median": round(float(np.median(rem)), 1), "p90": round(float(np.percentile(rem, 90)), 1),
                         "max": round(float(rem.max()), 1)} if cons.any() else None,
        "tau_yr_median": round(float(np.median(f["tau"][cons])), 2) if cons.any() else None,
        "check": check, "method": "docs/en/research/lines-and-consolidation.md",
    }
    atomic_write_json(out / "consolidation.json", summary)
    man = Manifest(kind="consolidation", id=product.name, engine=SCHEMA, inputs=[InputRef("hazard", str(hazard_dir))],
                   params=summary["params"], metrics={"consolidating": int(cons.sum())})
    man.add_outputs(out, ["consolidation.parquet", "consolidation.json"])
    man.write(out)
    say(f"consolidating cells: {int(cons.sum())}" + (f"; check: curve {check['mae_curve_mm']} mm, line "
                                                      f"{check['mae_line_mm']} mm" if check else ""))
    return summary


def asaoka(t_days: np.ndarray, s: np.ndarray, step_days: float = 60.0) -> dict:
    """The Asaoka construction of one series: s resampled every ``step_days``, the line s_i = β₀ + β₁·s_(i−1) and
    the final settlement β₀ / (1 − β₁) where it crosses s_i = s_(i−1)."""
    grid = np.arange(t_days[0], t_days[-1] + 1e-6, step_days)
    r = np.interp(grid, t_days, s)
    a, b = r[:-1], r[1:]
    if len(a) < 3:
        return {"prev": [], "next": [], "b0": None, "b1": None, "final": None}
    b1, b0 = np.polyfit(a, b, 1)
    final = b0 / (1 - b1) if 0 < b1 < 1 else None
    return {"prev": a.tolist(), "next": b.tolist(), "b0": float(b0), "b1": float(b1),
            "final": None if final is None else float(final), "step_days": step_days}


def read_summary(folder: Path) -> dict | None:
    f = folder / "consolidation.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
