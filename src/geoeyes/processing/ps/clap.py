"""CLAP filter (Combined Low-pass and Adaptive Phase, Hooper 2004) on a (n_i, n_j, n_ifg) phase grid.

Overlapping n_win windows stepped by n_win/4, each zero-padded by n_pad, Goldstein-type adaptive gain
(|FFT| smoothed by a 7x7 Gaussian, median-normalised, (H^alpha - 1)·beta) plus a Butterworth low-pass,
recombined with a triangular taper. Windows without any non-zero cell are skipped (their output is 0).
"""
from __future__ import annotations

import numpy as np
import scipy.fft as sfft
from scipy.signal import fftconvolve, windows


def low_pass(n_win: int, grid_size: float, wavelength: float) -> np.ndarray:
    """(n_win, n_win) 5th-order Butterworth response (cut-off 1/wavelength), fft-shifted."""
    freq0 = 1 / wavelength
    step = 1 / grid_size / n_win
    half = (n_win - 1) / grid_size / n_win / 2
    freq = np.arange(-half, half + step, step)
    butter = 1 / (1 + (freq / freq0) ** (2 * 5))
    return sfft.fftshift(np.outer(butter, butter))


def _gain_power(h, alpha):
    a = np.asarray(alpha, dtype=np.float32)
    if a.size == 1:
        return np.maximum(h ** float(a.ravel()[0]) - 1.0, 0.0)
    return np.maximum(h ** a[:, None, None] - 1.0, 0.0)


