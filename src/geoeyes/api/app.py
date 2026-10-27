"""``geoeyes serve``: the web app — JSON API under ``/api`` and the built single-page app, on one port.

Local by default (127.0.0.1, no login). Listening on another address requires a token (``GEOEYES_WEB_TOKEN``,
else a random one printed at start): the browser sends it once to ``/api/login`` and keeps it in a cookie.
The front end is built from ``webapp/`` into ``geoeyes/api/static``.
"""
from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from geoeyes.api import ai, behaviour, compare, gnss, hazard, jobs, learn, monitor, points, service, settings
from geoeyes.config.loader import load
from geoeyes.core.errors import ConfigError, GeoEyesError, LockedError
from geoeyes.workspace import WorkspaceLayout

STATIC = Path(__file__).parent / "static"
DEFAULT_PORT = 8765
COOKIE = "geoeyes_token"
OPEN_PATHS = ("/api/login", "/api/health")


def _inside(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(404, f"{rel}: not found")
    return path


def create_app(ws: WorkspaceLayout, token: str | None = None) -> FastAPI:
    """``token``: required on every API call except login / health (None = local use, no login)."""
    app = FastAPI(title="GeoEyes", docs_url="/api/docs", openapi_url="/api/openapi.json")
    web_cache = ws.cache_dir("web")

    def authorised(request: Request) -> bool:
        if not token:
            return True
        given = request.cookies.get(COOKIE) or request.headers.get("authorization", "").removeprefix("Bearer ")
        return bool(given) and hmac.compare_digest(given, token)

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        p = request.url.path
        if p.startswith("/api/") and p not in OPEN_PATHS and not authorised(request):
            return JSONResponse({"detail": "login required"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(GeoEyesError)
    async def _error(_: Request, exc: GeoEyesError):
        code = 409 if isinstance(exc, LockedError) else 404 if "no project" in str(exc) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    def project(name: str):
        p = ws.project(name)
        if not p.config.exists():
            raise ConfigError(f"no project {name!r}")
        return p

    def product(name: str, pid: str) -> Path:
        d = project(name).product(pid)
        if not (d / "manifest.json").exists():
            raise HTTPException(404, f"no product {pid!r}")
        return d

    # ------------------------------------------------------------ session
    @app.get("/api/health")
    def health(request: Request):
        from geoeyes import __version__
        return {"ok": True, "version": __version__, "workspace": str(ws.root), "auth_required": bool(token),
                "authenticated": authorised(request)}

    @app.post("/api/login")
    def login(body: dict = Body(...)):
        if not token:
            return {"ok": True}
        given = str(body.get("token", ""))
        if not hmac.compare_digest(given, token):
            raise HTTPException(401, "wrong token")
        r = JSONResponse({"ok": True})
        r.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=30 * 86400)
        return r

    # ------------------------------------------------------------ workspace and projects
    @app.get("/api/workspace")
    def workspace():
        return service.workspace_tree(ws)

    @app.put("/api/folders")
    def put_folders(data: dict = Body(...)):
        return service.save_folders(ws, data)

    @app.post("/api/projects/trash")
    def trash_projects(body: dict = Body(...)):
        """Move projects to <workspace>/trash/ (recoverable); refused while one of them runs."""
        names = [str(n) for n in body.get("names") or []]
        if not names:
            raise HTTPException(400, "names: the projects to move to the trash")
        return {"trashed": service.trash_projects(ws, names), "tree": service.folders(ws)}

    @app.post("/api/projects")
    def create_project(spec: dict = Body(...)):
        return {"name": settings.create(ws, spec)}

    @app.get("/api/projects/{name}")
    def project_detail(name: str):
        return service.project_detail(ws, name)

    @app.get("/api/projects/{name}/settings")
    def project_settings(name: str):
        return settings.describe(project(name))

    @app.patch("/api/projects/{name}/settings")
    def patch_settings(name: str, changes: dict = Body(...)):
        return settings.apply(project(name), changes)

    @app.put("/api/projects/{name}/config")
    def put_config(name: str, body: dict = Body(...)):
        return settings.save_toml(project(name), str(body.get("toml", "")))

    @app.get("/api/projects/{name}/plan")
    def plan(name: str, force: str = ""):
        project(name)
        return {"steps": service.plan(ws, name, [f for f in force.split(",") if f])}

    @app.post("/api/projects/{name}/run")
    def run(name: str, body: dict = Body(default={})):
        project(name)
        return service.start_run(ws, name, tracks=body.get("tracks"), force=body.get("force"),
                                 only=body.get("only"))

    @app.post("/api/projects/{name}/stop")
    def stop(name: str):
        project(name)
        return service.stop_run(ws, name)

    @app.get("/api/projects/{name}/runs/{run_id}/log")
    def run_log(name: str, run_id: str, after: int = 0, debug: bool = False):
        return service.run_log(project(name), run_id, after=after, debug=debug)

    # ------------------------------------------------------------ ASF (new-project wizard)
    @app.post("/api/asf/tracks")
    def asf_tracks(body: dict = Body(...)):
        bbox = body.get("bbox")
        if not bbox or len(bbox) != 4:
            raise HTTPException(400, "bbox: [west, south, east, north]")
        return {"tracks": settings.asf_tracks([float(v) for v in bbox])}

    @app.post("/api/asf/preview")
    def asf_preview(body: dict = Body(...)):
        return settings.asf_preview(body)

    # ------------------------------------------------------------ products
    @app.get("/api/projects/{name}/products/{pid}")
    def product_report(name: str, pid: str):
        d = product(name, pid)
        rep = service._read(d / "report.json")
        return {"id": pid, "brief": service._product_brief(project(name), pid), "report": rep,
                "files": sorted(str(f.relative_to(d).as_posix()) for f in d.rglob("*") if f.is_file())}

    @app.get("/api/projects/{name}/products/{pid}/layer")
    def layer(name: str, pid: str):
        d = product(name, pid)
        m = points.meta(points.ensure(d, web_cache))
        tiles = points.pmtiles_path(d, project(name).export(pid), web_cache, build=False)
        m["tiles"] = {"available": tiles is not None, "recommended": m["n"] > points.TILED_ABOVE,
                      **(_tile_zooms(tiles) if tiles else {})}
        return m

    def _tile_zooms(path: Path) -> dict:
        h = points._reader(str(path)).header
        return {"min_zoom": h["min_zoom"], "max_zoom": h["max_zoom"]}

    @app.post("/api/projects/{name}/products/{pid}/tiles")
    def build_tiles(name: str, pid: str):
        """Build the PMTiles of a product that has none (once; about a minute per million points)."""
        path = points.pmtiles_path(product(name, pid), project(name).export(pid), web_cache)
        return {"available": True, **_tile_zooms(path)}

    @app.get("/api/projects/{name}/products/{pid}/tiles/{z}/{x}/{y}.pbf")
    def get_tile(name: str, pid: str, z: int, x: int, y: int):
        path = points.pmtiles_path(product(name, pid), project(name).export(pid), web_cache, build=False)
        if path is None:
            raise HTTPException(404, "no tiles for this product (POST .../tiles builds them)")
        data = points.tile(path, z, x, y)
        if not data:                                     # outside the product: an empty tile
            return Response(b"", media_type="application/x-protobuf")
        return Response(data, media_type="application/x-protobuf",
                        headers={"Content-Encoding": "gzip", "Cache-Control": "private, max-age=86400"})

    @app.get("/api/projects/{name}/products/{pid}/tiles.pmtiles")
    def get_pmtiles(name: str, pid: str):
        path = points.pmtiles_path(product(name, pid), project(name).export(pid), web_cache)
        return FileResponse(path, filename=f"{pid}.pmtiles", media_type="application/vnd.pmtiles")

    @app.get("/api/projects/{name}/products/{pid}/layer/points.bin")
    def layer_points(name: str, pid: str):
        f = points.ensure(product(name, pid), web_cache) / "points.bin"
        return FileResponse(f, media_type="application/octet-stream",
                            headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/projects/{name}/products/{pid}/layer/points/{i}")
    def layer_point(name: str, pid: str, i: int):
        try:
            return points.point(points.ensure(product(name, pid), web_cache), i)
        except IndexError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.post("/api/projects/{name}/products/{pid}/layer/area")
    def layer_area(name: str, pid: str, body: dict = Body(...)):
        ring = body.get("ring") or []
        if len(ring) < 3:
            raise HTTPException(400, "ring: at least 3 [lon, lat] vertices")
        return points.area(points.ensure(product(name, pid), web_cache), ring)

    @app.get("/api/projects/{name}/products/{pid}/rainfall")
    def product_rainfall(name: str, pid: str):
        """Monthly rainfall (CHIRPS) over the product's extent and period."""
        from datetime import date

        from geoeyes.ancillary.rainfall import monthly
        m = points.meta(points.ensure(product(name, pid), web_cache))
        return monthly(ws.cache_dir("rainfall"), [round(v, 3) for v in m["bounds"]],
                       date.fromisoformat(m["dates"][0]), date.fromisoformat(m["dates"][-1]))

    @app.get("/api/activity")
    def activity():
        """Background analyses of every project (hazard, GNSS) and their state, for the notifications."""
        return {"jobs": jobs.activity(ws)}

    # ------------------------------------------------------------ hazard zoning with rainfall
    @app.get("/api/projects/{name}/products/{pid}/hazard")
    def hazard_status(name: str, pid: str):
        product(name, pid)
        return hazard.status(project(name), pid)

    @app.post("/api/projects/{name}/products/{pid}/hazard")
    def hazard_start(name: str, pid: str, body: dict = Body(default={})):
        """Run ``geoeyes hazard`` on the product in the background; ``params`` override [postprocess.hazard]."""
        from geoeyes.hazard import HazardParams
        product(name, pid)
        overrides = dict(body.get("params") or {})
        HazardParams.from_dict({**dict(load(project(name).config).postprocess.hazard), **overrides})   # validate
        return hazard.start(ws, name, pid, overrides)

    # ------------------------------------------------------------ learning path (one pair, step by step)
    @app.get("/api/projects/{name}/learn")
    def learn_stacks(name: str):
        return learn.stacks(project(name))

    @app.get("/api/projects/{name}/learn/{stack_id}/thumb")
    def learn_thumb_meta(name: str, stack_id: str):
        try:
            return learn.thumb(project(name), stack_id)[0]
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/learn/{stack_id}/thumb.bin")
    def learn_thumb(name: str, stack_id: str):
        try:
            return Response(learn.thumb(project(name), stack_id)[1], media_type="application/octet-stream")
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/learn/{stack_id}/pair")
    def learn_pair_meta(name: str, stack_id: str, request: Request):
        try:
            return learn.pair(project(name), stack_id, dict(request.query_params))[0]
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/learn/{stack_id}/pair.bin")
    def learn_pair(name: str, stack_id: str, request: Request):
        try:
            return Response(learn.pair(project(name), stack_id, dict(request.query_params))[1],
                            media_type="application/octet-stream")
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/learn/{stack_id}/points")
    def learn_points(name: str, stack_id: str, request: Request):
        try:
            return learn.points(project(name), stack_id, dict(request.query_params))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/learn/{stack_id}/ionosphere")
    def learn_ionosphere(name: str, stack_id: str, date: str | None = None):
        try:
            return learn.ionosphere(project(name), stack_id, date)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/learn/series/{pid}/{uid}")
    def learn_series(name: str, pid: str, uid: str):
        product(name, pid)
        return learn.series(project(name), pid, uid)

    @app.get("/api/projects/{name}/products/{pid}/hazard/cells")
    def hazard_cells_meta(name: str, pid: str):
        try:
            return hazard.cells_bin(project(name), pid)[0]
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/hazard/cells.bin")
    def hazard_cells(name: str, pid: str):
        try:
            return Response(hazard.cells_bin(project(name), pid)[1], media_type="application/octet-stream")
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/hazard/cells/{i}")
    def hazard_cell(name: str, pid: str, i: int):
        try:
            return hazard.cell(project(name), pid, i)
        except (FileNotFoundError, IndexError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/hazard/files/{rel}")
    def hazard_file(name: str, pid: str, rel: str):
        f = _inside(hazard.folder(project(name), pid), rel)
        return FileResponse(f, filename=f"{pid}_{f.name}")

    # ------------------------------------------------------------ AI: susceptibility and forecast
    @app.get("/api/projects/{name}/products/{pid}/ai")
    def ai_status(name: str, pid: str):
        product(name, pid)
        return ai.status(project(name), pid)

    @app.post("/api/projects/{name}/products/{pid}/ai/{task}")
    def ai_start(name: str, pid: str, task: str, body: dict = Body(default={})):
        """Run ``geoeyes susceptibility`` / ``geoeyes forecast`` on the product in the background."""
        from geoeyes.ml.forecast import ForecastParams
        from geoeyes.ml.susceptibility import SusceptibilityParams
        product(name, pid)
        if task not in ai.TASKS:
            raise HTTPException(404, f"{task}: susceptibility | forecast")
        overrides = dict(body.get("params") or {})
        cls = SusceptibilityParams if task == "susceptibility" else ForecastParams
        cls.from_dict({**dict(getattr(load(project(name).config).postprocess, task)), **overrides})     # validate
        return ai.start(ws, name, task, pid, overrides)

    def _bin(fn, name: str, pid: str, meta_only: bool):
        try:
            meta, data = fn(project(name), pid)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        return meta if meta_only else Response(data, media_type="application/octet-stream")

    @app.get("/api/projects/{name}/products/{pid}/ai/susceptibility/grid")
    def ai_grid_meta(name: str, pid: str):
        return _bin(ai.susceptibility_grid, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/ai/susceptibility/grid.bin")
    def ai_grid(name: str, pid: str):
        return _bin(ai.susceptibility_grid, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/ai/forecast/cells")
    def ai_forecast_meta(name: str, pid: str):
        return _bin(ai.forecast_cells, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/ai/forecast/cells.bin")
    def ai_forecast_cells(name: str, pid: str):
        return _bin(ai.forecast_cells, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/ai/forecast/cells/{i}")
    def ai_forecast_cell(name: str, pid: str, i: int):
        try:
            return ai.forecast_cell(project(name), pid, i)
        except (FileNotFoundError, IndexError) as exc:
            raise HTTPException(404, str(exc)) from None

    # ------------------------------------------------------------ kinds of motion and risk to buildings
    @app.get("/api/projects/{name}/products/{pid}/behaviour")
    def behaviour_status(name: str, pid: str):
        product(name, pid)
        return behaviour.status(project(name), pid)

    @app.post("/api/projects/{name}/products/{pid}/analysis/{kind}")
    def behaviour_start(name: str, pid: str, kind: str, body: dict = Body(default={})):
        """Run ``geoeyes behaviour`` / ``geoeyes risk`` on the product in the background."""
        from geoeyes.ml.behaviour import BehaviourParams
        from geoeyes.ml.risk import RiskParams
        product(name, pid)
        from geoeyes.ancillary.geology import GeologyParams
        from geoeyes.ml.consolidation import ConsolidationParams
        from geoeyes.ml.decompose import DecomposeParams
        from geoeyes.ml.lines import LinesParams
        classes = {"behaviour": BehaviourParams, "risk": RiskParams, "lines": LinesParams,
                   "consolidation": ConsolidationParams, "decompose": DecomposeParams, "geology": GeologyParams}
        if kind not in classes:
            raise HTTPException(404, f"{kind}: {' | '.join(classes)}")
        overrides = dict(body.get("params") or {})
        cls = classes[kind]
        cls.from_dict({**dict(getattr(load(project(name).config).postprocess, kind)), **overrides})     # validate
        return behaviour.start(ws, name, kind, pid, overrides)

    @app.get("/api/projects/{name}/products/{pid}/behaviour/cells")
    def behaviour_cells_meta(name: str, pid: str):
        return _bin(behaviour.behaviour_cells, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/behaviour/cells.bin")
    def behaviour_cells(name: str, pid: str):
        return _bin(behaviour.behaviour_cells, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/behaviour/cells/{i}")
    def behaviour_cell(name: str, pid: str, i: int):
        try:
            return behaviour.behaviour_cell(project(name), pid, i)
        except (FileNotFoundError, IndexError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/risk/buildings")
    def risk_buildings_meta(name: str, pid: str):
        return _bin(behaviour.risk_buildings, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/risk/buildings.bin")
    def risk_buildings(name: str, pid: str):
        return _bin(behaviour.risk_buildings, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/risk/buildings/{i}")
    def risk_building(name: str, pid: str, i: int):
        try:
            return behaviour.risk_building(project(name), pid, i)
        except (FileNotFoundError, IndexError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/lines/segments")
    def line_segments_meta(name: str, pid: str):
        return _bin(behaviour.line_segments, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/lines/segments.bin")
    def line_segments(name: str, pid: str):
        return _bin(behaviour.line_segments, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/lines/{line}")
    def line_profile(name: str, pid: str, line: int):
        try:
            return behaviour.line_profile(project(name), pid, line)
        except (FileNotFoundError, IndexError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/decompose/cells")
    def decompose_cells_meta(name: str, pid: str):
        return _bin(behaviour.decompose_cells, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/decompose/cells.bin")
    def decompose_cells(name: str, pid: str):
        return _bin(behaviour.decompose_cells, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/geology/cells")
    def geology_cells_meta(name: str, pid: str):
        return _bin(behaviour.geology_cells, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/geology/cells.bin")
    def geology_cells(name: str, pid: str):
        return _bin(behaviour.geology_cells, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/consolidation/cells")
    def consolidation_cells_meta(name: str, pid: str):
        return _bin(behaviour.consolidation_cells, name, pid, True)

    @app.get("/api/projects/{name}/products/{pid}/consolidation/cells.bin")
    def consolidation_cells(name: str, pid: str):
        return _bin(behaviour.consolidation_cells, name, pid, False)

    @app.get("/api/projects/{name}/products/{pid}/consolidation/cells/{i}")
    def consolidation_cell(name: str, pid: str, i: int):
        try:
            return behaviour.consolidation_cell(project(name), pid, i)
        except (FileNotFoundError, IndexError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/buildings")
    def buildings_status(name: str, pid: str):
        product(name, pid)
        return ai.buildings_status(project(name), pid)

    @app.post("/api/projects/{name}/products/{pid}/buildings")
    def buildings_start(name: str, pid: str):
        product(name, pid)
        return ai.start(ws, name, "buildings", pid, {})

    @app.get("/api/projects/{name}/products/{pid}/buildings/stats")
    def buildings_stats(name: str, pid: str, bbox: str):
        b = [float(v) for v in bbox.split(",")]
        if len(b) != 4:
            raise HTTPException(400, "bbox: west,south,east,north")
        try:
            return ai.buildings_in(project(name), pid, b)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    # ------------------------------------------------------------ GNSS comparison and calibration
    @app.get("/api/projects/{name}/products/{pid}/gnss")
    def gnss_status(name: str, pid: str):
        product(name, pid)
        return gnss.status(project(name), pid)

    @app.post("/api/projects/{name}/products/{pid}/gnss")
    def gnss_start(name: str, pid: str, body: dict = Body(default={})):
        """Run ``geoeyes gnss`` on the product in the background; ``params`` override [validation.gnss]."""
        from geoeyes.validation.gnss import GnssParams
        product(name, pid)
        overrides = dict(body.get("params") or {})
        GnssParams.from_dict({**dict(load(project(name).config).validation.gnss), **overrides})       # validate
        return gnss.start(ws, name, pid, overrides)

    @app.get("/api/projects/{name}/products/{pid}/gnss/stations/{site}")
    def gnss_station(name: str, pid: str, site: str):
        try:
            return gnss.station(project(name), pid, site)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/projects/{name}/products/{pid}/files/{rel:path}")
    def product_file(name: str, pid: str, rel: str):
        return FileResponse(_inside(product(name, pid), rel))

    @app.get("/api/projects/{name}/exports/{pid}/{rel:path}")
    def export_file(name: str, pid: str, rel: str):
        f = _inside(project(name).export(pid), rel)
        return FileResponse(f, filename=f.name)

    def _pair(a: str, b: str, cell: float, align: bool):
        fa, fb = [str(points.ensure(product(*_split(x)), web_cache)) for x in (a, b)]
        if not 5 <= cell <= 2000:
            raise HTTPException(400, "cell: 5 to 2000 m")
        return compare.difference(fa, fb, float(cell), bool(align))

    @app.get("/api/compare")
    def compare_meta(a: str, b: str, cell: float = 50, align: bool = True):
        return _pair(a, b, cell, align)[0]

    @app.get("/api/compare.bin")
    def compare_bin(a: str, b: str, cell: float = 50, align: bool = True):
        return Response(_pair(a, b, cell, align)[1], media_type="application/octet-stream")

    # ------------------------------------------------------------ catalog
    @app.get("/api/catalog/search")
    def catalog_search(bbox: str = "", start: str = "", end: str = "", sensor: str = "", all: bool = False,
                       vel_below: float | None = None, vel_above: float | None = None):
        from geoeyes.catalog import search
        b = [float(v) for v in bbox.split(",")] if bbox else None
        if b is not None and len(b) != 4:
            raise HTTPException(400, "bbox: west,south,east,north")
        rows = search(ws, bbox=b, start=start or None, end=end or None, sensor=sensor or None, latest_only=not all,
                      vel_below=vel_below, vel_above=vel_above)
        return {"products": [{k: v for k, v in r.items() if k not in ("item", "points", "timeseries")} for r in rows]}

    @app.post("/api/catalog/build")
    def catalog_build():
        from geoeyes.catalog import build_catalog
        return build_catalog(ws)

    # ------------------------------------------------------------ monitoring
    def _alerts(name: str) -> list[dict]:
        p = project(name)
        out = []
        for t in service.project_summary(ws, name)["tracks"]:
            if t["product"]:
                out += [{**a, "track": t["track_id"]}
                        for a in monitor.evaluate(p, p.product(t["product"]["id"]), web_cache)]
        return out

    @app.get("/api/projects/{name}/monitor")
    def monitoring(name: str):
        p = project(name)
        return {"next": monitor.next_acquisitions(ws, name), "schedule": monitor.get_schedule(name),
                "rules": monitor.rules(p), "alerts": _alerts(name)}

    @app.put("/api/projects/{name}/schedule")
    def put_schedule(name: str, body: dict = Body(...)):
        project(name)
        return monitor.set_schedule(ws, name, str(body.get("frequency", "off")), str(body.get("time", "02:00")),
                                    str(body.get("day", "MON")))

    @app.put("/api/projects/{name}/alerts")
    def put_alerts(name: str, body: dict = Body(...)):
        monitor.save_rules(project(name), list(body.get("rules") or []))
        return {"rules": monitor.rules(project(name)), "alerts": _alerts(name)}

    # ------------------------------------------------------------ validation (corner reflectors)
    @app.get("/api/projects/{name}/validation")
    def validation(name: str):
        root = project(name).root / "validation" / "corner_reflector"
        out = []
        for d in sorted(root.glob("*"), reverse=True) if root.exists() else []:
            rep = service._read(d / "cr_report.json")
            if not d.is_dir() or not rep:
                continue
            out.append({"id": d.name, "pdf": (d / "cr_report.pdf").exists(),
                        "files": sorted(f.name for f in d.iterdir() if f.is_file()), "report": rep})
        p = project(name)
        cr = dict(load(p.config).validation.corner_reflector)
        return {"configured": bool(cr.get("points")), "config": cr, "reports": out,
                "log": service._tail(p.state_dir / service.WEB_CR_LOG, 40)}

    @app.post("/api/projects/{name}/cr-report")
    def cr_report(name: str):
        project(name)
        return service.start_cr_report(ws, name)

    @app.get("/api/projects/{name}/validation/{rid}/{rel}")
    def validation_file(name: str, rid: str, rel: str):
        return FileResponse(_inside(project(name).root / "validation" / "corner_reflector" / rid, rel))

    # ------------------------------------------------------------ front end
    if (STATIC / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):          # an API route this server does not have
                raise HTTPException(404, f"/{path}: no such API route (is the server older than the page?)")
            f = (STATIC / path).resolve()
            if path and f.is_relative_to(STATIC.resolve()) and f.is_file():
                return FileResponse(f)
            # the page names the hashed bundles of the current build: never served from the browser cache
            return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
    return app


def _split(ref: str) -> tuple[str, str]:
    """``project/product_id`` of a compared layer."""
    project, _, pid = ref.partition("/")
    if not project or not pid:
        raise HTTPException(400, f"{ref!r}: expected <project>/<product_id>")
    return project, pid


def serve(ws: WorkspaceLayout, host: str = "127.0.0.1", port: int = DEFAULT_PORT, open_browser: bool = False,
          token: str | None = None) -> None:
    import secrets
    import threading
    import webbrowser

    import uvicorn
    local = host in ("127.0.0.1", "localhost", "::1")
    if not local and not token:
        token = secrets.token_urlsafe(18)
    url = f"http://{'localhost' if local else host}:{port}"
    print(f"GeoEyes web app on {url}  (workspace {ws.root}; Ctrl+C to stop)")
    if token:
        print(f"  login token: {token}" + ("" if local else "  (set GEOEYES_WEB_TOKEN to choose it)"))
    if not (STATIC / "index.html").exists():
        print("  front end not built: cd webapp && npm install && npm run build  (API only meanwhile)")
    if open_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(ws, token=token), host=host, port=port, log_level="warning")


__all__ = ["DEFAULT_PORT", "create_app", "serve"]
