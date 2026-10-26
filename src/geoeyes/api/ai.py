"""Machine learning in the web app (page "Machine learning research", route #/ai): susceptibility from thematic
layers and deformation forecast — background runs, their summaries, the grids for the map (binary) and one cell's
forecast.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.api import jobs
from geoeyes.hazard.assess import SIGN
from geoeyes.ml.layers import LAYERS
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

TASKS = {"susceptibility": "susceptibility.json", "forecast": "forecast.json"}
SUSC_FIELDS = ("dlon", "dlat", "probability", "class", "label", "rate_mm_yr", "outside", "p_logistic",
               "p_random_forest", "p_gradient_boosting", *LAYERS)


def _summary(project: ProjectLayout, task: str, pid: str) -> dict | None:
    f = project.analysis(task, pid) / TASKS[task]
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def status(project: ProjectLayout, pid: str) -> dict:
    out = {}
    for task in TASKS:
        s = _summary(project, task, pid)
        out[task] = {"summary": s, **jobs.state(project, task, pid, s is not None)}
    out["hazard"] = (project.analysis("hazard", pid) / "hazard.json").exists()
    return out


def start(ws: WorkspaceLayout, name: str, task: str, pid: str, overrides: dict) -> dict:
    _grid.cache_clear()
    _forecast.cache_clear()
    return jobs.start(ws, name, task, pid, overrides)


@lru_cache(maxsize=4)
def _grid(path: str, mtime: float) -> tuple[dict, bytes]:
    t = pd.read_parquet(Path(path) / "grid.parquet")
    s = json.loads((Path(path) / "susceptibility.json").read_text(encoding="utf-8"))
    if s.get("sign") != SIGN:                     # made before the GeoEyes sign: InSAR rates were sinking > 0
        t["rate_mm_yr"] = -t["rate_mm_yr"]
    lon0, lat0 = float(np.round(t["lon"].median(), 4)), float(np.round(t["lat"].median(), 4))
    cols = {"dlon": t["lon"] - lon0, "dlat": t["lat"] - lat0}
    empty = np.full(len(t), np.nan)
    arr = np.column_stack([np.asarray(cols[f] if f in cols else t.get(f, empty), np.float32) for f in SUSC_FIELDS])
    stats = {c: {"min": _num(np.nanmin(t[c])), "max": _num(np.nanmax(t[c])), "p02": _num(np.nanpercentile(t[c], 2)),
                 "p98": _num(np.nanpercentile(t[c], 98))} for c in LAYERS if c in t and t[c].notna().any()}
    meta = {"origin": [lon0, lat0], "fields": list(SUSC_FIELDS), "n": len(t), "cell_m": s["grid"]["cell_m"],
            "lat0": s["grid"]["lat0"], "stats": stats}
    return meta, arr.astype(np.float32).tobytes()


def susceptibility_grid(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    d = project.analysis("susceptibility", pid)
    f = d / "susceptibility.json"
    if not f.exists():
        raise FileNotFoundError(f"no susceptibility analysis of {pid} yet")
    return _grid(str(d), f.stat().st_mtime)


@lru_cache(maxsize=4)
def _forecast(path: str, mtime: float) -> tuple[pd.DataFrame, np.ndarray, dict]:
    d = Path(path)
    return (pd.read_parquet(d / "forecast.parquet"), np.load(d / "cells_ts.npy"),
            json.loads((d / "forecast.json").read_text(encoding="utf-8")))


def _forecast_data(project: ProjectLayout, pid: str):
    d = project.analysis("forecast", pid)
    f = d / "forecast.json"
    if not f.exists():
        raise FileNotFoundError(f"no forecast of {pid} yet")
    return _forecast(str(d), f.stat().st_mtime)


def forecast_cells(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Per cell: position, then for each horizon the median change and the 80 % bounds (float32)."""
    t, _, s = _forecast_data(project, pid)
    hs = s["horizons_days"]
    first = t[t["horizon_days"] == hs[0]].sort_values("cell")
    lon0, lat0 = float(np.round(first["lon"].median(), 4)), float(np.round(first["lat"].median(), 4))
    cols = [first["lon"].to_numpy() - lon0, first["lat"].to_numpy() - lat0]
    fields = ["dlon", "dlat"]
    for h in hs:
        r = t[t["horizon_days"] == h].sort_values("cell")
        cols += [r["change_mm"].to_numpy(), r["lo80"].to_numpy(), r["hi80"].to_numpy()]
        fields += [f"c{h}", f"l{h}", f"u{h}"]
    arr = np.column_stack(cols).astype(np.float32)
    meta = {"origin": [lon0, lat0], "fields": fields, "n": len(first), "cell_m": s["params"]["cell_m"],
            "horizons": hs}
    return meta, arr.tobytes()


def forecast_cell(project: ProjectLayout, pid: str, i: int) -> dict:
    t, ts, s = _forecast_data(project, pid)
    if not 0 <= i < ts.shape[0]:
        raise IndexError(f"cell {i} out of range")
    last = np.datetime64(s["last_date"])
    y = ts[i].astype(np.float64)
    rows = t[t["cell"] == i].sort_values("horizon_days")
    base = float(y[np.isfinite(y)][-1]) if np.isfinite(y).any() else 0.0
    fc = [{"date": str(last + np.timedelta64(int(r.horizon_days), "D")), "horizon_days": int(r.horizon_days),
           **{k: _num(base + float(getattr(r, k))) for k in ("change_mm", "lo80", "hi80", "lo95", "hi95")}}
          for r in rows.itertuples()]
    return {"cell": i, "lon": _num(rows["lon"].iloc[0]) if len(rows) else None,
            "lat": _num(rows["lat"].iloc[0]) if len(rows) else None, "dates": s["dates"],
            "series_mm": [_num(v) for v in y], "forecast": fc, "chosen": s["chosen"], "last_date": s["last_date"]}


def buildings_status(project: ProjectLayout, pid: str) -> dict:
    f = project.analysis("buildings", pid) / "buildings.json"
    s = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return {"summary": s, **jobs.state(project, "buildings", pid, s is not None)}


@lru_cache(maxsize=4)
def _buildings(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(Path(path) / "buildings.parquet")


def buildings_in(project: ProjectLayout, pid: str, bbox: list[float], limit: int = 60_000) -> dict:
    """Buildings with InSAR inside ``bbox``: their MVT ids and values, for the web app's feature state."""
    d = project.analysis("buildings", pid)
    f = d / "buildings.json"
    if not f.exists():
        raise FileNotFoundError(f"no building analysis of {pid} yet")
    t = _buildings(str(d), f.stat().st_mtime)
    w, s, e, n = bbox
    sub = t[(t.lon >= w) & (t.lon <= e) & (t.lat >= s) & (t.lat <= n)].head(limit)
    return {"fields": ["id", "v_vert", "n", "beta_10yr", "spread"],
            "rows": [[str(r.id), _num(r.v_vert), int(r.n), _num(r.beta_10yr), _num(r.spread)]
                     for r in sub.itertuples()], "truncated": len(sub) >= limit}


def _num(x) -> float | None:
    x = float(x)
    return round(x, 4) if np.isfinite(x) else None
