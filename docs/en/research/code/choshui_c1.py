"""C1 of choshui-groundwater.md: the MintPy product as a foreign product, and a first look at the well stations.

1. Products: `geoeyes.products.foreign.import_mintpy` (run separately) wrote
   projects/choshui_mintpy/products/choshui_mintpy_s1-{asc-069,desc-105}_*_v1 (200 m blocks).
2. Station series, from the native 40 m pixels (not the blocks): median of the valid pixels within RADIUS_M of
   each well station, per track; LOS (mm, + toward the satellite, zero at the first date) and the vertical
   projection LOS / l_u (assumes no horizontal motion; C3 does the decomposition).
3. Maps of the LOS velocity of both products with the stations; a first look at 5 stations chosen by rule (no
   statistics: C4 does that).

Outputs in studies/choshui_gw/c1/. Usage: python -I -X utf8 choshui_c1.py
"""
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
STUDY = Path(r"D:\projects\geoeyes_workspace\studies\choshui_gw")
PRODUCTS = Path(r"D:\projects\geoeyes_workspace\projects\choshui_mintpy\products")
TRACKS = {"asc": (Path(r"C:\Users\duong\Downloads\timeseries_SET_ERA5_ramp_demErr-001.h5"),
                  STUDY / "data" / "insar_asc" / "geometryGeo.h5", "s1-asc-069"),
          "desc": (Path(r"C:\Users\duong\Downloads\timeseries_SET_ERA5_ramp_demErr-002.h5"),
                   STUDY / "data" / "insar_desc" / "geometryGeo.h5", "s1-desc-105")}
OUT = STUDY / "c1"
RADIUS_M = 200.0


