"""Build a coregistered Sentinel-1 burst stack in a StackStore (native engine, ADR-006/023).

Input: archive scene folders (``processing.acquire.s1_bursts``) holding the same burst IDs of one
subswath. Output ``stack.zarr`` (ARCHITECTURE §10.2), cropped to the AOI in radar geometry:

    slc        (date, y, x) complex64  coregistered to the reference, *flattened*: the geometric
                                       phase 4π/λ(R_sec - R_ref) is removed, so an interferogram
                                       is simply slc[ref] · conj(slc[k])
    kh         (date, y, x) float32    height sensitivity d(phase of slc[ref]·conj(slc[k]))/dh, rad/m
                                       (finite difference of the geometry; a height error dh of a
                                       pixel adds kh·dh to that interferogram)
    bperp      (date)       float32    perpendicular baseline at the stack centre (m),
                                       + = secondary above the reference line of sight
    geometry_lat/lon/hgt   (y, x)       ground point of each pixel (hgt ellipsoidal, m)
    geometry_incidence     (y, x)       incidence angle at the ground (deg)
    geometry_slant_range   (y, x)       reference slant range (m)
    esd_shift  (date)       float32     azimuth ESD correction applied (lines)

The y axis is the debursted reference azimuth line (bursts cut at the middle of their overlaps),
x the range sample of the subswath.
"""
from __future__ import annotations

import itertools
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np

from geoeyes.core.errors import DataError
from geoeyes.core.logging import event
from geoeyes.core.types import BBox
from geoeyes.geometry.dem import Dem
from geoeyes.io.stack import StackStore
from geoeyes.processing.stack.native import common, tops
from geoeyes.processing.stack.native.reuse import Reuse
from geoeyes.sensors.sentinel1.burst import BurstMetadata, read_metadata, read_slc

log = logging.getLogger(__name__)
ENGINE = "geoeyes-native-tops/0.1"


@dataclass
class Burst:
    full_id: str
    meta: BurstMetadata
    tiff: Path


def load_scene(scene_dir: Path, burst_ids: list[str], polarization: str = "VV", orbits=None) -> dict[str, Burst]:
    """Bursts of one acquisition; ``orbits`` (a ``PoeorbProvider``) replaces the annotation orbit."""
    refs = json.loads((scene_dir / "bursts.json").read_text(encoding="utf-8"))
    out = {}
    for r in refs:
        if r["full_burst_id"] in burst_ids and r["polarization"] == polarization:
            xml = scene_dir / f"{r['slc_name']}_{polarization}.xml"
            tif = scene_dir / f"{r['subswath']}_{polarization}_{r['burst_index']}.tiff"
            if tif.exists() and xml.exists():
                meta = read_metadata(xml, r["subswath"], polarization, r["burst_index"], r["slc_name"])
                # guard: the annotation burst must be the one ASF served (a burst lasts ~2.76 s)
                asf_start = datetime.fromisoformat(str(r["start"])).replace(tzinfo=None)
                if abs((meta.sensing_start - asf_start).total_seconds()) > 1.5:
                    raise DataError(f"{r['full_burst_id']} {scene_dir.name}: annotation burst starts "
                                    f"{meta.sensing_start}, ASF says {asf_start} — burst index mismatch")
                if orbits is not None:
                    from geoeyes.sensors.sentinel1.orbits import with_precise_orbit
                    meta = with_precise_orbit(meta, orbits)
                out[r["full_burst_id"]] = Burst(r["full_burst_id"], meta, tif)
    return out


# ----------------------------------------------------------------------------- deburst layout
@dataclass
class Segment:
    """Part of the merged (debursted, subswath-mosaicked) grid taken from one reference burst."""

    full_id: str
    line_offset: int          # merged y = burst line + line_offset
    y0: int                   # first merged row of this segment (inclusive)
    y1: int                   # last row + 1
    subswath: str = ""
    sample_offset: int = 0    # merged x = burst sample + sample_offset
    x0: int = 0               # merged columns of the subswath (cut at the middle of the range overlaps)
    x1: int = 0


