"""``geoeyes`` command line (ARCHITECTURE §15.1).

    geoeyes check  [<project>]                    environment and project configuration
    geoeyes plan   <project> [selection]           what ``run`` would do, nothing is run
    geoeyes run    <project> [selection] [--force PHASE ...]
    geoeyes status <project>                       phase status per track, last runs
    geoeyes report <project> [--product ID]        (re)build the PDF report of the latest / given product
    geoeyes cr-report <project> [--track ID]       corner reflector identification report (Sentinel-1)
    geoeyes gacos-order <project> [--track ID]     GACOS troposphere order form: area, time, missing dates
    geoeyes catalog build | search [--bbox W,S,E,N] [--from D] [--to D] [--vel-below V]   products of the workspace
    geoeyes serve  [--port 8765] [--open]          web app on http://localhost:8765

``<project>`` is a project name in the workspace (``GEOEYES_WORKSPACE`` or ``--workspace``) or a path to a
``project.toml``. Selection: ``--track ID`` (repeatable), ``--from PHASE``, ``--to PHASE``, ``--only PHASE``;
``plan`` / ``run`` also ``--skip PHASE`` or ``--skip TRACK/PHASE`` (repeatable: phases left as they are) and
``--ps-from STEP`` / ``--ps-to STEP`` (steps 1-8 of the ps engine; each step is checkpointed and resumed).
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
    p = plan(cfg, project, ws, force=tuple(args.force or ()), skip=tuple(args.skip or ()), ps_from=args.ps_from,
             ps_to=args.ps_to, **_selection(args))
    print(f"project {cfg.project.name}: {len(p.to_run())} phase(s) to run")
    print(p)
    return 1 if any(s.action == "blocked" for s in p.steps) else 0


def cmd_run(args) -> int:
    from geoeyes.controller.pipeline import run
    cfg, project, ws = _open(args)
    res = run(cfg, project, ws, force=tuple(args.force or ()), skip=tuple(args.skip or ()), ps_from=args.ps_from,
              ps_to=args.ps_to, log_level=args.log_level, **_selection(args))
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


def cmd_atmosphere(args) -> int:
    """Weather models against the unwrapped phase of a product (``--product``, else the latest of each track)."""
    import logging

    from geoeyes.validation.atmosphere import run_atmosphere
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg, project, ws = _open(args)
    ids = _product_ids(args, cfg, project)
    if not ids:
        print("no product yet: run the project first (geoeyes run)", file=sys.stderr)
        return 1
    for pid in ids:
        s = run_atmosphere(cfg, project, ws, pid, _overrides(args.set), progress=lambda msg: print(msg, flush=True))
        rows = ", ".join(f"{k} {m['median_std_mm']:.2f} mm ({m['reduction_pct']:+.0f} %)"
                         for k, m in s["models"].items())
        print(f"{pid}: residual phase scatter, median over the interferograms: {rows}"
              + f" -> {project.analysis('atmosphere', pid)}")
        for k, e in s["errors"].items():
            print(f"  {k}: {e}")
    return 0


def _cmd_ml(kind: str):
    def cmd(args) -> int:
        """AI analysis of a product (``--product``, else the latest product of each track)."""
        import logging

        from geoeyes import ml
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        cfg, project, ws = _open(args)
        ids = _product_ids(args, cfg, project)
        if not ids:
            print("no product yet: run the project first (geoeyes run)", file=sys.stderr)
            return 1
        fn = {"susceptibility": ml.run_susceptibility, "forecast": ml.run_forecast, "buildings": ml.run_buildings,
              "behaviour": ml.run_behaviour, "risk": ml.run_risk, "lines": ml.run_lines,
              "consolidation": ml.run_consolidation, "decompose": ml.run_decompose,
              "geology": ml.run_geology}[kind]
        for pid in ids:
            s = fn(cfg, project, ws, pid, _overrides(args.set), progress=lambda msg: print(msg, flush=True))
            print(f"{pid}: {kind} done ({s.get('chosen')}) -> {project.analysis(kind, pid)}")
        return 0
    return cmd


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


def cmd_floods(args) -> int:
    """Inventory of reported flood locations: ``import`` a pasted announcement, ``locate`` the rows on OSM, ``list``."""
    from geoeyes.ancillary import flood_reports as fr
    from geoeyes.config.settings import load_settings
    from geoeyes.workspace import WorkspaceLayout
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
    if args.action == "import":
        if not args.file:
            print("error: the announcement text file is needed (geoeyes floods import <file>)", file=sys.stderr)
            return 2
        text = Path(args.file).read_text(encoding="utf-8")
        parse = fr.parse_prose if args.prose else fr.parse_list
        rows = parse(text, cause=args.cause or ("rain" if args.prose else None), reported=args.reported or "",
                     source=args.source or "", url=args.url or "", region=args.region)
        added, total = fr.add_rows(ws, args.region, rows)
        print(f"{len(rows)} location(s) read, {added} new -> {fr.folder(ws) / (args.region + '.csv')} ({total} rows)")
        return 0
    if args.action == "locate":
        s = fr.locate(ws, args.region, progress=lambda m: print(m, flush=True))
        counts = ", ".join(f"{k} {v}" for k, v in sorted(s["located"].items()))
        print(f"{s['rows']} row(s): {counts} -> {s['path']}")
        return 0
    for f in fr.collection(ws)["features"]:
        p = f["properties"]
        print(f"{f['id']}  {p['cause']:9s} {p['located']:9s} {p['reported']}  {p['text']}")
    return 0


def cmd_gacos_order(args) -> int:
    """What to enter in the GACOS order form (http://www.gacos.net, no API) for every track of a project: area,
    UTC time, and the dates that have no product yet in ``[atmosphere.gacos] dir``."""
    from geoeyes.controller.phase import PhaseContext
    from geoeyes.controller.phases import build_stack as bs
    from geoeyes.io.stack import StackStore
    from geoeyes.processing.atmosphere import gacos
    from geoeyes.processing.atmosphere.times import acquisition_times
    cfg, project, ws = _open(args)
    folder = dict(cfg.atmosphere.gacos).get("dir")
    if cfg.aoi.bbox is None:
        print("error: [aoi] bbox is needed for the order area", file=sys.stderr)
        return 2
    w, s, e, n = cfg.aoi.bbox
    for tr in cfg.tracks:
        if args.track and tr.track_id not in args.track:
            continue
        t = bs.target(PhaseContext(cfg, project, ws, tr))
        st = StackStore(t["path"])
        # times from the stack, else from the scene names (dates not in the stack yet)
        attrs = {**(st.attrs if st.exists() else {}), "scenes": {str(d): p.name for d, p in t["scenes"].items()}}
        days = list(t["scenes"])
        times = acquisition_times(attrs, days, fallback_utc=dict(cfg.atmosphere.era5).get("fallback_utc"))
        if folder:
            times = {d: v for d, v in times.items() if gacos.read_ztd(Path(folder), d) is None}
        o = gacos.order([w, e], [s, n], times)
        print(f"{tr.track_id}: {len(o['dates'])} date(s) to order"
              + (f" (the others are already in {folder})" if folder else ""))
        print(f"  area      N {o['north']}  S {o['south']}  W {o['west']}  E {o['east']}")
        print(f"  time UTC  {o['time_utc']}")
        for i in range(0, len(o["dates"]), 20):                 # the form takes the dates as text, one per line
            print("  " + "\n  ".join(o["dates"][i:i + 20]))
    if not folder:
        print("then set [atmosphere] method = \"gacos\" and [atmosphere.gacos] dir = \"<folder of the products>\"")
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


def cmd_opendata(args) -> int:
    """Open-data hub: ``sync`` the STAC catalogs, ``sources``, ``scenes`` / ``stacks`` search, ``show`` a stack,
    ``fetch`` it into the archive, ``project``: a new project on it."""
    from geoeyes import opendata as od
    from geoeyes.config.settings import load_settings
    from geoeyes.core.errors import ConfigError
    from geoeyes.opendata.stacks import get_stack
    from geoeyes.workspace import WorkspaceLayout
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    sources = args.source or None
    if args.action == "sync":
        from geoeyes.opendata.index import refresh
        for sid, r in refresh(ws, sources, progress=lambda s, m: print(f"{s}: {m}", flush=True)).items():
            print(f"{sid}: {r['scenes']} scene(s), {r['new']} new, {r['removed']} removed, {r['failed']} unreadable")
        return 0
    if args.action == "sources":
        from geoeyes.opendata.index import status
        for r in status(ws):
            print(f"{r['source']:8s} {r['scenes']:5d} scene(s)  synced {r['synced'] or 'never':25s}  "
                  f"reader: {r['sensor'] or '-':8s} {r['license']}  {r['homepage']}")
        return 0
    scenes = od.load(ws, sources)
    if not scenes:
        print("open-data index empty: run `geoeyes opendata sync`")
        return 1
    if args.action == "scenes":
        rows = od.search(scenes, bbox=bbox, start=args.start, end=args.end, mode=args.mode)
        for r in rows:
            inc = f"{r['incidence']:.1f}" if r["incidence"] is not None else "-"
            print(f"{r['datetime'][:19]}  {r['source']:7s} {r['platform']:10s} {r['mode']:17s} {r['orbit_state']:10s} "
                  f"{r['look']:5s} inc {inc:5s}  {r['id']}")
        print(f"{len(rows)} scene(s)")
        return 0
    stacks = od.find_stacks(od.search(scenes, start=args.start, end=args.end, mode=args.mode),
                            min_scenes=args.min_scenes, aoi=bbox)
    if args.action == "stacks":
        from geoeyes.opendata.places import names
        names(ws, stacks)
        for s in stacks:
            if args.supported and not s["supported"]:
                continue
            inc = f"{s['incidence'][0]:.1f}-{s['incidence'][1]:.1f}" if s["incidence"] else "-"
            gap = f"{s['median_gap_days']:g}" if s["median_gap_days"] is not None else "-"
            print(f"{s['id']:48s} {s['n_dates']:3d} dates  {s['first']}..{s['last']}  gap {gap:>4s} d  "
                  f"inc {inc:9s} {s['place'] or ''}{'' if s['supported'] else '  (search only: no reader)'}")
        print(f"{len(stacks)} stack(s)")
        return 0
    st = get_stack(stacks, args.stack or "")
    if st is None:
        raise ConfigError(f"stack {args.stack!r} not found (with these filters); see `geoeyes opendata stacks`")
    if args.action == "show":
        import json
        print(json.dumps({k: v for k, v in st.items() if k not in ("footprint",)}, indent=2))
        return 0
    if bbox is None:
        raise ConfigError("--bbox west,south,east,north: the AOI (it must lie inside the stack's footprint)")
    if args.action == "fetch":
        from geoeyes.geometry.dem import load_dem
        from geoeyes.opendata.fetch import fetch_stack
        if not st["supported"]:
            raise ConfigError(f"{st['id']}: GeoEyes has no reader for {st['product']} yet")
        track = args.track_id or f"{st['sensor']}-{st['orbit_state'][:3]}"
        w, s, e, n = bbox
        dem = load_dem(args.dem, s - 0.05, n + 0.05, w - 0.05, e + 0.05, cache=ws.cache_dir("dem")) \
            if st["source"] in ("iceye", "umbra") else None
        root = ws.archive / st["sensor"] / track
        from geoeyes.opendata.fetch import MARGIN_M
        margin = args.margin if args.margin is not None else MARGIN_M.get(st["source"], 0.0)
        got = fetch_stack(st, scenes, root, aoi=bbox, dem=dem, margin_m=margin,
                          progress=lambda i, k, sid: print(f"[{i}/{k}] {sid}", flush=True))
        print(f"{len(got)} scene(s) in {root} ({sum(g['bytes'] for g in got) / 1e6:.0f} MB new)")
        return 0
    # project
    import tomllib

    import tomli_w

    from geoeyes.config.loader import load_dict
    if not st["supported"]:
        raise ConfigError(f"{st['id']}: GeoEyes has no reader for {st['product']} yet")
    proj = ws.project(args.name)
    if proj.config.exists():
        raise ConfigError(f"project {args.name!r} already exists")
    method = args.method or ("ps_lite" if st["sensor"] in ("capella", "umbra") else "psi")    # short stacks
    doc = {"schema": "geoeyes.project/1",
           "project": {"name": args.name, "method": method,
                       "description": f"open-data stack {st['id']} ({st['first']}..{st['last']})"},
           "aoi": {"bbox": [round(v, 5) for v in bbox]},
           "tracks": [{"sensor": st["sensor"], "direction": st["orbit_state"]}],
           "acquire": {"opendata": st["id"]}}
    text = tomli_w.dumps(doc)
    load_dict(tomllib.loads(text))
    proj.ensure()
    proj.config.write_text(text, encoding="utf-8", newline="\n")
    print(f"project {args.name} -> {proj.config}\nnext: geoeyes run {args.name}")
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
    pl = add("plan", cmd_plan, help_="show what run would do")
    pl.add_argument("--force", action="append", metavar="PHASE")
    r = add("run", cmd_run, help_="run the project")
    r.add_argument("--force", action="append", metavar="PHASE", help="run this phase even when up to date")
    for x in (pl, r):
        x.add_argument("--skip", action="append", metavar="PHASE",
                       help="leave this phase as it is, not even checked (PHASE or TRACK/PHASE, repeatable)")
        x.add_argument("--ps-from", type=int, choices=range(1, 9), metavar="STEP",
                       help="ps engine: compute step STEP (1-8) and the following ones again (earlier: checkpoints)")
        x.add_argument("--ps-to", type=int, choices=range(1, 8), metavar="STEP",
                       help="ps engine: stop after step STEP (1-7); the next run resumes from STEP + 1")
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
    at = add("atmosphere", cmd_atmosphere, selection=False,
             help_="try the weather models (ERA5, CERRA, GACOS) on a product without running it again")
    at.add_argument("--product", help="product id (default: the latest product of each track)")
    at.add_argument("--track", action="append", help="track id (repeatable)")
    at.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help='models=["era5","cerra"] | max_points=200000 | grid=256 (repeatable)')
    for kind, help_ in (("susceptibility", "AI: ground-motion susceptibility from thematic layers (needs hazard)"),
                        ("forecast", "AI: deformation forecast of the cells, backtested against baselines"),
                        ("buildings", "InSAR velocity and tilt of every building (Overture footprints)"),
                        ("behaviour", "kind of motion of every hazard cell and the date of a change (needs hazard)"),
                        ("risk", "risk to every building: hazard x consequence (needs hazard; buildings if run)"),
                        ("lines", "InSAR profiles along dykes, railways and main roads (OpenStreetMap)"),
                        ("consolidation", "final and remaining settlement of the consolidating cells (needs hazard)"),
                        ("decompose", "vertical and east-west motion with a product seen from another direction"),
                        ("geology", "soft-soil thickness of the cells against their subsidence (needs hazard)")):
        ml = add(kind, _cmd_ml(kind), selection=False, help_=help_)
        ml.add_argument("--product", help="product id (default: the latest product of each track)")
        ml.add_argument("--track", action="append", help="track id (repeatable)")
        ml.add_argument("--set", action="append", metavar="KEY=VALUE",
                        help=f"override a [postprocess.{kind}] parameter (repeatable)")
    go = add("gacos-order", cmd_gacos_order, selection=False,
             help_="what to enter in the GACOS order form (troposphere products, no API)")
    go.add_argument("--track", action="append", help="track id (repeatable)")
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
    fl = sub.add_parser("floods", help="inventory of reported flood locations: import a list, locate on OSM, list")
    fl.add_argument("action", choices=["import", "locate", "list"])
    fl.add_argument("file", nargs="?", help="text of the announcement (import): '- item' lines, cause headings")
    fl.add_argument("--region", default="hcmc", help="inventory region (default hcmc)")
    fl.add_argument("--cause", choices=["rain", "tide", "rain_tide"], help="cause of every item (default: headings)")
    fl.add_argument("--reported", metavar="YYYY-MM-DD", help="date of the announcement")
    fl.add_argument("--source", help="who announced it (e.g. PC08 Công an TP.HCM)")
    fl.add_argument("--url", help="where it was published")
    fl.add_argument("--prose", action="store_true",
                    help="the list is sentences ('Lưu vực X: phố A (...), phố B, ...'), as Hanoi Drainage bulletins")
    fl.set_defaults(func=cmd_floods)
    od = sub.add_parser("opendata", help="open SAR data hub (ICEYE, Capella, Umbra STAC): sync, search stacks, fetch")
    od.add_argument("action", choices=["sync", "sources", "scenes", "stacks", "show", "fetch", "project"])
    od.add_argument("stack", nargs="?", help="stack id (show, fetch, project)")
    od.add_argument("name", nargs="?", help="project name (project)")
    od.add_argument("--source", action="append", help="iceye, capella, umbra (repeatable; default all)")
    od.add_argument("--bbox", help="west,south,east,north (AOI)")
    od.add_argument("--from", dest="start", metavar="YYYY-MM-DD")
    od.add_argument("--to", dest="end", metavar="YYYY-MM-DD")
    od.add_argument("--mode", help="stripmap, spotlight, sliding_spotlight...")
    od.add_argument("--min-scenes", type=int, default=3)
    od.add_argument("--supported", action="store_true", help="only stacks GeoEyes can process")
    od.add_argument("--track-id", help="archive track folder (fetch; default <sensor>-<asc|des>)")
    od.add_argument("--margin", type=float, help="metres around the AOI of a cut product (default ICEYE 500, Umbra 50)")
    od.add_argument("--dem", default="copernicus-30", help="DEM for the ICEYE range window (default copernicus-30)")
    od.add_argument("--method", help="method of the new project (project; default psi, Capella ps_lite)")
    od.set_defaults(func=cmd_opendata)
    sv = sub.add_parser("serve", help="web app (API and front end on one port)")
    sv.add_argument("--host", default="127.0.0.1", help="listen address (default: this machine only)")
    sv.add_argument("--port", type=int, default=8765, help="port (default 8765; never Vite's 5173)")
    sv.add_argument("--open", action="store_true", help="open the browser")
    sv.set_defaults(func=cmd_serve)
    return ap


def main(argv=None) -> int:
    # Windows consoles default to a legacy code page (cp1252): messages with "≥", "τ", "°" would crash the run
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except GeoEyesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
