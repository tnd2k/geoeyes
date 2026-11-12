"""Processing corridor (K1): buffered strokes in metres, joins and erasing, route files, the [aoi] checks, burst
selection by footprint."""
import math
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.geometry import corridor as C

LAT = 20.69
KM_LON = 1 / (111.32 * math.cos(math.radians(LAT)))      # degrees of longitude per km


def _line(x0_km, x1_km, lat=LAT):
    return [[105.0 + x0_km * KM_LON, lat], [105.0 + x1_km * KM_LON, lat]]


def test_area_is_the_buffer_in_metres():
    g, info = C.build([_line(0, 10)], 1000)
    # 10 km x 1 km plus the two half-discs of the round caps
    assert info["area_km2"] == pytest.approx(10 * 1 + math.pi * 0.5 ** 2, rel=0.01)
    assert info["length_km"] == pytest.approx(10, rel=0.01)
    assert info["parts"] == 1 and g.geom_type == "Polygon"


def test_strokes_join_and_erase():
    _, apart = C.build([_line(0, 4), _line(6, 10)], 1000)
    assert apart["parts"] == 2
    _, joined = C.build([_line(0, 4), _line(4.3, 10)], 1000)      # gap 300 m < 1 km width: one corridor
    assert joined["parts"] == 1
    _, cut = C.build([_line(0, 10)], 1000, erase=[[[105.0 + 5 * KM_LON, LAT - 0.02], [105.0 + 5 * KM_LON, LAT + 0.02]]])
    assert cut["parts"] == 2 and cut["area_km2"] < joined["area_km2"]
    with pytest.raises(DataError):
        C.build([_line(0, 1)], 1000, erase=[_line(-2, 3)])


def test_width_limits():
    with pytest.raises(ConfigError):
        C.build([_line(0, 1)], 10)
    with pytest.raises(DataError):
        C.build([], 1000)


def test_route_file_round_trip(tmp_path):
    f = tmp_path / "route.gpkg"
    gpd.GeoDataFrame({"name": ["QL6"]}, geometry=[LineString(_line(0, 5))], crs=4326).to_file(f, driver="GPKG")
    g, info = C.from_file(f, 500)
    assert info["area_km2"] == pytest.approx(5 * 0.5 + math.pi * 0.25 ** 2, rel=0.01)
    out = C.write(tmp_path / C.FILE, g, info, {"kind": "file"})
    back = C.read(out)
    assert back.symmetric_difference(g).area < 1e-12
    assert C.digest(back) == C.digest(g)
    w, s, e, n = C.bbox_of(g)
    assert w < g.bounds[0] and n > g.bounds[3]


def test_problem_checks_the_file_and_the_bbox(tmp_path):
    g, info = C.build([_line(0, 5)], 1000)
    C.write(tmp_path / C.FILE, g, info)
    cfg = lambda bbox, corr=C.FILE: SimpleNamespace(aoi=SimpleNamespace(bbox=bbox, corridor=corr))  # noqa: E731
    assert C.problem(cfg(C.bbox_of(g)), tmp_path) is None
    assert "outside" in C.problem(cfg([105.0, 20.6, 105.01, 20.8]), tmp_path)
    assert "cannot read" in C.problem(cfg(C.bbox_of(g), "missing.geojson"), tmp_path)
    assert C.problem(cfg(None, ""), tmp_path) is None
    assert C.of_project(cfg(None, ""), tmp_path) is None


def test_footprint_hits():
    g, _ = C.build([_line(0, 5)], 1000)
    near = box(105.0 + 2 * KM_LON, LAT + 0.004, 105.0 + 3 * KM_LON, LAT + 0.05).wkt      # ~0 m away after buffer
    far = box(105.0, LAT + 0.1, 105.05, LAT + 0.2).wkt
    assert C.footprint_hits(near, g) and not C.footprint_hits(far, g) and C.footprint_hits(None, g)


def test_burst_ids_keep_the_bursts_touching_the_corridor(monkeypatch):
    from geoeyes.sensors.sentinel1 import asf
    g, _ = C.build([_line(0, 5)], 1000)
    on = box(104.99, LAT - 0.05, 105.1, LAT + 0.05).wkt
    off = box(104.99, LAT + 0.2, 105.1, LAT + 0.3).wkt
    refs = [SimpleNamespace(subswath="IW2", slc_name="S1A_X", full_burst_id=i, footprint_wkt=w)
            for i, w in (("128_1_IW2", on), ("128_2_IW2", off))]
    monkeypatch.setattr(asf, "search", lambda **k: refs)
    aoi = SimpleNamespace(as_tuple=lambda: (104.9, 20.5, 105.2, 21.0))
    assert asf.burst_ids_for_aoi(aoi, relative_orbit=128, start="2024-01-01", end="2024-02-01") == \
        ["128_1_IW2", "128_2_IW2"]
    assert asf.burst_ids_for_aoi(aoi, relative_orbit=128, start="2024-01-01", end="2024-02-01", area=g) == \
        ["128_1_IW2"]


def test_config_accepts_a_corridor():
    from geoeyes.config.loader import load_dict
    cfg = load_dict({"project": {"name": "c", "method": "psi"},
                     "aoi": {"bbox": [105.0, 20.6, 105.2, 20.8], "corridor": "corridor.geojson"},
                     "tracks": [{"sensor": "sentinel1", "direction": "ascending", "relative_orbit": 128}]})
    assert cfg.aoi.corridor == "corridor.geojson"
