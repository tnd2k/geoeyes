"""Landslide study aspect (geoeyes.landslide.aspect): the frequency ratio, the first-harmonic azimuth recovered from a
known aspect effect, wind around a northern-hemisphere cyclone, illumination and cast shadows."""
import numpy as np
import pandas as pd

from geoeyes.landslide import aspect as asp


def _sample(n=6000, towards=180.0, strength=1.0, seed=0):
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0, 360, n)
    slope = rng.uniform(5, 45, n)
    z = -1 + 0.04 * (slope - 25) + strength * np.cos(np.radians(theta - towards))
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    t = pd.DataFrame({"theta": theta, "slope_deg": slope, "label": y, "w": 1.0,
                      "block": rng.integers(0, 60, n)})
    for k in asp.BASE_TERMS:
        t[k] = rng.normal(0, 1, n)
    return t


def test_frequency_ratio_is_flat_without_an_effect_and_peaks_where_it_is():
    t = _sample(strength=0.0)
    fr = asp.sector_ratio(t.theta.to_numpy(), t.label.to_numpy(), t.w.to_numpy())
    assert np.allclose(fr, 1, atol=0.35)
    t = _sample(towards=180.0, strength=1.0)
    fr = asp.sector_ratio(t.theta.to_numpy(), t.label.to_numpy(), t.w.to_numpy())
    assert np.argmax(fr) in (7, 8, 9) and np.argmin(fr) in (15, 0, 1)      # sector 8 = 180°


def test_conditional_model_recovers_the_azimuth_of_the_effect():
    t = _sample(towards=200.0, strength=0.8)
    c = asp.conditional(t, n_boot=20)
    lf = c["location free"]
    assert lf["p"] < 1e-6
    assert abs((lf["azimuth_deg"] - 200 + 180) % 360 - 180) < 15
    assert 0.6 < lf["amplitude"] < 1.0
    none = asp.conditional(_sample(strength=0.0, seed=3), n_boot=5)["location free"]
    assert none["p"] > 0.001


def test_wind_west_of_a_cyclone_comes_from_the_north():
    frm, dist = asp.wind_from(np.array([15.0]), np.array([110.0]), 15.0, 108.0)    # centre 2° east
    assert 330 < frm[0] < 350                     # northerly, turned 20° towards the centre (from north-north-west)
    frm, _ = asp.wind_from(np.array([13.0]), np.array([108.0]), 15.0, 108.0)        # centre to the south
    assert 70 < frm[0] < 90                       # easterly north of the centre
    assert 200 < dist[0] < 230


def test_illumination_and_cast_shadow():
    assert np.isclose(asp.cos_incidence(0.0, 123.0, 150.0, 50.0), np.sin(np.radians(50)))
    lit = asp.cos_incidence(30.0, 150.0, 150.0, 50.0)                # facing the sun
    dim = asp.cos_incidence(30.0, 330.0, 150.0, 50.0)                # facing away
    assert lit > dim > 0                                             # 30° < 50°: no self-shadow
    h = np.zeros((50, 50))
    h[30, :] = 200.0                                                 # a wall 200 m high, north of row 20
    rows, cols = np.array([20, 10]), np.array([25, 25])
    shade = asp.cast_shadow(h, rows, cols, 30.0, sun_az=0.0, sun_el=30.0)   # sun in the north
    assert shade[0] and not shade[1]                                 # 300 m away: 33.7° > 30°; 600 m: 18.4°
