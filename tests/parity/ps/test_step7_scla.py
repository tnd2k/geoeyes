"""Step 7 SCLA (calc + smooth) vs legacy ``_ps_calc_scla`` / ``_ps_smooth_scla`` for both unwrap passes."""
import numpy as np
import pytest

from geoeyes.processing.ps.steps.scla import calc_scla, smooth_scla
from tests.parity.ps.cases import rerun_cases, rerun_step


def run(case, pass1: bool):
    ps = case.step(4, "ps2.h5")
    return calc_scla(ph_uw=rerun_step(case, 6, "phuw2.h5", pass1=pass1)["ph_uw"],
                     bperp_mat=case.step(4, "bp2.h5")["bperp_mat"], ifgday=ps["ifgday"],
                     master_ix=int(ps["master_ix"]), xy=ps["xy"],
                     aps=None if pass1 else rerun_step(case, 6, "tca2.h5", pass1=True)["ph_tropo_linear"],
                     deramp_scla=case.parms.get("scla_deramp") == "y", legacy=True)


@pytest.mark.parametrize("pass1", [True, False], ids=["pass1", "pass2"])
@pytest.mark.parametrize("case", rerun_cases())
def test_scla_matches_legacy(case, pass1):
    new = run(case, pass1)
    old = rerun_step(case, 7, "scla2.h5", pass1=pass1)
    np.testing.assert_allclose(new.K_uw, np.ravel(old["K_ps_uw"]), rtol=1e-6, atol=1e-10)
    np.testing.assert_allclose(new.C_uw, np.ravel(old["C_ps_uw"]), rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(new.ph_ramp, old["ph_ramp"], rtol=1e-6, atol=1e-8, equal_nan=True)
    np.testing.assert_allclose(new.ph_scla, old["ph_scla"], rtol=1e-6, atol=1e-8, equal_nan=True)

    sm = smooth_scla(new, case.step(4, "ps2.h5")["xy"], case.step(4, "bp2.h5")["bperp_mat"])
    olds = rerun_step(case, 7, "scla_smooth2.h5", pass1=pass1)
    np.testing.assert_allclose(sm.K_uw, np.ravel(olds["K_ps_uw"]), rtol=1e-6, atol=1e-10)
    np.testing.assert_allclose(sm.C_uw, np.ravel(olds["C_ps_uw"]), rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(sm.ph_scla, olds["ph_scla"], rtol=1e-6, atol=1e-8)
