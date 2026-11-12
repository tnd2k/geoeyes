"""Stack quality check: a well coregistered date shows high coherence and no offset; a date left 40 lines away (the
Umbra case before the coarse offset) shows the offset and a low coherence; the images are written."""
import numpy as np

from geoeyes.io.stack import StackStore
from geoeyes.processing.stack.qc import stack_qc


def test_stack_qc_flags_a_misregistered_date(tmp_path):
    rng = np.random.default_rng(0)
    ny, nx = 1200, 1000
    scene = np.ones((ny + 80, nx))
    for _ in range(1500):
        r, c = rng.integers(0, ny + 60), rng.integers(0, nx - 20)
        scene[r:r + rng.integers(3, 15), c:c + rng.integers(3, 15)] += rng.uniform(5, 30)
    refl = np.sqrt(scene) * (rng.normal(size=scene.shape) + 1j * rng.normal(size=scene.shape))   # one reflectivity
    ramp = np.exp(1j * np.linspace(0, 6 * np.pi, nx))[None, :]                                    # a fringe pattern

    def date(shift, noise):
        a = refl[shift:shift + ny] * ramp
        return (a + noise * (rng.normal(size=a.shape) + 1j * rng.normal(size=a.shape))).astype(np.complex64)
    slc = np.stack([date(0, 0.0), date(0, 0.3), date(40, 0.3)])
    st = StackStore.create(tmp_path / "s" / "stack.zarr",
                           coords={"date": np.array(["2025-01-01", "2025-01-12", "2025-01-23"], dtype="datetime64[D]"),
                                   "y": np.arange(ny), "x": np.arange(nx)},
                           attrs={"reference_date": "2025-01-01", "azimuth_pixel_spacing_m": 0.5,
                                  "range_pixel_spacing_m": 0.5})
    st.write("slc", slc, ("date", "y", "x"))
    st.write("bperp", np.array([0.0, 120.0, -80.0], np.float32), ("date",))
    s = stack_qc(tmp_path / "s" / "stack.zarr", size=300, crop=512)
    good, bad = s["dates"][1], s["dates"][2]
    assert s["dates"][0]["reference"] and not good["reference"]
    assert good["coherence_mean"] > 0.6 and abs(good["offset_lines"]) < 0.2 and abs(good["offset_samples"]) < 0.2
    assert bad["coherence_mean"] < 0.3 and abs(abs(bad["offset_lines"]) - 40) <= 1
    for k in ("amp", "ifg", "coh"):
        assert (tmp_path / "s" / "qc" / f"{k}_2025-01-12.png").exists()
    assert (tmp_path / "s" / "qc" / "qc.json").exists()


