"""Hazard zoning with rainfall (geoeyes.hazard): the coupling recovers a rainfall response planted in synthetic
series and stays quiet on noise; classes, matrix and the end-to-end assessment on a small product."""
import numpy as np
import pytest

from geoeyes.ancillary.rainfall import RainGrid
from geoeyes.core.errors import ConfigError
from geoeyes.hazard import HazardParams, assess, coupling, zoning

MONTHS = [f"{y}-{m:02d}" for y in range(2018, 2022) for m in range(1, 13)]          # 48 months


def _rain(rng, n=len(MONTHS)):
    """Monsoon-like monthly rainfall: seasonal cycle + year-to-year noise (mm)."""
    month = np.arange(n) % 12
    return np.clip(160 + 140 * np.sin(2 * np.pi * (month - 3) / 12) + rng.normal(0, 40, n), 0, None)


def _setup(rng, n_coupled=40, n_noise=40, k=0.05, lag=2, noise_mm=1.5):
    t0 = np.datetime64("2018-01-01")
    bounds = coupling.month_bounds(MONTHS, t0)
    p = _rain(rng)
    crd = coupling.crd(p, bounds)
    dates = np.arange(np.datetime64("2018-08-01"), np.datetime64("2021-12-01"), 12)
    t = (dates - t0).astype(float)
    trend = -8.0 * t / coupling.DAYS_PER_YEAR
    forced = k * crd.at(t - lag * coupling.DAYS_PER_MONTH)
    y = np.vstack([trend + forced + rng.normal(0, noise_mm, (n_coupled, t.size)),
                   trend + rng.normal(0, noise_mm, (n_noise, t.size))])
    return y, t, crd, p - crd.mean_month_mm


def test_coupling_recovers_planted_rainfall_response():
    rng = np.random.default_rng(1)
    y, t, crd, anom = _setup(rng)
    res = coupling.couple(y, t, crd, anom, max_lag=6, n_surrogates=300, seed=2)
    q = coupling.fdr_bh(res.p)
    coupled, noise = slice(0, 40), slice(40, 80)
    assert (q[coupled] <= 0.05).mean() >= 0.95                     # found ...
    assert (q[noise] <= 0.05).mean() <= 0.05                       # ... and no false alarms on noise
    assert np.median(res.lag_months[coupled]) == 2
    assert np.median(res.k[coupled]) == pytest.approx(0.05, rel=0.15)
    assert np.median(res.trend[coupled]) == pytest.approx(-8.0, abs=1.0)


def test_surrogates_keep_spectrum_and_mean():
    rng = np.random.default_rng(0)
    a = rng.normal(3, 1, 48)
    s = coupling.surrogates(a, 20, rng)
    assert s.shape == (20, 48)
    np.testing.assert_allclose(s.mean(axis=1), a.mean(), atol=1e-9)
    np.testing.assert_allclose(np.abs(np.fft.rfft(s, axis=1)), np.abs(np.fft.rfft(a))[None, :].repeat(20, 0),
                               rtol=1e-9, atol=1e-9)
    assert not np.allclose(s[0], a)


def test_fdr_bh():
    q = coupling.fdr_bh(np.array([0.01, 0.04, 0.03, np.nan, 0.5]))
    np.testing.assert_allclose(q[[0, 1, 2, 4]], [0.04, 0.0533333, 0.0533333, 0.5], rtol=1e-5)
    assert np.isnan(q[3])


def test_crd_and_month_bounds():
    b = coupling.month_bounds(["2020-01", "2020-02"], np.datetime64("2020-01-01"))
    np.testing.assert_array_equal(b, [0, 31, 60])
    c = coupling.crd(np.array([100.0, np.nan]), b)
    assert c.mean_month_mm == 100 and c.missing == 0.5
    np.testing.assert_array_equal(c.values, [0, 0, 0])


def test_classes_and_matrix():
    np.testing.assert_array_equal(zoning.classify([0.001, 0.0025, 0.004, 0.01, np.nan], (1 / 500, 1 / 300, 1 / 150)),
                                  [0, 1, 2, 3, -1])
    i = zoning.intensity_class(np.array([1.0, -5.0, 5.0, 12.0, 40.0, np.nan]), np.full(6, 2.0), (10, 30))
    np.testing.assert_array_equal(i, [0, 0, 1, 2, 3, -1])          # uplift (−5) is not subsidence intensity
    lv = zoning.hazard_level(np.array([0, 1, 3, -1, 2]), np.array([3, 3, 0, 0, -1]))
    np.testing.assert_array_equal(lv, [1, 3, 3, -1, 2])


