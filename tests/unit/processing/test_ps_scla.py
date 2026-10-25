import numpy as np

from geoeyes.processing.ps.steps.scla import calc_scla


def test_scla_fits_each_ps_with_its_own_bperp():
    rng = np.random.default_rng(0)
    n, n_sec, master = 200, 9, 3
    day = np.arange(n_sec + 1) * 24.0 + 737000
    ifgday = np.column_stack([np.full(n_sec + 1, day[master]), day])
    b0 = rng.uniform(-300, 300, n_sec)
    s = rng.uniform(0.9, 1.1, n)
    bperp_mat = b0[None, :] * s[:, None]                                 # B⊥ varies 10 % across the scene
    K = rng.normal(0, 2e-3, n)
    K -= s * (K @ s) / (s @ s)                     # mean_i K_i·B⊥_ik = 0: the reference (mean) phase has no K term
    t = np.delete(day - day[master], master)
    ph = 0.3 + K[:, None] * bperp_mat + 1e-3 * t[None, :]
    xy = np.column_stack([np.arange(n), rng.uniform(0, 5000, (n, 2))])
    new = calc_scla(ph_uw=ph, bperp_mat=bperp_mat, ifgday=ifgday, master_ix=master, xy=xy, deramp_scla=False)
    old = calc_scla(ph_uw=ph, bperp_mat=bperp_mat, ifgday=ifgday, master_ix=master, xy=xy, deramp_scla=False,
                    legacy=True)
    np.testing.assert_allclose(new.K_uw, K, atol=1e-9)
    assert np.max(np.abs(old.K_uw - K)) > 1e-4                           # scene-mean B⊥ biases K
