"""SCN spatial filter: the grid (normalised convolution) form approximates the exact pairwise Gaussian."""
import numpy as np
from scipy.spatial import cKDTree

from geoeyes.processing.ps.steps.scn_filt import _gaussian_grid


def test_grid_matches_pairwise_gaussian():
    rng = np.random.default_rng(1)
    xy = rng.uniform(0, 3000, (3000, 2))
    v = (np.sin(xy[:, 0] / 400) + np.cos(xy[:, 1] / 300))[:, None] + 0.3 * rng.standard_normal((3000, 1))
    lam = 100.0
    t = cKDTree(xy)
    exact = np.empty(len(xy))
    for i, nb in enumerate(t.query_ball_point(xy, 4 * lam)):
        w = np.exp(-np.sum((xy[nb] - xy[i]) ** 2, axis=1) / (2 * lam**2))
        exact[i] = np.sum(w * v[nb, 0]) / np.sum(w)
    grid = _gaussian_grid(xy, v, lam, None)[:, 0]
    assert np.sqrt(np.mean((grid - exact) ** 2)) < 0.05 * np.std(exact)


def test_large_network_solver_matches_direct(monkeypatch):
    """When the sparse LU fails, the arc network is integrated by ILU-preconditioned CG: same answer."""
    from geoeyes.processing.ps.steps import scn_filt as m
    rng = np.random.default_rng(2)
    n, n_sec = 4000, 5
    xy = np.column_stack([np.arange(n), rng.uniform(0, 2000, (n, 2))])
    kw = dict(ph_uw=rng.standard_normal((n, n_sec)), ph_scla=np.zeros((n, n_sec)), C_uw=np.zeros(n),
              ph_ramp=np.zeros((n, 0)), day=np.arange(n_sec + 1) * 12.0, master_ix=0, xy=xy,
              weights=rng.uniform(0.2, 1.0, n))
    direct = m.scn_filt(**kw).ph_hpt
    monkeypatch.setattr(m, "DIRECT", False)
    iterative = m.scn_filt(**kw).ph_hpt
    np.testing.assert_allclose(iterative, direct, atol=1e-4)


def test_time_lowpass_keeps_a_trend():
    """The local linear low-pass reproduces a linear trend exactly, also in a series shorter than the window,
    where the StaMPS weighted mean leaks most of it into the high-pass (the SCN)."""
    from geoeyes.processing.ps.steps.scn_filt import time_lowpass
    d = np.arange(0, 180, 12, dtype=float)                       # 6 months of 12-day dates
    trend = -0.2 * d                                             # a steady motion
    lin = time_lowpass(d, 365.0, "linear")
    mean = time_lowpass(d, 365.0, "mean")
    np.testing.assert_allclose(lin @ trend, trend, atol=1e-9)
    leak = trend - mean @ trend
    assert np.abs(leak).max() > 0.4 * np.abs(trend).max()          # most of the trend becomes "noise"
    np.testing.assert_allclose(lin.sum(axis=1), 1.0)
    np.testing.assert_allclose(mean.sum(axis=1), 1.0)
    noise = np.random.default_rng(0).normal(0, 1, (200, d.size))
    hp = noise - noise @ lin.T                                   # white noise mostly stays high-pass
    assert 0.7 < hp.std() / noise.std() < 1.0
