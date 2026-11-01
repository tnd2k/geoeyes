"""Inventory of reported flood locations (streets, junctions, landmarks), located on OpenStreetMap, to set against
the motion of the products: does the ground subside where the city floods?

Workspace files (shared by every project, one pair per region)::

    inventories/flood/<region>.csv       the inventory: one row per reported location, as announced (editable;
                                         rows are added by ``geoeyes floods import`` from a pasted list)
    inventories/flood/<region>.geojson   the same rows located (``geoeyes floods locate``)

Announcements (traffic police, Department of Construction...) give places in words: "Đường A, từ B đến C", "Giao lộ
A - B", "Ngã tư Bảy Hiền", "Trước số 139", with the cause (rain, tide) as a list heading. ``parse_list`` turns a
pasted list into rows; ``locate`` finds them on OSM: a street segment is cut between its crossings with B and C, a
junction is where the two streets meet, a landmark is searched by name. Every row keeps how it was located
(``located``) and nothing is guessed silently: a row OSM cannot place stays without geometry, and ``geom_wkt`` in the
CSV overrides the search (a correction by hand).

``near_product``: per location, the product's points within ``radius_m`` against those of the ring around it.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import logging
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "GeoEyes/1.0 (flood inventory; InSAR research)"

# regions: bbox (w, s, e, n) of the search and the name appended to place searches
REGIONS = {"hcmc": {"name": "Thành phố Hồ Chí Minh", "bbox": (106.33, 10.30, 107.62, 11.52)},
           "hanoi": {"name": "Hà Nội", "bbox": (105.28, 20.53, 106.03, 21.40)}}

COLUMNS = ("id", "region", "cause", "kind", "street", "from", "to", "cross", "place", "ward", "text", "reported",
           "source", "url", "depth_m", "geom_wkt", "notes")
CAUSES = ("rain", "tide", "rain_tide")
KINDS = ("segment", "junction", "street", "address", "place")

JUNCTION_TOL_M = 40.0          # two streets meet when their lines come this close
ENDPOINT_TOL_M = 400.0         # a place ending a segment (bridge, market) is taken when this close to the street
SAME_STREET_GAP_M = 2000.0     # parts of a name closer than this are one street; farther, namesakes
DOMINANT = 4.0                 # a street this many times longer than its namesakes is the one announced


# ---------------------------------------------------------------- parsing an announced list
def norm(s: str) -> str:
    """Comparable street name: NFC, lower case, without "đường", single spaces, "-" for dashes."""
    s = unicodedata.normalize("NFC", s or "").lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    s = re.sub(r"^(đường|tuyến đường|đường phố|phố)\s+", "", s)
    return s


def aliases(name: str) -> set[str]:
    """Normalised spellings OSM may use for an announced street name: "30-4" -> "30 tháng 4", "ĐT744" -> "đt 744",
    "tỉnh lộ 744"..., "đường 35" -> "35", "số 35"."""
    n = norm(name)
    out = {n}
    m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", n)
    if m:
        out.add(f"{m.group(1)} tháng {m.group(2)}")
    m = re.fullmatch(r"(?:đt|tl|tỉnh lộ|đường tỉnh)\s*\.?\s*(\w+)", n)
    if m:
        k = m.group(1)
        out |= {f"đt{k}", f"đt {k}", f"đt.{k}", f"tỉnh lộ {k}", f"đường tỉnh {k}", f"tl{k}", f"tl {k}"}
    m = re.fullmatch(r"(?:ql|quốc lộ)\s*\.?\s*(\w+)", n)
    if m:
        k = m.group(1)
        out |= {f"ql{k}", f"ql {k}", f"ql.{k}", f"quốc lộ {k}"}
    if re.fullmatch(r"\d+\w?", n):
        out.add(f"số {n}")
    m = re.fullmatch(r"số (\d+\w?)", n)
    if m:
        out.add(m.group(1))
    return out


_WARD = re.compile(r"\((?:khu vực\s+)?((?:phường|xã|đặc khu)\s+[^)]+)\)", re.I)
_PAREN = re.compile(r"\(([^)]*)\)")
_JOIN = r"\s+[-–]\s+"                                  # "A - B" (spaces: "30-4" is a name)
_NAME = r"[^,()]+?"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip(" .,;:-–+")


def _strip_prefix(s: str) -> str:
    return re.sub(r"^(giao lộ|giao|ngã tư|ngã ba|ngã 3|ngã 4)\s+", "", _clean(s), flags=re.I)


def parse_item(text: str, parent: str | None = None) -> dict:
    """One announced location -> row fields (kind, street, from, to, cross, place, ward)."""
    raw = _clean(unicodedata.normalize("NFC", text or ""))
    ward, rest = "", []
    for p in _PAREN.findall(raw):
        m = _WARD.match(f"({p})")
        if m and not ward:                               # "(phường Phú Mỹ, hướng từ ...)": ward, then a note
            ward, _, tail = _clean(m.group(1)).partition(",")
            ward = _clean(ward)
            rest += [tail] if _clean(tail) else []
        else:
            rest.append(p)
    notes = "; ".join(_clean(p) for p in rest if _clean(p))
    s = _clean(_PAREN.sub("", raw))
    row = {"text": raw, "ward": ward, "notes": notes, "street": "", "from": "", "to": "", "cross": "", "place": ""}
    lane = r"^(?:làn|đoạn|hướng|nhánh|hai bên|chân cầu|trước(?!\s+số))\b"     # "Trước số 139": an address

    def seg(street: str, a: str, b: str) -> dict:
        street = _clean(street)
        if parent and re.match(lane, street, re.I):     # "Làn SF, từ ..." under a street: that street
            street = parent
        return {**row, "kind": "segment", "street": street, "from": _strip_prefix(a), "to": _strip_prefix(b)}

    # "Đường A, (đoạn) từ B đến|về|ra C"
    m = re.match(rf"^(?:đường\s+)?({_NAME}),\s*(?:đoạn\s+|nhánh\s+)?(?:từ\s+)(.+?)\s+(?:đến|về|ra|tới)\s+(.+)$", s,
                 re.I)
    if m:
        return seg(m.group(1), m.group(2), m.group(3))
    # under a street: "(Đoạn) từ B đến C"
    m = re.match(r"^(?:đoạn\s+)?(?:hướng\s+)?từ\s+(.+?)\s+(?:đến|về|ra|tới|đi)\s+(.+)$", s, re.I)
    if m and parent:
        return seg(parent, m.group(1), m.group(2))
    # under a street, a place on it: "Hai bên cầu Bình Phước, trước số 2", "Đoạn qua xã Nhà Bè"
    if parent and re.match(lane, s, re.I):
        return {**row, "kind": "place", "street": parent, "place": s}
    # "Giao lộ A - B", "Giao A với B", "Ngã tư A - B", "Đường A - B"
    m = re.match(rf"^(?:giao lộ|giao|ngã tư|ngã ba|đường)\s+({_NAME})(?:{_JOIN}|\s+với\s+)({_NAME})$", s, re.I)
    if m:
        a, b = _clean(m.group(1)), _clean(m.group(2))
        b = re.sub(r",.*$", "", b)
        return {**row, "kind": "junction", "street": a, "cross": _strip_prefix(b)}
    # under a street: "Giao B" / "Giao lộ B"
    m = re.match(rf"^(?:giao lộ|giao)\s+({_NAME})(?:,.*)?$", s, re.I)
    if m and parent:
        return {**row, "kind": "junction", "street": parent, "cross": _clean(m.group(1))}
    # "Số 69 Trịnh Thị Dối", "Trước số 139" (under a street), "Đường Bến Nghé, số 4"
    m = re.match(rf"^(?:trước\s+)?số\s+([\w/]+)\s+(?:đường\s+)?({_NAME})$", s, re.I)
    if m and not parent:
        return {**row, "kind": "address", "street": _clean(m.group(2)), "place": f"số {m.group(1)}"}
    m = re.match(r"^(?:đường\s+)?([^,]+?),\s*(?:trước\s+)?số\s+([\w/]+)$", s, re.I)
    if m:
        return {**row, "kind": "address", "street": _clean(m.group(1)), "place": f"số {m.group(2)}"}
    if parent and re.match(r"^(?:trước\s+)?số\s+", s, re.I):
        return {**row, "kind": "address", "street": parent, "place": _clean(re.sub(r"^trước\s+", "", s, flags=re.I))}
    # a street of its own: "Đường X", "Quốc lộ 50", "Tỉnh lộ 10" (optionally ", <qualifier>")
    m = re.match(r"^(?:đường\s+)([^,]+?)(?:,\s*(.+))?$", s, re.I) or \
        re.match(r"^((?:quốc lộ|tỉnh lộ|hương lộ|ĐT|QL)\s*[\w.]+)(?:,\s*(.+))?$", s, re.I)
    if m:
        street, qual = _clean(m.group(1)), _clean(m.group(2) or "")
        if qual:
            return {**row, "kind": "place", "street": street, "place": qual}
        return {**row, "kind": "street", "street": street}
    # anything else under a street: a place along it ("Chân cầu Bà Tàng, trước số 2377", "Km43+300 ...")
    if parent:
        return {**row, "kind": "place", "street": parent, "place": s}
    return {**row, "kind": "place", "place": s}


def parse_list(text: str, *, cause: str | None = None, reported: str = "", source: str = "", url: str = "",
               region: str = "hcmc") -> list[dict]:
    """Rows from a pasted announcement: "- item" lines, "+ item" lines under a "- Street:" line; headings with
    "mưa" / "triều" set the cause of the items after them (``cause`` forces one)."""
    rows, parent, cur = [], None, cause
    for line in unicodedata.normalize("NFC", text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        bullet = re.match(r"^([-+•*])\s*(.*)$", s)
        if not bullet:
            if cause is None and re.search(r"triều", s, re.I) and re.search(r"mưa", s, re.I):
                cur = "rain_tide"
            elif cause is None and re.search(r"triều", s, re.I):
                cur = "tide"
            elif cause is None and re.search(r"mưa", s, re.I):
                cur = "rain"
            parent = None
            continue
        mark, body = bullet.groups()
        # "- Đoạn ...", "- Giao ..." right after "- Đường X:" still belong to X (lists mix "-" and "+")
        if mark == "-" and not (parent and re.match(r"^(đoạn|giao|từ|hướng|trước|số)\b", body, re.I)):
            parent = None
        if body.rstrip().endswith(":"):                    # "- Đường Lê Quang Đạo:" opens a group
            head = parse_item(body.rstrip(" :"))
            parent = head.get("street") or _clean(body.rstrip(" :"))
            continue
        r = parse_item(body, parent if mark != "-" or parent else None)
        r.update(region=region, cause=cur or "", reported=reported, source=source, url=url, depth_m="", geom_wkt="")
        rows.append(r)
    for r in rows:
        r["id"] = row_id(r)
    return rows


_STARTS = r"^(đường|phố|ngõ|ngách|hầm|gầm|nút|ngã|giao|khu|chân|bến|cầu|quốc lộ|tỉnh lộ|chợ|cổng|trước|số|km)\b"


def _split_top(s: str) -> list[str]:
    """Split on "," and ";" outside brackets."""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if ch in ",;" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [c for c in (x.strip() for x in [*out, cur]) if c]


def parse_prose(text: str, *, cause: str | None = "rain", reported: str = "", source: str = "", url: str = "",
                region: str = "hanoi") -> list[dict]:
    """Rows from reports written as sentences, e.g. Hanoi Drainage Company bulletins: "Lưu vực sông Nhuệ: Dương Đình
    Nghệ – Nam Trung Yên (sau Keangnam), Hoa Bằng (ngõ 99), Yên Nghĩa (từ bến xe Yên Nghĩa đến ngã ba Ba La)...".
    The text before ":" (a basin) goes to the notes; a bare name is a street ("phố"), "A – B" a junction."""
    rows = []
    for line in unicodedata.normalize("NFC", text or "").replace(chr(0xA0), " ").splitlines():
        s = line.strip().rstrip(".…").replace("...", "").replace("…", "")
        if not s:
            continue
        head, sep, body = s.partition(":")
        basin = _clean(head) if sep and len(head) < 60 else ""
        items = _split_top(body if basin else s)
        merged: list[str] = []
        for it in items:
            it = re.sub(r"^(và|cùng)\s+", "", it.strip(), flags=re.I)
            if merged and re.match(r"^(phường|xã)\s", it, re.I):    # "khu TT18, phường Phú La": the ward of the last
                merged[-1] += f" ({it})"
            elif it:
                merged.append(it)
        for it in merged:
            body_ = re.sub(r"^(phố|đường)\s+", "", it, flags=re.I)
            # a bare name is a street; places keep their own words ("hầm chui ...", "ngã ba ...")
            own = re.match(_STARTS, it, re.I) and not re.match(r"^(phố|đường)\s", it, re.I)
            text_ = it if own else f"Đường {body_}"
            m = re.match(r"^nút giao\s+(.+?)\s+(?:giao|với|[-–])\s+(.+)$", it, re.I)
            if m:                                        # "nút giao Lương Thế Vinh giao Tố Hữu"
                text_ = f"Giao lộ {m.group(1)} - {m.group(2)}"
            m = re.match(r"^(?:số\s+)?(\d+\w?)\s+([^\d(][^(]*)$", body_)
            if m and not own:                            # "165 Thái Hà": a house number on a street
                text_ = f"Số {m.group(1)} {m.group(2)}"
            r = parse_item(text_)
            r["text"] = it
            if r.get("street"):                          # "Đội Cấn và ngõ 100 Đội Cấn", "Lê Đức Thọ quanh ..."
                r["street"] = _clean(re.split(r"\s+(?:và|quanh|xung quanh|trước|đoạn|khu vực)\s+", r["street"])[0])
            # "Thụy Khuê (trường Chu Văn An – dốc La Pho)": the spot is the place in brackets, on that street
            if r["kind"] == "street" and r.get("notes") and not re.search(r"\btừ\b", r["notes"]):
                r.update(kind="place", place=r["notes"].split(";")[0].split("–")[0].strip())
            if basin:
                r["notes"] = "; ".join(v for v in (basin, r.get("notes", "")) if v)
            # "Yên Nghĩa (từ bến xe Yên Nghĩa đến ngã ba Ba La)": the stretch is in the brackets
            m = re.search(r"\(\s*(?:đoạn\s+)?từ\s+(.+?)\s+(?:đến|tới)\s+(.+?)\)", it, re.I)
            if m and r["kind"] in ("street", "place") and r.get("street"):
                r.update(kind="segment", **{"from": _strip_prefix(m.group(1)), "to": _strip_prefix(m.group(2))})
            r.update(region=region, cause=cause or "", reported=reported, source=source, url=url, depth_m="",
                     geom_wkt="")
            rows.append(r)
    for r in rows:
        r["id"] = row_id(r)
    return rows


def row_id(r: dict) -> str:
    key = "|".join(str(r.get(k, "")) for k in ("region", "cause", "text", "reported", "source"))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- inventory files
def folder(ws) -> Path:
    return Path(ws.root) / "inventories" / "flood"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{c: (r.get(c) or "").strip() for c in COLUMNS} for r in csv.DictReader(f)]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:      # BOM: Excel opens Vietnamese correctly
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    tmp.replace(path)


def add_rows(ws, region: str, new: list[dict]) -> tuple[int, int]:
    """Append rows not already in the inventory (same id); returns (added, total)."""
    path = folder(ws) / f"{region}.csv"
    rows = read_csv(path)
    have = {r["id"] for r in rows}
    fresh = [r for r in new if r["id"] not in have]
    write_csv(path, rows + fresh)
    return len(fresh), len(rows) + len(fresh)


# ---------------------------------------------------------------- OSM
def _http_json(url: str, data: bytes | None = None, timeout: float = 300, attempts: int = 3):
    last = None
    for k in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:                           # Overpass answers 429 / 504 under load: wait, again
            last = exc
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"{url}: {last}")


def _rx(names: list[str]) -> str:
    return "|".join(re.escape(n) for n in names)


def osm_streets(names: set[str], bbox, cache: Path, progress: Callable[[str], None] | None = None) -> list[dict]:
    """OSM highways whose name (or alt / old name, ref) is one of ``names`` (normalised), with geometry; cached per
    name so later imports only ask for new streets."""
    cache.mkdir(parents=True, exist_ok=True)
    w, s, e, n = bbox
    tag = hashlib.sha1(json.dumps([round(v, 3) for v in bbox]).encode()).hexdigest()[:8]
    out, todo = [], []
    for nm in sorted(names):
        f = cache / f"street2_{tag}_{hashlib.sha1(nm.encode()).hexdigest()[:16]}.json"
        if f.exists():
            out += json.loads(f.read_text(encoding="utf-8"))
        else:
            todo.append(nm)
    for i in range(0, len(todo), 25):
        part = todo[i:i + 25]
        if progress:
            progress(f"OSM streets {i + len(part)}/{len(todo)}")
        rx = _rx(part)
        pre = "((Đường|đường|Phố|phố|Ngõ|ngõ) )?"                 # OSM names: "Phố Hoa Bằng", "Đường Láng"
        q = (f'[out:json][timeout:240];(way["highway"]["name"~"^{pre}({rx})$",i]({s},{w},{n},{e});'
             f'way["highway"]["alt_name"~"^{pre}({rx})$",i]({s},{w},{n},{e});'
             f'way["highway"]["old_name"~"^{pre}({rx})$",i]({s},{w},{n},{e});'
             f'way["highway"]["ref"~"^({rx})$",i]({s},{w},{n},{e}););out tags geom;')
        js = _http_json(OVERPASS, urllib.parse.urlencode({"data": q}).encode())
        ways = [{"id": el["id"], "tags": el.get("tags", {}),
                 "coords": [[p["lon"], p["lat"]] for p in el.get("geometry", [])]}
                for el in js.get("elements", []) if el.get("type") == "way" and el.get("geometry")]
        for nm in part:
            mine = [wy for wy in ways if nm in _way_names(wy["tags"])]
            f = cache / f"street2_{tag}_{hashlib.sha1(nm.encode()).hexdigest()[:16]}.json"
            f.write_text(json.dumps(mine), encoding="utf-8")
            out += mine
    return out


def _way_names(tags: dict) -> set[str]:
    out = set()
    for k in ("name", "name:vi", "alt_name", "old_name", "official_name", "ref"):
        for v in str(tags.get(k, "")).split(";"):
            if v.strip():
                out.add(norm(v))
    return out


def nominatim(q: str, bbox, cache: Path) -> dict | None:
    """First Nominatim hit inside the region (cached; 1 request per second, the service's rule)."""
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"nominatim_{hashlib.sha1(q.encode()).hexdigest()[:16]}.json"
    if f.exists():
        js = json.loads(f.read_text(encoding="utf-8"))
    else:
        w, s, e, n = bbox
        url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "bounded": 1,
                                                        "viewbox": f"{w},{n},{e},{s}", "countrycodes": "vn"})
        time.sleep(1.1)
        js = _http_json(url, timeout=60)
        f.write_text(json.dumps(js), encoding="utf-8")
    return js[0] if js else None


