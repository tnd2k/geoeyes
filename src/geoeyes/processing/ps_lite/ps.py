# Ported from modules/ps_stack/ps.py (algorithm unchanged; ADR-020).
"""PS candidate selection and extraction of their wrapped phase, in one pass over the stack.

The stack is read once, in blocks of lines. For each block and pixel:
  * D_A = std / mean of the calibrated amplitudes of every epoch (temporal intensity stability);
  * spectral diversity SD = mean over epochs of |I_lo - I_hi| / (I_lo + I_hi), with I_lo / I_hi the
    intensities of the lower / upper half of the occupied range spectrum: a point scatterer looks the
    same in both sub-bands (SD -> 0), distributed scatterers (speckle) give SD ~ 0.5;
candidates pass both thresholds and a mean-amplitude floor (water / shadow), are thinned to the best
one per ``cell`` (lowest D_A), and their phase arg(E_ref E_k*) minus the reference phase (flat earth +
topography) is kept for every interferogram.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft

from geoeyes.processing.ps_lite.inputs import Epoch, Ifg, MasterGeometry


@dataclass
class PSSet:
    line: np.ndarray             # (n,) int32 master line
    sample: np.ndarray           # (n,) int32 master sample
    da: np.ndarray               # (n,) float32
    sd: np.ndarray               # (n,) float32 spectral diversity (NaN if not computed)
    amp: np.ndarray              # (n,) float32 mean calibrated amplitude
    phase: np.ndarray            # (n, n_ifg) float32 wrapped phase after reference removal, rad
    calib: np.ndarray            # (n_epoch,) amplitude calibration factors
    amp_floor: float
    band: float                  # occupied range band, fraction of the sampling rate
    n_da: int                    # pixels passing D_A (and amplitude floor)
    n_candidates: int            # pixels passing every criterion, before thinning

    def __len__(self):
        return self.line.size


def calibration_factors(epochs: list[Epoch], window: tuple, every: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Mean amplitude of each epoch over every ``every``-th line and column with data, and the
    calibrated mean-amplitude sample used to set the amplitude floor."""
    l0, l1, s0, s1 = window
    rows = np.arange(l0, l1, every)
    amps = np.stack([np.hypot(np.asarray(e.i[rows, s0:s1:every], np.float32),
                              np.asarray(e.q[rows, s0:s1:every], np.float32)) for e in epochs])
    valid = np.all(amps > 0, axis=0)
    f = np.array([a[valid].mean() for a in amps])
    return f, (amps / f[:, None, None]).mean(axis=0)[valid]


def occupied_band(e: Epoch, window: tuple, lines: int = 256, level: float = 0.1) -> float:
    """Occupied two-sided range bandwidth as a fraction of the sampling rate (power > level * max)."""
    l0, l1, s0, s1 = window
    c = (l0 + l1) // 2
    z = e.read(max(c - lines // 2, l0), min(c + lines // 2, l1), s0, s1)
    P = np.mean(np.abs(sfft.fft(z, axis=1, workers=-1)) ** 2, axis=0)
    f = np.abs(sfft.fftfreq(z.shape[1]))
    return float(2 * f[level * P.max() < P].max())


def _subband_masks(n: int, band: float):
    f = sfft.fftfreq(n)
    half = band / 2
    return (f < 0) & (f >= -half), (f > 0) & (f <= half)


def select_and_extract(epochs: list[Epoch], ifgs: list[Ifg], geo: MasterGeometry, window: tuple, sign: float,
                       da_max: float = 0.4, sd_max: float | None = None, cell: tuple = (4, 6),
                       amp_floor_pct: float = 10.0, block_lines: int = 256, compute_sd: bool = True,
                       progress=None) -> PSSet:
    l0, l1, s0, s1 = window
    ca, cr = cell
    f, amp_sample = calibration_factors(epochs, window)
    floor = float(np.percentile(amp_sample, amp_floor_pct)) if amp_floor_pct > 0 else 0.0
    band = occupied_band(epochs[0], window)
    lo_m, hi_m = _subband_masks(s1 - s0, band)
    ref_ip = [geo.interpolator(g.ref_phase) for g in ifgs]
    step = max(ca, (block_lines // ca) * ca)
    out = {k: [] for k in ("line", "sample", "da", "sd", "amp", "phase")}
    n_da = n_cand = 0
    nb = (l1 - l0 + step - 1) // step
    ne = len(epochs)
    for ib, b0 in enumerate(range(l0, l1, step)):
        b1 = min(b0 + step, l1)
        E = [e.read(b0, b1, s0, s1) for e in epochs]
        s1_ = np.zeros(E[0].shape, np.float64)
        s2_ = np.zeros(E[0].shape, np.float64)
        allv = np.ones(E[0].shape, bool)
        for k, z in enumerate(E):
            a = np.abs(z) / f[k]
            s1_ += a
            s2_ += a * a
            allv &= a > 0
        mean = s1_ / ne
        std = np.sqrt(np.maximum(s2_ / ne - mean ** 2, 0.0))
        da = np.where(allv & (mean > 0), std / np.maximum(mean, 1e-30), np.inf)
        cand = (da <= da_max) & (mean >= floor)
        n_da += int(cand.sum())
        sd = np.full(E[0].shape, np.nan, np.float32)
        if (compute_sd or sd_max is not None) and cand.any():
            acc = np.zeros(E[0].shape, np.float64)
            for z in E:
                Z = sfft.fft(z, axis=1, workers=-1)
                il = np.abs(sfft.ifft(Z * lo_m, axis=1, workers=-1)) ** 2
                ih = np.abs(sfft.ifft(Z * hi_m, axis=1, workers=-1)) ** 2
                acc += np.abs(il - ih) / np.maximum(il + ih, 1e-30)
            sd = (acc / ne).astype(np.float32)
            if sd_max is not None:
                cand &= sd <= sd_max
        r, c = np.nonzero(cand)
        n_cand += r.size
        if r.size:
            cid = (r // ca) * ((s1 - s0) // cr + 1) + c // cr
            order = np.lexsort((da[r, c], cid))
            first = np.r_[True, cid[order][1:] != cid[order][:-1]]
            keep = order[first]
            r, c = r[keep], c[keep]
            pts = np.stack([(r + b0).astype(np.float64), (c + s0).astype(np.float64)], axis=-1)
            ph = np.empty((r.size, len(ifgs)), np.float32)
            for j, g in enumerate(ifgs):
                ifg = E[g.ref][r, c] * np.conj(E[g.sec][r, c])
                ph[:, j] = np.angle(ifg * np.exp(-1j * sign * ref_ip[j](pts)))
            out["line"].append((r + b0).astype(np.int32))
            out["sample"].append((c + s0).astype(np.int32))
            out["da"].append(da[r, c].astype(np.float32))
            out["sd"].append(sd[r, c])
            out["amp"].append(mean[r, c].astype(np.float32))
            out["phase"].append(ph)
        if progress:
            progress((ib + 1) / nb)
    cat = {k: (np.concatenate(v) if v else (np.zeros((0, len(ifgs))) if k == "phase" else np.zeros(0)))
           for k, v in out.items()}
    return PSSet(cat["line"].astype(np.int32), cat["sample"].astype(np.int32), cat["da"].astype(np.float32),
                 cat["sd"].astype(np.float32), cat["amp"].astype(np.float32), cat["phase"].astype(np.float32),
                 f, floor, band, n_da, n_cand)
