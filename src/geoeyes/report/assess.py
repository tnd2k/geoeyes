"""Assessment part of the report (Part A): plain-language statements, hot spots, the impacts read from the analyses
already run on the product, and the standardised indicators (``indicators.json``, an input of a digital twin).

Rates are vertical when the product has the line of sight (v_LOS / l_u, the ground assumed to move only up or
down, as the building and line analyses do), LOS otherwise; negative = sinking. Nothing is fetched: place names
come from offline caches (the stack places of the open-data browser, the OSM line names of ``geoeyes lines``, the
flood inventory of ``geoeyes floods``). An analysis that has not been run is reported as such, with the command
that runs it, never left out.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from geoeyes.report.qc import M_LAT, M_LON

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.indicators/1"
CELL_M = 100.0                       # cells of the area indicators and the hot spots
MIN_CELL_POINTS = 3                  # a cell counts with at least this many points (one noisy point is not an area)
THRESHOLDS = (5, 10, 20)             # mm/yr, sinking (and rising) area indicators
HOT_RATE = 5.0                       # mm/yr, least rate of a hot spot (raised to twice the median error)
HOT_MIN_CELLS, HOT_MIN_POINTS = 3, 30
HOT_MAX = {"sinking": 5, "rising": 2}
SERIES_POINTS = 2000                 # points per hot spot whose series are read
NEAR_M = 300.0                       # a named line or a flood location this close names a hot spot
LEVELS = ("very low", "low", "moderate", "high", "very high")
MOTION = {"stable": "no motion beyond the noise", "steady": "moves at a constant rate",
          "seasonal": "goes down and up with the seasons", "speeding": "the motion is speeding up",
          "slowing": "the motion is fading", "onset": "the motion started or stopped at a date",
          "step": "a sudden jump (an event, or a processing error to check)"}
# angular distortion reached in 10 years: Bjerrum (1963) 1/500 cracks possible, Skempton & MacDonald 1/300 damage
DAMAGE = (("no measurable tilt", None), ("below 1/500: negligible", 1 / 500),
          ("1/500 to 1/300: cracks possible", 1 / 300), ("1/300 or more: structural damage possible", math.inf))


# ---------------------------------------------------------------- rates, cells, hot spots
def rates(pts) -> tuple[np.ndarray, np.ndarray, str]:
    """Velocity and its standard error in the assessment basis: ``vertical`` (v_LOS / l_u) when the product has
    the line of sight, else ``los``."""
    v = pts["vel_los_mm_yr"].to_numpy(float)
    s = pts["vel_std_mm_yr"].to_numpy(float) if "vel_std_mm_yr" in pts else np.full(v.size, np.nan)
    if "los_u" in pts:
        lu = pts["los_u"].to_numpy(float)
        ok = np.abs(lu) > 0.3
        if ok.mean() > 0.9:
            lu = np.where(ok, lu, np.nan)
            return v / lu, s / np.abs(lu), "vertical"
    return v, s, "los"


def grid(lon, lat, v, cell_m: float = CELL_M):
    """Cells of ``cell_m`` holding points (ix, iy, n finite rates, median rate, centre) and the cell of each point."""
    import pandas as pd
    lat0 = math.radians(float(np.nanmean(lat)))
    ix = np.floor((lon - np.nanmin(lon)) * M_LON * math.cos(lat0) / cell_m).astype(np.int64)
    iy = np.floor((lat - np.nanmin(lat)) * M_LAT / cell_m).astype(np.int64)
    ny = int(iy.max()) + 1
    uniq, inv = np.unique(ix * ny + iy, return_inverse=True)
    g = pd.DataFrame({"c": inv, "v": v, "lon": lon, "lat": lat}).groupby("c")
    cells = pd.DataFrame({"ix": uniq // ny, "iy": uniq % ny, "n": g["v"].count().to_numpy(),
                          "v": g["v"].median().to_numpy(), "lon": g["lon"].mean().to_numpy(),
                          "lat": g["lat"].mean().to_numpy()})
    return cells, inv


def areas(cells, cell_m: float = CELL_M) -> dict[str, float]:
    """km² of the counted cells (``MIN_CELL_POINTS``) sinking / rising faster than each threshold, and stable."""
    ok = cells["n"].to_numpy() >= MIN_CELL_POINTS
    v = cells["v"].to_numpy(float)[ok]
    km2 = (cell_m / 1000) ** 2
    out = {"counted_km2": round(ok.sum() * km2, 2),
           "stable_km2": round(float((np.abs(v) < THRESHOLDS[0]).sum()) * km2, 2)}
    for t in THRESHOLDS:
        out[f"sinking_{t}"] = round(float((v <= -t).sum()) * km2, 2)
        out[f"rising_{t}"] = round(float((v >= t).sum()) * km2, 2)
    out["sinking_max_mm_yr"] = round(float(v.min()), 1) if v.size else None
    return out


def hotspots(cells, inv, lon, lat, v, threshold: float, cell_m: float = CELL_M) -> list[dict]:
    """Connected groups of counted cells moving faster than ``threshold`` (8-neighbours), the largest
    (area × rate) of each direction first: ``HOT_MAX`` sinking then rising, numbered H1, H2..."""
    from scipy import ndimage
    ix, iy = cells["ix"].to_numpy(), cells["iy"].to_numpy()
    cv = cells["v"].to_numpy(float)
    counted = cells["n"].to_numpy() >= MIN_CELL_POINTS
    km2 = (cell_m / 1000) ** 2
    out = []
    for kind, sign in (("sinking", -1), ("rising", 1)):
        m = counted & (sign * cv >= threshold)
        if not m.any():
            continue
        mask = np.zeros((int(ix.max()) + 1, int(iy.max()) + 1), bool)
        mask[ix[m], iy[m]] = True
        lab, _ = ndimage.label(mask, structure=np.ones((3, 3), int))
        comp = np.where(m, lab[ix, iy], 0)
        ncell = np.bincount(comp)
        pc = comp[inv]                                            # group of each point (0: none)
        sel = np.flatnonzero((pc > 0) & np.isfinite(v))
        order = sel[np.argsort(pc[sel], kind="stable")]
        groups, starts = np.unique(pc[order], return_index=True)
        found = []
        for c, a, z in zip(groups, starts, np.r_[starts[1:], order.size], strict=True):
            p = order[a:z]
            if ncell[c] < HOT_MIN_CELLS or p.size < HOT_MIN_POINTS:
                continue
            r = float(np.median(v[p]))
            found.append({"kind": kind, "cells": int(ncell[c]), "area_km2": round(ncell[c] * km2, 2),
                          "n": int(p.size), "rate_mm_yr": round(r, 1),
                          "fastest_mm_yr": round(float(np.percentile(v[p], 5 if sign < 0 else 95)), 1),
                          "lon": float(np.median(lon[p])), "lat": float(np.median(lat[p])),
                          "bbox": [float(lon[p].min()), float(lat[p].min()), float(lon[p].max()), float(lat[p].max())],
                          "score": ncell[c] * km2 * abs(r), "_points": p})
        out += sorted(found, key=lambda h: -h["score"])[:HOT_MAX[kind]]
    for i, h in enumerate(out, 1):
        h["id"] = f"H{i}"
    return out


def sample_points(h: dict, seed: int = 0) -> np.ndarray:
    p = h["_points"]
    return p if p.size <= SERIES_POINTS else np.sort(np.random.default_rng(seed).choice(p, SERIES_POINTS, False))


def series(uids, scale, wide) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Median and interquartile range per date of the series of ``uids`` (``wide``: point × date, mm LOS),
    each scaled to the assessment basis (``scale``: 1 / l_u, or 1)."""
    sub = wide.reindex(uids).to_numpy(float) * np.asarray(scale, float)[:, None]
    dates = [str(d.date()) if hasattr(d, "date") else str(d) for d in wide.columns]
    with np.errstate(all="ignore"):
        q = np.nanpercentile(sub, [25, 50, 75], axis=0)
    return dates, q[1], q[[0, 2]]


