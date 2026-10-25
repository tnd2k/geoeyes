"""Step 1 (load) vs legacy ``_ps_load_initial_gamma``."""
import numpy as np
import pytest

from geoeyes.io.legacy import stamps
from geoeyes.processing.ps.steps.load import RadarParams, load_initial
from tests.parity.ps.cases import cases


@pytest.mark.parametrize("case", cases())
def test_load_matches_legacy(case):
    master, secs, paths = stamps.read_ifg_list(case.root / "input" / "pscphase.in")
    cand = stamps.read_candidates(case.patch_dir, len(secs))
    new = load_initial(master=master, secondaries=secs, baselines=[stamps.read_base(p.with_suffix(".base"))
                                                                   for p in paths],
                       radar=RadarParams.from_par(case.master_par), **cand)
    ps, ph = case.step(1, "ps1.h5"), case.step(1, "ph1.h5")["ph"]
    assert new.n_ps == int(ps["n_ps"]) and new.n_ifg == int(ps["n_ifg"])
    assert new.master_ix == int(ps["master_ix"]) and new.master_day == int(ps["master_day"])
    np.testing.assert_array_equal(new.day, ps["day"])
    np.testing.assert_array_equal(new.sort_ix, ps["sort_ix"])
    np.testing.assert_array_equal(new.ij, ps["ij"])
    np.testing.assert_array_equal(new.lonlat, ps["lonlat"])
    np.testing.assert_array_equal(new.xy, ps["xy"])
    np.testing.assert_array_equal(new.ifgday, ps["ifgday"])
    np.testing.assert_array_equal(new.ifgday_ix + 1, ps["ifgday_ix"])
    # legacy mean bperp is accumulated in float32 (~0.4 % error); the port uses float64
    bp_mat = case.step(1, "bp1.h5")["bperp_mat"]
    np.testing.assert_allclose(np.delete(new.bperp, new.master_ix), bp_mat.mean(0, dtype=np.float64), rtol=1e-12)
    np.testing.assert_allclose(new.bperp, ps["bperp"], rtol=1e-2, atol=1e-3)
    np.testing.assert_allclose(new.ll0, ps["ll0"], rtol=1e-7)
    assert new.mean_incidence == pytest.approx(float(ps["mean_incidence"]), rel=1e-12)
    np.testing.assert_array_equal(new.ph, ph)
    np.testing.assert_array_equal(new.bperp_mat, bp_mat)
    np.testing.assert_allclose(new.la, case.step(1, "la1.h5")["la"], rtol=1e-12)
    np.testing.assert_array_equal(new.hgt, case.step(1, "hgt1.h5")["hgt"])
    np.testing.assert_array_equal(new.da, case.step(1, "da1.h5")["D_A"])
    np.testing.assert_array_equal(new.coh, ps["coh_ps_pref"])
    np.testing.assert_array_equal(new.forced, ps["forced_tag"].astype(bool))
