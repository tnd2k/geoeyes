"""Step 8 (SCN filter) vs legacy ``_ps_scn_filt`` (pass-2 inputs)."""
import numpy as np
import pytest

from geoeyes.processing.ps.steps.scn_filt import scn_filt
from tests.parity.ps.cases import rerun_cases, rerun_step


@pytest.mark.parametrize("case", rerun_cases())
def test_scn_matches_legacy(case):
    ps = case.step(4, "ps2.h5")
    sc = rerun_step(case, 7, "scla2.h5")
    xy = ps["xy"]
    new = scn_filt(ph_uw=rerun_step(case, 6, "phuw2.h5")["ph_uw"], ph_scla=sc["ph_scla"], C_uw=np.ravel(sc["C_ps_uw"]),
                   ph_ramp=sc["ph_ramp"], day=np.asarray(ps["day"]), master_ix=int(ps["master_ix"]), xy=xy,
                   filter_xy=xy[:, 0:2], method="exact",  # legacy bug: the filter used (PS id, x), not (x, y)
                   time_win=float(case.parms["scn_time_win"]), wavelength=float(case.parms["scn_wavelength"]))
    old = rerun_step(case, 8, "scn2.h5")
    np.testing.assert_allclose(new.ph_hpt, old["ph_hpt"], rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(new.ph_scn, old["ph_scn_slave"], rtol=1e-4, atol=1e-4)
