"""Kind of motion of every cell of a hazard zoning (docs/en/research/behaviour-and-risk.md §2).

A rate says how fast a cell moves; it does not say how. Each cell's series is fitted with a small set of models,
each with a physical reading, and the simplest one that the data support is kept (Bayesian information criterion;
a richer model must lower the BIC by ``min_delta_bic`` to be preferred):

========== ============================== =====================================================================
class      model                          reading
========== ============================== =====================================================================
stable     d = a                          no motion beyond the stability threshold of the zoning
steady     d = a + b·t                    constant rate (aquifer compaction, creep)
seasonal   d = a + b·t + c·sin + e·cos    annual cycle on top of the trend (recharge / pumping, thermal)
speeding   d = a + b·t + c·t²             the motion grows (|rate| increases)
slowing    d = a + b·t + c·t²             the motion fades (consolidation after loading)
onset      d = a + b·t + h·(t − t₀)₊      a change of rate at t₀: motion starts (or stops) at a date
step       d = a + b·t + δ·H(t − t₀)      a jump at t₀: a sudden event, or an unwrapping error to check
========== ============================== =====================================================================

The series are those of the zoning (``cells_ts.npy``, GeoEyes sign); the classes are read in the direction of
the cell's own motion, so "speeding" means faster sinking for a sinking cell and faster uplift for a rising one.
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

SCHEMA = "geoeyes.behaviour/1"
CLASSES = ("stable", "steady", "seasonal", "speeding", "slowing", "onset", "step")
YEAR = 365.2425


@dataclass(frozen=True)
class BehaviourParams:
    """``[postprocess.behaviour]`` of project.toml (every key optional)."""

    min_delta_bic: float = 6.0          # a richer model must lower the BIC this much ("strong" evidence, Kass &
                                        # Raftery 1995)
    edge_epochs: int = 3                # a change point leaves at least this many epochs on each side
    min_span_seasonal_yr: float = 0.9   # an annual term needs about a year of data

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> BehaviourParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.behaviour]: unknown key(s) {unknown}; known: {sorted(names)}")
        return cls(**{k: type(getattr(cls, k))(v) for k, v in d.items()})


def _fit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Least squares of every row of ``y`` (cells, T) on the columns of ``x`` (T, k): (coef (cells, k), rss)."""
    coef = np.linalg.lstsq(x, y.T, rcond=None)[0].T
    res = y - coef @ x.T
    return coef, (res ** 2).sum(axis=1)


def _bic(rss: np.ndarray, n: int, k: int) -> np.ndarray:
    return n * np.log(np.maximum(rss, 1e-12) / n) + k * np.log(n)


