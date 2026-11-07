"""Linear rate of every PS from its wrapped phase, before the grid (``[ps] unwrap_ps_rate``).

The grid unwrapping sees cells: a PS whose motion differs from its cell (a subsiding road or canal bank through
stable fields, 20-50 m wide) keeps only its wrapped residual to the cell, so it loses a cycle once that residual
passes ±π (14 mm on C-band: a few mm/yr of contrast over three years; HCMC Binh Chanh vs SARPROZ, 2026-11-07).
Removing a rate model of each PS first leaves small residuals, which the grid can carry.

Rates come from the PS network itself (as the arc-based PSI of SARPROZ / DePSI):

1. Delaunay triangulation of the PS, arcs longer than ``max_arc`` dropped (atmosphere);
2. linear rate of every arc from its wrapped double-difference phase (periodogram + least-squares refinement,
   ``space_time.edge_rates``: kept only above chance, else no arc);
3. only arcs that close a Delaunay triangle (three reliable sides, misclosure <= one trial step) are used: a
   pendant PS or two PS joined by a single arc have no check, and one wrong arc there became a fake rate (two PS
   at ±r/2 from one noise arc of rate r; up to rate_max in a simulated stable scene, 2026-11-08);
4. rates of the PS from the arc rates by an L1 (iteratively reweighted) least-squares integration, so a few
   wrong arcs do not spread. PS without a checked arc, or in a part of fewer than ``min_part`` PS, get 0;
5. every other part is tied to the largest one by the median difference to its nearest PS there (within
   2 × ``max_arc``), else set to 0. The largest part is defined up to a constant, which the grid unwrapping
   carries as now.

A PS whose own noise happens to fit a trend gives agreeing arcs to all its neighbours; no network check can see
it, and it stays a noisy PS for coherence / weeding.
"""
from __future__ import annotations

import logging

import numpy as np

from geoeyes.processing.ps.unwrap.space_time import edge_rates

log = logging.getLogger(__name__)


def delaunay_network(xy: np.ndarray, max_arc: float) -> tuple[np.ndarray, np.ndarray]:
    """Delaunay network of ``xy`` (n, 2) m: (m, 2) unique arcs (a < b) no longer than ``max_arc`` m, and (k, 3)
    arc indices of the triangles whose three sides are all kept, ordered (v0v1, v1v2, v0v2) with v0 < v1 < v2,
    so the closure of a triangle is r[0] + r[1] - r[2]."""
    from scipy.spatial import Delaunay
    xy = np.asarray(xy, np.float64)
    if xy.shape[0] < 3:
        return np.zeros((0, 2), np.int64), np.zeros((0, 3), np.int64)
    tri = np.sort(Delaunay(xy).simplices, axis=1)
    sides = np.stack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]], axis=1)       # (k, 3, 2)
    e, inv = np.unique(sides.reshape(-1, 2), axis=0, return_inverse=True)
    inv = inv.reshape(-1, 3)
    keep = np.hypot(*(xy[e[:, 1]] - xy[e[:, 0]]).T) <= max_arc
    new = np.cumsum(keep) - 1
    tri_ok = keep[inv].all(axis=1)
    return e[keep].astype(np.int64), new[inv[tri_ok]].astype(np.int64)


def delaunay_arcs(xy: np.ndarray, max_arc: float) -> np.ndarray:
    """(m, 2) unique PS index pairs (a < b) of the Delaunay triangulation of ``xy`` (n, 2) m, no longer than
    ``max_arc`` m."""
    return delaunay_network(xy, max_arc)[0]


def closed_arcs(tri: np.ndarray, rate: np.ndarray, ok: np.ndarray, tol: float) -> np.ndarray:
    """(m,) arcs that close at least one triangle: all three sides ``ok`` and |r01 + r12 - r02| <= ``tol``. An arc
    in no such triangle (a pendant PS, two PS joined by one arc) cannot be checked, and a wrong rate there is taken
    as is: the L1 integration splits it ±r/2 between two isolated PS, or gives it whole to a pendant PS."""
    out = np.zeros(ok.shape[0], bool)
    if tri.shape[0] == 0:
        return out
    good = ok[tri].all(axis=1)
    r = rate[tri]
    good &= np.abs(r[:, 0] + r[:, 1] - r[:, 2]) <= tol
    out[tri[good].ravel()] = True
    return out


def integrate_l1(arcs: np.ndarray, rate: np.ndarray, n: int, iters: int = 5, delta: float | None = None) -> np.ndarray:
    """Node values x (n,) with x[b] - x[a] ≈ ``rate`` on ``arcs`` (m, 2), in the L1 sense (IRLS). Nodes without an
    arc get 0; every connected part has zero mean (a small ridge term fixes the free constants)."""
    from scipy.sparse import coo_matrix, identity
    from scipy.sparse.linalg import spsolve
    m = arcs.shape[0]
    x = np.zeros(n)
    if m == 0:
        return x
    rows = np.repeat(np.arange(m), 2)
    cols = arcs.ravel()
    vals = np.tile([-1.0, 1.0], m)
    A = coo_matrix((vals, (rows, cols)), shape=(m, n)).tocsr()
    r = np.asarray(rate, np.float64)
    if delta is None:
        delta = max(1e-3, 0.05 * float(np.median(np.abs(r))))
    w = np.ones(m)
    for _ in range(max(1, iters)):
        AtW = A.T.multiply(w)
        L = (AtW @ A).tocsc()
        ridge = 1e-6 * max(float(L.diagonal().mean()), 1e-12)
        x = spsolve((L + ridge * identity(n, format="csc")).tocsc(), AtW @ r)
        w = 1.0 / np.maximum(np.abs(A @ x - r), delta)
    return x


