"""Geometry helpers shared by the PS steps."""
from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay


def geolocate(lat, lon, incidence_deg, heading_deg: float, look_side: str, dh):
    """Position of a scatterer dh above the DEM in a pixel geolocated at the DEM height. At the same slant
    range, a higher point lies farther from the sensor (the layover of a building top toward the sensor, seen
    the other way round): it is moved dh/tan(θ) along the ground in the look direction, away from the sensor.
    Checked against the exact range-sphere / zero-Doppler solution at h + dh (Capella left, CSK right)."""
    shift = np.nan_to_num(dh) / np.tan(np.radians(incidence_deg))
    away = np.radians(heading_deg + (90.0 if str(look_side).lower() == "right" else -90.0))   # look direction
    return (lat + shift * np.cos(away) / 111_320.0,
            lon + shift * np.sin(away) / (111_320.0 * np.cos(np.radians(lat))))


def triangulation_edges(xy: np.ndarray) -> np.ndarray:
    """Unique edges (m, 2) of the Delaunay triangulation of (n, 2) points, each as (low, high) index,
    sorted (replaces the external Triangle program of the legacy engine)."""
    s = Delaunay(np.asarray(xy, dtype=np.float64)).simplices
    e = np.sort(np.concatenate([s[:, [0, 1]], s[:, [1, 2]], s[:, [2, 0]]]), axis=1)
    return np.unique(e, axis=0)

# StaMPS llh2local constants (kept for parity with the legacy engine; e is not the WGS84 value)
_A = 6378137.0
_E = 0.08209443794970


def _meridian_arc(phi):
    e2, e4, e6 = _E**2, _E**4, _E**6
    return _A * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                 - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * np.sin(2 * phi)
                 + (15 * e4 / 256 + 45 * e6 / 1024) * np.sin(4 * phi)
                 - (35 * e6 / 3072) * np.sin(6 * phi))


def llh2local(lonlat: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """Polyconic projection of (n, 2) lon/lat (deg) about ``origin`` (lon, lat) -> (n, 2) east/north in km
    (StaMPS units; callers scale to m so the legacy mm rounding is reproduced bit for bit)."""
    lon, lat = (np.asarray(lonlat, np.float64) * np.pi / 180).T
    lon0, lat0 = np.asarray(origin, np.float64)[:2] * np.pi / 180
    xy = np.zeros((lon.size, 2))
    m0 = _meridian_arc(lat0)
    z = lat != 0
    phi = lat[z]
    n = _A / np.sqrt(1 - _E**2 * np.sin(phi) ** 2)
    e = (lon[z] - lon0) * np.sin(phi)
    xy[z, 0] = n / np.tan(phi) * np.sin(e)
    xy[z, 1] = _meridian_arc(phi) - m0 + n / np.tan(phi) * (1 - np.cos(e))
    xy[~z, 0] = _A * (lon[~z] - lon0)
    xy[~z, 1] = -m0
    return xy / 1000.0
