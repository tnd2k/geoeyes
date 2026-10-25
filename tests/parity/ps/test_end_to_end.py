"""Steps 1-8 chained by the runner core (``process``) from the legacy prep files, vs the legacy final outputs.

Not bit-exact by design: the weeding network orientation flips a few PS (step 4), the mean Bperp is accumulated
in float64, and every later step sees those differences. Checked statistically, by stack pixel."""
import numpy as np
import pytest

from geoeyes.io.legacy import stamps
from geoeyes.processing.ps.runner import process
from geoeyes.processing.ps.steps.load import RadarParams, load_initial
from tests.parity.ps.cases import cases, params


@pytest.mark.parametrize("case", cases())
def test_chain_matches_legacy(case):
    if case.uw_failed:
        pytest.skip(f"legacy pass-1 unwrap failed on interferograms {case.uw_failed} (its pass-2 APS is wrong); "
                    "both passes are compared separately in test_step6_end_to_end")
    master, secs, paths = stamps.read_ifg_list(case.root / "input" / "pscphase.in")
    L = load_initial(master=master, secondaries=secs, baselines=[stamps.read_base(p.with_suffix(".base"))
                                                                 for p in paths],
                     radar=RadarParams.from_par(case.master_par), **stamps.read_candidates(case.patch_dir, len(secs)))
    P = process(L, params(case), float(case.parms["lambda"]), scn_filter_xy=L.xy[:, 0:2], scn_method="exact")

    key_new = L.ij[P.ix, 1] * 100000 + L.ij[P.ix, 2]
    ps2 = case.step(4, "ps2.h5")
    key_old = ps2["ij"][:, 1] * 100000 + ps2["ij"][:, 2]
    _, a, b = np.intersect1d(key_new, key_old, return_indices=True)
    assert a.size >= 0.99 * key_old.size            # 99.75 % on csk_hanoi_native

    # Unwrapping is sensitive to tiny upstream differences: from the legacy step-4 state the chain 5-8 gives
    # velocity r 0.987 / median |d| 0.02 mm/yr (0.4 % cycle slips after two passes); from step 1, r 0.94 /
    # 0.12 mm/yr on this weak-signal scene (velocity spread ~1.5 mm/yr).
    def agree(new, old, name, r_min, tol):
        ok = np.isfinite(new) & np.isfinite(old)
        r = np.corrcoef(new[ok], old[ok])[0, 1]
        mad = np.median(np.abs(new[ok] - old[ok]))
        print(f"{name}: r={r:.4f} median|d|={mad:.4g}")
        assert r >= r_min and mad <= tol, (name, r, mad)

    vd = case.step(7, "ps_plot_v-dao.h5")
    agree(P.velocity.v[a], np.ravel(vd["ph_disp"])[b], "velocity", 0.9, 0.2)
    agree(P.scla_smooth.K_uw[a], np.ravel(case.step(7, "scla_smooth2.h5")["K_ps_uw"])[b], "K_uw", 0.9, 1e-3)
    ts_old = case.step(7, "ps_plot_ts_v-dao.h5")["ph_mm"][b]
    agree(P.velocity.ts_mm[a].ravel(), ts_old.ravel(), "time series", 0.9, 0.5)
