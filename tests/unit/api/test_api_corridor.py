"""Corridor brush API (K2): preview, route import, a project's corridor (save, read, clear), a new project drawn
with the brush."""
import base64
import json
import math
import tomllib

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("tomlkit")

from fastapi.testclient import TestClient  # noqa: E402

from geoeyes.api import create_app  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402

TOML = """# kept comment
schema = "geoeyes.project/1"

[project]
name = "alpha"
method = "psds"

[aoi]
bbox = [104.9, 20.6, 105.2, 20.8]

[[tracks]]
sensor = "sentinel1"
direction = "ascending"
relative_orbit = 128
"""
LAT = 20.69
KM = 1 / (111.32 * math.cos(math.radians(LAT)))
STROKE = [[105.0, LAT], [105.0 + 5 * KM, LAT], [105.0 + 5 * KM, LAT + 0.02]]


@pytest.fixture
def ws(tmp_path):
    w = WorkspaceLayout.at(tmp_path / "ws")
    p = w.project("alpha").ensure()
    p.config.write_text(TOML, encoding="utf-8")
    return w


def test_preview(ws):
    c = TestClient(create_app(ws))
    r = c.post("/api/corridor/preview", json={"strokes": [STROKE], "width_m": 500}).json()
    assert r["geometry"]["type"] == "Polygon" and r["info"]["parts"] == 1
    assert r["info"]["length_km"] == pytest.approx(5 + 0.02 * 110.57, rel=0.02)
    assert r["bbox"][0] < 105.0 and r["bbox"][3] > LAT + 0.02
    assert c.post("/api/corridor/preview", json={"strokes": []}).json()["geometry"] is None
    assert c.post("/api/corridor/preview", json={"strokes": [STROKE], "width_m": 5}).status_code == 400


def test_import_geojson_route(ws):
    c = TestClient(create_app(ws))
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": STROKE}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [
            [[105.1, 20.7], [105.11, 20.7], [105.11, 20.71], [105.1, 20.7]]]}}]}
    data = base64.b64encode(json.dumps(fc).encode()).decode()
    r = c.post("/api/corridor/import", json={"name": "ql6.geojson", "data_b64": data}).json()
    assert len(r["strokes"]) == 1 and len(r["polygons"]) == 1 and r["points"] == 3
    assert c.post("/api/corridor/import", json={"name": "x.txt", "data_b64": data}).status_code == 400


def test_project_corridor_save_read_clear(ws):
    c = TestClient(create_app(ws))
    assert c.get("/api/projects/alpha/corridor").json() == {"corridor": None}
    r = c.put("/api/projects/alpha/corridor", json={"strokes": [STROKE], "erase": [], "width_m": 1000}).json()
    assert r["file"] == "corridor.geojson"
    text = ws.project("alpha").config.read_text(encoding="utf-8")
    assert "# kept comment" in text
    aoi = tomllib.loads(text)["aoi"]
    assert aoi["corridor"] == "corridor.geojson" and aoi["bbox"] == r["bbox"]
    got = c.get("/api/projects/alpha/corridor").json()["corridor"]
    assert got["problem"] is None and got["info"]["source"]["strokes"] == [STROKE]
    assert got["geometry"]["type"] == "Polygon"
    c.delete("/api/projects/alpha/corridor")
    assert "corridor" not in tomllib.loads(ws.project("alpha").config.read_text(encoding="utf-8"))["aoi"]


def test_new_project_with_a_corridor(ws):
    c = TestClient(create_app(ws))
    spec = {"name": "ql6", "method": "psds", "track": {"sensor": "sentinel1", "direction": "ascending",
                                                       "relative_orbit": 128},
            "bbox": [0, 0, 1, 1], "corridor": {"strokes": [STROKE], "width_m": 1000}}
    assert c.post("/api/projects", json=spec).json() == {"name": "ql6"}
    p = ws.project("ql6")
    aoi = tomllib.loads(p.config.read_text(encoding="utf-8"))["aoi"]
    assert aoi["corridor"] == "corridor.geojson" and aoi["bbox"][0] < 105.0 < aoi["bbox"][2]   # bbox from the corridor
    assert (p.root / "corridor.geojson").exists()
