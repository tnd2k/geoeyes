"""``geoeyes`` command line (ARCHITECTURE §15.1).

    geoeyes check  [<project>]                    environment and project configuration
    geoeyes plan   <project> [selection]           what ``run`` would do, nothing is run
    geoeyes run    <project> [selection] [--force PHASE ...]
    geoeyes status <project>                       phase status per track, last runs
    geoeyes report <project> [--product ID]        (re)build the PDF report of the latest / given product
    geoeyes cr-report <project> [--track ID]       corner reflector identification report (Sentinel-1)
    geoeyes catalog build | search [--bbox W,S,E,N] [--from D] [--to D] [--vel-below V]   products of the workspace
    geoeyes serve  [--port 8765] [--open]          web app on http://localhost:8765

``<project>`` is a project name in the workspace (``GEOEYES_WORKSPACE`` or ``--workspace``) or a path to a
``project.toml``. Selection: ``--track ID`` (repeatable), ``--from PHASE``, ``--to PHASE``, ``--only PHASE``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from geoeyes.core.errors import GeoEyesError


def _open(args):
    from geoeyes.config.loader import load
    from geoeyes.config.settings import load_settings
    from geoeyes.workspace import ProjectLayout, WorkspaceLayout
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
    p = Path(args.project)
    if p.suffix == ".toml" or p.is_file():
        project = ProjectLayout(p.resolve().parent)
        cfg = load(p)
    else:
        project = ws.project(args.project)
        cfg = load(project.config)
    return cfg, project, ws


def _selection(args) -> dict:
    return {"tracks": args.track or None, "from_": args.from_, "to": args.to,
            "only": [args.only] if args.only else None}


def cmd_check(args) -> int:
    import importlib

    from geoeyes.config.settings import load_settings
    ok = True

    def report(good: bool, what: str) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'ok' if good else 'FAIL'}] {what}")

    print("environment")
    for mod in ("numpy", "scipy", "xarray", "zarr", "h5py", "geopandas", "rasterio", "pydantic"):
        try:
            importlib.import_module(mod)
            report(True, mod)
        except Exception as exc:
            report(False, f"{mod}: {exc}")
    ws = Path(args.workspace) if args.workspace else load_settings().workspace
    report(Path(ws).expanduser().exists(), f"workspace {ws}")
    if args.project:
        try:
            cfg, project, wsl = _open(args)
        except GeoEyesError as exc:
            report(False, f"project configuration: {exc}")
            return 1
        print(f"project {cfg.project.name} ({cfg.project.method}, {len(cfg.tracks)} track(s))")
        report(True, "configuration valid")
        from geoeyes.controller.pipeline import plan
        p = plan(cfg, project, wsl, **_selection(args))
        for s in p.steps:
            if s.action == "blocked":
                report(False, f"{s.label}: {s.reason}")
        if str(cfg.atmosphere.method).lower() not in ("none", "linear", "a_l", "n", ""):
            m = str(cfg.atmosphere.method).lower()
            if "era5" in m or m in ("a_e", "a_eh", "a_ew"):
                report((Path.home() / ".cdsapirc").exists(), "~/.cdsapirc (Copernicus CDS key for ERA5)")
            if "gacos" in m:
                d = dict(cfg.atmosphere.gacos).get("dir")
                report(bool(d) and Path(d).exists(), f"[atmosphere.gacos] dir {d!r}")
    print("all checks passed" if ok else "some checks failed")
    return 0 if ok else 1


def cmd_plan(args) -> int:
    from geoeyes.controller.pipeline import plan
    cfg, project, ws = _open(args)
    p = plan(cfg, project, ws, force=tuple(args.force or ()), **_selection(args))
    print(f"project {cfg.project.name}: {len(p.to_run())} phase(s) to run")
    print(p)
    return 1 if any(s.action == "blocked" for s in p.steps) else 0


def cmd_run(args) -> int:
    from geoeyes.controller.pipeline import run
    cfg, project, ws = _open(args)
    res = run(cfg, project, ws, force=tuple(args.force or ()), log_level=args.log_level, **_selection(args))
    print(json.dumps({k: res[k] for k in ("run_id", "status", "run_dir")}, indent=1))
    return 0 if res["status"] == "ok" else 1


def cmd_status(args) -> int:
    from geoeyes.controller.phase import ProjectState
    from geoeyes.workspace.lock import list_locks
    cfg, project, _ = _open(args)
    data = ProjectState(project).load()["phases"]
    print(f"project {cfg.project.name}")
    for key in sorted(data):
        r = data[key]
        extra = f"  {r['seconds']} s" if "seconds" in r else (f"  {r['error']}" if "error" in r else "")
        print(f"  {key:<40} {r.get('status', '?'):<8} run {r.get('run_id', '')}  {r.get('updated', '')}{extra}")
    runs = sorted(project.root.joinpath("runs").glob("*/manifest.json"))[-5:]
    if runs:
        print("last runs")
        for m in runs:
            d = json.loads(m.read_text(encoding="utf-8"))
            phases = ", ".join("{track}/{phase}:{status}".format(**p_) for p_ in d.get("phases", []))
            print(f"  {d['id']}  {d.get('metrics', {}).get('status', '?')}  {phases}")
    for lk in list_locks(project.locks):
        print(f"  lock {Path(lk['lock_path']).name}: PID {lk.get('pid')} {'running' if lk['alive'] else 'stale'}")
    return 0


def cmd_report(args) -> int:
    """(Re)build the PDF report of a product: ``--product ID``, else the latest product of each track."""
    import logging

    from geoeyes.controller.phase import ProjectState
    from geoeyes.report import build_report
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg, project, _ = _open(args)
    if args.product:
        ids = [args.product]
    else:
        state = ProjectState(project)
        ids = [((state.get(t.track_id, "build_product") or {}).get("result") or {}).get("product_id")
               for t in cfg.tracks if not args.track or t.track_id in args.track]
        ids = [i for i in ids if i]
    if not ids:
        print("no product yet: run the project first (geoeyes run)", file=sys.stderr)
        return 1
    for pid in ids:
        print(build_report(project.product(pid), copy_to=cfg.report.copy_to))
    return 0


def cmd_cr_report(args) -> int:
    """Corner reflector identification report from the project's Sentinel-1 bursts."""
    import logging

    from geoeyes.validation.corner_reflector import build_cr_report
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg, project, ws = _open(args)
    for r in build_cr_report(cfg, project, ws, tracks=args.track, pdf=not args.no_pdf):
        s = r["summary"]
        print(f"{s['track']}: {s['observations']} observation(s), {s['within_tolerance']} within tolerance -> "
              f"{r.get('pdf', r['dir'])}")
    return 0


