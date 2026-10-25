"""Coherence matrices over SHP windows and phase-linking estimators (batched over pixels).

Every estimator returns unit phasors ``v`` (B, n) referenced to the stack reference epoch (``v[:, ref] = 1``),
with ``v_i·conj(v_j)`` estimating the phase of the coherence ``C_ij = E[s_i·conj(s_j)]``.
"""
from __future__ import annotations

import numpy as np


def coherence(S: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Sample covariance over the SHP of each window, normalised by its own diagonal.

    ``S`` (B, n, win) complex window samples, ``mask`` (B, win) bool. Returns (B, n, n) complex64.
    """
    w = (mask & np.any(S != 0, axis=1)).astype(np.float32)
    Sm = S * w[:, None, :]
    C = np.matmul(Sm, np.conj(Sm).swapaxes(-1, -2)) / np.maximum(w.sum(-1), 1.0)[:, None, None]
    d = np.sqrt(np.maximum(np.real(np.diagonal(C, axis1=-2, axis2=-1)), 0.0))
    d = np.where(d == 0, 1.0, d)
    return np.nan_to_num(C / (d[:, :, None] * d[:, None, :])).astype(np.complex64)


def _unit_ref(v: np.ndarray, ref: int) -> np.ndarray:
    a = np.abs(v)
    v = v / np.where(a == 0, 1.0, a)
    r = v[:, ref:ref + 1]
    return v * np.conj(r / np.where(np.abs(r) == 0, 1.0, np.abs(r)))


def evd(C: np.ndarray, ref: int) -> np.ndarray:
    """Leading eigenvector of the coherence matrix."""
    return _unit_ref(np.linalg.eigh(C)[1][:, :, -1], ref)


def emi(C: np.ndarray, ref: int, beta: float = 0.5) -> np.ndarray:
    """EMI (Ansari et al. 2018): minimum-eigenvalue eigenvector of ``W⁻¹ ∘ |W|``, ``W = (1-β)C + βI``.

    An epoch without data at the pixel (zero diagonal) would give the trivial eigenvalue 1 and win the
    minimum, so its diagonal is inflated.
    """
    n = C.shape[-1]
    W = (1.0 - beta) * C + beta * np.eye(n, dtype=C.dtype)
    R = np.linalg.inv(W) * np.abs(W)
    R = np.where(np.isfinite(R), R, 1e-14)
    no_data = np.real(np.diagonal(C, axis1=-2, axis2=-1)) < 1e-6
    if no_data.any():
        k = np.arange(n)
        R[:, k, k] = np.where(no_data, 1e6, R[:, k, k])
    return _unit_ref(np.linalg.eigh(R)[1][:, :, 0], ref)


def pta(C: np.ndarray, ref: int, max_iter: int = 30, tol: float = 1e-7) -> np.ndarray:
    """Phase triangulation (uniform-weight MLE): fixed point of ``θ_i = arg Σ_j C_ij e^{jθ_j}``, from EVD."""
    v = evd(C, ref)
    for _ in range(max_iter):
        z = np.matmul(C, v[..., None])[..., 0]
        v_new = _unit_ref(np.where(np.abs(z) > 1e-12, z, 1.0), ref)
        done = float(np.max(np.abs(np.angle(v_new * np.conj(v))))) < tol
        v = v_new
        if done:
            break
    return v


def adaptive(C: np.ndarray, ref: int, threshold: float = 0.6) -> np.ndarray:
    """EMI where the mean off-diagonal coherence exceeds ``threshold``, PTA elsewhere."""
    n = C.shape[-1]
    mean_coh = (np.abs(C).sum(axis=(-2, -1)) - np.abs(np.diagonal(C, axis1=-2, axis2=-1)).sum(-1)) / (n * n - n)
    hi = mean_coh > threshold
    v = np.empty(C.shape[:2], np.complex128)
    if hi.any():
        v[hi] = emi(C[hi], ref)
    if (~hi).any():
        v[~hi] = pta(C[~hi], ref)
    return v


def link(C: np.ndarray, estimator: str, ref: int, adaptive_threshold: float = 0.6) -> np.ndarray:
    e = estimator.lower()
    if e == "evd":
        return evd(C, ref)
    if e == "emi":
        return emi(C, ref)
    if e in ("pta", "mle"):
        return pta(C, ref)
    if e == "adaptive":
        return adaptive(C, ref, adaptive_threshold)
    raise ValueError(f"phase-linking estimator {estimator!r} not implemented")


def temporal_coherence(C: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Fit of the linked phases to the coherence phases: Re Σ_{i<j} e^{j(arg C_ij - θ_i + θ_j)} / (n(n-1)/2)."""
    n = C.shape[-1]
    a = np.abs(C)
    u = np.where(a > 0, C / np.where(a > 0, a, 1.0), 0)
    r = u * np.conj(v[:, :, None]) * v[:, None, :]
    iu = np.triu_indices(n, 1)
    return np.real(r[:, iu[0], iu[1]]).mean(-1)
