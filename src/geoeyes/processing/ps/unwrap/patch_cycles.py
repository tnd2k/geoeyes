"""Whole-cycle patches of single interferograms after the grid unwrapping (``[ps] unwrap_patch_cycles``).

On some dates the grid unwrapping puts a large region (rounded "oval" patches with sharp edges, often bounded by
fields, water or PS-poor ground) a whole cycle off the rest of the scene: its PS all sit 2π·k (k × λ/2 of LOS,
27.7 mm on S1) away from their own time series there and nowhere else (HCMC hcm_d18, 2026-11-08: up to 49 % of the PS
on 2024-02-28, 3.9 % of all PS-epochs, about 28 % of the PS with >= 5 such epochs; the velocity of fast PS pushed
~9 mm/yr past SARPROZ).

Each PS has a smooth model in time (offset, rate, annual sine/cosine, look-angle error × B⊥) fitted robustly
(Huber), so the patch epochs barely pull it, and every epoch a constant (the IRLS result of an interferogram
carries an arbitrary one until the reference step: residuals of ~2 rad on hcm_d18, which hid every patch), the
mode of the residuals of all PS, fitted alternately with the models. Per epoch:

1. every PS proposes k = round(residual / 2π) when its residual is within ``tol`` of that multiple;
2. every grid cell takes the k of a clear majority (>= ``vote``) of its PS, else 0;
3. cells of the same k ≠ 0 are joined into patches (empty cells within ``gap_cells`` take their nearest occupied
   cell); a patch counts only with >= ``min_ps`` PS whose median distance to 2π·k is within ``tol``/2;
4. every PS of a counted patch is moved by -2π·k (the patch moved together in the grid, so its noisy PS too).

Two passes (the model is refitted on the corrected phase). A PS that is off alone is left alone: that is noise,
not a patch. Real motion does not make a patch: it is not a whole multiple of 2π over a large area at one date
and back at the next.
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

TWO_PI = 2 * np.pi


def robust_fit(ph: np.ndarray, t: np.ndarray, bp: np.ndarray | None, delta: float = 1.0, iters: int = 4,
               chunk: int = 50_000) -> np.ndarray:
    """(n, m) smooth model of ``ph`` (n, m) in time ``t`` (m,) years: offset, rate, annual sine / cosine and, with
    ``bp`` (n or 1, m), a look-angle term, by Huber IRLS (``delta`` rad)."""
    n, m = ph.shape
    base = np.c_[np.ones(m), t, np.sin(TWO_PI * t), np.cos(TWO_PI * t)]
    out = np.empty((n, m), np.float64)
    for s in range(0, n, chunk):
        y = ph[s:s + chunk].astype(np.float64)
        k = y.shape[0]
        if bp is not None:
            b = np.broadcast_to(np.asarray(bp, np.float64)[s:s + chunk] if np.shape(bp)[0] == n
                                else np.asarray(bp, np.float64), (k, m))
            b = b / max(float(np.abs(b).max()), 1e-9)
            X = np.concatenate([np.broadcast_to(base, (k, m, base.shape[1])), b[..., None]], axis=2)
        else:
            X = np.broadcast_to(base, (k, m, base.shape[1]))
        w = np.ones((k, m))
        p = X.shape[2]
        for _ in range(iters):
            G = np.einsum("ne,nep,neq->npq", w, X, X) + 1e-6 * np.eye(p)
            r = np.einsum("ne,nep,ne->np", w, X, y)
            c = np.linalg.solve(G, r[..., None])[..., 0]
            fit = np.einsum("nep,np->ne", X, c)
            w = np.minimum(1.0, delta / np.maximum(np.abs(y - fit), 1e-9))
        out[s:s + chunk] = fit
    return out


def epoch_offsets(R: np.ndarray, bin_w: float = 0.1, smooth: int = 3) -> np.ndarray:
    """(m,) constant of every epoch: the mode of the residuals ``R`` (n, m) of all PS (histogram peak), so the
    majority of the scene defines 0 (the IRLS result of an interferogram carries an arbitrary constant until the
    reference step; a median would fall between two halves a cycle apart)."""
    from scipy.ndimage import uniform_filter1d
    out = np.zeros(R.shape[1])
    edges = np.arange(-4 * np.pi, 4 * np.pi + bin_w, bin_w)
    for e in range(R.shape[1]):
        r = R[:, e]
        r = r[np.isfinite(r)]
        if r.size == 0:
            continue
        c0 = float(np.median(r))
        h, _ = np.histogram(r - c0, bins=edges)
        h = uniform_filter1d(h.astype(np.float64), smooth)
        out[e] = c0 + edges[int(np.argmax(h))] + bin_w / 2
    return out


def _cell_votes(kp: np.ndarray, ok: np.ndarray, cell: np.ndarray, n_cells: int, vote: float) -> np.ndarray:
    """k of every cell for one epoch: the k of >= ``vote`` of its PS (ok ones), else 0."""
    out = np.zeros(n_cells, np.int8)
    total = np.bincount(cell, minlength=n_cells)
    for k in np.unique(kp[ok & (kp != 0)]):
        sel = ok & (kp == k)
        cnt = np.bincount(cell[sel], minlength=n_cells)
        out[(cnt >= vote * np.maximum(total, 1)) & (cnt > 0)] = k
    return out


def fix_patch_cycles(ph: np.ndarray, t: np.ndarray, cell_ij: np.ndarray, shape: tuple[int, int],
                     bp: np.ndarray | None = None, *, tol: float = 0.25 * TWO_PI, vote: float = 0.6,
                     min_ps: int = 50, gap_cells: int = 3, passes: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """``ph`` (n, m) unwrapped phase of the PS (rad; master column excluded), ``t`` (m,) years, ``cell_ij`` (n, 2)
    0-based grid cell of every PS on a grid of ``shape``. Returns (corrected phase, k (n, m) int8 cycles removed)."""
    from scipy import ndimage
    n, m = ph.shape
    ph = np.asarray(ph, np.float64).copy()
    K = np.zeros((n, m), np.int8)
    if n == 0 or m < 8:
        return ph, K
    n_i, n_j = shape
    cell = (cell_ij[:, 0] * n_j + cell_ij[:, 1]).astype(np.int64)
    occupied = np.zeros(n_i * n_j, bool)
    occupied[cell] = True
    occ = occupied.reshape(n_i, n_j)
    dist, (ii, jj) = ndimage.distance_transform_edt(~occ, return_indices=True)
    near = dist <= gap_cells
    c = np.zeros(m)
    for _ in range(passes):
        for _ in range(2):                                   # the PS models and the epoch constants, alternately
            fit = robust_fit(ph - c[None, :], t, bp)
            c = epoch_offsets(ph - fit)
        R = ph - fit - c[None, :]
        kp = np.rint(R / TWO_PI)
        ok = np.abs(R - TWO_PI * kp) < tol
        kp = np.clip(kp, -127, 127).astype(np.int8)
        moved = 0
        for e in range(m):
            ck = _cell_votes(kp[:, e], ok[:, e], cell, n_i * n_j, vote).reshape(n_i, n_j)
            if not ck.any():
                continue
            filled = np.where(near, ck[ii, jj], 0)          # empty cells take their nearest occupied cell's k
            for k in np.unique(ck[ck != 0]):
                lab, nl = ndimage.label(filled == k, structure=np.ones((3, 3)))
                if nl == 0:
                    continue
                ps_lab = lab.ravel()[cell]
                cnt = np.bincount(ps_lab, minlength=nl + 1)
                for L in np.flatnonzero(cnt[1:] >= min_ps) + 1:
                    sel = ps_lab == L
                    if np.median(np.abs(R[sel, e] - TWO_PI * k)) > tol / 2:
                        continue
                    ph[sel, e] -= TWO_PI * k
                    K[sel, e] += k
                    moved += int(sel.sum())
        if moved == 0:
            break
    share = (K != 0).mean(axis=0)
    worst = np.argsort(share)[::-1][:5]
    log.info("patch cycles: %.2f %% of the PS-epochs moved by whole cycles (%d epochs touched); worst epochs %s",
             100 * (K != 0).mean(), int((share > 0).sum()),
             ", ".join(f"#{e + 1} {100 * share[e]:.0f} %" for e in worst if share[e] > 0) or "none")
    return ph, K
