"""geoeyes.io: manifest, StackStore (Zarr v3), StateStore (HDF5), PointStore/TimeSeriesStore, COG."""
import numpy as np
import pytest

from geoeyes.core.errors import StoreError
from geoeyes.io.manifest import Manifest, atomic_write_json, read_json
from geoeyes.io.points import read_points, read_timeseries, timeseries_matrix, write_points, write_timeseries
from geoeyes.io.raster import read_raster, write_cog
from geoeyes.io.stack import StackStore
from geoeyes.io.state import StateSchema, StateStore, VarSpec


def test_atomic_json_and_manifest_roundtrip(tmp_path):
    atomic_write_json(tmp_path / "a.json", {"x": 1})
    assert read_json(tmp_path / "a.json") == {"x": 1}
    (tmp_path / "points.parquet").write_bytes(b"data")
    m = Manifest(kind="product", id="p_v1", engine="ps_lite", params={"sha256": "abc"})
    m.add_outputs(tmp_path, ["points.parquet"])
    m.write(tmp_path)
    back = Manifest.read(tmp_path)
    assert back.id == "p_v1" and back.outputs[0].bytes == 4 and back.software["geoeyes"]
    assert back.verify(tmp_path) == []
    (tmp_path / "points.parquet").write_bytes(b"changed")
    assert back.verify(tmp_path) == ["points.parquet"]


def test_stack_store_whole_and_region_writes(tmp_path):
    dates = np.array(["2024-05-03", "2024-05-15", "2024-05-27"], dtype="datetime64[D]")
    st = StackStore.create(tmp_path / "stack.zarr", coords={"date": dates, "y": np.arange(40), "x": np.arange(30)},
                           attrs={"stack_id": "s1", "wavelength_m": 0.0555})
    rng = np.random.default_rng(0)
    slc = (rng.standard_normal((3, 40, 30)) + 1j * rng.standard_normal((3, 40, 30))).astype(np.complex64)
    st.write("slc", slc, ("date", "y", "x"), attrs={"units": "1"}, chunks={"y": 16, "x": 16})
    assert st.has("slc") and not st.has("ifg")
    np.testing.assert_array_equal(st.read("slc", date=1), slc[1])
    assert st.attrs["stack_id"] == "s1"
    ds = st.open()
    assert ds["date"].dtype == np.dtype("datetime64[ns]") and ds["slc"].dtype == np.complex64

    st.allocate("coherence", ("y", "x"), np.float32, chunks={"y": 20, "x": 30})
    block = np.full((20, 30), 0.5, np.float32)
    st.write_region("coherence", block, {"y": slice(20, 40)})
    coh = st.read("coherence")
    assert np.isnan(coh[:20]).all() and np.all(coh[20:] == 0.5)     # unwritten blocks read as NaN

    st.write("slc", slc[:, :, ::-1], ("date", "y", "x"))       # replace
    np.testing.assert_array_equal(st.read("slc", date=0), slc[0, :, ::-1])
    st.update_attrs(engine="snap")
    assert st.attrs["engine"] == "snap"
    with pytest.raises(StoreError):
        StackStore.create(tmp_path / "stack.zarr", coords={})


SCHEMA = StateSchema.of("geoeyes.test", 1, [
    VarSpec("step1/ph", "complex64", ("ps", "ifg"), "rad", "wrapped phase", legacy="ph1.mat:ph"),
    VarSpec("step1/n_ps", "int64", (), description="number of PS"),
])


def test_state_store_schema_and_checkpoints(tmp_path):
    s = StateStore(tmp_path / "state.h5", SCHEMA)
    ph = np.exp(1j * np.linspace(0, 6, 20)).reshape(5, 4)
    s.write("step1/ph", ph)
    s.write("step1/n_ps", 5)
    s.mark_done("step1")
    assert s.read("step1/n_ps") == 5 and s.read("step1/ph").dtype == np.complex64
    assert sorted(s.keys()) == ["step1/n_ps", "step1/ph"] and s.done_steps() == ["step1"]
    with pytest.raises(StoreError, match="not in schema"):
        s.write("step9/x", 1)
    with pytest.raises(StoreError, match="2-D"):
        s.write("step1/ph", np.zeros(3))
    other = StateSchema.of("geoeyes.other", 1, SCHEMA.vars.values())
    with pytest.raises(StoreError, match="schema"):
        StateStore(tmp_path / "state.h5", other).write("step1/n_ps", 1)


def test_points_and_timeseries(tmp_path):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point
    gdf = gpd.GeoDataFrame({"point_uid": ["a", "b", "c"], "vel_los_mm_yr": [1.0, -2.0, 0.5]},
                           geometry=[Point(-99.0, 19.35), Point(-99.01, 19.36), Point(-98.99, 19.34)], crs=4326)
    p = write_points(tmp_path / "points.parquet", gdf, metadata={"product": "x"})
    back = read_points(p)
    assert list(back.point_uid) == ["a", "b", "c"] and back.crs.to_epsg() == 4326
    with pytest.raises(StoreError):
        write_points(tmp_path / "bad.parquet", gdf.assign(point_uid=["a", "a", "b"]))

    dates = np.array(["2024-05-03", "2024-05-15"], dtype="datetime64[D]")
    disp = np.array([[0, 1], [0, -2], [0, 0.5]], np.float32)
    t = write_timeseries(tmp_path / "ts.parquet", ["b", "a", "c"], dates, disp)
    df = read_timeseries(t, point_uids=["a"])
    assert df.disp_mm.tolist() == [0.0, -2.0]
    uid, d, m = timeseries_matrix(read_timeseries(t))
    assert list(uid) == ["a", "b", "c"] and m[1, 1] == 1.0 and d[1] == dates[1]


def test_cog_roundtrip(tmp_path):
    pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    arr = np.arange(600 * 400, dtype=np.float32).reshape(600, 400)
    arr[0, 0] = np.nan
    p = write_cog(tmp_path / "v.tif", arr, from_origin(-99.1, 19.4, 1e-4, 1e-4), units="mm/yr")
    back, meta = read_raster(p)
    assert np.isnan(back[0, 0]) and back[5, 5] == arr[5, 5] and meta["units"] == "mm/yr"
