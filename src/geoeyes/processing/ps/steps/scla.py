"""Step 7 (first part) — spatially-correlated look-angle error (SCLA) and master atmosphere/orbit error from the
unwrapped phase (legacy ``_ps_calc_scla(coest_mean_vel=True)`` + ``_ps_smooth_scla``, single-master).

Per PS the unwrapped phase (APS removed in pass 2, ramp removed, referenced to the reference PS) is fitted
with phase = C + K·bperp + v·t over the interferograms (``bperp`` of the PS itself);
``C_uw`` is the intercept of phase - K·bperp_ps against t. Smoothing clips K and C of every PS to the range of
its Delaunay neighbours.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from geoeyes.processing.ps.geometry import triangulation_edges

log = logging.getLogger(__name__)


@dataclass
class SclaResult:
    K_uw: np.ndarray           # (n,) rad/m
    C_uw: np.ndarray           # (n,) rad
    ph_scla: np.ndarray        # (n, n_sec) K·bperp
    ph_ramp: np.ndarray        # (n, n_sec) removed ramp (empty when not deramped)
    deramp_degree: int | None


def nonlinear_improvement(xy: np.ndarray, ph: np.ndarray, max_ifg_sample: int = 12) -> float:
    """Median relative RMS reduction of a quadratic (x², y², xy, 1) over a plane fit across interferograms."""
    x = np.asarray(xy[:, 1], np.float64) / 1000.0
    y = np.asarray(xy[:, 2], np.float64) / 1000.0
    a1 = np.column_stack((x, y, np.ones_like(x)))
    a2 = np.column_stack((x**2, y**2, x * y, np.ones_like(x)))
    n_ifg = ph.shape[1]
    sample = np.arange(n_ifg) if n_ifg <= max_ifg_sample else np.linspace(0, n_ifg - 1, max_ifg_sample, dtype=int)
    gains = []
    for k in sample:
        col = np.asarray(ph[:, k], np.float64)
        ok = np.isfinite(col)
        if int(ok.sum()) <= 10:
            continue
        b = col[ok]
        r1 = np.sqrt(np.mean((b - a1[ok] @ np.linalg.lstsq(a1[ok], b, rcond=None)[0]) ** 2))
        r2 = np.sqrt(np.mean((b - a2[ok] @ np.linalg.lstsq(a2[ok], b, rcond=None)[0]) ** 2))
        if np.isfinite(r1) and r1 > 1e-12 and np.isfinite(r2):
            gains.append((r1 - r2) / r1)
    return float(np.median(gains)) if gains else 0.0


def deramp(xy: np.ndarray, ph: np.ndarray, degree: int = 1, weights: np.ndarray | None = None):
    """Remove a weighted least-squares surface per interferogram: degree 1 = plane, 2 = x² + y² + xy + c.
    Returns (deramped, ramp); interferograms with too few finite values keep NaN ramps."""
    n = ph.shape[0]
    if degree == 1:
        a = np.column_stack((xy[:, 1:3] / 1000, np.ones((n, 1))))
    elif degree == 2:
        x, y = xy[:, 1:2] / 1000, xy[:, 2:3] / 1000
        a = np.column_stack((x**2, y**2, x * y, np.ones((n, 1))))
    else:
        raise ValueError(f"unsupported deramp degree {degree}")
    w = np.ones(n) if weights is None else np.asarray(weights).reshape(-1)
    out = ph.copy()
    ramp = np.full_like(ph, np.nan)
    for k in range(ph.shape[1]):
        ok = ~np.isnan(ph[:, k])
        if n - int((~ok).sum()) <= a.shape[1]:
            log.warning("interferogram %d not deramped (too few values)", k + 1)
            continue
        ws = np.sqrt(w[ok])
        coeff = np.linalg.lstsq(a[ok] * ws[:, None], ph[ok, k] * ws, rcond=None)[0]
        ramp[:, k] = a @ coeff
        out[:, k] = ph[:, k] - ramp[:, k]
    return out, ramp


def calc_scla(*, ph_uw: np.ndarray, bperp_mat: np.ndarray, ifgday: np.ndarray, master_ix: int, xy: np.ndarray,
              aps: np.ndarray | None = None, deramp_scla: bool = True, nonlinear_min_improve: float = 0.08,
              ref_ps: np.ndarray | None = None, drop_ifg_index=(), legacy: bool = False) -> SclaResult:
    """``ph_uw`` (n, n_sec) step-6 output, ``bperp_mat`` (n, n_sec), ``ifgday`` (n_ifg, 2) ordinals including the
    master-master row, ``aps`` (n, n_ifg) with the master column (pass 2). ``ref_ps`` None = all PS.
    ``legacy``: K fitted against the scene-mean B⊥ instead of each PS's own."""
    ph = np.asarray(ph_uw, np.float64).copy()
    if aps is not None:
        ph = ph - np.delete(np.nan_to_num(np.asarray(aps, np.float64), nan=0.0), master_ix, axis=1)
    ph_ramp = np.array([])
    degree = None
    if deramp_scla:
        degree = 2 if nonlinear_improvement(xy, ph) >= nonlinear_min_improve else 1
        ph, ph_ramp = deramp(xy, ph, degree)
    n_sec = ph.shape[1]
    idx = np.setdiff1d(np.arange(n_sec), np.asarray(drop_ifg_index, dtype=int))
    ref = np.arange(ph.shape[0]) if ref_ps is None else ref_ps
    ph = ph - np.nanmean(ph[ref, :], axis=0)

    bperp = np.asarray(bperp_mat, np.float64)[:, idx]
    rows = np.where(idx < master_ix, idx, idx + 1)       # ifgday still holds the master-master row
    day = ifgday[rows, 1] - ifgday[rows, 0]
    phs = ph[:, idx]
    nan_col = np.all(np.isnan(phs), axis=0)
    ok = ~nan_col
    n_ok = int(ok.sum())
    if legacy:
        # legacy: one design matrix with the scene-mean B⊥ for every PS
        bmean = np.mean(bperp, axis=0)
        g = (np.column_stack((np.ones(n_ok), bmean[ok], day[ok])) if idx.size >= 4
             else np.column_stack((np.ones(n_ok), bmean[ok])))
        w = np.eye(n_ok)
        K = np.linalg.lstsq(g.T @ w @ g, g.T @ w @ phs[:, ok].T, rcond=None)[0].T[:, 1]
    else:
        # StaMPS ps_calc_scla: each PS against its own B⊥ (normal equations solved per PS)
        n = phs.shape[0]
        cols = [np.ones((n, n_ok)), bperp[:, ok]] + ([np.broadcast_to(day[ok], (n, n_ok))] if idx.size >= 4 else [])
        g = np.stack(cols, axis=2)                                        # (n, n_ok, p)
        K = (np.linalg.pinv(np.einsum("nip,niq->npq", g, g))
             @ np.einsum("nip,ni->np", g, phs[:, ok])[..., None])[:, 1, 0]
    ph_scla = K[:, None] * bperp
    ph_scla[:, nan_col] = np.nan
    gc = np.column_stack((np.ones(idx.size), day))
    wc = np.eye(idx.size)
    C = np.linalg.solve(gc.T @ wc @ gc, gc.T @ wc @ (phs - ph_scla).T)[0, :]
    return SclaResult(K_uw=K, C_uw=C, ph_scla=ph_scla, ph_ramp=ph_ramp, deramp_degree=degree)


def smooth_scla(scla: SclaResult, xy: np.ndarray, bperp_mat: np.ndarray) -> SclaResult:
    """Clip every PS's K and C to the [min, max] of its Delaunay neighbours."""
    e = triangulation_edges(np.asarray(xy, np.float64)[:, 1:3])
    out = []
    for v in (np.asarray(scla.K_uw, np.float64).copy(), np.asarray(scla.C_uw, np.float64).copy()):
        lo = np.full(v.size, np.inf, np.float32)
        hi = np.full(v.size, -np.inf, np.float32)
        for a, b in ((0, 1), (1, 0)):
            np.minimum.at(lo, e[:, a], v[e[:, b]].astype(np.float32))
            np.maximum.at(hi, e[:, a], v[e[:, b]].astype(np.float32))
        above, below = v > hi, v < lo
        v[above], v[below] = hi[above], lo[below]
        out.append(v)
    K, C = out
    with np.errstate(invalid="ignore"):
        ph_scla = np.nan_to_num(np.asarray(bperp_mat, np.float64) * K[:, None], nan=0.0)
    return SclaResult(K_uw=K, C_uw=C, ph_scla=ph_scla, ph_ramp=scla.ph_ramp, deramp_degree=scla.deramp_degree)
