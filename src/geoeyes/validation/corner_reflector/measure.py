"""Measurements of a point target on S1 SLC chips: calibrated RCS, peak position and coherence.

RCS (integrated-energy method): beta0 = |DN|^2 / A^2 with A the beta-nought LUT value; the energy
of the impulse response main lobe (3 azimuth x 5 range pixels around the peak) minus the clutter
level (median beta0 of the chip outside the response cross) times the slant-plane pixel area.

Coherence: the two chips are aligned to the nearest pixel by amplitude cross-correlation, the
residual fringe of each block (flat earth, topography, orbit) is removed with the block's dominant
2-D fringe frequency, and coherence is the magnitude of the normalised complex correlation in a
3 x 5 (azimuth x range) window.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter

LOBE = (1, 2)          # half size of the 3 x 5 integration window (azimuth, range)
CROSS = (4, 10)        # half width of the impulse-response cross excluded from the clutter estimate


@dataclass
class RcsResult:
    rcs_dbsm: float
    scr_db: float
    clutter_dbsm: float          # clutter energy in a cell of the integration window size
    peak_line: float             # sub-pixel, full-raster coordinates
    peak_sample: float
    peak_beta0_db: float


def beta0(chip: np.ndarray, cal_a: float) -> np.ndarray:
    return (np.abs(chip) ** 2 / cal_a ** 2).astype(np.float64)


def measure_rcs(b0: np.ndarray, line0: int, sample0: int, pred_line: float, pred_sample: float,
                range_spacing: float, azimuth_spacing: float, search: tuple[int, int] = (2, 8)) -> RcsResult:
    """Peak search within +/-search (azimuth, range) pixels of the predicted position, then RCS."""
    pr, pc = int(round(pred_line - line0)), int(round(pred_sample - sample0))
    sa, sr = search
    r0, c0 = max(pr - sa, LOBE[0]), max(pc - sr, LOBE[1])
    r1, c1 = min(pr + sa + 1, b0.shape[0] - LOBE[0]), min(pc + sr + 1, b0.shape[1] - LOBE[1])
    win = b0[r0:r1, c0:c1]
    i, j = np.unravel_index(int(np.argmax(win)), win.shape)
    i, j = i + r0, j + c0
    mask = np.ones_like(b0, bool)
    mask[max(i - CROSS[0], 0):i + CROSS[0] + 1, :] = False
    mask[:, max(j - CROSS[1], 0):j + CROSS[1] + 1] = False
    clutter = float(np.median(b0[mask]))
    lobe = b0[i - LOBE[0]:i + LOBE[0] + 1, j - LOBE[1]:j + LOBE[1] + 1]
    area = range_spacing * azimuth_spacing
    energy = (lobe.sum() - lobe.size * clutter) * area
    clutter_cell = lobe.size * clutter * area
    return RcsResult(
        rcs_dbsm=float(10 * np.log10(energy)) if energy > 0 else float("nan"),
        scr_db=float(10 * np.log10(max(energy, 1e-12) / clutter_cell)),
        clutter_dbsm=float(10 * np.log10(clutter_cell)),
        peak_line=line0 + i + _parabola(b0[i - 1:i + 2, j]),
        peak_sample=sample0 + j + _parabola(b0[i, j - 1:j + 2]),
        peak_beta0_db=float(10 * np.log10(b0[i, j])),
    )


def _parabola(v: np.ndarray) -> float:
    if len(v) != 3:
        return 0.0
    den = v[0] - 2 * v[1] + v[2]
    return float(np.clip(0.5 * (v[0] - v[2]) / den, -0.5, 0.5)) if den != 0 else 0.0


# ── coherence ────────────────────────────────────────────────────────────────

def offset(master: np.ndarray, slave: np.ndarray, max_shift: int = 8) -> tuple[float, float]:
    """Sub-pixel (azimuth, range) offset of ``slave`` relative to ``master`` from the amplitude
    cross-correlation peak (parabola fit around the integer maximum). A feature at (y, x) in the
    master is at (y - dy, x - dx) in the slave."""
    a = np.abs(master) - np.abs(master).mean()
    b = np.abs(slave) - np.abs(slave).mean()
    xc = np.fft.fftshift(np.fft.ifft2(np.fft.fft2(a) * np.conj(np.fft.fft2(b))).real)
    cy, cx = np.array(xc.shape) // 2
    sub = xc[cy - max_shift:cy + max_shift + 1, cx - max_shift:cx + max_shift + 1]
    i, j = np.unravel_index(int(np.argmax(sub)), sub.shape)
    fi = _parabola(sub[i - 1:i + 2, j]) if 0 < i < sub.shape[0] - 1 else 0.0
    fj = _parabola(sub[i, j - 1:j + 2]) if 0 < j < sub.shape[1] - 1 else 0.0
    return float(i + fi - max_shift), float(j + fj - max_shift)


def deramp_azimuth(z: np.ndarray) -> np.ndarray:
    """Remove the TOPS azimuth Doppler ramp of a chip so it can be interpolated in azimuth.
    The local Doppler centroid of each line comes from the lag-1 azimuth correlation; a linear fit
    of it over the chip gives the quadratic phase that is removed."""
    c = np.sum(z[1:] * np.conj(z[:-1]), axis=1)
    f = np.unwrap(np.angle(c)) / (2 * np.pi)            # cycles per line, per line
    y = np.arange(len(f)) + 0.5
    w = np.abs(c)
    b, a = np.polyfit(y, f, 1, w=w / w.max())
    yy = np.arange(z.shape[0])
    phase = 2 * np.pi * (a * yy + 0.5 * b * yy ** 2)
    return z * np.exp(-1j * phase)[:, None]


def shift(z: np.ndarray, dy: float, dx: float) -> np.ndarray:
    """Fourier shift of a (base-band) complex chip by (dy, dx) pixels."""
    from scipy.ndimage import fourier_shift
    return np.fft.ifft2(fourier_shift(np.fft.fft2(z), (dy, dx)))


def coregister(master: np.ndarray, slave: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    """Deramp both chips in azimuth and resample the slave onto the master grid."""
    m, s = deramp_azimuth(master), deramp_azimuth(slave)
    dy, dx = offset(master, slave)
    return m, shift(s, dy, dx), (dy, dx)


def flatten(ifg: np.ndarray, pad: int = 4) -> np.ndarray:
    """Remove the dominant linear fringe of a block (2-D FFT peak)."""
    ny, nx = ifg.shape
    spec = np.abs(np.fft.fft2(ifg, s=(ny * pad, nx * pad)))
    ky, kx = np.unravel_index(int(np.argmax(spec)), spec.shape)
    fy, fx = ky / (ny * pad), kx / (nx * pad)
    yy, xx = np.mgrid[0:ny, 0:nx]
    return ifg * np.exp(-2j * np.pi * (fy * yy + fx * xx))


def coherence_map(m: np.ndarray, s: np.ndarray, window: tuple[int, int] = (3, 5),
                  block: tuple[int, int] = (32, 128)) -> np.ndarray:
    """Coherence of two aligned complex chips, fringes removed block by block."""
    ifg = (m * np.conj(s)).astype(np.complex128)
    flat = np.empty_like(ifg)
    by, bx = block
    for y in range(0, ifg.shape[0], by):
        for x in range(0, ifg.shape[1], bx):
            flat[y:y + by, x:x + bx] = flatten(ifg[y:y + by, x:x + bx])
    num = uniform_filter(flat.real, window) + 1j * uniform_filter(flat.imag, window)
    den = np.sqrt(uniform_filter(np.abs(m) ** 2, window) * uniform_filter(np.abs(s) ** 2, window))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, np.abs(num) / den, np.nan)


def point_coherence(m: np.ndarray, s: np.ndarray, at: tuple[int, int], window: tuple[int, int] = (3, 5),
                    block: tuple[int, int] = (32, 128)) -> float:
    """Coherence at one pixel, the fringe estimated in a block centred on it."""
    y, x = at
    by, bx = block
    y0, x0 = max(y - by // 2, 0), max(x - bx // 2, 0)
    mm, ss = m[y0:y0 + by, x0:x0 + bx], s[y0:y0 + by, x0:x0 + bx]
    c = coherence_map(mm, ss, window, block=mm.shape)
    return float(c[y - y0, x - x0])
