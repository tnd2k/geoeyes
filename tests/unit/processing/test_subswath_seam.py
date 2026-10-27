"""Phase step across a subswath seam (geoeyes.processing.stack.native.s1_stack.seam_step)."""
import numpy as np

from geoeyes.processing.stack.native.s1_stack import SEAM_REACH, seam_step


def test_step_is_measured_under_noise_and_a_smooth_signal():
    rng = np.random.default_rng(1)
    ny, nx = 640, 2 * SEAM_REACH
    yy, xx = np.mgrid[0:ny, 0:nx]
    phase = 0.0005 * xx +2.0 * np.sin(yy / 90.0) + rng.normal(0, 0.8, (ny, nx))
    phase[:, SEAM_REACH:] += -2.2
    amp = rng.rayleigh(1.0, (ny, nx))
    strip = (amp * np.exp(1j * phase)).astype(np.complex64)
    strip[:96] = 0                                       # rows outside the bursts
    step, consistency, n = seam_step(strip)
    assert abs(step + 2.2) < 0.1 and consistency > 0.8 and n == 17


def test_no_data_gives_no_step():
    assert seam_step(np.zeros((64, 2 * SEAM_REACH), np.complex64)) == (0.0, 0.0, 0)