def trend(dates: list[str], d) -> dict[str, Any]:
    """Accelerating / slowing / seasonal / steady from a series (mm): the rates of the first and second half of the
    period (seasonal swing removed when one is found; a change must exceed 30 % of the rate, 2 mm/yr and twice its
    standard error) and an annual sine fit over at least ~10 months. Dates far off the line (beyond 3 robust
    standard deviations: the atmosphere or an unwrapping error of one image, shared by the whole area) are left
    out and listed in ``outliers``."""
    t = np.array([(date.fromisoformat(x) - date.fromisoformat(dates[0])).days for x in dates], float) / 365.25
    d = np.asarray(d, float)
    ok = np.isfinite(d)
    keep = ok.copy()
    for _ in range(3):
        if keep.sum() < 6:
            break
        res = d - np.polyval(np.polyfit(t[keep], d[keep], 1), t)
        mad = 1.4826 * float(np.median(np.abs(res[keep] - np.median(res[keep]))))
        new = ok & (np.abs(res) <= max(3 * mad, 1.0))
        if new.sum() < 6 or (new == keep).all():
            break
        keep = new
    outliers = [x for x, o, k in zip(dates, ok, keep, strict=True) if o and not k]
    t, d = t[keep], d[keep]
    if t.size < 6:
        return {"kind": "unknown", "text": "too few dates to tell how the motion evolves", "outliers": outliers}
    rate = float(np.polyfit(t, d, 1)[0])
    lin_res = float(np.std(d - np.polyval(np.polyfit(t, d, 1), t)))
    span = float(t[-1] - t[0])
    amp, seasonal = 0.0, np.zeros_like(d)
    if span >= 0.8 and t.size >= 10:
        w = 2 * np.pi * t
        a = np.column_stack([np.ones_like(t), t, np.sin(w), np.cos(w)])
        c = np.linalg.lstsq(a, d, rcond=None)[0]
        res = float(np.std(d - a @ c))
        if math.hypot(c[2], c[3]) >= 3.0 and res <= 0.75 * lin_res:          # a swing that the data carry
            amp, seasonal = math.hypot(c[2], c[3]), c[2] * np.sin(w) + c[3] * np.cos(w)
            rate = float(c[1])
    ds = d - seasonal
    mid = t[0] + span / 2
    first, second = t <= mid, t >= mid
    out: dict[str, Any] = {"rate_mm_yr": round(rate, 1), "seasonal_amp_mm": round(amp, 1), "outliers": outliers}
    if first.sum() >= 4 and second.sum() >= 4:
        (r1, se1), (r2, se2) = _slope(t[first], ds[first]), _slope(t[second], ds[second])
        out |= {"rate_first_mm_yr": round(r1, 1), "rate_second_mm_yr": round(r2, 1)}
        change = math.copysign(1, rate) * (r2 - r1)                       # > 0: faster in the direction of motion
        big = max(2.0, 0.3 * abs(rate), 2 * math.hypot(se1, se2))
        if change > big:
            out["kind"] = "accelerating"
            out["text"] = f"accelerating: {_mm(r1)} mm/yr in the first half of the period, {_mm(r2)} in the second"
        elif change < -big:
            out["kind"] = "slowing"
            out["text"] = f"slowing down: {_mm(r1)} mm/yr in the first half of the period, {_mm(r2)} in the second"
    if "kind" not in out:
        out["kind"] = "seasonal" if amp else "steady"
        out["text"] = (f"seasonal: swings ±{amp:.0f} mm over the year on top of {_mm(rate)} mm/yr" if amp
                       else f"steady at about {_mm(rate)} mm/yr")
    elif amp:
        out["text"] += f", with a seasonal swing of ±{amp:.0f} mm"
    if span < 1.0:
        out["text"] += " (less than a year of images: a seasonal swing may look like a change of rate)"
    if outliers:
        out["text"] += f"; {len(outliers)} date(s) far off the trend left out (hollow points)"
    return out


