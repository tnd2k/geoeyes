"""Automatic ramp selection, ``scla_deramp = "auto"`` (docs/en/research/ramp-selection.md, rule of §5.1).

Pure functions, no I/O. The ramp of every interferogram is a plane; its coefficient series over time is split into
a **trend** (a straight line in t) and a **rest**:

- the rest is always removed (it changes from one acquisition to the next, so it is not steady deformation);
  seasonal safeguard: when the series covers >= 1 year, const + trend + annual sin + cos are fitted jointly to each
  gradient series and the annual pair is F-tested against const + trend (Bonferroni over the 2 gradients); a
  significant annual part is kept (frame-wide seasonal deformation) with a warning. With fewer than
  ``seasonal_min_epochs`` epochs the test cannot run and the annual part is kept untested (conservative);
- the trend: the halves test (velocity, rest removed, per cell; stable cells = |residual of a robust plane| <
  max(5 mm/yr, 2 x PS scatter within a cell); each half W, E, S, N re-selecting its own stable cells must give the
  same gradient) only shows that the trend is *planar*. A bowl wider than the frame fails it, but a planar
  deformation field (interseismic gradient, plate motion, regional tilt) passes it too. The trend is therefore
  removed only with an independent constraint: the user's stable area (``deramp_non_defo``, plane fitted on its
  cells) or the explicit override ``allow_planar`` (``[ps] ramp_auto_allow_planar``). Otherwise it is kept.

The plane of each interferogram is fitted robustly (``robust_epoch_planes``) so that patches unwrapped one cycle
off do not leak into it, and the engine removes the ramp after the unwrapping only (it is not taken out of the
wrapped phase before pass 2): both because a ramp fed back into the unwrapping flipped the cycle of weakly
connected areas (ramp-selection.md §5.3, ring pattern).

Units: coordinates in km, displacement in mm, velocity in mm/yr, gradients in mm/km (reported per 10 km).
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)
RAMP_AUTO_VERSION = 3                # part of the step-6 checkpoint key: bump when the rule changes
PLANAR_KEPT = "planar trend kept: no independent constraint (GNSS / stable area)"


@dataclass(frozen=True)
class RampAutoParams:
    cell_m: float = 500.0             # cell size of the stable-background test
    min_ps_cell: int = 5              # PS per cell
    min_thr: float = 5.0              # mm/yr, floor of the stable threshold
    noise_factor: float = 2.0         # threshold = max(min_thr, noise_factor x PS scatter within a cell)
    min_half_cells: int = 30          # stable cells per half
    abs_tol: float = 5.0              # mm/yr per 10 km, frame-consistency tolerance ...
    rel_tol: float = 0.30             # ... or this share of the full-frame gradient, whichever is larger
    min_quadrants: int = 3
    min_span: float = 0.60            # stable cells along the gradient / frame extent
    min_frame_km: float = 5.0         # smaller frames keep the trend
    allow_planar: bool = False        # remove a trend that passes the halves test without a stable area
    seasonal_min_years: float = 1.0
    seasonal_min_epochs: int = 12     # fewer: the seasonal F-test cannot run, the annual part is kept untested
    seasonal_alpha: float = 0.01      # family-wise over the 2 gradients (Bonferroni: alpha / 2 each)
    n_sub: int = 400_000              # PS used for the plane per interferogram
    seed: int = 0
    robust_planes: bool = True        # per-ifg plane on cell medians, deformation line out, MAD rejection (v3)


@dataclass
class FrameTest:
    plane: np.ndarray                 # (3,) c, gx, gy of the velocity on the stable cells (mm/yr, mm/yr per km)
    stable: np.ndarray                # (n_cells,) bool
    threshold: float                  # mm/yr
    noise: float                      # PS scatter within a cell, mm/yr
    halves: dict[str, np.ndarray | None]   # gradient (2,) per half in mm/yr per km; None = too few stable cells
    max_dev: float                    # mm/yr per km
    tol: float                        # mm/yr per km
    consistent: bool
    quadrants: int
    span: float
    cells: np.ndarray | None = None   # (n_cells, 3) x, y (km, frame centre) and median velocity, for the figure


@dataclass
class RampAuto:
    ph_ramp: np.ndarray               # (n, n_ifg) removed ramp, same unit as the input phase
    coef: np.ndarray                  # (n_ifg, 3) plane per interferogram: c (mm), gx, gy (mm/km)
    trend: np.ndarray                 # (3,) slope of the coefficients in time (per yr)
    rest: np.ndarray                  # (n_ifg, 3) coefficients minus the trend line slope x t (removed part)
    seasonal: np.ndarray | None       # (2,) F-test p-value of the annual pair per gradient (None = not tested)
    seasonal_kept: bool
    trend_removed: bool
    trend_plane: np.ndarray           # (3,) removed velocity plane (zeros when kept)
    reason: str
    frame: FrameTest | None
    warnings: list[str] = field(default_factory=list)
    t: np.ndarray | None = None       # (n_ifg,) years from the master
    frame_passed: bool = False        # the halves test found one plane over the frame (planar, not proof)
    seasonal_note: str = ""           # how the seasonal safeguard ran

    def record(self) -> RampAuto:
        """The decision without the (n, n_ifg) ramp, what a checkpoint and the QC keep."""
        return dataclasses.replace(self, ph_ramp=np.zeros((0, 0), np.float32))

    def summary(self) -> dict:
        """JSON-ready record for params.json / the run manifest."""
        f = self.frame
        out = {"trend_removed": self.trend_removed, "reason": self.reason, "seasonal_kept": self.seasonal_kept,
               "trend_mm_yr_per_10km": [round(10 * float(v), 2) for v in self.trend[1:]],
               "removed_plane_mm_yr_per_10km": [round(10 * float(v), 2) for v in self.trend_plane[1:]],
               "rest_std_mm_per_10km": [round(10 * float(v), 2) for v in np.nanstd(self.rest[:, 1:], axis=0)],
               "seasonal_p": None if self.seasonal is None else [float(f"{float(v):.3g}") for v in self.seasonal],
               "seasonal_note": self.seasonal_note, "frame_test_passed": self.frame_passed,
               "warnings": list(self.warnings)}
        if f is not None:
            out["frame_test"] = {
                "threshold_mm_yr": round(f.threshold, 2), "noise_mm_yr": round(f.noise, 2),
                "stable_cells": int(f.stable.sum()), "cells": int(f.stable.size),
                "halves_mm_yr_per_10km": {h: None if g is None else [round(10 * float(v), 2) for v in g]
                                          for h, g in f.halves.items()},
                "max_dev_per_10km": round(10 * f.max_dev, 2) if np.isfinite(f.max_dev) else None,
                "tol_per_10km": round(10 * f.tol, 2), "consistent": f.consistent,
                "quadrants": f.quadrants, "span": round(f.span, 3)}
        return out


def fit_planes(x: np.ndarray, y: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Least-squares plane c + gx·x + gy·y per column of ``d`` (n, n_ifg); NaN rows skipped per column."""
    a = np.column_stack([np.ones_like(x), x, y])
    finite = np.isfinite(d)
    if finite.all():
        return np.linalg.lstsq(a, d, rcond=None)[0].T
    coef = np.full((d.shape[1], 3), np.nan)
    for k in range(d.shape[1]):
        ok = finite[:, k]
        if ok.sum() > 3:
            coef[k] = np.linalg.lstsq(a[ok], d[ok, k], rcond=None)[0]
    return coef


