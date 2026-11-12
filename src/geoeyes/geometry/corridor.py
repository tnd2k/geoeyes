"""Processing corridor: the area along a route that a project processes (docs/en/research/corridor-processing.md).

A corridor is one (multi)polygon in WGS84, saved as ``<project>/corridor.geojson`` and named by ``[aoi] corridor``.
It is the union of lines buffered by a width (brush strokes on the map, or an imported route), minus erased
strokes, computed in the local UTM zone so that the width is in metres. ``[aoi] bbox`` stays the rectangle around
it (the radar crop until the sparse stack, K3).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from geoeyes.core.errors import ConfigError, DataError

FILE = "corridor.geojson"
MIN_WIDTH_M, MAX_WIDTH_M = 50.0, 20000.0
BBOX_MARGIN_DEG = 0.005                 # ~500 m around the corridor: the bbox written with it
BURST_MARGIN_DEG = 0.005                # bursts within this distance of the corridor are kept
SIMPLIFY_M = 1.0


def utm_crs(lon: float, lat: float) -> str:
    zone = int((lon + 180) // 6) % 60 + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def _transformers(lon: float, lat: float):
    from pyproj import Transformer
    crs = utm_crs(lon, lat)
    return (Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform,
            Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform)


def _check_width(width_m: float) -> float:
    w = float(width_m)
    if not (MIN_WIDTH_M <= w <= MAX_WIDTH_M):
        raise ConfigError(f"corridor width {w:g} m: between {MIN_WIDTH_M:g} and {MAX_WIDTH_M:g} m")
    return w


def build(strokes, width_m: float, erase=(), polygons=()):
    """The corridor of ``strokes`` (lists of [lon, lat], or shapely lines) buffered by ``width_m`` (full width, round
    caps and joints), plus ``polygons`` (kept as drawn), minus ``erase`` strokes buffered the same way.
    Returns ``(polygon in WGS84, info)`` with the area (km²), the stroke length (km) and the bounds."""
    import shapely
    from shapely.geometry import LineString, Point, shape
    from shapely.ops import transform
    w = _check_width(width_m)

    def geom(s):
        if hasattr(s, "geom_type"):
            return s
        if isinstance(s, dict):
            return shape(s)
        pts = [tuple(map(float, p[:2])) for p in s]
        return Point(pts[0]) if len(pts) == 1 else LineString(pts)

    lines = [geom(s) for s in strokes]
    polys = [geom(p) for p in polygons]
    cut = [geom(s) for s in erase]
    if not lines and not polys:
        raise DataError("a corridor needs at least one stroke, line or polygon")
    c = shapely.union_all(lines + polys).centroid
    fwd, back = _transformers(c.x, c.y)
    half = w / 2
    parts = [transform(fwd, g).buffer(half, quad_segs=8) for g in lines]
    parts += [transform(fwd, g).buffer(0) for g in polys]
    area = shapely.union_all(parts)
    if cut:
        area = area.difference(shapely.union_all([transform(fwd, g).buffer(half, quad_segs=8) for g in cut]))
        # slivers left by the arcs of two buffers (and specks the eraser missed): drop parts under (width/10)²
        keep = [p for p in shapely.get_parts(area) if p.area >= (w / 10) ** 2]
        area = shapely.union_all(keep) if keep else shapely.Polygon()
    area = area.simplify(SIMPLIFY_M)
    if area.is_empty:
        raise DataError("the corridor is empty (everything erased)")
    length = sum(transform(fwd, g).length for g in lines if g.geom_type != "Point")
    out = transform(back, area)
    return out, {"width_m": w, "area_km2": round(area.area / 1e6, 3), "length_km": round(length / 1000, 3),
                 "parts": len(getattr(area, "geoms", [area])), "bounds": [round(v, 6) for v in out.bounds]}


def from_file(path: Path | str, width_m: float, layer: str | None = None):
    """Corridor of a route file (GeoPackage, KML/KMZ, GeoJSON, shapefile): lines and points buffered by ``width_m``,
    polygons kept as they are."""
    import pyogrio
    import shapely
    p = Path(path)
    if not p.exists():
        raise DataError(f"route file not found: {p}")
    df = pyogrio.read_dataframe(p, layer=layer)
    if df.crs is None:
        raise DataError(f"{p.name}: no coordinate system")
    df = df[df.geometry.notna() & ~df.geometry.is_empty].to_crs(4326)
    lines, polys = [], []
    for g in df.geometry:
        for part in shapely.get_parts(shapely.force_2d(g)):
            (polys if part.geom_type == "Polygon" else lines).append(part)
    if not lines and not polys:
        raise DataError(f"{p.name}: no line, point or polygon")
    return build(lines, width_m, polygons=polys)


def bbox_of(geom, margin_deg: float = BBOX_MARGIN_DEG) -> list[float]:
    w, s, e, n = geom.bounds
    return [round(w - margin_deg, 5), round(s - margin_deg, 5), round(e + margin_deg, 5), round(n + margin_deg, 5)]


def write(path: Path, geom, info: dict, source: dict | None = None) -> Path:
    """``corridor.geojson``: one feature with the polygon, the width, area, length and how it was made."""
    from shapely.geometry import mapping
    props = {**info, "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": source or {}}
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": props, "geometry": mapping(geom)}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def read(path: Path):
    """The corridor polygon of a ``corridor.geojson`` (the union of its features)."""
    import shapely
    from shapely.geometry import shape
    try:
        fc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"[aoi] corridor: cannot read {path}: {exc}") from None
    feats = fc.get("features") if fc.get("type") == "FeatureCollection" else [fc]
    geoms = [shape(f["geometry"]) for f in feats or [] if f.get("geometry")]
    g = shapely.union_all(geoms) if geoms else None
    if g is None or g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
        raise ConfigError(f"[aoi] corridor: {path} holds no polygon")
    return g


def of_project(cfg, project_dir: Path):
    """The project's corridor polygon, or None when ``[aoi] corridor`` is not set."""
    rel = getattr(cfg.aoi, "corridor", "")
    if not rel:
        return None
    return read(Path(project_dir) / rel)


