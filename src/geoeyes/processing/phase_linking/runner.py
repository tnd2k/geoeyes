"""Phase linking of a StackStore (distributed scatterers).

Per tile (padded by the half window): SHP by a two-sample Anderson-Darling (or KS) test on the amplitudes; pixels
with at least ``min_shp`` homogeneous neighbours get the coherence matrix over their SHP and linked phases; the
others, and PS (amplitude dispersion ``<= ps_da_max``), keep their SLC. The result is a new variable, the input
``slc`` is not modified::

    slc_linked              (date, y, x) complex64   |slc[k]| · e^{j(arg slc[ref] + θ_k)}, so that
                                                     slc_linked[ref]·conj(slc_linked[k]) has the linked phase
    pl_shp_count            (y, x)       int16       homogeneous neighbours
    pl_temporal_coherence   (y, x)       float32     fit of the linked phases (NaN where not linked)
    pl_pair_coherence       (pl_pair, y, x) float32  |C_ij| over the SHP family of the ``store_pairs`` (if any),
                                                     attribute ``pairs`` ["YYYY-MM-DD/YYYY-MM-DD", ...]

The optional Gaussian post-filter smooths each interferogram ``slc[ref]·conj(slc[k])`` over the linked pixels
and re-derives their ``slc_linked[k]`` from it, keeping the amplitudes, the reference SLC and the PS
(``gaussian_scope = "all"``: every pixel, as the legacy filter).
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

from geoeyes.core.errors import StoreError
from geoeyes.core.logging import event
from geoeyes.processing.phase_linking import estimators
from geoeyes.processing.phase_linking.shp import shp_mask, window_offsets

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhaseLinkingParams:
    estimator: str = "adaptive"
    half_window: tuple[int, int] = (7, 7)
    shp_test: str = "ad"             # ad (Anderson-Darling) | ks (Kolmogorov-Smirnov)
    shp_alpha: float = 0.05
    min_shp: int = 25
    ps_da_max: float = 0.25          # pixels this stable in amplitude are PS and keep their SLC; 0 links all
    adaptive_coherence_threshold: float = 0.6
    tile_size: int = 512
    gaussian_sigma: float = 0.0
    gaussian_scope: str = "linked"   # post-filter the linked pixels only (PS untouched) | "all" (legacy)
    store_pairs: tuple[tuple[str, str], ...] = ()   # date pairs whose |C_ij| is kept (pl_pair_coherence)
    batch: int = 4096

    @classmethod
    def from_section(cls, sec) -> PhaseLinkingParams:
        """From the project ``[phase_linking]`` section."""
        return cls(estimator=sec.estimator, half_window=tuple(sec.half_window), shp_test=sec.shp_test,
                   shp_alpha=sec.shp_alpha,
                   min_shp=sec.min_shp, ps_da_max=sec.ps_da_max,
                   adaptive_coherence_threshold=sec.adaptive_coherence_threshold, tile_size=sec.tile_size,
                   gaussian_sigma=sec.gaussian_sigma, gaussian_scope=sec.gaussian_scope,
                   store_pairs=tuple(tuple(str(d) for d in p) for p in sec.store_pairs))


def link_tile(slc: np.ndarray, interior: tuple[slice, slice], ref: int, p: PhaseLinkingParams,
              pair_idx: tuple[tuple[int, int], ...] = ()):
    """Phase-link the ``interior`` of a padded tile ``slc`` (n, H, W) (zeros outside the image).

    Returns (linked SLC (n, h, w), SHP count (h, w), temporal coherence (h, w), |C_ij| of the ``pair_idx`` date
    pairs (len(pair_idx), h, w) or None); the pair coherences are NaN where a pixel is not linked.
    """
    amp = np.abs(slc)
    mask = shp_mask(amp, p.half_window, p.shp_alpha, p.shp_test)[interior]
    count = mask.sum(-1) - 1
    out = slc[(slice(None), *interior)].copy()
    tcoh = np.full(count.shape, np.nan, np.float32)
    pc = np.full((len(pair_idx), *count.shape), np.nan, np.float32) if pair_idx else None
    a = amp[(slice(None), *interior)]
    mean = a.mean(0)
    ps = a.std(0) <= p.ps_da_max * np.where(mean > 0, mean, np.inf)
    rows, cols = np.nonzero((count >= p.min_shp) & ~ps)
    off = window_offsets(p.half_window)
    r0, c0 = interior[0].start, interior[1].start
    for b in range(0, rows.size, p.batch):
        r, c = rows[b:b + p.batch], cols[b:b + p.batch]
        S = slc[:, (r + r0)[:, None] + off[:, 0], (c + c0)[:, None] + off[:, 1]].transpose(1, 0, 2)  # (B, n, win)
        C = estimators.coherence(S, mask[r, c])
        for k, (i, j) in enumerate(pair_idx):
            pc[k, r, c] = np.abs(C[:, i, j])
        v = estimators.link(C, p.estimator, ref, p.adaptive_coherence_threshold)
        tcoh[r, c] = estimators.temporal_coherence(C, v)
        s = out[:, r, c]                                                                  # (n, B)
        out[:, r, c] = (np.abs(s) * np.exp(1j * (np.angle(s[ref]) + np.angle(v.T)))).astype(np.complex64)
    return out, count.astype(np.int16), tcoh, pc


def pair_coherence(store, pairs: list[tuple[int, int]], params: PhaseLinkingParams | None = None, *,
                   workers: int | None = None) -> np.ndarray:
    """|coherence| of date pairs over the SHP family of each pixel, as phase linking forms it (same test, window
    and ``min_shp``): (len(pairs), y, x) float32, NaN where a pixel has too few homogeneous neighbours. For change
    detection over distributed scatterers, where a boxcar window mixes unlike pixels."""
    params = params or PhaseLinkingParams()
    ds = store.open()
    _, ny, nx = ds["slc"].shape
    dates = sorted({i for p in pairs for i in p})
    col = {d: k for k, d in enumerate(dates)}
    hy, hx = params.half_window
    ts = params.tile_size
    off = window_offsets(params.half_window)
    out = np.full((len(pairs), ny, nx), np.nan, np.float32)

    def work(t):
        import dask
        y, x = t
        h, w = min(ts, ny - y), min(ts, nx - x)
        ya, yb, xa, xb = max(0, y - hy), min(ny, y + h + hy), max(0, x - hx), min(nx, x + w + hx)
        with dask.config.set(scheduler="synchronous"):
            block = ds["slc"].isel(y=slice(ya, yb), x=slice(xa, xb)).values
        block = np.pad(block, ((0, 0), (hy - (y - ya), y + h + hy - yb), (hx - (x - xa), x + w + hx - xb)))
        interior = (slice(hy, hy + h), slice(hx, hx + w))
        mask = shp_mask(np.abs(block), params.half_window, params.shp_alpha, params.shp_test)[interior]
        res = np.full((len(pairs), h, w), np.nan, np.float32)
        rows, cols = np.nonzero(mask.sum(-1) - 1 >= params.min_shp)
        sub = block[dates]
        for b in range(0, rows.size, params.batch):
            r, c = rows[b:b + params.batch], cols[b:b + params.batch]
            S = sub[:, (r + hy)[:, None] + off[:, 0], (c + hx)[:, None] + off[:, 1]].transpose(1, 0, 2)
            C = np.abs(estimators.coherence(S, mask[r, c]))
            for k, (i, j) in enumerate(pairs):
                res[k, r, c] = C[:, col[i], col[j]]
        return t, res

    tiles = [(y, x) for y in range(0, ny, ts) for x in range(0, nx, ts)]
    with ThreadPoolExecutor(workers or min(8, os.cpu_count() or 1)) as pool:
        for i, ((y, x), res) in enumerate(pool.map(work, tiles)):
            out[:, y:y + res.shape[1], x:x + res.shape[2]] = res
            event(log, "progress", "SHP pair coherence", stage="pair_coherence", done=i + 1, total=len(tiles))
    return out


DONE_ATTR = "phase_linking_done"     # stack attribute: parameters of the last completed run


def fingerprint(params: PhaseLinkingParams) -> dict:
    """The parameters that change the result (JSON form, as stored in the stack attributes); ``store_pairs`` only
    when some are asked, so that stacks linked before it existed stay up to date."""
    return {k: [list(x) if isinstance(x, tuple) else x for x in v] if isinstance(v, tuple) else v
            for k, v in asdict(params).items()
            if k not in ("tile_size", "batch") and not (k == "store_pairs" and not v)}


PAIRS_VAR = "pl_pair_coherence"      # (pl_pair, y, x) float32, attribute "pairs": ["YYYY-MM-DD/YYYY-MM-DD", ...]


def pair_indices(dates: list[str], pairs) -> tuple[tuple[int, int], ...]:
    """Date indices of ``pairs`` (date strings) in the stack's ``dates``; a date not in the stack is an error."""
    missing = sorted({d for p in pairs for d in p} - set(dates))
    if missing:
        raise StoreError(f"phase_linking.store_pairs: dates {missing} not in the stack ({dates[0]}..{dates[-1]})")
    return tuple((dates.index(a), dates.index(b)) for a, b in pairs)


