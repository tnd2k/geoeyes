"""Terrain coregistration model: a secondary displaced by an offset growing with height (and a ramp) is recovered
from the amplitude tiles, where one constant would leave a scatter of the size of the height term."""
import numpy as np
from scipy.ndimage import map_coordinates

from geoeyes.processing.stack.native.stripmap import residual_model


def test_height_dependent_offset_recovered():
    rng = np.random.default_rng(3)
    ny, nx = 1024, 1024
    # band-limited speckle (an SLC is sampled finer than its resolution): white noise oversampled x2 by FFT
    w = rng.standard_normal((ny // 2, nx // 2)) + 1j * rng.standard_normal((ny // 2, nx // 2))
    spec = np.zeros((ny, nx), complex)
    f = np.fft.fftshift(np.fft.fft2(w))
    spec[ny // 4:ny // 4 + ny // 2, nx // 4:nx // 4 + nx // 2] = f
    ref = np.fft.ifft2(np.fft.ifftshift(spec)).astype(np.complex64)
    yy, xx = np.mgrid[0:ny, 0:nx].astype(np.float64)
    h = 2000.0 + 1500.0 * np.exp(-((yy - 500) ** 2 + (xx - 600) ** 2) / (2 * 250.0**2))     # a volcano, m
    dl = 0.1 + 0.4 * (h / 1e3 - 2.0) + 0.05 * (yy - ny / 2) / 1e3                         # lines
    ds = -0.2 + 0.03 * (xx - nx / 2) / 1e3                                                # samples
    # sec content sits at +offset: sec(l + dl, s + ds) = ref(l, s)
    sec = sum(map_coordinates(part, [yy - dl, xx - ds], order=3, mode="reflect") * u
              for part, u in ((ref.real.astype(np.float64), 1), (ref.imag.astype(np.float64), 1j)))
    m = residual_model(ref, sec, h, tile=96, step=64)
    assert m is not None and m.n_tiles > 100
    hk, lk, sk = h / 1e3, (yy - ny / 2) / 1e3, (xx - nx / 2) / 1e3
    fl, fs = m.field(hk, lk, sk)
    assert np.abs(fl - dl).max() < 0.05 and np.abs(fs - ds).max() < 0.05
    assert abs(m.az[1] - 0.4) < 0.03                     # lines per km of height
    flat = residual_model(ref, sec, np.full_like(h, 100.0), tile=96, step=64)   # no relief: no height term
    assert flat is not None and flat.az[1] == 0.0
