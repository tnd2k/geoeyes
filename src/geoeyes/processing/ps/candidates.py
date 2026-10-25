"""PS candidate selection on a flattened stack (port of the legacy StaMPS prep: ``calamp`` +
``RobustAmplitudeDispersion`` + amplitude floor + ``pscphase`` coherence + lon/lat de-duplication).

Amplitudes are calibrated per date by the scene mean; with ``smooth_sigma`` > 0 each date is further divided
by its own Gaussian-smoothed local mean (removes aperture taper / slow backscatter trends; pixels within
``edge_margin`` of the border are excluded since that normalisation is biased there). D_A follows StaMPS
``selpsc``: sqrt(k·Σa²/(Σa)² − 1) with k the number of valid dates. Candidates have D_A ≤ ``da_max`` and a
mean calibrated amplitude above an Otsu (log-amplitude) floor that separates water from land.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

log = logging.getLogger(__name__)
AMP_MIN = 5e-5                 # selpsc_patch threshold on calibrated amplitude


def calibration_factor(amp: np.ndarray) -> float:
    """Mean |SLC| over amplitudes > 0.001, ignoring a corrupt tail above 30x the 99.999 percentile
    (legacy ``calamp``)."""
    a = np.asarray(amp, np.float64).ravel()
    base = np.isfinite(a) & (a > 0.001)
    if not base.any():
        return 0.0
    hi = max(float(np.percentile(a[base], 99.999)) * 30.0, 0.05)
    ok = base & (a <= hi)
    return float(np.sum(a[ok]) / np.count_nonzero(ok))


@dataclass
class Dispersion:
    da: np.ndarray            # (ny, nx) float32, +inf where undefined
    raw_mean_amp: np.ndarray  # (ny, nx) float32 mean calibrated amplitude (no spatial normalisation)
    count: np.ndarray         # (ny, nx) int16 valid dates
    calib: np.ndarray         # (n_dates,) calibration factors


def _smooth_mean(x, valid, sigma):
    num = ndimage.gaussian_filter(np.where(valid, x, 0.0).astype(np.float64), sigma=sigma, mode="nearest")
    den = ndimage.gaussian_filter(valid.astype(np.float64), sigma=sigma, mode="nearest")
    out = np.full(x.shape, np.nan)
    ok = den > 1e-3
    out[ok] = num[ok] / den[ok]
    return out


def amplitude_dispersion(amplitude: Callable[[int], np.ndarray], n_dates: int, *, smooth_sigma: float = 28.0,
                         edge_margin: int = 28, min_layers: int = 2, coverage_min_ratio: float = 0.5,
                         band_lines: int = 200) -> Dispersion:
    """``amplitude(k)`` returns date k's |SLC| (float32, NaN/≤1e-6 = no data). Dates with a much lower
    valid-pixel count than the median in an azimuth band are ignored in that band."""
    amps = []
    for k in range(n_dates):
        a = np.asarray(amplitude(k), np.float32).copy()
        a[~np.isfinite(a) | (a <= 1e-6)] = np.nan
        amps.append(a)
    ny, nx = amps[0].shape
    calib = np.array([calibration_factor(a) for a in amps])
    n_bands = max(1, int(np.ceil(ny / band_lines)))
    counts = np.array([[np.sum(np.isfinite(a[b * band_lines:(b + 1) * band_lines])) for b in range(n_bands)]
                       for a in amps], np.float64)
    outlier = counts < coverage_min_ratio * np.median(counts, axis=0)[None, :]

    raw_cnt = np.zeros((ny, nx), np.int32)
    raw_sum = np.zeros((ny, nx))
    s1 = np.zeros((ny, nx))
    s2 = np.zeros((ny, nx))
    cnt = np.zeros((ny, nx), np.int16)
    for k, a in enumerate(amps):
        norm = a / np.float32(calib[k])
        valid = np.isfinite(norm) & (norm > AMP_MIN)
        for b in np.flatnonzero(outlier[k]):
            valid[b * band_lines:(b + 1) * band_lines] = False
        raw_cnt += valid
        raw_sum += np.where(valid, norm, 0.0)
        if smooth_sigma > 0:
            sm = _smooth_mean(norm, valid, smooth_sigma)
            ok = valid & np.isfinite(sm) & (sm > AMP_MIN)
            final = np.where(ok, norm / sm, np.nan)
            valid = ok & np.isfinite(final) & (final > AMP_MIN)
        else:
            final = norm
        s1 += np.where(valid, final, 0.0)
        s2 += np.where(valid, final.astype(np.float64) ** 2, 0.0)
        cnt += valid.astype(np.int16)
    with np.errstate(invalid="ignore", divide="ignore"):
        raw_mean = np.where(raw_cnt >= 1, raw_sum / np.maximum(raw_cnt, 1), np.nan).astype(np.float32)
        k = cnt.astype(np.float64)
        dsq = np.maximum(np.where(k >= min_layers, k * s2 / np.maximum(s1 * s1, 1e-30) - 1.0, np.nan), 0.0)
        da = np.where(k >= min_layers, np.sqrt(dsq), np.inf).astype(np.float32)
    if smooth_sigma > 0 and edge_margin > 0:
        m = edge_margin
        da[:m, :] = da[-m:, :] = np.inf
        da[:, :m] = da[:, -m:] = np.inf
    return Dispersion(da=da, raw_mean_amp=raw_mean, count=cnt, calib=calib)


def otsu_amplitude_floor(raw_mean_amp: np.ndarray) -> float | None:
    """Otsu split of log10 mean amplitude (water/land); None with < 100 valid pixels."""
    from skimage.filters import threshold_otsu
    v = raw_mean_amp[np.isfinite(raw_mean_amp) & (raw_mean_amp > 0)]
    if v.size < 100:
        return None
    return float(10.0 ** float(threshold_otsu(np.log10(v.astype(np.float64)))))


def select(disp: Dispersion, da_max: float = 0.4, amp_floor: float | None = None):
    """(rows, cols, da) of the candidates, sorted by D_A."""
    keep = disp.da <= da_max
    if amp_floor is not None:
        keep &= np.isfinite(disp.raw_mean_amp) & (disp.raw_mean_amp >= amp_floor)
    r, c = np.where(keep)
    d = disp.da[r, c]
    order = np.argsort(d)
    return r[order], c[order], d[order]


def select_ds(tcoh: np.ndarray, exclude: np.ndarray, tcoh_min: float, cell: int = 3):
    """(rows, cols) of distributed scatterers: per ``cell``×``cell`` block the pixel of highest phase-linking
    temporal coherence, if ``>= tcoh_min`` and not ``exclude`` (already a PS candidate)."""
    ny, nx = tcoh.shape
    t = np.where(np.isfinite(tcoh) & ~exclude, tcoh, -np.inf)
    by, bx = -(-ny // cell), -(-nx // cell)
    t = np.pad(t, ((0, by * cell - ny), (0, bx * cell - nx)), constant_values=-np.inf)
    blocks = t.reshape(by, cell, bx, cell).transpose(0, 2, 1, 3).reshape(by, bx, cell * cell)
    k = blocks.argmax(-1)
    best = np.take_along_axis(blocks, k[..., None], -1)[..., 0]
    bi, bj = np.nonzero(best >= tcoh_min)
    return bi * cell + k[bi, bj] // cell, bj * cell + k[bi, bj] % cell


def pair_coherence(slc_ref: np.ndarray, slc_sec: np.ndarray, rows, cols, window=(2, 10)) -> np.ndarray:
    """Boxcar coherence of slc_ref·conj(slc_sec) (zero-padded window) at the given pixels."""
    a, b = slc_ref.astype(np.complex64), slc_sec.astype(np.complex64)
    cross = a * np.conj(b)
    f = (lambda x: ndimage.uniform_filter(x, size=window, mode="constant"))  # noqa: E731
    num = np.hypot(f(cross.real), f(cross.imag))
    den = np.sqrt(f(a.real**2 + a.imag**2) * f(b.real**2 + b.imag**2))
    coh = np.zeros(den.shape, np.float32)
    ok = den > 1e-12
    coh[ok] = np.clip(num[ok] / den[ok], 0.0, 1.0).astype(np.float32)
    return coh[rows, cols]


def prior_coherence(coh_ifg: np.ndarray, ph: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Per candidate: max(mean positive pair coherence, temporal coherence |Σ e^{iφ}|/N), clipped."""
    z = np.asarray(ph, np.complex128)
    mag = np.abs(z)
    zn = np.where(mag > 0, z / np.where(mag > 0, mag, 1.0), 0)
    temporal = np.abs(zn.sum(axis=1)) / z.shape[1]
    c = np.asarray(coh_ifg, np.float64)
    valid = np.isfinite(c) & (c > 0)
    n = valid.sum(axis=1)
    mean = np.zeros(c.shape[0])
    mean[n > 0] = np.where(valid, c, 0).sum(axis=1)[n > 0] / n[n > 0]
    out = np.maximum(mean, temporal)
    out[~np.isfinite(out)] = temporal[~np.isfinite(out)]
    return np.clip(np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0), eps, 1 - eps)


