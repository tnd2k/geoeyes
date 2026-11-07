"""Map layer extras (geoeyes.api.points): displacement frames for the time animation, and the points along a
profile line."""
import json

import numpy as np
import pytest

from geoeyes.api import points


def _cache(tmp_path):
    n = 200
    lon = np.linspace(105.80, 105.82, n)                      # a west-east row of points, ~2 km
    lat = np.full(n, 21.0) + np.where(np.arange(n) % 2, 1e-4, -1e-4)   # alternately ~11 m north and south
    vel = np.linspace(-10, 10, n).astype(np.float32)
    ts = np.stack([vel * t for t in (0.0, 0.5, 1.0)], axis=1).astype(np.float32)
    ts[3, 2] = np.nan
    np.savez(tmp_path / "attrs.npz", lon=lon, lat=lat, vel=vel, height_m=np.full(n, 12.0, np.float32),
             vel_std_mm_yr=np.full(n, 1.0, np.float32))
    np.save(tmp_path / "ts.npy", ts)
    (tmp_path / "meta.json").write_text(json.dumps({"dates": ["2025-01-01", "2025-07-01", "2026-01-01"]}))
    points._arrays.cache_clear()
    return tmp_path


def test_displacement_frames(tmp_path):
    f = _cache(tmp_path)
    m = points.disp_meta(f)
    assert m["dates"][-1] == "2026-01-01" and m["min"] == pytest.approx(-10) and m["max"] == pytest.approx(10)
    last = np.frombuffer(points.disp_frame(f, 2), "<i2")
    assert last[0] == -100 and last[-1] == 100 and last[3] == -32768        # 0.1 mm units, NaN marked
    with pytest.raises(IndexError):
        points.disp_frame(f, 3)


def test_profile_along_a_line(tmp_path):
    f = _cache(tmp_path)
    p = points.profile(f, [[105.805, 21.0], [105.815, 21.0]], 20.0)
    assert p["n"] == 100 and p["length_m"] == pytest.approx(1039, rel=0.01)
    d, off, v = map(np.asarray, (p["dist_m"], p["offset_m"], p["vel"]))
    assert d.min() < 15 and d.max() > 1020 and np.all(np.abs(np.abs(off) - 11) < 1)
    assert set(np.sign(off)) == {-1.0, 1.0}                                   # north of an eastward line: left (+)
    assert np.corrcoef(d, v)[0, 1] > 0.99 and p["height_m"][0] == 12.0
    assert len(p["median"]) > 10
    assert points.profile(f, [[105.805, 21.0], [105.815, 21.0]], 5.0)["n"] == 0
