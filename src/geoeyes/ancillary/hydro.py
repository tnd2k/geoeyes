"""Hydrography for the map: river network and watersheds over a view (web app, flood context).

rivers   OpenStreetMap waterways (Overpass): rivers, canals, streams, drains, tidal channels. OSM has the city
         canals (kênh, rạch) that drain or flood a delta city; HydroRIVERS (15 arc-second) does not. Over a
         wide view (> ``WIDE_DEG``) only rivers and canals are asked, to keep the answer small.
basins   HydroBASINS v1c level 12 (Lehner & Grill 2013, the finest Pfafstetter level, sub-basins of ~100 km²
         on average), clipped to the view. One archive per continent (Asia ~80 MB), downloaded once into the
         cache. On a flat delta the basin lines follow the DEM, not the canals: read them as the regional
         drainage frame, not as the drainage of a city block.

Both are GeoJSON FeatureCollections (EPSG:4326), cached per view (snapped to ``SNAP_DEG``).
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

from geoeyes.core.errors import DataError

log = logging.getLogger(__name__)

SNAP_DEG = 0.05
WIDE_DEG = 1.0
MAX_DEG = 6.0                       # larger views are refused (Overpass and the basin clip would be too large)
HYBAS = "https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_{reg}_lev{lev:02d}_v1c.zip"
# continents of HydroSHEDS (w, s, e, n), the first that holds the view's centre is used; "as" before "si" / "eu"
REGIONS = {"as": (57.0, -12.0, 180.0, 56.0), "au": (95.0, -56.0, 180.0, -10.0), "eu": (-25.0, 12.0, 70.0, 84.0),
           "af": (-19.0, -35.0, 55.0, 38.0), "na": (-138.0, 5.0, -52.0, 63.0), "sa": (-93.0, -56.0, -32.0, 15.0),
           "si": (58.0, 45.0, 180.0, 84.0), "ar": (-180.0, 51.0, -61.0, 84.0)}
KINDS = ("river", "canal", "tidal_channel", "stream", "drain", "ditch")


def snap(bbox: list[float]) -> list[float]:
    """The view (w, s, e, n) widened to the ``SNAP_DEG`` grid, so nearby views share a cache entry."""
    import math
    w, s, e, n = bbox
    if not (e > w and n > s):
        raise DataError(f"bad bbox {bbox}")
    if max(e - w, n - s) > MAX_DEG:
        raise DataError(f"view too large for hydrography ({e - w:.1f}° x {n - s:.1f}°, at most {MAX_DEG:g}°)")
    f = 1 / SNAP_DEG
    return [math.floor(w * f) / f, math.floor(s * f) / f, math.ceil(e * f) / f, math.ceil(n * f) / f]


def rivers(bbox: list[float], cache: Path) -> dict:
    """OSM waterways over ``bbox`` as LineStrings with ``kind`` and ``name``."""
    from geoeyes.ml.lines import overpass
    w, s, e, n = snap(bbox)
    wide = max(e - w, n - s) > WIDE_DEG
    kinds = KINDS[:3] if wide else KINDS
    box = f"({s:.4f},{w:.4f},{n:.4f},{e:.4f})"
    query = f'[out:json][timeout:180];way["waterway"~"^({"|".join(kinds)})$"]{box};out tags geom;'
    ways = overpass(query, cache, None, "waterways")
    feats = []
    for el in ways:
        tags = el.get("tags", {})
        coords = [[round(p["lon"], 6), round(p["lat"], 6)] for p in el["geometry"]]
        if len(coords) < 2:
            continue
        feats.append({"type": "Feature", "id": f"w{el['id']}",
                      "properties": {"kind": tags.get("waterway", ""), "name": tags.get("name", "")},
                      "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "bbox": [w, s, e, n], "source": "OpenStreetMap (ODbL), Overpass API",
            "kinds": list(kinds), "features": feats}


def _region(bbox: list[float]) -> str:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for reg, (w, s, e, n) in REGIONS.items():
        if w <= cx <= e and s <= cy <= n:
            return reg
    raise DataError(f"no HydroBASINS region holds {cx:.2f}, {cy:.2f}")


def _archive(reg: str, level: int, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"hybas_{reg}_lev{level:02d}_v1c.zip"
    if f.exists() and f.stat().st_size > 0:
        return f
    url = HYBAS.format(reg=reg, lev=level)
    log.info("HydroBASINS: downloading %s (once)", url)
    tmp = f.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "GeoEyes (InSAR analysis)"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise DataError(f"HydroBASINS unavailable: {exc}") from exc
    tmp.replace(f)
    return f


def basins(bbox: list[float], cache: Path, level: int = 12) -> dict:
    """HydroBASINS polygons of ``level`` over ``bbox``, clipped and simplified (~30 m)."""
    import geopandas as gpd
    from shapely.geometry import box as sbox
    from shapely.geometry import mapping
    w, s, e, n = snap(bbox)
    reg = _region([w, s, e, n])
    z = _archive(reg, level, cache)
    gdf = gpd.read_file(f"zip://{z}", bbox=(w, s, e, n))
    feats = []
    if not gdf.empty:
        clip = sbox(w, s, e, n)
        gdf["geometry"] = gdf.geometry.intersection(clip).simplify(0.0003, preserve_topology=True)
        gdf = gdf[~gdf.geometry.is_empty]
        for _, r in gdf.iterrows():
            feats.append({"type": "Feature", "id": f"b{int(r['HYBAS_ID'])}",
                          "properties": {"hybas_id": int(r["HYBAS_ID"]), "area_km2": float(r["SUB_AREA"]),
                                         "up_area_km2": float(r["UP_AREA"]), "coast": int(r.get("COAST", 0))},
                          "geometry": json.loads(json.dumps(mapping(r.geometry)))})
    return {"type": "FeatureCollection", "bbox": [w, s, e, n], "level": level,
            "source": f"HydroBASINS v1c level {level} (Lehner & Grill 2013), region {reg}", "features": feats}
