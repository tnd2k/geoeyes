"""D0 of ramp-selection.md: what would ``scla_deramp = "auto"`` decide on an existing PS state?

Usage:  python ramp_auto.py <ps_runs/<stack>/state.h5> [<out dir for the figure>] [--gnss]

No engine change: everything is recomputed from the state (pass-2 unwrapped phase; the engine fits the ramp on the
pass-1 phase, close enough for a study). Sentinel-1 only (wavelength fixed below).

1. Ramp per interferogram: weighted LS plane of the phase after the APS (mm, km), on a random subset of PS; the
   gain of a quadratic over the plane is reported (the engine's degree rule).
2. Split of the gradient series (E-W, N-S) over time, weights 1/ifg_std^2 as the velocity fit:
   trend = beta * t; rest = everything else (the intercept is the master's own ramp, so it is "rest").
   Seasonal check when the series covers >= 1 year: share of the rest's variance explained by an annual sinusoid.
3. Stable-background test on the velocity of (unwrapped - APS - SCLA), rest of the ramp removed, median per 500 m
   cell (>= 5 PS): robust plane (trim at 2.5 * 1.4826 * MAD, <= 10 rounds); stable = cells with
   |residual| < max(5 mm/yr, 2 * PS scatter within a cell); revised rule (§5.1): each half W/E/S/N re-selects its
   own stable cells and must give the same gradient, >= 3 of 4 quadrants, span along the gradient >= 60%.
4. Decision and, with --gnss (mexico_g3 only), the leave-one-out at ICMX / MMX1 / MXTX for: trend kept (n),
   stable-cell plane removed (auto if it passes), all-cell plane removed (like y).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import h5py
import numpy as np

WAVELENGTH_MM = 55.465763          # Sentinel-1 C-band
CELL_M = 500.0
MIN_PS_CELL = 5
N_SUB = 400_000
THRESHOLD = "noise"                # "noise": max(5, 2 x PS scatter within a cell) | a number in mm/yr (--thr=10)
BBOX = None                        # --bbox=w,s,e,n: only the PS inside (frame-dependence test)
STATIONS = {"ICMX": (-99.1709, 19.4056), "MMX1": (-99.0684, 19.4317), "MXTX": (-98.8763, 19.5396)}
GNSS = {"window": {"ICMX": -52.05, "MMX1": -258.23, "MXTX": -32.26},
        "midas": {"ICMX": -18.39, "MMX1": -187.61, "MXTX": -9.49}}


def wfit(t: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted LS of y (m,) or (m, k) on [t, 1]; returns the coefficients (2,) or (2, k)."""
    g = np.column_stack([t, np.ones_like(t)])
    return np.linalg.solve(g.T @ (w[:, None] * g), g.T @ (w[:, None] * y if y.ndim > 1 else w * y))


def robust_plane(x, y, v, rounds=10):
    keep = np.ones(v.size, bool)
    a = np.column_stack([np.ones_like(x), x, y])
    for _ in range(rounds):
        coef = np.linalg.lstsq(a[keep], v[keep], rcond=None)[0]
        r = v - a @ coef
        mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
        new = np.abs(r) < 2.5 * max(mad, 1e-6)
        if np.array_equal(new, keep):
            break
        keep = new
    return coef, r, keep


def select_plane(cx, cy, cv, thr):
    """Robust plane, then stable = |residual| < thr, the plane refitted on the stable cells until they settle."""
    coef, r, keep = robust_plane(cx, cy, cv)
    sig = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
    stable = np.abs(r) < thr
    for _ in range(10):
        if stable.sum() >= 10:
            coef = np.linalg.lstsq(np.column_stack([np.ones(stable.sum()), cx[stable], cy[stable]]), cv[stable],
                                   rcond=None)[0]
        new = np.abs(cv - (coef[0] + coef[1] * cx + coef[2] * cy)) < thr
        if np.array_equal(new, stable):
            break
        stable = new
    return coef, stable, sig


