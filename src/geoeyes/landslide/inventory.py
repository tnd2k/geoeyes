"""Landslide inventories of the workspace and their footprints (docs/en/research/landslide-susceptibility.md §3.1, L0).

Workspace files::

    cache/opendata/landslide/nasa_glc.csv            NASA Global Landslide Catalog export (data.nasa.gov)
    cache/opendata/landslide/das2024/raw/...         Das (2024) shapefiles (Zenodo 15596033, CC-BY-4.0)
    cache/opendata/boundaries/vnm_adm1.geojson       provinces (geoBoundaries VNM ADM1: 63 provinces, before 2025)
    inventories/landslide/curated_events.csv         reported events collected by hand (editable)
    inventories/landslide/vietnam.csv, .geojson      ``build_vietnam``: GLC + curated, one row per event
    inventories/landslide/central_vn_das2024.gpkg    ``build_das2024``: layers ``polygons`` and ``points``

``vietnam``: points outside Vietnam are dropped; two rows within 2 days and 10 km are one event (the more precise
location is kept, the other report goes to ``also_in``); ``usable`` = a slope failure located to 5 km or better.

Footprints (``footprints``): the area where an event's landslides were mapped is not published, so it is
approximated. ``near``: within 1 km of a mapped landslide, gaps under 3 km closed; ``hull``: the concave hull
(ratio 0.3) + 1 km; ``hull_shrunk``: the hull − 1 km. All minus the connected flat land (slope < 5°) larger than
1 km². L0 found the hull enclosing large unmapped areas (Ketsana): ``near`` is the main footprint.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

GLC = "cache/opendata/landslide/nasa_glc.csv"
DAS_RAW = "cache/opendata/landslide/das2024/raw/Landslide_data/Landslide_data"
ADM1 = "cache/opendata/boundaries/vnm_adm1.geojson"
FOLDER = "inventories/landslide"
DAS_CITATION = ("Das, R. (2024). Mapped landslides for Typhoon Ketsana, Molave and Tropical Storm Podul in central "
                "Vietnam [dataset]. Zenodo. https://doi.org/10.5281/zenodo.15596033 (CC-BY-4.0)")

# ---------------------------------------------------------------- reported events (points)
COLUMNS = ("id", "date", "date_precision", "province", "place", "lat", "lon", "accuracy_m", "type", "trigger",
           "storm", "fatalities", "injuries", "usable", "source_db", "source", "url", "also_in", "notes")
ACCURACY = {"exact": 1000, "500m": 500, "1km": 1000, "2km": 2000, "3km": 3000,
            "5km": 5000, "commune": 5000, "10km": 10000, "25km": 25000,
            "district": 25000, "50km": 50000, "province": 50000, "unknown": None}
SLOPE_TYPES = {"landslide", "debris_flow", "mudslide", "rock_fall", "complex", "flash_flood_landslide"}
CURATED_TYPES = {"rockfall": "rock_fall", "debris flow": "debris_flow",
                 "flash flood+landslide": "flash_flood_landslide"}
VN_BBOX = (102.0, 8.0, 110.0, 23.5)
COAST_TOL_DEG = 0.03              # ~3 km: simplified boundaries cut the coast, a point this near still counts
SAME_EVENT_DAYS, SAME_EVENT_KM = 2, 10.0
USABLE_ACCURACY_M = 5000


def _glc_rows(path: Path) -> list[dict]:
    out = []
    w, s, e, n = VN_BBOX
    with path.open(encoding="utf-8") as f:
        for x in csv.DictReader(f):
            if not x["latitude"] or x["country_name"] not in ("Vietnam", ""):
                continue
            lat, lon = float(x["latitude"]), float(x["longitude"])
            if not (s < lat < n and w < lon < e):
                continue
            d = datetime.strptime(x["event_date"][:10], "%m/%d/%Y").date().isoformat()
            out.append({"date": d, "date_precision": "day", "place": x["location_description"] or x["event_title"],
                        "lat": lat, "lon": lon, "accuracy_m": ACCURACY.get(x["location_accuracy"]),
                        "type": x["landslide_category"], "trigger": x["landslide_trigger"],
                        "storm": x["storm_name"], "fatalities": x["fatality_count"], "injuries": x["injury_count"],
                        "source_db": "nasa_glc", "source": x["source_name"], "url": x["source_link"],
                        "notes": f"GLC event {x['event_id']}: {x['event_title']}"})
    return out


def _curated_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8-sig") as f:
        for x in csv.DictReader(f):
            if not x.get("lat") or not x.get("lon"):
                continue
            acc = (x.get("accuracy") or "unknown").strip().lower()
            acc_key = next((k for k in ACCURACY if acc.startswith(k)), "unknown")
            date = x["date"].strip()
            t = (x.get("type") or "").strip().lower()
            out.append({"date": date, "date_precision": "day" if len(date) == 10 else "month",
                        "place": x.get("place", ""), "lat": float(x["lat"]), "lon": float(x["lon"]),
                        "accuracy_m": ACCURACY[acc_key], "type": CURATED_TYPES.get(t, t),
                        "trigger": x.get("trigger", ""), "storm": "", "fatalities": x.get("fatalities", ""),
                        "injuries": "", "source_db": "curated", "source": x.get("source", ""),
                        "url": x.get("url", ""), "notes": x.get("notes", "")})
    return out


def _km(a: dict, b: dict) -> float:
    dlat = math.radians(b["lat"] - a["lat"])
    dlon = math.radians(b["lon"] - a["lon"]) * math.cos(math.radians(a["lat"]))
    return 6371.0 * math.hypot(dlat, dlon)


def _day(r: dict) -> datetime:
    return datetime.fromisoformat(r["date"][:10] if len(r["date"]) >= 10 else r["date"] + "-15")


def build_vietnam(workspace: Path) -> dict:
    """``vietnam.csv`` and ``vietnam.geojson`` from the GLC export and ``curated_events.csv``."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    ws = Path(workspace)
    out_dir = ws / FOLDER
    feats = json.loads((ws / ADM1).read_text(encoding="utf-8"))["features"]
    polys = [shape(f["geometry"]) for f in feats]
    names = [f["properties"]["shapeName"] for f in feats]
    tree = STRtree(polys)

    rows, dropped = [], []
    for r in _glc_rows(ws / GLC) + _curated_rows(out_dir / "curated_events.csv"):
        p = Point(r["lon"], r["lat"])
        hit = [i for i in tree.query(p) if polys[i].contains(p)]
        if not hit:
            i = int(tree.nearest(p))
            if polys[i].distance(p) > COAST_TOL_DEG:
                dropped.append(r)
                continue
            hit = [i]
        r["province"] = names[hit[0]]
        rows.append(r)

    # one row per event: the more precise location first, curated before GLC at equal precision
    rows.sort(key=lambda r: (r["accuracy_m"] or 1e9, r["source_db"] != "curated"))
    kept: list[dict] = []
    for r in rows:
        twin = next((k for k in kept if abs((_day(k) - _day(r)).days) <= SAME_EVENT_DAYS
                     and _km(k, r) <= SAME_EVENT_KM), None)
        if twin is None:
            r["also_in"] = ""
            kept.append(r)
        else:       # same site, same days: one label; the other report stays traceable
            twin["also_in"] = ";".join(filter(None, [twin["also_in"], f"{r['source_db']}:{r['url']}"]))
    for r in kept:
        r["usable"] = int(r["type"] in SLOPE_TYPES and r["accuracy_m"] is not None
                          and r["accuracy_m"] <= USABLE_ACCURACY_M)
        r["id"] = hashlib.sha1(f"{r['date']}|{r['lat']:.4f}|{r['lon']:.4f}".encode()).hexdigest()[:10]
    kept.sort(key=lambda r: (r["date"], r["province"]))

    with (out_dir / "vietnam.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(kept)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": {k: r[k] for k in COLUMNS if k not in ("lat", "lon")}} for r in kept]}
    (out_dir / "vietnam.geojson").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    by_src: dict[str, int] = {}
    for r in kept:
        by_src[r["source_db"]] = by_src.get(r["source_db"], 0) + 1
    return {"events": len(kept), "by_source": by_src, "usable": sum(r["usable"] for r in kept),
            "dropped_outside_vietnam": [f"{d['date']} {d['place'][:40]}" for d in dropped]}


