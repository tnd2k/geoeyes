"""Can a GNSS calibration fitted in one place be used in another?

Pairs: (product, station) with the InSAR median series near the station and the GNSS vertical projected on the LOS,
both on a common zero (analyses/gnss/<pid>/series.npz).

Models of the GNSS-InSAR relation, fitted on a source, applied to a target:
  M1 offset        g(t) = i(t) + dv * t                 (the current calibration: a reference rate)
  M2 offset+scale  g(t) = k * i(t) + dv * t + c          (k: a processing gain, the only term that might transfer)

Metrics at the target stations: rate residual |v_g - v_corrected| and the series RMSE after correction.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\projects\geoeyes_workspace\projects")
PAIRS = {
    "MX-S1asc078": ("mexico_s1", "mexico_s1_sentinel1-asc-078_20240503_20241030_v7"),
    "HN-S1asc128": ("hanoi_s1", "hanoi_s1_sentinel1-asc-128_20251004_20261018_v6"),
    "HN-S1desc091": ("hanoi_s1", "hanoi_s1_sentinel1-desc-091_20251001_20261015_v4"),
}


def load(tag):
    proj, pid = PAIRS[tag]
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
        out.append({"tag": tag, "site": s["site"], "t": ty[ok], "i": i[ok] - i[ok].mean(), "g": g[ok] - g[ok].mean(),
                    "vstat": s["vertical"]})
    return out


def rate(t, y):
    A = np.column_stack([t, np.ones_like(t)])
    return float(np.linalg.lstsq(A, y, rcond=None)[0][0])


def fit_m1(pairs):
    return {"dv": float(np.mean([rate(p["t"], p["g"]) - rate(p["t"], p["i"]) for p in pairs]))}


def fit_m2(pairs):
    """Stacked LSQ of g = k i + dv t + c_s (one constant per station); returns k, dv and the sigma of k."""
    rows, ys = [], []
    for j, p in enumerate(pairs):
        for tt, ii, gg in zip(p["t"], p["i"], p["g"], strict=True):
            c = [0.0] * len(pairs)
            c[j] = 1.0
            rows.append([ii, tt, *c])
            ys.append(gg)
    A, y = np.array(rows), np.array(ys)
    x, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ x
    dof = max(len(y) - A.shape[1], 1)
    cov = np.linalg.pinv(A.T @ A) * (res @ res / dof)
    cond = np.linalg.cond(A[:, :2] - A[:, :2].mean(0))
    return {"k": float(x[0]), "dv": float(x[1]), "k_sigma": float(np.sqrt(cov[0, 0])), "cond": float(cond)}


def apply(model, p):
    k = model.get("k", 1.0)
    corr = k * p["i"] + model["dv"] * p["t"]
    corr -= corr.mean()
    return {"rate_res": abs(rate(p["t"], p["g"]) - rate(p["t"], corr)), "rmse": float(np.sqrt(np.mean((p["g"] - corr) ** 2)))}


data = {k: load(k) for k in PAIRS}
print("== pairs (vertical LOS, mm/yr)")
for tag, ps in data.items():
    for p in ps:
        v = p["vstat"]
        print(f"{tag:13s} {p['site']}: InSAR {v['rate_insar_mm_yr']:+8.1f}  GNSS {v['rate_gnss_mm_yr']:+8.1f} ± {v['rate_gnss_se']:.1f}"
              f"  diff {v['rate_diff_mm_yr']:+7.1f}  RMSE detrended {v['rmse_detrended_mm']:.1f} mm  r {v['corr']:+.2f}  n {len(p['t'])}")

print("\n== fits")
fits = {}
for tag, ps in data.items():
    fits[tag] = {"M1": fit_m1(ps), "M2": fit_m2(ps)}
    m2 = fits[tag]["M2"]
    print(f"{tag:13s} M1 dv {fits[tag]['M1']['dv']:+8.1f} | M2 k {m2['k']:+.2f} ± {m2['k_sigma']:.2f}  dv {m2['dv']:+8.1f}"
          f"  cond(i,t) {m2['cond']:.1f}")

print("\n== transfer: source -> target (mean over the target stations)")
print(f"{'source':13s} {'target':13s} {'model':5s} {'rate residual':>14s} {'series RMSE':>12s}")
for tgt in ("HN-S1asc128", "HN-S1desc091"):
    base = [apply({"dv": 0.0}, p) for p in data[tgt]]
    print(f"{'(none)':13s} {tgt:13s} {'-':5s} {np.mean([b['rate_res'] for b in base]):14.1f} {np.mean([b['rmse'] for b in base]):12.1f}")
    for src in PAIRS:
        for mname in ("M1", "M2"):
            if src == tgt:
                # same product: leave-one-out over its two stations
                r = []
                for j, p in enumerate(data[tgt]):
                    others = [q for k_, q in enumerate(data[tgt]) if k_ != j]
                    m = fit_m1(others) if mname == "M1" else fit_m2(others)
                    r.append(apply(m, p))
                label = "LOO"
            else:
                m = fits[src][mname]
                r = [apply(m, p) for p in data[tgt]]
                label = src
            print(f"{label:13s} {tgt:13s} {mname:5s} {np.mean([x['rate_res'] for x in r]):14.1f} {np.mean([x['rmse'] for x in r]):12.1f}")

print("\n== what the Mexico offset is: the scene-mean reference")
pm = ROOT / "mexico_s1" / "products" / PAIRS["MX-S1asc078"][1] / "points.parquet"
import pyarrow.parquet as pq
v = pq.read_table(pm, columns=["vel_los_mm_yr"])["vel_los_mm_yr"].to_numpy()
print(f"Mexico product: mean InSAR LOS rate {np.nanmean(v):+.1f}, median {np.nanmedian(v):+.1f} mm/yr (scene-mean reference -> ~0)")
print(f"=> dv {fits['MX-S1asc078']['M1']['dv']:+.1f} mm/yr is the motion of Mexico's reference itself, i.e. a property of "
      f"that scene, not of the sensor or the processing")
