"""Site advisor endpoints (site advisor V3): project and bbox, with the profile readers replaced (no network)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from geoeyes.advisor import profile as prof  # noqa: E402
from geoeyes.api import create_app  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402

TOML = """schema = "geoeyes.project/1"

[project]
name = "delta"
method = "psi"

[aoi]
bbox = [106.56, 10.69, 106.71, 10.78]

[[tracks]]
sensor = "sentinel1"
direction = "descending"
relative_orbit = 18

[acquire]
max_per_month = 2
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(prof, "terrain_part", lambda grid, dem, cache: {
        "source": dem, "cell_m": 30, "relief_m": 11.0, "slope_median_deg": 2.0, "steep_share": 0.0,
        "very_steep_share": 0.0})
    monkeypatch.setattr(prof, "land_cover_part", lambda grid: {
        "source": "test", "shares": {"built": 0.58, "tree": 0.17, "crop": 0.09, "grass": 0.08, "water": 0.03},
        "dominant": "built"})
    monkeypatch.setattr(prof, "geology_part", lambda grid, z: {
        "source": "test", "shares": {"su": 1.0}, "names": {"su": "unconsolidated sediments"}, "dominant": "su",
        "soft_share": 1.0})
    monkeypatch.setattr(prof, "climate_part", lambda bbox, cache: {
        "source": "test", "years": [2016, 2025], "koppen": "Aw", "rain_annual_mm": 1887, "wet_months": [5, 6],
        "rh_mean_pct": 80, "temp_mean_c": 27})
    ws = WorkspaceLayout.at(tmp_path / "ws")
    p = ws.project("delta").ensure()
    p.config.write_text(TOML, encoding="utf-8")
    return TestClient(create_app(ws))


def test_project_advise_compares_with_the_configuration(client):
    r = client.get("/api/projects/delta/advise")
    assert r.status_code == 200, r.text
    a = r.json()
    ids = {m["id"] for m in a["matched"]}
    assert {"flat-no-height-aps", "urban-psi", "soft-urban-subsidence", "hcmc-grid"} <= ids
    changes = {c["path"]: c for c in a["compare"]["changes"]}
    assert changes["acquire.max_per_month"]["current"] == 2 and changes["acquire.max_per_month"]["suggested"] == 0
    assert changes["ps.unwrap_grid_size"]["suggested"] == 50
    assert a["summary"]["vi"][1].startswith("  Địa hình")
    assert all(x["why"]["en"] and x["why"]["vi"] for x in a["recipe"])


def test_applying_the_changes_through_the_settings_endpoint(client):
    a = client.get("/api/projects/delta/advise").json()
    todo = {c["path"]: c["suggested"] for c in a["compare"]["changes"]}
    r = client.patch("/api/projects/delta/settings", json=todo)
    assert r.status_code == 200, r.text
    after = client.get("/api/projects/delta/advise").json()
    assert after["compare"]["changes"] == []


def test_bbox_advise_without_a_project(client):
    r = client.post("/api/advise", json={"bbox": [106.56, 10.69, 106.71, 10.78]})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["compare"] is None and any(x["path"] == "ps.subtr_tropo" for x in a["recipe"])
    assert client.post("/api/advise", json={"bbox": [1, 2]}).status_code == 400
