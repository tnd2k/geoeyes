"""Per-pixel fit of the look-angle (DEM) error K: phase ≈ K·bperp + C (StaMPS ``ps_topofit``), batched.

Two-stage ambiguity search: a coarse pass with one trial per ambiguity cycle (``COARSE_STEP`` trial units
of π/4/bperp_range) gives the best (C1) and the best competing (C2) peak, Q = (C1 - C2)/C1 scores how
unambiguous the lock is; a fine pass within ±1 cycle of the winner, then a weighted linear refinement.

Runs on the backend of the current run (``geoeyes.core.compute``): NumPy, or CuPy with larger batches.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from geoeyes.core import compute

COARSE_STEP = 8


@dataclass
class TopoFit:
    K: np.ndarray             # (n,) rad/m
    C: np.ndarray             # (n,) constant phase
    coh: np.ndarray           # (n,) temporal coherence of the residual
    residual: np.ndarray      # (n, n_ifg) complex residual phasors
    Q: np.ndarray             # (n,) ambiguity confidence in [0, 1]


def _refine(xp, z, bp, k0):
    """The weighted linear refinement of k0 and the final residual: (K, C, coh, residual)."""
    res = z * xp.exp(-1j * k0[:, None] * bp)
    res_ang = xp.angle(res * xp.conj(xp.sum(res, axis=1))[:, None])
    w = xp.abs(z)
    a = w * bp
    denom = xp.sum(a * a, axis=1)
    k0 = k0 + xp.where(denom > 0, xp.sum(a * (w * res_ang), axis=1) / denom, 0.0)
    res = z * xp.exp(-1j * k0[:, None] * bp)
    mean_res = xp.sum(res, axis=1)
    abs_res = xp.sum(xp.abs(res), axis=1)
    return k0, xp.angle(mean_res), xp.abs(mean_res) / xp.where(abs_res > 0, abs_res, 1.0), res


def _store(be, out: TopoFit, s: int, e: int, k0, c, coh, res) -> None:
    out.K[s:e] = be.asnumpy(k0)
    out.C[s:e] = be.asnumpy(c)
    out.coh[s:e] = be.asnumpy(coh)
    out.residual[s:e] = be.asnumpy(res)


def topofit_full(cpx: np.ndarray, bperp: np.ndarray, n_trial_wraps: float, mini_batch: int = 200) -> TopoFit:
    """StaMPS ``ps_topofit``: every trial multiple in ±8·n_trial_wraps, then the linear refinement (no Q,
    returned as ones)."""
    be = compute.current()
    xp = be.xp
    n, _ = cpx.shape
    mini_batch = be.batch(mini_batch)
    mult = xp.arange(-int(np.ceil(8 * n_trial_wraps)), int(np.ceil(8 * n_trial_wraps)) + 1)
    brange_all = np.max(bperp, axis=1) - np.min(bperp, axis=1)
    brange_all = np.where(brange_all == 0, 1.0, brange_all)
    out = TopoFit(np.zeros(n), np.zeros(n), np.zeros(n), np.zeros_like(cpx), np.ones(n))
    for s in range(0, n, mini_batch):
        e = min(s + mini_batch, n)
        z, bp, brange = be.asarray(cpx[s:e]), be.asarray(bperp[s:e]), be.asarray(brange_all[s:e])
        trial_phase = bp / brange[:, None] * np.pi / 4
        sums = xp.einsum("bi,bit->bt", z, xp.exp(-1j * trial_phase[:, :, None] * mult[None, None, :]))
        abs_sum = xp.sum(xp.abs(z), axis=1, keepdims=True)
        coh_t = xp.abs(sums) / xp.where(abs_sum > 0, abs_sum, 1.0)
        k0 = np.pi / 4 / brange * mult[xp.argmax(coh_t, axis=1)]
        _store(be, out, s, e, *_refine(xp, z, bp, k0))
    return out


def topofit(cpx: np.ndarray, bperp: np.ndarray, n_trial_wraps: float, mini_batch: int = 200) -> TopoFit:
    """``cpx`` (n, n_ifg) complex phasors (zeros are ignored by their zero weight), ``bperp`` (n, n_ifg)."""
    be = compute.current()
    xp = be.xp
    n, _ = cpx.shape
    mini_batch = be.batch(mini_batch)
    n_half = max(1, int(np.ceil(n_trial_wraps)))
    mult_coarse = xp.arange(-n_half, n_half + 1) * COARSE_STEP
    fine_offsets = xp.arange(-COARSE_STEP, COARSE_STEP + 1)
    n_coarse = int(mult_coarse.size)
    brange_all = np.max(bperp, axis=1) - np.min(bperp, axis=1)
    brange_all = np.where(brange_all == 0, 1.0, brange_all)

    out = TopoFit(np.zeros(n), np.zeros(n), np.zeros(n), np.zeros_like(cpx), np.zeros(n))
    for s in range(0, n, mini_batch):
        e = min(s + mini_batch, n)
        z, bp, brange = be.asarray(cpx[s:e]), be.asarray(bperp[s:e]), be.asarray(brange_all[s:e])
        rows = xp.arange(e - s)
        trial_phase = bp / brange[:, None] * np.pi / 4
        abs_sum = xp.sum(xp.abs(z), axis=1, keepdims=True)
        abs_sum = xp.where(abs_sum > 0, abs_sum, 1.0)

        coh_c = xp.abs(xp.einsum("bi,bit->bt", z, xp.exp(-1j * trial_phase[:, :, None] * mult_coarse))) / abs_sum
        best_c = xp.argmax(coh_c, axis=1)
        c1 = coh_c[rows, best_c]
        near = xp.abs(xp.arange(n_coarse)[None, :] - best_c[:, None]) <= 1
        c2 = xp.maximum(xp.max(xp.where(near, -1.0, coh_c), axis=1), 0.0)
        out.Q[s:e] = be.asnumpy(xp.where(c1 > 1e-6, (c1 - c2) / c1, 0.0))

        mult_fine = mult_coarse[best_c][:, None] + fine_offsets[None, :]
        coh_f = xp.abs(xp.einsum("bi,bit->bt", z, xp.exp(-1j * (trial_phase[:, :, None] * mult_fine[:, None, :]))))
        k0 = np.pi / 4 / brange * mult_fine[rows, xp.argmax(coh_f / abs_sum, axis=1)]
        _store(be, out, s, e, *_refine(xp, z, bp, k0))
    return out
