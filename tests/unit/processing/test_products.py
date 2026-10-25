import sqlite3

import numpy as np
import pandas as pd

from geoeyes.export.vector import export_product
from geoeyes.io.manifest import InputRef, Manifest
from geoeyes.io.points import read_points, read_timeseries, write_points, write_timeseries
from geoeyes.products.builder import build_product, los_vector, timeseries_stats


def test_los_vector_points_to_the_satellite():
    e, n, u = los_vector(np.array([40.0]), heading_deg=-10.0, look_side="right")     # ascending, right-looking
    assert u[0] > 0 and e[0] < 0                     # satellite to the west of the ground, above it
    e2, *_ = los_vector(np.array([40.0]), heading_deg=-10.0, look_side="left")
    assert e2[0] > 0
    np.testing.assert_allclose(e**2 + n**2 + u**2, 1.0)


def test_timeseries_stats_recover_trend_and_annual_term():
    rng = np.random.default_rng(0)
    dates = np.arange(np.datetime64("2023-01-05"), np.datetime64("2024-12-31"), 12)
    t = (dates - np.datetime64("2023-01-01")).astype(float) / 365.25
    amp, peak_doy = 4.0, 200.0
    d = -10 * t + amp * np.cos(2 * np.pi * (t - peak_doy / 365.25)) + 0.3 * rng.standard_normal((50, t.size))
    s = timeseries_stats(d.astype(np.float32), dates)
    assert np.allclose(s["amp"], amp, atol=0.3) and np.allclose(s["phase_day"], peak_doy, atol=6)
    assert abs(np.median(s["sigma"]) - 0.3) < 0.03 and np.all(s["vel_std"] < 0.2)


