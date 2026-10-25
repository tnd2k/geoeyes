"""Point layers for the map: a product's points and time series in a form the browser and the API read fast.

The product files stay the reference; the first request for a product writes a cache under
``<workspace>/cache/web/<product_id>/`` (rebuilt when ``points.parquet`` is newer):

    meta.json        n, origin, bounds, dates, velocity classes (QGIS Pretty Breaks, jet_r)
    points.bin       float32 x 3 per point: lon - lon0, lat - lat0, velocity (mm/yr), in product order
    attrs.npz        per-point attributes shown on click (velocity std, coherence, height, ...)
    ts.npy           float32 (points, dates) displacement, zero at each point's first date, in product order
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from geoeyes.core.errors import StoreError
from geoeyes.export.styles import CLASSES, jet_r, marker_size_m, pretty_breaks
from geoeyes.io.points import timeseries_arrays
from geoeyes.products.builder import zero_reference

CACHE_VERSION = 5                 # /5: series zero at the first date (products before geoeyes-product/3 too)
ATTRS = ("vel_std_mm_yr", "temporal_coherence", "height_m", "acc_los_mm_yr2", "seasonal_amp_mm", "dem_err_m")
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def classes(vel: np.ndarray) -> list[dict]:
    """Velocity classes as in QGIS and the report: Pretty Breaks over min-max, jet_r colours."""
    v = vel[np.isfinite(vel)]
    lo, hi = float(v.min()), float(v.max())
    uppers = pretty_breaks(lo, hi, CLASSES)
    lowers = [lo, *uppers[:-1]]
    idx = np.clip(np.searchsorted(uppers, v, side="left"), 0, len(uppers) - 1)
    counts = np.bincount(idx, minlength=len(uppers))
    return [{"lo": a, "hi": b, "color": [int(c) for c in rgb.split(",")], "count": int(k)}
            for a, b, rgb, k in zip(lowers, uppers, jet_r(len(uppers)), counts, strict=True)]


def _build(product: Path, out: Path) -> None:
    names = set(pq.read_schema(product / "points.parquet").names)
    geo = [c for c in ("heading_deg", "los_e", "los_n") if c in names]
    pts = pq.read_table(product / "points.parquet", columns=["point_uid", "lon", "lat", "vel_los_mm_yr", *ATTRS, *geo])
    lon = pts["lon"].to_numpy().astype(np.float64)
    lat = pts["lat"].to_numpy().astype(np.float64)
    vel = pts["vel_los_mm_yr"].to_numpy().astype(np.float32)
    n = len(lon)
    lon0, lat0 = float(np.round(np.median(lon), 4)), float(np.round(np.median(lat), 4))
    out.mkdir(parents=True, exist_ok=True)
    np.column_stack([lon - lon0, lat - lat0, vel]).astype(np.float32).tofile(out / "points.bin")
    np.savez(out / "attrs.npz", lon=lon, lat=lat, vel=vel,
             **{a: pts[a].to_numpy().astype(np.float32) for a in ATTRS})

    # timeseries.parquet: long format sorted by (point_uid, date), every point at every date
    has_scn = "disp_scn_mm" in pq.read_schema(product / "timeseries.parquet").names
    dates, series = timeseries_arrays(product / "timeseries.parquet", pts["point_uid"].to_numpy(zero_copy_only=False),
                                      ("disp_mm", "disp_scn_mm") if has_scn else ("disp_mm",))
    np.save(out / "ts.npy", zero_reference(series["disp_mm"]))
    if has_scn:
        np.save(out / "ts_scn.npy", zero_reference(series["disp_scn_mm"]))

    cls = classes(vel)
    # acquisition geometry for map figures: flight direction (heading) and look direction (LOS from the ground to
    # the satellite, reversed, horizontal part)
    heading = look = None
    if "heading_deg" in geo:
        heading = float(np.nanmedian(pts["heading_deg"].to_numpy().astype(np.float64)))
    if "los_e" in geo and "los_n" in geo:
        e = float(np.nanmedian(pts["los_e"].to_numpy().astype(np.float64)))
        nn = float(np.nanmedian(pts["los_n"].to_numpy().astype(np.float64)))
        if np.isfinite(e) and np.isfinite(nn) and (e or nn):
            look = float(np.degrees(np.arctan2(-e, -nn)) % 360)
    meta = {"version": CACHE_VERSION, "product_id": product.name, "n": n, "origin": [lon0, lat0],
            "heading_deg": None if heading is None or not np.isfinite(heading) else round(heading % 360, 2),
            "look_azimuth_deg": None if look is None else round(look, 2),
            "marker_m": marker_size_m(lon, lat),
            "bounds": [float(np.nanmin(lon)), float(np.nanmin(lat)), float(np.nanmax(lon)), float(np.nanmax(lat))],
            "dates": [str(d) for d in dates], "vel_min": float(np.nanmin(vel)), "vel_max": float(np.nanmax(vel)),
            "classes": cls, "attrs": list(ATTRS), "has_scn": has_scn}
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def ensure(product: Path, cache_root: Path) -> Path:
    """The cache folder of a product, built on first use."""
    out = cache_root / product.name
    src = product / "points.parquet"
    if not src.exists():
        raise StoreError(f"{product.name}: no points.parquet")
    with _lock(product.name):
        meta = out / "meta.json"
        fresh = (meta.exists() and meta.stat().st_mtime >= src.stat().st_mtime
                 and json.loads(meta.read_text(encoding="utf-8")).get("version") == CACHE_VERSION)
        if not fresh:
            meta.unlink(missing_ok=True)
            _build(product, out)
            _arrays.cache_clear()
    return out


@lru_cache(maxsize=4)
def _arrays(folder: str) -> tuple[dict, np.ndarray, np.ndarray | None]:
    """(attributes, time series, SCN-removed time series or None), memory-mapped."""
    f = Path(folder)
    with np.load(f / "attrs.npz") as z:
        attrs = {k: z[k] for k in z.files}
    scn = np.load(f / "ts_scn.npy", mmap_mode="r") if (f / "ts_scn.npy").exists() else None
    return attrs, np.load(f / "ts.npy", mmap_mode="r"), scn


def meta(folder: Path) -> dict:
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


TILED_ABOVE = 2_500_000          # points: above, the map reads the product as vector tiles (PMTiles)


def pmtiles_path(product: Path, export_dir: Path, cache_root: Path, build: bool = True) -> Path | None:
    """The product's PMTiles: the export when there is one, else a copy built once in the web cache."""
    exported = export_dir / f"{product.name}.pmtiles"
    if exported.exists():
        return exported
    cached = cache_root / product.name / "points.pmtiles"
    if cached.exists() and cached.stat().st_mtime >= (product / "points.parquet").stat().st_mtime:
        return cached
    if not build:
        return None
    from geoeyes.export.pmtiles import product_pmtiles
    with _lock(f"{product.name}/pmtiles"):
        if not cached.exists():
            product_pmtiles(product, cached)
    _reader.cache_clear()
    return cached


