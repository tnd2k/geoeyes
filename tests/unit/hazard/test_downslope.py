"""Downslope rate from a LOS rate (hazard.terrain.los_terrain / downslope_rate)."""
import numpy as np

from geoeyes.hazard.terrain import downslope_rate, los_terrain


def _slope(deg: float, down_az_deg: float, n: int = 1) -> dict:
    s, a = np.radians(deg), np.radians(down_az_deg)
    return {"slope_deg": np.full(n, deg), "down_e": np.full(n, np.sin(a) * np.cos(s)),
            "down_n": np.full(n, np.cos(a) * np.cos(s)), "down_u": np.full(n, -np.sin(s))}


# ascending Sentinel-1, right looking: the satellite to the west, 37 deg incidence (ground -> satellite)
INC, LOOK = np.radians(37.0), np.radians(77.7)
LOS = (-np.sin(INC) * np.sin(LOOK), -np.sin(INC) * np.cos(LOOK), np.cos(INC))


def test_slope_facing_away_moving_down_reads_negative_and_is_recovered():
    t = _slope(25.0, 77.7)                         # faces east, away from the satellite
    g = los_terrain(t, *LOS)
    assert g["sensitivity"][0] < -0.3 and bool(g["visible"][0])
    m = 12.0                                       # mm/yr down the slope
    assert np.isclose(downslope_rate(m * g["sensitivity"], t, *LOS)[0], m)


def test_flat_ground_slope_along_track_and_layover_are_hidden():
    flat = los_terrain(_slope(3.0, 77.7), *LOS)
    # a gentle slope down the flight direction: only its small vertical part reaches the LOS (0.17 of the motion);
    # a steeper one (30 deg) is seen through its vertical part (0.4)
    along = los_terrain(_slope(12.0, -12.3), *LOS)
    assert los_terrain(_slope(30.0, -12.3), *LOS)["visible"][0]
    layover = los_terrain(_slope(45.0, 257.7), *LOS)           # steeper than the incidence, faces the satellite
    assert not flat["visible"][0] and not along["visible"][0]
    assert layover["local_inc_deg"][0] < 5 and not layover["visible"][0]
    assert np.isnan(downslope_rate(np.array([-5.0]), _slope(45.0, 257.7), *LOS)[0])
