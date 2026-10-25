"""Capella / CSK readers (zero-Doppler geometry checks on real products when present) and the residual
coregistration offset estimator."""
import json
from pathlib import Path

import numpy as np
import pytest

from geoeyes.core.geodesy import llh_to_ecef
from geoeyes.geometry.rdr2geo import geo2rdr
from geoeyes.sensors.base import C

def test_scenes_outside_the_reference_geometry_are_left_out():
    from dataclasses import replace
    from datetime import date

    from geoeyes.processing.stack.native.stripmap import Scene, check_geometry
    from geoeyes.sensors.capella import slc as rdr
    if not CAPELLA.exists():
        import pytest
        pytest.skip("Capella scene not present")
    g = rdr.read_metadata(rdr.find_files(CAPELLA)[1])
    sc = {date(2024, 6, 26): Scene(g, None),
          date(2024, 6, 29): Scene(replace(g, heading_deg=g.heading_deg + 0.5), None),
          date(2024, 7, 2): Scene(replace(g, look_side="right" if g.look_side == "left" else "left"), None),
          date(2024, 7, 5): Scene(replace(g, heading_deg=g.heading_deg + 180, pass_direction="descending"), None),
          date(2024, 7, 8): Scene(replace(g, slant_range_time=g.slant_range_time * 1.2), None)}
    kept, rejected = check_geometry(sc, date(2024, 6, 26))
    assert sorted(kept) == [date(2024, 6, 26), date(2024, 6, 29)]
    assert len(rejected) == 3 and "other beam" in rejected[-1] and "looking" in rejected[0]


CAPELLA =Path(r"D:\projects\geoeyes_workspace\archive\capella\capella-asc\20240626")
CSK = Path(r"D:\projects\geoeyes_workspace\archive\cosmo_skymed\_incoming\20120731")


def _pixel(g, X, t_guess):
    t, r = geo2rdr(g.orbit, X, t_guess)
    return (t - g.orbit.seconds(g.sensing_start)) / g.azimuth_time_interval, (2 * r / C - g.slant_range_time) * \
        g.range_sampling_rate


@pytest.mark.skipif(not CAPELLA.exists(), reason="Capella sample not present")
def test_capella_centre_pixel_is_zero_doppler():
    from geoeyes.sensors.capella.slc import find_files, read_metadata
    tif, js = find_files(CAPELLA)
    g = read_metadata(js)
    X = np.asarray(json.loads(js.read_text())["collect"]["image"]["center_pixel"]["target_position"], float)[None]
    line, sample = _pixel(g, X, g.orbit_seconds(g.lines / 2))
    assert abs(line[0] - g.lines // 2) < 0.5 and abs(sample[0] - g.samples // 2) < 0.5
    assert g.look_side == "left" and g.pass_direction == "ascending"


@pytest.mark.skipif(not CSK.exists(), reason="CSK sample not present")
def test_csk_corners_match_annotation():
    from geoeyes.sensors.cosmo_skymed.hdf5 import find_h5, read_metadata
    g = read_metadata(find_h5(CSK))
    X = llh_to_ecef(g.grid.lat, g.grid.lon, np.zeros(4))
    line, sample = _pixel(g, X, g.orbit_seconds(g.grid.line))
    assert np.abs(line - g.grid.line).max() < 3 and np.abs(sample - g.grid.pixel).max() < 0.5
    assert g.look_side == "right" and abs(g.wavelength - 0.0312) < 1e-3


def test_residual_offset_recovers_known_shift():
    from scipy.ndimage import shift as nd_shift

    from geoeyes.processing.stack.native.stripmap import residual_offset
    rng = np.random.default_rng(3)
    amp = np.abs(rng.standard_normal((512, 512)) + 1j * rng.standard_normal((512, 512)))
    amp = nd_shift(np.kron(amp[:256, :256], np.ones((2, 2))), 0)         # some spatial structure
    ref = amp.astype(np.complex64)
    sec = nd_shift(amp, (0.6, -0.3), order=3).astype(np.complex64)       # content moved by +0.6 / -0.3
    dl, ds, n = residual_offset(ref, sec, tile=128)
    assert n >= 4 and abs(dl - 0.6) < 0.06 and abs(ds + 0.3) < 0.06
