"""Weather models in the web app (project page, Atmosphere tab): the models covering a product, ``geoeyes
atmosphere`` started in the background, its summary and its maps (one layer of one interferogram at a time)."""
from __future__ import annotations

import json
from datetime import date

import numpy as np

from geoeyes.api import jobs
from geoeyes.workspace import ProjectLayout, WorkspaceLayout


def status(project: ProjectLayout, pid: str) -> dict:
    """The last comparison (None before the first) and, always, the models covering the product."""
    from geoeyes.config.loader import load
    from geoeyes.processing.atmosphere import cerra
    from geoeyes.processing.atmosphere.models import catalogue
    from geoeyes.validation.atmosphere import read_summary
    summary = read_summary(project.analysis("atmosphere", pid))
    item = json.loads((project.product(pid) / "item.json").read_text(encoding="utf-8"))
    w, s, e, n = item["bbox"][:4]
    props = item["properties"]
    dates = [date.fromisoformat(props["geoeyes:first_date"]), date.fromisoformat(props["geoeyes:last_date"])]
    return {"summary": summary, "bbox": [w, s, e, n], "current_method": str(load(project.config).atmosphere.method),
            "catalogue": catalogue([w, e, w, e], [s, s, n, n], dates),
            "outlines": {"cerra": cerra.outline()}, **jobs.state(project, "atmosphere", pid, summary is not None)}


def start(ws: WorkspaceLayout, name: str, pid: str, overrides: dict) -> dict:
    return jobs.start(ws, name, "atmosphere", pid, overrides)


def grid(project: ProjectLayout, pid: str, layer: str, k: int) -> tuple[dict, bytes]:
    """Layer ``obs`` | ``aps:<model>`` | ``res:<model>`` of interferogram ``k``: (meta, float32 row-major, north up)."""
    folder = project.analysis("atmosphere", pid)
    f = folder / "grids.npz"
    if not f.exists():
        raise FileNotFoundError(f"{pid}: no atmosphere comparison yet")
    summary = json.loads((folder / "atmosphere.json").read_text(encoding="utf-8"))
    with np.load(f) as z:
        key = layer.replace(":", "__")
        if key not in z.files:
            raise FileNotFoundError(f"{layer}: not in the comparison ({', '.join(summary['grid']['layers'])})")
        a = z[key]
    if not 0 <= k < a.shape[0]:
        raise FileNotFoundError(f"interferogram {k}: 0..{a.shape[0] - 1}")
    g = np.ascontiguousarray(a[k], np.float32)
    ok = np.isfinite(g)
    meta = {"layer": layer, "k": k, "date": summary["ifg_dates"][k], "size": int(g.shape[0]),
            "bounds": summary["grid"]["bounds"], "min": float(g[ok].min()) if ok.any() else 0.0,
            "max": float(g[ok].max()) if ok.any() else 0.0, "unit": "mm"}
    return meta, g.tobytes()