def test_angular_distortion():
    kx, ky = np.array([0, 1, 2, 5]), np.array([0, 0, 0, 5])
    rate = np.array([0.0, 20.0, 20.0, 50.0])                     # mm/yr; cell 3 has no neighbour
    beta = zoning.angular_distortion(kx, ky, rate, 100.0, 10.0)
    np.testing.assert_allclose(beta[:3], [0.002, 0.002, 0.0])     # 20 mm/yr × 10 yr over 100 m = 1/500
    assert np.isnan(beta[3])


def test_params_validation():
    assert HazardParams.from_dict({"cell_m": 50, "subsidence_breaks": [5, 20]}).subsidence_breaks == (5.0, 20.0)
    with pytest.raises(ConfigError, match="unknown"):
        HazardParams.from_dict({"cel_m": 50})
    with pytest.raises(ConfigError, match="matrix"):
        HazardParams.from_dict({"matrix": [[0, 1], [1, 2]]})


@pytest.fixture
def product(tmp_path):
    """A flat 1.2 km × 1.2 km product: a subsiding bowl (−40 mm/yr vertical) whose west half also follows the
    rainfall, over a stable background; 36 epochs over 3.3 years."""
    import geopandas as gpd

    from geoeyes.io.points import write_points, write_timeseries
    rng = np.random.default_rng(5)
    n = 3000
    lon = 105.80 + 0.0115 * rng.random(n)
    lat = 21.00 + 0.0108 * rng.random(n)
    dx, dy = (lon - 105.80575) * 104e3, (lat - 21.0054) * 110.5e3
    bowl = np.hypot(dx, dy) < 300
    los_u = 0.78
    t0 = np.datetime64("2018-01-01")
    dates = np.arange(np.datetime64("2018-08-01"), np.datetime64("2021-11-15"), 35)
    t = (dates - t0).astype(float)
    p = _rain(np.random.default_rng(9))
    crd = coupling.crd(p, coupling.month_bounds(MONTHS, t0))
    vert = np.where(bowl[:, None], -40.0 * t[None, :] / 365.25, 0.0)
    vert += np.where((bowl & (dx < 0))[:, None], 0.08 * crd.at(t - 2 * coupling.DAYS_PER_MONTH)[None, :], 0.0)
    disp = (vert * los_u + rng.normal(0, 1.0, (n, t.size))).astype(np.float32)
    disp -= disp[:, :1]
    uid = np.array([f"t:{i:05d}" for i in range(n)])
    gdf = gpd.GeoDataFrame({"point_uid": uid, "lon": lon, "lat": lat, "vel_los_mm_yr": np.float32(0),
                            "temporal_coherence": np.float32(0.8), "los_e": np.float32(-0.6),
                            "los_n": np.float32(-0.15), "los_u": np.float32(los_u)},
                           geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    d = tmp_path / "products" / "p_v1"
    write_points(d / "points.parquet", gdf)
    write_timeseries(d / "timeseries.parquet", uid, dates, disp)
    return d, p


@pytest.fixture
def offline(product, monkeypatch):
    """Synthetic rainfall (the product's) instead of CHIRPS, and no DEM."""
    from geoeyes.ancillary import rainfall
    from geoeyes.hazard import terrain
    _, p = product

    def monthly_grid(cache, bbox, start, end):
        keys = [m for m in MONTHS if f"{start:%Y-%m}" <= m <= f"{end:%Y-%m}"]
        mm = np.array([p[MONTHS.index(k)] for k in keys], np.float32)[:, None, None]
        return RainGrid(keys, mm, 105.75, 21.05)

    def annual_grid(cache, bbox, first, last):
        years = [str(y) for y in range(first, last + 1)]
        return RainGrid(years, np.linspace(1500, 2300, len(years), dtype=np.float32)[:, None, None], 105.75, 21.05)

    monkeypatch.setattr(rainfall, "monthly_grid", monthly_grid)
    monkeypatch.setattr(rainfall, "annual_grid", annual_grid)
    monkeypatch.setattr(terrain, "load_terrain_dem", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))


