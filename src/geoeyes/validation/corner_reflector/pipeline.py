"""CR identification: for every reflector and every Sentinel-1 acquisition, the pointing the reflector needs,
the RCS it should give for the way it was set up, the RCS and position measured on the image, and the
coherence between acquisitions (port of the legacy ``modules.cr_report.pipeline`` on native burst files)."""
from __future__ import annotations

import itertools
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from geoeyes.validation.corner_reflector import measure, trihedral
from geoeyes.validation.corner_reflector.inputs import DEFAULT_TZ, CRSetup, CRTarget, setup_at

log = logging.getLogger(__name__)

CHIP = (48, 192)            # half size (azimuth, range) of the chip read around a reflector
CELL_SEARCH = (1, 2)        # RCS peak search: one resolution cell around the predicted position
NEAR_SEARCH = (2, 8)        # wider search, to flag a stronger scatterer next to the reflector
TOLERANCE_DB = 3.0
MAX_PAIRS_ALL = 10          # all date pairs up to this many dates, consecutive pairs above


@dataclass
class Observation:
    reflector: str
    date: str                       # UTC date of the acquisition
    acquired_utc: str
    acquired_local: str
    platform: str
    track: int
    direction: str
    swath: str
    burst: int
    los_azimuth_deg: float
    los_elevation_deg: float
    incidence_deg: float
    setup_face_azimuth_deg: float
    setup_base_tilt_deg: float
    setup_source: str               # "log" | "assumed"
    setup_note: str
    expected_dbsm: float
    measured_dbsm: float
    scr_db: float
    difference_db: float
    within_tolerance: bool
    peak_lat: float
    peak_lon: float
    offset_north_m: float
    offset_east_m: float
    offset_m: float
    nearby_dbsm: float              # strongest response within NEAR_SEARCH
    nearby_offset_m: float
    wavelength_m: float
    chip: dict = field(default_factory=dict, repr=False)   # beta0 chip for the figure (not saved to JSON)


@dataclass
class Pointing:
    reflector: str
    platform: str
    track: int
    direction: str
    from_date: str
    face_azimuth_deg: float
    boresight_elevation_deg: float
    base_tilt_deg: float
    incidence_deg: float


@dataclass
class Coherence:
    reflector: str
    date_1: str
    date_2: str
    track: int
    at_reflector: float
    area_median: float
    area_p90: float
    offset_az_px: float
    offset_rg_px: float


def run(targets: list[CRTarget], scenes: list, setups: list[CRSetup] | None = None, tz: str = DEFAULT_TZ,
        default_height: float = 0.0) -> dict:
    """``scenes``: ``s1burst.BurstScene`` (any reader with that interface), in any order."""
    setups = setups or []
    zone = ZoneInfo(tz)
    prods = sorted(scenes, key=lambda p: p.start_utc)
    warnings: list[str] = []
    obs: list[Observation] = []
    chips: dict[tuple[str, str], tuple] = {}
    seen: set[int] = set()

    for t in targets:
        h = t.height if t.height is not None else default_height
        if t.height is None:
            warnings.append(f"{t.name}: no height in the reflector list, {default_height:g} m used "
                            "(a wrong height shifts the predicted position).")
        for p in prods:
            loc = p.locate(t.lat, t.lon, h)
            if loc is None:
                continue
            sw = p.swath(loc)
            L, S = int(round(loc.line)), int(round(loc.sample))
            z, r0, c0 = p.read_chip(sw, L, S, *CHIP)
            b0 = measure.beta0(z, p.beta_nought_lut(sw, loc.line, loc.sample))
            cell = measure.measure_rcs(b0, r0, c0, loc.line, loc.sample, sw.range_spacing, sw.azimuth_spacing,
                                       search=CELL_SEARCH)
            near = measure.measure_rcs(b0, r0, c0, loc.line, loc.sample, sw.range_spacing, sw.azimuth_spacing,
                                       search=NEAR_SEARCH)
            plat, plon = p.geocode(sw, cell.peak_line, cell.peak_sample, h, (t.lat, t.lon))
            dn, de = _enu_offset(t.lat, t.lon, plat, plon)
            nlat, nlon = p.geocode(sw, near.peak_line, near.peak_sample, h, (t.lat, t.lon))
            ndn, nde = _enu_offset(t.lat, t.lon, nlat, nlon)

            local = p.start_utc.astimezone(zone)
            s = setup_at(setups, t.name, local)
            if s is None:
                req = trihedral.required_pointing(loc.los_azimuth_deg, loc.los_elevation_deg)
                face, tilt, src, note = req["face_azimuth_deg"], req["base_tilt_deg"], "assumed", ""
            else:
                face, tilt, src, note = s.face_azimuth_deg, s.base_tilt_deg, "log", s.note
            exp = trihedral.rcs_dbsm(t.edge_m, p.wavelength, loc.los_azimuth_deg, loc.los_elevation_deg, face, tilt)
            obs.append(Observation(
                reflector=t.name, date=p.date, acquired_utc=p.start_utc.strftime("%Y-%m-%d %H:%M"),
                acquired_local=local.strftime("%Y-%m-%d %H:%M"), platform=p.platform, track=p.relative_orbit,
                direction=p.pass_direction, swath=loc.swath.upper(), burst=loc.burst,
                los_azimuth_deg=loc.los_azimuth_deg, los_elevation_deg=loc.los_elevation_deg,
                incidence_deg=loc.incidence_deg, setup_face_azimuth_deg=face, setup_base_tilt_deg=tilt,
                setup_source=src, setup_note=note, expected_dbsm=exp, measured_dbsm=cell.rcs_dbsm,
                scr_db=cell.scr_db, difference_db=cell.rcs_dbsm - exp,
                within_tolerance=bool(abs(cell.rcs_dbsm - exp) <= TOLERANCE_DB),
                peak_lat=plat, peak_lon=plon, offset_north_m=dn, offset_east_m=de, offset_m=float(np.hypot(dn, de)),
                nearby_dbsm=near.rcs_dbsm, nearby_offset_m=float(np.hypot(ndn, nde)), wavelength_m=p.wavelength,
                chip=dict(beta0=b0, line0=r0, sample0=c0, pred=(loc.line, loc.sample),
                          peak=(cell.peak_line, cell.peak_sample), range_spacing=sw.range_spacing,
                          azimuth_spacing=sw.azimuth_spacing, incidence_deg=loc.incidence_deg)))
            chips[(t.name, p.date)] = (z, r0, c0, cell, loc.swath, p.relative_orbit)
            seen.add(id(p))

    used = [p for p in prods if id(p) in seen]          # acquisitions that image at least one reflector
    return {
        "generated_at": datetime.now(zone).strftime("%Y-%m-%d %H:%M"),
        "timezone": tz,
        "tolerance_db": TOLERANCE_DB,
        "reflectors": [asdict(t) for t in targets],
        "acquisitions": [dict(date=p.date, acquired_utc=p.start_utc.strftime("%Y-%m-%d %H:%M"),
                              acquired_local=p.start_utc.astimezone(zone).strftime("%Y-%m-%d %H:%M"),
                              platform=p.platform, track=p.relative_orbit, direction=p.pass_direction,
                              product=p.path.name) for p in used],
        "pointing": [asdict(x) for x in _pointing(targets, used, default_height)],
        "observations": obs,
        "coherence": [asdict(x) for x in _coherence(targets, chips)],
        "warnings": warnings,
    }