@lru_cache(maxsize=8)
def _reader(path: str):
    from geoeyes.export.pmtiles import TileReader
    return TileReader(path)


def tile(path: Path, z: int, x: int, y: int) -> bytes | None:
    """A gzip-compressed MVT tile, None outside the product."""
    r = _reader(str(path))
    h = r.header
    if not h["min_zoom"] <= z <= h["max_zoom"]:
        return None
    return r.get(z, x, y)


def point(folder: Path, i: int) -> dict:
    attrs, ts, scn = _arrays(str(folder))
    n = len(attrs["vel"])
    if not 0 <= i < n:
        raise IndexError(f"point {i} out of range (0..{n - 1})")
    return {"index": i, **{k: _num(v[i]) for k, v in attrs.items()},
            "disp_mm": [_num(x) for x in np.asarray(ts[i])],
            "disp_scn_mm": None if scn is None else [_num(x) for x in np.asarray(scn[i])]}


def area(folder: Path, ring: list[list[float]]) -> dict:
    """Mean (and spread) of the series of the points inside a polygon ``[[lon, lat], ...]``."""
    from matplotlib.path import Path as Poly
    attrs, ts, scn = _arrays(str(folder))
    lon, lat = attrs["lon"], attrs["lat"]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    box = (lon >= min(xs)) & (lon <= max(xs)) & (lat >= min(ys)) & (lat <= max(ys))
    cand = np.flatnonzero(box)
    inside = cand[Poly(np.asarray(ring)).contains_points(np.column_stack([lon[cand], lat[cand]]))]
    if inside.size == 0:
        return {"n": 0}
    rows = np.sort(inside)
    sub = np.asarray(ts[rows], dtype=np.float64)
    vel = attrs["vel"][inside].astype(np.float64)
    out = {"n": int(inside.size), "vel_mean": _num(vel.mean()), "vel_min": _num(vel.min()),
           "vel_max": _num(vel.max()), "mean_mm": [_num(x) for x in np.nanmean(sub, axis=0)],
           "std_mm": [_num(x) for x in np.nanstd(sub, axis=0)]}
    if scn is not None:
        out["mean_scn_mm"] = [_num(x) for x in np.nanmean(np.asarray(scn[rows], dtype=np.float64), axis=0)]
    return out


def _num(x) -> float | None:
    x = float(x)
    return round(x, 6) if np.isfinite(x) else None          # 1e-6° ≈ 0.1 m for lon / lat
