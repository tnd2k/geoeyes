"""Source Cooperative: catalog search, tile names of the layers, window mosaics, height filling, exposure (offline)."""
import json

import numpy as np
import pandas as pd
import pytest

from geoeyes.core.errors import ConfigError
from geoeyes.opendata import coop
from geoeyes.workspace import WorkspaceLayout


def _product(acc, pid, title, desc="", tags=()):
    return coop._record({"account_id": acc, "product_id": pid, "title": title, "description": desc,
                         "metadata": {"tags": list(tags)}, "updated_at": "2026-10-01T00:00:00Z"})


@pytest.fixture
def ws(tmp_path):
    w = WorkspaceLayout.at(tmp_path)
    rows = [_product("nlebovits", "jrc-glofas", "JRC GloFAS Global Flood Hazard Maps", "river flood depth"),
            _product("esa", "sen12flood", "SEN12-FLOOD: A SAR and Multispectral Dataset for Flood Detection"),
            _product("wfp", "jrc-ghsl-pop", "GHS-POP R2023A - GHS Population Grid"),
            _product("tge-labs", "globalbuildingatlas-lod1", "GlobalBuildingAtlas LoD1", "building heights"),
            _product("fiboa", "luxembourg", "Luxembourg FLIK Parcels", "LPIS field boundaries"),
            _product("wfp", "chirps-rnl-daily", "CHIRPS Daily Version 3 RNL", "daily rainfall")]
    coop._index(w).parent.mkdir(parents=True, exist_ok=True)
    coop._index(w).write_text(json.dumps({"synced": "2026-11-01T00:00:00+00:00", "products": rows}), encoding="utf-8")
    return w


def test_search_ranks_and_reads_vietnamese(ws):
    ids = [p["id"] for p in coop.search(ws, "flood")]
    assert ids[0] == "nlebovits/jrc-glofas" and "esa/sen12flood" in ids             # the GeoEyes layer first
    assert [p["id"] for p in coop.search(ws, "lũ lụt")][:2] == ids[:2]
    assert "fiboa/luxembourg" not in [p["id"] for p in coop.search(ws, "lũ")]     # "lu" is not a prefix
    assert coop.search(ws, "dân số")[0]["id"] == "wfp/jrc-ghsl-pop"
    assert coop.search(ws, "mưa lớn hằng ngày")[0]["id"] == "wfp/chirps-rnl-daily"
    assert coop.search(ws, "nhà")[0]["layer"] == "gba-buildings"                 # inside globalbuildingatlas
    assert len(coop.search(ws, "")) == 6 and coop.search(ws, "", layers_only=True)[0]["layer"]


def test_layers_point_at_their_products():
    assert {lay.product for lay in coop.LAYERS.values()} >= {"epoch/jrc-global-surface-water-monthly",
                                                            "wfp/jrc-ghsl-pop", "tge-labs/globalbuildingatlas-lod1"}
    rec = _product("wfp", "jrc-ghsl-pop", "x")
    assert rec["layer"] == "ghsl-pop" and rec["data"] == "https://data.source.coop/wfp/jrc-ghsl-pop/"


def test_tile_names():
    assert coop._zones((105.7, 20.9, 105.9, 21.1), 10) == [(100.0, 30.0)]
    assert coop._zones((-99.3, 19.3, -99.0, 19.5), 10) == [(-100.0, 20.0)]
    assert coop._hem(100, "E", "W") == "100E" and coop._hem(-100, "E", "W") == "100W"
    assert coop._gba_tiles((105.8, 21.0, 105.9, 21.1))[0].endswith("/e105_n25_e110_n20.parquet")
    assert coop._gba_tiles((-99.3, 19.3, -99.0, 19.5))[0].endswith("/w100_n20_w095_n15.parquet")
    assert len(coop._gba_tiles((104.9, 19.9, 105.1, 20.1))) == 4                  # corner of four tiles
    with pytest.raises(ConfigError):
        coop._bbox((106, 21, 105, 22))


