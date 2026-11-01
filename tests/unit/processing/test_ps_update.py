"""Incremental ps update (geoeyes.processing.ps.update): a new date added to a previous run, on a synthetic stack
with a subsidence bowl and, on the new date, an atmospheric ramp of more than one cycle across the area."""
import json
from datetime import date

import geopandas as gpd
import h5py
import numpy as np

from geoeyes.core.geodesy import geohash
from geoeyes.io.manifest import InputRef, Manifest
from geoeyes.io.points import write_points
from geoeyes.io.stack import StackStore
from geoeyes.processing.ps import update as pu

WL = 0.0555
LAM = WL / (4 * np.pi) * 1000.0                    # mm per radian
DATES = ["2025-01-01", "2025-01-13", "2025-01-25", "2025-02-06", "2025-02-18", "2025-03-02"]
N = 64


def _setup(tmp_path):
    rng = np.random.default_rng(0)
    y, x = np.mgrid[0:N, 0:N].astype(float)
    lon, lat = 105.80 + x * 1e-4, 21.00 + y * 1e-4                     # ~10 m pixels
    v = -40.0 * np.exp(-((x - 32) ** 2 + (y - 32) ** 2) / (2 * 12.0 ** 2))      # mm/yr bowl
    t = np.array([(date.fromisoformat(d) - date.fromisoformat(DATES[0])).days / 365.25 for d in DATES])
    disp = v[None] * t[:, None, None]                                           # mm, master (date 0) = 0
    atmo = np.zeros((len(DATES), N, N))
    atmo[-1] = 9.0 * x / N                                                      # rad: 1.4 cycles across, new date
    phase = -disp / LAM + atmo + rng.normal(0, 0.2, (len(DATES), N, N))         # phase of slc_0 · conj(slc_k)
    slc = np.exp(-1j * phase).astype(np.complex64)                              # slc_0 = 1
    s = StackStore.create(tmp_path / "stack.zarr", coords={"date": np.array(DATES, "datetime64[ns]"),
                                                            "y": np.arange(N), "x": np.arange(N)},
                          attrs={"reference_date": DATES[0], "wavelength_m": WL, "track": "t"})
    s.write("slc", slc, ("date", "y", "x"))
    s.write("kh", np.zeros((len(DATES), N, N), np.float32), ("date", "y", "x"))
    for k, a in {"incidence": np.full((N, N), 40.0), "slant_range": np.full((N, N), 8.5e5),
                 "lon": lon, "lat": lat}.items():
        s.write(f"geometry_{k}", a.astype(np.float32 if k != "lon" else np.float64), ("y", "x"))
    # the previous run: every pixel a point, the first five dates
    run = tmp_path / "run"
    run.mkdir()
    n = N * N
    ep = len(DATES) - 1
    hgt = rng.normal(10, 3, n)
    flat = lambda a: a.reshape(a.shape[0], -1).T                                # noqa: E731
    with h5py.File(run / "state.h5", "w") as f:
        f["ps/line"], f["ps/sample"] = y.ravel().astype(np.int32), x.ravel().astype(np.int32)
        f["ps/lat"], f["ps/lon"], f["ps/height_m"] = lat.ravel(), lon.ravel(), hgt.astype(np.float32)
        f["ps/dem_err_m"] = np.zeros(n, np.float32)
        f["ps/coherence"] = np.ones(n, np.float32)
        f["ps/bperp"] = np.zeros((n, ep - 1), np.float32)
        f["phase/unwrapped"] = (-flat(disp[1:ep]) / LAM).astype(np.float32)
        for k in ("scla", "aps", "aps_linear", "scn"):
            f[f"phase/{k}"] = np.zeros((n, ep - 1), np.float32)
        f["velocity/disp_mm"] = flat(disp[:ep]).astype(np.float32)
        f["velocity/disp_scn_mm"] = flat(disp[:ep]).astype(np.float32)
        for k in ("v_mm_yr", "v_linear_mm_yr", "v_scn_mm_yr"):
            f[f"velocity/{k}"] = v.ravel().astype(np.float32)
        f["time/ifg_std_deg"] = np.full(ep, 20.0, np.float32)
        f["time/epoch_dates"] = np.array(DATES[:ep], "S10")
        f["time/ifg_dates"] = np.array(DATES[1:ep], "S10")
    uid = np.char.add(np.char.add("t:", geohash(lat.ravel(), lon.ravel())),
                      np.char.add(":", np.round(hgt.astype(np.float32)).astype(int).astype(str)))
    write_points(run / "points.parquet", gpd.GeoDataFrame(
        {"point_uid": uid, "lon": lon.ravel(), "lat": lat.ravel(), "line": y.ravel(), "sample": x.ravel()},
        geometry=gpd.points_from_xy(lon.ravel(), lat.ravel()), crs="EPSG:4326"))
    (run / "params.json").write_text(json.dumps({"table": {}}))
    Manifest(kind="ps_run", id="t", engine="geoeyes-ps/4", inputs=[InputRef("stack", str(s.path), "")],
             extra={"config_fingerprint": "fp"}).write(run)
    return s, run, disp, atmo


def test_new_date_is_added_and_unwrapped(tmp_path):
    s, run, disp, atmo = _setup(tmp_path)
    new, why = pu.plan(run, s, "fp", full_every=4)
    assert new == [DATES[-1]] and why == ""
    assert pu.plan(run, s, "other", full_every=4)[0] == []                     # parameters changed: full run
    pu.update(s, run, new, grid_size=10.0, track_id="t", config_fingerprint="fp")
    with h5py.File(run / "state.h5", "r") as f:
        got = f["velocity/disp_mm"][()][:, -1].astype(float)
        assert f["time/epoch_dates"][()][-1].decode() == DATES[-1] and f["phase/unwrapped"].shape[1] == 5
    # what the engine would give: motion + the ramp the linear APS cannot remove, referenced to the scene mean
    want = (disp[-1] - atmo[-1] * LAM).ravel()
    d = (got - got.mean()) - (want - want.mean())
    assert np.std(d) < 1.5 and np.abs(d).max() < 13.0         # noise 0.2 rad = 0.9 mm; no 2π (27.7 mm) jump anywhere
    m = Manifest.read(run)
    assert m.engine == pu.UPDATE_ENGINE and m.metrics["update"]["dates_since_full"] == 1
    assert pu.plan(run, s, "fp", full_every=4) == ([], "no new date")


def test_update_refused_when_dates_are_not_appended(tmp_path):
    s, run, _, _ = _setup(tmp_path)
    with h5py.File(run / "state.h5", "a") as f:                               # the run lacks a middle date
        del f["time/epoch_dates"]
        f["time/epoch_dates"] = np.array([DATES[0], *DATES[2:]], "S10")
    new, why = pu.plan(run, s, "fp", full_every=4)
    assert new == [] and "not after" in why
