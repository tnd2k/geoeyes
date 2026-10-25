from datetime import date, datetime

import numpy as np
import pytest

from geoeyes.processing.atmosphere import gacos
from geoeyes.processing.atmosphere.era5.delays import delays_at_points, delays_at_points_exact
from geoeyes.processing.atmosphere.slant import zenith_to_ifg_phase
from geoeyes.processing.atmosphere.times import acquisition_times

LEVELS = np.array([1000, 975, 950, 925, 900, 875, 850, 800, 750, 700, 650, 600, 550, 500, 400, 300, 250, 200,
                   150, 100], float)


def synthetic_era5(path, lat=(18.5, 20.5), lon=(-100.0, -98.0), humid=1.0):
    """Standard atmosphere on a 0.25° grid, humidity varying with longitude."""
    import xarray as xr
    la = np.arange(lat[1], lat[0] - 1e-9, -0.25)            # ERA5: north to south
    lo = np.arange(lon[0], lon[1] + 1e-9, 0.25)
    h = 44330.8 * (1 - (LEVELS / 1013.25) ** 0.190263)      # m for each pressure level
    t = np.maximum(288.15 - 0.0065 * h, 216.65)
    rh = np.clip(80 * np.exp(-h / 3000.0), 5, 100) * humid
    shape = (LEVELS.size, la.size, lo.size)
    T = np.broadcast_to(t[:, None, None], shape).copy()
    R = np.broadcast_to(rh[:, None, None], shape) * (1 + 0.2 * np.sin(lo)[None, None, :])
    Z = np.broadcast_to((h * 9.80665)[:, None, None], shape).copy()
    ds = xr.Dataset({k: (("pressure_level", "latitude", "longitude"), v) for k, v in (("t", T), ("r", R), ("z", Z))},
                    coords={"pressure_level": LEVELS, "latitude": la, "longitude": lo})
    ds.to_netcdf(path)
    return path


def test_era5_delays_are_physical(tmp_path):
    p = synthetic_era5(tmp_path / "e.nc")
    lon = np.array([-99.1, -99.0, -98.9, -99.05, -105.0])
    lat = np.array([19.4, 19.35, 19.3, 19.42, 19.4])
    h = np.array([2240.0, 2240.0, 0.0, 3000.0, 2240.0])
    zhd, zwd = delays_at_points(p, lon, lat, h)
    assert np.isnan(zhd[4]) and np.isnan(zwd[4])            # far outside the grid
    # TRAIN integrates up to 15 km (the delay above cancels in interferograms): k1·Rd/g·(P - P(15 km))
    assert 1.95 < zhd[2] < 2.10                             # sea level
    assert 1.40 < zhd[0] < 1.55                             # 2240 m (Mexico City)
    assert zhd[3] < zhd[0] < zhd[2] and zwd[3] < zwd[0]     # less atmosphere above higher points
    assert np.all((zwd[:4] > 0.005) & (zwd[:4] < 0.4))


def test_era5_grid_columns_match_per_point(tmp_path):
    """Columns on the model grid interpolated to the points (TRAIN) vs one column per point: sub-mm."""
    p = synthetic_era5(tmp_path / "e.nc")
    rng = np.random.default_rng(1)
    lon, lat = rng.uniform(-99.5, -98.5, 300), rng.uniform(19.0, 20.0, 300)
    h = rng.uniform(0, 4000, 300)
    a, b = delays_at_points(p, lon, lat, h), delays_at_points_exact(p, lon, lat, h)
    d_h, d_w = np.max(np.abs(a[0] - b[0])), np.max(np.abs(a[1] - b[1]))
    print(f"grid vs per-point: hydro {d_h * 1e3:.3f} mm, wet {d_w * 1e3:.3f} mm")
    assert d_h < 1e-3 and d_w < 1e-3


def test_phase_sign_matches_flattened_stack():
    """A larger delay on the secondary k (range increase d) adds +4πd/λ to slc[ref]·conj(slc[k])."""
    zen = np.array([[2.0, 2.0 + 0.01, 2.0]])
    ph = zenith_to_ifg_phase(zen, np.array([0.0]) + 1e-9, 0.031, master_ix=0)
    assert ph[0, 0] == 0 and ph[0, 2] == 0
    np.testing.assert_allclose(ph[0, 1], 4 * np.pi * 0.01 / 0.031 / np.cos(0.05), rtol=1e-9)


def test_acquisition_times():
    attrs = {"sensing_mid_utc": {"2024-06-26": "2024-06-26T16:31:07.5"},
             "scenes": {"2024-06-29": "CSKS2_SCS_B_HI_03_HH_RA_SF_20240629225257_20240629225305"}}
    t = acquisition_times(attrs, [date(2024, 6, 26), date(2024, 6, 29), date(2024, 7, 2)], fallback_utc="06:30")
    assert t[date(2024, 6, 26)] == datetime(2024, 6, 26, 16, 31, 7, 500000)
    assert t[date(2024, 6, 29)] == datetime(2024, 6, 29, 22, 53, 1)
    assert t[date(2024, 7, 2)] == datetime(2024, 7, 2, 6, 30)
    with pytest.raises(ValueError):
        acquisition_times(attrs, [date(2024, 7, 2)])


def test_gacos_ztd_reader(tmp_path):
    lo0, la0, step = -100.0, 20.5, 0.01
    grid = (2.0 + 0.001 * np.arange(200)[None, :] + 0.0 * np.arange(150)[:, None]).astype(np.float32)
    grid.tofile(tmp_path / "20240626.ztd")
    (tmp_path / "20240626.ztd.rsc").write_text(
        f"WIDTH 200\nFILE_LENGTH 150\nX_FIRST {lo0}\nY_FIRST {la0}\nX_STEP {step}\nY_STEP {-step}\n")
    z = gacos.zenith_delays([-99.5, -98.0], [20.0, 20.0], [date(2024, 6, 26), date(2024, 6, 29)], tmp_path)
    np.testing.assert_allclose(z[0, 0], 2.0 + 0.001 * 50, atol=1e-6)
    assert np.isnan(z[1, 0]) and np.all(np.isnan(z[:, 1]))     # outside the grid / no product
    o = gacos.order([-99.5, -99.0], [19.0, 19.5], {date(2024, 6, 26): datetime(2024, 6, 26, 16, 31)})
    assert o["time_utc"] == "16:31" and o["dates"] == ["20240626"] and o["north"] == 19.6


def test_weather_params_from_config():
    from geoeyes.config.loader import load_dict
    from geoeyes.controller.phases.ps import weather_params
    base = {"project": {"name": "t", "method": "psi"}, "tracks": [{"sensor": "sentinel1", "direction": "ascending"}]}
    assert weather_params(load_dict(base)) is None
    p = weather_params(load_dict({**base, "atmosphere": {"method": "a_era5-w", "era5": {"cache": "c:/era5"}}}))
    assert p.method == "era5" and p.component == "wet" and str(p.cache).replace("\\", "/") == "c:/era5"
    g = weather_params(load_dict({**base, "atmosphere": {"method": "gacos", "gacos": {"dir": "d"}}}), "x")
    assert g.method == "gacos" and g.gacos_dir.name == "d"
