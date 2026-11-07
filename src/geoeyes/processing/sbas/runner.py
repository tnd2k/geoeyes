"""SBAS run on a StackStore: network → multilooked pairs → refined IRLS unwrapping → reference → closure check →
SVD inversion → temporal-coherence mask → points and time series in the ``ps_run`` layout (``points.parquet``,
``timeseries.parquet``, ``params.json``, ``network.json``, manifest), so that ``products.builder``, the export and
``hazard`` read it as they read the point engines.

Every multilooked pixel that passes the masks becomes a point (``type = "SBAS"``) at its block centre.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np

from geoeyes.processing.sbas import closure as cl
from geoeyes.processing.sbas import invert as iv
from geoeyes.processing.sbas import pairs as pr
from geoeyes.processing.sbas.network import Network, NetworkParams, components, select_pairs

log = logging.getLogger(__name__)

ENGINE = "geoeyes-sbas/0.1"
DAYS_PER_YEAR = 365.25
REF_MIN_VALID = 3          # reference pixels with a value a pair needs to be referenced
GEOMETRY = ("geometry_lat", "geometry_lon", "geometry_hgt", "geometry_incidence")


def network_params(network, sbas) -> NetworkParams:
    """From ``[network]`` / ``[network.sbas]`` and ``[sbas] n_nearest``."""
    days = network.sbas.max_temporal_days or network.max_temporal_days
    return NetworkParams(max_perp_m=float(network.max_perp_m), max_temporal_days=int(days),
                         n_nearest=int(sbas.n_nearest), redundant=bool(network.sbas.redundant_pairs),
                         redundant_max_days=int(network.sbas.redundant_max_days),
                         min_temporal_days=int(network.sbas.min_temporal_days))


def baseline_outliers(dates: list[date], bperp: np.ndarray, p: NetworkParams,
                      max_link_days: int = 365) -> tuple[np.ndarray, list[int]]:
    """Dates kept (stack indices) and dates left out. Without bridging, the baseline limit can cut the network into
    subsets; a subset of fewer than max(3, 10 % of the dates), typically one or two orbit outliers (Choshui desc
    105: 2024-04-10 at −435 m, 2025-05-05 at −397 m), would hang on one long bridge pair. When that pair is
    incoherent every pixel loses those dates and no series is complete, so such dates are left out; larger
    subsets are kept and bridged. Connectivity counts only pairs of at most ``max_link_days``: a date whose
    baseline-compatible pairs all span years (Choshui desc 105: 2015-04-22 at −248 m, nearest pairs 1080–1260
    days) is as cut off as one with no pair."""
    from dataclasses import replace
    net = select_pairs(dates, bperp, replace(p, bridge=False))
    span = {(i, j): (dates[j] - dates[i]).days for i, j in net.pairs}
    comps = components(len(dates), [pr for pr in net.pairs if span[pr] <= max_link_days])
    if len(comps) < 2:
        return np.arange(len(dates)), []
    small = max(3, int(0.1 * len(dates)))
    out = sorted(k for c in comps if len(c) < small for k in c)
    if len(out) == len(dates):
        return np.arange(len(dates)), []
    return np.array([k for k in range(len(dates)) if k not in set(out)]), out


def reference_mask(geo: dict, mean_coh: np.ndarray, ref: tuple[float, float] | None, half: int = 1) -> np.ndarray:
    """The pixels whose phase is set to zero: (2·half + 1)² around ``ref`` (lon, lat), else the most coherent 10 %."""
    if ref is not None:
        d = np.hypot(geo["geometry_lon"] - ref[0], (geo["geometry_lat"] - ref[1]))
        r, c = np.unravel_index(np.nanargmin(d), d.shape)
        m = np.zeros(d.shape, bool)
        m[max(r - half, 0):r + half + 1, max(c - half, 0):c + half + 1] = True
        return m
    thr = np.nanpercentile(mean_coh, 90)
    return mean_coh >= thr


def run(store, out_dir: str | Path, sbas, network, *, slc_var: str = "slc", run_id: str = "", track_id: str = "",
        psrun_id: str = "", progress=None) -> dict:
    """The SBAS engine (``sbas``: ``[sbas]``, ``network``: ``[network]``)."""
    import geopandas as gpd

    from geoeyes.core.geodesy import geohash
    from geoeyes.core.hashing import sha256_params
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.io.points import write_points, write_timeseries
    from geoeyes.processing.phase_linking.runner import provenance as pl_provenance
    say = progress or (lambda m: log.info("%s", m))
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ds = store.open()
    attrs = store.attrs
    dates = [date.fromisoformat(str(np.datetime64(d, "D"))) for d in ds["date"].values]
    all_dates = list(dates)
    wl = float(attrs["wavelength_m"])
    bperp = ds["bperp"].values.astype(float) if "bperp" in ds else np.zeros(len(dates))
    idx, outliers = baseline_outliers(dates, bperp, network_params(network, sbas))
    if outliers:
        say(f"sbas: {len(outliers)} date(s) left out, on a small subset of the network that only a bridge pair would "
            f"tie (B⊥ far from the others): {', '.join(f'{dates[k]} ({bperp[k]:+.0f} m)' for k in outliers)}")
        dates, bperp = [dates[k] for k in idx], bperp[idx]
    net = select_pairs(dates, bperp, network_params(network, sbas))
    say(f"sbas: {len(dates)} dates, {len(net.pairs)} pairs ({net.summary()['days']} days); "
        f"looks {sbas.looks_az} × {sbas.looks_rg}, source {slc_var}")
    la, lr = int(sbas.looks_az), int(sbas.looks_rg)
    geo = pr.ml_layers(store, GEOMETRY, la, lr)
    shape = geo["geometry_lat"].shape
    npx = shape[0] * shape[1]
    unw = np.full((len(net.pairs), npx), np.nan, np.float32)
    coh_sum = np.zeros(npx)
    for k, (i, j) in enumerate(net.pairs):
        ifg, coh = pr.interferogram(store, slc_var, int(idx[i]), int(idx[j]), la, lr, int(sbas.coherence_window))
        unw[k] = pr.unwrap(ifg, coh, sbas.min_pair_coherence, sbas.goldstein_alpha, int(sbas.goldstein_fft),
                           int(sbas.irls_iter), bool(sbas.link_islands)).ravel()
        coh_sum += coh.ravel()
        if (k + 1) % 10 == 0 or k + 1 == len(net.pairs):
            say(f"  pairs unwrapped {k + 1}/{len(net.pairs)}")
    mean_coh = (coh_sum / len(net.pairs)).reshape(shape)
    ref = reference_mask(geo, mean_coh, sbas.reference).ravel()
    ref_wide = (reference_mask(geo, mean_coh, sbas.reference, half=5).ravel() if sbas.reference is not None
                else ref)
    tropo = None
    tropo_mode = "off"
    day_of = np.array([(d - dates[0]).days for d in dates], np.float64)
    if sbas.troposphere is not False and "geometry_hgt" in geo:
        use = mean_coh.ravel() >= np.nanpercentile(mean_coh, 70)
        h = geo["geometry_hgt"].ravel()
        hu = h[use & np.isfinite(h)]
        relief = float(np.ptp(np.percentile(hu, [5, 95]))) if hu.size else 0.0
        if sbas.troposphere == "auto" and relief < sbas.troposphere_min_relief_m:
            say(f"sbas: stratified troposphere not removed: terrain relief {relief:.0f} m (p5-p95 of the coherent "
                f"pixels) < {sbas.troposphere_min_relief_m:.0f} m, too flat to measure it (the fit would take "
                "height-correlated deformation)")
            tropo_mode = f"off (relief {relief:.0f} m)"
        else:
            detrend = sbas.troposphere == "auto"
            unw, tropo = iv.remove_stratified(
                unw, h, use, adjust=(lambda b: iv.stratified_without_trend(b, net.pairs, day_of)) if detrend else None)
            tropo_mode = "removed without its steady trend" if detrend else "removed as fitted"
            say(f"sbas: stratified troposphere {tropo_mode} (relief {relief:.0f} m, median "
                f"{np.nanmedian(np.abs(tropo)) * 1000:.2f} rad/km)")
    with np.errstate(invalid="ignore"):
        # per pair, the median of the 3 × 3 reference; where fewer than REF_MIN_VALID of them have a value (low
        # coherence there: Choshui desc 105 at dawn, 0.1-0.2 on the reference tableland), the median of a wider
        # 11 × 11 window around it, else the pair cannot be referenced (all NaN)
        near, wide = unw[:, ref], unw[:, ref_wide]
        n_near = np.isfinite(near).sum(1)
        level = np.where(n_near >= REF_MIN_VALID, np.nanmedian(near, axis=1),
                         np.where(np.isfinite(wide).sum(1) >= REF_MIN_VALID, np.nanmedian(wide, axis=1), np.nan))
        unw -= level[:, None]
    n_wide = int(((n_near < REF_MIN_VALID) & np.isfinite(level)).sum())
    say(f"sbas: pairs referenced on the 3 × 3 reference {int((n_near >= REF_MIN_VALID).sum())}, on the wider window "
        f"{n_wide}, not referenced {int((~np.isfinite(level)).sum())}")
    masked = 0
    if sbas.closure_pixel_mask:
        unw, masked = cl.mask_bad_cells(unw, net.pairs)
    drop, clos = cl.bad_pairs(unw, net.pairs, float(sbas.closure_max_share))
    keep_pairs = [p for k, p in enumerate(net.pairs) if k not in set(drop)]
    unw = np.delete(unw, drop, axis=0)
    used = Network(net.dates, keep_pairs)
    say(f"sbas: closure over {clos['triplets']} triplets: {masked} pixel values masked, {len(drop)} pair(s) "
        "dropped")
    frac = np.isfinite(unw).mean(0)
    cand = np.flatnonzero((frac >= sbas.min_pair_fraction) & (mean_coh.ravel() >= sbas.min_mean_coherence))
    deficit = np.zeros(len(cand), int)
    vel, model = iv.invert(unw[:, cand], used.design(), min_pairs=max(1, len(dates) - 1), rank_out=deficit)
    n_pairs = np.isfinite(unw[:, cand]).sum(0)
    days = used.days()
    series = iv.displacement(vel, days)                          # phase, dates × candidates
    k_dem = np.zeros(series.shape[1])
    if sbas.dem_error:
        series, k_dem = iv.remove_dem_error(series, days, bperp)
        if np.any(k_dem):
            say(f"sbas: DEM error removed from the series (B⊥ {bperp.min():+.0f}..{bperp.max():+.0f} m; "
                f"|K| p50 {np.nanmedian(np.abs(k_dem)) * 1000:.2f} rad/km of B⊥)")
        else:
            say(f"sbas: DEM error not estimated (B⊥ spread {np.ptp(bperp):.0f} m)")
    tcoh = iv.temporal_coherence(unw[:, cand], model)
    ok = np.isfinite(series).all(0) & (tcoh >= sbas.min_temporal_coherence)
    px = cand[ok]
    fin = np.isfinite(series).all(0)
    say(f"sbas: {npx} pixels; share of the pairs with a value p50/p90/p99 "
        f"{np.percentile(frac, 50):.2f}/{np.percentile(frac, 90):.2f}/{np.percentile(frac, 99):.2f}; "
        f"{int(((frac >= sbas.min_pair_fraction)).sum())} with ≥ {sbas.min_pair_fraction:.0%} of the pairs, "
        f"{int((mean_coh.ravel() >= sbas.min_mean_coherence).sum())} with mean coherence ≥ "
        f"{sbas.min_mean_coherence}; {len(cand)} candidates, {int(fin.sum())} with a full series, temporal coherence "
        f"p50/p90 {np.nanpercentile(tcoh[fin], 50) if fin.any() else float('nan'):.2f}/"
        f"{np.nanpercentile(tcoh[fin], 90) if fin.any() else float('nan'):.2f}; {len(px)} points kept")
    if not len(px):
        from geoeyes.core.errors import DataError
        raise DataError("sbas: no pixel passes the selection (see the counts above): lower min_pair_fraction, "
                        "min_mean_coherence or min_temporal_coherence, or check the pair network")
    disp_mm = (-series[:, ok] * wl / (4 * np.pi) * 1000).T       # points × dates, + toward the satellite
    v_day, _ = iv.linear_velocity(disp_mm.T, days)
    rmse = np.sqrt(np.mean((disp_mm - (v_day[:, None] * (days - days.mean()) + disp_mm.mean(1, keepdims=True)))
                           ** 2, axis=1)) if len(px) else np.zeros(0)
    lat, lon = geo["geometry_lat"].ravel()[px], geo["geometry_lon"].ravel()[px]
    hgt = geo.get("geometry_hgt", np.zeros(shape)).ravel()[px]
    inc = geo.get("geometry_incidence", np.full(shape, np.nan)).ravel()[px]
    # DEM error (m) from K (rad per metre of B⊥): φ = 4π/λ · B⊥·Δh / (R sin θ), the sign of the ps engine
    rng = float(np.nanmedian(ds["geometry_slant_range"].values)) if "geometry_slant_range" in ds else np.nan
    dem_err = (-k_dem[ok] * wl * rng * np.sin(np.radians(inc)) / (4 * np.pi)).astype(np.float32)
    line, sample = np.divmod(px, shape[1])
    uid = np.char.add(np.char.add(f"{track_id or 'track'}:", geohash(lat, lon)),
                      np.char.add(":", np.round(hgt).astype(int).astype(str)))
    _, first = np.unique(uid, return_index=True)
    sel = np.sort(first)
    v = (v_day * DAYS_PER_YEAR)[sel]
    gdf = gpd.GeoDataFrame({
        "point_uid": uid[sel], "lon": lon[sel], "lat": lat[sel], "line": (line[sel] * la + la // 2),
        "sample": (sample[sel] * lr + lr // 2), "height_m": hgt[sel],
        "dem_err_m": dem_err[sel] if sbas.dem_error else np.full(len(sel), np.nan, np.float32),
        "type": np.full(len(sel), "SBAS"), "vel_los_mm_yr": v.astype(np.float32),
        "vel_linear_mm_yr": v.astype(np.float32), "temporal_coherence": tcoh[ok][sel].astype(np.float32),
        "amp_dispersion": np.full(len(sel), np.nan, np.float32), "fit_rmse_mm": rmse[sel].astype(np.float32),
        "incidence_deg": inc[sel].astype(np.float32), "mean_coherence": mean_coh.ravel()[px][sel].astype(np.float32),
        "n_pairs": n_pairs[ok][sel].astype(np.int16), "rank_deficit": deficit[ok][sel].astype(np.int16)},
        geometry=gpd.points_from_xy(lon[sel], lat[sel]), crs="EPSG:4326")
    write_points(out / "points.parquet", gdf, metadata={"engine": ENGINE, "reference_date": dates[0].isoformat(),
                                                         "sign_convention": "-phase·λ/4π, + toward the satellite"})
    write_timeseries(out / "timeseries.parquet", uid[sel], np.array(dates, "datetime64[D]"), disp_mm[sel])
    netinfo = {**net.summary(), "pairs_used": [[str(dates[i]), str(dates[j])] for i, j in keep_pairs],
               "dropped_by_closure": [[str(dates[net.pairs[k][0]]), str(dates[net.pairs[k][1]])] for k in drop],
               "closure_masked_values": masked,
               "dates_left_out": [str(all_dates[k]) for k in outliers],
               "troposphere_rad_per_m": None if tropo is None else np.round(tropo, 6).tolist(),
               "closure_share_bad": clos["share_bad"]}
    atomic_write_json(out / "network.json", netinfo)
    summary = {"engine": ENGINE, "reference_date": dates[0].isoformat(), "epochs": len(dates),
               "sbas": {"pairs": len(net.pairs), "pairs_used": len(keep_pairs), "grid": list(shape),
                        "candidates": int(cand.size), "points": int(sel.size)},
               "aps": "none", "troposphere": tropo_mode,
               "dem_error": bool(sbas.dem_error and np.any(k_dem)),
               "reference": ({"lon": float(sbas.reference[0]), "lat": float(sbas.reference[1])}
                             if sbas.reference is not None else "most coherent 10 % of pixels"),
               "velocity_mm_yr": ({"min": float(np.nanmin(v)), "max": float(np.nanmax(v)),
                                   "p02": float(np.nanpercentile(v, 2)), "median": float(np.nanmedian(v)),
                                   "p98": float(np.nanpercentile(v, 98))} if len(v) else {}),
               "runtime_s": round(time.time() - t0, 1)}
    snapshot = {"sbas": sbas.model_dump() if hasattr(sbas, "model_dump") else dict(sbas),
                "network": asdict(network_params(network, sbas)), "slc_var": slc_var}
    atomic_write_json(out / "params.json", snapshot)
    m = Manifest(kind="ps_run", id=psrun_id or out.name, run_id=run_id, engine=ENGINE,
                 inputs=[InputRef("stack", str(store.path), "")],
                 params={"sha256": sha256_params(snapshot), "snapshot": "params.json"}, metrics=summary,
                 extra=pl_provenance(store, slc_var))
    m.add_outputs(out, ["points.parquet", "timeseries.parquet", "params.json", "network.json"])
    m.write(out)
    say(f"sbas done in {time.time() - t0:.0f} s: {sel.size} points -> {out}")
    return summary
