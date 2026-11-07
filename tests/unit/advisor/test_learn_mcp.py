"""Site advisor V4 (rules against the projects) and V5 (local MCP server), and the engine's list of the [ps] keys
it reads. No network: the profile readers are replaced."""
import io
import json
import re
from pathlib import Path

import pytest

from geoeyes.advisor import learn, mcp
from geoeyes.advisor import profile as prof
from geoeyes.processing.ps import params
from geoeyes.workspace import WorkspaceLayout

TOML = """schema = "geoeyes.project/1"

[project]
name = "{name}"
method = "psi"

[aoi]
bbox = [106.56, 10.69, 106.71, 10.78]

[[tracks]]
sensor = "sentinel1"
direction = "descending"
relative_orbit = 18

[acquire]
max_per_month = {per_month}

[ps]
subtr_tropo = "n"
unwrap_grid_size = 50
da_threshold = 0.42
"""


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(prof, "terrain_part", lambda grid, dem, cache: {
        "source": dem, "cell_m": 30, "relief_m": 11.0, "slope_median_deg": 2.0, "steep_share": 0.0,
        "very_steep_share": 0.0})
    monkeypatch.setattr(prof, "land_cover_part", lambda grid: {
        "source": "test", "shares": {"built": 0.58, "tree": 0.17, "crop": 0.09, "grass": 0.08, "water": 0.03},
        "dominant": "built"})
    monkeypatch.setattr(prof, "geology_part", lambda grid, z: {
        "source": "test", "shares": {"su": 1.0}, "names": {"su": "unconsolidated sediments"}, "dominant": "su",
        "soft_share": 1.0})
    monkeypatch.setattr(prof, "climate_part", lambda bbox, cache: {
        "source": "test", "years": [2016, 2025], "koppen": "Aw", "rain_annual_mm": 1887, "wet_months": [5, 6],
        "rh_mean_pct": 80, "temp_mean_c": 27})
    w = WorkspaceLayout.at(tmp_path / "ws")
    for name, per_month, finished in (("done_a", 0, True), ("done_b", 0, True), ("wip", 2, False)):
        p = w.project(name).ensure()
        p.config.write_text(TOML.format(name=name, per_month=per_month), encoding="utf-8")
        if finished:
            (p.root / "products" / "x_v1").mkdir(parents=True)
            (p.root / "products" / "x_v1" / "manifest.json").write_text("{}")
    monkeypatch.setenv("GEOEYES_WORKSPACE", str(w.root))
    return w


# ---------------------------------------------------------------- V4
def test_learn_counts_finished_projects_only(ws):
    rows = learn.collect(ws, progress=lambda m: None)
    assert {r["project"]: r["finished"] for r in rows} == {"done_a": True, "done_b": True, "wip": False}
    s = learn.summarise(rows)
    assert s["per_rule"]["flat-no-height-aps"]["fired"] == ["done_a", "done_b", "wip"]
    assert s["per_rule"]["s1-every-date"]["agree"] == 2                   # wip (2 a month) is not evidence
    assert s["differ"] == [] and "steep-terrain" in s["never"]


def test_learn_report_names_ignored_keys(ws):
    text = learn.report(learn.collect(ws, progress=lambda m: None), "vi")
    assert "# Luật khu vực so với các dự án" in text
    assert "`[ps] da_threshold` = 0.42 (có phải ý là `selection.da_threshold`?)" in text
    assert "wip | " in text and "`acquire.max_per_month` 2→0" in text


# ---------------------------------------------------------------- V5
def _call(*messages):
    out = io.StringIO()
    mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in messages)), out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_mcp_handshake_and_tools():
    r = _call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
              {"jsonrpc": "2.0", "method": "notifications/initialized"},
              {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
              {"jsonrpc": "2.0", "id": 3, "method": "no/such"})
    assert [m["id"] for m in r] == [1, 2, 3]                               # the notification gets no reply
    assert r[0]["result"]["protocolVersion"] == "2025-06-18" and "tools" in r[0]["result"]["capabilities"]
    names = {t["name"] for t in r[1]["result"]["tools"]}
    assert names == {"explain_param", "site_profile", "advise", "list_rules"}
    assert all(t["inputSchema"]["type"] == "object" for t in r[1]["result"]["tools"])
    assert r[2]["error"]["code"] == -32601


def test_mcp_tools_answer(ws):
    r = _call({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "explain_param", "arguments": {"query": "unwrap_grid_size", "lang": "vi"}}},
              {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "advise", "arguments": {"project": "done_a"}}},
              {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "advise", "arguments": {}}},
              {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "list_rules"}})
    text = [m["result"]["content"][0]["text"] for m in r]
    assert "Rủi ro" in text[0]
    assert "To change: none" in text[1] and "da_threshold" in text[1]
    assert r[2]["result"]["isError"] is True                               # a tool error is a result
    assert "[hcmc-grid]" in text[3]


def test_mcp_parse_error_is_answered():
    out = io.StringIO()
    mcp.serve(io.StringIO("not json\n"), out)
    assert json.loads(out.getvalue())["error"]["code"] == -32700


# ---------------------------------------------------------------- engine keys
def test_unknown_ps_keys():
    assert params.unknown_keys({"da_threshold": 0.42, "unwrap_grid_size": 10, "drop_ifg_index": [3]}) == \
        ["da_threshold"]


def test_every_key_the_engine_reads_is_declared():
    src = Path(params.__file__).read_text(encoding="utf-8")
    read = set(re.findall(r'pm\.get\("([a-z_0-9]+)"', src)) | set(re.findall(r'pm\["([a-z_0-9]+)"\]', src))
    assert read <= set(params.DEFAULTS) | params.OPTIONAL, read - set(params.DEFAULTS) - params.OPTIONAL