def station_series(wells: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Per track: dates and (stations × dates) LOS series (mm) from the native pixels; and per station l_u."""
    st = wells.dropna(subset=["x_utm50"]).groupby("station")[["x_utm50", "y_utm50", "lon", "lat"]].first()
    res, info = {}, []
    for k, (ts_p, g_p, _) in TRACKS.items():
        with h5py.File(ts_p, "r") as f, h5py.File(g_p, "r") as g:
            a = f.attrs
            x0, y0, dx, dy = (float(a[n]) for n in ("X_FIRST", "Y_FIRST", "X_STEP", "Y_STEP"))
            ny, nx = f["timeseries"].shape[1:]
            ry, rx = int(a["REF_Y"]), int(a["REF_X"])
            dates = np.array([np.datetime64(f"{s[:4]}-{s[4:6]}-{s[6:]}") for s in
                              (d.decode() for d in f["date"][()])])
            w = int(np.ceil(RADIUS_M / abs(dx)))
            ser = np.full((len(st), len(dates)), np.nan, np.float32)
            for i, (name, r) in enumerate(st.iterrows()):
                c, rr = int((r.x_utm50 - x0) / dx), int((r.y_utm50 - y0) / dy)
                if not (w <= rr < ny - w and w <= c < nx - w):
                    continue
                blk = f["timeseries"][:, rr - w:rr + w + 1, c - w:c + w + 1] * 1000.0
                yy, xx = np.mgrid[-w:w + 1, -w:w + 1]
                inside = np.hypot(yy * dy, xx * dx) <= RADIUS_M
                land = g["waterMask"][rr - w:rr + w + 1, c - w:c + w + 1].astype(bool)
                valid = inside & land & ~np.all(blk == 0, axis=0)
                if not (rr - w <= ry <= rr + w and c - w <= rx <= c + w) and valid.sum() < 3:
                    continue
                inc = g["incidenceAngle"][rr - w:rr + w + 1, c - w:c + w + 1][valid]
                lu = float(np.cos(np.radians(np.median(inc)))) if valid.any() else np.nan
                ser[i] = np.median(blk[:, valid], axis=1) if valid.any() else np.nan
                info.append({"station": name, "track": k, "n_pixels": int(valid.sum()), "los_u": lu})
            ser -= ser[:, :1]                                        # zero at the first date
            res[k] = {"dates": dates, "series": ser, "stations": st.index.to_numpy()}
    return res, pd.DataFrame(info)


def velocity(dates, ser, t0=None, t1=None):
    t = (dates - dates[0]).astype(float) / 365.25
    sel = np.ones(len(dates), bool) if t0 is None else (dates >= np.datetime64(t0)) & (dates <= np.datetime64(t1))
    g = np.column_stack([np.ones(sel.sum()), t[sel]])
    out = np.full(ser.shape[0], np.nan)
    ok = np.all(np.isfinite(ser[:, sel]), axis=1)
    if ok.any():
        out[ok] = np.linalg.lstsq(g, ser[ok][:, sel].T, rcond=None)[0][1]
    return out


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    OUT.mkdir(parents=True, exist_ok=True)
    wells = pd.read_parquet(STUDY / "c0" / "wells.parquet")
    use = wells[(wells.valid_days_overlap >= 1500) & wells.lon.notna()]       # only current IDs reach 1,500 days
    res, info = station_series(use)
    info.to_csv(OUT / "station_pixels.csv", index=False)
    lu = info.pivot(index="station", columns="track", values="los_u")
    npx = info.pivot(index="station", columns="track", values="n_pixels")
    rows = []
    for k, r in res.items():
        v = velocity(r["dates"], r["series"], "2015-01-01", "2024-08-20")
        for s, vv in zip(r["stations"], v, strict=True):
            rows.append({"station": s, "track": k, "vel_los_mm_yr": vv})
        np.savez_compressed(OUT / f"station_series_{k}.npz", dates=r["dates"].astype(str), series=r["series"],
                            stations=r["stations"])
    sv = pd.DataFrame(rows).pivot(index="station", columns="track", values="vel_los_mm_yr")
    sv.columns = [f"vel_{c}_mm_yr" for c in sv.columns]
    sv = sv.join(lu.add_prefix("lu_")).join(npx.add_prefix("npx_"))
    sv["vert_asc_mm_yr"] = sv.vel_asc_mm_yr / sv.lu_asc
    sv["vert_desc_mm_yr"] = sv.vel_desc_mm_yr / sv.lu_desc
    st = use.groupby("station")[["lon", "lat"]].first()
    sv = sv.join(st)
    sv.to_csv(OUT / "station_velocity.csv")

    # maps of the two products (200 m blocks) with the stations
    fig, axs = plt.subplots(1, 2, figsize=(15, 8), sharex=True, sharey=True)
    for ax, (k, (_, _, trk)) in zip(axs, TRACKS.items(), strict=True):
        prod = sorted(PRODUCTS.glob(f"choshui_mintpy_{trk}_*_v*"))[-1]
        p = pd.read_parquet(prod / "points.parquet", columns=["lon", "lat", "vel_los_mm_yr"])
        v = p.vel_los_mm_yr.to_numpy()
        sc = ax.scatter(p.lon, p.lat, c=v, s=1.5, cmap="jet_r", vmin=np.nanmin(v), vmax=np.nanmax(v),
                        edgecolors="none", rasterized=True)
        ax.scatter(st.lon, st.lat, s=18, facecolors="none", edgecolors="k", linewidths=0.6)
        ax.set_title(f"MintPy {trk}: LOS velocity 2015–2026 (min {np.nanmin(v):.0f}, max {np.nanmax(v):.0f} mm/yr)")
        ax.set_aspect(1 / np.cos(np.radians(23.8)))
        fig.colorbar(sc, ax=ax, shrink=0.7, label="mm/yr, + toward the satellite")
    fig.savefig(OUT / "velocity_maps.png", dpi=110, bbox_inches="tight")
    plt.close(fig)

    # five stations by rule (documented in c1_report.md)
    ok = sv.dropna(subset=["vert_asc_mm_yr", "vert_desc_mm_yr"])
    vert = ok[["vert_asc_mm_yr", "vert_desc_mm_yr"]].mean(axis=1)
    amp = use[use.well_no <= 2].groupby("station").seasonal_amp_m.max()
    picks = {"fastest sinking": vert.idxmin(), "largest seasonal head swing": amp.reindex(ok.index).idxmax(),
             "northernmost": ok.lat.idxmax(), "easternmost (fan apex)": ok.lon.idxmax(),
             "westernmost (coast)": ok.lon.idxmin()}
    mon = pd.read_parquet(STUDY / "c0" / "heads_monthly.parquet")
    mon["month"] = pd.to_datetime(mon.month)
    fig, axs = plt.subplots(len(picks), 1, figsize=(13, 3.3 * len(picks)), sharex=True)
    for ax, (why, s) in zip(axs, picks.items(), strict=True):
        ax2 = ax.twinx()
        for _, wr in use[use.station == s].sort_values("well_no").iterrows():
            h = mon[mon.key == wr.key]
            ax.plot(h.month, h.head_m, lw=0.9, label=f"head, well {wr.well_no} ({wr.depth_m:.0f} m)")
        for k, col in (("asc", "tab:red"), ("desc", "tab:blue")):
            r = res[k]
            i = int(np.where(r["stations"] == s)[0][0])
            ax2.plot(pd.to_datetime(r["dates"]), r["series"][i] / sv.loc[s, f"lu_{k}"], lw=0.6, color=col,
                     alpha=0.8, label=f"InSAR {k}, LOS / l_u")
        ax.axvspan(pd.Timestamp("2021-01-01"), pd.Timestamp("2021-12-31"), color="0.9", zorder=-1)
        ax.set_ylabel("head (m)")
        ax2.set_ylabel("vertical (mm)")
        ax.set_title(f"{s} — {why}: vertical ≈ {vert.get(s, np.nan):.0f} mm/yr (mean of the two tracks)", fontsize=9)
        ax.legend(loc="lower left", fontsize=7)
        ax2.legend(loc="upper right", fontsize=7)
    fig.savefig(OUT / "first_look_5_stations.png", dpi=100, bbox_inches="tight")
    plt.close(fig)

    summ = {"stations_with_series": {k: int(np.isfinite(r["series"][:, -1]).sum()) for k, r in res.items()},
            "picks": picks,
            "vertical_mm_yr_quantiles": {k: ok[f"vert_{k}_mm_yr"].quantile([0.05, 0.5, 0.95]).round(1).to_dict()
                                         for k in ("asc", "desc")},
            "asc_minus_desc_vertical_mm_yr": (ok.vert_asc_mm_yr - ok.vert_desc_mm_yr).describe().round(1).to_dict(),
            "corr_vertical_asc_desc": round(float(np.corrcoef(ok.vert_asc_mm_yr, ok.vert_desc_mm_yr)[0, 1]), 3)}
    (OUT / "c1_summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summ, indent=2, default=str))


if __name__ == "__main__":
    main()
