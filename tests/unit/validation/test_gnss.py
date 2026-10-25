"""GNSS comparison and calibration (geoeyes.validation.gnss): NGL tenv3 parsing, cleaning of jumps and outliers,
and a synthetic product whose reference is off by a known rate, recovered from three synthetic stations."""
import numpy as np
import pandas as pd
import pytest

from geoeyes.core.errors import ConfigError
from geoeyes.validation.gnss import GnssParams, compare, correction, ngl

TENV3 = """site YYMMMDD yyyy.yyyy __MJD week d reflon _e0(m) __east(m) ____n0(m) _north(m) u0(m) ____up(m) _ant(m) sig_e(m) sig_n(m) sig_u(m) __corr_en __corr_eu __corr_nu _latitude(deg) _longitude(deg) __height(m)
JNAV 14JAN07 2014.0178 56664 1774 2  105.8   4569  0.103556   2323584  0.545521    34  0.755651  0.0000 0.000935 0.000799 0.003806 -0.032156  0.034535 -0.043603  21.0045853503 -254.1560524624    34.75565
JNAV 14JAN08 2014.0205 56665 1774 3  105.8   4569  0.103598   2323584  0.545072    34  0.741752  0.0000 0.000875 0.000793 0.003745 -0.007452 -0.015599 -0.036776  21.0045853462 -254.1560524620    34.74175
"""


def test_read_tenv3():
    df = ngl.read_tenv3(TENV3)
    assert list(df["date"].astype(str)) == ["2014-01-07", "2014-01-08"]
    assert df["up"].iloc[0] == pytest.approx(34.755651)
    assert df["east"].iloc[0] == pytest.approx(4569.103556)
    assert df["lon"].iloc[0] == pytest.approx(105.8439475376)                 # -254.156 deg -> 105.844 E


def _daily(start="2024-01-01", days=400, rate_mm_yr=(10.0, -5.0, -50.0), seed=0):
    rng = np.random.default_rng(seed)
    d = np.arange(np.datetime64(start), np.datetime64(start) + days)
    t = np.arange(days) / 365.25
    enu = np.column_stack([r / 1000 * t for r in rate_mm_yr]) + rng.normal(0, [0.001, 0.001, 0.003], (days, 3))
    return pd.DataFrame({"date": d, "east": 100 + enu[:, 0], "north": 200 + enu[:, 1], "up": 30 + enu[:, 2],
                         "sig_e": 0.001, "sig_n": 0.001, "sig_u": 0.004, "lat": 21.0, "lon": 105.8, "height": 30.0})


def test_clean_rejoins_a_moved_antenna_and_drops_outliers():
    df = _daily()
    df.loc[200:, ["east", "up"]] += [250.0, -11.0]                 # moved under the same name (as JNAV in 2025)
    df.loc[100, "up"] += 0.5                                       # one bad day
    c = ngl.clean(df, "TEST", "2024-01-01", "2025-02-03")
    assert c.segments == 2 and c.outliers >= 1
    rate_u = np.polyfit((c.date - c.date[0]).astype(float) / 365.25, c.enu[:, 2] * 1000, 1)[0]
    rate_e = np.polyfit((c.date - c.date[0]).astype(float) / 365.25, c.enu[:, 0] * 1000, 1)[0]
    assert rate_u == pytest.approx(-50, abs=2) and rate_e == pytest.approx(10, abs=1)


def test_params():
    assert GnssParams.from_dict({"stations": ["humg"], "n_rovers": 3}).stations == ("HUMG",)
    with pytest.raises(ConfigError):
        GnssParams.from_dict({"calibration": "spline"})


STATIONS = {"AAAA": (105.802, 21.002, -30.0), "BBBB": (105.818, 21.004, -5.0), "CCCC": (105.808, 21.016, -60.0)}
OFFSET = 7.0          # mm/yr LOS: the product's reference moves this much relative to the GNSS frame


