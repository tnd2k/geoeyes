import numpy as np
import pytest
from scipy.stats import ks_2samp

from geoeyes.processing.phase_linking import estimators
from geoeyes.processing.phase_linking.runner import PhaseLinkingParams, link_tile
from geoeyes.processing.phase_linking.shp import ks_critical, shp_mask, window_offsets


def test_shp_mask_matches_scipy_ks():
    rng = np.random.default_rng(0)
    n, H, W = 16, 9, 10
    amp = rng.rayleigh(1.0, (n, H, W)).astype(np.float32)
    amp[:, :, 5:] *= 3.0                                     # two populations
    amp[:, 4, 2] = 0                                         # no data
    hw = (2, 3)
    mask = shp_mask(amp, hw, 0.05, test="ks")
    off = window_offsets(hw)
    crit = ks_critical(0.05, n)
    for y in range(H):
        for x in range(W):
            for i, (dy, dx) in enumerate(off):
                yy, xx = y + dy, x + dx
                if (dy, dx) == (0, 0):
                    expect = bool(amp[:, y, x].any())
                elif not (0 <= yy < H and 0 <= xx < W) or not amp[:, y, x].any() or not amp[:, yy, xx].any():
                    expect = False
                else:
                    expect = ks_2samp(amp[:, y, x], amp[:, yy, xx]).statistic <= crit + 1e-9
                assert mask[y, x, i] == expect, (y, x, dy, dx)


def test_anderson_darling_matches_scipy():
    import warnings

    from scipy.stats import anderson_ksamp

    from geoeyes.processing.phase_linking.shp import ad_critical, ad_standardized
    rng = np.random.default_rng(5)
    for n in (8, 15, 30):
        for scale in (1.0, 1.3, 2.5):
            a, b = rng.rayleigh(1.0, n), rng.rayleigh(scale, n)
            merged = np.sort(np.r_[a, b])
            from_a = np.isin(merged, a)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ref = anderson_ksamp([a, b], midrank=False)
            np.testing.assert_allclose(ad_standardized(from_a[None], n)[0], ref.statistic, rtol=1e-4, atol=1e-5)
    assert abs(ad_critical(0.05) - 1.961) < 1e-3 and abs(ad_critical(0.01) - 3.752) < 1e-3


def test_shp_mask_ad_flags_the_other_population():
    rng = np.random.default_rng(6)
    amp = rng.rayleigh(1.0, (20, 9, 10)).astype(np.float32)
    amp[:, :, 5:] *= 3.0
    m = shp_mask(amp, (2, 2), 0.05, test="ad")
    off = window_offsets((2, 2))
    right = off[:, 1] == 2                                   # neighbours two columns to the right
    assert m[4, 4, right].mean() < 0.2 and m[4, 1, right].mean() > 0.6     # across vs within the edge


def synthetic_coherence(theta, gamma, looks, rng):
    n = theta.size
    T = gamma ** np.abs(np.subtract.outer(np.arange(n), np.arange(n)))   # exponential decorrelation
    Cs = T * np.exp(1j * np.subtract.outer(theta, theta))
    L = np.linalg.cholesky(Cs + 1e-9 * np.eye(n))
    z = (rng.standard_normal((n, looks)) + 1j * rng.standard_normal((n, looks))) / np.sqrt(2)
    return (L @ z)[None]                                                 # (1, n, looks)


@pytest.mark.parametrize("estimator", ["evd", "emi", "pta", "adaptive"])
def test_estimators_recover_phase(estimator):
    rng = np.random.default_rng(1)
    n, ref = 12, 4
    theta = rng.uniform(-np.pi, np.pi, n)
    S = np.concatenate([synthetic_coherence(theta, 0.9, 200, rng) for _ in range(8)])
    C = estimators.coherence(S.astype(np.complex64), np.ones(S.shape[::2], bool))
    v = estimators.link(C, estimator, ref)
    assert np.allclose(v[:, ref], 1)
    err = np.angle(v * np.exp(-1j * (theta - theta[ref])))
    assert np.max(np.abs(err)) < 0.3 and np.mean(np.abs(err)) < 0.1     # far epochs decorrelate (0.9^11)
    assert np.all(estimators.temporal_coherence(C, v) > 0.5)


