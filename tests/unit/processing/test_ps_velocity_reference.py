import numpy as np

from geoeyes.processing.ps.steps.scla import SclaResult
from geoeyes.processing.ps.steps.velocity import velocity


def test_scene_mean_reference_removes_per_date_offsets():
    """Hanoi S1 (2026-10): two dates kept a -10 mm scene-wide offset after the pass-2 unwrapping."""
    rng = np.random.default_rng(0)
    n, n_img, master = 500, 6, 2
    day = np.arange(n_img) * 12 + 739000
    n_sec = n_img - 1
    secs = [k for k in range(n_img) if k != master]
    ifgday = np.array([[day[master], day[k]] for k in range(n_img)])
    t = (day[secs] - day[master]) / 365.25
    v_true = rng.normal(0, 5, n)                                             # mm/yr, mean ~0 by construction
    v_true -= v_true.mean()
    lam = 0.0555 / (4 * np.pi) * 1000
    ph = -(v_true[:, None] * t[None, :]) / lam
    ph[:, 3] += 2.6                                                         # a scene-wide offset (~ -11 mm)
    scla = SclaResult(K_uw=np.zeros(n), C_uw=np.zeros(n), ph_scla=np.zeros((n, n_sec)), ph_ramp=np.zeros((0, 0)),
                      deramp_degree=None)
    kw = dict(ph_uw=ph, scla=scla, aps=None, ifgday=ifgday, day=day, master_ix=master,
              xy=np.column_stack([np.arange(n), rng.uniform(0, 5000, (n, 2))]), lonlat=rng.uniform(0, 0.05, (n, 2)),
              hgt=None, wavelength=0.0555, highpass=False)
    raw = velocity(**kw)
    ref = velocity(**kw, demean=True)
    assert abs(np.nanmean(raw.ts_mm[:, secs[3]])) > 10
    np.testing.assert_allclose(np.nanmean(ref.ts_mm, axis=0), 0.0, atol=1e-4)
    np.testing.assert_allclose(ref.v_linear, v_true, atol=1e-3)
