"""Point products as PMTiles (Mapbox Vector Tiles in one file): QGIS (3.32+) and web maps read them tile by tile.

Layer ``points``, one feature per point: the feature id is the row of the point in ``points.parquet`` (the web app
asks the API for its time series with it), properties ``v`` (LOS velocity, mm/yr), ``s`` (its standard deviation)
and ``c`` (temporal coherence). All points are in the tiles of the highest zoom, chosen so that neighbouring points
are about two screen pixels apart; lower zooms keep one point per cell of 1/128 of a tile (a random, fixed choice,
so a point shown at one zoom stays shown when zooming in), at most what a screen can show anyway.
"""
from __future__ import annotations

import gzip
import math
import struct
from pathlib import Path

import numpy as np

EXTENT = 4096
LAYER = "points"
KEYS = ("v", "s", "c")
CELLS = 128                     # per tile side, for the thinned lower zooms
MAX_ZOOM_CAP = 16


# ---------------------------------------------------------------- protobuf (the few types MVT needs)
def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def _field(num: int, payload: bytes) -> bytes:              # length-delimited field
    return _varint((num << 3) | 2) + _varint(len(payload)) + payload


def _packed(values) -> bytes:
    return b"".join(_varint(v) for v in values)


def encode_tile(ids: np.ndarray, px: np.ndarray, py: np.ndarray, props: np.ndarray) -> bytes:
    """One MVT tile: points at tile pixels (px, py) in 0..EXTENT, ``props`` (n, len(KEYS)) float32."""
    feats = []
    values = []
    nk = len(KEYS)
    for j in range(len(ids)):
        tags = []
        for k in range(nk):
            v = props[j, k]
            if np.isfinite(v):
                tags += [k, len(values)]
                values.append(b"\x15" + struct.pack("<f", float(v)))           # Value.float_value
        geom = _packed([9, _zigzag(int(px[j])), _zigzag(int(py[j]))])          # MoveTo(1)
        feats.append(_field(2, b"\x08" + _varint(int(ids[j])) + _field(2, _packed(tags)) + b"\x18\x01"
                            + _field(4, geom)))
    layer = (_field(1, LAYER.encode()) + b"".join(feats) + b"".join(_field(3, k.encode()) for k in KEYS)
             + b"".join(_field(4, v) for v in values) + b"\x28" + _varint(EXTENT) + b"\x78\x02")
    return _field(3, layer)


