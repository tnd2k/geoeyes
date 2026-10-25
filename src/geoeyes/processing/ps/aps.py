"""Atmospheric phase screen estimates from unwrapped phase."""
from __future__ import annotations

import numpy as np


def _detrend_parts(a: np.ndarray, t: np.ndarray, bperp: np.ndarray):
    """Per point, the residual of ``a`` (n, n_sec) about its least-squares c + v·t + K·B⊥ (B⊥ (n, n_sec) of the
    point itself), and the diagonal (n, n_sec) of that fit's hat matrix."""
    g = np.stack([np.ones_like(bperp), np.broadcast_to(t, bperp.shape), bperp], axis=2)       # (n, n_sec, 3)
    inv = np.linalg.pinv(np.einsum("nip,niq->npq", g, g))
    r = a - (g @ (inv @ np.einsum("nip,ni->np", g, a)[..., None]))[..., 0]
    h = np.einsum("nip,npq,niq->ni", g, inv, g)
    return r, h


def choose_aps(ph_uw: np.ndarray, weather: np.ndarray, linear: np.ndarray, t_days: np.ndarray,
               bperp_mat: np.ndarray, master_ix: int, sample: int = 200_000, seed: int = 0):
    """Per interferogram, the APS (weather model or linear) that leaves the smaller residual phase variance.

    The pass-1 unwrapped phase minus a linear motion and a look-angle error per PS is mostly atmosphere and
    noise; removing a correct APS reduces its variance. Each interferogram is judged on its own, the others
    keeping the linear APS: switching interferogram k from the linear APS l_k to the weather APS w_k changes
    its residual by -(1 - h_kk)·(w_k - l_k) (h the per-PS hat matrix), so a wrong model on one date does not
    leak into the decision for another. ``ph_uw``/``bperp_mat`` (n, n_sec), APS (n, n_sec + 1) with the master
    column. Returns (combined APS (n, n_sec + 1), use_weather (n_sec,) bool, variances (3, n_sec): residual
    without APS, with the weather APS, with the linear APS)."""
    sec = np.arange(weather.shape[1]) != master_ix
    w, lin = weather[:, sec], linear[:, sec]
    ok = np.all(np.isfinite(ph_uw), axis=1) & np.all(np.isfinite(w), axis=1) & np.all(np.isfinite(lin), axis=1)
    rows = np.flatnonzero(ok)
    if rows.size > sample:
        rows = np.random.default_rng(seed).choice(rows, sample, replace=False)
    t = np.asarray(t_days, np.float64) / 365.25
    b = np.asarray(bperp_mat, np.float64)[rows]
    p, wl, ll = (np.asarray(a, np.float64)[rows] for a in (ph_uw, w, lin))
    centred_var = (lambda r: (r - r.mean(axis=0)).var(axis=0))  # noqa: E731
    r_none, h = _detrend_parts(p, t, b)
    use = np.zeros(p.shape[1], bool)
    for _ in range(5):                          # coordinate descent: the other dates at the current choice
        base = np.where(use, wl, ll)
        r_b = _detrend_parts(p - base, t, b)[0]
        v_w = centred_var(r_b - (1.0 - h) * (wl - base))
        v_l = centred_var(r_b - (1.0 - h) * (ll - base))
        new = v_w < v_l
        if np.array_equal(new, use):
            break
        use = new
    var = np.stack([centred_var(r_none), v_w, v_l])
    cols = np.flatnonzero(sec)[use]
    out = linear.copy()
    out[:, cols] = np.where(np.isfinite(weather[:, cols]), weather[:, cols], linear[:, cols])
    return out, use, var


def centre_weather(ph_uw: np.ndarray, weather: np.ndarray, master_ix: int,
                   fit_mask: np.ndarray | None = None) -> np.ndarray:
    """Weather-model APS plus, per interferogram, the constant that makes the corrected phase zero-mean over the PS
    (over ``fit_mask`` when given), as the intercept b of the linear APS a·h + b does.

    The model gives an absolute delay difference and the unwrapped phase carries an arbitrary offset; neither is
    motion. Without this constant every interferogram corrected with the weather APS keeps a scene-wide offset of
    several mm, which shifts the time series of all points on those dates and biases every velocity (the scene
    mean is the reference). ``ph_uw`` (n, n_sec), ``weather`` (n, n_sec + 1) with the master column."""
    w = np.asarray(weather, np.float64).copy()
    sec = np.flatnonzero(np.arange(w.shape[1]) != master_ix)
    mask = np.ones(w.shape[0], bool) if fit_mask is None else np.asarray(fit_mask, bool)
    for k, col in enumerate(sec):
        ok = mask & np.isfinite(ph_uw[:, k]) & np.isfinite(w[:, col])
        if ok.any():
            w[:, col] += float(np.mean(ph_uw[ok, k] - w[ok, col]))
    return w


def inside_polygon(lonlat: np.ndarray, polygon) -> np.ndarray:
    """(n,) bool: points of ``lonlat`` (n, 2) inside the lon/lat ``polygon`` (m, 2)."""
    from matplotlib.path import Path
    return Path(np.asarray(polygon, np.float64)).contains_points(np.asarray(lonlat, np.float64))


def linear_aps(ph_uw: np.ndarray, hgt: np.ndarray, master_ix: int, weights: np.ndarray | None = None,
               fit_mask: np.ndarray | None = None) -> np.ndarray:
    """Topography-correlated APS (legacy ``_aps_linear``, ``a_l``): per interferogram a weighted least-squares
    line phase = a·h + b over the PS, evaluated at every PS (NaN where the phase is NaN). ``ph_uw`` (n, n_sec);
    returns (n, n_sec + 1) with a zero master column inserted at ``master_ix``. ``fit_mask``: only these PS
    enter the fit (StaMPS ``non_defo_flag``: a non-deforming area)."""
    n, n_dates = ph_uw.shape
    h = np.asarray(hgt, np.float64).reshape(-1)
    w = np.ones(n) if weights is None else np.asarray(weights, np.float64).reshape(-1)
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if fit_mask is not None:
        w = np.where(np.asarray(fit_mask, bool), w, 0.0)
    design = np.column_stack([h, np.ones_like(h)])
    out = np.zeros((n, n_dates))
    for k in range(n_dates):
        v = np.flatnonzero(~np.isnan(ph_uw[:, k]) & (w > 0))
        ws = np.sqrt(w[v])
        a, b = design[v] * ws[:, None], ph_uw[v, k] * ws
        ok = np.isfinite(a).all(axis=1) & np.isfinite(b)
        try:
            coeff = np.linalg.lstsq(a[ok], b[ok], rcond=None)[0]
        except np.linalg.LinAlgError:
            coeff = np.zeros(2)
        out[:, k] = design @ coeff
        out[np.isnan(ph_uw[:, k]), k] = np.nan
    return np.hstack([out[:, :master_ix], np.zeros((n, 1)), out[:, master_ix:]])
