# Ported from modules/ps_stack/invert.py (algorithm unchanged; ADR-020).
"""Per-PS inversion of a single-master stack: LOS velocity, height error, master term.

Phase convention: after the reference phase (flat earth + DEM topography) is removed with the
product's sign s (see modules.utils.flat_earth.detect_sign), a range increase d (away from the
satellite) between master and slave adds  s * 4 pi / lambda * d,  and a height error dh adds
s * kh * dh, with kh = d(-4 pi / lambda (R1 - R2)) / dh from the orbits. Per PS and pair k:

    phi_k = s * 4 pi / lambda * v * t_k  +  s * kh_k * dh  +  c  +  APS_k          (t_k in years)

c absorbs the master's own atmosphere (common to every pair of a single-master stack). APS_k, the
slave's atmosphere, is spatially smooth and uncorrelated in time: it is estimated by spatially
low-pass filtering the residual of each pair (``aps_fn``), removed, and the fit repeated (StaMPS
step 8 idea). This cleans the time series and the misfit; the part of the APS that happens to
project onto the linear trend stays in the velocity (it only averages out with more dates).
Spatially smooth non-linear motion is removed together with the APS. Velocities are reported toward
the satellite (positive = uplift / motion toward the sensor), in mm/yr.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree


@dataclass
class Inversion:
    v_mm_yr: np.ndarray          # (n,) LOS velocity toward the satellite
    v_std_mm_yr: np.ndarray
    dh_m: np.ndarray             # height error (true - DEM)
    c_rad: np.ndarray
    rmse_mm: np.ndarray          # (n,) misfit of the linear model after APS removal
    phase_std: np.ndarray        # (n,) standard deviation of that misfit, rad (GAMMA-style quality)
    disp_mm: np.ndarray          # (n, n_pair) LOS displacement toward the satellite; APS, height and master terms removed
    aps: np.ndarray              # (n, n_pair) estimated slave APS, rad
    phase: np.ndarray            # (n, n_pair) referenced unwrapped phase


def reference_phase(phase: np.ndarray, xy: np.ndarray, centre: np.ndarray, radius: float) -> tuple[np.ndarray, int]:
    """Per-pair reference: circular median of the PS within ``radius`` (same units as xy) of
    ``centre``, unwrapped so it stays consistent with the spatially unwrapped phase."""
    idx = cKDTree(xy).query_ball_point(centre, radius)
    if len(idx) < 5:
        _, idx = cKDTree(xy).query(centre, k=min(50, len(xy)))
        idx = np.atleast_1d(idx)
    sub = phase[idx]
    return np.median(sub, axis=0), len(idx)


def auto_reference(xy: np.ndarray, da: np.ndarray, radius: float) -> np.ndarray:
    """Centre of the densest, most stable PS cluster: lowest mean D_A among PS with enough
    neighbours within ``radius``."""
    tree = cKDTree(xy)
    sample = np.linspace(0, len(xy) - 1, min(len(xy), 5000)).astype(int)
    best, score = xy[sample[0]], np.inf
    counts = []
    for i in sample:
        nb = tree.query_ball_point(xy[i], radius)
        counts.append(len(nb))
    need = np.percentile(counts, 75)
    for i, cnt in zip(sample, counts, strict=True):
        if cnt < need:
            continue
        nb = tree.query_ball_point(xy[i], radius)
        s = float(np.mean(da[nb]))
        if s < score:
            best, score = xy[i], s
    return np.asarray(best, float)


def height_error_periodogram(resid: np.ndarray, kh: np.ndarray, sign: float, dh_max: float = 80.0,
                             step: float = 1.0, fine: float = 0.05, chunk: int = 10_000) -> tuple[np.ndarray, np.ndarray]:
    """Height error of each PS from its wrapped phase relative to the unwrapped grid
    (``resid`` (n, K) = wrap(phi - G)): dh maximising |mean_k exp(j(resid_k - s kh_k dh))|, searched
    on a ``step`` m grid within +-dh_max, then on a ``fine`` m grid within +-step of the best value.
    Works across pairs because kh_k follows Bperp_k; returns (dh, coherence at the peak)."""
    coarse = np.arange(-dh_max, dh_max + step / 2, step)
    local = np.arange(-step, step + fine / 2, fine)
    n = resid.shape[0]
    dh = np.empty(n, np.float32)
    gam = np.empty(n, np.float32)
    for i in range(0, n, chunk):
        sl = slice(i, min(i + chunk, n))
        e = np.exp(1j * resid[sl])[:, :, None]
        k = sign * kh[sl][:, :, None]
        P = np.abs((e * np.exp(-1j * k * coarse[None, None, :])).mean(axis=1))
        d0 = coarse[np.argmax(P, axis=1)]
        cand = d0[:, None] + local[None, :]                                   # (c, F)
        P = np.abs((e * np.exp(-1j * k * cand[:, None, :])).mean(axis=1))
        j = np.argmax(P, axis=1)
        r = np.arange(P.shape[0])
        dh[sl] = cand[r, j]
        gam[sl] = P[r, j]
    return dh, gam


def ifg_quality(resid: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Circular standard deviation (rad) of each interferogram's wrapped residual over the PS in
    ``mask``: ~0.5-1 rad for a usable interferogram, 1.81 rad for pure noise."""
    z = np.exp(1j * resid if mask is None else 1j * resid[mask])
    R = np.abs(z.mean(axis=0))
    return np.sqrt(-2 * np.log(np.clip(R, 1e-12, 1.0)))


