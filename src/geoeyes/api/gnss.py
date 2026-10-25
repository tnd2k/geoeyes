"""GNSS comparison in the web app (project page, Validation): ``geoeyes gnss`` started in the background, its
summary, and one station's series (InSAR around the antenna, GNSS in the line of sight, daily and per epoch).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from geoeyes.api import jobs
from geoeyes.workspace import ProjectLayout, WorkspaceLayout


def folder(project: ProjectLayout, pid: str) -> Path:
    return project.analysis("gnss", pid)


def status(project: ProjectLayout, pid: str) -> dict:
    f = folder(project, pid) / "comparison.json"
    summary = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return {"summary": summary, **jobs.state(project, "gnss", pid, summary is not None)}


def start(ws: WorkspaceLayout, name: str, pid: str, overrides: dict) -> dict:
    return jobs.start(ws, name, "gnss", pid, overrides)


def station(project: ProjectLayout, pid: str, site: str) -> dict:
    """One compared station: the InSAR median around it and the GNSS in the line of sight (both modes), both zero
    at their first shared date, plus the daily GNSS on the same zero."""
    d = folder(project, pid)
    summary = json.loads((d / "comparison.json").read_text(encoding="utf-8"))
    st = next((s for s in summary["stations"] if s["site"] == site and s["used"]), None)
    if st is None:
        raise FileNotFoundError(f"{site}: not compared in {pid}")
    with np.load(d / "series.npz") as z:
        a = {k.split("__", 1)[1]: z[k] for k in z.files if k.startswith(f"{site}__")}
        dates = [str(v) for v in z["dates"]]
    insar = a["insar"].astype(np.float64)
    out = {"site": site, "dates": dates, "spread_mm": _list(a["spread"]), "station": st}
    los = np.asarray(st["los"])
    day = a["day"].astype("datetime64[D]")
    for mode in ("vertical", "full"):
        g = a[f"gnss_{mode}"].astype(np.float64)
        ok = np.isfinite(g) & np.isfinite(insar)
        # both zero at their first shared date (the statistics align them on their means instead)
        k0 = int(np.argmax(ok))
        gi, ii = g[k0], insar[k0]
        daily = a["enu_mm"] @ los if mode == "full" else a["enu_mm"][:, 2] * los[2]
        # the epoch values are means of the daily positions: the same offset puts the daily series on that zero
        out[mode] = {"gnss_mm": _list(g - gi), "daily_mm": _list(daily - gi)}
        out[f"insar_{mode}_mm"] = _list(insar - ii)
    out["day"] = [str(v) for v in day]
    return out


def _list(a) -> list[float | None]:
    return [round(float(v), 2) if np.isfinite(v) else None for v in np.asarray(a, np.float64)]