def stored_pairs(store) -> dict[str, int]:
    """The pairs of ``pl_pair_coherence`` in a store, as {"YYYY-MM-DD/YYYY-MM-DD": index}."""
    if not store.has(PAIRS_VAR):
        return {}
    return {p: k for k, p in enumerate(store.open()[PAIRS_VAR].attrs.get("pairs", []))}


def provenance(store, slc_var: str) -> dict:
    """``{"phase_linking": <parameters>}`` for the manifest of a run on the linked stack, else ``{}``.
    A store linked before ``shp_test`` existed used the KS test (the only one then)."""
    if slc_var != "slc_linked":
        return {}
    done = store.attrs.get(DONE_ATTR)
    return {"phase_linking": {"shp_test": "ks", **done} if isinstance(done, dict) else None}


def is_done(store, params: PhaseLinkingParams, out_var: str = "slc_linked") -> bool:
    return store.has(out_var) and store.attrs.get(DONE_ATTR) == fingerprint(params)


def run(store, params: PhaseLinkingParams | None = None, *, out_var: str = "slc_linked",
        workers: int | None = None) -> dict:
    t0 = time.time()
    params = params or PhaseLinkingParams()
    store.update_attrs(**{DONE_ATTR: None})
    ds = store.open()
    dates = [str(np.datetime64(d, "D")) for d in ds["date"].values]
    ref = dates.index(str(ds.attrs["reference_date"]))
    _, ny, nx = ds["slc"].shape
    hy, hx = params.half_window
    ts = params.tile_size
    tiles = [(y, x) for y in range(0, ny, ts) for x in range(0, nx, ts)]
    pair_idx = pair_indices(dates, params.store_pairs)
    pair_coh = np.full((len(pair_idx), ny, nx), np.nan, np.float32) if pair_idx else None
    store.allocate(out_var, ("date", "y", "x"), np.complex64, chunks={"y": ts, "x": ts},
                   attrs={"phase_linking": fingerprint(params)})
    store.allocate("pl_shp_count", ("y", "x"), np.int16, chunks={"y": ts, "x": ts})
    store.allocate("pl_temporal_coherence", ("y", "x"), np.float32, chunks={"y": ts, "x": ts})

    def work(t):
        import dask
        y, x = t
        h, w = min(ts, ny - y), min(ts, nx - x)
        ya, yb, xa, xb = max(0, y - hy), min(ny, y + h + hy), max(0, x - hx), min(nx, x + w + hx)
        with dask.config.set(scheduler="synchronous"):
            block = ds["slc"].isel(y=slice(ya, yb), x=slice(xa, xb)).values
        block = np.pad(block, ((0, 0), (hy - (y - ya), y + h + hy - yb), (hx - (x - xa), x + w + hx - xb)))
        return t, link_tile(block, (slice(hy, hy + h), slice(hx, hx + w)), ref, params, pair_idx)

    n_linked = 0
    with ThreadPoolExecutor(workers or min(8, os.cpu_count() or 1)) as pool:
        for i, ((y, x), (out, count, tcoh, pc)) in enumerate(pool.map(work, tiles)):
            h, w = count.shape
            region = {"y": slice(y, y + h), "x": slice(x, x + w)}
            store.write_region(out_var, out, region)
            store.write_region("pl_shp_count", count, region)
            store.write_region("pl_temporal_coherence", tcoh, region)
            if pc is not None:
                pair_coh[:, y:y + h, x:x + w] = pc
            n_linked += int(np.isfinite(tcoh).sum())
            event(log, "progress", "phase linking", stage="phase_linking", done=i + 1, total=len(tiles))
    if pair_coh is not None:
        store.write(PAIRS_VAR, pair_coh, ("pl_pair", "y", "x"), chunks={"pl_pair": 1, "y": ts, "x": ts},
                    attrs={"pairs": [f"{a}/{b}" for a, b in params.store_pairs]})
    if params.gaussian_sigma > 0:
        mask = np.isfinite(store.read("pl_temporal_coherence")) if params.gaussian_scope == "linked" else None
        gaussian_postfilter(store, out_var, ref, params.gaussian_sigma, mask)
    store.update_attrs(**{DONE_ATTR: fingerprint(params)})
    summary = {"pixels": ny * nx, "linked": n_linked, "linked_fraction": n_linked / (ny * nx),
               "seconds": round(time.time() - t0, 1)}
    log.info("phase linking: %d of %d pixels linked (%.1f%%) in %.0f s", n_linked, ny * nx,
             100 * summary["linked_fraction"], summary["seconds"])
    return summary


def gaussian_postfilter(store, var: str, ref: int, sigma: float, mask: np.ndarray | None = None) -> None:
    """Smooth ``var[ref]·conj(var[k])`` with a Gaussian (σ in pixels) and rebuild ``var[k]`` from its phase.

    ``mask`` (y, x): only these pixels (the linked ones) enter the smoothing and are rewritten, so PS keep their
    own phase and a bright PS does not leak into its neighbours; None = every pixel (legacy)."""
    m = store.read(var, date=ref)
    um = m / np.where(np.abs(m) > 0, np.abs(m), 1.0)
    for k in range(store.open().sizes["date"]):
        if k == ref:
            continue
        s = store.read(var, date=k)
        ifg = m * np.conj(s)
        if mask is not None:
            ifg = np.where(mask, ifg, 0)
        z = gaussian_filter(ifg.real, sigma) + 1j * gaussian_filter(ifg.imag, sigma)
        az = np.abs(z)
        new = np.abs(s) * um * np.conj(np.where(az > 0, z / np.where(az > 0, az, 1.0), 0))
        if mask is not None:
            new = np.where(mask, new, s)
        store.write_region(var, new.astype(np.complex64)[None], {"date": slice(k, k + 1)})
