"""Deformation forecasting on the analysis cells of a product (docs/en/research/ai-forecasting.md).

Data: the median LOS series of each cell (``geoeyes.hazard.assess.load_cells``), irregular dates. A forecast is
the change of displacement from an origin date t0 to t0 + h, for a few horizons h (days).

Models, all evaluated the same way:

* ``last``    — no change (random walk): the floor any forecast must beat;
* ``linear``  — the cell's rate over its history up to t0, extrapolated;
* ``seasonal``— linear + annual sine fitted on the history (only with at least 1.5 years of history);
* ``gbm``     — one *global* gradient-boosting model for every cell and horizon (scikit-learn
  HistGradientBoostingRegressor, absolute-error loss), on features of the history up to t0: changes over the
  last 30 / 60 / 90 / 180 / 365 days, recent and full-history rates, acceleration, noise, day of year, horizon,
  and the rainfall of the previous months and the groundwater storage (GLDAS) when a hazard analysis gives
  them.

Evaluation: rolling origin. For each of ``n_origins`` cut-off dates, every model is fitted on what precedes the
cut-off only and scored on the changes after it (MAE per horizon, and the skill against the best baseline,
1 − MAE_model / MAE_baseline). The model used for the final forecast is the best one in that backtest — the global
model only when it beats the baselines.

Uncertainty: split-conformal intervals (Vovk et al. 2005): the absolute errors of the chosen model in the
backtest give, per horizon, the 80 % and 95 % half-widths; their coverage is reported. Series are not
exchangeable in time, so the coverage is checked, not assumed.
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

SCHEMA = "geoeyes.forecast/1"
DAY = 1.0
YEAR = 365.2425
LAGS = (30, 60, 90, 180, 365)
MODELS = ("last", "linear", "seasonal", "gbm")


@dataclass(frozen=True)
class ForecastParams:
    """``[postprocess.forecast]`` of project.toml (every key optional)."""

    cell_m: float = 100.0
    min_points: int = 3
    horizons_days: tuple[int, ...] = ()      # () = auto: 1/6, 1/3, 1/2 of the span (rounded to 10 days, ≤ 365)
    n_origins: int = 3                       # rolling-origin cut-offs of the backtest
    min_history_days: int = 90               # history needed before an origin
    max_samples: int = 400_000               # training rows (subsampled above)
    seed: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ForecastParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.forecast]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for f in fields(cls):
            if f.name in d:
                default = getattr(cls, f.name)
                v = d[f.name]
                out[f.name] = tuple(int(x) for x in v) if isinstance(default, tuple) else type(default)(v)
        return cls(**out)


def auto_horizons(span_days: float) -> tuple[int, ...]:
    hs = sorted({int(min(365, max(10, round(span_days * f / 10) * 10))) for f in (1 / 6, 1 / 3, 1 / 2)})
    return tuple(hs)


# ---------------------------------------------------------------- series helpers
def _value_at(t: np.ndarray, y: np.ndarray, at: np.ndarray) -> np.ndarray:
    """``y`` (cells, T) linearly interpolated at days ``at`` (cells,) — NaN outside the dates."""
    out = np.full(at.shape, np.nan)
    i = np.searchsorted(t, at, side="right") - 1
    ok = (i >= 0) & (i < len(t) - 1)
    i0 = np.clip(i, 0, len(t) - 2)
    w = (at - t[i0]) / np.maximum(t[i0 + 1] - t[i0], 1e-9)
    rows = np.arange(len(at))
    v = y[rows, i0] * (1 - w) + y[rows, i0 + 1] * w
    out[ok] = v[ok]
    exact = np.isclose(at, t[-1])
    out[exact] = y[rows[exact], -1]
    return out


def _fit(t: np.ndarray, y: np.ndarray, seasonal: bool) -> np.ndarray:
    """Least-squares coefficients per row of ``y`` (cells, k) on [1, t(yr)(, sin, cos)]; rows with NaN -> NaN."""
    ty = t / YEAR
    cols = [np.ones_like(ty), ty]
    if seasonal:
        cols += [np.sin(2 * np.pi * ty), np.cos(2 * np.pi * ty)]
    a = np.column_stack(cols)
    coef = np.full((y.shape[0], a.shape[1]), np.nan)
    ok = np.all(np.isfinite(y), axis=1)
    if ok.any() and len(t) > a.shape[1]:
        coef[ok] = np.linalg.lstsq(a, y[ok].T, rcond=None)[0].T
    return coef


def _design(t: np.ndarray, seasonal: bool) -> np.ndarray:
    ty = np.asarray(t, float) / YEAR
    cols = [np.ones_like(ty), ty]
    if seasonal:
        cols += [np.sin(2 * np.pi * ty), np.cos(2 * np.pi * ty)]
    return np.column_stack(cols)


# ---------------------------------------------------------------- baselines
def baseline(name: str, t: np.ndarray, y: np.ndarray, t0: float, h: float) -> np.ndarray:
    """Change from t0 to t0 + h predicted by a baseline fitted on the dates up to t0 (cells,)."""
    hist = t <= t0 + 1e-9
    if name == "last":
        return np.zeros(y.shape[0])
    seasonal = name == "seasonal"
    if hist.sum() < (5 if seasonal else 3) or (seasonal and t0 - t[0] < 1.5 * YEAR):
        return np.full(y.shape[0], np.nan)          # an annual term needs 1.5 years of history
    coef = _fit(t[hist], y[:, hist], seasonal)
    a = _design(np.array([t0, t0 + h]), seasonal)
    pred = coef @ a.T
    return pred[:, 1] - pred[:, 0]


# ---------------------------------------------------------------- features of the global model
FEATURES = (*(f"d{lag}" for lag in LAGS), "rate_90", "rate_all", "acc", "noise", "doy_sin", "doy_cos", "h",
            "rain_1", "rain_3", "rain_6", "gws_anom", "gws_d3", "gws_d12", "span")


def features(t: np.ndarray, y: np.ndarray, t0: float, h: float, day0: np.datetime64,
             drivers: dict | None) -> np.ndarray:
    """(cells, len(FEATURES)) at origin t0 for horizon h; history only (dates ≤ t0)."""
    n = y.shape[0]
    hist = t <= t0 + 1e-9
    th, yh = t[hist], y[:, hist]
    at0 = np.full(n, t0)
    y0 = _value_at(th, yh, at0)
    cols = [y0 - _value_at(th, yh, np.full(n, t0 - lag)) for lag in LAGS]
    recent = th >= t0 - 90
    cols.append(_fit(th[recent], yh[:, recent], False)[:, 1] if recent.sum() >= 3 else np.full(n, np.nan))
    lin = _fit(th, yh, False)
    cols.append(lin[:, 1])
    if len(th) >= 6:
        q = np.column_stack([np.ones_like(th), th / YEAR, 0.5 * (th / YEAR) ** 2])
        ok = np.all(np.isfinite(yh), axis=1)
        acc = np.full(n, np.nan)
        if ok.any():
            acc[ok] = np.linalg.lstsq(q, yh[ok].T, rcond=None)[0][2]
        cols.append(acc)
        res = yh - (lin @ _design(th, False).T)
        cols.append(np.nanstd(res, axis=1))
    else:
        cols += [np.full(n, np.nan), np.full(n, np.nan)]
    doy = (day0 + np.timedelta64(int(round(t0)), "D")).astype("datetime64[D]")
    frac = (doy - doy.astype("datetime64[Y]")).astype(float) / YEAR
    cols += [np.full(n, np.sin(2 * np.pi * frac)), np.full(n, np.cos(2 * np.pi * frac)), np.full(n, float(h))]
    drivers = drivers or {}
    cols += _rain_features(drivers.get("rain"), day0, t0, n)
    cols += _gws_features(drivers.get("gws"), day0, t0, n)
    cols.append(np.full(n, t0 - th[0]))
    return np.column_stack(cols).astype(np.float32)


def _rain_features(rain, day0, t0, n) -> list[np.ndarray]:
    """Rainfall anomaly (mm, AOI mean) of the last 1 / 3 / 6 months before t0; NaN without rainfall."""
    if rain is None:
        return [np.full(n, np.nan)] * 3
    months, mm = rain
    end = (day0 + np.timedelta64(int(round(t0)), "D")).astype("datetime64[M]")
    keys = [str(end - k) for k in range(1, 7)]
    idx = {m: i for i, m in enumerate(months)}
    vals = np.array([mm[idx[k]] if k in idx else np.nan for k in keys])
    mean = np.nanmean(mm) if np.isfinite(mm).any() else np.nan
    a = vals - mean
    return [np.full(n, np.nanmean(a[:k])) if np.isfinite(a[:k]).any() else np.full(n, np.nan) for k in (1, 3, 6)]


def _gws_features(gws, day0, t0, n) -> list[np.ndarray]:
    """Groundwater storage (mm, AOI mean) of the last month published before t0 (GLDAS comes months late, so the
    same rule holds in training and at the forecast origin): its anomaly from the mean and its change over 3 and
    12 months; NaN without groundwater."""
    if gws is None:
        return [np.full(n, np.nan)] * 3
    months, mm = gws
    end = (day0 + np.timedelta64(int(round(t0)), "D")).astype("datetime64[M]")
    idx = {m: i for i, m in enumerate(months)}
    last = next((end - k for k in range(1, 13) if str(end - k) in idx and np.isfinite(mm[idx[str(end - k)]])), None)
    if last is None:
        return [np.full(n, np.nan)] * 3

    def at(k):
        i = idx.get(str(last - k))
        return mm[i] if i is not None else np.nan
    mean = np.nanmean(mm)
    s1 = at(0)
    return [np.full(n, s1 - mean), np.full(n, s1 - at(3)), np.full(n, s1 - at(12))]


def _samples(t, y, origins, horizons, day0, drivers, rng, max_rows, until: float):
    """Training rows (features, target change) for every origin and horizon whose target date is observed and
    not later than ``until`` (the backtest cut-off: nothing after it is seen in training)."""
    xs, ys = [], []
    for t0 in origins:
        for h in horizons:
            if t0 + h > min(t[-1], until) + 1e-9:
                continue
            target = _value_at(t, y, np.full(y.shape[0], t0 + h)) - _value_at(t, y, np.full(y.shape[0], t0))
            ok = np.isfinite(target)
            if ok.any():
                xs.append(features(t, y, t0, h, day0, drivers)[ok])
                ys.append(target[ok])
    if not xs:
        return np.zeros((0, len(FEATURES)), np.float32), np.zeros(0)
    x, yy = np.vstack(xs), np.concatenate(ys)
    if len(yy) > max_rows:
        keep = rng.choice(len(yy), max_rows, replace=False)
        x, yy = x[keep], yy[keep]
    return x, yy


def train_gbm(x: np.ndarray, y: np.ndarray, seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingRegressor
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                      min_samples_leaf=40, l2_regularization=1.0, early_stopping=True,
                                      validation_fraction=0.15, random_state=seed)
    return m.fit(x, y)


def _origins(t: np.ndarray, until: float, min_history: float) -> np.ndarray:
    """Training origins: the acquisition dates with enough history, up to ``until``."""
    return t[(t - t[0] >= min_history) & (t <= until + 1e-9)]


# ---------------------------------------------------------------- backtest and forecast
def backtest(t, y, horizons, params: ForecastParams, day0, drivers) -> dict:
    """Rolling-origin evaluation of every model; returns errors per model and horizon, and the cut-offs."""
    rng = np.random.default_rng(params.seed)
    hmax = max(horizons)
    last_cut = t[-1] - hmax
    step = max(hmax / 2, 10.0)
    cuts = [c for c in (last_cut - k * step for k in range(params.n_origins)) if c - t[0] >= params.min_history_days]
    if not cuts:
        raise DataError(f"series too short to backtest horizons {list(horizons)} days "
                        f"(span {t[-1] - t[0]:.0f} days, history ≥ {params.min_history_days} days)")
    errors: dict[str, dict[int, list[np.ndarray]]] = {m: {h: [] for h in horizons} for m in MODELS}
    # cut-offs from the latest back: errors[m][h][0] is the latest one (kept to check the interval coverage)
    for cut in cuts:
        x, yy = _samples(t, y, _origins(t, cut - min(horizons), params.min_history_days), horizons, day0, drivers, rng,
                         params.max_samples, until=cut)
        gbm = train_gbm(x, yy, params.seed) if len(yy) >= 200 else None
        for h in horizons:
            if cut + h > t[-1] + 1e-9:
                continue
            truth = _value_at(t, y, np.full(y.shape[0], cut + h)) - _value_at(t, y, np.full(y.shape[0], cut))
            for name in ("last", "linear", "seasonal"):
                errors[name][h].append(baseline(name, t, y, cut, h) - truth)
            if gbm is not None:
                errors["gbm"][h].append(gbm.predict(features(t, y, cut, h, day0, drivers)) - truth)
    return {"cuts": [float(c) for c in cuts], "errors": errors}


def _mae(e: list[np.ndarray]) -> float:
    v = np.concatenate(e) if e else np.array([])
    v = v[np.isfinite(v)]
    return float(np.mean(np.abs(v))) if v.size else float("nan")


def forecast(dates: np.ndarray, y: np.ndarray, params: ForecastParams, drivers=None, progress=None) -> dict:
    """Backtest, choose the model, then forecast every cell from the last date. ``y`` (cells, T) LOS mm."""
    say = progress or (lambda m: log.info("%s", m))
    dates = np.asarray(dates, dtype="datetime64[D]")
    day0 = dates[0]
    t = (dates - day0).astype(float)
    span = float(t[-1])
    horizons = tuple(params.horizons_days) or auto_horizons(span)
    say(f"horizons {list(horizons)} days, span {span:.0f} days, {y.shape[0]} cells")
    bt = backtest(t, y, horizons, params, day0, drivers)
    mae = {m: {h: _mae(bt["errors"][m][h]) for h in horizons} for m in MODELS}
    base_best = {h: min((mae[m][h] for m in ("last", "linear", "seasonal") if np.isfinite(mae[m][h])),
                        default=np.nan) for h in horizons}
    score = {m: float(np.nanmean([mae[m][h] / base_best[h] for h in horizons if np.isfinite(mae[m][h])]))
             if any(np.isfinite(mae[m][h]) for h in horizons) else np.inf for m in MODELS}
    chosen = min(score, key=lambda m: score[m])
    say("backtest MAE (mm): " + "; ".join(f"{m} " + ", ".join(f"{h}d {mae[m][h]:.2f}" for h in horizons)
                                           for m in MODELS) + f" -> {chosen}")

    # conformal half-widths from the chosen model's backtest errors; their coverage is checked on the latest
    # cut-off with widths calibrated on the earlier ones only (when there are two cut-offs or more)
    def half_widths(errs: list[np.ndarray]) -> dict[float, float]:
        e = np.abs(np.concatenate(errs)) if errs else np.array([])
        e = e[np.isfinite(e)]
        n = e.size
        return {lvl: float(np.quantile(e, min(1.0, np.ceil((n + 1) * lvl) / n))) if n else float("nan")
                for lvl in (0.8, 0.95)}

    widths = {h: half_widths(bt["errors"][chosen][h]) for h in horizons}
    coverage = {}
    for h in horizons:
        errs = bt["errors"][chosen][h]
        if len(errs) < 2:
            coverage[h] = {"0.8": None, "0.95": None}
            continue
        w = half_widths(errs[1:])
        e = np.abs(errs[0])
        e = e[np.isfinite(e)]
        coverage[h] = {str(lvl): float(np.mean(e <= w[lvl])) if e.size else None for lvl in (0.8, 0.95)}

    # final model on every origin, forecast from the last date
    rng = np.random.default_rng(params.seed)
    model = None
    if chosen == "gbm":
        x, yy = _samples(t, y, _origins(t, t[-1], params.min_history_days), horizons, day0, drivers, rng,
                         params.max_samples, until=t[-1])
        model = train_gbm(x, yy, params.seed)
    pred = {}
    for h in horizons:
        pred[h] = model.predict(features(t, y, t[-1], h, day0, drivers)) if model is not None else \
            baseline(chosen, t, y, t[-1], h)
    skill = {m: {h: (1 - mae[m][h] / base_best[h]) if np.isfinite(mae[m][h]) and base_best[h] > 0 else None
                 for h in horizons} for m in MODELS}
    return {"horizons": list(horizons), "chosen": chosen, "pred": pred, "widths": widths, "mae": mae,
            "skill": skill, "coverage": coverage, "cuts": bt["cuts"], "model": model, "last_date": str(dates[-1])}


# ---------------------------------------------------------------- product -> analysis
def run(product: Path, out: Path, params: ForecastParams, *, hazard_dir: Path | None = None, progress=None) -> dict:
    """Forecast of a product's cells into ``out`` (``analyses/forecast/<product_id>/``)."""
    from geoeyes.hazard.assess import load_cells
    say = progress or (lambda m: log.info("%s", m))
    say(f"cells of {params.cell_m:g} m")
    dates, cells = load_cells(product, params.cell_m, params.min_points)
    y = cells.series - cells.series[:, :1]                         # 0 at the first date
    drivers = {}
    for key, name in (("rain", "rain.npz"), ("gws", "groundwater.npz")):
        if hazard_dir is not None and (hazard_dir / name).exists():
            with np.load(hazard_dir / name) as z:
                months = [str(m) for m in z["months"]]
                flat = z["monthly"].reshape(len(months), -1)
                mm = np.array([np.nanmean(r) if np.isfinite(r).any() else np.nan for r in flat])
            drivers[key] = (months, mm)
            say(f"{'rainfall' if key == 'rain' else 'groundwater storage'} of the hazard analysis used as features")
    r = forecast(dates, y, params, drivers, progress=say)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for h in r["horizons"]:
        p = r["pred"][h]
        w80, w95 = r["widths"][h][0.8], r["widths"][h][0.95]
        rows.append(pd.DataFrame({"cell": np.arange(len(p), dtype=np.int32), "lon": cells.lon, "lat": cells.lat,
                                  "horizon_days": np.int16(h), "change_mm": p.astype(np.float32),
                                  "lo80": (p - w80).astype(np.float32), "hi80": (p + w80).astype(np.float32),
                                  "lo95": (p - w95).astype(np.float32), "hi95": (p + w95).astype(np.float32)}))
    pd.concat(rows).to_parquet(out / "forecast.parquet", index=False)
    np.save(out / "cells_ts.npy", y.astype(np.float32))
    if r["model"] is not None:
        import joblib
        joblib.dump(r["model"], out / "model.joblib")
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(params).items()},
        "dates": [str(d) for d in dates], "last_date": r["last_date"], "n_cells": int(len(cells.lon)),
        "horizons_days": r["horizons"], "chosen": r["chosen"], "features": list(FEATURES), "rain": "rain" in drivers,
        "groundwater": "gws" in drivers,
        "backtest": {"cuts_days": r["cuts"],
                     "mae_mm": {m: {str(h): _num(v) for h, v in r["mae"][m].items()} for m in MODELS},
                     "skill": {m: {str(h): _num(v) for h, v in r["skill"][m].items()} for m in MODELS},
                     "coverage": {str(h): v for h, v in r["coverage"].items()},
                     "interval_mm": {str(h): {str(k): _num(v) for k, v in w.items()} for h, w in r["widths"].items()}},
        "units": "LOS mm, + toward the satellite, change from the last date",
        "method": "docs/en/research/ai-forecasting.md",
    }
    atomic_write_json(out / "forecast.json", summary)
    m = Manifest(kind="forecast", id=product.name, engine=SCHEMA, inputs=[InputRef("product", str(product))],
                 params=summary["params"], metrics={"chosen": r["chosen"], "n_cells": summary["n_cells"]})
    files = ["forecast.parquet", "cells_ts.npy", "forecast.json"] + (["model.joblib"] if r["model"] is not None else [])
    m.add_outputs(out, files)
    m.write(out)
    say(f"done: {r['chosen']}")
    return summary


def _num(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 3)


def read_summary(folder: Path) -> dict | None:
    f = folder / "forecast.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
