"""SICD: NITF segments and pixel windows (synthetic NITF), image projections on a real Umbra SICD XML (Umbra Open
Data, CC-BY 4.0; PFA spotlight), chips, the cut GeoTIFF reader."""
from pathlib import Path

import numpy as np
import pytest

from geoeyes.core.geodesy import llh_to_ecef
from geoeyes.sensors.sicd import meta as sm
from geoeyes.sensors.sicd import slc as sicd

XML = Path(__file__).parent / "data" / "2025-02-16-04-56-03_UMBRA-05_SICD.xml"


def _nitf(path: Path, data: np.ndarray, xml: str) -> None:
    """A NITF 2.1 with one uncompressed image segment (I / Q float32 big-endian, one block) and the SICD DES."""
    rows, cols = data.shape
    sec = " " * 166
    ish = ("IM" + "SICD000".ljust(10) + "20250216045600" + " " * 17 + " " * 80 + "U" + sec + "0" + " " * 42
           + f"{rows:08d}{cols:08d}" + "R  " + "NODISPLY" + "SAR     " + "32" + "R" + "G" + " " * 60 + "0" + "NC"
           + "2" + "I " + "I     " + "N" + "   " + "0" + "Q " + "Q     " + "N" + "   " + "0"
           + "0" + "P" + "0001" + "0001" + f"{cols:04d}{rows:04d}" + "32" + "001" + "000" + "0000000000" + "1.0 "
           + "00000" + "00000").encode("latin-1")
    pix = np.stack([data.real, data.imag], axis=-1).astype(">f4").tobytes()
    dsh = ("DE" + "XML_DATA_CONTENT".ljust(25) + "01" + "U" + sec + "0000").encode("latin-1")
    des = xml.encode("utf-8")

    def header(hl: int, fl: int) -> bytes:
        h = ("NITF" + "02.10" + "03" + "BF01" + " " * 10 + "20250216045600" + " " * 80 + "U" + sec + "00000" + "00000"
             + "0" + "   " + " " * 24 + " " * 18 + f"{fl:012d}{hl:06d}" + "001" + f"{len(ish):06d}{len(pix):010d}"
             + "000" + "000" + "000" + "001" + f"{len(dsh):04d}{len(des):09d}" + "000" + "00000" + "00000")
        return h.encode("latin-1")

    hl = len(header(0, 0))
    fl = hl + len(ish) + len(pix) + len(dsh) + len(des)
    path.write_bytes(header(hl, fl) + ish + pix + dsh + des)


def test_nitf_segments_xml_and_windows(tmp_path):
    from geoeyes.sensors.sicd.nitf import Nitf
    rng = np.random.default_rng(0)
    data = (rng.standard_normal((40, 70)) + 1j * rng.standard_normal((40, 70))).astype(np.complex64)
    f = tmp_path / "x_SICD.nitf"
    xml = XML.read_text(encoding="utf-8")
    _nitf(f, data, xml)
    n = Nitf(f)
    assert (n.rows, n.cols) == (40, 70) and n.xml.startswith("<SICD") and len(n.xml) == len(xml)
    np.testing.assert_array_equal(n.read(), data)
    np.testing.assert_array_equal(n.read(5, 17, 30, 61), data[5:17, 30:61])
    m = sm.parse(n.xml)
    win = sicd.read_slc(f, m, (30, 61, 5, 17))                # lines = SICD cols, samples = SICD rows
    np.testing.assert_array_equal(win, data[5:17, 30:61].T)


def test_projection_matches_scp_and_corners():
    s = sm.parse(XML.read_text(encoding="utf-8"))
    assert (s.ifa, s.side, s.look_side, s.pass_direction, s.polarization) == ("PFA", "R", "right", "ascending", "VV")
    assert abs(s.wavelength - 0.03074) < 1e-4 and abs(s.heading_deg + 11.9) < 0.1
    _, _, _, xyz = s.image_to_ground(np.array([s.scp_row]), np.array([s.scp_col]))
    assert np.linalg.norm(xyz[0] - s.scp) < 1e-3
    rows = np.array([0, 0, s.rows - 1, s.rows - 1])
    cols = np.array([0, s.cols - 1, s.cols - 1, 0])
    lat, lon, _, xyz = s.image_to_ground(rows, cols)
    icp = sm.corners(s)
    err = np.hypot((lat - icp[:, 0]) * 111e3, (lon - icp[:, 1]) * 111e3 * np.cos(np.radians(33.7)))
    assert err.max() < 6.0                                    # Umbra's corner points are approximate (3-4 m)
    r, c = s.ground_to_image(xyz)
    assert np.abs(r - rows).max() < 1e-3 and np.abs(c - cols).max() < 1e-3
    assert abs(float(s.phase_range(s.scp[None])[0])) < 1e-6