def clap_filter(ph_grid: np.ndarray, alpha, beta: float, n_win: int, n_pad: int,
                low_pass_resp: np.ndarray | None = None, coh_grid: np.ndarray | None = None,
                coh_floor: float = 0.2) -> np.ndarray:
    """Filtered complex64 grid, same shape as ``ph_grid``; ``alpha`` scalar or per-interferogram. With
    ``coh_grid`` (same shape, NaN = no data) each window's gain is scaled by clip(median coherence / 0.5,
    coh_floor, 1), the median taken over the zero-padded window with no-data as 0 (legacy behaviour)."""
    n_win, n_pad = int(n_win), int(n_pad)
    n_i, n_j, n_ifg = ph_grid.shape
    n_ex = n_win + n_pad
    if low_pass_resp is None:
        low_pass_resp = np.zeros((n_ex, n_ex), np.float32)
    g7 = windows.gaussian(7, std=1.2).astype(np.float32)
    kernel = np.outer(g7, g7)
    kernel /= kernel.sum()
    n_inc = n_win // 4
    n_win_i = int(np.ceil(n_i / n_inc)) - 3
    n_win_j = int(np.ceil(n_j / n_inc)) - 3
    x = np.arange(0, n_win // 2)
    xx, yy = np.meshgrid(x, x)
    xx = xx + yy
    taper = (np.vstack([np.hstack([xx, np.fliplr(xx)]), np.flipud(np.hstack([xx, np.fliplr(xx)]))])
             + 1e-6).astype(np.float32)

    work = ph_grid.copy()
    work[np.isnan(work)] = 0
    ph_t = work.transpose(2, 0, 1).astype(np.complex64)
    out = np.zeros_like(ph_t)
    bit = np.zeros((n_ifg, n_ex, n_ex), np.complex64)
    coh_t = coh_bit = None
    if coh_grid is not None:
        coh_t = np.nan_to_num(np.asarray(coh_grid, np.float32), nan=0.0).transpose(2, 0, 1)
        coh_bit = np.zeros((n_ifg, n_ex, n_ex), np.float32)
    occ = np.any(np.isfinite(ph_grid) & (ph_grid != 0), axis=2)
    occ_int = np.zeros((n_i + 1, n_j + 1), np.int64)
    occ_int[1:, 1:] = np.cumsum(np.cumsum(occ.astype(np.int64), axis=0), axis=1)

    for ix1 in range(n_win_i):
        wf = taper
        i1, i2 = ix1 * n_inc, ix1 * n_inc + n_win
        if i2 > n_i:
            shift = i2 - n_i
            i1, i2 = n_i - n_win, n_i
            wf = np.vstack([np.zeros((shift, n_win), np.float32), taper[:n_win - shift, :]])
        for ix2 in range(n_win_j):
            j1, j2 = ix2 * n_inc, ix2 * n_inc + n_win
            j_shift = 0
            if j2 > n_j:
                j_shift = j2 - n_j
                j1, j2 = n_j - n_win, n_j
            if occ_int[i2, j2] - occ_int[i1, j2] - occ_int[i2, j1] + occ_int[i1, j1] == 0:
                continue
            wf2 = wf
            if j_shift:
                wf2 = np.hstack([np.zeros((n_win, j_shift), np.float32), wf[:, :n_win - j_shift]])
            bit[:] = 0
            bit[:, :n_win, :n_win] = ph_t[:, i1:i2, j1:j2]
            spec = sfft.fft2(bit, axes=(-2, -1), workers=-1)
            h = np.abs(spec).astype(np.float32)
            h = fftconvolve(sfft.fftshift(h, axes=(-2, -1)), kernel[None], mode="same", axes=(-2, -1))
            h = sfft.ifftshift(h.astype(np.float32), axes=(-2, -1))
            med = np.median(h.reshape(n_ifg, -1), axis=1)[:, None, None]
            h = np.where(med != 0, h / (med + 1e-10), h)
            gain = (_gain_power(h, alpha) * beta + low_pass_resp[None]).astype(np.complex64)
            if coh_bit is not None:
                coh_bit[:] = 0.0
                coh_bit[:, :n_win, :n_win] = coh_t[:, i1:i2, j1:j2]
                med = np.nan_to_num(np.nanmedian(coh_bit.astype(np.float64), axis=(-2, -1)), nan=0.0)
                gain = gain * np.clip(med / 0.5, float(coh_floor), 1.0).astype(np.float32)[:, None, None]
            filt = sfft.ifft2(spec * gain, axes=(-2, -1), workers=-1)
            out[:, i1:i2, j1:j2] += filt[:, :n_win, :n_win] * wf2[None]
    return out.transpose(1, 2, 0)


def clap_at_points(ph_grid: np.ndarray, cells: np.ndarray, n_win: int, alpha, beta: float,
                   low_pass_resp: np.ndarray, osf_r: int = 0, batch: int = 1024, legacy: bool = False) -> np.ndarray:
    """CLAP-filtered phase at each point's own cell (StaMPS ``ps_select`` re-smoothing): an n_win window
    from cell - n_win/2, kept inside the grid (``legacy``: only clipped at the top/left edge, zero-padded past
    the bottom/right edge), the point's own cell (±osf_r) zeroed so it does not filter itself. ``cells``
    (n, 2) 0-based grid (row, col). Returns (n, n_ifg) complex64; the result depends only on the cell, so
    each distinct cell is filtered once."""
    n_ifg = ph_grid.shape[2]
    if cells.shape[0] == 0:
        return np.zeros((0, n_ifg), np.complex64)
    cells, inv = np.unique(cells, axis=0, return_inverse=True)
    n = cells.shape[0]
    out = np.zeros((n, n_ifg), np.complex64)
    i0 = np.maximum(cells[:, 0] - n_win // 2, 0)
    j0 = np.maximum(cells[:, 1] - n_win // 2, 0)
    if not legacy:
        i0 = np.minimum(i0, max(ph_grid.shape[0] - n_win, 0))
        j0 = np.minimum(j0, max(ph_grid.shape[1] - n_win, 0))

    g7 = windows.gaussian(7, std=1.2)
    kernel = np.outer(g7, g7).astype(np.float32)              # MATLAB gausswin(7)*gausswin(7)', unnormalised
    kh = kernel.shape[0]
    n_full = n_win + kh - 1
    k_full = np.zeros((n_full, n_full), np.float32)
    k_full[:kh, :kh] = kernel
    k_rfft = sfft.rfft2(k_full, workers=-1)[None, None]
    lp = np.asarray(low_pass_resp, np.float32)[None, None]
    pad = np.pad(ph_grid, ((0, n_win), (0, n_win), (0, 0)), mode="constant")
    off = np.arange(n_win, dtype=np.int64)
    ifg = np.arange(n_ifg)

    for s in range(0, n, batch):
        e = min(s + batch, n)
        nb, rows = e - s, np.arange(e - s)
        ib, jb = i0[s:e].astype(np.int64), j0[s:e].astype(np.int64)
        win = np.nan_to_num(pad[ib[:, None, None] + off[None, :, None], jb[:, None, None] + off[None, None, :], :],
                            nan=0.0)
        bi = (cells[s:e, 0] - ib).clip(0, n_win - 1).astype(np.int32)
        bj = (cells[s:e, 1] - jb).clip(0, n_win - 1).astype(np.int32)
        for di in range(-osf_r, osf_r + 1):
            for dj in range(-osf_r, osf_r + 1):
                win[rows, np.clip(bi + di, 0, n_win - 1), np.clip(bj + dj, 0, n_win - 1), :] = 0
        win = np.ascontiguousarray(win.transpose(0, 3, 1, 2))
        spec = sfft.fft2(win.reshape(nb * n_ifg, n_win, n_win), workers=-1)
        h = np.abs(spec).reshape(nb, n_ifg, n_win, n_win).astype(np.float32)
        h_pad = np.zeros((nb, n_ifg, n_full, n_full), np.float32)
        h_pad[:, :, :n_win, :n_win] = np.fft.fftshift(h, axes=(-2, -1))
        h = sfft.irfft2(sfft.rfft2(h_pad, axes=(-2, -1), workers=-1) * k_rfft, s=(n_full, n_full), axes=(-2, -1),
                        workers=-1)
        c = kh // 2
        h = np.fft.ifftshift(h[:, :, c:c + n_win, c:c + n_win], axes=(-2, -1))
        np.maximum(h, 0.0, out=h)
        med = np.median(h.reshape(nb, n_ifg, -1), axis=-1, keepdims=True)[..., None]
        h = np.where(med != 0, h / (med + 1e-10), h)
        gain = (np.maximum(h**alpha - 1, 0.0) * beta + lp).astype(np.complex64)
        filt = sfft.ifft2(spec.reshape(nb, n_ifg, n_win, n_win) * gain, axes=(-2, -1), workers=-1)
        out[s:e] = filt[rows[:, None], ifg[None, :], bi[:, None], bj[:, None]].astype(np.complex64)
    return out[inv.reshape(-1)]