def test_assess_end_to_end(product, offline, tmp_path):
    d, _ = product
    out = tmp_path / "analyses" / "hazard" / "p_v1"
    s = assess(d, out, HazardParams(n_surrogates=200), rain_cache=tmp_path / "c", dem_cache=tmp_path / "c")
    for f in ("cells.parquet", "cells_ts.npy", "rain.npz", "hazard.json", "hazard.gpkg", "manifest.json"):
        assert (out / f).exists()
    assert any("no terrain" in w for w in s["warnings"])

    import pandas as pd
    c = pd.read_parquet(out / "cells.parquet")
    assert set(c["mode"]) == {"subsidence"}
    cx, cy = (c["lon"] - 105.80575) * 104e3, (c["lat"] - 21.0054) * 110.5e3
    core = np.hypot(cx, cy) < 200
    far = np.hypot(cx, cy) > 450
    assert c.loc[core, "rate_mm_yr"].median() == pytest.approx(40, abs=3)        # sinking > 0, LOS / los_u
    assert (c.loc[far, "intensity"] == 0).mean() > 0.9
    assert (c.loc[core, "hazard"] >= 3).mean() > 0.9                             # I3 -> high or very high
    west = core & (cx < -50)
    east = core & (cx > 50)
    assert c.loc[west, "rain_coupled"].mean() > 0.8
    assert c.loc[east, "rain_coupled"].mean() < 0.2
    assert c.loc[west, "rain_lag_months"].median() == 2
    # the bowl's rim: neighbouring cells differ by ~40 mm/yr over 100 m -> 1/250 over 10 years
    assert c["angular_distortion"].max() > 1 / 300


def test_reference_bbox(product, offline, tmp_path):
    """A product referenced to the scene mean (here: every point offset by +6 mm/yr LOS) is put back on stable
    ground by reference_bbox; without it the summary warns."""
    import json

    import pandas as pd
    import pyarrow.parquet as pq

    from geoeyes.io.points import write_timeseries
    d, _ = product
    ts = pq.read_table(d / "timeseries.parquet").to_pandas()
    t = (pd.to_datetime(ts["date"]) - pd.Timestamp("2018-08-01")).dt.days.to_numpy() / 365.25
    dates = np.unique(ts["date"].to_numpy().astype("datetime64[D]"))
    uid = ts["point_uid"].unique()
    write_timeseries(d / "timeseries.parquet", uid, dates, (ts["disp_mm"] + 6.0 * t).to_numpy().reshape(uid.size, -1))
    (d / "manifest.json").write_text(json.dumps({"metrics": {"reference": "scene mean"}}), encoding="utf-8")
    s = assess(d, tmp_path / "a", HazardParams(n_surrogates=0), rain_cache=tmp_path / "c", dem_cache=tmp_path / "c")
    assert any("scene mean" in w for w in s["warnings"])
    biased = pd.read_parquet(tmp_path / "a" / "cells.parquet")
    s = assess(d, tmp_path / "b", HazardParams(n_surrogates=0, reference_bbox=(105.8, 21.0, 105.802, 21.002)),
               rain_cache=tmp_path / "c", dem_cache=tmp_path / "c")
    assert s["reference"]["kind"] == "reference_bbox"
    fixed = pd.read_parquet(tmp_path / "b" / "cells.parquet")
    assert biased["rate_mm_yr"].median() == pytest.approx(-6 / 0.78, abs=1)     # stable ground seen as uplift
    assert fixed["rate_mm_yr"].median() == pytest.approx(0, abs=1)
    assert biased["opposite_motion"].mean() > 0.5 and fixed["opposite_motion"].mean() < 0.1


def test_gnss_tie(product, offline, tmp_path):
    """gnss_tie adds the GNSS calibration of the product (here +5 mm/yr LOS, an offset) before the projection."""
    import json

    import pandas as pd
    d, _ = product
    with pytest.raises(ConfigError, match="geoeyes gnss"):
        assess(d, tmp_path / "x", HazardParams(n_surrogates=0, gnss_tie=True), rain_cache=tmp_path / "c",
               dem_cache=tmp_path / "c")
    g = tmp_path / "analyses" / "gnss" / "p_v1"
    g.mkdir(parents=True)
    calib = {"kind": "offset", "los_mode": "vertical", "stations": ["AAAA", "BBBB"], "rate_coef": [5.0],
             "rate_offset_mm_yr": 5.0, "centre": [105.8, 21.0], "lat0": 21.0, "loo_rms_after_mm_yr": 1.0}
    (g / "comparison.json").write_text(json.dumps({"calibration": calib}), encoding="utf-8")
    base = assess(d, tmp_path / "a", HazardParams(n_surrogates=0), rain_cache=tmp_path / "c", dem_cache=tmp_path / "c")
    tied = assess(d, tmp_path / "b", HazardParams(n_surrogates=0, gnss_tie=True), rain_cache=tmp_path / "c",
                  dem_cache=tmp_path / "c")
    assert base["reference"]["kind"] == "unknown" and tied["reference"]["kind"] == "gnss"
    a = pd.read_parquet(tmp_path / "a" / "cells.parquet")["rate_mm_yr"]
    b = pd.read_parquet(tmp_path / "b" / "cells.parquet")["rate_mm_yr"]
    np.testing.assert_allclose(b - a, -5.0 / 0.78, atol=0.05)        # +5 mm/yr LOS up = 6.4 mm/yr less sinking
