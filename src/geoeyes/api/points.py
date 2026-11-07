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

CACHE_VERSION = 6                 # /5: series zero at the first date (products before geoeyes-product/3 too)
                                  # /6: meta lists the velocity kinds (v-do, v-dao, v-dso)
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


def calibration_sig(calib: dict | None) -> str | None:
    if not calib:
        return None
    import hashlib
    return hashlib.sha1(json.dumps(calib, sort_keys=True).encode()).hexdigest()[:16]


# the StaMPS velocity kinds a product may carry (ps engine): v-do (DEM error and orbit ramps removed), v-dao (+ APS),
# v-dso (+ SCN, no APS); products written before them carry the SCN-removed velocity only (as v-dso)
KINDS = {"do": ("extra_vel_do_mm_yr",), "dao": ("extra_vel_dao_mm_yr",),
         "dso": ("extra_vel_dso_mm_yr", "extra_vel_scn_mm_yr")}


def _kind_columns(names) -> dict[str, str]:
    """{kind: column} of the kinds present in a points.parquet with these column names."""
    out = {}
    for k, cols in KINDS.items():
        c = next((c for c in cols if c in names), None)
        if c:
            out[k] = c
    return out


def kinds_available(product: Path) -> list[str]:
    return list(_kind_columns(set(pq.read_schema(product / "points.parquet").names)))


def _build(product: Path, out: Path, calib: dict | None = None, kind: str | None = None) -> None:
    names = set(pq.read_schema(product / "points.parquet").names)
    geo = [c for c in ("heading_deg", "los_e", "los_n") if c in names]
    kcols = _kind_columns(names)
    pts = pq.read_table(product / "points.parquet",
                        columns=["point_uid", "lon", "lat", "vel_los_mm_yr", *ATTRS, *geo, *set(kcols.values())])
    lon = pts["lon"].to_numpy().astype(np.float64)
    lat = pts["lat"].to_numpy().astype(np.float64)
    vel = pts["vel_los_mm_yr"].to_numpy().astype(np.float32)
    # which kind the product velocity is (v-dao with the APS removed, else v-do)
    product_kind = next((k for k in ("dao", "do") if k in kcols and np.allclose(
        pts[kcols[k]].to_numpy().astype(np.float32), vel, atol=1e-4, equal_nan=True)), None)
    if kind:
        vel = pts[kcols[kind]].to_numpy().astype(np.float32)
    n = len(lon)

    # timeseries.parquet: long format sorted by (point_uid, date), every point at every date
    has_scn = "disp_scn_mm" in pq.read_schema(product / "timeseries.parquet").names
    dates, series = timeseries_arrays(product / "timeseries.parquet", pts["point_uid"].to_numpy(zero_copy_only=False),
                                      ("disp_mm", "disp_scn_mm") if has_scn else ("disp_mm",))
    if calib:
        # calibrated view (GNSS, or a tie to another product): the correction added to every series and its rate
        # to the velocity; the product files stay as they are
        from geoeyes.validation.gnss import correction
        corr = correction(calib, dates, lon, lat).astype(np.float32)
        t = (dates - dates[0]).astype(np.float64) / 365.2425
        tc = t - t.mean()
        vel = (vel + (corr.astype(np.float64) @ tc) / float(tc @ tc)).astype(np.float32) if t.size > 1 else vel
        for k in series:
            series[k] = series[k] + corr
    lon0, lat0 = float(np.round(np.median(lon), 4)), float(np.round(np.median(lat), 4))
    out.mkdir(parents=True, exist_ok=True)
    np.column_stack([lon - lon0, lat - lat0, vel]).astype(np.float32).tofile(out / "points.bin")
    np.savez(out / "attrs.npz", lon=lon, lat=lat, vel=vel,
             **{a: pts[a].to_numpy().astype(np.float32) for a in ATTRS})
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
            "classes": cls, "attrs": list(ATTRS), "has_scn": has_scn,
            "calibration_sig": calibration_sig(calib), "calibration": calibration_brief(calib),
            "velocity_kind": kind, "velocity_kinds": list(kcols), "product_kind": product_kind,
            "legacy_dso": kcols.get("dso") == "extra_vel_scn_mm_yr"}
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def calibration_brief(calib: dict | None) -> dict | None:
    """What the web app shows of a calibration (layer panel, legend)."""
    if not calib:
        return None
    return {k: calib.get(k) for k in ("source", "kind", "los_mode", "rate_offset_mm_yr", "stations",
                                      "reference_product", "reference_calibration", "loo_rms_after_mm_yr")}


