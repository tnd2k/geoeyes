"""Aspect of the landslides of a study (docs/en/research/landslide-susceptibility.md §5 L2a).

Is the aspect signal of an inventory a property of the slopes, or of the mapping? Hypotheses:

    A0  confounding         aspect stands in for slope, relief, curvature or location
    A1  illumination        fewer landslides mapped where the light was dim or ridges cast shadows
    A2  misregistration     the inventory is shifted against the DEM
    A3  storm exposure      slopes facing into the storm wind during the heaviest rain fail more
    A4  physics             the same signal for two events on the same ground

Data: the L1 labels (scarp positives, the main footprint's negatives, every draw, each negative weighted 1 / draws)
and the L2 predictors. Aspect θ is the azimuth of the downslope direction (clockwise from north); cells flatter than
``MIN_SLOPE_DEG`` have none and are left out.

1  frequency ratio (positives / negatives) in 16 sectors, with a 2 km block bootstrap, by slope class
2  logistic models: base = B-spline of slope + relief + curvatures + TWI; + harmonics (sin θ, cos θ, sin 2θ, cos 2θ):
   likelihood-ratio test, amplitude and phase of the first harmonic (the azimuth of the highest odds), with and
   without 2 km blocks as fixed effects (location removed)
3  illumination: cos i = cos z cos s + sin z sin s cos(φ_sun − θ) for a grid of suns; base + cos i + cos i × slope
   against the harmonics; cast shadow (horizon towards the best sun) of positives and negatives
4  shift: the scarp cells moved by whole cells; median slope and AUC of slope over the shifts
5  storm exposure: wind at the study area from the IBTrACS tracks (cyclonic flow with 20° inflow), weighted by the
   daily rain of CHIRPS v3 (``sat``: IMERG timing) → the windward index cos(θ − φ_from) against the harmonics
6  same ground: both events in the overlap of their main footprints, event × harmonics interaction
"""
from __future__ import annotations

import itertools
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

MIN_SLOPE_DEG = 2.0
SECTORS = 16
SLOPE_CLASSES = (0, 20, 30, 40, 90)
BLOCK_M = 2000.0
N_BOOT = 200
SUN_AZ = np.arange(90, 201, 5)
SUN_EL = np.arange(30, 71, 5)
SHIFT_CELLS = 3
INFLOW_DEG = 20.0
STORM_RADIUS_KM = 800.0
IBTRACS = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
           "v04r01/access/csv/ibtracs.WP.list.v04r01.csv")
CHIRPS_SAT = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/{y}/chirps-v3.0.sat.{y}.{m:02d}.{d:02d}.tif"
# days of rain behind each event's landslides (the Molave set probably spans the whole October 2020 sequence)
EVENT_WINDOWS = {"Ketsana": ("2009-09-25", "2009-10-02"), "Podul": ("2013-11-10", "2013-11-17"),
                 "Molave": ("2020-10-05", "2020-10-31")}
BASE_TERMS = ("relief_300", "profile_curv", "plan_curv", "twi")
# dry-season suns at 15° N at the sensors' local times (azimuth, elevation): the corners of the plausible range
PLAUSIBLE_SUNS = {"RapidEye 11:00, mid-October": (147, 62), "RapidEye 11:00, late December": (159, 49),
                  "PlanetScope 10:00, mid-October": (126, 52), "PlanetScope 10:00, late December": (142, 42)}
AMPLITUDE_CLASSES = ((2, 20), (20, 30), (30, 90))


