"""Candidate selection on the native stack vs the legacy prep (``pscands.1.*`` of the exported run)."""
import numpy as np
import pytest

from geoeyes.geometry.dem import Geoid
from geoeyes.io.legacy import stamps
from geoeyes.io.stack import StackStore
from geoeyes.processing.ps import candidates as cd
from tests.parity.ps.cases import stack_cases


@pytest.mark.parametrize("case", stack_cases())
def test_candidates_match_legacy_prep(case):
    ds = StackStore(case.stack).open()
    dates = [np.datetime64(d, "D").item() for d in ds["date"].values]
    master, secs, _ = stamps.read_ifg_list(case.root / "input" / "pscphase.in")
    mi = dates.index(master)
    slc = ds["slc"].values
    disp = cd.amplitude_dispersion(lambda k: np.abs(slc[k]), len(dates))
    floor = cd.otsu_amplitude_floor(disp.raw_mean_amp)
    r, c, da = cd.select(disp, 0.4, floor)

    # legacy lon/lat: stack geometry with the prep's terrain shift (orthometric DEM, orbit incidence)
    par = case.master_par
    lat, lon = ds["geometry_lat"].values, ds["geometry_lon"].values
    hgt_e = ds["geometry_hgt"].values.astype(np.float64)
    ortho = (hgt_e - Geoid().undulation(lat, lon)).astype(np.float32)
    se, re = float(par["sar_to_earth_center"]), float(par["earth_radius_below_sensor"])
    rg = float(par["near_range_slc"]) + np.arange(lat.shape[1]) * float(par["range_pixel_spacing"])
    inc = np.arccos(np.clip((se**2 - re**2 - rg**2) / (2 * re * rg), -1, 1))
    lon_tc, lat_tc = cd.terrain_shift_lonlat(lon[r, c].astype(np.float64), lat[r, c].astype(np.float64),
                                             ortho[r, c].astype(np.float64), inc[c], float(par["heading"]), re)
    ll = np.column_stack([lon_tc, lat_tc]).astype(np.float32)
    keep = cd.dedup_lonlat(ll, da)
    r, c, da = r[keep], c[keep], da[keep]

    old = stamps.read_candidates(case.patch_dir, len(secs))
    # D_A agrees to ~1 ulp, so the D_A ordering of near-equal values may differ: compare by pixel
    o_new = np.lexsort((c, r))
    o_old = np.lexsort((old["ij"][:, 2], old["ij"][:, 1]))
    r, c, da = r[o_new], c[o_new], da[o_new]
    old = {k: (None if v is None else v[o_old]) for k, v in old.items()}
    np.testing.assert_array_equal(np.column_stack([r, c]), old["ij"][:, 1:3])
    np.testing.assert_allclose(da, old["da"], atol=1e-6)           # legacy writes D_A as %.6f text
    np.testing.assert_allclose(ortho[r, c], old["hgt"], atol=1e-3)
    ph = np.stack([slc[mi][r, c] * np.conj(slc[dates.index(s)][r, c]) for s in secs], axis=1)
    np.testing.assert_array_equal(ph, old["ph"])
    coh_ifg = np.stack([cd.pair_coherence(slc[mi], slc[dates.index(s)], r, c) for s in secs], axis=1)
    np.testing.assert_allclose(cd.prior_coherence(coh_ifg, ph), old["coh"], atol=1e-6)
