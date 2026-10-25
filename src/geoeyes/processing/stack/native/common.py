"""Geometry helpers shared by the TOPS and stripmap stack builders.

The functions take any object with the radar-grid interface (``BurstMetadata`` or ``RadarGrid``)
and a ``tops.BurstGeometry`` (ground points of the reference on a coarse grid).
"""
from __future__ import annotations

import numpy as np

from geoeyes.core.geodesy import enu_basis
from geoeyes.geometry.rdr2geo import geo2rdr


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
