"""Event catalogue of dated landslides for the forecast system (docs/en/research/landslide-forecast-system.md, F1).

Sources, one schema:

* ``vietnam.csv`` of the inventories (curated reports and NASA GLC; points with a location accuracy);
* news and situation-report records harvested per storm (``<study>/catalogue/news_*.csv``: date, place names,
  source URL and a quote stating the date and place).

Steps:

1. place names normalised (no diacritics, no administrative prefixes) and matched to the GADM 4.1 units (pre-2025
   communes, districts, provinces); a record keeps the finest unit it reaches, its centroid, and the radius of a
   circle of the unit's area as its location accuracy; points of ``vietnam.csv`` get their commune by position;
2. records of the same commune (or district) within ± ``MERGE_DAYS`` merged into one event (sources counted);
3. the unit-day labels: events with a day-precise date located to a commune (or better).

Outputs: ``<study>/catalogue/catalogue.parquet`` (one row per event), ``catalogue.json`` (counts per year, province,
level), ``f1_report.md``.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CENTRAL = ("Nghệ An", "Hà Tĩnh", "Quảng Bình", "Quảng Trị", "Thừa Thiên Huế", "Đà Nẵng", "Quảng Nam", "Quảng Ngãi",
           "Bình Định", "Phú Yên", "Khánh Hòa", "Ninh Thuận", "Kon Tum", "Gia Lai", "Đắk Lắk", "Đắk Nông", "Lâm Đồng")
# provinces merged on 2025-07-01 -> the pre-2025 provinces a record may belong to
MERGED = {"da nang": ("da nang", "quang nam"), "quang ngai": ("quang ngai", "kon tum"),
          "hue": ("thua thien hue",), "quang tri": ("quang tri", "quang binh"), "gia lai": ("gia lai", "binh dinh"),
          "dak lak": ("dak lak", "phu yen"), "khanh hoa": ("khanh hoa", "ninh thuan"),
          "lam dong": ("lam dong", "dak nong", "binh thuan"), "ha tinh": ("ha tinh",), "nghe an": ("nghe an",)}
SLOPE_TYPES = ("landslide", "rock_fall", "debris_flow", "flash_flood_landslide", "complex", "mudslide")
MERGE_DAYS = 1
PREFIX = re.compile(r"^(xa|phuong|thi tran|tt|huyen|thi xa|tx|thanh pho|tp|tinh|quan|h\.|x\.)\s+")


def clean(s) -> str:
    """A place-name cell without its remarks: "(cũ)", "(khu vực)", " - Đà Lạt" suffixes."""
    s = re.sub(r"\(.*?\)", " ", str(s or ""))
    return s.split(" - ")[0].strip()


def norm(s) -> str:
    """Lower case, no diacritics (đ -> d), no administrative prefix, single spaces."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = str(s).strip().lower().replace("đ", "d")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(2):
        s = PREFIX.sub("", s)
    return s


@dataclass
class Admin:
    """GADM units with normalised names, centroids (lon / lat) and accuracy radii (m)."""

    units: pd.DataFrame          # level, gid, p, d, c (normalised names), name, lon, lat, radius_m
    communes: object             # GeoDataFrame of level 3 (for point lookup)

    @classmethod
    def load(cls, gpkg: Path) -> Admin:
        import geopandas as gpd
        rows = []
        g3 = None
        for level, layer in ((1, "ADM_ADM_1"), (2, "ADM_ADM_2"), (3, "ADM_ADM_3")):
            g = gpd.read_file(gpkg, layer=layer)
            m = g.to_crs(3405)                                  # VN-2000 / UTM 48N: areas and centroids
            cen = m.geometry.centroid.to_crs(4326)
            rows.append(pd.DataFrame({
                "level": level, "gid": g[f"GID_{level}"],
                "p": g["NAME_1"].map(norm), "d": g["NAME_2"].map(norm) if level >= 2 else "",
                "c": g["NAME_3"].map(norm) if level == 3 else "",
                "name": g[f"NAME_{level}"], "province": g["NAME_1"],
                "lon": cen.x.to_numpy(), "lat": cen.y.to_numpy(),
                "radius_m": np.sqrt(m.geometry.area.to_numpy() / np.pi)}))
            if level == 3:
                g3 = g[["GID_3", "NAME_1", "NAME_2", "NAME_3", "geometry"]]
        return cls(pd.concat(rows, ignore_index=True), g3)

    def locate(self, province, district, commune) -> dict | None:
        """The finest unit matching the names (a merged post-2025 province searches its former provinces; several
        communes or districts separated by ';' or ',' are tried in turn)."""
        p = norm(province)
        ps = MERGED.get(p, (p,)) if p else ()
        u = self.units
        cand = u[u.p.isin(ps)] if ps else u
        ds = [norm(clean(x)) for x in re.split(r"[;,]", str(district or "")) if norm(clean(x))] or [""]
        cs = [norm(clean(x)) for x in re.split(r"[;,]", str(commune or "")) if norm(clean(x))]
        for c in cs:
            hit = cand[(cand.level == 3) & (cand.c == c)]
            if len(hit) != 1:                                # ambiguous (or absent): the district decides
                hit = cand[(cand.level == 3) & (cand.c == c) & cand.d.isin(ds)]
            if len(hit) == 1:
                return hit.iloc[0].to_dict()
        for d in ds:
            if d:
                hit = cand[(cand.level == 2) & (cand.d == d)]
                if len(hit) == 1:
                    return hit.iloc[0].to_dict()
        if ps:
            hit = u[(u.level == 1) & (u.p == ps[0])]         # a merged province: the namesake former province
            if len(hit) == 1:
                return hit.iloc[0].to_dict()
        return None

    def commune_of(self, lon: np.ndarray, lat: np.ndarray) -> pd.DataFrame:
        """Commune (GID_3, names) of points; NaN outside every commune."""
        import geopandas as gpd
        pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon, lat), crs=4326)
        j = gpd.sjoin(pts, self.communes, how="left", predicate="within")
        return j[~j.index.duplicated()][["GID_3", "NAME_1", "NAME_2", "NAME_3"]]


