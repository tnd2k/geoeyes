"""New landslide scars between two Sentinel-2 composites (docs/en/research/landslide-susceptibility.md §5 L3b.4).

The direction of Sui et al. (2026): the landslides of a rain event, mapped from optical images after it, as an
inventory. Here they are the independent test of the susceptibility models (L3b.5).

* composites: Sentinel-2 L2A (Earth Search, AWS open data; Cloud-Optimised GeoTIFFs read by window), the per-pixel
  median of the clear observations (SCL 4 vegetation, 5 not vegetated) of a window, on a 10 m UTM grid over the study
  area: NDVI (red, NIR at 10 m) and SWIR 1.6 µm reflectance (20 m), with the number of clear observations;
* candidates: NDVI before ≥ ``ndvi_pre`` (vegetated), NDVI after ≤ ``ndvi_post``, local NDVI drop (the drop minus
  its median over 500 m blocks: haze, season and orbit edges shift whole regions) ≥ ``dndvi``, slope ≥
  ``slope_deg`` (Copernicus GLO-30), connected (8) objects of ≥ ``min_px`` pixels;
* calibration: the thresholds are those with the best object F1 against an inventory event mapped from other images
  (Das 2024, Molave): precision = share of the objects touching a polygon (20 m tolerance), recall = share of the
  polygons ≥ ``RECALL_MIN_M2`` touched by an object;
* application: the same thresholds on another pair of windows; polygons (lon / lat, the schema of the inventory:
  event, date, src_fid, area_m2, valid) and the mapped extent (clear in both composites, ≥ ``MIN_CLEAR``
  observations each), ``scars/scars_<event>.gpkg``.

Limits: a dry-season composite does not date a scar within the rainy season; clearing for plantations also removes
the vegetation (hence the calibration); scars of a few pixels are missed.
"""
from __future__ import annotations

import itertools
import json
import logging
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

STAC = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
CLEAR_SCL = (4, 5)
MAX_CLOUD = 60.0              # scene cloud cover, %
MAX_SCENES = 30               # per MGRS tile and window, the least cloudy
MIN_CLEAR = 5                 # clear observations per pixel and composite for the mapped extent
# v2 (2026-11-02, after a blind visual check: 7 % of the v1 objects of 2025 were landslides, 55 % fields, 23 % flood
# deposits, and large new scars were missed):
BACKGROUND_PX = 300           # 3 km blocks: the regional NDVI-drop level (haze, orbit edge) — 500 m erased large
#                               scars and dense clusters
FOREST_NDVI = 0.75            # a pixel was forest before ...
FOREST_WIN = 15               # ... and so was this share of its 150 m neighbourhood: swidden mosaics are left out
FOREST_FRAC = 0.6
RES = 10.0
RECALL_MIN_M2 = 1000.0        # recall counted on the polygons at least this large (≥ 10 pixels)
TOLERANCE_PX = 2              # 20 m: co-registration of the inventory and Sentinel-2
_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_MAX_RETRY": "4", "GDAL_HTTP_RETRY_DELAY": "3",
        "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_HTTP_USERAGENT": "GeoEyes (landslide study)"}

# windows (before, after) of the events mapped; Molave is the calibration (an inventory event), S2_2025 the test
WINDOWS = {"Molave": (("2020-01-01", "2020-10-05"), ("2020-11-15", "2021-04-30")),
           "S2_2025": (("2025-01-01", "2025-10-20"), ("2025-11-20", "2026-04-30"))}
CALIBRATION = "Molave"
TEST_EVENTS = {"S2_2025": "2025-10-26"}     # test event -> date (the rains of late Oct – Nov 2025)
GRID = {"dndvi": (0.15, 0.2, 0.25, 0.3, 0.35), "ndvi_post": (0.35, 0.45, 0.55), "ndvi_pre": (0.5, 0.6),
        "slope_deg": (10.0, 15.0, 20.0), "min_px": (3, 5, 10)}
RATIOS = (0.0, 0.3, 0.4, 0.5, 0.6)
STRICT_PRECISION = 0.6        # L3b gate: an object set good enough to be a test


@dataclass(frozen=True)
class Thresholds:
    dndvi: float = 0.25
    ndvi_post: float = 0.45
    ndvi_pre: float = 0.6
    slope_deg: float = 15.0
    min_px: int = 5


