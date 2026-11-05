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
