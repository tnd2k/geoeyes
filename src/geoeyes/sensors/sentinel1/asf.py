"""ASF search API for Sentinel-1 burst SLCs (ADR-023).

The ``asf_search`` package goes through CMR, which fails on some machines; the plain search API
(``api.daac.asf.alaska.edu``) is used instead. Search needs no authentication.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

import requests

from geoeyes.core.errors import DataError
from geoeyes.core.types import BBox, OrbitDirection

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
DATASET = "SLC-BURST"


@dataclass(frozen=True)
class BurstRef:
    """One burst of one acquisition, as returned by the ASF burst search."""

    file_id: str                 # S1_165499_IW3_20240807T004900_VV_3001-BURST
    full_burst_id: str           # 078_165499_IW3
    relative_burst_id: int
    subswath: str                # IW3
    burst_index: int             # index inside the subswath of the source SLC (0-based, as ASF serves it)
    polarization: str
    start: datetime              # burst azimuth start (UTC)
    slc_name: str                # source SLC product name
    relative_orbit: int
    absolute_orbit: int
    direction: OrbitDirection
    platform: str                # Sentinel-1A / -1B / -1C
    data_url: str
    metadata_url: str
    bytes: int
    footprint_wkt: str

    @property
    def date(self) -> date:
        return self.start.date()

    @property
    def track_id(self) -> str:
        return f"sentinel1-{self.direction.short}-{self.relative_orbit:03d}"


def _polygon_wkt(geom: dict) -> str:
    if not geom or geom.get("type") != "Polygon":
        return ""
    ring = geom["coordinates"][0]
    return "POLYGON((" + ",".join(f"{x} {y}" for x, y, *_ in ring) + "))"


def parse_feature(feature: dict) -> BurstRef:
    p = feature["properties"]
    b = p.get("burst") or {}
    data_url = p["url"]
    parts = data_url.split("/")          # .../<SLC>/<IWx>/<POL>/<index>.tiff
    return BurstRef(
        file_id=p["fileID"],
        full_burst_id=b["fullBurstID"],
        relative_burst_id=int(b["relativeBurstID"]),
        subswath=b["subswath"],
        burst_index=int(b["burstIndex"]),
        polarization=p.get("polarization", parts[-2]),
        start=datetime.fromisoformat(p["startTime"].replace("Z", "+00:00")),
        slc_name=parts[-4],
        relative_orbit=int(p["pathNumber"]),
        absolute_orbit=int(p["orbit"]),
        direction=OrbitDirection.parse(p["flightDirection"]),
        platform=p.get("platform", ""),
        data_url=data_url,
        metadata_url=(p.get("additionalUrls") or [data_url.rsplit(".", 1)[0] + ".xml"])[0],
        bytes=int(float(p.get("bytes") or 0)),
        footprint_wkt=_polygon_wkt(feature.get("geometry")),
    )


def search(*, start: date | str, end: date | str, full_burst_ids: Iterable[str] | None = None,
           aoi: BBox | None = None, relative_orbit: int | None = None, polarization: str = "VV",
           session: requests.Session | None = None, timeout: float = 300) -> list[BurstRef]:
    """Burst SLCs between ``start`` and ``end`` (inclusive dates), filtered by burst IDs and/or AOI."""
    if not full_burst_ids and aoi is None:
        raise DataError("burst search needs full_burst_ids or an aoi")
    q: dict = {"dataset": DATASET, "start": str(start), "end": f"{end}T23:59:59Z" if len(str(end)) == 10 else str(end),
               "polarization": polarization, "output": "geojson", "maxResults": 10000}
    if full_burst_ids:
        q["fullBurstID"] = ",".join(sorted(set(full_burst_ids)))
    if aoi is not None:
        w, s, e, n = aoi.as_tuple()
        q["intersectsWith"] = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    if relative_orbit is not None:
        q["relativeOrbit"] = relative_orbit
    http = session or requests.Session()
    resp = http.get(SEARCH_URL, params=q, timeout=timeout)
    resp.raise_for_status()
    refs = [parse_feature(f) for f in resp.json().get("features", [])]
    refs.sort(key=lambda r: (r.start, r.subswath, r.relative_burst_id))
    log.info("ASF burst search: %d bursts", len(refs))
    return refs


def burst_ids_for_aoi(aoi: BBox, *, relative_orbit: int, start: date | str, end: date | str,
                      subswaths: Iterable[str] | None = None, polarization: str = "VV",
                      all_subswaths: bool = False, session: requests.Session | None = None) -> list[str]:
    """Full burst IDs covering ``aoi`` on one track (taken from the acquisition with most coverage).

    ``all_subswaths=True`` adds the same relative burst IDs in every IW subswath — needed only to
    build multi-swath SAFEs for the SNAP reference pipeline (ADR-023).
    """
    refs = search(start=start, end=end, aoi=aoi, relative_orbit=relative_orbit, polarization=polarization,
                  session=session)
    if subswaths:
        keep = {s.upper() for s in subswaths}
        refs = [r for r in refs if r.subswath in keep]
    if not refs:
        raise DataError(f"no bursts over {aoi} on relative orbit {relative_orbit}")
    by_acq: dict[str, set[str]] = defaultdict(set)
    for r in refs:
        by_acq[r.slc_name].add(r.full_burst_id)
    ids = max(by_acq.values(), key=len)
    if all_subswaths:
        rel = {i.split("_")[1] for i in ids}
        ids = {f"{relative_orbit:03d}_{b}_IW{k}" for b in rel for k in (1, 2, 3)}
    return sorted(ids)


def group_by_acquisition(refs: Iterable[BurstRef]) -> dict[str, list[BurstRef]]:
    out: dict[str, list[BurstRef]] = defaultdict(list)
    for r in refs:
        out[r.slc_name].append(r)
    return {k: sorted(v, key=lambda r: (r.subswath, r.burst_index)) for k, v in sorted(out.items())}