# ---------------------------------------------------------------- grid
@dataclass(frozen=True)
class UtmGrid:
    """A north-up grid in a UTM zone: ``x0``, ``y1`` the west / north edges, ``res`` metres, ``nx`` × ``ny``."""

    epsg: int
    x0: float
    y1: float
    nx: int
    ny: int
    res: float = RES

    @classmethod
    def around(cls, bounds_lonlat, res: float = RES, align: float = 20.0) -> UtmGrid:
        from pyproj import Transformer
        w, s, e, n = bounds_lonlat
        zone = int((((w + e) / 2) + 180) // 6) + 1
        epsg = (32600 if (s + n) / 2 >= 0 else 32700) + zone
        t = Transformer.from_crs(4326, epsg, always_xy=True)
        xs, ys = t.transform([w, e, w, e], [s, s, n, n])
        x0, x1 = math.floor(min(xs) / align) * align, math.ceil(max(xs) / align) * align
        y0, y1 = math.floor(min(ys) / align) * align, math.ceil(max(ys) / align) * align
        return cls(epsg, x0, y1, int(round((x1 - x0) / res)), int(round((y1 - y0) / res)), res)

    @property
    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.x0, self.y1, self.res, self.res)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.x0, self.y1 - self.ny * self.res, self.x0 + self.nx * self.res, self.y1

    def lonlat(self, rows: slice | None = None) -> tuple[np.ndarray, np.ndarray]:
        from pyproj import Transformer
        r = np.arange(self.ny)[rows or slice(None)]
        x = self.x0 + (np.arange(self.nx) + 0.5) * self.res
        y = self.y1 - (r + 0.5) * self.res
        xx, yy = np.meshgrid(x, y)
        lon, lat = Transformer.from_crs(self.epsg, 4326, always_xy=True).transform(xx, yy)
        return lon, lat


