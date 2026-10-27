"""Vertical / east-west decomposition (geoeyes.ml.decompose) and soft-soil thickness (geoeyes.ancillary.geology,
geoeyes.ml.geology)."""
import numpy as np
import pandas as pd

from geoeyes.ancillary.geology import GeologyParams, idw
from geoeyes.ml import decompose as dc
from geoeyes.ml import geology as gl

ASC = (-0.62, -0.13, 0.77)       # Sentinel-1 ascending, seen from the west
DESC = (0.62, -0.13, 0.77)       # descending, seen from the east


def test_east_and_up_are_recovered_from_two_looks():
    rng = np.random.default_rng(0)
    east = rng.normal(0, 10, 200)
    up = rng.normal(-20, 15, 200)
    v = np.column_stack([east * ASC[0] + up * ASC[2], east * DESC[0] + up * DESC[2]])
    le = np.tile([ASC[0], DESC[0]], (200, 1))
    lu = np.tile([ASC[2], DESC[2]], (200, 1))
    r = dc.solve(v, np.ones_like(v), le, lu)
    np.testing.assert_allclose(r["east"], east, atol=1e-9)
    np.testing.assert_allclose(r["up"], up, atol=1e-9)
    # opposite looks: east is less constrained than up (|l_e| < |l_u|)
    assert r["sigma_east"][0] > r["sigma_up"][0]


def test_vertical_projection_is_biased_by_horizontal_motion():
    east, up = 10.0, -5.0
    v_asc = east * ASC[0] + up * ASC[2]
    assert abs(v_asc / ASC[2] - up) > 7          # one geometry: 8 mm/yr off
    r = dc.solve(np.array([[v_asc, east * DESC[0] + up * DESC[2]]]), np.ones((1, 2)),
                 np.array([[ASC[0], DESC[0]]]), np.array([[ASC[2], DESC[2]]]))
    assert abs(r["up"][0] - up) < 1e-9


def test_cell_velocities_median_and_minimum_points():
    grid = {"lon0": 0.0, "lat0": 0.0, "dlon": 0.001, "dlat": 0.001, "nx": 10, "ny": 10}
    pts = pd.DataFrame({"lon": [0.0005] * 4 + [0.0025] * 2, "lat": [0.0005] * 4 + [0.0005] * 2,
                        "vel_los_mm_yr": [1.0, 2.0, 3.0, 100.0, 5.0, 5.0], "vel_std_mm_yr": 1.0,
                        "los_e": 0.6, "los_n": -0.1, "los_u": 0.77})
    c = dc.cell_velocities(pts, grid, dc.DecomposeParams(min_points=3))
    assert list(c.index) == [0] and c.loc[0, "v"] == 2.5 and c.loc[0, "n"] == 4


def test_point_neighbourhood_median_without_grid():
    kx = dc.M_LON * np.cos(np.radians(21.0))
    # three points within 10 m of the location, one 50 m away
    lon = 105.8 + np.array([0.0, 5.0, -5.0, 50.0]) / kx
    pts = pd.DataFrame({"lon": lon, "lat": 21.0, "vel_los_mm_yr": [1.0, 2.0, 3.0, 100.0], "vel_std_mm_yr": 1.0,
                        "los_e": 0.6, "los_n": -0.1, "los_u": 0.77})
    xy = np.array([[105.8 * kx, 21.0 * dc.M_LAT], [106.0 * kx, 21.0 * dc.M_LAT]])
    c = dc.point_velocities(pts, xy, kx, dc.DecomposeParams(support="points", radius_m=20, min_points=3))
    assert c.loc[0, "v"] == 2.0 and c.loc[0, "n"] == 3
    assert np.isnan(c.loc[1, "v"]) and c.loc[1, "n"] == 0


def test_boreholes_interpolated_and_masked_far_away():
    blon = np.array([105.80, 105.82, 105.80])
    blat = np.array([21.00, 21.00, 21.02])
    v, d = idw(np.array([105.80, 105.81, 106.5]), np.array([21.00, 21.00, 21.0]), blon, blat,
               np.array([10.0, 30.0, 20.0]), power=2, k=8, max_km=3)
    assert abs(v[0] - 10.0) < 1e-3                  # on a borehole
    assert 10 < v[1] < 30
    assert np.isnan(v[2]) and d[2] > 3


def test_implied_cv_terzaghi():
    # 10 m of clay drained on both faces (H_dr = 5 m), τ = 4·25 / (π²·2) ≈ 5.07 yr for c_v = 2 m²/yr
    tau = 4 * 25 / (np.pi ** 2 * 2.0)
    assert abs(gl.implied_cv(np.array([10.0]), np.array([tau]))[0] - 2.0) < 1e-9
    assert abs(gl.implied_cv(np.array([5.0]), np.array([tau]), "single")[0] - 2.0) < 1e-9


def test_rates_by_thickness_class():
    rng = np.random.default_rng(1)
    h = rng.uniform(0, 40, 500)
    rate = -h + rng.normal(0, 1, 500)                # thicker, faster
    b = gl.by_class(h, rate, rate < 0, 4, 5.0)
    assert len(b) == 4
    assert b[0]["median_rate_mm_yr"] > b[-1]["median_rate_mm_yr"]
    assert GeologyParams.from_dict({"open_fallback": "false"}).open_fallback is False
