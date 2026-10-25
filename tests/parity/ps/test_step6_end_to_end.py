"""Step 6 end to end (both passes) vs the legacy re-run with its pass-1 snapshot."""
import numpy as np
import pytest

from geoeyes.processing.ps.aps import linear_aps
from geoeyes.processing.ps.steps.unwrap import Scla, unwrap
from tests.parity.ps.cases import params, rerun_cases, rerun_step


def run(case, scla=None, aps=None):
    ps, pm2 = case.step(4, "ps2.h5"), case.step(4, "pm2.h5")
    return unwrap(ph_patch=pm2["ph_patch"], ph_rc=case.step(5, "rc2.h5")["ph_rc"], K=np.ravel(pm2["K_ps"]),
                  coh=pm2["coh_ps"], xy=ps["xy"], bperp=ps["bperp"],
                  day=np.asarray(ps["day"], np.float64) - float(ps["master_day"]), master_ix=int(ps["master_ix"]),
                  ifgday_ix=np.asarray(ps["ifgday_ix"], np.int64) - 1, mean_incidence=float(ps["mean_incidence"]),
                  params=params(case).unwrap, scla=scla, aps=aps)


def _cycle_slips(new, old):
    ok = ~np.isnan(old)
    d = (new - old)[ok]
    cyc = np.round(d / (2 * np.pi))
    return float(np.max(np.abs(d - 2 * np.pi * cyc))), float(np.mean(cyc != 0))


@pytest.mark.parametrize("case", rerun_cases())
def test_pass1_matches_legacy(case):
    new = run(case)
    old = rerun_step(case, 6, "phuw2.h5", pass1=True)["ph_uw"]
    np.testing.assert_array_equal(np.isnan(new.ph_uw), np.isnan(old))
    ok = np.setdiff1d(np.arange(old.shape[1]), case.uw_failed)      # legacy-failed interferograms left out
    resid, slipped = _cycle_slips(new.ph_uw[:, ok], old[:, ok])
    assert resid < 1e-3 and slipped < 1e-3, (resid, slipped)
    ck = rerun_step(case, 6, "edge_reestimation_checkpoint.h5", pass1=True)   # K before the coh < 0.22 cut
    np.testing.assert_allclose(new.st.K, np.where(ck["coh"] < 0.22, 0, ck["K"]), atol=1e-6)
    tca = linear_aps(old, case.step(4, "hgt2.h5")["hgt"], int(case.step(4, "ps2.h5")["master_ix"]))
    np.testing.assert_allclose(tca, rerun_step(case, 6, "tca2.h5", pass1=True)["ph_tropo_linear"], atol=1e-8,
                               equal_nan=True)


@pytest.mark.parametrize("case", rerun_cases())
def test_pass2_matches_legacy(case):
    sm = rerun_step(case, 7, "scla_smooth2.h5", pass1=True)
    ramp = sm.get("ph_ramp")
    scla = Scla(K_uw=np.ravel(sm["K_ps_uw"]), C_uw=np.ravel(sm["C_ps_uw"]),
                ph_ramp=None if ramp is None or ramp.size == 0 else ramp)
    new = run(case, scla=scla, aps=rerun_step(case, 6, "tca2.h5", pass1=True)["ph_tropo_linear"])
    old = rerun_step(case, 6, "phuw2.h5")["ph_uw"]
    np.testing.assert_array_equal(np.isnan(new.ph_uw), np.isnan(old))
    resid, slipped = _cycle_slips(new.ph_uw, old)
    assert resid < 1e-3 and slipped < 1e-3, (resid, slipped)