def test_gsw_urls_by_edition(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(coop, "_mosaic", lambda urls, bbox, **k: (seen.extend(urls), (np.ones((2, 2)), 0, 0, 1))[1])
    coop.gsw_month(tmp_path, (105.7, 20.9, 105.9, 21.1), "2024-09")
    coop.gsw_month(tmp_path, (105.7, 20.9, 105.9, 21.1), "2019-09")
    coop.gsw_month(tmp_path, (105.7, 20.9, 105.9, 21.1), "2021-09")
    assert seen[0].endswith("/v1_5/2024/2024_09/monthlyhistory_100E_30N_v1_5_2024_09.tif")
    assert seen[1].endswith("/tiles/2019/2019_09/2019_09-0000200000-0001120000.tif")
    assert seen[2].endswith("/tiles/2021/2021_09/0000200000-0001120000.tif")
    with pytest.raises(ConfigError):
        coop.gsw_month(tmp_path, (105.7, 20.9, 105.9, 21.1), "2016-09")


def _tif(path, west, north, res, a, nodata):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", width=a.shape[1], height=a.shape[0], count=1, dtype=a.dtype,
                       crs="EPSG:4326", transform=from_origin(west, north, res, res), nodata=nodata) as d:
        d.write(a, 1)
    return str(path)


def test_mosaic_of_two_tiles(tmp_path):
    a = np.full((10, 10), 5.0, np.float32)
    b = np.full((10, 10), 7.0, np.float32)
    b[2, 0] = -9999                                                                # lat 0.8-0.7, lon 1.0-1.1
    t1 = _tif(tmp_path / "a.tif", 0.0, 1.0, 0.1, a, -9999)
    t2 = _tif(tmp_path / "b.tif", 1.0, 1.0, 0.1, b, -9999)
    out, w, n, res = coop._mosaic([t1, str(tmp_path / "missing.tif"), t2], (0.55, 0.25, 1.45, 0.75))
    assert (w, n, res) == pytest.approx((0.5, 0.8, 0.1)) and out.shape == (6, 10)
    assert np.all(out[:, :5] == 5) and np.isnan(out[0, 5]) and np.all(out[1:, 5:] == 7)


def test_fill_heights_from_footprints(tmp_path, monkeypatch):
    import shapely
    sq = [shapely.box(0, 0, 1e-4, 1e-4), shapely.box(1e-3, 0, 1.1e-3, 1e-4)]
    g = pd.DataFrame({"source": ["osm", "google"], "height_m": [12.0, 30.0], "lon": [5e-5, 1.05e-3],
                      "lat": [5e-5, 5e-5], "geometry": [shapely.to_wkb(p) for p in sq]})
    monkeypatch.setattr(coop, "gba_buildings", lambda *a, **k: g)
    h, filled = coop.fill_heights(tmp_path, [5e-5, 1.05e-3, 5e-3], [5e-5, 5e-5, 5e-5], [np.nan, 9.0, np.nan],
                                  (0, 0, 0.01, 0.01))
    assert h[0] == 12.0 and h[1] == 9.0 and np.isnan(h[2])                         # own heights kept
    assert filled.tolist() == [True, False, False]


