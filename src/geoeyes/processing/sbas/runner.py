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
from geoeyes.processing.sbas.network import Network, NetworkParams, select_pairs

log = logging.getLogger(__name__)

ENGINE = "geoeyes-sbas/0.1"
DAYS_PER_YEAR = 365.25
GEOMETRY = ("geometry_lat", "geometry_lon", "geometry_hgt", "geometry_incidence")


def network_params(network, sbas) -> NetworkParams:
    """From ``[network]`` / ``[network.sbas]`` and ``[sbas] n_nearest``."""
    days = network.sbas.max_temporal_days or network.max_temporal_days
    return NetworkParams(max_perp_m=float(network.max_perp_m), max_temporal_days=int(days),
                         n_nearest=int(sbas.n_nearest), redundant=bool(network.sbas.redundant_pairs),
                         redundant_max_days=int(network.sbas.redundant_max_days))


def reference_mask(geo: dict, mean_coh: np.ndarray, ref: tuple[float, float] | None) -> np.ndarray:
    """The pixels whose phase is set to zero: 3 × 3 around ``ref`` (lon, lat), else the most coherent 10 %."""
    if ref is not None:
        d = np.hypot(geo["geometry_lon"] - ref[0], (geo["geometry_lat"] - ref[1]))
        r, c = np.unravel_index(np.nanargmin(d), d.shape)
        m = np.zeros(d.shape, bool)
        m[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2] = True
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
    wl = float(attrs["wavelength_m"])
    bperp = ds["bperp"].values.astype(float) if "bperp" in ds else np.zeros(len(dates))
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
        ifg, coh = pr.interferogram(store, slc_var, i, j, la, lr, int(sbas.coherence_window))
        unw[k] = pr.unwrap(ifg, coh, sbas.min_pair_coherence, sbas.goldstein_alpha, int(sbas.goldstein_fft),
                           int(sbas.irls_iter), bool(sbas.link_islands)).ravel()
        coh_sum += coh.ravel()
        if (k + 1) % 10 == 0 or k + 1 == len(net.pairs):
            say(f"  pairs unwrapped {k + 1}/{len(net.pairs)}")
    mean_coh = (coh_sum / len(net.pairs)).reshape(shape)
    ref = reference_mask(geo, mean_coh, sbas.reference).ravel()
    tropo = None
    if sbas.troposphere and "geometry_hgt" in geo:
        use = mean_coh.ravel() >= np.nanpercentile(mean_coh, 70)
        unw, tropo = iv.remove_stratified(unw, geo["geometry_hgt"].ravel(), use)
        say(f"sbas: stratified troposphere removed (median {np.nanmedian(np.abs(tropo)) * 1000:.2f} rad/km)")
    with np.errstate(invalid="ignore"):
        unw -= np.nanmedian(np.where(ref, unw, np.nan), axis=1, keepdims=True)
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
    vel, model = iv.invert(unw[:, cand], used.design(), min_pairs=max(1, len(dates) - 1))
    days = used.days()
    series = iv.displacement(vel, days)                          # phase, dates × candidates
    tcoh = iv.temporal_coherence(unw[:, cand], model)
    ok = np.isfinite(series).all(0) & (tcoh >= sbas.min_temporal_coherence)
    px = cand[ok]
    disp_mm = (-series[:, ok] * wl / (4 * np.pi) * 1000).T       # points × dates, + toward the satellite
    v_day, _ = iv.linear_velocity(disp_mm.T, days)
    rmse = np.sqrt(np.mean((disp_mm - (v_day[:, None] * (days - days.mean()) + disp_mm.mean(1, keepdims=True)))
                           ** 2, axis=1)) if len(px) else np.zeros(0)
    lat, lon = geo["geometry_lat"].ravel()[px], geo["geometry_lon"].ravel()[px]
    hgt = geo.get("geometry_hgt", np.zeros(shape)).ravel()[px]
    inc = geo.get("geometry_incidence", np.full(shape, np.nan)).ravel()[px]
    line, sample = np.divmod(px, shape[1])
    uid = np.char.add(np.char.add(f"{track_id or 'track'}:", geohash(lat, lon)),
                      np.char.add(":", np.round(hgt).astype(int).astype(str)))
    _, first = np.unique(uid, return_index=True)
    sel = np.sort(first)
    v = (v_day * DAYS_PER_YEAR)[sel]
    gdf = gpd.GeoDataFrame({
        "point_uid": uid[sel], "lon": lon[sel], "lat": lat[sel], "line": (line[sel] * la + la // 2),
        "sample": (sample[sel] * lr + lr // 2), "height_m": hgt[sel],
        "dem_err_m": np.full(len(sel), np.nan, np.float32),
        "type": np.full(len(sel), "SBAS"), "vel_los_mm_yr": v.astype(np.float32),
        "vel_linear_mm_yr": v.astype(np.float32), "temporal_coherence": tcoh[ok][sel].astype(np.float32),
        "amp_dispersion": np.full(len(sel), np.nan, np.float32), "fit_rmse_mm": rmse[sel].astype(np.float32),
        "incidence_deg": inc[sel].astype(np.float32), "mean_coherence": mean_coh.ravel()[px][sel].astype(np.float32)},
        geometry=gpd.points_from_xy(lon[sel], lat[sel]), crs="EPSG:4326")
    write_points(out / "points.parquet", gdf, metadata={"engine": ENGINE, "reference_date": dates[0].isoformat(),
                                                         "sign_convention": "-phase·λ/4π, + toward the satellite"})
    write_timeseries(out / "timeseries.parquet", uid[sel], np.array(dates, "datetime64[D]"), disp_mm[sel])
    netinfo = {**net.summary(), "pairs_used": [[str(dates[i]), str(dates[j])] for i, j in keep_pairs],
               "dropped_by_closure": [[str(dates[net.pairs[k][0]]), str(dates[net.pairs[k][1]])] for k in drop],
               "closure_masked_values": masked,
               "troposphere_rad_per_m": None if tropo is None else np.round(tropo, 6).tolist(),
               "closure_share_bad": clos["share_bad"]}
    atomic_write_json(out / "network.json", netinfo)
    summary = {"engine": ENGINE, "reference_date": dates[0].isoformat(), "epochs": len(dates),
               "sbas": {"pairs": len(net.pairs), "pairs_used": len(keep_pairs), "grid": list(shape),
                        "candidates": int(cand.size), "points": int(sel.size)},
               "aps": "none",
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
