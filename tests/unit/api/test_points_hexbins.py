"""Hexagon bins of a product layer: every point in one bin, the median per bin, cached."""
from __future__ import annotations

import json

import numpy as np

from geoeyes.api import points


def _layer(tmp_path, lon, lat, vel):
    tmp_path.mkdir(parents=True, exist_ok=True)
    z = {k: np.zeros(lon.size, np.float32) for k in points.ATTRS}
    np.savez(tmp_path / "attrs.npz", lon=lon, lat=lat, vel=vel.astype(np.float32), **z)
    np.save(tmp_path / "ts.npy", np.zeros((lon.size, 1), np.float32))
    (tmp_path / "meta.json").write_text(json.dumps({"origin": [float(lon.mean()), float(lat.mean())]}), encoding="utf-8")
    points._arrays.cache_clear()
    return tmp_path


def test_hexbins_counts_medians_and_cache(tmp_path):
    rng = np.random.default_rng(1)
    lon = 106.7 + rng.uniform(-0.05, 0.05, 50_000)
    lat = 10.8 + rng.uniform(-0.05, 0.05, 50_000)
    vel = np.where(lon > 106.7, -10.0, 2.0) + rng.normal(0, 0.1, lon.size)
    folder = _layer(tmp_path / "layer", lon, lat, vel)
    a = np.frombuffer(points.hexbins(folder, 1000), np.float32).reshape(-1, 4)
    assert int(a[:, 3].sum()) == lon.size                      # every point in exactly one hexagon
    # 11 km x 11 km over hexagons of 2.6 km2: about 50 cells (some partial at the edges)
    assert 40 < len(a) < 80
    east = a[:, 0] > 0.01                                     # cells well inside the subsiding half
    assert np.allclose(a[east, 2], -10.0, atol=0.2) and np.allclose(a[a[:, 0] < -0.01, 2], 2.0, atol=0.2)
    # cell centres: no two closer than the hexagon's short diameter (sqrt(3) x size)
    x, y = a[:, 0] * 111_320 * np.cos(np.radians(10.8)), a[:, 1] * 110_574
    d = np.hypot(x[:, None] - x[None], y[:, None] - y[None]) + np.eye(len(a)) * 1e9
    assert d.min() > 1000 * np.sqrt(3) * 0.99
    assert (folder / "hex_1000.bin").exists() and points.hexbins(folder, 1000) == a.tobytes()