# ---------------------------------------------------------------- tiling
def _mercator(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalised web mercator x, y in 0..1 (y down)."""
    x = (lon + 180.0) / 360.0
    s = np.sin(np.radians(np.clip(lat, -85.05112878, 85.05112878)))
    y = 0.5 - np.log((1 + s) / (1 - s)) / (4 * np.pi)
    return x, y


def zoom_range(lon: np.ndarray, lat: np.ndarray, spacing_m: float) -> tuple[int, int]:
    """(min, max) zoom: the product fits a few tiles at min; neighbours ~2 px apart (512 px tiles) at max."""
    width = max(float(np.ptp(lon)), float(np.ptp(lat)), 1e-4)
    zmin = int(np.clip(math.floor(math.log2(360.0 / width)) - 2, 0, 12))
    m_per_px0 = 40_075_016.686 * math.cos(math.radians(float(np.mean(lat)))) / 512.0
    zmax = int(np.clip(math.ceil(math.log2(m_per_px0 * 2.0 / max(spacing_m, 0.5))), zmin + 1, MAX_ZOOM_CAP))
    return zmin, zmax


def write_pmtiles(path: str | Path, lon, lat, props: np.ndarray, *, spacing_m: float, name: str = "",
                  description: str = "", attribution: str = "GeoEyes", seed: int = 0) -> dict:
    """Write the points; ``props`` (n, 3): velocity, velocity std, coherence. Returns a summary."""
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    lon = np.asarray(lon, np.float64)
    lat = np.asarray(lat, np.float64)
    props = np.asarray(props, np.float32)
    n = lon.size
    order = np.random.default_rng(seed).permutation(n)          # fixed random priority of the points
    mx, my = _mercator(lon[order], lat[order])
    ids = order.astype(np.int64)
    pr = props[order]
    zmin, zmax = zoom_range(lon, lat, spacing_m)
    tiles: dict[int, bytes] = {}
    counts = {}
    keep = np.arange(n)
    for z in range(zmax, zmin - 1, -1):                         # from the top: lower zooms are subsets
        scale = 2 ** z
        gx, gy = mx[keep] * scale, my[keep] * scale
        if z < zmax:
            cell = np.floor(gx * CELLS).astype(np.int64) * (scale * CELLS) + np.floor(gy * CELLS).astype(np.int64)
            _, first = np.unique(cell, return_index=True)
            keep = keep[np.sort(first)]                          # keep the highest-priority point of each cell
            gx, gy = mx[keep] * scale, my[keep] * scale
        tx, ty = np.floor(gx).astype(np.int64), np.floor(gy).astype(np.int64)
        px = np.clip(np.round((gx - tx) * EXTENT), 0, EXTENT - 1).astype(np.int64)
        py = np.clip(np.round((gy - ty) * EXTENT), 0, EXTENT - 1).astype(np.int64)
        key = tx * scale + ty
        srt = np.argsort(key, kind="stable")
        bounds = np.flatnonzero(np.diff(key[srt])) + 1
        for grp in np.split(srt, bounds):
            if grp.size == 0:
                continue
            x, y = int(tx[grp[0]]), int(ty[grp[0]])
            sel = keep[grp]
            tiles[zxy_to_tileid(z, x, y)] = gzip.compress(encode_tile(ids[sel], px[grp], py[grp], pr[sel]), 6)
        counts[z] = int(keep.size)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pmtiles.tmp")
    with tmp.open("wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            w.write_tile(tid, tiles[tid])
        e7 = (lambda v: int(round(v * 1e7)))  # noqa: E731
        header = {"tile_type": TileType.MVT, "tile_compression": Compression.GZIP,
                  "min_lon_e7": e7(lon.min()), "min_lat_e7": e7(lat.min()), "max_lon_e7": e7(lon.max()),
                  "max_lat_e7": e7(lat.max()), "center_zoom": min(zmin + 2, zmax),
                  "center_lon_e7": e7(float(np.median(lon))), "center_lat_e7": e7(float(np.median(lat)))}
        meta = {"name": name, "description": description, "attribution": attribution, "type": "overlay",
                "format": "pbf",
                "vector_layers": [{"id": LAYER, "minzoom": zmin, "maxzoom": zmax,
                                   "fields": {"v": "Number", "s": "Number", "c": "Number"}}],
                "geoeyes": {"points": n, "properties": {"v": "LOS velocity (mm/yr)", "s": "velocity std (mm/yr)",
                                                        "c": "temporal coherence"},
                            "feature_id": "row of the point in points.parquet", "points_per_zoom": counts}}
        w.finalize(header, meta)
    tmp.replace(path)
    return {"path": str(path), "min_zoom": zmin, "max_zoom": zmax, "tiles": len(tiles), "points_per_zoom": counts}


def product_pmtiles(product: str | Path, out: str | Path) -> dict:
    """PMTiles of a product folder (``points.parquet``)."""
    import pyarrow.parquet as pq

    from geoeyes.export.styles import marker_size_m
    product = Path(product)
    t = pq.read_table(product / "points.parquet",
                      columns=["lon", "lat", "vel_los_mm_yr", "vel_std_mm_yr", "temporal_coherence"])
    lon, lat = t["lon"].to_numpy().astype(np.float64), t["lat"].to_numpy().astype(np.float64)
    props = np.column_stack([t[c].to_numpy().astype(np.float32)
                             for c in ("vel_los_mm_yr", "vel_std_mm_yr", "temporal_coherence")])
    spacing = marker_size_m(lon, lat) / 0.9                    # median nearest-neighbour distance
    return write_pmtiles(out, lon, lat, props, spacing_m=spacing, name=product.name,
                         description=f"GeoEyes point product {product.name}: LOS velocity (mm/yr)")


class TileReader:
    """Tiles of a PMTiles file by z/x/y (still gzip-compressed, as stored)."""

    def __init__(self, path: str | Path):
        from pmtiles.reader import MmapSource, Reader
        self._f = open(path, "rb")  # noqa: SIM115 - kept open for the memory map
        self._r = Reader(MmapSource(self._f))
        self.header = self._r.header()

    def get(self, z: int, x: int, y: int) -> bytes | None:
        return self._r.get(z, x, y)

    def metadata(self) -> dict:
        return self._r.metadata()

    def close(self) -> None:
        self._f.close()