@pytest.fixture
def product(tmp_path):
    """Points around three stations with known vertical rates; the InSAR series are relative to a reference that
    itself moves by −OFFSET mm/yr in the line of sight (so InSAR = truth + OFFSET·t)."""
    import geopandas as gpd

    from geoeyes.io.points import write_points, write_timeseries
    rng = np.random.default_rng(1)
    lon, lat, vu = [], [], []
    for x, y, v in STATIONS.values():
        lon += list(x + rng.normal(0, 0.0003, 40))
        lat += list(y + rng.normal(0, 0.0003, 40))
        vu += [v] * 40
    lon, lat, vu = np.array(lon), np.array(lat), np.array(vu)
    los = np.array([-0.6, -0.12, 0.79])
    los /= np.linalg.norm(los)
    dates = np.arange(np.datetime64("2024-05-03"), np.datetime64("2025-05-01"), 12)
    t = (dates - dates[0]).astype(float) / 365.25
    disp = (vu[:, None] * los[2] + OFFSET) * t[None, :] + rng.normal(0, 1.5, (lon.size, t.size))
    uid = np.array([f"p{i:04d}" for i in range(lon.size)])
    gdf = gpd.GeoDataFrame({"point_uid": uid, "lon": lon, "lat": lat, "vel_los_mm_yr": np.float32(0),
                            "los_e": np.float32(los[0]), "los_n": np.float32(los[1]), "los_u": np.float32(los[2])},
                           geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    d = tmp_path / "products" / "p_v1"
    write_points(d / "points.parquet", gdf)
    write_timeseries(d / "timeseries.parquet", uid, dates, disp)
    return d, los


@pytest.fixture
def offline(monkeypatch):
    rows = [(s, y, x, 10.0, pd.Timestamp("2020-01-01"), pd.Timestamp("2026-01-01"), 2000)
            for s, (x, y, _) in STATIONS.items()]
    table = pd.DataFrame(rows, columns=["site", "lat", "lon", "height", "first", "last", "n_days"])
    monkeypatch.setattr(ngl, "stations", lambda cache: table)

    def series(cache, site):
        x, y, v = STATIONS[site]
        df = _daily("2024-04-01", 420, (30.0, -8.0, v), seed=hash(site) % 100)    # plate motion east + local up
        return df.assign(lat=y, lon=x)

    monkeypatch.setattr(ngl, "series", series)
    monkeypatch.setattr(ngl, "equipment_steps", lambda cache, site: [])
    monkeypatch.setattr(ngl, "midas", lambda cache, site: None)


def test_compare_recovers_reference_offset(product, offline, tmp_path):
    d, los = product
    s = compare(d, tmp_path / "out", GnssParams(calibration="plane"), tmp_path / "cache")
    used = [st for st in s["stations"] if st["used"]]
    assert len(used) == 3
    for st in used:
        v = st["vertical"]
        assert v["rate_diff_mm_yr"] == pytest.approx(-OFFSET, abs=2.5)         # GNSS − InSAR = −offset
        assert v["rmse_detrended_mm"] < 3
        # the full projection also sees the plate's eastward motion, absent from the relative InSAR
        assert abs(st["full"]["rate_diff_mm_yr"] - v["rate_diff_mm_yr"]) > 10
    c = s["calibration"]
    assert c["kind"] == "plane" and c["rate_offset_mm_yr"] == pytest.approx(-OFFSET, abs=2)
    assert c["loo_rms_after_mm_yr"] < c["loo_rms_before_mm_yr"]
    corr = correction(c, np.array(s["dates"], dtype="datetime64[D]"), np.array([105.81]), np.array([21.01]))
    assert corr[0, -1] == pytest.approx(-OFFSET * 0.99, abs=2)              # mm after a year


def test_compare_one_station_and_exclusion(product, offline, tmp_path):
    d, _ = product
    s = compare(d, tmp_path / "out", GnssParams(stations=("AAAA", "BBBB"), exclude=("BBBB",)), tmp_path / "c")
    assert [st["site"] for st in s["stations"] if st["used"]] == ["AAAA"]
    assert any("one station" in w for w in s["warnings"])
    assert "leave_one_out" not in s["calibration"]
