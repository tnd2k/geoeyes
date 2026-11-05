"""A surface model (DSM, buildings included) from the USGS 3DEP lidar point clouds, for the stacks whose height of
ambiguity is below a metre (spotlight stacks with baselines of tens of km: Umbra, Las Vegas 2025, 0.2-0.8 m).

The 3DEP 1 m DEMs are bare earth. The point clouds are public on AWS as Entwine Point Tiles (``usgs-lidar-public``,
EPSG:3857, heights in metres above the vertical datum of each survey, NAVD88 in the conterminous US). Here:

1. the most recent survey whose boundary covers the area (index ``resources.geojson`` of the usgs-lidar project);
2. the octree nodes over the area, down to the depth where the node grid is 0.5 m or finer;
3. per cell of ``cell_m`` (default 1 m): the highest point not classified as noise (the top surface: roofs, the
   ground between buildings), small gaps filled by the nearest cell.

The result is a GeoTIFF in EPSG:4326 cached in ``<cache>/<survey>_<hash>.tif``, orthometric heights (datum "EGM96":
NAVD88 and EGM96 differ by about a metre, the same over a few km, which the stack's reference absorbs).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from geoeyes.core.errors import DataError

log = logging.getLogger(__name__)

RESOURCES_URL = "https://raw.githubusercontent.com/hobuinc/usgs-lidar/master/boundaries/resources.geojson"
NOISE = (7, 18)                         # ASPRS low and high noise
NODE_CELL_M = 0.5                       # deepest octree level read: node grid at least this fine


def _get(url: str, timeout: float = 120, attempts: int = 3) -> bytes:
    import requests
    for k in range(attempts):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception:
            if k == attempts - 1:
                raise
            time.sleep(2 * (k + 1))
    raise AssertionError


def _year(name: str) -> int:
    m = re.search(r"(?:19|20)\d\d", name)
    if m:
        return int(m.group(0))
    m = re.search(r"_[A-Z](\d\d)(?:_|$)", name)              # NV_ClarkCo_2_B22: work unit B, 2022
    return 2000 + int(m.group(1)) if m else 0


def surveys_over(bbox, cache: Path) -> list[dict]:
    """3DEP surveys whose boundary covers ``bbox`` (w, s, e, n), the most recent first."""
    from shapely.geometry import box, shape
    f = Path(cache) / "resources.geojson"
    if not f.exists() or time.time() - f.stat().st_mtime > 30 * 86400:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(_get(RESOURCES_URL))
    area = box(*bbox)
    out = []
    for ft in json.loads(f.read_text(encoding="utf-8"))["features"]:
        g = shape(ft["geometry"])
        if g.covers(area):
            p = ft["properties"]
            out.append({"name": p["name"], "url": p["url"], "count": p.get("count", 0), "year": _year(p["name"])})
    return sorted(out, key=lambda s: (-s["year"], -s["count"]))


class Ept:
    """An Entwine Point Tile dataset: its octree keys ``D-X-Y-Z`` and their point counts."""

    def __init__(self, url: str):
        self.base = url.rsplit("/", 1)[0]
        self.info = json.loads(_get(url))
        b = self.info["bounds"]                              # the root cube, EPSG:3857
        self.x0, self.y0, self.side = b[0], b[1], b[3] - b[0]
        self.span = int(self.info.get("span", 128))
        self.counts: dict[str, int] = {}
        self._load("0-0-0-0")

    def _load(self, key: str) -> None:
        self.counts.update(json.loads(_get(f"{self.base}/ept-hierarchy/{key}.json")))

    def depth_for(self, cell_m: float) -> int:
        return max(int(math.ceil(math.log2(self.side / (self.span * cell_m)))), 0)

    def nodes_over(self, box3857, max_depth: int) -> list[tuple[str, int]]:
        """(key, points) of every node down to ``max_depth`` whose xy extent meets ``box3857`` (x0, y0, x1, y1)."""
        bx0, by0, bx1, by1 = box3857
        out, todo = [], ["0-0-0-0"]
        while todo:
            key = todo.pop()
            n = self.counts.get(key)
            if n is None:
                continue
            if n == -1:                                      # its subtree is in another hierarchy file
                self._load(key)
                n = self.counts.get(key, 0)
            d, x, y, z = map(int, key.split("-"))
            s = self.side / 2 ** d
            nx0, ny0 = self.x0 + x * s, self.y0 + y * s
            if nx0 > bx1 or nx0 + s < bx0 or ny0 > by1 or ny0 + s < by0:
                continue
            if n > 0:
                out.append((key, n))
            if d < max_depth:
                todo += [f"{d + 1}-{2 * x + i}-{2 * y + j}-{2 * z + k}" for i in (0, 1) for j in (0, 1) for k in (0, 1)]
        return out

    def points(self, key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """x, y (EPSG:3857), z, classification of a node."""
        import laspy
        las = laspy.read(io.BytesIO(_get(f"{self.base}/ept-data/{key}.laz")))
        return (np.asarray(las.x), np.asarray(las.y), np.asarray(las.z, np.float32),
                np.asarray(las.classification, np.uint8))


def lidar_dsm(bbox, cache: Path, *, cell_m: float = 1.0, survey: str | None = None, progress=None) -> Path:
    """GeoTIFF of the top surface over ``bbox`` (w, s, e, n) from the most recent 3DEP survey covering it (or
    ``survey``); cached."""
    import rasterio
    from pyproj import Transformer
    from rasterio.transform import from_origin
    from scipy import ndimage
    say = progress or (lambda m: log.info("%s", m))
    w, s, e, n = (float(v) for v in bbox)
    cache = Path(cache)
    found = surveys_over((w, s, e, n), cache)
    if survey:
        found = [x for x in found if x["name"] == survey]
    if not found:
        raise DataError(f"no 3DEP lidar survey covers {w:.4f},{s:.4f},{e:.4f},{n:.4f} (USGS lidar on AWS: the "
                        "conterminous US, Hawaii, parts of Alaska)")
    sv = found[0]
    tag = hashlib.sha1(json.dumps([sv["name"], round(w, 5), round(s, 5), round(e, 5), round(n, 5), cell_m])
                       .encode()).hexdigest()[:10]
    out = cache / f"{sv['name']}_{tag}.tif"
    if out.exists():
        return out
    lat0 = (s + n) / 2
    dlat = cell_m / 110_900.0
    dlon = cell_m / (111_320.0 * math.cos(math.radians(lat0)))
    ny, nx = int(math.ceil((n - s) / dlat)), int(math.ceil((e - w) / dlon))
    if ny * nx > 60_000_000:
        raise DataError(f"lidar DSM of {ny} x {nx} cells: too large (keep the area within a few km)")
    to3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    to4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    xs, ys = to3857.transform([w, e, w, e], [s, s, n, n])
    ept = Ept(sv["url"])
    depth = ept.depth_for(NODE_CELL_M)
    nodes = ept.nodes_over((min(xs), min(ys), max(xs), max(ys)), depth)
    say(f"lidar {sv['name']}: {len(nodes)} octree nodes down to depth {depth}, "
        f"{sum(c for _, c in nodes) / 1e6:.0f} M points over {ny} x {nx} cells of {cell_m:g} m")
    top = np.full(ny * nx, -np.inf, np.float32)
    done = 0

    def fetch(key):
        return ept.points(key)
    with ThreadPoolExecutor(8) as pool:
        for x, y, z, cls in pool.map(fetch, [k for k, _ in nodes]):
            keep = ~np.isin(cls, NOISE)
            lon, lat = to4326.transform(x[keep], y[keep])
            r = ((n - lat) / dlat).astype(np.int64)
            c = ((lon - w) / dlon).astype(np.int64)
            inside = (r >= 0) & (r < ny) & (c >= 0) & (c < nx)
            np.maximum.at(top, r[inside] * nx + c[inside], z[keep][inside])
            done += 1
            if done % 50 == 0:
                say(f"lidar: {done}/{len(nodes)} nodes")
    top = top.reshape(ny, nx)
    empty = ~np.isfinite(top)
    if empty.all():
        raise DataError(f"{sv['name']}: no lidar point over the area")
    if empty.any():                                          # gaps (water, dark roofs): the nearest cell
        idx = ndimage.distance_transform_edt(empty, return_distances=False, return_indices=True)
        top = top[tuple(idx)]
    say(f"lidar DSM: heights {np.percentile(top, 1):.1f}..{np.percentile(top, 99):.1f} m, "
        f"{100 * empty.mean():.1f} % of the cells filled from their neighbours")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    with rasterio.open(tmp, "w", driver="GTiff", width=nx, height=ny, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(w, n, dlon, dlat), compress="deflate", tiled=True) as dst:
        dst.write(top.astype(np.float32), 1)
        dst.update_tags(source=f"USGS 3DEP lidar {sv['name']} (top surface, {cell_m:g} m)", survey=sv["name"])
    tmp.replace(out)
    return out