# ---------------------------------------------------------------- locating
@dataclass
class _Frame:
    """Local metric frame (equirectangular around the region centre): metres <-> degrees."""
    lon0: float
    lat0: float
    k: float = field(init=False)

    def __post_init__(self):
        self.k = float(np.cos(np.radians(self.lat0)))

    def fwd(self, coords):
        a = np.asarray(coords, dtype=np.float64)
        return np.column_stack([(a[:, 0] - self.lon0) * 111_320.0 * self.k, (a[:, 1] - self.lat0) * 110_574.0])

    def inv(self, xy):
        a = np.asarray(xy, dtype=np.float64)
        return np.column_stack([a[:, 0] / (111_320.0 * self.k) + self.lon0, a[:, 1] / 110_574.0 + self.lat0])


class Locator:
    """Streets (by normalised name) as merged lines in metres, and the rules that place a row on them."""

    def __init__(self, ways: list[dict], frame: _Frame, place: Callable[[str], tuple[float, float] | None]):
        from shapely.geometry import LineString, MultiLineString
        from shapely.ops import linemerge
        self.f, self.place = frame, place
        by: dict[str, list] = {}
        for wy in ways:
            if len(wy["coords"]) < 2:
                continue
            line = LineString(frame.fwd(wy["coords"]))
            for nm in _way_names(wy["tags"]):
                by.setdefault(nm, []).append(line)
        self.streets = {}
        for nm, lines in by.items():
            merged = linemerge(MultiLineString(lines))
            self.streets[nm] = list(getattr(merged, "geoms", [merged]))

    def parts(self, name: str) -> list:
        seen, out = set(), []
        for a in aliases(name):
            for p in self.streets.get(a, []):
                if id(p) not in seen:
                    seen.add(id(p))
                    out.append(p)
        return out

    def _pt(self, xy):
        return [float(v) for v in self.f.inv(np.asarray([xy]))[0]]

    def junction(self, a: str, b: str):
        """Nearest meeting of streets ``a`` and ``b`` (point in metres) and the part of ``a`` it is on."""
        from shapely.ops import nearest_points
        best = None
        for pa in self.parts(a):
            for pb in self.parts(b):
                d = pa.distance(pb)
                if d <= JUNCTION_TOL_M and (best is None or d < best[0]):
                    p, _ = nearest_points(pa, pb)
                    best = (d, p, pa)
        return (best[1], best[2]) if best else (None, None)

    def endpoint(self, street: str, what: str):
        """Where ``what`` (a crossing street, a bridge, a market...) meets ``street``: (point, part, how)."""
        from shapely.geometry import Point
        p, part = self.junction(street, what)
        if p is not None:
            return p, part, "junction"
        ll = self.place(what)
        if ll is None:
            return None, None, ""
        q = Point(self.f.fwd([ll])[0])
        cand = [(pa.distance(q), pa) for pa in self.parts(street)]
        if not cand:
            return None, None, ""
        d, pa = min(cand, key=lambda c: c[0])
        if d > ENDPOINT_TOL_M:
            return None, None, ""
        return pa.interpolate(pa.project(q)), pa, "place"

    def locate(self, r: dict) -> tuple[dict | None, str]:
        """(GeoJSON geometry, how located): exact | approx | place | manual | none."""
        from shapely import wkt
        from shapely.geometry import mapping
        from shapely.ops import substring
        if r.get("geom_wkt"):
            return mapping(wkt.loads(r["geom_wkt"])), "manual"
        kind, street = r.get("kind"), r.get("street", "")
        if kind == "junction":
            p, _ = self.junction(street, r.get("cross", ""))
            if p is not None:
                return {"type": "Point", "coordinates": self._pt((p.x, p.y))}, "exact"
            ll = self.place(f"{street} {r.get('cross', '')}")
            return ({"type": "Point", "coordinates": list(ll)}, "place") if ll else (None, "none")
        if kind == "segment":
            pa, part_a, how_a = self.endpoint(street, r.get("from", ""))
            pb, _, how_b = self.endpoint(street, r.get("to", ""))
            if pa is not None and pb is not None and pa.distance(pb) >= 5:
                # the stretch on every part of that street between the two ends (both carriageways of an avenue)
                group = next((g for g in self._groups(self.parts(street)) if any(p is part_a for p in g)), [part_a])
                mid = type(pa)((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)
                reach = pa.distance(pb) / 2 + 150.0
                pieces = []
                for part in group:
                    d1, d2 = sorted((part.project(pa), part.project(pb)))
                    if d2 - d1 < 5:
                        continue
                    s = substring(part, d1, d2)
                    ends = [type(pa)(*s.coords[0]), type(pa)(*s.coords[-1])]
                    if all(e.distance(mid) <= reach for e in ends) and s.length <= 3 * pa.distance(pb) + 300:
                        pieces.append(s)
                if pieces:
                    how = "exact" if how_a == how_b == "junction" else "approx"
                    if len(pieces) == 1:
                        return self._line(pieces[0]), how
                    lines = [self._line(p)["coordinates"] for p in pieces]
                    return {"type": "MultiLineString", "coordinates": lines}, how
            one = pa if pa is not None else pb
            if one is not None:                        # one end found: the point, the rest is unknown
                return {"type": "Point", "coordinates": self._pt((one.x, one.y))}, "approx"
            return self._street(street, r.get("ward", ""))
        if kind == "street":
            return self._street(street, r.get("ward", ""))
        if kind in ("address", "place"):
            q = " ".join(v for v in (r.get("place", ""), street) if v)
            ll = self.place(q) if q else None
            if ll is not None and street and self.parts(street):
                from shapely.geometry import Point
                pt = Point(self.f.fwd([ll])[0])
                d, pa = min(((pa.distance(pt), pa) for pa in self.parts(street)), key=lambda c: c[0])
                if d <= ENDPOINT_TOL_M:
                    s = pa.interpolate(pa.project(pt))
                    return {"type": "Point", "coordinates": self._pt((s.x, s.y))}, "place"
            if ll is not None and not street:
                return {"type": "Point", "coordinates": list(ll)}, "place"
            if street:
                g, how = self._street(street, r.get("ward", ""))
                return g, ("approx" if g else how)
            return None, "none"
        return None, "none"

    def near(self, street: str, context: list[tuple[float, float]], max_m: float = 3_000.0) -> dict | None:
        """The namesake of ``street`` nearest the median of ``context`` (lon, lat), if within ``max_m`` of it."""
        from shapely.geometry import Point
        parts = self.parts(street)
        if not parts or not context:
            return None
        c = Point(np.median(self.f.fwd(context), axis=0))
        g = min(self._groups(parts), key=lambda grp: min(p.distance(c) for p in grp))
        if min(p.distance(c) for p in g) > max_m:
            return None
        lines = [self._line(p)["coordinates"] for p in g]
        return {"type": "LineString", "coordinates": lines[0]} if len(lines) == 1 else \
            {"type": "MultiLineString", "coordinates": lines}

    @staticmethod
    def _groups(parts: list, gap_m: float = SAME_STREET_GAP_M) -> list[list]:
        """Parts of a street name grouped by proximity: one group per distinct street of that name (dual
        carriageways and pieces split by a bridge stay together)."""
        n = len(parts)
        label = list(range(n))

        def root(i):
            while label[i] != i:
                label[i] = label[label[i]]
                i = label[i]
            return i

        for i in range(n):
            for j in range(i + 1, n):
                if root(i) != root(j) and parts[i].distance(parts[j]) <= gap_m:
                    label[root(i)] = root(j)
        out: dict[int, list] = {}
        for i in range(n):
            out.setdefault(root(i), []).append(parts[i])
        return list(out.values())

    def _line(self, line) -> dict:
        xy = np.asarray(line.coords)
        return {"type": "LineString", "coordinates": [[round(a, 6), round(b, 6)] for a, b in self.f.inv(xy)]}

    def _street(self, street: str, ward: str) -> tuple[dict | None, str]:
        """The whole street: its parts, or (when several far apart) the part nearest the ward."""
        from shapely.geometry import Point
        parts = self.parts(street)
        if not parts:
            return None, "none"
        groups = sorted(self._groups(parts), key=lambda g: -sum(p.length for p in g))
        size = [sum(p.length for p in g) for g in groups]
        if len(groups) > 1 and size[0] >= 2_000 and size[0] >= DOMINANT * size[1]:
            groups = groups[:1]                        # the avenue, and short namesakes (a lane, a stub)
        if len(groups) > 1:                            # the same name in distinct places ("Đường số 2")
            ll = self.place(ward) if ward else None
            if ll is None:
                return None, "ambiguous"
            q = Point(self.f.fwd([ll])[0])
            parts = min(groups, key=lambda g: min(pa.distance(q) for pa in g))
        lines = [self._line(pa)["coordinates"] for pa in parts]
        geom = {"type": "LineString", "coordinates": lines[0]} if len(lines) == 1 else \
            {"type": "MultiLineString", "coordinates": lines}
        return geom, "approx"


def _anchor_ll(geom: dict) -> tuple[float, float]:
    """A representative (lon, lat) of a geometry: the point, or the middle vertex of a line."""
    c = geom["coordinates"]
    if geom["type"] == "Point":
        return float(c[0]), float(c[1])
    pts = c if geom["type"] == "LineString" else [p for ln in c for p in ln]
    return float(pts[len(pts) // 2][0]), float(pts[len(pts) // 2][1])


def locate(ws, region: str = "hcmc", *, progress: Callable[[str], None] | None = None) -> dict:
    """Locate every row of ``<region>.csv`` on OSM -> ``<region>.geojson``; returns counts per ``located``."""
    reg = REGIONS[region]
    rows = read_csv(folder(ws) / f"{region}.csv")
    cache = Path(ws.cache_dir("osm")) / "flood"
    names = set()
    for r in rows:
        for k in ("street", "cross", "from", "to"):
            v = r.get(k, "")
            # ends that are not streets (a house number, a bridge, a market...) are searched as places
            if v and (k == "street" or not re.match(r"^(số|km|cầu|chợ|cổng|trường|ubnd|hẻm|trước|điểm)\b", v, re.I)):
                names |= aliases(v)
    names.discard("")
    ways = osm_streets(names, reg["bbox"], cache, progress)
    w, s, e, n = reg["bbox"]
    frame = _Frame((w + e) / 2, (s + n) / 2)

    def place(q: str):
        hit = nominatim(f"{q}, {reg['name']}", reg["bbox"], cache) if q else None
        return (float(hit["lon"]), float(hit["lat"])) if hit else None

    loc = Locator(ways, frame, place)
    feats, counts = [], {}
    for i, r in enumerate(rows):
        if progress and i % 10 == 0:
            progress(f"locating {i + 1}/{len(rows)}")
        try:
            geom, how = loc.locate(r)
        except Exception as exc:                       # a bad row must not stop the others
            log.warning("flood inventory %s: %s", r.get("id"), exc)
            geom, how = None, "none"
        feats.append({"type": "Feature", "id": r["id"], "geometry": geom,
                      "properties": {**{k: r.get(k, "") for k in COLUMNS if k != "geom_wkt"}, "located": how}})
    # a street name found in several places: the one near the other spots of the same bulletin (same date, source
    # and basin / area note), when they are close together
    for f, r in zip(feats, rows, strict=True):
        if f["properties"]["located"] != "ambiguous":
            continue
        ctx = [g["geometry"] for g, s in zip(feats, rows, strict=True)
               if g["geometry"] and g["properties"]["located"] in ("exact", "place", "manual", "approx")
               and (s["reported"], s["source"], s["notes"].split(";")[0]) ==
                   (r["reported"], r["source"], r["notes"].split(";")[0])]
        if len(ctx) >= 2:
            geom = loc.near(r.get("street", ""), [_anchor_ll(g) for g in ctx])
            if geom:
                f["geometry"], f["properties"]["located"] = geom, "approx"
    for f in feats:
        counts[f["properties"]["located"]] = counts.get(f["properties"]["located"], 0) + 1
    out = folder(ws) / f"{region}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "region": region, "features": feats},
                              ensure_ascii=False), encoding="utf-8")
    log.info("flood inventory %s: %d rows located -> %s (%s)", region, len(rows), out, counts)
    return {"rows": len(rows), "located": counts, "path": str(out)}


def collection(ws) -> dict:
    """Every located region as one FeatureCollection (rows without geometry included: the list shows them)."""
    feats, regions = [], []
    for f in sorted(folder(ws).glob("*.geojson")):
        try:
            js = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        csv_path = f.with_suffix(".csv")
        regions.append({"region": f.stem, "n": len(js.get("features", [])),
                        "stale": csv_path.exists() and csv_path.stat().st_mtime > f.stat().st_mtime})
        feats += js.get("features", [])
    return {"type": "FeatureCollection", "regions": regions, "features": feats}


# ---------------------------------------------------------------- against a product
def _densify(geom: dict, frame: _Frame, step_m: float = 10.0) -> np.ndarray:
    """Points every ``step_m`` along a (multi)line, or the point itself, in metres."""
    t = geom["type"]
    if t == "Point":
        return frame.fwd([geom["coordinates"]])
    lines = [geom["coordinates"]] if t == "LineString" else geom["coordinates"]
    out = []
    for ln in lines:
        xy = frame.fwd(ln)
        for a, b in itertools.pairwise(xy):
            k = max(int(np.ceil(np.hypot(*(b - a)) / step_m)), 1)
            out.append(a + (b - a) * np.linspace(0, 1, k, endpoint=False)[:, None])
        out.append(xy[-1:])
    return np.vstack(out)


def near_product(fc: dict, lon: np.ndarray, lat: np.ndarray, vel: np.ndarray, *, radius_m: float = 100.0,
                 ring_m: float = 500.0) -> dict:
    """Per located row: the points within ``radius_m`` (n, median and 10th percentile velocity, rank of the median
    among all points) and the median of the ring ``radius_m``..``ring_m`` around it (contrast = near - ring)."""
    from scipy.spatial import cKDTree
    ok = np.isfinite(vel)
    lon, lat, vel = lon[ok], lat[ok], vel[ok].astype(np.float64)
    frame = _Frame(float(np.median(lon)), float(np.median(lat)))
    tree = cKDTree(frame.fwd(np.column_stack([lon, lat])))
    srt = np.sort(vel)
    rows = {}
    for f in fc.get("features", []):
        g = f.get("geometry")
        if not g:
            continue
        pts = _densify(g, frame)
        near = set().union(*tree.query_ball_point(pts, radius_m))
        if not near:
            rows[f["id"]] = {"n": 0}
            continue
        ring = set().union(*tree.query_ball_point(pts, ring_m)) - near
        v = vel[np.fromiter(near, int)]
        med = float(np.median(v))
        r = {"n": int(v.size), "vel_median": round(med, 2), "vel_p10": round(float(np.percentile(v, 10)), 2),
             "rank": round(float(np.searchsorted(srt, med) / srt.size), 3)}
        if ring:
            rm = float(np.median(vel[np.fromiter(ring, int)]))
            r.update(ring_n=len(ring), ring_median=round(rm, 2), contrast=round(med - rm, 2))
        rows[f["id"]] = r
    meds = [r["vel_median"] for r in rows.values() if r.get("n")]
    return {"radius_m": radius_m, "ring_m": ring_m, "product_median": round(float(np.median(vel)), 2),
            "n_located": sum(1 for f in fc.get("features", []) if f.get("geometry")), "n_with_points": len(meds),
            "median_of_rows": round(float(np.median(meds)), 2) if meds else None, "rows": rows}


__all__ = ["add_rows", "collection", "locate", "near_product", "parse_item", "parse_list", "parse_prose"]
