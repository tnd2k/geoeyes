# Ported from modules/utils/flat_earth.py (estimate_linear_tropo, algorithm unchanged; ADR-020).
"""Linear tropospheric delay (phase vs height) fitted on the wrapped phase of a grid, without unwrapping."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LinearTropo:
    k_rad_per_m: float           # phase-height slope K
    ramp_az: float               # rad per grid line
    ramp_rg: float               # rad per grid column
    offset: float                # rad
    h_ref: float                 # height the K*h term is referenced to (weighted median of used cells)
    n_used: int
    block: int                   # block size (cells) the fit ran on
    fit_ramp_only: float         # phase consistency |Σ z e^-j model| / Σ |z| with the plane only
    fit_with_k: float            # same with plane + K*h
    delay_mm_per_km: float       # differential LOS delay gradient (master - slave) per km height


def _block_sum(a: np.ndarray, b: int) -> np.ndarray:
    ny, nx = (a.shape[0] // b) * b, (a.shape[1] // b) * b
    return a[:ny, :nx].reshape(ny // b, b, nx // b, b).sum(axis=(1, 3))


def estimate_linear_tropo(ifg: np.ndarray, height: np.ndarray, weight: np.ndarray, wavelength: float,
                          sign: float = 1.0, k_max_rad_per_km: float = 60.0, fit_ramp: bool = True,
                          block: int = 16, iters: int = 4) -> LinearTropo:
    """Fit arg(ifg) ~ K*h + a*i + b*j + c. The weighted unit phasors are summed over ``block``² cells (with
    their weighted mean height); on the blocks K maximises |Σ z e^{-jKh}| (periodogram over 1 m height bins)
    and the plane is the mean phase gradient between neighbouring blocks, alternated ``iters`` times.
    ``weight`` is 0 where the phase is not to be used. Raises ValueError with fewer than 100 usable cells."""
    w = np.where(np.isfinite(weight) & np.isfinite(height) & np.isfinite(ifg), weight, 0.0)
    if (w > 0).sum() < 100:
        raise ValueError("too few coherent cells to estimate the troposphere")
    zf = np.where(w > 0, np.exp(1j * np.angle(np.nan_to_num(ifg))), 0) * w
    hf = np.where(w > 0, height, 0.0)
    B = max(int(block), 1)
    ny, nx = ifg.shape
    if ny // B < 3 or nx // B < 3:
        B = max(1, min(ny, nx) // 3)
    zb = _block_sum(zf, B)
    wb = _block_sum(w, B)
    hb = np.where(wb > 0, _block_sum(w * hf, B) / np.maximum(wb, 1e-30), np.nan)
    use = (wb > 0) & np.isfinite(hb)
    order = np.argsort(height[w > 0])
    cw = np.cumsum(w[w > 0][order])
    h_ref = float(height[w > 0][order][np.searchsorted(cw, cw[-1] / 2)])
    nyb, nxb = zb.shape
    ib, jb = np.meshgrid(np.arange(nyb) - nyb / 2, np.arange(nxb) - nxb / 2, indexing="ij")
    hrel = np.where(use, hb - h_ref, 0.0)
    hbin = np.round(hrel[use]).astype(int)
    hmin = hbin.min()
    hbin -= hmin
    hv = np.arange(hbin.max() + 1, dtype=float) + hmin
    k_grid = np.linspace(-k_max_rad_per_km, k_max_rad_per_km, 4001) / 1000.0
    z = np.where(use, zb, 0)

    def consistency(ph):
        return float(np.abs(np.sum(z * np.exp(-1j * ph))) / max(np.sum(np.abs(z)), 1e-30))

    K = ab = bb = 0.0
    for _ in range(iters):
        if fit_ramp:
            zr = z * np.exp(-1j * K * hrel)
            ab = float(np.angle(np.sum(zr[1:] * np.conj(zr[:-1]))))
            bb = float(np.angle(np.sum(zr[:, 1:] * np.conj(zr[:, :-1]))))
        zk = (z * np.exp(-1j * (ab * ib + bb * jb)))[use]
        S = np.bincount(hbin, weights=zk.real) + 1j * np.bincount(hbin, weights=zk.imag)
        P = np.abs(np.exp(-1j * np.outer(k_grid, hv)) @ S)
        i = int(np.argmax(P))
        K = float(k_grid[i])
        if 0 < i < len(P) - 1:                    # parabolic refinement
            den = P[i - 1] - 2 * P[i] + P[i + 1]
            if den != 0:
                K += float(0.5 * (P[i - 1] - P[i + 1]) / den * (k_grid[1] - k_grid[0]))
    plane = ab * ib + bb * jb
    fit0 = consistency(plane)
    fitk = consistency(plane + K * hrel)
    a, b = ab / B, bb / B                         # back to cell units: block centres are B cells apart
    ii, jj = np.meshgrid(np.arange(ny) - ny / 2, np.arange(nx) - nx / 2, indexing="ij")
    c = float(np.angle(np.sum(zf * np.exp(-1j * (K * np.where(w > 0, height - h_ref, 0) + a * ii + b * jj)))))
    d_mm_km = -K * wavelength / (4 * np.pi * sign) * 1e6
    return LinearTropo(K, a, b, c, h_ref, int((w > 0).sum()), B, fit0, fitk, float(d_mm_km))
