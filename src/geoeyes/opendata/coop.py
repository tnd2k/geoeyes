"""Source Cooperative (https://source.coop): search its catalog, and read the open layers GeoEyes uses over an AOI.

Catalog: the products listed by the site map, described by the public API (``/api/v1/products/<account>``: title,
description, tags), indexed in ``<workspace>/cache/opendata/source_coop.json`` and refreshed by ``sync`` (a day old:
stale). ``search`` ranks the products on words of the query (every word must match; title and product id count
more than the description); products with a GeoEyes reader are flagged (``layer``).

Layers read here, only the AOI window (COG range requests, Parquet row groups filtered on their bbox statistics),
cached as GeoTIFF / GeoParquet under ``<workspace>/cache/sourcecoop/<layer>/``:

    gsw-monthly     JRC Global Surface Water, monthly history 2017-2024, 30 m: 0 no observation, 1 land, 2 water
    glofas-depth    JRC GloFAS riverine flood depth (m) for a return period (10 ... 500 years), 90 m
    chirps-daily    CHIRPS v3 daily rainfall (RNL: split with ERA5), 0.05°, 1981 to near present
    imerg           NASA GPM IMERG half-hourly rainfall, 0.1°, 1998 to present (Icechunk 2: ``imerg_reader``)
    ghsl-pop        JRC GHS-POP R2023A residents per cell, 2025 epoch, 3" (~90 m)
    gba-buildings   GlobalBuildingAtlas LoD1 footprints with a height for every building (TUM, 2.75 billion)

Every object is public: ``https://data.source.coop/<account>/<product>/<path>``, no account or key.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import requests

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.manifest import atomic_write_json

log = logging.getLogger(__name__)

SITE = "https://source.coop"
DATA = "https://data.source.coop"
SITEMAP = f"{SITE}/sitemap.xml"
API = f"{SITE}/api/v1/products/{{account}}"
UA = {"User-Agent": "GeoEyes (InSAR analysis)"}
_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_MAX_RETRY": "3", "GDAL_HTTP_USERAGENT": UA["User-Agent"]}


@dataclass(frozen=True)
class Layer:
    key: str
    product: str                 # <account>/<product>
    title: str
    topic: str                   # flood | exposure
    use: str                     # what GeoEyes does with it
    credit: str
    license: str


LAYERS = {lay.key: lay for lay in (
    Layer("gsw-monthly", "epoch/jrc-global-surface-water-monthly", "JRC Global Surface Water, monthly (2017-2024)",
          "flood", "water of a month against a dry-season month: the flooded area of an event (Yagi, 2024-09)",
          "Source: EC JRC/Google (Pekel et al. 2016)", "Copernicus, free of charge"),
    Layer("glofas-depth", "nlebovits/jrc-glofas", "JRC GloFAS flood hazard depth (return periods 10-500 yr)",
          "flood", "modelled river flood depth by return period: the scenarios of the flood hazard",
          "JRC CEMS-GloFAS v2.1.2 flood hazard maps", "CC BY 4.0"),
    Layer("chirps-daily", "wfp/chirps-rnl-daily", "CHIRPS v3 daily rainfall (RNL)",
          "flood", "daily rainfall of an event over the AOI (the CHC server throttles; this mirror does not)",
          "Climate Hazards Center CHIRPS3, doi:10.15780/G2JQ0P; WFP HDC", "CC BY 4.0"),
    Layer("imerg", "dynamical/nasa-imerg-analysis-late", "NASA GPM IMERG late, half-hourly rainfall (0.1°, 1998-)",
          "flood", "rain intensity of an event, half hour by half hour (needs icechunk >= 2, Python >= 3.12)",
          "NASA GPM IMERG, processed by dynamical.org", "CC BY 4.0"),
    Layer("ghsl-pop", "wfp/jrc-ghsl-pop", "JRC GHS-POP R2023A population, 2025 (3 arc-seconds)",
          "exposure", "residents in the subsiding cells and in the flooded area",
          "Schiavina et al. (2023), GHS-POP R2023A, EC JRC, doi:10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE",
          "CC BY 4.0"),
    Layer("gba-buildings", "tge-labs/globalbuildingatlas-lod1", "GlobalBuildingAtlas LoD1 (footprint + height)",
          "exposure", "a height for the buildings Overture leaves without one (floors of the risk exposure)",
          "Zhu et al. (2025), GlobalBuildingAtlas, TUM (mediatum 1782307)", "see the product page"),
)}


# ----------------------------------------------------------------------------------------------------- catalog

def _index(ws) -> Path:
    return ws.cache_dir("opendata") / "source_coop.json"


def read_index(ws) -> dict:
    p = _index(ws)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def _record(p: dict) -> dict:
    acc, pid = p["account_id"], p["product_id"]
    md = p.get("metadata") or {}
    return {"id": f"{acc}/{pid}", "account": acc, "product": pid, "title": (p.get("title") or "").strip(),
            "description": (p.get("description") or "").strip(), "tags": list(md.get("tags") or []),
            "updated": (p.get("updated_at") or "")[:10], "featured": bool(p.get("featured")),
            "url": f"{SITE}/{acc}/{pid}", "data": f"{DATA}/{acc}/{pid}/",
            "layer": next((k for k, lay in LAYERS.items() if lay.product == f"{acc}/{pid}"), None)}


def sync(ws, *, workers: int = 12, progress: Callable[[str], None] | None = None) -> dict:
    """Refresh the catalog: the accounts of the site map, then each account's products from the API."""
    say = progress or (lambda m: log.info("%s", m))
    with requests.Session() as s:
        s.headers.update(UA)
        r = s.get(SITEMAP, timeout=60)
        r.raise_for_status()
        listed = {tuple(u.split("/")[3:5]) for u in re.findall(r"<loc>([^<]+)</loc>", r.text)
                  if u.count("/") == 4}
        accounts = sorted({a for a, _ in listed})
        say(f"Source Cooperative: {len(listed)} product(s) of {len(accounts)} account(s) in the site map")

        def one(acc: str) -> list[dict]:
            try:
                q = s.get(API.format(account=acc), timeout=60)
                q.raise_for_status()
                return [p for p in q.json().get("products", []) if not p.get("disabled")
                        and p.get("visibility", "public") == "public"]
            except Exception as exc:                 # one account down: the others are kept
                log.warning("Source Cooperative account %s unreadable: %s", acc, exc)
                return []

        with ThreadPoolExecutor(workers) as ex:
            products = [_record(p) for ps in ex.map(one, accounts) for p in ps]
    products.sort(key=lambda p: p["id"])
    atomic_write_json(_index(ws), {"source": "source_coop", "synced": datetime.now(UTC).isoformat(timespec="seconds"),
                                   "products": products})
    say(f"Source Cooperative: {len(products)} product(s) indexed")
    return {"products": len(products), "accounts": len(accounts)}


