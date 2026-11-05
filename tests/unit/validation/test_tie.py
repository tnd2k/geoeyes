"""Tie of a product to another one: two products of one subsiding ground, other line of sight, other reference and
a shorter period, give back the known offset; the calibrated web layer and export add it."""
import json

import geopandas as gpd
import numpy as np
import pyogrio
import pytest

from geoeyes.io.points import write_points, write_timeseries
from geoeyes.validation.tie import tie

W, S = -99.03, 19.33


def _vertical(lon, lat):
    """True vertical rate (mm/yr): a subsidence bowl, −200 at its centre, 0 at its rim."""
    r = np.hypot((lon - (W + 0.02)) * 105_000, (lat - (S + 0.02)) * 110_600)
    return -200.0 * np.clip(1 - r / 2500.0, 0, 1)


def _product(root, name, los, ref_mm_yr, dates, n, seed):
    """Points over the bowl; LOS rate = vertical·los_u + ref_mm_yr (the product's own moving reference)."""
    rng = np.random.default_rng(seed)
    lon = W + rng.uniform(0, 0.04, n)
    lat = S + rng.uniform(0, 0.04, n)
    los = np.asarray(los) / np.linalg.norm(los)
    v = _vertical(lon, lat) * los[2] + ref_mm_yr
    t = (dates - dates[0]).astype(float) / 365.25
    disp = v[:, None] * t[None, :] + rng.normal(0, 1.0, (n, t.size))
    uid = np.array([f"{name}{i:05d}" for i in range(n)])
    vel = np.polyfit(t, disp.T, 1)[0]
    gdf = gpd.GeoDataFrame({"point_uid": uid, "lon": lon, "lat": lat, "vel_los_mm_yr": vel.astype(np.float32),
                            "los_e": np.float32(los[0]), "los_n": np.float32(los[1]), "los_u": np.float32(los[2]),
                            **{a: np.float32(0) for a in ("vel_std_mm_yr", "temporal_coherence", "height_m",
                                                          "acc_los_mm_yr2", "seasonal_amp_mm", "dem_err_m")}},
                           geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    d = root / name
    write_points(d / "points.parquet", gdf)
    write_timeseries(d / "timeseries.parquet", uid, dates, disp)
    return d, los


@pytest.fixture
def pair(tmp_path):
    s1_dates = np.arange(np.datetime64("2024-05-03"), np.datetime64("2024-10-31"), 12)
    cp_dates = np.arange(np.datetime64("2024-06-26"), np.datetime64("2024-08-16"), 3)
    ref, ref_los = _product(tmp_path, "s1_v1", [-0.69, -0.15, 0.71], 40.0, s1_dates, 6000, 1)
    tgt, tgt_los = _product(tmp_path, "cp_v1", [0.47, -0.46, 0.76], -25.0, cp_dates, 4000, 2)
    return tmp_path, ref, tgt, ref_los, tgt_los


def test_tie_recovers_the_reference_offset(pair):
    root, ref, tgt, ref_los, tgt_los = pair
    # the reference's own calibration (as from GNSS): its LOS reference moves +40 mm/yr, so −40 puts it on truth
    ref_cal = {"kind": "offset", "rate_coef": [-40.0], "rate_offset_mm_yr": -40.0, "stations": ["MMX1"],
               "centre": [W, S], "lat0": S, "los_mode": "vertical", "source": "gnss"}
    s = tie(tgt, ref, root / "tie", reference_calibration=ref_cal, cell_m=200)
    c = s["calibration"]
    # the target's reference moves −25 mm/yr in its LOS: the correction is +25
    assert c["rate_offset_mm_yr"] == pytest.approx(25.0, abs=1.5)
    assert c["reference_calibration"] == "GNSS MMX1" and c["source"] == "tie"
    assert s["corr"] > 0.95 and s["slope"] == pytest.approx(1.0, abs=0.05)
    assert s["window"][0] <= s["target_period"][0] and s["window"][1] >= s["target_period"][1]
    assert json.loads((root / "tie" / "tie.json").read_text(encoding="utf-8"))["n_cells"] == s["n_cells"]
    # without the reference's calibration, the target is tied to the reference's moving zero instead
    s2 = tie(tgt, ref, root / "tie2", cell_m=200)
    assert s2["calibration"]["rate_offset_mm_yr"] == pytest.approx(25.0 + 40.0 / ref_los[2] * tgt_los[2], abs=2.0)


def test_calibrated_layer_and_export(pair, tmp_path):
    from geoeyes.api import points
    from geoeyes.export.vector import export_product
    root, ref, tgt, *_ = pair
    cal = tie(tgt, ref, root / "tie", cell_m=200)["calibration"]
    raw = points.ensure(tgt, tmp_path / "web")
    on = points.ensure(tgt, tmp_path / "web", cal)
    assert on.name.endswith("@cal") and points.meta(on)["calibration"]["source"] == "tie"
    a, b = np.load(raw / "ts.npy"), np.load(on / "ts.npy")
    dates = np.array(points.meta(raw)["dates"], dtype="datetime64[D]")
    span = (dates[-1] - dates[0]).astype(float) / 365.2425
    assert np.median(b[:, -1] - a[:, -1]) == pytest.approx(cal["rate_offset_mm_yr"] * span, abs=0.05)
    assert points.ensure(tgt, tmp_path / "web", cal) == on                   # cached
    files = export_product(tgt, tmp_path / "exp", ("gpkg",), calibration=cal)
    gpkg = next(f for f in files if f.suffix == ".gpkg")
    assert gpkg.name == "cp_v1_calibrated.gpkg"
    df = pyogrio.read_dataframe(gpkg, layer="points", columns=["vel_los_mm_yr", "vel_los_cal_mm_yr"], read_geometry=False)
    assert np.allclose(df.vel_los_cal_mm_yr - df.vel_los_mm_yr, cal["rate_offset_mm_yr"], atol=1e-3)
