import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from geoeyes.api import events  # noqa: E402


class _Req:
    """A request that disconnects after ``n`` checks."""

    def __init__(self, n: int):
        self.n = n

    async def is_disconnected(self) -> bool:
        self.n -= 1
        return self.n < 0


def _collect(gen) -> list[str]:
    async def run():
        return [m async for m in gen]
    return asyncio.run(run())


def test_source_sends_only_changes():
    state = {"v": 1}
    s = events.Source("workspace", lambda: dict(state), fast=1, slow=1)
    first = s.poll()
    assert first.startswith("event: workspace\n") and json.loads(first.split("data: ", 1)[1]) == {"v": 1}
    assert s.poll() is None                     # unchanged: nothing sent
    state["v"] = 2
    assert s.poll() is not None


def test_source_nan_and_error():
    s = events.Source("project", lambda: {"x": float("nan")}, fast=1, slow=1)
    assert json.loads(s.poll().split("data: ", 1)[1]) == {"x": None}

    def boom():
        raise RuntimeError("no project 'x'")
    e = events.Source("project", boom, fast=1, slow=1)
    msg = e.poll()
    assert msg.startswith("event: fault\n")
    assert json.loads(msg.split("data: ", 1)[1]) == {"source": "project", "error": "no project 'x'"}
    assert e.data is None                       # an error is not the source's data (busy() reads it)


def test_incremental_source_none_sends_nothing():
    s = events.Source("log", lambda: None, fast=1, slow=1, dedupe=False)
    assert s.poll() is None


def test_stream_retry_then_events_until_disconnect(monkeypatch):
    monkeypatch.setattr(events, "TICK_S", 0)
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"n": calls["n"]}
    src = events.Source("activity", fetch, fast=0, slow=0)
    out = _collect(events._stream(_Req(3), [src], busy=lambda: False))
    assert out[0] == "retry: 2000\n\n"
    assert [m.split("\n")[0] for m in out[1:]] == ["event: activity"] * 3


def test_workspace_stream_through_the_app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from geoeyes.api import create_app
    from geoeyes.workspace import WorkspaceLayout
    monkeypatch.setattr(events, "MAX_S", 0.3)   # the stream ends by itself: the client reads it whole
    ws = WorkspaceLayout(tmp_path)
    with TestClient(create_app(ws)) as c:
        r = c.get("/api/events")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    kinds = [ln for ln in r.text.splitlines() if ln.startswith("event: ")]
    assert kinds[:2] == ["event: workspace", "event: activity"]
    assert c.get("/api/projects/nope/events").status_code == 404
