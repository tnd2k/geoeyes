"""Site profile (site advisor V1): Köppen classes of known climates, the data part from a stack QC, the cache and
the isolation of a failing part. No network: the readers are replaced."""
import json
from types import SimpleNamespace

import pytest

from geoeyes.advisor import profile as prof

# monthly climatologies (temperature °C, rain mm), Jan..Dec, rounded from station normals
CLIMATES = {
    "Aw": (10.8, [26, 27, 28, 29, 29, 28, 28, 28, 27, 27, 27, 26], [14, 4, 12, 42, 220, 331, 313, 268, 334, 268, 115, 50]),  # HCMC
    "Af": (1.3, [27] * 12, [240, 160, 180, 170, 170, 160, 160, 170, 170, 190, 250, 300]),                        # Singapore
    "Cwa": (21.0, [16, 17, 20, 24, 28, 29, 29, 29, 28, 25, 22, 18], [18, 26, 44, 90, 188, 240, 288, 318, 265, 130, 43, 23]),  # Hanoi
    "Cwb": (19.4, [14, 16, 18, 19, 19, 18, 17, 17, 17, 16, 15, 14], [8, 5, 10, 25, 55, 130, 170, 165, 130, 60, 10, 6]),     # Mexico City
    "Csa": (38.0, [10, 11, 13, 16, 20, 25, 28, 28, 24, 19, 15, 11], [70, 55, 50, 40, 25, 10, 3, 5, 20, 60, 80, 85]),        # Mediterranean
    "BWh": (24.0, [14, 16, 20, 25, 29, 31, 32, 32, 30, 26, 20, 15], [3, 2, 2, 1, 0, 0, 0, 0, 0, 1, 2, 3]),                 # desert
    "ET": (70.0, [-20, -21, -18, -10, -2, 4, 7, 6, 2, -5, -13, -18], [20, 18, 18, 15, 15, 20, 30, 35, 30, 25, 22, 20]),
}


@pytest.mark.parametrize("expected", sorted(CLIMATES))
def test_koppen_of_known_climates(expected):
    lat, t, p = CLIMATES[expected]
    assert prof.koppen(t, p, lat) == expected


def test_koppen_southern_hemisphere_summer_is_october_to_march():
    lat, t, p = CLIMATES["Csa"]
    assert prof.koppen(t[6:] + t[:6], p[6:] + p[:6], -lat) == "Csa"


def test_monthly_climatology_sums_rain_and_averages_the_rest():
    import pandas as pd
    days = pd.date_range("2020-01-01", "2021-12-31", freq="D")
    daily = {"time": [d.strftime("%Y-%m-%d") for d in days], "precipitation_sum": [1.0] * len(days),
             "temperature_2m_mean": [d.month for d in days], "relative_humidity_2m_mean": [80.0] * len(days)}
    c = prof.monthly_climatology(daily)
    assert c["rain_mm"][0] == pytest.approx(31) and c["rain_mm"][1] == pytest.approx(28.5)      # leap year 2020
    assert c["temp_c"] == pytest.approx(list(range(1, 13)))
    assert c["rh_pct"] == pytest.approx([80.0] * 12)


def _project(tmp_path, coherence=0.55):
    qc = tmp_path / "stacks" / "s1-ref" / "qc"
    qc.mkdir(parents=True)
    rows = [{"date": f"2024-{m:02d}-01", "reference": m == 6, "bperp_m": 10.0 * m - 60,
             "coherence_mean": 1.0 if m == 6 else coherence, "height_of_ambiguity_m": 200.0} for m in range(1, 13)]
    (qc / "qc.json").write_text(json.dumps({"stack": "s1-ref", "reference_date": "2024-06-01", "dates": rows}))
    (qc.parent / "stack.zarr").mkdir()
    (qc.parent / "stack.zarr" / "zarr.json").write_text(json.dumps(
        {"attributes": {"track": "sentinel1-desc-018", "sensor": "sentinel1", "wavelength_m": 0.0555}}))
    return SimpleNamespace(root=tmp_path)


def test_data_part_from_the_stack_qc(tmp_path):
    d = prof.data_part(_project(tmp_path), cfg=None)["tracks"]["sentinel1-desc-018"]
    assert d["dates"] == 12 and d["band"] == "C" and d["coherence_median"] == 0.55
    assert d["max_gap_days"] == 31 and d["span_years"] == pytest.approx(0.92, abs=0.01)
    assert d["bperp_spread_m"] == pytest.approx(99, abs=1)
    assert "warning" not in d


def test_data_part_flags_a_qc_coherence_of_one(tmp_path):
    d = prof.data_part(_project(tmp_path, coherence=1.0), cfg=None)["tracks"]["sentinel1-desc-018"]
    assert "warning" in d


def test_profile_caches_site_parts_and_isolates_failures(tmp_path, monkeypatch):
    calls = {"terrain": 0}

    def terrain(grid, dem, cache):
        calls["terrain"] += 1
        return {"relief_m": 12.0, "source": dem}

    def broken(grid):
        raise OSError("no network")

    monkeypatch.setattr(prof, "terrain_part", terrain)
    monkeypatch.setattr(prof, "land_cover_part", broken)
    monkeypatch.setattr(prof, "climate_part", lambda bbox, cache: {"koppen": "Aw"})
    bbox = [106.56, 10.68, 106.71, 10.78]
    p = prof.profile(bbox, cache_root=tmp_path, parts=("terrain", "land_cover", "climate"))
    assert p["terrain"]["relief_m"] == 12.0 and p["climate"]["koppen"] == "Aw"
    assert "land_cover" in p["errors"] and "land_cover" not in p
    prof.profile(bbox, cache_root=tmp_path, parts=("terrain",))
    assert calls["terrain"] == 1                                    # second call from the cache
    prof.profile(bbox, cache_root=tmp_path, parts=("terrain",), refresh=True)
    assert calls["terrain"] == 2


def test_band_and_area():
    assert prof.band_of(0.236) == "L" and prof.band_of(0.0555) == "C" and prof.band_of(0.031) == "X"
    assert prof.area_km2([0, 0, 1, 1]) == pytest.approx(111.32 * 110.54, rel=1e-3)
