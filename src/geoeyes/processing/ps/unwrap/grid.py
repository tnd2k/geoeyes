"""Resample the PS phase to a regular ``grid_size`` grid (legacy ``_uw_grid_wrapped``, Goldstein path).

Cells take the complex sum of their PS. With the prefilter on, each interferogram is CLAP/Goldstein
filtered (window ``prefilt_win``, exponent scaled per interferogram by its median coherence, gain scaled by
local coherence) and a Gaussian low-pass version is kept for the temporal step.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

from geoeyes.processing.ps.clap import clap_filter


@dataclass
class UwGrid:
    ph: np.ndarray            # (n_cells, n_ifg) complex64, filtered phase of the occupied cells
    ph_lowpass: np.ndarray    # (n_cells, n_ifg) complex64 or empty
    xy: np.ndarray            # (n_cells, 3) [id, x, y] cell centres (m)
    ij: np.ndarray            # (n_cells, 2) [row, col]
    nzix: np.ndarray          # (n_i, n_j) occupied cells
    grid_ij: np.ndarray       # (n_ps, 2) 1-based cell of every PS
    grid_x_min: float
    grid_y_min: float
    n_i: int
    n_j: int


def grid_wrapped(ph_in: np.ndarray, xy_in: np.ndarray, *, grid_size: float, prefilt_win: int, gold_alpha: float,
                 coh: np.ndarray | None, coh_floor: float = 0.2, prefilter: str | bool = "goldstein") -> UwGrid:
    """``ph_in`` (n_ps, n_ifg) complex phasors, ``xy_in`` (n_ps, 3) [id, x, y] m, ``coh`` (n_ps,) per-PS
    coherence used for the adaptive filter (broadcast to every interferogram). ``prefilter``: "goldstein"
    (coherence-adaptive CLAP + Gaussian low-pass copy, legacy CSK), "gaussian" (σ = prefilt_win/8 cells,
    legacy S1) or "none"."""
    prefilter = {True: "goldstein", False: "none"}.get(prefilter, prefilter)
    n_ps, n_ifg = ph_in.shape
    x_min, y_min = float(np.min(xy_in[:, 1])), float(np.min(xy_in[:, 2]))
    g = np.zeros((n_ps, 2))
    g[:, 0] = np.ceil((xy_in[:, 2] - y_min + 1e-3) / grid_size)
    g[g[:, 0] == np.amax(g[:, 0]), 0] = np.amax(g[:, 0]) - 1
    g[:, 1] = np.ceil((xy_in[:, 1] - x_min + 1e-3) / grid_size)
    g[g[:, 1] == np.amax(g[:, 1]), 1] = np.amax(g[:, 1]) - 1
    n_i, n_j = int(np.amax(g[:, 0])), int(np.amax(g[:, 1]))
    if min(n_i, n_j) < prefilt_win:
        raise ValueError(f"resampled grid {n_i}x{n_j} is smaller than the prefilter window {prefilt_win}")
    r, c = (g[:, 0] - 1).astype(int), (g[:, 1] - 1).astype(int)

    phc = np.nan_to_num(np.asarray(ph_in).astype(np.complex64), nan=0.0, posinf=0.0, neginf=0.0)
    grid = np.zeros((n_i, n_j, n_ifg), np.complex64)
    np.add.at(grid, (r, c), phc)
    nzix = np.any(grid != 0, axis=2)
    nz_i, nz_j = np.where(nzix)

    ph_lowpass = np.array([])
    if prefilter == "none":
        ph = grid[nzix]
    elif prefilter == "gaussian":
        sigma = max(prefilt_win // 8, 2)
        filt = np.empty_like(grid)
        for k in range(n_ifg):
            filt[:, :, k] = (gaussian_filter(grid[:, :, k].real, sigma=sigma)
                             + 1j * gaussian_filter(grid[:, :, k].imag, sigma=sigma)).astype(np.complex64)
        filt[~nzix, :] = 0
        ph = filt[nzix]
    else:
        coh_ps = np.ones(n_ps) if coh is None else np.clip(
            np.clip(np.nan_to_num(np.asarray(coh, np.float64).reshape(-1), nan=0.0, posinf=1.0, neginf=0.0),
                    1e-6, 1 - 1e-6), 0.0, 1.0)
        coh_grid = np.zeros((n_i, n_j, n_ifg), np.float32)
        count = np.zeros((n_i, n_j, n_ifg), np.float32)
        np.add.at(coh_grid, (r, c), np.broadcast_to(coh_ps[:, None], (n_ps, n_ifg)).astype(np.float32))
        np.add.at(count, (r, c), 1.0)
        coh_grid = np.divide(coh_grid, np.maximum(count, 1.0), out=np.zeros_like(coh_grid), where=count > 0)
        coh_grid[~nzix] = np.nan
        coh_med = np.clip(np.nan_to_num(np.nanmedian(coh_grid, axis=(0, 1)).astype(np.float64), nan=0.0, posinf=1.0,
                                        neginf=0.0), 0.0, 1.0)
        a_min = min(0.15, gold_alpha * 0.25)
        alpha = (a_min + (gold_alpha - a_min) * coh_med).astype(np.float32)
        work = np.where(nzix[:, :, None], grid, np.nan + 0j).astype(np.complex64)
        filt = clap_filter(work, alpha, 0.1, prefilt_win, 0, None, coh_grid=coh_grid, coh_floor=coh_floor)
        filt[~nzix, :] = 0
        ph = filt[nzix]
        sigma = max(prefilt_win // 8, 2)
        low = np.empty_like(grid)
        for k in range(n_ifg):
            low[:, :, k] = (gaussian_filter(grid[:, :, k].real, sigma=sigma)
                            + 1j * gaussian_filter(grid[:, :, k].imag, sigma=sigma)).astype(np.complex64)
        ph_lowpass = low[nzix]

    xy = np.column_stack([np.arange(nz_i.size), (nz_j - 0.5) * grid_size, (nz_i - 0.5) * grid_size])
    return UwGrid(ph=ph, ph_lowpass=ph_lowpass, xy=xy, ij=np.column_stack([nz_i, nz_j]), nzix=nzix, grid_ij=g,
                  grid_x_min=x_min, grid_y_min=y_min, n_i=n_i, n_j=n_j)