def _parts(arcs: np.ndarray, n: int) -> np.ndarray:
    """Connected-part label of every node (a node without an arc is its own part)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    return connected_components(coo_matrix((np.ones(arcs.shape[0]), (arcs[:, 0], arcs[:, 1])), shape=(n, n)),
                                directed=False)[1]


def anchor_parts(x: np.ndarray, arcs: np.ndarray, xy: np.ndarray, max_dist: float,
                 min_pairs: int = 3) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Each part of the network other than the largest is shifted so that its PS agree, in the median, with their
    nearest PS of the largest part within ``max_dist`` m (the rate is assumed continuous across the gap: a river,
    a field without PS). Parts with fewer than ``min_pairs`` such PS cannot be tied and are set to 0 (left to the
    grid). Returns (x, PS kept, parts anchored, parts dropped)."""
    from scipy.spatial import cKDTree
    n = x.shape[0]
    x = x.copy()
    keep = np.zeros(n, bool)
    if arcs.shape[0] == 0:
        return np.zeros(n), keep, 0, 0
    keep[arcs.ravel()] = True
    lab = _parts(arcs, n)
    size = np.bincount(lab[keep], minlength=lab.max() + 1)
    main = int(np.argmax(size))
    is_main = keep & (lab == main)
    other = np.flatnonzero(keep & ~is_main)
    if other.size == 0:
        return np.where(keep, x, 0.0), keep, 0, 0
    main_ix = np.flatnonzero(is_main)
    d, j = cKDTree(xy[main_ix]).query(xy[other], distance_upper_bound=max_dist)
    near = np.isfinite(d)
    diff = np.where(near, x[main_ix[np.minimum(j, main_ix.size - 1)]] - x[other], np.nan)
    order = np.argsort(lab[other], kind="stable")
    labs, start = np.unique(lab[other][order], return_index=True)
    n_anch = n_drop = 0
    for k, idx in zip(labs, np.split(order, start[1:])):
        dk = diff[idx][near[idx]]
        members = other[idx]
        if dk.size >= min_pairs:
            x[members] += float(np.median(dk))
            n_anch += 1
        else:
            keep[members] = False
            n_drop += 1
    return np.where(keep, x, 0.0), keep, n_anch, n_drop


def ps_rate_model(ph: np.ndarray, xy: np.ndarray, t: np.ndarray, rate_max: float, max_arc: float = 500.0,
                  chunk: int = 100_000, iters: int = 5, min_reliable: float = 0.0,
                  min_part: int = 30, anchor_dist: float | None = None) -> np.ndarray | None:
    """Linear phase rate (rad per unit of ``t``) of every PS. ``ph`` (n, n_ifg) complex phasors of the PS (0 = no
    data), ``xy`` (n, 2) m, ``t`` (n_ifg,) time from the master, ``rate_max`` the largest rate searched (same unit).
    None when fewer than ``min_reliable`` of the arcs have a rate above chance (the network cannot carry a model).
    PS in a connected part of fewer than ``min_part`` PS get 0 (zero mean of a few PS: offsets of 5-16 mm/yr on
    stable PS in simulation, enough for cycle errors over a few years). The other parts are tied to the largest by
    ``anchor_parts`` within ``anchor_dist`` m (default 2 × ``max_arc``), not left at their own zero mean (two banks
    of a river would differ by an arbitrary rate, and the grid unwrapping sees that step grow with time)."""
    n = ph.shape[0]
    t = np.asarray(t, np.float64)
    arcs, tri = delaunay_network(xy, max_arc)
    rates = np.zeros(arcs.shape[0], np.float32)
    ok = np.zeros(arcs.shape[0], bool)
    for s in range(0, arcs.shape[0], chunk):
        a, b = arcs[s:s + chunk, 0], arcs[s:s + chunk, 1]
        d = (ph[b] * np.conj(ph[a])).astype(np.complex64)
        rates[s:s + chunk], ok[s:s + chunk] = edge_rates(d, t, rate_max, with_reliable=True)
    share = float(ok.mean()) if ok.size else 0.0
    if share < min_reliable:
        log.info("PS rate model not used: %.1f %% of %d arcs with a rate above chance (< %.0f %%)", 100 * share,
                 arcs.shape[0], 100 * min_reliable)
        return None
    span = float(np.ptp(t)) if t.size else 0.0
    tol = np.pi / 4 / span if span > 0 else 0.0              # one trial step of the periodogram
    use = closed_arcs(tri, rates, ok, tol)
    reached = np.zeros(n, bool)
    reached[arcs[ok].ravel()] = True
    checked = np.zeros(n, bool)
    checked[arcs[use].ravel()] = True
    if use.any():                                          # small parts: too few PS to trust
        lab = _parts(arcs[use], n)
        big = np.bincount(lab)[lab] >= min_part
        use &= big[arcs[:, 0]]
    x = integrate_l1(arcs[use], rates[use], n, iters=iters)
    in_parts = np.zeros(n, bool)
    in_parts[arcs[use].ravel()] = True
    x, touched, n_anch, n_drop = anchor_parts(x, arcs[use], np.asarray(xy, np.float64),
                                              2 * max_arc if anchor_dist is None else anchor_dist)
    log.info("PS rate model: %d of %d arcs (%.1f %%) with a rate, %d in a closed triangle; %d of %d PS reached, "
             "%d parts tied to the largest (left at 0: %d PS only by unchecked arcs, %d in parts < %d PS, %d in %d "
             "parts too far to tie; arcs <= %.0f m)", int(ok.sum()), arcs.shape[0],
             100.0 * ok.mean() if ok.size else 0.0, int(use.sum()), int(touched.sum()), n, n_anch,
             int((reached & ~checked).sum()), int((checked & ~in_parts).sum()), min_part,
             int((in_parts & ~touched).sum()), n_drop, max_arc)
    return x
