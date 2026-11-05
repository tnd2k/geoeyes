import math

import numpy as np
import pandas as pd

from geoeyes.landslide import insar
from geoeyes.ml.layers import M_PER_DEG_LAT, M_PER_DEG_LON


def _cells():
    lat0 = 15.0
    kx = M_PER_DEG_LON * math.cos(math.radians(lat0))
    lon = (np.array([1000, 1001]) + 0.5) * 100 / kx
    lat = (np.array([16000, 16000]) + 0.5) * 100 / M_PER_DEG_LAT
    return pd.DataFrame({"lon": lon, "lat": lat, "mode": ["landslide", "subsidence"], "sensitivity": [0.8, 0.9],
                         "rate_mm_yr": [-12.0, -3.0], "stable_mm_yr": [4.0, 4.0], "coherence": [0.7, 0.8],
                         "n_points": [5, 9]}), kx


def test_attach_takes_the_holding_cell_and_masks_other_modes():
    cells, kx = _cells()
    y = cells.lat[0]
    pts_lon = np.array([cells.lon[0] + 30 / kx, cells.lon[1], cells.lon[0] + 500 / kx])
    f = insar.attach(pts_lon, np.full(3, y), cells, 100.0)
    assert f.insar_rate_mm_yr[0] == -12.0 and f.insar_moving[0] == 1.0 and f.insar_covered[0] == 1
    assert np.isnan(f.insar_rate_mm_yr[1]) and f.insar_covered[1] == 0       # subsidence mode: not a slope motion
    assert f.insar_points[1] == 9                                             # but its density is kept
    assert f.insar_covered[2] == 0 and np.isnan(f.insar_points[2])            # no cell within reach


def test_coverage_by_forest():
    pred = pd.DataFrame({"in_fp": [True, True, True, True, False], "slope_deg": [20, 20, 20, 5, 30],
                         "tree_cover_2000": [80, 80, 10, 10, 10]})
    feats = pd.DataFrame({"insar_covered": [1, 0, 1, 1, 1]})
    c = insar.coverage(pred, feats, "in_fp")
    assert c["slope_cells"] == 3 and c["covered"] == 2
    assert c["by_forest"]["forest"]["share"] == 0.5 and c["by_forest"]["open"]["share"] == 1.0
