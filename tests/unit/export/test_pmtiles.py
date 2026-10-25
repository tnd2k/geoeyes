import gzip

import numpy as np
import pytest

from tests.unit.export.mvt_decode import decode

pytest.importorskip("pmtiles")
from geoeyes.export.pmtiles import EXTENT, TileReader, write_pmtiles, zoom_range  # noqa: E402


def test_points_round_trip_through_pmtiles(tmp_path):
    rng = np.random.default_rng(0)
    n = 5000
    lon, lat = 105.8 + 0.05 * rng.random(n), 21.0 + 0.04 * rng.random(n)
    props = np.column_stack([rng.normal(0, 5, n), rng.uniform(0.5, 3, n), rng.uniform(0.6, 1, n)]).astype(np.float32)
    props[7, 1] = np.nan                                                    # missing values are left out
    s = write_pmtiles(tmp_path / "p.pmtiles", lon, lat, props, spacing_m=8.0, name="t")
    r = TileReader(tmp_path / "p.pmtiles")
    h, meta = r.header, r.metadata()
    assert (h["min_zoom"], h["max_zoom"]) == (s["min_zoom"], s["max_zoom"]) and meta["vector_layers"][0]["id"] == "points"
    z = h["max_zoom"]
    seen = {}

    def ty(la):
        return int((1 - np.log(np.tan(np.radians(la)) + 1 / np.cos(np.radians(la))) / np.pi) / 2 * 2 ** z)

    xs = range(int((lon.min() + 180) / 360 * 2 ** z), int((lon.max() + 180) / 360 * 2 ** z) + 1)
    for x in xs:
        for y in range(ty(lat.max()), ty(lat.min()) + 1):
            b = r.get(z, x, y)
            if not b:
                continue
            for fid, px, py, p in decode(gzip.decompress(b)):
                assert 0 <= px < EXTENT and 0 <= py < EXTENT
                mx = (x + px / EXTENT) / 2 ** z * 360 - 180                 # tile pixel back to longitude
                assert abs(mx - lon[fid]) < 360 / 2 ** z / EXTENT * 1.5
                seen[fid] = p
    assert len(seen) == n                                                   # every point at the top zoom
    assert seen[3]["v"] == pytest.approx(props[3, 0], abs=1e-5) and "s" not in seen[7]
    counts = s["points_per_zoom"]
    assert counts[z] == n and all(counts[k] <= counts[k + 1] for k in range(h["min_zoom"], z))
    r.close()


def test_zoom_range_follows_point_spacing():
    lon, lat = np.array([105.80, 105.90]), np.array([21.0, 21.08])
    zmin, zmax = zoom_range(lon, lat, spacing_m=5.0)
    assert zmin <= 10 and zmax == 15           # ~2 px between neighbours on 512 px tiles
    assert zoom_range(lon, lat, spacing_m=40.0)[1] == 12
