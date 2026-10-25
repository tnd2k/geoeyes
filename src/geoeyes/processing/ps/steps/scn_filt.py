"""Step 8 — spatially-correlated noise (SCN) estimate (legacy ``_ps_scn_filt``, single-master).

Phase differences along the Delaunay arcs (SCLA, C and ramp removed) are high-pass filtered in time
(Gaussian window ``time_win`` days); the high-pass arc network is integrated back to the PS by weighted least
squares (first PS fixed) and low-pass filtered in space with a Gaussian of width ``wavelength`` (pairs within
4·wavelength). The result is referenced to the first PS.

The temporal low-pass (``time_fit``) is either the Gaussian-weighted mean of StaMPS ``ps_scn_filt`` (``mean``,
the legacy and parity behaviour) or a Gaussian-weighted local linear fit (``linear``, the GeoEyes default). A
weighted mean is biased wherever the series has a trend that the window does not cover symmetrically: at both
ends of every series, and everywhere when the series is shorter than the window (a 6-month Sentinel-1 stack with
the 365-day window). The trend then passes into the "noise" and the SCN-removed series loses the deformation.
The local linear fit keeps a linear trend in the low-pass whatever the window (local polynomial regression,
Cleveland 1979; Fan 1992).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

from geoeyes.processing.ps.geometry import triangulation_edges


@dataclass
class Scn:
    ph_scn: np.ndarray        # (n, n_sec) spatially correlated noise, referenced to PS 0
    ph_hpt: np.ndarray        # (n, n_sec) float32 temporally high-passed phase


def scn_filt(*, ph_uw: np.ndarray, ph_scla: np.ndarray, C_uw: np.ndarray, ph_ramp: np.ndarray, day: np.ndarray,
             master_ix: int, xy: np.ndarray, filter_xy: np.ndarray | None = None, time_win: float = 365.0,
             wavelength: float = 100.0, weights: np.ndarray | None = None, method: str = "grid",
             cell: float | None = None, time_fit: str = "mean") -> Scn:
    """``ph_uw`` (n, n_sec) step-6 output, ``ph_scla``/``ph_ramp`` (n, n_sec) step-7 SCLA, ``day`` (n_image,)
    ordinals, ``xy`` (n, 3) [id, x, y] for the arc network; ``filter_xy`` (n, 2) coordinates of the spatial
    filter (default x, y). ``method``: ``grid`` = normalised Gaussian convolution on a grid of ``cell`` m
    (default wavelength/5; O(n)), ``exact`` = the legacy all-pairs sum within 4·wavelength (only feasible for
    sparse points)."""
    n, n_sec = ph_uw.shape
    sec = np.setdiff1d(np.arange(day.size), [master_ix])
    d = np.asarray(day, np.float64)[sec][:n_sec]
    ph = ph_uw.astype(np.float32) - ph_scla.astype(np.float32)
    ph = ph - np.tile(np.asarray(C_uw, np.float32), (n_sec, 1)).T
    if ph_ramp.size and ph_ramp.shape[1] > 0:
        ph = ph - ph_ramp.astype(np.float32)
    ph[np.isnan(ph)] = 0

    e = triangulation_edges(np.asarray(xy)[:, 1:3])
    dph = ph[e[:, 1]] - ph[e[:, 0]]
    dph_hpt = dph - dph @ time_lowpass(d, float(time_win), time_fit).T

    w = np.ones(n) if weights is None else np.asarray(weights, np.float64).ravel()
    sw = np.sqrt(np.sqrt(w[e[:, 0]] * w[e[:, 1]]))
    m = e.shape[0]
    a = sparse.csr_matrix((np.concatenate([-sw, sw]), (np.concatenate([np.arange(m), np.arange(m)]),
                                                       np.concatenate([e[:, 0], e[:, 1]]))), shape=(m, n))[:, 1:]
    hpt = splu((a.T @ a).tocsc()).solve(np.asarray(a.T @ (dph_hpt * sw[:, None]), np.float64))
    hpt = np.vstack((np.zeros((1, n_sec)), hpt)).astype(np.float32)

    fxy = np.asarray(xy, np.float64)[:, 1:3] if filter_xy is None else np.asarray(filter_xy, np.float64)
    if method == "grid":
        scn = _gaussian_grid(fxy, hpt, float(wavelength), cell)
        return Scn(ph_scn=(scn - scn[0, :]).astype(np.float64), ph_hpt=hpt)
    pairs = cKDTree(fxy).query_pairs(float(wavelength) * 4.0, output_type="ndarray")
    src = np.concatenate([pairs[:, 0], pairs[:, 1], np.arange(n)])
    dst = np.concatenate([pairs[:, 1], pairs[:, 0], np.arange(n)])
    d2 = np.sum((fxy[pairs[:, 0]] - fxy[pairs[:, 1]]) ** 2, axis=1)
    w_raw = np.exp(-np.concatenate([d2, d2, np.zeros(n)]) / (2.0 * float(wavelength) ** 2)).astype(np.float32)
    s = np.bincount(src, weights=w_raw.astype(np.float64), minlength=n).astype(np.float32)
    s[s == 0.0] = 1.0
    wmat = sparse.csr_matrix(((w_raw / s[src]).astype(np.float32), (src, dst)), shape=(n, n), dtype=np.float32)
    scn = wmat @ hpt
    return Scn(ph_scn=(scn - scn[0, :]).astype(np.float64), ph_hpt=hpt)


def time_lowpass(d: np.ndarray, time_win: float, fit: str = "mean") -> np.ndarray:
    """Smoother matrix L (T, T): the low-passed series at date i is Σ_j L[i, j]·x_j. ``mean``: Gaussian-weighted
    mean (StaMPS); ``linear``: the intercept at date i of a Gaussian-weighted linear fit, which reproduces any
    linear trend exactly. Dates where the local fit is degenerate (fewer than two distinct weighted dates) fall
    back to the mean."""
    if fit not in ("mean", "linear"):
        raise ValueError(f"scn time fit: mean | linear, not {fit!r}")
    d = np.asarray(d, np.float64)
    x = d[None, :] - d[:, None]                                       # (i, j): date j relative to date i
    w = np.exp(-(x ** 2) / (2.0 * time_win ** 2))
    s0 = w.sum(axis=1, keepdims=True)
    s0[s0 == 0.0] = 1.0
    mean = w / s0
    if fit == "mean":
        return mean
    s1 = (w * x).sum(axis=1, keepdims=True)
    s2 = (w * x * x).sum(axis=1, keepdims=True)
    det = s0 * s2 - s1 ** 2
    ok = det > 1e-9 * np.maximum(s0 * s2, 1e-300)
    lin = w * (s2 - s1 * x) / np.where(ok, det, 1.0)
    return np.where(ok, lin, mean)


def _gaussian_grid(xy: np.ndarray, values: np.ndarray, wavelength: float, cell: float | None) -> np.ndarray:
    """Σ_j w_ij v_j / Σ_j w_ij with w = exp(-d²/2λ²), d < 4λ, binned on a grid (cell ≤ λ/5)."""
    cell = float(cell or wavelength / 5.0)
    ij = np.floor((xy - xy.min(axis=0)) / cell).astype(int)
    shape = tuple(ij.max(axis=0) + 1)
    flat = np.ravel_multi_index((ij[:, 0], ij[:, 1]), shape)
    cnt = np.bincount(flat, minlength=shape[0] * shape[1]).reshape(shape).astype(np.float64)
    sigma = wavelength / cell
    den = ndimage.gaussian_filter(cnt, sigma, mode="constant", truncate=4.0)[ij[:, 0], ij[:, 1]]
    out = np.empty(values.shape, np.float32)
    for k in range(values.shape[1]):
        s = np.bincount(flat, weights=values[:, k].astype(np.float64), minlength=cnt.size).reshape(shape)
        num = ndimage.gaussian_filter(s, sigma, mode="constant", truncate=4.0)[ij[:, 0], ij[:, 1]]
        out[:, k] = num / np.maximum(den, 1e-12)
    return out
