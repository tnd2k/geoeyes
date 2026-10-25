"""Phase linking of a StackStore (distributed scatterers).

Per tile (padded by the half window): SHP by a two-sample Anderson-Darling (or KS) test on the amplitudes; pixels
with at least ``min_shp`` homogeneous neighbours get the coherence matrix over their SHP and linked phases; the
others, and PS (amplitude dispersion ``<= ps_da_max``), keep their SLC. The result is a new variable, the input
``slc`` is not modified::

    slc_linked              (date, y, x) complex64   |slc[k]| · e^{j(arg slc[ref] + θ_k)}, so that
                                                     slc_linked[ref]·conj(slc_linked[k]) has the linked phase
    pl_shp_count            (y, x)       int16       homogeneous neighbours
    pl_temporal_coherence   (y, x)       float32     fit of the linked phases (NaN where not linked)

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
    batch: int = 4096

    @classmethod
    def from_section(cls, sec) -> PhaseLinkingParams:
        """From the project ``[phase_linking]`` section."""
        return cls(estimator=sec.estimator, half_window=tuple(sec.half_window), shp_test=sec.shp_test,
                   shp_alpha=sec.shp_alpha,
                   min_shp=sec.min_shp, ps_da_max=sec.ps_da_max,
                   adaptive_coherence_threshold=sec.adaptive_coherence_threshold, tile_size=sec.tile_size,
                   gaussian_sigma=sec.gaussian_sigma, gaussian_scope=sec.gaussian_scope)


def link_tile(slc: np.ndarray, interior: tuple[slice, slice], ref: int, p: PhaseLinkingParams):
    """Phase-link the ``interior`` of a padded tile ``slc`` (n, H, W) (zeros outside the image).

    Returns (linked SLC (n, h, w), SHP count (h, w), temporal coherence (h, w)).
    """
    amp = np.abs(slc)
    mask = shp_mask(amp, p.half_window, p.shp_alpha, p.shp_test)[interior]
    count = mask.sum(-1) - 1
    out = slc[(slice(None), *interior)].copy()
    tcoh = np.full(count.shape, np.nan, np.float32)
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
        v = estimators.link(C, p.estimator, ref, p.adaptive_coherence_threshold)
        tcoh[r, c] = estimators.temporal_coherence(C, v)
        s = out[:, r, c]                                                                  # (n, B)
        out[:, r, c] = (np.abs(s) * np.exp(1j * (np.angle(s[ref]) + np.angle(v.T)))).astype(np.complex64)
    return out, count.astype(np.int16), tcoh


DONE_ATTR = "phase_linking_done"     # stack attribute: parameters of the last completed run


def fingerprint(params: PhaseLinkingParams) -> dict:
    """The parameters that change the result (JSON form, as stored in the stack attributes)."""
    return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(params).items()
            if k not in ("tile_size", "batch")}


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
    ref = [str(np.datetime64(d, "D")) for d in ds["date"].values].index(str(ds.attrs["reference_date"]))
    _, ny, nx = ds["slc"].shape
    hy, hx = params.half_window
    ts = params.tile_size
    tiles = [(y, x) for y in range(0, ny, ts) for x in range(0, nx, ts)]
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
        return t, link_tile(block, (slice(hy, hy + h), slice(hx, hx + w)), ref, params)

    n_linked = 0
    with ThreadPoolExecutor(workers or min(8, os.cpu_count() or 1)) as pool:
        for i, ((y, x), (out, count, tcoh)) in enumerate(pool.map(work, tiles)):
            h, w = count.shape
            region = {"y": slice(y, y + h), "x": slice(x, x + w)}
            store.write_region(out_var, out, region)
            store.write_region("pl_shp_count", count, region)
            store.write_region("pl_temporal_coherence", tcoh, region)
            n_linked += int(np.isfinite(tcoh).sum())
            event(log, "progress", "phase linking", stage="phase_linking", done=i + 1, total=len(tiles))
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
