"""``unwrap_time_win = "auto"``: a quarter of the data span, at least four sampling intervals, 60-730 days."""
import numpy as np

from geoeyes.processing.ps.params import auto_time_win


def test_auto_time_win_follows_the_span():
    # 46 dates over 1.86 years at 6/12-day spacing (HCMC 2017-2019): a quarter of 679 days
    days = np.r_[np.arange(0, 540, 12), [679]]
    assert auto_time_win(days) == round(679 / 4)
    # a long stack is capped at the StaMPS 730 days, a short one floored at 60
    assert auto_time_win(np.arange(0, 4000, 12)) == 730
    assert auto_time_win(np.arange(0, 120, 12)) == 60


def test_auto_time_win_keeps_enough_dates_and_degenerate_stacks():
    # monthly sampling over a year: 4 intervals (~120 days) win over span / 4 (~91)
    assert auto_time_win(np.arange(0, 365, 30.4)) == 122
    assert auto_time_win([5, 5]) == 730
