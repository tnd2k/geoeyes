"""Geometry helpers shared by the TOPS and stripmap stack builders.

The functions take any object with the radar-grid interface (``BurstMetadata`` or ``RadarGrid``)
and a ``tops.BurstGeometry`` (ground points of the reference on a coarse grid).
"""
from __future__ import annotations

import numpy as np

from geoeyes.core.geodesy import enu_basis
from geoeyes.geometry.rdr2geo import geo2rdr

KERNELS = ("spline", "lanczos")


def interpolate(base: np.ndarray, line: np.ndarray, sample: np.ndarray, *, kernel: str = "spline",
                radius: int = 8, chunk: int = 8192) -> np.ndarray:
    """``base`` (complex, already basebanded) at the fractional positions (``line``, ``sample``) of its own grid;
    0 outside. ``spline``: cubic B-spline (``map_coordinates`` order 3, prefiltered). ``lanczos``: windowed sinc
    sinc(x)·sinc(x/r) on 2r × 2r taps, each axis normalised to a unit sum (docs/en/research/resampling-kernel.md:
    on CSK, r = 8 loses 6e-6 of coherence where the spline loses 2e-3). Separable: the range taps are applied
    for each of the 2r azimuth rows, ``chunk`` points at a time."""
    if kernel not in KERNELS:
        raise ValueError(f"resample kernel {kernel!r}: {' | '.join(KERNELS)}")
    shape = np.shape(line)
    if kernel == "spline":
        from scipy.ndimage import map_coordinates
        coords = [np.ravel(line), np.ravel(sample)]
        re = map_coordinates(base.real, coords, order=3, mode="constant", cval=0.0)
        im = map_coordinates(base.imag, coords, order=3, mode="constant", cval=0.0)
        return (re + 1j * im).reshape(shape).astype(np.complex64)
    ny, nx = base.shape
    padded = np.zeros((ny + 2 * radius, nx + 2 * radius), np.complex64)    # zeros outside, as mode="constant"
    padded[radius:radius + ny, radius:radius + nx] = base
    lf, sf = np.ravel(line).astype(np.float64), np.ravel(sample).astype(np.float64)
    out = np.zeros(lf.size, np.complex64)
    ok = np.isfinite(lf) & np.isfinite(sf) & (lf > -radius) & (lf < ny - 1 + radius) & \
        (sf > -radius) & (sf < nx - 1 + radius)
    idx = np.flatnonzero(ok)
    taps = np.arange(-radius + 1, radius + 1)

    def weights(x):
        i0 = np.floor(x).astype(np.int64)
        d = x[:, None] - (i0[:, None] + taps)
        w = np.sinc(d) * np.sinc(d / radius)
        return i0, (w / w.sum(1, keepdims=True)).astype(np.float32)

    for a in range(0, idx.size, chunk):
        at = idx[a:a + chunk]
        il, wl = weights(lf[at])
        is_, ws = weights(sf[at])
        cols = is_[:, None] + taps + radius
        acc = np.zeros(at.size, np.complex64)
        for k, t in enumerate(taps):
            rows = il + t + radius
            acc += wl[:, k] * np.einsum("ij,ij->i", padded[rows[:, None], cols], ws)
        out[at] = acc
    return out.reshape(shape)


def height_sensitivity(ref, sec, geo) -> np.ndarray:
    """kh = d/dh [4π/λ (R_sec - R_ref)] on the coarse grid for a scatterer dh above the DEM *in the same
    reference resolution cell*: the point is moved along the reference range circle (perpendicular to the
    reference LOS and velocity) by the amount that raises it 1 m. kh ≈ 4π·B⊥/(λ·R·sinθ). (Moving the point
    straight up instead changes the reference range too and gives sin²θ times this.)"""
    t_guess = sec.orbit_seconds(geo.lines[:, None] * np.ones_like(geo.samples))
    t_sec, r_sec = geo2rdr(sec.orbit, geo.xyz, t_guess)
    p_ref, v_ref = ref.orbit.interpolate(geo.t_ref.ravel())
    x = geo.xyz.reshape(-1, 3)
    los = x - p_ref
    los /= np.linalg.norm(los, axis=1, keepdims=True)
    vel = v_ref / np.linalg.norm(v_ref, axis=1, keepdims=True)
    up = enu_basis(geo.lat.ravel(), geo.lon.ravel())[:, 2, :]
    d = up - np.einsum("ij,ij->i", up, los)[:, None] * los - np.einsum("ij,ij->i", up, vel)[:, None] * vel
    d /= np.einsum("ij,ij->i", d, up)[:, None]                         # 1 m of height
    x1 = (x + d).reshape(geo.xyz.shape)
    _, r_ref1 = geo2rdr(ref.orbit, x1, geo.t_ref)
    _, r_sec1 = geo2rdr(sec.orbit, x1, t_sec)
    return 4.0 * np.pi / ref.wavelength * ((r_sec1 - r_ref1) - (r_sec - geo.r_ref))


def perpendicular_baseline(ref, sec, geo) -> np.ndarray:
    """Perpendicular baseline on the coarse grid (+ = secondary above the reference LOS)."""
    t_sec, _ = geo2rdr(sec.orbit, geo.xyz, sec.orbit_seconds(geo.lines[:, None] * np.ones_like(geo.samples)))
    p_ref, _ = ref.orbit.interpolate(geo.t_ref.ravel())
    p_sec, _ = sec.orbit.interpolate(t_sec.ravel())
    x = geo.xyz.reshape(-1, 3)
    los = x - p_ref
    los /= np.linalg.norm(los, axis=1, keepdims=True)
    up = p_ref / np.linalg.norm(p_ref, axis=1, keepdims=True)
    perp = up - np.einsum("ij,ij->i", up, los)[:, None] * los
    perp /= np.linalg.norm(perp, axis=1, keepdims=True)
    return np.einsum("ij,ij->i", p_sec - p_ref, perp).reshape(geo.lat.shape)


def incidence(ref, geo) -> np.ndarray:
    """Incidence angle at the ground (deg) on the coarse grid."""
    p_ref, _ = ref.orbit.interpolate(geo.t_ref.ravel())
    x = geo.xyz.reshape(-1, 3)
    to_sat = p_ref - x
    to_sat /= np.linalg.norm(to_sat, axis=1, keepdims=True)
    up = enu_basis(geo.lat.ravel(), geo.lon.ravel())[:, 2, :]
    return np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", to_sat, up), -1, 1))).reshape(geo.lat.shape)