# ---------------------------------------------------------------- data
def table(study, event: str, grid_nx: int, footprint: str | None = None) -> pd.DataFrame:
    """Scarp positives and the negatives (all draws) of a footprint (default the main one) of an event, with their
    predictors."""
    fp = footprint or study.footprint_main
    lab = pd.read_parquet(study.step_dir("labels") / f"labels_{event}.parquet")
    lab = lab[(lab.variant == "scarp") & ((lab.label == 1) | (lab.footprint == fp))]
    pred = pd.read_parquet(study.step_dir("predictors") / f"predictors_{event}.parquet")
    t = lab[["cell", "label", "draw", "src_fid", "area_m2"]].merge(pred, on="cell", how="inner")
    draws = max(1, int(lab.draw.max()) + 1)
    t["w"] = np.where(t.label == 1, 1.0, 1.0 / draws)
    t["theta"] = np.degrees(np.arctan2(t.aspect_sin, t.aspect_cos)) % 360
    t["event"] = event
    ky, kx = np.divmod(t.cell.to_numpy(), grid_nx)
    k = int(round(BLOCK_M / study.labels.cell_m))
    t["block"] = (ky // k) * 100_000 + kx // k
    return t[t.slope_deg >= MIN_SLOPE_DEG].reset_index(drop=True)


# ---------------------------------------------------------------- 1 frequency ratio
def sector_ratio(theta: np.ndarray, label: np.ndarray, w: np.ndarray, n: int = SECTORS) -> np.ndarray:
    """Frequency ratio per aspect sector: share of the positives / share of the (weighted) negatives."""
    s = ((theta + 180 / n) % 360 // (360 / n)).astype(int)
    pos = np.bincount(s[label == 1], minlength=n).astype(float)
    neg = np.bincount(s[label == 0], weights=w[label == 0], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (pos / pos.sum()) / (neg / neg.sum())


def block_bootstrap(t: pd.DataFrame, fn, n: int = N_BOOT, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    blocks = t.block.unique()
    groups = {b: g.index.to_numpy() for b, g in t.groupby("block")}
    out = []
    for _ in range(n):
        idx = np.concatenate([groups[b] for b in rng.choice(blocks, len(blocks), replace=True)])
        out.append(fn(t.loc[idx]))
    return np.array(out)


def describe(t: pd.DataFrame) -> dict:
    def fr(x):
        return sector_ratio(x.theta.to_numpy(), x.label.to_numpy(), x.w.to_numpy())
    res = {}
    for lo, hi in [(SLOPE_CLASSES[0], SLOPE_CLASSES[-1]), *itertools.pairwise(SLOPE_CLASSES)]:
        x = t[(t.slope_deg >= lo) & (t.slope_deg < hi)].reset_index(drop=True)
        if (x.label == 1).sum() < 30:
            continue
        b = block_bootstrap(x, fr)
        res[f"{lo}-{hi}"] = {"positives": int((x.label == 1).sum()), "fr": np.round(fr(x), 3).tolist(),
                             "lo": np.round(np.nanpercentile(b, 2.5, axis=0), 3).tolist(),
                             "hi": np.round(np.nanpercentile(b, 97.5, axis=0), 3).tolist()}
    return res


# ---------------------------------------------------------------- 2 logistic models
def logit(x: np.ndarray, y: np.ndarray, w: np.ndarray, ridge: float = 1e-4) -> tuple[np.ndarray, float]:
    """Weighted logistic regression (intercept added, a tiny ridge for stability); returns (beta, deviance)."""
    from scipy.optimize import minimize
    xx = np.column_stack([np.ones(len(y)), x])

    def f(b):
        z = xx @ b
        ll = w * (y * z - np.logaddexp(0, z))
        p = 1 / (1 + np.exp(-z))
        return -ll.sum() + ridge * (b[1:] @ b[1:]), -(xx.T @ (w * (y - p))) + 2 * ridge * np.r_[0, b[1:]]
    r = minimize(f, np.zeros(xx.shape[1]), jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    return r.x, 2 * float(f(r.x)[0] - ridge * (r.x[1:] @ r.x[1:]))


def base_design(t: pd.DataFrame) -> np.ndarray:
    from sklearn.preprocessing import SplineTransformer
    sp = SplineTransformer(n_knots=5, degree=3, include_bias=False).fit_transform(t[["slope_deg"]].to_numpy())
    z = t[list(BASE_TERMS)].astype(float)
    z = ((z - z.mean()) / z.std()).fillna(0).to_numpy()
    return np.column_stack([sp, z])


def harmonics(theta: np.ndarray) -> np.ndarray:
    r = np.radians(theta)
    return np.column_stack([np.sin(r), np.cos(r), np.sin(2 * r), np.cos(2 * r)])


def blocks_design(t: pd.DataFrame) -> np.ndarray:
    codes = pd.Categorical(t.block).codes
    m = np.zeros((len(t), codes.max() + 1))
    m[np.arange(len(t)), codes] = 1
    return m[:, 1:]


def first_harmonic(beta_h: np.ndarray) -> tuple[float, float]:
    """Amplitude (log-odds) and azimuth of the highest odds of the first harmonic (b_sin, b_cos)."""
    return float(math.hypot(beta_h[0], beta_h[1])), float(math.degrees(math.atan2(beta_h[0], beta_h[1])) % 360)


def conditional(t: pd.DataFrame, n_boot: int = N_BOOT) -> dict:
    from scipy.stats import chi2
    y, w = t.label.to_numpy(float), t.w.to_numpy()
    base, h = base_design(t), harmonics(t.theta.to_numpy())
    out = {}
    for name, extra in (("location free", None), ("2 km blocks", blocks_design(t))):
        b0 = base if extra is None else np.column_stack([base, extra])
        _, d0 = logit(b0, y, w)
        beta, d1 = logit(np.column_stack([b0, h]), y, w)
        amp, az = first_harmonic(beta[-4:])
        out[name] = {"deviance_base": round(d0, 1), "deviance_harmonics": round(d1, 1),
                     "lr": round(d0 - d1, 1), "p": float(chi2.sf(d0 - d1, 4)),
                     "amplitude": round(amp, 3), "azimuth_deg": round(az, 1),
                     "second_harmonic": [round(float(v), 3) for v in beta[-2:]]}

    def boot(x):
        bb = logit(np.column_stack([base_design(x), harmonics(x.theta.to_numpy())]), x.label.to_numpy(float),
                   x.w.to_numpy())[0]
        return first_harmonic(bb[-4:])
    b = block_bootstrap(t, boot, n_boot, seed=1)
    az = b[:, 1]
    centre = out["location free"]["azimuth_deg"]
    dev = (az - centre + 180) % 360 - 180
    out["location free"]["amplitude_ci"] = [round(float(np.percentile(b[:, 0], q)), 3) for q in (2.5, 97.5)]
    out["location free"]["azimuth_ci"] = [round(float((centre + np.percentile(dev, q)) % 360), 1) for q in (2.5, 97.5)]
    return out


# ---------------------------------------------------------------- 3 illumination
def cos_incidence(slope_deg, theta_deg, sun_az, sun_el) -> np.ndarray:
    z, s = np.radians(90 - sun_el), np.radians(slope_deg)
    return np.cos(z) * np.cos(s) + np.sin(z) * np.sin(s) * np.cos(np.radians(sun_az - np.asarray(theta_deg)))


def illumination(t: pd.DataFrame) -> dict:
    y, w = t.label.to_numpy(float), t.w.to_numpy()
    base = base_design(t)
    _, d0 = logit(base, y, w)
    _, dh = logit(np.column_stack([base, harmonics(t.theta.to_numpy())]), y, w)
    sz = ((t.slope_deg - t.slope_deg.mean()) / t.slope_deg.std()).to_numpy()
    dev = np.full((len(SUN_EL), len(SUN_AZ)), np.nan)
    for i, el in enumerate(SUN_EL):
        for j, az in enumerate(SUN_AZ):
            c = cos_incidence(t.slope_deg.to_numpy(), t.theta.to_numpy(), az, el)
            c = (c - c.mean()) / c.std()
            dev[i, j] = logit(np.column_stack([base, c, c * sz]), y, w)[1]
    i, j = np.unravel_index(np.nanargmin(dev), dev.shape)
    return {"deviance_base": round(d0, 1), "deviance_harmonics": round(dh, 1),
            "aic_harmonics": round(dh + 2 * 4, 1), "deviance_best_sun": round(float(dev[i, j]), 1),
            "aic_best_sun": round(float(dev[i, j]) + 2 * 2, 1),
            "best_sun": {"azimuth": int(SUN_AZ[j]), "elevation": int(SUN_EL[i])},
            "surface": {"azimuth": SUN_AZ.tolist(), "elevation": SUN_EL.tolist(),
                        "deviance": np.round(dev, 1).tolist()}}


def by_slope_class(t: pd.DataFrame, n_boot: int = 50) -> dict:
    """First-harmonic amplitude per slope class, against what illumination predicts: under A1 the contrast between
    slopes facing the sun and facing away grows like sin(slope), so the amplitude should grow with it."""
    out = {}
    for lo, hi in AMPLITUDE_CLASSES:
        x = t[(t.slope_deg >= lo) & (t.slope_deg < hi)].reset_index(drop=True)
        if (x.label == 1).sum() < 50:
            continue
        c = conditional(x, n_boot)["location free"]
        out[f"{lo}-{hi}"] = {"positives": int((x.label == 1).sum()), "amplitude": c["amplitude"],
                             "amplitude_ci": c["amplitude_ci"], "azimuth_deg": c["azimuth_deg"],
                             "mean_sin_slope": round(float(np.sin(np.radians(x.slope_deg)).mean()), 3)}
    keys = list(out)
    if len(keys) >= 2:
        a, b = out[keys[0]], out[keys[-1]]
        out["steep_over_gentle"] = {"observed": round(b["amplitude"] / a["amplitude"], 2) if a["amplitude"] else None,
                                    "illumination_predicts": round(b["mean_sin_slope"] / a["mean_sin_slope"], 2)}
    return out


def plausible_suns(t: pd.DataFrame, height: np.ndarray, rows: np.ndarray, cols: np.ndarray, cell_m: float) -> dict:
    """Deviance of base + cos i and the shares in cast shadow at the plausible suns."""
    y, w = t.label.to_numpy(float), t.w.to_numpy()
    base = base_design(t)
    sz = ((t.slope_deg - t.slope_deg.mean()) / t.slope_deg.std()).to_numpy()
    pos, neg = (t.label == 1).to_numpy(), (t.label == 0).to_numpy()
    out = {}
    for name, (az, el) in PLAUSIBLE_SUNS.items():
        c = cos_incidence(t.slope_deg.to_numpy(), t.theta.to_numpy(), az, el)
        c = (c - c.mean()) / c.std()
        shade = cast_shadow(height, rows, cols, cell_m, az, el)
        out[name] = {"azimuth": az, "elevation": el,
                     "deviance": round(logit(np.column_stack([base, c, c * sz]), y, w)[1], 1),
                     "shadow_positives": round(float(shade[pos].mean()), 4),
                     "shadow_negatives": round(float(np.average(shade[neg], weights=w[neg])), 4)}
    return out


def cast_shadow(height: np.ndarray, rows: np.ndarray, cols: np.ndarray, cell_m: float, sun_az: float,
                sun_el: float, max_m: float = 3000.0) -> np.ndarray:
    """True where a cell lies in the shadow of the terrain towards the sun (``height`` rows go north)."""
    de, dn = math.sin(math.radians(sun_az)), math.cos(math.radians(sun_az))
    h0 = height[rows, cols]
    best = np.full(len(rows), -np.inf)
    for k in range(1, int(max_m / cell_m) + 1):
        r = np.clip(np.rint(rows + k * dn).astype(int), 0, height.shape[0] - 1)
        c = np.clip(np.rint(cols + k * de).astype(int), 0, height.shape[1] - 1)
        best = np.maximum(best, np.degrees(np.arctan((height[r, c] - h0) / (k * cell_m))))
    return best > sun_el


# ---------------------------------------------------------------- 4 shift
def shift_surface(t: pd.DataFrame, pred: pd.DataFrame, nx: int, n: int = SHIFT_CELLS) -> dict:
    """Median slope and AUC of slope (and of northness) of the positives moved by (dx, dy) whole cells."""
    from geoeyes.landslide.predictors import univariate_auc
    look = pred.set_index("cell")
    pos, neg = t[t.label == 1], t[t.label == 0]            # the negatives stay where they are
    rows = []
    for dy in range(-n, n + 1):
        for dx in range(-n, n + 1):
            ky, kx = np.divmod(pos.cell.to_numpy(), nx)
            cells = (ky + dy) * nx + (kx + dx)
            s = look.reindex(cells)[["slope_deg", "aspect_cos"]].dropna()
            rows.append({"dx": dx, "dy": dy, "n": int(len(s)),
                         "median_slope": round(float(s.slope_deg.median()), 2),
                         "auc_slope": univariate_auc(s.slope_deg, neg.slope_deg),
                         "auc_northness": univariate_auc(s.aspect_cos, neg.aspect_cos)})
    return {"rows": rows, "best": max(rows, key=lambda r: (r["auc_slope"] or 0))}


# ---------------------------------------------------------------- 5 storm exposure
def ibtracs(cache: Path) -> pd.DataFrame:
    import urllib.request
    f = cache / "ibtracs.WP.list.v04r01.csv"
    if not f.exists():
        cache.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".part")
        urllib.request.urlretrieve(IBTRACS, tmp)
        tmp.replace(f)
    t = pd.read_csv(f, skiprows=[1], usecols=["SID", "SEASON", "NAME", "ISO_TIME", "LAT", "LON"],
                    low_memory=False)
    t["time"] = pd.to_datetime(t.ISO_TIME)
    return t


def wind_from(lat_c, lon_c, lat_p: float, lon_p: float) -> np.ndarray:
    """Azimuth the wind comes from at (lat_p, lon_p) for cyclones centred at (lat_c, lon_c), northern hemisphere:
    counter-clockwise tangential flow turned INFLOW_DEG towards the centre."""
    e = (lon_p - np.asarray(lon_c)) * 111.32 * math.cos(math.radians(lat_p))
    n = (lat_p - np.asarray(lat_c)) * 110.54
    r = np.hypot(e, n)
    re, rn = e / r, n / r                                    # outward radial unit vector
    te, tn = -rn, re                                         # counter-clockwise tangent
    a = math.radians(INFLOW_DEG)
    we, wn = math.cos(a) * te - math.sin(a) * re, math.cos(a) * tn - math.sin(a) * rn
    return (np.degrees(np.arctan2(-we, -wn)) % 360), r


def daily_rain(cache: Path, bounds, start: str, end: str) -> pd.Series:
    """Mean daily rain (mm) of CHIRPS v3 ``sat`` over ``bounds``, cached as CSV."""
    import rasterio
    from rasterio.windows import from_bounds

    from geoeyes.ml.layers import _ENV
    f = cache / f"chirps3_sat_daily_{start}_{end}_{'_'.join(f'{v:.2f}' for v in bounds)}.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)["rain_mm"]
    out = {}
    for day in pd.date_range(start, end):
        url = CHIRPS_SAT.format(y=day.year, m=day.month, d=day.day)
        with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + url) as src:
            win = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win, boundless=True).astype(float)
            if src.nodata is not None:
                a[a == src.nodata] = np.nan
        a[a < 0] = np.nan
        out[day] = float(np.nanmean(a))
    s = pd.Series(out, name="rain_mm")
    cache.mkdir(parents=True, exist_ok=True)
    s.to_csv(f)
    return s


def storm_exposure(event: str, area_bounds, cache: Path) -> dict:
    """Rain-weighted wind directions at the study area during the event window."""
    start, end = EVENT_WINDOWS[event]
    lon_p, lat_p = (area_bounds[0] + area_bounds[2]) / 2, (area_bounds[1] + area_bounds[3]) / 2
    rain = daily_rain(cache / "rainfall", area_bounds, start, end)
    tr = ibtracs(cache / "opendata" / "ibtracs")
    tr = tr[(tr.time >= pd.Timestamp(start)) & (tr.time < pd.Timestamp(end) + pd.Timedelta(days=1))]
    days = []
    for day, mm in rain.items():
        x = tr[(tr.time >= day) & (tr.time < day + pd.Timedelta(days=1))]       # both in UTC days
        frm, dist = wind_from(x.LAT.to_numpy(float), x.LON.to_numpy(float), lat_p, lon_p) if len(x) else ([], [])
        near = np.asarray(dist) < STORM_RADIUS_KM if len(x) else np.array([], bool)
        rec = {"date": day.date().isoformat(), "rain_mm": round(float(mm), 1), "storms": sorted(set(x.NAME[near])) if
               len(x) else []}
        if near.any():
            ang = np.radians(np.asarray(frm)[near])
            rec["wind_from_deg"] = round(float(np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360), 1)
            rec["distance_km"] = round(float(np.asarray(dist)[near].min()), 0)
        days.append(rec)
    vec = sum(d["rain_mm"] * np.exp(1j * math.radians(d["wind_from_deg"])) for d in days if "wind_from_deg" in d)
    total = sum(d["rain_mm"] for d in days)
    storm_rain = sum(d["rain_mm"] for d in days if "wind_from_deg" in d)
    return {"window": [start, end], "days": days, "rain_total_mm": round(total, 1),
            "rain_with_storm_wind_mm": round(storm_rain, 1),
            "effective_wind_from_deg": round(float(np.degrees(np.angle(vec)) % 360), 1) if storm_rain else None,
            "coherence": round(float(abs(vec) / storm_rain), 3) if storm_rain else None}


def windward_test(t: pd.DataFrame, wind_from_deg: float) -> dict:
    """Base + windward index cos(θ − φ_from), against base + harmonics."""
    y, w = t.label.to_numpy(float), t.w.to_numpy()
    base = base_design(t)
    _, d0 = logit(base, y, w)
    _, dh = logit(np.column_stack([base, harmonics(t.theta.to_numpy())]), y, w)
    ww = np.cos(np.radians(t.theta.to_numpy() - wind_from_deg))
    beta, dw = logit(np.column_stack([base, ww]), y, w)
    return {"deviance_base": round(d0, 1), "deviance_windward": round(dw, 1), "aic_windward": round(dw + 2, 1),
            "deviance_harmonics": round(dh, 1), "aic_harmonics": round(dh + 8, 1), "coef": round(float(beta[-1]), 3)}


# ---------------------------------------------------------------- 6 same ground
def same_ground(tables: dict[str, pd.DataFrame], study) -> dict:
    from scipy.stats import chi2
    names = list(tables)
    if len(names) < 2:
        return {}
    a, b = names[:2]
    flag_a, flag_b = f"in_{study.footprint_main}_{a}", f"in_{study.footprint_main}_{b}"
    parts = [t[t[flag_a] & t[flag_b]] for t in tables.values()][:2]
    x = pd.concat(parts, ignore_index=True)
    if (x.label == 1).groupby(x.event).sum().min() < 30:
        return {"positives": (x.label == 1).groupby(x.event).sum().to_dict(), "note": "too few positives"}
    y, w = x.label.to_numpy(float), x.w.to_numpy()
    ev = (x.event == b).to_numpy(float)[:, None]
    base = np.column_stack([base_design(x), ev, base_design(x) * ev])      # each event its own terrain response
    h = harmonics(x.theta.to_numpy())
    _, d1 = logit(np.column_stack([base, h]), y, w)
    beta, d2 = logit(np.column_stack([base, h, h * ev]), y, w)
    amp_a, az_a = first_harmonic(beta[-8:-4])
    amp_b, az_b = first_harmonic(beta[-8:-4] + beta[-4:])
    return {"positives": {k: int(v) for k, v in (x.label == 1).groupby(x.event).sum().items()},
            "lr_interaction": round(d1 - d2, 1), "p": float(chi2.sf(d1 - d2, 4)),
            "first_harmonic": {a: {"amplitude": round(amp_a, 3), "azimuth_deg": round(az_a, 1)},
                               b: {"amplitude": round(amp_b, 3), "azimuth_deg": round(az_b, 1)}}}


# ---------------------------------------------------------------- the study step
def run_aspect(study, cache_root: Path, progress=None) -> dict:
    """L2a of a study: ``aspect/aspect.json``, ``aspect.md``, figures, manifest."""
    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.landslide.labels import grid_for, study_area
    from geoeyes.landslide.terrain import padded_grid, raster
    from geoeyes.ml.layers import M_PER_DEG_LAT
    say = progress or (lambda m: log.info("%s", m))
    area = study_area(study)
    grid = grid_for(area.bounds, study.labels.cell_m)
    big, ox, oy = padded_grid(grid)
    pad = 5000 / M_PER_DEG_LAT
    w, s, e, n = grid.bounds
    dem = load_copernicus30(s - pad, n + pad, w - pad, e + pad, cache_root / "dem" / "copernicus-30")
    height = raster(big, dem.orthometric(big.lat, big.lon))
    out_dir = study.step_dir("aspect")
    out_dir.mkdir(parents=True, exist_ok=True)
    res: dict = {"study": study.name, "citation": study.citation, "min_slope_deg": MIN_SLOPE_DEG,
                 "block_m": BLOCK_M, "n_boot": N_BOOT, "shift_step_m": study.labels.cell_m, "events": {}}
    tables = {}
    for name, _ in study.events:
        say(f"aspect: {name}")
        t = table(study, name, grid.nx)
        tables[name] = t
        pred = pd.read_parquet(study.step_dir("predictors") / f"predictors_{name}.parquet",
                               columns=["cell", "slope_deg", "aspect_cos"])
        r: dict = {"positives": int((t.label == 1).sum()), "negatives": int((t.label == 0).sum())}
        say("  1 frequency ratio")
        r["frequency_ratio"] = {study.footprint_main: describe(t)}
        th = table(study, name, grid.nx, study.footprint_sensitivity)
        r["frequency_ratio"][study.footprint_sensitivity] = {k: v for k, v in describe(th).items() if k == "0-90"}
        say("  2 conditional models")
        r["conditional"] = conditional(t)
        say("  3 illumination")
        r["illumination"] = illumination(t)
        ky, kx = np.divmod(t.cell.to_numpy(), grid.nx)
        r["illumination"]["plausible_suns"] = plausible_suns(t, height, ky + oy, kx + ox, grid.cell_m)
        r["illumination"]["by_slope_class"] = by_slope_class(t)
        say("  4 shift")
        r["shift"] = shift_surface(t, pred, grid.nx)
        say("  5 storm exposure")
        try:
            r["storm"] = storm_exposure(name, area.bounds, cache_root)
            if r["storm"]["effective_wind_from_deg"] is not None:
                r["storm"]["test"] = windward_test(t, r["storm"]["effective_wind_from_deg"])
        except Exception as exc:                                 # a missing source leaves the test out
            r["storm"] = {"error": str(exc)}
            log.warning("storm exposure of %s not computed: %s", name, exc)
        res["events"][name] = r
    say("aspect: 6 same ground")
    res["same_ground"] = same_ground(tables, study)
    files = plot_roses(res, out_dir) + plot_surfaces(res, out_dir)
    atomic_write_json(out_dir / "aspect.json", res)
    (out_dir / "aspect.md").write_text(report_md(res), encoding="utf-8")
    files += ["aspect.json", "aspect.md"]
    m = Manifest(kind="landslide_aspect", id=f"{study.name}/aspect", engine="geoeyes.landslide.aspect",
                 inputs=[InputRef("labels", str(study.step_dir("labels"))),
                         InputRef("predictors", str(study.step_dir("predictors"))),
                         InputRef("tracks", IBTRACS), InputRef("rain", "CHIRPS v3 daily sat"),
                         InputRef("dem", "Copernicus GLO-30")],
                 params={"min_slope_deg": MIN_SLOPE_DEG, "block_m": BLOCK_M, "n_boot": N_BOOT,
                         "sun_az": [int(SUN_AZ[0]), int(SUN_AZ[-1])], "sun_el": [int(SUN_EL[0]), int(SUN_EL[-1])],
                         "shift_cells": SHIFT_CELLS, "inflow_deg": INFLOW_DEG, "windows": EVENT_WINDOWS},
                 metrics={ev: {"lr_harmonics": r["conditional"]["location free"]["lr"],
                               "azimuth_deg": r["conditional"]["location free"]["azimuth_deg"]}
                          for ev, r in res["events"].items()})
    m.add_outputs(out_dir, files)
    m.write(out_dir)
    return res


def _sector_centres() -> np.ndarray:
    return np.arange(SECTORS) * 360 / SECTORS


def plot_roses(res: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = []
    th = np.radians(_sector_centres())
    width = 2 * np.pi / SECTORS * 0.9
    for ev, r in res["events"].items():
        fr = next(iter(r["frequency_ratio"].values()))
        keys = list(fr)
        fig, axs = plt.subplots(1, len(keys), figsize=(3.6 * len(keys), 4), subplot_kw={"projection": "polar"})
        for ax, k in zip(np.atleast_1d(axs), keys, strict=True):
            v, lo, hi = (np.array(fr[k][x], float) for x in ("fr", "lo", "hi"))
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            ax.bar(th, v, width=width, color=np.where(v >= 1, "#d62728", "#1f77b4"), alpha=0.75)
            ax.errorbar(th, v, yerr=[v - lo, hi - v], fmt="none", ecolor="k", lw=0.6)
            ax.plot(np.r_[th, th[0]], np.ones(SECTORS + 1), "k--", lw=0.6)
            ax.set_title(f"slope {k}° (n={fr[k]['positives']})", fontsize=9)
            ax.tick_params(labelsize=7)
        fig.suptitle(f"{ev}: frequency ratio of the landslides by aspect (downslope azimuth); dashed = 1; "
                     "bars: 95 % block bootstrap", fontsize=9)
        fig.tight_layout()
        name = f"aspect_rose_{ev}.png"
        fig.savefig(out_dir / name, dpi=110)
        plt.close(fig)
        out.append(name)
    return out


def plot_surfaces(res: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    evs = list(res["events"])
    fig, axs = plt.subplots(2, len(evs), figsize=(5.5 * len(evs), 8.5), squeeze=False)
    for j, ev in enumerate(evs):
        il = res["events"][ev]["illumination"]
        sf = il["surface"]
        d = np.array(sf["deviance"], float) - il["deviance_base"]
        ax = axs[0, j]
        im = ax.imshow(d, origin="lower", aspect="auto", cmap="viridis_r",
                       extent=(sf["azimuth"][0] - 2.5, sf["azimuth"][-1] + 2.5, sf["elevation"][0] - 2.5,
                               sf["elevation"][-1] + 2.5))
        ax.plot(il["best_sun"]["azimuth"], il["best_sun"]["elevation"], "r*", ms=12)
        ax.add_patch(plt.Rectangle((126, 42), 159 - 126, 62 - 42, fill=False, ec="red", ls="--"))
        ax.set_title(f"{ev}: Δ deviance of base + cos i (harmonics: "
                     f"{il['deviance_harmonics'] - il['deviance_base']:.1f})", fontsize=9)
        ax.set_xlabel("sun azimuth (°)")
        ax.set_ylabel("sun elevation (°)")
        fig.colorbar(im, ax=ax, fraction=0.04)
        sh = pd.DataFrame(res["events"][ev]["shift"]["rows"])
        g = sh.pivot(index="dy", columns="dx", values="auc_slope")
        ax = axs[1, j]
        im = ax.imshow(g.to_numpy(), origin="lower", cmap="magma",
                       extent=(g.columns.min() - .5, g.columns.max() + .5, g.index.min() - .5, g.index.max() + .5))
        b = res["events"][ev]["shift"]["best"]
        ax.plot(b["dx"], b["dy"], "c*", ms=12)
        ax.set_title(f"{ev}: AUC of slope with the positives shifted (cells of {res['shift_step_m']:.0f} m)",
                     fontsize=9)
        ax.set_xlabel("dx (cells east)")
        ax.set_ylabel("dy (cells north)")
        fig.colorbar(im, ax=ax, fraction=0.04)
    fig.suptitle("L2a: illumination (red box: the plausible dry-season suns) and inventory shift", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_dir / "aspect_surfaces.png", dpi=100)
    plt.close(fig)
    return ["aspect_surfaces.png"]


def report_md(res: dict) -> str:
    L = [f"# L2a aspect — {res['study']}", "", f"Inventory: {res['citation']}", "",
         f"Cells flatter than {res['min_slope_deg']}° left out; 2 km block bootstrap ({res['n_boot']} draws).", ""]
    for ev, r in res["events"].items():
        c = r["conditional"]
        il = r["illumination"]
        L += [f"## {ev}", "", f"Positives {r['positives']}, negatives {r['negatives']} (all draws, weighted).", "",
              "### Conditional models (harmonics of aspect over slope spline, relief, curvatures, TWI)", "",
              "| Model | LR (4 df) | p | First harmonic: amplitude, azimuth of highest odds |", "|---|---|---|---|"]
        for k, v in c.items():
            ci = f" [{v['amplitude_ci'][0]}–{v['amplitude_ci'][1]}], [{v['azimuth_ci'][0]}–{v['azimuth_ci'][1]}°]" \
                if "amplitude_ci" in v else ""
            L.append(f"| {k} | {v['lr']} | {v['p']:.2g} | {v['amplitude']}, {v['azimuth_deg']}°{ci} |")
        L += ["", "### Illumination", "",
              f"- Δ deviance from the base: harmonics (4 df) {il['deviance_harmonics'] - il['deviance_base']:.1f}; "
              f"best sun cos i (2 df) {il['deviance_best_sun'] - il['deviance_base']:.1f}",
              f"- AIC: harmonics {il['aic_harmonics']}, best sun {il['aic_best_sun']}",
              f"- best sun: azimuth {il['best_sun']['azimuth']}°, elevation {il['best_sun']['elevation']}° "
              "(plausible dry-season suns: azimuth 126–159°, elevation 42–62°)", "",
              "| Plausible sun | Az, el | Δ deviance (2 df) | In cast shadow: positives | negatives |",
              "|---|---|---|---|---|"]
        L += [f"| {k} | {v['azimuth']}°, {v['elevation']}° | {v['deviance'] - il['deviance_base']:.1f} | "
              f"{v['shadow_positives']:.1%} | {v['shadow_negatives']:.1%} |" for k, v in il["plausible_suns"].items()]
        bs = il["by_slope_class"]
        L += ["", "| Slope class | Positives | Amplitude [95 %] | Azimuth | mean sin(slope) |", "|---|---|---|---|---|"]
        L += [f"| {k} | {v['positives']} | {v['amplitude']} [{v['amplitude_ci'][0]}–{v['amplitude_ci'][1]}] | "
              f"{v['azimuth_deg']}° | {v['mean_sin_slope']} |" for k, v in bs.items() if k != "steep_over_gentle"]
        if "steep_over_gentle" in bs:
            g = bs["steep_over_gentle"]
            L.append(f"\nSteepest / gentlest class amplitude: observed {g['observed']}, illumination predicts "
                     f"{g['illumination_predicts']}.")
        L += ["", "### Shift", ""]
        b = r["shift"]["best"]
        z = next(x for x in r["shift"]["rows"] if x["dx"] == 0 and x["dy"] == 0)
        L += [f"- no shift: median slope {z['median_slope']}°, AUC slope {z['auc_slope']}, "
              f"AUC northness {z['auc_northness']}",
              f"- best: dx {b['dx']}, dy {b['dy']} cells: median slope {b['median_slope']}°, AUC slope "
              f"{b['auc_slope']}, AUC northness {b['auc_northness']}", "", "### Storm exposure", ""]
        st = r.get("storm", {})
        if "error" in st:
            L.append(f"- not computed: {st['error']}")
        else:
            L += [f"- window {st['window'][0]} → {st['window'][1]}: rain {st['rain_total_mm']} mm, of which "
                  f"{st['rain_with_storm_wind_mm']} mm with a storm within {STORM_RADIUS_KM:.0f} km",
                  f"- rain-weighted wind from {st['effective_wind_from_deg']}° (coherence {st['coherence']})"]
            if "test" in st:
                tt = st["test"]
                L.append(f"- windward index: Δ deviance {tt['deviance_windward'] - tt['deviance_base']:.1f} (1 df), "
                         f"coef {tt['coef']}; AIC windward {tt['aic_windward']} vs harmonics {tt['aic_harmonics']}")
            L += ["", "| Day | Rain (mm) | Storms | Wind from (°) |", "|---|---|---|---|"]
            L += [f"| {d['date']} | {d['rain_mm']} | {', '.join(d['storms'])} | {d.get('wind_from_deg', '')} |"
                  for d in st["days"] if d["rain_mm"] >= 5]
        L.append("")
    sg = res.get("same_ground", {})
    L += ["## Same ground (overlap of the main footprints)", ""]
    if "lr_interaction" in sg:
        L += [f"- positives: {sg['positives']}",
              f"- event × harmonics interaction: LR {sg['lr_interaction']} (4 df), p = {sg['p']:.2g}"]
        L += [f"- {k}: amplitude {v['amplitude']}, azimuth {v['azimuth_deg']}°"
              for k, v in sg["first_harmonic"].items()]
    else:
        L.append(f"- {sg}")
    return "\n".join(L) + "\n"
