"""Radar cross section of a triangular trihedral corner reflector seen from a given direction.

Physical-optics effective area of a triangular trihedral with inner edge ``a`` (Knott, *Radar Cross
Section*): with the direction cosines ``l <= m <= n`` of the radar direction on the three edges,

    A = 4 l m a^2 / (l + m + n)                  if l + m <= n
    A = a^2 [ (l + m + n) - 2 / (l + m + n) ]    otherwise
    RCS = 4 pi A^2 / lambda^2                    (on boresight: 4 pi a^4 / (3 lambda^2))

The reflector is described the way it is set up in the field: the opening faces ``face_az_deg``
(degrees from north) and the base plate is tilted ``tilt_deg`` with its front edge raised, so the
boresight elevation is 35.26 deg + tilt.
"""
from __future__ import annotations

import numpy as np

BORESIGHT_ELEVATION_FLAT_DEG = float(np.degrees(np.arctan(1 / np.sqrt(2))))   # 35.26


def enu(az_deg: float, el_deg: float) -> np.ndarray:
    az, el = np.radians(az_deg), np.radians(el_deg)
    return np.array([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)])


def edges(face_az_deg: float, tilt_deg: float) -> list[np.ndarray]:
    """Unit vectors of the three edges of a base-plate trihedral."""
    e = [enu(face_az_deg - 45, 0), enu(face_az_deg + 45, 0), np.array([0.0, 0.0, 1.0])]
    u = enu(face_az_deg, 0)
    k = np.cross(u, [0.0, 0.0, 1.0])
    k /= np.linalg.norm(k)
    t = np.radians(tilt_deg)
    return [v * np.cos(t) + np.cross(k, v) * np.sin(t) + k * np.dot(k, v) * (1 - np.cos(t)) for v in e]


def boresight(face_az_deg: float, tilt_deg: float) -> tuple[float, float]:
    """(azimuth, elevation) of the reflector's boresight."""
    b = sum(edges(face_az_deg, tilt_deg))
    b /= np.linalg.norm(b)
    return float(np.degrees(np.arctan2(b[0], b[1])) % 360), float(np.degrees(np.arcsin(b[2])))


def rcs_m2(edge_m: float, wavelength_m: float, los_az_deg: float, los_el_deg: float,
           face_az_deg: float, tilt_deg: float) -> float:
    """RCS (m^2) towards the satellite at (los_az, los_el), the ground -> satellite direction."""
    r = enu(los_az_deg, los_el_deg)
    a, b, c = sorted(float(np.dot(r, v)) for v in edges(face_az_deg, tilt_deg))   # direction cosines, ascending
    if a <= 0:
        return 0.0
    s = a + b + c
    area = 4 * a * b * edge_m ** 2 / s if a + b <= c else edge_m ** 2 * (s - 2 / s)
    return float(4 * np.pi * area ** 2 / wavelength_m ** 2)


def rcs_dbsm(*args, **kw) -> float:
    v = rcs_m2(*args, **kw)
    return float(10 * np.log10(v)) if v > 0 else float("-inf")


def peak_rcs_dbsm(edge_m: float, wavelength_m: float) -> float:
    return float(10 * np.log10(4 * np.pi * edge_m ** 4 / (3 * wavelength_m ** 2)))


def required_pointing(los_az_deg: float, los_el_deg: float) -> dict:
    """Set-up that points the boresight at the satellite: face azimuth, boresight elevation, base tilt."""
    return {"face_azimuth_deg": los_az_deg % 360, "boresight_elevation_deg": los_el_deg,
            "base_tilt_deg": los_el_deg - BORESIGHT_ELEVATION_FLAT_DEG}
