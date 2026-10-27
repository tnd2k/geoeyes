"""Ionospheric phase of a Sentinel-1 interferogram by range split-spectrum (Gomba et al. 2016, IEEE TGRS 54(3);
docs/en/research/two-geometries-and-soft-soil.md §4.2).

The ionosphere delays the radar signal in proportion to 1/f (dispersive), the troposphere and the ground motion in
proportion to f (non-dispersive). Two sub-bands of the range spectrum, centred at f_L = f0 − B/3 and f_H = f0 + B/3
with a width of B/3 (B: the smallest processed bandwidth of the subswaths used), give two interferograms

    φ_k = φ_nd · f_k / f0 + φ_iono · f0 / f_k,

whence the ionospheric phase at the centre frequency

    φ_iono = f_L·f_H / (f0·(f_H² − f_L²)) · (φ_L·f_H − φ_H·f_L).

The stack keeps flattened SLCs, so the sub-band interferograms are formed before the flattening, from the
reference burst and the resampled secondary. Both are flattened with the same geometric phase as the full band:
the resampling has already moved the secondary echo onto the reference pixel, so its geometric phase is that of
the centre frequency in every sub-band; only the delays the coregistration did not model (motion, troposphere,
ionosphere, DEM error) scale with f_k. Scaling the geometric phase by f_k / f0 would leave hundreds of radians in
the sub-bands, half of which would leak into φ_iono.

The estimate amplifies the phase noise ~f0 / (2·(f_H − f_L)) ≈ 90 times: it is formed on coarse cells (450 m) over
the whole bursts, from φ_L (unwrapped) and the small difference φ_H − φ_L (not wrapped), and a low-order surface
(quadratic by default) is fitted to it and evaluated on the stack crop. The secondary sub-bands are interpolated
linearly: only the coarse cells are used.
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


def subbands(f0: float, bandwidth: float) -> tuple[float, float, float]:
    """(f_L, f_H, width) of the two sub-bands."""
    return f0 - bandwidth / 3.0, f0 + bandwidth / 3.0, bandwidth / 3.0


def bandpass(slc: np.ndarray, offset_hz: float, width_hz: float, fs: float) -> np.ndarray:
    """Range sub-band of ``slc`` (lines × samples) centred ``offset_hz`` from the centre of the spectrum, ``width_hz``
    wide (cosine-tapered edges); returned at full sampling."""
    n = slc.shape[1]
    f = np.fft.fftfreq(n, 1.0 / fs)
    half = width_hz / 2.0
    taper = 0.1 * width_hz
    d = np.abs(f - offset_hz)
    edge = 0.5 * (1 + np.cos(np.pi * (d - half + taper) / taper))
    w = np.where(d <= half - taper, 1.0, np.where(d >= half, 0.0, edge))
    return np.fft.ifft(np.fft.fft(slc, axis=1) * w[None, :], axis=1).astype(np.complex64)


def resample_subband(sec, slc: np.ndarray, off, offset_hz: float, width_hz: float, fs: float, *, order: int = 1,
                     pad: int = 64) -> np.ndarray:
    """Range sub-band of the secondary burst resampled onto the reference grid, as ``tops.resample_secondary`` but
    filtered on the secondary grid and interpolated without its range carrier (moved to baseband, interpolated,
    moved back at the new positions): interpolating the carrier itself (±0.2 cycle per sample) would bend the
    phase of each sub-band differently."""
    from scipy.ndimage import map_coordinates

    from geoeyes.processing.stack.native.tops import tops_phase
    line = off.line + off.az_shift
    l0 = int(max(np.floor(np.nanmin(line)) - 8, 0))
    l1 = int(min(np.ceil(np.nanmax(line)) + 9, slc.shape[0]))
    s0 = int(max(np.floor(np.nanmin(off.sample)) - pad, 0))
    s1 = int(min(np.ceil(np.nanmax(off.sample)) + pad + 1, slc.shape[1]))
    if l1 <= l0 or s1 <= s0:
        return np.zeros(off.line.shape, np.complex64)
    L, S = np.mgrid[l0:l1, s0:s1]
    blk = bandpass(slc[l0:l1, s0:s1], offset_hz, width_hz, fs)
    carrier = 2 * np.pi * offset_hz / fs
    base = blk * np.exp(-1j * (tops_phase(sec, L, S) + carrier * S)).astype(np.complex64)
    del L, S, blk
    coords = [(line - l0).ravel(), (off.sample - s0).ravel()]
    re = map_coordinates(base.real, coords, order=order, mode="constant", cval=0.0, prefilter=True)
    im = map_coordinates(base.imag, coords, order=order, mode="constant", cval=0.0, prefilter=True)
    out = (re + 1j * im).reshape(off.line.shape).astype(np.complex64)
    out *= np.exp(1j * (tops_phase(sec, line, off.sample) + carrier * off.sample)).astype(np.complex64)
    inside = (line >= 0) & (line <= slc.shape[0] - 1) & (off.sample >= 0) & (off.sample <= slc.shape[1] - 1)
    out[~inside] = 0
    return out


def subband_ifgs(ref: np.ndarray, sec_meta, sec_slc: np.ndarray, off, f0: float, bandwidth: float,
                 fs: float, *, order: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Flattened low and high sub-band interferograms ref·conj(sec_k)·exp(−j·geom) on the reference window ``ref``
    (``off``: the offsets of that window into the secondary burst ``sec_slc``)."""
    fl, fh, width = subbands(f0, bandwidth)
    out = []
    for fk in (fl, fh):
        r = bandpass(ref, fk - f0, width, fs)
        s = resample_subband(sec_meta, sec_slc, off, fk - f0, width, fs, order=order)
        out.append((r * np.conj(s) * np.exp(-1j * off.geom_phase)).astype(np.complex64))
    return out[0], out[1]


