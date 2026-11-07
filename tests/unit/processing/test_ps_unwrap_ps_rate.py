"""PS rate model (unwrap/ps_rate.py): a 30 m wide subsiding strip through stable PS is recovered from the wrapped
phase of the PS network, and arcs / integration behave."""
import numpy as np

from geoeyes.processing.ps.unwrap.ps_rate import delaunay_arcs, integrate_l1, ps_rate_model

LAM = 0.0555


def _strip_scene(v_strip=-25.0, n_ifg=98, seed=0):
    rng = np.random.default_rng(seed)
    n = 4000
    xy = rng.uniform(0, 1500, size=(n, 2))
    strip = np.abs(xy[:, 0] - 750) < 15                       # 30 m wide road
    t = (np.arange(n_ifg) - n_ifg // 2) * 12 / 365.25          # years from the master (middle)
    v = np.where(strip, v_strip, 0.0)                          # mm/yr
    phase = -4 * np.pi / LAM * 1e-3 * np.outer(v, t) + rng.normal(0, 0.6, (n, n_ifg))
    return xy, t, strip, v, np.exp(1j * phase)


def test_strip_rate_recovered():
    xy, t, strip, v, ph = _strip_scene()
    rate_max = 4 * np.pi / LAM * 0.1                            # 100 mm/yr in rad/yr
    r = ps_rate_model(ph, xy, t, rate_max)
    v_hat = -r * LAM / (4 * np.pi) * 1e3
    v_hat -= np.median(v_hat[~strip])
    assert abs(np.median(v_hat[strip]) - (-25.0)) < 1.5
    assert np.percentile(np.abs(v_hat[~strip]), 90) < 1.5


def test_noise_network_gives_no_model_when_required():
    rng = np.random.default_rng(1)
    xy = rng.uniform(0, 1000, size=(1500, 2))
    t = (np.arange(17) - 8) * 16 / 365.25                       # 17 interferograms, as CSK Hanoi
    ph = np.exp(1j * rng.uniform(-np.pi, np.pi, size=(1500, 17)))
    assert ps_rate_model(ph, xy, t, 4 * np.pi / LAM * 0.1, min_reliable=0.5) is None


def test_arcs_respect_max_length():
    xy = np.array([[0, 0], [10, 0], [0, 10], [1000, 1000]], float)
    arcs = delaunay_arcs(xy, 100.0)
    assert arcs.size and np.all(np.hypot(*(xy[arcs[:, 1]] - xy[arcs[:, 0]]).T) <= 100.0)
    assert 3 not in arcs


def test_l1_ignores_one_bad_arc():
    # chain 0-1-2-3 plus closing arcs; one arc wrong by a lot
    arcs = np.array([[0, 1], [1, 2], [2, 3], [0, 2], [1, 3], [0, 3]])
    x_true = np.array([0.0, 1.0, 2.0, 3.0])
    r = x_true[arcs[:, 1]] - x_true[arcs[:, 0]]
    r[1] += 10.0
    x = integrate_l1(arcs, r, 5, iters=10)
    x = x[:4] - x[0]
    assert np.allclose(x, x_true, atol=0.2)
