"""Spatial unwrapping of every interferogram on the grid (legacy ``_uw_stat_costs``, IRLS_REFINED).

Edge variances come from the temporal residuals (robust MAD per edge, shrunk towards the scene median)
plus the local-gradient spread, scaled to SNAPHU-like integer costs; each interferogram's nearest-cell
phase grid is unwrapped by IRLS (``irls``), snapped to the wrapped phase + 2πk, and sampled at the PS cells.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from geoeyes.processing.ps.unwrap.grid import UwGrid
from geoeyes.processing.ps.unwrap.interp import UwInterp
from geoeyes.processing.ps.unwrap.irls import dct_init, enforce_congruence, irls_unwrap
from geoeyes.processing.ps.unwrap.space_time import SpaceTime

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpatialParams:
    costscale: float = 100
    nshortcycle: int = 200
    maxshort: int = 32000
    irls_iter: int = 50
    irls_target_rms: float = 0.01
    irls_epsilon: float = 0.001


@dataclass
class SpatialResult:
    ph_uw: np.ndarray      # (n_ps, n_ifg) float32 unwrapped phase at the PS (0 = empty, NaN = degenerate)
    msd: np.ndarray        # (n_ifg,) mean squared grid difference
    pcg_rms: np.ndarray    # (n_ifg,) last PCG residual RMS (NaN when not unwrapped)


def edge_variance(dph_noise: np.ndarray) -> np.ndarray:
    """Per-edge noise variance (cycles²): (1.4826·MAD/2π)² over the interferograms, ≥ 1e-3, shrunk towards the
    median of the well-sampled edges with weight n/(n + 20)."""
    finite = np.isfinite(dph_noise)
    n_valid = finite.sum(axis=1)
    ok = n_valid >= 3
    sig = np.full(dph_noise.shape[0], np.nan, np.float32)
    global_med = 0.1
    if np.any(ok):
        d = dph_noise[ok]
        with np.errstate(invalid="ignore"):
            med = np.nanmedian(d, axis=1, keepdims=True)
            mad = np.nanmedian(np.abs(d - med), axis=1)
        local = np.maximum((1.4826 * mad / (2 * np.pi)) ** 2, 1e-3)
        sig[ok] = local
        global_med = float(np.nanmedian(local))
    if not np.isfinite(global_med) or global_med <= 0:
        global_med = 0.1
    alpha = np.clip(n_valid.astype(np.float32) / (n_valid + 20.0), 0.0, 1.0)
    sig[np.isnan(sig)] = global_med
    return np.maximum(alpha * sig + (1.0 - alpha) * global_med, 1e-3)


def _msd(g: np.ndarray) -> float:
    d1 = g[:-1, :] - g[1:, :]
    d2 = g[:, :-1] - g[:, 1:]
    d1, d2 = d1[d1 != 0], d2[d2 != 0]
    n = d1.size + d2.size
    return float((np.sum(d1**2) + np.sum(d2**2)) / n) if n else np.nan


def spatial_unwrap(*, grid: UwGrid, ui: UwInterp, st: SpaceTime, params: SpatialParams | None = None,
                   ifg_index=None) -> SpatialResult:
    p = params or SpatialParams()
    ph = np.nan_to_num(grid.ph, nan=0.0, posinf=0.0, neginf=0.0)
    n_ifg = ph.shape[1]
    n_ps = grid.grid_ij.shape[0]
    rowix = np.asarray(ui.rowix, dtype=float)
    colix = np.asarray(ui.colix, dtype=float)
    ge = np.concatenate((np.abs(colix[colix != 0]), np.abs(rowix[rowix != 0]))).astype(np.int64)
    n_edges = np.bincount(ge - 1, minlength=ui.n_edge)[:ui.n_edge]
    with np.errstate(invalid="ignore", over="ignore"):
        sigsq = np.round((edge_variance(st.dph_noise) * (p.nshortcycle**2) * n_edges) / p.costscale).astype(np.int16)
    sigsq = np.clip(sigsq, 1, p.maxshort)

    nzr, nzc = np.abs(rowix) > 0, np.abs(colix) > 0
    rf, cf = np.isfinite(rowix), np.isfinite(colix)
    rsel = nzr & rf & (np.abs(np.nan_to_num(rowix)).astype(int) <= ui.n_edge)
    csel = nzc & cf & (np.abs(np.nan_to_num(colix)).astype(int) <= ui.n_edge)
    ridx = np.abs(rowix[rsel]).astype(int) - 1
    cidx = np.abs(colix[csel]).astype(int) - 1
    r_ix, c_ix = (grid.grid_ij[:, 0] - 1).astype(int), (grid.grid_ij[:, 1] - 1).astype(int)
    nrow, ncol = grid.nzix.shape
    in_grid = (r_ix >= 0) & (r_ix < nrow) & (c_ix >= 0) & (c_ix < ncol)

    ph_uw = np.zeros((n_ps, n_ifg), np.float32)
    msd = np.full(n_ifg, np.nan, np.float32)
    pcg = np.full(n_ifg, np.nan)
    for i in (range(n_ifg) if ifg_index is None else ifg_index):
        col = ph[:, i]
        nz = col != 0
        if int(nz.sum()) < 10:
            log.info("interferogram %d: empty grid, not unwrapped", i + 1)
            continue
        if float(np.abs(np.mean(np.exp(1j * np.angle(col[nz]))))) > 0.99:
            log.warning("interferogram %d: constant phase, marked NaN", i + 1)
            ph_uw[:, i] = np.nan
            continue
        with np.errstate(invalid="ignore"):
            spread_i = np.round((np.abs(st.spread[:, i:i + 1]) * (p.nshortcycle**2)) / (6 * p.costscale)
                                * n_edges[:, None]).astype(np.int16).ravel()
        tot = (sigsq + spread_i).astype(np.float32)
        row_c = np.ones(rowix.shape, np.float32)
        col_c = np.ones(colix.shape, np.float32)
        row_c[rsel] = tot[ridx]
        col_c[csel] = tot[cidx]
        g = ph[ui.Z, i].reshape(nrow, ncol)
        phase = np.where(np.abs(g) > 0, np.angle(g).astype(np.float32), np.nan)
        u, rms = irls_unwrap(phase, row_c, col_c, dct_init(phase), p.irls_iter, p.irls_target_rms, p.irls_epsilon)
        pcg[i] = rms if np.isfinite(rms) else np.nan
        uw = enforce_congruence(phase, u)
        msd[i] = _msd(uw)
        vals = np.zeros(n_ps, np.float32)
        vals[in_grid] = uw[r_ix[in_grid], c_ix[in_grid]]
        ph_uw[:, i] = vals
    return SpatialResult(ph_uw=ph_uw, msd=msd, pcg_rms=pcg)
