"""Open SAR STAC catalogs and the mapping of their items to one scene record.

Scene record (JSON): ``source``, ``id``, ``item`` (item URL), ``datetime`` (ISO UTC), ``date``, ``platform``,
``mode`` (stripmap | spotlight | sliding_spotlight | ...), ``orbit_state``, ``look`` (right | left), ``incidence``
and ``look_azimuth`` (deg, None when absent), ``polarization``, ``track`` (repeat ground track id when the provider
gives one), ``bbox`` [w, s, e, n], ``footprint`` (exterior ring, lon/lat), ``product`` (complex product format),
``slc`` and ``meta`` (asset URLs).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    homepage: str
    license: str
    roots: tuple[str, ...]          # catalog / collection JSON walked by ``crawl``
    sensor: str | None              # GeoEyes sensor whose reader opens the complex product; None = search only
    same_platform: bool             # repeat pass only with one satellite (no shared ground track between them)
    normalize: Callable[[dict, str], dict | None]
    incidence_tol: float = 1.0      # stack members: incidence (deg) and look azimuth (deg) within these of the reference
    azimuth_tol: float = 3.0


def _mode(v) -> str:
    return str(v or "").strip().lower().replace(" ", "_").replace("-", "_")


def _footprint(item: dict) -> tuple[list[float], list[list[float]]] | None:
    from shapely.geometry import shape
    if not item.get("geometry"):
        return None
    g = shape(item["geometry"])
    if g.is_empty:
        return None
    if g.geom_type != "Polygon":
        g = g.convex_hull
    ring = [[round(c[0], 5), round(c[1], 5)] for c in g.simplify(1e-4).exterior.coords]      # drop z (Umbra)
    return [round(v, 5) for v in g.bounds], ring


def _base(item: dict, url: str, source: str) -> dict | None:
    p = item.get("properties", {})
    fp = _footprint(item)
    when = p.get("datetime") or p.get("start_datetime")
    if fp is None or not when:
        return None
    inc, az = p.get("view:incidence_angle"), p.get("view:azimuth")
    return {"source": source, "id": item.get("id", ""), "item": url, "datetime": when, "date": when[:10],
            "platform": str(p.get("platform", "")).lower(), "mode": _mode(p.get("sar:instrument_mode")),
            "orbit_state": str(p.get("sat:orbit_state", "")).lower(),
            "look": str(p.get("sar:observation_direction", "")).lower(),
            "incidence": None if inc is None else round(float(inc), 3),
            "look_azimuth": None if az is None else round(float(az), 3),
            "polarization": "/".join(p.get("sar:polarizations") or []), "track": "",
            "bbox": fp[0], "footprint": fp[1]}


def _href(item: dict, url: str, key: str) -> str:
    return urljoin(url, item["assets"][key]["href"])


def _iceye(item: dict, url: str) -> dict | None:
    a = item.get("assets", {})
    if "slc-cog" not in a or "slc-json" not in a:
        return None
    rec = _base(item, url, "iceye")
    if rec:
        rec.update(product="SLC-COG", slc=_href(item, url, "slc-cog"), meta=_href(item, url, "slc-json"))
    return rec


def _capella(item: dict, url: str) -> dict | None:
    p, a = item.get("properties", {}), item.get("assets", {})
    if p.get("sar:product_type") != "SLC" or "metadata" not in a:
        return None
    pol = [k for k in a if k.upper() in ("HH", "VV", "HV", "VH")]
    rec = _base(item, url, "capella")
    if rec and pol:
        rec.update(product="SLC", slc=_href(item, url, pol[0]), meta=_href(item, url, "metadata"),
                   track=str(p.get("capella:rgt_id") or ""))
    return rec if rec and pol else None


def _umbra(item: dict, url: str) -> dict | None:
    a = item.get("assets", {})
    sicd = [k for k in a if "SICD" in k.upper() and k.lower().endswith(".nitf")]
    if not sicd:
        return None
    rec = _base(item, url, "umbra")
    if rec:                    # the asset hrefs are empty: fetch.umbra_sicd_url finds the file from the item
        rec.update(product="SICD", slc="", meta="")
    return rec


SOURCES: dict[str, Source] = {s.id: s for s in (
    Source("iceye", "ICEYE Open Data", "https://www.iceye.com/open-data-initiative", "CC-BY-4.0",
           ("https://iceye-open-data-catalog.s3.amazonaws.com/collections/iceye-sar.json",),
           sensor="iceye", same_platform=True, normalize=_iceye),
    Source("capella", "Capella Space Open Data", "https://www.capellaspace.com/earth-observation/gallery",
           "CC-BY-4.0",
           ("https://capella-open-data.s3.us-west-2.amazonaws.com/stac/capella-open-data-by-product-type/"
            "capella-open-data-slc/collection.json",),
           sensor="capella", same_platform=False, normalize=_capella),
    Source("umbra", "Umbra Open Data", "https://umbra.space/open-data/", "CC-BY-4.0",
           ("https://umbra-open-data-catalog.s3.us-west-2.amazonaws.com/stac/catalog.json",),
           # every Umbra satellite images the same sites: stacks mix them. ~1 GHz bandwidth: the critical incidence
           # change is ~10° in X band, 4° keeps most of the range spectrum; a 0.25 m spotlight spans only ~3.5° of
           # azimuth (λ / 2ρ), so look azimuths stay within 3° to keep a common azimuth spectrum
           sensor="umbra", same_platform=False, normalize=_umbra, incidence_tol=4.0, azimuth_tol=3.0),
)}
