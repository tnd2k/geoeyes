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


class SparseGrid:
    """An (n_i, n_j, n_ifg) grid that holds only its occupied cells: ``idx`` sorted flat cell indices (row-major),
    ``vals`` (len(idx), n_ifg). A 10 m grid of a city is mostly empty and several GB dense; the filters read it a
    band of rows at a time (``rows``)."""

    def __init__(self, shape, idx: np.ndarray, vals: np.ndarray):
        self.shape = tuple(int(s) for s in shape)
        self.idx = np.asarray(idx, np.int64)
        self.vals = vals
        self.dtype = vals.dtype

    @classmethod
    def accumulate(cls, shape, flat: np.ndarray, values: np.ndarray, cells=None) -> SparseGrid:
        """Sum of ``values`` (n, n_ifg) per flat cell (same order of summation as ``np.add.at`` on a dense grid);
        ``cells``: ``np.unique(flat, return_inverse=True)`` when already known (reused across iterations)."""
        idx, inv = cells if cells is not None else np.unique(flat, return_inverse=True)
        vals = np.zeros((idx.size, values.shape[1]), values.dtype)
        np.add.at(vals, np.asarray(inv).reshape(-1), values)
        return cls(shape, idx, vals)

    def rows(self, r0: int, r1: int) -> np.ndarray:
        """Dense rows [r0, r1), zero outside the grid."""
        n_i, n_j, k = self.shape
        out = np.zeros((r1 - r0, n_j, k), self.dtype)
        a, b = max(r0, 0), min(r1, n_i)
        if b > a:
            s, e = np.searchsorted(self.idx, [a * n_j, b * n_j])
            out.reshape(-1, k)[self.idx[s:e] - r0 * n_j] = self.vals[s:e]
        return out

    def dense(self) -> np.ndarray:
        return self.rows(0, self.shape[0])

    def occupied(self) -> np.ndarray:
        """(n_i, n_j) cells with a non-zero value."""
        occ = np.zeros(self.shape[0] * self.shape[1], bool)
        occ[self.idx[np.any(self.vals != 0, axis=1)]] = True
        return occ.reshape(self.shape[:2])


def _rows(grid, r0: int, r1: int) -> np.ndarray:
    """Dense rows [r0, r1) of a dense or sparse grid, zero outside it (NaN kept)."""
    if isinstance(grid, SparseGrid):
        return grid.rows(r0, r1)
    a, b = max(r0, 0), min(r1, grid.shape[0])
    if a == r0 and b == r1:
        return grid[r0:r1]
    out = np.zeros((r1 - r0, *grid.shape[1:]), grid.dtype)
    if b > a:
        out[a - r0:b - r0] = grid[a:b]
    return out


def gaussian_at(grid: SparseGrid, sigma: float, at: np.ndarray, rows: int = 64) -> np.ndarray:
    """``scipy.ndimage.gaussian_filter`` of the real and imaginary parts of each interferogram of ``grid``, at the
    flat cells ``at`` only: (len(at), n_ifg) complex64, a band of rows at a time with the kernel radius as margin
    (the same values as on the dense grid)."""
    from scipy.ndimage import gaussian_filter
    n_i, n_j, k = grid.shape
    m = int(4.0 * float(sigma) + 0.5)                # gaussian_filter radius (truncate 4)
    at = np.asarray(at, np.int64).reshape(-1)
    order = np.argsort(at, kind="stable")
    at_i, at_j = np.divmod(at[order], n_j)
    out = np.zeros((at.size, k), np.complex64)
    for r0 in range(0, n_i, rows):
        r1 = min(r0 + rows, n_i)
        s, e = np.searchsorted(at_i, [r0, r1])
        if s == e:
            continue
        a, b = max(r0 - m, 0), min(r1 + m, n_i)
        band = grid.rows(a, b)
        ii, jj = at_i[s:e] - a, at_j[s:e]
        for q in range(k):
            f = (gaussian_filter(band[:, :, q].real, sigma=sigma)
                 + 1j * gaussian_filter(band[:, :, q].imag, sigma=sigma)).astype(np.complex64)
            out[order[s:e], q] = f[ii, jj]
    return out


def _occupied(ph_grid, rows: int = 256) -> np.ndarray:
    """(n_i, n_j) cells with any finite non-zero value, a band of rows at a time (no full-size temporaries)."""
    if isinstance(ph_grid, SparseGrid):
        return ph_grid.occupied()
    occ = np.zeros(ph_grid.shape[:2], bool)
    for r in range(0, ph_grid.shape[0], rows):
        b = ph_grid[r:r + rows]
        occ[r:r + rows] = np.any(np.isfinite(b) & (b != 0), axis=2)
    return occ


