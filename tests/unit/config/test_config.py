"""geoeyes.config: schema validation, presets, subswath overrides, TOML round trip, legacy migration."""
import json
from datetime import date
from pathlib import Path

import pytest

from geoeyes.config import Method, Sensor, dump, load, load_dict, resolve_subswath
from geoeyes.config.migrate import migrate
from geoeyes.core.errors import ConfigError

TEMPLATE = Path(__file__).with_name("data") / "legacy_template.json"     # the legacy config/template.json


def _minimal(**over):
    d = {"schema": "geoeyes.project/1",
         "project": {"name": "demo", "method": "psi"},
         "tracks": [{"sensor": "sentinel1", "direction": "ascending", "relative_orbit": 78,
                     "subswaths": ["IW3"]}]}
    d.update(over)
    return d


def test_minimal_config_gets_sensor_preset():
    cfg = load_dict(_minimal())
    assert cfg.project.method is Method.PSI
    assert cfg.tracks[0].track_id == "sentinel1-asc-078"
    assert cfg.stack.geometry == "radar" and cfg.network.max_perp_m == 150.0


def test_tsx_preset_keeps_map_geometry():
    d = _minimal(tracks=[{"sensor": "terrasar_x", "direction": "descending"}])
    assert load_dict(d).stack.geometry == "map"


@pytest.mark.parametrize("bad", [
    {"project": {"name": "Bad Name", "method": "psi"}},
    {"tracks": []},
    {"aoi": {"bbox": [10, 0, 5, 1]}},
    {"stack": {"engine": "gamma"}},
    {"unknown_section": {}},
])
def test_invalid_configs_raise_config_error(bad):
    with pytest.raises(ConfigError):
        load_dict(_minimal(**bad))


def test_capella_requires_ps_lite():
    d = _minimal(tracks=[{"sensor": "capella", "direction": "ascending"}])
    with pytest.raises(ConfigError, match="ps_lite"):
        load_dict(d)
    d["project"]["method"] = "ps_lite"
    assert load_dict(d).sensors == {Sensor.CAPELLA}


def test_subswath_override_deep_merges():
    d = _minimal(ps={"weed_noisy_check": "y", "max_topo_err": 20},
                 overrides={"IW1": {"ps": {"weed_noisy_check": "n"}, "selection": {"da_threshold": 0.35}}})
    cfg = load_dict(d)
    iw1 = resolve_subswath(cfg, "IW1")
    assert iw1.ps == {"weed_noisy_check": "n", "max_topo_err": 20}
    assert iw1.selection.da_threshold == 0.35
    assert resolve_subswath(cfg, "IW2") is cfg


def test_toml_round_trip(tmp_path):
    cfg = load_dict(_minimal(acquire={"date_range": [date(2024, 5, 1), date(2024, 10, 31)]},
                             aoi={"bbox": [-99.03, 19.30, -98.98, 19.42]}))
    p = dump(cfg, tmp_path / "project.toml")
    assert load(p) == cfg


def test_migrate_template_s1():
    tpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    out, rep = migrate({"project": {"name": "london"}}, {"water_mask_run": False, "crlink_run": False},
                       template=tpl)
    cfg = load_dict(out)
    assert cfg.project.method is Method.PSI
    assert [t.direction.value for t in cfg.tracks] == ["descending", "ascending"]
    assert [t.frame for t in cfg.tracks] == [422, 163]
    assert cfg.acquire.date_range == (date(2020, 9, 1), date(2020, 12, 31))
    assert cfg.ps["max_topo_err"] == 20.0 and "tropo_method" not in cfg.ps
    assert cfg.atmosphere.method == "a_era5"
    assert cfg.phase_linking.enabled and cfg.phase_linking.half_window == (5, 5)
    assert cfg.phase_linking.gaussian_sigma == 1.5
    assert set(cfg.pipeline.disabled) == {"water_mask", "validate"}
    assert "project.dbschema" in rep.dropped