def test_small_stack_coherence_is_not_one_on_noise(tmp_path):
    """A stack smaller than the image size used to get 1 x 1 looks: the coherence of one pixel is 1 whatever the
    data (hp_maychai, 513 x 1537 Sentinel-1 pixels). The looks never drop below MIN_LOOKS."""
    from geoeyes.processing.stack.qc import MIN_LOOKS
    rng = np.random.default_rng(2)
    ny, nx = 256, 768
    noise = lambda: (rng.normal(size=(ny, nx)) + 1j * rng.normal(size=(ny, nx))).astype(np.complex64)  # noqa: E731
    ref = noise()
    slc = np.stack([ref, noise(), ref * np.exp(0.3j)])               # reference, unrelated date, the same scene
    slc[:, :, :192] = 0                                              # zero padding (no data) is not 0 coherence
    st = StackStore.create(tmp_path / "s" / "stack.zarr",
                           coords={"date": np.array(["2025-01-01", "2025-01-13", "2025-01-25"], dtype="datetime64[D]"),
                                   "y": np.arange(ny), "x": np.arange(nx)},
                           attrs={"reference_date": "2025-01-01", "azimuth_pixel_spacing_m": 14.0,
                                  "range_pixel_spacing_m": 2.33, "incidence_deg": 39.0})
    st.write("slc", slc, ("date", "y", "x"))
    s = stack_qc(tmp_path / "s" / "stack.zarr", size=1200, crop=256)
    (ly, lx), (wy, wx) = s["looks"], s["coherence_window"]
    assert (ly, lx) == (1, 4) and s["image_shape"] == [ny, nx // 4]  # square ground cells (14 x 14.8 m), no coarser
    assert ly * lx * wy * wx >= MIN_LOOKS and (wy, wx) == (2, 2)     # 2 x 8 pixels, about 28 x 30 m
    from PIL import Image
    assert Image.open(tmp_path / "s" / "qc" / "ifg_2025-01-13.png").size == (nx // 4, ny)
    unrelated, same = s["dates"][1], s["dates"][2]
    assert unrelated["coherence_mean"] < 0.35                        # noise floor of 16 looks, about 0.22
    assert same["coherence_mean"] > 0.99


def test_map_flips_by_heading():
    from geoeyes.processing.stack.qc import map_flips
    assert map_flips({"heading_deg": -168.0, "look_side": "right"}) == (False, True)   # descending: east was left
    assert map_flips({"heading_deg": -12.0, "look_side": "right"}) == (True, False)    # ascending: north was down
    assert map_flips({"heading_deg": -12.0, "look_side": "left"}) == (True, True)
    assert map_flips({}) == (False, False)


def test_stack_images_read_like_a_map(tmp_path):
    """Descending Sentinel-1: line 0 is north, sample 0 (near range) is east, so the images are turned left-right;
    the side taken from the stack's own lat / lon grid. A bright easternmost column must end up on the right."""
    from PIL import Image
    rng = np.random.default_rng(3)
    ny, nx = 64, 96
    base = (rng.normal(size=(ny, nx)) + 1j * rng.normal(size=(ny, nx))).astype(np.complex64)
    base[:, :8] *= 30                                                 # bright near range = east
    slc = np.stack([base, base * np.exp(0.5j)])
    lat = np.repeat(np.linspace(20.90, 20.84, ny)[:, None], nx, 1)    # rows run north -> south
    lon = np.repeat(np.linspace(106.72, 106.66, nx)[None, :], ny, 0)  # columns run east -> west
    st = StackStore.create(tmp_path / "s" / "stack.zarr",
                           coords={"date": np.array(["2025-01-01", "2025-01-13"], dtype="datetime64[D]"),
                                   "y": np.arange(ny), "x": np.arange(nx)},
                           attrs={"reference_date": "2025-01-01", "azimuth_pixel_spacing_m": 14.0,
                                  "range_pixel_spacing_m": 2.33, "incidence_deg": 39.0, "heading_deg": 12.0})
    st.write("slc", slc, ("date", "y", "x"))
    st.write("geometry_lat", lat.astype(np.float32), ("y", "x"))
    st.write("geometry_lon", lon.astype(np.float32), ("y", "x"))
    s = stack_qc(tmp_path / "s" / "stack.zarr", size=96, crop=64)
    assert s["image_flips"] == {"rows": False, "columns": True}       # the grid wins over the (wrong) heading
    assert "left-right" in s["orientation"]
    img = np.asarray(Image.open(tmp_path / "s" / "qc" / "amp_2025-01-13.png").convert("L"), float)
    assert img[:, -4:].mean() > img[:, :4].mean() + 50               # east (bright) on the right


def test_smooth_phase_keeps_fringes_and_lowers_noise():
    from geoeyes.processing.stack.qc import smooth_phase
    rng = np.random.default_rng(0)
    x = np.arange(200)[None, :].repeat(100, 0)
    truth = np.angle(np.exp(1j * x * 2 * np.pi / 50))              # fringes of 50 px, crossing ±π
    z = np.exp(1j * (truth + rng.normal(0, 1.2, truth.shape)))     # noisy, as distributed scatterers in forest
    err = lambda p: np.abs(np.angle(np.exp(1j * (p - truth))))[10:-10, 10:-10].mean()  # noqa: E731
    assert err(smooth_phase(z, 2.0)) < 0.5 * err(np.angle(z))
    assert np.allclose(smooth_phase(z, 0), np.angle(z))


def test_unwrap_grid_qc_writes_the_grid_phase_and_its_jumps(tmp_path):
    """A smooth phase on the unwrapping grid has few jumps between neighbours, noise about half."""
    from types import SimpleNamespace

    from geoeyes.processing.stack.qc import unwrap_grid_qc
    rng = np.random.default_rng(1)
    n_i, n_j = 40, 50
    ii, jj = np.meshgrid(np.arange(n_i), np.arange(n_j), indexing="ij")
    keep = rng.random(ii.shape) < 0.8
    i, j = ii[keep], jj[keep]
    smooth = np.exp(1j * 0.05 * j)                                     # a gentle ramp
    noise = np.exp(1j * rng.uniform(-np.pi, np.pi, i.size))
    ph = np.column_stack([np.ones(i.size), smooth, noise]).astype(np.complex64)   # master, smooth, noise
    grid = SimpleNamespace(ph=ph, ij=np.column_stack([i, j]), n_i=n_i, n_j=n_j)
    s = unwrap_grid_qc(grid, ["2020-01-01", "2020-01-13", "2020-01-25"], 0, [0, 1, 2], tmp_path, label="test")
    jf = {r["date"]: r["jump_frac"] for r in s["dates"]}
    assert jf["2020-01-13"] < 0.05 and 0.35 < jf["2020-01-25"] < 0.65
    assert (tmp_path / "uw_2020-01-13.png").exists() and (tmp_path / "uw_qc.json").exists()
    assert "2020-01-01" not in jf                                       # the master is not an interferogram


def test_unwrap_grid_image_north_up_when_the_frame_is_turned():
    """The load step may turn the points' frame by ~168° (ascending S1): north then sits at the first grid row and
    east at the first column; the image is reversed both ways. Unturned frame: rows only (row 0 = south)."""
    from geoeyes.processing.stack.qc import grid_map_flips
    rng = np.random.default_rng(0)
    lon, lat = 105 + rng.random(500) * 0.1, 20.6 + rng.random(500) * 0.1
    turned = np.column_stack([1 + (20.7 - lat) * 1000, 1 + (105.1 - lon) * 1000])    # row grows south, col west
    assert grid_map_flips(turned, np.column_stack([lon, lat])) == (False, True)
    plain = np.column_stack([1 + (lat - 20.6) * 1000, 1 + (lon - 105) * 1000])
    assert grid_map_flips(plain, np.column_stack([lon, lat])) == (True, False)
    assert grid_map_flips(plain, None) == (True, False)