def main(state: str, out: str | None, gnss: bool) -> None:
    with h5py.File(state, "r") as f:
        lon, lat = f["ps/lon"][:], f["ps/lat"][:]
        ifg = [date.fromisoformat(d.decode()) for d in f["time/ifg_dates"][:]]
        epochs = [date.fromisoformat(d.decode()) for d in f["time/epoch_dates"][:]]
        std = f["time/ifg_std_deg"][:].astype(np.float64)
        uw, aps, scla = f["phase/unwrapped"][:], f["phase/aps"][:], f["phase/scla"][:]
    master = (set(epochs) - set(ifg)).pop()
    m_ix = epochs.index(master)
    t = np.array([(d - master).days for d in ifg], np.float64) / 365.25
    w = 1.0 / np.maximum(np.delete(std, m_ix) * np.pi / 180.0, 1e-6) ** 2
    span_yr = (max(epochs) - min(epochs)).days / 365.25
    lam = -WAVELENGTH_MM / (4 * np.pi)                                    # mm per rad, + toward the satellite
    ok = np.isfinite(uw).all(1) & np.isfinite(aps).all(1) & np.isfinite(scla).all(1)
    if BBOX is not None:                                                  # sub-frame of the same state
        ok &= (lon >= BBOX[0]) & (lat >= BBOX[1]) & (lon <= BBOX[2]) & (lat <= BBOX[3])
    lon0, lat0 = 0.5 * (lon[ok].min() + lon[ok].max()), 0.5 * (lat[ok].min() + lat[ok].max())
    kx = 111.32 * np.cos(np.radians(lat0))
    x, y = (lon - lon0) * kx, (lat - lat0) * 111.32                       # km
    ext = (x[ok].max() - x[ok].min(), y[ok].max() - y[ok].min())
    print(f"{Path(state).parents[2].name}: {ok.sum():,} PS, {len(epochs)} epochs {min(epochs)} .. {max(epochs)} "
          f"({span_yr:.2f} yr), master {master}, frame {ext[0]:.1f} x {ext[1]:.1f} km")

    # 1. ramp per interferogram
    rng = np.random.default_rng(0)
    sub = rng.choice(np.flatnonzero(ok), size=min(N_SUB, int(ok.sum())), replace=False)
    d = lam * (uw[sub] - aps[sub]).astype(np.float64)                     # (n_sub, n_ifg) mm
    a1 = np.column_stack([np.ones(sub.size), x[sub], y[sub]])
    a2 = np.column_stack([np.ones(sub.size), x[sub] ** 2, y[sub] ** 2, x[sub] * y[sub]])
    c1 = np.linalg.lstsq(a1, d, rcond=None)[0]                           # (3, n_ifg): c, d/dx, d/dy in mm/km
    r1 = np.sqrt(np.mean((d - a1 @ c1) ** 2, 0))
    r2 = np.sqrt(np.mean((d - a2 @ np.linalg.lstsq(a2, d, rcond=None)[0]) ** 2, 0))
    quad_gain = float(np.median((r1 - r2) / r1))
    a3 = np.column_stack([a1, x[sub] ** 2, y[sub] ** 2, x[sub] * y[sub]])            # full quadratic
    r3 = np.sqrt(np.mean((d - a3 @ np.linalg.lstsq(a3, d, rcond=None)[0]) ** 2, 0))
    print(f"  full quadratic (x, y, x2, y2, xy) over plane: median RMS gain {100 * np.median((r1 - r3) / r1):.0f}%")
    # 2. split
    grad = c1[1:].T * 10.0                                                # (n_ifg, 2) mm per 10 km
    beta = wfit(t, grad, w)[0]                                            # (2,) mm per 10 km per yr
    rest = grad - np.outer(t, beta)
    print(f"  quadratic over plane: median RMS gain {100 * quad_gain:.0f}% (engine uses degree 2 when >= 8%)")
    print(f"  ramp gradient per ifg (mm/10 km): E-W std {grad[:, 0].std():.1f}, N-S std {grad[:, 1].std():.1f}")
    print(f"  trend of the ramp: E-W {beta[0]:+.1f}, N-S {beta[1]:+.1f} mm/yr per 10 km (all PS, bowl included)")
    print(f"  rest: E-W std {rest[:, 0].std():.1f}, N-S std {rest[:, 1].std():.1f} mm/10 km")
    seasonal = None
    if span_yr >= 1.0:
        om = 2 * np.pi * t
        g = np.column_stack([np.sin(om), np.cos(om), np.ones_like(t)])
        rr = rest - rest.mean(0)
        fit = g @ np.linalg.lstsq(g, rr, rcond=None)[0]
        seasonal = 1 - ((rr - fit) ** 2).sum(0) / (rr ** 2).sum(0)
        print(f"  seasonal share of the rest: E-W {100 * seasonal[0]:.0f}%, N-S {100 * seasonal[1]:.0f}% "
              f"(> 50% keeps it)")
    else:
        print("  seasonal check skipped (< 1 year)")

    # 3. velocity without the rest, per cell
    ph = lam * (uw[ok] - aps[ok] - scla[ok]).astype(np.float64)
    ph -= (x[ok, None] * rest[:, 0] + y[ok, None] * rest[:, 1]) / 10.0   # rest of the ramp removed
    tc = t - np.sum(w * t) / np.sum(w)
    v0 = (ph * w) @ tc / np.sum(w * tc * tc)                              # weighted slope, mm/yr
    del ph
    ix = np.floor((x[ok] - x[ok].min()) * 1000 / CELL_M).astype(np.int64)
    iy = np.floor((y[ok] - y[ok].min()) * 1000 / CELL_M).astype(np.int64)
    key = ix * 100_000 + iy
    order = np.argsort(key, kind="stable")
    ks, vs = key[order], v0[order]
    starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
    counts = np.diff(np.r_[starts, ks.size])
    parts = np.split(vs, starts[1:])
    med = np.array([np.median(s) for s in parts])
    spread = np.array([1.4826 * np.median(np.abs(s - m)) for s, m in zip(parts, med, strict=True)])
    good = counts >= MIN_PS_CELL
    noise = float(np.median(spread[good]))                                # PS scatter within a cell (noise level)
    cx = ((ks[starts] // 100_000) + 0.5) * CELL_M / 1000 + x[ok].min()
    cy = ((ks[starts] % 100_000) + 0.5) * CELL_M / 1000 + y[ok].min()
    cx, cy, cv = cx[good], cy[good], med[good]
    coef_all = np.linalg.lstsq(np.column_stack([np.ones_like(cx), cx, cy]), cv, rcond=None)[0]
    thr = max(5.0, 2.0 * noise) if THRESHOLD == "noise" else float(THRESHOLD)
    coef, stable, sig = select_plane(cx, cy, cv, thr)
    share = stable.mean()
    mx, my = 0.5 * (cx.min() + cx.max()), 0.5 * (cy.min() + cy.max())
    quads = len({(a, b) for a, b in zip(cx[stable] > mx, cy[stable] > my, strict=True)})
    gdir = coef[1:] / max(np.hypot(*coef[1:]), 1e-12)
    p_all, p_st = cx * gdir[0] + cy * gdir[1], cx[stable] * gdir[0] + cy[stable] * gdir[1]
    span = (np.percentile(p_st, 98) - np.percentile(p_st, 2)) / (p_all.max() - p_all.min()) if stable.any() else 0
    # sub-frame consistency: a nuisance ramp is one plane over the whole frame, so the stable cells of each half
    # (W, E, S, N) give the same gradient; the flank of a smooth bowl wider than the halves does not
    # each half selects its own stable cells from scratch (independent of the full-frame selection)
    halves = {"W": cx < mx, "E": cx >= mx, "S": cy < my, "N": cy >= my}
    g_full = 10 * coef[1:]
    dev = []
    for h, m in halves.items():
        ch, sh, _ = select_plane(cx[m], cy[m], cv[m], thr)
        if sh.sum() < 30:
            print(f"    half {h}: {int(sh.sum())} stable cells, not fitted")
            continue
        gh = 10 * ch[1:]
        dev.append(np.hypot(*(gh - g_full)))
        print(f"    half {h}: {int(sh.sum()):5d} stable cells ({sh.mean():.0%}), gradient E-W {gh[0]:+6.1f}, "
              f"N-S {gh[1]:+6.1f}")
    tol = max(5.0, 0.3 * float(np.hypot(*g_full)))
    consistent = len(dev) == 4 and max(dev) <= tol
    print(f"  sub-frame consistency: max deviation {max(dev) if dev else float('nan'):.1f} vs tolerance {tol:.1f} "
          f"mm/yr per 10 km -> {'consistent' if consistent else 'NOT consistent'}; stable cells {int(stable.sum())}")
    small = max(ext) < 5.0
    passes = (not small) and consistent and quads >= 3 and span >= 0.60          # revised rule (§5.1)
    coef_st = (np.linalg.lstsq(np.column_stack([np.ones(stable.sum()), cx[stable], cy[stable]]), cv[stable],
                               rcond=None)[0] if stable.sum() >= 10 else np.full(3, np.nan))
    print(f"  cells {cv.size:,} ({CELL_M:.0f} m, >= {MIN_PS_CELL} PS); velocity plane, all cells: "
          f"E-W {10 * coef_all[1]:+.1f}, N-S {10 * coef_all[2]:+.1f} mm/yr per 10 km")
    print(f"  robust plane: E-W {10 * coef[1]:+.1f}, N-S {10 * coef[2]:+.1f}; robust std of cells {sig:.1f}, "
          f"PS scatter within a cell {noise:.1f} -> threshold ({THRESHOLD}) {thr:.1f} mm/yr")
    print(f"  stable cells {share:.0%}, quadrants {quads}/4, span along the gradient {span:.0%}"
          + ("  (frame < 5 km: test skipped)" if small else ""))
    print(f"  plane on stable cells: E-W {10 * coef_st[1]:+.1f}, N-S {10 * coef_st[2]:+.1f} mm/yr per 10 km")
    reason = ("frame < 5 km" if small else
              "; ".join(s for s, bad in (("plane depends on the frame", not consistent), ("< 3 quadrants", quads < 3),
                                         ("span < 60%", span < 0.60)) if bad))
    print(f"  DECISION: rest removed; trend {'REMOVED (stable-cell plane)' if passes else 'KEPT - ' + reason}")

    if gnss:
        lo, la, vv = lon[ok], lat[ok], v0
        for label, c in (("n: trend kept", np.zeros(3)), ("auto plane (stable cells)", coef_st),
                         ("y-like (all-cell plane)", coef_all)):
            med_s = {}
            for s, (sx, sy) in STATIONS.items():
                px, py = (sx - lon0) * kx, (sy - lat0) * 111.32
                near = np.hypot((lo - sx) * kx * 1000, (la - sy) * 111320) <= 100
                med_s[s] = float(np.median(vv[near])) - (c[1] * px + c[2] * py)
            for ref, gv in GNSS.items():
                diff = {s: med_s[s] - gv[s] for s in STATIONS}
                after = {s: diff[s] - np.mean([diff[o] for o in STATIONS if o != s]) for s in STATIONS}
                gain = np.polyfit([gv[s] for s in STATIONS], [med_s[s] for s in STATIONS], 1)[0]
                print(f"  GNSS {ref:6s} | {label:26s}: gain {gain:.2f}, LOO "
                      f"{np.sqrt(np.mean(np.square(list(after.values())))):5.1f}  "
                      + ", ".join(f"{s} {v:+.0f}" for s, v in after.items()))

    if out:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        o = Path(out)
        o.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), dpi=120)
        ax[0].plot(ifg, grad[:, 0], "o-", label="E-W total")
        ax[0].plot(ifg, np.outer(t, beta)[:, 0], "--", label="E-W trend")
        ax[0].plot(ifg, grad[:, 1], "s-", label="N-S total", alpha=0.7)
        ax[0].plot(ifg, np.outer(t, beta)[:, 1], ":", label="N-S trend")
        ax[0].axhline(0, color="0.6", lw=0.5)
        ax[0].set_ylabel("ramp gradient (mm per 10 km)")
        ax[0].legend(fontsize=7)
        ax[0].tick_params(axis="x", rotation=60, labelsize=7)
        lim = np.percentile(np.abs(cv), 99)
        ax[1].scatter(cx[~stable], cy[~stable], c=cv[~stable], s=3, cmap="RdBu", vmin=-lim, vmax=lim)
        ax[1].scatter(cx[stable], cy[stable], s=1, c="k", alpha=0.5, label="stable cells")
        ax[1].set_aspect(1)
        ax[1].set_xlabel("km")
        ax[1].set_title(f"stable {share:.0%}, quadrants {quads}, span {span:.0%}, "
                        f"halves {'consistent' if consistent else 'NOT consistent'}: "
                        f"{'trend removed' if passes else 'trend kept'}", fontsize=9)
        ax[1].legend(fontsize=7, loc="lower right")
        fig.suptitle(Path(state).parents[2].name, fontsize=10)
        fig.tight_layout()
        fig.savefig(o / f"ramp_auto_{Path(state).parents[2].name}.png")
        plt.close(fig)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--thr="):
            THRESHOLD = a.split("=", 1)[1]
        if a.startswith("--bbox="):
            BBOX = [float(v) for v in a.split("=", 1)[1].split(",")]
    main(args[0], args[1] if len(args) > 1 else None, "--gnss" in sys.argv)