def robust_epoch_planes(x: np.ndarray, y: np.ndarray, d: np.ndarray, t: np.ndarray, w: np.ndarray,
                        cell_km: float, min_ps: int, min_cells: int = 30) -> np.ndarray | None:
    """Plane per interferogram that unwrapping errors do not tilt.

    ``d`` (n, m) mm, finite. Per square cell (>= ``min_ps`` PS) the median series; each cell's weighted line in
    ``t`` (its deformation) is taken out and the plane of what is left is fitted per interferogram with MAD
    rejection (``robust_plane``): a patch unwrapped one cycle off (lambda/2) in one interferogram stands out of
    that residual and is rejected, while in a plain fit it tilts the plane (ramp-selection.md §5.3). The cells'
    lines go back in as their least-squares planes, so the trend is that of all cells, as before.
    Returns (m, 3) [c, gx, gy], or None with fewer than ``min_cells`` cells (caller falls back to ``fit_planes``)."""
    ix = np.floor((x - x.min()) / cell_km).astype(np.int64)
    iy = np.floor((y - y.min()) / cell_km).astype(np.int64)
    ny = int(iy.max()) + 1
    key = ix * ny + iy
    order = np.argsort(key, kind="stable")
    ks = key[order]
    starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
    ends = np.r_[starts[1:], ks.size]
    good = (ends - starts) >= min_ps
    if good.sum() < min_cells:
        return None
    ds = d[order]
    med = np.array([np.median(ds[a:b], axis=0) for a, b, g in zip(starts, ends, good, strict=True) if g])
    k0 = ks[starts[good]]
    cx = (k0 // ny + 0.5) * cell_km + x.min()
    cy = (k0 % ny + 0.5) * cell_km + y.min()
    g = np.column_stack([np.ones_like(t), t])
    line = np.linalg.solve(g.T @ (w[:, None] * g), g.T @ (w[:, None] * med.T))      # (2, ncell): a, v
    res = med - (g @ line).T
    a = np.column_stack([np.ones_like(cx), cx, cy])
    base = np.linalg.lstsq(a, line.T, rcond=None)[0]                                 # (3, 2): planes of a, v
    rest = np.array([robust_plane(cx, cy, res[:, k]) for k in range(res.shape[1])])
    return base[:, 0][None, :] + np.outer(t, base[:, 1]) + rest


def split_trend(coef: np.ndarray, t: np.ndarray, w: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Weighted straight line in ``t`` (yr) per coefficient series; returns (slope (k,), rest = coef - slope·t)."""
    w = np.ones_like(t) if w is None else np.asarray(w, np.float64)
    g = np.column_stack([t, np.ones_like(t)])
    slope = np.linalg.solve(g.T @ (w[:, None] * g), g.T @ (w[:, None] * coef))[0]
    return slope, coef - np.outer(t, slope)


def seasonal_test(series: np.ndarray, t: np.ndarray, w: np.ndarray | None = None
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Joint weighted fit of const + trend + annual sin + cos per column of ``series`` (m, k), and the F-test of
    the annual pair against const + trend. Returns (p-value (k,), slope of the joint fit (k,), annual part (m, k)).
    Needs m >= 5 (one degree of freedom left)."""
    from scipy.stats import f as f_dist
    t = np.asarray(t, np.float64)
    w = np.ones_like(t) if w is None else np.asarray(w, np.float64)
    sw = np.sqrt(w)[:, None]
    om = 2 * np.pi * t
    a1 = np.column_stack([np.ones_like(t), t, np.sin(om), np.cos(om)])
    a0 = a1[:, :2]

    def fit(a):
        c = np.linalg.lstsq(a * sw, series * sw, rcond=None)[0]
        return c, (w[:, None] * (series - a @ c) ** 2).sum(0)

    _, rss0 = fit(a0)
    c1, rss1 = fit(a1)
    dof = t.size - 4
    with np.errstate(divide="ignore", invalid="ignore"):
        stat = ((rss0 - rss1) / 2) / (rss1 / dof)
    stat = np.where(rss1 > 0, stat, np.where(rss0 > rss1, np.inf, 0.0))
    p = f_dist.sf(np.maximum(stat, 0.0), 2, dof)
    return p, c1[1], a1[:, 2:] @ c1[2:]


def cell_medians(x: np.ndarray, y: np.ndarray, v: np.ndarray, cell_km: float, min_ps: int):
    """Median velocity per square cell with >= ``min_ps`` PS; returns (cx, cy, cv, noise = median within-cell
    scatter 1.4826·MAD)."""
    ix = np.floor((x - x.min()) / cell_km).astype(np.int64)
    iy = np.floor((y - y.min()) / cell_km).astype(np.int64)
    key = ix * (int(iy.max()) + 1) + iy
    order = np.argsort(key, kind="stable")
    ks, vs = key[order], v[order]
    starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
    counts = np.diff(np.r_[starts, ks.size])
    parts = np.split(vs, starts[1:])
    med = np.array([np.median(s) for s in parts])
    spread = np.array([1.4826 * np.median(np.abs(s - m)) for s, m in zip(parts, med, strict=True)])
    good = counts >= min_ps
    if not good.any():
        return np.array([]), np.array([]), np.array([]), float("nan")
    k0 = ks[starts][good]
    ny = int(iy.max()) + 1
    cx = (k0 // ny + 0.5) * cell_km + x.min()
    cy = (k0 % ny + 0.5) * cell_km + y.min()
    return cx, cy, med[good], float(np.median(spread[good]))


def _plane(cx, cy, cv):
    return np.linalg.lstsq(np.column_stack([np.ones_like(cx), cx, cy]), cv, rcond=None)[0]


def robust_plane(cx, cy, cv, rounds: int = 10):
    """Plane refitted on |residual| < 2.5 x 1.4826·MAD, at most ``rounds`` times."""
    keep = np.ones(cv.size, bool)
    coef = _plane(cx, cy, cv)
    for _ in range(rounds):
        r = cv - (coef[0] + coef[1] * cx + coef[2] * cy)
        mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
        new = np.abs(r) < 2.5 * max(mad, 1e-9)
        if np.array_equal(new, keep) or new.sum() < 3:
            break
        keep = new
        coef = _plane(cx[keep], cy[keep], cv[keep])
    return coef


def select_plane(cx, cy, cv, thr: float, rounds: int = 10):
    """Robust plane, then stable = |residual| < ``thr``, the plane refitted on the stable cells until they settle."""
    coef = robust_plane(cx, cy, cv)
    stable = np.abs(cv - (coef[0] + coef[1] * cx + coef[2] * cy)) < thr
    for _ in range(rounds):
        if stable.sum() >= 10:
            coef = _plane(cx[stable], cy[stable], cv[stable])
        new = np.abs(cv - (coef[0] + coef[1] * cx + coef[2] * cy)) < thr
        if np.array_equal(new, stable):
            break
        stable = new
    return coef, stable


def frame_test(cx, cy, cv, noise: float, p: RampAutoParams) -> FrameTest:
    """Stable-cell plane of the whole frame and of each half (W, E, S, N), each half selecting its own cells."""
    thr = max(p.min_thr, p.noise_factor * noise) if np.isfinite(noise) else p.min_thr
    coef, stable = select_plane(cx, cy, cv, thr)
    mx, my = 0.5 * (cx.min() + cx.max()), 0.5 * (cy.min() + cy.max())
    halves: dict[str, np.ndarray | None] = {}
    for h, m in {"W": cx < mx, "E": cx >= mx, "S": cy < my, "N": cy >= my}.items():
        if m.sum() < p.min_half_cells:
            halves[h] = None
            continue
        ch, sh = select_plane(cx[m], cy[m], cv[m], thr)
        halves[h] = ch[1:] if sh.sum() >= p.min_half_cells else None
    g = coef[1:]
    tol = max(p.abs_tol / 10.0, p.rel_tol * float(np.hypot(*g)))
    devs = [float(np.hypot(*(gh - g))) for gh in halves.values() if gh is not None]
    max_dev = max(devs) if devs else float("nan")
    consistent = len(devs) == 4 and max_dev <= tol
    quads = len({(a, b) for a, b in zip(cx[stable] > mx, cy[stable] > my, strict=True)})
    gn = np.hypot(*g)
    gdir = g / gn if gn > 1e-12 else np.array([1.0, 0.0])
    p_all = cx * gdir[0] + cy * gdir[1]
    extent = p_all.max() - p_all.min()
    if stable.sum() >= 2 and extent > 0:
        p_st = p_all[stable]
        span = float((np.percentile(p_st, 98) - np.percentile(p_st, 2)) / extent)
    else:
        span = 0.0
    return FrameTest(plane=coef, stable=stable, threshold=thr, noise=noise, halves=halves, max_dev=max_dev,
                     tol=tol, consistent=consistent, quadrants=quads, span=span,
                     cells=np.column_stack([cx, cy, cv]).astype(np.float32))


def weighted_velocity(d: np.ndarray, t: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted LS slope of each row of ``d`` (n, m) against ``t`` (m,)."""
    tc = t - np.sum(w * t) / np.sum(w)
    return (d * w) @ tc / np.sum(w * tc * tc)


def auto_ramp(x_km: np.ndarray, y_km: np.ndarray, ph: np.ndarray, t: np.ndarray, *, mm_per_unit: float,
              weights: np.ndarray | None = None, params: RampAutoParams | None = None,
              stable_mask: np.ndarray | None = None) -> RampAuto:
    """Ramp to remove under ``scla_deramp = "auto"``.

    ``ph`` (n, n_ifg): phase after the APS (any unit; ``mm_per_unit`` converts it to mm, sign irrelevant), NaN
    allowed. ``t`` (n_ifg,) years from the master; ``weights`` per interferogram as in the velocity fit.
    ``stable_mask`` (n,) the PS of a user's non-deforming area (``deramp_non_defo``): the trend plane is fitted on
    the cells inside it and removed whatever the frame test says (the test is still run and reported).
    Interferograms with fewer than 10 values get a NaN ramp, as ``scla.deramp``.
    Returns the removed ramp in the unit of ``ph`` and the record of the decision.
    """
    p = params or RampAutoParams()
    t_all = np.asarray(t, np.float64)
    w_all = np.ones_like(t_all) if weights is None else np.asarray(weights, np.float64)
    x = np.asarray(x_km, np.float64)
    y = np.asarray(y_km, np.float64)
    x0, y0 = 0.5 * (x.min() + x.max()), 0.5 * (y.min() + y.max())
    x, y = x - x0, y - y0                                                  # centred: c is the ramp at the centre
    warnings: list[str] = []
    fin = np.isfinite(ph)
    cols = fin.sum(0) > 10
    if not cols.all():
        warnings.append(f"{int((~cols).sum())} interferogram(s) without a ramp (too few values)")
    if cols.sum() < 3:
        raise ValueError("ramp auto: fewer than 3 interferograms with values")
    t, w = t_all[cols], w_all[cols]

    # 1. plane per interferogram, on a random subset of the PS
    rows = fin.any(1)
    idx = np.flatnonzero(rows)
    if idx.size > p.n_sub:
        idx = np.sort(np.random.default_rng(p.seed).choice(idx, size=p.n_sub, replace=False))
    d_sub = mm_per_unit * np.asarray(ph[idx][:, cols], np.float64)
    coef = None
    if p.robust_planes:
        full = np.isfinite(d_sub).all(1)
        coef = robust_epoch_planes(x[idx][full], y[idx][full], d_sub[full], t, w, p.cell_m / 1000.0, p.min_ps_cell)
        if coef is None:
            warnings.append("too few cells for the robust per-interferogram plane: plain least squares")
    if coef is None:
        coef = fit_planes(x[idx], y[idx], d_sub)
    del d_sub
    coef = np.nan_to_num(coef)

    # 2. trend + rest; seasonal safeguard on the gradients
    trend, rest = split_trend(coef, t, w)
    span_yr = float(max(t.max(), 0.0) - min(t.min(), 0.0))
    seasonal, seasonal_kept, hit = None, False, np.zeros(2, bool)
    names = np.array(["x", "y"])                     # the coordinate axes given (engine: rotated to the heading)
    if span_yr < p.seasonal_min_years:
        seasonal_note = f"not applicable (series {span_yr:.2f} yr < {p.seasonal_min_years:g} yr)"
    elif t.size < max(p.seasonal_min_epochs, 5):
        # too few epochs for the F-test: a frame-wide seasonal deformation cannot be excluded, so the annual part
        # of the joint fit is kept untested (conservative: less is removed)
        if t.size >= 5:
            _, slope, sinus = seasonal_test(coef[:, 1:], t, w)
            hit[:] = True
            seasonal_note = f"not tested ({t.size} epochs < {p.seasonal_min_epochs}): annual part kept untested"
        else:
            seasonal_note = f"not tested ({t.size} epochs < 5): seasonal deformation cannot be excluded"
        warnings.append(f"seasonal safeguard {seasonal_note}")
    else:
        seasonal, slope, sinus = seasonal_test(coef[:, 1:], t, w)
        hit = seasonal < p.seasonal_alpha / 2                              # Bonferroni over the 2 gradients
        seasonal_note = f"F-test, alpha {p.seasonal_alpha:g} over 2 gradients"
        if hit.any():
            warnings.append(f"seasonal frame-wide ramp kept ({', '.join(names[hit])}: F-test p = "
                            f"{', '.join(f'{s:.2g}' for s in seasonal[hit])})")
    if hit.any():
        seasonal_kept = True
        j = 1 + np.flatnonzero(hit)
        trend[j] = slope[hit]                                              # joint fit: the line cannot absorb
        rest[:, j] = coef[:, j] - np.outer(t, slope[hit]) - sinus[:, hit]  # part of the annual cycle

    def surface(c: np.ndarray) -> np.ndarray:                              # (n, n_ifg) mm
        return c[:, 0] + np.outer(x, c[:, 1]) + np.outer(y, c[:, 2])

    # 3. trend: velocity with the rest removed, per cell, frame test
    ext = (x.max() - x.min(), y.max() - y.min())
    frame = None
    trend_plane = np.zeros(3)
    trend_removed = frame_passed = False
    small = max(ext) < p.min_frame_km
    reason = f"frame < {p.min_frame_km:g} km" if small else ""
    if not small or stable_mask is not None:
        ok = fin[:, cols].all(1)
        d = mm_per_unit * np.asarray(ph[ok][:, cols], np.float64) - (rest[:, 0] + np.outer(x[ok], rest[:, 1])
                                                                     + np.outer(y[ok], rest[:, 2]))
        v = weighted_velocity(d, t, w)
        del d
        cx, cy, cv, noise = cell_medians(x[ok], y[ok], v, p.cell_m / 1000.0, p.min_ps_cell)
        if not small:
            if cv.size < 4 * p.min_half_cells:
                reason = f"too few cells ({cv.size})"
            else:
                frame = frame_test(cx, cy, cv, noise, p)
                bad = [s for s, b in (("plane depends on the frame", not frame.consistent),
                                      (f"< {p.min_quadrants} quadrants", frame.quadrants < p.min_quadrants),
                                      (f"span < {p.min_span:.0%}", frame.span < p.min_span)) if b]
                if bad:
                    reason = "; ".join(bad)
                else:
                    # one plane over the frame shows the trend is planar, not that it is a nuisance: a planar
                    # deformation field (interseismic, plate motion, regional tilt) passes as well
                    frame_passed = True
                    if p.allow_planar:
                        reason = "stable background spans the frame (planar trend removed: allow_planar)"
                        trend_removed = True
                        trend_plane = frame.plane.copy()
                    else:
                        reason = PLANAR_KEPT
        if stable_mask is not None:
            inside = cell_medians(x[ok], y[ok], np.asarray(stable_mask, np.float64)[ok], p.cell_m / 1000.0,
                                  p.min_ps_cell)[2] > 0.5
            if inside.sum() >= 10:
                if not trend_removed and not frame_passed:
                    warnings.append(f"trend removed on the user's non-deforming area although the frame test "
                                    f"fails ({reason})")
                reason = f"user area deramp_non_defo ({int(inside.sum())} cells)"
                trend_removed = True
                trend_plane = _plane(cx[inside], cy[inside], cv[inside])
            else:
                warnings.append(f"deramp_non_defo holds {int(inside.sum())} cells (< 10): not used")
        trend_plane[0] = 0.0                                               # a uniform rate is the reference's job
    removed = rest + (np.outer(t, trend_plane) if trend_removed else 0.0)
    ph_ramp = np.full(ph.shape, np.nan, np.float64)
    ph_ramp[:, cols] = surface(removed) / mm_per_unit
    ph_ramp[~rows] = np.nan
    ph_ramp = ph_ramp.astype(ph.dtype, copy=False)
    coef_all = np.full((t_all.size, 3), np.nan)
    rest_all = np.full((t_all.size, 3), np.nan)
    coef_all[cols], rest_all[cols] = coef, rest
    coef, rest = coef_all, rest_all
    log.info("ramp auto: rest removed; trend %s (%s)", "removed" if trend_removed else "kept", reason)
    for msg in warnings:
        log.warning("ramp auto: %s", msg)
    return RampAuto(ph_ramp=ph_ramp, coef=coef, trend=trend, rest=rest, seasonal=seasonal,
                    seasonal_kept=seasonal_kept, trend_removed=trend_removed, trend_plane=trend_plane,
                    reason=reason, frame=frame, warnings=warnings, t=t_all, frame_passed=frame_passed,
                    seasonal_note=seasonal_note)


def ramp_figure(r: RampAuto, ifg_dates, path, title: str = ""):
    """QC figure ``figures/ramp.png``: x / y gradient per interferogram (total, trend, removed) and the
    stable-cell map of the frame test. x / y: the axes given to ``auto_ramp`` (the engine's local frame is rotated
    to the radar heading, so they are not east / north; the halves W/E/S/N are the halves along x and y)."""
    from pathlib import Path

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), dpi=120)
    g = 10 * r.coef[:, 1:]
    removed = 10 * (r.rest[:, 1:] + (np.outer(r.t, r.trend_plane[1:]) if r.trend_removed else 0.0))
    for j, (name, c) in enumerate((("x", "tab:blue"), ("y", "tab:orange"))):
        ax[0].plot(ifg_dates, g[:, j], "o-", color=c, ms=3, label=f"{name} total")
        ax[0].plot(ifg_dates, 10 * r.trend[j + 1] * r.t, "--", color=c, label=f"{name} trend (all PS)")
        ax[0].plot(ifg_dates, removed[:, j], ":", color=c, label=f"{name} removed")
    ax[0].axhline(0, color="0.6", lw=0.5)
    ax[0].set_ylabel("ramp gradient (mm per 10 km)")
    ax[0].legend(fontsize=7)
    ax[0].tick_params(axis="x", rotation=60, labelsize=7)
    f = r.frame
    if f is not None and f.cells is not None:
        cx, cy, cv = f.cells.T
        lim = float(np.percentile(np.abs(cv), 99)) or 1.0
        sc = ax[1].scatter(cx[~f.stable], cy[~f.stable], c=cv[~f.stable], s=3, cmap="RdBu", vmin=-lim, vmax=lim)
        ax[1].scatter(cx[f.stable], cy[f.stable], s=1, c="k", alpha=0.5, label="stable cells")
        fig.colorbar(sc, ax=ax[1], fraction=0.04, pad=0.02, label="velocity, rest removed (mm/yr)")
        ax[1].set_aspect(1)
        ax[1].set_xlabel("x (km from the frame centre)")
        ax[1].set_ylabel("y (km)")
        ax[1].legend(fontsize=7, loc="lower right")
        halves = ", ".join(f"{h} {'-' if q is None else f'{10 * q[0]:+.0f}/{10 * q[1]:+.0f}'}"
                           for h, q in f.halves.items())
        ax[1].set_title(f"halves along x / y, gradient x/y per 10 km: {halves}", fontsize=8)
    else:
        ax[1].axis("off")
    fig.suptitle(f"{title} ramp: rest removed; trend {'removed' if r.trend_removed else 'kept'} ({r.reason})",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
