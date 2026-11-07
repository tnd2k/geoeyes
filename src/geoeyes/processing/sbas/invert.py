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


GROUP_MIN = 32            # a pattern of valid pairs shared by fewer pixels is solved in the batched path
BATCH = 256               # pixels per batch of the batched path (memory: BATCH × pairs × intervals floats)


def invert(phase: np.ndarray, design: np.ndarray, weights: np.ndarray | None = None,
           min_pairs: int | None = None, rank_out: np.ndarray | None = None,
           group_min: int = GROUP_MIN) -> tuple[np.ndarray, np.ndarray]:
    """Interval velocities (intervals, pixels; phase per day) and the modelled pair phase (pairs, pixels).

    A pixel needs ``min_pairs`` valid pairs (default: the number of intervals); fewer gives NaN. ``rank_out``
    (pixels, int): filled with the rank deficit of each pixel's own network (intervals − rank): above 0, its valid
    pairs leave some intervals tied to nothing and the minimum-norm solution pulls their velocity toward 0.

    Pixels that share a pattern of valid pairs share one pseudo-inverse. Masking (coherence, closure) makes many
    patterns of a few pixels each, and one SVD per pattern took most of the run (hcm_d18, 98 dates: 9 of 13 min at
    2 × 8 looks, 40 of 57 min at 1 × 4). Patterns of fewer than ``group_min`` pixels are solved together, per pixel,
    by the normal equations with a tiny ridge (the minimum-norm solution where the network is rank deficient)."""
    m, k = design.shape
    phase = np.asarray(phase, np.float64)
    valid = np.isfinite(phase)
    need = k if min_pairs is None else min_pairs
    vel = np.full((k, phase.shape[1]), np.nan)
    model = np.full(phase.shape, np.nan)
    if rank_out is not None:
        rank_out[:] = -1
    packed = np.packbits(valid, axis=0)                    # one key per pixel: its pattern of valid pairs
    _, inv, counts = np.unique(packed, axis=1, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    enough = valid.sum(0) >= need
    for g in np.flatnonzero(counts >= group_min):
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
    rare = np.flatnonzero((counts[inv] < group_min) & enough)
    w_pair = np.ones(m) if weights is None else np.asarray(weights, np.float64)
    for s in range(0, rare.size, BATCH):
        cols = rare[s:s + BATCH]
        w = valid[:, cols].T * w_pair[None, :]                        # (p, m): 0 where a pair has no value
        btw = design.T[None, :, :] * w[:, None, :]                    # (p, k, m)
        n = btw @ design                                              # (p, k, k) normal matrices (batched BLAS)
        rhs = (btw @ np.nan_to_num(phase[:, cols].T)[:, :, None])[..., 0]
        scale = np.maximum(np.trace(n, axis1=1, axis2=2) / k, 1e-30)
        if rank_out is not None:
            eig = np.linalg.eigvalsh(n)
            rank_out[cols] = k - (eig > 1e-9 * eig[:, -1:]).sum(1)
        ridge = 1e-10 * scale
        v = np.linalg.solve(n + ridge[:, None, None] * np.eye(k)[None], rhs[..., None])[..., 0]   # (p, k)
        vel[:, cols] = v.T
        model[:, cols] = design @ v.T
    return vel, model


def remove_stratified(phase: np.ndarray, height: np.ndarray, use: np.ndarray,
                      adjust=None) -> tuple[np.ndarray, np.ndarray]:
    """Per pair, the least-squares fit φ = a + b·h over the pixels ``use`` (coherent, finite) removed from every
    pixel: the delay of a stratified troposphere grows with height and, in mountains, looks like motion correlated
    with the relief. ``adjust(b) -> b'``: the coefficients actually removed (``stratified_without_trend``).
    Returns the corrected phase and the removed ``b`` (rad / m) per pair."""
    h = np.asarray(height, np.float64)
    out = phase.copy()
    coef = np.full(phase.shape[0], np.nan)
    h0 = np.full(phase.shape[0], np.nan)
    for k in range(phase.shape[0]):
        ok = use & np.isfinite(phase[k]) & np.isfinite(h)
        if ok.sum() < 100:
            continue
        a = np.column_stack([np.ones(ok.sum()), h[ok]])
        coef[k] = np.linalg.lstsq(a, phase[k, ok].astype(np.float64), rcond=None)[0][1]
        h0[k] = np.nanmedian(h[ok])
    if adjust is not None:
        coef = adjust(coef)
    for k in np.flatnonzero(np.isfinite(coef)):
        out[k] = phase[k] - coef[k] * (h - h0[k])
    return out, coef


def stratified_without_trend(coef: np.ndarray, pairs: list[tuple[int, int]], days: np.ndarray) -> np.ndarray:
    """The per-pair height coefficients ``coef`` (rad / m) less their steady trend over the dates.

    The correction b_k·(h − h0) is linear in height for every pixel, so its time series is β(t)·(h − h0) with β the
    inversion of b over the pairs: the trend of β becomes a velocity proportional to height. A stratified
    troposphere has no multi-year trend; a fit that has one took deformation correlated with height (the low,
    young fills of a delta subside more). Remove b_k − s·(t_j − t_i), s the slope of β."""
    b = np.where(np.isfinite(coef), coef, 0.0)
    n = len(days)
    a = np.zeros((len(pairs), n - 1))
    for k, (i, j) in enumerate(pairs):
        a[k, i:j] = np.diff(days)[i:j]
    beta_rate = np.linalg.lstsq(a, b, rcond=None)[0]                 # per interval, rad / m / day
    beta = np.concatenate([[0.0], np.cumsum(beta_rate * np.diff(days))])
    s = np.polyfit(days - days[0], beta, 1)[0]
    span = np.array([days[j] - days[i] for i, j in pairs], np.float64)
    return np.where(np.isfinite(coef), coef - s * span, coef)


def remove_dem_error(series: np.ndarray, days: np.ndarray, bperp: np.ndarray,
                     min_spread_m: float = 20.0) -> tuple[np.ndarray, np.ndarray]:
    """Per pixel, the least-squares fit series = c + v·t + K·B⊥ (``series``: dates × pixels, phase; ``bperp`` per
    date) and the series with K·B⊥ removed; returns (corrected series, K in rad per metre of B⊥). Not estimated
    (K = 0) when the baselines span less than ``min_spread_m`` (K would be noise)."""
    b = np.asarray(bperp, np.float64)
    k = np.zeros(series.shape[1])
    if np.ptp(b) < min_spread_m or series.shape[0] < 4:
        return series, k
    t = (days - days.mean()) / 365.25
    a = np.column_stack([np.ones_like(t), t, b - b.mean()])
    ok = np.isfinite(series).all(0)
    if ok.any():
        k[ok] = np.linalg.lstsq(a, series[:, ok], rcond=None)[0][2]
    return series - np.outer(b - b.mean(), k), k


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
