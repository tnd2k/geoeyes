"""Phase closure of unwrapped triplets (S3): for every triplet (i, j, k) of the network with pairs (i, j), (j, k) and
(i, k), the closure φᵢⱼ + φⱼₖ − φᵢₖ of the unwrapped phases is a multiple of 2π where one of the three was unwrapped
wrongly (wrapped closure, the non-zero residual of multilooking, is far below π). Pairs that close badly on many
pixels are dropped before the inversion; per pixel, the count of bad triplets flags local errors.
"""
from __future__ import annotations

import numpy as np


def triplets(pairs: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """Index triplets (a, b, c) into ``pairs`` with pairs[a] = (i, j), pairs[b] = (j, k), pairs[c] = (i, k)."""
    idx = {p: n for n, p in enumerate(pairs)}
    out = []
    for (i, j), a in idx.items():
        for (j2, k), b in idx.items():
            if j2 == j and (i, k) in idx:
                out.append((a, b, idx[(i, k)]))
    return out


def closure(phase: np.ndarray, trips: list[tuple[int, int, int]]) -> np.ndarray:
    """Closure (triplets, pixels) of the unwrapped ``phase`` (pairs, pixels)."""
    if not trips:
        return np.empty((0, phase.shape[1]))
    t = np.asarray(trips)
    return phase[t[:, 0]] + phase[t[:, 1]] - phase[t[:, 2]]


def mask_bad_cells(phase: np.ndarray, pairs: list[tuple[int, int]], threshold: float = np.pi,
                   max_bad: float = 0.5) -> tuple[np.ndarray, int]:
    """``phase`` with NaN where a pair, at a pixel, is in more than ``max_bad`` of its triplets with a bad closure
    there (a local unwrapping error: the pair stays elsewhere). Returns the masked copy and the number of values
    removed."""
    trips = triplets(pairs)
    out = phase.copy()
    if not trips:
        return out, 0
    c = closure(phase, trips)
    with np.errstate(invalid="ignore"):
        bad = np.abs(c) > threshold
    m = len(pairs)
    nbad = np.zeros((m, phase.shape[1]), np.int16)
    ntot = np.zeros((m, phase.shape[1]), np.int16)
    ok = np.isfinite(c)
    for (a, b, cc), br, okr in zip(trips, bad, ok, strict=True):
        for p in (a, b, cc):
            nbad[p] += br
            ntot[p] += okr
    with np.errstate(invalid="ignore", divide="ignore"):
        drop = (ntot > 0) & (nbad / np.maximum(ntot, 1) > max_bad)
    out[drop] = np.nan
    return out, int(drop.sum())


def _shares(bad: np.ndarray, trips, m: int, alive: np.ndarray) -> np.ndarray:
    """Per pair: mean over its live triplets of the share of pixels whose closure is bad."""
    share, seen = np.zeros(m), np.zeros(m)
    for (a, b, c), row in zip(trips, bad, strict=True):
        if alive[a] and alive[b] and alive[c]:
            f = float(row.mean()) if row.size else 0.0
            for p in (a, b, c):
                share[p] += f
                seen[p] += 1
    return np.divide(share, seen, out=np.zeros(m), where=seen > 0)


def bad_pairs(phase: np.ndarray, pairs: list[tuple[int, int]], max_share: float = 0.05,
              threshold: float = np.pi) -> tuple[list[int], dict]:
    """Pairs with unwrapping errors, removed one at a time: the pair whose triplets have the highest share of
    pixels with |closure| > ``threshold`` goes, if that share exceeds ``max_share``; the shares are recomputed
    without it. A wrong pair spoils every triplet it is in; a good pair only those it shares with a wrong one, so
    the worst pair is the wrong one."""
    trips = triplets(pairs)
    c = closure(phase, trips)
    with np.errstate(invalid="ignore"):
        bad = np.abs(c) > threshold                    # triplets × pixels (NaN closure: not bad)
    m = len(pairs)
    alive = np.ones(m, bool)
    drop: list[int] = []
    first = _shares(bad, trips, m, alive)
    while True:
        share = _shares(bad, trips, m, alive)
        worst = int(np.argmax(share)) if m else 0
        if not m or share[worst] <= max_share:
            break
        drop.append(worst)
        alive[worst] = False
    live = [r for (a, b, cc), r in zip(trips, bad, strict=True) if alive[a] and alive[b] and alive[cc]]
    per_pixel = np.sum(live, axis=0) if live else np.zeros(phase.shape[1], int)
    return sorted(drop), {"triplets": len(trips), "share_bad": np.round(first, 4).tolist(), "per_pixel_bad": per_pixel}