class OsmGeocoder:
    """Place names (passes, road sections, post-2025 communes) located with OpenStreetMap Nominatim, within the centre
    of Vietnam; one request per second (the service's policy); answers cached in a CSV, so a rerun asks nothing."""

    URL = "https://nominatim.openstreetmap.org/search"
    AGENT = "GeoEyes-landslide-study/1.0"
    VIEWBOX = "104.5,20.0,110.0,10.5"
    MAX_RADIUS_M = 10000.0

    def __init__(self, cache_csv: Path):
        self.file = Path(cache_csv)
        self.cache: dict[str, dict | None] = {}
        if self.file.exists():
            for _, r in pd.read_csv(self.file, keep_default_na=False).iterrows():
                self.cache[r["query"]] = None if r["lon"] == "" else {
                    "lon": float(r["lon"]), "lat": float(r["lat"]), "radius_m": float(r["radius_m"]),
                    "name": r["name"], "kind": r.get("kind", "")}
        self._last = 0.0

    def __call__(self, query: str) -> dict | None:
        import time

        import requests
        if query in self.cache:
            return self.cache[query]
        wait = 1.1 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        hit = None
        try:
            r = requests.get(self.URL, params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "vn",
                                               "viewbox": self.VIEWBOX, "bounded": 1},
                             headers={"User-Agent": self.AGENT, "Accept-Language": "vi"}, timeout=30)
            js = r.json() if r.status_code == 200 else []
            if js:
                s, n, w, e = (float(v) for v in js[0]["boundingbox"])
                rad = 0.5 * float(np.hypot((n - s) * 111_000, (e - w) * 111_000 * np.cos(np.radians(0.5 * (s + n)))))
                hit = {"lon": float(js[0]["lon"]), "lat": float(js[0]["lat"]), "radius_m": max(rad, 500.0),
                       "name": js[0].get("display_name", "")[:200],
                       "kind": f"{js[0].get('category', '')}/{js[0].get('type', '')}"}
        except Exception as exc:                                      # network: the record stays unplaced
            log.debug("Nominatim %r: %s", query, exc)
            return None
        self.cache[query] = hit
        self.save()
        return hit

    def save(self):
        empty = {"lon": "", "lat": "", "radius_m": "", "name": "", "kind": ""}
        rows = [{"query": q, **(h or empty)} for q, h in self.cache.items()]
        self.file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(self.file, index=False)


ROAD = re.compile(r"^(quoc lo|ql|duong|dt|dh|tl|tinh lo|km|cao toc|huong lo|hl|doan)\b")


