"""G7: a historical GNSS calibration of HCMC (S1 desc 018, 2017-11 → 2019-09) and its transfer to 2025-2026.

1. Leave-one-out over the three NGL stations of 2017-2019 (HCMC, LTHA, XC03), vertical projection:
   M0 none, M1 offset (g = i + dv t), M2 offset and scale (g = k i + dv t + c_s).
2. Transfer in time to the 2025-2026 product of the same track (S1 desc 018, 2025-01 → 2026-10). Both products are
   referenced to their own scene mean, over different footprints, so the tie is
       v_2025(tied) = v_2025 + dv + [mean_2017(footprint 2025) - mean_2017(footprint 2017)]
   which assumes the mean motion of the 2025 footprint did not change between the two periods. The check: the
   rate change at the same 20 m cells, overall and on the cells that were stable in 2017-2019.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\projects\geoeyes_workspace\projects")
HIST = ("hcm_hist_des", "hcm_hist_des_sentinel1-desc-018_20171101_20190910_v1")
NOW = ("hcm_test_des", "hcm_test_des_sentinel1-desc-018_20250117_20261010_v1")
CELL_DEG = 20 / 111_320                                         # ~20 m


def load_pairs(proj, pid):
    d = ROOT / proj / "analyses" / "gnss" / pid
    comp = json.loads((d / "comparison.json").read_text(encoding="utf-8"))
    z = np.load(d / "series.npz")
    t = np.array([np.datetime64(s) for s in z["dates"].astype(str)])
    ty = (t - t[0]).astype("timedelta64[D]").astype(float) / 365.25
    out = []
    for s in comp["stations"]:
        if not s.get("used") or f"{s['site']}__insar" not in z.files:
            continue
        i, g = z[f"{s['site']}__insar"].astype(float), z[f"{s['site']}__gnss_vertical"].astype(float)
        ok = np.isfinite(i) & np.isfinite(g)
        out.append({"site": s["site"], "t": ty[ok], "i": i[ok] - i[ok].mean(), "g": g[ok] - g[ok].mean(),
                    "v": s["vertical"]})
    return out


def rate(t, y):
    return float(np.linalg.lstsq(np.column_stack([t, np.ones_like(t)]), y, rcond=None)[0][0])


def fit_m1(pairs):
    return {"dv": float(np.mean([rate(p["t"], p["g"]) - rate(p["t"], p["i"]) for p in pairs]))}


def fit_m2(pairs):
    rows, ys = [], []
    for j, p in enumerate(pairs):
        for tt, ii, gg in zip(p["t"], p["i"], p["g"], strict=True):
            c = [0.0] * len(pairs)
            c[j] = 1.0
            rows.append([ii, tt, *c])
            ys.append(gg)
    x, *_ = np.linalg.lstsq(np.array(rows), np.array(ys), rcond=None)
    return {"k": float(x[0]), "dv": float(x[1])}


def apply(model, p):
    corr = model.get("k", 1.0) * p["i"] + model.get("dv", 0.0) * p["t"]
    corr -= corr.mean()
    return rate(p["t"], p["g"]) - rate(p["t"], corr), float(np.sqrt(np.mean((p["g"] - corr) ** 2)))


def vertical_points(proj, pid):
    t = pq.read_table(ROOT / proj / "products" / pid / "points.parquet",
                      columns=["lon", "lat", "vel_los_mm_yr", "incidence_deg"]).to_pandas()
    t["v"] = t["vel_los_mm_yr"] / np.cos(np.radians(t["incidence_deg"]))     # vertical, as the GNSS comparison
    return t


def cells(df):
    key = (np.floor(df["lon"] / CELL_DEG).astype(np.int64) * 10_000_000 + np.floor(df["lat"] / CELL_DEG).astype(np.int64))
    return df.assign(cell=key).groupby("cell")["v"].median()


# ------------------------------------------------------------------ 1. leave-one-out in 2017-2019
pairs = load_pairs(*HIST)
print("== 2017-2019 stations (vertical, mm/yr)")
for p in pairs:
    v = p["v"]
    print(f"{p['site']}: InSAR {v['rate_insar_mm_yr']:+6.1f}  GNSS {v['rate_gnss_mm_yr']:+6.1f} ± {v['rate_gnss_se']:.1f}"
          f"  diff {v['rate_diff_mm_yr']:+5.1f}  n {len(p['t'])}")
print("\n== leave-one-out: rate residual at the left-out station (GNSS - corrected InSAR), series RMSE")
loo = {}
for name, fit in (("M0", lambda ps: {}), ("M1", fit_m1), ("M2", fit_m2)):
    res = []
    for j, p in enumerate(pairs):
        m = fit([q for k, q in enumerate(pairs) if k != j])
        r, e = apply(m, p)
        res.append((p["site"], r, e, m))
    rms = float(np.sqrt(np.mean([r ** 2 for _, r, _, _ in res])))
    loo[name] = rms
    print(f"{name}: " + "  ".join(f"{s} {r:+5.1f} ({e:.1f} mm)" for s, r, e, _ in res) + f"  | RMS {rms:.1f} mm/yr")
    if name == "M2":
        print("     k fitted on the other two: " + ", ".join(f"{m['k']:+.2f}" for _, _, _, m in res))
m1_all = fit_m1(pairs)
print(f"M1 on all three: dv {m1_all['dv']:+.2f} mm/yr")

# ------------------------------------------------------------------ 2. transfer to 2025-2026
hist, now = vertical_points(*HIST), vertical_points(*NOW)
w, s, e, n = now["lon"].min(), now["lat"].min(), now["lon"].max(), now["lat"].max()
inside = hist[(hist["lon"] >= w) & (hist["lon"] <= e) & (hist["lat"] >= s) & (hist["lat"] <= n)]
shift = float(inside["v"].mean() - hist["v"].mean())
print(f"\n== reference of the two frames (vertical): 2017 scene mean {hist['v'].mean():+.2f}, "
      f"2017 mean over the 2025 footprint {inside['v'].mean():+.2f} -> frame shift {shift:+.2f} mm/yr; "
      f"2025 scene mean {now['v'].mean():+.2f}")
tie = m1_all["dv"] + shift
ch, cn = cells(inside), cells(now)
common = ch.index.intersection(cn.index)
d_raw = (cn[common] - ch[common]).to_numpy()
d_tied = (cn[common] + tie - (ch[common] + m1_all["dv"])).to_numpy()
stable = np.abs(ch[common].to_numpy() + m1_all["dv"]) < 2.0
print(f"common 20 m cells: {common.size:,} of {cn.size:,} (2025) / {ch.size:,} (2017)")
print(f"rate change 2025 - 2017, both GNSS-tied: median {np.median(d_tied):+.2f}, IQR {np.subtract(*np.percentile(d_tied, [75, 25])):.2f}"
      f" mm/yr (untied {np.median(d_raw):+.2f})")
print(f"  on the cells stable in 2017-2019 (|v| < 2 mm/yr, {stable.sum():,} cells): median {np.median(d_tied[stable]):+.2f},"
      f" IQR {np.subtract(*np.percentile(d_tied[stable], [75, 25])):.2f} mm/yr")
v25 = cn.to_numpy() + tie
print(f"2025-2026 tied vertical rates: p05 {np.percentile(v25, 5):+.1f}, median {np.median(v25):+.1f}, p95 {np.percentile(v25, 95):+.1f};"
      f" area-share sinking > 10 mm/yr {np.mean(v25 < -10) * 100:.1f} % (2017-2019 same footprint: "
      f"{np.mean(ch.to_numpy() + m1_all['dv'] < -10) * 100:.1f} %)")
