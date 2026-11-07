"""C0 of choshui-groundwater.md: audit and catalogue of the Choshui fan groundwater heads.

Reads the well file (read-only) and writes to studies/choshui_gw/c0/:
- wells.parquet      one row per well ID: station, well number, version, coordinates (EPSG:3826, 4326, 32650),
                     depth, screen, elevation, observation span, valid days, QC counts, summary statistics
- rebuild.csv        old (…1) / new (…2) IDs of the same well number: depth, elevation and head offset across the gap
- aquifer_index.csv  depth and screen by well number (test of "well number = aquifer index")
- qc_flags.csv       spikes, flat runs and persistent jumps per well, with dates
- heads_monthly.parquet, heads_12d.parquet   cleaned heads resampled (median) by month and to 12-day bins
- maps/*.png         trend, seasonal amplitude and month of the lowest head per well number, 2015-01 → 2024-08
- c0_summary.json    the numbers quoted in c0_audit.md

Usage: python -I -X utf8 choshui_c0.py
"""
import json
import re
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from pyproj import Transformer

sys.stdout.reconfigure(encoding="utf-8")
STUDY = Path(r"D:\projects\geoeyes_workspace\studies\choshui_gw")
GWL = STUDY / "data" / "20240828_GWL_CRFP_model.h5"
TS = {"asc": Path(r"C:\Users\duong\Downloads\timeseries_SET_ERA5_ramp_demErr-001.h5"),
      "desc": Path(r"C:\Users\duong\Downloads\timeseries_SET_ERA5_ramp_demErr-002.h5")}
OUT = STUDY / "c0"
T0, T1 = np.datetime64("2015-01-01"), np.datetime64("2024-08-20")       # overlap with InSAR
SPIKE_M, SPIKE_K, FLAT_DAYS, JUMP_M = 2.0, 6.0, 30, 3.0


def parse_screen(s):
    if not isinstance(s, str):
        return np.nan, np.nan
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    return (min(nums), max(nums)) if nums else (np.nan, np.nan)


def well_number(name, wid):
    m = re.search(r"\((\d+)\)", name or "")
    if m:
        return int(m.group(1))
    return int(wid[-2]) if wid[-2].isdigit() else 1


def qc(days, h):
    """Spikes (|h - running median| > max(SPIKE_M, SPIKE_K·MAD)), flat runs (≥ FLAT_DAYS equal values) and
    persistent jumps (median of the 30 days after a day minus the 30 days before > JUMP_M). Returns the cleaned
    series (spikes and flat runs set to NaN) and the flags."""
    s = pd.Series(h, index=pd.DatetimeIndex(days))
    med = s.rolling(31, center=True, min_periods=10).median()
    dev = (s - med).abs()
    mad = dev.rolling(181, center=True, min_periods=30).median() * 1.4826
    spike = (dev > np.maximum(SPIKE_M, SPIKE_K * mad)) & s.notna()
    v = s.to_numpy()
    flat = np.zeros(v.size, bool)
    i = 0
    while i < v.size:
        j = i
        while j + 1 < v.size and np.isfinite(v[i]) and v[j + 1] == v[i]:
            j += 1
        if j - i + 1 >= FLAT_DAYS:
            flat[i:j + 1] = True
        i = j + 1
    clean = s.mask(spike | flat)
    # abrupt steps: between consecutive valid values (≤ 30 days apart) a change > JUMP_M that persists (the 30-day
    # medians after and before differ by > 60 % of it). Seasonal declines are gradual (cm/day) and are not flagged.
    cv = clean.dropna()
    jumps = []
    if len(cv) > 60:
        dt = np.diff(cv.index.values).astype("timedelta64[D]").astype(int)
        dh = np.diff(cv.to_numpy())
        for i in np.where((np.abs(dh) > JUMP_M) & (dt <= 30))[0]:
            b = cv.iloc[max(0, i - 29):i + 1].median()
            a = cv.iloc[i + 1:i + 31].median()
            if abs(a - b) > 0.6 * abs(dh[i]):
                jumps.append((str(cv.index[i + 1].date()), round(float(a - b), 2)))
    return clean, int(spike.sum()), int(flat.sum()), jumps


