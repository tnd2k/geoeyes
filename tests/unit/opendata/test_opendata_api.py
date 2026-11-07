"""/api/opendata: index status, stack search, a new project on a stack (offline: index written by the test)."""
from datetime import UTC, datetime

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from geoeyes.api import create_app  # noqa: E402
from geoeyes.io.manifest import atomic_write_json  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402
from tests.unit.opendata.test_opendata import _scene  # noqa: E402


@pytest.fixture
def ws(tmp_path):
    w = WorkspaceLayout.at(tmp_path / "ws")
    w.projects.mkdir(parents=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")          # fresh: the page does not start a sync
    for sid in ("iceye", "capella", "umbra"):
        atomic_write_json(w.cache_dir("opendata") / f"{sid}.json",
                          {"source": sid, "synced": now, "scenes": [_scene(d) for d in range(11, 17)] if sid == "iceye" else []})
    atomic_write_json(w.cache_dir("opendata") / "places.json", {"28.2,-16.7": "Tenerife, Spain"})
    return w


def test_sources_and_stacks(ws):
    c = TestClient(create_app(ws))
    src = {s["source"]: s for s in c.get("/api/opendata/sources").json()["sources"]}
    assert not c.get("/api/opendata/sync").json()["running"]
    assert src["iceye"]["scenes"] == 6 and src["capella"]["scenes"] == 0 and src["umbra"]["sensor"] == "umbra"
    st = c.get("/api/opendata/stacks", params={"bbox": "-16.8,28.0,-16.7,28.1"}).json()["stacks"]
    assert [s["n_dates"] for s in st] == [6] and st[0]["sensor"] == "iceye" and st[0]["place"] == "Tenerife, Spain"
    assert c.get("/api/opendata/stacks", params={"bbox": "1,2,3"}).status_code == 400
    assert c.get("/api/opendata/stacks", params={"min_scenes": 7}).json()["stacks"] == []


def test_project_on_a_stack(ws):
    c = TestClient(create_app(ws))
    sid = c.get("/api/opendata/stacks").json()["stacks"][0]["id"]
    r = c.post("/api/projects", json={"name": "tf", "method": "psi", "bbox": [-16.8, 28.0, -16.7, 28.1],
                                      "track": {"sensor": "iceye", "direction": "ascending"}, "opendata": sid})
    assert r.status_code == 200, r.text
    text = ws.project("tf").config.read_text(encoding="utf-8")
    assert f'opendata = "{sid}"' in text and 'sensor = "iceye"' in text
