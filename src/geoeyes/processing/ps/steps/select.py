"""Step 3 — select PS (legacy ``_ps_select``, single-master).

A coherence threshold per amplitude-dispersion (D_A) bin is set so the expected fraction of random-phase
pixels above it equals ``percent_rand`` (or a density); a straight line through (mean D_A, threshold)
gives each candidate's threshold. The candidates passing it are re-estimated with their own cell left out
of the CLAP filter (so a pixel does not smooth itself), the thresholds are re-derived, and a PS is kept
when its re-estimated coherence passes and its K agrees with step 2 within one ambiguity cycle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from geoeyes.processing.ps.ambiguity import DemErrorParams, delaunay_edges, regularize
from geoeyes.processing.ps.clap import clap_at_points
from geoeyes.processing.ps.steps.est_gamma import EstGamma
from geoeyes.processing.ps.topofit import topofit, topofit_full

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectParams:
    select_method: str = "DENSITY"          # or "PERCENT"
    percent_rand: float = 20.0               # max % random pixels (PERCENT)
    density_rand: float = 20.0               # max random pixels per km² (DENSITY)
    gamma_min_threshold: float = 0.3
    gamma_stdev_reject: float = 0.0          # bootstrap std of coherence; 0 = off
    drop_ifg_index: tuple[int, ...] = ()     # 1-based epoch indices (master included) left out of the fit
    clap_win: int = 32
    clap_alpha: float = 1.0
    clap_beta: float = 0.3
    slc_osf: int = 1
    reestimate: bool = True
    resmooth: bool = True                    # False: reuse step-2 ph_patch instead of re-filtering
    dem_error: DemErrorParams = field(default_factory=DemErrorParams)
    batch: int = 1024
    nr_scaling: str = "low_coherence"        # StaMPS (first 31 bins) | "population" (bin's share of all PS)
    legacy: bool = False                     # legacy CLAP window zero-padded at the bottom/right edge (parity)


@dataclass
class Select:
    ix: np.ndarray                 # step-1 candidates passing the first threshold
    keep_ix: np.ndarray            # (len(ix),) bool, kept after re-estimation
    ph_patch2: np.ndarray          # (len(ix), n_sec) complex64
    ph_res2: np.ndarray            # (len(ix), n_sec) float32 residual angle (0 outside ifg_index)
    K2: np.ndarray
    C2: np.ndarray
    coh2: np.ndarray
    Q2: np.ndarray
    coh_thresh: np.ndarray
    coh_thresh_coeffs: np.ndarray
    ifg_index: np.ndarray          # secondary columns used
    max_percent_rand: float


def _polyfit3_eval(x, y, x_eval):
    """MATLAB ``[p,S,mu] = polyfit(x, y, 3); polyval(p, x_eval, [], mu)``."""
    x = np.asarray(x, np.float64).ravel()
    mu1, mu2 = np.mean(x), np.std(x, ddof=1)
    mu2 = mu2 or 1.0
    return np.polyval(np.polyfit((x - mu1) / mu2, np.asarray(y, np.float64).ravel(), 3), (x_eval - mu1) / mu2)


def _da_bins(da: np.ndarray | None, n_ps: int) -> tuple[np.ndarray, np.ndarray]:
    if da is not None and len(da) >= 10000:
        s = np.sort(da)
        step = 10000 if len(da) >= 50000 else 2000
        return da, np.concatenate(([0], s[step::step][:-1], [s[-1]]))
    return np.ones(n_ps), np.array([0.0, 1.0])


def _histograms(da, edges, coh, coh_bins):
    """Per D_A bin: mean D_A and coherence histogram (zero coherence excluded; NaN is excluded too —
    the legacy engine counted it in the top bin)."""
    n_bins = len(edges) - 1
    k = np.clip(np.searchsorted(edges, da, side="right") - 1, 0, n_bins - 1)
    counts = np.bincount(k, minlength=n_bins)
    sums = np.bincount(k, weights=da, minlength=n_bins)
    da_mean = np.full(n_bins, np.nan)
    da_mean[counts > 0] = sums[counts > 0] / counts[counts > 0]
    hist = np.zeros((n_bins, len(coh_bins)), np.int64)
    ok = (coh != 0) & np.isfinite(coh)
    if ok.any():
        c = np.clip(np.digitize(coh[ok], coh_bins, right=True) - 1, 0, len(coh_bins) - 1)
        np.add.at(hist, (k[ok], c), 1)
    return hist, da_mean


def _min_coh(hist, Nr, n_rand, coh_bins, method, max_percent_rand, low_coh: int | None = None):
    """Coherence threshold per D_A bin: where the cumulative random fraction drops below the target,
    from a cubic through the neighbouring bins (NaN when it cannot be fitted). The random histogram is
    scaled to the bin's population (``low_coh`` None) or, as StaMPS, to its count in the first ``low_coh``
    (certainly random) coherence bins."""
    out = np.full(hist.shape[0], np.nan)
    for b in range(hist.shape[0]):
        na = hist[b].astype(float)
        if na.sum() == 0:
            continue
        nr = (Nr * (na.sum() / n_rand) if low_coh is None
              else Nr * np.sum(na[:low_coh]) / max(np.sum(Nr[:low_coh]), 1))
        na[na == 0] = 1
        if method.upper() == "PERCENT":
            pr = np.flip(np.cumsum(np.flip(nr)) / np.cumsum(np.flip(na)) * 100)
        else:
            pr = np.flip(np.cumsum(np.flip(nr)))
        ok = np.flatnonzero(pr < max_percent_rand)
        if ok.size == 0:
            out[b] = 1
            continue
        lo, hi = ok.min() - 3, min(ok.min() + 2, len(pr))
        if lo <= 0 or hi - lo < 4:
            continue
        seg = pr[lo:hi + 1]
        out[b] = _polyfit3_eval(seg, np.linspace((lo + 1) * 0.01, (hi + 1) * 0.01, len(seg)), max_percent_rand)
    return out


def _threshold(min_coh, da_mean, da_eval, default):
    """Line through (mean D_A, min coherence) evaluated at ``da_eval`` (constant at D_A 0.35 when the slope
    is not positive); ``default`` when no bin could be fitted."""
    ok = ~np.isnan(min_coh)
    if ok.sum() < 1:
        return np.array([default]), np.array([])
    min_coh, da_mean = min_coh[ok], da_mean[ok]
    if min_coh.shape[0] > 1:
        coeffs = np.polyfit(da_mean, min_coh, 1)
        if coeffs[0] > 0:
            return np.atleast_1d(np.polyval(coeffs, da_eval)), coeffs
        return np.atleast_1d(np.polyval(coeffs, 0.35)), np.array([])
    return np.atleast_1d(min_coh), np.array([])


def select(*, ph: np.ndarray, bperp: np.ndarray, bperp_mat: np.ndarray, master_ix: int, xy: np.ndarray,
           forced: np.ndarray, da: np.ndarray | None, gamma: EstGamma, params: SelectParams,
           seed: int | None = None) -> Select:
    """``ph``/``bperp`` include the master column (dropped here); ``gamma`` is the step-2 result."""
    p = params
    n_ifg_all = ph.shape[1]
    sec = [k for k in range(n_ifg_all) if k != master_ix]
    ph, bperp = ph[:, sec], np.asarray(bperp)[sec]
    drop = {d - 1 for d in p.drop_ifg_index}
    ifg_index = [k - (k > master_ix) for k in range(n_ifg_all) if k not in drop and k != master_ix]
    mrl = np.abs(np.mean(np.exp(1j * np.angle(ph)), axis=0))
    degenerate = set(np.flatnonzero(mrl > 0.99).tolist())
    if degenerate:
        log.warning("dropping degenerate interferogram(s) (constant phase, MRL > 0.99): %s", sorted(degenerate))
        ifg_index = [k for k in ifg_index if k not in degenerate]
    ifg_index = np.asarray(ifg_index, dtype=int)
    if ifg_index.size == 0:
        raise ValueError("no interferogram left after drop_ifg_index")
    n_ps = ph.shape[0]

    da, edges = _da_bins(None if da is None else np.asarray(da, np.float64).reshape(-1), n_ps)
    max_percent_rand = p.percent_rand
    if p.select_method.upper() != "PERCENT":
        area = np.prod(np.amax(xy[:, 1:], axis=0) - np.amin(xy[:, 1:], axis=0)) / 1e6
        max_percent_rand = p.density_rand * area / (len(edges) - 1)
    Nr = np.asarray(gamma.Nr, np.float64).reshape(-1)
    coh_bins = np.asarray(gamma.coh_bins).reshape(-1)
    coh_all = np.asarray(gamma.coh, np.float64).reshape(-1).copy()

    low_coh = None if p.nr_scaling == "population" else 31

    def min_coh(h):
        return _min_coh(h, Nr, float(n_ps), coh_bins, p.select_method, max_percent_rand, low_coh)

    hist, da_mean = _histograms(da, edges, coh_all, coh_bins)
    coh_thresh, coeffs = _threshold(min_coh(hist), da_mean, da, p.gamma_min_threshold)
    coh_thresh[coh_thresh < 0] = 0
    ix = np.flatnonzero((coh_all > coh_thresh) | forced)
    log.info("%d PS selected initially (threshold %.3f-%.3f)", ix.size, coh_thresh.min(), coh_thresh.max())

    if p.gamma_stdev_reject > 0:
        res = np.exp(1j * gamma.ph_res[ix][:, ifg_index])
        rng = np.random.default_rng(seed)
        boot = np.stack([np.abs(np.sum(res[:, rng.integers(0, res.shape[1], res.shape[1])], axis=1)) / res.shape[1]
                         for _ in range(100)])
        ix = ix[(boot.std(axis=0, ddof=1) < p.gamma_stdev_reject) | forced[ix]]
        log.info("%d PS left after bootstrap rejection", ix.size)

    n_sel = ix.size
    if not p.reestimate:
        ones = np.ones(n_sel, bool)
        return Select(ix, ones, gamma.ph_patch[ix], gamma.ph_res[ix], gamma.K[ix], gamma.C[ix], gamma.coh[ix],
                      gamma.Q[ix], coh_thresh, coeffs, ifg_index, max_percent_rand)

    ph = ph[ix]
    if p.resmooth:
        n_i, n_j = int(np.amax(gamma.grid_ij[:, 0])), int(np.amax(gamma.grid_ij[:, 1]))
        cells = gamma.grid_ij[ix].astype(np.int64) - 1
        cells[:, 0] = np.clip(cells[:, 0], 0, n_i - 1)
        cells[:, 1] = np.clip(cells[:, 1], 0, n_j - 1)
        ph_patch2 = clap_at_points(gamma.ph_grid, cells, p.clap_win, p.clap_alpha, p.clap_beta,
                                   np.atleast_2d(gamma.low_pass), osf_r=max(p.slc_osf - 1, 0), batch=p.batch,
                                   legacy=p.legacy)
    else:
        ph_patch2 = gamma.ph_patch[ix].astype(np.complex64)

    K2, C2, coh2, Q2 = (np.full(n_sel, np.nan), np.full(n_sel, np.nan), np.full(n_sel, np.nan), np.zeros(n_sel))
    ph_res2 = np.zeros((n_sel, ph.shape[1]), np.float32)
    psdph = ph * np.conj(ph_patch2)
    sub = psdph[:, ifg_index]
    valid = np.flatnonzero(np.all(np.isfinite(sub) & (np.abs(sub) > np.float32(1e-6)), axis=1))
    if valid.size:
        z = psdph[valid].astype(np.complex128)
        z = (z / np.where(np.abs(z) > 0, np.abs(z), 1.0))[:, ifg_index]
        fitter = topofit if p.dem_error.enabled else topofit_full
        fit = fitter(z, bperp_mat[ix][valid][:, ifg_index].astype(np.float64), float(gamma.n_trial_wraps),
                     mini_batch=500)
        K2[valid], C2[valid], coh2[valid], Q2[valid] = fit.K, fit.C, fit.coh, fit.Q
        ph_res2[np.ix_(valid, ifg_index)] = np.angle(fit.residual)
        if p.dem_error.enabled:
            K2[valid] = regularize(K2[valid], coh2[valid], Q2[valid], delaunay_edges(xy[ix, 1:3][valid]),
                                   p.dem_error)

    coh_all[ix] = coh2
    hist, da_mean = _histograms(da, edges, coh_all, coh_bins)
    coh_thresh, coeffs = _threshold(min_coh(hist), da_mean, da[ix], p.gamma_min_threshold)
    coh_thresh[coh_thresh < p.gamma_min_threshold] = p.gamma_min_threshold
    k_tol = 2 * np.pi / (np.amax(bperp) - np.amin(bperp))
    with np.errstate(invalid="ignore"):
        keep = ((coh2 > coh_thresh) & (np.abs(np.asarray(gamma.K)[ix] - K2) < k_tol)) | forced[ix]
    log.info("%d PS selected after re-estimation", int(keep.sum()))
    return Select(ix, keep, ph_patch2, ph_res2, K2, C2, coh2, Q2, coh_thresh, coeffs, ifg_index, max_percent_rand)
