"""Topofit ambiguity handling: Q-score thresholds, Q -> trust weight, and edge-preserving spatial
regularisation of K over the Delaunay neighbour graph (IRLS with a Huber/TV edge penalty)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg, spsolve
from scipy.spatial import Delaunay

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemErrorParams:
    """Ambiguity down-weighting and spatial K regularisation (steps 2 and 3). ``enabled`` = False is the
    classic StaMPS behaviour: full trial search, no ambiguity score, no regularisation."""

    enabled: bool = True
    amb_auto_threshold: bool = True
    amb_q_reject: float = 0.10
    amb_q_ok: float = 0.25
    spatial_lambda: float = 0.5
    spatial_huber_delta: float | None = None
    spatial_iters: int = 5


def thresholds(Q, p: DemErrorParams) -> tuple[float, float]:
    """(q_reject, q_ok): auto-derived from the Q histogram, or the fixed values."""
    if not p.amb_auto_threshold:
        return p.amb_q_reject, p.amb_q_ok
    q_reject, q_ok, diag = auto_q_thresholds(Q, p.amb_q_reject, p.amb_q_ok)
    log.debug("Q thresholds: reject %.3f ok %.3f (%s)", q_reject, q_ok, diag)
    return q_reject, q_ok


def regularize(K: np.ndarray, coh: np.ndarray, Q: np.ndarray, edges, p: DemErrorParams) -> np.ndarray:
    """Spatially regularise K with confidence coh²·w(Q)."""
    return regularize_k(K, coh**2 * amb_weight(Q, *thresholds(Q, p)), edges, p.spatial_lambda,
                        p.spatial_huber_delta, p.spatial_iters)


def amb_weight(Q, q_reject: float, q_ok: float) -> np.ndarray:
    """Linear ramp: Q <= q_reject -> 0, Q >= q_ok -> 1."""
    q_reject = min(float(q_reject), float(q_ok) - 1e-9)
    span = max(float(q_ok) - q_reject, 1e-9)
    return np.clip((np.asarray(Q, dtype=np.float64) - q_reject) / span, 0.0, 1.0)


def auto_q_thresholds(Q, fallback_reject=0.10, fallback_ok=0.25, clamp_reject=(0.02, 0.35),
                      clamp_ok=(0.05, 0.60), min_gap=0.03, n_bins=100) -> tuple[float, float, dict | None]:
    """(q_reject, q_ok) from an Otsu split of the Q histogram, ramp sized by each side's MAD; the
    fallbacks when Q carries no usable split."""
    q = np.asarray(Q, dtype=np.float64).reshape(-1)
    q = q[np.isfinite(q)]
    fallback = float(fallback_reject), float(fallback_ok), None
    if q.size < 50 or np.ptp(q) < 1e-6:
        return fallback
    hist, edges = np.histogram(q, bins=n_bins, range=(0.0, 1.0))
    centers = 0.5 * (edges[:-1] + edges[1:])
    total = float(hist.sum())
    if total <= 0:
        return fallback
    w = hist.astype(np.float64) / total
    cum_w = np.cumsum(w)
    cum_wx = np.cumsum(w * centers)
    with np.errstate(divide="ignore", invalid="ignore"):
        between = np.where((cum_w > 1e-9) & (cum_w < 1 - 1e-9),
                           (cum_wx[-1] * cum_w - cum_wx) ** 2 / (cum_w * (1 - cum_w)), -np.inf)
    k = int(np.argmax(between))
    if not np.isfinite(between[k]):
        return fallback
    split = float(centers[k])
    low, high = q[q <= split], q[q > split]
    if low.size < 10 or high.size < 10:
        return fallback
    s_low = float(np.median(np.abs(low - np.median(low))) * 1.4826)
    s_high = float(np.median(np.abs(high - np.median(high))) * 1.4826)
    q_reject = float(np.clip(split - s_low, *clamp_reject))
    q_ok = float(np.clip(split + s_high, *clamp_ok))
    if q_ok - q_reject < min_gap:
        mid = 0.5 * (q_ok + q_reject)
        q_reject, q_ok = mid - min_gap / 2, mid + min_gap / 2
    q_reject = max(0.0, q_reject)
    q_ok = min(1.0, max(q_ok, q_reject + min_gap))
    return q_reject, q_ok, {"q_split": split, "n_low": int(low.size), "n_high": int(high.size)}


def delaunay_edges(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Edges of the Delaunay triangulation, one per triangle side (interior edges appear twice, which
    weights them ~2x in the smoothness term; kept for parity with the legacy engine)."""
    try:
        simplices = Delaunay(np.asarray(xy, dtype=np.float64)[:, :2]).simplices
    except Exception:  # degenerate geometry (collinear / too few points)
        return np.array([], np.int64), np.array([], np.int64)
    ei = np.concatenate([simplices[:, 0], simplices[:, 1], simplices[:, 0]]).astype(np.int64)
    ej = np.concatenate([simplices[:, 1], simplices[:, 2], simplices[:, 2]]).astype(np.int64)
    return ei, ej


def regularize_k(K: np.ndarray, conf: np.ndarray, edges: tuple[np.ndarray, np.ndarray],
                 lambda_reg: float = 0.5, huber_delta: float | None = None, n_iters: int = 5) -> np.ndarray:
    """Minimise Σ conf·(K - K0)² + λ Σ_edges huber(K_i - K_j) by IRLS. NaN K (no estimate) are free
    nodes during the solve and stay NaN in the output. ``huber_delta`` defaults to 3x the median edge
    difference."""
    ei, ej = edges
    n = K.shape[0]
    if n < 4 or ei.size == 0:
        return K.copy()
    k0 = np.asarray(K, dtype=np.float64).reshape(-1)
    conf = np.clip(np.asarray(conf, dtype=np.float64).reshape(-1), 1e-3, None)
    finite = np.isfinite(k0)
    if not finite.all():
        conf = np.where(finite, conf, 0.0)
        k0 = np.where(finite, k0, 0.0)
    if huber_delta is None:
        d0 = np.abs(k0[ei] - k0[ej])
        d0 = d0[np.isfinite(d0)]
        huber_delta = max(3.0 * float(np.median(d0)), 1e-6) if d0.size else 1e-6

    k = k0.copy()
    for _ in range(max(1, int(n_iters))):
        w = float(lambda_reg) / np.maximum(np.abs(k[ei] - k[ej]), huber_delta)
        deg = np.zeros(n)
        np.add.at(deg, ei, w)
        np.add.at(deg, ej, w)
        off = sp.coo_matrix((np.concatenate([-w, -w]), (np.concatenate([ei, ej]), np.concatenate([ej, ei]))),
                            shape=(n, n))
        diag = conf + deg + 1e-9                       # strictly SPD even for isolated free nodes
        a = sp.diags(diag) + off
        b = conf * k0
        k_new, info = cg(a.tocsr(), b, x0=k, M=sp.diags(1.0 / diag), atol=0.0, rtol=1e-5, maxiter=500)
        if info == 0 and np.all(np.isfinite(k_new)):
            k = k_new
            continue
        log.warning("K regularisation: CG did not converge (info=%d), direct solve", info)
        try:
            k_direct = np.asarray(spsolve(a.tocsc(), b), dtype=np.float64)
            if np.all(np.isfinite(k_direct)):
                k = k_direct
        except Exception as exc:  # keep the previous iterate
            log.warning("K regularisation: direct solve failed (%s)", exc)
    out = k.astype(K.dtype)
    out[~finite] = np.nan
    return out
