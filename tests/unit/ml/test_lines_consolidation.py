"""Infrastructure lines (geoeyes.ml.lines) and consolidation (geoeyes.ml.consolidation)."""
import numpy as np

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
