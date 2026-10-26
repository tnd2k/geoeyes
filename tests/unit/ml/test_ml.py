"""AI on products (geoeyes.ml): the forecast backtest picks the right family of model and never trains on the
future; the susceptibility models find the layer that drives the labels; Overture geometry decoding."""
import numpy as np
import pandas as pd
import pytest

from geoeyes.ml import forecast as fc
from geoeyes.ml import overture
from geoeyes.ml.layers import Grid


def _series(kind: str, n: int = 400, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = np.arange(np.datetime64("2023-01-01"), np.datetime64("2025-01-01"), 12)
    t = (dates - dates[0]).astype(float) / 365.25
    rate = rng.normal(-20, 8, n)[:, None]
    noise = rng.normal(0, 1.0, (n, t.size))
    # "walk": a random walk, for which no change is the best forecast (white noise would revert to its mean, and a
    # model that learns the reversion rightly beats "no change")
    y = rate * t[None, :] + noise if kind == "trend" else np.cumsum(noise * 3, axis=1)
    return dates, y - y[:, :1]


def test_forecast_picks_linear_for_trends_and_last_for_random_walks():
    p = fc.ForecastParams(horizons_days=(60, 120), n_origins=2)
    dates, y = _series("trend")
    r = fc.forecast(dates, y, p)
    assert r["chosen"] in ("linear", "gbm")
    assert r["mae"]["linear"][120] < 0.3 * r["mae"]["last"][120]
    dates, y = _series("walk")
    assert fc.forecast(dates, y, p)["chosen"] == "last"


def test_backtest_trains_on_the_past_only(monkeypatch):
    """Every training target of a backtest cut-off ends at or before it."""
    seen = []
    real = fc._samples

    def spy(t, y, origins, horizons, day0, drivers, rng, max_rows, until):
        x, yy = real(t, y, origins, horizons, day0, drivers, rng, max_rows, until)
        seen.append((until, max((o + h for o in origins for h in horizons if o + h <= until + 1e-9), default=-1)))
        return x, yy

    monkeypatch.setattr(fc, "_samples", spy)
    dates, y = _series("trend", n=120)
    fc.forecast(dates, y, fc.ForecastParams(horizons_days=(60,), n_origins=2))
    assert seen and all(last <= until + 1e-9 for until, last in seen)


def test_conformal_widths_grow_with_noise():
    p = fc.ForecastParams(horizons_days=(60,), n_origins=3)
    d1, y1 = _series("trend", seed=1)
    d2, y2 = _series("trend", seed=1)
    y2 = y2 + np.random.default_rng(9).normal(0, 6, y2.shape)
    w1 = fc.forecast(d1, y1, p)["widths"][60][0.8]
    w2 = fc.forecast(d2, y2, p)["widths"][60][0.8]
    assert w2 > 2 * w1


def test_grid_cell_of():
    g = Grid([105.80, 21.00, 105.81, 21.01], 100.0, 21.0)
    i = g.cell_of(g.lon[:5], g.lat[:5])
    np.testing.assert_array_equal(i, np.arange(5))
    assert g.cell_of(np.array([0.0]), np.array([0.0]))[0] == -1


def test_susceptibility_finds_the_driving_layer(monkeypatch, tmp_path):
    """Labels driven by 'built-up' (plus noise): every model scores well in spatial CV and ranks it first."""
    import json

    from geoeyes.ml import susceptibility as su
    rng = np.random.default_rng(3)
    g = Grid([105.80, 21.00, 105.86, 21.05], 100.0, 21.02)
    n = len(g)
    # smooth spatial pattern: neighbouring cells share built-up shares, as in a city
    built = np.clip(0.5 + 0.4 * np.sin(g.lon * 300) * np.cos(g.lat * 300) + rng.normal(0, 0.1, n), 0, 1)

    def fake_layers(grid, **kw):
        t = pd.DataFrame({"kx": grid.kx, "ky": grid.ky, "lon": grid.lon, "lat": grid.lat})
        for k in su.LAYERS:
            t[k] = rng.normal(0, 1, len(grid)).astype(np.float32)
        t["lc_built"] = built.astype(np.float32)
        return t, []

    monkeypatch.setattr(su, "build_layers", fake_layers)
    hz = tmp_path / "hazard"
    hz.mkdir()
    rate = -(20 * built + rng.normal(0, 3, n))                      # sinking (negative) faster where built up
    pd.DataFrame({"lon": g.lon, "lat": g.lat, "rate_mm_yr": rate, "n_points": 10, "mode": "subsidence"}) \
        .to_parquet(hz / "cells.parquet")
    (hz / "hazard.json").write_text(json.dumps({"bounds": [105.80, 21.00, 105.86, 21.05], "lat0": 21.02,
                                                "sign": "negative = sinking / downslope",
                                                "params": {"cell_m": 100.0}, "reference": {"kind": "test"}}))
    s = su.run(tmp_path / "p_v1", tmp_path / "out", su.SusceptibilityParams(label_rate=10.0, block_m=500.0),
               hazard_dir=hz, dem_source="", dem_cache=tmp_path, overture_cache=tmp_path)
    for m in su.MODELS:
        assert s["models"][m]["spatial_cv"]["auc"] > 0.8
        imp = s["models"][m]["importance"]
        assert max(imp, key=imp.get) == "lc_built"
    assert s["odds_ratio_per_sd"]["lc_built"] > 2
    grid = pd.read_parquet(tmp_path / "out" / "grid.parquet")
    assert grid["probability"].between(0, 1).all() and grid["label"].notna().sum() == n


def test_overture_rings_and_area():
    # MVT geometry of a 100 x 100 unit square: MoveTo(10,10) LineTo(+100,0)(0,+100)(-100,0) ClosePath
    def zz(v):
        return (v << 1) ^ (v >> 31)
    geom = [9, zz(10), zz(10), (3 << 3) | 2, zz(100), zz(0), zz(0), zz(100), zz(-100), zz(0), 15]
    rings = overture._rings(geom)
    assert len(rings) == 1 and rings[0].shape == (4, 2)
    np.testing.assert_array_equal(rings[0][2], [110, 110])
    tiles = overture.tiles_over([105.84, 21.02, 105.85, 21.03])          # ~1 km box on a z14 tile corner
    xs, ys = sorted({x for x, _ in tiles}), sorted({y for _, y in tiles})
    assert len(tiles) == len(xs) * len(ys) and xs == list(range(xs[0], xs[-1] + 1)) and len(tiles) <= 4


@pytest.mark.parametrize("bad", [{"cell": 3}, {"horizons": [1]}])
def test_params_reject_unknown_keys(bad):
    from geoeyes.core.errors import ConfigError
    from geoeyes.ml.susceptibility import SusceptibilityParams
    with pytest.raises(ConfigError):
        fc.ForecastParams.from_dict(bad)
    with pytest.raises(ConfigError):
        SusceptibilityParams.from_dict(bad)
