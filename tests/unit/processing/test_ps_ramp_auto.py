"""D1 of ramp-selection.md: ``scla_deramp = "auto"`` on synthetic scenes."""
from __future__ import annotations

import numpy as np
import pytest

from geoeyes.processing.ps.steps.ramp import (PLANAR_KEPT, RampAutoParams, auto_ramp, fit_planes, seasonal_test,
                                              split_trend)

SIZE = 40.0                    # km
N_PS = 60_000
NOISE = 2.0                    # mm per PS per interferogram
PLANAR = RampAutoParams(allow_planar=True)   # the explicit override: the halves test alone removes a planar trend


def _scene(*, bowl: str = "local", trend=(0.0, 0.0), rest_std: float = 7.0, seasonal: float = 0.0,
           span: float = 0.9, n_ep: int = 24, size: float = SIZE, seed: int = 1):
    """Displacement (n, n_ifg) mm = v·t + ramps + noise; gradients in mm per 10 km."""
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, size, N_PS), rng.uniform(0, size, N_PS)
    ep = np.linspace(-span / 2, span / 2, n_ep)
    t = np.delete(ep, n_ep // 2) - ep[n_ep // 2]                         # master in the middle, not an ifg
    if bowl == "local":                                                  # sharp bowl on a stable background
        v = -100.0 * np.exp(-((x - 12) ** 2 + (y - 25) ** 2) / (2 * 2.0 ** 2))
    elif bowl == "wide":                                                 # bowl wider than the frame
        v = -150.0 * np.exp(-((x - 0.6 * size) ** 2 + (y - 0.4 * size) ** 2) / (2 * 25.0 ** 2))
    else:
        v = np.zeros(N_PS)
    g_rest = rng.normal(0, rest_std, (t.size, 2))
    g_rest[:, 0] += seasonal * np.sin(2 * np.pi * t)
    g = (g_rest + np.outer(t, trend)) / 10.0                             # mm/km
    xc, yc = x - size / 2, y - size / 2
    ramp = np.outer(xc, g[:, 0]) + np.outer(yc, g[:, 1]) + rng.normal(0, 3, t.size)
    d = np.outer(v, t) + ramp + rng.normal(0, NOISE, (N_PS, t.size))
    return x, y, t, v, d, g_rest


def _true_trend(trend, g_rest, t):
    """The trend the data define: the input trend plus the straight line in t of the random ramps themselves
    (with a finite series that line cannot be told apart from a trend)."""
    return np.asarray(trend) + split_trend(g_rest, t)[0]


def _velocity(d, t):
    tc = t - t.mean()
    return d @ tc / (tc @ tc)


def test_fit_planes_and_split():
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 10, 500), rng.uniform(0, 10, 500)
    t = np.linspace(-0.5, 0.5, 9)
    c = np.column_stack([rng.normal(size=9), 0.3 * t + 0.1, -0.2 * t])
    d = c[:, 0] + np.outer(x, c[:, 1]) + np.outer(y, c[:, 2])
    d[3, 2] = np.nan
    np.testing.assert_allclose(fit_planes(x, y, d), c, atol=1e-9)
    slope, rest = split_trend(c, t)
    np.testing.assert_allclose(slope[1:], [0.3, -0.2], atol=1e-12)
    np.testing.assert_allclose(rest[:, 1], 0.1, atol=1e-12)


def test_a_local_bowl_trend_removed():
    """(a) local bowl + random ramps + a trend ramp: trend within 2 mm/yr per 10 km, bowl rate within 5%."""
    x, y, t, v, d, g_rest = _scene(bowl="local", trend=(12.0, -8.0))
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0, params=PLANAR)
    assert r.trend_removed, r.reason
    assert r.frame.consistent and r.frame.quadrants == 4 and r.frame_passed
    np.testing.assert_allclose(10 * r.trend_plane[1:], _true_trend((12.0, -8.0), g_rest, t), atol=2.0)
    vc = _velocity(d - r.ph_ramp, t)
    core, far = np.hypot(x - 12, y - 25) < 0.5, np.hypot(x - 12, y - 25) > 10
    got = np.median(vc[core]) - np.median(vc[far])
    want = np.median(v[core]) - np.median(v[far])
    assert abs(got - want) < 0.05 * abs(want)
    # the background is flat after the correction
    gb = fit_planes(x[far], y[far], vc[far, None])[0]
    assert np.hypot(*gb[1:]) * 10 < 2.0


