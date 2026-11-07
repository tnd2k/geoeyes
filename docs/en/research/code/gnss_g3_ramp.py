"""G3.1d (gnss-insar-calibration.md §9.1): is the ICMX / MXTX misfit a scene-wide ramp per epoch?

Usage:  python gnss_g3_ramp.py <ps_runs/<stack>/state.h5> <analyses/gnss/<product>/series.npz>

The PS around each station agree to 2-5 mm, yet ICMX (west) and MXTX (east, 30 km away) scatter in opposite directions
on the same dates. That points to a long-wavelength (ramp) phase per epoch, not to point noise.

For a random subset of PS, displacement per epoch d = k * (unwrapped - SCLA - APS) (k from the velocity fit, as in
gnss_g3_aps.py). Per epoch a plane a + b*x + c*y (km) is fitted to
- d itself (total), and
- d minus each PS's own linear trend (the non-linear part: what a straight-line deformation model cannot explain).
The plane of the non-linear part is the candidate nuisance: ionosphere / orbit / long-wavelength troposphere.

Prints per epoch the E-W and N-S gradient (mm per 10 km) of the non-linear plane, and, per station, the station
residual InSAR - GNSS (detrended) next to the plane value at the station (detrended), with their correlation.
"""
from __future__ import annotations

import sys
from datetime import date

import h5py
import numpy as np

STATIONS = {"ICMX": (-99.1709, 19.4056), "MMX1": (-99.0684, 19.4317), "MXTX": (-98.8763, 19.5396)}
N_SUB = 300_000


def main(state: str, series: str) -> None:
    rng = np.random.default_rng(0)
    with h5py.File(state, "r") as f:
        n = f["ps/lon"].shape[0]
        lon, lat = f["ps/lon"][:], f["ps/lat"][:]
        ifg = [date.fromisoformat(d.decode()) for d in f["time/ifg_dates"][:]]
        epochs = [date.fromisoformat(d.decode()) for d in f["time/epoch_dates"][:]]
        v = f["velocity/v_linear_mm_yr"][:]
        uw, scla, aps = f["phase/unwrapped"][:], f["phase/scla"][:], f["phase/aps"][:]
    master = (set(epochs) - set(ifg)).pop()
    order = np.argsort([d.toordinal() for d in ifg + [master]])
    dates = [(ifg + [master])[i] for i in order]
    t = np.array([(d - master).days for d in dates], np.float64) / 365.25

    ph = np.hstack([uw - scla - aps, np.zeros((n, 1), np.float32)])[:, order]
    raw = np.hstack([uw - scla, np.zeros((n, 1), np.float32)])[:, order]      # before APS
    ok = np.isfinite(ph).all(1) & np.isfinite(raw).all(1) & np.isfinite(v)
    tc = t - t.mean()
    s = (ph - ph.mean(1, keepdims=True)) @ tc / (tc @ tc)
    k = np.polyfit(s[ok], v[ok], 1)[0]                                          # mm/yr per rad/yr
    d_mm, raw_mm = k * ph, k * raw
    print(f"PS {n:,}, complete {ok.sum():,}; k = {k:.3f} mm/rad; master {master}")

    idx = rng.choice(np.flatnonzero(ok), size=min(N_SUB, ok.sum()), replace=False)
    lon0, lat0 = float(np.mean(lon[idx])), float(np.mean(lat[idx]))
    kx = 111.32 * np.cos(np.radians(lat0))
    x, y = (lon - lon0) * kx, (lat - lat0) * 111.32                             # km
    G = np.column_stack([np.ones(idx.size), x[idx], y[idx]])

    def planes(dd: np.ndarray) -> np.ndarray:            # (3, epochs)
        return np.linalg.lstsq(G, dd[idx], rcond=None)[0]

    # non-linear part: remove each PS's own straight line in time
    def nonlinear(dd: np.ndarray) -> np.ndarray:
        dc = dd - dd.mean(1, keepdims=True)
        sl = dc @ tc / (tc @ tc)
        return dc - np.outer(sl, tc)

    P_nl = planes(nonlinear(d_mm))
    P_nl_raw = planes(nonlinear(raw_mm))
    P_tot = planes(d_mm)
    print("\nper-epoch plane of the NON-LINEAR displacement (mm per 10 km): after APS | before APS (ERA5)")
    for j, dt in enumerate(dates):
        print(f"  {dt}  E-W {10 * P_nl[1, j]:+6.1f}  N-S {10 * P_nl[2, j]:+6.1f}   |  "
              f"E-W {10 * P_nl_raw[1, j]:+6.1f}  N-S {10 * P_nl_raw[2, j]:+6.1f}")
    print(f"  std over epochs, E-W: after APS {10 * P_nl[1].std():.1f}, before APS {10 * P_nl_raw[1].std():.1f} "
          f"mm/10 km")
    # how much of the non-linear variance over the scene the plane explains
    nl = nonlinear(d_mm)[idx]
    fit = G @ P_nl
    print(f"  plane explains {100 * (1 - np.var(nl - fit) / np.var(nl)):.0f}% of the non-linear variance")
    # linear-in-time ramp: velocity carried by the plane of the total displacement
    st = (P_tot - P_tot.mean(1, keepdims=True)) @ tc / (tc @ tc)
    print(f"\nvelocity plane of the total displacement: E-W {10 * st[1]:+.1f}, N-S {10 * st[2]:+.1f} mm/yr per 10 km "
          f"(includes the real subsidence bowl, so not a nuisance estimate by itself)")

    z = np.load(series, allow_pickle=True)
    sd = [date.fromisoformat(str(s)) for s in z["dates"]]
    assert sd == dates, "series dates differ from state epochs"
    print("\nstation residual InSAR - GNSS(vertical), detrended, vs the non-linear plane at the station (mm)")
    for site, (lo, la) in STATIONS.items():
        xs, ys = (lo - lon0) * kx, (la - lat0) * 111.32
        pl = P_nl[0] + P_nl[1] * xs + P_nl[2] * ys
        r = z[f"{site}__insar"] - z[f"{site}__gnss_vertical"]
        m = np.isfinite(r)
        rd = r[m] - np.polyval(np.polyfit(t[m], r[m], 1), t[m])
        pd = pl[m] - np.polyval(np.polyfit(t[m], pl[m], 1), t[m])
        c = np.corrcoef(rd, pd)[0, 1]
        g = np.polyfit(pd, rd, 1)[0]
        print(f"  {site}: residual std {rd.std():5.1f}  plane std {pd.std():5.1f}  corr {c:+.2f}  "
              f"residual std after removing the plane {np.std(rd - pd):5.1f}  (fit gain {g:.2f})")
        print("     resid " + " ".join(f"{a:+5.0f}" for a in rd))
        print("     plane " + " ".join(f"{a:+5.0f}" for a in pd))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
