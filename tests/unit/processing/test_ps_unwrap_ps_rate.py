"""PS rate model (unwrap/ps_rate.py): a 30 m wide subsiding strip through stable PS is recovered from the wrapped
phase of the PS network, and arcs / integration behave."""
import numpy as np

from geoeyes.processing.ps.unwrap.ps_rate import anchor_parts, closed_arcs, delaunay_arcs, delaunay_network, integrate_l1, ps_rate_model

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


def test_unchecked_arcs_and_small_parts_get_no_rate():
    # a stable scene where some PS are almost pure noise: a noise arc that passes the chance test reaches a pendant
    # PS or an isolated pair with no closing triangle; it used to become a fake rate up to rate_max
    rng = np.random.default_rng(0)
    n, n_ifg = 20000, 98
    xy = rng.uniform(0, 4000, size=(n, 2))
    t = (np.arange(n_ifg) - n_ifg // 2) * 12 / 365.25
    sig = np.where(rng.random(n) < 0.3, 2.5, 0.6)
    ph = np.exp(1j * rng.normal(0, 1, (n, n_ifg)) * sig[:, None])
    r = ps_rate_model(ph, xy, t, 4 * np.pi / LAM * 0.1)
    v = np.abs(r) * LAM / (4 * np.pi) * 1e3
    assert v.max() < 8.0                                        # was 100 mm/yr (pendants, pairs)


def test_closed_arcs_rejects_inconsistent_triangle():
    arcs, tri = delaunay_network(np.array([[0, 0], [10, 0], [0, 10], [10, 10]], float), 100.0)
    assert tri.shape == (2, 3)
    rate = np.zeros(arcs.shape[0])
    ok = np.ones(arcs.shape[0], bool)
    assert closed_arcs(tri, rate, ok, 0.1).all()
    lone = tri[0, 0] if tri[0, 0] not in tri[1] else tri[0, 1]   # a side of triangle 0 only
    rate[lone] = 5.0
    out = closed_arcs(tri, rate, ok, 0.1)
    assert not out[lone] and not out[tri[0]].all() and out[tri[1]].all()


def test_part_across_a_river_is_tied_to_the_main_part():
    # left bank (large part) stable; a 600 m river (> max_arc, no arcs); right bank: half stable, half -20 mm/yr.
    # A zero-mean right bank would put its stable PS at +10 mm/yr; tied to the left bank they stay at 0
    rng = np.random.default_rng(3)
    left = np.c_[rng.uniform(0, 1000, 6000), rng.uniform(0, 1000, 6000)]
    right = np.c_[rng.uniform(1600, 2000, 2400), rng.uniform(0, 1000, 2400)]
    xy = np.vstack([left, right])
    sub = np.r_[np.zeros(len(left), bool), right[:, 1] > 500]
    t = (np.arange(98) - 49) * 12 / 365.25
    v = np.where(sub, -20.0, 0.0)
    ph = np.exp(1j * (-4 * np.pi / LAM * 1e-3 * np.outer(v, t) + rng.normal(0, 0.6, (len(xy), 98))))
    r = ps_rate_model(ph, xy, t, 4 * np.pi / LAM * 0.1)
    v_hat = -r * LAM / (4 * np.pi) * 1e3
    v_hat -= np.median(v_hat[: len(left)])
    right_stable = np.r_[np.zeros(len(left), bool), right[:, 1] <= 500]
    assert abs(np.median(v_hat[right_stable])) < 1.5
    assert abs(np.median(v_hat[sub]) - (-20.0)) < 1.5


def test_anchor_drops_far_parts():
    arcs = np.array([[0, 1], [1, 2], [0, 2], [3, 4], [4, 5], [3, 5]])
    xy = np.array([[0, 0], [10, 0], [0, 10], [5000, 0], [5010, 0], [5000, 10]], float)
    x = np.array([1.0, 1.0, 1.0, 7.0, 7.0, 7.0])
    out, keep, n_anch, n_drop = anchor_parts(x, arcs[:3], xy, 100.0)
    assert keep[:3].all() and not keep[3:].any() and n_drop == 0
    out, keep, n_anch, n_drop = anchor_parts(x, arcs, xy, 100.0)
    assert n_drop == 1 and np.all(out[3:] == 0) and np.all(out[:3] == 1.0)


def test_l1_ignores_one_bad_arc():
    # chain 0-1-2-3 plus closing arcs; one arc wrong by a lot
    arcs = np.array([[0, 1], [1, 2], [2, 3], [0, 2], [1, 3], [0, 3]])
    x_true = np.array([0.0, 1.0, 2.0, 3.0])
    r = x_true[arcs[:, 1]] - x_true[arcs[:, 0]]
    r[1] += 10.0
    x = integrate_l1(arcs, r, 5, iters=10)
    x = x[:4] - x[0]
    assert np.allclose(x, x_true, atol=0.2)
