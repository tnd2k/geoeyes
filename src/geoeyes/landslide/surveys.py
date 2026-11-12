"""Field landslide surveys of the workspace: the owner's site lists (GeoPackage, KML/KMZ, GeoJSON, shapefile)
copied as GeoJSON into ``inventories/landslide/surveys/<name>.geojson``, every attribute kept as surveyed.

The map shows them with the reported events of ``vietnam.geojson`` (``inventory.build_vietnam``): ``collection``
returns both, every feature with an ``id`` and ``properties.layer`` (the survey name, or ``reported``).
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from geoeyes.core.errors import DataError

FOLDER = "inventories/landslide/surveys"
REPORTED = "inventories/landslide/vietnam.geojson"


def folder(ws) -> Path:
    return Path(ws.root) / FOLDER


def _name(src: Path) -> str:
    s = re.sub(r"[^0-9A-Za-z_-]+", "_", src.stem.encode("ascii", "ignore").decode()).strip("_").lower()
    return s or "survey"


def _clean(v):
    """JSON-safe attribute: NaN and empty strings -> None, dates as ISO text, numpy scalars as Python."""
    if v is None:
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, datetime):
        return v.isoformat()
    return v if isinstance(v, (int, float, bool)) else str(v)


def import_survey(ws, src: Path | str, name: str | None = None, layer: str | None = None) -> dict:
    """Copy the features of ``src`` (first layer, or ``layer``) into ``surveys/<name>.geojson`` in WGS84, 2D;
    returns the name, the count and the path. An ``id`` attribute is kept as the feature id when unique."""
    import pyogrio
    import shapely
    src = Path(src)
    if not src.exists():
        raise DataError(f"survey file not found: {src}")
    df = pyogrio.read_dataframe(src, layer=layer)
    if df.crs is None:
        raise DataError(f"{src.name}: no coordinate system")
    df = df[df.geometry.notna() & ~df.geometry.is_empty].to_crs(4326)
    if df.empty:
        raise DataError(f"{src.name}: no feature with a geometry")
    name = name or _name(src)
    cols = [c for c in df.columns if c != "geometry"]
    ids = [str(x) for x in df["id"]] if "id" in df and df["id"].notna().all() else []
    if len(set(ids)) != len(df):
        ids = [str(i + 1) for i in range(len(df))]
    feats = []
    for i, (fid, (_, r)) in enumerate(zip(ids, df.iterrows())):
        g = shapely.force_2d(r.geometry)
        feats.append({"type": "Feature", "id": f"{name}:{fid}", "geometry": shapely.geometry.mapping(g),
                      "properties": {**{c: _clean(r[c]) for c in cols}, "layer": name}})
    out = folder(ws) / f"{name}.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "name": name, "source": str(src), "source_layer": layer or "",
          "imported": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "features": feats}
    out.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"name": name, "features": len(feats), "fields": cols, "path": str(out)}


def signature(ws) -> str:
    """Changes when a survey or the reported events change (cache key)."""
    files = sorted(folder(ws).glob("*.geojson")) + [p for p in [Path(ws.root) / REPORTED] if p.exists()]
    return ";".join(f"{f.name}:{f.stat().st_mtime_ns}" for f in files)


def collection(ws) -> dict:
    """The surveys and the reported events as one FeatureCollection; ``layers`` lists each with its count."""
    feats, layers = [], []
    for f in sorted(folder(ws).glob("*.geojson")):
        try:
            js = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        fs = [x for x in js.get("features", []) if x.get("geometry")]
        layers.append({"layer": js.get("name", f.stem), "kind": "survey", "n": len(fs), "source": js.get("source", ""),
                       "imported": js.get("imported", "")})
        feats += fs
    rep = Path(ws.root) / REPORTED
    if rep.exists():
        js = json.loads(rep.read_text(encoding="utf-8"))
        fs = []
        for x in js.get("features", []):
            p = x.get("properties", {})
            if x.get("geometry"):
                fs.append({**x, "id": f"reported:{p.get('id')}", "properties": {**p, "layer": "reported"}})
        layers.append({"layer": "reported", "kind": "reported", "n": len(fs), "source": "NASA GLC + curated events",
                       "imported": ""})
        feats += fs
    return {"type": "FeatureCollection", "layers": layers, "features": feats}


__all__ = ["collection", "import_survey", "signature"]
