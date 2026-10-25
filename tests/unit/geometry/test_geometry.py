"""geoeyes.core.geodesy, geoeyes.geometry.orbit / rdr2geo on synthetic geometry."""
from datetime import datetime, timedelta

import numpy as np
import pytest

from geoeyes.core.errors import DataError
from geoeyes.core.geodesy import ecef_to_llh, enu_basis, llh_to_ecef
from geoeyes.geometry.orbit import StateVectors
from geoeyes.geometry.rdr2geo import geo2rdr, rdr2geo


def test_missing_srtm_tiles_are_downloaded_or_ocean(tmp_path, monkeypatch):
    import zipfile

    from geoeyes.geometry import dem as D
    tile = (np.arange(3601 * 3601) % 100).astype(">i2").reshape(3601, 3601)     # SRTM: big-endian int16
    calls = []

    def fake_download(url, dest, attempts=3):
        calls.append(url)
        if "N21E105" not in url:
            return False                                      # 404: ocean
        with zipfile.ZipFile(dest, "w") as z:
            z.writestr("N21E105.hgt", tile.tobytes())
        return True
    monkeypatch.setattr(D, "_download", fake_download)
    tmp_path.mkdir(exist_ok=True)
    d = D.load_srtm1(21.1, 21.9, 105.1, 106.5, tmp_path, download=True)   # N21E105 + N21E106 (ocean)
    assert d.height.shape == (3601, 2 * 3601 - 1)
    assert np.array_equal(d.height[:, :3601], tile.astype(np.float32)) and not d.height[:, 3601:].any()
    assert (tmp_path / "N21E105.SRTMGL1.hgt.zip").exists() and len(calls) == 2
    D.load_srtm1(21.1, 21.9, 105.1, 105.5, tmp_path, download=True)        # cached now: no new download
    assert len(calls) == 2
    with pytest.raises(D.DataError):
        D.load_srtm1(21.1, 21.9, 107.1, 107.5, tmp_path / "empty", download=False)


GM = 3.986004418e14


def test_llh_ecef_roundtrip():
    lat = np.array([0.0, 19.35, -45.0, 89.9])
    lon = np.array([0.0, -99.0, 170.0, 10.0])
    h = np.array([0.0, 2240.0, -50.0, 1000.0])
    la, lo, hh = ecef_to_llh(llh_to_ecef(lat, lon, h))
    np.testing.assert_allclose(la, lat, atol=1e-9)
    np.testing.assert_allclose(lo, lon, atol=1e-9)
    np.testing.assert_allclose(hh, h, atol=1e-4)
    b = enu_basis(19.35, -99.0)
    np.testing.assert_allclose(b @ b.T, np.eye(3), atol=1e-12)


def _circular_orbit(n=40, dt=10.0, radius=7.07e6, incl=np.radians(98.2)):
    """Inertial-ish circular orbit sampled as ECEF-like state vectors (enough for interpolation tests)."""
    w = np.sqrt(GM / radius**3)
    t = np.arange(n) * dt
    u = w * t
    pos = radius * np.stack([np.cos(u), np.sin(u) * np.cos(incl), np.sin(u) * np.sin(incl)], -1)
    vel = radius * w * np.stack([-np.sin(u), np.cos(u) * np.cos(incl), np.cos(u) * np.sin(incl)], -1)
    t0 = datetime(2024, 7, 14, 0, 49)
    return StateVectors.from_lists([t0 + timedelta(seconds=float(x)) for x in t], pos, vel), w, radius, incl


def test_hermite_interpolation_matches_analytic_orbit():
    orb, w, r, incl = _circular_orbit()
    tq = np.linspace(5, 380, 101) + 0.123
    p, v = orb.interpolate(tq)
    u = w * tq
    p_true = r * np.stack([np.cos(u), np.sin(u) * np.cos(incl), np.sin(u) * np.sin(incl)], -1)
    assert np.abs(p - p_true).max() < 1e-3                     # < 1 mm with 10 s spacing
    v_true = r * w * np.stack([-np.sin(u), np.cos(u) * np.cos(incl), np.cos(u) * np.sin(incl)], -1)
    assert np.abs(v - v_true).max() < 1e-4
    with pytest.raises(DataError):
        orb.interpolate(1e6)


class _FlatDem:
    def __init__(self, h):
        self.h = h

    def ellipsoidal(self, lat, lon, order=1):
        return np.full(np.shape(lat), self.h, float)


def test_zero_doppler_rdr2geo_and_back():
    orb, *_ = _circular_orbit()
    t = np.array([100.0, 150.0, 200.0])
    p, v = orb.interpolate(t)
    # ground points 800-900 km slant range, roughly below/side of the track
    la, lo, _ = ecef_to_llh(p * (6.38e6 / np.linalg.norm(p, axis=1, keepdims=True)))
    rng = np.array([850e3, 880e3, 900e3])
    g = rdr2geo(orb, t, rng, _FlatDem(500.0), la + 2.0, lo + 3.0)
    assert g["converged"].all()
    t2, r2 = geo2rdr(orb, g["xyz"], t + 1.0)
    np.testing.assert_allclose(t2, t, atol=1e-7)
    np.testing.assert_allclose(r2, rng, atol=1e-3)
    np.testing.assert_allclose(g["h"], 500.0, atol=0.05)
