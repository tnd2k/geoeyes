"""Spatial outliers (products/spatial_filter.py): a single PS far from its neighbours is left out; a subsidence
bowl, its edges and a lone point without neighbours are kept."""
import numpy as np

from geoeyes.products.spatial_filter import SpatialFilter, spatial_outliers


def _scene(seed=0, n=20000, size=3000.0):
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, size, n), rng.uniform(0, size, n)
    lat0 = 10.7
    lon = 106.6 + x / (111_320.0 * np.cos(np.radians(lat0)))
    lat = lat0 + y / 110_540.0
    v = -45 * np.exp(-((x - 1500) ** 2 + (y - 1500) ** 2) / 400 ** 2) + rng.normal(0, 1.5, n)   # a bowl to -45
    return rng, x, y, lon, lat, v


def test_single_outliers_left_out_bowl_kept():
    rng, x, y, lon, lat, v = _scene()
    far = np.hypot(x - 1500, y - 1500) > 900
    spikes = rng.choice(np.flatnonzero(far), 40, replace=False)
    v[spikes] -= rng.uniform(25, 60, spikes.size)
    bad = spatial_outliers(lon, lat, [v])
    assert bad[spikes].mean() > 0.95
    others = np.ones(v.size, bool)
    others[spikes] = False
    assert bad[others].mean() < 1e-3                                # the bowl and its slopes stay
    assert not bad[np.hypot(x - 1500, y - 1500) < 300].any()


def test_any_velocity_kind_and_lone_points():
    rng, x, y, lon, lat, v = _scene(seed=1)
    w = v.copy()
    w[7] += 40                                                      # off in a second velocity kind only
    lon = np.r_[lon, 107.5]                                         # a point far from all: kept
    lat = np.r_[lat, 11.5]
    bad = spatial_outliers(lon, lat, [np.r_[v, -80.0], np.r_[w, -80.0]])
    assert bad[7] and not bad[-1]
    assert not spatial_outliers(lon, lat, [np.r_[v, -80.0]], SpatialFilter(dv_min=100.0)).any()
