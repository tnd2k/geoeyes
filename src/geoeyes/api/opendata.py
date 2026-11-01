"""Open-data hub in the web app: index status, catalog sync in the background (one at a time per server, started by
itself when the index is missing or a day old), scene and stack search over an area / period, stacks named by place
(``geoeyes.opendata``)."""
from __future__ import annotations

import threading
import traceback
from datetime import UTC, datetime

from geoeyes.workspace import WorkspaceLayout

_sync: dict = {"running": False, "log": [], "result": None, "error": None, "started": None, "finished": None}
_lock = threading.Lock()


def sync_state() -> dict:
    with _lock:
        return {**_sync, "log": _sync["log"][-40:]}


def start_sync(ws: WorkspaceLayout, sources: list[str] | None) -> dict:
    from geoeyes.opendata.index import refresh
    with _lock:
        if _sync["running"]:
            return {**_sync, "log": _sync["log"][-40:]}
        _sync.update(running=True, log=[], result=None, error=None,
                     started=datetime.now(UTC).isoformat(timespec="seconds"), finished=None)

    def say(source: str, msg: str):
        with _lock:
            _sync["log"].append(f"{source}: {msg}")
            del _sync["log"][:-200]

    def work():
        try:
            res, err = refresh(ws, sources or None, progress=say), None
        except Exception as exc:                 # reported to the page, the server keeps running
            res, err = None, f"{exc}\n{traceback.format_exc(limit=3)}"
        with _lock:
            _sync.update(running=False, result=res, error=err, finished=datetime.now(UTC).isoformat(timespec="seconds"))

    threading.Thread(target=work, name="opendata-sync", daemon=True).start()
    return sync_state()


def sources(ws: WorkspaceLayout) -> dict:
    """Index status; an index never built or older than a day is refreshed in the background (the page lists the
    open data without the user searching for it)."""
    from geoeyes.opendata.index import stale, status
    if stale(ws) and not _sync["running"] and not _sync["error"]:
        start_sync(ws, None)
    return {"sources": status(ws), "sync": sync_state()}


def _bbox(bbox: str):
    if not bbox:
        return None
    b = tuple(float(v) for v in bbox.split(","))
    if len(b) != 4:
        raise ValueError("bbox: west,south,east,north")
    return b


def scenes(ws: WorkspaceLayout, *, bbox: str = "", start: str = "", end: str = "", source: str = "",
           mode: str = "", limit: int = 3000) -> dict:
    from geoeyes.opendata import load, search
    rows = search(load(ws, [source] if source else None), bbox=_bbox(bbox), start=start or None, end=end or None,
                  mode=mode or None)
    return {"total": len(rows), "scenes": rows[-limit:]}


def stacks(ws: WorkspaceLayout, *, bbox: str = "", start: str = "", end: str = "", source: str = "", mode: str = "",
           min_scenes: int = 3, supported: bool = False) -> dict:
    from geoeyes.opendata import find_stacks, load, places, search
    sc = search(load(ws, [source] if source else None), start=start or None, end=end or None, mode=mode or None)
    out = find_stacks(sc, min_scenes=min_scenes, aoi=_bbox(bbox))
    if supported:
        out = [s for s in out if s["supported"]]
    places.names(ws, out)
    return {"stacks": out}
