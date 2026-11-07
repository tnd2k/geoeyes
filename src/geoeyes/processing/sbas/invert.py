"""SBAS inversion (S4): mean phase velocity between consecutive dates from the unwrapped pairs (Berardino et al.
2002), minimum norm by SVD across disconnected subsets; temporal coherence (Pepe & Lanari 2006); linear velocity.

``phase`` (pairs, pixels) is the unwrapped phase of each pair, NaN where a pair has no value. Pixels that share the
same set of valid pairs share one pseudo-inverse (most pixels have every pair), so the cost is a few SVDs, not one
per pixel. Optional pair weights (e.g. the mean coherence² of each pair) enter as a weighted least squares.
"""
from __future__ import annotations

import numpy as np


def _pinv(b: np.ndarray, w: np.ndarray | None, rcond: float = 1e-10) -> np.ndarray:
    if w is None:
        return np.linalg.pinv(b, rcond=rcond)
    sw = np.sqrt(w)[:, None]
    return np.linalg.pinv(b * sw, rcond=rcond) * sw.T


def invert(phase: np.ndarray, design: np.ndarray, weights: np.ndarray | None = None,
           min_pairs: int | None = None, rank_out: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Interval velocities (intervals, pixels; phase per day) and the modelled pair phase (pairs, pixels).

    A pixel needs ``min_pairs`` valid pairs (default: the number of intervals); fewer gives NaN. ``rank_out``
    (pixels, int): filled with the rank deficit of each pixel's own network (intervals − rank): above 0, its valid
    pairs leave some intervals tied to nothing and the minimum-norm solution pulls their velocity toward 0."""
    m, k = design.shape
    phase = np.asarray(phase, np.float64)
    valid = np.isfinite(phase)
    need = k if min_pairs is None else min_pairs
    vel = np.full((k, phase.shape[1]), np.nan)
    model = np.full(phase.shape, np.nan)
    if rank_out is not None:
        rank_out[:] = -1
    packed = np.packbits(valid, axis=0)                    # one key per pixel: its pattern of valid pairs
    keys, inv = np.unique(packed, axis=1, return_inverse=True)
    inv = inv.ravel()
    for g in range(keys.shape[1]):
        cols = np.flatnonzero(inv == g)
        rows = np.flatnonzero(valid[:, cols[0]])
        if len(rows) < need:
            continue
        b = design[rows]
        if rank_out is not None:
            rank_out[cols] = k - np.linalg.matrix_rank(b)
        p = _pinv(b, None if weights is None else weights[rows])
        v = p @ phase[np.ix_(rows, cols)]
        vel[:, cols] = v
        model[np.ix_(np.arange(m), cols)] = design @ v
    return vel, model


def remove_stratified(phase: np.ndarray, height: np.ndarray, use: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per pair, the least-squares fit φ = a + b·h over the pixels ``use`` (coherent, finite) removed from every
    pixel: the delay of a stratified troposphere grows with height and, in mountains, looks like motion correlated
    with the relief. Returns the corrected phase and ``b`` (rad / m) per pair."""
    h = np.asarray(height, np.float64)
    out = phase.copy()
    coef = np.full(phase.shape[0], np.nan)
    for k in range(phase.shape[0]):
        ok = use & np.isfinite(phase[k]) & np.isfinite(h)
        if ok.sum() < 100:
            continue
        a = np.column_stack([np.ones(ok.sum()), h[ok]])
        sol = np.linalg.lstsq(a, phase[k, ok].astype(np.float64), rcond=None)[0]
        coef[k] = sol[1]
        out[k] = phase[k] - sol[1] * (h - np.nanmedian(h[ok]))
    return out, coef


def displacement(vel: np.ndarray, days: np.ndarray) -> np.ndarray:
    """Cumulative phase at every date (dates, pixels), zero at the first date."""
    dt = np.diff(days)[:, None]
    return np.vstack([np.zeros((1, vel.shape[1])), np.cumsum(vel * dt, axis=0)])


def temporal_coherence(phase: np.ndarray, model: np.ndarray) -> np.ndarray:
    """|mean over the valid pairs of exp(j(φ − φ_model))|: 1 when the series explains every pair."""
    r = np.exp(1j * (phase - model))
    ok = np.isfinite(r)
    s = np.where(ok, r, 0).sum(0)
    n = ok.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, np.abs(s) / n, np.nan)


def linear_velocity(series: np.ndarray, days: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Least-squares slope (per day) and intercept of each column of ``series`` (dates, pixels)."""
    t = days - days.mean()
    a = np.column_stack([t, np.ones_like(t)])
    coef = np.linalg.lstsq(a, series, rcond=None)[0]
    return coef[0], coef[1] - coef[0] * days.mean()
