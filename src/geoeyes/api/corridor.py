"""Web side of the processing corridor (docs/en/research/corridor-processing.md, K2): the brush preview, route
files turned into strokes, and a project's corridor (read, save, clear).

A brush corridor is saved with its strokes (``source.strokes`` / ``source.erase``), so the map can reopen it and
keep editing; the polygon is always recomputed on the server (``geometry.corridor.build``)."""
from __future__ import annotations

import base64
import tempfile
import zipfile
from pathlib import Path

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.geometry import corridor as C

MAX_STROKE_POINTS = 20000
MAX_UPLOAD_BYTES = 50_000_000
ROUTE_SUFFIXES = {".gpkg", ".geojson", ".json", ".kml", ".kmz", ".shp", ".zip"}


def _strokes(v, what: str) -> list[list[list[float]]]:
    out = []
    for s in v or []:
        pts = [[float(p[0]), float(p[1])] for p in s if len(p) >= 2]
        if pts:
            out.append(pts)
    if sum(len(s) for s in out) > MAX_STROKE_POINTS:
        raise DataError(f"{what}: more than {MAX_STROKE_POINTS} points")
    return out


def _build(body: dict):
    strokes = _strokes(body.get("strokes"), "strokes")
    erase = _strokes(body.get("erase"), "erase")
    polygons = list(body.get("polygons") or [])
    width = float(body.get("width_m") or 1000)
    geom, info = C.build(strokes, width, erase=erase, polygons=polygons)
    return geom, info, {"kind": "brush", "width_m": width, "strokes": strokes, "erase": erase, "polygons": polygons}


def preview(body: dict) -> dict:
    """The corridor of the strokes as drawn: polygon (GeoJSON), area, length, parts, and the bbox it would write."""
    from shapely.geometry import mapping
    if not body.get("strokes") and not body.get("polygons"):
        return {"geometry": None, "info": None, "bbox": None}
    geom, info, _ = _build(body)
    return {"geometry": mapping(geom), "info": info, "bbox": C.bbox_of(geom)}


def import_route(body: dict) -> dict:
    """A route file sent as ``{"name", "data_b64"}``: its lines and points as strokes, its polygons as GeoJSON, so
    the brush can show and edit them."""
    import pyogrio
    import shapely
    from shapely.geometry import mapping
    name = Path(str(body.get("name") or "route.gpkg")).name
    suffix = Path(name).suffix.lower()
    if suffix not in ROUTE_SUFFIXES:
        raise DataError(f"{name}: a GeoPackage, GeoJSON, KML/KMZ or zipped shapefile is needed")
    try:
        raw = base64.b64decode(str(body.get("data_b64") or ""), validate=True)
    except ValueError:
        raise DataError(f"{name}: the file did not arrive whole") from None
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise DataError(f"{name}: empty or larger than {MAX_UPLOAD_BYTES // 1_000_000} MB")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / f"route{suffix}"
        f.write_bytes(raw)
        if suffix in (".kmz", ".zip"):              # the KML inside a KMZ, the .shp inside a zip
            with zipfile.ZipFile(f) as z:
                z.extractall(tmp)
            found = [p for p in Path(tmp).rglob("*") if p.suffix.lower() in (".kml", ".shp")]
            if not found:
                raise DataError(f"{name}: no KML or shapefile inside")
            f = found[0]
        layers = [n for n, _ in pyogrio.list_layers(f)]
        strokes, polygons = [], []
        for layer in layers:
            df = pyogrio.read_dataframe(f, layer=layer)
            if df.crs is None or df.empty:
                continue
            df = df[df.geometry.notna() & ~df.geometry.is_empty].to_crs(4326)
            for g in df.geometry:
                for part in shapely.get_parts(shapely.force_2d(g)):
                    if part.geom_type == "Polygon":
                        polygons.append(mapping(part))
                    elif part.geom_type == "LineString":
                        strokes.append([[round(x, 7), round(y, 7)] for x, y in part.coords])
                    elif part.geom_type == "Point":
                        strokes.append([[round(part.x, 7), round(part.y, 7)]])
    if not strokes and not polygons:
        raise DataError(f"{name}: no line, point or polygon with a coordinate system")
    return {"name": name, "strokes": strokes, "polygons": polygons,
            "points": sum(len(s) for s in strokes)}


def read(project, cfg) -> dict | None:
    """The project's corridor: polygon, figures and the strokes it was drawn with (None without a corridor)."""
    import json
    if not cfg.aoi.corridor:
        return None
    f = project.root / cfg.aoi.corridor
    try:
        fc = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"[aoi] corridor: cannot read {f.name}: {exc}") from None
    feat = (fc.get("features") or [{}])[0]
    return {"file": cfg.aoi.corridor, "geometry": feat.get("geometry"), "info": feat.get("properties", {}),
            "bbox": list(cfg.aoi.bbox) if cfg.aoi.bbox else None, "problem": C.problem(cfg, project.root)}


def save(project, body: dict) -> dict:
    """Write ``corridor.geojson`` from the strokes and set ``[aoi] corridor`` and ``[aoi] bbox``."""
    from geoeyes.api.settings import apply
    geom, info, source = _build(body)
    C.write(project.root / C.FILE, geom, info, source)
    apply(project, {"aoi.corridor": C.FILE, "aoi.bbox": C.bbox_of(geom)})
    return {"file": C.FILE, "info": info, "bbox": C.bbox_of(geom)}


def clear(project) -> dict:
    """Remove ``[aoi] corridor`` (the bbox and the file stay: a redraw starts from it)."""
    from geoeyes.api.settings import apply
    apply(project, {"aoi.corridor": None})
    return {"file": None}


def for_new_project(spec: dict):
    """The corridor of a new project's ``spec["corridor"]`` (strokes), or None: ``(geom, info, source)``."""
    c = spec.get("corridor")
    if not c:
        return None
    return _build(c)
