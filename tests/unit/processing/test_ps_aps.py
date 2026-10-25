import numpy as np

from geoeyes.processing.ps.aps import centre_weather, choose_aps, inside_polygon, linear_aps


def test_weather_aps_is_centred_like_the_linear_intercept():
    """Hanoi S1 (2026-10): ERA5 dates kept a scene-wide offset of up to 12 mm in every time series."""
    rng = np.random.default_rng(1)
    n, n_sec, master = 2000, 6, 2
    atm = rng.normal(0, 1, (n, n_sec))
    offset = np.array([3.0, -2.0, 0.5, 4.0, -1.0, 2.5])              # unwrapping constant + model bias
    ph = atm + offset[None, :] + 0.05 * rng.standard_normal((n, n_sec))
    weather = np.insert(atm, master, 0.0, axis=1)                   # right pattern, absolute level differs
    c = centre_weather(ph, weather, master)
    corrected = ph - np.delete(c, master, axis=1)
    np.testing.assert_allclose(corrected.mean(axis=0), 0.0, atol=1e-9)
    assert np.all(c[:, master] == 0) and np.std(corrected) < 0.06
    lin = np.delete(linear_aps(ph, np.zeros(n), master), master, axis=1)
    np.testing.assert_allclose((ph - lin).mean(axis=0), 0.0, atol=1e-9)    # the linear APS already was
    nan = weather.copy()
    nan[:5, 0] = np.nan
    assert np.isnan(centre_weather(ph, nan, master)[:5, 0]).all()


def test_choose_aps_per_interferogram():
    rng = np.random.default_rng(0)
    n, n_sec, master = 3000, 15, 6
    x = rng.uniform(0, 1, n)
    t = np.r_[np.arange(-6, 0), np.arange(1, 10)] * 12.0
    bp = rng.uniform(-100, 100, n_sec)[None, :] * rng.uniform(0.95, 1.05, (n, 1))
    # true atmosphere: a different spatial pattern on every date (a pattern repeated on every date would be a
    # per-PS constant, absorbed by the per-PS fit)
    atm = np.sin(rng.uniform(2, 6, n_sec)[None, :] * x[:, None] + rng.uniform(0, 6, n_sec)[None, :])
    ph = atm + 0.02 * (t / 365.25)[None, :] * rng.normal(0, 30, (n, 1)) + 0.1 * rng.standard_normal((n, n_sec))
    good = rng.random(n_sec) > 0.3
    weather = np.where(good, atm, -atm)                                      # wrong model (sign) on some dates
    linear = np.zeros_like(atm)                                              # a weak linear APS
    ins = (lambda a: np.insert(a, master, 0.0, axis=1))  # noqa: E731
    out, use, var = choose_aps(ph, ins(weather), ins(linear), t, bp, master)
    np.testing.assert_array_equal(use, good)
    np.testing.assert_allclose(np.delete(out, master, axis=1)[:, good], weather[:, good])
    np.testing.assert_allclose(np.delete(out, master, axis=1)[:, ~good], 0.0)
    assert np.all(out[:, master] == 0) and np.all(var[1, good] < var[2, good])


def test_linear_aps_fit_mask_ignores_deforming_area():
    rng = np.random.default_rng(0)
    n = 400
    lonlat = np.column_stack([rng.uniform(0, 1, n), rng.uniform(0, 1, n)])
    h = rng.uniform(0, 500, n)
    k = np.array([2e-3, -1e-3, 3e-3])
    ph = h[:, None] * k[None, :]
    bowl = lonlat[:, 0] > 0.6                                   # deformation correlated with height there
    ph[bowl] += (h[bowl] * 4e-3)[:, None]
    stable = inside_polygon(lonlat, [[0, 0], [0.55, 0], [0.55, 1], [0, 1]])
    assert stable.sum() > 100 and not np.any(stable & bowl)
    aps = linear_aps(ph, h, master_ix=1, fit_mask=stable)
    np.testing.assert_allclose(np.delete(aps, 1, axis=1), h[:, None] * k[None, :], atol=1e-9)
    assert np.all(aps[:, 1] == 0)
    biased = linear_aps(ph, h, master_ix=1)
    assert np.max(np.abs(np.delete(biased, 1, axis=1) - h[:, None] * k[None, :])) > 0.1
