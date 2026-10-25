"""Acquisition time (UTC) of every stack date: the stack's ``sensing_mid_utc`` (written by the native stack
builders), else the start/stop timestamps in the scene name (CSK, Capella), else a configured overpass time."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

_STAMP = re.compile(r"(?<!\d)(\d{14})(?!\d)")


def _from_scene_name(name: str) -> datetime | None:
    stamps = []
    for s in _STAMP.findall(str(name)):
        try:
            stamps.append(datetime.strptime(s, "%Y%m%d%H%M%S"))
        except ValueError:
            continue
    if not stamps:
        return None
    return stamps[0] + (stamps[-1] - stamps[0]) / 2


def parse_utc(value: str) -> time:
    """'HH', 'HH:MM' or 'HH:MM:SS'."""
    parts = [float(p) for p in str(value).replace(";", ":").split(":") if p.strip()]
    h, m, s = [*parts, 0.0, 0.0, 0.0][:3]
    return (datetime(2000, 1, 1) + timedelta(hours=h, minutes=m, seconds=s)).time()


def acquisition_times(attrs: dict, dates: list[date], fallback_utc: str | None = None) -> dict[date, datetime]:
    """UTC acquisition time per date; raises ValueError when a date has none and no fallback is given."""
    mids = attrs.get("sensing_mid_utc") or {}
    scenes = attrs.get("scenes") or {}
    out = {}
    for d in dates:
        t = None
        if str(d) in mids:
            t = datetime.fromisoformat(str(mids[str(d)])).replace(tzinfo=None)
        elif str(d) in scenes:
            t = _from_scene_name(scenes[str(d)])
            if t is not None and t.date() != d:
                t = None
        if t is None:
            if not fallback_utc:
                raise ValueError(f"no acquisition time for {d}: set [atmosphere.era5] fallback_utc")
            t = datetime.combine(d, parse_utc(fallback_utc))
        out[d] = t
    return out