def test_higher_ground_is_nearer_in_range():
    s = sm.parse(XML.read_text(encoding="utf-8"))
    lat, lon = s.scp_llh[0], s.scp_llh[1]
    r0, _ = s.ground_to_image(llh_to_ecef(np.array([lat]), np.array([lon]), np.array([0.0])))
    r1, _ = s.ground_to_image(llh_to_ecef(np.array([lat]), np.array([lon]), np.array([100.0])))
    # layover: 100 m up moves the point ~100·cos(θ) toward the sensor (rows grow with range here: Row.Sgn -1)
    assert 0.5 < abs(r1[0] - r0[0]) * s.row_ss / 100.0 < 1.0


def test_chip_keeps_the_geometry(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    xml = XML.read_text(encoding="utf-8")
    full = sm.parse(xml)
    chip_text = sicd.chip_xml(xml, 9000, 20000, 1000, 3000)
    chip = sm.parse(chip_text)
    assert (chip.rows, chip.cols, chip.first_row, chip.first_col) == (1000, 3000, 9000, 20000)
    a = full.image_to_ground(np.array([9500.0]), np.array([21000.0]))[3]
    b = chip.image_to_ground(np.array([500.0]), np.array([1000.0]))[3]
    assert np.linalg.norm(a - b) < 1e-6
    data = (np.arange(12).reshape(3, 4) + 1j).astype(np.complex64)                 # SICD rows x cols
    tif = tmp_path / "c_SICD.tif"
    with rasterio.open(tif, "w", driver="GTiff", width=4, height=3, count=1, dtype="complex64") as dst:
        dst.write(data, 1)
    tif.with_suffix(".xml").write_text(chip_text, encoding="utf-8")
    d, x = sicd.find_files(tmp_path)
    m = sicd.read_metadata(d, x)
    np.testing.assert_array_equal(sicd.read_slc(d, m, (1, 3, 0, 2)), data[0:2, 1:3].T)
    m.row_sgn = 1                                                                  # +1 products are conjugated
    np.testing.assert_array_equal(sicd.read_slc(d, m, (1, 3, 0, 2)), np.conj(data[0:2, 1:3].T))


def test_unsupported_grid_is_refused():
    from geoeyes.core.errors import SensorError
    xml = XML.read_text(encoding="utf-8").replace("<Type>RGAZIM</Type>", "<Type>PLANE</Type>")
    with pytest.raises(SensorError):
        sm.parse(xml)


def test_central_reference_keeps_the_most_scenes():
    """The Las Vegas Umbra stack: the median date (2025-03-07) has the lowest incidence and would leave four scenes
    out; the central incidence keeps all eight."""
    from datetime import date

    from geoeyes.processing.stack.native.sicd_stack import MAX_INCIDENCE_DIFF_DEG, central_reference
    inc = {date(2025, 2, 15): 42.92, date(2025, 2, 20): 41.25, date(2025, 3, 4): 43.99, date(2025, 3, 7): 39.34,
           date(2025, 5, 5): 43.48, date(2025, 5, 10): 40.39, date(2025, 7, 16): 40.87, date(2025, 8, 3): 42.01}
    r = central_reference(inc)
    assert all(abs(v - inc[r]) <= MAX_INCIDENCE_DIFF_DEG for v in inc.values())
    assert r == date(2025, 8, 3)


def test_coarse_offset_finds_a_shift_beyond_the_residual_tiles():
    """Two speckled scenes of one urban grid, the secondary 223 lines and 7 samples away (Umbra positions differ by
    tens of metres): the coarse search finds the shift that the 256-pixel residual tiles alias."""
    import numpy as np

    from geoeyes.processing.stack.native.sicd_stack import coarse_offset
    rng = np.random.default_rng(3)
    ny, nx = 3000, 2600
    scene = np.zeros((ny + 400, nx + 40))
    for _ in range(4000):                                       # bright blocks (buildings) over clutter
        r, c = rng.integers(0, ny + 380), rng.integers(0, nx + 20)
        scene[r:r + rng.integers(4, 20), c:c + rng.integers(4, 20)] += rng.uniform(5, 30)
    scene += 1.0

    def look(r0, c0):
        a = scene[r0:r0 + ny, c0:c0 + nx]
        return (np.sqrt(a) * (rng.normal(size=a.shape) + 1j * rng.normal(size=a.shape))).astype(np.complex64)
    ref, sec = look(100, 20), look(100 + 223, 20 + 7)            # sec pixel (i, j) = ref pixel (i + 223, j + 7)
    dl, ds, n = coarse_offset(ref, sec)
    assert n >= 5 and (dl, ds) == (-223.0, -7.0)               # sample the secondary at line - 223, sample - 7
