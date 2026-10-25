"""Statistically homogeneous pixels (SHP): two-sample test on the amplitude time series of each pixel against
every neighbour in its window — Anderson-Darling (``ad``, Scholz & Stephens 1987; more sensitive to the tails)
or Kolmogorov-Smirnov (``ks``).

The tests are symmetric, so one offset of each ``(o, -o)`` pair is computed and written to both pixels. Both
samples have ``n`` values; both statistics only need, along the merged sorted samples, how many of the first j
values come from the centre pixel: the amplitudes are packed with a source bit (float32 bits are monotonic for
non-negative values) and sorted once per offset.
"""
from __future__ import annotations

import functools

import numpy as np


def ks_critical(alpha: float, n: int) -> float:
    """Asymptotic two-sample critical value for equal sizes: c(α)·sqrt(2/n), c(α) = sqrt(-ln(α/2)/2)."""
    return float(np.sqrt(-0.5 * np.log(alpha / 2.0)) * np.sqrt(2.0 / n))


# Scholz & Stephens (1987) critical values of the standardized k-sample statistic: b0 + b1/sqrt(m) + b2/m
_AD_ALPHA = np.array([0.25, 0.1, 0.05, 0.025, 0.01, 0.005, 0.001])
_AD_B = np.array([[0.675, 1.281, 1.645, 1.96, 2.326, 2.573, 3.085],
                  [-0.245, 0.25, 0.678, 1.149, 1.822, 2.364, 3.615],
                  [-0.105, -0.305, -0.362, -0.391, -0.396, -0.345, -0.154]])


def ad_critical(alpha: float, k: int = 2) -> float:
    """Critical value of the standardized Anderson-Darling k-sample statistic (log-interpolated in alpha)."""
    m = k - 1
    crit = _AD_B[0] + _AD_B[1] / np.sqrt(m) + _AD_B[2] / m
    return float(np.interp(np.log(alpha), np.log(_AD_ALPHA[::-1]), crit[::-1]))


@functools.lru_cache(maxsize=64)
def ad_sigma(n: int) -> float:
    """Standard deviation of the Anderson-Darling 2-sample statistic A² for two samples of size n."""
    k, N = 2, 2 * n
    H = 2.0 / n
    h = np.sum(1.0 / np.arange(1, N))
    g = sum(np.sum(1.0 / ((N - i) * np.arange(i + 1, N))) for i in range(1, N - 1))
    a = (4 * g - 6) * (k - 1) + (10 - 6 * g) * H
    b = (2 * g - 4) * k**2 + 8 * h * k + (2 * g - 14 * h - 4) * H - 8 * h + 4 * g - 6
    c = (6 * h + 2 * g - 2) * k**2 + (4 * h - 4 * g + 6) * k + (2 * h - 6) * H + 4 * h
    d = (2 * h + 6) * k**2 - 4 * h * k
    return float(np.sqrt((a * N**3 + b * N**2 + c * N + d) / ((N - 1.0) * (N - 2.0) * (N - 3.0))))


def ad_standardized(from_centre: np.ndarray, n: int) -> np.ndarray:
    """Standardized 2-sample A² from ``from_centre`` (..., 2n) bool: merged sorted values from the centre."""
    N = 2 * n
    j = np.arange(1, N, dtype=np.float32)
    m1 = np.cumsum(from_centre, axis=-1, dtype=np.int16)[..., :-1].astype(np.float32)
    m2 = j - m1
    w = 1.0 / (j * (N - j))
    a2 = (((N * m1 - j * n) ** 2 + (N * m2 - j * n) ** 2) * w).sum(axis=-1) / (N * n)
    return (a2 - 1.0) / ad_sigma(n)


def window_offsets(half_window: tuple[int, int]) -> np.ndarray:
    """(win, 2) (dy, dx) of the window pixels, azimuth-major; the centre is at index ``win // 2``."""
    hy, hx = half_window
    dy, dx = np.meshgrid(np.arange(-hy, hy + 1), np.arange(-hx, hx + 1), indexing="ij")
    return np.column_stack([dy.ravel(), dx.ravel()])


def shp_mask(amp: np.ndarray, half_window: tuple[int, int], alpha: float, test: str = "ad") -> np.ndarray:
    """(H, W, win) bool: window pixel homogeneous with the centre (the centre itself always True).

    ``amp`` (n, H, W); pixels with an all-zero time series (no data) are never homogeneous, nor are window
    positions outside the array. ``test``: ``ad`` (Anderson-Darling) or ``ks`` (Kolmogorov-Smirnov).
    """
    if test not in ("ad", "ks"):
        raise ValueError(f"SHP test {test!r} not implemented (ad, ks)")
    n, H, W = amp.shape
    off = window_offsets(half_window)
    win = len(off)
    mid = win // 2
    a = np.nan_to_num(amp.astype(np.float32), nan=0.0)
    valid = np.any(a > 0, axis=0)
    keys = np.ascontiguousarray(np.moveaxis(a, 0, -1)).view(np.uint32).astype(np.uint64) << np.uint64(1)
    d_max = int(np.floor(ks_critical(alpha, n) * n + 1e-9))
    t_max = ad_critical(alpha)
    mask = np.zeros((H, W, win), bool)
    mask[..., mid] = valid
    for i in range(mid + 1, win):                  # offsets after the centre; i <-> win-1-i is the opposite one
        dy, dx = off[i]
        p = (slice(max(0, -dy), H - max(0, dy)), slice(max(0, -dx), W - max(0, dx)))
        q = (slice(max(0, dy), H - max(0, -dy)), slice(max(0, dx), W - max(0, -dx)))
        merged = np.concatenate([keys[p], keys[q] | np.uint64(1)], axis=-1)
        merged.sort(axis=-1)
        centre = (merged & np.uint64(1)) == 0
        if test == "ks":
            step = 2 * centre.astype(np.int16) - 1
            ok = np.abs(np.cumsum(step, axis=-1, dtype=np.int16)).max(axis=-1) <= d_max
        else:
            ok = ad_standardized(centre, n) <= t_max
        ok = ok & valid[p] & valid[q]
        mask[(*p, i)] = ok
        mask[(*q, win - 1 - i)] = ok
    return mask
