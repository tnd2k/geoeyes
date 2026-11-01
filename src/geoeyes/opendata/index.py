"""Local index of the open-data scenes: ``<workspace>/cache/opendata/<source>.json``.

``sync`` walks each source's catalog, fetches only the items not already indexed (STAC items of these catalogs
are immutable) and drops the ones no longer listed. ``load`` / ``search`` read the index offline.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

import requests

from geoeyes.core.errors import ConfigError
from geoeyes.io.manifest import atomic_write_json
from geoeyes.opendata.crawl import get_json, walk
from geoeyes.opendata.sources import SOURCES

log = logging.getLogger(__name__)


def index_dir(ws) -> Path:
    return ws.cache_dir("opendata")


def _path(ws, source: str) -> Path:
    return index_dir(ws) / f"{source}.json"


def _sources(sources: Iterable[str] | None) -> list[str]:
    ids = list(sources or SOURCES)
    bad = [s for s in ids if s not in SOURCES]
    if bad:
        raise ConfigError(f"unknown open-data source(s) {bad}; known: {sorted(SOURCES)}")
    return ids


def read_index(ws, source: str) -> dict:
    p = _path(ws, source)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _read_item(session: requests.Session, src, url: str) -> tuple[str, dict | bool | None]:
    """(url, scene record | None when not a complex product | False when unreadable)."""
    try:
        return url, src.normalize(get_json(session, url), url)
    except Exception as exc:
        log.warning("%s: item %s unreadable: %s", src.id, url, exc)
        return url, False


def sync(ws, sources: Iterable[str] | None = None, *, workers: int = 32,
         progress: Callable[[str, str], None] | None = None) -> dict[str, dict]:
    """Refresh the index of each source; returns per source ``{"scenes", "new", "removed", "items"}``."""
    say = progress or (lambda s, m: log.info("%s: %s", s, m))
    out = {}
    with requests.Session() as session:
        session.headers["User-Agent"] = "geoeyes-opendata"
        session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=workers))
        for sid in _sources(sources):
            src = SOURCES[sid]
            old = read_index(ws, sid)
            known = {r["item"]: r for r in old.get("scenes", [])}
            skipped = set(old.get("skipped", []))
            say(sid, "walking the catalog")
            urls = walk(src.roots, session, workers=workers,
                        progress=partial(lambda s, n, k: say(s, f"{n} catalog node(s), {k} item(s)"), sid))
            todo = [u for u in urls if u not in known and u not in skipped]
            say(sid, f"{len(urls)} item(s), {len(todo)} new")
            fresh, failed = [], 0
            with ThreadPoolExecutor(workers) as ex:
                for i, (url, rec) in enumerate(ex.map(partial(_read_item, session, src), todo), 1):
                    if rec is False:
                        failed += 1
                    elif rec is None:
                        skipped.add(url)                 # not a complex product of this source (GRD, GEO...)
                    else:
                        fresh.append(rec)
                    if i % 200 == 0:
                        say(sid, f"{i}/{len(todo)} item(s) read")
            listed = set(urls)
            scenes = [r for u, r in known.items() if u in listed] + fresh
            scenes.sort(key=lambda r: (r["datetime"], r["id"]))
            atomic_write_json(_path(ws, sid), {"source": sid, "synced": datetime.now(UTC).isoformat(timespec="seconds"),
                                               "roots": list(src.roots), "scenes": scenes,
                                               "skipped": sorted(skipped & listed)})
            out[sid] = {"scenes": len(scenes), "new": len(fresh), "removed": len(known) - (len(scenes) - len(fresh)),
                        "items": len(urls), "failed": failed}
            say(sid, f"{len(scenes)} complex scene(s) indexed ({len(fresh)} new, {failed} unreadable)")
    return out


def status(ws) -> list[dict]:
    rows = []
    for sid, src in SOURCES.items():
        d = read_index(ws, sid)
        rows.append({"source": sid, "title": src.title, "homepage": src.homepage, "license": src.license,
                     "sensor": src.sensor, "synced": d.get("synced"), "scenes": len(d.get("scenes", []))})
    return rows


def load(ws, sources: Iterable[str] | None = None) -> list[dict]:
    return [r for sid in _sources(sources) for r in read_index(ws, sid).get("scenes", [])]


def _d(v) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def search(scenes: list[dict], *, bbox=None, start=None, end=None, mode: str | None = None,
           orbit_state: str | None = None, look: str | None = None, covers: bool = False) -> list[dict]:
    """Scenes over ``bbox`` (w, s, e, n; ``covers``: the footprint contains it) in [start, end]."""
    from shapely.geometry import Polygon, box
    area = box(*bbox) if bbox else None
    s, e = _d(start), _d(end)
    out = []
    for r in scenes:
        d = _d(r["date"])
        if (s and d < s) or (e and d > e) or (mode and r["mode"] != mode) \
                or (orbit_state and r["orbit_state"] != orbit_state) or (look and r["look"] != look):
            continue
        if area is not None:
            w, so, ea, n = r["bbox"]
            if w > bbox[2] or ea < bbox[0] or so > bbox[3] or n < bbox[1]:
                continue
            fp = Polygon(r["footprint"])
            if not (fp.covers(area) if covers else fp.intersects(area)):
                continue
        out.append(r)
    return out


def stale(ws, max_age_h: float = 24.0) -> bool:
    """A source never synced, or synced more than ``max_age_h`` ago."""
    now = datetime.now(UTC)
    for sid in SOURCES:
        synced = read_index(ws, sid).get("synced")
        if not synced or (now - datetime.fromisoformat(synced)).total_seconds() > max_age_h * 3600:
            return True
    return False


def refresh(ws, sources: Iterable[str] | None = None, *, progress: Callable[[str, str], None] | None = None) -> dict:
    """``sync``, then the place names of the stacks not named yet (``places.fill``)."""
    from geoeyes.opendata import places
    from geoeyes.opendata.stacks import find_stacks
    out = sync(ws, sources, progress=progress)
    try:
        places.fill(ws, find_stacks(load(ws)), progress=progress)
    except Exception as exc:                     # names are a convenience: the index is what matters
        log.warning("place names not updated: %s", exc)
    return out
