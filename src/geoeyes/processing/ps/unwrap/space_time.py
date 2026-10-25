"""Temporal unwrapping of every edge (legacy ``_uw_sb_unwrap_space_time``, ``3D`` branch as used by
IRLS_REFINED).

Edge phase differences are optionally corrected for an edge look-angle (DEM) error found by a trial search
(pass 1 only), fitted with an epoch time series (least squares over the interferogram design matrix ``G``),
smoothed by a Gaussian window in time and re-wrapped around the smooth model (``dph_space_uw`` = model +
wrapped residual). Where the local spatial phase gradient (FFT peak in a sliding window, interpolated to the
cells) explains an edge better than the temporal model, that edge takes the spatial estimate instead.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree

from geoeyes.processing.ps.unwrap.grid import UwGrid
from geoeyes.processing.ps.unwrap.interp import UwInterp


@dataclass
class SpaceTime:
    dph_space_uw: np.ndarray     # (n_edge, n_ifg) temporally unwrapped edge phase
    dph_noise: np.ndarray        # (n_edge, n_ifg) float32 residual about the model (NaN = unreliable)
    G: np.ndarray                # (n_ifg, n_image) design matrix
    spread: np.ndarray           # (n_edge, n_ifg) float32
    ifreq_ij: np.ndarray         # (n_cells, n_ifg) float32 local gradients
    jfreq_ij: np.ndarray
    shaky_ix: np.ndarray         # (n_edge,) edges taken from the spatial gradient
    K: np.ndarray                # (n_edge,) edge look-angle error (0 when not estimated)
    coh: np.ndarray


def _safe_range(b) -> float:
    b = np.asarray(b, dtype=np.float64).ravel()
    if b.size == 0:
        return 1.0
    for r in (float(np.max(b) - np.min(b)), float(np.max(np.abs(b)))):
        if np.isfinite(r) and r > 0:
            return r
    return 1.0


def _wrapped(space_cpx, smooth, chunk=200_000):
    out = np.empty(space_cpx.shape, np.float32)
    two_pi, pi = np.float32(2.0 * np.pi), np.float32(np.pi)
    for e0 in range(0, space_cpx.shape[0], chunk):
        res = np.angle(space_cpx[e0:e0 + chunk]).astype(np.float32, copy=False) - \
            smooth[e0:e0 + chunk].astype(np.float32, copy=False)
        out[e0:e0 + chunk] = ((res + pi) % two_pi) - pi
    return out


def _edge_dem_error(dph_space, G, day, ifgday_ix, bperp, n_trial_wraps, chunk=100_000):
    """Trial search + linear refinement of a look-angle error per edge, on sequential differences of the
    single-master interferograms (legacy "multiple image sequential daisy chain" branch)."""
    n_edge = dph_space.shape[0]
    brange = _safe_range(bperp)
    ix = np.flatnonzero(np.abs(np.diff(ifgday_ix, axis=1)).ravel() == 1)
    if len(ix) >= len(day) - 1:
        dsub, bsub = dph_space[:, ix], bperp[ix]
        brange_sub = _safe_range(bsub)
    else:
        per_image = np.sum(np.abs(G), axis=0)
        m = int(np.argmax(per_image))
        if np.amax(per_image) >= len(day) - 2:
            sel = G[:, m] != 0
            sign = -np.sign(G[sel, m].astype(np.float32))
            dsub = dph_space[:, sel].copy()
            bsub = bperp[sel].copy()
            bsub[sign == -1] = -bsub[sign == -1]
            bsub = np.concatenate([bsub, [0]])
            flip = np.tile(sign, (n_edge, 1)) == -1
            dsub[flip] = np.conj(dsub[flip])
            dsub = np.hstack([dsub, np.mean(np.abs(dsub), axis=1, keepdims=True)])
            sec = (np.sum(ifgday_ix[sel, :], axis=1) - m).astype(np.int32)
            order = np.argsort(day[np.concatenate([sec, [m]])], axis=0)
            dsub, bsub = dsub[:, order], np.diff(bsub[order], axis=0)
            brange_sub = _safe_range(bsub)
            dsub = dsub[:, 1:] * np.conj(dsub[:, :-1])
            with np.errstate(divide="ignore", invalid="ignore"):
                dsub /= np.abs(dsub)
            dsub = np.nan_to_num(dsub, nan=0.0)
        else:
            dsub, bsub, brange_sub = dph_space, bperp, brange
    ntw = float(np.asarray(n_trial_wraps * (brange_sub / brange)).reshape(-1)[0])
    if not np.isfinite(ntw) or ntw <= 0:
        ntw = float(n_trial_wraps)

    mult = np.arange(-int(np.ceil(8 * ntw)), int(np.ceil(8 * ntw)) + 1)
    n_trials = mult.size
    tp = np.atleast_1d(np.asarray(bsub, np.float64) / float(brange_sub) * (np.pi / 4))
    tmat = np.exp(-1j * tp[:, None] * mult[None, :])
    sums = np.empty((n_edge, n_trials), np.result_type(dsub.dtype, np.complex128))
    for e0 in range(0, n_edge, chunk):
        sums[e0:e0 + chunk] = dsub[e0:e0 + chunk] @ tmat
    coh_all = np.abs(sums) / np.abs(dsub).sum(axis=1, keepdims=True).clip(1e-10)
    best = np.argmax(coh_all, axis=1)
    cmax = coh_all[np.arange(n_edge), best]
    pw = max(3, n_trials // 20)
    r = np.arange(n_trials)[None, :]
    peak = (r >= np.maximum(0, best[:, None] - pw)) & (r <= np.minimum(n_trials - 1, best[:, None] + pw))
    valid = (cmax - np.where(peak, 0.0, coh_all).max(axis=1)) > 0.03
    k0_all = (np.pi / 4 / brange_sub) * mult[best].astype(np.float64)
    K = np.zeros(n_edge, np.float32)
    coh = np.zeros(n_edge, np.float32)
    vi = np.flatnonzero(valid)
    brow = np.asarray(bsub, np.float64)
    for c0 in range(0, vi.size, chunk):
        v = vi[c0:c0 + chunk]
        d, k0 = dsub[v], k0_all[v]
        rph = d * np.exp(-1j * k0[:, None] * brow[None, :])
        ang = np.angle(rph * np.conj(rph.sum(axis=1, keepdims=True)))
        w = np.abs(d)
        wb, wr = w * brow[None, :], w * ang
        den = (wb * wb).sum(axis=1)
        kv = (k0 + np.where(den > 0, (wb * wr).sum(axis=1) / den, 0.0)).astype(np.float32)
        pr = d * np.exp(-1j * kv[:, None] * brow[None, :])
        K[v] = kv
        coh[v] = (np.abs(pr.sum(axis=1)) / np.abs(pr).sum(axis=1).clip(1e-10)).astype(np.float32)
    return K, coh


def gradient_filt(ph: np.ndarray, n_win: int, legacy: bool = False):
    """Dominant fringe frequency of every n_win window (step n_win/4) with >= 6 non-zero cells: (ifreq,
    jfreq, centres (row, col), peak/mean |FFT|). ``legacy``: the indices of the C-order flat argmax are
    swapped, so ``ifreq`` is read along columns and ``jfreq`` along rows."""
    n_i, n_j = ph.shape
    n_inc = n_win // 4
    n_wi, n_wj = (n_i + n_inc - 1) // n_inc - 3, (n_j + n_inc - 1) // n_inc - 3
    ph = np.nan_to_num(ph)
    fi, fj, hm, cij = [], [], [], []
    for a in range(n_wi):
        i1, i2 = a * n_inc, a * n_inc + n_win
        if i2 > n_i:
            i1, i2 = n_i - n_win, n_i
        for b in range(n_wj):
            j1, j2 = b * n_inc, b * n_inc + n_win
            if j2 > n_j:
                j1, j2 = n_j - n_win, n_j
            bit = ph[i1:i2, j1:j2].astype(np.float64)       # NumPy >= 2 keeps float32 FFTs in single precision
            if np.sum(bit != 0) < 6:
                continue
            h = np.abs(np.fft.fft2(bit))
            k = int(np.argmax(h))
            r, c = (k % n_win, k // n_win) if legacy else (k // n_win, k % n_win)
            k1 = (r + n_win // 2) % n_win or n_win
            k2 = (c + n_win // 2) % n_win or n_win
            fi.append((k1 - n_win // 2 - 1) * 2 * np.pi / n_win)
            fj.append((k2 - n_win // 2 - 1) * -2 * np.pi / n_win)
            hm.append(np.max(h) / np.mean(h))
            cij.append([(i1 + i2) / 2, (j1 + j2) / 2])
    if not cij:
        e = np.array([], np.float64)
        return e, e, np.empty((0, 2)), e
    return np.array(fi), np.array(fj), np.array(cij, np.float64), np.array(hm)


def _to_cells(centres, values, mask, ij, chunk=100_000):
    n = ij.shape[0]
    out = np.full(n, np.nan, np.float32)
    if np.sum(mask) <= 2:
        return out
    src = np.column_stack((centres[mask, 1], centres[mask, 0])).astype(np.float32)
    val = values[mask].astype(np.float32)
    q = np.column_stack((ij[:, 1], ij[:, 0])).astype(np.float32)
    if src.shape[0] >= 100:
        f = LinearNDInterpolator(src, val, fill_value=np.nan)
        for k in range(0, n, chunk):
            out[k:k + chunk] = f(q[k:k + chunk]).astype(np.float32, copy=False)
        return out
    tree = cKDTree(src)
    for k in range(0, n, chunk):
        out[k:k + chunk] = val[tree.query(q[k:k + chunk], k=1)[1]]
    return out


def space_time(*, grid: UwGrid, ui: UwInterp, day: np.ndarray, ifgday_ix: np.ndarray, bperp: np.ndarray,
               n_trial_wraps: float, time_win: float, prefilt_win: int, la_flag: bool = True,
               estimate_K: bool = True, scf_flag: bool = True, legacy: bool = False) -> SpaceTime:
    """``day`` (n_image,) days relative to the master, ``ifgday_ix`` (n_ifg, 2) 0-based, ``bperp`` (n_ifg,).
    ``estimate_K`` is off in the second pass (DEM error already removed with the SCLA). ``legacy``: the
    master-master row of ``G`` is +1 and ``gradient_filt`` swaps its frequency indices."""
    ph = grid.ph
    n_cells, n_ifg = ph.shape
    e1, e2 = ui.edgs[:, 1], ui.edgs[:, 2]
    n_edge = ui.n_edge
    dph = (ph[e2, :] * np.conj(ph[e1, :])).astype(np.complex64, copy=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        dph = np.nan_to_num(dph / np.abs(dph), nan=0.0)

    ifgday_ix = np.array(ifgday_ix, dtype=np.int64)
    G = np.zeros((n_ifg, day.shape[0]), np.float32)
    for i in range(n_ifg):                       # legacy: sequential, so a master-master row ends up +1
        if not legacy and ifgday_ix[i, 0] == ifgday_ix[i, 1]:
            continue
        G[i, int(ifgday_ix[i, 0])] = -1
        G[i, int(ifgday_ix[i, 1])] = 1
    used = np.sum(np.abs(G), axis=0) != 0
    day, G = day[used], G[:, used]
    for idx in np.sort(np.flatnonzero(~used))[::-1]:
        ifgday_ix[ifgday_ix > idx] -= 1

    K = np.zeros(n_edge, np.float32)
    coh = np.ones(n_edge, np.float32)
    if la_flag:
        if estimate_K:
            K, coh = _edge_dem_error(dph, G, day, ifgday_ix, bperp, n_trial_wraps)
        K[coh < 0.22] = 0
        dph = dph * np.exp(-1j * np.outer(K, bperp.T))

    series = np.vstack([np.zeros((1, n_edge)),
                        np.linalg.lstsq(G[:, 1:].astype(np.float64), np.angle(dph).T.astype(np.float64),
                                        rcond=None)[0]])
    wm = np.exp(-((day[:, None] - day[None, :]) ** 2) / (2.0 * time_win**2))
    wm /= wm.sum(axis=1, keepdims=True)
    smooth_ifg = (G @ (wm @ series).astype(np.float32)).T
    noise = _wrapped(dph, smooth_ifg)
    uw = smooth_ifg + noise
    if la_flag:
        uw = uw + K[:, None] * bperp[None, :]

    ifreq = np.full((n_cells, n_ifg), np.nan, np.float32)
    jfreq = np.full((n_cells, n_ifg), np.nan, np.float32)
    spread = np.zeros((n_edge, n_ifg), np.float32)
    shaky = np.array([])
    if scf_flag:
        ang = np.angle(ph)
        for i in range(n_ifg):
            img = np.zeros(grid.nzix.shape, np.float32)
            img[grid.ij[:, 0], grid.ij[:, 1]] = ang[:, i]
            fi, fj, cij, hm = gradient_filt(img, prefilt_win, legacy)
            ifreq[:, i] = _to_cells(cij, fi, ~np.isnan(fi) & (hm / (np.abs(fi) + 1) > 3), grid.ij)
            jfreq[:, i] = _to_cells(cij, fj, ~np.isnan(fj) & (hm / (np.abs(fj) + 1) > 3), grid.ij)
        di = grid.ij[e2, 0] - grid.ij[e1, 0]
        dj = grid.ij[e2, 1] - grid.ij[e1, 1]
        sm_grad = (di[:, None] * 0.5 * (ifreq[e1] + ifreq[e2]) + dj[:, None] * 0.5 * (jfreq[e1] + jfreq[e2])) \
            .astype(np.float32, copy=False)
        noise2 = ((uw - sm_grad + np.pi) % (2.0 * np.pi)) - np.pi
        std1 = np.nanstd(noise, axis=1)
        std2 = np.nanstd(noise2, axis=1)
        shaky = np.isnan(std1) | (std1 > std2)
        s = np.flatnonzero(shaky)
        n2 = noise2[s].copy()
        n2[np.nanstd(n2, axis=1) > 1.3, :] = np.nan
        noise[s] = n2
        uw[s] = sm_grad[s] + n2
        spread[s] = (ifreq[e2[s]] - ifreq[e1[s]] + jfreq[e2[s]] - jfreq[e1[s]]).astype(np.float32)
    return SpaceTime(dph_space_uw=uw, dph_noise=noise, G=G, spread=spread, ifreq_ij=ifreq, jfreq_ij=jfreq,
                     shaky_ix=shaky, K=K, coh=coh)
