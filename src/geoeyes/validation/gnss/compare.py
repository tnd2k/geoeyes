"""InSAR against GNSS, and GNSS calibration of the InSAR series (docs/en/research/gnss-insar-calibration.md).

Per station inside the product (NGL, ``ngl``):

1. GNSS: cleaned daily ENU, averaged over ±``window_days`` around each InSAR epoch;
2. InSAR: median series of the points within ``radius_m`` of the antenna (at least ``min_points``);
3. GNSS in the line of sight, two ways:
   * ``full``: d = e·l_e + n·l_n + u·l_u (every component; includes the motion of the tectonic plate in IGS20);
   * ``vertical``: d = u·l_u (the horizontal motion is taken as the plate's, uniform over the scene, so it is
     part of the InSAR reference and cancels; what is compared is the local vertical motion);
4. both series are put on a common zero (their mean over the shared epochs), then: rates and their difference,
   RMSE, RMSE after removing the linear trend of the difference (agreement in shape), correlation.

Calibration (``calibration``) of the InSAR with the stations' LOS (``los_mode``):

* ``offset``: one rate added to every point, Δv = mean over the stations of (v_GNSS − v_InSAR);
* ``plane``: Δv = a + b·x + c·y fitted to the stations (at least 3), for an orbital / reference ramp;
* ``epoch``: a correction per epoch c(t) = median over the stations of (GNSS(t) − InSAR(t)), the common mode
  of the reference area (it carries the GNSS daily noise into every point).

With two stations or more, every station is also predicted by a calibration made without it (leave one out):
the honest measure of what GNSS calibration gives where there is no station.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.io.points import timeseries_arrays
from geoeyes.validation.gnss import ngl

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.gnss/1"
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON = 111_320.0
DAYS_PER_YEAR = 365.2425


@dataclass(frozen=True)
class GnssParams:
    """``[validation.gnss]`` of project.toml (every key optional)."""

    source: str = "ngl"
    radius_m: float = 100.0                 # InSAR points around the antenna
    min_points: int = 5
    window_days: int = 3                    # GNSS days averaged around each InSAR epoch (± days)
    min_epochs: int = 6                     # shared epochs needed to compare a station
    los_mode: str = "vertical"              # vertical | full (see the module docstring)
    calibration: str = "offset"             # offset | plane | epoch
    gnss_rate: str = "window"               # window (GNSS rate over the InSAR period) | midas (NGL long-term rate)
    stations: tuple[str, ...] = ()          # only these stations (default: every NGL station in the product)
    exclude: tuple[str, ...] = ()           # stations left out (bad monument, moved antenna, ...)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> GnssParams:
        d = {k: v for k, v in dict(d or {}).items() if k not in _LEGACY_KEYS}
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[validation.gnss]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for f in fields(cls):
            if f.name in d:
                default = getattr(cls, f.name)
                v = d[f.name]
                out[f.name] = tuple(str(s).upper() for s in v) if isinstance(default, tuple) else type(default)(v)
        p = cls(**out)
        if p.source != "ngl":
            raise ConfigError("[validation.gnss] source: only 'ngl' (Nevada Geodetic Laboratory) for now")
        if p.los_mode not in ("vertical", "full"):
            raise ConfigError("[validation.gnss] los_mode: vertical | full")
        if p.calibration not in ("offset", "plane", "epoch"):
            raise ConfigError("[validation.gnss] calibration: offset | plane | epoch")
        if p.gnss_rate not in ("window", "midas"):
            raise ConfigError("[validation.gnss] gnss_rate: window | midas")
        return p


_LEGACY_KEYS = {"n_rovers"}                 # written by the legacy config migration


def _fit(t: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Rate (per year) and its standard error, ordinary least squares."""
    a = np.column_stack([np.ones_like(t), t])
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    r = y - a @ coef
    dof = max(len(t) - 2, 1)
    cov = np.linalg.pinv(a.T @ a) * (r @ r) / dof
    return float(coef[1]), float(math.sqrt(max(cov[1, 1], 0.0)))


