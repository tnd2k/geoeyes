import numpy as np

from geoeyes.processing.ps.candidates import select_ds


def test_select_ds_best_per_block():
    t = np.full((7, 8), 0.2, np.float32)
    t[1, 2] = 0.9                                  # block (0, 0)
    t[0, 0] = 0.8                                  # same block, lower
    t[4, 4], t[5, 5] = 0.95, 0.85                  # block (1, 1): best excluded -> next best
    t[6, 7] = 0.75                                 # partial edge block
    t[2, 7] = np.nan
    excl = np.zeros(t.shape, bool)
    excl[4, 4] = True
    r, c = select_ds(t, excl, 0.7, cell=3)
    assert sorted(zip(r.tolist(), c.tolist())) == [(1, 2), (5, 5), (6, 7)]
