import tomllib

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("tomlkit")

from fastapi.testclient import TestClient  # noqa: E402

from geoeyes.api import create_app  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402

TOML = """# my comment, kept by edits
schema = "geoeyes.project/1"

[project]
name = "alpha"
method = "psi"

[aoi]
bbox = [-99.01, 19.29, -98.98, 19.32]   # inline comment

[[tracks]]
sensor = "sentinel1"
direction = "ascending"
relative_orbit = 78

[acquire]
max_per_month = 3
"""


@pytest.fixture
def ws(tmp_path):
    w = WorkspaceLayout.at(tmp_path / "ws")
    p = w.project("alpha").ensure()
    p.config.write_text(TOML, encoding="utf-8")
    return w


def _field(spec, section, key):
    sec = next(s for s in spec["sections"] if s["name"] == section)
    return next(f for f in sec["fields"] if f["key"] == key)


def test_settings_form_edit_keeps_comments_and_backs_up(ws):
    c = TestClient(create_app(ws))
    spec = c.get("/api/projects/alpha/settings").json()
    f = _field(spec, "acquire", "max_per_month")
    assert (f["kind"], f["value"], f["default"], f["own"]) == ("int", 3, 0, True)
    assert _field(spec, "acquire", "date_range")["kind"] == "daterange"
    assert _field(spec, "phase_linking", "shp_test")["default"] == "ad"
    assert _field(spec, "ps", "unwrap_grid_size")["value"] == 10
    r = c.patch("/api/projects/alpha/settings", json={"acquire.max_per_month": None,
                                                       "acquire.date_range": ["2024-01-01", "2024-06-30"],
                                                       "ps.unwrap_grid_size": 20, "stack.esd": False})
    assert r.status_code == 200, r.text
    text = ws.project("alpha").config.read_text(encoding="utf-8")
    assert "# my comment, kept by edits" in text and "# inline comment" in text
    data = tomllib.loads(text)
    assert "max_per_month" not in data["acquire"] and str(data["acquire"]["date_range"][0]) == "2024-01-01"
    assert data["ps"]["unwrap_grid_size"] == 20 and data["stack"]["esd"] is False
    assert len(list(ws.project("alpha").state_dir.glob("project.toml.*.bak"))) == 1
    # invalid values are refused and the file is left as it was
    bad = c.patch("/api/projects/alpha/settings", json={"acquire.max_per_month": -2})
    assert bad.status_code == 400 and ws.project("alpha").config.read_text(encoding="utf-8") == text
    assert c.patch("/api/projects/alpha/settings", json={"legacy.x": 1}).status_code == 400


def test_raw_toml_save_validates(ws):
    c = TestClient(create_app(ws))
    assert c.put("/api/projects/alpha/config", json={"toml": "not = [toml"}).status_code == 400
    renamed = TOML.replace('name = "alpha"', 'name = "beta"')
    assert "must stay 'alpha'" in c.put("/api/projects/alpha/config", json={"toml": renamed}).json()["detail"]
    ok = TOML.replace("max_per_month = 3", "max_per_month = 2")
    assert c.put("/api/projects/alpha/config", json={"toml": ok}).status_code == 200
    assert "max_per_month = 2" in ws.project("alpha").config.read_text(encoding="utf-8")


def test_create_project_into_a_folder(ws):
    c = TestClient(create_app(ws))
    spec = {"name": "new_one", "folder": "Mexico/City", "description": "test", "method": "psi",
            "track": {"sensor": "sentinel1", "direction": "descending", "relative_orbit": 143},
            "bbox": [-99.2, 19.3, -99.0, 19.5], "date_range": ["2024-01-01", "2024-12-31"], "max_per_month": 2,
            "atmosphere": "era5"}
    assert c.post("/api/projects", json=spec).json() == {"name": "new_one"}
    data = tomllib.loads(ws.project("new_one").config.read_text(encoding="utf-8"))
    assert data["tracks"][0]["relative_orbit"] == 143 and data["atmosphere"]["method"] == "era5"
    assert str(data["acquire"]["date_range"][1]) == "2024-12-31"
    tree = c.get("/api/workspace").json()["tree"]
    assert tree["folders"][0]["name"] == "Mexico" and tree["folders"][0]["folders"][0]["projects"] == ["new_one"]
    assert c.post("/api/projects", json=spec).status_code == 400                     # exists
    assert c.post("/api/projects", json={**spec, "name": "Bad Name"}).status_code == 400
    assert not (ws.projects / "Bad Name").exists()


def test_difference_of_two_point_sets(tmp_path):
    from geoeyes.api import compare
    rng = np.random.default_rng(0)
    folders = []
    for k, shift in enumerate((0.0, 5.0)):
        f = tmp_path / f"p{k}"
        f.mkdir()
        lon, lat = -99 + 0.01 * rng.random(4000), 19.3 + 0.01 * rng.random(4000)
        vel = (100 * (lon + 99) + shift).astype(np.float32)                # same field, B offset by +5
        np.savez(f / "attrs.npz", lon=lon, lat=lat, vel=vel)
        np.save(f / "ts.npy", np.zeros((4000, 2), np.float32))
        folders.append(str(f))
    meta, buf = compare.difference(*folders, cell_m=100.0, align=False)
    assert meta["n"] > 50 and abs(meta["stats"]["median"] - 5.0) < 0.2 and meta["stats"]["corr"] > 0.95
    assert len(buf) == meta["n"] * 5 * 4
    aligned, _ = compare.difference(*folders, cell_m=100.0, align=True)
    assert abs(aligned["offset"] - 5.0) < 0.2 and abs(aligned["stats"]["median"]) < 1e-6


def test_token_login_when_exposed(ws):
    c = TestClient(create_app(ws, token="s3cret"))
    assert c.get("/api/workspace").status_code == 401
    h = c.get("/api/health").json()
    assert h["auth_required"] and not h["authenticated"]
    assert c.post("/api/login", json={"token": "nope"}).status_code == 401
    assert c.post("/api/login", json={"token": "s3cret"}).status_code == 200            # sets the cookie
    assert c.get("/api/workspace").status_code == 200
    other = TestClient(create_app(ws, token="s3cret"))
    assert other.get("/api/workspace", headers={"Authorization": "Bearer s3cret"}).status_code == 200
