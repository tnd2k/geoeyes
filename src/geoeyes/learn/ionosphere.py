"""Principles, chapter 6: what a stack holds on the ionosphere and the subswath seams, per date (web page
"Principles", route #/learn-ionosphere). Method: docs/en/guide/ionosphere.md."""
from __future__ import annotations

import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from geoeyes.learn.pair import _dates, _ground_spacing, _mtime, _store

FIELD = 64                                         # side of the preview of the ionospheric phase, in cells


def _local_hour(utc: str | None, lon: float) -> float | None:
    """Local solar time (h) of a UTC instant at longitude ``lon``."""
    if not utc:
        return None
    t = datetime.fromisoformat(str(utc).replace("Z", ""))
    return round((t.hour + t.minute / 60 + t.second / 3600 + lon / 15.0) % 24, 2)


@lru_cache(maxsize=8)
def _summary(path: str, mtime: float) -> dict:
    s = _store(Path(path))
    ds = s.open()
    a = s.attrs
    dates = _dates(ds)
    ny, nx = int(ds.sizes["y"]), int(ds.sizes["x"])
    c = {"y": slice(ny // 2 - 4, ny // 2 + 4), "x": slice(nx // 2 - 4, nx // 2 + 4)}
    lon = float(np.nanmedian(s.read("geometry_lon", **c)))
    lat = float(np.nanmedian(s.read("geometry_lat", **c)))
    inc = float(np.nanmedian(s.read("geometry_incidence", **c)))
    k = float(a["wavelength_m"]) * 1000 / (4 * math.pi)            # mm of LOS per radian
    utc = a.get("sensing_mid_utc") or {}
    per = a.get("ionosphere_per_date") or {}
    offs = a.get("subswath_phase_offsets") or {}
    esd = [float(v) for v in np.ravel(s.read("esd_shift"))] if s.has("esd_shift") else [0.0] * len(dates)
    # subswath seams inside the crop, in columns of the crop
    x0 = int((a.get("crop_samples") or [0])[0])
    seams = sorted({(int(v[0]) - x0, sw) for sw, v in (a.get("subswath_columns") or {}).items()
                    if 0 < int(v[0]) - x0 < nx})
    rows = []
    for i, d in enumerate(dates):
        p = per.get(d) or {}
        g, e = p.get("rad_per_km_az_rg"), p.get("se_rad_per_km_az_rg")
        o = offs.get(d) or {}
        steps = {sw: v for sw, v in o.items() if isinstance(v, dict)}
        rows.append({
            "date": d, "local_hour": _local_hour(utc.get(d), lon), "esd_lines": esd[i],
            "iono_mm_per_km": [round(g[0] * k, 3), round(g[1] * k, 3)] if g else None,
            "iono_se_mm_per_km": [round(e[0] * k, 3), round(e[1] * k, 3)] if e else None,
            "iono_cells": p.get("kept"),
            "seam_rad": {sw: v.get("rad") for sw, v in steps.items()} or None,
            "seam_consistency": {sw: v.get("consistency") for sw, v in steps.items()} or None,
            "anchor": o.get("anchor"),
        })
    az, gr = _ground_spacing(a, inc)
    return {
        "stack_id": Path(path).parent.name, "track": a.get("track"), "pass_direction": a.get("pass_direction"),
        "reference_date": str(a.get("reference_date")), "lon": lon, "lat": lat,
        "wavelength_m": float(a["wavelength_m"]), "mm_per_rad": k,
        "ionosphere": a.get("ionosphere") or "none", "ionosphere_model": a.get("ionosphere_model"),
        "ionosphere_smooth_m": a.get("ionosphere_smooth_m"), "subswath": a.get("subswath"),
        "seams": [{"col": col, "subswath": sw} for col, sw in seams], "shape": [ny, nx],
        "size_km": [round(ny * az / 1000, 2), round(nx * gr / 1000, 2)], "has_field": s.has("iono"),
        "dates": rows,
    }


@lru_cache(maxsize=16)
def _field(path: str, mtime: float, date: str) -> dict:
    s = _store(Path(path))
    ds = s.open()
    dates = _dates(ds)
    if date not in dates or not s.has("iono"):
        raise FileNotFoundError(f"no ionospheric phase for {date}")
    phi = np.asarray(s.read("iono", date=dates.index(date)), np.float64)
    ny, nx = phi.shape
    fy, fx = max(1, ny // FIELD), max(1, nx // FIELD)
    small = phi[: ny // fy * fy, : nx // fx * fx].reshape(ny // fy, fy, nx // fx, fx).mean(axis=(1, 3))
    k = float(s.attrs["wavelength_m"]) * 1000 / (4 * math.pi)
    mm = (small - np.nanmedian(small)) * k
    return {"date": date, "shape": list(mm.shape), "mm": [round(float(v), 2) for v in mm.ravel()]}


def summary(stack_path: Path) -> dict:
    """Per date: local time, ESD, ionospheric gradient removed and subswath steps of a stack."""
    return _summary(str(stack_path), _mtime(stack_path))


def field(stack_path: Path, date: str) -> dict:
    """The ionospheric phase removed on ``date`` (mm of LOS, median 0), averaged to about 64 × 64 cells."""
    return _field(str(stack_path), _mtime(stack_path), date)
