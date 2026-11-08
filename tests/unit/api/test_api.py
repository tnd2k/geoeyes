import functools
import json

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from geoeyes.api import create_app  # noqa: E402
from geoeyes.controller.phase import ProjectState  # noqa: E402
from geoeyes.io.manifest import InputRef, Manifest  # noqa: E402
from geoeyes.io.points import write_points, write_timeseries  # noqa: E402
from geoeyes.products.builder import build_product as _build_product  # noqa: E402
from geoeyes.products.spatial_filter import SpatialFilter  # noqa: E402

# the points here are scattered white noise (every point traceable by its row): no spatial filter
build_product = functools.partial(_build_product, spatial=SpatialFilter(enabled=False))
from geoeyes.workspace import WorkspaceLayout  # noqa: E402

TOML = """schema = "geoeyes.project/1"
[project]
name = "{name}"
method = "psi"
description = "test project"
[aoi]
bbox = [-99.01, 19.29, -98.98, 19.32]
[[tracks]]
sensor = "sentinel1"
direction = "ascending"
relative_orbit = 78
"""
TRACK = "sentinel1-asc-078"


def _ps_run(root, n=80, kinds=False, coherence=None):
    import geopandas as gpd
    run = root / "ps_runs" / TRACK
    rng = np.random.default_rng(3)
    lon, lat = -99.0 + 0.01 * rng.random(n), 19.3 + 0.01 * rng.random(n)
    uid = np.array([f"{TRACK}:{(7 * i) % n:05d}" for i in range(n)])        # not in sorted order on purpose
    vel = rng.normal(-5, 8, n).astype(np.float32)
    # the StaMPS velocity kinds (ps engine): the product velocity is v-dao
    extra = {"vel_do_mm_yr": vel + 3, "vel_dao_mm_yr": vel, "vel_dso_mm_yr": vel / 2} if kinds else {}
    gdf = gpd.GeoDataFrame({"point_uid": uid, "lon": lon, "lat": lat, "height_m": np.float32(2240),
                            "dem_err_m": np.float32(0), "type": "PS", "vel_los_mm_yr": vel,
                            "temporal_coherence": np.float32(0.9) if coherence is None else coherence,
                            "amp_dispersion": np.float32(0.2),
                            "fit_rmse_mm": np.float32(1), "incidence_deg": np.float32(38), **extra},
                           geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    write_points(run / "points.parquet", gdf)
    dates = np.arange(np.datetime64("2024-05-03"), np.datetime64("2024-11-01"), 12)
    disp = np.arange(n)[:, None] + 0.001 * np.arange(dates.size)[None, :]     # row i: value ≈ i (traceable)
    write_timeseries(run / "timeseries.parquet", uid, dates, disp)
    m = Manifest(kind="ps_run", id=TRACK, engine="geoeyes-ps/2", inputs=[InputRef("stack", "", "")],
                 metrics={"reference_date": "2024-07-14"})
    m.add_outputs(run, ["points.parquet"])
    m.write(run)
    return run, uid, lon, lat, dates


@pytest.fixture
def ws(tmp_path):
    w = WorkspaceLayout.at(tmp_path / "ws")
    for name in ("alpha", "beta"):
        p = w.project(name).ensure()
        p.config.write_text(TOML.format(name=name), encoding="utf-8")
    return w


def test_workspace_tree_folders_and_status(ws):
    c = TestClient(create_app(ws))
    d = c.get("/api/workspace").json()
    assert d["tree"] == {"folders": [], "projects": ["alpha", "beta"]}
    assert d["projects"]["alpha"]["status"] == "new" and d["projects"]["alpha"]["tracks"][0]["track_id"] == TRACK
    tree = {"folders": [{"name": "Mexico", "projects": ["beta", "gone"], "folders": []}], "projects": []}
    r = c.put("/api/folders", json=tree).json()
    assert r == {"folders": [{"name": "Mexico", "projects": ["beta"], "folders": []}], "projects": ["alpha"]}
    assert json.loads((ws.projects / ".folders.json").read_text(encoding="utf-8"))["folders"][0]["name"] == "Mexico"
    assert c.put("/api/folders", json={"folders": [{"name": " "}]}).status_code == 400
    # a phase left "running" by a killed run, without a live lock, is shown as interrupted
    ProjectState(ws.project("alpha")).set(TRACK, "build_stack", status="running", run_id="x")
    assert c.get("/api/workspace").json()["projects"]["alpha"]["status"] == "interrupted"
    assert c.get("/api/projects/nope").status_code == 404


def test_product_layer_points_and_area_series(ws):
    proj = ws.project("alpha")
    run, uid, lon, lat, dates = _ps_run(proj.root)
    r = build_product(run, proj.root / "products", project="alpha", track_id=TRACK)
    ProjectState(proj).set(TRACK, "build_product", status="done", run_id="r1", result={"product_id": r["product_id"]})
    c = TestClient(create_app(ws))
    s = c.get("/api/workspace").json()["projects"]["alpha"]
    assert s["status"] == "done" and s["tracks"][0]["product"]["n_points"] == 80
    pid = r["product_id"]
    meta = c.get(f"/api/projects/alpha/products/{pid}/layer").json()
    assert meta["n"] == 80 and len(meta["dates"]) == dates.size
    assert meta["classes"][0]["lo"] == pytest.approx(meta["vel_min"]) and sum(k["count"] for k in meta["classes"]) == 80
    buf = np.frombuffer(c.get(f"/api/projects/alpha/products/{pid}/layer/points.bin").content, np.float32).reshape(-1, 3)
    np.testing.assert_allclose(buf[:, 0] + meta["origin"][0], lon, atol=1e-5)
    p = c.get(f"/api/projects/alpha/products/{pid}/layer/points/5").json()
    assert len(p["disp_mm"]) == dates.size and p["lon"] == pytest.approx(lon[5], abs=1e-6)
    assert c.get(f"/api/projects/alpha/products/{pid}/layer/points/80").status_code == 404
    ring = [[-99.01, 19.29], [-98.98, 19.29], [-98.98, 19.32], [-99.01, 19.32]]
    a = c.post(f"/api/projects/alpha/products/{pid}/layer/area", json={"ring": ring}).json()
    assert a["n"] == 80 and len(a["mean_mm"]) == dates.size
    assert c.get(f"/api/projects/alpha/products/{pid}/files/../../project.toml").status_code == 404
    assert c.get(f"/api/projects/alpha/products/{pid}/files/item.json").status_code == 200


def test_layer_coherence_and_filtered_hexagons(ws):
    """The coherence slider: coherence per point in the order of points.bin; hexagons binned above a threshold."""
    proj = ws.project("alpha")
    run, *_ = _ps_run(proj.root, n=200, coherence=np.linspace(0.3, 0.99, 200).astype(np.float32))
    pid = build_product(run, proj.root / "products", project="alpha", track_id=TRACK)["product_id"]
    c = TestClient(create_app(ws))
    base = f"/api/projects/alpha/products/{pid}/layer"
    n = c.get(base).json()["n"]
    coh = np.frombuffer(c.get(f"{base}/coherence.bin").content, np.float32)
    assert coh.size == n and np.nanmin(coh) == pytest.approx(0.3, abs=1e-3)
    size = c.get(base).json()["hex_sizes"][0]
    count = lambda q: int(np.frombuffer(c.get(f"{base}/hex.bin?size={size}{q}").content, np.float32).reshape(-1, 4)[:, 3].sum())  # noqa: E731
    assert count("") == n
    assert count("&coh=0.7") == int((coh >= 0.7).sum())
    assert c.get(f"{base}/hex.bin?size={size}&coh=1.5").status_code == 400


def test_layer_velocity_kinds(ws):
    """The map can show v-do, v-dao or v-dso of a ps product; the product velocity is recognised as v-dao."""
    proj = ws.project("alpha")
    run, *_ = _ps_run(proj.root, kinds=True)
    pid = build_product(run, proj.root / "products", project="alpha", track_id=TRACK)["product_id"]
    c = TestClient(create_app(ws))
    base = f"/api/projects/alpha/products/{pid}/layer"
    m = c.get(base).json()
    assert m["velocity_kinds"] == ["do", "dao", "dso"] and m["product_kind"] == "dao" and m["velocity_kind"] is None
    v0 = np.frombuffer(c.get(f"{base}/points.bin").content, np.float32).reshape(-1, 3)[:, 2]
    md = c.get(f"{base}?vel=do").json()
    assert md["velocity_kind"] == "do" and md["vel_min"] == pytest.approx(m["vel_min"] + 3, abs=1e-4)
    vd = np.frombuffer(c.get(f"{base}/points.bin?vel=do").content, np.float32).reshape(-1, 3)[:, 2]
    np.testing.assert_allclose(vd, v0 + 3, atol=1e-4)
    vs = np.frombuffer(c.get(f"{base}/points.bin?vel=dso").content, np.float32).reshape(-1, 3)[:, 2]
    np.testing.assert_allclose(vs, v0 / 2, atol=1e-4)
    assert c.get(f"{base}/points/3?vel=do").json()["vel"] == pytest.approx(vd[3], abs=1e-4)
    assert c.get(f"{base}?vel=xyz").status_code == 404
    # a product without the kinds offers none
    beta = ws.project("beta")
    run_b, *_ = _ps_run(beta.root)
    pid_b = build_product(run_b, beta.root / "products", project="beta", track_id=TRACK)["product_id"]
    assert c.get(f"/api/projects/beta/products/{pid_b}/layer").json()["velocity_kinds"] == []
    assert c.get(f"/api/projects/beta/products/{pid_b}/layer?vel=do").status_code == 404


def test_point_series_follow_the_point_order(ws):
    """Each map point carries the series written for it, whatever the uid order."""
    from geoeyes.api import points
    proj = ws.project("beta")
    run, uid, *_ = _ps_run(proj.root)
    r = build_product(run, proj.root / "products", project="beta", track_id=TRACK)
    prod = proj.product(r["product_id"])
    import pyarrow.parquet as pq
    uid_prod = pq.read_table(prod / "points.parquet", columns=["point_uid"])["point_uid"].to_pylist()
    ts = pq.read_table(prod / "timeseries.parquet").to_pandas()
    first = ts.sort_values("date").groupby("point_uid")["disp_mm"].first()
    folder = points.ensure(prod, ws.cache_dir("web"))
    for i in (0, 7, 41):
        assert points.point(folder, i)["disp_mm"][0] == pytest.approx(first[uid_prod[i]], abs=1e-3)


def test_run_log_and_runs(ws):
    proj = ws.project("alpha")
    rdir = proj.run("20261025T010000")
    rdir.mkdir(parents=True)
    lines = [{"ts": "2026-10-25T01:00:00+00:00", "level": "INFO", "msg": "start", "phase": "ps"},
             {"ts": "2026-10-25T01:00:01+00:00", "level": "DEBUG", "msg": "noise"},
             {"ts": "2026-10-25T01:00:02+00:00", "level": "ERROR", "msg": "boom", "phase": "ps"}]
    (rdir / "log.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines) + '{"partial', encoding="utf-8")
    c = TestClient(create_app(ws))
    r = c.get("/api/projects/alpha/runs/20261025T010000/log").json()
    assert [x["msg"] for x in r["lines"]] == ["start", "boom"] and r["next"] == 3     # partial line not consumed
    assert c.get("/api/projects/alpha/runs/20261025T010000/log?after=3").json()["lines"] == []
    d = c.get("/api/projects/alpha").json()
    assert d["runs"][0] == {"id": "20261025T010000", "status": "interrupted", "phases": [], "seconds": None,
                            "error": None}
    assert {s["key"] for s in d["settings"]} >= {"aoi.bbox", "ps.unwrap_grid_size"}
    assert next(s for s in d["settings"] if s["key"] == "aoi.bbox")["own"] is True


def test_trash_projects(ws):
    """Projects go to <workspace>/trash/ (recoverable) and leave the tree; unknown names change nothing."""
    c = TestClient(create_app(ws))
    c.put("/api/folders", json={"folders": [{"name": "Region", "projects": ["alpha", "beta"], "folders": []}],
                                "projects": []})
    assert c.post("/api/projects/trash", json={"names": ["alpha", "nope"]}).status_code == 404
    assert ws.project("alpha").config.exists()
    r = c.post("/api/projects/trash", json={"names": ["alpha"]}).json()
    assert [x["name"] for x in r["trashed"]] == ["alpha"]
    assert not ws.project("alpha").root.exists()
    moved = list((ws.root / "trash").glob("alpha__*"))
    assert len(moved) == 1 and (moved[0] / "project.toml").exists()
    assert r["tree"] == {"folders": [{"name": "Region", "projects": ["beta"], "folders": []}], "projects": []}
    assert c.post("/api/projects/trash", json={"names": []}).status_code == 400