def test_b_wide_bowl_trend_kept_rest_removed():
    """(b) bowl wider than the frame + random ramps: test fails, trend untouched, rest removed."""
    x, y, t, v, d, g_rest = _scene(bowl="wide")
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0)
    assert not r.trend_removed
    assert "frame" in r.reason
    np.testing.assert_array_equal(r.trend_plane, 0.0)
    # the removed gradient differs from the true random ramp only by a straight line in t (absorbed in the trend)
    removed = fit_planes(x - SIZE / 2, y - SIZE / 2, r.ph_ramp)[:, 1:] * 10
    _, left = split_trend(removed - g_rest, t)
    assert np.abs(left).max() < 0.5
    # the bowl's velocity is untouched up to a plane (the random ramps' own line in t, which stays in the trend)
    dv = (_velocity(d - r.ph_ramp, t) - v)[:, None]
    c = fit_planes(x, y, dv)[0]
    assert np.std(dv[:, 0] - (c[0] + c[1] * x + c[2] * y)) < 3.0


def test_c_no_ramp_removes_nothing():
    """(c) no ramp: removed ramp < 0.5 mm/yr per 10 km (trend) and < 0.5 mm per 10 km per epoch."""
    x, y, t, _, d, _ = _scene(bowl="local", rest_std=0.0)
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0, params=PLANAR)
    assert np.abs(10 * r.trend_plane[1:]).max() < 0.5
    assert np.abs(10 * r.rest[:, 1:]).max() < 0.5


def test_d_seasonal_frame_wide_kept_with_warning():
    """(d) a seasonal frame-wide signal: the seasonal part is kept, with a warning."""
    x, y, t, _, d, g_rest = _scene(bowl="local", rest_std=1.0, seasonal=10.0, span=1.5, n_ep=36)
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0)
    assert r.seasonal_kept
    assert r.seasonal[0] < 0.005 and "F-test" in r.seasonal_note
    assert any("seasonal" in w for w in r.warnings)
    removed = fit_planes(x - SIZE / 2, y - SIZE / 2, r.ph_ramp)[:, 1] * 10
    sin = np.sin(2 * np.pi * t)
    assert abs(np.polyfit(sin, removed, 1)[0]) < 1.5                     # the 10 mm/10 km annual term stays


def test_small_frame_keeps_trend():
    x, y, t, _, d, _ = _scene(bowl="none", trend=(10.0, 0.0), size=4.0)
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0)
    assert not r.trend_removed and r.reason.startswith("frame <")


def test_units_and_nan_rows():
    """Phase in rad with a negative scale gives the same ramp in rad; NaN rows stay NaN."""
    x, y, t, _, d, _ = _scene(bowl="local", trend=(12.0, -8.0))
    k = -55.465763 / (4 * np.pi)
    ph = d / k
    ph[:10] = np.nan
    r = auto_ramp(x, y, ph, t, mm_per_unit=k, params=RampAutoParams(n_sub=20_000, allow_planar=True))
    assert np.isnan(r.ph_ramp[:10]).all()
    ref = auto_ramp(x[10:], y[10:], d[10:], t, mm_per_unit=1.0,
                    params=RampAutoParams(n_sub=20_000, allow_planar=True))
    assert r.trend_removed == ref.trend_removed
    assert np.nanmax(np.abs(r.ph_ramp[10:] * k - ref.ph_ramp)) < 0.5   # mm (different PS subsets / centre)
    s = r.summary()
    assert s["trend_removed"] is True and s["frame_test"]["consistent"] is True


def test_params_modes():
    from geoeyes.processing.ps.params import engine_params
    for v, on, auto in (("n", False, False), ("y", True, False), ("yes", True, False), ("auto", True, True),
                        ("AUTO", True, True)):
        p = engine_params({"scla_deramp": v}, wavelength=0.0555, rho=850e3)
        assert (p.scla_deramp, p.unwrap.scla_deramp, p.deramp_auto) == (on, on, auto)
    p = engine_params({"scla_deramp": "auto", "deramp_non_defo": [[0, 0], [1, 0], [1, 1]]}, wavelength=0.0555,
                      rho=850e3)
    assert p.deramp_non_defo == ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))
    assert not p.deramp_allow_planar
    assert engine_params({"scla_deramp": "auto", "ramp_auto_allow_planar": "y"}, wavelength=0.0555,
                         rho=850e3).deramp_allow_planar
    with pytest.raises(ValueError, match="scla_deramp"):
        engine_params({"scla_deramp": "maybe"}, wavelength=0.0555, rho=850e3)