def _stats(t: np.ndarray, insar: np.ndarray, gnss: np.ndarray) -> dict:
    ok = np.isfinite(insar) & np.isfinite(gnss)
    t, a, b = t[ok], insar[ok] - insar[ok].mean(), gnss[ok] - gnss[ok].mean()
    va, sa = _fit(t, a)
    vb, sb = _fit(t, b)
    diff = a - b
    vd, _ = _fit(t, diff)
    detr = diff - np.polyval(np.polyfit(t, diff, 1), t)
    corr = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else None
    return {"n_epochs": int(ok.sum()), "rate_insar_mm_yr": round(va, 2), "rate_insar_se": round(sa, 2),
            "rate_gnss_mm_yr": round(vb, 2), "rate_gnss_se": round(sb, 2),
            "rate_diff_mm_yr": round(vb - va, 2),
            "rmse_mm": round(float(np.sqrt(np.mean(diff ** 2))), 2),
            "rmse_detrended_mm": round(float(np.sqrt(np.mean(detr ** 2))), 2),
            "corr": None if corr is None else round(corr, 3), "diff_rate_mm_yr": round(vd, 2)}


def _epoch_mean(day: np.ndarray, enu: np.ndarray, epochs: np.ndarray, window: int) -> np.ndarray:
    """GNSS ENU (m) averaged within ±window days of each epoch; NaN where no day falls in."""
    out = np.full((epochs.size, 3), np.nan)
    for i, e in enumerate(epochs):
        sel = np.abs((day - e).astype(np.int64)) <= window
        if sel.any():
            out[i] = enu[sel].mean(axis=0)
    return out


