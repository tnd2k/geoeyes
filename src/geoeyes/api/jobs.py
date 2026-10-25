"""Background ``geoeyes`` commands of the web app on one product (hazard zoning, GNSS comparison): started detached,
one at a time per project and kind, their log tailed by the page."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from geoeyes.api import service
from geoeyes.workspace import ProjectLayout, WorkspaceLayout


def _files(project: ProjectLayout, kind: str):
    return project.state_dir / f"web_{kind}.out", project.state_dir / f"web_{kind}.json"


def job(project: ProjectLayout, kind: str) -> dict:
    f = _files(project, kind)[1]
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def alive(pid: int | None, kind: str) -> bool:
    if not pid:
        return False
    import psutil
    try:
        p = psutil.Process(int(pid))
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE and kind in " ".join(p.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def state(project: ProjectLayout, kind: str, pid: str, done: bool) -> dict:
    """Running / failed state of the last job of ``kind`` on product ``pid``, and its log."""
    j = job(project, kind)
    mine = j.get("product") == pid
    running = mine and alive(j.get("pid"), kind)
    return {"running": running, "log": service._tail(_files(project, kind)[0], 30) if mine else [],
            "failed": mine and not running and not done and bool(j)}


def start(ws: WorkspaceLayout, name: str, kind: str, pid: str, overrides: dict) -> dict:
    """``geoeyes <kind> <name> --product <pid> [--set k=v ...]`` detached."""
    project = ws.project(name)
    j = job(project, kind)
    if alive(j.get("pid"), kind):
        return {"pid": j["pid"], "already": True}
    argv = [sys.executable, "-m", "geoeyes.cli.main", "--workspace", str(ws.root), kind, name, "--product", pid]
    for k, v in (overrides or {}).items():
        argv += ["--set", f"{k}={json.dumps(v)}"]
    log_file, job_file = _files(project, kind)
    proc = service._spawn(project, argv, log_file.name)
    job_file.write_text(json.dumps({"pid": proc, "product": pid, "overrides": overrides,
                                    "started": datetime.now(UTC).isoformat()}), encoding="utf-8")
    return {"pid": proc}


_RESULT = {"hazard": "hazard.json", "gnss": "comparison.json"}


def activity(ws: WorkspaceLayout) -> list[dict]:
    """The last background job of each kind in every project, with its state: ``running``, ``done`` (its result
    was written after it started) or ``failed`` (it ended without one). The web app notifies the transitions."""
    out = []
    for name in ws.list_projects():
        project = ws.project(name)
        for kind, result in _RESULT.items():
            j = job(project, kind)
            if not j:
                continue
            f = project.analysis(kind, j["product"]) / result
            started = datetime.fromisoformat(j["started"])
            finished = datetime.fromtimestamp(f.stat().st_mtime, UTC) if f.exists() else None
            state = "running" if alive(j.get("pid"), kind) else \
                "done" if finished and finished >= started else "failed"
            out.append({"project": name, "kind": kind, "product": j["product"], "started": j["started"],
                        "finished": finished.isoformat(timespec="seconds") if finished and state == "done" else None,
                        "state": state})
    return out
