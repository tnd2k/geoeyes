"""Rainfall coupling of InSAR time series (docs/en/research/rainfall-insar-hazard.md §4.3).

Model, per cell (median series of its points, in the motion direction of the cell):

    d(t) = a + b·t + k·CRD(t − τ) + ε

``CRD`` is the cumulative rainfall departure of the cell's CHIRPS pixel, Σ (P_month − P̄), linear within a month.
If the rate of motion follows the rainfall anomaly with a delay τ, v(t) − b = k·(P(t − τ) − P̄), its integral is the
model above: the same form serves groundwater-driven seasonal subsidence / heave (heads follow the CRD) and slow
landslides (velocity follows antecedent rainfall). ``b`` is the rain-corrected trend (mm/yr), ``k`` the rainfall
sensitivity (mm of displacement per mm of rainfall departure), τ the lag (months, 0..max_lag, chosen by the largest
partial correlation of d and CRD once the trend is removed).

Significance: the lag search is repeated on phase-randomised surrogates of the monthly rainfall anomaly (same
power spectrum, random timing; Ebisuzaki 1997), so the test includes the choice of the lag and the serial
correlation of the rainfall; ``p`` = share of surrogates whose best |r| reaches the observed one (with a fitted
tail when fewer than ``TAIL_BELOW`` do).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DAYS_PER_MONTH = 365.2425 / 12
DAYS_PER_YEAR = 365.2425
TAIL_BELOW = 10                  # surrogates reaching the observed |r|: below, the p-value comes from the tail fit


@dataclass
class Crd:
    """Cumulative rainfall departure of one rainfall pixel: values at month boundaries (days since ``t0``)."""

    t_days: np.ndarray           # M + 1 boundaries
    values: np.ndarray           # mm, 0 at the first boundary
    mean_month_mm: float         # P̄
    missing: float               # share of months without data (filled with P̄)

    def at(self, t_days: np.ndarray) -> np.ndarray:
        return np.interp(t_days, self.t_days, self.values)


def month_bounds(months: list[str], t0: np.datetime64) -> np.ndarray:
    """Days since ``t0`` of the start of each month and the end of the last one (M + 1 values)."""
    starts = np.array([np.datetime64(f"{m}-01") for m in months], dtype="datetime64[D]")
    end = (np.datetime64(months[-1], "M") + 1).astype("datetime64[D]")
    return np.append((starts - t0).astype(np.float64), float((end - t0).astype(np.float64)))


def crd(monthly_mm: np.ndarray, bounds: np.ndarray) -> Crd:
    """CRD of one pixel: ``monthly_mm[M]`` (NaN = missing month, counted as P̄)."""
    p = np.asarray(monthly_mm, np.float64)
    ok = np.isfinite(p)
    mean = float(p[ok].mean()) if ok.any() else 0.0
    dep = np.where(ok, p - mean, 0.0)
    return Crd(bounds, np.concatenate([[0.0], np.cumsum(dep)]), mean, float(1 - ok.mean()) if p.size else 1.0)


def storage(monthly_mm: np.ndarray, months: list[str], t0: np.datetime64) -> tuple[Crd, np.ndarray]:
    """A storage series (groundwater, mm of water: already a cumulative quantity, the counterpart of the CRD) as
    a ``Crd`` at mid-month, with its month-to-month changes for the surrogates. Missing months are left out
    (``missing`` = their share); the anomaly is relative to the first month (the [1, t] basis removes the rest)."""
    s = np.asarray(monthly_mm, np.float64)
    ok = np.isfinite(s)
    mid = np.array([np.datetime64(f"{m}-15") for m in months], dtype="datetime64[D]")
    t = (mid - t0).astype(np.float64)[ok]
    v = s[ok] - s[ok][0] if ok.any() else np.zeros(0)
    return Crd(t, v, float(s[ok].mean()) if ok.any() else 0.0, float(1 - ok.mean()) if s.size else 1.0), np.diff(v)


def surrogates(anomaly: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """``n`` phase-randomised copies of a series (Ebisuzaki 1997): same amplitude spectrum and mean, random
    phases. Returns (n, M)."""
    a = np.asarray(anomaly, np.float64)
    m = a.size
    f = np.fft.rfft(a)
    ph = rng.uniform(0, 2 * np.pi, (n, f.size))
    if m % 2 == 0:                                   # the Nyquist term of an even length stays real: 0 or π
        ph[:, -1] = rng.choice([0.0, np.pi], n)
    g = np.abs(f)[None, :] * np.exp(1j * ph)
    g[:, 0] = f[0]                                   # the mean is kept
    return np.fft.irfft(g, n=m, axis=1)


def _basis(t_yr: np.ndarray) -> np.ndarray:
    """Orthonormal basis of [1, t] (T, 2)."""
    q, _ = np.linalg.qr(np.column_stack([np.ones_like(t_yr), t_yr]))
    return q


def _resid(x: np.ndarray, q: np.ndarray) -> np.ndarray:
    """``x`` (..., T) minus its projection on span(q)."""
    return x - (x @ q) @ q.T


@dataclass
class Coupling:
    """Per-cell results (arrays of the cells given)."""

    lag_months: np.ndarray       # τ (int, -1 = not assessed)
    r: np.ndarray                # partial correlation of d and CRD(t − τ) given [1, t]
    k: np.ndarray                # mm per mm of rainfall departure
    k_se: np.ndarray
    trend: np.ndarray            # b of the joint fit, mm/yr
    p: np.ndarray                # surrogate p-value of max |r| over the lags
    rmse: np.ndarray             # residual of the joint fit, mm


def couple(y: np.ndarray, t_days: np.ndarray, rain: Crd, anomaly_months: np.ndarray, max_lag: int = 6,
           n_surrogates: int = 500, seed: int = 0) -> Coupling:
    """Coupling of the series ``y`` (cells, T) observed at ``t_days`` (days since the CRD origin) with one rainfall
    pixel. ``anomaly_months`` = P − P̄ per month (missing = 0), for the surrogates. Cells with a NaN are skipped."""
    y = np.asarray(y, np.float64)
    nc, nt = y.shape
    t_yr = t_days / DAYS_PER_YEAR
    q = _basis(t_yr)
    ok = np.all(np.isfinite(y), axis=1)
    ey = _resid(np.where(ok[:, None], y, 0.0), q)
    ny = np.linalg.norm(ey, axis=1)
    ny[ny == 0] = np.inf
    lags = np.arange(max_lag + 1)

    def best(crd_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(max |r| over the lags, index of the lag) for every cell, CRD given at the month bounds."""
        cs = np.stack([np.interp(t_days - lag * DAYS_PER_MONTH, rain.t_days, crd_values) for lag in lags])
        ec = _resid(cs, q)
        nc_ = np.linalg.norm(ec, axis=1)
        nc_[nc_ == 0] = np.inf
        r = (ey @ ec.T) / ny[:, None] / nc_[None, :]                          # (cells, lags)
        i = np.argmax(np.abs(r), axis=1)
        return r[np.arange(nc), i], i

    r, li = best(rain.values)
    # surrogate rainfall: same spectrum, random timing -> null distribution of the best |r|
    rng = np.random.default_rng(seed)
    p = np.ones(nc)
    if n_surrogates:
        null = np.stack([np.abs(best(np.concatenate([[0.0], np.cumsum(s)]))[0])
                         for s in surrogates(anomaly_months, n_surrogates, rng)])            # (S, cells)
        exceed = (null >= np.abs(r)[None, :] - 1e-12).sum(axis=0)
        p = (1 + exceed) / (1 + n_surrogates)
        # few exceedances: the empirical p is bounded by 1 / (S + 1); its tail is approximated by a normal fit of
        # the Fisher z of the null (Knijnenburg et al. 2009), so that a map-wide FDR can still reach small areas
        rare = exceed < TAIL_BELOW
        if rare.any():
            from scipy.stats import norm
            z = np.arctanh(np.clip(null[:, rare], 0, 1 - 1e-9))
            sd = z.std(axis=0, ddof=1)
            sd[sd == 0] = np.inf
            tail = norm.sf((np.arctanh(np.clip(np.abs(r[rare]), 0, 1 - 1e-9)) - z.mean(axis=0)) / sd)
            p[rare] = np.minimum(p[rare], np.maximum(tail, 1e-12))

    # joint least squares at the chosen lag: [1, t, CRD(t − τ)]
    k = np.full(nc, np.nan)
    k_se = np.full(nc, np.nan)
    trend = np.full(nc, np.nan)
    rmse = np.full(nc, np.nan)
    for lag in np.unique(li[ok]):
        sel = ok & (li == lag)
        c = rain.at(t_days - lag * DAYS_PER_MONTH)
        x = np.column_stack([np.ones(nt), t_yr, c])
        coef, *_ = np.linalg.lstsq(x, y[sel].T, rcond=None)
        res = y[sel] - (x @ coef).T
        dof = max(nt - 3, 1)
        s2 = (res ** 2).sum(axis=1) / dof
        cov = np.linalg.pinv(x.T @ x)
        k[sel], trend[sel] = coef[2], coef[1]
        k_se[sel] = np.sqrt(s2 * cov[2, 2])
        rmse[sel] = np.sqrt((res ** 2).mean(axis=1))
    lag_out = np.where(ok, lags[li], -1)
    return Coupling(lag_out, np.where(ok, r, np.nan), k, k_se, trend, np.where(ok, p, np.nan), rmse)


