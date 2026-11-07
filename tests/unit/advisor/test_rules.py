"""Site rules (site advisor V2): the rule file is consistent, conditions parse, rules fire on the right sites, a
later rule wins over an earlier one, missing metrics are reported, and the comparison with a project works. The
rules must reproduce the owner's settings of hcm_d18 and hp_maychai (no change suggested)."""
import pytest

from geoeyes.advisor import catalog, rules
from geoeyes.config.loader import load_dict


def _profile(*, relief=11.0, steep=0.0, built=0.58, tree=0.17, crop=0.09, grass=0.08, water=0.03, soft=1.0,
             koppen="Aw", dates=98, span=3.8, gap=96, coh=0.45, centre=(106.635, 10.733)):
    return {"area_km2": 167.0, "centre": list(centre),
            "terrain": {"relief_m": relief, "slope_median_deg": 2.0, "steep_share": steep, "very_steep_share": 0.0},
            "land_cover": {"shares": {"built": built, "tree": tree, "crop": crop, "grass": grass, "water": water,
                                      "bare": 0.0, "wetland": 0.0}, "dominant": "built"},
            "geology": {"soft_share": soft, "dominant": "su"},
            "climate": {"koppen": koppen, "rain_annual_mm": 1800, "rh_mean_pct": 80},
            "data": {"tracks": {"t": {"sensor": "sentinel1", "band": "C", "dates": dates, "span_years": span,
                                      "revisit_median_days": 12, "max_gap_days": gap, "coherence_median": coh,
                                      "bperp_spread_m": 250}}}}


def test_rule_file_is_consistent():
    regions, rs = rules.load()
    assert regions and rs
    known = set(rules.metrics(_profile()))
    cat = catalog.load()
    for r in rs:
        assert r.why["en"] and r.why["vi"] and r.source, r.id
        for c in r.when:
            assert c.metric in known, f"{r.id}: unknown metric {c.metric}"
        for path in r.set:
            assert path in cat


@pytest.mark.parametrize("text, expected", [
    ("terrain.relief_m < 100", ("terrain.relief_m", "<", 100)),
    ("climate.zone == 'A'", ("climate.zone", "==", "A")),
    ('site.regions contains "HCMC"', ("site.regions", "contains", "HCMC")),
    ("climate.koppen in ['Aw', 'Am']", ("climate.koppen", "in", ["Aw", "Am"])),
    ("land_cover.built >= 0.4", ("land_cover.built", ">=", 0.4)),
])
def test_parse_condition(text, expected):
    c = rules.parse_condition(text)
    assert (c.metric, c.op, c.value) == expected


def test_parse_condition_refuses_garbage():
    with pytest.raises(ValueError):
        rules.parse_condition("import os")


def test_hcmc_profile_gives_the_owner_settings():
    a = rules.evaluate(_profile())
    r = {k: s.value for k, s in a.recipe.items()}
    assert r["ps.subtr_tropo"] == "n" and r["atmosphere.method"] == "none"
    assert r["project.method"] == "psi" and r["ps.unwrap_grid_size"] == 50
    assert r["ps.unwrap_ps_rate"] == "y" and r["acquire.max_per_month"] == 0
    assert "long-gap" in a.matched


def test_mountain_profile_gives_weather_model_and_phase_linking():
    p = _profile(relief=1160, steep=0.62, built=0.0, tree=0.9, crop=0.0, grass=0.09, soft=0.0, koppen="Af",
                 centre=(108.15, 15.15))
    a = rules.evaluate(p)
    r = {k: s.value for k, s in a.recipe.items()}
    assert r["atmosphere.method"] == "era5" and r["ps.subtr_tropo"] == "y"
    assert r["project.method"] == "psds" and r["phase_linking.enabled"] is True
    assert r["stack.dem"] == "copernicus-30" and "ps.unwrap_grid_size" not in r
    assert {"tropical-convection", "steep-terrain"} <= {rid for rid, _ in a.notes}


def _csk_profile():
    """Central Hanoi seen by COSMO-SkyMed before its stack exists: the data part holds only the configured sensor."""
    p = _profile(relief=15.0, built=0.60, tree=0.16, crop=0.02, grass=0.0, water=0.21, koppen="Cwa",
                 centre=(105.842, 21.033))
    p["data"] = {"tracks": {"cosmo_skymed-asc": {"source": "configuration (no stack yet)", "sensor": "cosmo_skymed"}}}
    return p


def test_csk_keeps_its_phase_linking_chain():
    a = rules.evaluate(_csk_profile())
    r = {k: s.value for k, s in a.recipe.items()}
    assert a.metrics["data.band"] == "X"                                   # from the sensor, before any stack
    assert "urban-psi" not in a.matched and "csk-chain" in a.matched
    assert r["phase_linking.enabled"] is True and r["phase_linking.gaussian_sigma"] == 1.5
    assert "acquire.max_per_month" not in r                                # the Sentinel-1 download rule
    assert "project.method" not in r
    assert "soft-urban-subsidence" in {rid for rid, _ in a.notes}          # the reference note still applies