def stale(ws, max_age_h: float = 24.0) -> bool:
    synced = read_index(ws).get("synced")
    return not synced or (datetime.now(UTC) - datetime.fromisoformat(synced)).total_seconds() > max_age_h * 3600


def status(ws) -> dict:
    d = read_index(ws)
    return {"synced": d.get("synced"), "products": len(d.get("products", [])),
            "layers": [{"key": lay.key, "product": lay.product, "title": lay.title, "topic": lay.topic,
                        "use": lay.use, "credit": lay.credit, "license": lay.license,
                        "url": f"{SITE}/{lay.product}"} for lay in LAYERS.values()]}


def _words(text: str) -> list[str]:
    import unicodedata
    t = unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
    return re.findall(r"[a-z0-9]+", "".join(c for c in t if not unicodedata.combining(c)))


# Vietnamese words of a query, in English (the catalog is in English); phrases first, accents removed
_VI = (("dan so", "population"), ("toa nha", "building"), ("cong trinh", "building"), ("lu lut", "flood"),
       ("ngap lut", "flood"), ("ngap", "flood"), ("lu", "flood"), ("nha", "building"),
       ("mua", "rain"), ("lun", "subsidence"), ("sut lo", "landslide"), ("truot lo", "landslide"),
       ("dia hinh", "elevation"), ("do cao", "elevation"), ("mat nuoc", "water"), ("nuoc", "water"),
       ("rung", "forest"), ("dat nong nghiep", "crop"), ("ranh gioi", "boundaries"), ("hanh chinh", "admin"),
       ("ve tinh", "satellite"), ("anh", "imagery"), ("duong", "roads"), ("thoi tiet", "weather"),
       ("hang ngay", "daily"), ("hang thang", "monthly"), ("hang nam", "annual"), ("chieu cao", "height"),
       ("toan cau", "global"), ("viet nam", "vietnam"))
