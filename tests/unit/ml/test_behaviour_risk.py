"""Kinds of motion (geoeyes.ml.behaviour) and risk to buildings (geoeyes.ml.risk)."""
import numpy as np

from geoeyes.ml import behaviour as bh
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