def test_csk_project_from_its_preset_needs_no_linking_change():
    raw = {"schema": "geoeyes.project/1", "project": {"name": "x", "method": "psi"},
           "aoi": {"bbox": [105.8092, 21.0012, 105.8754, 21.0639]},
           "tracks": [{"sensor": "cosmo_skymed", "direction": "ascending"}]}
    cmp = rules.compare(rules.evaluate(_csk_profile()), load_dict(raw), raw)
    assert {c["path"] for c in cmp["changes"]} == {"ps.subtr_tropo"}       # the preset already links and filters
    assert {"phase_linking.enabled", "phase_linking.gaussian_sigma"} <= {a["path"] for a in cmp["agree"]}


def test_long_gap_is_measured_in_revisits():
    s1 = rules.metrics(_profile(gap=96))                                   # 96 days at a 12-day revisit: 8
    assert s1["data.gap_ratio"] == 8
    p = _profile(gap=160)
    p["data"]["tracks"]["t"].update(sensor="cosmo_skymed", band="X", revisit_median_days=64)
    assert "long-gap" not in rules.evaluate(p).matched                     # 160 days at a 64-day revisit: 2.5


def test_missing_metric_is_reported_not_guessed():
    p = _profile()
    p.pop("data")
    a = rules.evaluate(p)
    assert a.skipped["soft-urban-ps-rate"] == ["data.dates"]
    assert "ps.unwrap_ps_rate" not in a.recipe


def test_a_known_bad_qc_coherence_is_not_used():
    p = _profile(coh=1.0)
    p["data"]["tracks"]["t"]["warning"] = "stack QC coherence is 1.0"
    assert "data.coherence_median" not in rules.metrics(p)


def test_later_rule_wins_and_the_replaced_value_is_kept(monkeypatch):
    rs = (rules.Rule("a", (rules.parse_condition("terrain.relief_m < 100"),), {"ps.unwrap_grid_size": 10},
                     {"en": "", "vi": ""}, {"en": "x", "vi": "x"}, "s"),
          rules.Rule("b", (rules.parse_condition("site.regions contains 'HCMC'"),), {"ps.unwrap_grid_size": 50},
                     {"en": "", "vi": ""}, {"en": "y", "vi": "y"}, "s"))
    monkeypatch.setattr(rules, "load", lambda: ({"HCMC": [106.3, 10.35, 107.05, 11.2]}, rs))
    s = rules.evaluate(_profile()).recipe["ps.unwrap_grid_size"]
    assert (s.value, s.rule, s.replaced) == (50, "b", [("a", 10)])


def _project(extra_ps: dict, acquire: dict | None = None):
    raw = {"schema": "geoeyes.project/1", "project": {"name": "x", "method": "psi"},
           "aoi": {"bbox": [106.56, 10.69, 106.71, 10.78]},
           "tracks": [{"sensor": "sentinel1", "direction": "descending", "relative_orbit": 18}],
           "acquire": acquire or {"max_per_month": 0}, "ps": extra_ps}
    return load_dict(raw), raw


def test_rules_reproduce_hcm_d18():
    cfg, raw = _project({"da_threshold": 0.42, "unwrap_grid_size": 50, "ref_centre_lonlat": [106.6445, 10.7602],
                         "ref_radius": 300, "subtr_tropo": "n", "unwrap_ps_rate": "y",
                         "unwrap_grid_filter_unit": "y"})
    cmp = rules.compare(rules.evaluate(_profile()), cfg, raw)
    assert cmp["changes"] == []
    assert {r["path"] for r in cmp["unexplained"]} == {"ps.ref_centre_lonlat", "ps.ref_radius"}
    # [ps] da_threshold is not read by the engine (the threshold is [selection] da_threshold): reported apart
    assert cmp["ignored"] == [{"path": "ps.da_threshold", "value": 0.42, "did_you_mean": "selection.da_threshold"}]


def test_rules_reproduce_hp_maychai():
    p = _profile(relief=10.2, built=0.44, water=0.18, koppen="Cwa", dates=36, span=1.3, gap=36,
                 centre=(106.69, 20.87))
    cfg, raw = _project({"da_threshold": 0.42, "subtr_tropo": "n"})
    cmp = rules.compare(rules.evaluate(p), cfg, raw)
    assert cmp["changes"] == []


def test_compare_lists_a_change_and_the_recipe_is_valid():
    cfg, raw = _project({}, acquire={"max_per_month": 2})
    p = _profile(relief=1160, steep=0.62, built=0.0, tree=0.9, crop=0.0, grass=0.09, soft=0.0, koppen="Af",
                 centre=(108.15, 15.15))
    a = rules.evaluate(p)
    cmp = rules.compare(a, cfg, raw)
    changed = {r["path"]: (r["current"], r["suggested"]) for r in cmp["changes"]}
    assert changed["atmosphere.method"] == ("none", "era5") and changed["project.method"] == ("psi", "psds")
    # every suggested value is accepted by the configuration schema
    new = {k: dict(v) if isinstance(v, dict) else v for k, v in raw.items()}
    for path, s in a.recipe.items():
        section, key = path.split(".", 1)
        new.setdefault(section, {})[key] = s.value
    load_dict(new)


def test_report_in_both_languages():
    cfg, raw = _project({"subtr_tropo": "y"})
    a = rules.evaluate(_profile())
    cmp = rules.compare(a, cfg, raw)
    en, vi = rules.report(a, cmp, "en"), rules.report(a, cmp, "vi")
    assert "ps.subtr_tropo: 'y' -> 'n'" in en and "Cần đổi" in vi and "Vì sao" in vi
