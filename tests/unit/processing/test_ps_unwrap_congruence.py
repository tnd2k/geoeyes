"""Snapping an IRLS solution to the wrapped phase must not depend on the interferogram's mean phase.

The least-squares integration is defined up to a constant (zero mean / median); with an interferogram whose mean
phase is near ±π, (u - φ) / 2π sits near ±1/2 in every cell, the noise decides the rounding and whole regions end up
one cycle off with sharp boundaries (Tenerife ICEYE 2026-02-19 / 02-27: a 13 mm step along a straight line)."""
import numpy as np

from geoeyes.processing.ps.unwrap.irls import dct_init, enforce_congruence, irls_unwrap


def _unwrap(mean_phase: float, noise: float, seed: int):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:120, 0:120]
    base = 0.03 * x + 0.02 * y + 0.8 * np.sin(x / 15.0)                               # smooth, < 1 rad / cell
    true = base - base.mean() + mean_phase
    wrapped = np.angle(np.exp(1j * (true + rng.normal(0, noise, true.shape)))).astype(np.float32)
    r = np.ones((119, 120), np.float32)
    c = np.ones((120, 119), np.float32)
    u, _ = irls_unwrap(wrapped, r, c, dct_init(wrapped), 30, 0.01, 0.001)
    uw = enforce_congruence(wrapped, u, align=True)
    k = np.round((uw - true) / (2 * np.pi))
    return wrapped, uw, np.unique(k, return_counts=True)[1].max() / k.size


def test_one_cycle_everywhere_whatever_the_mean_phase():
    for i, m in enumerate((0.0, 2.0, np.pi - 0.05, np.pi, -np.pi + 0.05)):
        wrapped, uw, dominant = _unwrap(m, 0.6, seed=5 + i)
        assert dominant > 0.99, f"mean phase {m:.2f}: only {dominant:.1%} of the cells on the same cycle"
        assert np.allclose(np.angle(np.exp(1j * (uw - wrapped))), 0, atol=1e-4)       # still congruent
