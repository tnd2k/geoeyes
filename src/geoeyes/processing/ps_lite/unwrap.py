# Ported from modules/ps_stack/unwrap.py (algorithm unchanged; ADR-020).
"""Spatial unwrapping of PS phase, one interferogram at a time, with the refined IRLS solver.

PS are summed onto a regular grid of ``cell`` master pixels (unit phasors), the empty
cells near PS are filled from the nearest occupied cell, the grid is Goldstein-filtered and
unwrapped with the refined IRLS solver of the StaMPS ``IRLS_REFINED`` path (``processing.ps.unwrap.irls``:
DCT initialisation, IRLS driven by space-time edge costs — ``space_time_costs``: variance of each edge's
phase difference about a linear-in-time model, plus that interferogram's own misfit — then congruence
with the wrapped phase). The legacy ``method="capella"`` solver was not ported. Islands are
tied together with integer 2 pi offsets. The result per PS is the grid phase G at its cell and its own
wrapped phase (after the optional linear tropospheric term K*h (+ plane), estimated on the wrapped
grid and removed from the PS); the caller adds the PS's height-error term before taking
phi_uw = G + s*kh*dh + wrap(phi - G - s*kh*dh).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from scipy.ndimage import distance_transform_edt, uniform_filter

from geoeyes.processing.ps.unwrap.irls import dct_init, enforce_congruence, irls_unwrap, irls_unwrap_weighted
from geoeyes.processing.ps_lite.tropo import estimate_linear_tropo
from geoeyes.processing.unwrap.components import link_components
from geoeyes.processing.unwrap.goldstein import goldstein


def wrap(x):
    return np.angle(np.exp(1j * x))


@dataclass
class GridSpec:
    l0: int
    s0: int
    cell: tuple                  # (lines, samples) per grid cell
    ny: int
    nx: int

    @classmethod
    def for_window(cls, window: tuple, cell: tuple) -> GridSpec:
        l0, l1, s0, s1 = window
        return cls(l0, s0, cell, (l1 - l0 + cell[0] - 1) // cell[0], (s1 - s0 + cell[1] - 1) // cell[1])

    def index(self, line, sample):
        return (np.asarray(line) - self.l0) // self.cell[0], (np.asarray(sample) - self.s0) // self.cell[1]


@dataclass
class PairUnwrap:
    grid_phase: np.ndarray       # (n_ps,) unwrapped grid phase G at each PS cell, rad
    wrapped: np.ndarray          # (n_ps,) PS wrapped phase after the tropospheric model, rad
    tropo: object | None          # tropo.LinearTropo
    tropo_removed: np.ndarray | None   # (n_ps,) model removed from the PS phase, rad
    rms: float
    n_cells: int                 # occupied grid cells
    n_components: int            # islands before linking


def _grid(ph, iy, ix, spec, w=None):
    """Sum of (weighted) unit phasors per cell and the sum of weights."""
    w = np.ones(ph.shape) if w is None else w
    g = np.zeros((spec.ny, spec.nx), np.complex128)
    np.add.at(g, (iy, ix), w * np.exp(1j * ph))
    n = np.zeros((spec.ny, spec.nx))
    np.add.at(n, (iy, ix), w)
    return g, n


def unwrap_pair(phase: np.ndarray, iy: np.ndarray, ix: np.ndarray, height: np.ndarray, spec: GridSpec,
                wavelength: float, sign: float, *, tropo: bool = True, remove_plane: bool = False,
                tropo_block: int = 16, fill_radius: int = 4, gs_alpha: float = 0.8, gs_win: int = 32,
                gs_passes: int = 1, irls_iter: int = 30,
                ps_weight: np.ndarray | None = None, method: str = "s1", costs: dict | None = None,
                irls_target_rms: float = 0.01, irls_epsilon: float = 0.001) -> PairUnwrap:
    """Unwrap one interferogram given the wrapped PS phase and the PS grid cells. ``ps_weight``
    (0..1) sets how much each PS counts in its cell (e.g. its phase stability)."""
    if method != "s1":
        raise ValueError(f"ps_lite unwrap_method {method!r} is no longer supported (s1)")
    ph = phase.astype(np.float64)
    g, n = _grid(ph, iy, ix, spec, ps_weight)
    occ = n > 0
    tr, removed = None, None
    if tropo:
        hsum = np.zeros((spec.ny, spec.nx))
        np.add.at(hsum, (iy, ix), height)
        hcell = np.where(occ, hsum / np.maximum(n, 1), np.nan)
        consistency = np.where(occ, np.abs(g) / np.maximum(n, 1), 0.0)
        try:
            tr = estimate_linear_tropo(g, hcell, consistency, wavelength, sign=sign, block=tropo_block)
        except ValueError:
            tr = None
        if tr is not None:
            removed = tr.k_rad_per_m * (height - tr.h_ref)
            if remove_plane:
                ci, cj = iy - spec.ny / 2, ix - spec.nx / 2
                removed = removed + tr.ramp_az * ci + tr.ramp_rg * cj
            ph = ph - removed
            g, n = _grid(ph, iy, ix, spec, ps_weight)

    # fill empty cells near PS from the nearest occupied cell (low weight)
    dist, (ni, nj) = distance_transform_edt(~occ, return_indices=True)
    near = dist <= fill_radius
    unit = np.where(occ, g / np.maximum(np.abs(g), 1e-30), 0)
    filled = np.where(near, unit[ni, nj], 0)
    filt = goldstein(filled, int(min(gs_win, spec.ny, spec.nx)), gs_alpha, gs_passes) \
        if gs_passes > 0 and gs_alpha > 0 else filled
    wrapped = np.where(near, np.angle(filt), np.nan).astype(np.float32)
    cons = np.abs(uniform_filter(filled.real, 3) + 1j * uniform_filter(filled.imag, 3))
    weight = np.where(near, np.clip(cons, 0.05, 1.0) * np.where(occ, 1.0, 0.3), 0.0).astype(np.float32)

    init = dct_init(wrapped)
    if costs is not None:
        uw, rms = irls_unwrap(wrapped, costs["row_costs"], costs["col_costs"], init, irls_iter, irls_target_rms,
                              irls_epsilon)
    else:
        uw, rms = irls_unwrap_weighted(wrapped, weight, init, irls_iter, irls_target_rms, irls_epsilon)
    uw = np.where(near, enforce_congruence(wrapped, uw), np.nan)
    n_comp = int(ndimage.label(near)[1])
    if n_comp > 1:
        uw = link_components(uw)
    G = uw[iy, ix]
    return PairUnwrap(G.astype(np.float32), wrap(ph).astype(np.float32), tr, None if removed is None else removed.astype(np.float32),
                      float(rms), int(occ.sum()), n_comp)


def filled_grid_stack(phase: np.ndarray, iy: np.ndarray, ix: np.ndarray, spec: GridSpec,
                      ps_weight: np.ndarray | None = None, fill_radius: int = 4):
    """Unit phasor grid of every interferogram (K, ny, nx), empty cells near PS filled from the nearest
    occupied cell, 0 elsewhere; and the mask of cells that carry data (occupied or filled)."""
    K = phase.shape[1]
    occ = np.zeros((spec.ny, spec.nx), bool)
    occ[iy, ix] = True
    dist, (ni, nj) = distance_transform_edt(~occ, return_indices=True)
    near = dist <= fill_radius
    Z = np.zeros((K, spec.ny, spec.nx), np.complex64)
    for k in range(K):
        g, _ = _grid(phase[:, k].astype(np.float64), iy, ix, spec, ps_weight)
        unit = np.where(occ, g / np.maximum(np.abs(g), 1e-30), 0)
        Z[k] = np.where(near, unit[ni, nj], 0)
    return Z, near


def space_time_costs(Z: np.ndarray, near: np.ndarray, t_days: np.ndarray, rate_max: float | None = None,
                     n_rates: int = 81, chunk: int = 200_000) -> list[dict]:
    """StaMPS-style statistical costs for each interferogram's grid edges.

    For every edge (neighbouring cells along rows / columns) the wrapped phase difference d_k over the
    K interferograms is fitted with c + w * t_k, w from a periodogram on ``n_rates`` rates within
    +-``rate_max`` rad/day (default: one cycle over a quarter of the time span); the residual r_k is the
    edge's misfit. Edge variance for interferogram k = mean_j r_j^2 (the edge's noise, StaMPS ``sigsq``)
    + r_k^2 (this interferogram's ``spread``). Returns, per interferogram, the dict
    ``{'row_costs': (ny-1, nx), 'col_costs': (ny, nx-1)}`` the S1 solver turns into 1 / (1 + var/median).
    """
    K, ny, nx = Z.shape
    t = np.asarray(t_days, float)
    span = max(float(np.ptp(t)), 1.0)
    rate_max = rate_max or 2 * np.pi / (span / 4)
    rates = np.linspace(-rate_max, rate_max, n_rates)
    E = np.exp(-1j * np.outer(rates, t))                                   # (R, K)

    def edge_var(d, ok):                                                   # d: (K, E) complex
        n = d.shape[1]
        out = np.empty((K, n), np.float32)
        for i in range(0, n, chunk):
            sl = slice(i, min(i + chunk, n))
            z = d[:, sl]
            z = np.where(np.abs(z) > 0, z / np.maximum(np.abs(z), 1e-30), 0)
            P = np.abs(E @ z)                                               # (R, c)
            w = rates[np.argmax(P, axis=0)]
            m = z * np.exp(-1j * np.outer(t, w))
            c = np.angle(m.sum(axis=0))
            r = np.angle(m * np.exp(-1j * c))                               # (K, c)
            out[:, sl] = (np.mean(r ** 2, axis=0)[None, :] + r ** 2).astype(np.float32)
        return np.where(ok[None, :], out, 1e3)

    dr = (Z[:, 1:, :] * np.conj(Z[:, :-1, :])).reshape(K, -1)              # row edges (ny-1, nx)
    okr = (near[1:, :] & near[:-1, :]).ravel()
    vr = edge_var(dr, okr).reshape(K, ny - 1, nx)
    dc = (Z[:, :, 1:] * np.conj(Z[:, :, :-1])).reshape(K, -1)              # column edges (ny, nx-1)
    okc = (near[:, 1:] & near[:, :-1]).ravel()
    vc = edge_var(dc, okc).reshape(K, ny, nx - 1)
    return [{"row_costs": vr[k], "col_costs": vc[k]} for k in range(K)]
