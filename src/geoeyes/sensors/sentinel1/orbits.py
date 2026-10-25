"""Sentinel-1 orbits from the ASF orbit host, cached in the workspace: precise (AUX_POEORB, ~5 cm, published
~20 days after the acquisition), else restituted (AUX_RESORB, ~10 cm, a few hours after), else the annotation
orbit of the product (with a warning).

File names: ``S1A_OPER_AUX_<KIND>_OPOD_<production>_V<start>_<stop>.EOF``. The EOF lists state vectors every
10 s (UTC, ECEF position/velocity). Only a window around the requested time is kept (Hermite interpolation
needs a few neighbours).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import requests

from geoeyes.core.errors import DataError
from geoeyes.geometry.orbit import StateVectors

log = logging.getLogger(__name__)

URLS = {"POEORB": "https://s1qc.asf.alaska.edu/aux_poeorb/", "RESORB": "https://s1qc.asf.alaska.edu/aux_resorb/"}
POEORB_URL = URLS["POEORB"]
_NAME_RE = re.compile(r"(S1[ABCD])_OPER_AUX_(POEORB|RESORB)_OPOD_(\d{8}T\d{6})_V(\d{8}T\d{6})_(\d{8}T\d{6})\.EOF")


def _t(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%dT%H%M%S")


class PoeorbProvider:
    """Finds, downloads and parses orbit files; ``orbit_for(mission, t0, t1)``. ``used`` counts the orbit kind
    given to each acquisition (``with_precise_orbit``)."""

    def __init__(self, cache_dir: str | Path, *, token: str | None = None, session: requests.Session | None = None,
                 kinds: tuple[str, ...] = ("POEORB", "RESORB")):
        from geoeyes.sensors.sentinel1.earthdata import EarthdataSession
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or (EarthdataSession(token) if token else requests.Session())
        self.kinds = kinds
        self._listing: dict[str, list[str]] = {}
        self.used: dict[str, str] = {}               # acquisition (SLC name) -> POEORB | RESORB | annotation

    def _names(self, kind: str) -> list[str]:
        local = [p.name for p in self.cache_dir.glob(f"*_AUX_{kind}_*.EOF")]
        if kind not in self._listing:
            try:
                r = self.session.get(URLS[kind], timeout=300)
                r.raise_for_status()
                self._listing[kind] = sorted({m.group(0) for m in _NAME_RE.finditer(r.text) if m.group(2) == kind})
            except requests.RequestException as exc:
                log.warning("%s listing unavailable (%s); using cached files only", kind, exc)
                self._listing[kind] = []
        return sorted(set(local) | set(self._listing[kind]))

    def find(self, mission: str, t0: datetime, t1: datetime, margin_s: float = 120, kind: str = "POEORB") -> str:
        best = None
        for name in self._names(kind):
            m = _NAME_RE.fullmatch(name)
            if not m or m.group(1) != mission:
                continue
            covers = (_t(m.group(4)) <= t0 - timedelta(seconds=margin_s)
                      and _t(m.group(5)) >= t1 + timedelta(seconds=margin_s))
            if covers and (best is None or m.group(3) > _NAME_RE.fullmatch(best).group(3)):
                best = name                            # latest production wins
        if best is None:
            raise DataError(f"no {kind} for {mission} {t0:%Y-%m-%d %H:%M:%S}")
        return best

    def path(self, name: str) -> Path:
        p = self.cache_dir / name
        if not p.exists():
            r = self.session.get(URLS[_NAME_RE.fullmatch(name).group(2)] + name, timeout=300)
            r.raise_for_status()
            tmp = p.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(p)
            log.info("downloaded orbit %s", name)
        return p

    def orbit_for(self, mission: str, t0: datetime, t1: datetime, window_s: float = 600,
                  kind: str = "POEORB") -> StateVectors:
        return read_eof(self.path(self.find(mission, t0, t1, kind=kind)), t0 - timedelta(seconds=window_s),
                        t1 + timedelta(seconds=window_s))

    def summary(self) -> str:
        """e.g. ``POEORB (24), RESORB (3)`` over the acquisitions seen so far."""
        return ", ".join(f"{k} ({n})" for k, n in Counter(self.used.values()).most_common()) or "annotation"


def read_eof(path: str | Path, t_min: datetime | None = None, t_max: datetime | None = None) -> StateVectors:
    root = ET.parse(path).getroot()
    times, pos, vel = [], [], []
    for osv in root.iter("OSV"):
        t = datetime.fromisoformat(osv.findtext("UTC").split("=", 1)[1])
        if (t_min and t < t_min) or (t_max and t > t_max):
            continue
        times.append(t)
        pos.append([float(osv.findtext(k)) for k in ("X", "Y", "Z")])
        vel.append([float(osv.findtext(k)) for k in ("VX", "VY", "VZ")])
    if len(times) < 4:
        raise DataError(f"{path}: fewer than 4 state vectors in the requested window")
    return StateVectors.from_lists(times, pos, vel)


def with_precise_orbit(meta, provider: PoeorbProvider):
    """BurstMetadata with its annotation orbit replaced by the best available orbit (``provider.kinds`` in
    order); the annotation orbit is kept, with a warning, when none covers the burst (e.g. an acquisition a few
    hours old)."""
    t0 = meta.sensing_start
    t1 = t0 + timedelta(seconds=meta.lines * meta.azimuth_time_interval)
    for kind in provider.kinds:
        try:
            sv = provider.orbit_for(meta.mission, t0, t1, kind=kind)
        except DataError:
            continue
        if kind != "POEORB" and meta.slc_name not in provider.used:
            log.info("%s: no POEORB yet, %s orbit used", meta.slc_name, kind)
        provider.used[meta.slc_name] = kind
        return replace(meta, orbit=sv)
    if meta.slc_name not in provider.used:
        log.warning("%s: no POEORB/RESORB orbit, annotation orbit kept", meta.slc_name)
    provider.used[meta.slc_name] = "annotation"
    return meta