def problem(cfg, project_dir: Path) -> str | None:
    """Why the corridor cannot be used (missing file, not a polygon, outside the bbox), or None."""
    if not getattr(cfg.aoi, "corridor", ""):
        return None
    try:
        g = of_project(cfg, project_dir)
    except ConfigError as exc:
        return str(exc)
    if cfg.aoi.bbox is None:
        return "[aoi] bbox is required with a corridor (geoeyes corridor writes it)"
    w, s, e, n = cfg.aoi.bbox
    gw, gs, ge, gn = g.bounds
    tol = 1e-6
    if gw < w - tol or gs < s - tol or ge > e + tol or gn > n + tol:
        return f"[aoi] corridor reaches outside [aoi] bbox {list(cfg.aoi.bbox)}: widen the bbox or redraw"
    return None


def digest(geom) -> str:
    """Stable short hash of the polygon (to the cm): a redrawn corridor changes it."""
    import shapely
    g = shapely.set_precision(geom, 1e-7)
    return hashlib.sha256(shapely.to_wkb(shapely.normalize(g))).hexdigest()[:16]


def footprint_hits(footprint_wkt: str | None, area, margin_deg: float = BURST_MARGIN_DEG) -> bool:
    """Whether a burst footprint (WKT) touches ``area`` within ``margin_deg``; a burst without footprint is kept."""
    if not footprint_wkt:
        return True
    from shapely import wkt
    return wkt.loads(footprint_wkt).distance(area) <= margin_deg


def ground_km2(geom) -> float:
    from shapely.ops import transform
    c = geom.centroid
    fwd, _ = _transformers(c.x, c.y)
    return transform(fwd, geom).area / 1e6


__all__ = ["FILE", "bbox_of", "build", "digest", "footprint_hits", "from_file", "of_project", "problem", "read",
           "write", "utm_crs", "ground_km2"]
