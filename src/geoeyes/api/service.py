"""What the web app shows, read from the workspace through the core (layouts, project state, run records, products).

Nothing here processes data: runs are ``geoeyes run`` subprocesses, so the server can restart without stopping
them, and their status comes back from the project lock and the run records like for the CLI.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from geoeyes.config.loader import load
from geoeyes.controller.phase import ProjectState
from geoeyes.core.errors import ConfigError, GeoEyesError, LockedError
from geoeyes.io.manifest import atomic_write_json
from geoeyes.workspace import ProjectLayout, WorkspaceLayout
from geoeyes.workspace.lock import list_locks

PHASES = ("acquire", "build_stack", "phase_linking", "ps", "build_product", "export", "report")
FOLDERS_FILE = ".folders.json"
WEB_RUN_LOG = "web_run.out"          # stdout/stderr of the last run started from the web app (.state/)
WEB_CR_LOG = "web_cr_report.out"     # same for the last corner reflector report


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- folders
def folders(ws: WorkspaceLayout) -> dict:
    """Folder tree ``{"folders": [{"name", "projects": [...], "folders": [...]}], "projects": [...]}``; projects in
    no folder are listed at the root, projects removed from disk are dropped."""
    data = _read(ws.projects / FOLDERS_FILE) or {"folders": [], "projects": []}
    present = set(ws.list_projects())
    seen: set[str] = set()

    def clean(node: dict) -> dict:
        names = [p for p in node.get("projects", []) if p in present and p not in seen]
        seen.update(names)
        return {"name": str(node.get("name", "Folder")), "projects": names,
                "folders": [clean(f) for f in node.get("folders", [])]}

    tree = [clean(f) for f in data.get("folders", [])]
    root = [p for p in data.get("projects", []) if p in present and p not in seen]
    seen.update(root)
    return {"folders": tree, "projects": root + sorted(present - seen)}


def save_folders(ws: WorkspaceLayout, data: dict) -> dict:
    def check(node: dict, depth: int = 0) -> dict:
        if depth > 8:
            raise ConfigError("folders nested too deep")
        name = str(node.get("name", "")).strip()
        if not name or len(name) > 80:
            raise ConfigError(f"invalid folder name {name!r}")
        return {"name": name, "projects": [str(p) for p in node.get("projects", [])],
                "folders": [check(f, depth + 1) for f in node.get("folders", [])]}

    clean = {"folders": [check(f) for f in data.get("folders", [])],
             "projects": [str(p) for p in data.get("projects", [])]}
    ws.projects.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ws.projects / FOLDERS_FILE, clean)
    return folders(ws)


# ---------------------------------------------------------------- projects
def _product_brief(project: ProjectLayout, pid: str | None) -> dict | None:
    if not pid:
        return None
    d = project.product(pid)
    man = _read(d / "manifest.json")
    if not man:
        return None
    m = man.get("metrics", {})
    rep = _read(d / "report.json")
    conf = rep.get("confidence", {})
    return {"id": pid, "version": pid.rsplit("_v", 1)[-1], "created": man.get("created"),
            "n_points": m.get("n_points"), "epochs": m.get("epochs"), "first": m.get("first_date"),
            "last": m.get("last_date"), "vel_min": m.get("vel_min_mm_yr"), "vel_max": m.get("vel_max_mm_yr"),
            "engine": m.get("engine"), "confidence": conf.get("level"), "issues": conf.get("issues", []),
            "report": (d / "report.pdf").exists()}


def _running(project: ProjectLayout) -> dict | None:
    alive = [lk for lk in list_locks(project.locks) if lk["alive"]]
    if not alive:
        return None
    runs = sorted(p.name for p in (project.root / "runs").glob("*") if p.is_dir())
    return {"pid": alive[0].get("pid"), "started": alive[0].get("started_at"),
            "run_id": runs[-1] if runs else None}


def project_summary(ws: WorkspaceLayout, name: str) -> dict:
    project = ws.project(name)
    try:
        cfg = load(project.config)
    except GeoEyesError as exc:
        return {"name": name, "status": "invalid", "error": str(exc), "tracks": []}
    states = ProjectState(project).load()["phases"]
    running = _running(project)
    tracks, worst = [], "new"
    rank = {"new": 0, "idle": 1, "done": 2, "interrupted": 3, "failed": 4, "running": 5}
    for tr in cfg.tracks:
        tid = tr.track_id
        phases = {}
        for ph in PHASES:
            rec = states.get(f"{tid}/{ph}")
            if rec:
                st = rec.get("status")
                if st == "running" and not running:
                    st = "interrupted"
                phases[ph] = {"status": st, "seconds": rec.get("seconds"), "updated": rec.get("updated"),
                              "run_id": rec.get("run_id"), "error": rec.get("error")}
        pid = ((states.get(f"{tid}/build_product") or {}).get("result") or {}).get("product_id")
        product = _product_brief(project, pid)
        sts = {p["status"] for p in phases.values()}
        status = ("running" if running and "running" in sts else "failed" if "failed" in sts else
                  "interrupted" if "interrupted" in sts else "done" if product else "idle" if phases else "new")
        tracks.append({"track_id": tid, "sensor": tr.sensor.value, "direction": tr.direction.value,
                       "relative_orbit": tr.relative_orbit, "subswaths": list(tr.subswaths), "phases": phases,
                       "product": product, "status": status})
        worst = max(worst, status, key=rank.__getitem__)
    if running:
        worst = "running"
    last = runs(project, limit=1)
    alerts = 0
    if dict(cfg.postprocess.alerts).get("rules"):
        from geoeyes.api import monitor
        for t in tracks:
            if t["product"]:
                with contextlib.suppress(Exception):           # a broken cache must not hide the project
                    alerts += sum(a["triggered"] for a in monitor.evaluate(
                        project, project.product(t["product"]["id"]), ws.cache_dir("web")))
    return {"name": name, "description": cfg.project.description, "method": cfg.project.method.value,
            "alerts": alerts,
            "last_run": last[0] if last else None,
            "bbox": list(cfg.aoi.bbox) if cfg.aoi.bbox else None, "status": worst, "running": running,
            "date_range": [str(d) for d in cfg.acquire.date_range] if cfg.acquire.date_range else None,
            "tracks": tracks}


def workspace_tree(ws: WorkspaceLayout) -> dict:
    return {"root": str(ws.root), "tree": folders(ws),
            "projects": {n: project_summary(ws, n) for n in ws.list_projects()}}


def runs(project: ProjectLayout, limit: int = 30) -> list[dict]:
    running = _running(project)
    out = []
    for d in sorted((project.root / "runs").glob("*"), reverse=True)[:limit]:
        if not d.is_dir():
            continue
        man = _read(d / "manifest.json")
        if man:
            phases = [{k: v for k, v in p.items() if k != "result"} for p in man.get("phases", [])]
            out.append({"id": d.name, "status": man.get("metrics", {}).get("status", "?"), "phases": phases,
                        "seconds": round(sum(p.get("seconds") or 0 for p in phases), 1),
                        "error": next((p.get("error") for p in phases if p.get("status") == "failed"), None)})
        else:
            live = running is not None and running.get("run_id") == d.name
            out.append({"id": d.name, "status": "running" if live else "interrupted", "phases": [],
                        "seconds": None, "error": None})
    return out


def project_detail(ws: WorkspaceLayout, name: str) -> dict:
    project = ws.project(name)
    if not project.config.exists():
        raise ConfigError(f"no project {name!r}")
    out = project_summary(ws, name)
    out["config_toml"] = project.config.read_text(encoding="utf-8")
    try:
        cfg = load(project.config)
        out["settings"] = _settings(project, cfg)
    except GeoEyesError:
        out["settings"] = []
    out["runs"] = runs(project)
    out["products"] = [b for b in (_product_brief(project, d.name) for d in
                                   sorted((project.root / "products").glob("*"), reverse=True)) if b]
    out["exports"] = {d.name: [f.name for f in sorted(d.iterdir()) if f.is_file()]
                      for d in sorted((project.root / "exports").glob("*")) if d.is_dir()}
    out["web_run_log"] = _tail(project.state_dir / WEB_RUN_LOG, 30)
    return out


def _settings(project: ProjectLayout, cfg) -> list[dict]:
    """Effective values of the main settings, marked as set in project.toml or coming from preset / defaults."""
    import tomllib
    raw = tomllib.loads(project.config.read_text(encoding="utf-8"))

    def own(*path) -> bool:
        node: Any = raw
        for k in path:
            if not isinstance(node, dict) or k not in node:
                return False
            node = node[k]
        return True

    ps = {**_ps_defaults(), **cfg.ps}
    rows = [
        (("aoi", "bbox"), cfg.aoi.bbox), (("project", "method"), cfg.project.method.value),
        (("acquire", "date_range"), cfg.acquire.date_range), (("acquire", "max_per_month"), cfg.acquire.max_per_month),
        (("network", "reference"), cfg.network.reference), (("stack", "dem"), cfg.stack.dem),
        (("stack", "incremental"), cfg.stack.incremental), (("selection", "da_threshold"), cfg.selection.da_threshold),
        (("phase_linking", "enabled"), cfg.phase_linking.enabled),
        (("phase_linking", "estimator"), cfg.phase_linking.estimator),
        (("phase_linking", "shp_test"), cfg.phase_linking.shp_test),
        (("atmosphere", "method"), cfg.atmosphere.method), (("ps", "unwrap_grid_size"), ps.get("unwrap_grid_size")),
        (("export", "formats"), cfg.export.formats),
    ]
    out = []
    for path, value in rows:
        if isinstance(value, (tuple, list)):
            value = ", ".join(str(v) for v in value)
        out.append({"key": ".".join(path), "value": "" if value is None else str(value), "own": own(*path)})
    return out


def _ps_defaults() -> dict:
    from geoeyes.processing.ps.params import DEFAULTS
    return dict(DEFAULTS)


def _tail(path: Path, n: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def run_log(project: ProjectLayout, run_id: str, after: int = 0, debug: bool = False) -> dict:
    """Records of ``runs/<id>/log.jsonl`` from line ``after`` on (the client polls with the returned ``next``)."""
    path = project.run(run_id) / "log.jsonl"
    lines: list[dict] = []
    nxt = after
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i < after:
                    continue
                if not line.endswith("\n"):
                    break                                # being written
                nxt = i + 1
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not debug and r.get("level") == "DEBUG":
                    continue
                lines.append({"ts": r.get("ts"), "level": r.get("level"), "phase": r.get("phase"),
                              "track": r.get("track"), "msg": r.get("msg"), "event": r.get("event")})
    except OSError:
        pass
    return {"run_id": run_id, "lines": lines[-2000:], "next": nxt}


# ---------------------------------------------------------------- plan / run
def plan(ws: WorkspaceLayout, name: str, force: list[str] | None = None) -> list[dict]:
    from geoeyes.controller.pipeline import plan as make_plan
    project = ws.project(name)
    cfg = load(project.config)
    p = make_plan(cfg, project, ws, force=tuple(force or ()))
    return [{"track": s.ctx.track_id, "phase": s.phase.name, "action": s.action, "reason": s.reason}
            for s in p.steps]


def start_run(ws: WorkspaceLayout, name: str, *, tracks=None, force=None, only=None) -> dict:
    """Start ``geoeyes run`` detached from the server; its output goes to ``.state/web_run.out``."""
    project = ws.project(name)
    load(project.config)                                 # invalid configuration: fail here, not in the subprocess
    if _running(project):
        raise LockedError(f"{name} is already running")
    argv = [sys.executable, "-m", "geoeyes.cli.main", "--workspace", str(ws.root), "run", name]
    for t in tracks or ():
        argv += ["--track", str(t)]
    for f in force or ():
        argv += ["--force", str(f)]
    if only:
        argv += ["--only", str(only)]
    return {"pid": _spawn(project, argv, WEB_RUN_LOG), "argv": argv[2:]}


def _spawn(project: ProjectLayout, argv: list[str], log_name: str) -> int:
    """Start a ``geoeyes`` command detached from the server (it survives a server restart)."""
    project.state_dir.mkdir(parents=True, exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    with (project.state_dir / log_name).open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                cwd=str(project.root), creationflags=flags, start_new_session=os.name != "nt")
    return proc.pid


def start_cr_report(ws: WorkspaceLayout, name: str) -> dict:
    """``geoeyes cr-report`` in the background (reads the archive only; no project lock)."""
    project = ws.project(name)
    cfg = load(project.config)
    if not dict(cfg.validation.corner_reflector).get("points"):
        raise ConfigError("[validation.corner_reflector] points (reflector CSV) is not set in project.toml")
    argv = [sys.executable, "-m", "geoeyes.cli.main", "--workspace", str(ws.root), "cr-report", name]
    return {"pid": _spawn(project, argv, WEB_CR_LOG)}


def stop_run(ws: WorkspaceLayout, name: str) -> dict:
    """Stop the running ``geoeyes run`` of a project (the process holding the project lock and its children)."""
    import psutil
    project = ws.project(name)
    run = _running(project)
    if not run:
        return {"stopped": False}
    try:
        proc = psutil.Process(int(run["pid"]))
        for p in [*proc.children(recursive=True), proc]:
            p.terminate()
        psutil.wait_procs([proc], timeout=10)
    except psutil.NoSuchProcess:
        pass
    return {"stopped": True, "pid": run["pid"]}