def fdr_bh(p: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values (q) of the finite entries (valid under the positive dependence of
    neighbouring cells, Benjamini & Yekutieli 2001); NaN stays NaN."""
    p = np.asarray(p, np.float64)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if not m:
        return q
    order = np.argsort(p[ok])
    ranked = p[ok][order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    q[ok] = out
    return q


def linear_fit(y: np.ndarray, t_days: np.ndarray, quadratic: bool = False) -> dict[str, np.ndarray]:
    """Per row of ``y`` (cells, T): velocity (mm/yr) and its standard error, and with ``quadratic`` the
    acceleration (mm/yr²) and its standard error (ordinary least squares, NaN rows skipped)."""
    y = np.asarray(y, np.float64)
    t = t_days / DAYS_PER_YEAR
    t = t - t.mean()
    cols = [np.ones_like(t), t] + ([0.5 * t ** 2] if quadratic else [])
    x = np.column_stack(cols)
    ok = np.all(np.isfinite(y), axis=1)
    out = {k: np.full(len(y), np.nan) for k in ("vel", "vel_se", "acc", "acc_se")}
    if not ok.any() or len(t) <= x.shape[1]:
        return out
    coef, *_ = np.linalg.lstsq(x, y[ok].T, rcond=None)
    res = y[ok] - (x @ coef).T
    s2 = (res ** 2).sum(axis=1) / (len(t) - x.shape[1])
    cov = np.linalg.pinv(x.T @ x)
    out["vel"][ok], out["vel_se"][ok] = coef[1], np.sqrt(s2 * cov[1, 1])
    if quadratic:
        out["acc"][ok], out["acc_se"][ok] = coef[2], np.sqrt(s2 * cov[2, 2])
    return out