def deburst_layout(bursts: list[Burst]) -> tuple[list[Segment], tuple[int, int]]:
    """Merged grid of the reference bursts: one azimuth-time axis (IW subswaths share the line interval) and
    one slant-range-time axis (they share the range sampling rate); bursts of a subswath are cut at the middle
    of their azimuth overlaps, adjacent subswaths at the middle of their range overlap. One subswath: the
    debursted grid of that subswath."""
    bursts = sorted(bursts, key=lambda b: b.meta.sensing_start)
    m0 = bursts[0].meta
    srt0 = min(b.meta.slant_range_time for b in bursts)
    by_sw: dict[str, list[Burst]] = {}
    for b in bursts:
        by_sw.setdefault(b.meta.subswath, []).append(b)
    span = {}
    segs = []
    for sw, bb in by_sw.items():
        so = int(round((bb[0].meta.slant_range_time - srt0) * m0.range_sampling_rate))
        offsets = [int(round((b.meta.sensing_start - m0.sensing_start).total_seconds() / m0.azimuth_time_interval))
                   for b in bb]
        wins = [b.meta.valid_window for b in bb]
        for k, b in enumerate(bb):
            y0 = wins[k][0] + offsets[k]
            y1 = wins[k][1] + offsets[k]
            if k > 0:                           # cut at the middle of the overlap with the previous burst
                prev_end = wins[k - 1][1] + offsets[k - 1]
                y0 = (y0 + prev_end) // 2
            if k < len(bb) - 1:
                next_start = wins[k + 1][0] + offsets[k + 1]
                y1 = (next_start + y1) // 2
            segs.append(Segment(b.full_id, offsets[k], y0, y1, sw, so))
        span[sw] = [max(w[2] for w in wins) + so, min(w[3] for w in wins) + so]
    names = sorted(span, key=lambda s: span[s][0])
    for a, b in itertools.pairwise(names):     # range overlap of adjacent subswaths: cut at its middle
        cut = (span[a][1] + span[b][0]) // 2
        span[a][1], span[b][0] = cut, cut
    for s in segs:
        s.x0, s.x1 = span[s.subswath]
    return segs, (span[names[0]][0], span[names[-1]][1])


# ----------------------------------------------------------------------------- helpers
def _crop_to_aoi(geos: dict[str, tops.BurstGeometry], segs: list[Segment], srange: tuple[int, int],
                 aoi: BBox | None, margin: int) -> tuple[int, int, int, int]:
    y_all = (min(s.y0 for s in segs), max(s.y1 for s in segs))
    if aoi is None:
        return y_all[0], y_all[1], srange[0], srange[1]
    ys, xs = [], []
    for s in segs:
        g = geos[s.full_id]
        L, S = np.meshgrid(g.lines, g.samples, indexing="ij")
        inside = (g.lon >= aoi.west) & (g.lon <= aoi.east) & (g.lat >= aoi.south) & (g.lat <= aoi.north)
        rows = L + s.line_offset
        S = S + s.sample_offset
        keep = inside & (rows >= s.y0) & (rows < s.y1) & (s.x0 <= S) & (s.x1 > S)
        ys.extend(rows[keep])
        xs.extend(S[keep])
    if not ys:
        raise DataError(f"AOI {aoi} is not inside the bursts")
    y0 = max(int(min(ys)) - margin, y_all[0])
    y1 = min(int(max(ys)) + margin + 1, y_all[1])
    x0 = max(int(min(xs)) - margin, srange[0])
    x1 = min(int(max(xs)) + margin + 1, srange[1])
    return y0, y1, x0, x1


# ----------------------------------------------------------------------------- main
def _mid_time(metas) -> str:
    """UTC centre of the bursts of one date (ISO)."""
    mids = sorted(m.sensing_mid for m in metas)          # BurstMetadata.sensing_mid is a property
    return (mids[0] + (mids[-1] - mids[0]) / 2).isoformat()


