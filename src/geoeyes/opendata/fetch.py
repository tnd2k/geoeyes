"""Download the scenes of an open-data stack into ``<root>/YYYYMMDD/`` (the folder layout ``build_stack`` reads).

ICEYE SLC-COG with an AOI: only the window covering the AOI (+ ``margin_m``) is read from the cloud-optimised
GeoTIFF (HTTP range requests) and written as a smaller SLC-COG; the window comes from the product's RPC model at
the lowest and highest DEM heights of the AOI, and ``geoeyes:crop`` in the metadata records it. Umbra SICD (NITF)
with an AOI: the window from the SICD projection at the same heights, read row by row with range requests, written
as a complex GeoTIFF + the chip SICD XML (``FirstRow / FirstCol``). Capella SLC: the GeoTIFF and
``*_extended.json`` as delivered (the reader takes whole scenes). Each folder gets ``opendata.json``
(stack, item, AOI, margin) once complete: a folder with the same request is not fetched again.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import requests

from geoeyes.core import netrate
from geoeyes.core.errors import DataError
from geoeyes.io.manifest import atomic_write_json
from geoeyes.opendata.crawl import get_json

log = logging.getLogger(__name__)
MARKER = "opendata.json"
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "2",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MULTIRANGE": "YES",
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES"}


def _download(session: requests.Session, url: str, dest: Path, attempts: int = 3) -> int:
    tmp = dest.with_name(dest.name + ".part")
    for i in range(attempts):
        try:
            with session.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 22):
                        f.write(chunk)
                        netrate.add(len(chunk))
            tmp.replace(dest)
            return dest.stat().st_size
        except requests.RequestException:
            if i == attempts - 1:
                raise
            time.sleep(3 * (i + 1))
    raise AssertionError("unreachable")


def iceye_window(props: dict, aoi, heights: tuple[float, float], margin_m: float) -> tuple[int, int, int, int]:
    """(row0, row1, col0, col1) of the TIFF covering ``aoi`` (w, s, e, n) at both heights, plus the margin."""
    from geoeyes.sensors.iceye.slc_cog import rpc_to_tiff
    w, s, e, n = aoi
    lon, lat = np.meshgrid(np.linspace(w, e, 11), np.linspace(s, n, 11))
    rows, cols = [], []
    for h in heights:
        r, c = rpc_to_tiff(props, lat.ravel(), lon.ravel(), np.full(lat.size, h))
        rows.append(r)
        cols.append(c)
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    inc = np.radians(float(props.get("view:incidence_angle", 30.0)))
    mr = margin_m * np.sin(inc) / float(props["sar:pixel_spacing_range"])        # ground -> slant range samples
    mc = margin_m / float(props["sar:pixel_spacing_azimuth"])
    width, height = int(props["proj:shape"][0]), int(props["proj:shape"][1])
    r0, r1 = int(max(np.floor(rows.min() - mr), 0)), int(min(np.ceil(rows.max() + mr) + 1, height))
    c0, c1 = int(max(np.floor(cols.min() - mc), 0)), int(min(np.ceil(cols.max() + mc) + 1, width))
    if r1 - r0 < 64 or c1 - c0 < 64:
        raise DataError(f"{props.get('iceye:filename')}: the AOI {aoi} is not inside the scene")
    return r0, r1, c0, c1


def read_window_retrying(url: str, r0: int, r1: int, c0: int, c1: int, *, strip: int = 512, attempts: int = 5):
    """All bands of the window (row0..row1, col0..col1) of a remote GeoTIFF, read in strips of ``strip`` rows; a
    strip that fails (a connection cut mid-tile: GDAL retries HTTP errors, not a truncated body) is read again from a
    re-opened dataset. Returns (bands, rows, cols) and the scales / offsets / tags of the bands."""
    import rasterio
    from rasterio.errors import RasterioIOError
    from rasterio.windows import Window
    out, meta = None, None
    for a in range(r0, r1, strip):
        b = min(a + strip, r1)
        for attempt in range(attempts):
            try:
                with rasterio.open(url) as src:
                    if out is None:
                        out = np.empty((src.count, r1 - r0, c1 - c0), src.dtypes[0])
                        meta = {"scales": src.scales, "offsets": src.offsets,
                                "tags": [src.tags(i) for i in range(1, src.count + 1)]}
                    out[:, a - r0:b - r0] = src.read(window=Window(c0, a, c1 - c0, b - a))
                break
            except RasterioIOError as exc:
                if attempt == attempts - 1:
                    raise
                log.warning("%s rows %d..%d: read failed (%s), retrying", Path(url).name, a, b, str(exc)[:80])
                time.sleep(5 * (attempt + 1))
    return out, meta


def _iceye(rec: dict, folder: Path, session, aoi, heights, margin_m: float) -> int:
    import rasterio
    item = get_json(session, rec["meta"])
    p = item["properties"]
    name = str(p.get("iceye:filename") or Path(rec["slc"]).name)
    tif, meta = folder / name, folder / name.replace(".tif", ".json")
    if aoi is None:
        n = _download(session, rec["slc"], tif)
    else:
        h = heights or (float(p.get("iceye:average_scene_height", 0.0)) - 300.0,
                        float(p.get("iceye:average_scene_height", 0.0)) + 300.0)
        r0, r1, c0, c1 = iceye_window(p, aoi, h, margin_m)
        with rasterio.Env(**GDAL_ENV):
            data, src_meta = read_window_retrying(rec["slc"], r0, r1, c0, c1)
            prof = {"driver": "GTiff", "width": c1 - c0, "height": r1 - r0, "count": data.shape[0], "dtype": data.dtype,
                    "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "deflate", "predictor": 2,
                    "BIGTIFF": "IF_SAFER"}
            tmp = tif.with_name(tif.name + ".part")
            with rasterio.open(tmp, "w", **prof) as dst:
                dst.write(data)
                dst.scales, dst.offsets = src_meta["scales"], src_meta["offsets"]
                for b, tags in enumerate(src_meta["tags"], 1):
                    dst.update_tags(b, **tags)
            tmp.replace(tif)
        p["geoeyes:crop"] = {"row0": r0, "col0": c0, "rows": r1 - r0, "cols": c1 - c0, "source": rec["slc"]}
        n = tif.stat().st_size
    atomic_write_json(meta, item)
    return n


def _capella(rec: dict, folder: Path, session, aoi, heights, margin_m: float) -> int:
    meta = folder / Path(rec["meta"]).name
    tif = folder / Path(rec["slc"]).name
    meta.write_bytes(session.get(rec["meta"], timeout=120).content)
    return _download(session, rec["slc"], tif) + meta.stat().st_size


def umbra_sicd_url(session, item_url: str) -> str:
    """The SICD NITF of an Umbra item. The STAC assets carry no href: the files are under
    ``sar-data/task-data/<umbra:task_id>/<YYYY-MM-DD-HH-MM-SS>_UMBRA-NN/``, one folder per collect of the task; the
    folder nearest in time to the item is taken."""
    import re
    from datetime import datetime
    from urllib.parse import quote
    item = get_json(session, item_url)
    p = item["properties"]
    bucket = item_url.split("/stac/")[0]
    prefix = f"sar-data/task-data/{p['umbra:task_id']}/"
    r = session.get(f"{bucket}/?list-type=2&prefix={quote(prefix)}", timeout=60)
    r.raise_for_status()
    keys = [k for k in re.findall(r"<Key>([^<]+)</Key>", r.text) if k.endswith("_SICD.nitf")]
    if not keys:
        raise DataError(f"{item_url}: no SICD in {bucket}/{prefix}")
    when = datetime.fromisoformat((p.get("start_datetime") or p["datetime"]).replace("Z", "+00:00"))
    when = when.replace(tzinfo=None)

    def gap(k: str) -> float:
        m = re.search(r"(\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d)_UMBRA", k)
        return abs((datetime.strptime(m.group(1), "%Y-%m-%d-%H-%M-%S") - when).total_seconds()) if m else 1e12

    key = min(keys, key=gap)
    if gap(key) > 600:
        raise DataError(f"{item_url}: no SICD within 10 min of the item in {prefix}")
    return f"{bucket}/{quote(key)}"


def sicd_window(meta, aoi, heights: tuple[float, float], margin_m: float) -> tuple[int, int, int, int]:
    """(row0, row1, col0, col1) of the SICD covering ``aoi`` at both heights, plus the margin."""
    from geoeyes.core.geodesy import llh_to_ecef
    w, s, e, n = aoi
    lon, lat = np.meshgrid(np.linspace(w, e, 11), np.linspace(s, n, 11))
    rows, cols = [], []
    for h in heights:
        r, c = meta.ground_to_image(llh_to_ecef(lat.ravel(), lon.ravel(), np.full(lat.size, h)))
        rows.append(r)
        cols.append(c)
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    arp = meta.arp.pos(meta.scp_time)
    up = meta.scp / np.linalg.norm(meta.scp)
    sin_inc = np.sin(np.arccos(np.dot(up, (arp - meta.scp) / np.linalg.norm(arp - meta.scp))))
    mr, mc = margin_m * sin_inc / meta.row_ss, margin_m / meta.col_ss
    r0, r1 = int(max(np.floor(rows.min() - mr), 0)), int(min(np.ceil(rows.max() + mr) + 1, meta.rows))
    c0, c1 = int(max(np.floor(cols.min() - mc), 0)), int(min(np.ceil(cols.max() + mc) + 1, meta.cols))
    if r1 - r0 < 64 or c1 - c0 < 64:
        raise DataError(f"{meta.core_name}: the AOI {aoi} is not inside the scene")
    return r0, r1, c0, c1


def _umbra(rec: dict, folder: Path, session, aoi, heights, margin_m: float) -> int:
    from geoeyes.sensors.sicd.meta import parse
    from geoeyes.sensors.sicd.nitf import Nitf
    from geoeyes.sensors.sicd.slc import chip_xml
    url = umbra_sicd_url(session, rec["item"])
    name = Path(url).name.replace("%20", " ")
    if aoi is None:
        return _download(session, url, folder / name)
    nitf = Nitf(url)
    meta = parse(nitf.xml)
    h = heights or (meta.scp_llh[2] - 300.0, meta.scp_llh[2] + 300.0)
    r0, r1, c0, c1 = sicd_window(meta, aoi, h, margin_m)
    log.info("%s: SICD rows %d..%d, cols %d..%d (%.0f MB)", rec["id"], r0, r1, c0, c1, (r1 - r0) * (c1 - c0) * 8 / 1e6)
    data = nitf.read(r0, r1, c0, c1)
    import rasterio
    tif = folder / name.replace(".nitf", ".tif")
    tmp = tif.with_name(tif.name + ".part")
    with rasterio.open(tmp, "w", driver="GTiff", width=c1 - c0, height=r1 - r0, count=1, dtype="complex64",
                       tiled=True, blockxsize=512, blockysize=512, compress="deflate", BIGTIFF="IF_SAFER") as dst:
        dst.write(data, 1)
    tmp.replace(tif)
    tif.with_suffix(".xml").write_text(chip_xml(nitf.xml, r0, c0, r1 - r0, c1 - c0), encoding="utf-8")
    return tif.stat().st_size


FETCHERS: dict[str, Callable] = {"iceye": _iceye, "capella": _capella, "umbra": _umbra}
CUT = {"iceye", "umbra"}                       # sources whose products are cut to the AOI
MARGIN_M = {"iceye": 500.0, "umbra": 50.0}     # default margin around the AOI (pixels of ~1.5 m vs ~0.15 m)


def aoi_heights(dem, aoi) -> tuple[float, float]:
    """Lowest and highest ellipsoidal height of the DEM over the AOI (the range window must hold both)."""
    w, s, e, n = aoi
    lon, lat = np.meshgrid(np.linspace(w, e, 60), np.linspace(s, n, 60))
    h = np.asarray(dem.ellipsoidal(lat.ravel(), lon.ravel()), float)
    h = h[np.isfinite(h)]
    if not h.size:
        raise DataError(f"no DEM height over the AOI {aoi}")
    return float(h.min()) - 50.0, float(h.max()) + 50.0


def fetch_stack(stack: dict, scenes: list[dict], root: Path, *, aoi=None, dem=None, margin_m: float = 500.0,
                progress: Callable[[int, int, str], None] | None = None) -> list[dict]:
    """Fetch every scene of ``stack`` (records of ``scenes`` by id) into ``root/YYYYMMDD``; returns per date the
    folder and the bytes written (0 when already there)."""
    src = stack["source"]
    if src not in FETCHERS:
        raise DataError(f"{stack['id']}: GeoEyes has no reader for {stack.get('product') or src} products yet")
    by_id = {r["id"]: r for r in scenes if r["source"] == src}
    heights = aoi_heights(dem, aoi) if (dem is not None and aoi is not None) else None
    request = {"stack": stack["id"], "aoi": list(aoi) if aoi is not None else None,
               "margin_m": margin_m if src in CUT and aoi is not None else None}
    out = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "geoeyes-opendata"
        for i, s in enumerate(stack["scenes"], 1):
            rec = by_id.get(s["id"])
            if rec is None:
                raise DataError(f"{s['id']}: not in the open-data index (run `geoeyes opendata sync`)")
            folder = Path(root) / s["date"].replace("-", "")
            marker = folder / MARKER
            done = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
            if done.get("item") == rec["item"] and all(done.get(k) == v for k, v in request.items()):
                out.append({"date": s["date"], "dir": str(folder), "bytes": 0})
                continue
            folder.mkdir(parents=True, exist_ok=True)
            marker.unlink(missing_ok=True)
            if progress:
                progress(i, len(stack["scenes"]), s["id"])
            n = FETCHERS[src](rec, folder, session, aoi, heights, margin_m)
            atomic_write_json(marker, {**request, "item": rec["item"], "scene": rec["id"], "bytes": n})
            log.info("%s: %s -> %s (%.1f MB)", s["date"], rec["id"], folder, n / 1e6)
            out.append({"date": s["date"], "dir": str(folder), "bytes": n})
    return out