class WideArea:
    """Sums of the sub-band interferograms on coarse cells (``looks``) of the whole debursted grid of the bursts:
    the ionosphere is estimated over the bursts (~140 × 40 km for two IW subswaths), not over the AOI crop, where
    the C-band estimate is too noisy (docs/en/research/two-geometries-and-soft-soil.md §4.2)."""

    def __init__(self, rows: tuple[int, int], cols: tuple[int, int], looks: tuple[int, int]):
        self.r0, self.c0 = rows[0], cols[0]
        self.la, self.lr = looks
        self.ny = (rows[1] - rows[0] + self.la - 1) // self.la
        self.nx = (cols[1] - cols[0] + self.lr - 1) // self.lr
        n = self.ny * self.nx
        self.low = np.zeros(n, np.complex128)
        self.cross = np.zeros(n, np.complex128)
        self.low_abs = np.zeros(n)
        self.cross_abs = np.zeros(n)
        self.low_parts: dict[int, np.ndarray] = {}     # low-band sums of each subswath, for ``shift``

    def shift(self, offsets: dict[int, float]) -> None:
        """Remove a constant phase (rad) from the low-band interferogram of each subswath (``offsets`` by
        ``part``): the phase step between subswaths measured on the full band, the same in both sub-bands, so the
        cross interferogram keeps no trace of it while ``a·c`` of it would pass into the dispersive estimate."""
        self.low = sum((v * np.exp(-1j * offsets.get(k, 0.0)) for k, v in self.low_parts.items()),
                       np.zeros_like(self.low))

    def add(self, lo: np.ndarray, hi: np.ndarray, row0: int, col0: int, rows_ok: tuple[int, int],
            cols_ok: tuple[int, int], part: int = 0) -> None:
        """Add sub-band interferograms whose first pixel is at merged (``row0``, ``col0``); only the merged rows and
        columns of the burst's own segment (``rows_ok``, ``cols_ok``) are kept, so overlaps count once. ``part``:
        the subswath (0, 1, … from near range), for ``shift``."""
        rr = np.arange(lo.shape[0]) + row0
        cc = np.arange(lo.shape[1]) + col0
        mr = (rr >= max(rows_ok[0], self.r0)) & (rr < rows_ok[1])
        mc = (cc >= max(cols_ok[0], self.c0)) & (cc < cols_ok[1])
        if not mr.any() or not mc.any():
            return
        lo, hi = lo[mr][:, mc], hi[mr][:, mc]
        idx = (((rr[mr] - self.r0) // self.la)[:, None] * self.nx + ((cc[mc] - self.c0) // self.lr)[None, :])
        ok = (lo != 0) & (hi != 0) & (idx < self.ny * self.nx)
        i = idx[ok]
        x = (hi * np.conj(lo))[ok]
        v = lo[ok]
        n = self.ny * self.nx
        lv = np.bincount(i, v.real, n) + 1j * np.bincount(i, v.imag, n)
        self.low += lv
        self.low_parts[part] = self.low_parts.get(part, 0) + lv
        self.cross += np.bincount(i, x.real, n) + 1j * np.bincount(i, x.imag, n)
        self.low_abs += np.bincount(i, np.abs(v), n)
        self.cross_abs += np.bincount(i, np.abs(x), n)


def estimate_wide(area: WideArea, f0: float, bandwidth: float, *, spacing_m: tuple[float, float],
                  rows: tuple[int, int], cols: tuple[int, int], model: str = "local", smooth_km: float = 10.0,
                  min_cross_coherence: float = 0.7) -> tuple[np.ndarray, dict]:
    """Ionospheric phase (rad, at f0) of the merged ``rows`` × ``cols`` crop, from the sums of ``area``.

    Fitted by weighted least squares (weights g²/(1−g²) of the sub-band cross coherence g, cells beyond 3 MAD
    dropped). A phase step between subswaths must be removed beforehand (``WideArea.shift``): fitted here as a
    free constant per subswath it trades off with the range gradient (±4 rad on Hanoi asc 128, on dates with
    no step at all). ``model``:
    * "local" (default): a plane around the crop, the cells weighted by a Gaussian of ``smooth_km`` from its
      centre: the dusk ionosphere over Hanoi has structure at 10–30 km that a surface over the whole bursts
      smooths away, while the crop alone (~15 km) is too noisy;
    * "quadratic" or "plane": over the whole bursts;
    * "smooth": a Gaussian surface of ``smooth_km``."""
    from scipy.interpolate import RegularGridInterpolator
    from scipy.ndimage import gaussian_filter

    from geoeyes.processing.ps.unwrap.irls import irls_unwrap_weighted
    fl, fh, _ = subbands(f0, bandwidth)
    shape = (area.ny, area.nx)
    low, cross = area.low.reshape(shape), area.cross.reshape(shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        coh_low = np.where(area.low_abs > 0, np.abs(area.low) / area.low_abs, 0.0).reshape(shape)
        coh_x = np.where(area.cross_abs > 0, np.abs(area.cross) / area.cross_abs, 0.0).reshape(shape)
    usable = coh_low >= 0.3
    unw, _ = irls_unwrap_weighted(np.where(usable, np.angle(low), np.nan).astype(np.float32),
                                  (coh_low ** 2).astype(np.float32))
    a = fl * fh / (f0 * (fh + fl))
    b = fl * fl * fh / (f0 * (fh * fh - fl * fl))
    ok = usable & (coh_x >= min_cross_coherence)
    if ok.sum() < 30:
        raise ValueError(f"only {int(ok.sum())} coherent cells for the ionosphere")
    iono = np.where(ok, a * unw - b * np.angle(cross), np.nan)
    w = np.where(ok, coh_x ** 2 / np.maximum(1 - coh_x ** 2, 1e-3), 0.0)
    km_y, km_x = area.la * spacing_m[0] / 1000.0, area.lr * spacing_m[1] / 1000.0
    jj, ii = np.nonzero(ok)

    def design(yk, xk):
        cols_ = [np.ones_like(yk), yk, xk]
        if model == "quadratic":
            cols_ += [yk * yk, yk * xk, xk * xk]
        if model == "local":                         # centred, so that the constant is the value at the crop
            cols_ = [np.ones_like(yk), yk - yc, xk - xc]
        return np.column_stack(cols_)
    yk, xk = (jj + 0.5) * km_y, (ii + 0.5) * km_x
    py = (np.arange(rows[0], rows[1]) - area.r0 + 0.5) / area.la * km_y
    px = (np.arange(cols[0], cols[1]) - area.c0 + 0.5) / area.lr * km_x
    yc, xc = py.mean(), px.mean()
    A = design(yk, xk)
    v, ww = iono[jj, ii], w[jj, ii]
    if model == "local":
        ww = ww * np.exp(-((yk - yc) ** 2 + (xk - xc) ** 2) / (2 * smooth_km ** 2))
    keep = ww > 1e-4 * ww.max()
    for _ in range(4):
        sw = np.sqrt(ww[keep])
        coef = np.linalg.lstsq(A[keep] * sw[:, None], v[keep] * sw, rcond=None)[0]
        r = v - A @ coef
        mad = np.median(np.abs(r[keep] - np.median(r[keep])))
        keep = (ww > 1e-4 * ww.max()) & (np.abs(r - np.median(r[keep])) <= 3 * 1.4826 * max(mad, 1e-3))
    r = (v - A @ coef)[keep]
    scale = float(np.sum(ww[keep] * r ** 2)) / max(1, int(keep.sum()) - A.shape[1])
    cov = np.linalg.inv((A[keep] * ww[keep][:, None]).T @ A[keep]) * scale
    smooth_px = smooth_km / km_y
    if model == "smooth":
        wk = np.zeros_like(w)
        wk[jj[keep], ii[keep]] = ww[keep]
        smooth = gaussian_filter(np.nan_to_num(iono) * wk, smooth_px) / np.maximum(gaussian_filter(wk, smooth_px), 1e-6)
        f = RegularGridInterpolator(((np.arange(area.ny) + 0.5) * km_y, (np.arange(area.nx) + 0.5) * km_x), smooth,
                                    bounds_error=False, fill_value=None)
        Y, X = np.meshgrid(py, px, indexing="ij")
        full = f((Y, X))
    else:
        Y, X = np.meshgrid(py, px, indexing="ij")
        full = (design(Y.ravel(), X.ravel()) @ coef).reshape(Y.shape)
    # gradient at the centre of the crop, and its error
    gy_row = np.array([0, 1, 0] + ([2 * yc, xc, 0] if model == "quadratic" else []))  # "local": centred
    gx_row = np.array([0, 0, 1] + ([0, yc, 2 * xc] if model == "quadratic" else []))
    info = {"cells": int(ok.sum()), "kept": int(keep.sum()), "model": model,
            "area_km": [round(area.ny * km_y, 1), round(area.nx * km_x, 1)],
            "rad_per_km_az_rg": [round(float(gy_row @ coef), 4), round(float(gx_row @ coef), 4)],
            "se_rad_per_km_az_rg": [round(float(np.sqrt(gy_row @ cov @ gy_row)), 4),
                                    round(float(np.sqrt(gx_row @ cov @ gx_row)), 4)],
            "noise_rad": round(float(1.4826 * np.median(np.abs(r - np.median(r)))), 2)}
    return full.astype(np.float32), info
