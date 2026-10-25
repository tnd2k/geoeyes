"""Step 3 (select) vs legacy ``_ps_select``, fed with the legacy step-1/2 outputs."""
import numpy as np
import pytest

from geoeyes.processing.ps.steps.select import select
from tests.parity.ps.cases import cases, legacy_gamma, params


@pytest.mark.parametrize("case", cases())
def test_select_matches_legacy(case):
    ps = case.step(1, "ps1.h5")
    new = select(ph=case.step(1, "ph1.h5")["ph"], bperp=ps["bperp"], bperp_mat=case.step(1, "bp1.h5")["bperp_mat"],
                 master_ix=int(ps["master_ix"]), xy=ps["xy"], forced=ps["forced_tag"].reshape(-1).astype(bool),
                 da=case.step(1, "da1.h5")["D_A"], gamma=legacy_gamma(case), params=params(case).select)
    old = case.step(3, "select1.h5")
    np.testing.assert_array_equal(new.ix, old["ix"])
    np.testing.assert_array_equal(new.ifg_index, old["ifg_index"])
    np.testing.assert_allclose(new.ph_patch2, old["ph_patch2"], atol=1e-5)
    np.testing.assert_allclose(new.coh2, old["coh_ps2"], atol=1e-6, equal_nan=True)
    if "Q_ps2" in old:                           # CSK engine only
        np.testing.assert_allclose(new.Q2, old["Q_ps2"], atol=1e-6)
    np.testing.assert_allclose(new.K2, old["K_ps2"], atol=1e-7, equal_nan=True)
    np.testing.assert_allclose(new.C2, old["C_ps2"], atol=1e-6, equal_nan=True)
    np.testing.assert_allclose(new.ph_res2, old["ph_res2"].real, atol=1e-5)
    np.testing.assert_allclose(new.coh_thresh, np.ravel(old["coh_thresh"]), rtol=1e-9)
    np.testing.assert_array_equal(new.keep_ix, old["keep_ix"])
