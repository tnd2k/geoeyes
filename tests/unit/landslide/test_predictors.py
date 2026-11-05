"""Landslide study predictors (geoeyes.landslide.terrain, .predictors): curvature signs on known surfaces, every cell
drains to the edge after filling, accumulation on a plane, the collinearity screening, Hansen tiles."""
import numpy as np
import pandas as pd

from geoeyes.landslide import predictors as pr
from geoeyes.landslide import terrain as tr

D = 30.0


def _xy(n=41):
    y, x = np.mgrid[0:n, 0:n].astype(float) * D
    return x - x.mean(), y - y.mean()


def test_curvature_signs_follow_the_documented_convention():
    x, y = _xy()
    dome = -(x ** 2 + y ** 2) / 2000.0
    z = tr.zevenbergen_thorne(dome, D)
    off = (20, 30)                                      # east of the top: slope down to the east
    assert z["profile_curv"][off] > 0                   # convex along the slope (steepens downslope)
    assert z["plan_curv"][off] < 0                      # divergent across the slope (a spur)
    assert z["aspect_sin"][off] > 0.99                  # downslope points east
    hollow = y / 10.0 + x ** 2 / 2000.0                 # descends south, a trough along x = 0
    z = tr.zevenbergen_thorne(hollow, D)
    assert z["plan_curv"][20, 20] > 0                   # convergent (a hollow)
    assert z["aspect_cos"][20, 20] < -0.99              # downslope points south
    assert tr.tpi(dome, D, 150.0)[20, 20] > 0 > tr.tpi(-dome, D, 150.0)[20, 20]


def test_filled_dem_drains_every_cell_to_the_edge():
    rng = np.random.default_rng(0)
    x, y = _xy(60)
    h = x / 50 + rng.normal(0, 2.0, x.shape)            # noisy plane: many pits
    h[25:35, 25:35] -= 30                               # and a deep basin
    zf = tr.fill_depressions(h)
    assert (zf >= h - 1e-9).all()
    rec = tr.d8_receivers(zf, D).reshape(h.shape)
    interior = rec[1:-1, 1:-1]
    assert (interior >= 0).all()
    acc = tr.flow_accumulation(zf, rec.ravel())
    edge = np.zeros(h.shape, bool)
    edge[[0, -1], :] = edge[:, [0, -1]] = True
    outlets = edge & (rec < 0)
    assert np.isclose(acc[outlets].sum(), h.size)       # every cell reaches one outlet


def test_accumulation_on_a_plane_grows_downslope():
    x, y = _xy(30)
    h = 1000 + y / 5                                    # descends south
    zf = tr.fill_depressions(h)
    acc = tr.flow_accumulation(zf, tr.d8_receivers(zf, D))
    col = acc[1:-1, 15]
    assert (np.diff(col) <= 0).all() and col[0] > col[-1]


def test_hand_and_upslope_slope_on_a_valley():
    x, y = _xy(41)
    h = 500 + np.abs(x) / 3 + y / 20                    # V valley along x = 0, descending south
    zf = tr.fill_depressions(h)
    rec = tr.d8_receivers(zf, D)
    acc = tr.flow_accumulation(zf, rec)
    stream = np.zeros(h.shape, bool)
    stream[:, 20] = True                                # the valley floor
    hand = tr.height_above_drainage(h, zf, rec, stream)
    assert np.allclose(hand[:, 20], 0)
    # a side cell drains straight to the floor: its HAND is its height above the floor cell it reaches
    assert 0 < hand[20, 30] <= h[20, 30] - h[:, 20].min() and np.isclose(hand[20, 30], h[20, 30] - h[20, 20], atol=5)
    slope = tr.zevenbergen_thorne(h, D)["slope_deg"]
    up = tr.flow_accumulation(zf, rec, slope) / acc
    assert abs(up[20, 30] - slope[20, 30]) < 2.5        # a side slope: its upslope cells about as steep
    assert up[30, 20] > 3 * slope[30, 20]               # the valley floor collects the steep side slopes
    hs = tr.hillslope_layers(h, zf, rec, acc, slope, D, 0.01)
    assert set(hs) == {"slope_s90", "profile_curv_s150", "plan_curv_s150", "hand_m", "upslope_slope_deg", "spi",
                       "tpi_1000", "relief_1000"}


def test_screen_drops_the_later_of_two_collinear_layers_and_high_vif():
    rng = np.random.default_rng(1)
    n = 500
    slope = rng.normal(25, 8, n)
    s = pd.DataFrame({"slope_deg": slope, "relief_300": slope * 3 + rng.normal(0, 1, n),   # ρ ≈ 1 with slope
                      "twi": rng.normal(6, 2, n), "soil_clay": rng.normal(300, 40, n),
                      "lith_pb": (rng.random(n) > 0.2).astype(float), "lith_pa": (rng.random(n) > 0.8).astype(float)})
    s["tpi_150"] = s.twi * -1.0 + s.soil_clay * 0.01 + rng.normal(0, 0.05, n)   # a near-linear mix: high VIF
    res = pr.screen(s, list(s.columns))
    assert "relief_300" in res["dropped"] and "slope_deg" in res["trees"]
    assert "lith_pb" in res["trees"] and res["logistic"].count("lith_pb") + res["logistic"].count("lith_pa") == 1
    assert all(v <= pr.MAX_VIF for k, v in res["vif"].items() if k in res["logistic"])


def test_rare_lithology_is_merged_and_hansen_tiles():
    t = pd.DataFrame({"lith_pb": [1.0] * 199 + [0.0], "lith_va": [0.0] * 199 + [1.0], "lith_nd": [0.0] * 200})
    merged = pr.merge_rare(t, {})
    assert set(merged) == {"lith_va", "lith_nd"} and "lith_other" in t and t["lith_other"].sum() == 1
    assert pr._hansen_tiles((107.56, 14.99, 108.20, 15.21)) == ["20N_100E"]
    assert pr._hansen_tiles((109.5, 19.5, 110.5, 20.5)) == ["20N_100E", "20N_110E", "30N_100E", "30N_110E"]
