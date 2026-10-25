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
from geoeyes.processing.ps.geometry import geolocate
from geoeyes.processing.ps.params import engine_params, hoa_max_topo_err
from geoeyes.processing.ps.steps.correct_phase import correct_phase
from geoeyes.processing.ps.steps.est_gamma import est_gamma
from geoeyes.processing.ps.steps.load import load_initial
from geoeyes.processing.ps.steps.reference import reference_ps
from geoeyes.processing.ps.steps.scla import calc_scla, smooth_scla
from geoeyes.processing.ps.steps.scn_filt import scn_filt
from geoeyes.processing.ps.steps.select import select
from geoeyes.processing.ps.steps.unwrap import Scla, unwrap
from geoeyes.processing.ps.steps.velocity import velocity
from geoeyes.processing.ps.steps.weed import weed

log = logging.getLogger(__name__)
ENGINE = "geoeyes-ps/4"              # /2: height-error geolocation moves away from the sensor (sign fixed)
# /3: the weather-model APS is centred per interferogram (scene-wide offsets removed)
# /4: without a reference area, every interferogram is referenced to the scene mean (pass-2 unwrapping offsets)
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
        resume_from: str | Path | None = None) -> dict:
    """``table``: StaMPS-named parameters (project ``[ps]``); missing keys take the legacy defaults;
    ``max_topo_err = "auto"``: median height of ambiguity / 4 (pairs with |B⊥| >= ``hoa_max_perp`` left out).
    ``weather`` (``atmosphere.weather.WeatherParams``): ERA5/GACOS APS removed in pass 2 instead of the linear one.
    ``slc_var``: ``slc_linked`` to run on the phase-linked stack; ``ds_tcoh_min`` then also takes distributed
    scatterers (best phase-linking temporal coherence per ``ds_cell``² block) as candidates.
    Every run keeps its steps 1-5 in ``checkpoint_step5.pkl``; ``resume_from`` (a previous run folder) reuses
    them and unwraps again (steps 6-8: unwrap, SCLA, APS, reference, velocity, SCN parameters may change; the
    candidate / gamma / select / weed parameters and the stack must be the same)."""
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
    if resume_from is None:
        C = _candidates(ds, dates, mi, sec_ix, wl, args, log)
        L = load_initial(ij=np.column_stack([np.arange(C["n"]), C["r"], C["c"]]), lonlat=C["lonlat"], ph=C["ph"],
                         master=master, secondaries=secs, bperp_mat=C["bperp_mat"], inc=C["inc"],
                         heading=float(attrs["heading_deg"]) % 360.0, mean_range=C["mean_range"], hgt=C["hgt"],
                         da=C["da"], coh=C["coh"], log=log)
        for k in ("r", "c", "lonlat", "ph", "bperp_mat", "hgt", "da", "coh"):
            del C[k]                                 # kept in L
        event(log, "progress", "step 1", stage="ps", done=2, total=9)
    else:
        ck = load_checkpoint(Path(resume_from))
        L, C = ck["L"], ck["cand"]
        log.info("resumed from %s: steps 1-5 reused, unwrapping again", resume_from)
    inc, rng, is_ds = C["inc"], C["rng"], C["is_ds"]
    if str((table or {}).get("max_topo_err", "")).lower() == "auto":
        mte = hoa_max_topo_err(ds["bperp"].values, wl, float(np.nanmedian(ds["geometry_slant_range"].values)),
                               np.radians(float(np.nanmedian(ds["geometry_incidence"].values))), hoa_max_perp)
        table = {**table, "max_topo_err": mte}
        log.info("max_topo_err = median height of ambiguity / 4 = %.2f m", mte)
    prm = engine_params(table, wavelength=wl, rho=C["mean_range"])
    fingerprint = sha256_params({"args": args, "est_gamma": repr(prm.est_gamma), "select": repr(prm.select),
                                 "weed": repr(prm.weed)})
    est = None
    if resume_from is not None:
        if ck["fingerprint"] != fingerprint:
            raise DataError(f"{resume_from}: steps 1-5 were run with other candidate / gamma / select / weed "
                            "parameters or another stack; run without resume_from")
        est = ck["est"]
    aps_model = None
    if weather is not None:
        times = acquisition_times(dict(attrs), dates, weather.fallback_utc)

        def aps_model(ix):
            return weather_aps(weather, lon=L.lonlat[ix, 0], lat=L.lonlat[ix, 1], hgt=L.hgt[ix],
                               incidence=inc[L.cand_ix[ix]], times=times, master_ix=L.master_ix, wavelength=wl)
    P = process(L, prm, wl, aps_model=aps_model, aps_select=weather.select if weather is not None else "auto",
                est=est)
    if resume_from is None:
        import dataclasses
        e = P.estimated
        none = np.zeros((0, 0), np.complex64)        # arrays only steps 2-5 read
        save_checkpoint(out, {"L": dataclasses.replace(L, ph=none), "cand": C, "fingerprint": fingerprint,
                              "est": Estimated(None, dataclasses.replace(e.select, ph_patch2=none, ph_res2=none),
                                               dataclasses.replace(e.weed, ph_res=none),
                                               dataclasses.replace(e.correct, ph_reref=none))})
    s, w, ix, u, aps, sc, sm, vel, scn = P.select, P.weed, P.ix, P.unwrapped, P.aps, P.scla, P.scla_smooth, \
        P.velocity, P.scn
    bp_ix, hgt_ix = L.bperp_mat[ix], L.hgt[ix]

    # ---------------------------------------------------------------- outputs
    line, sample = L.ij[ix, 1], L.ij[ix, 2]
    orig = L.cand_ix[ix]
    inc_ps, rng_ps = inc[orig], rng[orig]
    dem_err = -sm.K_uw * wl * rng_ps * np.sin(inc_ps) / (4 * np.pi)
    lat_ps, lon_ps = geolocate(L.lonlat[ix, 1].astype(np.float64), L.lonlat[ix, 0].astype(np.float64),
                               np.degrees(inc_ps), float(attrs["heading_deg"]), str(attrs.get("look_side", "right")),
                               dem_err)
    height = (hgt_ix + dem_err).astype(np.float32)
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
               "velocity_mm_yr": {"min": float(np.nanmin(v)), "max": float(np.nanmax(v)),
                                  "p02": float(np.nanpercentile(v, 2)), "median": float(np.nanmedian(v)),
                                  "p98": float(np.nanpercentile(v, 98))},
               "runtime_s": round(time.time() - t0, 1)}
    params_snapshot = {"table": table or {}, "da_max": da_max, "amp_floor": amp_floor, "smooth_sigma": smooth_sigma,
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


CHECKPOINT = "checkpoint_step5.pkl"


def save_checkpoint(out: Path, data: dict) -> Path:
    """Steps 1-5 state of a run (to unwrap again with other parameters: ``run(..., resume_from=out)``)."""
    import pickle
    p = Path(out) / CHECKPOINT
    tmp = p.with_suffix(".part")
    with open(tmp, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(p)
    return p


def load_checkpoint(run_dir: Path) -> dict:
    """The checkpoint a previous run wrote in ``run_dir`` (written by this engine; not for untrusted files)."""
    import pickle
    p = Path(run_dir) / CHECKPOINT
    if not p.exists():
        raise DataError(f"{run_dir}: no {CHECKPOINT} (run the full engine first)")
    with open(p, "rb") as f:
        return pickle.load(f)


def _candidates(ds, dates, mi, sec_ix, wl, args, log) -> dict:
    """D_A (+ DS) candidates of the stack with their phase, geometry and prior coherence."""
    slc = ds[args["slc_var"]].values
    da_max, ds_tcoh_min, ds_cell = args["da_max"], args["ds_tcoh_min"], args["ds_cell"]
    disp = cd.amplitude_dispersion(lambda k, a=slc: np.abs(a[k]), len(dates), smooth_sigma=args["smooth_sigma"],
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
    ph = np.stack([slc[mi][r, c] * np.conj(slc[k][r, c]) for k in sec_ix], axis=1).astype(np.complex64)
    coh_ifg = np.stack([cd.pair_coherence(slc[mi], slc[k], r, c) for k in sec_ix], axis=1)
    coh = cd.prior_coherence(coh_ifg, ph)
    rng = ds["geometry_slant_range"].values[r, c].astype(np.float64)
    inc = np.radians(ds["geometry_incidence"].values[r, c].astype(np.float64))
    kh = ds["kh"].values[:, r, c].astype(np.float64)
    # topographic phase kh·dh = K·B⊥  with  kh = -4π B⊥ / (λ R sinθ)
    bperp_mat = -(kh[sec_ix] - kh[mi]).T * wl * (rng * np.sin(inc))[:, None] / (4 * np.pi)
    del slc
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
    ifg_std: np.ndarray | None = None       # (n_ifg,) step-5 phase noise per epoch, degrees
    estimated: Any = None                   # Estimated (steps 2-5), what a checkpoint keeps


@dataclass
class Estimated:
    """Steps 2-5 (what the unwrapping and the later steps need)."""
    gamma: Any                # None when resumed from a checkpoint (not stored)
    select: Any
    weed: Any
    correct: Any


def estimate(L, prm) -> Estimated:
    """Steps 2-5 on the step-1 state ``L``: estimate gamma, select, weed, correct phase."""
    g = est_gamma(ph=L.ph, bperp=L.bperp, bperp_mat=L.bperp_mat, master_ix=L.master_ix, xy=L.xy, la=L.la, da=L.da,
                  coh_prior=L.coh, params=prm.est_gamma)
    event(log, "progress", "step 2", stage="ps", done=3, total=9)
    s = select(ph=L.ph, bperp=L.bperp, bperp_mat=L.bperp_mat, master_ix=L.master_ix, xy=L.xy, forced=L.forced,
               da=L.da, gamma=g, params=prm.select)
    event(log, "progress", "step 3", stage="ps", done=4, total=9)
    w = weed(ph=L.ph, bperp=L.bperp, day=L.day, master_ix=L.master_ix, xy=L.xy, ij=L.ij, forced=L.forced,
             hgt=L.hgt, ph_patch=g.ph_patch, sel=s, params=prm.weed)
    log.info("PS: %d candidates -> %d selected -> %d after weeding", L.n_ps, int(s.keep_ix.sum()), w.ix.size)
    cp = correct_phase(ph=L.ph[w.ix], bperp_mat=L.bperp_mat[w.ix], K=w.K, C=w.C, ph_patch=w.ph_patch,
                       master_ix=L.master_ix)
    event(log, "progress", "steps 4-5", stage="ps", done=5, total=9)
    return Estimated(g, s, w, cp)


def process(L, prm, wavelength: float, *, scn_filter_xy: np.ndarray | None = None, scn_method: str = "grid",
            aps_model=None, aps_select: str = "auto", est: Estimated | None = None) -> Processed:
    """Steps 2-8 on the step-1 state ``L`` (``est``: steps 2-5 already done, e.g. from a checkpoint): estimate
    gamma, select, weed, correct phase, unwrap (pass 1, linear APS, SCLA; pass 2 with SCLA + APS removed when
    ``prm.two_pass``), SCLA, velocity, SCN. ``aps_model(ix)``: weather-model APS (len(ix), n_ifg) of the weeded
    PS; ``aps_select`` "auto": used for the interferograms where it explains the pass-1 residual phase better than
    the linear APS, "all": for every interferogram (the linear APS where it has no data)."""
    est = est or estimate(L, prm)
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
                   deramp_scla=prm.scla_deramp, legacy=prm.legacy, ref_ps=ref)
    event(log, "progress", "pass 1", stage="ps", done=6, total=9)
    if prm.two_pass:
        sm = smooth_scla(sc, xy_ix, bp_ix)
        u = unwrap(**common, scla=Scla(sm.K_uw, sm.C_uw, sm.ph_ramp if sm.ph_ramp.size else None), aps=aps)
        sc = calc_scla(ph_uw=u.ph_uw, bperp_mat=bp_ix, ifgday=L.ifgday, master_ix=L.master_ix, xy=xy_ix, aps=aps,
                       deramp_scla=prm.scla_deramp, legacy=prm.legacy, ref_ps=ref)
    sm = smooth_scla(sc, xy_ix, bp_ix)
    event(log, "progress", "pass 2", stage="ps", done=7, total=9)
    vel = velocity(ph_uw=u.ph_uw, scla=sc, aps=aps if prm.two_pass else None, ifgday=L.ifgday, day=L.day,
                   master_ix=L.master_ix, xy=xy_ix, lonlat=L.lonlat[ix], hgt=hgt_ix, wavelength=wavelength,
                   deramp=prm.scla_deramp, ifg_std_deg=None if prm.legacy else cp.ifg_std, legacy=prm.legacy,
                   demean=ref is None and not prm.legacy)
    if ref is not None:
        # velocity and time series are linear in the phase: referencing the phase to the reference PS (StaMPS
        # ps_setref) shifts them by the reference mean; the high-pass correction removes a plane, so it stays
        off = float(np.nanmean(vel.v_linear[ref]))
        vel.v, vel.v_linear = vel.v - off, vel.v_linear - off
        vel.ts_mm = (vel.ts_mm - np.nanmean(vel.ts_mm[ref], axis=0)).astype(np.float32)
    scn = scn_filt(ph_uw=u.ph_uw, ph_scla=sc.ph_scla, C_uw=sc.C_uw, ph_ramp=sc.ph_ramp, day=L.day,
                   master_ix=L.master_ix, xy=xy_ix, filter_xy=None if scn_filter_xy is None else scn_filter_xy[ix],
                   time_win=prm.scn_time_win, wavelength=prm.scn_wavelength, method=scn_method,
                   time_fit=prm.scn_time_fit)
    # StaMPS "v-dso": SCN removed too (referenced to the reference PS / the scene mean instead of PS 0); no
    # high-pass correction, the SCN is that noise
    scn_ref = np.nanmean(scn.ph_scn[ref if ref is not None else slice(None)], axis=0)
    vel_scn = velocity(ph_uw=u.ph_uw - (scn.ph_scn - scn_ref), scla=sc, aps=aps if prm.two_pass else None,
                       ifgday=L.ifgday, day=L.day, master_ix=L.master_ix, xy=xy_ix, lonlat=L.lonlat[ix], hgt=hgt_ix,
                       wavelength=wavelength, deramp=prm.scla_deramp,
                       ifg_std_deg=None if prm.legacy else cp.ifg_std, legacy=prm.legacy, highpass=False,
                       demean=ref is None and not prm.legacy)
    if ref is not None:
        vel_scn.v = vel_scn.v - float(np.nanmean(vel_scn.v[ref]))
        vel_scn.ts_mm = (vel_scn.ts_mm - np.nanmean(vel_scn.ts_mm[ref], axis=0)).astype(np.float32)
    event(log, "progress", "steps 7-8", stage="ps", done=8, total=9)
    return Processed(gamma=g, select=s, weed=w, ix=ix, unwrapped=u, aps=aps, scla=sc, scla_smooth=sm, velocity=vel,
                     scn=scn, ref_ps=ref, aps_linear=aps_lin, aps_choice=aps_choice, velocity_scn=vel_scn,
                     ifg_std=cp.ifg_std, estimated=est)


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
