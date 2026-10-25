"""Step 5 — remove the look-angle error and the constant phase from the PS phase (legacy
``_ps_correct_phase``), and the per-epoch noise standard deviation (legacy ``_ps_calc_ifg_std``).
Single-master; ``ph`` (n, n_ifg) includes the master column, ``bperp_mat``/``ph_patch`` (n, n_sec) do not.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CorrectedPhase:
    ph_rc: np.ndarray        # (n, n_ifg) complex128, ph·exp(-i(K·bperp + C))
    ph_reref: np.ndarray     # (n, n_ifg) complex64, patch phase with 1 at the master
    ifg_std: np.ndarray      # (n_ifg,) degrees


def _with_master(a: np.ndarray, master_ix: int, fill) -> np.ndarray:
    return np.hstack([a[:, :master_ix], np.full((a.shape[0], 1), fill, a.dtype), a[:, master_ix:]])


def correct_phase(*, ph: np.ndarray, bperp_mat: np.ndarray, K: np.ndarray, C: np.ndarray, ph_patch: np.ndarray,
                  master_ix: int) -> CorrectedPhase:
    bp = _with_master(np.asarray(bperp_mat, np.float32), master_ix, 0) if bperp_mat.shape[1] == ph.shape[1] - 1 \
        else bperp_mat
    patch = np.asarray(ph_patch).astype(np.complex64)
    if patch.shape[1] == ph.shape[1] - 1:
        patch = _with_master(patch, master_ix, 1)
    k, c = np.reshape(K, (-1, 1)), np.reshape(C, (-1, 1))
    ph_rc = ph * np.exp(-1j * (k * bp + c))
    ph_diff = np.angle(ph * np.conj(patch.astype(np.complex128)) * np.exp(-1j * (k * bp + c)))
    ifg_std = np.sqrt(np.sum(ph_diff**2, axis=0) / ph.shape[0]) * 180 / np.pi
    return CorrectedPhase(ph_rc=ph_rc, ph_reref=patch, ifg_std=ifg_std)