def build_s1_stack(scenes: dict[date, Path], burst_ids: list[str], reference: date, dem: Dem, out: Path, *,
                   aoi: BBox | None = None, polarization: str = "VV", margin: int = 64,
                   stack_id: str = "", track_id: str = "", overwrite: bool = False, orbits=None,
                   previous: StackStore | None = None, reuse_dates: set[date] | None = None) -> StackStore:
    """``previous`` / ``reuse_dates``: incremental build, as ``stripmap.build_stripmap_stack``."""
    if reference not in scenes:
        raise DataError(f"reference date {reference} not in the scenes")
    data = {d: load_scene(p, burst_ids, polarization, orbits) for d, p in sorted(scenes.items())}
    dates = [d for d, b in data.items() if set(b) == set(burst_ids)]
    skipped = sorted(set(data) - set(dates))
    if skipped:
        log.warning("dates without all bursts skipped: %s", ", ".join(map(str, skipped)))
    # a burst set most dates do not have is a selection problem, not missing data: never build such a stack
    if reference not in dates:
        raise DataError(f"the reference {reference} lacks bursts of the set {', '.join(burst_ids)}")
    if len(dates) < 3 or len(skipped) > len(dates):
        raise DataError(f"{len(skipped)} of {len(data)} dates lack bursts of the set {', '.join(burst_ids)}: "
                        "check the burst selection (AOI, [[tracks]] subswaths)")
    ref = data[reference]
    segs, srange = deburst_layout(list(ref.values()))
    log.info("reference %s: %d bursts, deburst rows %d..%d, samples %d..%d",
             reference, len(segs), segs[0].y0, segs[-1].y1, *srange)

    geos = {fid: tops.reference_geometry(b.meta, dem) for fid, b in ref.items()}
    y0, y1, x0, x1 = _crop_to_aoi(geos, segs, srange, aoi, margin)
    ny, nx = y1 - y0, x1 - x0
    log.info("stack grid %d x %d (rows %d..%d, samples %d..%d)", ny, nx, y0, y1, x0, x1)
    # same burst set as before, else the debursted rows (and the window) move
    reuse = Reuse.open(previous, reuse_dates, reference, (y0, y1, x0, x1))
    if reuse is not None and list(reuse.store.attrs.get("burst_ids", ())) != list(burst_ids):
        log.info("burst set changed: coregistering every date")
        reuse = None

    m_ref0 = ref[segs[0].full_id].meta
    subswaths = sorted({s.subswath for s in segs})
    attrs = {"stack_id": stack_id, "track": track_id, "sensor": "sentinel1", "mode": "tops",
             "subswath": ",".join(subswaths), "polarization": polarization, "reference_date": str(reference),
             "wavelength_m": m_ref0.wavelength, "azimuth_time_interval_s": m_ref0.azimuth_time_interval,
             "range_sampling_rate_hz": m_ref0.range_sampling_rate, "range_pixel_spacing_m": m_ref0.range_pixel_spacing,
             "azimuth_pixel_spacing_m": m_ref0.azimuth_pixel_spacing, "heading_deg": m_ref0.heading_deg,
             "pass_direction": m_ref0.pass_direction.lower(), "look_side": "right",
             "engine": ENGINE, "burst_ids": list(burst_ids),
             "subswath_columns": {s.subswath: [s.x0, s.x1] for s in segs},
             "orbit": orbits.summary() if orbits is not None else "annotation",
             "orbit_per_date": {str(d): (orbits.used.get(next(iter(data[d].values())).meta.slc_name, "annotation")
                                         if orbits is not None else "annotation") for d in dates},
             "crop_rows": [y0, y1], "crop_samples": [x0, x1], "dem": dem.source,
             "sensing_mid_utc": {str(d): _mid_time([b.meta for b in data[d].values()]) for d in dates},
             "slc_convention": "flattened: interferogram = slc[ref] * conj(slc[k])",
             "bperp_convention": "+ = secondary above the reference line of sight",
             "phase_convention": "SLC phase exp(-j 4 pi R / lambda); range increase d between ref and k "
                                 "adds +4 pi d / lambda to slc[ref]*conj(slc[k]) (ps_lite sign = +1)"}
    st = StackStore.create(out, coords={"date": np.array(dates, dtype="datetime64[D]"),
                                        "y": np.arange(y0, y1), "x": np.arange(x0, x1)},
                           attrs=attrs, overwrite=overwrite)
    st.allocate("slc", ("date", "y", "x"), np.complex64, chunks={"y": 512, "x": 512})
    st.allocate("kh", ("date", "y", "x"), np.float32, chunks={"y": 512, "x": 512})
    bperp_centre = np.zeros(len(dates), np.float32)

    # part of the cropped merged grid of each reference burst: rows (a, b), merged columns (c0, c1)
    part: dict[str, tuple[int, int, int, int]] = {}
    for s in segs:
        a, b = max(s.y0, y0), min(s.y1, y1)
        c0, c1 = max(s.x0, x0), min(s.x1, x1)
        if a < b and c0 < c1:
            part[s.full_id] = (a, b, c0, c1)
    seg_by_id = {s.full_id: s for s in segs}
    used_sw = {seg_by_id[f].subswath for f in part}
    if len(used_sw) < len(subswaths):
        log.info("subswath(s) %s outside the AOI window", ", ".join(sorted(set(subswaths) - used_sw)))

    # geometry of the reference on the cropped grid
    geom = {k: np.full((ny, nx), np.nan, np.float32) for k in ("lat", "lon", "hgt", "incidence", "slant_range")}
    for fid, (a, b, c0, c1) in part.items():
        s, g = seg_by_id[fid], geos[fid]
        ll = np.arange(a, b, dtype=np.float64) - s.line_offset
        ss = np.arange(c0, c1, dtype=np.float64) - s.sample_offset
        inc = common.incidence(ref[fid].meta, g)
        for key, val in (("lat", g.lat), ("lon", g.lon), ("hgt", g.h), ("incidence", inc), ("slant_range", g.r_ref)):
            geom[key][a - y0:b - y0, c0 - x0:c1 - x0] = g.spline(val)(ll, ss)
    for key, arr in geom.items():
        st.write(f"geometry_{key}", arr, ("y", "x"), attrs={"units": {"lat": "deg", "lon": "deg", "incidence": "deg"}
                                                             .get(key, "m")}, chunks={"y": 512, "x": 512})

    y_mid, x_mid = (y0 + y1) // 2, (x0 + x1) // 2
    centre_fid = min(part, key=lambda f: (0 if part[f][0] <= y_mid < part[f][1] else 1,
                                          0 if part[f][2] <= x_mid < part[f][3] else 1))
    esd = np.zeros(len(dates), np.float32)
    # bursts processed per subswath (ESD needs every consecutive pair of the subswath, even outside the AOI)
    order = {sw: sorted((f for f in ref if seg_by_id[f].subswath == sw), key=lambda f: ref[f].meta.sensing_start)
             for sw in sorted(used_sw)}
    for di, d in enumerate(dates):
        if d != reference and reuse is not None and d in reuse:
            st.write_region("slc", reuse.block("slc", d)[None], {"date": slice(di, di + 1)})
            st.write_region("kh", reuse.block("kh", d)[None], {"date": slice(di, di + 1)})
            bperp_centre[di] = reuse.value("bperp", d)
            esd[di] = reuse.value("esd_shift", d)
            log.info("%s: reused from the previous build", d)
            event(log, "progress", f"stack date {d} done", stage="build_stack", done=di + 1, total=len(dates))
            continue
        sec = data[d]
        shifts = []
        for sw, fids in order.items():
            s_sw = seg_by_id[fids[0]]
            bx0, bx1 = max(s_sw.x0, x0) - s_sw.sample_offset, min(s_sw.x1, x1) - s_sw.sample_offset
            work: dict[str, dict] = {}
            for fid in fids:
                rm, sm = ref[fid].meta, sec[fid].meta
                win = rm.valid_window
                win = (win[0], win[1], max(win[2], bx0), min(win[3], bx1))
                rs = read_slc(ref[fid].tiff, win)
                if d == reference:
                    off, res, s_slc = None, rs, None
                else:
                    off = tops.secondary_offsets(rm, sm, geos[fid], win)
                    s_slc = read_slc(sec[fid].tiff)
                    res = tops.resample_secondary(sm, s_slc, off)
                work[fid] = {"rm": rm, "sm": sm, "win": win, "rs": rs, "off": off, "res": res, "s_slc": s_slc}
            if d != reference and len(fids) > 1:
                ovl = [_overlap(work[a], work[b]) for a, b in itertools.pairwise(fids)]
                shift, info = tops.esd_shift(ovl, work[fids[0]]["rm"].azimuth_time_interval)
                for w in work.values():
                    w["off"].az_shift = shift
                    w["res"] = tops.resample_secondary(w["sm"], w["s_slc"], w["off"])
                shifts.append(shift)
                log.info("%s %s: ESD %+.5f lines (%d px)", d, sw, shift, info.get("n", 0))
            for fid in fids:
                if fid not in part:
                    continue
                a, b, c0, c1 = part[fid]
                w, s = work[fid], seg_by_id[fid]
                l0, l1 = a - s.line_offset - w["win"][0], b - s.line_offset - w["win"][0]
                k0, k1 = c0 - s.sample_offset - w["win"][2], c1 - s.sample_offset - w["win"][2]
                if d == reference:
                    block = w["res"][l0:l1, k0:k1]
                    kh = np.zeros(block.shape, np.float32)
                else:
                    block = (w["res"][l0:l1, k0:k1] * np.exp(1j * w["off"].geom_phase[l0:l1, k0:k1])
                             ).astype(np.complex64)
                    g = geos[fid]
                    kh = g.spline(common.height_sensitivity(w["rm"], w["sm"], g))(
                        np.arange(a, b) - s.line_offset, np.arange(c0, c1, dtype=np.float64) - s.sample_offset)
                    kh = kh.astype(np.float32)
                    if fid == centre_fid:
                        bp = common.perpendicular_baseline(w["rm"], w["sm"], g)
                        bperp_centre[di] = bp[bp.shape[0] // 2, bp.shape[1] // 2]
                region = {"date": slice(di, di + 1), "y": slice(a - y0, b - y0), "x": slice(c0 - x0, c1 - x0)}
                st.write_region("slc", block[None], region)
                st.write_region("kh", kh[None], region)
        esd[di] = float(np.mean(shifts)) if shifts else 0.0
        event(log, "progress", f"stack date {d} done", stage="build_stack", done=di + 1, total=len(dates))
    st.write("esd_shift", esd, ("date",), attrs={"units": "lines", "note": "mean over the subswaths"})
    st.write("bperp", bperp_centre, ("date",), attrs={"units": "m", "where": "stack centre"})
    return st


def _overlap(a: dict, b: dict) -> tops.OverlapIfg:
    """Interferograms of consecutive bursts ``a`` (earlier) and ``b`` over their common ground."""
    ma, mb = a["rm"], b["rm"]
    dt_lines = (mb.sensing_start - ma.sensing_start).total_seconds() / ma.azimuth_time_interval
    shift = int(round(dt_lines))
    la0, la1, sa0, sa1 = a["win"]
    lb0, lb1, sb0, sb1 = b["win"]
    lo, hi = max(la0, lb0 + shift), min(la1, lb1 + shift)
    s_lo, s_hi = max(sa0, sb0), min(sa1, sb1)
    if hi <= lo or s_hi <= s_lo:
        raise DataError("consecutive bursts do not overlap")
    ia, ib = slice(lo - la0, hi - la0), slice(lo - shift - lb0, hi - shift - lb0)
    ca, cb = slice(s_lo - sa0, s_hi - sa0), slice(s_lo - sb0, s_hi - sb0)

    def ifg(w, rows, cols):
        o = w["off"]
        return tops.interferogram(w["rs"][rows, cols], w["res"][rows, cols],
                                  tops.Offsets(o.line[rows, cols], o.sample[rows, cols], o.geom_phase[rows, cols]))
    kt = tops.doppler_rate(ma, np.arange(s_lo, s_hi, dtype=float))[None, :]
    df = np.broadcast_to(kt * dt_lines * ma.azimuth_time_interval, (hi - lo, s_hi - s_lo))
    return tops.OverlapIfg(ifg(a, ia, ca), ifg(b, ib, cb), df)
