"""L4 rain layers: windows, bilinear sampling on pixel centres, phase-randomised surrogates keep the spectrum."""
import numpy as np
import pandas as pd

from geoeyes.landslide import rain


def test_event_layers_windows():
    dates = [d.date().isoformat() for d in pd.date_range("2020-09-28", "2020-10-29")]
    mm = np.ones((len(dates), 2, 3), np.float32)
    k0 = dates.index("2020-10-28")
    mm[k0] = 50.0
    mm[k0 + 1] = 80.0                                   # the day after counts for the maximum only
    lay = rain.event_layers(mm, dates, "2020-10-28")
    assert np.allclose(lay["rain_5d"], 54) and np.allclose(lay["rain_10d"], 59) and np.allclose(lay["rain_30d"], 79)
    assert np.allclose(lay["rain_max1d"], 80)


def test_sample_is_bilinear_between_pixel_centres():
    f = np.array([[0.0, 10.0], [0.0, 10.0]])
    box = (100.0, 10.0, 100.1, 10.1)                    # 2 x 2 pixels of 0.05°
    centres = rain.sample(f, box, np.array([100.025, 100.075]), np.array([10.075, 10.025]))
    assert np.allclose(centres, [0.0, 10.0])
    assert np.isclose(rain.sample(f, box, np.array([100.05]), np.array([10.05]))[0], 5.0)


def test_phase_randomised_keeps_mean_and_spectrum():
    rng = np.random.default_rng(0)
    y, x = np.mgrid[0:16, 0:24]
    a = 100 + 20 * np.sin(x / 4.0) + rng.normal(0, 2, x.shape)
    stack = np.stack([a, 2 * a])
    s = rain.phase_randomised(stack, rng)
    assert np.allclose(s.mean(axis=(1, 2)), stack.mean(axis=(1, 2)))
    amp = lambda z: np.abs(np.fft.fft2(z - z.mean()))   # noqa: E731
    assert np.allclose(amp(s[0]), amp(stack[0]), rtol=1e-6, atol=1e-6)
    assert np.allclose(s[1], 2 * s[0])                  # the same phases: the layers keep their relation
    assert not np.allclose(s[0], stack[0])