def clap_filter(ph_grid: np.ndarray | SparseGrid, alpha, beta: float, n_win: int, n_pad: int,
                low_pass_resp: np.ndarray | None = None, coh_grid: np.ndarray | SparseGrid | None = None,
                coh_floor: float = 0.2, at: np.ndarray | None = None) -> np.ndarray:
    """Filtered complex64 grid, same shape as ``ph_grid``; ``alpha`` scalar or per-interferogram. With
    ``coh_grid`` (same shape, NaN = no data) each window's gain is scaled by clip(median coherence / 0.5,
    coh_floor, 1), the median taken over the zero-padded window with no-data as 0 (legacy behaviour).
    With ``at`` (flat cell indices) only those cells are returned, (len(at), n_ifg), and no full-size
    output is held: the windows read the input in place and the overlap-add keeps a band of n_win rows,
    so a large grid needs little memory beyond the input itself."""
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

    bit = np.zeros((n_ifg, n_ex, n_ex), np.complex64)
    coh_bit = None
    if coh_grid is not None:
        coh_bit = np.zeros((n_ifg, n_ex, n_ex), np.float32)
    occ_int = np.zeros((n_i + 1, n_j + 1), np.int64)
    occ_int[1:, 1:] = np.cumsum(np.cumsum(_occupied(ph_grid).astype(np.int64), axis=0), axis=1)

    # the output: full, or only the cells of ``at`` (ordered by row so that a band of rows is a slice)
    if at is None:
        out = np.zeros((n_i, n_j, n_ifg), np.complex64)
    else:
        at = np.asarray(at, np.int64).reshape(-1)
        order = np.argsort(at, kind="stable")
        at_i, at_j = np.divmod(at[order], n_j)
        res = np.zeros((at.size, n_ifg), np.complex64)
    band = np.zeros((n_ifg, n_win, n_j), np.complex64)      # output rows [base, base + n_win)
    base = 0

    def flush(r1: int) -> None:
        """Rows [base, r1) are final: write them out."""
        r0, r1 = base, min(r1, n_i)
        if r1 <= r0:
            return
        if at is None:
            out[r0:r1] = band[:, :r1 - r0].transpose(1, 2, 0)
        else:
            s, e = np.searchsorted(at_i, [r0, r1])
            res[order[s:e]] = band[:, at_i[s:e] - r0, at_j[s:e]].T

    for ix1 in range(n_win_i):
        wf = taper
        i1, i2 = ix1 * n_inc, ix1 * n_inc + n_win
        if i2 > n_i:
            shift = i2 - n_i
            i1, i2 = n_i - n_win, n_i
            wf = np.vstack([np.zeros((shift, n_win), np.float32), taper[:n_win - shift, :]])
        # the window rows only move down (the last, shifted window too): rows above i1 are final
        if i1 > base:
            d = i1 - base
            flush(i1)
            band[:, :n_win - d] = band[:, d:]
            band[:, n_win - d:] = 0
            base = i1
        ph_rows = _rows(ph_grid, i1, i2)                 # the window rows of the input (dense or sparse grid)
        coh_rows = _rows(coh_grid, i1, i2) if coh_bit is not None else None
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
            bit[:, :n_win, :n_win] = np.nan_to_num(ph_rows[:, j1:j2, :], nan=0.0).transpose(2, 0, 1)
            spec = sfft.fft2(bit, axes=(-2, -1), workers=-1)
            h = np.abs(spec).astype(np.float32)
            h = fftconvolve(sfft.fftshift(h, axes=(-2, -1)), kernel[None], mode="same", axes=(-2, -1))
            h = sfft.ifftshift(h.astype(np.float32), axes=(-2, -1))
            med = np.median(h.reshape(n_ifg, -1), axis=1)[:, None, None]
            h = np.where(med != 0, h / (med + 1e-10), h)
            gain = (_gain_power(h, alpha) * beta + low_pass_resp[None]).astype(np.complex64)
            if coh_bit is not None:
                coh_bit[:] = 0.0
                coh_bit[:, :n_win, :n_win] = np.nan_to_num(
                    np.asarray(coh_rows[:, j1:j2, :], np.float32), nan=0.0).transpose(2, 0, 1)
                med = np.nan_to_num(np.nanmedian(coh_bit.astype(np.float64), axis=(-2, -1)), nan=0.0)
                gain = gain * np.clip(med / 0.5, float(coh_floor), 1.0).astype(np.float32)[:, None, None]
            filt = sfft.ifft2(spec * gain, axes=(-2, -1), workers=-1)
            band[:, :, j1:j2] += filt[:, :n_win, :n_win] * wf2[None]
    flush(base + n_win)
    return out if at is None else res


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
    off = np.arange(n_win, dtype=np.int64)
    ifg = np.arange(n_ifg)
    max_rows = 256                                   # rows of the grid read at once (the cells are sorted by row)

    s = 0
    while s < n:
        e = min(s + batch, n, int(np.searchsorted(i0, i0[s] + max_rows - n_win, side="right")))
        e = max(e, s + 1)
        nb, rows = e - s, np.arange(e - s)
        ib, jb = i0[s:e].astype(np.int64), j0[s:e].astype(np.int64)
        r0 = int(ib.min())
        band = _rows(ph_grid, r0, int(ib.max()) + n_win)
        band = np.pad(band, ((0, 0), (0, n_win), (0, 0)), mode="constant")    # zero past the right edge
        win = np.nan_to_num(band[(ib - r0)[:, None, None] + off[None, :, None],
                                 jb[:, None, None] + off[None, None, :], :], nan=0.0)
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
        s = e
    return out[inv.reshape(-1)]
