"""Radar <-> ground geometry for zero-Doppler SAR (range-Doppler equations).

``rdr2geo``: for radar coordinates (azimuth time t, slant range R) find the ground point X on the
DEM with |X - S(t)| = R and (X - S(t)) · V(t) = 0. Solved by Newton iteration on (lat, lon) with the
height taken from the DEM at the current estimate; the initial guess comes from the product's
geolocation grid, so 3-6 iterations reach millimetre level.

``geo2rdr``: for ground points X and another acquisition's orbit, the zero-Doppler time and slant
range — i.e. where X sits in that acquisition's radar geometry.
"""
from __future__ import annotations

import logging

import numpy as np

from geoeyes.core.errors import DataError
from geoeyes.core.geodesy import ecef_to_llh, llh_to_ecef
from geoeyes.geometry.dem import Dem
from geoeyes.geometry.orbit import StateVectors

log = logging.getLogger(__name__)


def _solve_llh_fixed_h(sat, vel, rng, lat, lon, h, iters: int = 4):
    """Newton on (lat, lon) for the range sphere ∩ zero-Doppler plane at fixed ellipsoidal height."""
    d = 1e-6                                           # degrees for the numerical Jacobian
    vn = vel / np.linalg.norm(vel, axis=1, keepdims=True)

    def residual(la, lo):
        x = llh_to_ecef(la, lo, h)
        dx = x - sat
        return np.linalg.norm(dx, axis=1) - rng, np.einsum("ij,ij->i", dx, vn), x

    for _ in range(iters):
        f1, f2, _ = residual(lat, lon)
        a1, a2, _ = residual(lat + d, lon)
        b1, b2, _ = residual(lat, lon + d)
        j11, j12, j21, j22 = (a1 - f1) / d, (b1 - f1) / d, (a2 - f2) / d, (b2 - f2) / d
        det = j11 * j22 - j12 * j21
        det = np.where(np.abs(det) < 1e-12, 1e-12, det)
        lat = lat - (j22 * f1 - j12 * f2) / det
        lon = lon - (-j21 * f1 + j11 * f2) / det
    f1, f2, x = residual(lat, lon)
    return lat, lon, x, f1, f2


def rdr2geo(orbit: StateVectors, t: np.ndarray, rng: np.ndarray, dem: Dem, lat0: np.ndarray, lon0: np.ndarray,
            *, max_iter: int = 40, tol_h: float = 0.05) -> dict[str, np.ndarray]:
    """Ground points for radar coordinates. ``t`` orbit seconds, ``rng`` slant range (m), any shape.

    Outer loop on the height with relaxation: on slopes facing the radar, plain fixed-point
    iteration h <- DEM(p(h)) oscillates (the ground point moves along the range sphere faster than
    the DEM height changes); damping the update makes it contract. Returns lat, lon, h (ellipsoidal),
    xyz (ECEF), a converged mask and the final DEM-height mismatch.
    """
    shape = np.shape(t)
    t = np.ravel(t).astype(np.float64)
    rng = np.ravel(rng).astype(np.float64)
    lat = np.ravel(lat0).astype(np.float64).copy()
    lon = np.ravel(lon0).astype(np.float64).copy()
    sat, vel = orbit.interpolate(t)
    h = np.nan_to_num(dem.ellipsoidal(lat, lon), nan=0.0)
    relax = np.ones_like(h)
    prev_dh = np.zeros_like(h)
    active = np.ones(h.shape, bool)
    for _it in range(max_iter):
        idx = np.flatnonzero(active)
        if not idx.size:
            break
        la, lo, _, _, _ = _solve_llh_fixed_h(sat[idx], vel[idx], rng[idx], lat[idx], lon[idx], h[idx])
        lat[idx], lon[idx] = la, lo
        h_dem = np.nan_to_num(dem.ellipsoidal(la, lo), nan=h[idx])
        dh = h_dem - h[idx]
        flip = np.sign(dh) != np.sign(prev_dh[idx])          # oscillating -> damp harder
        relax[idx] = np.where(flip & (np.abs(prev_dh[idx]) > 0), np.maximum(relax[idx] * 0.5, 0.05), relax[idx])
        h[idx] += relax[idx] * dh
        prev_dh[idx] = dh
        active[idx] = np.abs(dh) >= tol_h
    lat, lon, x, f1, f2 = _solve_llh_fixed_h(sat, vel, rng, lat, lon, h)
    mismatch = np.nan_to_num(dem.ellipsoidal(lat, lon), nan=h) - h
    ok = (np.abs(f1) < 0.01) & (np.abs(f2) < 0.01) & (np.abs(mismatch) < 10 * tol_h)
    if not ok.all():
        log.warning("rdr2geo: %d / %d points did not converge", (~ok).sum(), ok.size)
    out = {"lat": lat, "lon": lon, "h": h, "xyz": x, "converged": ok, "height_mismatch": mismatch}
    return {k: (v.reshape(*shape, 3) if k == "xyz" else v.reshape(shape)) for k, v in out.items()}


def geo2rdr(orbit: StateVectors, xyz: np.ndarray, t_guess) -> tuple[np.ndarray, np.ndarray]:
    """Zero-Doppler orbit time (s) and slant range (m) of ECEF points in another acquisition."""
    shape = np.shape(xyz)[:-1]
    x = np.reshape(xyz, (-1, 3))
    tg = np.broadcast_to(np.asarray(t_guess, np.float64), shape).ravel()
    t = orbit.zero_doppler_time(x, tg)
    if not orbit.covers(t):
        raise DataError("geo2rdr: points fall outside the secondary orbit span")
    r = orbit.slant_range(x, t)
    return t.reshape(shape), r.reshape(shape)


def llh_grid_guess(grid_line, grid_pixel, grid_lat, grid_lon, lines, samples):
    """Initial lat/lon guess at (lines, samples) by linear interpolation of the geolocation grid."""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    pts = np.column_stack([grid_line, grid_pixel])
    q = np.column_stack([np.ravel(lines), np.ravel(samples)])
    if len(pts) < 3:                      # e.g. only a scene-centre tie point: constant guess (Newton converges)
        return (np.full(np.shape(lines), float(np.mean(grid_lat))),
                np.full(np.shape(lines), float(np.mean(grid_lon))))
    out = []
    for v in (grid_lat, grid_lon):
        lin = LinearNDInterpolator(pts, v)(q)
        bad = ~np.isfinite(lin)
        if bad.any():
            lin[bad] = NearestNDInterpolator(pts, v)(q[bad])
        out.append(lin.reshape(np.shape(lines)))
    return out[0], out[1]


__all__ = ["ecef_to_llh", "geo2rdr", "llh_grid_guess", "rdr2geo"]
