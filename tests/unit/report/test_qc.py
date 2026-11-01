"""Quality checks of the report (geoeyes.report.qc): ionosphere at dusk, the velocity step at a subswath seam, the
ramp left against the ionosphere removed."""
import math

import h5py
import numpy as np
import pandas as pd

from geoeyes.report import qc


def test_ionosphere_at_dusk_needs_the_correction():
    a = {"sensor": "sentinel1", "sensing_mid_utc": {"2025-10-04": "2025-10-04T11:06:33"}}
    r = qc.ionosphere(a, 105.8, 21.0)[0]
    assert r["status"] == "review" and "18:" in r["note"]
    assert qc.ionosphere(a | {"ionosphere": "split_spectrum"}, 105.8, 21.0)[0]["status"] == "pass"
    dawn = {"sensor": "sentinel1", "sensing_mid_utc": {"2025-10-01": "2025-10-01T22:51:16"}}
    assert qc.ionosphere(dawn, 105.8, 21.0)[0]["status"] == "pass"


def test_velocity_step_at_a_seam():
    rng = np.random.default_rng(0)
    inc = np.tile(np.linspace(41.0, 42.5, 300), (10, 1))         # incidence grows with the column
    n = 20_000
    pi = rng.uniform(41.0, 42.5, n)
    seam_inc = float(inc[0, 150])
    v = rng.normal(0, 1, n) + np.where(pi >= seam_inc, 8.0, 0.0)
    pts = pd.DataFrame({"incidence_deg": pi, "vel_los_mm_yr": v})
    a = {"subswath_columns": {"IW2": [0, 1150], "IW3": [1150, 5000]}, "crop_samples": [1000, 1300],
         "subswath_phase_offsets": {"2025-10-16": {"anchor": "IW3", "IW3": {"rad": -2.2}}}}
    r = qc.seams(a, inc, pts)[0]
    assert r["check"].endswith("IW3 seam") and r["status"] == "review"
    assert abs(float(r["value"].split()[0]) - 8.0) < 0.5 and "1 above 1 rad" in r["note"]
    pts["vel_los_mm_yr"] = rng.normal(0, 1, n)
    assert qc.seams(a, inc, pts)[0]["status"] == "pass"


def test_residual_ramp_correlated_with_the_ionosphere_removed(tmp_path):
    rng = np.random.default_rng(1)
    n, m = 5000, 12
    lon, lat = 105.8 + rng.uniform(0, 0.15, n), 21.0 + rng.uniform(0, 0.13, n)
    x = (lon - lon.mean()) * qc.M_LON * math.cos(math.radians(lat.mean())) / 1000
    y = (lat - lat.mean()) * qc.M_LAT / 1000
    g = rng.normal(0, 0.2, (m, 2))                                    # ionospheric gradient removed (az, rg), rad/km
    ph = np.stack([0.5 * (g[j, 0] * y + g[j, 1] * x) for j in range(m)], axis=1)  # heading 0: az = north, rg = east
    dates = [f"2025-{1 + j // 2:02d}-{1 + 14 * (j % 2):02d}" for j in range(m)]
    with h5py.File(tmp_path / "state.h5", "w") as f:
        f["ps/lon"], f["ps/lat"], f["phase/unwrapped"] = lon, lat, ph
        f["time/ifg_dates"] = np.array([d.encode() for d in dates])
    a = {"ionosphere_per_date": {d: {"rad_per_km_az_rg": list(g[j])} for j, d in enumerate(dates)}}
    rows = qc.residual_ramps(tmp_path, a, 0.0, 4.4)
    assert [r["status"] for r in rows] == ["review", "review"]      # half of it left: the scale is wrong
    assert all(float(r["value"].split()[-1]) > 0.95 for r in rows)


def test_method_shows_the_parameters_the_engine_used():
    from geoeyes.report import methods
    density = {"da_max": 0.4, "table": {}}
    t = {r[0]: r[1] for r in methods.describe(None, _Psm(), density, {})["params"]}
    assert t["Selection"] == "80 % random pixels (PERCENT)" and t["Max. height error (m)"] == "20"   # the defaults
    auto = {"da_max": 0.4, "table": {"max_topo_err": 2.789, "select_method": "PERCENT", "percent_rand": 92},
            "resolved": {"max_topo_err": {"from": "auto", "rule": "median height of ambiguity / 4"}}}
    t = {r[0]: r[1] for r in methods.describe(None, _Psm(), auto, {})["params"]}
    assert t["Selection"] == "92 % random pixels (PERCENT)"
    assert t["Max. height error (m)"] == "2.79 (auto: median height of ambiguity / 4)"


class _Psm:
    engine = "geoeyes.ps/3"
    metrics: dict = {}
    extra: dict = {}