_VI_STOP = {"lon", "cao", "tang", "cua", "va", "o", "tai", "cac", "nhung", "du", "lieu", "theo", "ve", "cho", "co"}


def _query(query: str) -> list[str]:
    t = " " + " ".join(_words(query)) + " "
    for vi, en in _VI:
        t = t.replace(f" {vi} ", f" {en} ")
    return [w for w in t.split() if w not in _VI_STOP]


def search(ws, query: str = "", *, layers_only: bool = False, limit: int = 100) -> list[dict]:
    """Products matching every word of ``query`` (words of 4+ letters also as a prefix; Vietnamese words of the
    usual topics are read in English), best first; no query: the GeoEyes layers first, then the latest updated."""
    products = read_index(ws).get("products", [])
    if layers_only:
        products = [p for p in products if p["layer"]]
    q = _query(query)
    out = []
    for p in products:
        fields = ((3.0, _words(p["title"]) + _words(p["product"])), (2.0, _words(" ".join(p["tags"]))),
                  (1.5, _words(p["account"])), (1.0, _words(p["description"])))
        score, hit = 0.0, 0
        for w in q:
            best = max((wt * (1.0 if w in ws_ else 0.6) for wt, ws_ in fields
                        if w in ws_ or (len(w) >= 4 and any(x.startswith(w) for x in ws_))
                        or (len(w) >= 6 and any(w in x for x in ws_))), default=0.0)      # globalbuildingatlas
            score += best
            hit += best > 0
        if hit >= math.ceil(len(q) / 2):             # half the words at least: a query in Vietnamese keeps words
            out.append({**p, "matched": hit,          # that are not in _VI
                        "score": round(score + (0.5 if p["layer"] else 0.0) + (0.2 if p["featured"] else 0.0), 2)})
    out.sort(key=lambda p: p["updated"], reverse=True)                  # latest first among equals
    out.sort(key=lambda p: (-p["matched"], -p["score"]))
    return out[:limit]


# ------------------------------------------------------------------------------------------------------ rasters

