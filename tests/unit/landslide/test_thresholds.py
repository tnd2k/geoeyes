"""L6: rainfall events (CTRL-T simplified), the triggering event, antecedent sums, E–D threshold, best TSS cut."""
import numpy as np
import pandas as pd

from geoeyes.landslide import thresholds as th


def test_rain_events_split_on_two_dry_days():
    r = np.array([0, 5, 0, 3, 0, 0, 8, 9, 0.5, 0, 0, 2])
    assert th.rain_events(r) == [(1, 3), (6, 7), (11, 11)]          # one dry day does not split; two do


def test_triggering_cuts_at_the_landslide_day():
    ev = [(1, 3), (6, 9)]
    assert th.triggering(ev, 7) == (6, 7)
    assert th.triggering(ev, 4) == (1, 3)                          # ended the day before
    assert th.triggering(ev, 5) is None


def test_antecedent_and_percentile():
    r = np.arange(10, dtype=float)
    a = th.antecedent(r, 3)
    assert np.isnan(a[1]) and a[2] == 3 and a[9] == 24
    dates = pd.date_range("2000-01-01", periods=3 * 365)
    x = dates.dayofyear.to_numpy().astype(float)
    p = th.percentile_of(x, dates, half=0)
    assert np.allclose(p, 100.0)                                   # the same value every year: the top of its pool
    y = x + np.repeat([0.0, 1.0, 2.0], [366, 365, 364])             # rising year by year
    q = th.percentile_of(y, dates, half=0)
    assert np.isclose(q[400], 200 / 3)                              # 2001: second of three in its pool


def test_ed_threshold_and_best_cut():
    rng = np.random.default_rng(0)
    d = rng.integers(1, 15, 400).astype(float)
    e = 20 * d ** 0.6 * 10 ** rng.normal(0, 0.1, d.size)
    a, b = th.ed_threshold(e, d)
    assert abs(b - 0.6) < 0.05 and 0.02 < np.mean(e < a * d ** b) < 0.09        # ~5 % below
    pos, neg = rng.normal(2, 1, 500), rng.normal(0, 1, 5000)
    c, s = th.best_cut(pos, neg)
    assert 0.6 < c < 1.4 and s["tss"] > 0.6