# ---------------------------------------------------------------- mapped polygons (Das 2024)
DAS_EVENTS = {"Ketsana": ("Ketsana_landslides/kesana_landslides/Ketsana_landslides.shp", "2009-09-29"),
              "Podul": ("Podul_landslides/Podul_landslides/Podul_landslides.shp", "2013-11-15"),
              "Molave": ("Molave_landslides/Molave_landslides/Molave_landslides.shp", "2020-10-28")}


def build_das2024(workspace: Path) -> dict:
    """``central_vn_das2024.gpkg`` in WGS84: ``polygons`` (event, storm date, src_fid, area_m2 in the source UTM,
    province, valid = 0 where the geometry was repaired) and ``points`` (a point inside each polygon)."""
    import geopandas as gpd
    import pandas as pd
    import shapely
    ws = Path(workspace)
    adm = gpd.read_file(ws / ADM1)[["shapeName", "geometry"]].rename(columns={"shapeName": "province"})
    parts, stats = [], {}
    for event, (rel, date) in DAS_EVENTS.items():
        g = gpd.read_file(ws / DAS_RAW / rel)
        area = g.geometry.area.to_numpy()                      # m², in the source UTM zone
        geom = g.geometry.to_crs(4326).to_numpy()
        valid = shapely.is_valid(geom)
        geom = np.where(valid, geom, shapely.make_valid(geom))
        # a repair can return lines or points beside the polygon: keep the area only
        polys = [shapely.MultiPolygon([q for q in shapely.get_parts(shapely.get_parts(x)) if q.geom_type == "Polygon"])
                 for x in geom]
        ok = np.array([not p.is_empty for p in polys])
        df = gpd.GeoDataFrame({"event": event, "date": date, "src_fid": np.arange(len(g))[ok],
                               "area_m2": np.round(area[ok], 1), "valid": valid[ok].astype(int)},
                              geometry=np.array(polys, dtype=object)[ok], crs=4326)
        parts.append(df)
        a = np.sort(area[ok])
        stats[event] = {"landslides": int(ok.sum()), "repaired": int((~valid[ok]).sum()),
                        "median_m2": round(float(a[len(a) // 2])), "p95_m2": round(float(a[int(len(a) * .95)])),
                        "total_km2": round(float(a.sum()) / 1e6, 2)}
    poly = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326)
    pts = poly.copy()
    pts["geometry"] = poly.geometry.representative_point()
    within = gpd.sjoin(pts[["geometry"]], adm, predicate="within", how="left")
    within = within[~within.index.duplicated()]
    miss = within["province"].isna()
    if miss.any():
        near = gpd.sjoin_nearest(pts.loc[miss, ["geometry"]], adm, how="left")
        within.loc[miss, "province"] = near[~near.index.duplicated()]["province"]
    poly["province"] = pts["province"] = within["province"].to_numpy()
    cols = ["event", "date", "src_fid", "area_m2", "province", "valid", "geometry"]
    out = ws / FOLDER / "central_vn_das2024.gpkg"
    out.unlink(missing_ok=True)
    poly[cols].to_file(out, layer="polygons", driver="GPKG")
    pts[cols].to_file(out, layer="points", driver="GPKG")
    return stats


# ---------------------------------------------------------------- footprints, area–frequency, overlaps
HULL_RATIO, BUFFER_M, SHRINK_M, CLOSE_M = 0.3, 1000.0, 1000.0, 1500.0
FLAT_DEG, FLAT_MIN_KM2 = 5.0, 1.0


def slope_deg(dem) -> np.ndarray:
    """Slope (degrees) of a ``geometry.dem.Dem`` on its own lat/lon grid."""
    lat = dem.lat0 - np.arange(dem.height.shape[0]) * dem.dlat
    dy = dem.dlat * 110_540.0
    dx = dem.dlon * 111_320.0 * np.cos(np.radians(lat))[:, None]
    gy, gx = np.gradient(dem.height.astype(np.float64))
    return np.degrees(np.arctan(np.hypot(gx / dx, gy / dy)))


def large_flats(dem, crs):
    """Connected land with slope < FLAT_DEG larger than FLAT_MIN_KM2, one (multi)polygon in ``crs``."""
    import geopandas as gpd
    import rasterio.features
    import shapely
    from rasterio.transform import from_origin
    from scipy import ndimage
    flat = slope_deg(dem) < FLAT_DEG
    lab, _ = ndimage.label(flat)
    lat_mid = dem.lat0 - dem.height.shape[0] * dem.dlat / 2
    cell_km2 = (dem.dlat * 110.54) * (dem.dlon * 111.32 * math.cos(math.radians(lat_mid)))
    keep = np.flatnonzero(np.bincount(lab.ravel()) * cell_km2 > FLAT_MIN_KM2)
    big = np.isin(lab, keep[keep > 0])
    tr = from_origin(dem.lon0 - dem.dlon / 2, dem.lat0 + dem.dlat / 2, dem.dlon, dem.dlat)
    geoms = [shapely.geometry.shape(g) for g, v in
             rasterio.features.shapes(big.astype(np.uint8), mask=big, transform=tr) if v == 1]
    return gpd.GeoSeries([shapely.union_all(geoms)], crs=4326).to_crs(crs).iloc[0]


def footprints(points, flats=None):
    """Footprint variants per event of ``points`` (GeoDataFrame in a metric CRS, column ``event``)."""
    import geopandas as gpd
    import shapely
    rows = []
    for ev, p in points.groupby("event", sort=False):
        hull = shapely.concave_hull(shapely.MultiPoint(list(p.geometry)), ratio=HULL_RATIO)
        near = shapely.union_all(list(p.geometry.buffer(BUFFER_M, 8))).buffer(CLOSE_M).buffer(-CLOSE_M)
        for variant, g in (("near", near), ("hull", hull.buffer(BUFFER_M)), ("hull_shrunk", hull.buffer(-SHRINK_M))):
            if flats is not None:
                g = g.difference(flats)
            g = g.buffer(0)
            rows.append({"event": ev, "variant": variant, "area_km2": round(g.area / 1e6, 1),
                         "n_landslides": len(p), "n_inside": int(p.within(g).sum()), "geometry": g})
    return gpd.GeoDataFrame(rows, crs=points.crs)


def power_tail(a: np.ndarray, min_tail: int = 50) -> dict | None:
    """Power-law tail of the areas (Clauset et al. 2009): the x_min that minimises the KS distance, and the MLE
    exponent alpha of the density p(A) ~ A^-alpha above it."""
    a = np.sort(np.asarray(a, float))
    best = None
    for xmin in np.quantile(a, np.linspace(0.05, 0.9, 60)):
        t = a[a >= xmin]
        if len(t) < min_tail:
            continue
        alpha = 1 + len(t) / np.sum(np.log(t / xmin))
        ks = np.max(np.abs(np.arange(1, len(t) + 1) / len(t) - (1 - (t / xmin) ** (1 - alpha))))
        if best is None or ks < best["ks"]:
            best = {"xmin_m2": float(xmin), "alpha": float(alpha), "n_tail": int(len(t)), "ks": float(ks)}
    return best


AREA_BINS = np.logspace(1, 6, 41)       # 10 m² to 1 km², 8 bins per decade


def area_frequency(areas: np.ndarray) -> dict:
    """Summary of a landslide area sample (m²): quantiles, the density peak (rollover), the power-law tail."""
    a = np.asarray(areas, float)
    h, e = np.histogram(a, AREA_BINS)
    dens = h / np.diff(e) / len(a)
    c = np.sqrt(e[:-1] * e[1:])
    return {"n": int(len(a)), "min_m2": float(a.min()), "median_m2": float(np.median(a)),
            "p95_m2": float(np.quantile(a, .95)), "max_m2": float(a.max()),
            "rollover_m2": float(c[np.argmax(dens)]), "below_900m2": int((a < 900).sum()),
            "tail": power_tail(a), "density": {"area_m2": c[h > 0].tolist(), "p": dens[h > 0].tolist()}}


def overlaps(polygons) -> dict:
    """Polygons of an event on those of another (reactivations); polygons of an event touching each other."""
    import geopandas as gpd
    import shapely
    out = {}
    events = list(dict.fromkeys(polygons["event"]))
    for i, a in enumerate(events):
        for b in events[:i] + events[i + 1:]:
            pa, pb = polygons[polygons.event == a], polygons[polygons.event == b]
            n = gpd.sjoin(pa, pb[["geometry"]], predicate="intersects", how="inner").index.nunique()
            out[f"{a}_on_{b}"] = {"n": int(n), "fraction": round(n / len(pa), 4)}
    for ev in events:
        p = polygons[polygons.event == ev].reset_index(drop=True)
        j = gpd.sjoin(p, p[["geometry"]], predicate="intersects", how="inner")
        j = j[j.index < j["index_right"]]
        inter = shapely.intersection(p.geometry.loc[j.index].values, p.geometry.loc[j["index_right"]].values)
        overlap = shapely.area(inter) > 1
        edge = ~overlap & (shapely.length(inter) > 0)
        out[f"{ev}_internal"] = {"pairs": int(len(j)), "overlapping_area": int(overlap.sum()),
                                 "shared_edge": int(edge.sum()), "point_touch": int((~overlap & ~edge).sum())}
    return out


def audit(workspace: Path, out_dir: Path, dem_cache: Path) -> dict:
    """L0 on the Das (2024) inventory: ``footprints.gpkg``, ``audit.json`` (footprints, area–frequency, overlaps)."""
    import geopandas as gpd

    from geoeyes.geometry.dem import load_copernicus30
    ws = Path(workspace)
    inv = ws / FOLDER / "central_vn_das2024.gpkg"
    polys = gpd.read_file(inv, layer="polygons")
    pts = gpd.read_file(inv, layer="points")
    crs = pts.estimate_utm_crs()
    w, s, e, n = pts.total_bounds
    dem = load_copernicus30(s - 0.05, n + 0.05, w - 0.05, e + 0.05, dem_cache)
    fp = footprints(pts.to_crs(crs), large_flats(dem, crs))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "footprints.gpkg").unlink(missing_ok=True)
    fp.to_crs(4326).to_file(out_dir / "footprints.gpkg", layer="footprints", driver="GPKG")
    res = {"citation": DAS_CITATION, "crs": str(crs),
           "footprints": fp.drop(columns="geometry").to_dict("records"),
           "area_frequency": {ev: area_frequency(g["area_m2"].to_numpy()) for ev, g in polys.groupby("event")},
           "overlaps": overlaps(polys.to_crs(crs))}
    (out_dir / "audit.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res
