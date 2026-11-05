"""Multilooked interferograms of the SBAS pairs (S2) and their unwrapping (S3), the chain of ``learn.pair``:

    multilook (looks_az × looks_rg) of s_i·conj(s_j), |s_i|², |s_j|²   (the stack SLCs are flattened: the product is the
                                                                       differential interferogram)
    coherence  |boxcar(ifg)| / sqrt(boxcar(p_i)·boxcar(p_j))
    Goldstein  on unit phasors, pixels below ``min_pair_coherence`` left out
    unwrapping refined IRLS weighted by coherence² (``processing.ps.unwrap.irls``) on the filtered phase; the cycles
               found are put on the unfiltered phase (the filter guides the unwrapping, it does not flatten the
               signal)

The phase of a pair (i, j), i earlier, is arg(s_i·conj(s_j)): a range increase from i to j adds +4πΔr/λ (stack
``phase_convention``), so a displacement toward the satellite is −φλ/4π.
"""
from __future__ import annotations

import numpy as np

from geoeyes.learn.pair import boxcar, multilook


def strips(ny: int, la: int, rows: int = 1024) -> list[slice]:
    """Row slices of whole look blocks."""
    step = max(la, (rows // la) * la)
    usable = (ny // la) * la
    return [slice(y, min(y + step, usable)) for y in range(0, usable, step)]


def ml_layers(store, names: tuple[str, ...], la: int, lr: int) -> dict[str, np.ndarray]:
    """Block means of (y, x) stack layers (e.g. ``geometry_lat``) on the multilooked grid."""
    ds = store.open()
    ny = ds.sizes["y"]
    out = {}
    for n in names:
        if n in ds:
            out[n] = np.vstack([multilook(ds[n].isel(y=s).values.astype(np.float64), la, lr)
                                for s in strips(ny, la)])
    return out


def interferogram(store, var: str, i: int, j: int, la: int, lr: int, win: int) -> tuple[np.ndarray, np.ndarray]:
    """Multilooked interferogram (complex) and coherence of dates ``i`` and ``j`` of ``var``."""
    ds = store.open()
    ny = ds.sizes["y"]
    ifg, p1, p2 = [], [], []
    for s in strips(ny, la):
        a = ds[var].isel(date=i, y=s).values
        b = ds[var].isel(date=j, y=s).values
        ifg.append(multilook(a * np.conj(b), la, lr))
        p1.append(multilook(np.abs(a) ** 2, la, lr))
        p2.append(multilook(np.abs(b) ** 2, la, lr))
    ifg, p1, p2 = np.vstack(ifg), np.vstack(p1), np.vstack(p2)
    with np.errstate(invalid="ignore", divide="ignore"):
        coh = np.abs(boxcar(ifg, win)) / np.sqrt(boxcar(p1, win) * boxcar(p2, win))
    return ifg, np.clip(np.nan_to_num(coh), 0, 1).astype(np.float32)


def unwrap(ifg: np.ndarray, coh: np.ndarray, min_coherence: float, alpha: float, fft: int,
           irls_iter: int, link_islands: bool = True) -> np.ndarray:
    """Unwrapped phase (float32), NaN where the coherence is below ``min_coherence``; with ``link_islands``, the
    disconnected islands are tied by integer cycles (``processing.unwrap.components``, as the point engines do)."""
    from geoeyes.processing.ps.unwrap.irls import enforce_congruence, irls_unwrap_weighted
    from geoeyes.processing.unwrap.goldstein import goldstein
    keep = (coh >= min_coherence) & np.isfinite(ifg) & (np.abs(ifg) > 0)
    if keep.sum() < 16:
        return np.full(ifg.shape, np.nan, np.float32)
    unit = np.where(keep, ifg / np.where(keep, np.abs(ifg), 1), 0)
    filt = np.angle(goldstein(unit, min(fft, min(ifg.shape)), alpha)) if alpha > 0 else np.angle(unit)
    filt = np.where(keep, filt, np.nan).astype(np.float32)
    unw, _ = irls_unwrap_weighted(filt, (coh ** 2).astype(np.float32), max_iter=irls_iter)
    # the filtered phase only guides the unwrapping: the cycles are put on the unfiltered phase, which the Goldstein
    # filter would otherwise flatten (−5 % of a subsidence bowl's depth at alpha 0.3 on the synthetic test)
    raw = np.where(keep, np.angle(ifg), np.nan).astype(np.float32)
    unw = enforce_congruence(raw, unw, align=True)
    unw = np.where(keep, unw, np.nan).astype(np.float32)
    if link_islands:
        # across the gaps of a forest scene the IRLS surface has no support: each island may sit an integer number
        # of cycles off its neighbours (the uniform patches of the first real run)
        from geoeyes.processing.unwrap.components import link_components
        unw = link_components(unw).astype(np.float32)
    return unw
