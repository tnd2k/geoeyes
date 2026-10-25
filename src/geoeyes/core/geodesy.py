"""WGS84 ellipsoid conversions (degrees, metres): geodetic <-> ECEF, local ENU."""
from __future__ import annotations

import numpy as np

A = 6_378_137.0
F = 1 / 298.257223563
B = A * (1 - F)
E2 = F * (2 - F)
EP2 = E2 / (1 - E2)


def llh_to_ecef(lat, lon, h) -> np.ndarray:
    lat, lon, h = (np.radians(np.asarray(lat, np.float64)), np.radians(np.asarray(lon, np.float64)),
                   np.asarray(h, np.float64))
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (n * (1 - E2) + h) * np.sin(lat)
    return np.stack([x, y, z], axis=-1)


def ecef_to_llh(xyz) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bowring's method, refined twice (sub-millimetre near the Earth surface)."""
    xyz = np.asarray(xyz, np.float64)
    x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    th = np.arctan2(z * A, p * B)
    lat = np.arctan2(z + EP2 * B * np.sin(th) ** 3, p - E2 * A * np.cos(th) ** 3)
    for _ in range(2):
        n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - E2 * n / (n + h)))
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return np.degrees(lat), np.degrees(lon), h


_GEOHASH32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat, lon, precision: int = 9) -> np.ndarray:
    """Standard geohash strings (precision 9 ≈ 4.8 m x 4.8 m), vectorised over arrays."""
    lat = np.atleast_1d(np.asarray(lat, np.float64))
    lon = np.atleast_1d(np.asarray(lon, np.float64))
    lat_lo, lat_hi = np.full(lat.shape, -90.0), np.full(lat.shape, 90.0)
    lon_lo, lon_hi = np.full(lon.shape, -180.0), np.full(lon.shape, 180.0)
    codes = np.zeros((lat.size, precision), np.int64)
    even = True
    for i in range(precision * 5):
        if even:
            mid = (lon_lo + lon_hi) / 2
            bit = lon >= mid
            lon_lo = np.where(bit, mid, lon_lo)
            lon_hi = np.where(bit, lon_hi, mid)
        else:
            mid = (lat_lo + lat_hi) / 2
            bit = lat >= mid
            lat_lo = np.where(bit, mid, lat_lo)
            lat_hi = np.where(bit, lat_hi, mid)
        codes[:, i // 5] = (codes[:, i // 5] << 1) | bit
        even = not even
    alphabet = np.array(list(_GEOHASH32))
    chars = alphabet[codes]
    return np.array(["".join(r) for r in chars])


def enu_basis(lat, lon) -> np.ndarray:
    """(..., 3, 3) rows = unit East, North, Up vectors in ECEF."""
    lat, lon = np.radians(np.asarray(lat, np.float64)), np.radians(np.asarray(lon, np.float64))
    sl, cl, so, co = np.sin(lat), np.cos(lat), np.sin(lon), np.cos(lon)
    e = np.stack([-so, co, np.zeros_like(so)], -1)
    n = np.stack([-sl * co, -sl * so, cl], -1)
    u = np.stack([cl * co, cl * so, sl], -1)
    return np.stack([e, n, u], -2)
