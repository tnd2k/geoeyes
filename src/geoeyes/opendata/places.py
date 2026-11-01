"""Place names of the stacks (so a stack is chosen by "Tenerife, Spain", not by its coordinates).

Reverse geocoding of the stack centres with OpenStreetMap data: Nominatim, or Photon (komoot) when Nominatim cannot be
reached (only the coordinates are sent, at most one request per second as their usage policies ask), cached in
``<workspace>/cache/opendata/places.json`` keyed by the centre rounded to 0.1°; a place without a name (sea) is cached
as "". ``names`` reads the cache only (offline).
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import requests

from geoeyes.io.manifest import atomic_write_json

log = logging.getLogger(__name__)
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
PHOTON = "https://photon.komoot.io/reverse"
_LOCAL = ("city", "town", "village", "municipality", "county", "state_district")
_REGION = ("state", "region", "island")


def key(lat: float, lon: float) -> str:
    return f"{lat:.1f},{lon:.1f}"


def centre(stack: dict) -> tuple[float, float]:
    w, s, e, n = stack["bbox"]
    return (s + n) / 2.0, (w + e) / 2.0


def _path(ws):
    return ws.cache_dir("opendata") / "places.json"


def _read(ws) -> dict[str, str]:
    p = _path(ws)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def label(address: dict) -> str:
    """'Los Angeles, California, United States': the most local named part, the region and the country (a part
    equal to the previous one is left out)."""
    parts = [next((address[k] for k in _LOCAL if address.get(k)), ""),
             next((address[k] for k in _REGION if address.get(k)), ""), address.get("country", "")]
    out: list[str] = []
    for part in parts:
        if part and (not out or out[-1] != part):
            out.append(part)
    return ", ".join(out)


def _nominatim(http: requests.Session, lat: float, lon: float) -> str:
    r = http.get(NOMINATIM, params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "accept-language": "en"},
                 timeout=30)
    r.raise_for_status()
    return label(r.json().get("address") or {})


def _photon(http: requests.Session, lat: float, lon: float) -> str:
    r = http.get(PHOTON, params={"lat": lat, "lon": lon, "lang": "en"}, timeout=30)
    r.raise_for_status()
    feats = r.json().get("features") or []
    return label(feats[0].get("properties") or {}) if feats else ""


def names(ws, stacks: list[dict]) -> None:
    """Add ``place`` to each stack from the cache ("" when not looked up yet or unnamed)."""
    cache = _read(ws)
    for s in stacks:
        s["place"] = cache.get(key(*centre(s)), "")


def fill(ws, stacks: list[dict], *, progress: Callable[[str, str], None] | None = None,
         session: requests.Session | None = None, pause_s: float = 1.1) -> int:
    """Look up the centres not in the cache; returns how many were added."""
    cache = _read(ws)
    todo = sorted({key(*centre(s)) for s in stacks} - set(cache))
    if not todo:
        return 0
    http = session or requests.Session()
    http.headers["User-Agent"] = "geoeyes-opendata/0.1 (InSAR processing; open-data stack names)"
    added, provider = 0, _nominatim
    for i, k in enumerate(todo, 1):
        lat, lon = (float(v) for v in k.split(","))
        try:
            try:
                cache[k] = provider(http, lat, lon)
            except requests.ConnectionError:
                if provider is _photon:
                    raise
                log.info("Nominatim unreachable: place names from Photon")
                provider = _photon
                cache[k] = provider(http, lat, lon)
            added += 1
        except (requests.RequestException, ValueError) as exc:     # retried at the next sync
            log.warning("place name of %s unavailable: %s", k, exc)
        if i % 10 == 0 or i == len(todo):
            atomic_write_json(_path(ws), cache)
            if progress:
                progress("places", f"{i}/{len(todo)} place name(s)")
        time.sleep(pause_s)
    atomic_write_json(_path(ws), cache)
    return added