def invert(phase: np.ndarray, t_yr: np.ndarray, kh: np.ndarray, wavelength: float, sign: float,
           aps_fn=None, aps_iters: int = 2, weights: np.ndarray | None = None) -> Inversion:
    """``phase`` (n, K) referenced unwrapped phase; ``kh`` (n, K) rad/m; ``t_yr`` (K,).
    ``aps_fn(residual (n, K)) -> (n, K)`` returns the spatially smooth part of a residual.
    ``weights`` (K,) per interferogram (0 = not used in the fit, e.g. 1/sigma_k^2)."""
    n, K = phase.shape
    ph = phase.astype(np.float64)
    wk = np.ones(K) if weights is None else np.asarray(weights, float)
    chunk = 200_000
    AtA_inv = np.empty((n, 3, 3))

    def design(sl):
        m = sl.stop - sl.start
        a_t = sign * 4 * np.pi / wavelength * np.broadcast_to(t_yr, (m, K))
        return np.stack([a_t, sign * kh[sl], np.ones((m, K))], axis=-1)    # (m, K, 3)

    for i in range(0, n, chunk):
        sl = slice(i, min(i + chunk, n))
        A = design(sl)
        AtA_inv[sl] = np.linalg.inv(np.einsum("nki,k,nkj->nij", A, wk, A) + 1e-9 * np.eye(3))

    def fit(y):
        x = np.empty((n, 3))
        r = np.empty_like(y)
        for i in range(0, n, chunk):
            sl = slice(i, min(i + chunk, n))
            A = design(sl)
            x[sl] = np.einsum("nij,nj->ni", AtA_inv[sl], np.einsum("nki,k,nk->ni", A, wk, y[sl]))
            r[sl] = y[sl] - np.einsum("nki,ni->nk", A, x[sl])
        return x, r

    aps = np.zeros_like(ph)
    x, res = fit(ph)
    for _ in range(aps_iters if aps_fn is not None else 0):
        aps = aps + aps_fn(res)
        x, res = fit(ph - aps)
    used = wk > 0
    dof = max(int(used.sum()) - 3, 1)
    wn = wk / wk[used].mean()                      # weights normalised to mean 1 over used ifgs
    sigma2 = np.sum(wn[used] * res[:, used] ** 2, axis=1) / dof
    v_std = np.sqrt(sigma2 * AtA_inv[:, 0, 0] * wk[used].mean())
    d_away = (ph - aps - sign * kh * x[:, 1:2] - x[:, 2:3]) * wavelength / (4 * np.pi * sign)
    return Inversion(
        v_mm_yr=(-x[:, 0] * 1000).astype(np.float32),
        v_std_mm_yr=(v_std * 1000).astype(np.float32),
        dh_m=x[:, 1].astype(np.float32),
        c_rad=x[:, 2].astype(np.float32),
        rmse_mm=(np.sqrt(sigma2) * wavelength / (4 * np.pi) * 1000).astype(np.float32),
        phase_std=np.std(res[:, used], axis=1).astype(np.float32),
        disp_mm=(-d_away * 1000).astype(np.float32),
        aps=aps.astype(np.float32),
        phase=ph.astype(np.float32),
    )


def invert_weighted(phase: np.ndarray, t_yr: np.ndarray, kh: np.ndarray, wavelength: float, sign: float,
                    aps_fn=None, std_max: float = 1.5, mask: np.ndarray | None = None, iters: int = 3):
    """Inversion with interferogram weights 1/sigma_k^2 from the circular std of each
    interferogram's wrapped residual (over ``mask``), interferograms above ``std_max`` dropped;
    re-estimated ``iters`` times so a bad interferogram does not spoil the others' residuals.
    Returns (Inversion, sigma_k, weights)."""
    w = None
    for _ in range(iters):
        r = invert(phase, t_yr, kh, wavelength, sign, aps_fn=aps_fn, weights=w)
        a_t = sign * 4 * np.pi / wavelength * (-r.v_mm_yr[:, None] / 1000) * t_yr[None, :]
        resid = phase - a_t - sign * kh * r.dh_m[:, None] - r.c_rad[:, None] - r.aps
        q = ifg_quality(resid, mask)
        w_new = np.where(q <= std_max, 1.0 / np.maximum(q, 0.1) ** 2, 0.0)
        if (w_new > 0).sum() < 4:                    # keep the best four rather than fail
            w_new = np.where(q <= np.sort(q)[3], 1.0 / np.maximum(q, 0.1) ** 2, 0.0)
        if w is not None and np.array_equal(w_new > 0, w > 0) and np.allclose(w_new, w, rtol=0.05):
            w = w_new
            break
        w = w_new
    r = invert(phase, t_yr, kh, wavelength, sign, aps_fn=aps_fn, weights=w)
    return r, q, w
