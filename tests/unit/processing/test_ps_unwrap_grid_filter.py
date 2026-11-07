"""Gaussian grid prefilter of the unwrapping: σ in metres on unit phasors (a dense cell does not swamp a sparse one)
vs the legacy σ = 2 cells on the summed phasors."""
import numpy as np

from geoeyes.processing.ps.unwrap.grid import grid_wrapped


def _scene(grid_size):
    # dense stable block (30 PS per cell, phase 0) beside a sparse subsiding strip (1 PS per cell, phase 2.5 rad)
    rng = np.random.default_rng(0)
    pts, ph = [], []
    for i in range(20):
        for j in range(20):
            x0, y0 = j * grid_size, i * grid_size
            dense = j < 10
            for _ in range(30 if dense else 1):
                pts.append((x0 + rng.uniform(0.1, 0.9) * grid_size, y0 + rng.uniform(0.1, 0.9) * grid_size))
                ph.append(0.0 if dense else 2.5)
    xy = np.column_stack([np.arange(len(pts)), np.array(pts)])
    return xy, np.exp(1j * np.array(ph))[:, None]


def _sparse_phase(g):
    return np.angle(g.ph[g.ij[:, 1] == 10, 0])          # first sparse column, beside the dense block


def test_metric_sigma_keeps_the_sparse_side():
    xy, ph = _scene(50.0)
    kw = dict(grid_size=50.0, prefilt_win=16, gold_alpha=0.8, coh=None, prefilter="gaussian")
    legacy = _sparse_phase(grid_wrapped(ph, xy, **kw))
    unit = _sparse_phase(grid_wrapped(ph, xy, sigma_m=20.0, unit=True, **kw))
    assert np.median(np.abs(legacy)) < 1.0               # pulled towards the dense block's 0
    assert np.median(np.abs(unit - 2.5)) < 0.3           # σ 20 m on unit phasors: keeps its own phase


def test_auto_sigma_is_the_legacy_filter_at_10_m():
    xy, ph = _scene(10.0)
    kw = dict(grid_size=10.0, prefilt_win=16, gold_alpha=0.8, coh=None, prefilter="gaussian")
    legacy = grid_wrapped(ph, xy, **kw).ph
    auto = grid_wrapped(ph, xy, sigma_m=20.0, **kw).ph       # (16 // 8) × 10 m
    assert np.allclose(legacy, auto, atol=1e-5)
