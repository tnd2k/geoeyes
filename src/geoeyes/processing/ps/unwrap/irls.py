"""Weighted L1-type 2-D phase unwrapping by IRLS (legacy ``RefinedIRLSSolver``, ``dct`` initialisation),
NumPy/SciPy port of the torch implementation.

Minimises Σ w·|∇u - wrap(∇φ)| on the grid: each IRLS step solves a weighted Poisson equation by
conjugate gradients preconditioned with the unweighted (DCT) Poisson solver; the starting surface is the
DCT least-squares integration of the wrapped gradients. Edge weights come from the edge variances
(``row_costs``/``col_costs``) as 1/(1 + var/median var).
"""
from __future__ import annotations

import numpy as np
from scipy.fft import dctn, idctn, next_fast_len


def _poisson_eigs(h: int, w: int) -> np.ndarray:
    i = np.arange(h, dtype=np.float32)[:, None]
    j = np.arange(w, dtype=np.float32)[None, :]
    ev = (2 * np.cos(np.float32(np.pi) * i / h) - 2) + (2 * np.cos(np.float32(np.pi) * j / w) - 2)
    ev[0, 0] = 1.0
    return ev.astype(np.float32)


def _dct_solve(rho: np.ndarray, ev: np.ndarray) -> np.ndarray:
    """Neumann Poisson solve on a zero-padded (FFT-friendly) grid, cropped back."""
    h, w = rho.shape
    pad = np.zeros(ev.shape, np.float32)
    pad[:h, :w] = rho
    spec = (dctn(pad.astype(np.float64), type=2, norm=None).astype(np.float32) / ev)
    return idctn(spec.astype(np.float64), type=2, norm=None).astype(np.float32)[:h, :w]


def _div(dx: np.ndarray, dy: np.ndarray, shape) -> np.ndarray:
    out = np.zeros(shape, np.float32)
    out[:, :-1] += dx
    out[:, 1:] -= dx
    out[:-1, :] += dy
    out[1:, :] -= dy
    return out


def dct_init(phase: np.ndarray) -> np.ndarray:
    """Least-squares integration of the wrapped gradients (no integer jumps); NaN cells are no-data."""
    h, w = phase.shape
    valid = np.isfinite(phase)
    p = np.where(valid, phase, 0.0)
    dx = (((p[:, 1:] - p[:, :-1] + np.pi) % (2 * np.pi)) - np.pi) * (valid[:, :-1] & valid[:, 1:])
    dy = (((p[1:, :] - p[:-1, :] + np.pi) % (2 * np.pi)) - np.pi) * (valid[:-1, :] & valid[1:, :])
    rho = _div(dx.astype(np.float32), dy.astype(np.float32), (h, w))
    return _dct_solve(rho, _poisson_eigs(next_fast_len(h), next_fast_len(w)))


def _lower_median(a: np.ndarray) -> np.float32:
    """torch.median semantics: the lower of the two middle values."""
    return np.partition(a, (a.size - 1) // 2)[(a.size - 1) // 2] if a.size else np.float32(1.0)


def irls_unwrap(phase: np.ndarray, row_costs: np.ndarray, col_costs: np.ndarray, init: np.ndarray | None = None,
                max_iter: int = 50, target_rms: float = 0.01, epsilon: float = 0.001) -> tuple[np.ndarray, float]:
    """``phase`` (h, w) wrapped (NaN = no data); ``row_costs`` (h-1, w) / ``col_costs`` (h, w-1) edge variances.
    Returns the continuous surface (float32) and the last PCG residual RMS."""
    wx0 = col_costs.astype(np.float32)
    wy0 = row_costs.astype(np.float32)
    sx, sy = _lower_median(wx0[wx0 > 0]), _lower_median(wy0[wy0 > 0])
    wx0 = (1.0 / (1.0 + wx0 / sx)).astype(np.float32)
    wy0 = (1.0 / (1.0 + wy0 / sy)).astype(np.float32)
    return _irls(phase, wx0, wy0, init, max_iter, target_rms, epsilon)


def irls_unwrap_weighted(phase: np.ndarray, weight: np.ndarray, init: np.ndarray | None = None, max_iter: int = 50,
                         target_rms: float = 0.01, epsilon: float = 0.001) -> tuple[np.ndarray, float]:
    """As ``irls_unwrap`` with a per-cell ``weight`` (h, w) used directly as edge weight (cell at the edge start)."""
    wgt = np.asarray(weight, np.float32)
    return _irls(phase, wgt[:, :-1], wgt[:-1, :], init, max_iter, target_rms, epsilon)


def _irls(phase, wx0, wy0, init, max_iter, target_rms, epsilon) -> tuple[np.ndarray, float]:
    h, w = phase.shape
    phi = phase.astype(np.float32)
    nan = ~np.isfinite(phi)
    vx = ~(nan[:, :-1] | nan[:, 1:])
    vy = ~(nan[:-1, :] | nan[1:, :])
    p = np.where(nan, np.float32(0), phi)
    gx, gy = p[:, 1:] - p[:, :-1], p[1:, :] - p[:-1, :]
    dx_t = np.arctan2(np.sin(gx), np.cos(gx)) * vx
    dy_t = np.arctan2(np.sin(gy), np.cos(gy)) * vy
    wx0, wy0 = wx0 * vx, wy0 * vy
    ev = _poisson_eigs(next_fast_len(h), next_fast_len(w))

    def lap(u, wx, wy):
        return _div(wx * (u[:, 1:] - u[:, :-1]), wy * (u[1:, :] - u[:-1, :]), (h, w))

    u = np.zeros((h, w), np.float32) if init is None else np.nan_to_num(init.astype(np.float32).reshape(h, w))
    n_pix = h * w
    max_pcg = 200 if n_pix > 1_000_000 else 300 if n_pix > 100_000 else 500
    rms = float("inf")
    for it in range(max_iter):
        if it == 0:
            wx, wy = wx0, wy0
        else:
            wx = wx0 / np.sqrt(((u[:, 1:] - u[:, :-1]) - dx_t) ** 2 + epsilon**2)
            wy = wy0 / np.sqrt(((u[1:, :] - u[:-1, :]) - dy_t) ** 2 + epsilon**2)
        r = _div(wx * dx_t, wy * dy_t, (h, w)) - lap(u, wx, wy)
        z = _dct_solve(r, ev)
        d = z.copy()
        rz = np.sum(r * z, dtype=np.float32)
        for _ in range(max_pcg):
            ad = lap(d, wx, wy)
            dad = np.sum(d * ad, dtype=np.float32)
            if abs(dad) < 1e-12:
                break
            a = rz / dad
            u = u + a * d
            r = r - a * ad
            rms = float(np.sqrt(np.mean(r**2, dtype=np.float32)))
            if rms < target_rms:
                break
            z = _dct_solve(r, ev)
            rz_new = np.sum(r * z, dtype=np.float32)
            d = z + (rz_new / rz) * d
            rz = rz_new
        if rms < target_rms:
            break
    if init is None:
        u = u - np.median(u)
    return u, rms


def enforce_congruence(phase: np.ndarray, unwrapped: np.ndarray) -> np.ndarray:
    """Snap to ``phase + 2πk`` (k integer) wherever the wrapped phase is defined."""
    wp = np.asarray(phase, np.float64)
    u = np.asarray(unwrapped).astype(np.float64).reshape(wp.shape)
    ok = np.isfinite(wp) & np.isfinite(u)
    out = u.copy()
    out[ok] = wp[ok] + 2 * np.pi * np.round((u[ok] - wp[ok]) / (2 * np.pi))
    return out.astype(np.float32)