def osm_queries(r) -> list[tuple[str, str]]:
    """(query, kind) from the most to the least precise: a named place (a pass, a hill, a village — never a road
    or a kilometre: a road is not a location), then the (post-2025) commune, in the province."""
    place = clean(str(r.get("place", "")).split(";")[0].split(",")[0])
    if ROAD.match(norm(place)):
        place = ""
    prov = clean(r.get("province", ""))
    out = []
    for c in [clean(x) for x in re.split(r"[;,]", str(r.get("commune", "")))] + [""]:
        if place:
            out.append((", ".join(x for x in (place, c, prov) if x), "place"))
        if c:
            out.append((", ".join(x for x in (c, prov) if x), "commune"))
    return list(dict.fromkeys(q for q in out if q[0]))


def osm_accept(query: str, kind: str, hit: dict | None) -> bool:
    """An answer is kept only when its name is the name asked for (first component), and, for a commune, when it
    is an administrative boundary."""
    if not hit:
        return False
    asked = norm(query.split(",")[0])
    got = norm(str(hit.get("name", "")).split(",")[0])
    if not asked or not (asked == got or asked in got or got in asked):
        return False
    return kind != "commune" or str(hit.get("kind", "")).startswith("boundary/administrative")


COLUMNS = ["date", "date_precision", "province", "district", "commune", "gid", "level", "lon", "lat", "loc_accuracy_m",
           "type", "trigger", "storm", "fatalities", "source_db", "source_url", "evidence"]


def from_vietnam_csv(f: Path, admin: Admin) -> pd.DataFrame:
    """Day- or month-dated slope failures of ``vietnam.csv``, with their commune by position."""
    d = pd.read_csv(f)
    d["date"] = pd.to_datetime(d["date"], errors="coerce", format="mixed")
    d = d[d["date"].notna() & d["type"].isin(SLOPE_TYPES)].reset_index(drop=True)
    com = admin.commune_of(d["lon"].to_numpy(), d["lat"].to_numpy()).reset_index(drop=True)
    acc = d["accuracy_m"].fillna(25000.0)
    # a point located to <= 2 km keeps its commune; coarser points are only known to the province
    fine = acc <= 2000
    out = pd.DataFrame({
        "date": d["date"].dt.normalize(), "date_precision": d["date_precision"],
        "province": com["NAME_1"].fillna(d["province"]), "district": com["NAME_2"].where(fine),
        "commune": com["NAME_3"].where(fine), "gid": com["GID_3"].where(fine),
        "level": np.where(fine & com["GID_3"].notna(), "point", "province"),
        "lon": d["lon"], "lat": d["lat"], "loc_accuracy_m": acc, "type": d["type"], "trigger": d["trigger"],
        "storm": d["storm"], "fatalities": d["fatalities"], "source_db": d["source_db"], "source_url": d["url"],
        "evidence": d["notes"]})
    return out


