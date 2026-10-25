"""ESA's published Sentinel-1 acquisition plan (one KML per satellite, ~20 days ahead): which passes over an AOI will
actually acquire, in which mode. The plan page and the KML files are cached under ``<workspace>/cache/s1plan``.

ESA publishes a new file whenever the planning changes; a newer file supersedes the older ones over its own period
only (a short re-plan can end before an older file does), so a data take is kept when no newer file covers it.
"""
from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

log = logging.getLogger(__name__)

PLAN_PAGE = "https://sentinels.copernicus.eu/copernicus/sentinel-1/acquisition-plans"
PLAN_HOST = "https://sentinels.copernicus.eu"
_LINK_RE = re.compile(r"/documents/d/sentinel/(s1([a-d])_mp_user_(\d{8}t\d{6})_(\d{8}t\d{6}))")
PAGE_TTL_S = 6 * 3600
FULL_PLAN_DAYS = 30
_UA = {"User-Agent": "Mozilla/5.0 (GeoEyes acquisition planner)"}


@dataclass(frozen=True)
class PlanFile:
    name: str
    platform: str           # S1C
    start: datetime
    end: datetime

    @property
    def url(self) -> str:
        return f"{PLAN_HOST}/documents/d/sentinel/{self.name}"


@dataclass(frozen=True)
class DataTake:
    platform: str
    start: datetime
    stop: datetime
    mode: str
    polarisation: str
    orbit: int | None
    relative_orbit: int | None
    footprint: object       # shapely polygon
    plan_file: str


def _utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def plan_files(cache: Path, refresh: bool = False) -> list[PlanFile]:
    """The KML plans listed on ESA's page (the page is re-read every 6 hours)."""
    cache.mkdir(parents=True, exist_ok=True)
    idx = cache / "plan_page.json"
    rows = None
    if idx.exists() and not refresh:
        d = json.loads(idx.read_text(encoding="utf-8"))
        if time.time() - d.get("at", 0) < PAGE_TTL_S:
            rows = d["files"]
    if rows is None:
        try:
            r = requests.get(PLAN_PAGE, headers=_UA, timeout=60)
            r.raise_for_status()
            rows = sorted({m.group(1) for m in _LINK_RE.finditer(r.text)})
            idx.write_text(json.dumps({"at": time.time(), "files": rows}), encoding="utf-8")
        except requests.RequestException as exc:
            if not idx.exists():
                raise
            log.warning("ESA plan page unavailable (%s); using the last listing", exc)
            rows = json.loads(idx.read_text(encoding="utf-8"))["files"]
    out = []
    for name in rows:
        m = _LINK_RE.search(f"/documents/d/sentinel/{name}")
        s = datetime.strptime(m.group(3), "%Y%m%dt%H%M%S").replace(tzinfo=UTC)
        e = datetime.strptime(m.group(4), "%Y%m%dt%H%M%S").replace(tzinfo=UTC)
        out.append(PlanFile(name, f"S1{m.group(2).upper()}", s, e))
    return sorted(out, key=lambda f: (f.platform, f.start))


def parse_kml(data: bytes, plan_file: str = "") -> list[DataTake]:
    from shapely.geometry import Polygon
    root = ET.fromstring(data)
    out = []
    for pm in root.iter():
        if not pm.tag.endswith("Placemark"):
            continue
        ext: dict[str, str] = {}
        coords = None
        for el in pm.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "Data":
                v = next((c.text for c in el if c.tag.rsplit("}", 1)[-1] == "value"), None)
                ext[el.get("name")] = (v or "").strip()
            elif tag == "coordinates" and el.text:
                coords = [tuple(float(x) for x in c.split(",")[:2]) for c in el.text.split()]
        if not coords or len(coords) < 3 or "ObservationTimeStart" not in ext:
            continue
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            sat = re.search(r"1([A-D])", (ext.get("SatelliteId") or "").upper())
            out.append(DataTake(
                platform=f"S1{sat.group(1)}" if sat else "", start=_utc(ext["ObservationTimeStart"]),
                stop=_utc(ext.get("ObservationTimeStop") or ext["ObservationTimeStart"]),
                mode=ext.get("Mode", ""), polarisation=ext.get("Polarisation", ""),
                orbit=int(ext["OrbitAbsolute"]) if ext.get("OrbitAbsolute", "").isdigit() else None,
                relative_orbit=int(ext["OrbitRelative"]) if ext.get("OrbitRelative", "").isdigit() else None,
                footprint=poly, plan_file=plan_file))
        except (ValueError, KeyError):
            continue
    return out


def _datatakes(f: PlanFile, cache: Path) -> list[DataTake]:
    path = cache / f"{f.name}.kml"
    if not path.exists():
        r = requests.get(f.url, headers=_UA, timeout=120)
        r.raise_for_status()
        tmp = path.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(path)
    return parse_kml(path.read_bytes(), f.name)


def planned(cache: Path, bbox: list[float], *, relative_orbit: int | None = None, start: datetime | None = None,
            end: datetime | None = None) -> tuple[list[DataTake], dict[str, datetime]]:
    """Data takes over ``bbox`` (on ``relative_orbit`` when given) between ``start`` and ``end``, and, per
    satellite, the end of its published plan."""
    from shapely.geometry import box
    start = start or datetime.now(UTC)
    files = [f for f in plan_files(cache) if f.end >= start and (end is None or f.start <= end)]
    aoi = box(*bbox)
    out: list[DataTake] = []
    until: dict[str, datetime] = {}
    for sat in sorted({f.platform for f in files}):
        own = [f for f in files if f.platform == sat]
        # the regular ~20-day files define the planned period; occasional long-range files hold part of a plan
        # only: their data takes count, a pass missing from them is not "not planned"
        regular = [f.end for f in own if (f.end - f.start).days <= FULL_PLAN_DAYS]
        if regular:
            until[sat] = max(regular)
        for i, f in enumerate(own):
            newer = [(g.start, g.end) for g in own[i + 1:]]
            for dt in _datatakes(f, cache):
                if dt.stop < start or (end is not None and dt.start > end):
                    continue
                if any(s <= dt.start <= e for s, e in newer):
                    continue
                if relative_orbit is not None and dt.relative_orbit != relative_orbit:
                    continue
                if dt.footprint.intersects(aoi):
                    out.append(dt)
    return sorted(out, key=lambda d: d.start), until
