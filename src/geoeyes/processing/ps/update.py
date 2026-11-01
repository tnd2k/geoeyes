"""Incremental ``ps`` run: acquisitions appended to a stack after the last date of a previous run are added to its
points, instead of running the engine again on the whole stack (docs/en/guide/incremental.md).

Kept from the previous run: the points (selection and weeding), their DEM error (look-angle error K), their master
error C, the reference and the velocity model. For each new date d, at every point:

    φ_obs   = arg(slc_ref · conj(slc_d))                      wrapped interferogram, as the engine forms it
    φ_topo  = K · B⊥_d                                       B⊥ from the stack's height sensitivity kh
    φ_pred  = -d_pred / (λ/4π)                               displacement predicted by the linear fit of the series
    r       = wrap(φ_obs - φ_topo - φ_pred - C)               atmosphere + unexpected motion + noise
    φ_uw    = φ_topo + φ_pred + C + unwrap_space(r)          r unwrapped on the grid (IRLS), snapped to φ_obs + 2πk
    d       = -(φ_uw - φ_topo - APS - C) · λ/4π              APS: weather model or linear in height (smaller residual)

then referenced as the engine does (reference PS or scene mean). The velocity, acceleration and fit RMSE are fitted
again over all dates; the engine's high-pass correction of the velocity is carried over unchanged.

What an update cannot do: re-select points (new stable / lost scatterers), re-estimate K and the APS of earlier
dates, or separate the spatially correlated noise of the new dates (no temporal window after them: their SCN is
0). After ``full_every`` added dates the pipeline runs the full engine again.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import date
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from geoeyes.core.errors import StoreError
from geoeyes.core.geodesy import geohash
from geoeyes.io.manifest import InputRef, Manifest
from geoeyes.io.points import read_points, write_points, write_timeseries

log = logging.getLogger(__name__)

UPDATE_ENGINE = "geoeyes-ps-update/1"
M_LAT = 110_540.0
M_LON = 111_320.0


def _dates(raw) -> list[str]:
    return [d.decode() if isinstance(d, bytes) else str(d) for d in raw]


def stack_identity(attrs: dict, dates: list[str]) -> dict[str, str]:
    """Per date, what makes its stored SLC what it is: the raw scene signature and the orbit used."""
    sig = attrs.get("scene_signatures") or {}
    orb = attrs.get("orbit_per_date") or {}
    return {d: f"{sig.get(d, '')}|{orb.get(d, '')}" for d in dates}


def plan(prev: Path, store, config_fingerprint: str, full_every: int) -> tuple[list[str], str]:
    """(new dates to add, '') when the previous run in ``prev`` can be extended, else ([], why not)."""
    m = prev / "manifest.json"
    if not m.exists() or not (prev / "state.h5").exists():
        return [], "no previous run"
    pm = Manifest.read(prev)
    extra = pm.extra or {}
    if extra.get("config_fingerprint") != config_fingerprint:
        return [], "parameters changed since the previous run" if extra.get("config_fingerprint") else \
            "the previous run predates incremental updates"
    stack_in = next((i.uri for i in pm.inputs if i.kind == "stack"), "")
    if Path(stack_in).resolve() != Path(store.path).resolve():
        return [], "another stack (reference date changed)"
    with h5py.File(prev / "state.h5", "r") as f:
        old = _dates(f["time/epoch_dates"][()])
    ds = store.open()
    now = [str(np.datetime64(d, "D")) for d in ds["date"].values]
    if not set(old) <= set(now):
        return [], "dates of the previous run are no longer in the stack"
    ident = stack_identity(dict(store.attrs), old)
    if extra.get("stack_identity") and any(extra["stack_identity"].get(d) != ident[d] for d in old):
        return [], "dates of the previous run were coregistered again (new scene or orbit)"
    new = sorted(set(now) - set(old))
    if not new:
        return [], "no new date"
    if new[0] < old[-1]:
        return [], f"new date {new[0]} is not after the last date of the previous run ({old[-1]})"
    done = int((pm.metrics.get("update") or {}).get("dates_since_full", 0))
    if done + len(new) > full_every:
        return [], f"{done + len(new)} dates added since the last full run (full_every = {full_every})"
    return new, ""


def _local_xy(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lat0 = np.radians(np.nanmean(lat))
    return np.column_stack([np.arange(lon.size), (lon - np.nanmean(lon)) * M_LON * np.cos(lat0),
                            (lat - np.nanmean(lat)) * M_LAT])


def unwrap_residual(res: np.ndarray, xy: np.ndarray, grid_size: float, align: bool = False) -> np.ndarray:
    """Spatially unwrap one wrapped phase ``res`` (n,) at the points ``xy`` (n, 3) on a ``grid_size`` grid (cells:
    Gaussian-smoothed complex sum, IRLS weighted by the cell coherence), each point snapped to its own wrapped
    phase + 2πk."""
    from geoeyes.processing.ps.unwrap.grid import grid_wrapped
    from geoeyes.processing.ps.unwrap.interp import interp
    from geoeyes.processing.ps.unwrap.irls import enforce_congruence, irls_unwrap_weighted
    ok = np.isfinite(res)
    z = np.where(ok, np.exp(1j * np.nan_to_num(res)), 0).astype(np.complex64)
    g = grid_wrapped(z[:, None], xy, grid_size=grid_size, prefilt_win=16, gold_alpha=0.8, coh=None,
                     prefilter="gaussian")
    raw = grid_wrapped(z[:, None], xy, grid_size=grid_size, prefilt_win=16, gold_alpha=0.8, coh=None,
                       prefilter="none")
    ui = interp(g.nzix)
    cell = g.ph[:, 0]
    amp = np.abs(cell) / np.maximum(np.abs(raw.ph[:, 0]), 1e-9)       # coherence of the smoothed cell, 0..1
    nrow, ncol = g.nzix.shape
    phase = np.angle(cell[ui.Z]).reshape(nrow, ncol).astype(np.float32)
    w = np.clip(amp[ui.Z].reshape(nrow, ncol), 0.05, 1.0).astype(np.float32) ** 2
    u, _ = irls_unwrap_weighted(phase, w)
    u = enforce_congruence(phase, u, align=align)
    r_ix, c_ix = (g.grid_ij[:, 0] - 1).astype(int), (g.grid_ij[:, 1] - 1).astype(int)
    at = u[r_ix, c_ix]
    out = res + 2 * np.pi * np.round((at - res) / (2 * np.pi))
    return np.where(ok, out, np.nan)


def _fit(disp: np.ndarray, t: np.ndarray, w: np.ndarray):
    """Weighted per-point fits of d = v·t + c and d = a/2·t² + v·t + c (columns with a NaN anywhere left out, as
    the engine): (v_linear, acc, rmse of the quadratic)."""
    keep = ~np.all(np.isnan(disp), axis=0)
    d, tk = np.nan_to_num(disp[:, keep]), t[keep]
    wk = np.diag(w[keep])
    g = np.column_stack([tk, np.ones_like(tk)])
    v = np.linalg.solve(g.T @ wk @ g, g.T @ wk @ d.T).T[:, 0]
    gq = np.column_stack([tk ** 2, tk, np.ones_like(tk)])
    mq = (np.linalg.pinv(gq.T @ wk @ gq) @ gq.T @ wk @ d.T).T
    res = d - (gq @ mq.T).T
    return v, 2.0 * mq[:, 0], np.sqrt(np.mean(res ** 2, axis=1))


def update(store, prev: Path, new_dates: list[str], *, weather=None, grid_size: float = 10.0,
           slc_var: str = "slc", run_id: str = "", track_id: str = "", config_fingerprint: str = "") -> dict:
    """Add ``new_dates`` of ``store`` to the run in ``prev`` (rewritten in place: state.h5, points, time series,
    manifest)."""
    from geoeyes.processing.atmosphere.times import acquisition_times
    from geoeyes.processing.atmosphere.weather import weather_aps
    from geoeyes.processing.ps.aps import centre_weather, linear_aps
    from geoeyes.processing.ps.params import engine_params
    from geoeyes.processing.ps.steps.reference import reference_ps
    t0 = time.time()
    pm = Manifest.read(prev)
    params = json.loads((prev / "params.json").read_text(encoding="utf-8"))
    ds = store.open()
    attrs = dict(store.attrs)
    wl = float(attrs["wavelength_m"])
    lam = wl / (4 * np.pi) * 1000.0                                 # mm per radian
    stack_dates = [str(np.datetime64(d, "D")) for d in ds["date"].values]
    with h5py.File(prev / "state.h5", "r") as f:
        S = {k: f[k][()] for k in ("ps/line", "ps/sample", "ps/lat", "ps/lon", "ps/height_m", "ps/dem_err_m",
                                   "ps/coherence", "ps/bperp", "phase/unwrapped", "phase/scla", "phase/aps",
                                   "phase/aps_linear", "phase/scn", "velocity/v_mm_yr", "velocity/v_linear_mm_yr",
                                   "velocity/disp_mm", "velocity/disp_scn_mm", "velocity/v_scn_mm_yr",
                                   "time/ifg_std_deg")}
        epochs = _dates(f["time/epoch_dates"][()])
        ifg_dates = _dates(f["time/ifg_dates"][()])
    ref_date = str(attrs["reference_date"])
    mi = epochs.index(ref_date)
    line, sample = S["ps/line"].astype(np.int64), S["ps/sample"].astype(np.int64)
    n = line.size
    lat, lon = S["ps/lat"], S["ps/lon"]
    hgt = (S["ps/height_m"] - S["ps/dem_err_m"]).astype(np.float64)        # DEM height above the geoid
    unw, scla, aps = (S[k].astype(np.float64) for k in ("phase/unwrapped", "phase/scla", "phase/aps"))
    bperp = S["ps/bperp"].astype(np.float64)
    disp = S["velocity/disp_mm"].astype(np.float64)                        # (n, epochs), master 0
    sec = [i for i in range(len(epochs)) if i != mi]
    # look-angle error K (scla = K·B⊥) and master error C, per point, from the previous run
    K = np.nansum(scla * bperp, axis=1) / np.maximum(np.nansum(bperp ** 2, axis=1), 1e-12)
    C = np.nanmedian(unw - scla - aps + disp[:, sec] / lam, axis=1)
    day = np.array([date.fromisoformat(d).toordinal() for d in epochs], np.float64)
    t_prev = (day - day[mi]) / 365.25
    std = np.asarray(S["time/ifg_std_deg"], np.float64)
    w_prev = 1.0 / np.maximum(np.delete(std, mi) * np.pi / 180.0, 1e-6) ** 2
    v_prev, _, _ = _fit(disp[:, sec], t_prev[sec], w_prev)
    c_prev = np.nanmedian(disp - v_prev[:, None] * t_prev[None, :], axis=1)
    dv_hp = S["velocity/v_mm_yr"].astype(np.float64) - S["velocity/v_linear_mm_yr"].astype(np.float64)

    prm = engine_params(params.get("effective") or params.get("table") or {}, wavelength=wl, rho=1.0)
    ref = None if prm.reference.is_default else reference_ps(np.column_stack([lon, lat]), prm.reference,
                                                             coh=S["ps/coherence"])
    xy = _local_xy(lon, lat)
    inc = np.radians(np.asarray(ds["geometry_incidence"].values[line, sample], np.float64))
    rng = np.asarray(ds["geometry_slant_range"].values[line, sample], np.float64)
    smi = stack_dates.index(ref_date)
    slc_ref = np.asarray(store.read(slc_var, date=smi))[line, sample]
    kh_ref = np.asarray(store.read("kh", date=smi), np.float64)[line, sample]
    aps_model = None
    if weather is not None:
        times = acquisition_times(attrs, [date.fromisoformat(d) for d in [ref_date, *new_dates]],
                                  weather.fallback_utc)
        try:
            aps_model = weather_aps(weather, lon=lon, lat=lat, hgt=hgt, incidence=inc, times=times, master_ix=0,
                                    wavelength=wl)
        except Exception as exc:                                     # no ERA5 yet for a date of today
            log.warning("weather APS for the new dates not available (%s): linear APS", exc)

    cols = {k: [] for k in ("unw", "scla", "aps", "aps_lin", "bperp", "disp", "choice")}
    for k, d in enumerate(new_dates):
        j = stack_dates.index(d)
        slc_d = np.asarray(store.read(slc_var, date=j))[line, sample]
        obs = np.angle(slc_ref * np.conj(slc_d)).astype(np.float64)
        kh_d = np.asarray(store.read("kh", date=j), np.float64)[line, sample]
        b = -(kh_d - kh_ref) * wl * rng * np.sin(inc) / (4 * np.pi)
        topo = K * b
        td = (date.fromisoformat(d).toordinal() - day[mi]) / 365.25
        pred = -(v_prev * td + c_prev) / lam                          # corrected phase of the predicted motion
        base = topo + pred + C
        r = np.angle(np.exp(1j * (obs - base)))
        ph_uw = base + unwrap_residual(r, xy, grid_size, align=prm.unwrap.spatial.align)
        lin = linear_aps(ph_uw[:, None], hgt, 0)[:, 1]
        use_weather = False
        a = lin
        if aps_model is not None and np.isfinite(aps_model[:, k + 1]).mean() > 0.5:
            wm = centre_weather(ph_uw[:, None], aps_model[:, [0, k + 1]], 0)[:, 1]
            resid = ph_uw - topo - pred - C
            v_w = np.nanvar(resid - np.where(np.isfinite(wm), wm, lin))
            v_l = np.nanvar(resid - lin)
            use_weather = bool(v_w < v_l)
            a = np.where(np.isfinite(wm), wm, lin) if use_weather else lin
        corr = ph_uw - topo - a - C
        dd = -corr * lam
        dd = dd - (np.nanmean(dd[ref]) if ref is not None else np.nanmean(dd))
        for key, val in (("unw", ph_uw), ("scla", topo), ("aps", a), ("aps_lin", lin), ("bperp", b),
                         ("disp", dd), ("choice", use_weather)):
            cols[key].append(val)
        log.info("%s added: unwrapped residual %.2f rad (std), APS %s, median motion vs prediction %+.1f mm", d,
                 float(np.nanstd(ph_uw - base)), "weather" if use_weather else "linear",
                 float(np.nanmedian(dd - (v_prev * td + c_prev))))

    # ---------------------------------------------------------------- new state
    stackc = lambda old, key: np.column_stack([old, *cols[key]]).astype(np.float32)   # noqa: E731
    disp_all = np.column_stack([disp, *cols["disp"]])
    scn_new = np.column_stack([S["velocity/disp_scn_mm"], *cols["disp"]]).astype(np.float32)
    all_epochs = epochs + new_dates
    day_all = np.array([date.fromisoformat(d).toordinal() for d in all_epochs], np.float64)
    t_all = (day_all - day[mi]) / 365.25
    std_all = np.r_[std, np.full(len(new_dates), np.nanmedian(np.delete(std, mi)))]
    sec_all = [i for i in range(len(all_epochs)) if i != mi]
    w_all = 1.0 / np.maximum(std_all[sec_all] * np.pi / 180.0, 1e-6) ** 2
    v_lin, acc, rmse = _fit(disp_all[:, sec_all], t_all[sec_all], w_all)
    v_scn, _, _ = _fit(scn_new[:, sec_all].astype(np.float64), t_all[sec_all], w_all)
    v = v_lin + dv_hp
    values = {
        "phase/unwrapped": stackc(unw, "unw"), "phase/scla": stackc(scla, "scla"), "phase/aps": stackc(aps, "aps"),
        "phase/aps_linear": stackc(S["phase/aps_linear"], "aps_lin"),
        "phase/scn": np.column_stack([S["phase/scn"], np.zeros((n, len(new_dates)))]).astype(np.float32),
        "ps/bperp": stackc(bperp, "bperp"), "velocity/disp_mm": disp_all.astype(np.float32),
        "velocity/disp_scn_mm": scn_new, "velocity/v_mm_yr": v.astype(np.float32),
        "velocity/v_linear_mm_yr": v_lin.astype(np.float32), "velocity/acc_mm_yr2": acc.astype(np.float32),
        "velocity/rmse_mm": rmse.astype(np.float32), "velocity/v_scn_mm_yr": v_scn.astype(np.float32),
        "time/ifg_std_deg": std_all.astype(np.float32),
        "time/epoch_dates": np.array(all_epochs, "S10"), "time/ifg_dates": np.array(ifg_dates + new_dates, "S10")}
    tmp = prev / "state.h5.update"
    shutil.copy2(prev / "state.h5", tmp)
    with h5py.File(tmp, "a") as f:
        for key, val in values.items():
            if key in f:
                del f[key]
            f.create_dataset(key, data=val)
    tmp.replace(prev / "state.h5")

    # ---------------------------------------------------------------- points and time series
    uid = np.char.add(np.char.add(f"{track_id or 'track'}:", geohash(lat, lon)),
                      np.char.add(":", np.round(S["ps/height_m"]).astype(int).astype(str)))
    _, first = np.unique(uid, return_index=True)
    sel = np.sort(first)
    gdf = read_points(prev / "points.parquet").set_index("point_uid").loc[uid[sel]].reset_index()
    gdf["vel_los_mm_yr"] = v[sel].astype(np.float32)
    gdf["vel_linear_mm_yr"] = v_lin[sel].astype(np.float32)
    gdf["vel_los_scn_mm_yr"] = v_scn[sel].astype(np.float32)
    gdf["acc_mm_yr2"] = acc[sel].astype(np.float32)
    gdf["fit_rmse_mm"] = rmse[sel].astype(np.float32)
    write_points(prev / "points.parquet", gdf, metadata={"engine": UPDATE_ENGINE, "reference_date": ref_date,
                                                          "sign_convention": "StaMPS: -phase·λ/4π"})
    write_timeseries(prev / "timeseries.parquet", uid[sel], np.array(all_epochs, "datetime64[D]"),
                     disp_all[sel].astype(np.float32), disp_scn_mm=scn_new[sel])

    # ---------------------------------------------------------------- manifest
    up = dict(pm.metrics.get("update") or {})
    base_run = up.get("base_run") or pm.run_id
    up = {"base_run": base_run, "dates_since_full": int(up.get("dates_since_full", 0)) + len(new_dates),
          "added": [*up.get("added", []), *new_dates],
          "weather_aps": [d for d, c in zip(new_dates, cols["choice"], strict=True) if c]}
    metrics = {**pm.metrics, "epochs": len(all_epochs), "update": up, "runtime_s": round(time.time() - t0, 1),
               "velocity_mm_yr": {"min": float(np.nanmin(v[sel])), "max": float(np.nanmax(v[sel])),
                                  "p02": float(np.nanpercentile(v[sel], 2)), "median": float(np.nanmedian(v[sel])),
                                  "p98": float(np.nanpercentile(v[sel], 98))}}
    extra = {**(pm.extra or {}), "stack_identity": stack_identity(attrs, all_epochs),
             "config_fingerprint": config_fingerprint or (pm.extra or {}).get("config_fingerprint")}
    m = Manifest(kind="ps_run", id=pm.id, run_id=run_id or pm.run_id, engine=UPDATE_ENGINE,
                 inputs=[InputRef("stack", str(store.path), "")], params=pm.params, metrics=metrics, extra=extra)
    m.add_outputs(prev, [o.path for o in pm.outputs if (prev / o.path).exists()])
    m.write(prev)
    log.info("ps update: %d date(s) added to %d points in %.0f s (%d since the last full run)", len(new_dates),
             int(sel.size), time.time() - t0, up["dates_since_full"])
    return metrics


def mark_full(run: Path, store, config_fingerprint: str) -> None:
    """After a full engine run: record what an update needs to know it can extend this run."""
    pm = Manifest.read(run)
    with h5py.File(run / "state.h5", "r") as f:
        epochs = _dates(f["time/epoch_dates"][()])
    pm.extra = {**(pm.extra or {}), "config_fingerprint": config_fingerprint,
                "stack_identity": stack_identity(dict(store.attrs), epochs)}
    pm.write(run)


def describe(prev: Path) -> dict[str, Any]:
    """The update record of a run (empty for a full run)."""
    try:
        return dict(Manifest.read(prev).metrics.get("update") or {})
    except StoreError:
        return {}
