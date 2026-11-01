"""Today's flood outlook at the reported flood locations: forecast rain (Open-Meteo, hourly, per location), the tide
(Open-Meteo Marine sea level off the river mouth, a model, not a gauge) and, with a product, the ground's subsidence
around the location (InSAR). A reference, not a flood forecast: no hydraulic model, no drainage, no gauge.

Score (0-100), transparent on purpose:

    rain  R = (0.5 min(rain_24h / 50 mm, 1) + 0.5 min(max_hourly / 25 mm, 1)) x (0.5 + 0.5 max_probability)
    tide  T = (peak - median daily high of the last 30 days) / (highest of the 30 days and forecast - that median),
              clipped to 0..1: 0 for an ordinary tide, 1 for the highest of the month (spring tide)
    score = 100 (w_R R + w_T T) + subsidence bonus      w = 0.8 / 0.2 (rain spot), 0.2 / 0.8 (tide), 0.5 / 0.5
    subsidence bonus: median LOS velocity around the location <= -5 / -10 / -20 mm/yr -> +3 / +6 / +10; for the
    city, the median over its reported flood locations covered by the product (at least 3)

Levels: < 20 low, < 45 watch, < 70 high, else very high; the depth class follows the level (unlikely, < 20 cm,
20-40 cm, > 40 cm) and says no more than that. The risk window spans the hours of the next 24 with rain (>= 2 mm and
>= 40 % probability) or a tide in the upper 40 % of the month's range, whichever counts for the location's cause.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import numpy as np

log = logging.getLogger(__name__)

FORECAST = "https://api.open-meteo.com/v1/forecast"
MARINE = "https://marine-api.open-meteo.com/v1/marine"
TZ = "Asia/Bangkok"
# the sea off the river mouth (a marine model cell; the city's river levels follow it with a lag of a few hours)
TIDE_POINT = {"hcmc": (107.08, 10.33)}
CENTRE = {"hcmc": (106.70, 10.78), "hanoi": (105.83, 21.03)}
NAME = {"hcmc": "Ho Chi Minh City", "hanoi": "Hanoi"}
TTL_S = 1800
GRID_DEG = 0.05                    # locations closer than this share one forecast (the model's cells are ~ 2-10 km)

WEIGHTS = {"rain": (0.8, 0.2), "tide": (0.2, 0.8), "rain_tide": (0.5, 0.5), "": (0.5, 0.5), "rain_only": (1.0, 0.0)}
LEVELS = ((20, "low"), (45, "watch"), (70, "high"), (101, "very_high"))
DEPTH = {"low": "unlikely", "watch": "lt20", "high": "20_40", "very_high": "gt40"}

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _get(url: str, params: dict, timeout: float = 30):
    key = url + "?" + urllib.parse.urlencode(params)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL_S:
            return hit[1]
    req = urllib.request.Request(key, headers={"User-Agent": "GeoEyes/1.0 (flood outlook)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        js = json.loads(resp.read().decode("utf-8"))
    with _lock:
        _cache[key] = (time.time(), js)
    return js


def rain(points: list[tuple[float, float]], days: int = 2) -> list[dict]:
    """Hourly rain (mm) and probability (%) at each (lon, lat), from the current hour on; one request for all."""
    cells = sorted({(round(lo / GRID_DEG) * GRID_DEG, round(la / GRID_DEG) * GRID_DEG) for lo, la in points})
    out: dict[tuple[float, float], dict] = {}
    for i in range(0, len(cells), 100):                    # the API takes a list of coordinates
        part = cells[i:i + 100]
        js = _get(FORECAST, {"latitude": ",".join(f"{la:.3f}" for _, la in part),
                             "longitude": ",".join(f"{lo:.3f}" for lo, _ in part),
                             "hourly": "precipitation,precipitation_probability", "forecast_days": days,
                             "timezone": TZ})
        for c, d in zip(part, js if isinstance(js, list) else [js], strict=True):
            h = d["hourly"]
            out[c] = {"time": h["time"], "mm": h["precipitation"], "prob": h["precipitation_probability"]}
    return [out[(round(lo / GRID_DEG) * GRID_DEG, round(la / GRID_DEG) * GRID_DEG)] for lo, la in points]


def tide(region: str = "hcmc") -> dict:
    """Hourly sea level (m, model, mean sea level datum) of the last 30 days and the next 3, with the month's scale."""
    lon, lat = TIDE_POINT[region]
    js = _get(MARINE, {"latitude": lat, "longitude": lon, "hourly": "sea_level_height_msl", "past_days": 30,
                       "forecast_days": 3, "timezone": TZ})
    t, v = js["hourly"]["time"], js["hourly"]["sea_level_height_msl"]
    lv = np.array([np.nan if x is None else x for x in v], dtype=float)
    days: dict[str, float] = {}
    for ti, x in zip(t, lv, strict=True):
        if np.isfinite(x):
            days[ti[:10]] = max(days.get(ti[:10], -np.inf), x)
    highs = np.array(list(days.values()))
    return {"time": t, "level": [None if not np.isfinite(x) else round(float(x), 3) for x in lv],
            "median_daily_high": round(float(np.median(highs)), 3), "highest": round(float(np.nanmax(lv)), 3),
            "point": [lon, lat], "source": "Open-Meteo Marine (sea level, model)"}


def _window(times: list[str], now: datetime, hours: int = 24) -> list[int]:
    t0 = now.replace(minute=0, second=0, microsecond=0)
    t1 = t0 + timedelta(hours=hours)
    return [i for i, s in enumerate(times) if t0 <= datetime.fromisoformat(s) < t1]