def test_calc_scla_auto_removes_the_auto_ramp():
    """calc_scla with ``auto``: the ramp is auto_ramp's; ``y`` (full plane) differs; the record is kept."""
    from geoeyes.processing.ps.steps.scla import DerampAuto, calc_scla, smooth_scla
    x, y, t, _, d, _ = _scene(bowl="local", trend=(12.0, -8.0))
    n, m = d.shape
    k = -55.465763 / (4 * np.pi)
    ph = d / k
    xy = np.column_stack([np.arange(n), 1000 * x, 1000 * y])
    days = np.r_[t[: m // 2], 0.0, t[m // 2:]] * 365.25
    ifgday = np.column_stack([np.zeros(m + 1), days]).astype(np.float64)
    master_ix = m // 2
    bperp = np.random.default_rng(5).normal(0, 100, (n, m))
    auto = DerampAuto(t=t, mm_per_rad=k, params=PLANAR)
    sc = calc_scla(ph_uw=ph, bperp_mat=bperp, ifgday=ifgday, master_ix=master_ix, xy=xy, deramp_scla=True, auto=auto)
    ref = auto_ramp(x, y, ph, t, mm_per_unit=k, params=PLANAR)
    assert sc.ph_ramp.dtype == np.float32
    np.testing.assert_allclose(sc.ph_ramp, ref.ph_ramp, atol=1e-5)                 # float32 storage
    assert sc.ramp_auto is not None and sc.ramp_auto.ph_ramp.size == 0 and sc.ramp_auto.trend_removed
    assert smooth_scla(sc, xy, bperp).ramp_auto is sc.ramp_auto
    y_ = calc_scla(ph_uw=ph, bperp_mat=bperp, ifgday=ifgday, master_ix=master_ix, xy=xy, deramp_scla=True)
    assert y_.ramp_auto is None and not np.allclose(y_.ph_ramp, sc.ph_ramp)


def test_user_area_and_nan_column(tmp_path):
    """deramp_non_defo: the trend plane comes from the user's cells even when the frame test fails; an
    interferogram without values gets a NaN ramp; the figure is written."""
    from geoeyes.processing.ps.steps.ramp import ramp_figure
    x, y, t, v, d, g_rest = _scene(bowl="wide")
    d[:, 3] = np.nan
    far = (x < 8) & (y > 32)                                             # a corner, the flank of the wide bowl
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0, stable_mask=far)
    assert r.trend_removed and r.reason.startswith("user area")
    assert any("frame test fails" in w for w in r.warnings)
    assert np.isnan(r.ph_ramp[:, 3]).all() and np.isfinite(r.ph_ramp[:, 4]).all()
    vc = _velocity(np.delete(d - r.ph_ramp, 3, 1), np.delete(t, 3))
    gb = fit_planes(x[far], y[far], vc[far, None])[0]
    assert np.hypot(*gb[1:]) * 10 < 2.0                                  # the user's area is flat afterwards
    p = ramp_figure(r.record(), np.arange(t.size), tmp_path / "ramp.png", title="test")
    assert p.exists() and p.stat().st_size > 10_000


@pytest.mark.parametrize("seed", [2, 3])
def test_a_is_stable_over_seeds(seed):
    x, y, t, _, d, g_rest = _scene(bowl="local", trend=(-15.0, 5.0), seed=seed)
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0, params=PLANAR)
    assert r.trend_removed
    np.testing.assert_allclose(10 * r.trend_plane[1:], _true_trend((-15.0, 5.0), g_rest, t), atol=2.0)


def test_planar_deformation_without_constraint_kept():
    """A planar deformation field (interseismic gradient) passes the halves test; without GNSS or a stable area
    ``auto`` keeps it and says why."""
    x, y, t, _, d, _ = _scene(bowl="none", trend=(20.0, -6.0))
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0)
    assert r.frame_passed and r.frame.consistent
    assert not r.trend_removed and r.reason == PLANAR_KEPT
    np.testing.assert_array_equal(r.trend_plane, 0.0)
    s = r.summary()
    assert s["frame_test_passed"] is True and s["reason"] == PLANAR_KEPT


def test_stable_area_removes_planar_trend():
    """With the user's stable area (``deramp_non_defo``) the planar trend is fitted on its cells and removed."""
    x, y, t, v, d, g_rest = _scene(bowl="local", trend=(12.0, -8.0))
    area = (x > 25) & (y < 15)                                           # far from the bowl
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0, stable_mask=area)
    assert r.trend_removed and r.reason.startswith("user area") and r.frame_passed
    assert not any("frame test fails" in w for w in r.warnings)
    np.testing.assert_allclose(10 * r.trend_plane[1:], _true_trend((12.0, -8.0), g_rest, t), atol=3.0)
    vc = _velocity(d - r.ph_ramp, t)
    gb = fit_planes(x[area], y[area], vc[area, None])[0]
    assert np.hypot(*gb[1:]) * 10 < 2.0


