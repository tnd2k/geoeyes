"""Sentinel-1 TOPS burst coregistration (native engine).

Per burst pair (reference burst R, secondary burst S with the same burst ID):

1. **Geometry** — on a coarse grid of R, ``rdr2geo`` with the DEM gives ground points; ``geo2rdr``
   with the orbit of S gives their line/sample in S and the slant range from S. Offsets and the
   geometric phase 4π/λ (R_S - R_R) are interpolated to every pixel of R.
2. **Deramp / resample / reramp** — S is multiplied by exp(-jφ) with the TOPS azimuth phase
   φ(η, τ) (Miranda 2017, ESA "Definition of the TOPS SLC deramping function"), interpolated at the
   offset positions, and the ramp is put back at those positions.
3. **ESD** — the double-difference phase of the interferograms of consecutive bursts in their
   overlap measures the residual azimuth misregistration Δη = φ_ESD / (2π Δf_ovl); it is applied as
   a constant azimuth shift and the resampling is repeated (Prats-Iraola et al. 2012).

Lines/samples are burst coordinates (0 = first line/sample of the burst GeoTIFF).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import RectBivariateSpline
from scipy.ndimage import map_coordinates

from geoeyes.geometry.dem import Dem
from geoeyes.geometry.rdr2geo import geo2rdr, llh_grid_guess, rdr2geo
from geoeyes.sensors.sentinel1.burst import BurstMetadata, C

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- TOPS azimuth ramp
def tops_phase(m: BurstMetadata, line, sample) -> np.ndarray:
    """TOPS azimuth phase φ(η, τ) at (fractional) burst line/sample; deramp = data · exp(-jφ)."""
    line = np.asarray(line, np.float64)
    tau = m.sample_range_time(sample)
    t_mid = m.orbit.seconds(m.sensing_mid)
    _, v = m.orbit.interpolate(t_mid)
    vs = float(np.linalg.norm(v))
    ks = 2.0 * vs / m.wavelength * m.azimuth_steering_rate          # Doppler rate from beam steering
    ka = m.fm_rate(tau)                                               # azimuth FM rate
    kt = ka * ks / (ka - ks)                                          # Doppler centroid rate in focused data
    fdc = m.doppler(tau)
    eta = (line - m.lines / 2.0) * m.azimuth_time_interval           # zero-Doppler time from burst centre
    eta_c = -fdc / ka                                                 # beam-centre crossing time
    tau_mid = m.slant_range_time + m.samples / 2.0 / m.range_sampling_rate
    eta_ref = eta_c - (-m.doppler(tau_mid) / m.fm_rate(tau_mid))
    d = eta - eta_ref
    return np.pi * kt * d * d + 2.0 * np.pi * fdc * d


def doppler_rate(m: BurstMetadata, sample) -> np.ndarray:
    """k_t(τ): Doppler centroid rate of the focused burst (Hz/s)."""
    tau = m.sample_range_time(sample)
    _, v = m.orbit.interpolate(m.orbit.seconds(m.sensing_mid))
    ks = 2.0 * float(np.linalg.norm(v)) / m.wavelength * m.azimuth_steering_rate
    ka = m.fm_rate(tau)
    return ka * ks / (ka - ks)


# ----------------------------------------------------------------------------- geometry
@dataclass
class BurstGeometry:
    """Reference-burst geometry on a coarse grid, plus per-pixel interpolators."""

    lines: np.ndarray          # coarse grid line coordinates (burst)
    samples: np.ndarray
    lat: np.ndarray            # (nl, ns)
    lon: np.ndarray
    h: np.ndarray
    xyz: np.ndarray            # (nl, ns, 3)
    t_ref: np.ndarray          # orbit seconds of the reference
    r_ref: np.ndarray          # slant range from the reference (m)

    def spline(self, values: np.ndarray, kx: int = 3, ky: int = 3) -> RectBivariateSpline:
        return RectBivariateSpline(self.lines, self.samples, values, kx=kx, ky=ky)


def reference_geometry(m: BurstMetadata, dem: Dem, *, step_lines: int = 32, step_samples: int = 128,
                       window: tuple[int, int, int, int] | None = None) -> BurstGeometry:
    """Ground points of the reference on a coarse grid over ``window`` (default: the whole image).
    ``m`` is any radar grid with the BurstMetadata interface (also ``sensors.base.RadarGrid``)."""
    l0, l1, s0, s1 = window if window is not None else (0, m.lines, 0, m.samples)
    lines = np.unique(np.r_[np.arange(l0, l1, step_lines), l1 - 1]).astype(np.float64)
    samples = np.unique(np.r_[np.arange(s0, s1, step_samples), s1 - 1]).astype(np.float64)
    L, S = np.meshgrid(lines, samples, indexing="ij")
    t = m.orbit_seconds(L)
    r = m.slant_range(S)
    lat0, lon0 = llh_grid_guess(m.grid.line, m.grid.pixel, m.grid.lat, m.grid.lon, L, S)
    g = rdr2geo(m.orbit, t, r, dem, lat0, lon0)
    return BurstGeometry(lines, samples, g["lat"], g["lon"], g["h"], g["xyz"], t, r)


@dataclass
class Offsets:
    """Where every reference pixel is in the secondary burst, and the geometric phase."""

    line: np.ndarray           # (L, S) fractional secondary line
    sample: np.ndarray
    geom_phase: np.ndarray     # 4π/λ (R_sec - R_ref), rad
    az_shift: float = 0.0      # ESD / residual correction applied to ``line`` (lines)
    rg_shift: float = 0.0      # residual correction applied to ``sample`` (stripmap coregistration)


def secondary_offsets(ref: BurstMetadata, sec: BurstMetadata, geo: BurstGeometry,
                      window: tuple[int, int, int, int]) -> Offsets:
    """Offsets for the reference pixels inside ``window`` (l0, l1, s0, s1)."""
    t_guess = sec.orbit_seconds(geo.lines[:, None] * np.ones_like(geo.samples)[None, :])
    t_sec, r_sec = geo2rdr(sec.orbit, geo.xyz, t_guess)
    line_sec = (t_sec - sec.orbit.seconds(sec.sensing_start)) / sec.azimuth_time_interval
    sample_sec = (2.0 * r_sec / C - sec.slant_range_time) * sec.range_sampling_rate
    phase = 4.0 * np.pi / ref.wavelength * (r_sec - geo.r_ref)
    l0, l1, s0, s1 = window
    ll = np.arange(l0, l1, dtype=np.float64)
    ss = np.arange(s0, s1, dtype=np.float64)
    return Offsets(geo.spline(line_sec)(ll, ss), geo.spline(sample_sec)(ll, ss), geo.spline(phase)(ll, ss))


# ----------------------------------------------------------------------------- resampling
def resample_secondary(sec: BurstMetadata, slc: np.ndarray, off: Offsets, *, order: int = 3,
                       pad: int = 8) -> np.ndarray:
    """Secondary burst resampled onto the reference grid (deramp → interpolate → reramp).

    Only the part of the secondary burst the offsets point into (plus ``pad``) is deramped.
    """
    line = off.line + off.az_shift
    l0 = int(max(np.floor(np.nanmin(line)) - pad, 0))
    l1 = int(min(np.ceil(np.nanmax(line)) + pad + 1, slc.shape[0]))
    s0 = int(max(np.floor(np.nanmin(off.sample)) - pad, 0))
    s1 = int(min(np.ceil(np.nanmax(off.sample)) + pad + 1, slc.shape[1]))
    if l1 <= l0 or s1 <= s0:
        return np.zeros(off.line.shape, np.complex64)
    L, S = np.mgrid[l0:l1, s0:s1]
    base = slc[l0:l1, s0:s1] * np.exp(-1j * tops_phase(sec, L, S)).astype(np.complex64)
    del L, S
    coords = [(line - l0).ravel(), (off.sample - s0).ravel()]
    re = map_coordinates(base.real, coords, order=order, mode="constant", cval=0.0, prefilter=True)
    im = map_coordinates(base.imag, coords, order=order, mode="constant", cval=0.0, prefilter=True)
    out = (re + 1j * im).reshape(off.line.shape).astype(np.complex64)
    out *= np.exp(1j * tops_phase(sec, line, off.sample)).astype(np.complex64)
    inside = (line >= 0) & (line <= slc.shape[0] - 1) & (off.sample >= 0) & (off.sample <= slc.shape[1] - 1)
    out[~inside] = 0
    return out


def interferogram(ref_slc: np.ndarray, sec_resampled: np.ndarray, off: Offsets) -> np.ndarray:
    """ref · conj(sec) with the geometric (flat-earth + topographic) phase removed."""
    return (ref_slc * np.conj(sec_resampled) * np.exp(-1j * off.geom_phase)).astype(np.complex64)


# ----------------------------------------------------------------------------- ESD
@dataclass
class OverlapIfg:
    """Interferograms of two consecutive bursts over the same ground, and their Doppler gap."""

    ifg_first: np.ndarray      # from burst i (its last lines)
    ifg_second: np.ndarray     # from burst i+1 (its first lines)
    delta_f: np.ndarray        # Doppler difference f_i - f_{i+1} at the same ground (Hz)


def esd_shift(overlaps: list[OverlapIfg], azimuth_time_interval: float, *, coh_min: float = 0.3,
              win: int = 5) -> tuple[float, dict]:
    """Residual azimuth misregistration (lines) from the overlap double-difference phase.

    The double-difference phasors of coherent pixels are summed (coherent average) and the angle of
    the sum gives the ESD phase; averaging per-pixel angles instead would be biased toward zero by
    noisy pixels, whose phase is uniform around zero. Δf varies little across an overlap, so its
    mean over the pixels used converts phase to time.
    """
    from scipy.ndimage import uniform_filter
    total, w_sum, df_sum, n = 0j, 0.0, 0.0, 0
    per_overlap = []
    for o in overlaps:
        dd = o.ifg_first * np.conj(o.ifg_second)
        num = uniform_filter(dd.real, win) + 1j * uniform_filter(dd.imag, win)
        den = np.sqrt(uniform_filter(np.abs(o.ifg_first) ** 2, win) * uniform_filter(np.abs(o.ifg_second) ** 2, win))
        coh = np.abs(num) / np.maximum(den, 1e-12)
        ok = coh > coh_min
        if not ok.any():
            continue
        w = coh[ok]
        z = np.sum(num[ok] / np.maximum(np.abs(num[ok]), 1e-12) * w)    # unit phasors weighted by coherence
        total += z
        w_sum += float(w.sum())
        df_sum += float(np.sum(o.delta_f[ok] * w))
        n += int(ok.sum())
        per_overlap.append(float(np.angle(z)))
    if n == 0:
        return 0.0, {"n": 0}
    phase = float(np.angle(total))
    df = df_sum / w_sum
    shift_s = phase / (2.0 * np.pi * df)
    return shift_s / azimuth_time_interval, {"n": n, "phase_rad": phase, "delta_f_hz": df,
                                             "shift_s": shift_s, "per_overlap_rad": per_overlap}
