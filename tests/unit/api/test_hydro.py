"""River network and watersheds over a view (ancillary/hydro.py, /api/hydro/*): views snapped to the cache grid,
too-large views refused, OSM ways turned into LineStrings, answers cached on disk."""
import pytest

from geoeyes.ancillary import hydro
from geoeyes.core.errors import DataError

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from geoeyes.api import create_app  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402


def test_snap_and_limits():
    assert hydro.snap([106.5605, 10.6867, 106.7095, 10.7795]) == [106.55, 10.65, 106.75, 10.8]
    with pytest.raises(DataError):
        hydro.snap([100.0, 10.0, 108.0, 12.0])                  # wider than MAX_DEG
    with pytest.raises(DataError):
        hydro.snap([106.7, 10.7, 106.6, 10.8])                  # west > east
    assert hydro._region([106.5, 10.6, 106.8, 10.8]) == "as" and hydro._region([-99.2, 19.2, -98.9, 19.5]) == "na"


def test_rivers_from_osm_ways(tmp_path, monkeypatch):
    seen = {}

    def fake_overpass(query, cache, progress, what):
        seen["q"] = query
        return [{"id": 1, "tags": {"waterway": "canal", "name": "Kênh Tẻ"},
                 "geometry": [{"lon": 106.70, "lat": 10.75}, {"lon": 106.71, "lat": 10.751}]},
                {"id": 2, "tags": {"waterway": "drain"}, "geometry": [{"lon": 106.70, "lat": 10.75}]}]   # 1 node: dropped
    monkeypatch.setattr("geoeyes.ml.lines.overpass", fake_overpass)
    fc = hydro.rivers([106.69, 10.74, 106.72, 10.76], tmp_path)
    assert [f["properties"] for f in fc["features"]] == [{"kind": "canal", "name": "Kênh Tẻ"}]
    assert "drain" in seen["q"] and fc["bbox"] == [106.65, 10.7, 106.75, 10.8]
    hydro.rivers([104.0, 10.0, 106.0, 11.0], tmp_path)          # a wide view: rivers and canals only
    assert "drain" not in seen["q"] and "canal" in seen["q"]


def test_api_caches_and_refuses(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(hydro, "rivers", lambda b, c: calls.append(b) or {"type": "FeatureCollection", "features": []})
    c = TestClient(create_app(WorkspaceLayout.at(tmp_path / "ws")))
    assert c.get("/api/hydro/rivers?bbox=106.6,10.7,106.7,10.8").status_code == 200
    assert c.get("/api/hydro/rivers?bbox=106.61,10.71,106.69,10.79").status_code == 200    # same snapped view
    assert len(calls) == 1
    assert c.get("/api/hydro/rivers?bbox=1,2,3").status_code == 400
    assert c.get("/api/hydro/basins?bbox=90,0,110,20").status_code == 422