def _enu_offset(lat0, lon0, lat, lon) -> tuple[float, float]:
    return (lat - lat0) * 110574.0, (lon - lon0) * 111320.0 * float(np.cos(np.radians(lat0)))


def _pointing(targets, prods, default_height) -> list[Pointing]:
    """Required set-up per reflector and track, from the latest acquisition of that track."""
    out = []
    for t in targets:
        h = t.height if t.height is not None else default_height
        latest = {}
        for p in prods:                          # sorted by time: the last one that sees the CR wins
            loc = p.locate(t.lat, t.lon, h)
            if loc is not None:
                latest[(p.platform, p.relative_orbit, p.pass_direction)] = (p, loc)
        for (plat, track, direc), (p, loc) in sorted(latest.items(), key=lambda kv: kv[0][1]):
            req = trihedral.required_pointing(loc.los_azimuth_deg, loc.los_elevation_deg)
            out.append(Pointing(reflector=t.name, platform=plat, track=track, direction=direc, from_date=p.date,
                                face_azimuth_deg=req["face_azimuth_deg"],
                                boresight_elevation_deg=req["boresight_elevation_deg"],
                                base_tilt_deg=req["base_tilt_deg"], incidence_deg=loc.incidence_deg))
    return out


def _coherence(targets, chips) -> list[Coherence]:
    out = []
    for t in targets:
        dates = sorted(d for (n, d) in chips if n == t.name)
        by_track: dict[tuple, list[str]] = {}
        for d in dates:
            _z, _r, _c, _cell, swath, track = chips[(t.name, d)]
            by_track.setdefault((track, swath), []).append(d)
        for (track, _swath), ds in by_track.items():
            pairs = list(itertools.combinations(ds, 2)) if len(ds) <= MAX_PAIRS_ALL else list(itertools.pairwise(ds))
            for d1, d2 in pairs:
                zm, rm, cm, cell, _, _ = chips[(t.name, d1)]
                zs = chips[(t.name, d2)][0]
                n = min(zm.shape[0], zs.shape[0]), min(zm.shape[1], zs.shape[1])
                m, s, (dy, dx) = measure.coregister(zm[:n[0], :n[1]], zs[:n[0], :n[1]])
                at = (int(round(cell.peak_line)) - rm, int(round(cell.peak_sample)) - cm)
                edge = measure.coherence_map(m, s)[8:-8, 24:-24]
                out.append(Coherence(reflector=t.name, date_1=d1, date_2=d2, track=track,
                                     at_reflector=measure.point_coherence(m, s, at),
                                     area_median=float(np.nanmedian(edge)),
                                     area_p90=float(np.nanpercentile(edge, 90)),
                                     offset_az_px=dy, offset_rg_px=dx))
    return out
