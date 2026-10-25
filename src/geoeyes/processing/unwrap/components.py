"""Tie disconnected islands of a 2-D unwrapped grid together with integer 2π offsets (port of
``modules/utils/unwrap_grid.link_unwrapped_components_2d``).

Islands (4-connected, at least ``min_size`` cells) are linked to their best-scoring neighbours (size over
distance, plus the 5 largest); each link proposes the offset between the median phases of both islands
around their closest cells, with a confidence from how close it is to a whole number of cycles. The offsets
minimise Σ weight·|k_i - k_j - k_ij| (integer program, the largest island fixed at 0), solved with SciPy's
MILP (the legacy code used OR-Tools CP-SAT; greedy breadth-first linking when no solution is found).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.spatial.distance import cdist

FOUR = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)


def _min_size(n_valid: int, min_size: int | None) -> int:
    if min_size is not None and min_size > 0:
        return max(4, int(min_size))
    return max(4, min(100, int(0.005 * n_valid)))


def _offset(phase, labeled, li, lj, p_i, p_j, half):
    h, w = phase.shape

    def vals(r, c, lab):
        sl = (slice(max(0, r - half), min(h, r + half + 1)), slice(max(0, c - half), min(w, c + half + 1)))
        p = phase[sl]
        return p[(labeled[sl] == lab) & np.isfinite(p)]

    vi, vj = vals(*p_i, li), vals(*p_j, lj)
    if vi.size < 3 or vj.size < 3:
        return 0, 0.0
    d = float(np.median(vi) - np.median(vj)) / (2 * np.pi)
    k = int(np.round(d))
    return k, max(0.0, 1.0 - 2.0 * abs(d - k))


def _connections(phase, labeled, comps, gap, link_count, link_size):
    coords, cent, sizes = [], [], []
    for c in comps:
        r, cc = np.where(labeled[c["slices"]] == c["label"])
        r, cc = r + c["slices"][0].start, cc + c["slices"][1].start
        coords.append(np.column_stack([r, cc]))
        cent.append((r.mean(), cc.mean()))
        sizes.append(r.size)
    cent, sizes = np.array(cent, float), np.array(sizes, float)
    n = len(comps)
    largest = set(np.argsort(sizes)[::-1][:min(5, n)].tolist())
    links = []
    for i in range(n):
        dist = np.sqrt(((cent - cent[i]) ** 2).sum(axis=1))
        dist[i] = np.inf
        score = np.log1p(sizes) / (dist + 1.0)
        score[i] = -np.inf
        m = min(link_count, n - 1)
        cand = set(np.argpartition(score, -m)[-m:].tolist()) | (largest - {i})
        for j in sorted(cand):
            if j <= i or not np.isfinite(dist[j]):
                continue
            d = cdist(coords[i], coords[j])
            a, b = np.unravel_index(int(np.argmin(d)), d.shape)
            dv = float(d[a, b])
            if gap is not None and dv > gap:
                continue
            k, conf = _offset(phase, labeled, comps[i]["label"], comps[j]["label"], tuple(coords[i][a]),
                              tuple(coords[j][b]), max(link_size, 1))
            links.append((i, j, k, conf * np.sqrt(min(sizes[i], sizes[j])) / (np.sqrt(dv) + 1.0)))
    return links


def _solve_offsets(n, links) -> np.ndarray | None:
    """min Σ w_e·d_e, d_e >= |k_i - k_j - k_e|, k_0 = 0, integer k in [-100, 100]."""
    m = len(links)
    c = np.r_[np.zeros(n), [max(1, int(w * 1000)) for *_, w in links]].astype(float)
    a = np.zeros((2 * m, n + m))
    lo = np.empty(2 * m)
    for e, (i, j, k, _) in enumerate(links):
        a[2 * e, [i, j, n + e]] = [-1, 1, 1]          # d_e - (k_i - k_j) >= -k_e
        a[2 * e + 1, [i, j, n + e]] = [1, -1, 1]      # d_e + (k_i - k_j) >= k_e
        lo[2 * e], lo[2 * e + 1] = -k, k
    lb = np.r_[np.full(n, -100.0), np.zeros(m)]
    ub = np.r_[np.full(n, 100.0), np.full(m, 200.0)]
    lb[0] = ub[0] = 0.0
    res = milp(c, constraints=LinearConstraint(a, lo, np.inf), integrality=np.r_[np.ones(n), np.ones(m)],
               bounds=Bounds(lb, ub), options={"time_limit": 60.0})
    return None if res.x is None else np.round(res.x[:n]).astype(int)


def _greedy(n, links) -> np.ndarray:
    k = np.zeros(n, int)
    adj = {i: [] for i in range(n)}
    for i, j, kij, _ in links:
        adj[i].append((j, kij))
        adj[j].append((i, -kij))
    seen, queue = {0}, [0]
    while queue:
        i = queue.pop(0)
        for j, kij in adj[i]:
            if j not in seen:
                k[j] = k[i] + kij
                seen.add(j)
                queue.append(j)
    return k


def link_components(phase: np.ndarray, min_size: int | None = None, gap: int | None = None, link_size: int = 5,
                    link_count: int = 30) -> np.ndarray:
    """``phase`` 2-D unwrapped (NaN = no data); returns it with every island shifted by its 2π offset."""
    valid = np.isfinite(phase)
    if not valid.any():
        return phase
    labeled, n_total = ndimage.label(valid, structure=FOUR)
    if n_total < 2:
        return phase
    sizes = np.bincount(labeled.ravel(), minlength=n_total + 1)
    slices = ndimage.find_objects(labeled)
    ms = _min_size(int(valid.sum()), min_size)
    comps = [{"label": i + 1, "slices": slices[i]} for i in np.argsort(sizes[1:])[::-1]
             if sizes[i + 1] >= ms and slices[i] is not None]
    if len(comps) < 2:
        return phase
    links = _connections(phase, labeled, comps, gap, link_count, link_size)
    if not links:
        return phase
    k = _solve_offsets(len(comps), links)
    if k is None:
        k = _greedy(len(comps), links)
    out = phase.copy()
    for c, kv in zip(comps, k, strict=True):
        if kv:
            out[labeled == c["label"]] += kv * 2.0 * np.pi
    return out
