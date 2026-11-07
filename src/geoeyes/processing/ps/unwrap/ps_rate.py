"""Linear rate of every PS from its wrapped phase, before the grid (``[ps] unwrap_ps_rate``).

The grid unwrapping sees cells: a PS whose motion differs from its cell (a subsiding road or canal bank through
stable fields, 20-50 m wide) keeps only its wrapped residual to the cell, so it loses a cycle once that residual
passes ±π (14 mm on C-band: a few mm/yr of contrast over three years; HCMC Binh Chanh vs SARPROZ, 2026-11-07).
Removing a rate model of each PS first leaves small residuals, which the grid can carry.

Rates come from the PS network itself (as the arc-based PSI of SARPROZ / DePSI):

1. Delaunay triangulation of the PS, arcs longer than ``max_arc`` dropped (atmosphere);
2. linear rate of every arc from its wrapped double-difference phase (periodogram + least-squares refinement,
   ``space_time.edge_rates``: kept only above chance, else no arc);
3. rates of the PS from the arc rates by an L1 (iteratively reweighted) least-squares integration, so a few
   wrong arcs do not spread. PS without a reliable arc get 0; each connected part is defined up to a constant,
   which the grid unwrapping then carries as now.
"""
from __future__ import annotations

import logging

import numpy as np

from geoeyes.processing.ps.unwrap.space_time import edge_rates

log = logging.getLogger(__name__)


def delaunay_arcs(xy: np.ndarray, max_arc: float) -> np.ndarray:
    """(m, 2) unique PS index pairs (a < b) of the Delaunay triangulation of ``xy`` (n, 2) m, no longer than
    ``max_arc`` m."""
    from scipy.spatial import Delaunay
    xy = np.asarray(xy, np.float64)
    if xy.shape[0] < 3:
        return np.zeros((0, 2), np.int64)
    tri = Delaunay(xy).simplices
    e = np.vstack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]])
    e = np.unique(np.sort(e, axis=1), axis=0).astype(np.int64)
    length = np.hypot(*(xy[e[:, 1]] - xy[e[:, 0]]).T)
    return e[length <= max_arc]


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


def ps_rate_model(ph: np.ndarray, xy: np.ndarray, t: np.ndarray, rate_max: float, max_arc: float = 500.0,
                  chunk: int = 100_000, iters: int = 5, min_reliable: float = 0.0) -> np.ndarray | None:
    """Linear phase rate (rad per unit of ``t``) of every PS. ``ph`` (n, n_ifg) complex phasors of the PS (0 = no
    data), ``xy`` (n, 2) m, ``t`` (n_ifg,) time from the master, ``rate_max`` the largest rate searched (same unit).
    None when fewer than ``min_reliable`` of the arcs have a rate above chance (the network cannot carry a model)."""
    n = ph.shape[0]
    t = np.asarray(t, np.float64)
    arcs = delaunay_arcs(xy, max_arc)
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
    x = integrate_l1(arcs[ok], rates[ok], n, iters=iters)
    touched = np.zeros(n, bool)
    touched[arcs[ok].ravel()] = True
    log.info("PS rate model: %d of %d arcs (%.1f %%) with a rate, %d of %d PS reached (arcs <= %.0f m)",
             int(ok.sum()), arcs.shape[0], 100.0 * ok.mean() if ok.size else 0.0, int(touched.sum()), n, max_arc)
    return np.where(touched, x, 0.0)