def assess(r: dict, td: dict | None, cause: str, now: datetime, velocity: float | None = None) -> dict:
    """The outlook of one location (``r``: its hourly rain, ``td``: the tide, None where there is none: rain only)
    over the next 24 hours."""
    ir = _window(r["time"], now)
    mm = np.array([r["mm"][i] or 0.0 for i in ir], dtype=float)
    prob = np.array([r["prob"][i] or 0.0 for i in ir], dtype=float)
    if td is None:                                    # an inland city (Hanoi): rain only
        td, cause = {"time": [], "level": [], "median_daily_high": 0.0, "highest": 0.0}, "rain_only"
    it = _window(td["time"], now)
    lv = np.array([np.nan if td["level"][i] is None else td["level"][i] for i in it], dtype=float)
    rain_24h, rain_max = float(mm.sum()), float(mm.max(initial=0.0))
    prob_max = float(prob.max(initial=0.0))
    R = (0.5 * min(rain_24h / 50.0, 1.0) + 0.5 * min(rain_max / 25.0, 1.0)) * (0.5 + 0.5 * prob_max / 100.0)
    lo, hi = td["median_daily_high"], max(td["highest"], td["median_daily_high"] + 0.1)
    k = int(np.nanargmax(lv)) if np.isfinite(lv).any() else None
    peak = float(lv[k]) if k is not None else None
    T = 0.0 if peak is None else float(np.clip((peak - lo) / (hi - lo), 0.0, 1.0))
    w_r, w_t = WEIGHTS.get(cause, WEIGHTS[""])
    bonus = 0
    if velocity is not None and np.isfinite(velocity):
        bonus = 10 if velocity <= -20 else 6 if velocity <= -10 else 3 if velocity <= -5 else 0
    score = int(round(min(100.0, 100.0 * (w_r * R + w_t * T) + bonus)))
    level = next(name for limit, name in LEVELS if score < limit)
    # hours that count for this location's cause
    hot = []
    if w_r >= 0.5:
        hot += [r["time"][i] for i, a, p in zip(ir, mm, prob, strict=True) if a >= 2.0 and p >= 40]
    if w_t >= 0.5:
        hot += [td["time"][i] for i, x in zip(it, lv, strict=True) if np.isfinite(x) and x >= lo + 0.6 * (hi - lo)]
    hot.sort()
    return {"score": score, "level": level, "depth": DEPTH[level],
            "window": [hot[0], hot[-1]] if hot else None,
            "rain_24h_mm": round(rain_24h, 1), "rain_max_mm_h": round(rain_max, 1), "rain_prob_max": round(prob_max),
            "tide_peak_m": None if peak is None else round(peak, 2),
            "tide_peak_time": None if k is None else td["time"][it[k]],
            "parts": {"rain": round(R, 2), "tide": round(T, 2), "w_rain": w_r, "w_tide": w_t,
                      "subsidence_bonus": bonus},
            "velocity_mm_yr": None if velocity is None else round(float(velocity), 1),
            "hours": {"time": [r["time"][i] for i in ir], "mm": [round(float(a), 1) for a in mm],
                      "prob": [int(p) for p in prob]}}


def _anchor(geom: dict) -> tuple[float, float]:
    c = geom["coordinates"]
    if geom["type"] == "Point":
        return float(c[0]), float(c[1])
    pts = np.asarray(c if geom["type"] == "LineString" else [p for ln in c for p in ln], dtype=float)
    return tuple(pts[len(pts) // 2])


def outlook(fc: dict, stats: dict | None = None, now: datetime | None = None) -> dict:
    """The outlook of every located row of ``fc`` and of each region's centre; ``stats``: ``near_product``."""
    now = now or datetime.now()                       # the forecasts are in local time (TZ)
    feats = [f for f in fc.get("features", []) if f.get("geometry") and f["properties"].get("region") in CENTRE]
    regions = sorted({f["properties"]["region"] for f in feats})
    tides = {g: tide(g) if g in TIDE_POINT else None for g in regions}
    pts = [CENTRE[g] for g in regions] + [_anchor(f["geometry"]) for f in feats]
    rains = rain(pts) if pts else []
    srow = (stats or {}).get("rows", {})
    rows = {}
    for f, r in zip(feats, rains[len(regions):], strict=True):
        p = f["properties"]
        rows[f["id"]] = assess(r, tides[p["region"]], p.get("cause", ""), now, srow.get(f["id"], {}).get("vel_median"))
    areas = {}
    for g, r in zip(regions, rains[:len(regions)], strict=True):
        td = tides[g]
        it = _window(td["time"], now, 24) if td else []
        # the city's subsidence: median velocity at its reported flood locations the product covers (>= 3)
        vel = [srow[f["id"]]["vel_median"] for f in feats if f["properties"]["region"] == g
               and srow.get(f["id"], {}).get("vel_median") is not None and np.isfinite(srow[f["id"]]["vel_median"])]
        v_city = float(np.median(vel)) if len(vel) >= 3 else None
        areas[g] = {"name": NAME.get(g, g), "centre": list(CENTRE[g]),
                    "city": assess(r, td, "rain_tide" if td else "rain_only", now, v_city),
                    "subsidence": {"locations": len(vel), "sinking_over_5": int(sum(v <= -5 for v in vel)),
                                   "median_mm_yr": None if v_city is None else round(v_city, 1)},
                    "tide": None if td is None else {
                        "time": [td["time"][i] for i in it], "level": [td["level"][i] for i in it],
                        "median_daily_high": td["median_daily_high"], "highest": td["highest"],
                        "point": td["point"], "source": td["source"]}}
    return {"generated": now.isoformat(timespec="minutes"), "areas": areas, "rows": rows,
            "sources": {"rain": "Open-Meteo forecast (best model mix)", "tide": "Open-Meteo Marine (sea level, model)"}}


__all__ = ["assess", "outlook", "rain", "tide"]
