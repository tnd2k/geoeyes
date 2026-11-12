"""Field landslide surveys: import (attributes kept, WGS84 2D, ids) and the map collection with reported events."""
import json
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import Point

from geoeyes.core.errors import DataError
from geoeyes.landslide.surveys import collection, import_survey, signature


def _survey(tmp_path, ids=("QL6-124+300", "QL6-128+400")):
    df = gpd.GeoDataFrame({"name": ["124+300", "128+400"], "id": list(ids), "risk_level": ["Rất cao", "Cao"],
                           "landslide_width": [50.0, float("nan")], "photo": [None, " "]},
                          geometry=[Point(105.1035, 20.6780, 12.0), Point(105.0811, 20.6811, 9.0)], crs=4326)
    f = tmp_path / "Điểm trượt.gpkg"
    df.to_file(f, layer="Điểm trượt", driver="GPKG")
    return f


def test_import_keeps_the_attributes(tmp_path):
    ws = SimpleNamespace(root=tmp_path)
    r = import_survey(ws, _survey(tmp_path), "ql6")
    assert r["features"] == 2 and "risk_level" in r["fields"]
    fc = json.loads((tmp_path / "inventories/landslide/surveys/ql6.geojson").read_text(encoding="utf-8"))
    f = fc["features"][0]
    assert f["id"] == "ql6:QL6-124+300"
    assert f["geometry"]["coordinates"] == pytest.approx([105.1035, 20.6780])         # Z dropped
    assert f["properties"]["risk_level"] == "Rất cao" and f["properties"]["layer"] == "ql6"
    assert fc["features"][1]["properties"]["landslide_width"] is None                    # NaN -> null
    assert fc["features"][1]["properties"]["photo"] is None                              # blank -> null


def test_duplicate_ids_are_numbered(tmp_path):
    ws = SimpleNamespace(root=tmp_path)
    import_survey(ws, _survey(tmp_path, ids=("a", "a")), "s")
    fc = collection(ws)
    assert [f["id"] for f in fc["features"]] == ["s:1", "s:2"]


def test_collection_adds_the_reported_events(tmp_path):
    ws = SimpleNamespace(root=tmp_path)
    import_survey(ws, _survey(tmp_path), "ql6")
    rep = tmp_path / "inventories/landslide/vietnam.geojson"
    rep.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [105.0, 20.7]}, "properties": {"id": "x1"}},
        {"type": "Feature", "geometry": None, "properties": {"id": "x2"}}]}), encoding="utf-8")
    fc = collection(ws)
    assert [(l["layer"], l["n"]) for l in fc["layers"]] == [("ql6", 2), ("reported", 1)]
    assert fc["features"][-1]["id"] == "reported:x1" and fc["features"][-1]["properties"]["layer"] == "reported"
    assert "vietnam.geojson" in signature(ws)


def test_missing_file(tmp_path):
    with pytest.raises(DataError):
        import_survey(SimpleNamespace(root=tmp_path), tmp_path / "none.gpkg")
