"""Step 2 — estimate the temporal coherence (gamma) of every candidate (legacy ``_ps_est_gamma_quick``).

Iterates: candidate phases (DEM-error term removed, weighted) are summed on a ``grid_size`` grid and
CLAP-filtered to an estimate of the spatially-correlated phase (``ph_patch``); the residual
``ph·conj(ph_patch)`` is fitted for the look-angle error K (topofit), K is spatially regularised where the
fit is ambiguous, and the weights are re-derived from the probability of each coherence being random
(``P-square``, from a Monte-Carlo topofit of random phases) until the RMS coherence change converges.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import lfilter, resample_poly, windows

from geoeyes.processing.ps.ambiguity import DemErrorParams, amb_weight, delaunay_edges, regularize, thresholds
from geoeyes.processing.ps.clap import clap_filter, low_pass
from geoeyes.processing.ps.topofit import topofit, topofit_full

log = logging.getLogger(__name__)
LOW_COH_BINS = 15                    # coherence bins (of 0.01) treated as certainly random


@dataclass(frozen=True)
class EstGammaParams:
    wavelength: float
    rho: float                       # mean slant range used to scale the DEM-error search (m)
    max_topo_err: float = 5.0
    grid_size: float = 50.0
    filter_weighting: str = "P-square"
    clap_win: int = 32
    clap_low_pass_wavelength: float = 800.0
    clap_alpha: float = 1.0
    clap_beta: float = 0.3
    gamma_change_convergence: float = 0.005
    gamma_max_iterations: int = 3
    dem_error: DemErrorParams = field(default_factory=DemErrorParams)
    chunk: int = 200_000             # candidates per topofit chunk (memory)
    max_K: float | None = None       # override of the K search bound (units of 1/bperp); None = from max_topo_err
    # parity only: the legacy S1 engine let NaN K (pixels with no valid phase) poison the CLAP grid
    legacy_nan_k: bool = False


@dataclass
class EstGamma:
    ph_patch: np.ndarray             # (n_ps, n_sec) complex64 unit phasors
    ph_res: np.ndarray               # (n_ps, n_sec) float32 residual angle of the last topofit
    ph_grid: np.ndarray              # (n_i, n_j, n_sec) complex64
    ph_weight: np.ndarray            # (n_ps, n_sec) complex64 (last iteration)
    K: np.ndarray                    # (n_ps,) rad/m, NaN where no interferogram is valid
    C: np.ndarray
    coh: np.ndarray
    Q: np.ndarray
    grid_ij: np.ndarray              # (n_ps, 2) 1-based grid cell (row, col)
    low_pass: np.ndarray
    n_trial_wraps: float
    Nr: np.ndarray                   # random-coherence histogram (scaled)
    Nr_max_nz_ix: int
    coh_bins: np.ndarray
    n_iter: int


def _hist(coh, bins):
    return np.bincount(np.digitize(np.ravel(coh), bins), minlength=bins.size + 1)[1:bins.size + 1]


def _grid_ij(xy, grid_size):
    g = np.zeros((xy.shape[0], 2))
    g[:, 0] = np.ceil((xy[:, 2] - np.amin(xy[:, 2]) + 1e-6) / grid_size)
    g[g[:, 0] == np.amax(g[:, 0]), 0] = np.amax(g[:, 0]) - 1
    g[:, 1] = np.ceil((xy[:, 1] - np.amin(xy[:, 1]) + 1e-6) / grid_size)
    g[g[:, 1] == np.amax(g[:, 1]), 1] = np.amax(g[:, 1]) - 1
    return g


def _prand_weight(coh, Nr, Nr_max_nz_ix, coh_bins):
    """(1 - P(random | coh))² per candidate; rescales ``Nr`` in place to the observed low-coherence count."""
    Na = _hist(coh, coh_bins)
    low = np.sum(Nr[:LOW_COH_BINS])
    if low > 0:
        Nr *= np.sum(Na[:LOW_COH_BINS]) / low
    else:
        log.warning("no random-phase samples in the first %d coherence bins; Nr not rescaled", LOW_COH_BINS)
    Na[Na == 0] = 1
    prand = Nr / Na
    prand[:LOW_COH_BINS] = 1
    prand[Nr_max_nz_ix + 1:] = 0
    prand[prand > 1] = 1
    g = windows.gaussian(7, std=1.2)
    prand = (lfilter(g, [1], np.concatenate([np.ones(7), prand])) / np.sum(g))[7:]
    prand = resample_poly(np.concatenate([[1], prand]), 10, 1)[:-9]
    ix = np.round(np.clip(np.nan_to_num(coh, nan=0.0), 0.0, 1.0) * 1000).astype(int)
    return (1 - prand[ix]) ** 2


def est_gamma(*, ph: np.ndarray, bperp: np.ndarray, bperp_mat: np.ndarray, master_ix: int, xy: np.ndarray,
              la: np.ndarray | None, da: np.ndarray | None, coh_prior: np.ndarray | None,
              params: EstGammaParams, seed: int = 2005) -> EstGamma:
    """Single-master: ``ph`` (n, n_ifg) and ``bperp`` (n_ifg,) include the master column, which is
    dropped here; ``bperp_mat`` (n, n_sec) and the outputs cover the secondaries only."""
    p = params
    ph = np.delete(ph, master_ix, axis=1)
    bperp = np.delete(np.asarray(bperp), master_ix)
    n_ps, n_ifg = ph.shape
    amp = np.float32(np.abs(ph))
    amp[amp == 0] = 1
    ph = ph / amp

    inc_mean = float(np.mean(la)) + 0.052 if la is not None else 21 * np.pi / 180
    max_k = p.max_K if p.max_K is not None else p.max_topo_err / (p.wavelength * p.rho * np.sin(inc_mean) / 4 / np.pi)
    n_trial_wraps = float((np.amax(bperp) - np.amin(bperp)) * max_k / (2 * np.pi))
    log.info("%d candidates, n_trial_wraps = %.4f", n_ps, n_trial_wraps)

    amb = p.dem_error.enabled
    fitter = topofit if amb else topofit_full
    # coherence distribution of random phases
    rand = 2 * np.pi * np.random.RandomState(seed).rand(n_ps, n_ifg)
    coh_rand = fitter(np.exp(1j * rand).astype(np.complex128), np.tile(bperp.T, (n_ps, 1)).astype(np.float64),
                       n_trial_wraps).coh
    del rand
    coh_bins = np.arange(0.005, 0.996, 0.01)
    Nr = _hist(coh_rand, coh_bins).astype(np.float64)
    nz = np.flatnonzero(Nr)
    Nr_max_nz_ix = int(nz[-1]) if nz.size else -1

    K = np.zeros(n_ps)
    C = np.zeros(n_ps)
    coh = (np.zeros(n_ps) if coh_prior is None
           else np.clip(np.nan_to_num(np.asarray(coh_prior, np.float64).reshape(-1), nan=0.0, posinf=1.0,
                                      neginf=0.0), 1e-6, 1 - 1e-6))
    Q = np.ones(n_ps)
    coh_save = coh.copy()
    ph_res = np.zeros((n_ps, n_ifg), np.float32)
    grid_ij = _grid_ij(xy, p.grid_size)
    weighting = 1.0 / (np.ones(n_ps) if da is None else np.asarray(da, np.float64).reshape(-1))
    gamma_change_save = 0.0
    n_i, n_j = int(np.amax(grid_ij[:, 0])), int(np.amax(grid_ij[:, 1]))
    cell = np.clip(grid_ij.astype(np.int64) - 1, 0, None)
    cell[:, 0] = np.minimum(cell[:, 0], n_i - 1)
    cell[:, 1] = np.minimum(cell[:, 1], n_j - 1)
    flat = cell[:, 0] * n_j + cell[:, 1]
    lp = low_pass(p.clap_win, p.grid_size, p.clap_low_pass_wavelength)
    edges = None

    i_loop = 1
    while True:
        ph_weight = (ph * np.exp(-1j * bperp_mat * (K if p.legacy_nan_k else np.nan_to_num(K, nan=0.0))[:, None])
                     * weighting.reshape(-1, 1)).astype(np.complex64)
        grid_flat = np.zeros((n_i * n_j, n_ifg), np.complex64)
        np.add.at(grid_flat, flat, ph_weight)
        ph_grid = grid_flat.reshape(n_i, n_j, n_ifg)
        ph_filt = clap_filter(ph_grid, p.clap_alpha, p.clap_beta, int(p.clap_win * 0.75), int(p.clap_win * 0.25),
                              lp)
        ph_patch = np.ascontiguousarray(ph_filt.reshape(-1, n_ifg)[flat, :]).astype(np.complex64)
        nzp = ph_patch != 0
        ph_patch[nzp] = ph_patch[nzp] / np.abs(ph_patch[nzp])

        chunk = max(10_000, int(p.chunk))
        for s in range(0, n_ps, chunk):
            e = min(s + chunk, n_ps)
            z = ph[s:e] * np.conj(ph_patch[s:e])
            valid = np.any(z != 0, axis=1)
            bad = np.flatnonzero(~valid) + s
            K[bad], coh[bad] = np.nan, 0
            loc = np.flatnonzero(valid)
            if loc.size == 0:
                continue
            idx = loc + s
            fit = fitter(z[loc].astype(np.complex128, copy=False), bperp_mat[idx].astype(np.float64, copy=False),
                         n_trial_wraps)
            K[idx], C[idx], coh[idx], Q[idx] = fit.K, fit.C, fit.coh, fit.Q
            ph_res[idx] = np.angle(fit.residual)

        if amb:
            if edges is None:
                edges = delaunay_edges(xy[:, 1:3])
            K = regularize(K, coh, Q, edges, p.dem_error)

        gamma_change_rms = np.sqrt(np.sum((coh - coh_save) ** 2) / n_ps)
        gamma_change_change = gamma_change_rms - gamma_change_save
        log.info("iteration %d: gamma change %.5f", i_loop, gamma_change_change)
        gamma_change_save = gamma_change_rms
        coh_save = coh.copy()
        if abs(gamma_change_change) < p.gamma_change_convergence or i_loop >= p.gamma_max_iterations:
            break
        i_loop += 1
        if p.filter_weighting == "P-square":
            weighting = _prand_weight(coh, Nr, Nr_max_nz_ix, coh_bins)
        else:                                       # SNR
            g = np.mean(amp * np.cos(ph_res), axis=1)
            sigma = np.sqrt(0.5 * (np.mean(amp**2, axis=1) - g**2))
            weighting = np.where(sigma == 0, 0.0, g / np.where(sigma == 0, 1.0, sigma))
        weighting = np.asarray(weighting).reshape(-1)
        if amb:
            weighting = weighting * amb_weight(Q, *thresholds(Q, p.dem_error))

    return EstGamma(ph_patch=ph_patch, ph_res=ph_res, ph_grid=ph_grid, ph_weight=ph_weight, K=K, C=C, coh=coh, Q=Q,
                    grid_ij=grid_ij, low_pass=lp, n_trial_wraps=n_trial_wraps, Nr=Nr, Nr_max_nz_ix=Nr_max_nz_ix,
                    coh_bins=coh_bins, n_iter=i_loop)
