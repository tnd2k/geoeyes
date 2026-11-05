"""Landslide study independent check (geoeyes.landslide.verify): patches keep only small scars, the capture test
finds an inventory that misses scars on one aspect, the local incidence masks layover and shadow."""
import numpy as np
import pandas as pd

from geoeyes.landslide import aspect as asp
from geoeyes.landslide import verify as vf
from geoeyes.ml.layers import Grid


def test_patches_keep_small_connected_scars_only():
    g = Grid([108.0, 15.0, 108.02, 15.02], 30.0, 15.01)
    m = np.zeros((g.ny, g.nx), bool)
    m[2:4, 2:4] = True                       # 4 cells = 0.36 ha
    m[10:30, 10:30] = True                   # 400 cells = 36 ha: clearing, not a scar
    lab = vf.patches(m.ravel(), g, 30.0, max_ha=5.0)
    assert len(np.unique(lab[lab > 0])) == 1
    assert (lab.reshape(g.ny, g.nx)[2:4, 2:4] > 0).all() and (lab.reshape(g.ny, g.nx)[10:30, 10:30] == 0).all()


def test_capture_test_finds_an_inventory_that_misses_north_facing_scars():
    rng = np.random.default_rng(0)
    n = 1500
    theta = rng.uniform(0, 360, n)
    p = 0.45 + 0.35 * np.cos(np.radians(theta - 180))          # captured mostly on south-facing slopes
    pt = pd.DataFrame({"theta": theta, "slope_deg": rng.uniform(15, 45, n), "area_ha": rng.uniform(0.1, 3, n),
                       "captured": (rng.random(n) < p).astype(int)})
    for k in asp.BASE_TERMS:
        pt[k] = rng.normal(0, 1, n)
    c = vf.capture_test(pt)
    assert c["p"] < 1e-6 and abs((c["azimuth_deg"] - 180 + 180) % 360 - 180) < 20
    assert c["rate_by_sector"][4] > c["rate_by_sector"][0]    # S above N
    pt["captured"] = (rng.random(n) < 0.45).astype(int)
    assert vf.capture_test(pt)["p"] > 0.001


def test_local_incidence_of_a_descending_pass():
    heading = 192.0                                            # descending, right-looking: the satellite is to the east
    assert np.isclose(vf.local_incidence(30.0, 102.0, 39.0, heading), 9.0)     # facing the satellite: foreshortened
    assert np.isclose(vf.local_incidence(30.0, 282.0, 39.0, heading), 69.0)    # facing away
    assert np.isclose(vf.local_incidence(0.0, 0.0, 39.0, heading), 39.0)
