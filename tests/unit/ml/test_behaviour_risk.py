"""Kinds of motion (geoeyes.ml.behaviour) and risk to buildings (geoeyes.ml.risk)."""
import numpy as np
import pytest

from geoeyes.ml import behaviour as bh
from geoeyes.ml import buildings as bd
from geoeyes.ml import risk as rk


def _series(n=30, seed=0):
    rng = np.random.default_rng(seed)
    t_days = np.arange(n) * 12.0
    t = t_days / 365.2425
    noise = lambda: rng.normal(0, 1.0, n)  # noqa: E731
    out = {
        "stable": noise(),
        "steady": -20 * t + noise(),
        "seasonal": -5 * t + 12 * np.sin(2 * np.pi * t) + noise(),
        "speeding": -5 * t - 40 * t ** 2 + noise(),
        "slowing": -60 * t + 40 * t ** 2 + noise(),
        "onset": -60 * np.maximum(0, t - t[15]) + noise(),
        "step": -2 * t - 25 * (t >= t[12]) + noise(),
    }
    return t_days, out


def test_each_kind_of_motion_is_recognised():
    t_days, s = _series()
    names = list(s)
    r = bh.classify(t_days, np.stack([s[k] for k in names]), np.full(len(names), 2.0), bh.BehaviourParams())
    got = [bh.CLASSES[c] for c in r["cls"]]
    assert got == names, got
    i = names.index("onset")
    assert r["t0"][i] in (14, 15, 16)
    assert r["rate_after"][i] < -40 and abs(r["rate_before"][i]) < 10        # GeoEyes sign: sinking < 0
    assert names.index("step") and r["jump"][names.index("step")] < -20
    assert r["amp"][names.index("seasonal")] > 9
    assert np.isfinite(r["fit"]).all()


def test_uplift_reads_along_its_own_motion():
    """A rising cell whose uplift grows is 'speeding' too (classes follow the cell's own motion)."""
    t_days, s = _series(seed=1)
    r = bh.classify(t_days, np.stack([-s["speeding"]]), np.array([2.0]), bh.BehaviourParams())
    assert bh.CLASSES[r["cls"][0]] == "speeding"


def test_risk_classes():
    p = rk.RiskParams()
    area = np.array([50.0, 400.0, 2000.0, 400.0])
    height = np.array([3.0, np.nan, 30.0, np.nan])
    floors = np.array([1.0, 3.0, 10.0, 3.0])
    e = rk.exposure(area, floors, p)
    v = rk.vulnerability(area, height, p)
    assert list(e) == [1, 2, 3, 2] and list(v) == [1, 2, 3, 2]
    c, r = rk.combine(np.array([4, 2, 3, -1]), e, v)
    assert list(c) == [1, 2, 3, 2]
    assert list(r) == [3, 2, 4, -1]                                           # very high hazard on a shed: high


def _building(seed=0, n=40, size=30.0):
    rng = np.random.default_rng(seed)
    return rng.uniform(-size / 2, size / 2, n), rng.uniform(-size / 2, size / 2, n), rng


def test_pure_tilt_gives_tilt_but_no_distortion():
    x, y, rng = _building()
    vv = -10.0 + 0.8 * x + 0.3 * y + rng.normal(0, 0.5, x.size)              # rigid tilt + PS noise
    r = bd.tilt_and_distortion(x, y, vv, np.full(x.size, 0.5))
    assert r["tilt_10yr"] == pytest.approx(np.hypot(0.8, 0.3) * 10 / 1000, rel=0.1)
    assert np.isnan(r["beta_10yr"])                                           # the residuals are noise only
    r = bd.tilt_and_distortion(x, y, -10.0 + 0.8 * x)                         # noise-free, no PS standard errors
    assert r["tilt"] > 0 and np.isnan(r["beta_10yr"]) and r["distortion"] < 1e-9


def test_bowl_gives_distortion():
    x, y, rng = _building(1)
    vv = -10.0 - 0.05 * (x ** 2 + y ** 2) + rng.normal(0, 0.5, x.size)       # sagging: 11 mm/yr centre to corner
    r = bd.tilt_and_distortion(x, y, vv)
    assert r["beta_10yr"] > 1 / 500
    assert np.isnan(r["tilt"])                                                # symmetric bowl: no rigid tilt


def test_own_secondary_is_the_larger_of_distortion_and_tilt():
    p = rk.RiskParams()
    beta = np.array([1 / 400, np.nan, 1 / 100, np.nan])
    tilt = np.array([1 / 200, 1 / 50, np.nan, np.nan])
    s = rk.own_secondary(beta, tilt, (1 / 500, 1 / 300, 1 / 150), p.tilt_breaks, np.array([0, 0, 0, 2]))
    assert list(s) == [2, 3, 3, 2]                                            # last: the cell's S