def _slope(t, d) -> tuple[float, float]:
    """Least-squares rate and its standard error."""
    a = np.column_stack([np.ones_like(t), t])
    c, *_ = np.linalg.lstsq(a, d, rcond=None)
    s2 = float(np.sum((d - a @ c) ** 2)) / max(t.size - 2, 1)
    return float(c[1]), float(np.sqrt(s2 * np.linalg.pinv(a.T @ a)[1, 1]))


def _mm(x: float) -> str:
    return (f"{x:+.0f}" if abs(x) >= 10 else f"{x:+.1f}").replace("-", "\u2212")


def _speed(x: float) -> str:
    """'12 mm per year' from a rate of any sign."""
    return (f"{abs(x):.0f}" if abs(x) >= 10 else f"{abs(x):.1f}") + " mm per year"


# ---------------------------------------------------------------- names (offline)
def _places(ws, lon: float, lat: float) -> str:
    """City-level name from the place cache of the open-data browser (``cache/opendata/places.json``)."""
    try:
        from geoeyes.opendata import places
        s = [{"bbox": [lon, lat, lon, lat]}]
        places.names(ws, s)
        return s[0]["place"]
    except Exception as exc:                                  # a missing or broken cache: coordinates only
        log.debug("place cache: %s", exc)
        return ""


class Namer:
    """Names a location from the named OSM lines of ``geoeyes lines`` and the located flood reports, within
    ``NEAR_M``."""

    def __init__(self, lines_dir: Path | None, floods: list[dict]):
        from scipy.spatial import cKDTree
        self.items: list[tuple[float, float, str]] = []
        if lines_dir is not None and (lines_dir / "stations.parquet").exists():
            import pandas as pd
            st = pd.read_parquet(lines_dir / "stations.parquet", columns=["line", "lon", "lat"])
            ln = pd.read_parquet(lines_dir / "lines.parquet", columns=["line", "kind", "name"])
            st = st.merge(ln[ln["name"].fillna("") != ""], on="line")
            self.items += [(a, b, f"{n} ({k})") for a, b, n, k in zip(st.lon, st.lat, st.name, st.kind, strict=True)]
        for f in floods:
            p = f["properties"]
            lo, la = _anchor(f["geometry"])
            self.items.append((lo, la, f"reported flood: {p.get('street') or p.get('place') or p.get('text', '')}"))
        self.tree = None
        if self.items:
            a = np.array([(x, y) for x, y, _ in self.items])
            self.lat0 = float(np.mean(a[:, 1]))
            self.tree = cKDTree(self._xy(a[:, 0], a[:, 1]))

    def _xy(self, lon, lat):
        return np.column_stack([np.asarray(lon) * M_LON * math.cos(math.radians(self.lat0)), np.asarray(lat) * M_LAT])

    def __call__(self, lon: float, lat: float) -> str:
        if self.tree is None:
            return ""
        dist, i = self.tree.query(self._xy([lon], [lat])[0])
        return self.items[int(i)][2] if dist <= NEAR_M else ""


