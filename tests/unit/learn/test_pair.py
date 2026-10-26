"""Learning path (geoeyes.learn): on a synthetic flattened stack, the rebuilt geometric phase gives back the raw
interferogram, and a 20 mm sinking bowl (more than one fringe at X band) is unwrapped and converted to −20 mm."""
import numpy as np
import pytest

from geoeyes.io.stack import StackStore
from geoeyes.learn import PairParams, overview, pair_layers
from geoeyes.learn.pair import flat_earth_phase, multilook, residues

LAM = 0.031
N = 128


def _stack(tmp_path):
    rng = np.random.default_rng(0)
    dates = np.array(["2020-01-01", "2020-01-17", "2020-02-02"], dtype="datetime64[ns]")
    y, x = np.mgrid[0:N, 0:N].astype(float)
    inc = np.full((N, N), 30.0)
    rng_m = 700_000.0 + x * 1.0
    hgt = 15 * np.sin(x / 20) * np.cos(y / 25)
    bperp = np.array([0.0, 100.0, -50.0])
    kh = np.stack([4 * np.pi * b / (LAM * rng_m * np.sin(np.radians(inc))) for b in bperp])
    # a sinking bowl between date 0 and date 1: range increase d (m)
    d = np.zeros((3, N, N))
    d[1] = 0.020 * np.exp(-((y - 64) ** 2 + (x - 64) ** 2) / (2 * 18.0 ** 2))
    psi = rng.uniform(-np.pi, np.pi, (N, N))                       # the scatterers' own phase, common to all dates
    amp = rng.rayleigh(1.0, (N, N)) + 0.5
    # GeoEyes convention: slc_i · conj(slc_j) is the differential interferogram, range increase → +4πd/λ
    slc = np.stack([amp * np.exp(1j * (psi - 4 * np.pi * d[k] / LAM + rng.normal(0, 0.15, (N, N))))
                    for k in range(3)]).astype(np.complex64)
    s = StackStore.create(tmp_path / "stack.zarr", coords={"date": dates, "y": np.arange(N), "x": np.arange(N)},
                          attrs={"reference_date": "2020-01-01", "wavelength_m": LAM, "azimuth_pixel_spacing_m": 2.0,
                                 "range_pixel_spacing_m": 1.0, "sensor": "test", "track": "test-asc"})
    s.write("slc", slc, ("date", "y", "x"))
    s.write("kh", kh.astype(np.float32), ("date", "y", "x"))
    s.write("bperp", bperp, ("date",))
    for k, v in {"hgt": hgt, "incidence": inc, "slant_range": rng_m, "lat": 21 + y * 1e-5, "lon": 105 + x * 1e-5}.items():
        s.write(f"geometry_{k}", v.astype(np.float32), ("y", "x"))
    return tmp_path / "stack.zarr"


def test_pair_layers_rebuild_and_unwrap(tmp_path):
    sp = _stack(tmp_path)
    ov = overview(sp)
    assert ov["default"]["first"] == "2020-01-01" and ov["default"]["second"] == "2020-01-17"
    p = PairParams(first="2020-01-01", second="2020-01-17", row0=0, col0=0, rows=N, cols=N, looks_az=2,
                   looks_rg=2, alpha=0.5)
    meta, L = pair_layers(sp, p)
    assert meta["shape"] == [64, 64] and abs(meta["bperp_m"] - 100) < 1e-6
    # raw − (flat + topo) = differential, exactly by construction
    back = np.angle(np.exp(1j * (L["raw"] - L["flat"] - L["topo"] - L["diff"])))
    assert np.abs(back).max() < 1e-3
    # the raw fringes are those of the flat earth predicted from kh and the incidence
    assert meta["fringes_per_km"]["raw"] == pytest.approx(meta["flat_fringes_per_km_range"], rel=0.1)
    # the bowl: 20 mm away from the satellite at the centre, 0 far from it
    assert meta["coherence_median"] > 0.8
    assert L["disp"][32, 32] == pytest.approx(-20.0, abs=1.5)
    assert abs(float(np.median(L["disp"][:6, :6]))) < 1.5
    assert meta["mm_per_fringe"] == pytest.approx(LAM / 2 * 1000)


def test_flat_earth_multilook_residues():
    kh = np.full((4, 50), 0.3)
    inc = np.full((4, 50), 30.0)
    r = 700_000.0 + np.arange(50)[None, :] * np.ones((4, 1)) * 2.0
    phi = flat_earth_phase(kh, inc, r)
    np.testing.assert_allclose(np.diff(phi, axis=1), 0.3 * np.cos(np.radians(30)) * 2.0, rtol=1e-6)
    assert phi[2, 25] == pytest.approx(0.0)
    np.testing.assert_allclose(multilook(np.arange(16.0).reshape(4, 4), 2, 2), [[2.5, 4.5], [10.5, 12.5]])
    y, x = np.mgrid[0:21, 0:21] - 10.3
    assert np.abs(residues(np.arctan2(y, x))).sum() == 1                   # one vortex, one residue
    assert np.abs(residues(np.angle(np.exp(1j * 0.4 * x)))).sum() == 0     # a ramp has none
