"""Hazard zoning in the web app (page "Thematic analysis", route #/hazard): ``geoeyes hazard`` started in the
background, its cells for the map (binary), and one cell in detail (series in the motion direction, rainfall and
groundwater storage of its pixels, fitted models).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.api import jobs
from geoeyes.hazard import coupling
from geoeyes.hazard.assess import read_cells, up_positive
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

# per cell in cells.bin (float32): position relative to the origin, then the attributes the map colours by
FIELDS = ("dlon", "dlat", "hazard", "intensity", "secondary", "mode", "rate_mm_yr", "rain_r", "rain_lag_months",
          "rain_coupled", "angular_distortion", "slope_deg", "rain_k_mm_per_100mm", "accelerating", "n_points",
          "intensity_observed", "rain_q", "gw_r", "gw_lag_months", "gw_coupled", "gw_k_mm_per_100mm")


def folder(project: ProjectLayout, pid: str) -> Path:
    return project.analysis("hazard", pid)


def status(project: ProjectLayout, pid: str) -> dict:
    """Summary of the last zoning of the product (None if never run), and the background job if one runs."""
    d = folder(project, pid)
    summary = json.loads((d / "hazard.json").read_text(encoding="utf-8")) if (d / "hazard.json").exists() else None
    return {"summary": summary, **jobs.state(project, "hazard", pid, summary is not None)}


def start(ws: WorkspaceLayout, name: str, pid: str, overrides: dict) -> dict:
    _load.cache_clear()
    return jobs.start(ws, name, "hazard", pid, overrides)


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> tuple[pd.DataFrame, np.ndarray, dict, dict, dict | None]:
    d = Path(path)
    summary = json.loads((d / "hazard.json").read_text(encoding="utf-8"))
    cells = read_cells(d, summary)            # GeoEyes sign, also for analyses made before it
    ts = np.load(d / "cells_ts.npy")          # read whole (a few MB): a memory map would block "Run again" on Windows
    if not up_positive(summary):
        ts = -ts
    with np.load(d / "rain.npz") as z:
        rain = {k: z[k] for k in z.files}
    gw = None
    if (d / "groundwater.npz").exists():
        with np.load(d / "groundwater.npz") as z:
            gw = {k: z[k] for k in z.files}
    return cells, ts, rain, summary, gw


def _data(project: ProjectLayout, pid: str):
    d = folder(project, pid)
    f = d / "hazard.json"
    if not f.exists():
        raise FileNotFoundError(f"no hazard zoning of {pid} yet")
    return _load(str(d), f.stat().st_mtime)


def cells_bin(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    cells, _, _, summary, _ = _data(project, pid)
    lon0 = float(np.round(cells["lon"].median(), 4))
    lat0 = float(np.round(cells["lat"].median(), 4))
    cols = {"dlon": cells["lon"] - lon0, "dlat": cells["lat"] - lat0,
            "mode": (cells["mode"] == "landslide").astype(np.float32)}
    empty = np.full(len(cells), np.nan)                 # analyses made before a field existed
    arr = np.column_stack([np.asarray(cols[f] if f in cols else cells.get(f, empty), np.float32) for f in FIELDS])
    meta = {"origin": [lon0, lat0], "fields": list(FIELDS), "n": len(cells), "cell_m": summary["params"]["cell_m"],
            "lat0": summary["lat0"]}
    return meta, arr.astype(np.float32).tobytes()


def cell(project: ProjectLayout, pid: str, i: int) -> dict:
    """One cell: its attributes, its series (motion direction), the linear, rainfall and groundwater models, the
    rainfall and the groundwater storage of its pixels."""
    cells, ts, rain, summary, gw = _data(project, pid)
    if not 0 <= i < len(cells):
        raise IndexError(f"cell {i} out of range (0..{len(cells) - 1})")
    row = cells.iloc[i]
    y = np.asarray(ts[i], np.float64)
    if np.isfinite(y).any():
        y = y - y[np.isfinite(y)][0]                  # zero at the first date (the fits below have an intercept)
    dates = np.array(summary["dates"], dtype="datetime64[D]")
    t_obs = (dates - dates[0]).astype(np.float64)
    months = [str(m) for m in rain["months"]]
    r, c = int(row["rain_row"]), int(row["rain_col"])
    monthly = rain["monthly"][:, r, c].astype(np.float64)
    t0 = np.datetime64(f"{months[0]}-01")
    crd = coupling.crd(monthly, coupling.month_bounds(months, t0))
    out = {k: _num(v) if isinstance(v, (float, np.floating, int, np.integer)) and not isinstance(v, bool) else
           (bool(v) if isinstance(v, (bool, np.bool_)) else str(v)) for k, v in row.items()}
    out["dates"] = summary["dates"]
    out["series_mm"] = [_num(v) for v in y]
    ok = np.isfinite(y)
    if ok.sum() >= 3:
        lin = np.polyfit(t_obs[ok] / coupling.DAYS_PER_YEAR, y[ok], 1)
        out["linear_mm"] = [_num(v) for v in np.polyval(lin, t_obs / coupling.DAYS_PER_YEAR)]
        lag = int(row["rain_lag_months"])
        if lag >= 0:
            cv = crd.at((dates - t0).astype(np.float64) - lag * coupling.DAYS_PER_MONTH)
            x = np.column_stack([np.ones_like(t_obs), t_obs / coupling.DAYS_PER_YEAR, cv])
            coef, *_ = np.linalg.lstsq(x[ok], y[ok], rcond=None)
            out["rain_model_mm"] = [_num(v) for v in x @ coef]
            out["crd_lagged_mm"] = [_num(v) for v in cv]
    pix = next((p for p in summary["rain"]["pixels"] if p["row"] == r and p["col"] == c), None)
    out["rain"] = {"months": months, "mm": [_num(v) for v in monthly], "crd_mm": [_num(v) for v in crd.values[1:]],
                   "pixel": pix, "source": summary["rain"]["source"]}
    if gw is not None and int(row.get("gw_row", -1)) >= 0:
        gmonths = [str(m) for m in gw["months"]]
        gr, gc = int(row["gw_row"]), int(row["gw_col"])
        storage = gw["monthly"][:, gr, gc].astype(np.float64)
        g0 = np.datetime64(f"{gmonths[0]}-01")
        s, _ = coupling.storage(storage, gmonths, g0)
        glag = int(row["gw_lag_months"])
        if glag >= 0 and ok.sum() >= 3 and s.values.size:
            sv = s.at((dates - g0).astype(np.float64) - glag * coupling.DAYS_PER_MONTH)
            x = np.column_stack([np.ones_like(t_obs), t_obs / coupling.DAYS_PER_YEAR, sv])
            coef, *_ = np.linalg.lstsq(x[ok], y[ok], rcond=None)
            out["gw_model_mm"] = [_num(v) for v in x @ coef]
        gpix = next((p for p in summary["groundwater"]["pixels"] if p["row"] == gr and p["col"] == gc), None)
        mean = np.nanmean(storage) if np.isfinite(storage).any() else np.nan
        out["groundwater"] = {"months": gmonths, "anomaly_mm": [_num(v - mean) for v in storage], "pixel": gpix,
                              "source": summary["groundwater"]["source"]}
    return out


def _num(x) -> float | None:
    x = float(x)
    return round(x, 6) if np.isfinite(x) else None
