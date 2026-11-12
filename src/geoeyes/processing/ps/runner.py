"""StaMPS-type PS engine on a StackStore (single master = the stack reference).

Candidates (D_A + amplitude floor), per-PS geometry from the stack (perpendicular baseline from the height
sensitivity ``kh``, incidence, slant range, DEM height), steps 1-5, two unwrapping passes (the second with the
pass-1 smoothed SCLA and the linear APS removed), SCLA, velocity and SCN.

Output folder ``ps_runs/<psrun_id>/`` (ARCHITECTURE §10.3), same layout as ``ps_lite``::

    manifest.json  params.json  state.h5 (schema ``geoeyes.ps`` v1)
    points.parquet  timeseries.parquet  figures/*.png
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from geoeyes.core.errors import DataError
from geoeyes.core.geodesy import geohash
from geoeyes.core.hashing import sha256_params
from geoeyes.core.logging import event
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.io.points import write_points, write_timeseries
from geoeyes.io.state import StateSchema, StateStore, VarSpec
from geoeyes.processing.atmosphere.times import acquisition_times
from geoeyes.processing.atmosphere.weather import weather_aps
from geoeyes.processing.phase_linking.runner import provenance as pl_provenance
from geoeyes.processing.ps import candidates as cd
from geoeyes.processing.ps.aps import centre_weather, choose_aps, inside_polygon, linear_aps
from geoeyes.processing.ps.checkpoints import Checkpoints, pack_gamma, unpack_gamma
from geoeyes.processing.ps.geometry import geolocate, geolocation_dh
from geoeyes.processing.ps.params import DEFAULTS, auto_time_win, engine_params, hoa_max_topo_err
from geoeyes.processing.ps.steps.correct_phase import correct_phase
from geoeyes.processing.ps.steps.est_gamma import est_gamma
from geoeyes.processing.ps.steps.load import load_initial
from geoeyes.processing.ps.steps.ramp import RAMP_AUTO_VERSION, RampAutoParams, ramp_figure
from geoeyes.processing.ps.steps.reference import reference_ps
from geoeyes.processing.ps.steps.scla import DerampAuto, calc_scla, smooth_scla
from geoeyes.processing.ps.steps.scn_filt import scn_filt
from geoeyes.processing.ps.steps.select import select
from geoeyes.processing.ps.steps.unwrap import Scla, unwrap
from geoeyes.processing.ps.steps.velocity import velocity
from geoeyes.processing.ps.steps.weed import weed

log = logging.getLogger(__name__)
ENGINE = "geoeyes-ps/5"            # /2: height-error geolocation moves away from the sensor (sign fixed)
# /3: the weather-model APS is centred per interferogram (scene-wide offsets removed)
# /4: without a reference area, every interferogram is referenced to the scene mean (pass-2 unwrapping offsets)
# /5: geolocated with the local DEM error, its plane over the scene removed ([ps] geolocate_dem_error)
# Runs with the linear APS were already zero-mean per date (its intercept; checked on hanoi_csk: 0.0 mm on every
# date), so their outputs do not change: they keep the /2 fingerprint and are not re-run.
UNCHANGED_WITHOUT_WEATHER = "geoeyes-ps/2"

STATE_SCHEMA = StateSchema.of("geoeyes.ps", 1, [
    VarSpec("ps/line", "int32", ("ps",), description="stack row"),
    VarSpec("ps/sample", "int32", ("ps",), description="stack column"),
    VarSpec("ps/lat", "float64", ("ps",), "deg", "corrected for the height error"),
    VarSpec("ps/lon", "float64", ("ps",), "deg"),
    VarSpec("ps/height_m", "float32", ("ps",), "m", "orthometric: DEM + height error"),
    VarSpec("ps/dem_err_m", "float32", ("ps",), "m"),
    VarSpec("ps/da", "float32", ("ps",), "", "amplitude dispersion"),
    VarSpec("ps/coherence", "float32", ("ps",), "", "temporal coherence (step 3/4)"),
    VarSpec("ps/bperp", "float32", ("ps", "ifg"), "m"),
    VarSpec("phase/unwrapped", "float32", ("ps", "ifg"), "rad", "step-6 pass-2 output"),
    VarSpec("phase/scla", "float32", ("ps", "ifg"), "rad"),
    VarSpec("phase/aps_linear", "float32", ("ps", "ifg"), "rad"),
    VarSpec("phase/aps", "float32", ("ps", "ifg"), "rad",
            "APS removed in pass 2: weather model (ERA5/GACOS), the linear APS where it has no data"),
    VarSpec("phase/scn", "float32", ("ps", "ifg"), "rad", "spatially correlated noise (step 8)"),
    VarSpec("velocity/v_mm_yr", "float32", ("ps",), "mm/yr"),
    VarSpec("velocity/v_linear_mm_yr", "float32", ("ps",), "mm/yr"),
    VarSpec("velocity/acc_mm_yr2", "float32", ("ps",), "mm/yr2"),
    VarSpec("velocity/rmse_mm", "float32", ("ps",), "mm"),
    VarSpec("velocity/disp_mm", "float32", ("ps", "epoch"), "mm"),
    VarSpec("velocity/v_scn_mm_yr", "float32", ("ps",), "mm/yr", "spatially correlated noise removed (v-dso)"),
    VarSpec("velocity/disp_scn_mm", "float32", ("ps", "epoch"), "mm", "spatially correlated noise removed"),
    VarSpec("time/ifg_std_deg", "float32", ("epoch",), "deg", "step-5 phase noise per epoch"),
    VarSpec("time/epoch_dates", "S10", ("epoch",)),
    VarSpec("time/ifg_dates", "S10", ("ifg",)),
])


def run(store, out_dir: str | Path, table: dict[str, Any] | None = None, *, da_max: float = 0.4,
        amp_floor: str = "otsu", smooth_sigma: float = 28.0, edge_margin: int = 28, run_id: str = "",
        track_id: str = "", psrun_id: str = "", slc_var: str = "slc", ds_tcoh_min: float | None = None,
        ds_cell: int = 3, hoa_max_perp: float | None = None, weather=None,
        resume_from: str | Path | None = None, from_step: int | None = None,
        stop_after: int | None = None) -> dict:
    """``table``: StaMPS-named parameters (project ``[ps]``); missing keys take the legacy defaults;
    ``max_topo_err = "auto"``: median height of ambiguity / 4 (pairs with |B⊥| >= ``hoa_max_perp`` left out).
    ``weather`` (``atmosphere.weather.WeatherParams``): ERA5/GACOS APS removed in pass 2 instead of the linear one.
    ``slc_var``: ``slc_linked`` to run on the phase-linked stack; ``ds_tcoh_min`` then also takes distributed
    scatterers (best phase-linking temporal coherence per ``ds_cell``² block) as candidates.
    Every step keeps a checkpoint (``checkpoints/``, see ``checkpoints.py``): a new run in the same folder resumes
    from the last step whose parameters and stack are unchanged; ``from_step`` computes that step and the
    following ones again, ``stop_after`` stops after that step (``PhasePaused``). ``resume_from`` (a previous run
    folder) reuses its steps 1-5, which must exist with the same candidate / gamma / select / weed parameters."""
    t0 = time.time()
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    ds = store.open()
    attrs = ds.attrs
    dates = [np.datetime64(d, "D").item() for d in ds["date"].values]
    master = np.datetime64(str(attrs["reference_date"]), "D").item()
    mi = dates.index(master)
    secs = [d for d in dates if d != master]
    sec_ix = [dates.index(d) for d in secs]
    wl = float(attrs["wavelength_m"])
    args = {"da_max": da_max, "amp_floor": amp_floor, "smooth_sigma": smooth_sigma, "edge_margin": edge_margin,
            "slc_var": slc_var, "ds_tcoh_min": ds_tcoh_min, "ds_cell": ds_cell, "stack": str(store.path)}
    resolved: dict[str, dict] = {}                   # parameters set from the data ("auto"): rule and value
    mte_mode = str((table or {}).get("max_topo_err", "")).lower()
    if mte_mode in ("auto", "auto_master"):
        about_master = mte_mode == "auto_master"
        mte = hoa_max_topo_err(ds["bperp"].values, wl, float(np.nanmedian(ds["geometry_slant_range"].values)),
                               np.radians(float(np.nanmedian(ds["geometry_incidence"].values))), hoa_max_perp,
                               about_master=about_master)
        rule = ("median height of ambiguity / 4 (B⊥ about the master)" if about_master
                else "median height of ambiguity / 4 (B⊥ about the stack median)")
        table = {**table, "max_topo_err": mte}
        resolved["max_topo_err"] = {"from": mte_mode, "rule": rule, "value": round(mte, 3)}
        log.info("max_topo_err = %s = %.2f m", rule, mte)
    if str((table or {}).get("unwrap_time_win", "")).lower() == "auto":
        tw = auto_time_win([d.toordinal() for d in dates])
        table = {**table, "unwrap_time_win": tw}
        resolved["unwrap_time_win"] = {"from": "auto", "rule": "span / 4, at least 4 sampling intervals, 60-730 days",
                                       "value": tw}
        log.info("unwrap_time_win = span / 4 (at least 4 sampling intervals, 60-730) = %.0f days", tw)

    # one checkpoint per step (checkpoints/): a run stopped or killed resumes from its last finished step
    import dataclasses
    lean = str((table or {}).get("checkpoints", "all")).lower() == "lean"
    ck = Checkpoints(out, read_from=resume_from, from_step=from_step, stop_after=stop_after, lean=lean)
    ck.key(1, args=args, stack=stack_identity(attrs, slc_var))
    L = C = None

    def step1():
        C = _candidates(ds, dates, mi, sec_ix, wl, args, log)
        L = load_initial(ij=np.column_stack([np.arange(C["n"]), C["r"], C["c"]]), lonlat=C["lonlat"], ph=C["ph"],
                         master=master, secondaries=secs, bperp_mat=C["bperp_mat"], inc=C["inc"],
                         heading=float(attrs["heading_deg"]) % 360.0, mean_range=C["mean_range"], hgt=C["hgt"],
                         da=C["da"], coh=C["coh"], log=log)
        for k in ("r", "c", "lonlat", "ph", "bperp_mat", "hgt", "da", "coh"):
            del C[k]                                 # kept in L
        ck.save(1, {"L": L, "cand": C}, mean_range=C["mean_range"])
        ck.reached(1)
        return L, C

    # the step-1 values the later keys need: from its .json (its data may be gone in a lean run)
    rho = ck.meta(1).get("mean_range") if ck.known(1) else None
    if rho is None:
        L, C = step1()
        rho = C["mean_range"]
    prm = engine_params(table, wavelength=wl, rho=rho)
    ck.key(2, est_gamma=prm.est_gamma)
    ck.key(3, select=prm.select)
    ck.key(4, weed=prm.weed)
    ck.key(5)
    # "auto" adds its own parts, so the keys of the "y" / "n" runs (and their checkpoints) are unchanged
    ck.key(6, unwrap=prm.unwrap, reference=prm.reference, aps_non_defo=prm.aps_non_defo,
           scla_deramp=prm.scla_deramp, legacy=prm.legacy, weather=weather,
           **({"deramp_auto": RAMP_AUTO_VERSION, "deramp_non_defo": prm.deramp_non_defo,
               "deramp_allow_planar": prm.deramp_allow_planar} if prm.deramp_auto else {}))
    ck.key(7, two_pass=prm.two_pass)
    if resume_from is not None and not ck.valid(5):
        raise DataError(f"{resume_from}: no steps 1-5 checkpoint with these candidate / gamma / select / weed "
                        "parameters on this stack; run without resume_from")
    if ck.valid(5):
        d = ck.load(5)
        est = d["est"]
        if L is None:
            L, C = d["L"], d["cand"]
            for n in range(1, 6):
                ck.reached(n)
    else:
        if L is None and ck.valid(1):
            d = ck.load(1)
            L, C = d["L"], d["cand"]
            ck.reached(1)
        elif L is None:                              # lean run: step 1 deleted, step 5 not reusable
            L, C = step1()
        ck.extra = {"L": dataclasses.replace(L, ph=np.zeros((0, 0), np.complex64)), "cand": C}
        est = estimate(L, prm, ck)
    inc, rng, is_ds = C["inc"], C["rng"], C["is_ds"]
    aps_model = None
    if weather is not None:
        times = acquisition_times(dict(attrs), dates, weather.fallback_utc)

        def aps_model(ix):
            return weather_aps(weather, lon=L.lonlat[ix, 0], lat=L.lonlat[ix, 1], hgt=L.hgt[ix],
                               incidence=inc[L.cand_ix[ix]], times=times, master_ix=L.master_ix, wavelength=wl)
    P = process(L, prm, wl, aps_model=aps_model, aps_select=weather.select if weather is not None else "auto",
                est=est, ck=ck)
    s, w, ix, u, aps, sc, sm, vel, scn = P.select, P.weed, P.ix, P.unwrapped, P.aps, P.scla, P.scla_smooth, \
        P.velocity, P.scn
    bp_ix, hgt_ix = L.bperp_mat[ix], L.hgt[ix]
    try:                                            # the wrapped phase the last pass unwrapped (Stack tab)
        from geoeyes.processing.stack.qc import unwrap_grid_qc
        drop = {d - 1 for d in prm.unwrap.drop_ifg_index}
        uw_idx = [k for k in range(len(dates)) if k not in drop]
        q = unwrap_grid_qc(u.grid, [d.isoformat() for d in dates], L.master_ix, uw_idx, out / "qc", lonlat=L.lonlat[ix],
                           label=f"pass {'2' if prm.two_pass else '1'}, grid {prm.unwrap.grid_size:g} m, "
                                 f"prefilter {prm.unwrap.prefilter}")
        log.info("unwrapping input: %d cells; phase jumps > pi/2 between neighbours %s", q["cells"],
                 " ".join(f"{r['jump_frac']:.2f}" for r in q["dates"] if r["jump_frac"] is not None))
    except Exception as exc:                        # the images never fail the run
        log.warning("unwrapping input images not written: %s", exc)

    # ---------------------------------------------------------------- outputs
    line, sample = L.ij[ix, 1], L.ij[ix, 2]
    orig = L.cand_ix[ix]
    inc_ps, rng_ps = inc[orig], rng[orig]
    dem_err = -sm.K_uw * wl * rng_ps * np.sin(inc_ps) / (4 * np.pi)
    lat_pix, lon_pix = L.lonlat[ix, 1].astype(np.float64), L.lonlat[ix, 0].astype(np.float64)
    dh_geo = geolocation_dh(dem_err, lat_pix, lon_pix, prm.geolocate)
    lat_ps, lon_ps = geolocate(lat_pix, lon_pix, np.degrees(inc_ps), float(attrs["heading_deg"]),
                               str(attrs.get("look_side", "right")), dh_geo)
    height = (hgt_ix + dh_geo).astype(np.float32)
    log.info("geolocation: DEM error %s (p16..p84 %.1f..%.1f m; used %.1f..%.1f m)", prm.geolocate,
             *np.percentile(dem_err, [16, 84]), *np.percentile(dh_geo, [16, 84]))
    epoch_dates = np.array([d.isoformat() for d in dates], "S10")
    st = StateStore(out / "state.h5", STATE_SCHEMA)
    st.write_many({
        "ps/line": line, "ps/sample": sample, "ps/lat": lat_ps, "ps/lon": lon_ps, "ps/height_m": height,
        "ps/dem_err_m": dem_err, "ps/da": L.da[ix], "ps/coherence": w.coh, "ps/bperp": bp_ix,
        "phase/unwrapped": u.ph_uw, "phase/scla": sc.ph_scla,
        "phase/aps_linear": np.delete(P.aps_linear, L.master_ix, 1), "phase/aps": np.delete(aps, L.master_ix, 1),
        "phase/scn": scn.ph_scn, "velocity/v_mm_yr": vel.v, "velocity/v_linear_mm_yr": vel.v_linear,
        "velocity/acc_mm_yr2": vel.acc, "velocity/rmse_mm": vel.rmse, "velocity/disp_mm": vel.ts_mm,
        "velocity/v_scn_mm_yr": P.velocity_scn.v, "velocity/disp_scn_mm": P.velocity_scn.ts_mm,
        "time/ifg_std_deg": P.ifg_std,
        "time/epoch_dates": epoch_dates, "time/ifg_dates": np.array([d.isoformat() for d in secs], "S10")})
    st.mark_done("ps")

    import geopandas as gpd
    uid = np.char.add(np.char.add(f"{track_id or 'track'}:", geohash(lat_ps, lon_ps)),
                      np.char.add(":", np.round(height).astype(int).astype(str)))
    _, first = np.unique(uid, return_index=True)
    sel = np.sort(first)
    gdf = gpd.GeoDataFrame({
        "point_uid": uid[sel], "lon": lon_ps[sel], "lat": lat_ps[sel], "line": line[sel], "sample": sample[sel],
        "height_m": height[sel], "dem_err_m": dem_err[sel].astype(np.float32),
        "type": np.where(is_ds[orig][sel], "DS", "PS"),
        "vel_los_mm_yr": vel.v[sel].astype(np.float32), "vel_linear_mm_yr": vel.v_linear[sel].astype(np.float32),
        "vel_los_scn_mm_yr": P.velocity_scn.v[sel].astype(np.float32),
        **{f"vel_{k}_mm_yr": v[sel].astype(np.float32) for k, v in (P.velocity_kinds or {}).items()},
        "acc_mm_yr2": vel.acc[sel].astype(np.float32), "temporal_coherence": w.coh[sel].astype(np.float32),
        "amp_dispersion": L.da[ix][sel].astype(np.float32), "fit_rmse_mm": vel.rmse[sel].astype(np.float32),
        "incidence_deg": np.degrees(inc_ps[sel]).astype(np.float32)},
        geometry=gpd.points_from_xy(lon_ps[sel], lat_ps[sel]), crs="EPSG:4326")
    write_points(out / "points.parquet", gdf, metadata={"engine": ENGINE, "reference_date": master.isoformat(),
                                                         "sign_convention": "StaMPS: -phase·λ/4π"})
    write_timeseries(out / "timeseries.parquet", uid[sel], np.array(dates, "datetime64[D]"), vel.ts_mm[sel],
                     disp_scn_mm=P.velocity_scn.ts_mm[sel])
    is_ref = np.zeros(ix.size, bool)
    if P.ref_ps is not None:
        is_ref[P.ref_ps] = True
    figs = _figures(out / "figures", lat=lat_ps[sel], lon=lon_ps[sel], v=vel.v[sel], v_scn=P.velocity_scn.v[sel],
                    ref=is_ref[sel] if P.ref_ps is not None else None, title=f"{track_id} {len(sel)} PS",
                    ifg_dates=secs, aps=np.delete(aps, L.master_ix, 1), aps_linear=np.delete(P.aps_linear,
                    L.master_ix, 1), aps_choice=P.aps_choice, epoch_dates=dates, ifg_std=P.ifg_std)
    ramp = None
    if sc.ramp_auto is not None:
        ramp = sc.ramp_auto.summary()
        log.info("ramp (scla_deramp auto): rest removed; trend %s (%s)",
                 "removed" if ramp["trend_removed"] else "kept", ramp["reason"])
        try:
            figs.append(ramp_figure(sc.ramp_auto, secs, out / "figures" / "ramp.png", title=track_id))
        except Exception as exc:                    # the images never fail the run
            log.warning("ramp figure not written: %s", exc)
    v = vel.v[sel]
    summary = {"engine": ENGINE, "reference_date": master.isoformat(), "epochs": len(dates),
               "ps": {"candidates": C["n"], "ds_candidates": int(is_ds.sum()), "selected": int(s.keep_ix.sum()),
                      "weeded": int(ix.size), "unique_points": int(sel.size),
                      "ds_points": int(is_ds[orig][sel].sum())},
               "aps": ("linear" if weather is None else
                       {"method": weather.method, "select": weather.select,
                        "weather_ifgs": [d.isoformat() for d, c in zip(secs, P.aps_choice, strict=True) if c]
                        if P.aps_choice is not None else "all"}),
               "reference": ({"n_ps": int(P.ref_ps.size), "lat": float(np.mean(lat_ps[P.ref_ps])),
                              "lon": float(np.mean(lon_ps[P.ref_ps]))} if P.ref_ps is not None else "scene mean"),
               **({"ramp": ramp} if ramp is not None else {}),
               "velocity_mm_yr": {"min": float(np.nanmin(v)), "max": float(np.nanmax(v)),
                                  "p02": float(np.nanpercentile(v, 2)), "median": float(np.nanmedian(v)),
                                  "p98": float(np.nanpercentile(v, 98))},
               "runtime_s": round(time.time() - t0, 1)}
    # "table": the [ps] keys of the project (data-set values in place of "auto"); "effective": every parameter the
    # engine used (defaults included), what the report and the settings page show
    params_snapshot = {"table": table or {}, "effective": {**DEFAULTS, **(table or {})}, "resolved": resolved,
                       "da_max": da_max, "amp_floor": amp_floor, "smooth_sigma": smooth_sigma,
                       "edge_margin": edge_margin, "slc_var": slc_var, "ds_tcoh_min": ds_tcoh_min, "ds_cell": ds_cell}
    atomic_write_json(out / "params.json", params_snapshot)
    m = Manifest(kind="ps_run", id=psrun_id or out.name, run_id=run_id, engine=ENGINE,
                 inputs=[InputRef("stack", str(store.path), "")],
                 params={"sha256": sha256_params(params_snapshot), "snapshot": "params.json"}, metrics=summary,
                 extra=pl_provenance(store, slc_var))
    m.add_outputs(out, ["state.h5", "points.parquet", "timeseries.parquet", "params.json",
                        *(f.relative_to(out) for f in figs)])
    m.write(out)
    event(log, "progress", "outputs", stage="ps", done=9, total=9)
    log.info("ps done in %.0f s: %d points -> %s", time.time() - t0, sel.size, out)
    return summary


def stack_identity(attrs, slc_var: str) -> dict:
    """What makes step 1 differ on the same stack path: a rebuilt stack, phase linking run again."""
    from geoeyes.processing.phase_linking.runner import DONE_ATTR
    return {"build": attrs.get("build_fingerprint"), "scenes": attrs.get("scene_signatures"),
            "phase_linking": attrs.get(DONE_ATTR) if slc_var == "slc_linked" else None}


def _candidates(ds, dates, mi, sec_ix, wl, args, log) -> dict:
    """D_A (+ DS) candidates of the stack with their phase, geometry and prior coherence."""
    # one date at a time (the stack is chunked per date): the whole (n_date, rows, cols) stack is not held in memory
    var = ds[args["slc_var"]]

    def slc(k: int) -> np.ndarray:
        return np.asarray(var[k].values)

    da_max, ds_tcoh_min, ds_cell = args["da_max"], args["ds_tcoh_min"], args["ds_cell"]
    disp = cd.amplitude_dispersion(lambda k: np.abs(slc(k)), len(dates), smooth_sigma=args["smooth_sigma"],
                                   edge_margin=args["edge_margin"])
    floor = cd.otsu_amplitude_floor(disp.raw_mean_amp) if args["amp_floor"] == "otsu" else None
    r, c, da = cd.select(disp, da_max, floor)
    is_ds = np.zeros(r.size, bool)
    if ds_tcoh_min is not None:
        excl = np.zeros(disp.da.shape, bool)
        excl[r, c] = True
        rd, cdd = cd.select_ds(ds["pl_temporal_coherence"].values, excl, ds_tcoh_min, ds_cell)
        da_ds = np.where(np.isfinite(disp.da[rd, cdd]), disp.da[rd, cdd], np.float32(10.0))   # PS win ties
        o = np.argsort(np.r_[da, da_ds], kind="stable")
        r, c, da = np.r_[r, rd][o], np.r_[c, cdd][o], np.r_[da, da_ds][o]
        is_ds = np.r_[is_ds, np.ones(rd.size, bool)][o]
        log.info("DS candidates: %d (phase-linking temporal coherence >= %s, one per %dx%d)", rd.size, ds_tcoh_min,
                 ds_cell, ds_cell)
    lat, lon = ds["geometry_lat"].values, ds["geometry_lon"].values
    lonlat = np.column_stack([lon[r, c], lat[r, c]]).astype(np.float32)
    keep = cd.dedup_lonlat(lonlat, da)
    r, c, da, lonlat, is_ds = r[keep], c[keep], da[keep], lonlat[keep], is_ds[keep]
    from geoeyes.geometry.dem import Geoid
    h_ell = ds["geometry_hgt"].values[r, c].astype(np.float64)
    hgt = (h_ell - Geoid().undulation(lonlat[:, 1], lonlat[:, 0])).astype(np.float32)
    m = slc(mi)
    ph = np.empty((r.size, len(sec_ix)), np.complex64)
    coh_cols = []
    for j, k in enumerate(sec_ix):
        s = slc(k)
        ph[:, j] = m[r, c] * np.conj(s[r, c])
        coh_cols.append(cd.pair_coherence(m, s, r, c))
    del m, s
    coh_ifg = np.stack(coh_cols, axis=1)
    coh = cd.prior_coherence(coh_ifg, ph)
    rng = ds["geometry_slant_range"].values[r, c].astype(np.float64)
    inc = np.radians(ds["geometry_incidence"].values[r, c].astype(np.float64))
    kh = np.stack([np.asarray(ds["kh"][k].values)[r, c] for k in range(len(dates))]).astype(np.float64)
    # topographic phase kh·dh = K·B⊥  with  kh = -4π B⊥ / (λ R sinθ)
    bperp_mat = -(kh[sec_ix] - kh[mi]).T * wl * (rng * np.sin(inc))[:, None] / (4 * np.pi)
    log.info("candidates: %d (D_A <= %s, amplitude floor %s)", r.size, da_max,
             "none" if floor is None else f"{floor:.3f}")
    event(log, "progress", "candidates", stage="ps", done=1, total=9)
    return {"n": int(r.size), "r": r, "c": c, "da": da, "is_ds": is_ds, "lonlat": lonlat, "hgt": hgt, "ph": ph,
            "coh": coh, "rng": rng, "inc": inc, "bperp_mat": bperp_mat, "mean_range": float(np.mean(rng))}


@dataclass
class Processed:
    gamma: Any
    select: Any
    weed: Any
    ix: np.ndarray            # step-1 rows of the weeded PS
    unwrapped: Any            # last unwrap pass
    aps: np.ndarray           # APS (n, n_ifg) removed in pass 2 (weather model or linear from pass 1)
    scla: Any                # SCLA of the last pass (unsmoothed)
    scla_smooth: Any
    velocity: Any
    scn: Any
    ref_ps: np.ndarray | None = None   # rows of ``ix`` used as reference (None = scene mean, legacy default)
    aps_linear: np.ndarray | None = None
    aps_choice: np.ndarray | None = None   # (n_sec,) weather APS used (aps_select "auto")
    velocity_scn: Any = None                # velocity with the SCN removed as well (StaMPS v-dso)
    velocity_kinds: dict | None = None      # {"do", "dao", "dso"}: the StaMPS velocity kinds (mm/yr per PS)
    ifg_std: np.ndarray | None = None       # (n_ifg,) step-5 phase noise per epoch, degrees
    estimated: Any = None                   # Estimated (steps 2-5), what a checkpoint keeps


@dataclass
class Estimated:
    """Steps 2-5 (what the unwrapping and the later steps need)."""
    gamma: Any                # None when resumed from a checkpoint (not stored)
    select: Any
    weed: Any
    correct: Any


def _reached(ck, n: int) -> None:
    if ck is None:
        event(log, "progress", f"step {n}", stage="ps", done=n + 1, total=9)
    else:
        ck.reached(n)


def estimate(L, prm, ck: Checkpoints | None = None) -> Estimated:
    """Steps 2-5 on the step-1 state ``L``: estimate gamma, select, weed, correct phase; ``ck``: resumed from the
    latest valid checkpoint of steps 2-4, each step computed here saved."""
    import dataclasses
    h = max((n for n in (2, 3, 4) if ck is not None and ck.valid(n)), default=1)
    g = s = w = ph_patch = None
    if h == 4:
        d = ck.load(4)
        s, w = d["s"], d["w"]
    elif h == 3:
        d = ck.load(3)
        s, ph_patch = d["s"], d["ph_patch"]
    elif h == 2:
        g = unpack_gamma(ck.load(2))
    for n in range(2, h + 1):
        _reached(ck, n)
    if h < 2:
        g = est_gamma(ph=L.ph, bperp=L.bperp, bperp_mat=L.bperp_mat, master_ix=L.master_ix, xy=L.xy, la=L.la,
                      da=L.da, coh_prior=L.coh, params=prm.est_gamma)
        if ck is not None:
            ck.save(2, pack_gamma(g))
        _reached(ck, 2)
    if h < 3:
        s = select(ph=L.ph, bperp=L.bperp, bperp_mat=L.bperp_mat, master_ix=L.master_ix, xy=L.xy, forced=L.forced,
                   da=L.da, gamma=g, params=prm.select)
        ph_patch = g.ph_patch
        if ck is not None:
            ck.save(3, {"s": s, "ph_patch": ph_patch})
        _reached(ck, 3)
    if h < 4:
        w = weed(ph=L.ph, bperp=L.bperp, day=L.day, master_ix=L.master_ix, xy=L.xy, ij=L.ij, forced=L.forced,
                 hgt=L.hgt, ph_patch=ph_patch, sel=s, params=prm.weed)
        if ck is not None:
            ck.save(4, {"s": s, "w": w})
        _reached(ck, 4)
    log.info("PS: %d candidates -> %d selected -> %d after weeding", L.n_ps, int(s.keep_ix.sum()), w.ix.size)
    cp = correct_phase(ph=L.ph[w.ix], bperp_mat=L.bperp_mat[w.ix], K=w.K, C=w.C, ph_patch=w.ph_patch,
                       master_ix=L.master_ix)
    if ck is not None:
        none = np.zeros((0, 0), np.complex64)        # arrays only steps 2-5 read
        ck.save(5, {"est": Estimated(None, dataclasses.replace(s, ph_patch2=none, ph_res2=none),
                                     dataclasses.replace(w, ph_res=none), dataclasses.replace(cp, ph_reref=none))})
    _reached(ck, 5)
    return Estimated(g, s, w, cp)


def process(L, prm, wavelength: float, *, scn_filter_xy: np.ndarray | None = None, scn_method: str = "grid",
            aps_model=None, aps_select: str = "auto", est: Estimated | None = None,
            ck: Checkpoints | None = None) -> Processed:
    """Steps 2-8 on the step-1 state ``L`` (``est``: steps 2-5 already done, e.g. from a checkpoint): estimate
    gamma, select, weed, correct phase, unwrap (pass 1, linear APS, SCLA; pass 2 with SCLA + APS removed when
    ``prm.two_pass``), SCLA, velocity, SCN. ``aps_model(ix)``: weather-model APS (len(ix), n_ifg) of the weeded
    PS; ``aps_select`` "auto": used for the interferograms where it explains the pass-1 residual phase better than
    the linear APS, "all": for every interferogram (the linear APS where it has no data)."""
    est = est or estimate(L, prm, ck)
    g, s, w, cp = est.gamma, est.select, est.weed, est.correct
    ix = w.ix

    day_rel = L.day.astype(np.float64) - float(L.master_day)
    bp_ix, xy_ix, hgt_ix = L.bperp_mat[ix], L.xy[ix], L.hgt[ix]
    common = dict(ph_patch=w.ph_patch, ph_rc=cp.ph_rc, K=w.K, coh=w.coh, xy=L.xy[ix], bperp=L.bperp, day=day_rel,
                  master_ix=L.master_ix, ifgday_ix=L.ifgday_ix, mean_incidence=L.mean_incidence, params=prm.unwrap,
                  bperp_mat=bp_ix)
    ref = None if prm.reference.is_default else reference_ps(L.lonlat[ix], prm.reference, coh=w.coh)
    aps_mask = None
    if prm.aps_non_defo is not None:
        aps_mask = inside_polygon(L.lonlat[ix], prm.aps_non_defo)
        log.info("linear APS fitted on %d PS of the non-deforming area", int(aps_mask.sum()))
        if aps_mask.sum() < 10:
            log.warning("fewer than 10 PS in the non-deforming area: linear APS fitted on all PS")
            aps_mask = None
    auto = None
    if prm.deramp_auto:
        stable = None
        if prm.deramp_non_defo is not None:
            stable = inside_polygon(L.lonlat[ix], prm.deramp_non_defo)
            log.info("ramp auto: %d PS inside deramp_non_defo", int(stable.sum()))
        wts = None
        if not prm.legacy and cp.ifg_std is not None:
            std = np.delete(np.asarray(cp.ifg_std, np.float64).ravel(), L.master_ix)
            wts = 1.0 / np.maximum(std * np.pi / 180.0, 1e-6) ** 2      # as the velocity fit
        auto = DerampAuto(t=np.delete(day_rel, L.master_ix) / 365.25, mm_per_rad=-wavelength / (4 * np.pi) * 1000.0,
                          weights=wts, stable_mask=stable,
                          params=RampAutoParams(allow_planar=prm.deramp_allow_planar))
    # steps 6 and 7 (the unwrapping passes): resumed from their checkpoints when valid
    h = max((n for n in (6, 7) if ck is not None and ck.valid(n)), default=5)
    if h >= 6:
        d = ck.load(h)
        u, sc, aps_lin, aps, aps_choice = d["u"], d["sc"], d["aps_lin"], d["aps"], d["aps_choice"]
        del d
        for n in range(6, h + 1):
            _reached(ck, n)
    else:
        u = unwrap(**common)
        aps_lin = aps = linear_aps(u.ph_uw, hgt_ix, L.master_ix, fit_mask=aps_mask)
        aps_choice = None
        if aps_model is not None:
            wm = centre_weather(u.ph_uw, np.asarray(aps_model(ix), np.float64), L.master_ix, fit_mask=aps_mask)
            if aps_select == "auto":
                aps, aps_choice, var = choose_aps(u.ph_uw, wm, aps_lin, np.delete(day_rel, L.master_ix), bp_ix,
                                                  L.master_ix)
                ifgs = np.delete(L.day, L.master_ix)
                for k, d in enumerate(ifgs):
                    log.info("APS %s: %s (residual %.2f, - weather %.2f, - linear %.2f rad2)",
                             date.fromordinal(int(d)), "weather" if aps_choice[k] else "linear", *var[:, k])
                log.info("weather APS chosen for %d of %d interferograms", int(aps_choice.sum()), aps_choice.size)
            else:
                filled = ~np.isfinite(wm)
                aps = np.where(filled, aps_lin, wm)
                log.info("weather APS used for %.1f %% of the values (linear APS elsewhere)",
                         100.0 * (1.0 - filled[:, np.arange(wm.shape[1]) != L.master_ix].mean()))
        sc = calc_scla(ph_uw=u.ph_uw, bperp_mat=bp_ix, ifgday=L.ifgday, master_ix=L.master_ix, xy=xy_ix,
                       deramp_scla=prm.scla_deramp, legacy=prm.legacy, ref_ps=ref, auto=auto)
        if ck is not None:
            ck.save(6, {"u": u, "sc": sc, "aps_lin": aps_lin, "aps": aps, "aps_choice": aps_choice})
        _reached(ck, 6)
    if h < 7:
        if prm.two_pass:
            sm = smooth_scla(sc, xy_ix, bp_ix)
            # "auto": the ramp is removed after the unwrapping only (velocity, SCN). Taken out of the wrapped phase
            # it flipped the cycle of weakly connected areas (ramp-selection.md §5.3). "y" keeps StaMPS' order.
            keep_ramp = sm.ph_ramp.size and auto is None
            scla1 = Scla(sm.K_uw, sm.C_uw, sm.ph_ramp if keep_ramp else None)
            del u, sc, sm                            # pass 1 is in its checkpoint: its arrays are not kept for pass 2
            u = unwrap(**common, scla=scla1, aps=aps)
            # "auto": the pass-1 SCLA is taken out of the phase the ramp is estimated on (ramp-selection.md §5.3)
            sc = calc_scla(ph_uw=u.ph_uw, bperp_mat=bp_ix, ifgday=L.ifgday, master_ix=L.master_ix, xy=xy_ix,
                           aps=aps, deramp_scla=prm.scla_deramp, legacy=prm.legacy, ref_ps=ref, auto=auto,
                           scla_k_prior=scla1.K_uw if auto is not None else None)
        if ck is not None:
            ck.save(7, {"u": u, "sc": sc, "aps_lin": aps_lin, "aps": aps, "aps_choice": aps_choice})
        _reached(ck, 7)
    # the unwrapping is done: the arrays only it read are dropped (GBs on millions of PS) before step 8
    import dataclasses
    none = np.zeros((0, 0), np.complex64)
    del common
    w = est.weed = dataclasses.replace(w, ph_patch=none)
    cp = est.correct = dataclasses.replace(cp, ph_rc=none, ph_reref=none)
    sm = smooth_scla(sc, xy_ix, bp_ix)
    def _vel(ph, with_aps: bool):
        v = velocity(ph_uw=ph, scla=sc, aps=aps if with_aps else None, ifgday=L.ifgday, day=L.day,
                     master_ix=L.master_ix, xy=xy_ix, lonlat=L.lonlat[ix], hgt=hgt_ix, wavelength=wavelength,
                     deramp=prm.scla_deramp, ifg_std_deg=None if prm.legacy else cp.ifg_std, legacy=prm.legacy,
                     demean=ref is None and not prm.legacy)
        if ref is not None:
            # velocity and time series are linear in the phase: referencing the phase to the reference PS (StaMPS
            # ps_setref) shifts them by the reference mean; the high-pass correction removes a plane, so it stays
            off = float(np.nanmean(v.v_linear[ref]))
            v.v, v.v_linear = v.v - off, v.v_linear - off
            v.ts_mm = (v.ts_mm - np.nanmean(v.ts_mm[ref], axis=0)).astype(np.float32)
        return v

    vel = _vel(u.ph_uw, prm.two_pass)
    # the StaMPS velocity kinds, for the user to choose on the map: v-do (DEM error and orbit ramps removed),
    # v-dao (+ the APS), v-dso (+ the SCN, no APS); the product velocity is v-dao with the APS ("subtr_tropo"),
    # else v-do
    other = _vel(u.ph_uw, not prm.two_pass).v
    kinds = {"do": other if prm.two_pass else vel.v, "dao": vel.v if prm.two_pass else other}
    scn = scn_filt(ph_uw=u.ph_uw, ph_scla=sc.ph_scla, C_uw=sc.C_uw, ph_ramp=sc.ph_ramp, day=L.day,
                   master_ix=L.master_ix, xy=xy_ix, filter_xy=None if scn_filter_xy is None else scn_filter_xy[ix],
                   time_win=prm.scn_time_win, wavelength=prm.scn_wavelength, method=scn_method,
                   time_fit=prm.scn_time_fit)
    # StaMPS "v-dso": SCN removed too (referenced to the reference PS / the scene mean instead of PS 0); no
    # high-pass correction, the SCN is that noise
    scn_ref = np.nanmean(scn.ph_scn[ref if ref is not None else slice(None)], axis=0)
    ph_dso = scn.ph_scn - scn_ref
    np.subtract(u.ph_uw, ph_dso, out=ph_dso)                      # φ - (SCN - ref) in one buffer
    vel_scn = velocity(ph_uw=ph_dso, scla=sc, aps=aps if prm.two_pass else None,
                       ifgday=L.ifgday, day=L.day, master_ix=L.master_ix, xy=xy_ix, lonlat=L.lonlat[ix], hgt=hgt_ix,
                       wavelength=wavelength, deramp=prm.scla_deramp,
                       ifg_std_deg=None if prm.legacy else cp.ifg_std, legacy=prm.legacy, highpass=False,
                       demean=ref is None and not prm.legacy)
    if ref is not None:
        vel_scn.v = vel_scn.v - float(np.nanmean(vel_scn.v[ref]))
        vel_scn.ts_mm = (vel_scn.ts_mm - np.nanmean(vel_scn.ts_mm[ref], axis=0)).astype(np.float32)
    if prm.two_pass:
        # StaMPS v-dso keeps the APS in: the SCN estimate holds the atmosphere already
        dso = velocity(ph_uw=ph_dso, scla=sc, aps=None, ifgday=L.ifgday, day=L.day, master_ix=L.master_ix, xy=xy_ix,
                       lonlat=L.lonlat[ix], hgt=hgt_ix, wavelength=wavelength, deramp=prm.scla_deramp,
                       ifg_std_deg=None if prm.legacy else cp.ifg_std, legacy=prm.legacy, highpass=False,
                       demean=ref is None and not prm.legacy).v
        kinds["dso"] = dso - float(np.nanmean(dso[ref])) if ref is not None else dso
    else:
        kinds["dso"] = vel_scn.v
    del ph_dso
    return Processed(gamma=g, select=s, weed=w, ix=ix, unwrapped=u, aps=aps, scla=sc, scla_smooth=sm, velocity=vel,
                     scn=scn, ref_ps=ref, aps_linear=aps_lin, aps_choice=aps_choice, velocity_scn=vel_scn,
                     ifg_std=cp.ifg_std, estimated=est, velocity_kinds=kinds)


def _velocity_map(path: Path, lat, lon, v, title: str, ref=None, lim=None) -> Path:
    import matplotlib.pyplot as plt
    lim = lim or float(np.nanmax(np.abs(v))) or 1.0                # full velocity range
    o = np.argsort(np.abs(v))
    fig, ax = plt.subplots(figsize=(7, 7), dpi=130)
    sc = ax.scatter(lon[o], lat[o], c=v[o], s=0.4, cmap="RdBu", vmin=-lim, vmax=lim, linewidths=0)
    if ref is not None and np.any(ref):
        ax.scatter(lon[ref], lat[ref], s=0.6, c="k", linewidths=0, label="reference PS")
        ax.legend(loc="lower right", fontsize=7, markerscale=8)
    ax.set_aspect(1 / np.cos(np.radians(np.nanmean(lat))))
    ax.set_title(f"{title}\nLOS velocity (mm/yr, + = toward the satellite)", fontsize=9)
    fig.colorbar(sc, ax=ax, fraction=0.04, pad=0.02)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def _figures(out: Path, *, lat, lon, v, v_scn, ref, title: str, ifg_dates, aps, aps_linear, aps_choice,
             epoch_dates, ifg_std) -> list[Path]:
    """QC figures: velocity (reference PS marked), SCN-removed velocity, APS and phase noise per interferogram."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out.mkdir(parents=True, exist_ok=True)
    lim = float(max(np.nanmax(np.abs(v)), np.nanmax(np.abs(v_scn)))) or 1.0     # full range, one scale for both
    figs =[_velocity_map(out / "velocity.png", lat, lon, v, title, ref, lim),
            _velocity_map(out / "velocity_scn.png", lat, lon, v_scn, f"{title}, SCN removed", ref, lim)]
    labels = [d.isoformat() for d in ifg_dates]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=130)
    ax.bar(x - 0.2, np.nanstd(aps_linear, axis=0), 0.4, label="linear APS", color="0.6")
    used = np.nanstd(aps, axis=0)
    colors = ["tab:blue" if (aps_choice is not None and aps_choice[k]) else "0.3" for k in range(len(x))]
    ax.bar(x + 0.2, used, 0.4, color=colors, label="APS removed (blue: weather model)")
    ax.set_xticks(x, labels, rotation=60, fontsize=7)
    ax.set_ylabel("std over the PS (rad)")
    ax.set_title("Atmospheric phase screen per interferogram", fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    figs.append(out / "aps.png")
    fig.savefig(figs[-1])
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 3.2), dpi=130)
    ax.bar(np.arange(len(epoch_dates)), ifg_std, color="tab:orange")
    ax.set_xticks(np.arange(len(epoch_dates)), [d.isoformat() for d in epoch_dates], rotation=60, fontsize=7)
    ax.set_ylabel("phase noise (deg)")
    ax.set_title("Step-5 phase noise per epoch (ifg_std; the velocity fit weights)", fontsize=9)
    fig.tight_layout()
    figs.append(out / "ifg_std.png")
    fig.savefig(figs[-1])
    plt.close(fig)
    return figs


__all__ = ["ENGINE", "STATE_SCHEMA", "run"]
