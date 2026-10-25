"""Goldstein adaptive phase filter on a complex grid (StaMPS ``wrap_filt``; port of the CPU path of
``modules/unwrap/unwrap_2d_goldstein.py``).

Overlapping n_win windows (step n_win/2, zero-padded by n_win/4): spectrum |FFT| smoothed by a 7×7 Gaussian,
normalised by its median, raised to ``alpha`` and applied; windows are blended with a triangular weight and
normalised by the accumulated weight. The output keeps the input magnitude.
"""
from __future__ import annotations

import numpy as np
from numpy.fft import fft2, fftshift, ifft2, ifftshift
from scipy.signal import convolve2d, windows


def _wrap_filt(ph: np.ndarray, n_win: int, alpha: float, n_pad: int | None = None) -> np.ndarray:
    n_pad = round(n_win * 0.25) if n_pad is None else n_pad
    n_i, n_j = ph.shape
    n_inc = n_win // 2
    n_win_i = int(np.ceil(n_i / n_inc)) - 1
    n_win_j = int(np.ceil(n_j / n_inc)) - 1
    out = np.zeros(ph.shape, complex)
    w_acc = np.zeros(ph.shape, np.float64)
    x = np.arange(0, n_win // 2)
    X, Y = np.meshgrid(x, x)
    X = X + Y
    wind = np.block([[X, np.fliplr(X)], [np.flipud(X), np.flipud(np.fliplr(X))]])
    work = np.nan_to_num(ph, nan=0)
    B = np.outer(windows.gaussian(7, std=1.2), windows.gaussian(7, std=1.2))
    bit = np.zeros((n_win + n_pad, n_win + n_pad), complex)
    for a in range(n_win_i):
        wf = wind.copy()
        i1, i2 = a * n_inc, a * n_inc + n_win
        if i2 > n_i:
            sh = i2 - n_i
            i1, i2 = n_i - n_win, n_i
            wf = np.vstack((np.zeros((sh, n_win)), wf[:n_win - sh, :]))
        for b in range(n_win_j):
            wf2 = wf.copy()
            j1, j2 = b * n_inc, b * n_inc + n_win
            if j2 > n_j:
                sh = j2 - n_j
                j1, j2 = n_j - n_win, n_j
                wf2 = np.hstack((np.zeros((n_win, sh)), wf2[:, :n_win - sh]))
            bit[:n_win, :n_win] = work[i1:i2, j1:j2]
            spec = fft2(bit)
            H = ifftshift(convolve2d(fftshift(np.abs(spec)), B, mode="same"))
            med = np.median(H)
            if med != 0:
                H = H / med
            filt = ifft2(spec * H**alpha)[:n_win, :n_win] * wf2
            if np.isnan(filt[0, 0]):
                raise ValueError("Goldstein filter produced NaN")
            out[i1:i2, j1:j2] += filt
            w_acc[i1:i2, j1:j2] += wf2
    out = out / (w_acc + 1e-10)
    return np.abs(work) * np.exp(1j * np.angle(out))


def goldstein(ph: np.ndarray, n_win: int, alpha: float, n_passes: int = 1) -> np.ndarray:
    """``n_passes`` Goldstein passes over the complex grid ``ph`` (NaN = 0)."""
    out = np.asarray(ph, np.complex128)
    if n_passes <= 0:
        return out.copy()
    for _ in range(int(n_passes)):
        out = _wrap_filt(out, int(n_win), float(alpha))
    return out
