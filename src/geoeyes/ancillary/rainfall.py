"""Monthly rainfall over an AOI from CHIRPS v3 (Climate Hazards Center, 0.05°, global land), read from the
cloud-optimized GeoTIFFs over HTTP (only the AOI window), cached per AOI under ``<workspace>/cache/rainfall``.

Rainfall helps reading seasonal motion (clay swelling / shrinking, groundwater recharge) against the time series.
CHIRPS is published about a month after the month ends; later months are simply absent.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/monthly/global/cogs/chirps-v3.0.{y}.{m:02d}.cog"
SOURCE = "CHIRPS v3.0 monthly (Climate Hazards Center, UC Santa Barbara)"


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _read_month(y: int, m: int, bbox: list[float]) -> float | None:
    """Mean monthly rainfall (mm) over the bbox (at least the pixel holding its centre)."""
    import rasterio
    from rasterio.windows import from_bounds
    w, s, e, n = bbox
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".cog",
           "GDAL_HTTP_TIMEOUT": "60"}
    try:
        with rasterio.Env(**env), rasterio.open(f"/vsicurl/{URL.format(y=y, m=m)}") as src:
            px = src.res[0]
            cx, cy = (w + e) / 2, (s + n) / 2
            w, e = min(w, cx - px / 2), max(e, cx + px / 2)          # never smaller than one pixel
            s, n = min(s, cy - px / 2), max(n, cy + px / 2)
            win = from_bounds(w, s, e, n, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win, masked=True).astype(np.float64)
            a = np.ma.masked_less(a, 0)                               # -9999: ocean / no data
            return None if a.count() == 0 else round(float(a.mean()), 1)
    except Exception as exc:                                         # a month not published yet, or no network
        log.debug("CHIRPS %d-%02d unavailable: %s", y, m, exc)
        return None


def monthly(cache: Path, bbox: list[float], start: date, end: date) -> dict:
    """``{"source", "bbox", "months": [{"month": "YYYY-MM", "mm": value or None}]}``; published months are cached
    for good, missing recent ones are asked again next time."""
    cache.mkdir(parents=True, exist_ok=True)
    key = "_".join(f"{v:.3f}" for v in bbox)
    f = cache / f"chirps3_{key}.json"
    known: dict[str, float] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    out = []
    changed = False
    for y, m in _months(start, end):
        k = f"{y}-{m:02d}"
        if k not in known:
            v = _read_month(y, m, bbox)
            if v is not None:
                known[k] = v
                changed = True
        out.append({"month": k, "mm": known.get(k)})
    if changed:
        f.write_text(json.dumps(known, indent=0), encoding="utf-8")
    return {"source": SOURCE, "bbox": bbox, "months": out}
