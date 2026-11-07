"""``geoeyes`` command line (ARCHITECTURE §15.1).

    geoeyes check  [<project>]                    environment and project configuration
    geoeyes plan   <project> [selection]           what ``run`` would do, nothing is run
    geoeyes run    <project> [selection] [--force PHASE ...]
    geoeyes status <project>                       phase status per track, last runs
    geoeyes report <project> [--product ID]        (re)build the PDF report of the latest / given product
    geoeyes cr-report <project> [--track ID]       corner reflector identification report (Sentinel-1)
    geoeyes gacos-order <project> [--track ID]     GACOS troposphere order form: area, time, missing dates
    geoeyes tie    <project> --reference P/ID      tie a product with no GNSS station to another product (calibration)
    geoeyes stack-qc <project> [--stack ID]        interferograms, coherence and offsets of a coregistered stack
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
    from geoeyes.core import compute
    gpu = compute.info("auto")
    report(True, f"compute: {gpu['describe']}" + ("" if gpu["backend"] == "cupy" else
                                                  " (no usable GPU: CuPy not installed or no device)"))
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
        if cfg.compute.backend != "auto":
            want = compute.info(cfg.compute.backend)
            report(want["ok"], f"[compute] backend = {cfg.compute.backend!r}: {want['describe']}")
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


def cmd_tie(args) -> int:
    """Tie a product to another product of the same ground: one rate correction (validation.tie)."""
    from geoeyes.validation.tie import active_calibration, tie
    cfg, project, ws = _open(args)
    ids = _product_ids(args, cfg, project)
    rp, _, rpid = args.reference.partition("/")
    if not ids or not rpid:
        print("no product yet, or --reference is not PROJECT/PRODUCT_ID", file=sys.stderr)
        return 1
    ref = ws.project(rp)
    for pid in ids:
        s = tie(project.product(pid), ref.product(rpid), project.analysis("tie", pid),
                reference_calibration=active_calibration(ref, rpid), cell_m=args.cell)
        c = s["calibration"]
        print(f"{pid}: {s['n_cells']} common cells, correlation {s['corr']}, gain {s['slope']}; offset "
              f"{c['rate_offset_mm_yr']:+.2f} mm/yr LOS ({c['vertical_offset_mm_yr']:+.2f} vertical)"
              + (f", through {c['reference_calibration']}" if c["reference_calibration"] else "")
              + f" -> {project.analysis('tie', pid)}")
        for w in s["warnings"]:
            print(f"  warning: {w}")
    return 0


def cmd_stack_qc(args) -> int:
    """Amplitude, interferogram and coherence of every date of a stack against its reference (processing.stack.qc)."""
    from geoeyes.processing.stack.qc import stack_qc
    _cfg, project, _ws = _open(args)
    root = project.root / "stacks"
    ids = args.stack or sorted(d.parent.name for d in root.glob("*/stack.zarr"))
    if not ids:
        print("no stack yet: run build_stack first", file=sys.stderr)
        return 1
    for sid in ids:
        s = stack_qc(project.stack_store(sid), progress=lambda m, sid=sid: print(f"{sid}: {m}", flush=True))
        for r in s["dates"]:
            if r["reference"]:
                print(f"  {r['date']}  reference")
                continue
            print(f"  {r['date']}  Bperp {r['bperp_m']:+9.0f} m  HoA {r['height_of_ambiguity_m']} m  coherence "
                  f"{r['coherence_mean']:.2f} (p90 {r['coherence_p90']:.2f})  offset {r['offset_lines']:+.2f} / "
                  f"{r['offset_samples']:+.2f} px  amplitude corr {r['amplitude_corr']:.2f}")
        print(f"-> {project.stack(sid) / 'qc'}")
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
              "geology": ml.run_geology, "exposure": ml.run_exposure}[kind]
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


def cmd_params(args) -> int:
    """What a processing parameter is for (the parameter catalogue, geoeyes/advisor/params.toml)."""
    from geoeyes.advisor import catalog
    words = " ".join(args.words)
    found = catalog.search(words)
    if not found:
        print(f"no parameter matches {words!r}", file=sys.stderr)
        return 1
    if args.list or (len(found) > 5 and not words):
        for p in found:
            print(f"{p.path:<40} {p.text[args.lang]['help']}")
        return 0
    print("\n\n".join(catalog.explain(p, args.lang) for p in found))
    return 0


def cmd_site(args) -> int:
    """Site profile of a project or a bbox: terrain, land cover, geology, climate, data (site advisor V1)."""
    import json

    from geoeyes.advisor.profile import profile, summary
    from geoeyes.config.settings import load_settings
    from geoeyes.workspace import WorkspaceLayout
    project = cfg = None
    if args.project:
        cfg, project, ws = _open(args)
        bbox = list(cfg.aoi.bbox) if cfg.aoi and cfg.aoi.bbox else None
        dem = args.dem or cfg.stack.dem or "srtm-1"
    else:
        ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
        bbox, dem = None, args.dem or "copernicus-30"
    if args.bbox:
        bbox = [float(v) for v in args.bbox.split(",")]
    if not bbox or len(bbox) != 4:
        print("error: give a project with [aoi] bbox, or --bbox W,S,E,N", file=sys.stderr)
        return 2
    p = profile(bbox, cache_root=ws.cache, dem=str(dem), project=project, cfg=cfg, refresh=args.refresh,
                progress=lambda m: print(m, file=sys.stderr))
    print(json.dumps(p, ensure_ascii=False, indent=1) if args.json else summary(p, args.lang))
    return 0


def cmd_advise(args) -> int:
    """Site advisor: profile of the AOI -> rules -> suggested parameters with their reasons (site advisor V2)."""
    import json
    import tomllib

    from geoeyes.advisor import rules
    from geoeyes.advisor.profile import profile, summary
    from geoeyes.config.settings import load_settings
    from geoeyes.workspace import WorkspaceLayout
    project = cfg = raw = None
    if args.learn:
        from geoeyes.advisor import learn
        ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
        text = learn.report(learn.collect(ws, progress=lambda m: print(m, file=sys.stderr)), args.lang)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"written {args.out}", file=sys.stderr)
        print(text)
        return 0
    if args.project:
        cfg, project, ws = _open(args)
        raw = tomllib.loads(project.config.read_text(encoding="utf-8"))
        bbox = list(cfg.aoi.bbox) if cfg.aoi and cfg.aoi.bbox else None
        dem = cfg.stack.dem or "srtm-1"
    else:
        ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
        bbox, dem = None, "copernicus-30"
    if args.bbox:
        bbox = [float(v) for v in args.bbox.split(",")]
    if not bbox or len(bbox) != 4:
        print("error: give a project with [aoi] bbox, or --bbox W,S,E,N", file=sys.stderr)
        return 2
    p = profile(bbox, cache_root=ws.cache, dem=str(dem), project=project, cfg=cfg,
                progress=lambda m: print(m, file=sys.stderr))
    advice = rules.evaluate(p)
    cmp = rules.compare(advice, cfg, raw) if cfg is not None else None
    if args.json:
        print(json.dumps({"profile": p, "metrics": advice.metrics, "matched": advice.matched,
                          "skipped": advice.skipped,
                          "recipe": {k: {"value": s.value, "rule": s.rule, "replaced": s.replaced}
                                     for k, s in advice.recipe.items()},
                          "notes": [{"rule": r, "note": n} for r, n in advice.notes], "compare": cmp},
                         ensure_ascii=False, indent=1, default=str))
        return 0
    print(summary(p, args.lang))
    print()
    print(rules.report(advice, cmp, args.lang))
    if args.apply:
        if cmp is None:
            print("error: --apply needs a project", file=sys.stderr)
            return 2
        from geoeyes.api import settings
        todo = {r["path"]: r["suggested"] for r in cmp["changes"]}
        if not todo:
            print("\nnothing to apply")
            return 0
        settings.apply(project, todo)
        print(f"\napplied {len(todo)} value(s) to {project.config} (previous file kept in .state/)")
    return 0


def cmd_mcp(args) -> int:
    """The site advisor as a local MCP server on stdin / stdout (site advisor V5)."""
    import os

    from geoeyes.advisor.mcp import serve
    if args.workspace:
        os.environ["GEOEYES_WORKSPACE"] = args.workspace
    return serve()


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


def cmd_landslide(args) -> int:
    """Landslide study (docs/en/research/landslide-susceptibility.md): ``inventory`` rebuilds the workspace
    inventories, ``audit`` their footprints and area–frequency (L0), ``labels`` the labels of a study (L1)."""
    from geoeyes.config.settings import load_settings
    from geoeyes.landslide import inventory as inv
    from geoeyes.workspace import WorkspaceLayout
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
    if args.action == "inventory":
        print(json.dumps({"vietnam": inv.build_vietnam(ws.root), "das2024": inv.build_das2024(ws.root)},
                         indent=1, ensure_ascii=False))
        return 0
    from geoeyes.landslide.study import load_study
    st = load_study(ws.root, args.study)
    if args.action == "audit":
        res = inv.audit(ws.root, st.step_dir("audit"), ws.cache_dir("dem") / "copernicus-30")
        for r in res["footprints"]:
            print(f"{r['event']:8s} {r['variant']:12s} {r['area_km2']:8.1f} km²  {r['n_inside']}/{r['n_landslides']}")
        return 0
    if args.action == "layers":
        from geoeyes.landslide.predictors import run_predictors
        smy = run_predictors(st, ws.cache, load_settings().earthdata_token, progress=lambda m: print(m, flush=True))
        for w in smy["warnings"]:
            print(f"warning: {w}")
        for ev, s in smy["events"].items():
            print(f"{ev}: kept for the trees {len(s['screen']['trees'])}, for the logistic model "
                  f"{len(s['screen']['logistic'])}, dropped {sorted(s['screen']['dropped'])}")
        print(f"-> {st.step_dir('predictors')}")
        return 0
    if args.action == "fit":
        from geoeyes.landslide.model import run_fit
        res = run_fit(st, progress=lambda m: print(m, flush=True), cache_root=ws.cache)
        b0 = f"spatial_{st.models.blocks_m[0]:g}"
        for ev, r in res["events"].items():
            m = r["main"][r["best_model"]]
            print(f"{ev}: best {r['best_model']}, spatial AUC {m[b0].get('auc')} (random "
                  f"{m.get('random', {}).get('auc')})")
        print(f"-> {st.step_dir('models')}")
        return 0
    if args.action == "persistence":
        from geoeyes.landslide.dating import run_persistence
        res = run_persistence(st, progress=lambda m: print(m, flush=True))
        print(f"-> {st.step_dir('scars')} ({len(res['events'])} sets)")
        return 0
    if args.action == "dating":
        from geoeyes.landslide.dating import run_dating
        res = run_dating(st, progress=lambda m: print(m, flush=True))
        for ev, r in res["events"].items():
            print(f"{ev}: {r['objects']} objects, timing {r['timing']}")
        print(f"-> {st.step_dir('scars')}")
        return 0
    if args.action == "raincheck":
        from geoeyes.landslide.satrain import run_check
        y0, _, y1 = args.years.partition("-")
        res = run_check(st, ws.cache, years=range(int(y0), int(y1 or y0) + 1), progress=lambda m: print(m, flush=True))
        p = res["pooled"]
        print(f"F2: Early/Final totals {p['ratio_totals']}, p99 {p['p99_ratio']}, POD>=100 mm "
              f"{p['thresholds']['100']['pod']}")
        print(f"-> {st.step_dir('rain_f2')}")
        return 0
    if args.action == "l5":
        from geoeyes.landslide.insar import run_l5
        res = run_l5(st, ws.root / "projects" / args.insar, progress=lambda m: print(m, flush=True))
        print(f"-> {st.step_dir('insar')} (coverage {res['coverage']['share']:.1%}, H3 tested "
              f"{res['h3']['tested']})")
        return 0
    if args.action == "rainproducts":
        from geoeyes.landslide.satrain import run_products
        y0, _, y1 = args.years.partition("-")
        res = run_products(st, ws.cache, years=range(int(y0), int(y1 or y0) + 1),
                           progress=lambda m: print(m, flush=True))
        for k, v in res["pooled"].items():
            print(f"{k}: totals {v['ratio_totals']}, corr {v['corr']}, p99 {v['p99_ratio']}")
        print(f"-> {st.step_dir('rain_f2')}")
        return 0
    if args.action == "catalogue":
        from geoeyes.landslide.catalogue import run_catalogue
        res = run_catalogue(st, ws.root, ws.cache, progress=lambda m: print(m, flush=True))
        print(f"F1: {res['events']} events, {res['commune_days']} positive commune-days on {res['distinct_days']} "
              f"days (target {res['target_commune_days']})")
        print(f"-> {st.step_dir('catalogue')}")
        return 0
    if args.action == "rainarchive":
        from geoeyes.landslide.satrain import run_archive
        y0, _, y1 = args.years.partition("-")
        res = run_archive(None, ws.cache, runs=tuple(args.runs.split(",")), years=range(int(y0), int(y1 or y0) + 1),
                          progress=lambda m: print(m, flush=True))
        for run, ys in res.items():
            print(f"{run}: {sum(v['days'] for v in ys.values())} days, "
                  f"{sum(v['missing'] for v in ys.values())} missing")
        print(f"-> {ws.cache / 'rainfall'}")
        return 0
    if args.action == "rain":
        from geoeyes.landslide.rain import run_rain
        res = run_rain(st, ws.cache, progress=lambda m: print(m, flush=True))
        n = res["null"]
        print(f"L4: gain {n['gain_real']:+.4f} vs null q95 {n['null_q95']:+.4f} (p = {n['p_value']}): "
              f"H2 {'holds' if n['h2'] else 'does not hold'}")
        print(f"-> {st.step_dir('rain')}")
        return 0
    if args.action == "improve" and args.step == "c5":
        from geoeyes.landslide.improve import run_c5
        res = run_c5(st, progress=lambda m: print(m, flush=True))
        print(f"C5: kept {[k for k, v in res['variants'].items() if v['keep']]}")
        print(f"-> {st.step_dir('models') / 'improve'}")
        return 0
    if args.action == "improve" and args.step == "c3":
        from geoeyes.landslide.improve import run_c3
        res = run_c3(st, ws.cache, progress=lambda m: print(m, flush=True))
        print(f"C3: kept {[k for k, v in res['families'].items() if v['keep']]}")
        print(f"-> {st.step_dir('models') / 'improve'}")
        return 0
    if args.action == "improve":
        from geoeyes.landslide.improve import run_c1
        res = run_c1(st, progress=lambda m: print(m, flush=True))
        b, n = res["best"], res["nested"]
        print(f"C1: baseline {res['baseline']['pooled']} -> best {b['pooled']} (Δ {b['paired']['delta']:+.4f}, "
              f"95 % {b['paired']['ci95']}, keep {b['keep']}); nested {n['auc']}")
        print(f"-> {st.step_dir('models') / 'improve'}")
        return 0
    if args.action == "thresholds":
        from geoeyes.landslide.thresholds import run_thresholds
        res = run_thresholds(st, ws.root, ws.cache, progress=lambda m: print(m, flush=True))
        for reg, r in res["regions"].items():
            print(f"{reg}: {r['landslides']} landslides; E-D TSS {r.get('ED', {}).get('tss')}, A10 % >= "
                  f"{r['A10_pct']['cut']} TSS {r['A10_pct']['tss']}; LOYO {r['loyo']}")
        print(f"-> {st.step_dir('thresholds')}")
        return 0
    if args.action == "reliability":
        from geoeyes.landslide.reliability import run_reliability
        res = run_reliability(st, ws.cache)
        for ev, r in res["events"].items():
            print(f"{ev}: {r['polygons']} polygons, {r['share']}; reasons {r['reasons']}")
        print(f"-> {st.step_dir('labels')}")
        return 0
    if args.action == "test":
        from geoeyes.landslide.model import rerun_test
        res = rerun_test(st, ws.cache, progress=lambda m: print(m, flush=True))
        for ev, r in res["test"]["events"].items():
            print(f"{ev}: {r['positives']} positives")
        print(f"-> {st.step_dir('models')}")
        return 0
    if args.action == "scars":
        from geoeyes.landslide.scars import run_scars
        res = run_scars(st, ws.cache, progress=lambda m: print(m, flush=True))
        c = res["calibration"]
        print(f"calibration on {res['calibration_event']}: {res['thresholds']}; precision {c['precision']}, "
              f"recall {c['recall']}, F1 {c['f1']}")
        for ev, r in res["events"].items():
            print(f"{ev}: {r['objects']} objects")
        print(f"-> {st.step_dir('scars')}")
        return 0
    if args.action == "verify":
        from geoeyes.landslide.verify import run_verify
        stores = {}
        for name in args.s1 or []:
            for z in sorted(ws.project(name).root.glob("stacks/*/stack.zarr")):
                stores[f"{name}/{z.parent.name}"] = z
        res = run_verify(st, stores, progress=lambda m: print(m, flush=True))
        for ev, r in res["events"].items():
            c = r["b1_hansen"]["event"]["capture"]
            print(f"{ev}: Hansen event scars captured by Das {c.get('captured')}/{c.get('patches')}"
                  + (f", aspect LR {c['lr']} towards {c['azimuth_deg']}°" if "lr" in c else ""))
        print(f"-> {st.step_dir('verify')}")
        return 0
    if args.action == "aspect":
        from geoeyes.landslide.aspect import run_aspect
        res = run_aspect(st, ws.cache, progress=lambda m: print(m, flush=True))
        for ev, r in res["events"].items():
            c = r["conditional"]["location free"]
            print(f"{ev}: harmonics LR {c['lr']} (p {c['p']:.2g}), highest odds towards {c['azimuth_deg']}°; "
                  f"best sun {r['illumination']['best_sun']}")
        print(f"-> {st.step_dir('aspect')}")
        return 0
    import dataclasses

    from geoeyes.landslide.labels import run_labels
    from geoeyes.landslide.study import LabelParams
    if args.set:
        st.labels = LabelParams.from_dict({**dataclasses.asdict(st.labels), **_overrides(args.set)})
    smy = run_labels(st, ws.cache_dir("dem") / "copernicus-30")
    for ev, s in smy["events"].items():
        print(f"{ev}: {s['polygons']} polygons, positives {s['positives']}, candidates {s['candidates']}"
              + (f", short: {s['short']}" if s["short"] else ""))
    print(f"-> {st.step_dir('labels')}")
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


def cmd_coop(args) -> int:
    """Source Cooperative: ``sync`` the catalog, ``search`` it, list the ``layers`` GeoEyes reads, ``get`` one over
    an AOI (GeoTIFF / Parquet in ``<workspace>/cache/sourcecoop``)."""
    import numpy as np

    from geoeyes.config.settings import load_settings
    from geoeyes.core.errors import ConfigError
    from geoeyes.opendata import coop
    from geoeyes.workspace import WorkspaceLayout
    ws = WorkspaceLayout.at(args.workspace) if args.workspace else load_settings().workspace_layout()
    if args.action == "sync":
        r = coop.sync(ws, progress=lambda m: print(m, flush=True))
        print(f"{r['products']} product(s) of {r['accounts']} account(s)")
        return 0
    if args.action == "layers":
        for lay in coop.LAYERS.values():
            print(f"{lay.key:14s} {lay.topic:9s} {lay.product:42s} {lay.use}")
        return 0
    if args.action == "search":
        if coop.stale(ws):
            coop.sync(ws, progress=lambda m: print(m, flush=True))
        rows = coop.search(ws, " ".join(args.query), limit=args.limit)
        for p in rows:
            mark = f"[{p['layer']}] " if p["layer"] else ""
            print(f"{p['id']:50s} {mark}{p['title']}\n{'':50s} {p['url']}")
        print(f"{len(rows)} product(s)")
        return 0
    if not args.query or args.query[0] not in coop.LAYERS:
        raise ConfigError(f"coop get <layer>: one of {sorted(coop.LAYERS)}")
    if not args.bbox:
        raise ConfigError("--bbox west,south,east,north")
    key, bbox = args.query[0], [float(v) for v in args.bbox.split(",")]
    cache = ws.cache_dir("sourcecoop")
    if key == "chirps-daily":
        if not (args.start and args.end):
            raise ConfigError("chirps-daily: --from and --to")
        for d in coop.chirps_daily(cache, bbox, args.start, args.end, progress=print)["days"]:
            print(f"{d['date']}  mean {d['mean_mm'] if d['mean_mm'] is not None else '-':>7} mm   "
                  f"max {d['max_mm'] if d['max_mm'] is not None else '-':>7} mm")
        return 0
    if key == "imerg":
        if not (args.start and args.end):
            raise ConfigError("imerg: --from and --to")
        r = coop.imerg_halfhourly(cache, bbox, args.start, args.end, python=load_settings().icechunk_python or None,
                                  progress=print)
        for s in r["steps"]:
            if s["mean_mm_h"] is not None and s["mean_mm_h"] >= 0.1:          # dry half hours left out
                print(f"{s['time'][:16]}Z  mean {s['mean_mm_h']:6.1f} mm/h   max {s['max_mm_h']:6.1f} mm/h")
        wet = [s for s in r["steps"] if s["mean_mm_h"] is not None]
        print(f"{len(r['steps'])} half hour(s), {sum(s['mean_mm_h'] for s in wet) / 2:.1f} mm in all ({r['source']})")
        return 0
    if key == "gba-buildings":
        t = coop.gba_buildings(cache, bbox, progress=print)
        print(f"{len(t)} building(s), median height {np.nanmedian(t['height_m']):.1f} m -> {cache / key}")
        return 0
    if key == "gsw-monthly" and not args.month:
        raise ConfigError("gsw-monthly: --month YYYY-MM")
    g = {"gsw-monthly": lambda: coop.gsw_month(cache, bbox, args.month),
         "glofas-depth": lambda: coop.glofas_depth(cache, bbox, args.rp),
         "ghsl-pop": lambda: coop.ghsl_pop(cache, bbox)}[key]()
    a = g.data
    seen = np.isfinite(a)
    info = {"gsw-monthly": lambda: f"water {(a == 2).sum() / max(seen.sum(), 1):.1%} of the observed pixels, "
                                   f"{1 - seen.mean():.1%} not observed",
            "glofas-depth": lambda: f"flooded {seen.mean():.1%}, depth max {np.nanmax(a) if seen.any() else 0:.1f} m",
            "ghsl-pop": lambda: f"{np.nansum(a):,.0f} people"}[key]()
    print(f"{key}: {a.shape[1]} x {a.shape[0]} px of {g.res * 3600:.2f}\", {info} -> {g.path}")
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
        from geoeyes.core.types import OrbitDirection
        # the folder a project of this stack reads (TrackSpec.track_id: <sensor>-asc | <sensor>-desc)
        track = args.track_id or f"{st['sensor']}-{OrbitDirection.parse(st['orbit_state']).short}"
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
    ti = add("tie", cmd_tie, selection=False,
             help_="tie a product with no GNSS station to another product of the same ground (calibration)")
    ti.add_argument("--product", help="product id (default: the latest product of each track)")
    ti.add_argument("--track", action="append", help="track id (repeatable)")
    ti.add_argument("--reference", required=True, metavar="PROJECT/PRODUCT_ID",
                    help="the product tied to (its own GNSS calibration is applied first)")
    ti.add_argument("--cell", type=float, default=100.0, help="comparison cells, metres (default 100)")
    sq = add("stack-qc", cmd_stack_qc, selection=False,
             help_="quality check of the coregistered stacks: interferograms, coherence, offsets left")
    sq.add_argument("--stack", action="append", help="stack id (repeatable; default: every stack of the project)")
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
                        ("exposure", "people and buildings on sinking ground and in an event's flood "
                                     "(--set flood_month=2024-09; Source Cooperative layers)"),
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
    pa = sub.add_parser("params", help="what a processing parameter is for: geoeyes params unwrap_grid_size | "
                                       "geoeyes params atmosphere | geoeyes params (all, one line each)")
    pa.add_argument("words", nargs="*", help="section.key, a key, or words to look for (English or Vietnamese)")
    pa.add_argument("--lang", choices=["en", "vi"], default="en")
    pa.add_argument("--list", action="store_true", help="one line per match")
    pa.set_defaults(func=cmd_params)
    si = sub.add_parser("site", help="site profile of a project or an area: terrain, land cover, geology, climate, "
                                     "data (cached per AOI)")
    si.add_argument("project", nargs="?")
    si.add_argument("--bbox", help="west,south,east,north (instead of the project's [aoi] bbox)")
    si.add_argument("--dem", help="DEM for the terrain part (default: the project's [stack] dem, else copernicus-30)")
    si.add_argument("--lang", choices=["en", "vi"], default="en")
    si.add_argument("--json", action="store_true", help="the whole profile as JSON")
    si.add_argument("--refresh", action="store_true", help="read the site parts again (ignore the cache)")
    si.set_defaults(func=cmd_site)
    av = sub.add_parser("advise", help="site advisor: what an area needs and how to set the parameters, with the "
                                       "reason of each value (rules in geoeyes/advisor/rules.toml, no AI)")
    av.add_argument("project", nargs="?")
    av.add_argument("--bbox", help="west,south,east,north (use --bbox=... when the west is negative)")
    av.add_argument("--lang", choices=["en", "vi"], default="en")
    av.add_argument("--json", action="store_true")
    av.add_argument("--apply", action="store_true", help="write the suggested changes into project.toml "
                                                         "(validated; the previous file is kept)")
    av.add_argument("--learn", action="store_true", help="every project of the workspace against the rules: where "
                                                         "they agree, differ, and values that recur without a rule")
    av.add_argument("--out", help="with --learn: also write the report (Markdown) to this file")
    av.set_defaults(func=cmd_advise)
    mc = sub.add_parser("mcp", help="site advisor as a local MCP server on stdin / stdout (for Claude Code: "
                                    "claude mcp add geoeyes-advisor -- geoeyes mcp)")
    mc.set_defaults(func=cmd_mcp)
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
    ls = sub.add_parser("landslide",
                        help="landslide study: inventories, footprints (L0), labels (L1), predictor layers (L2), "
                             "aspect (L2a), independent check (L2b), susceptibility models (L3), Sentinel-2 "
                             "scars (L3b)")
    ls.add_argument("action", choices=["inventory", "audit", "labels", "layers", "aspect", "verify", "scars",
                                       "dating", "persistence", "reliability", "rain", "thresholds", "improve",
                                       "fit", "test", "rainarchive", "raincheck", "rainproducts", "catalogue", "l5"])
    ls.add_argument("--insar", default="quangnam_l5_d120", metavar="PROJECT",
                    help="l5: the pre-event InSAR project with a hazard analysis (default quangnam_l5_d120)")
    ls.add_argument("--step", default="c1", choices=["c1", "c3", "c5"], help="improve: the L3c step (default c1)")
    ls.add_argument("--runs", default="early,final",
                    help="rainarchive: IMERG runs, comma-separated (early, late, final)")
    ls.add_argument("--years", default="2015-2025", help="rainarchive: first-last year (UTC days)")
    ls.add_argument("--s1", action="append", metavar="PROJECT",
                    help="verify: a project whose Sentinel-1 stack spans the October 2020 storms (repeatable)")
    ls.add_argument("--study", default="landslide_central_vn",
                    help="study folder under <workspace>/studies (default landslide_central_vn)")
    ls.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override a [labels] parameter, e.g. --set draws=5 (repeatable)")
    ls.set_defaults(func=cmd_landslide)
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
    od.add_argument("--track-id", help="archive track folder (fetch; default <sensor>-<asc|desc>, the project's track)")
    od.add_argument("--margin", type=float, help="metres around the AOI of a cut product (default ICEYE 500, Umbra 50)")
    od.add_argument("--dem", default="copernicus-30", help="DEM for the ICEYE range window (default copernicus-30)")
    od.add_argument("--method", help="method of the new project (project; default psi, Capella ps_lite)")
    od.set_defaults(func=cmd_opendata)
    sc = sub.add_parser("coop", help="Source Cooperative: sync / search the catalog, read an open layer over an AOI")
    sc.add_argument("action", choices=["sync", "search", "layers", "get"])
    sc.add_argument("query", nargs="*", help="search words (search) | layer key (get)")
    sc.add_argument("--bbox", help="west,south,east,north (get; --bbox=-99.3,19.3,-99,19.5 when west < 0)")
    sc.add_argument("--month", help="YYYY-MM (gsw-monthly)")
    sc.add_argument("--rp", type=int, default=100, help="return period, years (glofas-depth; default 100)")
    sc.add_argument("--from", dest="start", metavar="YYYY-MM-DD", help="first day (chirps-daily, imerg)")
    sc.add_argument("--to", dest="end", metavar="YYYY-MM-DD", help="last day (chirps-daily, imerg)")
    sc.add_argument("--limit", type=int, default=30)
    sc.set_defaults(func=cmd_coop)
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
