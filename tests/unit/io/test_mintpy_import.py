"""MintPy time series imported as a (foreign) GeoEyes point product (products/foreign.py)."""
import h5py
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geoeyes.ml.decompose import describe
from geoeyes.products.builder import los_vector
from geoeyes.products.foreign import block_mean, import_mintpy, mintpy_los


def _write_stack(tmp_path, *, orbit="ascending", heading=-12.36, azimuth=100.9, vel_mm_yr=-30.0):
    ny, nx, nt = 20, 20, 12
    dates = [f"2020{m:02d}15" for m in range(1, 13)]
    t = (np.array([np.datetime64(f"{d[:4]}-{d[4:6]}-{d[6:]}") for d in dates]) - np.datetime64("2020-01-15"))
    tyr = t.astype(float) / 365.25
    ts = np.broadcast_to((vel_mm_yr / 1000.0 * tyr)[:, None, None], (nt, ny, nx)).astype(np.float32).copy()
    ts[:, :5, :5] = 0.0                                 # masked by MintPy: all-zero series
    ts[:, 10, 10] = 0.0                                 # the reference pixel (kept)
    p_ts = tmp_path / "timeseries.h5"
    with h5py.File(p_ts, "w") as f:
        f["timeseries"] = ts
        f["date"] = np.array(dates, "S8")
        f.attrs.update({"EPSG": "32650", "X_FIRST": "800000.0", "Y_FIRST": "2650000.0", "X_STEP": "40.0",
                        "Y_STEP": "-40.0", "ORBIT_DIRECTION": orbit, "HEADING": str(heading), "REF_Y": "10",
                        "REF_X": "10", "REF_DATE": dates[0], "UNIT": "m", "WAVELENGTH": "0.0555",
                        "mintpy.deramp": "linear"})
    p_g = tmp_path / "geometryGeo.h5"
    with h5py.File(p_g, "w") as g:
        g["incidenceAngle"] = np.full((ny, nx), 34.0, np.float32)
        g["azimuthAngle"] = np.full((ny, nx), azimuth, np.float32)
        g["height"] = np.full((ny, nx), 12.0, np.float32)
        wm = np.ones((ny, nx), bool)
        wm[:, -5:] = False                              # sea on the right
        g["waterMask"] = wm
    return p_ts, p_g


def test_block_mean_ignores_nan():
    a = np.arange(16, dtype=float).reshape(4, 4)
    a[0, 0] = np.nan
    b = block_mean(a, 2)
    assert b.shape == (2, 2)
    assert np.isclose(b[0, 0], np.mean([1, 4, 5]))


def test_mintpy_los_matches_heading_geometry():
    for heading, az in ((-12.36, 100.9), (-167.65, 259.1)):          # asc, desc (MintPy azimuth convention)
        e, n, u = mintpy_los(34.0, az)
        e2, n2, u2 = los_vector(34.0, heading, "right")
        assert abs(e - e2) < 0.03 and abs(n - n2) < 0.03 and abs(u - u2) < 1e-9
    assert mintpy_los(34.0, 100.9)[0] < -0.5 and mintpy_los(34.0, 259.1)[0] > 0.5   # asc looks east, desc west


def test_import_mintpy_product(tmp_path):
    p_ts, p_g = _write_stack(tmp_path)
    res = import_mintpy(p_ts, p_g, tmp_path / "products", project="demo", track_id="s1-asc-069", step=5)
    out = tmp_path / "products" / res["product_id"]
    pts = pq.read_table(out / "points.parquet").to_pandas()
    # 4 × 4 blocks: the masked corner block and the 4 sea blocks are dropped
    assert len(pts) == 16 - 1 - 4
    v = np.sort(pts["vel_los_mm_yr"].to_numpy())
    # the reference pixel (all-zero series) is kept: its block averages 24 × −30 and one 0
    assert np.allclose(v[:-1], -30.0, atol=1e-3) and np.isclose(v[-1], -30.0 * 24 / 25, atol=1e-3)
    assert (pts["los_e"] < -0.5).all() and np.allclose(pts["los_u"], np.cos(np.radians(34.0)), atol=1e-6)
    ts = pd.read_parquet(out / "timeseries.parquet")
    assert ts.groupby("point_uid")["disp_mm"].first().abs().max() < 1e-6        # zero at the first date
    d = describe(out)
    assert d["track"] == "s1-asc-069" and d["los"][0] < -0.5
    assert res["engine"] == "mintpy" and res["first_date"] == "2020-01-15"
