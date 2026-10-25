"""Step 6 — unwrap the PS phase (legacy ``_ps_unwrap``, single-master, ``unwrap_patch_phase=y``,
IRLS_REFINED).

The spatially filtered patch phase is unwrapped (grid → edge network → temporal → spatial IRLS) and the
PS-specific residual ``angle(ph_rc · conj(ph_patch))`` is added back. Pass 1 unwraps as is; pass 2 first
removes the pass-1 smoothed look-angle error (``K_uw·bperp + C_uw``, optional ramp) and the APS, and adds
them back after unwrapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from geoeyes.processing.ps.unwrap.grid import UwGrid, grid_wrapped
from geoeyes.processing.ps.unwrap.interp import UwInterp, interp
from geoeyes.processing.ps.unwrap.space_time import SpaceTime, space_time
from geoeyes.processing.ps.unwrap.spatial import SpatialParams, SpatialResult, spatial_unwrap


@dataclass(frozen=True)
class UnwrapParams:
    wavelength: float
    rho: float
    max_topo_err: float = 5.0
    grid_size: float = 50.0
    prefilt_win: int = 16
    gold_alpha: float = 0.8
    coh_floor: float = 0.2
    prefilter: str = "gaussian"                # grid prefilter: gaussian (legacy S1) | goldstein (CSK) | none
    time_win: float = 730.0
    la_flag: bool = True
    scla_deramp: bool = False
    drop_ifg_index: tuple[int, ...] = ()       # 1-based epochs (master included) not unwrapped
    spatial: SpatialParams = field(default_factory=SpatialParams)
    legacy: bool = False                       # legacy G master-master row and gradient_filt indices (parity)


@dataclass
class Scla:
    """Pass-1 smoothed look-angle error and master atmosphere/orbit error (step 7)."""

    K_uw: np.ndarray            # (n,) rad/m
    C_uw: np.ndarray            # (n,)
    ph_ramp: np.ndarray | None  # (n, n_sec) or None


@dataclass
class Unwrapped:
    ph_uw: np.ndarray           # (n, n_sec) unwrapped phase, master column removed
    msd: np.ndarray             # (n_ifg,)
    grid: UwGrid
    ui: UwInterp
    st: SpaceTime
    sp: SpatialResult


def _with_master(a: np.ndarray, master_ix: int, fill) -> np.ndarray:
    return np.hstack([a[:, :master_ix], np.full((a.shape[0], 1), fill, a.dtype), a[:, master_ix:]])


def unwrap(*, ph_patch: np.ndarray, ph_rc: np.ndarray, K: np.ndarray, coh: np.ndarray, xy: np.ndarray,
           bperp: np.ndarray, day: np.ndarray, master_ix: int, ifgday_ix: np.ndarray, mean_incidence: float,
           params: UnwrapParams, scla: Scla | None = None, aps: np.ndarray | None = None,
           bperp_mat: np.ndarray | None = None) -> Unwrapped:
    """Single-master. ``ph_patch`` (n, n_sec) step-4 patch phase, ``ph_rc`` (n, n_ifg) step-5 corrected phase,
    ``K`` (n,) step-4 look-angle error, ``bperp``/``day`` (n_ifg,) per epoch (master: 0 / its date), ``day``
    relative to the master, ``ifgday_ix`` (n_ifg, 2) 0-based. ``scla``/``aps`` (n, n_ifg) select pass 2.
    ``bperp_mat`` (n, n_sec): the look-angle terms K·B⊥ removed and restored with each PS's own B⊥ (StaMPS
    ``ps_unwrap``); None or ``params.legacy`` = the scene-mean ``bperp`` for every PS (legacy)."""
    p = params
    n, n_ifg = ph_rc.shape
    bperp = np.asarray(bperp, np.float64)
    bp_ps = (bperp[None, :] if bperp_mat is None or p.legacy
             else _with_master(np.asarray(bperp_mat, np.float64), master_ix, 0.0))   # (n or 1, n_ifg)
    ph_w = _with_master(np.complex128(ph_patch) / np.abs(ph_patch), master_ix, 1)
    k_dem = np.nan_to_num(np.asarray(K, np.float64).reshape(-1))
    has_k = bool(np.any(np.isfinite(K) & (np.asarray(K) != 0)))
    kb = k_dem[:, None] * bp_ps if has_k else None
    if has_k:
        ph_w = ph_w * np.exp(1j * kb)
    nz = ph_w != 0
    ph_w[nz] = ph_w[nz] / np.abs(ph_w[nz])

    ramp = None
    if scla is not None:
        ph_w = ph_w * np.exp(-1j * (np.nan_to_num(scla.K_uw)[:, None] * bp_ps))
        ph_w = ph_w * np.exp(-1j * np.nan_to_num(scla.C_uw)[:, None])
        if p.scla_deramp and scla.ph_ramp is not None and scla.ph_ramp.shape[0] == n:
            ramp = scla.ph_ramp if scla.ph_ramp.shape[1] == n_ifg else _with_master(scla.ph_ramp, master_ix, 0.0)
            ph_w = ph_w * np.exp(-1j * ramp)
    aps_c = None if aps is None else np.nan_to_num(np.asarray(aps, np.float64), nan=0.0)
    if aps_c is not None:
        ph_w = ph_w * np.exp(-1j * aps_c)
    restore = None
    if scla is None and has_k:                    # IRLS unwraps without the DEM term; restored afterwards
        ph_w = ph_w * np.exp(-1j * kb)
        nz = ph_w != 0
        ph_w[nz] = ph_w[nz] / np.abs(ph_w[nz])
        restore = kb

    max_k = p.max_topo_err / (p.wavelength * p.rho * np.sin(mean_incidence) / 4 / np.pi)
    n_trial_wraps = (np.amax(bperp) - np.amin(bperp)) * max_k / (2 * np.pi)
    drop = {d - 1 for d in p.drop_ifg_index}
    idx = np.array([k for k in range(n_ifg) if k not in drop], dtype=int)

    grid = grid_wrapped(ph_w[:, idx], xy, grid_size=p.grid_size, prefilt_win=p.prefilt_win, gold_alpha=p.gold_alpha,
                        coh=coh, coh_floor=p.coh_floor, prefilter=p.prefilter)
    ui = interp(grid.nzix)
    st = space_time(grid=grid, ui=ui, day=np.asarray(day, np.float64), ifgday_ix=np.asarray(ifgday_ix)[idx],
                    bperp=bperp[idx], n_trial_wraps=n_trial_wraps, time_win=p.time_win, prefilt_win=p.prefilt_win,
                    la_flag=p.la_flag, estimate_K=scla is None, legacy=p.legacy)
    sp = spatial_unwrap(grid=grid, ui=ui, st=st, params=p.spatial)

    ph_uw = np.zeros((n, n_ifg), np.float32)
    msd = np.zeros(n_ifg, np.float32)
    ph_uw[:, idx] = sp.ph_uw
    msd[idx] = sp.msd
    if restore is not None:
        ph_uw[:, idx] += restore[:, idx].astype(np.float32)
    if scla is not None:
        ph_uw = ph_uw + scla.K_uw[:, None] * bp_ps + scla.C_uw[:, None]
        if ramp is not None:
            ph_uw = ph_uw + ramp
    patch = _with_master(np.asarray(ph_patch) / np.abs(ph_patch), master_ix, 0)
    ph_uw = ph_uw + np.angle(ph_rc * np.conj(patch))
    ph_uw[:, np.setdiff1d(np.arange(n_ifg), idx)] = 0
    if aps_c is not None:
        ph_uw = ph_uw + aps_c
    return Unwrapped(ph_uw=np.delete(ph_uw, master_ix, axis=1), msd=msd, grid=grid, ui=ui, st=st, sp=sp)