def compare(product: Path, out: Path, params: GnssParams, cache: Path, progress=None) -> dict:
    """Compare a product with the NGL stations inside it and fit the calibration; written to ``out``."""
    say = progress or (lambda msg: log.info("%s", msg))
    p = params
    names = set(pq.read_schema(product / "points.parquet").names)
    for c in ("los_e", "los_n", "los_u"):
        if c not in names:
            raise DataError(f"{product.name}: no {c} column (line of sight needed to project the GNSS)")
    pts = pq.read_table(product / "points.parquet", columns=["point_uid", "lon", "lat", "los_e", "los_n", "los_u"])
    lon = pts["lon"].to_numpy().astype(np.float64)
    lat = pts["lat"].to_numpy().astype(np.float64)
    los = np.column_stack([pts[c].to_numpy().astype(np.float64) for c in ("los_e", "los_n", "los_u")])
    dates, series = timeseries_arrays(product / "timeseries.parquet", pts["point_uid"].to_numpy(zero_copy_only=False))
    ts = series["disp_mm"]
    t_yr = (dates - dates[0]).astype(np.float64) / DAYS_PER_YEAR
    bbox = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]
    lat0 = float(np.median(lat))
    kx = M_PER_DEG_LON * math.cos(math.radians(lat0))

    say(f"NGL stations over {[round(v, 3) for v in bbox]}, {dates[0]} .. {dates[-1]}")
    found = ngl.stations_in(cache, bbox, str(dates[0]), str(dates[-1]))
    if p.stations:
        found = found[found["site"].isin(p.stations)]
    rows, arrays, warnings = [], {}, []
    for st in found.itertuples():
        info: dict[str, Any] = {"site": st.site, "lon": round(st.lon, 6), "lat": round(st.lat, 6),
                                "first": str(st.first.date()), "last": str(st.last.date()), "used": False}
        rows.append(info)
        if st.site in p.exclude:
            info["reason"] = "excluded in [validation.gnss]"
            continue
        try:
            raw = ngl.series(cache, st.site)
            cl = ngl.clean(raw, st.site, dates[0] - 30, dates[-1] + 30, ngl.equipment_steps(cache, st.site))
        except DataError as exc:
            info["reason"] = str(exc)
            continue
        info.update({"lon": round(cl.lon, 6), "lat": round(cl.lat, 6), "segments": cl.segments,
                     "jumps": cl.jumps, "outliers": cl.outliers, "notes": cl.notes})
        dist = np.hypot((lon - cl.lon) * kx, (lat - cl.lat) * M_PER_DEG_LAT)
        near = np.flatnonzero(dist <= p.radius_m)
        info["n_points"] = int(near.size)
        if near.size < p.min_points:
            info["reason"] = f"{near.size} InSAR points within {p.radius_m:g} m (needs {p.min_points})"
            continue
        insar = np.nanmedian(ts[near], axis=0).astype(np.float64)
        spread = np.nanstd(ts[near], axis=0).astype(np.float64)
        lv = np.median(los[near], axis=0)
        lv /= np.linalg.norm(lv)
        g = _epoch_mean(cl.date, cl.enu, dates, p.window_days) * 1000.0           # mm
        g_full = g @ lv
        g_vert = g[:, 2] * lv[2]
        shared = np.isfinite(g_full) & np.isfinite(insar)
        info["n_epochs"] = int(shared.sum())
        if shared.sum() < p.min_epochs:
            info["reason"] = f"{int(shared.sum())} epochs with GNSS (needs {p.min_epochs})"
            continue
        day_t = (cl.date - cl.date[0]).astype(np.float64) / DAYS_PER_YEAR
        info["gnss_rate_enu_mm_yr"] = [round(_fit(day_t, cl.enu[:, c] * 1000)[0], 2) for c in range(3)]
        info["los"] = [round(float(v), 4) for v in lv]
        info["median_distance_m"] = round(float(np.median(dist[near])), 1)
        info["full"] = _stats(t_yr, insar, g_full)
        info["vertical"] = _stats(t_yr, insar, g_vert)
        mid = ngl.midas(cache, st.site)
        if mid:
            v = np.asarray(mid["enu_mm_yr"])
            mid["los_full_mm_yr"] = round(float(v @ lv), 2)
            mid["los_vertical_mm_yr"] = round(float(v[2] * lv[2]), 2)
            for mode in ("full", "vertical"):
                rate = mid[f"los_{mode}_mm_yr"] - info[mode]["rate_insar_mm_yr"]
                info[mode]["rate_diff_midas_mm_yr"] = round(rate, 2)
            if cl.segments > 1:
                mid["note"] = "the station moved or changed equipment: the long-term rate may mix two monuments"
        info["midas"] = mid
        info["used"] = True
        arrays[st.site] = {"insar": insar, "spread": spread, "gnss_full": g_full, "gnss_vertical": g_vert,
                           "day": cl.date.astype("datetime64[D]").astype(str), "enu_mm": cl.enu * 1000.0}
        say(f"{st.site}: {near.size} points within {p.radius_m:g} m, rate diff "
            f"{info[p.los_mode]['rate_diff_mm_yr']:+.1f} mm/yr ({p.los_mode}), RMSE {info[p.los_mode]['rmse_mm']} mm")
    used = [r for r in rows if r["used"]]
    if not found.size:
        warnings.append("no NGL station inside the product over its period")
    elif not used:
        warnings.append("no NGL station could be compared (see the reasons per station)")

    calib = calibrate(used, arrays, t_yr, p, lat0, bbox) if used else None
    if calib:
        warnings += calib.pop("warnings", [])

    out.mkdir(parents=True, exist_ok=True)
    flat: dict[str, np.ndarray] = {"dates": dates.astype(str)}
    for s, a in arrays.items():
        for k, v in a.items():
            flat[f"{s}__{k}"] = np.asarray(v)
    np.savez(out / "series.npz", **flat)
    summary = {"schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
               "params": {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(p).items()},
               "source": ngl.SOURCE, "frame": ngl.FRAME, "dates": [str(d) for d in dates], "bounds": bbox,
               "stations": rows, "calibration": calib, "warnings": warnings,
               "method": "docs/en/research/gnss-insar-calibration.md"}
    atomic_write_json(out / "comparison.json", summary)
    m = Manifest(kind="gnss_comparison", id=product.name, engine=SCHEMA,
                 inputs=[InputRef("product", str(product))], params=summary["params"],
                 metrics={"stations_used": len(used)})
    m.add_outputs(out, ["comparison.json", "series.npz"])
    m.write(out)
    return summary


