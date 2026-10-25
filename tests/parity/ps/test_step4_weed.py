"""Step 4 (weed) vs legacy ``_ps_weed``, fed with the legacy step-1/2/3 outputs."""
import numpy as np
import pytest

from geoeyes.processing.ps.geometry import triangulation_edges
from geoeyes.processing.ps.steps.weed import weed
from tests.parity.ps.cases import cases, legacy_select, params


def _legacy_edges(case) -> np.ndarray:
    """Triangle's ``psweed.2.edge`` as sorted unique (low, high) pairs."""
    lines = (case.patch_dir / "step4" / "psweed.2.edge").read_text().splitlines()
    e = np.array([[int(v) for v in ln.split()[1:3]] for ln in lines[1:int(lines[0].split()[0]) + 1]])
    return np.unique(np.sort(e, axis=1), axis=0)


@pytest.mark.parametrize("case", cases())
def test_weed_matches_legacy(case):
    ps = case.step(1, "ps1.h5")
    ph1 = case.step(1, "ph1.h5")["ph"]
    new = weed(ph=ph1, bperp=ps["bperp"], day=ps["day"], master_ix=int(ps["master_ix"]), xy=ps["xy"], ij=ps["ij"],
               forced=ps["forced_tag"].reshape(-1).astype(bool), hgt=case.step(1, "hgt1.h5")["hgt"],
               ph_patch=case.step(2, "pm1.h5")["ph_patch"], sel=legacy_select(case), params=params(case).weed)
    # the scipy Delaunay network replaces Triangle: identical edge set
    np.testing.assert_array_equal(triangulation_edges(ps["xy"][new.ix2[new.ix_pre]][:, 1:3]), _legacy_edges(case))

    old = case.step(4, "weed1.h5")
    np.testing.assert_array_equal(new.ifg_index, np.ravel(old["ifg_index"]))
    # Triangle orients its edges arbitrarily; the sign of an arc's phase enters the per-interferogram
    # mean of the variance weights, so ps_std/ps_max agree to ~1e-4 only, and a few PS sitting exactly
    # at the noise threshold may flip
    np.testing.assert_allclose(new.ps_std, old["ps_std"], rtol=1e-3)
    np.testing.assert_allclose(new.ps_max, old["ps_max"], rtol=1e-3)
    old_keep = old["ix_weed"].astype(bool)
    flips = int(np.sum(new.ix_weed != old_keep))
    assert flips <= 1e-4 * new.ix_weed.size, flips

    both = new.ix_weed & old_keep                       # compare the PS both versions kept
    in_new, in_old = both[new.ix_weed], both[old_keep]
    pm2 = case.step(4, "pm2.h5")
    np.testing.assert_array_equal(new.K[in_new], np.ravel(pm2["K_ps"])[in_old])
    np.testing.assert_array_equal(new.coh[in_new], np.ravel(pm2["coh_ps"])[in_old])
    np.testing.assert_array_equal(new.ph_patch[in_new], pm2["ph_patch"][in_old])
    np.testing.assert_array_equal(new.ph_res[in_new], pm2["ph_res"].real[in_old])
    np.testing.assert_array_equal(ps["xy"][new.ix][in_new], case.step(4, "ps2.h5")["xy"][in_old])
    np.testing.assert_array_equal(ph1[new.ix][in_new], case.step(4, "ph2.h5")["ph"][in_old])