def test_seasonal_short_series_conservative():
    """>= 1 yr but < 12 epochs: the F-test cannot run, the annual part is kept untested, with a warning."""
    x, y, t, _, d, _ = _scene(bowl="local", rest_std=2.0, span=1.5, n_ep=9)
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0)
    assert t.size < 12
    assert r.seasonal_kept and r.seasonal is None and "not tested" in r.seasonal_note
    assert any("seasonal safeguard not tested" in w for w in r.warnings)
    # under 1 yr the safeguard does not apply (no annual cycle to separate)
    x, y, t, _, d, _ = _scene(bowl="local", span=0.5, n_ep=16)
    r = auto_ramp(x, y, d, t, mm_per_unit=1.0)
    assert not r.seasonal_kept and "not applicable" in r.seasonal_note


def test_seasonal_f_test_on_noise_rarely_fires():
    """Pure noise gradient series (n = 24, 1.5 yr): the F-test with alpha 0.01 over the 2 gradients (Bonferroni)
    fires in about 1% of the series; the old R² > 50% rule fired often on short series."""
    rng = np.random.default_rng(7)
    p = RampAutoParams()
    t = np.sort(rng.uniform(-0.75, 0.75, 24))
    hits = 0
    trials = 2000
    for _ in range(trials):
        g = rng.normal(0, 7, (t.size, 2)) + np.outer(t, rng.normal(0, 10, 2))
        pv, _, _ = seasonal_test(g, t)
        hits += bool((pv < p.seasonal_alpha / 2).any())
    assert hits / trials < 0.02
    # and it sees a real annual signal of the size of the noise
    g = rng.normal(0, 3, (t.size, 2))
    g[:, 0] += 7 * np.sin(2 * np.pi * t)
    pv, _, sinus = seasonal_test(g, t)
    assert pv[0] < 1e-3 and pv[1] > p.seasonal_alpha / 2
    np.testing.assert_allclose(sinus[:, 0], 7 * np.sin(2 * np.pi * t), atol=2.5)


def test_calc_scla_auto_scla_prior():
    """``scla_k_prior``: the ramp is estimated on the phase minus K·B⊥ (D0's input); the SCLA fit is unchanged."""
    from geoeyes.processing.ps.steps.scla import DerampAuto, calc_scla
    x, y, t, _, d, _ = _scene(bowl="local", trend=(12.0, -8.0))
    n, m = d.shape
    k = -55.465763 / (4 * np.pi)
    rng = np.random.default_rng(5)
    bperp = rng.normal(0, 100, (n, m))
    kdem = rng.normal(0, 0.01, n)                                        # rad/m DEM error
    ph = d / k + kdem[:, None] * bperp
    xy = np.column_stack([np.arange(n), 1000 * x, 1000 * y])
    days = np.r_[t[: m // 2], 0.0, t[m // 2:]] * 365.25
    ifgday = np.column_stack([np.zeros(m + 1), days]).astype(np.float64)
    auto = DerampAuto(t=t, mm_per_rad=k)
    sc = calc_scla(ph_uw=ph, bperp_mat=bperp, ifgday=ifgday, master_ix=m // 2, xy=xy, deramp_scla=True, auto=auto,
                   scla_k_prior=kdem)
    ref = auto_ramp(x, y, d / k, t, mm_per_unit=k)
    np.testing.assert_allclose(sc.ph_ramp, ref.ph_ramp, atol=1e-4)
    assert np.median(np.abs(sc.K_uw - kdem)) < 2e-3                    # K still fitted on the full phase


def test_cycle_patch_does_not_tilt_the_ramp():
    """A corner unwrapped one cycle (lambda/2) off in one interferogram (ramp-selection.md §5.3, ring pattern):
    the robust plane ignores it (< 1 mm per 10 km), the plain least-squares plane is tilted by it."""
    x, y, t, _, d, _ = _scene(bowl="local")
    patch = (x < 12) & (y > 28)
    k = 5
    bad = d.copy()
    bad[patch, k] += 27.7
    def grad(params):
        clean = auto_ramp(x, y, d, t, mm_per_unit=1.0, params=params)
        hit = auto_ramp(x, y, bad, t, mm_per_unit=1.0, params=params)
        return 10 * np.abs(hit.coef[k, 1:] - clean.coef[k, 1:]).max()
    assert grad(RampAutoParams()) < 1.0
    assert grad(RampAutoParams(robust_planes=False)) > 2.0