def harmonic_fit(t_yr, y):
    """y = a + b·t + c·sin(2πt) + d·cos(2πt); returns trend (m/yr), its SE, amplitude (m), month of the minimum."""
    ok = np.isfinite(y)
    if ok.sum() < 24:
        return np.nan, np.nan, np.nan, np.nan
    t, y = t_yr[ok], y[ok]
    a = np.column_stack([np.ones_like(t), t, np.sin(2 * np.pi * t), np.cos(2 * np.pi * t)])
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    res = y - a @ coef
    cov = np.linalg.pinv(a.T @ a) * (res @ res) / max(len(y) - 4, 1)
    amp = float(np.hypot(coef[2], coef[3]))
    phase = np.arctan2(coef[2], coef[3])                # c·sin + d·cos = amp·cos(2πt − phase)
    t_min = ((phase + np.pi) / (2 * np.pi)) % 1.0       # fraction of the year at the minimum
    return float(coef[1]), float(np.sqrt(cov[1, 1])), amp, float(t_min * 12 + 1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "maps").mkdir(exist_ok=True)
    to_ll = Transformer.from_crs(3826, 4326, always_xy=True)
    to_utm = Transformer.from_crs(3826, 32650, always_xy=True)
    rows, flags, monthly, d12 = [], [], [], []
    with h5py.File(GWL, "r") as f:
        days = np.array([np.datetime64(f"{s[:4].decode()}-{s[4:6].decode()}-{s[6:].decode()}") for s in f["date"][()]])
        bins = np.arange(np.datetime64("2015-01-14"), T1 + 12, 12)          # 12-day bins on the asc first date
        for st in f:
            if st == "date":
                continue
            ga = f[st].attrs
            has_xy = "X" in ga and "Y" in ga and float(ga["X"]) > 1e5
            x, y = (float(ga["X"]), float(ga["Y"])) if has_xy else (np.nan, np.nan)
            lon, lat = to_ll.transform(x, y) if has_xy else (np.nan, np.nan)
            ux, uy = to_utm.transform(x, y) if has_xy else (np.nan, np.nan)
            for wid in f[st]:
                g = f[st][wid]
                if not isinstance(g, h5py.Group) or "measure" not in g:
                    continue
                a = g.attrs
                h = g["measure/daily_value"][()].astype(float)
                clean, n_spike, n_flat, jumps = qc(days, h)
                top, bot = parse_screen(a.get("Well_Screen(m)"))
                name = a.get("WellName", "")
                key = f"{st}/{wid}"
                ov = (days >= T0) & (days <= T1)
                c = clean.to_numpy()
                m = clean[(clean.index >= str(T0)) & (clean.index <= str(T1))].resample("MS").agg(["median", "count"])
                mm = m["median"].where(m["count"] >= 10)
                ty = ((mm.index.values - np.datetime64("2015-01-01")).astype("timedelta64[D]").astype(float)
                      / 365.25)
                trend, trend_se, amp, mon_min = harmonic_fit(ty, mm.to_numpy())
                # historical minimum on monthly medians (daily minima are pumping transients and spikes)
                mall = clean.resample("MS").agg(["median", "count"])
                mall = mall["median"].where(mall["count"] >= 10)
                pre = mall[mall.index < str(T0)]
                ovm = mall[(mall.index >= str(T0)) & (mall.index <= str(T1))]
                hist_min = float(pre.min()) if pre.notna().any() else np.nan
                below = int((ovm < hist_min).sum()) if np.isfinite(hist_min) else None
                rows.append({
                    "key": key, "station": st, "abbr": ga.get("Abbreviation", ""), "well_id": wid,
                    "well_no": well_number(name, wid), "version": wid[-1], "name": name,
                    "x_3826": x, "y_3826": y, "lon": lon, "lat": lat, "x_utm50": ux, "y_utm50": uy,
                    "depth_m": float(a.get("Well_Depth(m)", np.nan)), "elev_m": float(a.get("Well_Elev(m)", np.nan)),
                    "screen_top_m": top, "screen_bot_m": bot, "first_obs": a.get("FIRST_OBS"),
                    "last_obs": a.get("LAST_OBS"), "status": a.get("Status"),
                    "valid_days": int(np.isfinite(h).sum()), "valid_days_overlap": int(np.isfinite(c[ov]).sum()),
                    "n_spike": n_spike, "n_flat": n_flat, "n_jump": len(jumps),
                    "trend_m_yr": trend, "trend_se": trend_se, "seasonal_amp_m": amp, "month_of_min": mon_min,
                    "head_median_overlap": float(np.nanmedian(c[ov])) if np.isfinite(c[ov]).any() else np.nan,
                    "hist_min_pre2015": hist_min, "days_below_hist_min": below,
                    "min_overlap": float(ovm.min()) if ovm.notna().any() else np.nan,
                    "year_of_min_overlap": int(ovm.idxmin().year) if ovm.notna().any() else None,
                    "months_valid_pre2015": int(pre.notna().sum()),
                })
                for d, v in jumps:
                    flags.append({"key": key, "kind": "jump", "date": d, "size_m": v})
                if n_spike or n_flat:
                    flags.append({"key": key, "kind": "spike/flat", "date": "", "size_m": np.nan,
                                  "n_spike": n_spike, "n_flat": n_flat})
                mon = clean.resample("MS").agg(["median", "count"])
                mon = mon[mon["count"] >= 10]
                monthly += [{"key": key, "month": i.date(), "head_m": float(v)} for i, v in mon["median"].items()]
                ix = np.searchsorted(bins, clean.index.values, side="right") - 1
                ser = pd.Series(c, index=ix)
                ser = ser[(ix >= 0) & np.isfinite(c) & (clean.index.values >= bins[0])]
                for b, v in ser.groupby(level=0).median().items():
                    d12.append({"key": key, "bin_start": pd.Timestamp(bins[b]).date(), "head_m": float(v)})
    w = pd.DataFrame(rows)
    # pre-2015 minimum including the old ID of the same well number (2001-2010), when the depth changed ≤ 5 m;
    # no datum offset is applied (rebuild.csv gives the size of the gap)
    w["hist_min_pre2015_incl_old"] = w["hist_min_pre2015"]
    for (st, no), g in w.groupby(["station", "well_no"]):
        if set(g.version) >= {"1", "2"}:
            o, n = g[g.version == "1"].iloc[0], g[g.version == "2"].index[0]
            if abs(o.depth_m - w.at[n, "depth_m"]) <= 5:
                w.at[n, "hist_min_pre2015_incl_old"] = np.nanmin([w.at[n, "hist_min_pre2015"], o.hist_min_pre2015])
    w["below_incl_old"] = w["min_overlap"] < w["hist_min_pre2015_incl_old"]
    w.to_parquet(OUT / "wells.parquet", index=False)
    pd.DataFrame(flags).to_csv(OUT / "qc_flags.csv", index=False, encoding="utf-8")
    pd.DataFrame(monthly).to_parquet(OUT / "heads_monthly.parquet", index=False)
    pd.DataFrame(d12).to_parquet(OUT / "heads_12d.parquet", index=False)

    # rebuild 2011-2012: same station and well number, version 1 and 2
    mon = pd.DataFrame(monthly)
    mon["month"] = pd.to_datetime(mon["month"])
    reb = []
    for (st, no), g in w.groupby(["station", "well_no"]):
        if set(g.version) >= {"1", "2"}:
            o, n = g[g.version == "1"].iloc[0], g[g.version == "2"].iloc[0]
            ho = mon[(mon.key == o.key) & (mon.month >= "2010-01-01") & (mon.month < "2011-01-01")].head_m
            hn = mon[(mon.key == n.key) & (mon.month >= "2012-01-01") & (mon.month < "2013-01-01")].head_m
            reb.append({"station": st, "well_no": no, "old": o.well_id, "new": n.well_id,
                        "depth_old": o.depth_m, "depth_new": n.depth_m, "elev_old": o.elev_m, "elev_new": n.elev_m,
                        "head_2010_median": ho.median(), "head_2012_median": hn.median(),
                        "offset_2012_minus_2010": hn.median() - ho.median()})
    reb = pd.DataFrame(reb)
    reb.to_csv(OUT / "rebuild.csv", index=False, encoding="utf-8")

    # aquifer index: depth and screen by well number
    ai = w.groupby("well_no").agg(n=("key", "size"), depth_min=("depth_m", "min"), depth_med=("depth_m", "median"),
                                  depth_max=("depth_m", "max"), screen_top_med=("screen_top_m", "median"),
                                  screen_bot_med=("screen_bot_m", "median")).round(1)
    ai.to_csv(OUT / "aquifer_index.csv", encoding="utf-8")
    mono = []
    for st, g in w[w.version != "1"].groupby("station"):
        g = g.dropna(subset=["depth_m"]).sort_values("well_no")
        if len(g) >= 2:
            mono.append(bool(np.all(np.diff(g.depth_m.to_numpy()) > 0)))

    # dates of the two InSAR stacks (the small date datasets only)
    ins = {}
    for k, p in TS.items():
        if p.exists():
            with h5py.File(p, "r") as f:
                d = [s.decode() for s in f["date"][()]]
            ins[k] = {"n": len(d), "first": d[0], "last": d[-1],
                      "n_in_overlap": sum(str(T0).replace("-", "") <= s <= str(T1).replace("-", "") for s in d)}
            (OUT / f"insar_dates_{k}.txt").write_text("\n".join(d), encoding="utf-8")

    _maps(w)
    use = w[(w.valid_days_overlap >= 1500) & w.lon.notna()]
    summ = {
        "stations": int(w.station.nunique()), "wells": int(len(w)),
        "stations_without_xy": sorted(w[w.lon.isna()].station.unique().tolist()),
        "wells_usable_overlap": int(len(use)), "stations_usable_overlap": int(use.station.nunique()),
        "usable_by_well_no": use.groupby("well_no").size().to_dict(),
        "rebuild_pairs": int(len(reb)),
        "rebuild_depth_change_gt_5m": int((reb.depth_new - reb.depth_old).abs().gt(5).sum()) if len(reb) else 0,
        "rebuild_offset_median_m": float(reb.offset_2012_minus_2010.median()) if len(reb) else None,
        "depth_increases_with_well_no_share": float(np.mean(mono)) if mono else None, "stations_tested": len(mono),
        "wells_with_jumps": int((w.n_jump > 0).sum()), "wells_with_spikes": int((w.n_spike > 0).sum()),
        "wells_with_flat_runs": int((w.n_flat > 0).sum()),
        "trend_m_yr_median_by_well_no": use.groupby("well_no").trend_m_yr.median().round(3).to_dict(),
        "amp_m_median_by_well_no": use.groupby("well_no").seasonal_amp_m.median().round(2).to_dict(),
        "month_of_min_median_by_well_no": use.groupby("well_no").month_of_min.median().round(1).to_dict(),
        "wells_below_pre2015_min": int((use.days_below_hist_min.fillna(0) > 0).sum()),
        "wells_below_pre2015_min_incl_old_id": int(use.below_incl_old.sum()),
        "year_of_min_overlap_counts": use.year_of_min_overlap.value_counts().sort_index().to_dict(),
        "wells_with_depth_0": int((w.depth_m <= 0).sum()),
        "wells_starting_2012_or_later": int((pd.to_datetime(use.first_obs) >= "2012-01-01").sum()),
        "jump_dates_by_year": pd.DataFrame(flags).query("kind == 'jump'").date.str[:4].value_counts().sort_index()
        .to_dict() if flags else {},
        "insar": ins,
    }
    (OUT / "c0_summary.json").write_text(json.dumps(summ, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(summ, indent=2, ensure_ascii=False, default=str))


def _maps(w):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    use = w[(w.valid_days_overlap >= 1500) & w.lon.notna() & (w.well_no <= 4)]
    for col, label, cmap, sym in (("trend_m_yr", "head trend 2015-01 → 2024-08 (m/yr)", "jet_r", True),
                                  ("seasonal_amp_m", "seasonal amplitude of the head (m)", "viridis", False),
                                  ("month_of_min", "month of the lowest head", "twilight", False)):
        fig, axs = plt.subplots(1, 4, figsize=(16, 5.2), sharex=True, sharey=True)
        v = use[col]
        lim = np.nanpercentile(np.abs(v), 100) if sym else None
        for k, ax in enumerate(axs, start=1):
            s = use[use.well_no == k]
            kw = {"vmin": -lim, "vmax": lim} if sym else ({"vmin": 1, "vmax": 13} if col == "month_of_min"
                                                          else {"vmin": 0, "vmax": np.nanmax(v)})
            sc = ax.scatter(s.lon, s.lat, c=s[col], cmap=cmap, s=40, edgecolors="none", **kw)
            ax.set_title(f"well (no. {k}) · n = {len(s)}")
            ax.set_aspect(1 / np.cos(np.radians(23.7)))
            ax.grid(alpha=0.3)
        fig.colorbar(sc, ax=axs, label=label, shrink=0.8)
        fig.suptitle(f"Choshui fan, {label}")
        fig.savefig(OUT / "maps" / f"{col}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
