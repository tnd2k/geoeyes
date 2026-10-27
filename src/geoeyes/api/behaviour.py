"""Kinds of motion and risk to buildings in the web app (page "Thematic analysis"): background runs, the classes of
the hazard cells (binary, same order as the cells), one cell's fitted model, the buildings (packed binary)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.api import jobs
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

SOURCES = ("none", "cell", "building")


def _summary(project: ProjectLayout, kind: str, pid: str) -> dict | None:
    f = project.analysis(kind, pid) / f"{kind}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def status(project: ProjectLayout, pid: str) -> dict:
    out = {}
    for kind in ("behaviour", "risk", "lines", "consolidation", "decompose", "geology"):
        s = _summary(project, kind, pid)
        out[kind] = {"summary": s, **jobs.state(project, kind, pid, s is not None)}
    out["buildings"] = (project.analysis("buildings", pid) / "buildings.json").exists()
    return out


def start(ws: WorkspaceLayout, name: str, kind: str, pid: str, overrides: dict) -> dict:
    _behaviour.cache_clear()
    _risk.cache_clear()
    _lines.cache_clear()
    _consolidation.cache_clear()
    _decompose.cache_clear()
    _geology.cache_clear()
    return jobs.start(ws, name, kind, pid, overrides)


@lru_cache(maxsize=4)
def _behaviour(path: str, mtime: float) -> tuple[pd.DataFrame, np.ndarray, dict]:
    d = Path(path)
    return (pd.read_parquet(d / "behaviour.parquet"), np.load(d / "behaviour_fit.npy"),
            json.loads((d / "behaviour.json").read_text(encoding="utf-8")))


def _behaviour_data(project: ProjectLayout, pid: str):
    d = project.analysis("behaviour", pid)
    f = d / "behaviour.json"
    if not f.exists():
        raise FileNotFoundError(f"no classification of the kinds of motion of {pid} yet")
    return _behaviour(str(d), f.stat().st_mtime)


def behaviour_cells(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Per hazard cell (same order): class index (−1 = not assessed) and the change date in days since the first
    date (−1 = none), float32."""
    t, _, s = _behaviour_data(project, pid)
    d0 = np.datetime64(s["dates"][0])
    change = np.where(t["change_date"] != "", (pd.to_datetime(t["change_date"].replace("", None)).to_numpy()
                                               .astype("datetime64[D]") - d0).astype("float64"), -1.0)
    arr = np.column_stack([t["class_id"].to_numpy(np.float32), np.nan_to_num(change, nan=-1).astype(np.float32)])
    meta = {"n": len(t), "fields": ["class", "change_day"], "classes": s["classes"], "first_date": s["dates"][0],
            "last_date": s["dates"][-1], "counts": s["counts"], "hazard_created": s.get("hazard_created")}
    return meta, arr.astype(np.float32).tobytes()


def behaviour_cell(project: ProjectLayout, pid: str, i: int) -> dict:
    t, fit, s = _behaviour_data(project, pid)
    if not 0 <= i < len(t):
        raise IndexError(f"cell {i} out of range")
    row = t.iloc[i]
    # the cell chart of the zoning starts the series at 0: the fitted model is shifted the same way
    from geoeyes.api.hazard import _data as hazard_data
    ts = hazard_data(project, pid)[1][i]
    first = ts[np.isfinite(ts)][0] if np.isfinite(ts).any() else 0.0
    fit = fit - first if np.ndim(fit) == 1 else fit[i] - first
    num = {k: (None if not np.isfinite(float(row[k])) else round(float(row[k]), 3))
           for k in ("rate_mm_yr", "rate_before_mm_yr", "rate_after_mm_yr", "acc_mm_yr2", "seasonal_amp_mm", "jump_mm",
                     "delta_bic")}
    return {"cell": i, "class": row["class"], "change_date": row["change_date"] or None, **num,
            "fit_mm": [None if not np.isfinite(v) else round(float(v), 2) for v in fit], "dates": s["dates"]}


@lru_cache(maxsize=3)
def _risk(path: str, mtime: float) -> tuple[pd.DataFrame, dict]:
    d = Path(path)
    return pd.read_parquet(d / "risk.parquet"), json.loads((d / "risk.json").read_text(encoding="utf-8"))


def _risk_data(project: ProjectLayout, pid: str):
    d = project.analysis("risk", pid)
    f = d / "risk.json"
    if not f.exists():
        raise FileNotFoundError(f"no building risk of {pid} yet")
    return _risk(str(d), f.stat().st_mtime)


