"""Interpolation kernels of the native stacks (geoeyes.processing.stack.native.common.interpolate)."""
import numpy as np
import pytest

from geoeyes.processing.stack.native.common import interpolate


def _bandlimited(n, bandwidth, rng):
    """A complex 2D signal limited to |f| <= bandwidth / 2 cycles per sample on both axes (Hamming-weighted, as
    a focused SLC after the carrier is removed) and its exact value at any position."""
    f = np.fft.fftfreq(n)
    w = np.where(np.abs(f) <= bandwidth / 2, 0.75 + 0.25 * np.cos(2 * np.pi * f / bandwidth), 0.0)
    spec = np.outer(w, w) * (rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n)))
    z = np.fft.ifft2(spec)

    def exact(y, x):
        ey = np.exp(2j * np.pi * np.outer(y, f))
        ex = np.exp(2j * np.pi * np.outer(x, f))
        return np.einsum("pi,ij,pj->p", ey, spec, ex) / n / n
    return z, exact


def _loss(a, b):
    return 1 - abs(np.vdot(b, a)) / np.sqrt(np.vdot(a, a).real * np.vdot(b, b).real)


@pytest.fixture(scope="module")
def case():
    rng = np.random.default_rng(3)
    z, exact = _bandlimited(128, 1 / 1.2, rng)                # CSK-like oversampling 1.2
    y, x = rng.uniform(20, 108, 400), rng.uniform(20, 108, 400)
    return z, y, x, exact(y, x)


def test_lanczos_beats_the_spline(case):
    z, y, x, truth = case
    spline = _loss(interpolate(z, y, x, kernel="spline"), truth)
    l4 = _loss(interpolate(z, y, x, kernel="lanczos", radius=4), truth)
    l8 = _loss(interpolate(z, y, x, kernel="lanczos", radius=8), truth)
    assert l8 < l4 < spline
    assert l8 < 1e-4 and spline > 1e-3


def test_integer_positions_are_the_samples():
    z = (np.arange(64 * 64).reshape(64, 64) * (1 + 0.5j)).astype(np.complex64)
    yy, xx = np.mgrid[10:20, 10:20]
    np.testing.assert_allclose(interpolate(z, yy.astype(float), xx.astype(float), kernel="lanczos"), z[10:20, 10:20],
                               rtol=1e-5)


def test_outside_is_zero_and_chunks_agree(case):
    z, y, x, _ = case
    a = interpolate(z, np.r_[y, -50.0, np.nan], np.r_[x, 3.0, 3.0], kernel="lanczos", radius=6)
    b = interpolate(z, np.r_[y, -50.0, np.nan], np.r_[x, 3.0, 3.0], kernel="lanczos", radius=6, chunk=37)
    assert a[-1] == 0 and a[-2] == 0
    np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-6)