def ensure(product: Path, cache_root: Path, calib: dict | None = None, kind: str | None = None) -> Path:
    """The cache folder of a product, built on first use; with ``calib`` (``validation.tie.active_calibration``),
    the calibrated one (``<product_id>@cal``), rebuilt when the calibration changes; with ``kind`` (``KINDS``), that
    velocity in place of the product's (``<product_id>@v-<kind>``)."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"velocity kind {kind!r} (one of {', '.join(KINDS)})")
    out = cache_root / (product.name + ("@cal" if calib else "") + (f"@v-{kind}" if kind else ""))
    src = product / "points.parquet"
    if not src.exists():
        raise StoreError(f"{product.name}: no points.parquet")
    sig = calibration_sig(calib)
    with _lock(out.name):
        meta = out / "meta.json"
        fresh = False
        if meta.exists() and meta.stat().st_mtime >= src.stat().st_mtime:
            m = json.loads(meta.read_text(encoding="utf-8"))
            fresh = m.get("version") == CACHE_VERSION and m.get("calibration_sig") == sig
        if not fresh:
            meta.unlink(missing_ok=True)
            _build(product, out, calib, kind)
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


HEX_SIZES = (125, 250, 500, 1000, 2000, 4000)   # m, centre to vertex: the map's hexagons when zoomed out


def hexbins(folder: Path, size_m: int) -> bytes:
    """The points binned in flat-top hexagons of ``size_m`` (centre to vertex), in a local metric frame at the
    product's origin: float32 x 4 per hexagon (lon - lon0, lat - lat0, median velocity mm/yr, count). Cached next to
    the layer (``hex_<size>.bin``), rebuilt with it."""
    if size_m not in HEX_SIZES:
        raise ValueError(f"hexagon size {size_m} m (one of {HEX_SIZES})")
    out = folder / f"hex_{size_m}.bin"
    src = folder / "meta.json"
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out.read_bytes()
    with _lock(f"{folder.name}/hex{size_m}"):
        if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            return out.read_bytes()
        attrs = _arrays(str(folder))[0]
        lon0, lat0 = meta(folder)["origin"]
        ok = np.isfinite(attrs["vel"])
        lon, lat, vel = attrs["lon"][ok], attrs["lat"][ok], attrs["vel"][ok].astype(np.float64)
        kx = 111_320.0 * np.cos(np.radians(lat0))
        x, y = (lon - lon0) * kx, (lat - lat0) * 110_574.0
        # axial coordinates of flat-top hexagons, rounded in cube coordinates
        q = (2.0 / 3.0) * x / size_m
        r = (-x / 3.0 + np.sqrt(3.0) / 3.0 * y) / size_m
        cx, cz = q, r
        cy = -cx - cz
        rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
        dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
        fix_x = (dx > dy) & (dx > dz)
        fix_z = ~fix_x & (dy <= dz)
        rx = np.where(fix_x, -ry - rz, rx)
        rz = np.where(fix_z, -rx - ry, rz)
        key = rx.astype(np.int64) * 1_000_003 + rz.astype(np.int64)
        order = np.lexsort((vel, key))
        key, vel, rx, rz = key[order], vel[order], rx[order], rz[order]
        starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        counts = np.diff(np.r_[starts, key.size])
        med = (vel[starts + (counts - 1) // 2] + vel[starts + counts // 2]) / 2.0     # sorted within each bin
        hq, hr = rx[starts], rz[starts]
        hx = size_m * 1.5 * hq
        hy = size_m * np.sqrt(3.0) * (hr + hq / 2.0)
        rec = np.column_stack([hx / kx, hy / 110_574.0, med, counts]).astype(np.float32)
        tmp = out.with_suffix(".tmp")
        rec.tofile(tmp)
        tmp.replace(out)
        return out.read_bytes()


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
        s2 = np.asarray(scn[rows], dtype=np.float64)
        out["mean_scn_mm"] = [_num(x) for x in np.nanmean(s2, axis=0)]
        out["std_scn_mm"] = [_num(x) for x in np.nanstd(s2, axis=0)]
    return out


DISP_SCALE = 10.0                # displacement frames: int16 in 0.1 mm (±3.2 m)


def disp_meta(folder: Path) -> dict:
    """Dates and classes of the cumulative displacement over all points and dates (full range, Pretty Breaks)."""
    f = folder / "disp.json"
    if f.exists() and f.stat().st_mtime >= (folder / "ts.npy").stat().st_mtime:
        return json.loads(f.read_text(encoding="utf-8"))
    _, ts, _ = _arrays(str(folder))
    a = np.asarray(ts, dtype=np.float32)
    v = a[np.isfinite(a)]
    out = {"dates": meta(folder)["dates"], "scale": DISP_SCALE, "min": float(v.min()), "max": float(v.max()),
           "classes": classes(v)}
    f.write_text(json.dumps(out), encoding="utf-8")
    return out


def disp_frame(folder: Path, k: int) -> bytes:
    """Cumulative displacement of every point (product order) at date ``k``: int16 in 1/DISP_SCALE mm, NaN = −32768."""
    _, ts, _ = _arrays(str(folder))
    if not 0 <= k < ts.shape[1]:
        raise IndexError(f"date {k} out of range (0..{ts.shape[1] - 1})")
    col = np.asarray(ts[:, k], dtype=np.float32) * DISP_SCALE
    out = np.where(np.isfinite(col), np.clip(np.round(col), -32767, 32767), -32768).astype("<i2")
    return out.tobytes()


def profile(folder: Path, line: list[list[float]], half_width_m: float, max_points: int = 20_000) -> dict:
    """Points within ``half_width_m`` of a polyline ``[[lon, lat], ...]``: distance along it, signed offset (left +),
    velocity, height; with the median velocity in bins along the line."""
    attrs, _, _ = _arrays(str(folder))
    lon, lat = attrs["lon"], attrs["lat"]
    ln = np.asarray(line, dtype=np.float64)
    lat0 = np.radians(ln[:, 1].mean())
    kx, ky = 111_320.0 * np.cos(lat0), 110_540.0
    pad_x, pad_y = half_width_m / kx, half_width_m / ky
    box = ((lon >= ln[:, 0].min() - pad_x) & (lon <= ln[:, 0].max() + pad_x)
           & (lat >= ln[:, 1].min() - pad_y) & (lat <= ln[:, 1].max() + pad_y))
    cand = np.flatnonzero(box)
    px, py = (lon[cand] - ln[0, 0]) * kx, (lat[cand] - ln[0, 1]) * ky
    vx, vy = (ln[:, 0] - ln[0, 0]) * kx, (ln[:, 1] - ln[0, 1]) * ky
    best = np.full(cand.size, np.inf)
    along = np.zeros(cand.size)
    side = np.zeros(cand.size)
    beyond = np.zeros(cand.size, bool)                  # past either end of the line: not in the profile
    start = 0.0
    nseg = len(ln) - 1
    for i, ((ax, ay), (bx, by)) in enumerate(zip(zip(vx[:-1], vy[:-1], strict=True), zip(vx[1:], vy[1:], strict=True),
                                                 strict=True)):
        dx, dy = bx - ax, by - ay
        seg = float(np.hypot(dx, dy))
        if seg == 0:
            continue
        raw = ((px - ax) * dx + (py - ay) * dy) / seg ** 2
        t = np.clip(raw, 0, 1)
        cx, cy = ax + t * dx, ay + t * dy
        dist = np.hypot(px - cx, py - cy)
        sign = np.sign(dx * (py - ay) - dy * (px - ax))
        better = dist < best
        best[better], along[better], side[better] = dist[better], start + t[better] * seg, sign[better] * dist[better]
        beyond[better] = ((raw < 0) & (i == 0) | (raw > 1) & (i == nseg - 1))[better]
        start += seg
    keep = (best <= half_width_m) & ~beyond
    idx, along, side = cand[keep], along[keep], side[keep]
    n = int(idx.size)
    if n > max_points:
        pick = np.sort(np.random.default_rng(0).choice(n, max_points, replace=False))
        idx, along, side = idx[pick], along[pick], side[pick]
    vel = attrs["vel"][idx].astype(np.float64)
    bin_m = max(20.0, start / 100)
    edges = np.arange(0, start + bin_m, bin_m)
    b = np.clip(np.digitize(along, edges) - 1, 0, len(edges) - 1)
    med = [[round(float(edges[k] + bin_m / 2), 1), round(float(np.median(vel[b == k])), 2), int((b == k).sum())]
           for k in range(len(edges)) if (b == k).any()]
    h = attrs.get("height_m")
    return {"n": n, "shown": int(idx.size), "length_m": round(start, 1), "half_width_m": half_width_m,
            "bin_m": round(bin_m, 1), "index": idx.astype(int).tolist(),
            "dist_m": np.round(along, 1).tolist(), "offset_m": np.round(side, 1).tolist(),
            "vel": np.round(vel, 2).tolist(),
            "vel_std": [_num(x) for x in attrs["vel_std_mm_yr"][idx]] if "vel_std_mm_yr" in attrs else None,
            "height_m": [_num(x) for x in h[idx]] if h is not None else None, "median": med}


def _num(x) -> float | None:
    x = float(x)
    return round(x, 6) if np.isfinite(x) else None          # 1e-6° ≈ 0.1 m for lon / lat
