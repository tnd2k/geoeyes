"""G3.1b (gnss-insar-calibration.md §9.1): how much velocity does the APS remove at the GNSS stations?

Usage:  python gnss_g3_aps.py <ps_runs/<stack>/state.h5>

The PS state keeps, per PS and interferogram, the unwrapped phase, the SCLA (look-angle error) phase, the APS
actually removed (``phase/aps``) and the linear (height-correlated) APS (``phase/aps_linear``). Velocity is linear
in the phase, so the velocity each term carries is the slope of that term over time, scaled by the factor k that
maps phase slope to ``velocity/v_linear_mm_yr`` (fitted here, so the sign and units come from the engine itself).

Prints:
- k and how well slope(unwrapped - SCLA - APS) reproduces v_linear (the check that the decomposition is right);
- the B_perp-time correlation and the velocity carried by the SCLA term;
- the phase-height coefficient of the APS velocity over the scene (mm/yr per 100 m);
- per station (PS within 100 m, medians): v as delivered, without the APS, without the APS and the SCLA, and the
  velocity the APS and the SCLA removed;
- leave-one-out with an offset against the GNSS rates (window and MIDAS) for each variant.
"""
from __future__ import annotations

import sys
from datetime import date

import h5py
import numpy as np

STATIONS = {"ICMX": (-99.1709, 19.4056), "MMX1": (-99.0684, 19.4317), "MXTX": (-98.8763, 19.5396)}
# GNSS LOS rates (vertical projection, mm/yr) from analyses/gnss/.../comparison.json of mexico_g3 v1
GNSS = {"window": {"ICMX": -52.05, "MMX1": -258.23, "MXTX": -32.26},
        "midas": {"ICMX": -18.39, "MMX1": -187.61, "MXTX": -9.49}}


def slope(a: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Least-squares slope per row of ``a`` (n, m) over ``t`` (m,), NaN-free rows."""
    tc = t - t.mean()
    return (a - a.mean(axis=1, keepdims=True)) @ tc / (tc @ tc)


def loo_offset(diff: dict[str, float]) -> tuple[float, float, dict[str, float]]:
    sites = list(diff)
    after = {s: diff[s] - np.mean([diff[o] for o in sites if o != s]) for s in sites}
    rms = lambda d: float(np.sqrt(np.mean(np.square(list(d.values())))))  # noqa: E731
    return rms(diff), rms(after), after


def main(state: str) -> None:
    with h5py.File(state, "r") as f:
        lon, lat = f["ps/lon"][:], f["ps/lat"][:]
        hgt = f["ps/height_m"][:]
        ifg = [date.fromisoformat(d.decode()) for d in f["time/ifg_dates"][:]]
        epochs = [date.fromisoformat(d.decode()) for d in f["time/epoch_dates"][:]]
        uw, scla = f["phase/unwrapped"][:], f["phase/scla"][:]
        aps, aps_lin = f["phase/aps"][:], f["phase/aps_linear"][:]
        v = f["velocity/v_linear_mm_yr"][:]
    master = (set(epochs) - set(ifg)).pop()
    # the master epoch is a zero column of every term: include it so the slopes match the engine's
    t = np.array([(d - master).days for d in ifg] + [0], np.float64) / 365.25
    z = np.zeros((uw.shape[0], 1), np.float32)
    add0 = lambda a: np.hstack([a, z])  # noqa: E731

    ok = np.isfinite(uw).all(1) & np.isfinite(scla).all(1) & np.isfinite(aps).all(1) & np.isfinite(aps_lin).all(1) \
        & np.isfinite(v)
    print(f"PS {ok.size:,}, complete {ok.sum():,}; master {master}")
    s_corr = slope(add0(uw - scla - aps)[ok], t)
    s_aps, s_lin = slope(add0(aps)[ok], t), slope(add0(aps_lin)[ok], t)
    k, c = np.polyfit(s_corr, v[ok], 1)
    resid = v[ok] - (k * s_corr + c)
    print(f"v_linear = {k:.3f} x slope(uw - scla - aps) + {c:.2f}   (residual std {resid.std():.2f} mm/yr)")

    s_scla = slope(add0(scla)[ok], t)
    with h5py.File(state, "r") as f:
        bp = f["ps/bperp"][:][ok]
    bp_mean = np.hstack([np.nanmean(bp, axis=0), 0.0])
    print(f"B_perp per epoch (scene mean, m): {np.round(bp_mean[:-1], 0).tolist()}")
    print(f"corr(B_perp, time) = {np.corrcoef(bp_mean, t)[0, 1]:.2f}")
    print(f"velocity carried by the SCLA term: scene std {np.std(k * s_scla):.1f} mm/yr")

    v_del, v_noaps = v[ok], v[ok] + k * s_aps          # adding the APS back removes its velocity
    variants_extra = {"no APS, no SCLA": v[ok] + k * s_aps + k * s_scla}
    dv_aps, dv_lin = -k * s_aps, -k * s_lin             # change the APS made to the delivered velocity (+ = raised)
    h0 = hgt[ok].astype(np.float64) - float(np.mean(hgt[ok]))
    a = np.polyfit(h0, dv_lin, 1)[0]
    print(f"linear APS velocity vs height: {100 * a:.1f} mm/yr per 100 m "
          f"(heights {np.percentile(hgt[ok], 2):.0f}-{np.percentile(hgt[ok], 98):.0f} m), "
          f"corr {np.corrcoef(hgt[ok], dv_lin)[0, 1]:.2f}")
    print(f"delivered velocity vs height: corr {np.corrcoef(hgt[ok], v_del)[0, 1]:.2f}; "
          f"without APS: corr {np.corrcoef(hgt[ok], v_noaps)[0, 1]:.2f}")

    lo, la = lon[ok], lat[ok]
    variants = {"delivered": v_del, "no APS": v_noaps, **variants_extra}
    med: dict[str, dict[str, float]] = {n: {} for n in variants}
    print("\nper station (median of PS within 100 m, mm/yr)")
    for site, (x0, y0) in STATIONS.items():
        kx = 111_320.0 * np.cos(np.radians(y0))
        near = np.hypot((lo - x0) * kx, (la - y0) * 111_320.0) <= 100
        for n, vv in variants.items():
            med[n][site] = float(np.median(vv[near]))
        print(f"  {site}: n={near.sum():4d}  height {np.median(hgt[ok][near]):6.0f} m  delivered "
              f"{med['delivered'][site]:8.1f}  no APS {med['no APS'][site]:8.1f}  removed by APS "
              f"{np.median(dv_aps[near]):7.1f} (linear APS {np.median(dv_lin[near]):7.1f}); by SCLA "
              f"{np.median(-k * s_scla[near]):7.1f}")

    for n in variants:
        x = np.array([med[n][s] for s in STATIONS])
        for ref, g in GNSS.items():
            y = np.array([g[s] for s in STATIONS])
            diff = {s: med[n][s] - g[s] for s in STATIONS}
            before, after, per = loo_offset(diff)
            gain = np.polyfit(y, x, 1)[0]
            print(f"\n{n:9s} vs GNSS {ref:6s}: InSAR = {gain:.2f} x GNSS + c;  LOO RMS {before:.1f} -> {after:.1f}"
                  f"  ({', '.join(f'{s} {d:+.1f}' for s, d in per.items())})")


if __name__ == "__main__":
    main(sys.argv[1])
