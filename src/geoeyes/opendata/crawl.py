"""Walk a static STAC catalog: follow ``child`` links level by level, collect ``item`` links (absolute URLs)."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests

log = logging.getLogger(__name__)


def get_json(session: requests.Session, url: str, attempts: int = 3) -> dict:
    for i in range(attempts):
        try:
            r = session.get(url, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if i == attempts - 1:
                raise
            time.sleep(1.5 * (i + 1))
    raise AssertionError("unreachable")


def walk(roots: Iterable[str], session: requests.Session, *, workers: int = 16,
         progress: Callable[[int, int], None] | None = None) -> list[str]:
    """Item URLs below ``roots`` (catalogs or collections). A node that cannot be read is logged and skipped."""
    seen: set[str] = set()
    items: list[str] = []
    level = list(dict.fromkeys(roots))

    def node(url: str) -> tuple[list[str], list[str]]:
        try:
            d = get_json(session, url)
        except Exception as exc:                 # one broken sub-catalog must not lose the rest
            log.warning("STAC node %s unreadable: %s", url, exc)
            return [], []
        links = d.get("links", [])
        return ([urljoin(url, lk["href"]) for lk in links if lk.get("rel") == "child"],
                [urljoin(url, lk["href"]) for lk in links if lk.get("rel") == "item"])

    with ThreadPoolExecutor(workers) as ex:
        while level:
            seen.update(level)
            nxt: list[str] = []
            for children, found in ex.map(node, level):
                nxt.extend(c for c in children if c not in seen)
                items.extend(found)
            level = list(dict.fromkeys(nxt))
            if progress:
                progress(len(seen), len(items))
    return list(dict.fromkeys(items))