def classify(t_days: np.ndarray, series: np.ndarray, stable: np.ndarray, params: BehaviourParams) -> dict:
    """Classes of ``series`` (cells, T; mm, any sign) observed at ``t_days``; ``stable`` (cells,) mm/yr thresholds.

    Returns per cell: ``cls`` (index in CLASSES), ``t0`` (index of the change epoch, −1 if none), ``rate`` (linear
    rate), ``rate_before`` / ``rate_after`` (onset), ``acc`` (2c, speeding / slowing), ``amp`` (seasonal), ``jump``
    (step), ``dbic`` (BIC of the linear model minus the BIC of the kept one) and ``fit`` (cells, T)."""
    s = np.asarray(series, np.float64)
    nc, n = s.shape
    t = (np.asarray(t_days, np.float64) - t_days[0]) / YEAR
    ok = np.all(np.isfinite(s), axis=1)
    y = np.where(ok[:, None], s, 0.0)
    one = np.ones(n)
    out = {k: np.full(nc, np.nan) for k in ("rate", "rate_before", "rate_after", "acc", "amp", "jump", "dbic")}
    out["cls"] = np.full(nc, -1, np.int8)
    out["t0"] = np.full(nc, -1, np.int16)
    out["fit"] = np.full((nc, n), np.nan)
    if n < 2 * params.edge_epochs + 3:
        raise DataError(f"{n} epochs: too few to classify the motion (at least {2 * params.edge_epochs + 3})")

    models: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, int]] = {}      # name -> (coef, rss, fit, k)

    def add(name: str, x: np.ndarray):
        c, r = _fit(x, y)
        models[name] = (c, r, c @ x.T, x.shape[1])

    add("const", one[:, None])
    add("lin", np.column_stack([one, t]))
    add("quad", np.column_stack([one, t, t ** 2]))
    if t[-1] >= params.min_span_seasonal_yr:
        add("seas", np.column_stack([one, t, np.sin(2 * np.pi * t), np.cos(2 * np.pi * t)]))
    # change points: the best epoch per cell (the epoch is a parameter too: k counts it)
    changes = (("hinge", lambda t0: np.maximum(0.0, t - t[t0])), ("step", lambda t0: (t >= t[t0]).astype(float)))
    for name, col in changes:
        best_rss = np.full(nc, np.inf)
        best = (np.zeros((nc, 3)), np.zeros((nc, n)), np.full(nc, -1, np.int16))
        for t0 in range(params.edge_epochs, n - params.edge_epochs):
            x = np.column_stack([one, t, col(t0)])
            c, r = _fit(x, y)
            better = r < best_rss
            best_rss = np.where(better, r, best_rss)
            best[0][better], best[1][better], best[2][better] = c[better], (c @ x.T)[better], t0
        models[name] = (best[0], best_rss, best[1], 4)
        out[f"t0_{name}"] = best[2]

    bic = {m: _bic(v[1], n, v[3]) for m, v in models.items()}
    lin_c = models["lin"][0]
    out["rate"] = lin_c[:, 1]
    # the simplest model the data support: linear (or stable), unless a richer one lowers the BIC enough
    rich = [m for m in ("quad", "seas", "hinge", "step") if m in models]
    rich_bic = np.stack([bic[m] for m in rich])
    k = np.argmin(rich_bic, axis=0)
    gain = bic["lin"] - rich_bic[k, np.arange(nc)]
    use_rich = gain >= params.min_delta_bic
    moving = np.abs(lin_c[:, 1]) >= stable

    cls = np.where(moving, CLASSES.index("steady"), CLASSES.index("stable")).astype(np.int8)
    fit = np.where(moving[:, None], models["lin"][2], models["const"][2])
    dbic = np.zeros(nc)
    for j, m in enumerate(rich):
        sel = use_rich & (k == j)
        if not sel.any():
            continue
        c, _, f, _ = models[m]
        fit[sel] = f[sel]
        dbic[sel] = gain[sel]
        if m == "quad":
            # the motion grows when the rate at the end is larger in size than at the start (any direction)
            grows = np.abs(c[:, 1] + 2 * c[:, 2] * t[-1]) > np.abs(c[:, 1])
            cls[sel] = np.where(grows[sel], CLASSES.index("speeding"), CLASSES.index("slowing"))
            out["acc"][sel] = 2 * c[sel, 2]
        elif m == "seas":
            cls[sel] = CLASSES.index("seasonal")
            out["amp"][sel] = np.hypot(c[sel, 2], c[sel, 3])
        elif m == "hinge":
            cls[sel] = CLASSES.index("onset")
            out["t0"][sel] = out["t0_hinge"][sel]
            out["rate_before"][sel] = c[sel, 1]
            out["rate_after"][sel] = c[sel, 1] + c[sel, 2]
        else:
            cls[sel] = CLASSES.index("step")
            out["t0"][sel] = out["t0_step"][sel]
            out["jump"][sel] = c[sel, 2]
    cls[~ok] = -1
    fit[~ok] = np.nan
    out.update(cls=cls, fit=fit, dbic=dbic)
    for key in ("t0_hinge", "t0_step"):
        out.pop(key)
    return out