def cmd_hazard(args) -> int:
    """Hazard zoning with rainfall of a product (``--product``, else the latest product of each track)."""
    import logging

    from geoeyes.hazard import run_hazard
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg, project, ws = _open(args)
    ids = _product_ids(args, cfg, project)
    if not ids:
        print("no product yet: run the project first (geoeyes run)", file=sys.stderr)
        return 1
    overrides = _overrides(args.set)
    for pid in ids:
        s = run_hazard(cfg, project, ws, pid, overrides, progress=lambda msg: print(msg, flush=True))
        levels = {m: {k: v["cells"] for k, v in d.items() if isinstance(v, dict) and v["cells"]}
                  for m, d in s["by_level"].items()}
        print(f"{pid}: {s['n_cells']} cells, rainfall coupling significant in "
              f"{s['coupling']['cells_significant']}; {levels} -> {project.analysis('hazard', pid)}")
    return 0


def cmd_gnss(args) -> int:
    """InSAR against the NGL GNSS stations of a product, and the GNSS calibration (``--product``, else the latest
    product of each track)."""
    import logging

    from geoeyes.validation.gnss import run_gnss
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg, project, ws = _open(args)
    ids = _product_ids(args, cfg, project)
    if not ids:
        print("no product yet: run the project first (geoeyes run)", file=sys.stderr)
        return 1
    for pid in ids:
        s = run_gnss(cfg, project, ws, pid, _overrides(args.set), progress=lambda msg: print(msg, flush=True))
        used = [st["site"] for st in s["stations"] if st["used"]]
        c = s["calibration"] or {}
        print(f"{pid}: {len(s['stations'])} NGL station(s), compared {used or 'none'}"
              + (f"; {c['kind']} calibration {c['rate_offset_mm_yr']:+.2f} mm/yr" if c else "")
              + f" -> {project.analysis('gnss', pid)}")
        for w in s["warnings"]:
            print(f"  warning: {w}")
    return 0


def _product_ids(args, cfg, project) -> list[str]:
    """``--product``, else the latest product of each (selected) track."""
    from geoeyes.controller.phase import ProjectState
    if args.product:
        return [args.product]
    state = ProjectState(project)
    ids = [((state.get(t.track_id, "build_product") or {}).get("result") or {}).get("product_id")
           for t in cfg.tracks if not args.track or t.track_id in args.track]
    return [i for i in ids if i]


def _overrides(pairs) -> dict:
    """``KEY=VALUE`` pairs, values read as JSON when they parse."""
    out = {}
    for kv in pairs or []:
        key, _, value = kv.partition("=")
        try:
            out[key.strip()] = json.loads(value)
        except json.JSONDecodeError:
            out[key.strip()] = value
    return out