def fake_run(tmp_path, n=60):
    import geopandas as gpd
    run = tmp_path / "ps_runs" / "track"
    rng = np.random.default_rng(1)
    lon, lat = -99.0 + 0.01 * rng.random(n), 19.3 + 0.01 * rng.random(n)
    uid = np.array([f"track:{i:05d}" for i in range(n)])
    gdf = gpd.GeoDataFrame({"point_uid": uid, "lon": lon, "lat": lat, "height_m": np.float32(2240),
                            "dem_err_m": np.float32(1.0), "type": np.where(np.arange(n) % 5 == 0, "DS", "PS"),
                            "vel_los_mm_yr": rng.normal(-20, 10, n).astype(np.float32),
                            "acc_mm_yr2": np.float32(0), "temporal_coherence": np.float32(0.8),
                            "amp_dispersion": np.float32(0.2), "fit_rmse_mm": np.float32(1.0),
                            "incidence_deg": np.float32(38.0), "vel_los_scn_mm_yr": np.float32(-19)},
                           geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    write_points(run / "points.parquet", gdf)
    dates = np.arange(np.datetime64("2024-05-03"), np.datetime64("2024-11-01"), 12)
    write_timeseries(run / "timeseries.parquet", uid, dates, rng.normal(0, 2, (n, dates.size)))
    m = Manifest(kind="ps_run", id="track", engine="geoeyes-ps/1", inputs=[InputRef("stack", "", "")],
                 metrics={"reference_date": "2024-07-14"})
    m.add_outputs(run, ["points.parquet"])
    m.write(run)
    return run, dates


def test_qgis_style_pretty_breaks_jet_r_ground_sized_markers():
    from geoeyes.export.styles import marker_size_m, pretty_breaks, velocity_qml
    # R: pretty(c(-207.75, 207.83), 10) -> -250, -200, ..., 250; QGIS clamps the ends to the data
    assert pretty_breaks(-207.75, 207.83) == [-200, -150, -100, -50, 0.0, 50, 100, 150, 200, 207.83]
    assert pretty_breaks(-6.78, 7.77) == [-6, -4, -2, 0.0, 2, 4, 6, 7.77]
    rng = np.random.default_rng(0)
    v = rng.uniform(-207.75, 207.83, 1000)
    v[:2] = -207.75, 207.83
    qml = velocity_qml(v, size_m=4.5)
    assert '<range lower="-207.750000" upper="-200.000000"' in qml and 'upper="207.830000"' in qml
    assert qml.count("<range ") == 10 and '<classificationMethod id="Pretty">' in qml
    assert 'name="color" value="128,0,0,255"' in qml                # jet_r: dark red for the lowest class
    assert 'name="outline_style" value="no"' in qml and 'value="RenderMetersInMapUnits"' in qml
    lon = -99 + np.arange(100) % 10 * 1e-4                          # 10 x 10 grid, ~10.5 m x 11 m
    lat = 19.3 + np.arange(100) // 10 * 1e-4
    assert 9 < marker_size_m(lon, lat) < 10.5                     # 0.9 x nearest-neighbour distance


def test_report_uses_the_parameters_of_the_run_not_the_current_config():
    from types import SimpleNamespace as NS

    from geoeyes.report.methods import linking_params, weather_used
    cfg = NS(phase_linking=NS(enabled=True), atmosphere=NS(method="era5", select="auto"))
    old_stack = {"phase_linking_done": {"estimator": "adaptive", "half_window": [7, 7]}}    # before shp_test
    run = NS(extra={}, metrics={"aps": "linear"})
    assert linking_params(cfg, run, {"slc_var": "slc_linked"}, old_stack)["shp_test"] == "ks"
    assert linking_params(cfg, run, {"slc_var": "slc"}, old_stack) is None
    new = NS(extra={"phase_linking": {"shp_test": "ad", "estimator": "emi"}}, metrics={})
    assert linking_params(cfg, new, {}, old_stack)["shp_test"] == "ad"
    assert weather_used(cfg, run) == ("", "", 0)                                  # config says era5, run did not
    lite = NS(extra={"pairs": [{"weather_aps": True}, {"weather_aps": False}]}, metrics={"aps": ""})
    assert weather_used(cfg, lite) == ("era5", "auto", 1)
    ps = NS(extra={}, metrics={"aps": {"method": "gacos", "select": "auto", "weather_ifgs": ["2024-01-01"] * 3}})
    assert weather_used(cfg, ps) == ("gacos", "auto", 3)


def test_report_of_a_product(tmp_path):
    import json

    import pytest
    pytest.importorskip("typst")
    from geoeyes.report import build_report
    from geoeyes.report.collect import confidence
    run, dates = fake_run(tmp_path)
    r = build_product(run, tmp_path / "products", project="mx", track_id="sentinel1-asc-078")
    prod = tmp_path / "products" / r["product_id"]
    pdf = build_report(prod, copy_to=tmp_path / "copies")
    assert pdf.read_bytes()[:4] == b"%PDF" and (tmp_path / "copies" / f"{prod.name}.pdf").exists()
    data = json.loads((prod / "report.json").read_text(encoding="utf-8"))
    assert data["stats"]["n_points"] == 60 and data["stats"]["n_ds"] == 12
    assert [c["label"] for c in data["clusters"]][-1] == "stable points"
    assert data["confidence"]["level"] in ("medium", "low")                     # 16 dates over 168 days
    assert any("shorter than one year" in x for x in data["limitations"])
    assert prod.joinpath("report.pdf").name not in [f["path"] for f in data["files"]]  # derived, not in manifest
    good = {"vel": {"p02": -20, "p50": 0, "p98": 20}, "vel_std": {"p50": 1.0}, "tcoh": {"p50": 0.8}}
    assert confidence(60, 1000, 0.95, good)["level"] == "high"
    moving_ref = {**good, "vel": {"p02": 40, "p50": 80, "p98": 120}}
    assert any("reference area" in i for i in confidence(60, 1000, 0.95, moving_ref)["issues"])


def test_product_carries_the_scn_removed_series(tmp_path):
    run, dates = fake_run(tmp_path)
    ts = read_timeseries(run / "timeseries.parquet")
    wide = ts.pivot(index="point_uid", columns="date", values="disp_mm")
    write_timeseries(run / "timeseries.parquet", wide.index.to_numpy(), dates, wide.to_numpy(),
                     disp_scn_mm=wide.to_numpy() * 0.5)
    r = build_product(run, tmp_path / "products", project="mx", track_id="sentinel1-asc-078")
    out = read_timeseries(tmp_path / "products" / r["product_id"] / "timeseries.parquet")
    np.testing.assert_allclose(out["disp_scn_mm"], out["disp_mm"] * 0.5, atol=1e-5)


def test_build_and_export_product(tmp_path):
    run, dates = fake_run(tmp_path)
    r = build_product(run, tmp_path / "products", project="mx", track_id="sentinel1-asc-078")
    last = dates[-1].astype(object)
    assert r["product_id"] == f"mx_sentinel1-asc-078_20240503_{last:%Y%m%d}_v1" and r["n_points"] == 60
    prod = tmp_path / "products" / r["product_id"]
    pts = read_points(prod / "points.parquet")
    assert {"los_e", "seasonal_amp_mm", "residual_sigma_mm", "extra_vel_scn_mm_yr"} <= set(pts.columns)
    assert pts["seasonal_amp_mm"].isna().all()       # < 300 days: no annual term
    assert len(read_timeseries(prod / "timeseries.parquet")) == 60 * dates.size
    assert (prod / "rasters" / "velocity.tif").exists() and (prod / "item.json").exists()
    assert build_product(run, tmp_path / "products", project="mx",
                         track_id="sentinel1-asc-078")["product_id"].endswith("_v2")     # new version, immutable
    files = export_product(prod, tmp_path / "exports" / r["product_id"], formats=("gpkg", "csv"))
    gpkg = next(f for f in files if f.suffix == ".gpkg")
    import geopandas as gpd
    g = gpd.read_file(gpkg, layer="points")
    assert len(g) == 60 and sum(c.startswith("D2024") for c in g.columns) == dates.size
    with sqlite3.connect(gpkg) as con:
        name, qml, default = con.execute("SELECT f_table_name, styleQML, useAsDefault FROM layer_styles").fetchone()
    assert name == "points" and default == 1 and "graduatedSymbol" in qml and "vel_los_mm_yr" in qml
    assert pd.read_csv(next(f for f in files if f.suffix == ".csv")).shape[0] == 60