def test_exposure_classes_and_flood(tmp_path, monkeypatch):
    from geoeyes.hazard import exposure
    res = 1 / 1200
    pop = coop.Grid(np.full((4, 4), 100.0, np.float32), 105.0, 21.0, res, "pop")
    water_ev = np.ones((12, 12), np.float32)
    water_ev[:3, :3] = 2                                                          # cell (0, 0) flooded
    water_ev[9:, 9:] = np.nan                                                      # not observed
    ref = np.ones((12, 12), np.float32)
    monkeypatch.setattr(coop, "ghsl_pop", lambda cache, bbox: pop)
    monkeypatch.setattr(coop, "gsw_month", lambda cache, bbox, m: coop.Grid(water_ev if m == "2024-09" else ref,
                                                                             105.0, 21.0, res / 3, "gsw"))
    monkeypatch.setattr(coop, "chirps_daily", lambda *a, **k: {"days": [{"date": "2024-09-07", "mean_mm": 200.0},
                                                                         {"date": "2024-09-08", "mean_mm": 30.0}]})
    lon, lat, v = [], [], []
    for r in range(4):
        for c in range(4):
            for _ in range(3):
                lon.append(105.0 + (c + 0.5) * res)
                lat.append(21.0 - (r + 0.5) * res)
                v.append(-15.0 if (r, c) == (0, 0) else -1.0)
    prod = tmp_path / "p"
    prod.mkdir()
    pd.DataFrame({"lon": lon, "lat": lat, "vel_los_mm_yr": v, "los_u": 1.0}).to_parquet(prod / "points.parquet")
    monkeypatch.setattr(exposure, "_peak_30min", lambda *a: {"time": "2024-09-07T04:30:00", "mm_h": 7.2,
                                                              "max_cell_mm_h": 8.6})
    ws = WorkspaceLayout.at(tmp_path)
    out = ws.project("p").analysis("exposure", "p")
    s = exposure.run(prod, out, exposure.ExposureParams(buildings=False, flood_month="2024-09"), cache=tmp_path)
    cls = {c["class"]: c["people"] for c in s["subsidence"]["classes"]}
    assert cls["< 5"] == 1500 and cls["10-20"] == 100 and s["subsidence"]["people_not_observed"] == 0
    f = s["flood"]
    assert f["dry_month"] == "2024-03" and f["people"] == 100 and f["people_on_sinking_ground"] == 100
    assert f["rain_month_mm"] == 230.0 and f["rain_wettest_day"]["date"] == "2024-09-07"
    assert f["rain_peak_30min"]["mm_h"] == 7.2
    from geoeyes.api import behaviour                                              # the web app's cells
    meta, raw = behaviour.exposure_cells(ws.project("p"), "p")
    arr = np.frombuffer(raw, np.float32).reshape(meta["n"], len(meta["fields"]))
    assert meta["n"] == 16 and meta["fields"][5] == "class"
    assert arr[0, 2] == 100 and arr[0, 5] == 2 and arr[0, 6] == 1.0 and np.isnan(arr[0, 7])
    assert exposure._dry("2024-02") == "2023-08" and exposure._dry("2017-03") == "2017-09"


def test_imerg_from_reader_output(tmp_path, monkeypatch):
    import subprocess
    calls = []

    def fake_run(argv, **k):
        calls.append(argv)
        np.savez(argv[-1], time=np.array(["2024-09-07T04:00:00", "2024-09-07T04:30:00"]),
                 mean_mm_h=np.array([7.1, np.nan], np.float32), max_mm_h=np.array([8.7, np.nan], np.float32),
                 attribution=np.array("NASA GPM IMERG"))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = coop.imerg_halfhourly(tmp_path, (105.7, 20.95, 105.95, 21.1), "2024-09-07", "2024-09-07", python="py312")
    assert calls[0][0] == "py312" and calls[0][3] == "late" and calls[0][-3:-1] == ["2024-09-07T00:00", "2024-09-07T23:59"]
    assert r["steps"] == [{"time": "2024-09-07T04:00:00", "mean_mm_h": 7.1, "max_mm_h": 8.7},
                          {"time": "2024-09-07T04:30:00", "mean_mm_h": None, "max_mm_h": None}]
    coop.imerg_halfhourly(tmp_path, (105.7, 20.95, 105.95, 21.1), "2024-09-07", "2024-09-07", python="py312")
    assert len(calls) == 1                                                       # past period: cached
    with pytest.raises(ConfigError):
        coop.imerg_halfhourly(tmp_path, (105.7, 20.95, 105.95, 21.1), "2024-01-01", "2024-09-07", python="py312")


def test_imerg_needs_icechunk_2(monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, "icechunk", types.SimpleNamespace(__version__="1.1.21"))
    with pytest.raises(ConfigError, match="GEOEYES_ICECHUNK_PYTHON"):
        coop._icechunk_python(None)
    monkeypatch.setitem(sys.modules, "icechunk", types.SimpleNamespace(__version__="2.3.1"))
    assert coop._icechunk_python(None) == [sys.executable]
