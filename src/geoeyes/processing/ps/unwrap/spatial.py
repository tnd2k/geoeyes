"""Spatial unwrapping of every interferogram on the grid (legacy ``_uw_stat_costs``, IRLS_REFINED).

Edge variances come from the temporal residuals (robust MAD per edge, shrunk towards the scene median)
plus the local-gradient spread, scaled to SNAPHU-like integer costs; each interferogram's nearest-cell
phase grid is unwrapped by IRLS (``irls``), snapped to the wrapped phase + 2πk, and sampled at the PS cells.
The interferograms are independent: on large grids they run on worker processes (``SpatialParams.n_jobs``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from geoeyes.processing.ps.unwrap.grid import UwGrid
from geoeyes.processing.ps.unwrap.interp import UwInterp
from geoeyes.processing.ps.unwrap.irls import dct_init, enforce_congruence, irls_unwrap
from geoeyes.processing.ps.unwrap.space_time import SpaceTime

log = logging.getLogger(__name__)
DEGENERATE_MRL = 1.0 - 1e-6   # a smooth coherent interferogram (MRL 0.99..0.9999) is unwrapped, not dropped


@dataclass(frozen=True)
class SpatialParams:
    costscale: float = 100
    nshortcycle: int = 200
    maxshort: int = 32000
    irls_iter: int = 50
    irls_target_rms: float = 0.01
    irls_epsilon: float = 0.001
    align: bool = False                # irls.enforce_congruence(align=...): [ps] unwrap_align_constant
    # the cycle count of the grid steps from the space-time model (dph_space_uw), as StaMPS's SNAPHU cost offsets, on
    # the edges with a temporal rate (SpaceTime.rate != 0; every edge when the rate is off); False = the wrapped
    # gradients only (legacy IRLS_REFINED): an edge past ±π then takes a wrong cycle
    model_cycles: bool = False
    # worker processes over the interferograms: 0 = auto (CPU, memory), 1 = serial. Out of repr: the checkpoint keys
    # are built from repr(params), and the result does not depend on it
    n_jobs: int = field(default=0, repr=False, compare=False)


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
    tasks = []                                      # (i, phase grid, row costs, column costs)
    for i in (range(n_ifg) if ifg_index is None else ifg_index):
        col = ph[:, i]
        nz = col != 0
        if int(nz.sum()) < 10:
            log.info("interferogram %d: empty grid, not unwrapped", i + 1)
            continue
        if float(np.abs(np.mean(np.exp(1j * np.angle(col[nz]))))) > DEGENERATE_MRL:      # the same phase everywhere
            log.warning("interferogram %d: constant phase, marked NaN", i + 1)
            ph_uw[:, i] = np.nan
            continue
        tasks.append(i)

    def inputs(i):
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
        if not p.model_cycles:
            return phase, row_c, col_c, None, None
        # a grid step from the cell with the lower number to the higher one is +edge (dph = ph[e2]·conj(ph[e1])).
        # Only the edges with a reliable rate (temporal unwrapping) take the model's cycles: elsewhere the model is
        # the legacy one, fitted to the wrapped phase, which adds nothing but its noise to the wrapped gradient
        uw_i = np.asarray(st.dph_space_uw[:, i], np.float32)
        if st.rate is not None:
            uw_i = np.where(st.rate != 0, uw_i, np.nan).astype(np.float32)
        mx = np.full(colix.shape, np.nan, np.float32)
        my = np.full(rowix.shape, np.nan, np.float32)
        mx[csel] = np.sign(colix[csel]) * uw_i[cidx]
        my[rsel] = np.sign(rowix[rsel]) * uw_i[ridx]
        return phase, row_c, col_c, mx, my

    done = [0]

    def store(i, uw, rms):
        done[0] += 1
        log.info("interferogram %d unwrapped (%d/%d), PCG rms %.3g", i + 1, done[0], len(tasks), rms)
        pcg[i] = rms if np.isfinite(rms) else np.nan
        msd[i] = _msd(uw)
        vals = np.zeros(n_ps, np.float32)
        vals[in_grid] = uw[r_ix[in_grid], c_ix[in_grid]]
        ph_uw[:, i] = vals

    n_jobs = _n_jobs(len(tasks), nrow * ncol, p.n_jobs)
    if n_jobs <= 1:
        log.info("spatial unwrapping: %d interferograms, serial (grid %d x %d)", len(tasks), nrow, ncol)
        for i in tasks:
            store(i, *_unwrap_one(*inputs(i), p))
    else:                                           # the interferograms are independent: one per worker process
        from joblib import Parallel, delayed, parallel_config
        log.info("spatial unwrapping: %d interferograms on %d workers (grid %d x %d)", len(tasks), n_jobs, nrow, ncol)
        with parallel_config(backend="loky", inner_max_num_threads=1):
            par = Parallel(n_jobs=n_jobs, return_as="generator")
            for i, (uw, rms) in zip(tasks, par(delayed(_unwrap_one)(*inputs(i), p) for i in tasks), strict=True):
                store(i, uw, rms)
    return SpatialResult(ph_uw=ph_uw, msd=msd, pcg_rms=pcg)


def _unwrap_one(phase: np.ndarray, row_c: np.ndarray, col_c: np.ndarray, mx: np.ndarray | None,
                my: np.ndarray | None, p: SpatialParams) -> tuple[np.ndarray, float]:
    """One interferogram: IRLS from the DCT start, snapped to the wrapped phase + 2πk. ``mx``/``my``: model
    gradients that set the cycle count of each grid step (None = wrapped gradients)."""
    u, rms = irls_unwrap(phase, row_c, col_c, dct_init(phase, mx, my), p.irls_iter, p.irls_target_rms,
                         p.irls_epsilon, model_x=mx, model_y=my)
    return enforce_congruence(phase, u, align=p.align), rms


def _n_jobs(n_tasks: int, n_cells: int, requested: int) -> int:
    """Worker processes for the spatial unwrapping: ``requested`` (0 = auto) capped by the tasks, half the logical
    CPUs and the free memory (~100 bytes per grid cell per worker: the IRLS arrays and the padded DCT). Small grids
    stay in-process (starting workers costs more than it saves)."""
    import os
    if n_tasks <= 1 or (requested == 0 and n_cells < 1_000_000):
        return 1
    if requested > 0:
        return min(requested, n_tasks)
    cpu = max(1, (os.cpu_count() or 2) // 2)
    try:
        import psutil
        free = psutil.virtual_memory().available
    except ImportError:
        free = 8 * 1024**3
    by_mem = int(0.6 * free // max(1, 100 * n_cells))
    return max(1, min(n_tasks, cpu, by_mem))