# ---------------------------------------------------------------- search and read
def search(bbox, d0: str, d1: str, max_cloud: float = MAX_CLOUD) -> list[dict]:
    """Sentinel-2 L2A items over ``bbox`` (lon / lat) between two dates, every page."""
    body = {"collections": [COLLECTION], "bbox": list(bbox), "datetime": f"{d0}T00:00:00Z/{d1}T23:59:59Z",
            "limit": 100, "query": {"eo:cloud_cover": {"lt": max_cloud}}}
    items: list[dict] = []
    while body is not None:
        req = urllib.request.Request(STAC, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            page = json.load(r)
        items += page["features"]
        nxt = [lk for lk in page.get("links", []) if lk.get("rel") == "next"]
        body = {**body, **nxt[0]["body"]} if nxt and nxt[0].get("body") else None
    return items


def _tile(it: dict) -> str:
    return it["properties"].get("s2:mgrs_tile") or it["id"].split("_")[1]


def pick(items: list[dict], max_scenes: int = MAX_SCENES) -> list[dict]:
    """One item per tile and day (the latest processing: Earth Search keeps the reprocessed versions ``_1``, ``_2``
    beside ``_0``), then the least cloudy ``max_scenes`` of each MGRS tile."""
    latest: dict[tuple[str, str], dict] = {}
    for it in items:
        k = (_tile(it), it["properties"]["datetime"][:10])
        if k not in latest or it["properties"].get("created", "") > latest[k]["properties"].get("created", ""):
            latest[k] = it
    by: dict[str, list[dict]] = {}
    for it in latest.values():
        by.setdefault(_tile(it), []).append(it)
    out = []
    for v in by.values():
        out += sorted(v, key=lambda it: it["properties"]["eo:cloud_cover"])[:max_scenes]
    return out


def _band(ds, grid: UtmGrid, factor: int):
    """The part of ``grid`` covered by ``ds`` (same CRS, pixels ``factor`` × ``grid.res``): (array at the grid
    resolution, row slice, column slice) or None."""
    from rasterio.windows import Window
    gx0, gy0, gx1, gy1 = grid.bounds
    dx0, dy0, dx1, dy1 = ds.bounds
    x0, x1, y0, y1 = max(gx0, dx0), min(gx1, dx1), max(gy0, dy0), min(gy1, dy1)
    if x1 - x0 < grid.res * factor or y1 - y0 < grid.res * factor:
        return None
    px = grid.res * factor
    c0 = int(math.floor((x0 - dx0) / px))
    c1 = int(math.ceil((x1 - dx0) / px))
    r0 = int(math.floor((dy1 - y1) / px))
    r1 = int(math.ceil((dy1 - y0) / px))
    a = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
    if factor > 1:
        a = np.repeat(np.repeat(a, factor, 0), factor, 1)
    # the window's west / north edge on the grid
    wx, ny_ = dx0 + c0 * px, dy1 - r0 * px
    gc0, gr0 = int(round((wx - gx0) / grid.res)), int(round((gy1 - ny_) / grid.res))
    rs, cs = slice(max(gr0, 0), min(gr0 + a.shape[0], grid.ny)), slice(max(gc0, 0), min(gc0 + a.shape[1], grid.nx))
    a = a[rs.start - gr0:rs.stop - gr0, cs.start - gc0:cs.stop - gc0]
    return a, rs, cs


def _scale(item: dict, asset: dict) -> tuple[float, float]:
    """Reflectance = DN · scale + offset. Processing baseline ≥ 04.00 adds 1000 to the DN; Earth Search removes it
    when ``earthsearch:boa_offset_applied`` is true (its ``raster:bands`` still says −0.1: not applied twice)."""
    b = (asset.get("raster:bands") or [{}])[0]
    p = item["properties"]
    if p.get("earthsearch:boa_offset_applied"):
        off = 0.0
    else:
        try:
            off = -0.1 if float(p.get("s2:processing_baseline", "0")) >= 4.0 else 0.0
        except ValueError:
            off = float(b.get("offset", 0.0))
    return float(b.get("scale", 1e-4)), off


def read_scene(item: dict, grid: UtmGrid):
    """NDVI and SWIR reflectance of the clear pixels of one item on ``grid`` (int16 × 1e4, -32768 elsewhere), with
    the row / column slices they cover; None when the item misses the grid or has no clear pixel."""
    import rasterio
    a = item["assets"]
    if int(item["properties"].get("proj:epsg", grid.epsg)) != grid.epsg:
        return None
    with rasterio.Env(**_ENV):
        with rasterio.open(a["scl"]["href"]) as ds:
            r = _band(ds, grid, 2)
            if r is None:
                return None
            scl, rs, cs = r
            clear = np.isin(scl, CLEAR_SCL)
            if not clear.any():
                return None
        out = {}
        for k, f in (("red", 1), ("nir", 1), ("swir16", 2)):
            with rasterio.open(a[k]["href"]) as ds:
                v, rs2, cs2 = _band(ds, grid, f)
            if (rs2, cs2) != (rs, cs):          # 10 / 20 m windows can differ by a pixel at the edge
                rr = slice(max(rs.start, rs2.start), min(rs.stop, rs2.stop))
                cc = slice(max(cs.start, cs2.start), min(cs.stop, cs2.stop))
                v = v[rr.start - rs2.start:rr.stop - rs2.start, cc.start - cs2.start:cc.stop - cs2.start]
                full = np.zeros((rs.stop - rs.start, cs.stop - cs.start), v.dtype)
                full[rr.start - rs.start:rr.stop - rs.start, cc.start - cs.start:cc.stop - cs.start] = v
                v = full
            sc, off = _scale(item, a[k])
            out[k] = np.where(v > 0, v * sc + off, np.nan).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (out["nir"] - out["red"]) / (out["nir"] + out["red"])
    ok = clear & np.isfinite(ndvi) & np.isfinite(out["swir16"])
    if not ok.any():
        return None
    nd = np.where(ok, np.clip(ndvi, -1, 1) * 1e4, -32768).astype(np.int16)
    sw = np.where(ok, np.clip(out["swir16"], 0, 3) * 1e4, -32768).astype(np.int16)
    return nd, sw, rs, cs


def composite(grid: UtmGrid, items: list[dict], progress=None, workers: int = 6, strip: int = 256):
    """Median NDVI, median SWIR and number of clear observations over ``items`` (float32, NaN without any)."""
    say = progress or (lambda m: None)
    scenes = []
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(lambda it: _safe_read(it, grid), items):
            done += 1
            if r is not None:
                scenes.append(r)
            if done % 10 == 0 or done == len(items):
                say(f"  read {done}/{len(items)} scenes ({len(scenes)} with clear pixels)")
    ndvi = np.full((grid.ny, grid.nx), np.nan, np.float32)
    swir = np.full((grid.ny, grid.nx), np.nan, np.float32)
    count = np.zeros((grid.ny, grid.nx), np.int16)
    for r0 in range(0, grid.ny, strip):
        r1 = min(r0 + strip, grid.ny)
        nd = np.full((len(scenes), r1 - r0, grid.nx), np.nan, np.float32)
        sw = np.full_like(nd, np.nan)
        for k, (a, b, rs, cs) in enumerate(scenes):
            lo, hi = max(r0, rs.start), min(r1, rs.stop)
            if lo >= hi:
                continue
            x, y = a[lo - rs.start:hi - rs.start], b[lo - rs.start:hi - rs.start]
            m = x != -32768
            nd[k, lo - r0:hi - r0, cs] = np.where(m, x / 1e4, np.nan)
            sw[k, lo - r0:hi - r0, cs] = np.where(m, y / 1e4, np.nan)
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                ndvi[r0:r1] = np.nanmedian(nd, axis=0)
                swir[r0:r1] = np.nanmedian(sw, axis=0)
        count[r0:r1] = np.isfinite(nd).sum(0)
    return ndvi, swir, count


def _safe_read(item, grid):
    for attempt in range(3):
        try:
            return read_scene(item, grid)
        except Exception as exc:                        # network: retried, then the scene is skipped
            log.warning("scene %s, attempt %d: %s", item["id"], attempt + 1, exc)
    return None


def write_composite(path: Path, grid: UtmGrid, ndvi, swir, count, meta: dict) -> None:
    import rasterio
    with rasterio.open(path, "w", driver="GTiff", width=grid.nx, height=grid.ny, count=3, dtype="float32",
                       crs=f"EPSG:{grid.epsg}", transform=grid.transform, nodata=np.nan, compress="deflate",
                       tiled=True, predictor=3) as dst:
        for i, a in enumerate((ndvi, swir, count.astype(np.float32)), 1):
            dst.write(a, i)
        dst.descriptions = ("ndvi_median", "swir16_median", "n_clear")
        dst.update_tags(**{k: json.dumps(v) for k, v in meta.items()})


def read_composite(path: Path):
    import rasterio
    with rasterio.open(path) as ds:
        a = ds.read()
    return a[0], a[1], a[2].astype(np.int16)


# ---------------------------------------------------------------- terrain on the 10 m grid
def slope_on(grid: UtmGrid, dem) -> tuple[np.ndarray, np.ndarray]:
    """Height (bilinear GLO-30) and slope (degrees) at the pixel centres."""
    h = np.empty((grid.ny, grid.nx), np.float32)
    for r0 in range(0, grid.ny, 512):
        lon, lat = grid.lonlat(slice(r0, min(r0 + 512, grid.ny)))
        h[r0:r0 + lon.shape[0]] = dem.orthometric(lat, lon)
    hh = np.where(np.isfinite(h), h, np.nanmin(h)).astype(np.float64)
    gy, gx = np.gradient(hh, grid.res)
    return h, np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


# ---------------------------------------------------------------- detection
def background(a: np.ndarray, block: int = BACKGROUND_PX) -> np.ndarray:
    """The regional level of ``a``: median per ``block`` × ``block`` pixels, interpolated back (bilinear)."""
    import warnings

    from scipy.ndimage import zoom
    ny, nx = a.shape
    by, bx = -(-ny // block), -(-nx // block)
    p = np.full((by * block, bx * block), np.nan, np.float32)
    p[:ny, :nx] = a
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmedian(p.reshape(by, block, bx, block), axis=(1, 3))
    m = np.where(np.isfinite(m), m, np.nanmedian(m))
    return zoom(m, (by * block / by, bx * block / bx), order=1)[:ny, :nx].astype(np.float32)


def local_drop(pre, post, block: int = BACKGROUND_PX) -> np.ndarray:
    """NDVI drop minus its regional level: a scar is a local anomaly, while haze, season or the edge of an orbit
    shift a whole region (the seam of 2025 at the 48PYB / 48PZB overlap)."""
    d = pre[0] - post[0]
    return d - background(d, block)


def forest_mask(pre) -> np.ndarray:
    """Forest before the event, in a forested neighbourhood (not a pixel of a swidden mosaic)."""
    from scipy.ndimage import uniform_filter
    with np.errstate(invalid="ignore"):
        f = pre[0] >= FOREST_NDVI
    return f & (uniform_filter(f.astype(np.float32), FOREST_WIN, mode="nearest") >= FOREST_FRAC)


def candidates(pre, post, slope, th: Thresholds, drop: np.ndarray | None = None,
               forest: np.ndarray | None = None) -> np.ndarray:
    drop = local_drop(pre, post) if drop is None else drop
    forest = forest_mask(pre) if forest is None else forest
    with np.errstate(invalid="ignore"):
        return ((pre[0] >= th.ndvi_pre) & (post[0] <= th.ndvi_post) & (drop >= th.dndvi)
                & (slope >= th.slope_deg) & forest)


def objects(mask: np.ndarray, min_px: int) -> tuple[np.ndarray, int]:
    """Connected (8) objects of ``mask`` with ≥ ``min_px`` pixels, relabelled 1..n."""
    from scipy import ndimage
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if n == 0:
        return lab, 0
    size = np.bincount(lab.ravel())
    keep = size >= min_px
    keep[0] = False
    new = np.zeros(n + 1, np.int32)
    new[keep] = np.arange(1, keep.sum() + 1)
    return new[lab], int(keep.sum())


def rasterize_inventory(polys_utm, grid: UtmGrid) -> np.ndarray:
    """Polygon index + 1 per pixel (0 = none); later polygons win on overlaps."""
    from rasterio.features import rasterize
    shapes = ((g, i + 1) for i, g in enumerate(polys_utm.geometry.values))
    return rasterize(shapes, out_shape=(grid.ny, grid.nx), transform=grid.transform, fill=0, dtype="int32",
                     all_touched=False)


def dilate(inv: np.ndarray, tol_px: int = TOLERANCE_PX) -> np.ndarray:
    from scipy import ndimage
    if not tol_px:
        return inv
    return ndimage.grey_dilation(inv, footprint=ndimage.iterate_structure(np.ones((3, 3), bool), tol_px))


def match(lab: np.ndarray, n: int, inv: np.ndarray, inv_area: np.ndarray, valid: np.ndarray,
          tol_px: int = TOLERANCE_PX, inv_d: np.ndarray | None = None) -> dict:
    """Object precision and polygon recall against a rasterised inventory, inside ``valid``: an object and a polygon
    match when they come within ``tol_px`` pixels (the inventory grown by ``tol_px``: ``inv_d``, computed once)."""
    inv_d = dilate(inv, tol_px) if inv_d is None else inv_d
    lab = np.where(valid, lab, 0)
    obj = lab > 0
    hit_obj = np.zeros(n + 1, bool)
    hit_obj[np.unique(lab[obj & (inv_d > 0)])] = True
    present = np.unique(lab[obj])
    prec = float(hit_obj[present].mean()) if len(present) else float("nan")
    inv_v = np.where(valid, inv, 0)
    ids = np.unique(inv_v[inv_v > 0])
    hit = np.isin(ids, np.unique(inv_d[obj]))
    area = inv_area[ids - 1]
    out = {"objects": int(len(present)), "precision": round(prec, 4), "polygons": int(len(ids))}
    for lo, hi in ((0, 300), (300, 1000), (1000, 3000), (3000, 1e12)):
        k = (area >= lo) & (area < hi)
        out[f"recall_{lo:g}_{hi:g}"] = round(float(hit[k].mean()), 4) if k.any() else None
    k = area >= RECALL_MIN_M2
    out["recall"] = round(float(hit[k].mean()), 4) if k.any() else float("nan")
    p, r = out["precision"], out["recall"]
    out["f1"] = round(2 * p * r / (p + r), 4) if p + r > 0 else 0.0
    return out


def calibrate(pre, post, slope, inv, inv_area, valid, progress=None) -> tuple[Thresholds, list[dict]]:
    """Every combination of GRID; the best object F1."""
    say = progress or (lambda m: None)
    rows = []
    keys = list(GRID)
    combos = list(itertools.product(*GRID.values()))
    inv_d = dilate(inv)
    drop = local_drop(pre, post)
    forest = forest_mask(pre)
    for i, vals in enumerate(combos):
        th = Thresholds(**dict(zip(keys, vals, strict=True)))
        lab, n = objects(candidates(pre, post, slope, th, drop, forest) & valid, th.min_px)
        rows.append({**asdict(th), **match(lab, n, inv, inv_area, valid, inv_d=inv_d)})
        if (i + 1) % 30 == 0:
            say(f"  calibration {i + 1}/{len(combos)}")
    best = max(rows, key=lambda r: (r["f1"], r["precision"]))
    return Thresholds(**{k: best[k] for k in keys}), rows


def polygons(lab: np.ndarray, n: int, grid: UtmGrid, height: np.ndarray, event: str, date: str,
             expected_precision: float | None):
    """Objects as polygons (lon / lat) in the inventory schema, with their head / foot heights."""
    import geopandas as gpd
    import shapely
    from rasterio.features import shapes
    from scipy import ndimage
    geoms: dict[int, list] = {}
    for g, v in shapes(lab, mask=lab > 0, transform=grid.transform, connectivity=8):
        geoms.setdefault(int(v), []).append(shapely.geometry.shape(g))
    idx = np.arange(1, n + 1)
    px = ndimage.sum(np.ones_like(lab), lab, idx)
    hmax = ndimage.maximum(height, lab, idx)
    hmin = ndimage.minimum(height, lab, idx)
    rows = [{"event": event, "date": date, "src_fid": int(i), "area_m2": float(px[i - 1] * grid.res ** 2),
             "head_m": float(hmax[i - 1]), "foot_m": float(hmin[i - 1]), "valid": True,
             "expected_precision": expected_precision, "geometry": shapely.union_all(geoms[int(i)])}
            for i in idx if int(i) in geoms]
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{grid.epsg}")
    g["length_m"] = [_long_side(r) for r in g.geometry.minimum_rotated_rectangle()]
    g["drop_ratio"] = (g.head_m - g.foot_m) / g.length_m.clip(lower=grid.res)
    return g.to_crs(4326)


def _long_side(rect) -> float:
    x, y = rect.exterior.coords.xy
    return float(max(math.hypot(x[1] - x[0], y[1] - y[0]), math.hypot(x[2] - x[1], y[2] - y[1])))


def ratio_filter(lab: np.ndarray, objs, inv, inv_area, valid, inv_d) -> list[dict]:
    """Precision / recall of the objects whose ``drop_ratio`` (head − foot height over the long side: a landslide
    runs down the slope, a clearing across it) reaches each of RATIOS."""
    out = []
    ratio = np.zeros(int(lab.max()) + 1)
    ratio[objs.src_fid.to_numpy()] = objs.drop_ratio.to_numpy()
    for r in RATIOS:
        keep = ratio >= r
        keep[0] = False
        sub = np.where(keep[lab], lab, 0)
        out.append({"drop_ratio": r, **match(sub, int(lab.max()), inv, inv_area, valid, inv_d=inv_d)})
    return out


def extent(valid: np.ndarray, grid: UtmGrid, block: int = 3):
    """The mapped extent (lon / lat): blocks of ``block`` pixels clear in both composites."""
    import geopandas as gpd
    import shapely
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    ny, nx = valid.shape[0] // block, valid.shape[1] // block
    v = valid[:ny * block, :nx * block].reshape(ny, block, nx, block).all(axis=(1, 3)).astype(np.uint8)
    tr = from_origin(grid.x0, grid.y1, grid.res * block, grid.res * block)
    geoms = [shapely.geometry.shape(g) for g, val in shapes(v, mask=v > 0, transform=tr) if val]
    return gpd.GeoSeries([shapely.union_all(geoms)], crs=f"EPSG:{grid.epsg}").to_crs(4326).iloc[0]


# ---------------------------------------------------------------- the study step
def run_scars(study, cache_root: Path, progress=None) -> dict:
    """L3b.4 of a study: ``scars/`` composites, calibration on CALIBRATION, objects of TEST_EVENTS."""
    import geopandas as gpd

    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.landslide.labels import study_area
    say = progress or (lambda m: log.info("%s", m))
    area = study_area(study)
    grid = UtmGrid.around(area.bounds)
    out_dir = study.step_dir("scars")
    out_dir.mkdir(parents=True, exist_ok=True)
    say(f"grid EPSG:{grid.epsg} {grid.nx} x {grid.ny} pixels of {grid.res:g} m")
    comps = {}
    for ev, wins in WINDOWS.items():
        for tag, (d0, d1) in zip(("before", "after"), wins, strict=True):
            f = out_dir / f"composite_{ev}_{tag}.tif"
            if not f.exists():
                items = pick(search(area.bounds, d0, d1))
                say(f"{ev} {tag} {d0} → {d1}: {len(items)} scenes")
                nd, sw, cnt = composite(grid, items, say)
                write_composite(f, grid, nd, sw, cnt, {"window": [d0, d1], "scenes": [it["id"] for it in items]})
            comps[(ev, tag)] = read_composite(f)
    w, s, e, n = area.bounds
    dem = load_copernicus30(s - 0.02, n + 0.02, w - 0.02, e + 0.02, cache_root / "dem" / "copernicus-30")
    height, slope = slope_on(grid, dem)
    in_area = _in_area(area, grid)

    def valid_of(ev):
        pre, post = comps[(ev, "before")], comps[(ev, "after")]
        return in_area & (pre[2] >= MIN_CLEAR) & (post[2] >= MIN_CLEAR) & np.isfinite(pre[0]) & np.isfinite(post[0])

    say(f"calibration on {CALIBRATION}")
    polys = gpd.read_file(study.inventory, layer="polygons")
    polys = polys[(polys.event == CALIBRATION) & polys.geometry.intersects(area)].to_crs(grid.epsg)
    inv = rasterize_inventory(polys, grid)
    inv_area = polys.area_m2.to_numpy() if "area_m2" in polys else polys.area.to_numpy()
    # only where the inventory was mapped (its main footprint): an object elsewhere is not a false positive
    fps = gpd.read_file(study.footprints, layer="footprints")
    mapped = _in_area(fps[(fps.event == CALIBRATION) & (fps.variant == study.footprint_main)].geometry.iloc[0], grid)
    valid = valid_of(CALIBRATION) & mapped
    best, table = calibrate(comps[(CALIBRATION, "before")], comps[(CALIBRATION, "after")], slope, inv, inv_area,
                            valid, say)
    cal = next(r for r in table if all(r[k] == v for k, v in asdict(best).items()))
    lab, nobj = objects(candidates(comps[(CALIBRATION, "before")], comps[(CALIBRATION, "after")], slope, best) & valid,
                        best.min_px)
    cal_g = polygons(lab, nobj, grid, height, CALIBRATION, "", cal["precision"])
    ratios = ratio_filter(lab, cal_g, inv, inv_area, valid, dilate(inv))
    ok = [r for r in ratios if r["precision"] >= STRICT_PRECISION]
    strict = min((r["drop_ratio"] for r in ok), default=None)
    res: dict = {"study": study.name, "grid": asdict(grid), "windows": WINDOWS, "calibration_event": CALIBRATION,
                 "calibration_area": f"{CALIBRATION} footprint {study.footprint_main}",
                 "thresholds": asdict(best), "calibration": cal, "drop_ratio": ratios, "strict_drop_ratio": strict,
                 "valid_fraction": {}, "events": {}}
    res["valid_fraction"][CALIBRATION] = round(float(valid[in_area].mean()), 4)
    files = [f"composite_{ev}_{t}.tif" for ev in WINDOWS for t in ("before", "after")]
    cal_g["in_inventory"] = _touches(lab, nobj, inv)[cal_g.src_fid.to_numpy() - 1]
    cal_g["strict"] = cal_g.drop_ratio >= strict if strict is not None else False
    n_before = len(cal_g)
    cal_g = terrain_filter(cal_g, study, dem, None)
    res["terrain_dropped"] = {CALIBRATION: n_before - len(cal_g)}
    cal_g.to_file(out_dir / f"scars_{CALIBRATION}.gpkg", layer="polygons", driver="GPKG")
    gpd.GeoDataFrame({"event": [CALIBRATION], "name": ["extent"]}, geometry=[extent(valid, grid)], crs=4326).to_file(
        out_dir / f"scars_{CALIBRATION}.gpkg", layer="extent", driver="GPKG")
    files.append(f"scars_{CALIBRATION}.gpkg")
    import pandas as pd
    pd.DataFrame(table).to_csv(out_dir / "calibration.csv", index=False)
    files.append("calibration.csv")
    for ev, date in TEST_EVENTS.items():
        pre, post = comps[(ev, "before")], comps[(ev, "after")]
        valid = valid_of(ev)
        res["valid_fraction"][ev] = round(float(valid[in_area].mean()), 4)
        lab, nobj = objects(candidates(pre, post, slope, best) & valid, best.min_px)
        g = polygons(lab, nobj, grid, height, ev, date, cal["precision"])
        g["strict"] = g.drop_ratio >= strict if strict is not None else False
        n_before = len(g)
        g = terrain_filter(g, study, dem, None)
        res["terrain_dropped"][ev] = n_before - len(g)
        nobj = len(g)
        g.to_file(out_dir / f"scars_{ev}.gpkg", layer="polygons", driver="GPKG")
        gpd.GeoDataFrame({"event": [ev], "name": ["extent"]}, geometry=[extent(valid, grid)], crs=4326).to_file(
            out_dir / f"scars_{ev}.gpkg", layer="extent", driver="GPKG")
        res["events"][ev] = {"date": date, "objects": int(nobj), "strict_objects": int(g.strict.sum()),
                             "area_m2": {"median": round(float(g.area_m2.median()), 1) if len(g) else None,
                                         "total": round(float(g.area_m2.sum()), 1)},
                             "density_per_km2": round(nobj / max(valid.sum() * grid.res ** 2 / 1e6, 1e-9), 3)}
        files.append(f"scars_{ev}.gpkg")
        say(f"{ev}: {nobj} objects")
    files += plot_scars(comps, slope, best, grid, out_dir, area)
    atomic_write_json(out_dir / "scars.json", res)
    (out_dir / "scars.md").write_text(report_md(res, table), encoding="utf-8")
    files += ["scars.json", "scars.md"]
    m = Manifest(kind="landslide_scars", id=f"{study.name}/scars", engine="geoeyes.landslide.scars",
                 inputs=[InputRef("sentinel-2", f"{STAC} {COLLECTION}"), InputRef("inventory", str(study.inventory)),
                         InputRef("dem", "Copernicus GLO-30")],
                 params={"windows": WINDOWS, "thresholds": asdict(best), "grid": GRID, "min_clear": MIN_CLEAR},
                 metrics={"calibration": cal, **{k: v["objects"] for k, v in res["events"].items()}})
    m.add_outputs(out_dir, files)
    m.write(out_dir)
    return res


def terrain_filter(g, study, dem, year: int | None):
    """The objects with their terrain class (``landslide.reliability``, the rules of the inventory polygons); the
    implausible ones (flat, or wholly on a valley floor by a stream: flood deposits, bank erosion) are dropped."""
    import pandas as pd

    from geoeyes.landslide.labels import grid_for, study_area
    from geoeyes.landslide.reliability import flags
    if g.empty:
        return g.assign(reliability=pd.Series(dtype=str))
    grid30 = grid_for(study_area(study).bounds, study.labels.cell_m)
    table = pd.read_parquet(study.step_dir("predictors") / f"predictors_{study.events[-1][0]}.parquet")
    f = flags(g, grid30, table, dem, year)[["src_fid", "reliability"]]
    g = g.merge(f, on="src_fid", how="left")
    return g[g.reliability != "implausible"].reset_index(drop=True)


def _in_area(area, grid: UtmGrid) -> np.ndarray:
    import geopandas as gpd
    from rasterio.features import rasterize
    g = gpd.GeoSeries([area], crs=4326).to_crs(grid.epsg).iloc[0]
    return rasterize([(g, 1)], out_shape=(grid.ny, grid.nx), transform=grid.transform, fill=0,
                     dtype="uint8").astype(bool)


def _touches(lab: np.ndarray, n: int, inv: np.ndarray, tol_px: int = TOLERANCE_PX) -> np.ndarray:
    inv_d = dilate(inv, tol_px)
    hit = np.zeros(n + 1, bool)
    hit[np.unique(lab[(lab > 0) & (inv_d > 0)])] = True
    return hit[1:]


def plot_scars(comps, slope, th: Thresholds, grid: UtmGrid, out_dir: Path, area) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    evs = list(WINDOWS)
    fig, axs = plt.subplots(len(evs), 1, figsize=(15, 3.4 * len(evs)), squeeze=False)
    ext = (grid.bounds[0], grid.bounds[2], grid.bounds[1], grid.bounds[3])
    for ax, ev in zip(axs[:, 0], evs, strict=True):
        pre, post = comps[(ev, "before")], comps[(ev, "after")]
        d = local_drop(pre, post)
        ax.imshow(d[::3, ::3], cmap="RdBu_r", vmin=-0.4, vmax=0.4, extent=ext)
        m = candidates(pre, post, slope, th, d)
        yy, xx = np.nonzero(m[::3, ::3])
        ax.scatter(grid.x0 + xx * 30, grid.y1 - yy * 30, s=0.3, c="k")
        ax.set_title(f"{ev}: local NDVI drop (before − after − its 500 m median; red: loss); black: candidates "
                     f"{asdict(th)}", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_dir / "scars.png", dpi=100)
    plt.close(fig)
    return ["scars.png"]


def report_md(res: dict, table: list[dict]) -> str:
    c = res["calibration"]
    L = [f"# L3b.4 Sentinel-2 scars — {res['study']}", "",
         f"Windows (before, after): {res['windows']}", "",
         f"## Calibration on {res['calibration_event']} (Das 2024 polygons)", "",
         f"Best thresholds (object F1): {res['thresholds']}", "",
         f"- objects {c['objects']}, precision {c['precision']}, recall (polygons ≥ {RECALL_MIN_M2:g} m²) "
         f"{c['recall']}, F1 {c['f1']}",
         f"- recall by area: < 300 m² {c['recall_0_300']}, 300–1000 {c['recall_300_1000']}, "
         f"1000–3000 {c['recall_1000_3000']}, ≥ 3000 {c['recall_3000_1e+12']}",
         f"- mapped (clear) fraction of the area: {res['valid_fraction']}",
         f"- scored inside: {res['calibration_area']}", "",
         "Objects filtered by drop ratio (head − foot height / long side):", "",
         "| drop ratio ≥ | objects | precision | recall | F1 |", "|---|---|---|---|---|",
         *[f"| {r['drop_ratio']} | {r['objects']} | {r['precision']} | {r['recall']} | {r['f1']} |"
           for r in res["drop_ratio"]],
         "", f"Strict set (precision ≥ {STRICT_PRECISION}): drop ratio ≥ {res['strict_drop_ratio']}", "",
         "Top 10 combinations by F1:", "", "| dndvi | ndvi_post | ndvi_pre | slope | min_px | objects | precision | "
         "recall | F1 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(table, key=lambda r: -r["f1"])[:10]:
        L.append(f"| {r['dndvi']} | {r['ndvi_post']} | {r['ndvi_pre']} | {r['slope_deg']} | {r['min_px']} | "
                 f"{r['objects']} | {r['precision']} | {r['recall']} | {r['f1']} |")
    L += ["", "## Test events", ""]
    for ev, v in res["events"].items():
        L.append(f"- {ev} ({v['date']}): {v['objects']} objects ({v['strict_objects']} strict), median area "
                 f"{v['area_m2']['median']} m², "
                 f"{v['density_per_km2']} per km² mapped")
    return "\n".join(L) + "\n"
