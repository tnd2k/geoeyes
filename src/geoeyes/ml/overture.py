"""Building footprints from Overture Maps (buildings theme, PMTiles on the public S3 bucket), read tile by tile
at zoom 14 over HTTP range requests and cached under ``<workspace>/cache/overture/<release>/``.

Overture buildings combine OpenStreetMap with Microsoft and Google footprints detected on imagery: in Hanoi one
z14 tile holds ~17 500 buildings against ~60 in OpenStreetMap alone. Licence: ODbL (© OpenStreetMap contributors,
Overture Maps Foundation), with CC BY 4.0 sources (Google Open Buildings, Esri Community Maps): credit them.
"""
from __future__ import annotations

import gzip
import logging
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

RELEASE = "2026-10-21.0"
URL = "https://overturemaps-extras-us-west-2.s3.amazonaws.com/tiles/{release}/buildings.pmtiles"
ZOOM = 14
FLOOR_M = 3.0                     # storey height when only the number of floors is known
CREDIT = "Overture Maps Foundation, © OpenStreetMap contributors (ODbL), Google Open Buildings, Microsoft (CC BY 4.0)"


def _varint(b: bytes, i: int) -> tuple[int, int]:
    s = o = 0
    while True:
        c = b[i]
        i += 1
        o |= (c & 0x7F) << s
        if not c & 0x80:
            return o, i
        s += 7


def _fields(b: bytes):
    """(field, wire type, value) of a protobuf message."""
    i = 0
    while i < len(b):
        k, i = _varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 2:
            n, i = _varint(b, i)
            v = b[i:i + n]
            i += n
        elif w == 5:
            v = b[i:i + 4]
            i += 4
        elif w == 1:
            v = b[i:i + 8]
            i += 8
        else:
            raise ValueError(f"protobuf wire type {w}")
        yield f, w, v


def _value(b: bytes):
    import struct
    for f, _, v in _fields(b):
        if f == 1:
            return v.decode("utf-8", "replace")
        if f == 2:
            return struct.unpack("<f", v)[0]
        if f == 3:
            return struct.unpack("<d", v)[0]
        if f in (4, 5):
            return v
        if f == 6:
            return (v >> 1) ^ -(v & 1)
        if f == 7:
            return bool(v)
    return None


def _rings(geom: list[int]) -> list[np.ndarray]:
    """Polygon rings (tile coordinates) from MVT geometry commands."""
    rings, cur, x, y, i = [], [], 0, 0, 0
    while i < len(geom):
        cmd, count = geom[i] & 7, geom[i] >> 3
        i += 1
        if cmd in (1, 2):
            for _ in range(count):
                dx, dy = geom[i], geom[i + 1]
                i += 2
                x += (dx >> 1) ^ -(dx & 1)
                y += (dy >> 1) ^ -(dy & 1)
                if cmd == 1 and cur:
                    rings.append(np.array(cur, float))
                    cur = []
                cur.append((x, y))
        elif cmd == 7 and cur:
            rings.append(np.array(cur, float))
            cur = []
    if cur:
        rings.append(np.array(cur, float))
    return rings


def decode_buildings(tile: bytes, z: int, x: int, y: int) -> list[dict]:
    """Buildings of an MVT tile: ``{"id", "gers", "lon", "lat", "area_m2", "height_m", "ring"}`` (outer ring lon/lat;
    ``gers`` = the stable Overture id, also what the web app keys the buildings by)."""
    if tile[:2] == b"\x1f\x8b":
        tile = gzip.decompress(tile)
    out = []
    for f, _, layer in _fields(tile):
        if f != 3:
            continue
        name, feats, keys, vals, extent = None, [], [], [], 4096
        for lf, _, lv in _fields(layer):
            if lf == 1:
                name = lv.decode()
            elif lf == 2:
                feats.append(lv)
            elif lf == 3:
                keys.append(lv.decode())
            elif lf == 4:
                vals.append(_value(lv))
            elif lf == 5:
                extent = lv
        if name != "building":
            continue
        n = 2.0 ** z
        for ft in feats:
            fid, tags, geom = None, [], []
            for ff, _fw, fv in _fields(ft):
                if ff == 1:
                    fid = fv
                elif ff == 2:
                    tags = _packed(fv)
                elif ff == 4:
                    geom = _packed(fv)
            props = {keys[tags[k]]: vals[tags[k + 1]] for k in range(0, len(tags) - 1, 2)}
            if props.get("is_underground") is True:
                continue
            rings = _rings(geom)
            if not rings:
                continue
            ring = rings[0]
            lon = (x + ring[:, 0] / extent) / n * 360.0 - 180.0
            lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + ring[:, 1] / extent) / n))))
            lat0 = float(np.mean(lat))
            mx = np.radians(lon) * 6_378_137 * math.cos(math.radians(lat0))
            my = np.radians(lat) * 6_378_137
            area = 0.5 * abs(np.dot(mx, np.roll(my, 1)) - np.dot(my, np.roll(mx, 1)))
            h = props.get("height")
            floors = props.get("num_floors")
            height = float(h) if isinstance(h, (int, float)) and h > 0 else \
                float(floors) * FLOOR_M if isinstance(floors, (int, float)) and floors > 0 else float("nan")
            out.append({"id": fid, "gers": props.get("id"), "lon": float(np.mean(lon)), "lat": lat0,
                        "area_m2": float(area), "height_m": height, "ring": np.column_stack([lon, lat])})
    return out


def _packed(b: bytes) -> list[int]:
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i)
        out.append(v)
    return out


def tiles_over(bbox: list[float], z: int = ZOOM) -> list[tuple[int, int]]:
    w, s, e, n = bbox

    def xy(lon, lat):
        k = 2 ** z
        return (int((lon + 180) / 360 * k),
                int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * k))
    x0, y0 = xy(w, n)
    x1, y1 = xy(e, s)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def buildings(bbox: list[float], cache: Path, release: str = RELEASE, workers: int = 8, progress=None) -> list[dict]:
    """Every building whose centroid lies in ``bbox`` (z14 tiles, cached)."""
    from pmtiles.reader import Reader
    url = URL.format(release=release)
    folder = cache / release / str(ZOOM)
    folder.mkdir(parents=True, exist_ok=True)

    def source(offset, length):
        req = urllib.request.Request(url, headers={"Range": f"bytes={offset}-{offset + length - 1}",
                                                   "User-Agent": "GeoEyes (InSAR analysis)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    reader = Reader(source)
    todo = tiles_over(bbox)

    def one(xy):
        f = folder / f"{xy[0]}_{xy[1]}.mvt"
        if f.exists():
            return xy, f.read_bytes()
        data = reader.get(ZOOM, *xy) or b""
        f.write_bytes(data)
        return xy, data

    if progress:
        progress(f"Overture buildings: {len(todo)} tiles (z{ZOOM}), release {release}")
    out = []
    w, s, e, n = bbox
    with ThreadPoolExecutor(workers) as pool:
        for (x, y), data in pool.map(one, todo):
            if not data:
                continue
            for b in decode_buildings(data, ZOOM, x, y):
                if w <= b["lon"] <= e and s <= b["lat"] <= n:
                    out.append(b)
    # a building crossing a tile edge appears in both tiles: keep the largest piece
    best: dict = {}
    for b in out:
        k = b["gers"] or b["id"] or id(b)
        if k not in best or b["area_m2"] > best[k]["area_m2"]:
            best[k] = b
    return list(best.values())
