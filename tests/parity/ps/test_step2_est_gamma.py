"""Step 2 (est_gamma) vs legacy ``_ps_est_gamma_quick``, fed with the legacy step-1 outputs."""
import numpy as np
import pytest

from geoeyes.processing.ps.steps.est_gamma import est_gamma
from tests.parity.ps.cases import cases, params


def run_step2(case):
    import dataclasses
    ps = case.step(1, "ps1.h5")
    prm = params(case).est_gamma
    if not prm.dem_error.enabled:                # legacy S1 engine: NaN K poisoned the CLAP grid (fixed in CSK)
        prm = dataclasses.replace(prm, legacy_nan_k=True)
    return est_gamma(ph=case.step(1, "ph1.h5")["ph"], bperp=ps["bperp"], bperp_mat=case.step(1, "bp1.h5")["bperp_mat"],
                     master_ix=int(ps["master_ix"]), xy=ps["xy"], la=case.step(1, "la1.h5")["la"],
                     da=case.step(1, "da1.h5")["D_A"], coh_prior=ps.get("coh_ps_pref"), params=prm)


@pytest.mark.parametrize("case", cases())
def test_est_gamma_matches_legacy(case):
    new = run_step2(case)
    old = case.step(2, "pm1.h5")
    assert new.n_trial_wraps == pytest.approx(float(old["n_trial_wraps"]), rel=1e-12)
    assert new.n_iter == int(old["i_loop"]) and new.Nr_max_nz_ix == int(old["Nr_max_nz_ix"])
    np.testing.assert_array_equal(new.grid_ij, old["grid_ij"])
    np.testing.assert_allclose(new.low_pass, old["low_pass"], rtol=1e-12)
    np.testing.assert_allclose(new.Nr, old["Nr"], rtol=1e-9)
    np.testing.assert_allclose(new.ph_grid, old["ph_grid"], rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(new.ph_patch, old["ph_patch"], atol=1e-5)
    np.testing.assert_allclose(new.coh, old["coh_ps"], atol=1e-6)
    if "Q_ps" in old:                            # CSK engine only
        np.testing.assert_allclose(new.Q, old["Q_ps"], atol=1e-6)
    np.testing.assert_allclose(new.K, old["K_ps"], atol=1e-7, equal_nan=True)
    np.testing.assert_allclose(new.C, old["C_ps"], atol=1e-6)
    np.testing.assert_allclose(new.ph_res, old["ph_res"].real, atol=1e-5)
