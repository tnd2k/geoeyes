"""Inputs of the CR report: reflector list and set-up log (CSV files named in ``[validation] corner_reflector``)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_EDGE_M = 0.8
DEFAULT_TZ = "Asia/Ho_Chi_Minh"


@dataclass
class CRTarget:
    name: str
    lat: float
    lon: float
    height: float | None        # ellipsoidal (m); None when the CSV has no height column
    edge_m: float


@dataclass
class CRSetup:
    """How a reflector was set up from ``valid_from`` (local time) until the next entry."""
    name: str                   # reflector name, or "*" for every reflector
    valid_from: datetime        # timezone-aware
    face_azimuth_deg: float
    base_tilt_deg: float
    note: str = ""


def _col(row: dict, *names):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for n in names:
        v = low.get(n)
        if v not in (None, ""):
            return v
    return None


def read_targets(path: str | Path, default_edge_m: float = DEFAULT_EDGE_M) -> list[CRTarget]:
    """Reflector CSV: ``lon,lat`` required; optional ``name|id``, ``height|h|elevation|alt``
    (ellipsoidal metres) and ``edge_m|size_m|edge`` (inner edge length of the trihedral)."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            lon, lat = _col(row, "lon", "longitude"), _col(row, "lat", "latitude")
            if lon is None or lat is None:
                continue
            h = _col(row, "height", "h", "elevation", "elev", "alt", "altitude", "altitude_m")
            edge = _col(row, "edge_m", "size_m", "edge", "target_size_m")
            out.append(CRTarget(name=str(_col(row, "name", "id", "target_name") or f"CR{i}"),
                                lat=float(lat), lon=float(lon), height=float(h) if h is not None else None,
                                edge_m=float(edge) if edge is not None else default_edge_m))
    if not out:
        raise ValueError(f"no lon/lat rows in {path}")
    return out


def read_setup(path: str | Path, tz: str = DEFAULT_TZ) -> list[CRSetup]:
    """Set-up log CSV: ``valid_from`` (YYYY-MM-DD[ HH:MM], local time), ``face_azimuth_deg``,
    ``base_tilt_deg``; optional ``name`` (default every reflector) and ``note``. Each row holds
    until the next row of the same reflector."""
    zone = ZoneInfo(tz)
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            when = _col(row, "valid_from", "from", "date", "datetime")
            az = _col(row, "face_azimuth_deg", "azimuth_deg", "azimuth")
            tilt = _col(row, "base_tilt_deg", "tilt_deg", "tilt")
            if when is None or az is None or tilt is None:
                continue
            dt = datetime.fromisoformat(when.strip().replace("/", "-"))
            out.append(CRSetup(name=str(_col(row, "name", "id") or "*"),
                               valid_from=dt if dt.tzinfo else dt.replace(tzinfo=zone),
                               face_azimuth_deg=float(az), base_tilt_deg=float(tilt),
                               note=str(_col(row, "note", "ghi_chu", "description") or "")))
    return sorted(out, key=lambda s: s.valid_from)


def setup_at(setups: list[CRSetup], name: str, when: datetime) -> CRSetup | None:
    """The set-up in force for reflector ``name`` at ``when`` (aware datetime)."""
    hit = None
    for s in setups:
        if s.name in ("*", name) and s.valid_from <= when:
            hit = s
    return hit
