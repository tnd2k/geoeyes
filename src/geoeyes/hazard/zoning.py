"""Classes and the hazard matrix (docs/en/research/rainfall-insar-hazard.md §4.4–4.5).

Every cell gets an intensity class I (InSAR motion, raised by the rainfall scenario and by a significant
acceleration) and a secondary class S (subsidence: angular distortion reached over the horizon; landslide: the
susceptibility class of the user, else the slope class). The hazard level is ``matrix[I][S]``:
0 very low, 1 low, 2 moderate, 3 high, 4 very high; -1 = not assessed (too few points, insensitive geometry).
"""
from __future__ import annotations

import numpy as np

LEVELS = ("very low", "low", "moderate", "high", "very high")
MODES = ("subsidence", "landslide")

# rows: intensity class I0..I3, columns: secondary class S0..S3
DEFAULT_MATRIX = ((0, 0, 1, 1),
                  (1, 1, 2, 3),
                  (2, 2, 3, 4),
                  (3, 3, 4, 4))


def classify(x: np.ndarray, breaks) -> np.ndarray:
    """Class index of each value: 0 below ``breaks[0]``, ..., len(breaks) above the last; NaN -> -1."""
    x = np.asarray(x, np.float64)
    out = np.searchsorted(np.asarray(breaks, np.float64), x, side="right").astype(np.int8)
    out[~np.isfinite(x)] = -1
    return out


def intensity_class(rate: np.ndarray, stable: np.ndarray, breaks) -> np.ndarray:
    """I0 below the stability threshold of the cell (``stable``, mm/yr), then I1.. by ``breaks`` (mm/yr, two
    values: upper bounds of I1 and I2). ``rate`` is in the hazard direction (sinking / downslope > 0): motion the
    other way (uplift, apparent upslope motion) is I0 here and flagged by the caller."""
    r = np.asarray(rate, np.float64)
    i = 1 + classify(r, breaks)
    i[r < stable] = 0
    i[~np.isfinite(r)] = -1
    return i.astype(np.int8)


def angular_distortion(kx: np.ndarray, ky: np.ndarray, rate: np.ndarray, cell_m: float, horizon_yr: float,
                       ok: np.ndarray | None = None) -> np.ndarray:
    """Largest differential settlement over one cell spacing toward any of the 8 neighbours, accumulated over
    ``horizon_yr``: β = max |v_i − v_j| · T / L (dimensionless; v in mm/yr, L in m). NaN without a neighbour."""
    rate = np.asarray(rate, np.float64)
    ok = np.isfinite(rate) if ok is None else ok & np.isfinite(rate)
    index = {(int(a), int(b)): i for i, (a, b, good) in enumerate(zip(kx, ky, ok, strict=True)) if good}
    beta = np.full(len(rate), np.nan)
    steps = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    for (a, b), i in index.items():
        best = np.nan
        for dx, dy in steps:
            j = index.get((a + dx, b + dy))
            if j is None:
                continue
            g = abs(rate[i] - rate[j]) / (cell_m * np.hypot(dx, dy))        # mm/yr per m
            if not best >= g:                                                # NaN at first
                best = g
        beta[i] = best * horizon_yr / 1000.0
    return beta


def hazard_level(i: np.ndarray, s: np.ndarray, matrix=DEFAULT_MATRIX) -> np.ndarray:
    """``matrix[I][S]``; a missing secondary class counts as S0, a missing intensity gives -1."""
    m = np.asarray(matrix, np.int8)
    i = np.asarray(i, np.int8)
    s = np.where(np.asarray(s) < 0, 0, s).astype(np.int8)
    out = np.full(i.shape, -1, np.int8)
    good = i >= 0
    out[good] = m[np.clip(i[good], 0, 3), np.clip(s[good], 0, 3)]
    return out
