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