def test_link_tile_keeps_reference_and_amplitude():
    rng = np.random.default_rng(2)
    n, ref, H, W = 10, 3, 24, 24
    theta = rng.uniform(-np.pi, np.pi, n)
    slc = (rng.rayleigh(1.0, (n, H, W)) * np.exp(1j * (theta[:, None, None]
           + 0.8 * rng.standard_normal((n, H, W))))).astype(np.complex64)
    p = PhaseLinkingParams(estimator="evd", half_window=(3, 3), min_shp=10)
    out, count, tcoh = link_tile(slc, (slice(3, 21), slice(3, 21)), ref, p)
    inner = slc[:, 3:21, 3:21]
    np.testing.assert_allclose(np.abs(out), np.abs(inner), rtol=1e-5)
    np.testing.assert_allclose(out[ref], inner[ref], rtol=1e-5, atol=1e-6)
    linked = np.isfinite(tcoh)
    assert linked.mean() > 0.9 and np.all(count[linked] >= 10)
    ifg_old = np.angle(inner[ref] * np.conj(inner)) + (theta - theta[ref])[:, None, None]
    ifg_new = np.angle(out[ref] * np.conj(out)) + (theta - theta[ref])[:, None, None]
    spread = (lambda a: np.abs(np.angle(np.exp(1j * a)))[:, linked].mean())  # noqa: E731
    assert spread(ifg_new) < 0.5 * spread(ifg_old)


def test_gaussian_postfilter_leaves_ps(tmp_path):
    from geoeyes.io.stack import StackStore
    from geoeyes.processing.phase_linking.runner import run
    rng = np.random.default_rng(4)
    n, H, W = 6, 20, 24
    dates = np.array(["2020-01-01", "2020-01-13", "2020-01-25", "2020-02-06", "2020-02-18", "2020-03-01"],
                     "datetime64[D]")
    st = StackStore.create(tmp_path / "s.zarr", coords={"date": dates, "y": np.arange(H), "x": np.arange(W)},
                           attrs={"reference_date": "2020-01-25"})
    slc = (rng.rayleigh(1.0, (n, H, W)) * np.exp(1j * rng.uniform(-np.pi, np.pi, (n, H, W)))).astype(np.complex64)
    slc[:, 10, 12] = 5.0 * np.exp(1j * rng.uniform(-np.pi, np.pi, n))           # bright PS (D_A = 0)
    st.write("slc", slc, ("date", "y", "x"))
    run(st, PhaseLinkingParams(half_window=(2, 2), min_shp=5, tile_size=16, gaussian_sigma=1.5))
    out = st.read("slc_linked")
    np.testing.assert_allclose(out[:, 10, 12], slc[:, 10, 12], rtol=1e-6)        # PS untouched
    linked = np.isfinite(st.read("pl_temporal_coherence"))
    assert linked.mean() > 0.8 and not linked[10, 12]
    np.testing.assert_allclose(np.abs(out), np.abs(slc), rtol=1e-5)             # amplitudes kept


def test_link_tile_keeps_ps():
    rng = np.random.default_rng(3)
    n, H, W = 10, 16, 16
    slc = (rng.rayleigh(1.0, (n, H, W)) * np.exp(1j * rng.uniform(-np.pi, np.pi, (n, H, W)))).astype(np.complex64)
    slc[:, 8, 8] = 1.0 * np.exp(1j * rng.uniform(-np.pi, np.pi, n))             # constant amplitude: D_A = 0
    out, _, tcoh = link_tile(slc, (slice(3, 13), slice(3, 13)), 0, PhaseLinkingParams(half_window=(3, 3), min_shp=0))
    np.testing.assert_array_equal(out[:, 5, 5], slc[:, 8, 8])
    assert np.isnan(tcoh[5, 5]) and np.isfinite(tcoh).sum() > 90
