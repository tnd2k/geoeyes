"""Step 5 (correct_phase + ifg_std) vs legacy ``_ps_correct_phase`` / ``_ps_calc_ifg_std``."""
import numpy as np
import pytest

from geoeyes.processing.ps.steps.correct_phase import correct_phase
from tests.parity.ps.cases import cases


@pytest.mark.parametrize("case", cases())
def test_correct_phase_matches_legacy(case):
    pm = case.step(4, "pm2.h5")
    new = correct_phase(ph=case.step(4, "ph2.h5")["ph"], bperp_mat=case.step(4, "bp2.h5")["bperp_mat"],
                        K=pm["K_ps"], C=pm["C_ps"], ph_patch=pm["ph_patch"],
                        master_ix=int(case.step(4, "ps2.h5")["master_ix"]))
    rc = case.step(5, "rc2.h5")
    np.testing.assert_allclose(new.ph_rc, rc["ph_rc"], rtol=1e-6, atol=1e-6)
    np.testing.assert_array_equal(new.ph_reref, rc["ph_reref"])
    np.testing.assert_allclose(new.ifg_std, case.step(5, "ifgstd2.h5")["ifg_std"], rtol=1e-6)
