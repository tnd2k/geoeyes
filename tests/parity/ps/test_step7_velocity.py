"""Step 7 velocity / time series vs legacy ``_ps_plot_v_dao`` (pass 2: the final outputs)."""
import numpy as np
import pytest

from geoeyes.processing.ps.steps.scla import SclaResult
from geoeyes.processing.ps.steps.velocity import velocity
from tests.parity.ps.cases import rerun_cases, rerun_step


@pytest.mark.parametrize("case", rerun_cases())
def test_velocity_matches_legacy(case):
    ps = case.step(4, "ps2.h5")
    sc = rerun_step(case, 7, "scla2.h5")                  # v_dao reads the unsmoothed SCLA of its pass
    scla = SclaResult(K_uw=np.ravel(sc["K_ps_uw"]), C_uw=np.ravel(sc["C_ps_uw"]), ph_scla=sc["ph_scla"],
                      ph_ramp=sc["ph_ramp"], deramp_degree=None)
    new = velocity(ph_uw=rerun_step(case, 6, "phuw2.h5")["ph_uw"], scla=scla,
                   aps=rerun_step(case, 6, "tca2.h5")["ph_tropo_linear"], ifgday=ps["ifgday"],
                   day=np.asarray(ps["day"]), master_ix=int(ps["master_ix"]), xy=ps["xy"], lonlat=ps["lonlat"],
                   hgt=case.step(4, "hgt2.h5")["hgt"], wavelength=float(case.parms["lambda"]),
                   deramp=case.parms.get("scla_deramp") == "y", legacy=True)
    vd = rerun_step(case, 7, "ps_plot_v-dao.h5")
    np.testing.assert_allclose(new.v_linear, np.ravel(rerun_step(case, 7, "ps_plot_v-dao_linear.h5")["ph_disp"]),
                               rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(new.acc, np.ravel(vd["acc"]), rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(new.acc_var, np.ravel(vd["accv"]), rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(new.rmse, np.ravel(vd["rmse"]), rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(new.ts_mm, rerun_step(case, 7, "ps_plot_ts_v-dao.h5")["ph_mm"], rtol=1e-6, atol=1e-5)
    np.testing.assert_allclose(new.residual_mm, rerun_step(case, 7, "ph_uw_detrended.h5")["ph_mm"], rtol=1e-6,
                               atol=1e-5, equal_nan=True)
    np.testing.assert_allclose(new.v, np.ravel(vd["ph_disp"]), rtol=1e-6, atol=1e-6)
