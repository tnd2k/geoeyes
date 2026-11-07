"""Repeat-pass stacks among the open-data scenes.

Scenes go together when they share the source, the satellite (``Source.same_platform``) or the provider's repeat
ground track id, the imaging mode, pass direction and look side; then, within such a group, a scene joins the
first stack whose reference scene (its earliest) has an incidence within ``incidence_tol``, a look azimuth within
``azimuth_tol`` and a footprint overlapping by ``min_overlap`` of the smaller one. Only geometry from the STAC
items: the perpendicular baselines are known once the products are read (``build_stack`` logs them and leaves out
the scenes outside the reference geometry).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import pairwise
from statistics import median

from geoeyes.opendata.sources import SOURCES

_MODE_SHORT = {"stripmap": "sm", "spotlight": "sp", "sliding_spotlight": "sl", "scan": "sc", "scansar": "sc",
               "dwell": "dw", "topsar": "tp"}


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _fits(ref: dict, r: dict, ref_fp, fp, incidence_tol: float, azimuth_tol: float, min_overlap: float) -> bool:
    if ref["incidence"] is not None and r["incidence"] is not None \
            and abs(ref["incidence"] - r["incidence"]) > incidence_tol:
        return False
    if ref["look_azimuth"] is not None and r["look_azimuth"] is not None \
            and _angle_diff(ref["look_azimuth"], r["look_azimuth"]) > azimuth_tol:
        return False
    inter = ref_fp.intersection(fp).area
    return inter >= min_overlap * min(ref_fp.area, fp.area)


def stack_id(ref: dict, platforms: list[str]) -> str:
    """Stable, readable id from the reference scene: ``iceye:x53-sm-ar-26-28.2n016.7w``; a provider's repeat ground
    track adds a short hash of it (``-t3fa2``), as several tracks can share the other fields."""
    import hashlib

    from shapely.geometry import Polygon
    c = Polygon(ref["footprint"]).centroid
    plat = (platforms[0] if len(platforms) == 1 else "multi").replace("iceye-", "").replace("capella-", "c")
    plat = plat.replace("umbra-", "u")
    geo = f"{abs(c.y):.1f}{'n' if c.y >= 0 else 's'}{abs(c.x):05.1f}{'e' if c.x >= 0 else 'w'}"
    inc = f"{ref['incidence']:.0f}" if ref["incidence"] is not None else "x"
    track = f"-t{hashlib.sha1(ref['track'].encode()).hexdigest()[:4]}" if ref.get("track") else ""
    return (f"{ref['source']}:{plat}-{_MODE_SHORT.get(ref['mode'], ref['mode'][:2] or 'x')}-"
            f"{(ref['orbit_state'] or 'x')[0]}{(ref['look'] or 'x')[0]}-{inc}-{geo}{track}")


def find_stacks(scenes: list[dict], *, min_scenes: int = 3, aoi=None, incidence_tol: float | None = None,
                azimuth_tol: float | None = None, min_overlap: float = 0.5) -> list[dict]:
    """Candidate stacks (most dates first). ``aoi`` (w, s, e, n): only the scenes whose footprint covers it, the
    stacks being formed (and named) from all scenes, so an id does not depend on the AOI. Tolerances: those of each
    source (``Source.incidence_tol`` / ``azimuth_tol``) unless given."""
    from shapely.geometry import Polygon, box
    area = box(*aoi) if aoi is not None else None
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in scenes:
        src = SOURCES.get(r["source"])
        plat = r["platform"] if (src is None or src.same_platform) and not r.get("track") else ""
        groups[(r["source"], plat, r.get("track", ""), r["mode"], r["orbit_state"], r["look"])].append(r)
    out = []
    for (source, *_), members in groups.items():
        src = SOURCES.get(source)
        inc_tol = incidence_tol if incidence_tol is not None else (src.incidence_tol if src else 1.0)
        az_tol = azimuth_tol if azimuth_tol is not None else (src.azimuth_tol if src else 3.0)
        members.sort(key=lambda r: r["datetime"])
        clusters: list[tuple[dict, object, list[dict]]] = []
        for r in members:
            fp = Polygon(r["footprint"])
            for ref, ref_fp, lst in clusters:
                if _fits(ref, r, ref_fp, fp, inc_tol, az_tol, min_overlap):
                    lst.append(r)
                    break
            else:
                clusters.append((r, fp, [r]))
        for ref, _, lst in clusters:
            by_date: dict[str, dict] = {}
            for r in lst:                       # one scene per date (the first)
                if area is None or Polygon(r["footprint"]).covers(area):
                    by_date.setdefault(r["date"], r)
            if len(by_date) < min_scenes:
                continue
            out.append(_summary(ref, list(by_date.values()), stack_id(ref, sorted({r["platform"] for r in lst}))))
    seen: dict[str, int] = {}
    for s in sorted(out, key=lambda s: (s["id"], s["scenes"][0]["datetime"])):     # same fields, other cluster
        n = seen[s["id"]] = seen.get(s["id"], 0) + 1
        if n > 1:
            s["id"] = f"{s['id']}-{n}"
    out.sort(key=lambda s: (-s["n_dates"], s["id"]))
    return out


def _summary(ref: dict, lst: list[dict], sid: str) -> dict:
    from shapely.geometry import Polygon, mapping
    common = Polygon(lst[0]["footprint"])
    for r in lst[1:]:
        common = common.intersection(Polygon(r["footprint"]))
    if common.is_empty or common.geom_type != "Polygon":
        common = Polygon(ref["footprint"])
    dates = [date.fromisoformat(r["date"]) for r in lst]
    gaps = [(b - a).days for a, b in pairwise(dates)]
    platforms = sorted({r["platform"] for r in lst})
    inc = [r["incidence"] for r in lst if r["incidence"] is not None]
    src = SOURCES.get(ref["source"])
    return {"id": sid, "source": ref["source"], "sensor": src.sensor if src else None,
            "supported": bool(src and src.sensor), "product": ref.get("product", ""), "platforms": platforms,
            "track": ref.get("track", ""), "mode": ref["mode"], "orbit_state": ref["orbit_state"], "look": ref["look"],
            "polarization": ref["polarization"],
            "incidence": [min(inc), max(inc)] if inc else None, "n_dates": len(lst),
            "first": str(dates[0]), "last": str(dates[-1]), "span_days": (dates[-1] - dates[0]).days,
            "median_gap_days": median(gaps) if gaps else None, "min_gap_days": min(gaps) if gaps else None,
            "bbox": [round(v, 5) for v in common.bounds],
            "footprint": [[round(x, 5), round(y, 5)] for x, y in mapping(common.simplify(1e-4))["coordinates"][0]],
            "scenes": [{"id": r["id"], "date": r["date"], "datetime": r["datetime"], "platform": r["platform"],
                        "incidence": r["incidence"], "item": r["item"]} for r in lst]}


def get_stack(stacks: list[dict], sid: str) -> dict | None:
    return next((s for s in stacks if s["id"] == sid), None)