def from_news(files: list[Path], admin: Admin, geocoder=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Harvested news records geocoded to the finest unit (``geocoder``: OSM for the names GADM does not hold, kept
    when finer than the GADM answer); also the records that could not be placed."""
    parts = [pd.read_csv(f, dtype=str, keep_default_na=False) for f in files if Path(f).exists()]
    if not parts:
        return pd.DataFrame(columns=COLUMNS), pd.DataFrame()
    n = pd.concat(parts, ignore_index=True)
    n["date"] = pd.to_datetime(n["date"], errors="coerce")
    n = n[n["date"].notna() & n["type"].isin(SLOPE_TYPES)].reset_index(drop=True)
    rows, lost = [], []
    for _, r in n.iterrows():
        u = admin.locate(r["province"], r["district"], r["commune"])
        lat = pd.to_numeric(r.get("lat"), errors="coerce")
        lon = pd.to_numeric(r.get("lon"), errors="coerce")
        if geocoder is not None and (u is None or u["level"] < 3) and not np.isfinite(lat):
            for q, kind in osm_queries(r):
                hit = geocoder(q)
                if not osm_accept(q, kind, hit):
                    continue
                com = admin.commune_of(np.array([hit["lon"]]), np.array([hit["lat"]])).iloc[0]
                if not (isinstance(com["GID_3"], str) and com["NAME_1"] in CENTRAL):
                    continue
                fine = hit["radius_m"] <= OsmGeocoder.MAX_RADIUS_M     # coarser: located, but not a commune label
                u = {"level": 3 if fine else 2, "gid": com["GID_3"] if fine else None, "province": com["NAME_1"],
                     "lon": hit["lon"], "lat": hit["lat"], "radius_m": hit["radius_m"], "osm": q}
                break
        if u is None and not (np.isfinite(lat) and np.isfinite(lon)):
            lost.append(r)
            continue
        level = {1: "province", 2: "district", 3: "commune"}[int(u["level"])] if u is not None else "point"
        if u is not None and "osm" in u:                    # a named place or a 2025 commune found in OpenStreetMap
            level = "osm" if u["gid"] else "osm_coarse"
        rows.append({
            "date": r["date"].normalize(), "date_precision": r["date_precision"] or "day",
            "province": u["province"] if u is not None else r["province"],
            "district": r["district"], "commune": r["commune"],
            "gid": u["gid"] if u is not None and u["level"] == 3 else (u["gid"] if u is not None else None),
            "level": level,
            "lon": lon if np.isfinite(lon) else u["lon"], "lat": lat if np.isfinite(lat) else u["lat"],
            "loc_accuracy_m": 1000.0 if level == "point" else float(u["radius_m"]),
            "type": r["type"], "trigger": r["trigger"], "storm": r["storm"],
            "fatalities": pd.to_numeric(r["fatalities"], errors="coerce"), "source_db": "news",
            "source_url": r["source_url"], "evidence": r["evidence"]})
    return pd.DataFrame(rows, columns=COLUMNS), pd.DataFrame(lost)


def merge_events(t: pd.DataFrame, days: int = MERGE_DAYS) -> pd.DataFrame:
    """Records of the same unit within ± ``days`` become one event: the earliest day-precise date, the finest
    location, the sources counted."""
    t = t.copy()
    t["key"] = t["gid"].fillna(t["province"].map(norm) + "|" + t["lon"].round(2).astype(str) + "," +
                               t["lat"].round(2).astype(str))
    rank = {"point": 0, "osm": 1, "commune": 1, "district": 2, "osm_coarse": 2, "province": 3}
    t["rk"] = t["level"].map(rank)
    t = t.sort_values(["key", "date"]).reset_index(drop=True)
    gap = t.groupby("key")["date"].diff().dt.days
    t["event"] = ((t["key"] != t["key"].shift()) | (gap > days)).cumsum()
    out = []
    for _, g in t.groupby("event"):
        best = g.sort_values(["rk", "date"]).iloc[0].to_dict()
        best["date"] = g.loc[g["date_precision"] == "day", "date"].min() if (g["date_precision"] == "day").any() \
            else g["date"].min()
        best["n_sources"] = len(g)
        best["sources"] = ";".join(sorted(set(g["source_db"].astype(str))))
        out.append(best)
    return pd.DataFrame(out).drop(columns=["key", "rk", "event"]).sort_values("date").reset_index(drop=True)


def unit_days(ev: pd.DataFrame) -> pd.DataFrame:
    """Positive commune-days: day-precise events located to a commune or a point."""
    ok = ev["date_precision"].eq("day") & ev["level"].isin(["commune", "point", "osm"]) & ev["gid"].notna()
    return ev.loc[ok, ["gid", "date", "province"]].drop_duplicates(["gid", "date"]).reset_index(drop=True)


MIN_MAPPED_SHARE = 0.5      # a commune is scored for a storm when at least half of it lies in the mapped extent


def storm_communes(study, admin: Admin) -> pd.DataFrame:
    """Storm-scale labels from the polygon inventory: for every event, each commune at least half inside the mapped
    extent (the main footprint of L0), its number of mapped landslides and their density per km² of mapped area.
    A commune with none is a true negative for that storm — what reports never give."""
    import geopandas as gpd
    pts = gpd.read_file(study.inventory, layer="points").to_crs(4326)
    fps = gpd.read_file(study.footprints, layer="footprints")
    com = admin.communes.to_crs(3405)
    com["area_km2"] = com.geometry.area / 1e6
    rows = []
    for ev, day in study.events:
        fp = fps[(fps.event == ev) & (fps.variant == study.footprint_main)].to_crs(3405)
        if fp.empty:
            continue
        inside = gpd.overlay(com[["GID_3", "NAME_1", "geometry", "area_km2"]], fp[["geometry"]], how="intersection")
        inside["mapped_km2"] = inside.geometry.area / 1e6
        inside = inside.groupby(["GID_3", "NAME_1"], as_index=False).agg(mapped_km2=("mapped_km2", "sum"),
                                                                         area_km2=("area_km2", "first"))
        inside = inside[inside.mapped_km2 >= MIN_MAPPED_SHARE * inside.area_km2]
        p = pts[pts.event == ev]
        c = admin.commune_of(p.geometry.x.to_numpy(), p.geometry.y.to_numpy())["GID_3"].value_counts()
        inside["n_landslides"] = inside.GID_3.map(c).fillna(0).astype(int)
        inside["density_km2"] = inside.n_landslides / inside.mapped_km2
        rows.append(inside.assign(event=ev, date=pd.Timestamp(day)))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return out.rename(columns={"GID_3": "gid", "NAME_1": "province"})


def run_catalogue(study, workspace_root: Path, cache: Path, progress=None) -> dict:
    """F1: the catalogue of the central provinces from 2015; ``catalogue.parquet``, ``catalogue.json``,
    ``f1_report.md``."""
    from geoeyes.io.manifest import atomic_write_json
    say = progress or (lambda m: log.info("%s", m))
    out_dir = study.step_dir("catalogue")
    out_dir.mkdir(parents=True, exist_ok=True)
    admin = Admin.load(cache / "admin" / "gadm41_VNM.gpkg")
    vn = from_vietnam_csv(Path(workspace_root) / "inventories" / "landslide" / "vietnam.csv", admin)
    news, lost = from_news(sorted(out_dir.glob("news_*.csv")), admin, OsmGeocoder(out_dir / "geocode_osm.csv"))
    say(f"F1: vietnam.csv {len(vn)} records, news {len(news)} placed, {len(lost)} not placed")
    allr = pd.concat([vn, news], ignore_index=True)
    allr = allr[allr["province"].isin(CENTRAL) & (allr["date"] >= "2015-01-01")]
    ev = merge_events(allr)
    ev["fatalities"] = pd.to_numeric(ev["fatalities"], errors="coerce")
    for c in ("date_precision", "province", "district", "commune", "gid", "level", "type", "trigger", "storm",
              "source_db", "source_url", "evidence", "sources"):
        ev[c] = ev[c].astype("string")
    pos = unit_days(ev)
    ev.to_parquet(out_dir / "catalogue.parquet", index=False)
    if len(lost):
        lost.to_csv(out_dir / "not_placed.csv", index=False)
    res = {"records": int(len(allr)), "events": int(len(ev)), "commune_days": int(len(pos)),
           "distinct_days": int(pos["date"].nunique()), "target_commune_days": 150,
           "by_year": {int(k): int(v) for k, v in pos.groupby(pos["date"].dt.year).size().items()},
           "by_province": pos.groupby("province").size().sort_values(ascending=False).astype(int).to_dict(),
           "by_level": ev["level"].value_counts().astype(int).to_dict(),
           "by_source": ev["sources"].value_counts().astype(int).to_dict(),
           "not_placed": int(len(lost))}
    sc = storm_communes(study, admin)
    if len(sc):
        sc.to_parquet(out_dir / "storm_communes.parquet", index=False)
        res["storms"] = {ev: {"date": str(g.date.iloc[0].date()), "communes_mapped": int(len(g)),
                              "with_landslides": int((g.n_landslides > 0).sum()),
                              "without": int((g.n_landslides == 0).sum()),
                              "landslides": int(g.n_landslides.sum())} for ev, g in sc.groupby("event")}
        say(f"F1: storm-scale labels {res['storms']}")
    atomic_write_json(out_dir / "catalogue.json", res)
    (out_dir / "f1_report.md").write_text(report_md(res), encoding="utf-8")
    return res


def report_md(r: dict) -> str:
    ok = r["commune_days"] >= r["target_commune_days"]
    L = ["# F1 — Event catalogue (central Vietnam, 2015–)", "",
         f"- records {r['records']} → events {r['events']} (same commune within ± {MERGE_DAYS} day merged)",
         f"- positive commune-days (day-precise, located to a commune): **{r['commune_days']}** on "
         f"{r['distinct_days']} distinct days; target {r['target_commune_days']}: **{'met' if ok else 'not met'}**",
         f"- events by location level: {r['by_level']}", f"- events by source: {r['by_source']}",
         f"- records that could not be placed: {r['not_placed']} (`not_placed.csv`)", "",
         "| year | commune-days |", "|---|---|"]
    L += [f"| {y} | {n} |" for y, n in r["by_year"].items()]
    L += ["", "| province | commune-days |", "|---|---|"]
    L += [f"| {p} | {n} |" for p, n in r["by_province"].items()]
    if r.get("storms"):
        L += ["", "## Storm-scale labels (polygon inventory, communes ≥ half inside the mapped extent)", "",
              "| storm | date | communes mapped | with landslides | without (true negatives) | landslides |",
              "|---|---|---|---|---|---|"]
        L += [f"| {ev} | {v['date']} | {v['communes_mapped']} | {v['with_landslides']} | {v['without']} | "
              f"{v['landslides']:,} |" for ev, v in r["storms"].items()]
    return "\n".join(L) + "\n"
