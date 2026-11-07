"""Google Earth (KMZ) and 3D Tiles exports of a small synthetic product."""
import json
import struct
import xml.dom.minidom
import zipfile

import geopandas as gpd
import numpy as np

from geoeyes.export.kmz import export_kmz
from geoeyes.export.tiles3d import ecef, export_3dtiles
from geoeyes.io.points import write_points, write_timeseries


def _product(tmp_path, n=3000):
    rng = np.random.default_rng(0)
    lon, lat = 105.80 + 0.02 * rng.random(n), 21.00 + 0.02 * rng.random(n)
    vel = rng.normal(0, 5, n).astype(np.float32)
    uid = np.array([f"p{i}" for i in range(n)])
    gdf = gpd.GeoDataFrame({"point_uid": uid, "lon": lon, "lat": lat, "vel_los_mm_yr": vel,
                            "height_m": np.full(n, 10.0, np.float32), "temporal_coherence": np.full(n, 0.9)},
                           geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    p = tmp_path / "prod"
    p.mkdir()
    write_points(p / "points.parquet", gdf)
    dates = np.array(["2025-01-01", "2025-02-01", "2025-03-01"], "datetime64[D]")
    write_timeseries(p / "timeseries.parquet", uid, dates, np.outer(vel, [0, 0.1, 0.2]).astype(np.float32))
    return p, vel


def test_kmz(tmp_path):
    p, vel = _product(tmp_path)
    k = export_kmz(p, tmp_path / "out" / "x.kmz")
    z = zipfile.ZipFile(k)
    assert set(z.namelist()) == {"doc.kml", "velocity.png", "legend.png"}
    doc = xml.dom.minidom.parseString(z.read("doc.kml"))
    marks = doc.getElementsByTagName("Placemark")
    assert len(marks) == 1500                                       # the fastest, both directions
    names = sorted(float(m.getElementsByTagName("name")[0].firstChild.data) for m in marks)
    assert names[0] == round(float(vel.min()), 1) and names[-1] == round(float(vel.max()), 1)


def test_3dtiles(tmp_path):
    p, vel = _product(tmp_path)
    ts = export_3dtiles(p, tmp_path / "3dtiles")
    t = json.loads(ts.read_text())
    assert t["asset"]["version"] == "1.0" and t["root"]["refine"] == "ADD"
    total = 0
    for content in [t["root"]["content"], *[c["content"] for c in t["root"]["children"]]]:
        b = (ts.parent / content["uri"]).read_bytes()
        magic, ver, length, fj, fb, bj, bb = struct.unpack("<4s6I", b[:28])
        assert magic == b"pnts" and ver == 1 and length == len(b) and (28 + fj) % 8 == 0
        ft = json.loads(b[28:28 + fj])
        n = ft["POINTS_LENGTH"]
        pos = np.frombuffer(b[28 + fj:28 + fj + 12 * n], "<f4").reshape(n, 3) + ft["RTC_CENTER"]
        r = np.linalg.norm(pos, axis=1)
        assert np.all(np.abs(r - np.linalg.norm(ecef(105.81, 21.01, 0.0), axis=1)) < 200)   # on the ellipsoid
        bt = json.loads(b[28 + fj + fb:28 + fj + fb + bj])
        v = np.frombuffer(b[28 + fj + fb + bj:], "<f4", count=n, offset=bt["vel_los_mm_yr"]["byteOffset"])
        assert np.all(np.isin(v, vel))
        total += n
    assert total == len(vel)                                        # every point once (additive refinement)
    assert "tileset.json" in (ts.parent / "viewer.html").read_text(encoding="utf-8")
