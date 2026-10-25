"""Step 6 (unwrap) stages vs the legacy ``_uw_grid_wrapped`` / ``_uw_interp`` / ... intermediates
(``step6/uw_*.h5``, written by the last — pass-2 — unwrap of the legacy run)."""
import numpy as np
import pytest

from geoeyes.processing.ps.unwrap.grid import UwGrid, grid_wrapped
from geoeyes.processing.ps.unwrap.interp import UwInterp, interp
from geoeyes.processing.ps.unwrap.space_time import SpaceTime, space_time
from geoeyes.processing.ps.unwrap.spatial import spatial_unwrap
from tests.parity.ps.cases import cases, params


def run_grid(case):
    u = params(case).unwrap
    uw = case.step(6, "uw_grid.h5")
    return uw, grid_wrapped(uw["ph_in"], case.step(4, "ps2.h5")["xy"], grid_size=u.grid_size,
                            prefilt_win=u.prefilt_win, gold_alpha=u.gold_alpha, coh=case.step(4, "pm2.h5")["coh_ps"],
                            coh_floor=u.coh_floor, prefilter=u.prefilter)


@pytest.mark.parametrize("case", cases())
def test_grid_matches_legacy(case):
    old, new = run_grid(case)
    np.testing.assert_array_equal(new.grid_ij, old["grid_ij"])
    np.testing.assert_array_equal(new.nzix, old["nzix"])
    np.testing.assert_array_equal(new.ij, old["ij"])
    np.testing.assert_allclose(new.xy, old["xy"])
    np.testing.assert_array_equal(new.ph, old["ph"])
    if new.ph_lowpass.size or np.asarray(old["ph_lowpass"]).size:
        np.testing.assert_allclose(new.ph_lowpass, old["ph_lowpass"], rtol=1e-5, atol=1e-6)


def legacy_grid(case) -> UwGrid:
    uw = case.step(6, "uw_grid.h5")
    return UwGrid(ph=uw["ph"], ph_lowpass=uw["ph_lowpass"], xy=uw["xy"], ij=uw["ij"], nzix=uw["nzix"].astype(bool),
                  grid_ij=uw["grid_ij"], grid_x_min=float(uw["grid_x_min"]), grid_y_min=float(uw["grid_y_min"]),
                  n_i=int(uw["n_i"]), n_j=int(uw["n_j"]))


def legacy_interp(case) -> UwInterp:
    ui = case.step(6, "uw_interp.h5")
    return UwInterp(edgs=ui["edgs"], rowix=ui["rowix"], colix=ui["colix"], Z=ui["Z"])


def unwrap_geometry(case):
    """(day rel. master, 0-based ifgday_ix, bperp per epoch, n_trial_wraps) as the legacy unwrap builds them."""
    pm, ps = case.parms, case.step(4, "ps2.h5")
    bperp = np.asarray(ps["bperp"], np.float64)
    max_k = float(pm["max_topo_err"]) / (float(pm["lambda"]) * case.rho * np.sin(float(ps["mean_incidence"])) / 4 / np.pi)
    return (np.asarray(ps["day"], np.float64) - float(ps["master_day"]), np.asarray(ps["ifgday_ix"], np.int64) - 1,
            bperp, (np.amax(bperp) - np.amin(bperp)) * max_k / (2 * np.pi))


@pytest.mark.parametrize("case", cases())
def test_space_time_matches_legacy_pass2(case):
    pm = case.parms
    day, ifgday_ix, bperp, ntw = unwrap_geometry(case)
    new = space_time(grid=legacy_grid(case), ui=legacy_interp(case), day=day, ifgday_ix=ifgday_ix, bperp=bperp,
                     n_trial_wraps=ntw, time_win=float(pm["unwrap_time_win"]), prefilt_win=int(pm["unwrap_gold_n_win"]),
                     la_flag=pm["unwrap_la_error_flag"] == "y", estimate_K=False, legacy=True)
    old = case.step(6, "uw_space_time.h5")
    np.testing.assert_array_equal(new.G, old["G"])
    np.testing.assert_allclose(new.ifreq_ij, old["ifreq_ij"], atol=1e-5, equal_nan=True)
    np.testing.assert_allclose(new.jfreq_ij, old["jfreq_ij"], atol=1e-5, equal_nan=True)
    np.testing.assert_array_equal(new.shaky_ix, old["shaky_ix"].astype(bool))
    np.testing.assert_allclose(new.dph_noise, old["dph_noise"], atol=1e-4, equal_nan=True)
    np.testing.assert_allclose(new.dph_space_uw, old["dph_space_uw"], atol=1e-4, equal_nan=True)
    np.testing.assert_allclose(new.spread, old["spread"], atol=1e-5)


def legacy_space_time(case) -> SpaceTime:
    ut = case.step(6, "uw_space_time.h5")
    return SpaceTime(dph_space_uw=ut["dph_space_uw"], dph_noise=ut["dph_noise"], G=ut["G"], spread=ut["spread"],
                     ifreq_ij=ut["ifreq_ij"], jfreq_ij=ut["jfreq_ij"], shaky_ix=ut["shaky_ix"].astype(bool),
                     K=np.zeros(0), coh=np.zeros(0))


@pytest.mark.parametrize("case", cases())
def test_spatial_matches_legacy_pass2(case):
    new = spatial_unwrap(grid=legacy_grid(case), ui=legacy_interp(case), st=legacy_space_time(case),
                         params=params(case).unwrap.spatial)
    old = case.step(6, "uw_phaseuw.h5")["ph_uw"]
    np.testing.assert_array_equal(np.isnan(new.ph_uw), np.isnan(old))
    d = np.abs(new.ph_uw - old)[~np.isnan(old)]
    cycles = np.round(d / (2 * np.pi))
    assert np.max(np.abs(d - 2 * np.pi * cycles)) < 1e-3          # both congruent to the same wrapped phase
    slipped = float(np.mean(cycles != 0))
    assert slipped < 1e-3, f"{slipped:.2%} of PS values differ by whole cycles"


@pytest.mark.parametrize("case", cases())
def test_interp_matches_legacy(case):
    old = case.step(6, "uw_interp.h5")
    new = interp(case.step(6, "uw_grid.h5")["nzix"])
    np.testing.assert_array_equal(new.Z, old["Z"])
    np.testing.assert_array_equal(new.edgs, old["edgs"])
    np.testing.assert_array_equal(new.rowix, old["rowix"])
    np.testing.assert_array_equal(new.colix, old["colix"])
