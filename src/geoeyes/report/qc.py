"""Quality checks of a product for the report: the acceptance criteria of docs/en/guide/ionosphere.md §5.

Each check: ``{"check", "value", "rule", "status", "note"}``, status ``pass`` | ``review`` (look again) | ``info``
(nothing to compare with). Inputs, all optional: the stack (ionosphere, subswath steps, geometry), the PS run
(per-interferogram phase), the other tracks of the project (latest product of each) and a decomposition of the
two geometries. A check whose input is missing is left out.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

M_LAT = 110_540.0
M_LON = 111_320.0
GRADIENT_PASS, GRADIENT_REVIEW = 0.3, 0.5             # mm/yr/km, difference between two tracks, each axis
SEAM_PASS, SEAM_REVIEW = 2.0, 4.0                     # mm/yr across a subswath seam
CORR_PASS, CORR_REVIEW = 0.3, 0.5                     # |r|
HORIZONTAL_PASS, HORIZONTAL_REVIEW = 0.10, 0.15       # share of cells with significant east-west motion
SEAM_BAND_DEG = 0.08                                  # points within this incidence of the seam, on each side


def _status(v: float, ok: float, bad: float) -> str:
    return "pass" if abs(v) < ok else "review" if abs(v) > bad else "borderline"


def _plane(lon, lat, v) -> tuple[float, float]:
    """East and north gradient (per km) of a plane fitted to ``v``."""
    lat0 = math.radians(float(np.nanmean(lat)))
    x = (lon - np.nanmean(lon)) * M_LON * math.cos(lat0) / 1000
    y = (lat - np.nanmean(lat)) * M_LAT / 1000
    ok = np.isfinite(v)
    c = np.linalg.lstsq(np.column_stack([np.ones(ok.sum()), x[ok], y[ok]]), v[ok], rcond=None)[0]
    return float(c[1]), float(c[2])


def _local_hour(utc: str, lon: float) -> float:
    t = datetime.fromisoformat(str(utc).replace("Z", ""))
    return (t.hour + t.minute / 60 + lon / 15.0) % 24


def ionosphere(attrs: dict, lon: float, lat: float) -> list[dict]:
    """Was the ionosphere corrected where it is likely to matter (low latitude, afternoon to night)?"""
    utc = attrs.get("sensing_mid_utc") or {}
    if not utc:
        return []
    h = float(np.mean([_local_hour(v, lon) for v in utc.values()]))
    risky = abs(lat) < 30 and 14 <= h <= 23
    done = (attrs.get("ionosphere") or "none") != "none"
    tops = "sentinel" in str(attrs.get("sensor", "")).lower()          # the split-spectrum of GeoEyes: TOPS only
    hh = f"{int(h)}:{round((h % 1) * 60):02d}"
    status = "pass" if done or not risky else "review" if tops else "info"
    note = f"passes at {hh} local time, latitude {lat:.1f}°"
    if risky and not done:
        note += ": ionospheric ramps likely" + (", set [stack] ionosphere = \"split_spectrum\"" if tops else "")
    return [{"check": "Ionospheric correction", "value": "split-spectrum" if done else "none",
             "rule": "on for passes 14:00–23:00 local time within 30° of the equator", "status": status,
             "note": note}]


def seams(attrs: dict, incidence: np.ndarray | None, pts) -> list[dict]:
    """Velocity step across each subswath seam inside the area, and the phase steps removed at it."""
    cols = attrs.get("subswath_columns") or {}
    x0 = int((attrs.get("crop_samples") or [0])[0])
    out = []
    if incidence is None or "incidence_deg" not in pts:
        return out
    nx = incidence.shape[1]
    inc_pts = pts["incidence_deg"].to_numpy(float)
    v = pts["vel_los_mm_yr"].to_numpy(float)
    offsets = attrs.get("subswath_phase_offsets") or {}
    for sw, (c0, _) in sorted(cols.items(), key=lambda kv: kv[1][0]):
        col = int(c0) - x0
        if not 0 < col < nx:
            continue
        seam_inc = float(np.nanmedian(incidence[:, col]))
        near = (inc_pts > seam_inc - SEAM_BAND_DEG) & (inc_pts < seam_inc)
        far = (inc_pts >= seam_inc) & (inc_pts < seam_inc + SEAM_BAND_DEG)
        if near.sum() < 50 or far.sum() < 50:
            continue
        step = float(np.nanmedian(v[far]) - np.nanmedian(v[near]))
        steps = [o[sw]["rad"] for o in offsets.values() if isinstance(o.get(sw), dict)]
        shifted = sum(abs(s) > 1 for s in steps)
        note = (f"incidence {seam_inc:.2f}°; phase steps removed on {len(steps)} dates, {shifted} above 1 rad"
                if steps else f"incidence {seam_inc:.2f}°; no phase step removed (stack without seam alignment)")
        out.append({"check": f"Velocity step at the {sw} seam", "value": f"{step:+.1f} mm/yr",
                    "rule": f"|step| < {SEAM_PASS:g} mm/yr (look again above {SEAM_REVIEW:g})",
                    "status": _status(step, SEAM_PASS, SEAM_REVIEW), "note": note})
    return out


def _latest_products(project: Path, track: str) -> list[Path]:
    """Latest product (highest version) of every other track of the project."""
    best: dict[str, tuple[int, Path]] = {}
    for p in (project / "products").glob("*"):
        item = p / "item.json"
        if not item.exists():
            continue
        try:
            props = json.loads(item.read_text(encoding="utf-8"))["properties"]
        except (ValueError, KeyError):
            continue
        t = props.get("geoeyes:track", "")
        m = re.search(r"_v(\d+)$", p.name)
        if t and t != track and m and int(m.group(1)) > best.get(t, (-1, p))[0]:
            best[t] = (int(m.group(1)), p)
    return [p for _, p in best.values()]


def other_tracks(product: Path, pts) -> list[dict]:
    """Velocity gradients against the latest product of each other track, over the common area."""
    from geoeyes.io.points import read_points
    project = product.parent.parent
    track = json.loads((product / "item.json").read_text(encoding="utf-8"))["properties"].get("geoeyes:track", "")
    out = []
    lon, lat, v = (pts[c].to_numpy(float) for c in ("lon", "lat", "vel_los_mm_yr"))
    for other in _latest_products(project, track):
        q = read_points(other / "points.parquet")
        olon, olat, ov = (q[c].to_numpy(float) for c in ("lon", "lat", "vel_los_mm_yr"))
        w, e = max(lon.min(), olon.min()), min(lon.max(), olon.max())
        s, n = max(lat.min(), olat.min()), min(lat.max(), olat.max())
        if w >= e or s >= n:
            continue
        a = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
        b = (olon >= w) & (olon <= e) & (olat >= s) & (olat <= n)
        if a.sum() < 1000 or b.sum() < 1000:
            continue
        ge, gn = _plane(lon[a], lat[a], v[a])
        oe, on = _plane(olon[b], olat[b], ov[b])
        d = max(abs(ge - oe), abs(gn - on))
        props = json.loads((other / "item.json").read_text(encoding="utf-8"))["properties"]
        label = f"{props.get('geoeyes:track', '')} {other.name.rpartition('_')[2]}".strip()
        out.append({"check": f"Velocity gradient against {label}",
                    "value": f"east {ge - oe:+.2f}, north {gn - on:+.2f} mm/yr/km",
                    "rule": f"each axis < {GRADIENT_PASS:g} mm/yr/km (look again above {GRADIENT_REVIEW:g})",
                    "status": _status(d, GRADIENT_PASS, GRADIENT_REVIEW),
                    "note": f"{other.name}: east {oe:+.2f}, north {on:+.2f}; this product {ge:+.2f}, {gn:+.2f} "
                            "mm/yr/km; a tilt of the ground shows in both, a ramp in one"})
    return out


def residual_ramps(ps_dir: Path, attrs: dict, heading: float | None, mm_per_rad: float) -> list[dict]:
    """Per date: is the ramp left in the interferograms related to the ionospheric gradient removed?"""
    import h5py
    per = attrs.get("ionosphere_per_date") or {}
    state = ps_dir / "state.h5"
    if not per or not state.exists() or heading is None:
        return []
    rng = np.random.default_rng(0)
    with h5py.File(state, "r") as f:
        if "phase/unwrapped" not in f or "time/ifg_dates" not in f:
            return []
        n = f["ps/lon"].shape[0]
        idx = np.sort(rng.choice(n, min(n, 60_000), replace=False))
        lon, lat = f["ps/lon"][idx], f["ps/lat"][idx]
        ph = f["phase/unwrapped"][:][idx]
        dates = [d.decode() if isinstance(d, bytes) else str(d) for d in f["time/ifg_dates"][:]]
    x = (lon - lon.mean()) * M_LON * math.cos(math.radians(float(lat.mean()))) / 1000
    y = (lat - lat.mean()) * M_LAT / 1000
    h = math.radians(heading)
    az, rg = x * math.sin(h) + y * math.cos(h), x * math.cos(h) - y * math.sin(h)
    A = np.column_stack([np.ones_like(az), az, rg])
    left, removed = [], []
    for j, d in enumerate(dates):
        g = (per.get(d) or {}).get("rad_per_km_az_rg")
        ok = np.isfinite(ph[:, j])
        if not g or ok.sum() < 100:
            continue
        c = np.linalg.lstsq(A[ok], ph[ok, j], rcond=None)[0] * mm_per_rad
        left.append(c[1:])
        removed.append(np.asarray(g) * mm_per_rad)
    if len(left) < 6:
        return []
    L, R = np.asarray(left), np.asarray(removed)
    out = []
    for k, name in ((0, "along track"), (1, "across track")):
        r = float(np.corrcoef(R[:, k], L[:, k])[0, 1])
        out.append({"check": f"Ramp left against ionosphere removed, {name}", "value": f"r = {r:+.2f}",
                    "rule": f"|r| < {CORR_PASS:g} (above {CORR_REVIEW:g}: the correction has the wrong scale)",
                    "status": _status(r, CORR_PASS, CORR_REVIEW),
                    "note": f"{len(L)} dates; ramp left {np.std(L[:, k]):.2f} mm/km (std), removed "
                            f"{np.std(R[:, k]):.2f} mm/km; a low r with a large ramp left points to the troposphere"})
    return out


def decomposition(project: Path, product: Path, track: str) -> list[dict]:
    """East/up correlation and horizontal share of a decomposition of this product with the latest product of the
    other tracks (one made with an older version of either is left out)."""
    import pandas as pd
    current = {product.name} | {p.name for p in _latest_products(project, track)}
    for f in sorted((project / "analyses" / "decompose").glob("*/decompose.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        ids = {p["id"] for p in s.get("products", [])}
        if product.name not in ids or not ids <= current:
            continue
        t = pd.read_parquet(f.parent / "decompose.parquet", columns=["up", "east"])
        r = float(np.corrcoef(t["east"], t["up"])[0, 1])
        deramp = (s.get("params") or {}).get("deramp", "none")
        hs = float(s.get("horizontal_share", 0))
        how = "with a plane removed from each product" if deramp == "plane" else "as is"
        return [{"check": "Decomposition: east/up correlation", "value": f"r = {r:+.2f}",
                 "rule": f"|r| < {CORR_PASS:g} without plane removal (look again above {CORR_REVIEW:g})",
                 "status": _status(r, CORR_PASS, CORR_REVIEW) if deramp == "none" else "info",
                 "note": f"{s.get('n_cells', 0):,} cells, decomposed {how}"},
                {"check": "Decomposition: significant east-west motion", "value": f"{100 * hs:.1f} % of the cells",
                 "rule": f"< {100 * HORIZONTAL_PASS:g} % (look again above {100 * HORIZONTAL_REVIEW:g} %)",
                 "status": _status(hs, HORIZONTAL_PASS, HORIZONTAL_REVIEW),
                 "note": f"decomposed {how}; ramps {[r_['span_mm_yr'] for r_ in s.get('ramps', [])]} mm/yr"}]
    return []


def checks(product: Path, pts, stack: dict, ps_dir: Path) -> list[dict]:
    """All checks that the available inputs allow; a failing check is logged and left out."""
    from geoeyes.io.stack import StackStore
    a = stack.get("attrs", {})
    lon, lat = float(np.nanmedian(pts["lon"])), float(np.nanmedian(pts["lat"]))
    incidence = None
    if stack.get("path"):
        try:
            incidence = np.asarray(StackStore(stack["path"]).read("geometry_incidence"), float)
        except Exception:                                     # an old stack
            incidence = None
    wl = a.get("wavelength_m")
    heading = a.get("heading_deg")
    out: list[dict] = []
    for name, f in (("ionosphere", lambda: ionosphere(a, lon, lat)),
                    ("seams", lambda: seams(a, incidence, pts)),
                    ("other tracks", lambda: other_tracks(product, pts)),
                    ("residual ramps", lambda: residual_ramps(ps_dir, a, heading, wl * 1000 / (4 * math.pi))
                     if wl else []),
                    ("decomposition", lambda: decomposition(product.parent.parent, product, a.get("track", "")))):
        try:
            out += f()
        except Exception as exc:                              # a check never stops the report
            log.warning("quality check %s skipped: %s", name, exc)
    return out


def summary(rows: list[dict]) -> dict[str, Any]:
    return {k: sum(r["status"] == k for r in rows) for k in ("pass", "borderline", "review", "info")}
