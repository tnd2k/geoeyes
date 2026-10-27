"""Range split-spectrum ionospheric estimate (geoeyes.processing.stack.native.iono)."""
import numpy as np

from geoeyes.processing.stack.native import iono

F0 = 5.405e9
B = 42.8e6
FS = 64.345e6


def test_bandpass_keeps_its_band_only():
    n = np.arange(512)
    inside = np.exp(2j * np.pi * (-B / 3) * n / FS)
    outside = np.exp(2j * np.pi * (B / 3) * n / FS)
    x = np.tile(inside + outside, (4, 1))
    y = iono.bandpass(x, -B / 3, B / 3, FS)
    assert np.allclose(y[:, 100:400], np.tile(inside, (4, 1))[:, 100:400], atol=0.05)


def test_dispersive_surface_is_recovered_and_evaluated_on_the_crop():
    rng = np.random.default_rng(0)
    ny, nx = 660, 2460                                    # 20 x 20 cells of 33 x 123 looks
    yy, xx = np.mgrid[0:ny, 0:nx]
    sp = (14.0, 3.7)                                      # m per pixel (azimuth, ground range)
    yk, xk = yy * sp[0] / 1000, xx * sp[1] / 1000
    iono_true = 0.8 * yk - 0.3 * xk + 0.02 * yk * yk     # rad at f0, quadratic
    nondisp = 3.0 * np.sin(xk / 2.0) + 1.5 * yk           # motion, troposphere: scale with f
    fl, fh, _ = iono.subbands(F0, B)
    noise = lambda: rng.normal(0, 0.3, (ny, nx))          # noqa: E731
    low = np.exp(1j * (nondisp * fl / F0 + iono_true * F0 / fl + noise())).astype(np.complex64)
    high = np.exp(1j * (nondisp * fh / F0 + iono_true * F0 / fh + noise())).astype(np.complex64)
    area = iono.WideArea((0, ny), (0, nx), (33, 123))
    area.add(low[:300], high[:300], 0, 0, (0, ny), (0, nx))             # added in two blocks of lines
    area.add(low[300:], high[300:], 300, 0, (0, ny), (0, nx))
    crop = (slice(200, 400), slice(800, 1600))
    est, info = iono.estimate_wide(area, F0, B, spacing_m=sp, rows=(200, 400), cols=(800, 1600),
                                   min_cross_coherence=0.5)
    d = est - iono_true[crop]
    assert np.std(d) < 0.3, info                          # up to a constant
    gy, gx = info["rad_per_km_az_rg"]
    yc = yk[crop].mean()
    assert abs(gy - (0.8 + 0.04 * yc)) < 0.1 and abs(gx + 0.3) < 0.1, info


def test_subswath_step_is_shifted_out_of_the_ionosphere():
    rng = np.random.default_rng(2)
    ny, nx = 660, 2460
    yy, xx = np.mgrid[0:ny, 0:nx]
    sp = (14.0, 3.7)
    yk, xk = yy * sp[0] / 1000, xx * sp[1] / 1000
    iono_true = 0.5 * yk + 0.2 * xk                         # rad at f0
    c = np.where(xx >= 1599, -2.2, 0.0)                     # constant of the right subswath, same in both bands
    fl, fh, _ = iono.subbands(F0, B)
    noise = lambda: rng.normal(0, 0.3, (ny, nx))            # noqa: E731
    low = np.exp(1j * (c + iono_true * F0 / fl + noise())).astype(np.complex64)
    high = np.exp(1j * (c + iono_true * F0 / fh + noise())).astype(np.complex64)
    area = iono.WideArea((0, ny), (0, nx), (33, 123))
    area.add(low, high, 0, 0, (0, ny), (0, 1599), part=0)
    area.add(low, high, 0, 0, (0, ny), (1599, nx), part=1)
    rows, cols = (200, 400), (800, 2400)
    kw = dict(spacing_m=sp, rows=rows, cols=cols, model="plane", min_cross_coherence=0.5)
    truth = iono_true[rows[0]:rows[1], cols[0]:cols[1]]
    est, info = iono.estimate_wide(area, F0, B, **kw)
    assert np.std(est - truth) > 0.2, info                  # a·c of the step passes into the ionosphere
    area.shift({1: -2.2})
    est, info = iono.estimate_wide(area, F0, B, **kw)
    assert np.std(est - truth) < 0.1, info                  # no step left in the ionosphere