def _anchor(geom: dict) -> tuple[float, float]:
    c = geom["coordinates"]
    if geom["type"] == "Point":
        return float(c[0]), float(c[1])
    pts = c if geom["type"] == "LineString" else [p for ln in c for p in ln]
    return float(pts[len(pts) // 2][0]), float(pts[len(pts) // 2][1])


# ---------------------------------------------------------------- impacts: the analyses run on the product
def _not_run(cmd: str, why: str = "") -> dict:
    return {"assessed": False, "run": cmd, "why": why}


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None


def hazard(folder: Path, cmd: str) -> dict:
    s = _read(folder / "hazard.json")
    if s is None:
        return _not_run(cmd)
    cell_m = (s.get("params") or {}).get("cell_m", CELL_M)
    modes = {m: {lv: (d.get(lv) or {}).get("km2", 0.0) for lv in LEVELS}
             for m, d in (s.get("by_level") or {}).items() if any((d.get(lv) or {}).get("cells") for lv in LEVELS)}
    high = sum(d["high"] + d["very high"] for d in modes.values())
    moderate = sum(d["moderate"] for d in modes.values())
    cp = s.get("coupling") or {}
    acc = int(s.get("accelerating_cells") or 0)
    text = [f"The hazard zoning rates every {cell_m:g} m cell from very low to very high, from how fast the ground "
            "moves and how much damage that motion can do (uneven settlement on flat ground, slope on hillsides).",
            f"{high:.2f} km² is rated high or very high and {moderate:.2f} km² moderate." if high or moderate else
            "No cell is rated moderate or higher."]
    if acc:
        text.append(f"In {acc} cell(s) the sinking is speeding up; their level was raised by one class.")
    if cp.get("assessed"):
        text.append(f"In {cp.get('cells_significant', 0)} of {cp.get('cells_tested', 0)} cells the motion follows "
                    "the rainfall" + (f", about {cp['lag_months_median']:.0f} month(s) later" if cp.get(
                        "lag_months_median") is not None else "") + ".")
    return {"assessed": True, "folder": str(folder), "cell_m": cell_m, "created": s.get("created", ""),
            "by_level": modes, "high_km2": round(high, 3), "moderate_km2": round(moderate, 3),
            "accelerating_cells": acc, "rain_coupled_cells": cp.get("cells_significant"),
            "rain_tested_cells": cp.get("cells_tested"), "warnings": s.get("warnings", []), "text": text,
            "groundwater": s.get("groundwater") or {}}


def hazard_cells(folder: str | Path):
    import pandas as pd
    return pd.read_parquet(Path(folder) / "cells.parquet", columns=["lon", "lat", "mode", "hazard"])


def behaviour(folder: Path, cmd: str) -> dict:
    s = _read(folder / "behaviour.json")
    if s is None:
        return _not_run(cmd)
    counts = s.get("counts") or {}
    n = max(sum(counts.values()), 1)
    rows = [{"kind": k, "reading": MOTION.get(k, ""), "cells": int(c), "share": round(c / n, 3)}
            for k, c in counts.items()]
    moving = [r for r in rows if r["kind"] != "stable" and r["cells"]]
    text = [f"Each hazard cell's series was matched to the simplest kind of motion it supports; "
            f"{counts.get('stable', 0) / n:.0%} of the cells are stable."]
    if moving:
        top = max(moving, key=lambda r: r["cells"])
        text.append(f"Of the moving cells, most {top['reading']} ({top['cells']:,} cells).")
    if counts.get("speeding"):
        text.append(f"In {counts['speeding']} cell(s) the motion is speeding up: they deserve a first look.")
    for d in s.get("shared_change_dates", []):
        text.append(f"Many cells change on {d}: more likely that radar image than the ground; check before use.")
    return {"assessed": True, "rows": rows, "text": text}


def buildings(b_dir: Path, r_dir: Path, cmd_b: str, cmd_r: str) -> dict:
    s, r = _read(b_dir / "buildings.json"), _read(r_dir / "risk.json")
    if s is None and r is None:
        return _not_run(cmd_b)
    out: dict[str, Any] = {"assessed": True, "text": []}
    if s is not None:
        import pandas as pd
        out |= {"total": s.get("buildings_total"), "with_points": s.get("buildings_with_points"),
                "with_tilt": s.get("with_tilt"), "beta_over_1_500": s.get("beta_over_1_500")}
        damage = {k: 0 for k, _ in DAMAGE}
        sinking = {f"sinking over {t} mm/yr": 0 for t in THRESHOLDS}
        if (b_dir / "buildings.parquet").exists():
            t = pd.read_parquet(b_dir / "buildings.parquet", columns=["v_vert", "beta_10yr"])
            beta = t["beta_10yr"].to_numpy(float)
            damage[DAMAGE[0][0]] = int((~np.isfinite(beta)).sum())
            lo = 0.0
            for name, hi in DAMAGE[1:]:
                damage[name] = int(((beta >= lo) & (beta < hi)).sum())
                lo = hi
            for th in THRESHOLDS:
                sinking[f"sinking over {th} mm/yr"] = int((t["v_vert"].to_numpy(float) <= -th).sum())
        out["damage"] = damage
        out["sinking"] = sinking
        out["text"].append(f"{s.get('buildings_with_points', 0):,} of {s.get('buildings_total', 0):,} building "
                           "footprints (Overture Maps) hold enough measurement points to rate their own motion.")
        out["text"].append(f"{sinking[f'sinking over {THRESHOLDS[0]} mm/yr']:,} of them sink faster than "
                           f"{THRESHOLDS[0]} mm per year; {s.get('beta_over_1_500', 0):,} reach an angular distortion "
                           "of 1/500 in 10 years, the limit above which cracks may appear.")
    else:
        out["buildings_run"] = cmd_b
    if r is not None:
        out["risk"] = r.get("by_risk") or {}
        hi = sum((r.get("by_risk") or {}).get(k, 0) for k in ("high", "very high"))
        out["text"].append(f"Risk screening (hazard × size of the building): {hi:,} building(s) at high or very high "
                           "risk. A screening, not a structural survey.")
    else:
        out["risk_run"] = cmd_r
    return out


def lines(folder: Path, cmd: str) -> dict:
    s = _read(folder / "lines.json")
    if s is None:
        return _not_run(cmd)
    horizon = (s.get("params") or {}).get("horizon_yr", 10)
    kinds = [{"kind": k, **v} for k, v in (s.get("by_kind") or {}).items() if v.get("lines")]
    km = sum(k["km"] for k in kinds)
    flagged = sum(k["flagged_stations"] for k in kinds)
    text = [f"Ground motion was read every few tens of metres along {km:,.0f} km of dykes, railways and main roads "
            "(OpenStreetMap).",
            f"{flagged} place(s) along them settle unevenly enough to reach 1/500 within {horizon:g} years, the limit "
            "above which embankments and pavements crack." if flagged else
            "No place along them settles unevenly enough to reach 1/500 within "
            f"{horizon:g} years."]
    return {"assessed": True, "kinds": kinds, "km": round(km, 1), "flagged": flagged,
            "hotspots": (s.get("hotspots") or [])[:6], "text": text}


def floods(features: list[dict], inventory: bool, lon, lat, v, cmd: str) -> dict:
    """Located flood reports inside the product against the rate around them (``flood_reports.near_product``)."""
    if not inventory:
        return _not_run(cmd)
    if not features:
        return {"assessed": True, "n": 0, "in_sinking": 0, "rows": [],
                "text": ["No reported flood location of the inventory lies in the measured area."]}
    from geoeyes.ancillary.flood_reports import near_product
    near = near_product({"features": features}, lon, lat, v)
    rows = []
    for f in features:
        r = near["rows"].get(f["id"], {})
        if not r.get("n"):
            continue
        p = f["properties"]
        rows.append({"id": f["id"], "where": p.get("street") or p.get("place") or p.get("text", ""),
                     "cause": p.get("cause", ""), "reported": p.get("reported", ""), "n": r["n"],
                     "rate_mm_yr": r["vel_median"], "contrast_mm_yr": r.get("contrast")})
    rows.sort(key=lambda r: r["rate_mm_yr"])
    sinking = [r for r in rows if r["rate_mm_yr"] <= -THRESHOLDS[0]]
    text = [f"{len(features)} reported flood location(s) lie in the area; {len(rows)} have measurement points within "
            f"{near['radius_m']:g} m."]
    text.append(f"{len(sinking)} of them sit on ground sinking faster than {THRESHOLDS[0]} mm per year: there, "
                "flooding gets worse as the ground goes down, and drainage levels drift." if sinking else
                f"None of them sits on ground sinking faster than {THRESHOLDS[0]} mm per year.")
    return {"assessed": True, "n": len(features), "with_points": len(rows), "in_sinking": len(sinking),
            "rows": rows[:12], "text": text}


def groundwater(hz: dict, cmd: str) -> dict:
    if not hz.get("assessed"):
        return _not_run(cmd, "part of the hazard zoning")
    g = hz.get("groundwater") or {}
    if not g.get("used"):
        return _not_run(cmd + " (with EARTHDATA_TOKEN set)", g.get("reason", ""))
    text = ["Groundwater storage comes from GLDAS, a regional model on a 25 km grid: it shows the trend of the "
            "aquifers, not the pumping of single wells."]
    if g.get("trend_mm_yr") is not None:
        text.append(f"Storage changes by {g['trend_mm_yr']:+.0f} mm of water per year over the period.")
    if g.get("cells_tested"):
        text.append(f"In {g.get('cells_significant', 0)} of {g['cells_tested']} cells the ground motion follows the "
                    "storage" + (f", about {g['lag_months_median']:.0f} month(s) later" if g.get(
                        "lag_months_median") is not None else "") + ".")
    else:
        text.append("Whether the ground follows the storage could not be tested: the storage is published months "
                    "late, or the series are too short.")
    return {"assessed": True, "trend_mm_yr": g.get("trend_mm_yr"), "cells_tested": g.get("cells_tested"),
            "cells_coupled": g.get("cells_significant"), "lag_months": g.get("lag_months_median"), "text": text}


def gnss(folder: Path, cmd: str) -> dict:
    s = _read(folder / "comparison.json")
    if s is None:
        return _not_run(cmd)
    mode = (s.get("params") or {}).get("los_mode", "full")
    rows = []
    for st in s.get("stations", []):
        if not st.get("used"):
            continue
        m = st.get(mode) or {}
        d = m.get("rate_diff_mm_yr")
        if d is None:
            continue
        rows.append({"site": st["site"], "distance_m": st.get("median_distance_m"), "epochs": m.get("n_epochs"),
                     "insar_mm_yr": m.get("rate_insar_mm_yr"), "gnss_mm_yr": m.get("rate_gnss_mm_yr"),
                     "diff_mm_yr": d, "rmse_mm": m.get("rmse_mm"),
                     "agreement": "good" if abs(d) <= 2 else "fair" if abs(d) <= 5 else "poor"})
    if not rows:
        return {"assessed": True, "rows": [], "rms_mm_yr": None, "n": 0,
                "text": ["No GNSS station of the Nevada Geodetic Laboratory could be compared with this product"
                         + (f" ({s['warnings'][0]})" if s.get("warnings") else "") + "."]}
    rms = float(np.sqrt(np.mean([r["diff_mm_yr"] ** 2 for r in rows])))
    text = [f"At {len(rows)} permanent GNSS station(s) the radar rate differs from the GNSS rate by "
            f"{rms:.1f} mm per year (root mean square): "
            + ("good agreement." if rms <= 2 else "fair agreement." if rms <= 5 else
               "poor agreement: the reference area may be moving.")]
    return {"assessed": True, "rows": rows, "rms_mm_yr": round(rms, 2), "n": len(rows), "text": text}


# ---------------------------------------------------------------- plain statements, recommendations, indicators
def statements(where: str, a: dict, st: dict, ar: dict, hot: list[dict], conf: dict, basis: str) -> list[str]:
    months = a["span_days"] / 30.44
    out = [f"{where} was measured at {st['n_points']:,} points over {st['area_km2']:,.1f} km², from "
           f"{a['n_dates']} radar images taken between {a['first']} and {a['last']} ({months:.0f} months)."]
    if ar["counted_km2"]:
        out.append(f"{ar['stable_km2'] / ar['counted_km2']:.0%} of the measured area moves less than "
                   f"{THRESHOLDS[0]} mm per year: stable, within what the method can tell apart.")
    down = "sinks" if basis == "vertical" else "moves away from the satellite (most often: sinks)"
    if ar[f"sinking_{THRESHOLDS[0]}"]:
        s = (f"The ground {down} faster than {THRESHOLDS[0]} mm per year over {ar[f'sinking_{THRESHOLDS[0]}']:.2f} "
             f"km² ({ar[f'sinking_{THRESHOLDS[0]}'] / max(ar['counted_km2'], 1e-9):.0%} of the measured area)")
        more = [f"faster than {t} mm per year over {ar[f'sinking_{t}']:.2f} km²" for t in THRESHOLDS[1:]
                if ar[f"sinking_{t}"]]
        out.append(s + ("; " + " and ".join(more) if more else "") + ".")
    else:
        out.append(f"No area {down} faster than {THRESHOLDS[0]} mm per year.")
    sink = [h for h in hot if h["kind"] == "sinking"]
    if sink:
        h = sink[0]
        out.append(f"The main sinking area ({h['id']}, {h['label']}) goes down about {_speed(h['rate_mm_yr'])}, "
                   f"up to {_speed(h['fastest_mm_yr'])} at its fastest points; "
                   f"its motion is {h.get('trend', {}).get('kind', 'unknown')}."
                   + (f" {len(sink) - 1} other sinking area(s) are listed in section 2." if len(sink) > 1 else ""))
    if ar[f"rising_{THRESHOLDS[0]}"]:
        out.append(f"{ar[f'rising_{THRESHOLDS[0]}']:.2f} km² rises faster than {THRESHOLDS[0]} mm per year (for "
                   "example recovering groundwater, swelling soil, or an error to check).")
    out.append(f"Confidence: {conf['level']}" + (f" — {conf['plain'][0]}." if conf.get("plain") else "."))
    return out


def recommendations(hot: list[dict], imp: dict, conf: dict, a: dict) -> list[dict]:
    """What to do, most urgent first: ``{"text", "why"}``."""
    out = []
    sink = [h for h in hot if h["kind"] == "sinking"]
    if sink:
        out.append({"text": f"Visit the sinking areas {', '.join(h['id'] for h in sink)} (section 2): look for new "
                            "cracks in walls and pavements, tilted poles and fences, broken pipes, doors that jam.",
                    "why": "the radar sees the ground move; a visit tells whether buildings and networks suffer"})
    if any(h.get("trend", {}).get("kind") == "accelerating" for h in sink):
        out.append({"text": "Give priority to the areas where sinking is speeding up ("
                            + ", ".join(h["id"] for h in sink if h.get("trend", {}).get("kind") == "accelerating")
                            + ") and look for a cause: new pumping wells, construction, dewatering, fill.",
                    "why": "a faster rate means the cause is still active or growing"})
    hz = imp["hazard"]
    if hz.get("assessed") and hz["high_km2"] > 0:
        out.append({"text": "Take the high and very high hazard zones into account in building permits, foundation "
                            "design and drainage plans.", "why": f"{hz['high_km2']:.2f} km² rated high or very high"})
    fl = imp["floods"]
    if fl.get("assessed") and fl.get("in_sinking"):
        out.append({"text": "Re-level the drains and street inlets of the flooded streets that also sink; plan their "
                            "drainage for the ground level of 10 years from now.",
                    "why": f"{fl['in_sinking']} reported flood location(s) on sinking ground"})
    ln = imp["lines"]
    if ln.get("assessed") and ln.get("flagged"):
        out.append({"text": "Survey the flagged sections of dykes, railways and roads (crest level, cracks).",
                    "why": f"{ln['flagged']} place(s) settle unevenly beyond 1/500"})
    bd = imp["buildings"]
    if bd.get("assessed") and bd.get("beta_over_1_500"):
        out.append({"text": "Inspect the buildings whose angular distortion reaches 1/500 in 10 years (list in the "
                            "building analysis).", "why": f"{bd['beta_over_1_500']} building(s)"})
    if conf["level"] != "high":
        out.append({"text": "Treat the rates as indicative until the points under 'How sure are we' are cleared; "
                            "check them against levelling or a GNSS station before a decision.",
                    "why": f"confidence {conf['level']}"})
    if a["span_days"] < 365 or a["n_dates"] < 20:
        out.append({"text": "Keep monitoring for at least one full year with images every 12 days or less.",
                    "why": "a longer series separates seasonal swings from lasting sinking"})
    if not imp["gnss"].get("assessed") or not imp["gnss"].get("n"):
        out.append({"text": "Tie the measurements to the ground: compare with a GNSS station or levelling "
                            "benchmarks in the area.", "why": "the rates are relative to a reference area assumed "
                                                              "stable"})
    out.append({"text": "Update this report with each new year of images and compare the indicators "
                        "(indicators.json) from one report to the next.",
                "why": "trends and new hot spots show only in repeated assessments"})
    return out


def field_checks(hot: list[dict], imp: dict, qc_rows: list[dict]) -> list[str]:
    out = [f"{h['id']}: {h['lat']:.5f}° N, {h['lon']:.5f}° E" + (f" ({h['label']})" if h["name"] else "")
           + f", {h['kind']} {_speed(h['rate_mm_yr'])}" for h in hot]
    ln = imp["lines"]
    if ln.get("assessed"):
        out += [f"{x['name'] or 'unnamed'} ({x['kind']}): uneven settlement up to 1/{round(1 / x['beta_max'])} "
                "over the analysis horizon" for x in ln["hotspots"][:4] if x.get("beta_max")]
    out += [f"processing check to look at again: {r['check']} (section B.4.1)" for r in qc_rows
            if r["status"] == "review"]
    return out


INDICATORS: dict[str, tuple[str, str]] = {
    "area_monitored_km2": ("km2", "area holding measurement points (100 m cells with at least one point)"),
    "points_n": ("count", "measurement points (persistent and distributed scatterers)"),
    "points_density_per_km2": ("1/km2", "points per km² of monitored area"),
    "period_first": ("date", "first radar image"),
    "period_last": ("date", "last radar image"),
    "period_days": ("days", "time span of the images"),
    "images_n": ("count", "radar images used"),
    "vel_p01_mm_yr": ("mm/yr", "1st percentile of the point rates (basis: velocity_basis; negative = sinking)"),
    "vel_p05_mm_yr": ("mm/yr", "5th percentile of the point rates"),
    "vel_p50_mm_yr": ("mm/yr", "median point rate, relative to the reference area"),
    "vel_p95_mm_yr": ("mm/yr", "95th percentile of the point rates"),
    "vel_p99_mm_yr": ("mm/yr", "99th percentile of the point rates"),
    "vel_min_mm_yr": ("mm/yr", "lowest point rate (single point, may be noise)"),
    "vel_max_mm_yr": ("mm/yr", "highest point rate (single point, may be noise)"),
    "vel_std_p50_mm_yr": ("mm/yr", "median standard error of the point rates"),
    "sinking_rate_max_mm_yr": ("mm/yr", "fastest sinking of a 100 m cell (median of its points, cells with at "
                                        "least 3 points); negative"),
    **{f"area_sinking_over_{t}_mm_yr_km2": ("km2", f"area of 100 m cells (at least 3 points) sinking faster than "
                                                  f"{t} mm/yr") for t in THRESHOLDS},
    **{f"area_rising_over_{t}_mm_yr_km2": ("km2", f"area of 100 m cells (at least 3 points) rising faster than "
                                                 f"{t} mm/yr") for t in THRESHOLDS},
    "hotspots_sinking_n": ("count", "connected sinking areas faster than the hot-spot threshold (at most 5 listed)"),
    "hotspots_rising_n": ("count", "connected rising areas faster than the hot-spot threshold (at most 2 listed)"),
    "hotspot_threshold_mm_yr": ("mm/yr", "rate threshold of the hot spots: 5 mm/yr or twice the median error"),
    **{f"hazard_{m}_{lv.replace(' ', '_')}_km2": ("km2", f"{m} hazard zoning: area rated {lv}")
       for m in ("subsidence", "landslide") for lv in LEVELS},
    "hazard_accelerating_cells_n": ("count", "hazard cells whose motion is speeding up"),
    "hazard_rain_coupled_cells_n": ("count", "hazard cells whose motion follows the rainfall (significant)"),
    "groundwater_coupled_cells_n": ("count", "hazard cells whose motion follows the GLDAS groundwater storage"),
    "groundwater_storage_trend_mm_yr": ("mm/yr", "trend of the GLDAS groundwater storage (water equivalent)"),
    **{f"motion_{k}_cells_n": ("count", f"hazard cells whose kind of motion is '{k}' ({v})")
       for k, v in MOTION.items()},
    "buildings_with_points_n": ("count", "buildings (Overture footprints) with their own measurement points"),
    **{f"buildings_sinking_over_{t}_mm_yr_n": ("count", f"buildings sinking faster than {t} mm/yr (vertical)")
       for t in THRESHOLDS},
    "buildings_tilt_over_1_500_n": ("count", "buildings whose angular distortion reaches 1/500 in 10 years"),
    "buildings_tilt_over_1_300_n": ("count", "buildings whose angular distortion reaches 1/300 in 10 years"),
    **{f"buildings_risk_{lv.replace(' ', '_')}_n": ("count", f"buildings at {lv} risk (screening)") for lv in LEVELS},
    "lines_km": ("km", "length of dykes, railways and main roads profiled"),
    "lines_flagged_stations_n": ("count", "stations along the lines with uneven settlement beyond 1/500"),
    "flood_reports_n": ("count", "located flood reports inside the area"),
    "flood_reports_in_sinking_n": ("count", "flood reports on ground sinking faster than 5 mm/yr (within 100 m)"),
    "gnss_stations_n": ("count", "GNSS stations compared"),
    "gnss_rate_diff_rms_mm_yr": ("mm/yr", "RMS of the GNSS − InSAR rate differences (line of sight)"),
    "qc_review_n": ("count", "quality checks to look at again"),
    "confidence": ("level", "high / medium / low, from stated rules (not a calibrated uncertainty)"),
}


def indicators(data: dict, asm: dict) -> dict[str, Any]:
    """Every key of ``INDICATORS``, always present: ``value`` None when the analysis behind it was not run."""
    a, ar, imp = data["acquisition"], asm["areas"], asm["impacts"]
    s = asm["stats"]
    v: dict[str, Any] = {
        "area_monitored_km2": data["stats"]["area_km2"], "points_n": data["stats"]["n_points"],
        "points_density_per_km2": data["stats"]["density_per_km2"], "period_first": a["first"],
        "period_last": a["last"], "period_days": a["span_days"], "images_n": a["n_dates"],
        **{f"vel_{k}_mm_yr": s[k] for k in ("p01", "p05", "p50", "p95", "p99")},
        "vel_min_mm_yr": s["min"], "vel_max_mm_yr": s["max"], "vel_std_p50_mm_yr": s["std_p50"],
        "sinking_rate_max_mm_yr": ar["sinking_max_mm_yr"],
        **{f"area_sinking_over_{t}_mm_yr_km2": ar[f"sinking_{t}"] for t in THRESHOLDS},
        **{f"area_rising_over_{t}_mm_yr_km2": ar[f"rising_{t}"] for t in THRESHOLDS},
        "hotspots_sinking_n": sum(h["kind"] == "sinking" for h in asm["hotspots"]),
        "hotspots_rising_n": sum(h["kind"] == "rising" for h in asm["hotspots"]),
        "hotspot_threshold_mm_yr": asm["hot_threshold"],
        "qc_review_n": data["qc_summary"]["review"], "confidence": data["confidence"]["level"],
    }
    source = dict.fromkeys(v, "product")
    hz = imp["hazard"]
    if hz.get("assessed"):
        for m in ("subsidence", "landslide"):
            for lv in LEVELS:
                v[f"hazard_{m}_{lv.replace(' ', '_')}_km2"] = (hz["by_level"].get(m) or {}).get(lv, 0.0)
        v["hazard_accelerating_cells_n"] = hz["accelerating_cells"]
        v["hazard_rain_coupled_cells_n"] = hz["rain_coupled_cells"]
        source |= {k: "hazard" for k in INDICATORS if k.startswith("hazard_")}
    gw = imp["groundwater"]
    if gw.get("assessed"):
        v["groundwater_coupled_cells_n"], v["groundwater_storage_trend_mm_yr"] = gw["cells_coupled"], gw["trend_mm_yr"]
        source |= {k: "hazard (groundwater)" for k in INDICATORS if k.startswith("groundwater_")}
    if imp["behaviour"].get("assessed"):
        for r in imp["behaviour"]["rows"]:
            v[f"motion_{r['kind']}_cells_n"] = r["cells"]
        source |= {k: "behaviour" for k in INDICATORS if k.startswith("motion_")}
    bd = imp["buildings"]
    if bd.get("assessed"):
        if "with_points" in bd:
            v["buildings_with_points_n"] = bd["with_points"]
            v |= {f"buildings_sinking_over_{t}_mm_yr_n": bd["sinking"][f"sinking over {t} mm/yr"] for t in THRESHOLDS}
            dm = list(bd["damage"].values())
            v["buildings_tilt_over_1_500_n"], v["buildings_tilt_over_1_300_n"] = dm[2] + dm[3], dm[3]
            source |= {k: "buildings" for k in v if k.startswith("buildings_")}
        for lv, n in (bd.get("risk") or {}).items():
            v[f"buildings_risk_{lv.replace(' ', '_')}_n"] = n
            source[f"buildings_risk_{lv.replace(' ', '_')}_n"] = "risk"
    if imp["lines"].get("assessed"):
        v["lines_km"], v["lines_flagged_stations_n"] = imp["lines"]["km"], imp["lines"]["flagged"]
        source |= {"lines_km": "lines", "lines_flagged_stations_n": "lines"}
    if imp["floods"].get("assessed"):
        v["flood_reports_n"], v["flood_reports_in_sinking_n"] = imp["floods"]["n"], imp["floods"]["in_sinking"]
        source |= {"flood_reports_n": "floods", "flood_reports_in_sinking_n": "floods"}
    if imp["gnss"].get("assessed"):
        v["gnss_stations_n"], v["gnss_rate_diff_rms_mm_yr"] = imp["gnss"]["n"], imp["gnss"]["rms_mm_yr"]
        source |= {"gnss_stations_n": "gnss", "gnss_rate_diff_rms_mm_yr": "gnss"}
    return {"schema": SCHEMA, "product_id": data["product_id"], "project": data["project"], "track": data["track"],
            "generated": data["generated"], "bbox": data["bbox"], "velocity_basis": asm["basis"],
            "sign": "negative = sinking (or motion away from the satellite with the los basis)",
            "indicators": {k: {"value": v.get(k), "unit": u, "description": d, "source": source.get(k, "not assessed")}
                           for k, (u, d) in INDICATORS.items()}}


# ---------------------------------------------------------------- everything of Part A
def assess(data: dict, pts, product: Path, wide_of) -> dict[str, Any]:
    """Part A of the report. ``wide_of(uids)``: the LOS series (point × date, mm) of those points."""
    from geoeyes.workspace import WorkspaceLayout
    project = product.parent.parent
    ws = WorkspaceLayout.at(project.parent.parent)
    pid, name = product.name, project.name
    an = lambda kind: project / "analyses" / kind / pid                          # noqa: E731
    cmd = lambda kind: f"geoeyes {kind} {name} --product {pid}"                    # noqa: E731

    lon, lat = pts["lon"].to_numpy(float), pts["lat"].to_numpy(float)
    v, sd, basis = rates(pts)
    q = lambda p: round(float(np.nanpercentile(v, p)), 2)                         # noqa: E731
    st = {"p01": q(1), "p05": q(5), "p50": q(50), "p95": q(95), "p99": q(99), "min": round(float(np.nanmin(v)), 2),
          "max": round(float(np.nanmax(v)), 2),
          "std_p50": round(float(np.nanmedian(sd)), 2) if np.isfinite(sd).any() else None}
    cells, inv = grid(lon, lat, v)
    ar = areas(cells)
    threshold = round(max(HOT_RATE, 2 * (st["std_p50"] or 0)), 1)
    hot = hotspots(cells, inv, lon, lat, v, threshold)

    # flood inventory: the located rows inside the product (a margin of NEAR_M)
    from geoeyes.ancillary.flood_reports import collection, folder
    inventory = folder(ws).exists() and any(folder(ws).glob("*.geojson"))
    pad = NEAR_M / M_LAT
    w, s, e, n = lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad
    feats = [f for f in (collection(ws)["features"] if inventory else []) if f.get("geometry")
             and w <= _anchor(f["geometry"])[0] <= e and s <= _anchor(f["geometry"])[1] <= n]

    centre = _places(ws, float(np.median(lon)), float(np.median(lat)))
    namer = Namer(an("lines") if (an("lines") / "lines.parquet").exists() else None, feats)
    scale = np.ones(len(pts))
    if basis == "vertical":
        lu = pts["los_u"].to_numpy(float)
        scale = np.where(np.abs(lu) > 0.3, 1 / np.where(lu == 0, 1, lu), np.nan)
    uid = pts["point_uid"].to_numpy()
    samples = [sample_points(h, i) for i, h in enumerate(hot)]
    wide = wide_of(uid[np.concatenate(samples)]) if hot else None             # one read for every hot spot
    for h, p in zip(hot, samples, strict=True):
        h["dates"], h["median_mm"], h["iqr_mm"] = series(uid[p], scale[p], wide)
        h["trend"] = tr = trend(h["dates"], h["median_mm"])
        if tr.get("outliers") and abs(tr.get("rate_mm_yr", h["rate_mm_yr"]) - h["rate_mm_yr"]) > max(
                3.0, 0.3 * abs(h["rate_mm_yr"])):
            tr["text"] += (f". The rate of its points ({_mm(h['rate_mm_yr'])} mm/yr) rests on those dates: "
                           "check them")
        h["median_mm"] = np.round(h["median_mm"], 2).tolist()
        h["iqr_mm"] = np.round(h["iqr_mm"], 2).tolist()
        place = _places(ws, h["lon"], h["lat"])
        h["name"] = namer(h["lon"], h["lat"])
        h["place"] = place if place and place != centre else ""
        h["label"] = ", ".join(x for x in (h["name"], h["place"]) if x) or f"{h['lat']:.4f}° N, {h['lon']:.4f}° E"
        del h["_points"], h["score"]

    hz = hazard(an("hazard"), cmd("hazard"))
    imp = {"hazard": hz, "behaviour": behaviour(an("behaviour"), cmd("behaviour")),
           "buildings": buildings(an("buildings"), an("risk"), cmd("buildings"), cmd("risk")),
           "lines": lines(an("lines"), cmd("lines")),
           "floods": floods(feats, inventory, lon, lat, v, "geoeyes floods import <list.txt> --region <region>, "
                                                           "then geoeyes floods locate --region <region>"),
           "groundwater": groundwater(hz, cmd("hazard")), "gnss": gnss(an("gnss"), cmd("gnss"))}
    hz.pop("groundwater", None)
    where = centre.split(",")[0] if centre else f"The {data['project']} area"
    out = {"basis": basis, "place": centre, "stats": st, "areas": ar, "hot_threshold": threshold, "hotspots": hot,
           "impacts": imp,
           "statements": statements(where, data["acquisition"], data["stats"], ar, hot, data["confidence"], basis)}
    out["recommendations"] = recommendations(hot, imp, data["confidence"], data["acquisition"])
    out["field_checks"] = field_checks(hot, imp, data["qc"])
    # a date off the trend in most hot spots is more likely an error of that image than motion of the ground
    off = [x for h in hot for x in h["trend"].get("outliers", [])]
    out["suspect_dates"] = sorted({x for x in off if off.count(x) >= max(2, len(hot) / 2)})
    return out