def calibrate(used: list[dict], arrays: dict, t_yr: np.ndarray, p: GnssParams, lat0: float, bbox) -> dict:
    """The calibration of ``p.calibration`` from the compared stations, with a leave-one-out check."""
    mode = p.los_mode
    warnings: list[str] = []
    xs = np.array([(r["lon"] - (bbox[0] + bbox[2]) / 2) * M_PER_DEG_LON * math.cos(math.radians(lat0)) / 1000
                   for r in used])
    ys = np.array([(r["lat"] - (bbox[1] + bbox[3]) / 2) * M_PER_DEG_LAT / 1000 for r in used])
    key = "rate_diff_mm_yr"
    if p.gnss_rate == "midas":
        key = "rate_diff_midas_mm_yr"
        missing = [r["site"] for r in used if key not in r[mode]]
        if missing:
            warnings.append(f"no MIDAS velocity for {missing}: their rate over the InSAR period is used")
    dv = np.array([r[mode].get(key, r[mode]["rate_diff_mm_yr"]) for r in used])
    kind = p.calibration
    if kind == "plane" and len(used) < 3:
        warnings.append(f"plane calibration needs 3 stations, {len(used)} compared: offset used instead")
        kind = "offset"

    def model(idx: np.ndarray) -> np.ndarray:
        """Coefficients of the rate correction from the stations ``idx``: [a] or [a, b, c] (mm/yr, per km)."""
        if kind == "plane" and idx.size >= 3:
            a = np.column_stack([np.ones(idx.size), xs[idx], ys[idx]])
            return np.linalg.lstsq(a, dv[idx], rcond=None)[0]
        return np.array([dv[idx].mean()])

    def predict(coef: np.ndarray, x: float, y: float) -> float:
        return float(coef[0] + (coef[1] * x + coef[2] * y if coef.size == 3 else 0.0))

    out: dict[str, Any] = {"kind": kind, "los_mode": mode, "gnss_rate": p.gnss_rate,
                           "stations": [r["site"] for r in used]}
    coef = model(np.arange(len(used)))
    out["rate_coef"] = [round(float(c), 4) for c in coef]
    out["rate_offset_mm_yr"] = round(float(coef[0]), 2)
    if kind == "epoch":
        diffs = []
        for r in used:
            a = arrays[r["site"]]
            g, s = a[f"gnss_{mode}"], a["insar"]
            ok = np.isfinite(g) & np.isfinite(s)
            d = np.full(t_yr.size, np.nan)
            d[ok] = (g[ok] - g[ok].mean()) - (s[ok] - s[ok].mean())
            diffs.append(d)
        c = np.nanmedian(np.vstack(diffs), axis=0)
        good = np.isfinite(c)
        c = np.interp(t_yr, t_yr[good], c[good]) if good.sum() >= 2 else np.zeros_like(t_yr)
        out["epoch_mm"] = [round(float(v), 3) for v in c - c[0]]
        if len(used) == 1:
            warnings.append("epoch calibration from one station: its daily GNSS noise goes into every point")
    if len(used) >= 2:
        loo = []
        for i, r in enumerate(used):
            others = np.array([j for j in range(len(used)) if j != i])
            pred = predict(model(others), xs[i], ys[i])
            loo.append({"site": r["site"], "rate_diff_before_mm_yr": float(dv[i]),
                        "rate_diff_after_mm_yr": round(float(dv[i] - pred), 2)})
        out["leave_one_out"] = loo
        out["loo_rms_before_mm_yr"] = round(float(np.sqrt(np.mean(dv ** 2))), 2)
        out["loo_rms_after_mm_yr"] = round(float(np.sqrt(np.mean([v["rate_diff_after_mm_yr"] ** 2 for v in loo]))),
                                           2)
    else:
        warnings.append("one station: the calibration ties the reference to it but cannot be checked "
                        "independently (leave-one-out needs two stations)")
    out["centre"] = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    out["lat0"] = lat0
    out["warnings"] = warnings
    return out


def correction(calib: dict, dates: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """LOS correction (mm) to add to series at ``dates`` for points at ``lon`` / ``lat``: (points, epochs)."""
    dates = np.asarray(dates, dtype="datetime64[D]")
    t = (dates - dates[0]).astype(np.float64) / DAYS_PER_YEAR
    if calib["kind"] == "epoch" and calib.get("epoch_mm"):
        return np.broadcast_to(np.asarray(calib["epoch_mm"], np.float64)[None, :], (lon.size, t.size)).copy()
    coef = np.asarray(calib["rate_coef"], np.float64)
    rate = np.full(lon.size, coef[0])
    if coef.size == 3:
        cx, cy = calib["centre"]
        x = (lon - cx) * M_PER_DEG_LON * math.cos(math.radians(calib["lat0"])) / 1000
        y = (lat - cy) * M_PER_DEG_LAT / 1000
        rate = rate + coef[1] * x + coef[2] * y
    return rate[:, None] * t[None, :]


def read_comparison(folder: Path) -> dict | None:
    f = folder / "comparison.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