def dedup_lonlat(lonlat: np.ndarray, da: np.ndarray) -> np.ndarray:
    """Indices keeping one candidate per (lon, lat) rounded to 1e-8 deg, the lowest D_A (then the first)."""
    ll = np.round(np.asarray(lonlat, np.float64), 8)
    order = np.lexsort((np.arange(len(da)), da, ll[:, 1], ll[:, 0]))
    s = ll[order]
    first = np.r_[True, np.any(s[1:] != s[:-1], axis=1)]
    return np.sort(order[first])


def terrain_shift_lonlat(lon, lat, hgt, inc_rad, heading_deg, earth_radius):
    """Legacy prep's lon/lat "terrain correction": move each pixel by h/tan(θ) along the ground range
    (θ from the orbit geometry). Only for grids geolocated at zero height (SNAP tie points); native stack
    geometry is already at the DEM height, so the native runner does not apply it."""
    tan_inc = np.where(np.tan(inc_rad) > 0.01, np.tan(inc_rad), 0.01)
    dgr = hgt / tan_inc
    theta = (180.0 - heading_deg) * np.pi / 180.0
    cos_lat = np.cos(np.radians(lat))
    cos_lat = np.where(np.abs(cos_lat) > 1e-6, cos_lat, 1e-6)
    return (lon - np.degrees(dgr * np.cos(theta) / (earth_radius * cos_lat)),
            lat - np.degrees(dgr * np.sin(theta) / earth_radius))


__all__ = ["Dispersion", "amplitude_dispersion", "calibration_factor", "dedup_lonlat", "otsu_amplitude_floor",
           "pair_coherence", "prior_coherence", "select", "terrain_shift_lonlat"]
