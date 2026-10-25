import tomllib
from datetime import date

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("tomlkit")

from geoeyes.api import monitor  # noqa: E402
from geoeyes.core.errors import ConfigError  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402

TOML = """schema = "geoeyes.project/1"
# keep me
[project]
name = "alpha"
method = "psi"
[aoi]
bbox = [-99.01, 19.29, -98.98, 19.32]
[[tracks]]
sensor = "sentinel1"
direction = "ascending"
relative_orbit = 78
"""


@pytest.fixture
def ws(tmp_path):
    w = WorkspaceLayout.at(tmp_path / "ws")
    p = w.project("alpha").ensure()
    p.config.write_text(TOML, encoding="utf-8")
    return w


def test_next_acquisitions_from_the_archive(ws):
    root = ws.archive / "sentinel1" / "sentinel1-asc-078" / "2026"
    for name in ("S1C_IW_SLC__1SDV_20261003T000000_x", "S1D_IW_SLC__1SDV_20261009T000000_x",
                 "S1A_IW_SLC__1SDV_20260601T000000_x"):                              # S1A: silent for months
        (root / name).mkdir(parents=True)
    n = monitor.next_acquisitions(ws, "alpha", today=date(2026, 10, 25), count=3, with_plan=False)[0]
    assert n["track"] == "sentinel1-asc-078" and n["last"]["S1A"] == "2026-06-01"
    assert [(x["date"], x["platform"]) for x in n["next"]] == [("2026-10-27", "S1C"), ("2026-11-02", "S1D"),
                                                               ("2026-11-08", "S1C")]
    # ESA's plan: the S1C pass of 10-27 is planned, the S1D one of 11-02 is not (inside the planned period)
    from datetime import UTC, datetime
    from types import SimpleNamespace as NS
    from unittest.mock import patch
    take = NS(platform="S1C", start=datetime(2026, 10, 27, 0, 5, tzinfo=UTC), mode="IW", polarisation="DV")
    with patch("geoeyes.sensors.sentinel1.plan.planned",
               return_value=([take], {"S1C": datetime(2026, 11, 3, tzinfo=UTC), "S1D": datetime(2026, 11, 5, tzinfo=UTC)})):
        n = monitor.next_acquisitions(ws, "alpha", today=date(2026, 10, 25), count=3)[0]
    assert [(x["date"], x["status"]) for x in n["next"]] == [("2026-10-27", "planned"), ("2026-11-02", "not planned"),
                                                             ("2026-11-08", "predicted")]
    assert n["next"][0]["mode"] == "IW"


def test_alert_rules_saved_and_evaluated(ws, tmp_path):
    p = ws.project("alpha")
    with pytest.raises(ConfigError):
        monitor.save_rules(p, [{"name": "x", "kind": "nonsense", "threshold": 1}])
    rules = monitor.save_rules(p, [{"name": "fast subsidence", "kind": "velocity_below", "threshold": -20,
                                    "min_points": 5},
                                   {"name": "corner uplift", "kind": "velocity_above", "threshold": 5,
                                    "bbox": [-99.0, 19.3, -98.99, 19.31]}])
    text = p.config.read_text(encoding="utf-8")
    assert "# keep me" in text and tomllib.loads(text)["postprocess"]["alerts"]["rules"][0]["threshold"] == -20.0
    assert monitor.rules(p) == rules
    # a product cache: 100 points, 8 of them below -20 mm/yr, uplift only outside the bbox
    cache = tmp_path / "cache"
    folder = cache / "prod"
    folder.mkdir(parents=True)
    rng = np.random.default_rng(0)
    lon, lat = -99.02 + 0.04 * rng.random(100), 19.28 + 0.04 * rng.random(100)
    vel = np.full(100, -1.0, np.float32)
    vel[:8] = -30
    vel[8] = 9.0
    lon[8], lat[8] = -98.98, 19.28                                       # outside the bbox
    np.savez(folder / "attrs.npz", lon=lon, lat=lat, vel=vel)
    np.save(folder / "ts.npy", np.zeros((100, 2), np.float32))
    from unittest.mock import patch
    with patch("geoeyes.api.points.ensure", return_value=folder):
        res = monitor.evaluate(p, tmp_path / "prod", cache)
    assert res[0]["triggered"] and res[0]["n"] == 8 and res[0]["worst"] == -30.0
    assert not res[1]["triggered"] and res[1]["n"] == 0
