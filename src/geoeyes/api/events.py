"""Server-sent events: the web app's live state pushed over one connection instead of several polls.

Each stream checks a few sources on their own cadence (faster while something runs) and sends a source only when
its JSON changed, so an idle page receives nothing but a heartbeat. The browser reconnects by itself
(``EventSource``); a stream also ends after ``MAX_S`` so that no connection outlives a server restart for long.
The web app falls back to polling when the stream is not there (an older server).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections.abc import AsyncIterator, Callable

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from geoeyes.api import jobs, service
from geoeyes.workspace import WorkspaceLayout

log = logging.getLogger(__name__)

MAX_S = 600          # a stream ends after 10 min; the browser reopens it at once
HEARTBEAT_S = 15     # a comment line: keeps proxies from closing an idle stream, detects a closed tab
TICK_S = 0.5


def _finite(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


def _dump(data) -> str:
    try:
        return json.dumps(data, separators=(",", ":"), allow_nan=False, default=str)
    except ValueError:
        return json.dumps(_finite(data), separators=(",", ":"), default=str)


class Source:
    """One kind of event: ``fetch()`` (run in a worker thread) every ``fast`` s while busy, else ``slow`` s.
    ``fetch`` returning None sends nothing (incremental sources: nothing new)."""

    def __init__(self, event: str, fetch: Callable[[], object], fast: float, slow: float, dedupe: bool = True):
        self.event, self.fetch, self.fast, self.slow, self.dedupe = event, fetch, fast, slow, dedupe
        self.data: object = None
        self.last: str | None = None
        self.due = 0.0

    def poll(self) -> str | None:
        ev = self.event
        try:
            data = self.fetch()
        except Exception as exc:  # a project deleted meanwhile, a file half written: say it, keep the stream
            log.debug("event source %s failed", self.event, exc_info=True)
            # "fault", not "error": that name is the browser's own EventSource event for a lost connection
            ev, data = "fault", {"source": self.event, "error": str(exc)}
        if data is None:
            return None
        if ev == self.event:
            self.data = data
        text = _dump(data)
        if self.dedupe and text == self.last:
            return None
        self.last = text
        return f"event: {ev}\ndata: {text}\n\n"


async def _stream(request: Request, sources: list[Source], busy: Callable[[], bool]) -> AsyncIterator[str]:
    yield "retry: 2000\n\n"
    end = time.monotonic() + MAX_S
    beat = time.monotonic() + HEARTBEAT_S
    while time.monotonic() < end:
        if await request.is_disconnected():
            return
        now = time.monotonic()
        fast = busy()
        for s in sources:
            if now < s.due:
                continue
            s.due = now + (s.fast if fast else s.slow)
            msg = await run_in_threadpool(s.poll)
            if msg:
                yield msg
                beat = time.monotonic() + HEARTBEAT_S
        if time.monotonic() >= beat:
            yield ": ping\n\n"
            beat = time.monotonic() + HEARTBEAT_S
        await asyncio.sleep(TICK_S)


def _response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def workspace_events(request: Request, ws: WorkspaceLayout) -> StreamingResponse:
    """``workspace`` (the tree and every project's state) and ``activity`` (background analyses)."""
    tree = Source("workspace", lambda: service.workspace_tree(ws), fast=2, slow=10)
    act = Source("activity", lambda: {"jobs": jobs.activity(ws)}, fast=3, slow=6)

    def busy() -> bool:
        projects = (tree.data or {}).get("projects", {}) if isinstance(tree.data, dict) else {}
        jobs_ = (act.data or {}).get("jobs", []) if isinstance(act.data, dict) else []
        return any(p.get("running") for p in projects.values()) or any(j.get("state") == "running" for j in jobs_)

    return _response(_stream(request, [tree, act], busy))


def project_events(request: Request, ws: WorkspaceLayout, name: str, run: str | None, after: int) -> StreamingResponse:
    """``project`` (detail), ``ps-steps`` (checkpoints) and, with ``run``, ``log`` (its new lines from ``after``)."""
    detail = Source("project", lambda: service.project_detail(ws, name), fast=2, slow=15)
    steps = Source("ps-steps", lambda: service.ps_steps(ws, name), fast=5, slow=30)
    sources = [detail, steps]
    if run:
        cursor = {"next": after}

        def new_lines():
            before = cursor["next"]
            r = service.run_log(ws.project(name), run, after=before)
            if not r.get("lines"):
                return None
            cursor["next"] = r["next"]
            return {**r, "after": before}   # the client checks it continues its own cursor

        sources.append(Source("log", new_lines, fast=1, slow=5, dedupe=False))

    def busy() -> bool:
        return isinstance(detail.data, dict) and bool(detail.data.get("running"))

    return _response(_stream(request, sources, busy))
