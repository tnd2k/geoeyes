"""Dating the loss of vegetation (geoeyes.landslide.dating): the bracket needs a lasting drop, the class follows the
months of the bracket."""
from datetime import date

import numpy as np
import pandas as pd

from geoeyes.landslide import dating as dt


def test_bracket_needs_a_lasting_drop():
    d = [date(2020, 1, 10), date(2020, 3, 1), date(2020, 9, 20), date(2020, 11, 20), date(2021, 1, 15)]
    nd = np.array([0.85, 0.84, 0.86, 0.40, 0.45])           # lost between 20 Sep and 20 Nov
    lo, hi, level = dt.bracket(d, nd, date(2020, 10, 5))
    assert (lo, hi) == (date(2020, 9, 20), date(2020, 11, 20)) and abs(level - 0.85) < 0.01
    nd2 = np.array([0.85, 0.40, 0.86, 0.85, 0.84])           # one cloudy-looking dip that recovers: not a loss
    assert dt.bracket(d, nd2, date(2020, 10, 5))[:2] == (None, None)


def test_persistent_means_still_bare_next_season():
    p = dt.persistent([0.85, 0.85, 0.85, np.nan], [0.50, 0.80, np.nan, 0.5])
    assert bool(p[0]) is True and bool(p[1]) is False and p[2] is pd.NA and p[3] is pd.NA


def test_classes_follow_the_months():
    assert dt.classify(date(2020, 9, 20), date(2020, 11, 20)) == "rain_season"
    assert dt.classify(date(2021, 1, 20), date(2021, 3, 5)) == "dry_season"
    assert dt.classify(date(2020, 8, 1), date(2020, 10, 1)) == "undated"          # spans both
    assert dt.classify(date(2020, 3, 1), date(2020, 11, 1)) == "undated"          # too wide
    assert dt.classify(None, date(2020, 11, 1)) == "undated"
