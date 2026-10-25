"""Step 4 — weed PS (legacy ``_ps_weed``, single-master).

Optionally keeps only the best of adjacent pixels and drops zero-elevation pixels; always drops duplicate
positions (keeping the most coherent). Then, on the Delaunay network of the remaining PS, every arc's
phase (DEM error removed) is compared with its temporally smoothed version; a PS is kept if its least
noisy arc has standard deviation < ``weed_standard_dev`` and maximum |noise| < ``weed_max_noise``.
Forced (corner-reflector) points are always kept.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from geoeyes.processing.ps.geometry import triangulation_edges
from geoeyes.processing.ps.steps.select import Select

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeedParams:
    time_win: float = 730.0             # days, Gaussian width of the temporal smoothing
    weed_standard_dev: float = 1.0
    weed_max_noise: float = np.inf
    weed_zero_elevation: bool = False
    weed_neighbours: bool = False
    keep_per_group: int = 1             # adjacent-pixel groups: keep the N most coherent
    drop_ifg_index: tuple[int, ...] = ()  # 1-based epoch indices left out of the noise estimate
    edge_chunk: int | None = None
    ifg_chunk: int = 12
    noisy_check: bool = True            # False skips the arc-noise test (e.g. wetlands decorrelating everywhere)
    legacy: bool = False                # legacy leave-one-out mean and forced-point restore (parity)


@dataclass
class Weed:
    ix2: np.ndarray            # step-1 indices of the PS selected in step 3
    ix_weed: np.ndarray        # (len(ix2),) bool
    ix_pre: np.ndarray         # (len(ix2),) bool, left after adjacency/elevation/duplicate weeding
    ix_weed2: np.ndarray       # noise test over the ``ix_pre`` PS
    ps_std: np.ndarray
    ps_max: np.ndarray
    ifg_index: np.ndarray      # epochs used in the noise estimate
    ph_patch: np.ndarray       # step-2 patch phase of the kept PS
    ph_res: np.ndarray
    coh: np.ndarray
    K: np.ndarray
    C: np.ndarray

    @property
    def ix(self) -> np.ndarray:
        """Step-1 indices of the kept PS."""
        return self.ix2[self.ix_weed]


def _drop_adjacent(ij, coh, forced, keep_per_group):
    """Groups of 8-connected pixels: keep the ``keep_per_group`` most coherent (all forced points and no
    natural one when the group holds a forced point)."""
    keep = np.ones(ij.shape[0], bool)
    rc = ij[:, 1:3] - np.min(ij[:, 1:3], axis=0)
    lut = {(int(r), int(c)): k for k, (r, c) in enumerate(rc)}
    parent = np.arange(ij.shape[0])

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for k, (r, c) in enumerate(rc):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                j = lut.get((int(r) + dr, int(c) + dc))
                if j is not None and j != k:
                    parent[find(j)] = find(k)
    roots = np.array([find(k) for k in range(ij.shape[0])])
    for g in np.unique(roots):
        members = np.flatnonzero(roots == g)
        if members.size < 2:
            continue
        f = forced[members]
        if f.any():
            keep[members[~f]] = False
        else:
            order = np.lexsort((members, -coh[members]))
            keep[np.setdiff1d(members, members[order[:keep_per_group]])] = False
    return keep


def _drop_duplicates(xy, coh, forced, ix_weed):
    """Among PS sharing identical (x, y), keep the most coherent (lowest index on ties); forced points win."""
    num = np.flatnonzero(ix_weed)
    _, labels = np.unique(xy[num][:, 1:3], axis=0, return_inverse=True)
    labels = labels.reshape(-1)
    order = np.argsort(labels, kind="mergesort")
    lab = labels[order]
    starts = np.flatnonzero(np.r_[True, lab[1:] != lab[:-1]])
    ends = np.r_[starts[1:], lab.size]
    n_drop = 0
    for s, e in zip(starts, ends, strict=True):
        if e - s < 2:
            continue
        g = num[order[s:e]]
        f = forced[g]
        if f.any():
            fi = g[f]
            best = int(fi[np.lexsort((fi, -coh[fi]))[0]])
        else:
            gs = np.sort(g)
            best = int(gs[np.lexsort((gs, -coh[gs]))[0]])
        drop = g[g != best]
        ix_weed[drop] = False
        n_drop += drop.size
    if n_drop:
        log.info("%d PS with duplicate coordinates removed", n_drop)


def _arc_noise(dph: np.ndarray, days: np.ndarray, time_win: float, bperp: np.ndarray, edge_chunk, ifg_chunk,
               legacy: bool = False):
    """Per-arc std and max |noise|: arc phase minus its temporally smoothed version (Gaussian window in
    time plus a two-pass linear fit in time around each epoch, StaMPS ``ps_weed``), arc DEM error removed
    by weighted least squares."""
    n_edge, n_use = dph.shape
    dt = days[:, None] - days[None, :]
    w = np.exp(-(dt**2) / (2.0 * time_win**2)).astype(np.float32)
    w /= w.sum(axis=1, keepdims=True)
    g = np.concatenate([np.ones((n_use, n_use, 1)), dt[:, :, None]], axis=2)
    w_sqrt = np.sqrt(w)
    gw = g * w_sqrt[:, :, None]
    inv_gtg = np.linalg.inv(np.einsum("ijk,ijl->ikl", gw, gw))
    gw_t = gw.transpose(0, 2, 1)
    w_loo = w.copy()
    np.fill_diagonal(w_loo, 0.0)
    rs = w_loo.sum(axis=1, keepdims=True)
    nz = rs.reshape(-1) > 0
    w_loo[nz] /= rs[nz]
    w_loo[~nz] = w[~nz]

    chunk = max(1, min(n_edge, int(200_000_000 // max(1, n_use * n_use * 8))))
    if edge_chunk:
        chunk = max(1, min(chunk, int(edge_chunk)))
    smooth = np.zeros((n_edge, n_use), np.complex64)
    for e0 in range(0, n_edge, chunk):
        ds = dph[e0:e0 + chunk]
        dmean = ds @ w.T
        dma = np.angle(ds[:, None, :] * np.conj(dmean)[:, :, None])
        m = np.einsum("uij,uje->uie", inv_gtg,
                      np.einsum("uik,uke->uie", gw_t, dma.transpose(1, 2, 0) * w_sqrt[:, :, None]))
        dma2 = np.angle(np.exp(1j * (dma - np.transpose(np.einsum("uki,uie->uke", g, m), (2, 0, 1)))))
        m2 = np.einsum("uij,uje->uie", inv_gtg,
                       np.einsum("uik,uke->uie", gw_t, dma2.transpose(1, 2, 0) * w_sqrt[:, :, None]))
        smooth[e0:e0 + chunk] = dmean * np.exp(1j * (m[:, 0, :] + m2[:, 0, :]).T)

    noise = np.empty((n_edge, n_use), np.float32)
    s2 = np.zeros(n_use)
    ss2 = np.zeros(n_use)
    ifg_chunk = max(1, min(n_use, ifg_chunk))
    for cs in range(0, n_use, ifg_chunk):
        ce = min(cs + ifg_chunk, n_use)
        sp_ = dph[:, cs:ce].astype(np.complex64, copy=False)
        noise[:, cs:ce] = np.angle(sp_ * np.conj(smooth[:, cs:ce])).astype(np.float32, copy=False)
        # leave-one-out mean of epoch j: Σ_k W_loo[j, k]·dph[:, k]; legacy used the columns W_loo[:, j]
        loo = dph @ (w_loo[:, cs:ce] if legacy else w_loo[cs:ce].T)
        n2 = np.angle(sp_ * np.conj(loo.astype(np.complex64, copy=False))).astype(np.float32)
        n2 = np.nan_to_num(n2, nan=0.0)
        s2[cs:ce] += n2.sum(axis=0, dtype=np.float64)
        ss2[cs:ce] += np.square(n2, dtype=np.float32).sum(axis=0, dtype=np.float64)
    mean2 = s2 / max(float(n_edge), 1.0)
    var = ss2 / max(float(n_edge), 1.0) - np.square(mean2)
    var[var == 0] = 1e-6
    wd = np.diag(1.0 / var)
    gk = bperp[:, None]
    k = np.linalg.solve(gk.T @ wd @ gk, gk.T @ wd @ noise.T).T
    noise = noise - (k @ bperp[None, :]).astype(np.float32, copy=False)
    return np.std(noise, axis=1, ddof=0), np.amax(np.abs(noise), axis=1)


def weed(*, ph: np.ndarray, bperp: np.ndarray, day: np.ndarray, master_ix: int, xy: np.ndarray, ij: np.ndarray,
         forced: np.ndarray, hgt: np.ndarray | None, ph_patch: np.ndarray, sel: Select, params: WeedParams) -> Weed:
    """Arrays are the step-1 candidate arrays (``ph``/``bperp``/``day`` with the master column);
    ``ph_patch`` is the step-2 patch phase (the PS left in, as StaMPS)."""
    p = params
    ix2 = sel.ix[sel.keep_ix]
    K2, C2, coh2 = sel.K2[sel.keep_ix], sel.C2[sel.keep_ix], sel.coh2[sel.keep_ix]
    xy2, ij2, ph2, f2 = xy[ix2], ij[ix2], ph[ix2], forced[ix2]
    n_ps = ix2.size
    drop = {d - 1 for d in p.drop_ifg_index}
    ifg_index = np.array([k for k in range(len(day)) if k not in drop], dtype=int)
    ix_weed = np.ones(n_ps, bool)
    ix_pre = ix_weed.copy()
    ix_weed2 = np.ones(0, bool)
    ps_std = ps_max = np.zeros(0)

    if n_ps >= 4:
        if p.weed_neighbours:
            ix_weed &= _drop_adjacent(ij2, coh2, f2, max(1, p.keep_per_group))
            log.info("%d PS kept after dropping adjacent pixels", int(ix_weed.sum()))
        if p.weed_zero_elevation and hgt is not None:
            ix_weed &= ~((np.asarray(hgt).reshape(-1)[ix2] < 1e-6) & ~f2)
        _drop_duplicates(xy2, coh2, f2, ix_weed)

        ix_pre = ix_weed.copy()
        n_w = int(ix_weed.sum())
        ix_weed2 = np.ones(n_w, bool)
        ps_std = ps_max = np.zeros(n_w)
        noisy = p.noisy_check and not (p.weed_standard_dev >= np.pi and p.weed_max_noise >= np.pi)
        if n_w and noisy:
            edges = triangulation_edges(xy2[ix_weed][:, 1:3])
            phw = ph2[ix_weed] * np.exp(-1j * (K2[ix_weed].reshape(-1, 1) @ np.asarray(bperp).reshape(1, -1)))
            phw /= np.abs(phw)
            phw[:, master_ix] = np.exp(1j * C2[ix_weed])
            dph = (phw[edges[:, 1]] * np.conj(phw[edges[:, 0]]))[:, ifg_index].astype(np.complex64)
            edge_std, edge_max = _arc_noise(dph, np.asarray(day, np.float64)[ifg_index], p.time_win,
                                            np.asarray(bperp)[ifg_index], p.edge_chunk, p.ifg_chunk, p.legacy)
            ps_std = np.full(n_w, np.inf, np.float32)
            ps_max = np.full(n_w, np.inf, np.float32)
            for col in (0, 1):
                np.minimum.at(ps_std, edges[:, col], edge_std.astype(np.float32))
                np.minimum.at(ps_max, edges[:, col], edge_max.astype(np.float32))
            ix_weed2 = (ps_std < p.weed_standard_dev) & (ps_max < p.weed_max_noise) | f2[ix_weed]
            ix_weed[ix_weed] = ix_weed2
            if p.legacy:
                ix_weed |= f2                   # legacy: also the forced points weeded as duplicates
            log.info("%d PS kept after dropping noisy pixels", int(ix_weed.sum()))

    keep = ix_weed
    return Weed(ix2=ix2, ix_weed=ix_weed, ix_pre=ix_pre, ix_weed2=ix_weed2, ps_std=ps_std, ps_max=ps_max,
                ifg_index=ifg_index, ph_patch=ph_patch[ix2][keep], ph_res=sel.ph_res2[sel.keep_ix][keep],
                coh=coh2[keep], K=K2[keep], C=C2[keep])