@dataclass
class Grid:
    """A raster over the AOI in EPSG:4326: ``data[row, col]`` (row 0 = north), NaN where no data."""

    data: np.ndarray
    west: float
    north: float
    res: float
    source: str
    path: Path | None = None

    @property
    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.west, self.north, self.res, self.res)

    def pixel(self, lon, lat) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(row, col, inside) of each location."""
        r = np.floor((self.north - np.asarray(lat, float)) / self.res).astype(np.int64)
        c = np.floor((np.asarray(lon, float) - self.west) / self.res).astype(np.int64)
        ok = (r >= 0) & (c >= 0) & (r < self.data.shape[0]) & (c < self.data.shape[1])
        return np.clip(r, 0, self.data.shape[0] - 1), np.clip(c, 0, self.data.shape[1] - 1), ok

    def cell_area_m2(self) -> np.ndarray:
        """Area of the cells of each row (m²)."""
        lat = self.north - (np.arange(self.data.shape[0]) + 0.5) * self.res
        return (self.res * 111_320.0) ** 2 * np.cos(np.radians(lat))


def _bbox(bbox) -> tuple[float, float, float, float]:
    w, s, e, n = (float(v) for v in bbox)
    if not (w < e and s < n and w >= -180 and e <= 180 and s >= -90 and n <= 90):
        raise ConfigError(f"bbox {bbox}: west,south,east,north in degrees")
    return w, s, e, n


def _key(bbox) -> str:
    return "_".join(f"{v:.4f}" for v in bbox)


def _mosaic(urls: list[str], bbox, *, nodata: float | None = None, scale_nodata=None) -> tuple[np.ndarray, float,
                                                                                              float, float]:
    """The bbox window of the tiles that exist among ``urls`` on their common grid (the first tile's pixel), as
    float32 with NaN for no data; (array, west, north, res)."""
    import rasterio
    from rasterio.windows import from_bounds
    w, s, e, n = bbox
    quiet = logging.getLogger("rasterio._env")
    level = quiet.level
    quiet.setLevel(logging.CRITICAL)
    try:
        out = grid = None
        with rasterio.Env(**_ENV):
            for url in urls:
                try:
                    src = rasterio.open(f"/vsicurl/{url}" if url.startswith("http") else url)
                except Exception as exc:
                    log.debug("no tile %s: %s", url, exc)
                    continue
                with src:
                    if grid is None:
                        res = abs(src.res[0])
                        tw, tn = src.transform.c, src.transform.f
                        gw = tw + math.floor((w - tw) / res) * res          # snapped to the tile's pixel edges
                        gn = tn - math.floor((tn - n) / res) * res
                        nx, ny = max(1, math.ceil((e - gw) / res)), max(1, math.ceil((gn - s) / res))
                        grid = (gw, gn, res)
                        out = np.full((ny, nx), np.nan, np.float32)
                    gw, gn, res = grid
                    ny, nx = out.shape
                    win = from_bounds(gw, gn - ny * res, gw + nx * res, gn, src.transform)
                    win = win.round_offsets().round_lengths()
                    a = src.read(1, window=win, boundless=True, fill_value=src.nodata if src.nodata is not None
                                 else (nodata if nodata is not None else 0), out_shape=(ny, nx)).astype(np.float32)
                    nd = src.nodata if src.nodata is not None else nodata
                    if nd is not None:
                        a[a == nd] = np.nan
                    if scale_nodata is not None:
                        a = scale_nodata(a)
                    ok = np.isfinite(a) & ~np.isfinite(out)
                    out[ok] = a[ok]
        if grid is None:
            raise DataError(f"no tile over {bbox} among {urls[:3]}{'...' if len(urls) > 3 else ''}")
        return out, *grid
    finally:
        quiet.setLevel(level)


def _save(path: Path, g: Grid, dtype: str = "float32") -> None:
    import rasterio
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", driver="GTiff", width=g.data.shape[1], height=g.data.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=g.transform, nodata=np.nan if "float" in dtype else 0,
                       compress="deflate", tiled=True) as dst:
        dst.write(g.data.astype(dtype), 1)
        dst.update_tags(source=g.source)
    tmp.replace(path)


def _load(path: Path, source: str) -> Grid:
    import rasterio
    with rasterio.open(path) as src:
        a = src.read(1).astype(np.float32)
        if src.nodata is not None and not np.isnan(src.nodata):
            a[a == src.nodata] = np.nan
        return Grid(a, src.transform.c, src.transform.f, abs(src.res[0]), source, path)


def _cached(cache: Path, layer: str, name: str, make: Callable[[], Grid], *, keep: bool = True) -> Grid:
    f = cache / layer / f"{name}.tif"
    if f.exists():
        return _load(f, LAYERS[layer].credit)
    g = make()
    if keep:
        _save(f, g)
        g.path = f
    return g


def _zones(bbox, size: float) -> list[tuple[float, float]]:
    """(west, north) of the ``size``° tiles (aligned on -180 / 90) covering the bbox."""
    w, s, e, n = bbox
    lons = np.arange(math.floor((w + 180) / size) * size - 180, e, size)
    lats = np.arange(math.ceil(n / size) * size, s, -size)
    return [(round(float(lo), 6), round(float(la), 6)) for la in lats for lo in lons]


def _hem(v: float, pos: str, neg: str) -> str:
    return f"{abs(int(round(v)))}{pos if v >= 0 else neg}"


def gsw_month(cache: Path, bbox, month: str) -> Grid:
    """Surface water of ``month`` (``YYYY-MM``, 2017-01 ... 2024-12): 0 no observation (NaN), 1 land, 2 water."""
    bbox = _bbox(bbox)
    y, m = (int(v) for v in month.split("-"))
    if not (2017 <= y <= 2024):
        raise ConfigError(f"gsw-monthly: {month} outside 2017-01 ... 2024-12 (the mirror on Source Cooperative)")
    base = f"{DATA}/epoch/jrc-global-surface-water-monthly"

    def url(lon0: float, lat0: float) -> str:
        if y >= 2022:
            return (f"{base}/v1_5/{y}/{y}_{m:02d}/monthlyhistory_{_hem(lon0, 'E', 'W')}_{_hem(lat0, 'N', 'S')}"
                    f"_v1_5_{y}_{m:02d}.tif")
        yo, xo = round((80 - lat0) / 10 * 40000), round((lon0 + 180) / 10 * 40000)
        name = f"{yo:010d}-{xo:010d}.tif" if y == 2021 else f"{y}_{m:02d}-{yo:010d}-{xo:010d}.tif"
        return f"{base}/tiles/{y}/{y}_{m:02d}/{name}"

    def make() -> Grid:
        a, w, n, res = _mosaic([url(*z) for z in _zones(bbox, 10)], bbox, nodata=0)
        a[a == 0] = np.nan
        return Grid(a, w, n, res, LAYERS["gsw-monthly"].credit)

    return _cached(cache, "gsw-monthly", f"{month}_{_key(bbox)}", make)


_GLOFAS_RP = (10, 20, 50, 75, 100, 200, 500)


def _glofas_tiles(cache: Path) -> dict[tuple[int, int], str]:
    f = cache / "glofas-depth" / "tiles.json"
    if f.exists():
        return {tuple(json.loads(k)): v for k, v in json.loads(f.read_text(encoding="utf-8")).items()}
    r = requests.get(f"{DATA}/nlebovits/jrc-glofas/all_urls.txt", headers=UA, timeout=60)
    r.raise_for_status()
    tiles = {}
    for name, ns, la, ew, lo in re.findall(r"(ID\d+_([NS])(\d+)_([EW])(\d+))_RP", r.text):
        tiles[(int(lo) * (1 if ew == "E" else -1), int(la) * (1 if ns == "N" else -1))] = name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({json.dumps(list(k)): v for k, v in tiles.items()}), encoding="utf-8")
    return tiles


def glofas_depth(cache: Path, bbox, rp: int = 100) -> Grid:
    """GloFAS river flood depth (m) of the ``rp``-year flood; NaN where dry."""
    bbox = _bbox(bbox)
    if rp not in _GLOFAS_RP:
        raise ConfigError(f"glofas-depth: return period {rp} not in {_GLOFAS_RP}")
    tiles = _glofas_tiles(cache)
    names = [tiles[(int(lo), int(la))] for lo, la in _zones(bbox, 10) if (int(lo), int(la)) in tiles]
    if not names:
        raise DataError(f"glofas-depth: no GloFAS tile over {bbox}")
    urls = [f"{DATA}/nlebovits/jrc-glofas/depth-rp{rp}/{t}/{t}_RP{rp}_depth.tif" for t in names]

    def make() -> Grid:
        a, w, n, res = _mosaic(urls, bbox, nodata=-9999)
        a[a <= 0] = np.nan
        return Grid(a, w, n, res, LAYERS["glofas-depth"].credit)

    return _cached(cache, "glofas-depth", f"rp{rp}_{_key(bbox)}", make)


def ghsl_pop(cache: Path, bbox) -> Grid:
    """Residents per 3" cell (GHS-POP R2023A, 2025 epoch); tiles R<row>_C<col> of 10° from 180 W / 89.1 N."""
    bbox = _bbox(bbox)
    w, s, e, n = bbox
    urls = [f"{DATA}/wfp/jrc-ghsl-pop/r2023/GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R{r}_C{c}.tif"
            for r in range(int((89.1 - n) // 10) + 1, int((89.1 - s) // 10) + 2)
            for c in range(int((w + 180) // 10) + 1, int((e + 180) // 10) + 2)]

    def make() -> Grid:
        a, w_, n_, res = _mosaic(urls, bbox, nodata=-200)
        a[a < 0] = np.nan
        return Grid(a, w_, n_, res, LAYERS["ghsl-pop"].credit)

    return _cached(cache, "ghsl-pop", _key(bbox), make)


def chirps_daily(cache: Path, bbox, start: date | str, end: date | str, *, progress=None) -> dict:
    """Daily rainfall (mm) over the bbox: the AOI mean and the wettest pixel per day,
    ``{"source", "days": [{"date", "mean_mm", "max_mm"}]}``; days are cached per AOI (absent days asked again)."""
    bbox = _bbox(bbox)
    d0, d1 = (date.fromisoformat(str(v)[:10]) for v in (start, end))
    if (d1 - d0).days > 3660:
        raise ConfigError("chirps-daily: at most ten years at a time")
    f = cache / "chirps-daily" / f"{_key(bbox)}.json"
    known = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    todo = [d for d in days if d.isoformat() not in known and d < date.today()]
    if todo and progress:
        progress(f"CHIRPS daily: reading {len(todo)} day(s)")

    def one(d: date):
        u = f"{DATA}/wfp/chirps-rnl-daily/v3.0/{d:%Y}/{d:%m}/{d:%d}/chirps-v3.0.rnl.{d:%Y.%m.%d}.tif"
        try:
            a = _mosaic([u], bbox, nodata=-9999)[0]
        except DataError:
            return d, None                           # not published yet
        a[a < 0] = np.nan
        return d, (None if not np.isfinite(a).any() else
                   [round(float(np.nanmean(a)), 2), round(float(np.nanmax(a)), 2)])

    if todo:
        with ThreadPoolExecutor(8) as ex:
            for d, v in ex.map(one, todo):
                if v is not None:
                    known[d.isoformat()] = v
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(known), encoding="utf-8")
    return {"source": LAYERS["chirps-daily"].credit, "bbox": list(bbox),
            "days": [{"date": d.isoformat(), "mean_mm": known.get(d.isoformat(), [None, None])[0],
                      "max_mm": known.get(d.isoformat(), [None, None])[1]} for d in days]}


def _icechunk_python(python: str | None) -> list[str]:
    """The interpreter that runs ``imerg_reader``: ``python`` (``GEOEYES_ICECHUNK_PYTHON``), else this one when its
    icechunk reads the v2 format of the store (icechunk >= 2, Python >= 3.12)."""
    import sys
    if python:
        return [python]
    try:
        import icechunk
        if int(icechunk.__version__.split(".")[0]) >= 2:
            return [sys.executable]
    except ImportError:
        pass
    raise ConfigError("imerg: needs icechunk >= 2 (Python >= 3.12); set GEOEYES_ICECHUNK_PYTHON to such an "
                      "interpreter (docs/en/guide/opendata.md §8)")


def imerg_halfhourly(cache: Path, bbox, start: date | str, end: date | str, *, run: str = "late",
                     python: str | None = None, progress=None) -> dict:
    """Half-hourly rainfall (mm/h) over the bbox from NASA GPM IMERG (``late``: final within ~14 h, or ``early``:
    ~4 h), ``{"source", "run", "steps": [{"time" (UTC, start of the half hour), "mean_mm_h", "max_mm_h"}]}``.
    Read by ``imerg_reader`` in the icechunk interpreter; a whole past period is cached per AOI."""
    import subprocess
    bbox = _bbox(bbox)
    d0, d1 = (date.fromisoformat(str(v)[:10]) for v in (start, end))
    if run not in ("late", "early"):
        raise ConfigError("imerg: run = late | early")
    if (d1 - d0).days > 92:
        raise ConfigError("imerg: at most three months at a time (half-hourly series)")
    f = cache / f"imerg-{run}" / f"{_key(bbox)}_{d0}_{d1}.npz"
    if not f.exists():
        if progress:
            progress(f"IMERG {run} half-hourly: {d0} .. {d1}")
        f.parent.mkdir(parents=True, exist_ok=True)
        out = f.with_name(f"{f.stem}.{os.getpid()}.part.npz")
        reader = Path(__file__).with_name("imerg_reader.py")
        argv = [*_icechunk_python(python), "-I", str(reader), run, *(f"{v:.5f}" for v in bbox),
                f"{d0}T00:00", f"{d1}T23:59", str(out)]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            out.unlink(missing_ok=True)
            raise DataError(f"imerg: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
        if d1 >= date.today() - timedelta(days=3):              # recent: not complete yet, not kept
            try:
                return _imerg(out, run)
            finally:
                out.unlink(missing_ok=True)
        out.replace(f)
    return _imerg(f, run)


def _imerg(f: Path, run: str) -> dict:
    with np.load(f) as z:
        times, mean, peak = z["time"], z["mean_mm_h"], z["max_mm_h"]
        attribution = str(z["attribution"]) if "attribution" in z else ""

    def num(v):
        return None if not np.isfinite(v) else round(float(v), 2)
    return {"source": attribution or "NASA GPM IMERG, dynamical.org (Source Cooperative), CC BY 4.0", "run": run,
            "steps": [{"time": str(t), "mean_mm_h": num(m), "max_mm_h": num(p)}
                      for t, m, p in zip(times, mean, peak, strict=True)]}


# ---------------------------------------------------------------------------------------------------- buildings

def _gba_tiles(bbox) -> list[str]:
    w, s, e, n = bbox

    def lon(v):
        return f"{'e' if v >= 0 else 'w'}{abs(v):03d}"

    def lat(v):
        return f"{'n' if v >= 0 else 's'}{abs(v):02d}"
    out = []
    for lo in range(math.floor(w / 5) * 5, math.ceil(e / 5) * 5, 5):
        for la in range(math.ceil(n / 5) * 5, math.floor(s / 5) * 5, -5):
            out.append(f"{DATA}/tge-labs/globalbuildingatlas-lod1/{lon(lo)}_{lat(la)}_{lon(lo + 5)}_{lat(la - 5)}"
                       ".parquet")
    return out


def gba_buildings(cache: Path, bbox, *, geometry: bool = True, progress=None):
    """GlobalBuildingAtlas LoD1 buildings meeting the bbox: a DataFrame ``source, height_m, lon, lat, geometry``
    (WKB polygons; without ``geometry``: centres only, a fraction of the size for a whole city), cached as Parquet
    per AOI. Only the row groups whose bbox statistics meet the AOI are read (DuckDB over HTTP), a few seconds for
    a city district."""
    import duckdb
    import pandas as pd
    bbox = _bbox(bbox)
    f = cache / "gba-buildings" / f"{_key(bbox)}{'' if geometry else '_points'}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    w, s, e, n = bbox
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    parts = []
    for url in _gba_tiles(bbox):
        if requests.head(url, headers=UA, timeout=60).status_code != 200:
            continue                                 # sea: no tile
        if progress:
            progress(f"GlobalBuildingAtlas: {url.rsplit('/', 1)[-1]}")
        parts.append(con.execute(
            f"SELECT source, height AS height_m, (bbox.xmin + bbox.xmax) / 2 AS lon, (bbox.ymin + bbox.ymax) / 2 AS lat"
            f"{', geometry' if geometry else ''} FROM read_parquet('{url}') WHERE bbox.xmin < {e} AND bbox.xmax > {w} "
            f"AND bbox.ymin < {n} AND bbox.ymax > {s}").fetchdf())
    con.close()
    cols = ["source", "height_m", "lon", "lat"] + (["geometry"] if geometry else [])
    t = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({c: [] for c in cols})
    if geometry:
        t["geometry"] = t["geometry"].map(bytes)
    f.parent.mkdir(parents=True, exist_ok=True)
    t.to_parquet(f, index=False)
    return t


def fill_heights(cache: Path, lon, lat, height, bbox, *, progress=None) -> tuple[np.ndarray, np.ndarray]:
    """Heights for the buildings without one (NaN or <= 0), from the GlobalBuildingAtlas footprint holding their
    centroid; (height, filled mask). Network or data errors leave the heights as they were."""
    import shapely
    height = np.asarray(height, np.float64).copy()
    miss = ~(np.isfinite(height) & (height > 0))
    if not miss.any():
        return height, np.zeros_like(miss)
    try:
        g = gba_buildings(cache, bbox, progress=progress)
    except Exception as exc:
        log.warning("GlobalBuildingAtlas heights unavailable: %s", exc)
        return height, np.zeros_like(miss)
    if g.empty:
        return height, np.zeros_like(miss)
    polys = shapely.from_wkb(g["geometry"].to_numpy())
    tree = shapely.STRtree(polys)
    idx = np.flatnonzero(miss)
    pi, gi = tree.query(shapely.points(np.asarray(lon)[idx], np.asarray(lat)[idx]), predicate="within")
    h = g["height_m"].to_numpy(np.float64)
    good = np.isfinite(h[gi]) & (h[gi] > 0)
    filled = np.zeros_like(miss)
    height[idx[pi[good]]] = h[gi[good]]
    filled[idx[pi[good]]] = True
    return height, filled