def risk_buildings(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Every building, packed in 12 bytes: dlon, dlat (float32), risk + 1, hazard + 1, source, √area (uint8)."""
    t, s = _risk_data(project, pid)
    lon0, lat0 = float(np.round(t["lon"].median(), 4)), float(np.round(t["lat"].median(), 4))
    rec = np.zeros(len(t), dtype=[("dlon", "<f4"), ("dlat", "<f4"), ("risk", "u1"), ("hazard", "u1"),
                                  ("source", "u1"), ("side", "u1")])
    rec["dlon"] = t["lon"].to_numpy() - lon0
    rec["dlat"] = t["lat"].to_numpy() - lat0
    rec["risk"] = t["risk"].to_numpy().astype(np.int16) + 1
    rec["hazard"] = t["hazard"].to_numpy().astype(np.int16) + 1
    rec["source"] = pd.Categorical(t["source"], categories=SOURCES).codes.clip(0)
    rec["side"] = np.clip(np.sqrt(t["area_m2"].to_numpy()), 1, 255).astype(np.uint8)
    meta = {"origin": [lon0, lat0], "n": len(t), "record": 12, "sources": list(SOURCES), "levels": s["levels"],
            "by_risk": s["by_risk"], "by_source": s["by_source"], "warnings": s.get("warnings", [])}
    return meta, rec.tobytes()


def risk_building(project: ProjectLayout, pid: str, i: int) -> dict:
    t, _ = _risk_data(project, pid)
    if not 0 <= i < len(t):
        raise IndexError(f"building {i} out of range")
    row = t.iloc[i]
    out = {}
    for k, v in row.items():
        if isinstance(v, (bool, np.bool_)):
            out[k] = bool(v)
        elif isinstance(v, (int, np.integer)):
            out[k] = int(v)
        elif isinstance(v, (float, np.floating)):
            out[k] = None if not np.isfinite(v) else round(float(v), 4)
        else:
            out[k] = str(v)
    return out


# ---------------------------------------------------------------- linear infrastructure
@lru_cache(maxsize=3)
def _lines(path: str, mtime: float) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    d = Path(path)
    return (pd.read_parquet(d / "lines.parquet"), pd.read_parquet(d / "stations.parquet"),
            json.loads((d / "lines.json").read_text(encoding="utf-8")))


def _lines_data(project: ProjectLayout, pid: str):
    d = project.analysis("lines", pid)
    f = d / "lines.json"
    if not f.exists():
        raise FileNotFoundError(f"no infrastructure profiles of {pid} yet")
    return _lines(str(d), f.stat().st_mtime)


def line_segments(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Every station-to-station segment: lon1, lat1, lon2, lat2, β class (−1 = no data), line index (float32)."""
    lt, st, s = _lines_data(project, pid)
    same = st["line"].to_numpy()[1:] == st["line"].to_numpy()[:-1]
    a, b = st.iloc[:-1][same], st.iloc[1:][same]
    cls = np.where(np.isfinite(b["beta"].to_numpy()), b["beta_class"].to_numpy(), -1)
    arr = np.column_stack([a["lon"], a["lat"], b["lon"], b["lat"], cls, b["line"]]).astype(np.float32)
    kinds = lt.set_index("line")["kind"]
    meta = {"n": len(arr), "fields": ["lon1", "lat1", "lon2", "lat2", "beta_class", "line"],
            "kinds": {int(k): v for k, v in kinds.items()}, "by_kind": s["by_kind"], "hotspots": s["hotspots"]}
    return meta, arr.tobytes()


def line_profile(project: ProjectLayout, pid: str, line: int) -> dict:
    lt, st, s = _lines_data(project, pid)
    row = lt[lt["line"] == line]
    if row.empty:
        raise IndexError(f"line {line} not found")
    p = st[st["line"] == line]
    r = row.iloc[0]

    def num(x, d=3):
        return None if not np.isfinite(float(x)) else round(float(x), d)
    return {"line": int(line), "kind": r["kind"], "name": r["name"], "length_m": num(r["length_m"], 0),
            "covered_share": num(r["covered_share"]), "beta_max": num(r["beta_max"], 5),
            "loss_mm": num(r["loss_mm"], 1),
            "chainage_m": [num(x, 0) for x in p["chainage_m"]], "v_vert_mm_yr": [num(x, 2) for x in p["v_vert_mm_yr"]],
            "n_points": p["n_points"].astype(int).tolist(), "beta": [num(x, 5) for x in p["beta"]],
            "horizon_yr": s["params"]["horizon_yr"]}


# ---------------------------------------------------------------- consolidation
@lru_cache(maxsize=3)
def _consolidation(path: str, mtime: float) -> tuple[pd.DataFrame, dict]:
    d = Path(path)
    summary = json.loads((d / "consolidation.json").read_text(encoding="utf-8"))
    return pd.read_parquet(d / "consolidation.parquet"), summary


def _consolidation_data(project: ProjectLayout, pid: str):
    d = project.analysis("consolidation", pid)
    f = d / "consolidation.json"
    if not f.exists():
        raise FileNotFoundError(f"no consolidation analysis of {pid} yet")
    return _consolidation(str(d), f.stat().st_mtime)


def consolidation_cells(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Per hazard cell (same order): remaining settlement (mm, NaN = not consolidating), years to 90 %."""
    t, s = _consolidation_data(project, pid)
    arr = np.column_stack([t["remaining_mm"].to_numpy(np.float32), t["t90_from_now_yr"].to_numpy(np.float32)])
    return {"n": len(t), "fields": ["remaining_mm", "t90_from_now_yr"], "summary": s}, arr.astype(np.float32).tobytes()


def consolidation_cell(project: ProjectLayout, pid: str, i: int) -> dict:
    """One cell: its settlement, the fitted curve projected 5 years ahead, and the Asaoka construction."""
    from geoeyes.api.hazard import _data as hazard_data
    from geoeyes.ml.consolidation import YEAR, asaoka, curve
    t, s = _consolidation_data(project, pid)
    if not 0 <= i < len(t):
        raise IndexError(f"cell {i} out of range")
    row = t.iloc[i]
    ts = hazard_data(project, pid)[1][i].astype(np.float64)
    dates = np.array(s["dates"], dtype="datetime64[D]")
    td = (dates - dates[0]).astype(np.float64)
    settle = -(ts - ts[np.isfinite(ts)][0]) if np.isfinite(ts).any() else ts
    out = {"cell": i, "consolidating": bool(row["consolidating"]), "dates": s["dates"],
           "settlement_mm": [None if not np.isfinite(v) else round(float(v), 2) for v in settle]}
    for k in ("tau_yr", "settled_mm", "final_mm", "remaining_mm", "t90_from_now_yr", "delta_bic"):
        out[k] = None if not np.isfinite(float(row[k])) else round(float(row[k]), 3)
    if row["consolidating"]:
        future = np.arange(0.0, td[-1] / YEAR + 5.0 + 1e-9, 1 / 24)
        out["curve_t_yr"] = [round(float(x), 4) for x in future]
        out["curve_mm"] = [round(float(x), 2) for x in curve(row["c_mm"], row["A_mm"], row["tau_yr"], future)]
    ok = np.isfinite(settle)
    # about eight readings over the span, between one acquisition cycle and 60 days
    step = float(np.clip(round((td[-1] - td[0]) / 8), 12, 60))
    out["asaoka"] = asaoka(td[ok], settle[ok], step_days=step)
    return out


# ---------------------------------------------------------------- two geometries and soft soil
@lru_cache(maxsize=3)
def _decompose(path: str, mtime: float) -> tuple[pd.DataFrame, dict]:
    d = Path(path)
    return pd.read_parquet(d / "decompose.parquet"), json.loads((d / "decompose.json").read_text(encoding="utf-8"))


def _decompose_data(project: ProjectLayout, pid: str):
    d = project.analysis("decompose", pid)
    f = d / "decompose.json"
    if not f.exists():
        raise FileNotFoundError(f"no decomposition of {pid} yet")
    return _decompose(str(d), f.stat().st_mtime)


def decompose_cells(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Every cell of the decomposition: lon, lat, up, east, σ up, σ east, the vertical projection of each product
    (float32)."""
    t, s = _decompose_data(project, pid)
    k = len(s["products"])
    cols = ["lon", "lat", "up", "east", "sigma_up", "sigma_east"] + [f"vert_only_{i}" for i in range(k)]
    arr = np.column_stack([t[c].to_numpy(np.float64) for c in cols]).astype(np.float32)
    meta = {"n": len(t), "fields": cols, "dlon": s["grid"]["dlon"], "dlat": s["grid"]["dlat"], "summary": s}
    return meta, arr.tobytes()


@lru_cache(maxsize=3)
def _geology(path: str, mtime: float) -> tuple[pd.DataFrame, dict]:
    d = Path(path)
    return pd.read_parquet(d / "geology.parquet"), json.loads((d / "geology.json").read_text(encoding="utf-8"))


def geology_cells(project: ProjectLayout, pid: str) -> tuple[dict, bytes]:
    """Per hazard cell (same order): soft-soil thickness (m) and implied c_v (m²/yr, NaN if not consolidating)."""
    d = project.analysis("geology", pid)
    f = d / "geology.json"
    if not f.exists():
        raise FileNotFoundError(f"no soft-soil analysis of {pid} yet")
    t, s = _geology(str(d), f.stat().st_mtime)
    cv = t["cv_m2_yr"].to_numpy(np.float32) if "cv_m2_yr" in t else np.full(len(t), np.nan, np.float32)
    arr = np.column_stack([t["thickness_m"].to_numpy(np.float32), cv])
    return {"n": len(t), "fields": ["thickness_m", "cv_m2_yr"], "summary": s}, arr.astype(np.float32).tobytes()
