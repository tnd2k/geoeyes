"""Per-pixel fit of the look-angle (DEM) error K: phase ≈ K·bperp + C (StaMPS ``ps_topofit``), batched.

Two-stage ambiguity search: a coarse pass with one trial per ambiguity cycle (``COARSE_STEP`` trial units
of π/4/bperp_range) gives the best (C1) and the best competing (C2) peak, Q = (C1 - C2)/C1 scores how
unambiguous the lock is; a fine pass within ±1 cycle of the winner, then a weighted linear refinement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

COARSE_STEP = 8


@dataclass
class TopoFit:
    K: np.ndarray             # (n,) rad/m
    C: np.ndarray             # (n,) constant phase
    coh: np.ndarray           # (n,) temporal coherence of the residual
    residual: np.ndarray      # (n, n_ifg) complex residual phasors
    Q: np.ndarray             # (n,) ambiguity confidence in [0, 1]


def topofit_full(cpx: np.ndarray, bperp: np.ndarray, n_trial_wraps: float, mini_batch: int = 200) -> TopoFit:
    """StaMPS ``ps_topofit``: every trial multiple in ±8·n_trial_wraps, then the linear refinement (no Q,
    returned as ones)."""
    n, _ = cpx.shape
    mult = np.arange(-int(np.ceil(8 * n_trial_wraps)), int(np.ceil(8 * n_trial_wraps)) + 1)
    brange_all = np.max(bperp, axis=1) - np.min(bperp, axis=1)
    brange_all = np.where(brange_all == 0, 1.0, brange_all)
    out = TopoFit(np.zeros(n), np.zeros(n), np.zeros(n), np.zeros_like(cpx), np.ones(n))
    for s in range(0, n, mini_batch):
        e = min(s + mini_batch, n)
        z, bp, brange = cpx[s:e], bperp[s:e], brange_all[s:e]
        trial_phase = bp / brange[:, None] * np.pi / 4
        sums = np.einsum("bi,bit->bt", z, np.exp(-1j * trial_phase[:, :, None] * mult[None, None, :]))
        abs_sum = np.sum(np.abs(z), axis=1, keepdims=True)
        coh_t = np.abs(sums) / np.where(abs_sum > 0, abs_sum, 1.0)
        k0 = np.pi / 4 / brange * mult[np.argmax(coh_t, axis=1)]
        res = z * np.exp(-1j * k0[:, None] * bp)
        res_ang = np.angle(res * np.conj(np.sum(res, axis=1))[:, None])
        w = np.abs(z)
        a = w * bp
        denom = np.sum(a * a, axis=1)
        k0 = k0 + np.where(denom > 0, np.sum(a * (w * res_ang), axis=1) / denom, 0.0)
        res = z * np.exp(-1j * k0[:, None] * bp)
        mean_res = np.sum(res, axis=1)
        abs_res = np.sum(np.abs(res), axis=1)
        out.K[s:e] = k0
        out.C[s:e] = np.angle(mean_res)
        out.coh[s:e] = np.abs(mean_res) / np.where(abs_res > 0, abs_res, 1.0)
        out.residual[s:e] = res
    return out


def topofit(cpx: np.ndarray, bperp: np.ndarray, n_trial_wraps: float, mini_batch: int = 200) -> TopoFit:
    """``cpx`` (n, n_ifg) complex phasors (zeros are ignored by their zero weight), ``bperp`` (n, n_ifg)."""
    n, _ = cpx.shape
    n_half = max(1, int(np.ceil(n_trial_wraps)))
    mult_coarse = np.arange(-n_half, n_half + 1) * COARSE_STEP
    fine_offsets = np.arange(-COARSE_STEP, COARSE_STEP + 1)
    n_coarse = mult_coarse.size
    brange_all = np.max(bperp, axis=1) - np.min(bperp, axis=1)
    brange_all = np.where(brange_all == 0, 1.0, brange_all)

    out = TopoFit(np.zeros(n), np.zeros(n), np.zeros(n), np.zeros_like(cpx), np.zeros(n))
    for s in range(0, n, mini_batch):
        e = min(s + mini_batch, n)
        z, bp, brange = cpx[s:e], bperp[s:e], brange_all[s:e]
        rows = np.arange(e - s)
        trial_phase = bp / brange[:, None] * np.pi / 4
        abs_sum = np.sum(np.abs(z), axis=1, keepdims=True)
        abs_sum = np.where(abs_sum > 0, abs_sum, 1.0)

        coh_c = np.abs(np.einsum("bi,bit->bt", z, np.exp(-1j * trial_phase[:, :, None] * mult_coarse))) / abs_sum
        best_c = np.argmax(coh_c, axis=1)
        c1 = coh_c[rows, best_c]
        near = np.abs(np.arange(n_coarse)[None, :] - best_c[:, None]) <= 1
        c2 = np.maximum(np.max(np.where(near, -1.0, coh_c), axis=1), 0.0)
        out.Q[s:e] = np.where(c1 > 1e-6, (c1 - c2) / c1, 0.0)

        mult_fine = mult_coarse[best_c][:, None] + fine_offsets[None, :]
        coh_f = np.abs(np.einsum("bi,bit->bt", z, np.exp(-1j * (trial_phase[:, :, None] * mult_fine[:, None, :]))))
        k0 = np.pi / 4 / brange * mult_fine[rows, np.argmax(coh_f / abs_sum, axis=1)]

        res = z * np.exp(-1j * k0[:, None] * bp)
        res_ang = np.angle(res * np.conj(np.sum(res, axis=1))[:, None])
        w = np.abs(z)
        a = w * bp
        denom = np.sum(a * a, axis=1)
        k0 = k0 + np.where(denom > 0, np.sum(a * (w * res_ang), axis=1) / denom, 0.0)

        res = z * np.exp(-1j * k0[:, None] * bp)
        mean_res = np.sum(res, axis=1)
        abs_res = np.sum(np.abs(res), axis=1)
        out.K[s:e] = k0
        out.C[s:e] = np.angle(mean_res)
        out.coh[s:e] = np.abs(mean_res) / np.where(abs_res > 0, abs_res, 1.0)
        out.residual[s:e] = res
    return out
