"""Infrastructure lines (geoeyes.ml.lines) and consolidation (geoeyes.ml.consolidation)."""
import numpy as np
import pytest

from geoeyes.ml import consolidation as cs
from geoeyes.ml import lines as ln


def _way(i, coords, **tags):
    return {"id": i, "tags": tags, "geometry": [{"lon": x, "lat": y} for x, y in coords]}


def test_kinds_of_line():
    assert ln._kind({"man_made": "dyke"}) == "dyke"
    assert ln._kind({"highway": "primary", "name": "Đê La Thành"}) == "dyke"
    assert ln._kind({"railway": "rail"}) == "railway"
    assert ln._kind({"highway": "trunk", "embankment": "yes"}) == "embankment"
    assert ln._kind({"highway": "motorway"}) == "road"


def test_ways_of_one_name_are_chained_whatever_their_direction():
    ways = [
        _way(1, [(0.0, 0.0), (1.0, 0.0)], highway="primary", name="A"),
        _way(2, [(2.0, 0.0), (1.0, 0.0)], highway="primary", name="A"),   # reversed
        _way(3, [(-1.0, 0.0), (0.0, 0.0)], highway="primary", name="A"),  # before the start
        _way(4, [(5.0, 5.0), (6.0, 5.0)], highway="primary", name="B"),
    ]
    lines = {line["name"]: line for line in ln.chain(ways)}
    assert set(lines) == {"A", "B"}
    np.testing.assert_array_equal(lines["A"]["coords"][:, 0], [-1, 0, 1, 2])


def test_stations_every_step_along_the_line():
    lat0 = 21.0
    kx = ln.M_LON * np.cos(np.radians(lat0))
    coords = np.array([[105.0, lat0], [105.0 + 1000 / kx, lat0]])        # 1 km east
    ch, pos = ln.stations(coords, 50.0, lat0)
    assert len(ch) == 21 and ch[-1] == 1000
    np.testing.assert_allclose(np.diff(pos[:, 0]) * kx, 50.0, rtol=1e-9)
    assert len(ln.stations(coords, 2000.0, lat0)[0]) == 0                 # shorter than one step


def test_uniform_slope_along_a_line_is_no_distortion():
    ch = np.arange(0.0, 1001.0, 50.0)
    vv = -0.1 * ch                                                        # 5 mm/yr more every 50 m: a slope
    tilt, beta = ln.distortion(ch, vv, np.full(ch.size, 0.5), 2, 10.0)
    np.testing.assert_allclose(tilt[2:], 0.1 * 10 / 1000)                 # 1/1000 of slope in 10 years
    np.testing.assert_allclose(beta[2:-2], 0.0, atol=1e-12)
    assert np.isnan(beta[:2]).all() and np.isnan(beta[-2:]).all()


def test_kink_along_a_line_is_distortion_above_noise():
    ch = np.arange(0.0, 1001.0, 50.0)
    vv = np.where(ch < 500, 0.0, -0.3 * (ch - 500))                       # flat, then sinking 30 mm/yr per 100 m
    _, beta = ln.distortion(ch, vv, np.full(ch.size, 0.5), 2, 10.0)
    i = int(np.flatnonzero(ch == 500)[0])
    assert beta[i] == pytest.approx(0.3 * 10 / 1000)                      # change of slope 0.3 mm/yr/m: 1/333
    assert np.nanmax(beta[np.abs(ch - 500) >= 100]) == 0.0                # straight on either side
    _, small = ln.distortion(ch, 0.01 * np.abs(ch - 500), np.full(ch.size, 3.0), 2, 10.0)
    assert np.nanmax(small) == 0.0                                        # within the noise: not counted


def test_consolidation_curve_is_recovered():
    t = np.arange(31) * 12 / cs.YEAR
    rng = np.random.default_rng(1)
    s = np.stack([cs.curve(0.0, 80.0, 0.4, t) + rng.normal(0, 1.0, t.size),    # consolidating
                  30.0 * t + rng.normal(0, 1.0, t.size)])                       # steady sinking
    f = cs.fit(t, s)
    assert abs(f["tau"][0] - 0.4) / 0.4 < 0.15
    assert abs(f["A"][0] - 80.0) < 8.0
    gain = cs._bic(f["rss_line"], t.size, 2) - cs._bic(f["rss"], t.size, 3)
    assert gain[0] > 6 > gain[1]


def test_asaoka_final_settlement():
    t_days = np.arange(0, 1000, 12.0)
    s = cs.curve(0.0, 100.0, 0.5, t_days / cs.YEAR)
    a = cs.asaoka(t_days, s)
    assert abs(a["final"] - 100.0) < 1.0
    assert abs(a["b1"] - np.exp(-60 / cs.YEAR / 0.5)) < 1e-3
