"""Sentinel-1 burst search parsing, and (when the archive is present) burst metadata + native coregistration."""
import os
from pathlib import Path

import numpy as np
import pytest

from geoeyes.core.types import OrbitDirection
from geoeyes.sensors.sentinel1.asf import group_by_acquisition, parse_feature


def test_orbit_kinds_and_fallback_wording():
    from geoeyes.report.methods import _orbit_text
    from geoeyes.sensors.sentinel1.orbits import _NAME_RE, PoeorbProvider
    m = _NAME_RE.fullmatch("S1D_OPER_AUX_RESORB_OPOD_20261016T021512_V20261015T221224_20261016T012954.EOF")
    assert m and m.group(1) == "S1D" and m.group(2) == "RESORB"
    p = PoeorbProvider.__new__(PoeorbProvider)
    p.used = {"a": "POEORB", "b": "POEORB", "c": "RESORB"}
    assert p.summary() == "POEORB (2), RESORB (1)"
    assert _orbit_text("POEORB (16)") == "precise (POEORB)"
    assert "restituted" in _orbit_text(p.summary()) and _orbit_text("") == "annotation"


FEATURE = {
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [[[-99.55, 19.10], [-98.80, 19.23], [-98.84, 19.42],
                                                     [-99.58, 19.29], [-99.55, 19.10]]]},
    "properties": {
        "fileID": "S1_165499_IW3_20240807T004900_VV_3001-BURST",
        "url": "https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20240807T004846_20240807T004913_055100_"
               "06B6C4_3001/IW3/VV/5.tiff",
        "additionalUrls": ["https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20240807T004846_20240807T004913_"
                           "055100_06B6C4_3001/IW3/VV/5.xml"],
        "bytes": "148200208", "startTime": "2024-08-07T00:49:02Z", "pathNumber": 78, "orbit": 55100,
        "flightDirection": "ASCENDING", "platform": "Sentinel-1A", "polarization": "VV",
        "burst": {"fullBurstID": "078_165499_IW3", "relativeBurstID": 165499, "burstIndex": 5, "subswath": "IW3"},
    },
}


def test_parse_feature():
    r = parse_feature(FEATURE)
    assert r.full_burst_id == "078_165499_IW3" and r.burst_index == 5 and r.subswath == "IW3"
    assert r.slc_name.startswith("S1A_IW_SLC__1SDV_20240807") and r.metadata_url.endswith("5.xml")
    assert r.direction is OrbitDirection.ASCENDING and r.track_id == "sentinel1-asc-078"
    assert r.footprint_wkt.startswith("POLYGON((-99.55 19.1")
    assert list(group_by_acquisition([r])) == [r.slc_name]


EOF = """<?xml version="1.0"?>
<Earth_Explorer_File><Data_Block><List_of_OSVs count="6">{osv}</List_of_OSVs></Data_Block></Earth_Explorer_File>"""
OSV = ("<OSV><UTC>UTC=2024-07-14T00:4{m}:{s:02d}.000000</UTC><X unit=\"m\">{x}</X><Y unit=\"m\">0</Y>"
       "<Z unit=\"m\">0</Z><VX unit=\"m/s\">10</VX><VY unit=\"m/s\">0</VY><VZ unit=\"m/s\">0</VZ></OSV>")


def test_read_eof_window(tmp_path):
    from datetime import datetime

    from geoeyes.sensors.sentinel1.orbits import _NAME_RE, read_eof
    osv = "".join(OSV.format(m=8, s=s, x=7e6 + 10 * s) for s in range(0, 60, 10))
    p = tmp_path / "S1A_OPER_AUX_POEORB_OPOD_20240803T070744_V20240713T225942_20240715T005942.EOF"
    p.write_text(EOF.format(osv=osv), encoding="utf-8")
    sv = read_eof(p, datetime(2024, 7, 14, 0, 48, 0), datetime(2024, 7, 14, 0, 48, 40))
    assert len(sv.t) == 5 and sv.pos[0, 0] == 7e6
    pos, vel = sv.interpolate(25.0)
    assert abs(pos[0, 0] - (7e6 + 250)) < 1e-6 and abs(vel[0, 0] - 10) < 1e-9
    assert _NAME_RE.fullmatch(p.name).group(1) == "S1A"


ARCHIVE = Path(os.environ.get("GEOEYES_WORKSPACE", r"D:\projects\geoeyes_workspace")) / \
    "archive/sentinel1/sentinel1-asc-078/2024"


@pytest.mark.slow
@pytest.mark.skipif(not ARCHIVE.exists(), reason="S1 Mexico burst archive not present")
def test_real_burst_metadata_matches_esa_geolocation_grid():
    from geoeyes.core.geodesy import llh_to_ecef
    from geoeyes.sensors.sentinel1.burst import C, read_metadata
    scene = sorted(ARCHIVE.iterdir())[0]
    m = read_metadata(next(scene.glob("*_VV.xml")), "IW3", "VV", 5)
    assert (m.lines, m.samples) == (1508, 24568) and abs(m.wavelength - 0.05547) < 1e-4
    g = m.grid
    x = llh_to_ecef(g.lat, g.lon, g.height)
    t = m.orbit.seconds(m.sensing_start) + g.azimuth_time
    tz = m.orbit.zero_doppler_time(x, t)
    assert np.abs(tz - t).max() < 1e-5                                   # 10 µs
    assert np.abs(m.orbit.slant_range(x, tz) - g.slant_range_time * C / 2).max() < 0.01
