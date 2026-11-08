"""Whole-cycle patches (unwrap/patch_cycles.py): an oval region a cycle off at one date is moved back; a lone PS off
by a cycle, a real subsidence bowl and a fast linear trend are left alone."""
import numpy as np

from geoeyes.processing.ps.unwrap.patch_cycles import fix_patch_cycles

TWO_PI = 2 * np.pi


def _scene(seed=0, n=6000, m=60, size=2000.0, cell=50.0):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, size, (n, 2))
    t = np.arange(1, m + 1) * 12 / 365.25
    ij = np.floor(xy / cell).astype(np.int64)
    shape = (int(size // cell) + 1,) * 2
    return rng, xy, t, ij, shape


def test_oval_patch_moved_back_and_lone_ps_kept():
    rng, xy, t, ij, shape = _scene()
    n, m = xy.shape[0], t.size
    rate = -TWO_PI * 1.5 * np.exp(-(((xy[:, 0] - 600) ** 2 + (xy[:, 1] - 1400) ** 2) / 300 ** 2))  # a bowl, rad/yr
    truth = rate[:, None] * t[None, :] + 0.6 * np.sin(TWO_PI * t)[None, :]
    ph = truth + rng.normal(0, 0.5, (n, m))
    oval = ((xy[:, 0] - 1300) / 400) ** 2 + ((xy[:, 1] - 700) / 250) ** 2 < 1
    ph[oval, 20] += TWO_PI                                    # the grid put this region a cycle off on date 21
    ph[oval, 41] -= TWO_PI                                    # and the other way on date 42
    lone = np.flatnonzero(~oval)[:5]
    ph[lone, 30] += TWO_PI                                    # single PS off: noise, not a patch
    fixed, k = fix_patch_cycles(ph, t, ij, shape)
    assert np.mean(k[oval, 20] == 1) > 0.97 and np.mean(k[oval, 41] == -1) > 0.97
    assert np.all(k[lone, 30] == 0)
    others = np.ones((n, m), bool)
    others[oval, 20] = others[oval, 41] = False
    assert np.mean(k[others] != 0) < 1e-3                     # the bowl and the trend are not touched
    assert np.abs(np.median(fixed[oval, 20] - truth[oval, 20])) < 0.3


def test_patch_found_under_arbitrary_epoch_constants():
    # the IRLS result of every interferogram carries its own constant until the reference step
    rng, xy, t, ij, shape = _scene(seed=2)
    n, m = xy.shape[0], t.size
    const = rng.uniform(-3, 3, m)
    clean = -TWO_PI * 0.5 * t[None, :] + const[None, :] + rng.normal(0, 0.5, (n, m))
    ph = clean.copy()
    oval = ((xy[:, 0] - 900) / 500) ** 2 + ((xy[:, 1] - 1000) / 350) ** 2 < 1      # ~30 % of the scene
    ph[oval, 10] -= TWO_PI
    fixed, k = fix_patch_cycles(ph, t, ij, shape)
    assert np.mean(k[oval, 10] == -1) > 0.97
    k[oval, 10] = 0
    assert np.mean(k != 0) < 1e-3
    assert np.allclose(np.median(fixed[oval, 10] - clean[oval, 10]), 0, atol=0.3)


def test_fast_trend_without_patches_untouched():
    rng, xy, t, ij, shape = _scene(seed=1)
    rate = np.where(xy[:, 0] > 1000, -TWO_PI * 3.0, 0.0)      # half the scene at ~-80 mm/yr: a step in rate
    ph = rate[:, None] * t[None, :] + rng.normal(0, 0.6, (xy.shape[0], t.size))
    _, k = fix_patch_cycles(ph, t, ij, shape)
    assert np.mean(k != 0) < 1e-3
