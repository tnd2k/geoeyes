"""Groundwater storage (GLDAS via NASA Harmony, mocked here): monthly cache, and its coupling with InSAR series."""
from datetime import date

import numpy as np

from geoeyes.ancillary import groundwater as gw
from geoeyes.hazard import coupling


def _daily(first: date, last: date, shape, seasonal=True):
    days = np.arange(np.datetime64(first), np.datetime64(last) + 1)
    doy = (days - days.astype("datetime64[Y]")).astype(float)
    out = {}
    for d, x in zip(days, doy, strict=True):
        out[str(d)] = np.full(shape, 1700 + (100 * np.sin(2 * np.pi * x / 365.25) if seasonal else 0), np.float32)
    return out


def test_monthly_grid_caches_complete_months(monkeypatch, tmp_path):
    calls = []

    def fake(token, box, first, last, progress=None):
        calls.append((first, last))
        ny, nx = round((box[3] - box[1]) / gw.RES), round((box[2] - box[0]) / gw.RES)
        return _daily(first, min(last, date(2024, 3, 10)), (ny, nx))     # March 2024 not complete yet

    monkeypatch.setattr(gw, "_harmony_daily", fake)
    g = gw.monthly_grid(tmp_path, [105.7, 20.9, 105.95, 21.15], date(2024, 1, 1), date(2024, 3, 1), "tok")
    assert g.mm.shape == (3, 2, 2) and g.west == 105.5 and g.north == 21.25
    assert np.isfinite(g.mm[:2]).all() and np.isnan(g.mm[2]).all()
    gw.monthly_grid(tmp_path, [105.7, 20.9, 105.95, 21.15], date(2024, 1, 1), date(2024, 2, 1), "tok")
    assert len(calls) == 1                                                # Jan, Feb from the cache
    gw.monthly_grid(tmp_path, [105.7, 20.9, 105.95, 21.15], date(2024, 1, 1), date(2024, 3, 1), "tok")
    assert calls[-1][0] == date(2024, 3, 1)                               # only the missing month is asked


def test_storage_coupling_finds_an_aquifer_response():
    """Sinking that slows when storage rises (elastic aquifer, 2-month lag) is found with k < 0; a series without
    that response is not."""
    rng = np.random.default_rng(1)
    months = [f"{y}-{m:02d}" for y in range(2020, 2025) for m in range(1, 13)]
    t_m = np.arange(len(months))
    stor = 150 * np.sin(2 * np.pi * t_m / 12) + rng.normal(0, 15, len(months))
    t0 = np.datetime64("2020-01-01")
    s, changes = coupling.storage(stor, months, t0)
    obs = np.arange(np.datetime64("2020-08-01"), np.datetime64("2024-10-01"), 12)
    t = (obs - t0).astype(float)
    lagged = np.interp(t - 2 * coupling.DAYS_PER_MONTH, s.t_days, s.values)
    y = np.vstack([20 * t / 365.25 - 0.05 * lagged + rng.normal(0, 1, t.size) for _ in range(5)]
                  + [20 * t / 365.25 + rng.normal(0, 1, t.size) for _ in range(5)])
    res = coupling.couple(y, t, s, changes, max_lag=4, n_surrogates=200, seed=0)
    assert (res.p[:5] < 0.01).all() and (res.k[:5] < 0).all() and (res.lag_months[:5] == 2).all()
    assert np.median(res.p[5:]) > 0.05
    np.testing.assert_allclose(res.trend[:5], 20, atol=2)


def test_forecast_groundwater_features():
    from geoeyes.ml import forecast as fc
    months = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]
    mm = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    f = fc._gws_features((months, mm), np.datetime64("2024-01-01"), 140.0, 2)        # t0 in May 2024
    np.testing.assert_allclose([v[0] for v in f[:2]], [40 - 30, 40 - 10])
    assert np.isnan(f[2][0])                                                          # 12 months back: none
    assert all(np.isnan(v).all() for v in fc._gws_features(None, np.datetime64("2024-01-01"), 140.0, 2))
    late = np.array([10.0, 20.0, 30.0, np.nan, np.nan])                              # April, May not published
    f = fc._gws_features((months, late), np.datetime64("2024-01-01"), 140.0, 2)
    np.testing.assert_allclose([f[0][0], f[1][0]], [30 - 20, 30 - np.nan], equal_nan=True)
