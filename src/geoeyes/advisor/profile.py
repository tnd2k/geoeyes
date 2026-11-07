"""Site profile (site advisor, step V1): measured properties of an area that decide how to process it.

    terrain     relief (p5–p95 of the height), slope median / p90, share of slopes > 20° and > 35°
                (the project DEM, default Copernicus GLO-30, on cells of ``cell_m``; ``geoeyes.ml.layers.terrain``)
    land_cover  shares of built-up, tree, crop, grass, bare, water, wetland (ESA WorldCover 10 m 2021)
    geology     shares of the GLiM lithology classes; ``soft_share`` = unconsolidated sediments ("su")
    climate     10-year monthly climatology of rain, temperature and humidity at the centre (ERA5 through the
                Open-Meteo archive API, one request) and its Köppen-Geiger class (computed, Peel et al. 2007)
    data        per track of a project: dates, span, revisit, gaps, B⊥ spread, coherence, band (the stack QC);
                without a stack, what the configuration asks for

Every part is read on its own: one that fails is named in ``errors`` and the others are kept. Terrain, land cover
and geology are cached per AOI and DEM under ``<cache>/advisor/``, the climate as its raw ERA5 request (the
statistics and the class are computed again); ``data`` is read again each time (it changes as stacks grow).
No language model is involved.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.site_profile/1"
SITE_PARTS = ("terrain", "land_cover", "geology", "climate")
PARTS = (*SITE_PARTS, "data")
CACHED_PARTS = ("terrain", "land_cover", "geology")    # the climate keeps its raw ERA5 request; classes recomputed
CELL_M = 30.0
MAX_CELLS = 2_500_000                       # larger AOIs get coarser cells
STEEP_DEG, VERY_STEEP_DEG = 20.0, 35.0
CLIMATE_YEARS = 10
OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_SOURCE = "ERA5 reanalysis (ECMWF / Copernicus), via the Open-Meteo archive API"
BANDS = ((0.15, "L"), (0.045, "C"), (0.0, "X"))          # wavelength (m) lower bound -> band
GLIM_SOFT = "su"


# ---------------------------------------------------------------- helpers
def area_km2(bbox: list[float]) -> float:
    w, s, e, n = bbox
    lat0 = math.radians((s + n) / 2)
    return abs(e - w) * 111.32 * math.cos(lat0) * abs(n - s) * 110.54


def _grid(bbox: list[float], cell_m: float):
    from geoeyes.ml.layers import Grid
    cell = cell_m
    while area_km2(bbox) * 1e6 / cell ** 2 > MAX_CELLS:
        cell *= 1.5
    return Grid(list(bbox), round(cell, 1), (bbox[1] + bbox[3]) / 2)


def _r(x, nd: int = 3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def band_of(wavelength_m: float | None) -> str | None:
    if not wavelength_m:
        return None
    return next(b for lim, b in BANDS if wavelength_m >= lim)


# ---------------------------------------------------------------- parts
def terrain_part(grid, dem_source: str, dem_cache: Path) -> dict:
    from geoeyes.ml.layers import terrain
    t = terrain(grid, dem_source, dem_cache)
    h, sl = t["height_m"].astype(float), t["slope_deg"].astype(float)
    h, sl = h[np.isfinite(h)], sl[np.isfinite(sl)]
    if not h.size:
        raise ValueError("the DEM has no value over the AOI")
    p5, p50, p95 = np.percentile(h, [5, 50, 95])
    return {"source": dem_source, "cell_m": grid.cell_m, "height_p5_m": _r(p5, 1), "height_median_m": _r(p50, 1),
            "height_p95_m": _r(p95, 1), "relief_m": _r(p95 - p5, 1),
            "slope_median_deg": _r(np.median(sl), 1), "slope_p90_deg": _r(np.percentile(sl, 90), 1),
            "steep_share": _r(np.mean(sl > STEEP_DEG)), "very_steep_share": _r(np.mean(sl > VERY_STEEP_DEG))}


def land_cover_part(grid) -> dict:
    from geoeyes.ml.layers import worldcover
    lc = worldcover(grid)
    shares = {}
    for k, v in lc.items():
        if k.startswith("lc_"):
            v = v[np.isfinite(v)]
            shares[k[3:]] = _r(v.mean()) if v.size else None
    known = {k: v for k, v in shares.items() if v is not None}
    if not known:
        raise ValueError("WorldCover has no value over the AOI")
    return {"source": "ESA WorldCover 10 m 2021 v200", "shares": shares, "dominant": max(known, key=known.get)}


def geology_part(grid, glim_zip: Path) -> dict:
    from geoeyes.landslide.predictors import GLIM_CLASSES, lithology
    if not glim_zip.exists():
        raise FileNotFoundError(f"GLiM not in the cache ({glim_zip}); `geoeyes landslide` downloads it")
    _, frac = lithology(grid, glim_zip)
    frac = {k: _r(v) for k, v in sorted(frac.items(), key=lambda kv: -kv[1])}
    land = {k: v for k, v in frac.items() if k not in ("nd", "wb")}
    return {"source": "GLiM (Hartmann & Moosdorf 2012)", "shares": frac,
            "names": {k: GLIM_CLASSES.get(k, k) for k in frac},
            "dominant": next(iter(land), None), "soft_share": frac.get(GLIM_SOFT, 0.0)}


def _climate_request(lat: float, lon: float, y0: int, y1: int, cache: Path) -> dict:
    import urllib.parse
    import urllib.request
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"climate_{lat:.2f}_{lon:.2f}_{y0}_{y1}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    q = urllib.parse.urlencode({"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}", "start_date": f"{y0}-01-01",
                                "end_date": f"{y1}-12-31", "models": "era5", "timezone": "UTC",
                                "daily": "precipitation_sum,temperature_2m_mean,relative_humidity_2m_mean"})
    req = urllib.request.Request(f"{OPEN_METEO}?{q}", headers={"User-Agent": "GeoEyes (InSAR site profile)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    f.write_text(json.dumps(data), encoding="utf-8")
    return data


def monthly_climatology(daily: dict) -> dict[str, list[float]]:
    """Mean monthly rain (mm, the sum of each month averaged over the years), temperature (°C) and relative
    humidity (%) from daily series ``{"time", "precipitation_sum", "temperature_2m_mean", ...}``."""
    import pandas as pd
    idx = pd.to_datetime(daily["time"])
    out = {}
    for key, name, how in (("precipitation_sum", "rain_mm", "sum"), ("temperature_2m_mean", "temp_c", "mean"),
                           ("relative_humidity_2m_mean", "rh_pct", "mean")):
        if key not in daily:
            continue
        s = pd.Series(daily[key], index=idx, dtype=float)
        m = s.resample("MS").sum(min_count=25) if how == "sum" else s.resample("MS").mean()
        out[name] = [float(m[m.index.month == k].mean()) for k in range(1, 13)]
    return out


def koppen(temp_c: list[float], rain_mm: list[float], lat: float) -> str:
    """Köppen-Geiger class from a monthly climatology (Peel, Finlayson & McMahon 2007)."""
    t, p = np.asarray(temp_c, float), np.asarray(rain_mm, float)
    mat, map_ = t.mean(), p.sum()
    thot, tcold = t.max(), t.min()
    summer = np.zeros(12, bool)
    summer[3:9] = True                                      # April–September
    if lat < 0:
        summer = ~summer
    ps, pw = p[summer], p[~summer]
    if ps.sum() >= 0.7 * map_:
        pth = 2 * mat + 14
    elif pw.sum() >= 0.7 * map_:
        pth = 2 * mat
    else:
        pth = 2 * mat + 7
    if thot < 10:
        return "ET" if thot > 0 else "EF"
    if map_ < 10 * pth:
        return ("BW" if map_ < 5 * pth else "BS") + ("h" if mat >= 18 else "k")
    if tcold >= 18:
        pdry = p.min()
        if pdry >= 60:
            return "Af"
        return "Am" if pdry >= 100 - map_ / 25 else "Aw"
    main = "C" if tcold > 0 else "D"
    dry_summer = ps.min() < 40 and ps.min() < pw.max() / 3
    dry_winter = pw.min() < ps.max() / 10
    if dry_summer and dry_winter:                   # both hold (monsoon highlands): the wetter half decides
        second = "w" if ps.sum() >= pw.sum() else "s"
    else:
        second = "s" if dry_summer else "w" if dry_winter else "f"
    warm = int((t >= 10).sum())
    if thot >= 22:
        third = "a"
    elif warm >= 4:
        third = "b"
    elif main == "D" and tcold < -38:
        third = "d"
    else:
        third = "c"
    return main + second + third


def climate_part(bbox: list[float], cache: Path, today: date | None = None) -> dict:
    w, s, e, n = bbox
    lat, lon = (s + n) / 2, (w + e) / 2
    y1 = (today or date.today()).year - 1
    y0 = y1 - CLIMATE_YEARS + 1
    data = _climate_request(lat, lon, y0, y1, cache)
    c = monthly_climatology(data["daily"])
    rain, temp = c["rain_mm"], c["temp_c"]
    wet = [m + 1 for m, v in enumerate(rain) if v >= 100]
    return {"source": CLIMATE_SOURCE, "years": [y0, y1], "point": [round(lon, 2), round(lat, 2)],
            "koppen": koppen(temp, rain, lat), "rain_annual_mm": _r(sum(rain), 0),
            "wettest_month": int(np.argmax(rain)) + 1, "wet_months": wet,
            "temp_mean_c": _r(np.mean(temp), 1), "rh_mean_pct": _r(np.mean(c["rh_pct"]), 0) if "rh_pct" in c else None,
            "monthly": {k: [round(v, 1) for v in vals] for k, vals in c.items()}}


def data_part(project, cfg) -> dict:
    """Per track: from the stack QC when the stack exists, else from the configuration."""
    tracks = {}
    for qc_file in sorted(project.root.glob("stacks/*/qc/qc.json")):
        try:
            qc = json.loads(qc_file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rows = qc.get("dates") or []
        dates = sorted(date.fromisoformat(r["date"]) for r in rows)
        if not dates:
            continue
        gaps = np.diff([d.toordinal() for d in dates]) if len(dates) > 1 else np.array([0])
        bp = np.array([r.get("bperp_m", np.nan) for r in rows], float)
        coh = np.array([r.get("coherence_mean", np.nan) for r in rows if not r.get("reference")], float)
        hoa = np.array([abs(r.get("height_of_ambiguity_m", np.nan)) for r in rows if not r.get("reference")], float)
        attrs = {}
        zj = qc_file.parents[1] / "stack.zarr" / "zarr.json"
        if zj.exists():
            with contextlib.suppress(ValueError):
                attrs = json.loads(zj.read_text(encoding="utf-8")).get("attributes", {})
        wl = attrs.get("wavelength_m")
        key = attrs.get("track") or qc.get("stack", qc_file.parents[1].name)
        tracks[key] = {
            "source": "stack QC", "stack": qc.get("stack", qc_file.parents[1].name),
            "sensor": attrs.get("sensor"), "band": band_of(wl), "wavelength_m": wl,
            "dates": len(dates), "first": dates[0].isoformat(), "last": dates[-1].isoformat(),
            "span_years": _r((dates[-1] - dates[0]).days / 365.25, 2),
            "revisit_median_days": _r(np.median(gaps), 0), "max_gap_days": int(gaps.max()),
            "reference": qc.get("reference_date"),
            "bperp_spread_m": _r(np.nanpercentile(bp, 95) - np.nanpercentile(bp, 5), 0) if np.isfinite(bp).any()
            else None,
            "coherence_median": _r(np.nanmedian(coh)) if np.isfinite(coh).any() else None,
            "height_of_ambiguity_median_m": _r(np.nanmedian(hoa), 0) if np.isfinite(hoa).any() else None}
        if np.isfinite(coh).any() and np.nanmin(coh) >= 0.999:
            tracks[key]["warning"] = ("stack QC coherence is 1.0 for every date: not a real value (run "
                                      "`geoeyes stack-qc` again)")
    if tracks:
        return {"tracks": tracks}
    out = {}
    for tr in cfg.tracks:
        dr = cfg.acquire.date_range
        out[tr.track_id] = {"source": "configuration (no stack yet)", "sensor": str(tr.sensor),
                            "first": dr[0].isoformat() if dr else None, "last": dr[1].isoformat() if dr else None,
                            "max_per_month": cfg.acquire.max_per_month}
    return {"tracks": out}


# ---------------------------------------------------------------- profile
def _key(bbox: list[float], dem: str, cell_m: float) -> str:
    raw = f"{[round(v, 5) for v in bbox]}|{dem}|{cell_m}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def profile(bbox: list[float], *, cache_root: Path, dem: str = "copernicus-30", project=None, cfg=None,
            parts: tuple[str, ...] = PARTS, cell_m: float = CELL_M, refresh: bool = False, progress=None) -> dict:
    """Profile of the AOI ``bbox`` (west, south, east, north). ``project`` / ``cfg`` (a ProjectLayout and its
    configuration) add the ``data`` part. Parts that cannot be read are listed in ``errors``."""
    say = progress or log.info
    bbox = [float(v) for v in bbox]
    folder = cache_root / "advisor"
    folder.mkdir(parents=True, exist_ok=True)
    cf = folder / f"site_{_key(bbox, dem, cell_m)}.json"
    cached = {}
    if cf.exists() and not refresh:
        try:
            cached = json.loads(cf.read_text(encoding="utf-8"))
        except ValueError:
            cached = {}
    out = {"schema": SCHEMA, "bbox": bbox, "area_km2": _r(area_km2(bbox), 1),
           "centre": [round((bbox[0] + bbox[2]) / 2, 5), round((bbox[1] + bbox[3]) / 2, 5)],
           "created": datetime.now(UTC).isoformat(timespec="seconds"), "errors": {}}
    grid = None
    for part in SITE_PARTS:
        if part not in parts:
            continue
        if part in cached and part in CACHED_PARTS:
            out[part] = cached[part]
            continue
        say(f"site profile: {part}")
        try:
            if part == "climate":
                out[part] = climate_part(bbox, folder)
            else:
                grid = grid or _grid(bbox, cell_m)
                if part == "terrain":
                    out[part] = terrain_part(grid, dem, cache_root / "dem")
                elif part == "land_cover":
                    out[part] = land_cover_part(grid)
                else:
                    from geoeyes.landslide.predictors import GLIM_ZIP
                    out[part] = geology_part(grid, cache_root / GLIM_ZIP)
        except Exception as exc:
            log.warning("site profile: %s not read: %s", part, exc)
            out["errors"][part] = f"{type(exc).__name__}: {exc}"
    keep = {p: out[p] for p in CACHED_PARTS if p in out}
    if keep and keep != {p: cached.get(p) for p in keep}:
        cf.write_text(json.dumps({**cached, **keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    if "data" in parts and project is not None and cfg is not None:
        try:
            out["data"] = data_part(project, cfg)
        except Exception as exc:
            out["errors"]["data"] = f"{type(exc).__name__}: {exc}"
    return out


def summary(p: dict, lang: str = "en") -> str:
    """A few lines of plain text (the CLI)."""
    vi = lang == "vi"
    lines = [f"AOI {p['bbox']}  ({p['area_km2']} km²)"]
    t = p.get("terrain")
    if t:
        lines.append((f"  Địa hình: chênh cao {t['relief_m']} m (p5–p95), dốc trung vị {t['slope_median_deg']}°, "
                      f"dốc > 20°: {t['steep_share']:.0%}  [{t['source']}]") if vi else
                     (f"  Terrain: relief {t['relief_m']} m (p5–p95), median slope {t['slope_median_deg']}°, "
                      f"slopes > 20°: {t['steep_share']:.0%}  [{t['source']}]"))
    lc = p.get("land_cover")
    if lc:
        top = sorted(((k, v) for k, v in lc["shares"].items() if v), key=lambda kv: -kv[1])[:4]
        lines.append(("  Lớp phủ: " if vi else "  Land cover: ") + ", ".join(f"{k} {v:.0%}" for k, v in top))
    g = p.get("geology")
    if g:
        top = list(g["shares"].items())[:3]
        lines.append(("  Địa chất: " if vi else "  Geology: ")
                     + ", ".join(f"{g['names'].get(k, k)} {v:.0%}" for k, v in top)
                     + (f"; trầm tích bở rời {g['soft_share']:.0%}" if vi
                        else f"; soft sediments {g['soft_share']:.0%}"))
    c = p.get("climate")
    if c:
        wet = ",".join(str(m) for m in c["wet_months"]) or "-"
        lines.append((f"  Khí hậu: Köppen {c['koppen']}, mưa {c['rain_annual_mm']:.0f} mm/năm, tháng mưa (≥ 100 mm) "
                      f"{wet}, độ ẩm {c['rh_mean_pct']} %  [{c['years'][0]}–{c['years'][1]}]") if vi else
                     (f"  Climate: Köppen {c['koppen']}, rain {c['rain_annual_mm']:.0f} mm/yr, wet months (≥ 100 mm) "
                      f"{wet}, humidity {c['rh_mean_pct']} %  [{c['years'][0]}–{c['years'][1]}]"))
    for tid, d in ((p.get("data") or {}).get("tracks") or {}).items():
        if "dates" in d:
            lines.append((f"  Dữ liệu {tid}: {d['dates']} ảnh {d['first']}..{d['last']} ({d['span_years']} năm), "
                          f"chu kỳ {d['revisit_median_days']} ngày, khoảng trống lớn nhất {d['max_gap_days']} ngày, "
                          f"B⊥ trải {d['bperp_spread_m']} m, độ nhất quán {d['coherence_median']}, băng {d['band']}")
                         if vi else
                         (f"  Data {tid}: {d['dates']} dates {d['first']}..{d['last']} ({d['span_years']} yr), revisit "
                          f"{d['revisit_median_days']} d, largest gap {d['max_gap_days']} d, B⊥ spread "
                          f"{d['bperp_spread_m']} m, coherence {d['coherence_median']}, band {d['band']}"))
        else:
            lines.append(f"  {'Dữ liệu' if vi else 'Data'} {tid}: {d['source']}, {d['first']}..{d['last']}")
        if d.get("warning"):
            lines.append(f"  ! {tid}: {d['warning']}")
    for part, msg in p.get("errors", {}).items():
        lines.append(f"  ! {part}: {msg}")
    return "\n".join(lines)