def run(product: Path, out: Path, params: BehaviourParams, *, hazard_dir: Path, progress=None) -> dict:
    """Kinds of motion of the cells of the hazard zoning of ``product`` into ``out``."""
    from geoeyes.hazard.assess import read_cells, read_summary, up_positive
    say = progress or (lambda m: log.info("%s", m))
    hz = read_summary(hazard_dir)
    if hz is None:
        raise DataError(f"no hazard zoning of {product.name}: run geoeyes hazard first (its cells are classified)")
    cells = read_cells(hazard_dir, hz)
    ts = np.load(hazard_dir / "cells_ts.npy").astype(np.float64)
    if not up_positive(hz):
        ts = -ts
    dates = np.array(hz["dates"], dtype="datetime64[D]")
    t_days = (dates - dates[0]).astype(np.float64)
    stable = cells["stable_mm_yr"].to_numpy(np.float64) if "stable_mm_yr" in cells else np.full(len(cells), 2.0)
    say(f"{len(cells)} cells, {len(dates)} epochs: fitting {len(CLASSES)} kinds of motion")
    r = classify(t_days, ts, np.nan_to_num(stable, nan=2.0), params)
    cls = r["cls"]
    onset = np.where(r["t0"] >= 0, np.array([str(d) for d in dates], dtype=object)[np.clip(r["t0"], 0, None)], "")
    table = pd.DataFrame({
        "cell": cells["cell"].to_numpy(np.int32), "lon": cells["lon"], "lat": cells["lat"], "mode": cells["mode"],
        "class": np.where(cls >= 0, np.array(CLASSES, dtype=object)[np.clip(cls, 0, None)], "not assessed"),
        "class_id": cls, "change_date": onset, "rate_mm_yr": r["rate"].astype(np.float32),
        "rate_before_mm_yr": r["rate_before"].astype(np.float32),
        "rate_after_mm_yr": r["rate_after"].astype(np.float32),
        "acc_mm_yr2": r["acc"].astype(np.float32), "seasonal_amp_mm": r["amp"].astype(np.float32),
        "jump_mm": r["jump"].astype(np.float32), "delta_bic": r["dbic"].astype(np.float32),
    })
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "behaviour.parquet", index=False)
    np.save(out / "behaviour_fit.npy", r["fit"].astype(np.float32))
    counts = {c: int((cls == i).sum()) for i, c in enumerate(CLASSES)}
    changes = table.loc[table["change_date"] != "", "change_date"].str.slice(0, 7).value_counts().sort_index()
    # a change shared by many cells on one date is more likely one acquisition (atmosphere, unwrapping) than ground
    by_date = table.loc[table["change_date"] != "", "change_date"].value_counts()
    floor = max(20.0, 5 * float(by_date.median())) if len(by_date) else np.inf
    shared = sorted(d for d, n in by_date.items() if n >= floor and n >= 0.25 * by_date.sum())
    warnings = [f"{int(by_date[d])} cells change on {d}: a change shared by so many cells points to that acquisition "
                f"(atmosphere, unwrapping) rather than to the ground; check it before reading them as onsets"
                for d in shared]
    for w in warnings:
        say(w)
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "hazard_created": hz.get("created"), "params": asdict(params), "classes": list(CLASSES),
        "dates": hz["dates"], "n_cells": len(table), "counts": counts,
        "not_assessed": int((cls < 0).sum()), "changes_by_month": {k: int(v) for k, v in changes.items()},
        "shared_change_dates": shared, "warnings": warnings,
        "sign": "negative = sinking / downslope", "method": "docs/en/research/behaviour-and-risk.md",
    }
    atomic_write_json(out / "behaviour.json", summary)
    m = Manifest(kind="behaviour", id=product.name, engine=SCHEMA, inputs=[InputRef("hazard", str(hazard_dir))],
                 params=summary["params"], metrics=counts)
    m.add_outputs(out, ["behaviour.parquet", "behaviour_fit.npy", "behaviour.json"])
    m.write(out)
    say("kinds of motion: " + ", ".join(f"{c} {n}" for c, n in counts.items()))
    return summary


def read_summary(folder: Path) -> dict | None:
    f = folder / "behaviour.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
