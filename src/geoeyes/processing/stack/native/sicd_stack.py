"""Coregistered stack of SICD scenes (slant-plane PFA spotlight, e.g. Umbra; RMA / INCA too).

The SICD grid is not a zero-Doppler (azimuth time, slant range) grid, so the geometry goes through the SICD image
projections (``sensors.sicd.meta``): reference pixels of a coarse grid -> ground points on the DEM -> pixels of each
secondary; resampling (SICD data are at baseband: no deramping); a residual constant offset from amplitude
correlation (``stripmap.residual_offset``); flattening with the geometric phase 2π (KCtr_sec ΔR_sec - KCtr_ref ΔR_ref)
of the DEM point (SICD phases are referenced to each scene's SCP). Output: the StackStore of the other builders
(lines = SICD columns, samples = SICD rows; flattened ``slc``, ``kh``, ``bperp``, ``geometry_*``, ``coreg_residual``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from scipy.interpolate import RectBivariateSpline
from scipy.ndimage import map_coordinates

from geoeyes.core.errors import DataError
from geoeyes.core.geodesy import enu_basis
from geoeyes.core.logging import event
from geoeyes.core.types import BBox
from geoeyes.geometry.dem import Dem
from geoeyes.io.stack import StackStore
from geoeyes.processing.stack.native.reuse import Reuse
from geoeyes.processing.stack.native.stripmap import residual_offset
from geoeyes.sensors.sicd.meta import Sicd

log = logging.getLogger(__name__)
ENGINE = "geoeyes-native-sicd/0.1"
MAX_INCIDENCE_DIFF_DEG = 2.0


@dataclass
class SicdScene:
    meta: Sicd
    read: object                    # window (l0, l1, s0, s1) -> complex64 (lines = SICD cols, samples = SICD rows)
    scene_id: str = ""

    @property
    def lines(self) -> int:
        return self.meta.cols

    @property
    def samples(self) -> int:
        return self.meta.rows


@dataclass
class Geometry:
    """Reference ground points on a coarse grid (lines = SICD cols, samples = SICD rows of the reference)."""

    lines: np.ndarray
    samples: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    h: np.ndarray
    xyz: np.ndarray                 # (nl, ns, 3)

    def spline(self, values: np.ndarray) -> RectBivariateSpline:
        k = min(3, len(self.lines) - 1, len(self.samples) - 1)
        return RectBivariateSpline(self.lines, self.samples, values, kx=k, ky=k)


def reference_geometry(ref: Sicd, dem: Dem, window: tuple[int, int, int, int], step: tuple[int, int]) -> Geometry:
    l0, l1, s0, s1 = window
    lines = np.unique(np.r_[np.arange(l0, l1, step[0]), l1 - 1]).astype(float)
    samples = np.unique(np.r_[np.arange(s0, s1, step[1]), s1 - 1]).astype(float)
    L, S = np.meshgrid(lines, samples, indexing="ij")
    lat, lon, h, xyz = ref.image_to_ground(S, L, dem=dem)            # SICD (row, col) = (sample, line)
    return Geometry(lines, samples, lat, lon, h, xyz)


def aoi_window(ref: Sicd, dem: Dem, aoi: BBox | None, margin: int) -> tuple[int, int, int, int]:
    if aoi is None:
        return 0, ref.cols, 0, ref.rows
    lon, lat = np.meshgrid(np.linspace(aoi.west, aoi.east, 15), np.linspace(aoi.south, aoi.north, 15))
    from geoeyes.core.geodesy import llh_to_ecef
    h = np.asarray(dem.ellipsoidal(lat.ravel(), lon.ravel()), float)
    row, col = ref.ground_to_image(llh_to_ecef(lat.ravel(), lon.ravel(), h))
    if not (np.isfinite(row).all() and (col.max() > 0) and (col.min() < ref.cols) and (row.max() > 0)
            and (row.min() < ref.rows)):
        raise DataError(f"AOI {aoi} is not inside the reference SICD")
    return (int(max(np.floor(col.min()) - margin, 0)), int(min(np.ceil(col.max()) + margin + 1, ref.cols)),
            int(max(np.floor(row.min()) - margin, 0)), int(min(np.ceil(row.max()) + margin + 1, ref.rows)))


def _phase(m: Sicd, xyz: np.ndarray, row=None, col=None) -> np.ndarray:
    return 2.0 * np.pi * m.row_kctr * m.phase_range(xyz, row, col)


def _incidence(m: Sicd, g: Geometry) -> np.ndarray:
    arp = m.arp.pos(m.scp_time)
    to_sat = arp - g.xyz
    to_sat /= np.linalg.norm(to_sat, axis=-1, keepdims=True)
    up = enu_basis(g.lat.ravel(), g.lon.ravel())[:, 2, :].reshape(g.xyz.shape)
    return np.degrees(np.arccos(np.clip(np.einsum("...i,...i->...", to_sat, up), -1, 1)))


def _up_in_cell(m: Sicd, g: Geometry) -> np.ndarray:
    """1 m of height inside the reference resolution cell: perpendicular to the reference LOS and velocity."""
    t = m.scp_time
    arp, vel = m.arp.pos(t), m.arp.vel(t)
    los = g.xyz - arp
    los /= np.linalg.norm(los, axis=-1, keepdims=True)
    v = vel / np.linalg.norm(vel)
    up = enu_basis(g.lat.ravel(), g.lon.ravel())[:, 2, :].reshape(g.xyz.shape)
    d = up - np.einsum("...i,...i->...", up, los)[..., None] * los - np.einsum("...i,i->...", up, v)[..., None] * v
    return d / np.einsum("...i,...i->...", d, up)[..., None]


def bperp(ref: Sicd, sec: Sicd, xyz: np.ndarray) -> float:
    """Perpendicular baseline at a ground point (+ = secondary above the reference LOS)."""
    a, b = ref.arp.pos(ref.scp_time), sec.arp.pos(sec.scp_time)
    los = (xyz - a) / np.linalg.norm(xyz - a)
    up = a / np.linalg.norm(a)
    perp = up - np.dot(up, los) * los
    return float(np.dot(b - a, perp / np.linalg.norm(perp)))


def resample(sec: SicdScene, line: np.ndarray, smp: np.ndarray, *, pad: int = 8, order: int = 3) -> np.ndarray:
    l0 = int(max(np.floor(np.nanmin(line)) - pad, 0))
    l1 = int(min(np.ceil(np.nanmax(line)) + pad + 1, sec.lines))
    s0 = int(max(np.floor(np.nanmin(smp)) - pad, 0))
    s1 = int(min(np.ceil(np.nanmax(smp)) + pad + 1, sec.samples))
    if l1 <= l0 or s1 <= s0:
        raise DataError(f"{sec.scene_id}: reference window falls outside the secondary image")
    data = sec.read((l0, l1, s0, s1))
    coords = [(line - l0).ravel(), (smp - s0).ravel()]
    re = map_coordinates(data.real, coords, order=order, mode="constant", cval=0.0)
    im = map_coordinates(data.imag, coords, order=order, mode="constant", cval=0.0)
    out = (re + 1j * im).reshape(line.shape).astype(np.complex64)
    out[~((line >= 0) & (line <= sec.lines - 1) & (smp >= 0) & (smp <= sec.samples - 1))] = 0
    return out


def check_geometry(scenes: dict[date, SicdScene], reference: date) -> tuple[dict[date, SicdScene], list[str]]:
    """Same side of track and pass, incidence at the SCP within ``MAX_INCIDENCE_DIFF_DEG`` of the reference."""
    r = scenes[reference].meta

    def inc(m: Sicd) -> float:
        arp = m.arp.pos(m.scp_time)
        up = m.scp / np.linalg.norm(m.scp)
        los = (arp - m.scp) / np.linalg.norm(arp - m.scp)
        return float(np.degrees(np.arccos(np.dot(up, los))))

    kept, rejected = {}, []
    for d, sc in scenes.items():
        m, why = sc.meta, []
        if m.side != r.side:
            why.append(f"{m.look_side}-looking")
        if m.pass_direction != r.pass_direction:
            why.append(f"{m.pass_direction} pass")
        if abs(inc(m) - inc(r)) > MAX_INCIDENCE_DIFF_DEG:
            why.append(f"incidence {inc(m):.1f} deg vs {inc(r):.1f}")
        if not m.delta_kcoa_zero:
            why.append("non-zero DeltaKCOAPoly (spectrum not at baseband)")
        if why:
            rejected.append(f"{d}: {', '.join(why)}")
        else:
            kept[d] = sc
    return kept, rejected


def build_sicd_stack(scenes: dict[date, SicdScene], reference: date, dem: Dem, out: Path, *, aoi: BBox | None = None,
                     margin: int = 64, stack_id: str = "", track_id: str = "", overwrite: bool = False,
                     geo_spacing_m: float = 2.0, max_residual_iter: int = 2, sensor: str = "umbra",
                     previous: StackStore | None = None, reuse_dates: set[date] | None = None) -> StackStore:
    """``geo_spacing_m``: spacing of the coarse geometry grid (the DEM detail sets the geometric phase)."""
    if reference not in scenes:
        raise DataError(f"reference date {reference} not in the scenes")
    scenes, rejected = check_geometry(scenes, reference)
    for msg in rejected:
        log.warning("scene left out (not the reference geometry): %s", msg)
    if len(scenes) < 3:
        raise DataError(f"{len(scenes)} scene(s) in the reference geometry, at least 3 needed")
    dates = sorted(scenes)
    ref = scenes[reference]
    rm = ref.meta
    win = aoi_window(rm, dem, aoi, margin)
    y0, y1, x0, x1 = win
    ny, nx = y1 - y0, x1 - x0
    log.info("%s reference %s: window lines %d..%d, samples %d..%d (%d x %d)", sensor, reference, *win, ny, nx)
    reuse = Reuse.open(previous, reuse_dates, reference, win)
    step = (max(int(round(geo_spacing_m / rm.col_ss)), 1), max(int(round(geo_spacing_m / rm.row_ss)), 1))
    geo = reference_geometry(rm, dem, win, step)
    log.info("geometry grid every %d lines x %d samples", *step)
    L, S = np.meshgrid(geo.lines, geo.samples, indexing="ij")
    phi_ref = _phase(rm, geo.xyz, S, L)
    xyz_up = geo.xyz + _up_in_cell(rm, geo)
    phi_ref_up = _phase(rm, xyz_up)
    centre = geo.xyz[geo.xyz.shape[0] // 2, geo.xyz.shape[1] // 2]
    attrs = {"stack_id": stack_id, "track": track_id, "sensor": sensor, "mode": "spotlight",
             "image_formation": rm.ifa, "polarization": rm.polarization, "reference_date": str(reference),
             "wavelength_m": rm.wavelength, "range_pixel_spacing_m": rm.row_ss, "azimuth_pixel_spacing_m": rm.col_ss,
             "heading_deg": rm.heading_deg, "pass_direction": rm.pass_direction, "look_side": rm.look_side,
             "engine": ENGINE, "crop_rows": [y0, y1], "crop_samples": [x0, x1], "dem": dem.source,
             "scenes": {str(d): scenes[d].scene_id for d in dates},
             "sensing_mid_utc": {str(d): scenes[d].meta.scp_utc.isoformat() for d in dates},
             "slc_convention": "flattened: interferogram = slc[ref] * conj(slc[k])",
             "bperp_convention": "+ = secondary above the reference line of sight",
             "phase_convention": "SLC phase exp(-j 4 pi R / lambda); range increase d between ref and k "
                                 "adds +4 pi d / lambda to slc[ref]*conj(slc[k]) (ps_lite sign = +1)"}
    st = StackStore.create(out, coords={"date": np.array(dates, dtype="datetime64[D]"), "y": np.arange(y0, y1),
                                        "x": np.arange(x0, x1)}, attrs=attrs, overwrite=overwrite)
    st.allocate("slc", ("date", "y", "x"), np.complex64, chunks={"y": 512, "x": 512})
    st.allocate("kh", ("date", "y", "x"), np.float32, chunks={"y": 512, "x": 512})
    ll, ss = np.arange(y0, y1, dtype=float), np.arange(x0, x1, dtype=float)
    r_ref = np.linalg.norm(geo.xyz - rm.arp.pos(rm.scp_time), axis=-1)
    for key, val, unit in (("lat", geo.lat, "deg"), ("lon", geo.lon, "deg"), ("hgt", geo.h, "m"),
                           ("incidence", _incidence(rm, geo), "deg"), ("slant_range", r_ref, "m")):
        st.write(f"geometry_{key}", geo.spline(val)(ll, ss).astype(np.float32), ("y", "x"), attrs={"units": unit},
                 chunks={"y": 512, "x": 512})

    ref_slc = ref.read(win)
    bp = np.zeros(len(dates), np.float32)
    resid = np.zeros((len(dates), 2), np.float32)
    for di, d in enumerate(dates):
        sc = scenes[d]
        if d == reference:
            block, kh = ref_slc, np.zeros((ny, nx), np.float32)
        elif reuse is not None and d in reuse:
            block, kh = reuse.block("slc", d), reuse.block("kh", d)
            bp[di] = reuse.value("bperp", d)
            resid[di] = reuse.value("coreg_residual", d, (0.0, 0.0))
            log.info("%s: reused from the previous build", d)
        else:
            sm = sc.meta
            row_s, col_s = sm.ground_to_image(geo.xyz)
            phi_sec = _phase(sm, geo.xyz, row_s, col_s)
            line = geo.spline(col_s)(ll, ss)
            smp = geo.spline(row_s)(ll, ss)
            geom = geo.spline(phi_sec - phi_ref)(ll, ss)
            dl = ds = 0.0
            res = resample(sc, line, smp)
            n_tiles = 0
            for _ in range(max_residual_iter):
                a, b, n_tiles = residual_offset(ref_slc, res)
                if abs(a) < 0.01 and abs(b) < 0.01:
                    break
                dl, ds = dl + a, ds + b
                res = resample(sc, line + dl, smp + ds)
            resid[di] = (dl, ds)
            block = (res * np.exp(1j * geom)).astype(np.complex64)
            kh_c = (_phase(sm, xyz_up) - phi_ref_up) - (phi_sec - phi_ref)
            kh = geo.spline(kh_c)(ll, ss).astype(np.float32)
            bp[di] = bperp(rm, sm, centre)
            log.info("%s: residual offset %+.3f lines, %+.3f samples (%d tiles), Bperp %.0f m", d, dl, ds, n_tiles,
                     bp[di])
        st.write_region("slc", block[None], {"date": slice(di, di + 1)})
        st.write_region("kh", kh[None], {"date": slice(di, di + 1)})
        event(log, "progress", f"stack date {d} done", stage="build_stack", done=di + 1, total=len(dates))
    st.write("bperp", bp, ("date",), attrs={"units": "m", "where": "stack centre"})
    st.write("coreg_residual", resid, ("date", "axis"), attrs={"units": "pixels", "axis": "lines, samples"})
    return st
