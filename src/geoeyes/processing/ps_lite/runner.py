"""ps_lite runner on a StackStore (port of ``modules.ps_stack.run_stack``, ADR-020).

Steps (unchanged from ``run_stack``): reference epoch, PS selection (D_A + range spectral diversity,
best per cell), two-pass refined-IRLS unwrapping of the PS grid with a height-error periodogram
in between, reference area, weighted least squares per PS (LOS velocity, height error, reference
term) with a spatially filtered APS and per-interferogram quality weights.

Output folder ``ps_runs/<psrun_id>/`` (ARCHITECTURE §10.3)::

    manifest.json  params.json
    state.h5        engine state, schema ``geoeyes.ps_lite`` v1
    pairs.parquet   per-interferogram quality
    points.parquet  kept PS (GeoParquet: point_uid, lon/lat, velocity, height error, quality ...)
    timeseries.parquet
    figures/*.png
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

from geoeyes.config.schema import PsLiteSection
from geoeyes.core.errors import ConfigError, DataError
from geoeyes.core.geodesy import geohash
from geoeyes.core.hashing import sha256_params
from geoeyes.core.logging import event
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.io.points import write_points, write_timeseries
from geoeyes.io.state import StateSchema, StateStore, VarSpec
from geoeyes.processing.phase_linking.runner import provenance as pl_provenance
from geoeyes.processing.ps_lite import inputs as inp_mod
from geoeyes.processing.ps_lite import invert as inv
from geoeyes.processing.ps_lite import ps as psmod
from geoeyes.processing.ps_lite import unwrap as uwmod

log = logging.getLogger(__name__)
ENGINE = "geoeyes-ps_lite/2"         # /2: height-error geolocation moves away from the sensor (sign fixed)
SIGN = 1.0          # flattened stack, SLC phase exp(-j 4 pi R / lambda) (stack attr phase_convention)

STATE_SCHEMA = StateSchema.of("geoeyes.ps_lite", 1, [
    VarSpec("candidates/line", "int32", ("ps",), description="stack row"),
    VarSpec("candidates/sample", "int32", ("ps",), description="stack column"),
    VarSpec("candidates/da", "float32", ("ps",), description="amplitude dispersion"),
    VarSpec("candidates/sd", "float32", ("ps",), description="range spectral diversity"),
    VarSpec("candidates/amp", "float32", ("ps",), description="mean calibrated amplitude"),
    VarSpec("geometry/kh", "float32", ("ps", "ifg"), "rad/m", "height sensitivity per interferogram"),
    VarSpec("geometry/h_ortho", "float32", ("ps",), "m", "DEM orthometric height"),
    VarSpec("geometry/lat", "float64", ("ps",), "deg"),
    VarSpec("geometry/lon", "float64", ("ps",), "deg"),
    VarSpec("phase/wrapped", "float32", ("ps", "ifg"), "rad"),
    VarSpec("phase/grid", "float32", ("ps", "ifg"), "rad", "unwrapped grid phase at the PS cell"),
    VarSpec("phase/unwrapped", "float32", ("ps", "ifg"), "rad"),
    VarSpec("phase/tropo_removed", "float32", ("ps", "ifg"), "rad"),
    VarSpec("phase/weather_aps", "float32", ("ps", "ifg"), "rad", "ERA5/GACOS APS removed (0 where not used)"),
    VarSpec("reference/phase", "float32", ("ifg",), "rad"),
    VarSpec("inversion/v_mm_yr", "float32", ("ps",), "mm/yr", "LOS velocity toward the satellite"),
    VarSpec("inversion/v_std_mm_yr", "float32", ("ps",), "mm/yr"),
    VarSpec("inversion/dh_m", "float32", ("ps",), "m", "height error vs DEM"),
    VarSpec("inversion/c_rad", "float32", ("ps",), "rad", "reference-epoch term"),
    VarSpec("inversion/rmse_mm", "float32", ("ps",), "mm"),
    VarSpec("inversion/phase_std", "float32", ("ps",), "rad"),
    VarSpec("inversion/tcoh", "float32", ("ps",), "", "phase coherence after height correction"),
    VarSpec("inversion/disp_mm", "float32", ("ps", "epoch"), "mm", "LOS displacement toward the satellite"),
    VarSpec("inversion/aps", "float32", ("ps", "ifg"), "rad"),
    VarSpec("time/epoch_dates", "S10", ("epoch",)),
    VarSpec("time/ifg_dates", "S10", ("ifg",)),
])


def _weather_aps(weather, inp, epochs, ifgs, ref_ix, pset, h_ortho, kh, t_days, wl, ph_uw1):
    """Weather-model APS (n, K) of the PS for the interferograms (vs ``epochs[ref_ix]``) where it is used, and the
    (K,) use flags: ``select = "auto"`` keeps it where it explains the pass-1 unwrapped phase ``ph_uw1`` better
    than no APS (per-PS linear motion + height error removed first), ``all`` everywhere it has data."""
    from geoeyes.processing.atmosphere.times import acquisition_times
    from geoeyes.processing.atmosphere.weather import weather_aps
    from geoeyes.processing.ps.aps import choose_aps
    times = acquisition_times(inp.attrs, [e.date for e in epochs], weather.fallback_utc)
    lat, lon = _ps_geolocate(inp, pset.line, pset.sample, np.zeros(len(pset)))
    inc = np.radians(inp.incidence[pset.line, pset.sample])
    full = weather_aps(weather, lon=lon, lat=lat, hgt=h_ortho, incidence=inc, times=times, master_ix=ref_ix,
                       wavelength=wl)                                   # (n, n_epoch), reference column 0
    sec = [g.sec for g in ifgs]
    w = full[:, sec]
    if weather.select == "auto":
        ins = (lambda a: np.insert(a, ref_ix, 0.0, axis=1))  # noqa: E731
        _, use, var = choose_aps(ph_uw1, ins(w), np.zeros((len(pset), len(epochs))), t_days, kh, ref_ix)
        for k, g in enumerate(ifgs):
            log.info("APS %s: %s (residual %.2f, - weather %.2f, - none %.2f rad2)", g.date,
                     "weather" if use[k] else "none", *var[:, k])
    else:
        use = np.any(np.isfinite(w), axis=0)
    log.info("%s APS removed for %d of %d interferograms", weather.method.upper(), int(use.sum()), use.size)
    return np.where(use[None, :] & np.isfinite(w), w, 0.0).astype(np.float32), use


def _ps_geolocate(inp: inp_mod.StackInputs, line, sample, dh):
    """lat/lon of each PS: stack geometry at its pixel, moved away from the sensor by dh / tan(θ)
    (``ps.geometry.geolocate``; Capella can look left)."""
    from geoeyes.processing.ps.geometry import geolocate
    return geolocate(inp.lat[line, sample], inp.lon[line, sample], inp.incidence[line, sample], inp.heading_deg,
                     str(inp.attrs.get("look_side", "right")), dh)


def run(store, out_dir: str | Path, params: PsLiteSection | None = None, *, run_id: str = "",
        track_id: str = "", psrun_id: str = "", slc_var: str = "slc", weather=None) -> dict:
    """Run ps_lite on a flattened StackStore (``slc_var="slc_linked"`` after phase linking). ``weather``
    (``atmosphere.weather.WeatherParams``): ERA5/GACOS APS removed before the second unwrapping pass, for the
    interferograms where it explains the pass-1 residual phase (``select = "auto"``) or for all of them."""
    p = params or PsLiteSection()
    t0 = time.time()
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    inp = inp_mod.load(store, geo_step=tuple(p.geo_step), slc_var=slc_var)
    epochs, geo, wl = inp.epochs, inp.geo, inp.wavelength
    if p.exclude_dates:
        drop = {str(x) for x in p.exclude_dates}
        keep = [k for k, e in enumerate(epochs) if e.date.strftime("%Y%m%d") not in drop]
        epochs = [epochs[k] for k in keep]
        inp.kh, inp.bperp = inp.kh[keep], inp.bperp[keep]
        inp.epochs = epochs
    ny, nx = epochs[0].slc.shape
    win = tuple(p.window) if p.window else (0, ny, 0, nx)
    log.info("ps_lite: %d epochs, grid %dx%d, window %s", len(epochs), ny, nx, win)

    if p.ref_date in ("", "coreg", "stack"):
        ref_ix = next(k for k, e in enumerate(epochs) if e.days == 0)
    elif p.ref_date == "auto":
        ref_ix = int(np.argmin(inp_mod.longest_baselines(inp.bperp)))
    else:
        hits = [k for k, e in enumerate(epochs) if e.date.strftime("%Y%m%d") == str(p.ref_date)]
        if not hits:
            raise DataError(f"no epoch on {p.ref_date}")
        ref_ix = hits[0]
    ifgs = inp_mod.make_ifgs(inp, ref_ix)
    ref_ep = epochs[ref_ix]
    log.info("reference epoch %s; Bperp: %s", ref_ep.date, ", ".join(f"{g.date:%d/%m} {g.bperp:.0f} m" for g in ifgs))

    pset = psmod.select_and_extract(epochs, ifgs, geo, win, SIGN, da_max=p.da_max, sd_max=p.sd_max,
                                    cell=tuple(p.ps_cell), amp_floor_pct=p.amp_floor_pct,
                                    block_lines=p.block_lines)
    log.info("PS: %d (D_A <= %s: %d; with spectral diversity <= %s: %d), amplitude floor %.3f, band %.3f fs",
             len(pset), p.da_max, pset.n_da, p.sd_max, pset.n_candidates, pset.amp_floor, pset.band)
    if len(pset) < 100:
        raise DataError(f"too few PS ({len(pset)})")

    pts = np.stack([pset.line, pset.sample], axis=-1).astype(float)
    h_ortho = geo.interpolator(geo.h_ortho)(pts)
    spec = uwmod.GridSpec.for_window(win, tuple(p.uw_cell))
    iy, ix = spec.index(pset.line, pset.sample)
    if p.unwrap_method != "s1":
        raise ConfigError(f"ps_lite.unwrap_method {p.unwrap_method!r}: the legacy Capella solver was not ported "
                          "(use 's1')")
    t_days = np.array([g.days for g in ifgs])

    def stack_costs(phase, weight=None):
        Z, near = uwmod.filled_grid_stack(phase, iy, ix, spec, weight)
        return uwmod.space_time_costs(Z, near, t_days)

    K = len(ifgs)
    kh = np.stack([g.kh_spline.ev(pset.line, pset.sample) for g in ifgs], axis=1)
    uw_kw = dict(gs_alpha=p.gs_alpha, gs_win=p.gs_win, gs_passes=p.gs_passes, irls_iter=p.irls_iter,
                 method=p.unwrap_method)

    def common_offset_removed(r):
        return uwmod.wrap(r - np.angle(np.exp(1j * r).mean(axis=0)))

    dh_topo = np.zeros(len(pset), np.float32)
    patch = None
    if p.unwrap_input == "patch" and not (p.topo_first and p.topo_first_method == "gamma"):
        raise DataError("unwrap_input='patch' needs topo_first=true with topo_first_method='gamma'")
    if p.topo_first:
        if p.topo_first_method == "gamma":
            lat_t, lon_t = _ps_geolocate(inp, pset.line, pset.sample, np.zeros(len(pset)))
            dh_topo, gam_t, patch = _topo_first_gamma(pset.phase, kh, lat_t, lon_t, pset.da, wl, p)
        else:
            dh_topo, gam_t = _topo_first(pset.phase, kh, iy, ix, spec, p)
        pset.phase = uwmod.wrap(pset.phase - SIGN * kh * dh_topo[:, None]).astype(np.float32)
        log.info("topo-first: height error median %.1f m (P5..P95 %.1f..%.1f), coherence median %.2f",
                 np.median(dh_topo), np.percentile(dh_topo, 5), np.percentile(dh_topo, 95), np.median(gam_t))

    use_patch = p.unwrap_input == "patch"
    G = np.empty((len(pset), K), np.float32)
    src = patch if use_patch else pset.phase
    costs = stack_costs(src)
    for k in range(K):
        G[:, k] = uwmod.unwrap_pair(src[:, k], iy, ix, h_ortho, spec, wl, SIGN, tropo=False,
                                    costs=costs[k], **uw_kw).grid_phase
        event(log, "progress", f"unwrap pass 1 {k + 1}/{K}", stage="ps_lite", done=k + 1, total=2 * K)
    if use_patch:            # topography already removed by the gamma estimator; residuals are PS noise
        dh0, gam0 = np.zeros(len(pset), np.float32), np.nan_to_num(np.asarray(gam_t, np.float64))
    else:
        dh0, gam0 = inv.height_error_periodogram(common_offset_removed(uwmod.wrap(pset.phase - G)), kh, SIGN)
    log.info("pass 1: PS height error median %.1f m (P5..P95 %.1f..%.1f), coherence median %.2f",
             np.median(dh0), np.percentile(dh0, 5), np.percentile(dh0, 95), np.median(gam0))

    wps = np.clip((gam0 - 0.3) / 0.5, 0.05, 1.0)
    aps_w, aps_use = np.zeros((len(pset), K), np.float32), np.zeros(K, bool)
    if weather is not None and not use_patch:
        aps_w, aps_use = _weather_aps(weather, inp, epochs, ifgs, ref_ix, pset, h_ortho, kh, t_days, wl,
                                      G + uwmod.wrap(pset.phase - G))
    ph_topo = uwmod.wrap(pset.phase - SIGN * kh * dh0[:, None] - aps_w)
    ph_w = np.empty((len(pset), K), np.float32)
    tropo_rm = np.zeros((len(pset), K), np.float32)
    rows = []
    src = patch if use_patch else ph_topo
    costs = stack_costs(src, wps)
    for k, g in enumerate(ifgs):
        r = uwmod.unwrap_pair(src[:, k], iy, ix, h_ortho, spec, wl, SIGN, tropo=p.tropo and not use_patch,
                              remove_plane=p.remove_plane, ps_weight=wps, costs=costs[k], **uw_kw)
        G[:, k], ph_w[:, k] = r.grid_phase, (ph_topo[:, k] if use_patch else r.wrapped)
        if r.tropo_removed is not None:
            tropo_rm[:, k] = r.tropo_removed
        t = r.tropo
        rows.append({"date": g.date.isoformat(), "days": round(g.days, 3), "bperp_m": round(g.bperp, 1),
                     "hoa_m": round(g.hoa, 2), "unwrap_rms": round(r.rms, 4), "cells": r.n_cells,
                     "islands": r.n_components,
                     "tropo_k_rad_km": None if t is None else round(t.k_rad_per_m * 1e3, 3),
                     "weather_aps": bool(aps_use[k])})
        event(log, "progress", f"unwrap pass 2 {k + 1}/{K}", stage="ps_lite", done=K + k + 1, total=2 * K)

    ddh, gam1 = inv.height_error_periodogram(common_offset_removed(uwmod.wrap(ph_w - G)), kh, SIGN,
                                             dh_max=5.0, step=0.5)
    dh1 = dh0 + ddh
    topo = SIGN * kh * dh1[:, None]
    ph_full = uwmod.wrap(ph_w + SIGN * kh * dh0[:, None])       # weather APS stays removed
    ph_uw = (G + topo + uwmod.wrap(ph_full - G - topo)).astype(np.float32)
    if p.topo_first:                          # put the pre-removed topography back: the inversion fits all of it
        ph_uw = (ph_uw + SIGN * kh * dh_topo[:, None]).astype(np.float32)
        pset.phase = uwmod.wrap(pset.phase + SIGN * kh * dh_topo[:, None]).astype(np.float32)
        dh1 = dh1 + dh_topo
    log.info("pass 2: height correction median %.2f m; PS phase coherence median %.2f", np.median(ddh),
             np.median(gam1))

    lat0, lon0 = _ps_geolocate(inp, pset.line, pset.sample, np.zeros(len(pset)))
    lat_c = np.radians(np.nanmean(lat0))
    xy = np.stack([(lon0 - np.nanmean(lon0)) * 111320 * np.cos(lat_c), (lat0 - np.nanmean(lat0)) * 110574], -1)
    if p.ref_latlon is not None:
        centre = np.array([(p.ref_latlon[1] - np.nanmean(lon0)) * 111320 * np.cos(lat_c),
                           (p.ref_latlon[0] - np.nanmean(lat0)) * 110574])
    else:
        centre = inv.auto_reference(xy, pset.da, p.ref_radius_m)
    ref, n_ref = inv.reference_phase(ph_uw, xy, centre, p.ref_radius_m)
    ph_ref = ph_uw - ref[None, :]
    ref_lat = float(centre[1] / 110574 + np.nanmean(lat0))
    ref_lon = float(centre[0] / (111320 * np.cos(lat_c)) + np.nanmean(lon0))
    log.info("reference point %.5f, %.5f (%d PS within %g m)", ref_lat, ref_lon, n_ref, p.ref_radius_m)

    t_yr = t_days / 365.25
    az_m = float(inp.attrs.get("azimuth_pixel_spacing_m", 14.0))
    rg_m = float(inp.attrs.get("range_pixel_spacing_m", 2.33)) / np.sin(np.radians(np.nanmean(inp.incidence)))
    sig = (p.aps_sigma_m / (spec.cell[0] * az_m), p.aps_sigma_m / (spec.cell[1] * rg_m))

    def aps_fn(resid):
        res = np.empty_like(resid)
        wsum = np.zeros((spec.ny, spec.nx))
        np.add.at(wsum, (iy, ix), wps)
        den = gaussian_filter(wsum, sig, mode="nearest")
        for k in range(resid.shape[1]):
            gg = np.zeros((spec.ny, spec.nx))
            np.add.at(gg, (iy, ix), wps * resid[:, k])
            res[:, k] = (gaussian_filter(gg, sig, mode="nearest") / np.maximum(den, 1e-12))[iy, ix]
        return res

    res, q, wk = inv.invert_weighted(ph_ref, t_yr, kh, wl, SIGN, aps_fn=aps_fn if p.aps_sigma_m > 0 else None,
                                     std_max=p.ifg_std_max, mask=gam1 >= p.tcoh_min)
    for k, r_ in enumerate(rows):
        r_["phase_std_rad"] = round(float(q[k]), 3)
        r_["used"] = bool(wk[k] > 0)
    tcoh = gam1
    good = (tcoh >= p.tcoh_min) & (res.phase_std <= p.phase_std_max)
    log.info("inversion: median RMSE %.1f mm; %d / %d PS kept (tcoh >= %s, phase std <= %s rad); %d ifgs dropped",
             np.median(res.rmse_mm), good.sum(), len(pset), p.tcoh_min, p.phase_std_max, int((wk == 0).sum()))

    # ---------------------------------------------------------------- outputs
    lat, lon = _ps_geolocate(inp, pset.line, pset.sample, res.dh_m)
    disp = np.zeros((len(pset), len(epochs)), np.float32)
    for k, g in enumerate(ifgs):
        disp[:, g.sec] = res.disp_mm[:, k]
    st = StateStore(out / "state.h5", STATE_SCHEMA)
    st.write_many({
        "candidates/line": pset.line, "candidates/sample": pset.sample, "candidates/da": pset.da,
        "candidates/sd": pset.sd, "candidates/amp": pset.amp, "geometry/kh": kh, "geometry/h_ortho": h_ortho,
        "geometry/lat": lat, "geometry/lon": lon, "phase/wrapped": pset.phase, "phase/grid": G,
        "phase/unwrapped": ph_uw, "phase/tropo_removed": tropo_rm, "phase/weather_aps": aps_w,
        "reference/phase": ref,
        "inversion/v_mm_yr": res.v_mm_yr, "inversion/v_std_mm_yr": res.v_std_mm_yr, "inversion/dh_m": res.dh_m,
        "inversion/c_rad": res.c_rad, "inversion/rmse_mm": res.rmse_mm, "inversion/phase_std": res.phase_std,
        "inversion/tcoh": tcoh, "inversion/disp_mm": disp, "inversion/aps": res.aps,
        "time/epoch_dates": np.array([e.date.isoformat() for e in epochs], "S10"),
        "time/ifg_dates": np.array([g.date.isoformat() for g in ifgs], "S10")})
    st.mark_done("ps_lite")
    pd.DataFrame(rows).to_parquet(out / "pairs.parquet", index=False)

    import geopandas as gpd
    sel = np.flatnonzero(good)
    h_true = h_ortho + res.dh_m
    uid = np.char.add(np.char.add(f"{track_id or 'track'}:", geohash(lat[sel], lon[sel])),
                      np.char.add(":", np.round(h_true[sel]).astype(int).astype(str)))
    _, first = np.unique(uid, return_index=True)          # one point per uid (ADR-018)
    sel, uid = sel[np.sort(first)], uid[np.sort(first)]
    gdf = gpd.GeoDataFrame({
        "point_uid": uid, "lon": lon[sel], "lat": lat[sel], "line": pset.line[sel], "sample": pset.sample[sel],
        "height_m": h_true[sel].astype(np.float32), "dem_err_m": res.dh_m[sel], "type": "PS",
        "vel_los_mm_yr": res.v_mm_yr[sel], "vel_std_mm_yr": res.v_std_mm_yr[sel],
        "temporal_coherence": tcoh[sel], "amp_dispersion": pset.da[sel], "spectral_diversity": pset.sd[sel],
        "fit_rmse_mm": res.rmse_mm[sel], "phase_std_rad": res.phase_std[sel],
        "incidence_deg": inp.incidence[pset.line[sel], pset.sample[sel]].astype(np.float32)},
        geometry=gpd.points_from_xy(lon[sel], lat[sel]), crs="EPSG:4326")
    write_points(out / "points.parquet", gdf, metadata={"engine": ENGINE, "reference_date": ref_ep.date.isoformat(),
                                                         "reference_point": [ref_lat, ref_lon],
                                                         "sign_convention": "LOS toward the satellite positive"})
    write_timeseries(out / "timeseries.parquet", uid, np.array([e.date for e in epochs], "datetime64[D]"),
                     disp[sel])                                   # reference epoch = 0 by construction
    title = f"{track_id} {epochs[0].date:%d/%m/%Y}-{epochs[-1].date:%d/%m/%Y}, {len(sel)} PS"
    figs = _quicklooks(out / "figures", lat[sel], lon[sel], res.v_mm_yr[sel], res.dh_m[sel], tcoh[sel],
                       (ref_lat, ref_lon), title)

    v = res.v_mm_yr[sel]
    summary = {
        "engine": ENGINE, "reference_date": ref_ep.date.isoformat(), "epochs": len(epochs), "window": list(win),
        "reference": {"lat": ref_lat, "lon": ref_lon, "n_ps": n_ref, "given": p.ref_latlon is not None},
        "ps": {"pass_da": pset.n_da, "candidates": pset.n_candidates, "selected": len(pset), "kept": int(good.sum()),
               "unique_points": len(sel),
               "rmse_mm_median": float(np.median(res.rmse_mm[good])) if good.any() else None},
        "velocity_mm_yr": {"min": float(v.min()), "max": float(v.max()), "p02": float(np.percentile(v, 2)),
                           "median": float(np.median(v)), "p98": float(np.percentile(v, 98))} if v.size else None,
        "aps": ("none" if weather is None or use_patch else
                {"method": weather.method, "select": weather.select,
                 "weather_ifgs": [g.date.isoformat() for g, u in zip(ifgs, aps_use, strict=True) if u]}),
        "ifgs_used": int((wk > 0).sum()), "runtime_s": round(time.time() - t0, 1)}
    atomic_write_json(out / "params.json", p.model_dump(mode="json"))
    m = Manifest(kind="ps_run", id=psrun_id or out.name, run_id=run_id, engine=ENGINE,
                 inputs=[InputRef("stack", str(store.path), "")],
                 params={"sha256": sha256_params(p.model_dump(mode="json")), "snapshot": "params.json"},
                 metrics=summary, extra={"pairs": rows, **pl_provenance(store, slc_var)})
    m.add_outputs(out, ["state.h5", "pairs.parquet", "points.parquet", "timeseries.parquet", "params.json",
                        *(f.relative_to(out) for f in figs)])
    m.write(out)
    log.info("ps_lite done in %.0f s: %d points -> %s", time.time() - t0, len(sel), out)
    return summary


def _topo_first(phase: np.ndarray, kh: np.ndarray, iy, ix, spec, p: PsLiteSection):
    """Height error of each PS from wrapped phase: remove the spatially smooth phase (atmosphere,
    deformation, orbit) estimated from neighbouring PS on the unwrapping grid, then search the
    height error that best explains the residual across interferograms (periodogram). The search
    step follows the smallest height of ambiguity in the stack."""
    from scipy.ndimage import uniform_filter
    z = np.exp(1j * phase.astype(np.float64))
    smooth = np.empty_like(z)
    w = p.topo_first_smooth_cells
    for k in range(phase.shape[1]):
        g = np.zeros((spec.ny, spec.nx), np.complex128)
        np.add.at(g, (iy, ix), z[:, k])
        gs = uniform_filter(g.real, w) + 1j * uniform_filter(g.imag, w)
        own = g[iy, ix]                                  # leave each cell's own PS mostly out
        smooth[:, k] = gs[iy, ix] * w * w - own + 1e-9
    resid = np.angle(z * np.conj(smooth))
    hoa_min = 2 * np.pi / max(float(np.percentile(np.abs(kh), 99)), 1e-9)
    step = max(min(hoa_min / 8.0, 1.0), 0.05)
    dh, gam = inv.height_error_periodogram(resid, kh, SIGN, dh_max=p.topo_first_dh_max, step=step,
                                           fine=step / 10.0)
    log.info("topo-first: smallest height of ambiguity %.1f m, search step %.2f m", hoa_min, step)
    return dh.astype(np.float32), gam


def _topo_first_gamma(phase, kh, lat, lon, da, wavelength, p: PsLiteSection):
    """Height error of each PS with the StaMPS step-2 estimator (``processing.ps.steps.est_gamma``): the
    interferograms are fitted against ``kh`` as the "baseline", so K is the height error itself (×SIGN)."""
    from geoeyes.processing.ps.steps.est_gamma import EstGammaParams, est_gamma
    n = phase.shape[0]
    lat_c = np.radians(np.nanmean(lat))
    x = (lon - np.nanmean(lon)) * 111320 * np.cos(lat_c)
    y = (lat - np.nanmean(lat)) * 110574
    xy = np.column_stack([np.arange(n), x, y]).astype(np.float32)
    ph = np.hstack([np.ones((n, 1), np.complex64), np.exp(1j * phase).astype(np.complex64)])
    bperp = np.r_[0.0, np.median(kh, axis=0)]
    prm = EstGammaParams(wavelength=wavelength, rho=1.0, max_K=p.topo_first_dh_max, grid_size=p.topo_first_grid_m)
    g = est_gamma(ph=ph, bperp=bperp, bperp_mat=kh.astype(np.float32), master_ix=0, xy=xy, la=None, da=da,
                  coh_prior=None, params=prm)
    dh = SIGN * np.nan_to_num(g.K)
    log.info("topo-first (gamma): %d iterations, coherence median %.2f", g.n_iter, np.nanmedian(g.coh))
    return dh.astype(np.float32), g.coh, np.angle(g.ph_patch).astype(np.float32)


def _quicklooks(out: Path, lat, lon, v, dh, tcoh, ref_latlon, title: str) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    order = np.argsort(np.abs(v))
    lim = float(np.nanmax(np.abs(v))) or 1.0                       # full velocity range
    for name, val, cmap, vmin, vmax, label in (
            ("velocity", v, "RdBu", -lim, lim, "LOS velocity toward the satellite (mm/yr)"),
            ("height_error", dh, "PuOr_r", *np.nanpercentile(dh, [2, 98]), "Height error vs DEM (m)"),
            ("temporal_coherence", tcoh, "viridis", 0, 1, "Temporal coherence")):
        fig, ax = plt.subplots(figsize=(7, 7), dpi=130)
        o = order if name == "velocity" else np.arange(len(val))
        sc = ax.scatter(lon[o], lat[o], c=val[o], s=0.6, cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0)
        ax.plot(ref_latlon[1], ref_latlon[0], marker="*", color="k", ms=12, mfc="none")
        ax.set_aspect(1 / np.cos(np.radians(np.nanmean(lat))))
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(f"{title}\n{label}", fontsize=9)
        fig.colorbar(sc, ax=ax, fraction=0.04, pad=0.02, label=label)
        fig.tight_layout()
        pth = out / f"{name}.png"
        fig.savefig(pth)
        plt.close(fig)
        paths.append(pth)
    return paths


__all__ = ["ENGINE", "STATE_SCHEMA", "run"]