def cmd_catalog(args) -> int:
    """Workspace catalog: ``build`` (STAC + DuckDB index) or ``search``."""
    from geoeyes.catalog import build_catalog, search
    from geoeyes.config.settings import load_settings
    from geoeyes.workspace import WorkspaceLayout
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
    if args.action == "build":
        s = build_catalog(ws)
        print(f"{s['products']} product(s) of {s['projects']} project(s) -> {s['path']}")
        return 0
    bbox = [float(v) for v in args.bbox.split(",")] if args.bbox else None
    rows = search(ws, bbox=bbox, start=args.start, end=args.end, sensor=args.sensor, project=args.project_name,
                  latest_only=not args.all, vel_below=args.vel_below, vel_above=args.vel_above)
    for r in rows:
        a = r.get("in_area")
        extra = (f"  {a['n']} pts in area, {a['vel_min']:.1f}..{a['vel_max']:.1f} mm/yr"
                 + (f", {a['n_below']} <= {args.vel_below}" if "n_below" in a else "")
                 + (f", {a['n_above']} >= {args.vel_above}" if "n_above" in a else "")) if a else ""
        print(f"{r['id']}  {r['sensor']}  {r['first_date']}..{r['last_date']}{'' if r['latest'] else '  (old)'}{extra}")
    if not rows:
        print("no product")
    return 0


def cmd_serve(args) -> int:
    """Web app: API + front end on one port (local only unless ``--host`` says otherwise)."""
    from geoeyes.api import serve
    from geoeyes.config.settings import load_settings
    from geoeyes.workspace import WorkspaceLayout
    s = load_settings()
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else s.workspace_layout()
    serve(ws, host=args.host, port=args.port, open_browser=args.open, token=s.web_token or None)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="geoeyes", description="GeoEyes InSAR processing")
    ap.add_argument("--workspace", help="workspace root (default: GEOEYES_WORKSPACE)")
    sub = ap.add_subparsers(dest="command", required=True)

    def add(name, fn, project_required=True, selection=True, help_=""):
        p = sub.add_parser(name, help=help_)
        p.add_argument("project", nargs=None if project_required else "?")
        if selection:
            p.add_argument("--track", action="append", help="track id (repeatable)")
            p.add_argument("--from", dest="from_", metavar="PHASE")
            p.add_argument("--to", metavar="PHASE")
            p.add_argument("--only", metavar="PHASE")
        p.set_defaults(func=fn)
        return p

    add("check", cmd_check, project_required=False, help_="check the environment and a project")
    add("plan", cmd_plan, help_="show what run would do").add_argument("--force", action="append", metavar="PHASE")
    r = add("run", cmd_run, help_="run the project")
    r.add_argument("--force", action="append", metavar="PHASE", help="run this phase even when up to date")
    r.add_argument("--log-level", default="INFO")
    add("status", cmd_status, selection=False, help_="phase status and last runs")
    rp = add("report", cmd_report, selection=False, help_="build the PDF report of a product")
    rp.add_argument("--product", help="product id (default: the latest product of each track)")
    rp.add_argument("--track", action="append", help="track id (repeatable)")
    cr = add("cr-report", cmd_cr_report, selection=False, help_="corner reflector identification report (S1)")
    cr.add_argument("--track", action="append", help="track id (repeatable)")
    cr.add_argument("--no-pdf", action="store_true", help="JSON, CSV and figures only")
    hz = add("hazard", cmd_hazard, selection=False, help_="hazard zoning of a product with rainfall (CHIRPS)")
    hz.add_argument("--product", help="product id (default: the latest product of each track)")
    hz.add_argument("--track", action="append", help="track id (repeatable)")
    hz.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override a [postprocess.hazard] parameter, e.g. --set cell_m=50 (repeatable)")
    gn = add("gnss", cmd_gnss, selection=False, help_="compare a product with the NGL GNSS stations; GNSS calibration")
    gn.add_argument("--product", help="product id (default: the latest product of each track)")
    gn.add_argument("--track", action="append", help="track id (repeatable)")
    gn.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override a [validation.gnss] parameter, e.g. --set radius_m=200 (repeatable)")
    ca = sub.add_parser("catalog", help="workspace catalog: build, search")
    ca.add_argument("action", choices=["build", "search"])
    ca.add_argument("--bbox", help="west,south,east,north")
    ca.add_argument("--from", dest="start", metavar="YYYY-MM-DD")
    ca.add_argument("--to", dest="end", metavar="YYYY-MM-DD")
    ca.add_argument("--sensor")
    ca.add_argument("--project", dest="project_name")
    ca.add_argument("--all", action="store_true", help="every product version, not only the latest per track")
    ca.add_argument("--vel-below", type=float, help="count points at or below this velocity (mm/yr) in the bbox")
    ca.add_argument("--vel-above", type=float, help="count points at or above this velocity (mm/yr) in the bbox")
    ca.set_defaults(func=cmd_catalog)
    sv = sub.add_parser("serve", help="web app (API and front end on one port)")
    sv.add_argument("--host", default="127.0.0.1", help="listen address (default: this machine only)")
    sv.add_argument("--port", type=int, default=8765, help="port (default 8765; never Vite's 5173)")
    sv.add_argument("--open", action="store_true", help="open the browser")
    sv.set_defaults(func=cmd_serve)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except GeoEyesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
