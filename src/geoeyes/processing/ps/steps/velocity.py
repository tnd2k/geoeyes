"""Step 7 (second part) — LOS velocity and time series (legacy ``_ps_plot_v_dao``, single-master, linear fit).

The unwrapped phase is corrected (SCLA, APS, ramp, master error C), turned into LOS displacement
d = -φ·λ/4π, and fitted per PS with d = v·t + c (t from the master, years); a quadratic fit gives the
acceleration and its variance. Per interferogram, the residual about the linear motion (plane removed) is
cleaned of its topography correlation and of the scene-scale low-pass (Gaussian, sigma = extent/2π); the
velocity of what remains is added to ``v`` (legacy "step7 HP" correction).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator, RegularGridInterpolator
from scipy.ndimage import gaussian_filter
from scipy.spatial import Delaunay, cKDTree

from geoeyes.processing.ps.steps.scla import SclaResult


@dataclass
class Velocity:
    v: np.ndarray              # (n,) mm/yr, high-pass corrected
    v_linear: np.ndarray       # (n,) mm/yr, plain linear fit
    acc: np.ndarray            # (n,) mm/yr²
    acc_var: np.ndarray        # (n,)
    rmse: np.ndarray           # (n,) mm of the quadratic fit
    ts_mm: np.ndarray          # (n, n_image) float32 LOS displacement per epoch (master 0)
    residual_mm: np.ndarray    # (n, n_sec) detrended, topography- and low-pass-cleaned residual
    t_days: np.ndarray         # (n_sec,) days from the master


def corrected_phase(ph_uw, scla: SclaResult, aps, master_ix, deramp: bool) -> np.ndarray:
    """φ - K·bperp - APS - ramp - C (each NaN treated as 0)."""
    ph = np.asarray(ph_uw, np.float64) - np.nan_to_num(scla.ph_scla)
    if aps is not None:
        ph = ph - np.nan_to_num(np.delete(np.nan_to_num(np.asarray(aps, np.float64), nan=0.0), master_ix, axis=1))
    if deramp and scla.ph_ramp.size:
        ph = ph - np.nan_to_num(scla.ph_ramp)
    return ph - np.nan_to_num(scla.C_uw)[:, None]


def highpass_gaussian(lon, lat, values, wavelength_m, grid_n=150):
    """Subtract a Gaussian low-pass (sigma = wavelength/2π) computed on a grid_n² lon/lat grid (linear
    interpolation, nearest valid point outside the hull) from every column of ``values``."""
    n, m = values.shape
    lon_ext = lon.max() - lon.min() + 1e-12
    lat_ext = lat.max() - lat.min() + 1e-12
    sigma = wavelength_m / (2.0 * np.pi)
    s_lat = sigma / 111320.0
    s_lon = sigma / (111320.0 * np.cos(np.radians(lat.mean())))
    glon_v, glat_v = np.linspace(lon.min(), lon.max(), grid_n), np.linspace(lat.min(), lat.max(), grid_n)
    glon, glat = np.meshgrid(glon_v, glat_v)
    q = np.column_stack([glon.ravel(), glat.ravel()])
    pts = np.column_stack([lon, lat])
    tri, tree, k = Delaunay(pts), cKDTree(pts), min(32, n)
    grid = np.empty((grid_n, grid_n, m))
    for i in range(m):
        v = values[:, i].copy()
        ok = np.isfinite(v)
        if ok.sum() < 4:
            grid[:, :, i] = 0.0
            continue
        g = LinearNDInterpolator(tri, v)(q)
        miss = ~np.isfinite(g)
        if miss.any():
            _, nn = tree.query(q[miss], k=k)
            nn = nn[:, None] if k == 1 else nn
            nv = v[nn]
            first = np.argmax(np.isfinite(nv), axis=1)
            rows = np.arange(nn.shape[0])
            fill = nv[rows, first]
            none = ~np.isfinite(nv)[rows, first]
            if none.any():
                fill[none] = NearestNDInterpolator(pts[ok], v[ok])(q[miss][none])
            g[miss] = fill
        grid[:, :, i] = g.reshape(grid_n, grid_n)
    low = gaussian_filter(grid, sigma=(s_lat / lat_ext * grid_n, s_lon / lon_ext * grid_n, 0))
    out = values.astype(np.float64).copy()
    pq = np.column_stack([lat, lon])
    for i in range(m):
        lp = RegularGridInterpolator((glat_v, glon_v), low[:, :, i], method="linear", bounds_error=False,
                                     fill_value=np.nan)(pq)
        ok = np.isfinite(lp)
        out[ok, i] -= lp[ok]
    return out


def velocity(*, ph_uw: np.ndarray, scla: SclaResult, aps: np.ndarray | None, ifgday: np.ndarray, day: np.ndarray,
             master_ix: int, xy: np.ndarray, lonlat: np.ndarray, hgt: np.ndarray | None, wavelength: float,
             deramp: bool = True, ifg_std_deg: np.ndarray | None = None, highpass: bool = True,
             legacy: bool = False, demean: bool = False) -> Velocity:
    """``ifgday`` (n_ifg, 2) with the master-master row, ``day`` (n_image,) ordinals. ``ifg_std_deg`` weights
    the fit (None = unweighted, as the legacy run, which never found its ``ifg_std`` file). ``legacy``: the
    legacy epoch shift of the time series after a dropped interferogram. ``demean``: reference every
    interferogram to the mean of all PS (the "scene mean" reference, StaMPS ``ref`` = all): the corrected phase
    can keep an offset where the pass-2 unwrapping differs from the pass-1 phase the APS was estimated on."""
    ph = corrected_phase(ph_uw, scla, aps, master_ix, deramp)
    if demean:
        ph = ph - np.nanmean(ph, axis=0, keepdims=True)
    n, n_sec = ph.shape
    rows = ifgday[ifgday[:, 0] != ifgday[:, 1]] if ifgday.shape[0] > n_sec else ifgday
    t_days = (rows[:n_sec, 1] - rows[:n_sec, 0]).astype(np.float64)
    if ifg_std_deg is None:
        w = np.eye(n_sec)
    else:
        std = np.delete(np.asarray(ifg_std_deg, np.float64).ravel(), master_ix)
        w = np.diag(1.0 / np.maximum(std * np.pi / 180.0, 1e-6) ** 2)
    t = t_days / 365.25
    lam = wavelength / (4.0 * np.pi) * 1000.0
    disp = -ph * lam

    keep = ~np.all(np.isnan(disp), axis=0)
    d, tk, wk = disp[:, keep], t[keep], w[np.ix_(keep, keep)]
    g = np.column_stack([tk, np.ones_like(tk)])
    v_lin = np.linalg.solve(g.T @ wk @ g, g.T @ wk @ d.T).T[:, 0]

    gq = np.column_stack((tk**2, tk, np.ones(tk.size)))
    try:
        inv_q = np.linalg.inv(gq.T @ wk @ gq)
    except np.linalg.LinAlgError:
        inv_q = np.linalg.pinv(gq.T @ wk @ gq)
    mq = (inv_q @ gq.T @ wk @ d.T).T
    res = d - (gq @ mq.T).T
    acc = 2.0 * mq[:, 0]
    acc_var = 4.0 * float(inv_q[0, 0]) * (res**2 * np.diag(wk)[None, :]).sum(axis=1) / max(1, d.shape[1] - 3)
    rmse = np.sqrt(np.mean(res**2, axis=1))
    bad = ~np.isfinite(v_lin)
    acc[bad] = acc_var[bad] = rmse[bad] = np.nan

    img = np.setdiff1d(np.arange(day.size), [master_ix])
    ts = np.zeros((n, day.size), np.float32)
    if legacy and img.size != d.shape[1]:
        # legacy: the NaN-dropped columns are written to the first epochs, shifting every epoch after a dropped
        # interferogram by one
        img = img[:d.shape[1]]
        ts[:, img] = d[:, :img.size].astype(np.float32)
    else:
        ts[:, img] = disp.astype(np.float32)          # a dropped interferogram stays NaN at its own epoch
    ts[:, master_ix] = 0

    resid = (disp - v_lin[:, None] * t[None, :])
    g_sp = np.column_stack((np.asarray(xy, np.float64)[:, 1:3] / 1000.0, np.ones(n)))
    for k in range(n_sec):
        ok = np.isfinite(resid[:, k])
        if int(ok.sum()) >= g_sp.shape[1] + 10:
            resid[:, k] = resid[:, k] - g_sp @ np.linalg.lstsq(g_sp[ok], resid[ok, k], rcond=None)[0]
    resid = resid.astype(np.float32)

    v = v_lin.copy()
    if highpass:
        lon, lat = np.asarray(lonlat[:, 0], np.float64), np.asarray(lonlat[:, 1], np.float64)
        wl = max((lat.max() - lat.min()) * 111_320.0,
                 (lon.max() - lon.min()) * 111_320.0 * np.cos(np.radians(lat.mean())))
        tc = resid.copy()
        if hgt is not None:
            h = np.asarray(hgt, np.float64).ravel()
            hf = np.isfinite(h)
            for k in range(n_sec):
                ok = hf & np.isfinite(resid[:, k])
                if ok.sum() < 10:
                    continue
                mh = np.linalg.lstsq(np.column_stack([h[ok], np.ones(ok.sum())]), resid[ok, k], rcond=None)[0]
                tc[hf, k] -= h[hf] * mh[0] + mh[1]
        resid = highpass_gaussian(lon, lat, tc, wl)
        tc_ = t - float(np.mean(t))
        okc = ~np.all(np.isnan(resid), axis=0)
        dv = np.linalg.lstsq(np.column_stack([tc_[okc], np.ones(okc.sum())]), resid[:, okc].T, rcond=None)[0][0, :]
        v = v + dv
    return Velocity(v=v, v_linear=v_lin, acc=acc, acc_var=acc_var, rmse=rmse, ts_mm=ts, residual_mm=resid,
                    t_days=t_days)
