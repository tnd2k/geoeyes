"""geoeyes.validation.corner_reflector: trihedral RCS model, point-target measurements, coherence, inputs,
and the whole chain on the Hanoi CR-VP bursts against the legacy SAFE-based report (19/10/2026)."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from geoeyes.validation.corner_reflector import measure, trihedral
from geoeyes.validation.corner_reflector.inputs import CRSetup, CRTarget, read_setup, read_targets, setup_at

WL = 0.05546576           # S1 C-band
LOS_AZ, LOS_EL = 100.7, 50.29   # S1D track 91 descending over Hanoi (ground -> satellite)
ARCHIVE = Path(r"D:\projects\geoeyes_workspace\archive\sentinel1\sentinel1-desc-091")


# ── trihedral ────────────────────────────────────────────────────────────────

def test_boresight_of_flat_base_is_35_26_deg_and_tilt_adds():
    assert trihedral.boresight(101, 0)[1] == pytest.approx(35.264, abs=0.01)
    az, el = trihedral.boresight(101, 16)
    assert el == pytest.approx(51.264, abs=0.01)
    assert az == pytest.approx(101, abs=0.01)


def test_rcs_on_boresight_equals_peak_formula():
    req = trihedral.required_pointing(LOS_AZ, LOS_EL)
    assert req["base_tilt_deg"] == pytest.approx(15.03, abs=0.01)
    on = trihedral.rcs_dbsm(0.8, WL, LOS_AZ, LOS_EL, req["face_azimuth_deg"], req["base_tilt_deg"])
    assert on == pytest.approx(trihedral.peak_rcs_dbsm(0.8, WL), abs=0.01)
    assert on == pytest.approx(27.46, abs=0.02)


@pytest.mark.parametrize("tilt, expected", [(67 - 35.264, 25.4), (0.0, 25.8), (16.0, 27.5)])
def test_rcs_for_cr_vp_setups(tilt, expected):
    assert trihedral.rcs_dbsm(0.8, WL, LOS_AZ, LOS_EL, 101.0, tilt) == pytest.approx(expected, abs=0.05)


def test_rcs_behind_reflector_is_zero():
    assert trihedral.rcs_m2(0.8, WL, LOS_AZ, LOS_EL, LOS_AZ + 180, 0.0) == 0.0


# ── measurements ─────────────────────────────────────────────────────────────

def _scene(rng, shape=(64, 160), at=(32.0, 80.0), amp=40.0):
    """Complex Gaussian clutter (beta0 = 1) plus a point target with a sinc impulse response."""
    z = (rng.normal(size=shape) + 1j * rng.normal(size=shape)) / np.sqrt(2)
    y, x = np.mgrid[0:shape[0], 0:shape[1]]
    z += amp * np.sinc(y - at[0]) * np.sinc((x - at[1]) / 1.6)
    return z


def test_measure_rcs_finds_target_and_reports_offset():
    rng = np.random.default_rng(0)
    z = _scene(rng, at=(33.0, 82.0))
    r = measure.measure_rcs(measure.beta0(z, 1.0), 1000, 2000, 1032.0, 2080.0, 2.33, 13.98, search=(1, 2))
    assert (round(r.peak_line), round(r.peak_sample)) == (1033, 2082)
    assert r.scr_db > 15
    clutter_only = measure.measure_rcs(measure.beta0(_scene(rng, amp=0.0), 1.0), 0, 0, 32, 80, 2.33, 13.98)
    assert r.rcs_dbsm > clutter_only.clutter_dbsm + 15


def test_offset_and_coherence_of_shifted_copy():
    rng = np.random.default_rng(1)
    m = _scene(rng, shape=(96, 256), amp=20.0)
    s = np.roll(m, (2, -3), axis=(0, 1)) * np.exp(1j * 0.7)          # same scene, shifted, phase offset
    dy, dx = measure.offset(m, s)
    assert (dy, dx) == pytest.approx((-2, 3), abs=0.2)
    mm, ss, _ = measure.coregister(m, s)
    c = measure.coherence_map(mm[8:-8, 16:-16], ss[8:-8, 16:-16])
    assert np.nanmedian(c) > 0.95


def test_coherence_of_independent_noise_is_low():
    rng = np.random.default_rng(2)
    a, b = _scene(rng, amp=0.0), _scene(rng, amp=0.0)
    assert np.nanmedian(measure.coherence_map(a, b)) < 0.45


def test_coherence_is_insensitive_to_a_fringe():
    rng = np.random.default_rng(3)
    m = _scene(rng, shape=(64, 256), amp=0.0)
    y, x = np.mgrid[0:64, 0:256]
    s = m * np.exp(1j * 2 * np.pi * (0.05 * y + 0.12 * x))
    assert np.nanmedian(measure.coherence_map(m, s)) > 0.95


# ── inputs ───────────────────────────────────────────────────────────────────

def test_read_targets_optional_columns(tmp_path):
    p = tmp_path / "points.csv"
    p.write_text("name,lon,lat,height\nA,105.7,21.0,-5.8\n,105.8,21.1,\n", encoding="utf-8")
    t = read_targets(p, default_edge_m=0.8)
    assert [x.name for x in t] == ["A", "CR2"]
    assert t[0].height == -5.8 and t[1].height is None and t[0].edge_m == 0.8


def test_setup_log_applies_until_next_entry(tmp_path):
    p = tmp_path / "cr_setup.csv"
    p.write_text('name,valid_from,face_azimuth_deg,base_tilt_deg,note\n'
                 'CR-VP,2026-09-20 17:00,101,31.74,"welded wrong, 67°"\n'
                 '*,2026-09-22 12:00,101,0,flat\n'
                 'CR-VP,2026-10-15 17:00,101,16,raised 16°\n', encoding="utf-8")
    s = read_setup(p)
    hcm = ZoneInfo("Asia/Ho_Chi_Minh")
    at = datetime(2026, 10, 3, 22, 50, tzinfo=ZoneInfo("UTC")).astimezone(hcm)   # 05:50 local on 10-04
    assert setup_at(s, "CR-VP", at).base_tilt_deg == 0
    assert setup_at(s, "CR-VP", datetime(2026, 9, 22, 5, 50, tzinfo=hcm)).note == "welded wrong, 67°"
    assert setup_at(s, "CR-VP", datetime(2026, 10, 16, 5, 50, tzinfo=hcm)).base_tilt_deg == 16
    assert setup_at(s, "CR-VP", datetime(2026, 9, 1, tzinfo=hcm)) is None


def test_report_survives_missing_dbsm(tmp_path):
    """A CR seen from behind (expected -inf) or a cell below clutter (measured NaN) must not stop the
    figure, and the JSON must stay strict (no NaN/Infinity)."""
    import json

    from geoeyes.validation.corner_reflector.pipeline import Observation
    from geoeyes.validation.corner_reflector.report import _finite, rcs_figure

    def obs(date, exp, meas):
        return Observation(reflector="CR", date=date, acquired_utc="", acquired_local="", platform="S1D", track=91,
                           direction="descending", swath="IW2", burst=0, los_azimuth_deg=100.7,
                           los_elevation_deg=50.3, incidence_deg=39.7, setup_face_azimuth_deg=101,
                           setup_base_tilt_deg=16, setup_source="log", setup_note="", expected_dbsm=exp,
                           measured_dbsm=meas, scr_db=float("nan"), difference_db=meas - exp,
                           within_tolerance=False, peak_lat=0, peak_lon=0, offset_north_m=0, offset_east_m=0,
                           offset_m=0, nearby_dbsm=float("nan"), nearby_offset_m=0, wavelength_m=WL)
    oo = [obs("2026-09-21", float("-inf"), 24.1), obs("2026-10-03", 25.8, float("nan"))]
    assert rcs_figure(oo, 0.8, WL, tmp_path / "rcs.png").exists()
    text = json.dumps(_finite({"a": float("-inf"), "b": [float("nan"), 1.0]}))
    assert json.loads(text) == {"a": None, "b": [None, 1.0]}


# ── whole chain on real bursts ──────────────────────────────────────────────

# legacy report results/hanoi/cr_report/20261019-171235_DESC (SAFE products of the same acquisitions)
LEGACY = {"2026-09-21": (24.08129672690064, 25.362001216834273, -6.2909, -8.9894),
          "2026-10-03": (30.762414239644137, 25.80984074700641, 1.6491, -4.9805),
          "2026-10-15": (24.917019121018548, 27.45748070760232, -4.0853, -8.4010)}
LEGACY_COH = {("2026-09-21", "2026-10-03"): 0.7591191173060914, ("2026-09-21", "2026-10-15"): 0.7377002253753203,
              ("2026-10-03", "2026-10-15"): 0.873580066598392}


@pytest.mark.skipif(not ARCHIVE.exists(), reason="Hanoi S1 track 91 bursts not in the archive")
def test_cr_vp_matches_the_legacy_report():
    from geoeyes.validation.corner_reflector.pipeline import run
    from geoeyes.validation.corner_reflector.s1burst import scenes
    z = ZoneInfo("Asia/Ho_Chi_Minh")
    setups = [CRSetup("CR-VP", datetime(2026, 9, 1, tzinfo=z), 101.0, 31.74),
              CRSetup("CR-VP", datetime(2026, 9, 25, tzinfo=z), 101.0, 0.0),
              CRSetup("CR-VP", datetime(2026, 10, 10, tzinfo=z), 101.0, 16.0)]
    sc = [s for s in scenes(ARCHIVE) if s.date in LEGACY]
    res = run([CRTarget("CR-VP", 21.0082438335, 105.73276644651, -5.8189, 0.8)], sc, setups)
    for o in res["observations"]:
        meas, exp, dn, de = LEGACY[o.date]
        assert (o.swath, o.burst) == ("IW2", 4)
        assert o.measured_dbsm == pytest.approx(meas, abs=1e-9)             # same pixels, same calibration
        assert o.expected_dbsm == pytest.approx(exp, abs=1e-6)
        assert (o.offset_north_m, o.offset_east_m) == pytest.approx((dn, de), abs=0.02)
    for c in res["coherence"]:
        assert c["at_reflector"] == pytest.approx(LEGACY_COH[(c["date_1"], c["date_2"])], abs=1e-6)
