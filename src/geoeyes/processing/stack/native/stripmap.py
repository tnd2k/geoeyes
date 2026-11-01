"""Coregistered stack for zero-Doppler stripmap / spotlight SLCs (COSMO-SkyMed, Capella, ...).

Per secondary: geometric offsets from orbits + DEM (``tops.secondary_offsets``), resampling of the
Doppler-deramped data, then a residual constant offset measured by amplitude phase-correlation on
tiles (orbit / timing errors of a few centimetres to metres) and a second resampling with it. The
output StackStore has the same variables and conventions as the Sentinel-1 builder (flattened
``slc``, ``kh``, ``bperp``, ``geometry_*``), plus ``coreg_residual`` (date, 2) lines/samples.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

from geoeyes.core.errors import DataError
from geoeyes.core.logging import event
from geoeyes.core.types import BBox
from geoeyes.geometry.dem import Dem
from geoeyes.io.stack import StackStore
from geoeyes.processing.stack.native import common, tops
from geoeyes.processing.stack.native.reuse import Reuse
from geoeyes.sensors.base import RadarGrid

log = logging.getLogger(__name__)
ENGINE = "geoeyes-native-stripmap/0.1"


@dataclass
class Scene:
    grid: RadarGrid
    read: Callable[[tuple[int, int, int, int]], np.ndarray]     # window (l0, l1, s0, s1) -> complex64


def _doppler_phase(g: RadarGrid, line, sample) -> np.ndarray:
    """Azimuth phase of the Doppler centroid, 2π f_dc(τ) η, used to baseband before interpolation."""
    if g.doppler is None:
        return np.zeros(np.broadcast(np.asarray(line), np.asarray(sample)).shape)
    return 2.0 * np.pi * g.doppler(g.sample_range_time(sample)) * g.line_time(line)


def resample(sec: Scene, off: tops.Offsets, *, pad: int = 8, order: int = 3) -> np.ndarray:
    g = sec.grid
    line = off.line + off.az_shift
    smp = off.sample + off.rg_shift
    l0 = int(max(np.floor(np.nanmin(line)) - pad, 0))
    l1 = int(min(np.ceil(np.nanmax(line)) + pad + 1, g.lines))
    s0 = int(max(np.floor(np.nanmin(smp)) - pad, 0))
    s1 = int(min(np.ceil(np.nanmax(smp)) + pad + 1, g.samples))
    if l1 <= l0 or s1 <= s0:
        raise DataError(f"{g.scene_id}: reference window falls outside the secondary image")
    data = sec.read((l0, l1, s0, s1))
    L, S = np.mgrid[l0:l1, s0:s1]
    base = data * np.exp(-1j * _doppler_phase(g, L, S)).astype(np.complex64)
    del L, S
    coords = [(line - l0).ravel(), (smp - s0).ravel()]
    re = map_coordinates(base.real, coords, order=order, mode="constant", cval=0.0)
    im = map_coordinates(base.imag, coords, order=order, mode="constant", cval=0.0)
    out = (re + 1j * im).reshape(off.line.shape).astype(np.complex64)
    out *= np.exp(1j * _doppler_phase(g, line, smp)).astype(np.complex64)
    inside = (line >= 0) & (line <= g.lines - 1) & (smp >= 0) & (smp <= g.samples - 1)
    out[~inside] = 0
    return out


def residual_offset(ref: np.ndarray, sec: np.ndarray, *, tile: int = 256,
                    upsample: int = 20) -> tuple[float, float, int]:
    """Median sub-pixel shift (lines, samples) of ``sec`` relative to ``ref`` from amplitude
    phase-correlation on tiles; returns (dl, ds, n_tiles used)."""
    from skimage.registration import phase_cross_correlation
    a, b = np.abs(ref), np.abs(sec)
    shifts = []
    for r in range(0, a.shape[0] - tile + 1, tile // 2):
        for c in range(0, a.shape[1] - tile + 1, tile // 2):
            ta, tb = a[r:r + tile, c:c + tile], b[r:r + tile, c:c + tile]
            if (tb == 0).mean() > 0.05:
                continue
            s, err, _ = phase_cross_correlation(ta, tb, upsample_factor=upsample, normalization=None)
            if err < 0.9:
                shifts.append(s)
    if len(shifts) < 4:
        return 0.0, 0.0, len(shifts)
    s = np.median(np.asarray(shifts), axis=0)
    # phase_cross_correlation returns the shift that registers ``tb`` onto ``ta``: sec content sits at -s
    return float(-s[0]), float(-s[1]), len(shifts)


COREG_MODELS = ("constant", "terrain")
MIN_RELIEF_M = 50.0                 # below this height spread, the terrain model has no height term


@dataclass
class OffsetModel:
    """Residual offsets of a secondary (lines, samples) as a + b·h_km + c·line_k + d·sample_k (line_k, sample_k:
    thousands of pixels from the window centre, h_km: km), fitted on amplitude cross-correlation tiles."""

    az: np.ndarray                   # (4,) coefficients
    rg: np.ndarray
    n_tiles: int
    rms: tuple[float, float]         # scatter of the tile offsets about the model (lines, samples)

    def field(self, h_km: np.ndarray, line_k: np.ndarray, sample_k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return (self.az[0] + self.az[1] * h_km + self.az[2] * line_k + self.az[3] * sample_k,
                self.rg[0] + self.rg[1] * h_km + self.rg[2] * line_k + self.rg[3] * sample_k)


def residual_model(ref: np.ndarray, sec: np.ndarray, h: np.ndarray, *, tile: int = 128, step: int = 96,
                   upsample: int = 50, max_err: float = 0.85) -> OffsetModel | None:
    """Terrain-dependent residual offsets of ``sec`` relative to ``ref`` (same window, ``h`` the DEM height (m)
    of every pixel). Commercial X-band SLCs (ICEYE) coregistered from their orbits keep an azimuth offset that
    grows with the terrain height (Tenerife 2026-02: up to 0.47 lines per km of relief, 0.3 lines scatter over the
    volcano with one constant): a constant leaves part of each slope misregistered. Tiles of amplitude
    phase-correlation, then a robust least-squares plane in (height, line, sample) per axis. None when fewer
    than 12 tiles correlate."""
    from skimage.registration import phase_cross_correlation
    a, b = np.abs(ref), np.abs(sec)
    ny, nx = a.shape
    rows = []
    for r in range(0, ny - tile + 1, step):
        for c in range(0, nx - tile + 1, step):
            ta, tb = a[r:r + tile, c:c + tile], b[r:r + tile, c:c + tile]
            if (tb == 0).mean() > 0.05 or (ta == 0).mean() > 0.05:
                continue
            s, err, _ = phase_cross_correlation(ta, tb, upsample_factor=upsample, normalization=None)
            if err < max_err:
                hh = h[r:r + tile, c:c + tile]
                # sec content sits at -s (phase_cross_correlation registers tb onto ta)
                rows.append((-s[0], -s[1], float(np.nanmean(hh)) / 1e3, (r + tile / 2 - ny / 2) / 1e3,
                             (c + tile / 2 - nx / 2) / 1e3))
    if len(rows) < 12:
        return None
    t = np.asarray(rows)
    use_h = np.nanstd(t[:, 2]) * 1e3 >= MIN_RELIEF_M
    G = np.column_stack([np.ones(len(t)), t[:, 2] - np.nanmean(t[:, 2]) if use_h else np.zeros(len(t)),
                         t[:, 3], t[:, 4]])
    hm = float(np.nanmean(t[:, 2]))
    coefs, rms = [], []
    for y in (t[:, 0], t[:, 1]):
        keep = np.isfinite(y) & np.all(np.isfinite(G), axis=1)
        for _ in range(4):                           # iterative 3-MAD rejection: tiles on layover, water, change
            x = np.linalg.lstsq(G[keep], y[keep], rcond=None)[0]
            r = y - G @ x
            mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep]))) + 1e-6
            new = keep & (np.abs(r) <= 3 * mad)
            if new.sum() == keep.sum() or new.sum() < 12:
                break
            keep = new
        if not use_h:
            x[1] = 0.0
        x[0] -= x[1] * hm                                # back to a + b·h_km
        coefs.append(x)
        rms.append(float(np.sqrt(np.mean(r[keep] ** 2))))
    return OffsetModel(coefs[0], coefs[1], len(t), (rms[0], rms[1]))


def _aoi_window(ref: RadarGrid, dem: Dem, aoi: BBox | None, margin: int) -> tuple[int, int, int, int]:
    if aoi is None:
        return 0, ref.lines, 0, ref.samples
    step_l, step_s = max(ref.lines // 60, 1), max(ref.samples // 60, 1)
    g = tops.reference_geometry(ref, dem, step_lines=step_l, step_samples=step_s)
    inside = (g.lon >= aoi.west) & (g.lon <= aoi.east) & (g.lat >= aoi.south) & (g.lat <= aoi.north)
    if not inside.any():
        raise DataError(f"AOI {aoi} is not inside {ref.scene_id}")
    L, S = np.meshgrid(g.lines, g.samples, indexing="ij")
    li, si = L[inside], S[inside]
    return (int(max(li.min() - step_l - margin, 0)), int(min(li.max() + step_l + margin + 1, ref.lines)),
            int(max(si.min() - step_s - margin, 0)), int(min(si.max() + step_s + margin + 1, ref.samples)))


MAX_HEADING_DIFF_DEG = 2.0
MAX_NEAR_RANGE_DIFF = 0.03          # relative: same beam / incidence
MAX_PRF_DIFF = 0.005                # relative, ICEYE only (see check_geometry)


def check_geometry(scenes: dict[date, Scene], reference: date) -> tuple[dict[date, Scene], list[str]]:
    """Keep the scenes acquired in the reference geometry: same pass direction and look side, heading within
    ``MAX_HEADING_DIFF_DEG``, near slant range within ``MAX_NEAR_RANGE_DIFF`` (same beam). COSMO-SkyMed and
    Capella folders carry no track number: this is what makes a folder of dates one stack. Returns the kept
    scenes and one reason per rejected date."""
    r = scenes[reference].grid
    kept, rejected = {}, []
    for d, sc in scenes.items():
        g = sc.grid
        why = []
        if g.pass_direction.lower() != r.pass_direction.lower():
            why.append(f"{g.pass_direction} pass")
        if g.look_side != r.look_side:
            why.append(f"{g.look_side}-looking")
        dh = (g.heading_deg - r.heading_deg + 180) % 360 - 180
        if abs(dh) > MAX_HEADING_DIFF_DEG:
            why.append(f"heading {g.heading_deg:.1f} deg vs {r.heading_deg:.1f}")
        dr = abs(g.near_range - r.near_range) / r.near_range
        if dr > MAX_NEAR_RANGE_DIFF:
            why.append(f"near range {g.near_range / 1e3:.1f} km vs {r.near_range / 1e3:.1f} km (other beam)")
        # ICEYE fixes the PRF per beam: another PRF = another beam / pointing, much lower coherence (Tenerife
        # 2026-02-27..03-01: PRF 4916 vs 4699 Hz, coherence 0.16-0.23 vs 0.4-0.8). Capella chooses it per collect.
        if r.sensor == "iceye" and abs(g.azimuth_time_interval / r.azimuth_time_interval - 1) > MAX_PRF_DIFF:
            why.append(f"PRF {1 / g.azimuth_time_interval:.0f} Hz vs {1 / r.azimuth_time_interval:.0f} Hz (other beam)")
        if why:
            rejected.append(f"{d}: {', '.join(why)}")
        else:
            kept[d] = sc
    return kept, rejected


def build_stripmap_stack(scenes: dict[date, Scene], reference: date, dem: Dem, out: Path, *, aoi: BBox | None = None,
                         margin: int = 64, stack_id: str = "", track_id: str = "", overwrite: bool = False,
                         geo_step: tuple[int, int] | None = None, geo_spacing_m: float = 15.0,
                         max_residual_iter: int = 2, previous: StackStore | None = None,
                         reuse_dates: set[date] | None = None, coreg_model: str = "constant") -> StackStore:
    """``geo_step`` (lines, samples) of the geometry grid; by default ~``geo_spacing_m`` on the ground
    (half an SRTM/Copernicus 30 m cell): the geometric phase must follow the DEM detail, which matters
    for small height ambiguities (X-band, long baselines).

    ``previous``: an earlier build of this stack (moved aside, not at ``out``); its ``reuse_dates`` are
    copied when it has the same reference and window (``reuse.Reuse``), the other dates are coregistered.

    ``coreg_model``: the residual offset left by the orbits, ``constant`` (one shift per secondary) or
    ``terrain`` (``residual_model``: a plane in height, line and sample per secondary)."""
    if coreg_model not in COREG_MODELS:
        raise DataError(f"coreg_model {coreg_model!r}: {' | '.join(COREG_MODELS)}")
    if reference not in scenes:
        raise DataError(f"reference date {reference} not in the scenes")
    scenes, rejected = check_geometry(scenes, reference)
    for msg in rejected:
        log.warning("scene left out (not the reference geometry): %s", msg)
    if len(scenes) < 3:
        raise DataError(f"{len(scenes)} scene(s) in the reference geometry, at least 3 needed")
    dates = sorted(scenes)
    ref = scenes[reference]
    rg = ref.grid
    win = _aoi_window(rg, dem, aoi, margin)
    y0, y1, x0, x1 = win
    ny, nx = y1 - y0, x1 - x0
    log.info("%s reference %s: window lines %d..%d, samples %d..%d (%d x %d)", rg.sensor, reference, *win, ny, nx)
    reuse = Reuse.open(previous, reuse_dates, reference, win)
    if geo_step is None:
        az_m = rg.azimuth_pixel_spacing or 2.0
        gr_m = (rg.range_pixel_spacing or 1.0) / np.sin(np.radians(35.0))     # ground range, approx.
        geo_step = (max(int(round(geo_spacing_m / az_m)), 1), max(int(round(geo_spacing_m / gr_m)), 1))
    log.info("geometry grid every %d lines x %d samples", *geo_step)
    geo = tops.reference_geometry(rg, dem, step_lines=geo_step[0], step_samples=geo_step[1], window=win)
    attrs = {"stack_id": stack_id, "track": track_id, "sensor": rg.sensor, "mode": "stripmap",
             "polarization": rg.polarization, "reference_date": str(reference), "wavelength_m": rg.wavelength,
             "azimuth_time_interval_s": rg.azimuth_time_interval, "range_sampling_rate_hz": rg.range_sampling_rate,
             "range_pixel_spacing_m": rg.range_pixel_spacing, "azimuth_pixel_spacing_m": rg.azimuth_pixel_spacing,
             "heading_deg": rg.heading_deg, "pass_direction": rg.pass_direction, "look_side": rg.look_side,
             "engine": ENGINE, "crop_rows": [y0, y1], "crop_samples": [x0, x1], "dem": dem.source,
             "coreg_model": coreg_model,
             "scenes": {str(d): scenes[d].grid.scene_id for d in dates},
             "sensing_mid_utc": {str(d): scenes[d].grid.sensing_mid.isoformat() for d in dates},
             "slc_convention": "flattened: interferogram = slc[ref] * conj(slc[k])",
             "bperp_convention": "+ = secondary above the reference line of sight",
             "phase_convention": "SLC phase exp(-j 4 pi R / lambda); range increase d between ref and k "
                                 "adds +4 pi d / lambda to slc[ref]*conj(slc[k]) (ps_lite sign = +1)"}
    st = StackStore.create(out, coords={"date": np.array(dates, dtype="datetime64[D]"), "y": np.arange(y0, y1),
                                        "x": np.arange(x0, x1)}, attrs=attrs, overwrite=overwrite)
    st.allocate("slc", ("date", "y", "x"), np.complex64, chunks={"y": 512, "x": 512})
    st.allocate("kh", ("date", "y", "x"), np.float32, chunks={"y": 512, "x": 512})
    ll, ss = np.arange(y0, y1, dtype=float), np.arange(x0, x1, dtype=float)
    h_win = None
    for key, val, unit in (("lat", geo.lat, "deg"), ("lon", geo.lon, "deg"), ("hgt", geo.h, "m"),
                           ("incidence", common.incidence(rg, geo), "deg"), ("slant_range", geo.r_ref, "m")):
        arr = geo.spline(val)(ll, ss).astype(np.float32)
        if key == "hgt":
            h_win = arr
        st.write(f"geometry_{key}", arr, ("y", "x"), attrs={"units": unit}, chunks={"y": 512, "x": 512})
    line_k = ((np.arange(ny) - ny / 2) / 1e3)[:, None]
    sample_k = ((np.arange(nx) - nx / 2) / 1e3)[None, :]
    models: dict[str, dict] = {}

    ref_slc = ref.read(win)
    bperp = np.zeros(len(dates), np.float32)
    resid = np.zeros((len(dates), 2), np.float32)
    for di, d in enumerate(dates):
        sc = scenes[d]
        if d == reference:
            block, kh = ref_slc, np.zeros((ny, nx), np.float32)
        elif reuse is not None and d in reuse:
            block, kh = reuse.block("slc", d), reuse.block("kh", d)
            bperp[di] = reuse.value("bperp", d)
            resid[di] = reuse.value("coreg_residual", d, (0.0, 0.0))
            log.info("%s: reused from the previous build", d)
        else:
            off = tops.secondary_offsets(rg, sc.grid, geo, win)
            res = resample(sc, off)
            n_tiles = 0
            if coreg_model == "terrain":
                acc = np.zeros(8)
                for _ in range(max_residual_iter):
                    m = residual_model(ref_slc, res, h_win)
                    if m is None:
                        log.warning("%s: too few correlating tiles for the terrain model, constant offset", d)
                        break
                    n_tiles = m.n_tiles
                    dl, ds = m.field(h_win / 1e3, line_k, sample_k)
                    acc += np.r_[m.az, m.rg]
                    off.line = off.line + dl
                    off.sample = off.sample + ds
                    res = resample(sc, off)
                    if max(np.abs(dl).max(), np.abs(ds).max()) < 0.02:
                        break
                models[str(d)] = {"az": [round(float(v), 4) for v in acc[:4]],
                                  "rg": [round(float(v), 4) for v in acc[4:]], "tiles": n_tiles}
                hm = float(np.nanmean(h_win)) / 1e3
                shift = (acc[0] + acc[1] * hm, acc[4] + acc[5] * hm)     # the field at the mean height
                log.info("%s: terrain coregistration %+.3f lines/km, %+.3f samples/km of height", d, acc[1], acc[5])
            else:
                for _ in range(max_residual_iter):
                    dl, ds, n_tiles = residual_offset(ref_slc, res)
                    if abs(dl) < 0.01 and abs(ds) < 0.01:
                        break
                    off.az_shift += dl
                    off.rg_shift += ds
                    res = resample(sc, off)
                shift = (off.az_shift, off.rg_shift)
            resid[di] = shift
            # The residual shift is a timing / range-bias error of the product: the signal phase still
            # follows the true range to the ground point, so the orbit-based geometric phase stays valid.
            block = (res * np.exp(1j * off.geom_phase)).astype(np.complex64)
            kh = geo.spline(common.height_sensitivity(rg, sc.grid, geo))(ll, ss).astype(np.float32)
            bp = common.perpendicular_baseline(rg, sc.grid, geo)
            bperp[di] = bp[bp.shape[0] // 2, bp.shape[1] // 2]
            log.info("%s: residual offset %+.3f lines, %+.3f samples (%d tiles), Bperp %.0f m", d, *shift,
                     n_tiles, bperp[di])
        st.write_region("slc", block[None], {"date": slice(di, di + 1)})
        st.write_region("kh", kh[None], {"date": slice(di, di + 1)})
        event(log, "progress", f"stack date {d} done", stage="build_stack", done=di + 1, total=len(dates))
    st.write("bperp", bperp, ("date",), attrs={"units": "m", "where": "stack centre"})
    st.write("coreg_residual", resid, ("date", "axis"), attrs={"units": "pixels", "axis": "lines, samples"})
    if models:
        st.update_attrs(coreg_terrain={"terms": "a + b h_km + c line_k + d sample_k (lines / samples)",
                                       "dates": models})
    return st
