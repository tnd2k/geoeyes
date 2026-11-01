"""ICEYE SLC-COG reader: geometry against the product's own RPC model (real Open Data metadata, CC-BY 4.0 ICEYE),
amplitude / phase decoding and the transposition of the shadows-down raster, AOI crops."""
import json
from pathlib import Path

import numpy as np
import pytest

from geoeyes.core.geodesy import llh_to_ecef
from geoeyes.geometry.rdr2geo import geo2rdr
from geoeyes.sensors.base import C
from geoeyes.sensors.iceye import slc_cog

META = Path(__file__).parent / "data" / "ICEYE_ETH0SK_20260219T021322Z_8871777_X53_SM_SLC.json"
LAT = np.array([28.0, 28.2, 28.4, 28.5])
LON = np.array([-16.75, -16.65, -16.75, -16.8])
H = np.array([0.0, 500.0, 1000.0, 0.0])


def _orbit_pixel(g, lat, lon, h, line_guess):
    t, r = geo2rdr(g.orbit, llh_to_ecef(lat, lon, h), g.orbit_seconds(line_guess))
    return (t - g.orbit.seconds(g.sensing_start)) / g.azimuth_time_interval, \
        (2 * r / C - g.slant_range_time) * g.range_sampling_rate


def test_metadata_geometry_matches_rpc():
    g = slc_cog.read_metadata(META)
    p = slc_cog.properties(META)
    assert (g.lines, g.samples) == (44840, 18032)            # azimuth lines = TIFF columns
    assert g.look_side == "right" and g.pass_direction == "ascending" and g.polarization == "VV"
    assert abs(g.wavelength - 0.031067) < 1e-5 and abs(g.heading_deg + 12.07) < 0.1
    row, col = slc_cog.rpc_to_tiff(p, LAT, LON, H)
    line, sample = _orbit_pixel(g, LAT, LON, H, col)
    assert np.abs(line - col).max() < 0.3 and np.abs(sample - row).max() < 0.3


def test_crop_shifts_the_grid(tmp_path):
    p = json.loads(META.read_text())
    p["properties"]["geoeyes:crop"] = {"row0": 10000, "col0": 15000, "rows": 3000, "cols": 6000}
    cut = tmp_path / META.name
    cut.write_text(json.dumps(p))
    g = slc_cog.read_metadata(cut)
    assert (g.lines, g.samples) == (6000, 3000)
    row, col = slc_cog.rpc_to_tiff(p["properties"], LAT[1:2], LON[1:2], H[1:2])
    line, sample = _orbit_pixel(g, LAT[1:2], LON[1:2], H[1:2], col)
    assert abs(line[0] - col[0]) < 0.3 and abs(sample[0] - row[0]) < 0.3
    assert 0 < col[0] < 6000 and 0 < row[0] < 3000


def test_read_slc_decodes_amplitude_phase_and_transposes(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    rows, cols = 6, 10                                       # range samples x azimuth lines in the TIFF
    rng = np.random.default_rng(0)
    amp = rng.uniform(1, 100, (rows, cols))
    pha = rng.uniform(-np.pi, np.pi, (rows, cols))
    a_scale, p_scale = 2.5, 2 * np.pi / 65535
    tif = tmp_path / "x_SLC.tif"
    with rasterio.open(tif, "w", driver="GTiff", width=cols, height=rows, count=2, dtype="uint16") as dst:
        dst.write(np.round(amp / a_scale).astype(np.uint16), 1)
        dst.write(np.round((pha + np.pi) / p_scale).astype(np.uint16), 2)
        dst.scales, dst.offsets = (a_scale, p_scale), (0.0, -np.pi)
        dst.update_tags(1, NAME="AMPLITUDE")
        dst.update_tags(2, NAME="PHASE")
    full = slc_cog.read_slc(tif)
    assert full.shape == (cols, rows) and full.dtype == np.complex64
    ref = (np.round(amp / a_scale) * a_scale * np.exp(1j * (np.round((pha + np.pi) / p_scale) * p_scale - np.pi))).T
    np.testing.assert_allclose(full, ref, rtol=1e-5, atol=1e-4)
    win = slc_cog.read_slc(tif, (2, 7, 1, 4))                # lines 2..7 (azimuth), samples 1..4 (range)
    np.testing.assert_allclose(win, full[2:7, 1:4])


def test_iceye_scene_of_another_beam_is_left_out():
    from dataclasses import replace
    from datetime import date

    from geoeyes.processing.stack.native.stripmap import Scene, check_geometry
    from geoeyes.sensors.iceye.slc_cog import read_metadata
    g = read_metadata(META)
    sc = {date(2026, 2, d): Scene(g, None) for d in (18, 19, 20)}
    sc[date(2026, 2, 27)] = Scene(replace(g, azimuth_time_interval=1 / 4916.0), None)
    kept, rejected = check_geometry(sc, date(2026, 2, 19))
    assert sorted(kept) == [date(2026, 2, d) for d in (18, 19, 20)] and "PRF 4916" in rejected[0]
