"""Ground-motion hazard zoning of a point product with rainfall (docs/en/research/rainfall-insar-hazard.md §4).

Steps (each documented in the research note):

1. cells: the points are reduced to square cells (median series, median line of sight; at least ``min_points``);
2. terrain: slope and downslope direction from the DEM smoothed to the cell size; ``landslide`` cells are the ones
   steeper than ``landslide_min_slope_deg``, the others are ``subsidence`` cells;
3. motion: the LOS series is projected on the expected motion: vertical (subsidence) or the steepest descent
   (landslide; cells whose line of sight sees less than ``min_sensitivity`` of it are not assessed); linear (and
   quadratic) fit -> rate, its error, acceleration. The classes work on the motion in the hazard direction
   (sinking / downslope > 0); the outputs keep the GeoEyes sign: negative = sinking or downslope, positive =
   uplift or upslope (``SIGNED``; ``hazard.json`` "sign");
4. rainfall: CHIRPS monthly per pixel over the period (plus the lag window), annual totals over the climate
   normal; rainfall coupling d = a + b·t + k·CRD(t − τ) with a surrogate test (``coupling``);
5. intensity class from the observed rate, raised to the rate of a dry (P10) or wet (P90) year where the
   coupling is significant, and by one class where the motion accelerates significantly;
6. secondary class: angular distortion over the horizon (subsidence) or susceptibility / slope (landslide);
7. hazard level = matrix[intensity][secondary].

Outputs in ``<project>/analyses/hazard/<product_id>/``: ``cells.parquet`` (one row per cell), ``cells_ts.npy``
(series along the motion, negative = sinking / downslope), ``rain.npz``, ``hazard.json`` (parameters, summary,
sources), ``hazard.gpkg`` (cell squares for QGIS) and ``manifest.json``.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geoeyes.ancillary import rainfall
from geoeyes.core.errors import ConfigError, DataError
from geoeyes.core.hashing import sha256_file
from geoeyes.hazard import coupling, terrain, zoning
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.io.points import timeseries_arrays

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.hazard/2"
SIGN = "negative = sinking / downslope"
# columns written with the GeoEyes sign (computed in the hazard direction, sinking / downslope > 0)
SIGNED = ("rate_mm_yr", "acc_mm_yr2", "rain_r", "rain_k_mm_per_100mm", "trend_rain_corrected_mm_yr",
          "rate_dry_year_mm_yr", "rate_wet_year_mm_yr", "gw_r", "gw_k_mm_per_100mm")
M_PER_DEG_LAT = terrain.M_PER_DEG_LAT
M_PER_DEG_LON = terrain.M_PER_DEG_LON


@dataclass(frozen=True)
class HazardParams:
    """``[postprocess.hazard]`` of project.toml (every key optional). Defaults and their sources: research note §5."""

    cell_m: float = 100.0                       # analysis cell (m)
    min_points: int = 3                         # points needed in a cell
    horizon_yr: float = 10.0                    # angular distortion accumulated over this horizon
    max_lag_months: int = 6                     # rainfall lag searched 0..max
    n_surrogates: int = 500                     # rainfall surrogates of the significance test
    alpha: float = 0.05                         # significance of the rainfall coupling ...
    fdr: bool = True                            # ... as a false discovery rate over the cells (Benjamini–Hochberg)
    min_span_months: float = 12.0               # coupling needs at least one seasonal cycle ...
    min_epochs: int = 12                        # ... and this many acquisitions
    landslide_min_slope_deg: float = 10.0       # steeper cells: landslide mode (ADAtools: landslide >= 5°,
                                                # subsidence <= 10°; the upper bound keeps urban DSM edges out)
    min_sensitivity: float = 0.3                # |downslope · LOS| below: landslide motion not measurable
    stable_floor_mm_yr: float = 2.0             # stability threshold: max(floor, stable_sigma × σ_rate)
    stable_sigma: float = 2.0                   # (Barra et al. 2017: 2σ; Cigna et al. 2013: ±2 mm/yr band)
    subsidence_breaks: tuple[float, float] = (10.0, 30.0)      # mm/yr vertical: upper bounds of I1, I2 (local
                                                               # choice: 30 mm/yr = 0.3 m over the horizon)
    landslide_breaks: tuple[float, float] = (16.0, 160.0)      # mm/yr downslope: Cruden & Varnes extremely slow
                                                               # < 16; very slow split at 160 (log midpoint)
    distortion_breaks: tuple[float, float, float] = (1 / 500, 1 / 300, 1 / 150)    # S1, S2, S3 from: Bjerrum
                                                # safe limit, Skempton & MacDonald cracking, structural damage
    slope_breaks: tuple[float, float, float] = (15.0, 25.0, 35.0)                  # degrees: S1, S2, S3 from
                                                # (a proxy until a susceptibility map is given)
    rain_source: str = "auto"                   # auto (CHIRPS, ERA5 if CHIRPS cannot be read) | chirps | era5
    groundwater: str = "auto"                   # GLDAS groundwater coupling: auto (when EARTHDATA_TOKEN is set) |
                                                # gldas (required) | off
    accel_t: float = 3.0                        # |acceleration / its error| for a significant acceleration
    accel_min_span_months: float = 18.0
    climate_years: tuple[int, int] = (1991, 2020)               # WMO climate normal for the P10 / P90 years
    reference_bbox: tuple[float, ...] = ()      # [w, s, e, n] of stable ground: series re-referenced to it
    gnss_tie: bool = False                      # apply the GNSS calibration of the product (geoeyes gnss)
    dem: str = ""                               # "" = [stack].dem of the project
    susceptibility: str = ""                    # optional raster of classes 0..3 (replaces the slope classes)
    matrix: tuple[tuple[int, ...], ...] = zoning.DEFAULT_MATRIX

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> HazardParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.hazard]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for f in fields(cls):
            if f.name not in d:
                continue
            v = d[f.name]
            default = getattr(cls, f.name)
            out[f.name] = (tuple(tuple(r) for r in v) if f.name == "matrix" else tuple(v)) \
                if isinstance(default, tuple) else type(default)(v)
        p = cls(**out)
        if not 5 <= p.cell_m <= 5000:
            raise ConfigError("[postprocess.hazard] cell_m: 5 to 5000 m")
        if len(p.matrix) != 4 or any(len(r) != 4 or not all(0 <= x <= 4 for x in r) for r in p.matrix):
            raise ConfigError("[postprocess.hazard] matrix: 4 rows of 4 levels (0..4)")
        if len(p.reference_bbox) not in (0, 4):
            raise ConfigError("[postprocess.hazard] reference_bbox: [west, south, east, north]")
        if p.groundwater not in ("auto", "gldas", "off"):
            raise ConfigError(f"[postprocess.hazard] groundwater: auto | gldas | off, not {p.groundwater!r}")
        return p


@dataclass
class Cells:
    kx: np.ndarray
    ky: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    n: np.ndarray
    los: np.ndarray              # (cells, 3) e, n, u
    series: np.ndarray           # (cells, T) median LOS series, mm
    extra: dict[str, np.ndarray] = field(default_factory=dict)


def _months_before(d: np.datetime64, k: int) -> date:
    m = np.datetime64(d, "M") - k
    return date.fromisoformat(f"{m}-01")


def load_cells(product: Path, cell_m: float, min_points: int) -> tuple[np.ndarray, Cells]:
    """(dates, cells) of a product: points grouped in square cells of ``cell_m`` (local metric grid)."""
    names = set(pq.read_schema(product / "points.parquet").names)
    for c in ("los_e", "los_n", "los_u"):
        if c not in names:
            raise DataError(f"{product.name}: no {c} column (line of sight needed to project the motion)")
    cols = ["point_uid", "lon", "lat", "los_e", "los_n", "los_u", "temporal_coherence"]
    pts = pq.read_table(product / "points.parquet", columns=[c for c in cols if c in names])
    lon = pts["lon"].to_numpy().astype(np.float64)
    lat = pts["lat"].to_numpy().astype(np.float64)
    dates, series = timeseries_arrays(product / "timeseries.parquet", pts["point_uid"].to_numpy(zero_copy_only=False))
    lat0 = float(np.median(lat))
    kx = np.floor(lon * M_PER_DEG_LON * math.cos(math.radians(lat0)) / cell_m).astype(np.int64)
    ky = np.floor(lat * M_PER_DEG_LAT / cell_m).astype(np.int64)
    keys, inv, counts = np.unique(np.column_stack([kx, ky]), axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    keep = counts >= min_points
    if not keep.any():
        raise DataError(f"{product.name}: no cell of {cell_m:g} m holds {min_points} points")
    df = pd.DataFrame(series["disp_mm"])
    med = df.groupby(inv).median().to_numpy(np.float64)
    los = pd.DataFrame({c: pts[c].to_numpy().astype(np.float64) for c in ("los_e", "los_n", "los_u")}) \
        .groupby(inv).median().to_numpy()
    los /= np.linalg.norm(los, axis=1, keepdims=True)
    coh = pd.Series(pts["temporal_coherence"].to_numpy().astype(np.float64)).groupby(inv).median().to_numpy() \
        if "temporal_coherence" in names else np.full(len(keys), np.nan)
    kx_c, ky_c = keys[:, 0], keys[:, 1]
    lon_c = (kx_c + 0.5) * cell_m / (M_PER_DEG_LON * math.cos(math.radians(lat0)))
    lat_c = (ky_c + 0.5) * cell_m / M_PER_DEG_LAT
    return dates, Cells(kx_c[keep], ky_c[keep], lon_c[keep], lat_c[keep], counts[keep], los[keep], med[keep],
                        {"coherence": coh[keep], "lat0": np.array([lat0])})


def assess(product: Path, out: Path, params: HazardParams, *, rain_cache: Path, dem_cache: Path,
           dem_source: str = "", gw_cache: Path | None = None, earthdata_token: str = "", progress=None) -> dict:
    """Hazard zoning of ``product`` into ``out``; returns the summary written to ``hazard.json``."""
    say = progress or (lambda msg: log.info("%s", msg))
    p = params
    warnings: list[str] = []
    say(f"cells of {p.cell_m:g} m")
    dates, cells = load_cells(product, p.cell_m, p.min_points)
    nc, nt = cells.series.shape
    t_obs = (dates - dates[0]).astype(np.float64)
    span_months = float(t_obs[-1] / coupling.DAYS_PER_MONTH) if nt else 0.0
    say(f"{nc} cells, {nt} epochs over {span_months:.1f} months")

    # ---------------------------------------------------------------- reference
    # intensities need rates relative to stable ground: the product's reference, or the cells of reference_bbox
    reference = _product_reference(product)
    if p.gnss_tie:
        from geoeyes.validation.gnss import correction, read_comparison
        comp = read_comparison(product.parent.parent / "analyses" / "gnss" / product.name)
        calib = (comp or {}).get("calibration")
        if not calib:
            raise ConfigError("[postprocess.hazard] gnss_tie: no GNSS calibration of this product "
                              "(run geoeyes gnss first; it needs an NGL station inside the product)")
        cells.series = cells.series + correction(calib, dates, cells.lon, cells.lat)
        reference = {"kind": "gnss", "stations": calib["stations"], "calibration": calib["kind"],
                     "los_mode": calib["los_mode"], "rate_offset_mm_yr": calib["rate_offset_mm_yr"],
                     "loo_rms_after_mm_yr": calib.get("loo_rms_after_mm_yr")}
        say(f"series tied to GNSS {calib['stations']} ({calib['kind']}, {calib['rate_offset_mm_yr']:+.1f} mm/yr)")
        if len(calib["stations"]) == 1:
            warnings.append(f"GNSS tie on one station ({calib['stations'][0]}): not checked independently")
        if p.reference_bbox:
            warnings.append("reference_bbox ignored: gnss_tie is set")
    elif p.reference_bbox:
        w, s, e, n = p.reference_bbox
        inside = (cells.lon >= w) & (cells.lon <= e) & (cells.lat >= s) & (cells.lat <= n)
        if not inside.any():
            raise ConfigError(f"[postprocess.hazard] reference_bbox {list(p.reference_bbox)}: no cell inside")
        cells.series = cells.series - np.nanmedian(cells.series[inside], axis=0)[None, :]
        reference = {"kind": "reference_bbox", "bbox": list(p.reference_bbox), "cells": int(inside.sum())}
        say(f"series re-referenced to the median of {int(inside.sum())} cells in {list(p.reference_bbox)}")
    elif reference.get("kind") == "scene mean":
        warnings.append("the product is referenced to the scene mean: rates are relative, not to stable ground, so "
                        "the intensity classes are biased (set gnss_tie or reference_bbox); the angular "
                        "distortion does not depend on the reference")

    # ---------------------------------------------------------------- terrain
    slope = np.full(nc, np.nan, np.float32)
    down = np.zeros((nc, 3))
    dem_name = p.dem or dem_source or "srtm-1"
    try:
        say(f"terrain from the DEM ({dem_name})")
        dem = terrain.load_terrain_dem(dem_name, [cells.lon.min(), cells.lat.min(), cells.lon.max(),
                                                   cells.lat.max()], dem_cache, p.cell_m)
        ter = terrain.slope_aspect(dem, cells.lon, cells.lat, p.cell_m)
        slope = ter["slope_deg"]
        down = np.column_stack([ter["down_e"], ter["down_n"], ter["down_u"]]).astype(np.float64)
    except Exception as exc:                                      # no DEM: subsidence mode everywhere
        warnings.append(f"no terrain ({exc}); every cell treated as subsidence")
        log.warning("hazard: no terrain: %s", exc)
    landslide = np.nan_to_num(slope, nan=0.0) >= p.landslide_min_slope_deg
    mode = landslide.astype(np.int8)                              # 0 subsidence, 1 landslide

    # ---------------------------------------------------------------- motion in the hazard direction
    sens = np.where(landslide, np.einsum("ij,ij->i", down, cells.los), cells.los[:, 2])
    measurable = np.abs(sens) >= np.where(landslide, p.min_sensitivity, 0.1)
    sign = np.where(landslide, 1.0, -1.0)                         # subsidence: sinking > 0; landslide: downslope > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.where(measurable[:, None], sign[:, None] * cells.series / sens[:, None], np.nan)
    fit = coupling.linear_fit(y, t_obs, quadratic=nt >= 6)
    rate, rate_se = fit["vel"], fit["vel_se"]
    stable = np.maximum(p.stable_floor_mm_yr, p.stable_sigma * np.nan_to_num(rate_se, nan=0.0))

    # ---------------------------------------------------------------- rainfall
    rain_m, rain_y = _rain(p, [cells.lon.min(), cells.lat.min(), cells.lon.max(), cells.lat.max()],
                           _months_before(dates[0], p.max_lag_months), date.fromisoformat(str(dates[-1])),
                           rain_cache, say, warnings)
    pr, pc = rain_m.pixel(cells.lon, cells.lat)
    t0 = np.datetime64(f"{rain_m.periods[0]}-01")
    bounds = coupling.month_bounds(rain_m.periods, t0)
    t_rain = (dates - t0).astype(np.float64)

    lag = np.full(nc, -1, np.int8)
    r = np.full(nc, np.nan)
    k = np.full(nc, np.nan)
    k_se = np.full(nc, np.nan)
    trend = np.full(nc, np.nan)
    pval = np.full(nc, np.nan)
    rate_dry = np.full(nc, np.nan)
    rate_wet = np.full(nc, np.nan)
    pixels = []
    can_couple = span_months >= p.min_span_months and nt >= p.min_epochs
    if not can_couple:
        warnings.append(f"rainfall coupling not assessed: {span_months:.1f} months / {nt} epochs "
                        f"(needs {p.min_span_months:g} months and {p.min_epochs} epochs)")
    for row, col in sorted({(int(a), int(b)) for a, b in zip(pr, pc, strict=True)}):
        sel = (pr == row) & (pc == col)
        series = rain_m.mm[:, row, col]
        c = coupling.crd(series, bounds)
        annual = rain_y.mm[:, row, col]
        annual = annual[np.isfinite(annual)]
        clim = {q: float(np.percentile(annual, v)) for q, v in (("p10", 10), ("p50", 50), ("p90", 90))} \
            if annual.size >= 10 else None
        lon_p, lat_p = rain_m.centre(row, col)
        info = {"row": row, "col": col, "lon": round(lon_p, 3), "lat": round(lat_p, 3), "cells": int(sel.sum()),
                "mean_month_mm": round(c.mean_month_mm, 1), "missing": round(c.missing, 3),
                "annual": {kk: round(v, 0) for kk, v in clim.items()} if clim else None, "assessed": False}
        pixels.append(info)
        if not can_couple or c.missing > 0.2:
            continue
        anomaly = np.where(np.isfinite(series), series - c.mean_month_mm, 0.0)
        res = coupling.couple(y[sel], t_rain, c, anomaly, p.max_lag_months, p.n_surrogates, seed=row * 1000 + col)
        lag[sel], r[sel], k[sel], k_se[sel], trend[sel], pval[sel] = (res.lag_months, res.r, res.k, res.k_se,
                                                                        res.trend, res.p)
        info["assessed"] = True
        if clim:
            normal = 12 * c.mean_month_mm                         # the departure the model was fitted against
            rate_dry[sel] = res.trend + res.k * (clim["p10"] - normal)
            rate_wet[sel] = res.trend + res.k * (clim["p90"] - normal)
    partial = [px["missing"] for px in pixels if px["assessed"] and px["missing"] > 0]
    if partial:                                                   # one message for every pixel (the details: pixels)
        warnings.append(f"{len(partial)} rainfall pixel(s): up to {max(partial):.0%} of the months not published yet "
                        "(counted as average)")
    # thousands of cells are tested: the false discovery rate is controlled over the map (field significance)
    qval = coupling.fdr_bh(pval) if p.fdr else pval
    coupled = (qval <= p.alpha) & np.isfinite(k)
    say(f"rainfall coupling significant in {int(coupled.sum())} of {int(np.isfinite(pval).sum())} assessed cells")

    # ---------------------------------------------------------------- groundwater (diagnostic, not in the level)
    gw = _groundwater(p, y, dates, cells, can_couple, gw_cache, earthdata_token, say, warnings)

    # ---------------------------------------------------------------- intensity
    # rates in the hazard direction (sinking / downslope > 0); the worse of a dry and a wet year where coupled
    scenario = np.where(coupled, np.fmax(rate_dry, rate_wet), np.nan)
    rate_eff = np.where(coupled, np.fmax(rate, scenario), rate)
    opposite = rate < -stable                                     # uplift / apparent upslope motion: flagged
    i_obs = np.where(landslide, zoning.intensity_class(rate, stable, p.landslide_breaks),
                     zoning.intensity_class(rate, stable, p.subsidence_breaks))
    i_eff = np.where(landslide, zoning.intensity_class(rate_eff, stable, p.landslide_breaks),
                     zoning.intensity_class(rate_eff, stable, p.subsidence_breaks)).astype(np.int8)
    accel = np.zeros(nc, bool)
    if span_months >= p.accel_min_span_months:
        with np.errstate(divide="ignore", invalid="ignore"):
            tstat = fit["acc"] / fit["acc_se"]
        accel = (np.nan_to_num(tstat, nan=0.0) >= p.accel_t) & (rate > 0)       # speeding up in the hazard direction
    i_eff = np.where(accel & (i_eff >= 0), np.minimum(i_eff + 1, 3), i_eff).astype(np.int8)
    i_eff[~measurable] = -1
    i_obs[~measurable] = -1

    # ---------------------------------------------------------------- secondary class
    beta = zoning.angular_distortion(cells.kx, cells.ky, np.where(landslide, np.nan, rate), p.cell_m, p.horizon_yr)
    s_sub = zoning.classify(beta, p.distortion_breaks)
    susc = np.full(nc, np.nan, np.float32)
    if p.susceptibility:
        try:
            susc = terrain.sample_classes(Path(p.susceptibility), cells.lon, cells.lat)
        except Exception as exc:
            warnings.append(f"susceptibility raster not read ({exc}); slope classes used")
    s_land = np.where(np.isfinite(susc), np.nan_to_num(susc, nan=0).astype(np.int8),
                      zoning.classify(slope, p.slope_breaks))
    secondary = np.where(landslide, s_land, s_sub).astype(np.int8)
    level = zoning.hazard_level(i_eff, secondary, p.matrix)

    # ---------------------------------------------------------------- outputs
    out.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame({
        "cell": np.arange(nc, dtype=np.int32), "lon": cells.lon, "lat": cells.lat, "n_points": cells.n.astype(np.int32),
        "mode": np.array(zoning.MODES)[mode], "slope_deg": slope, "sensitivity": sens.astype(np.float32),
        "coherence": cells.extra["coherence"].astype(np.float32),
        "rate_mm_yr": rate.astype(np.float32), "rate_se_mm_yr": rate_se.astype(np.float32),
        "stable_mm_yr": stable.astype(np.float32),
        "acc_mm_yr2": fit["acc"].astype(np.float32), "accelerating": accel, "opposite_motion": opposite,
        "rain_lag_months": lag, "rain_r": r.astype(np.float32), "rain_p": pval.astype(np.float32),
        "rain_q": qval.astype(np.float32),
        "rain_k_mm_per_100mm": (100 * k).astype(np.float32), "rain_k_se": (100 * k_se).astype(np.float32),
        "rain_coupled": coupled, "trend_rain_corrected_mm_yr": trend.astype(np.float32),
        "rate_dry_year_mm_yr": rate_dry.astype(np.float32), "rate_wet_year_mm_yr": rate_wet.astype(np.float32),
        "intensity_observed": i_obs.astype(np.int8), "intensity": i_eff,
        "angular_distortion": beta.astype(np.float32), "susceptibility": susc, "secondary": secondary,
        "hazard": level, "rain_row": pr.astype(np.int16), "rain_col": pc.astype(np.int16),
        **gw["columns"],
    })
    for c in SIGNED:                                              # back to the GeoEyes sign
        table[c] = -table[c]
    table.to_parquet(out / "cells.parquet", index=False)
    np.save(out / "cells_ts.npy", np.where(np.isfinite(y), -y, np.nan).astype(np.float32))
    np.savez(out / "rain.npz", months=np.array(rain_m.periods), monthly=rain_m.mm, years=np.array(rain_y.periods),
             annual=rain_y.mm, west=rain_m.west, north=rain_m.north, res=rain_m.res)
    outputs = ["cells.parquet", "cells_ts.npy", "rain.npz", "hazard.json", "hazard.gpkg"]
    if gw["grid"] is not None:
        g = gw["grid"]
        np.savez(out / "groundwater.npz", months=np.array(g.periods), monthly=g.mm, west=g.west, north=g.north,
                 res=g.res)
        outputs.append("groundwater.npz")
    else:
        (out / "groundwater.npz").unlink(missing_ok=True)
    _write_gpkg(out / "hazard.gpkg", table, p.cell_m, float(cells.extra["lat0"][0]))

    area_km2 = (p.cell_m / 1000) ** 2
    summary = {
        "schema": SCHEMA, "sign": SIGN, "product_id": product.name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": {kk: (list(map(list, v)) if kk == "matrix" else list(v) if isinstance(v, tuple) else v)
                   for kk, v in asdict(p).items()},
        "dates": [str(d) for d in dates], "span_months": round(span_months, 1), "n_cells": nc,
        "n_points": int(cells.n.sum()), "lat0": float(cells.extra["lat0"][0]),
        "bounds": [float(cells.lon.min()), float(cells.lat.min()), float(cells.lon.max()), float(cells.lat.max())],
        "dem": dem_name, "levels": list(zoning.LEVELS),
        "by_level": {m: {zoning.LEVELS[lv]: {"cells": int(((mode == mi) & (level == lv)).sum()),
                                             "km2": round(float(((mode == mi) & (level == lv)).sum()) * area_km2, 3)}
                         for lv in range(5)} | {"not assessed": int(((mode == mi) & (level < 0)).sum())}
                     for mi, m in enumerate(zoning.MODES)},
        "coupling": {"assessed": bool(can_couple), "cells_tested": int(np.isfinite(pval).sum()),
                     "cells_significant": int(coupled.sum()),
                     "cells_p_below_alpha": int((pval <= p.alpha).sum()), "fdr": p.fdr,
                     "lag_months_median": None if not coupled.any() else float(np.median(lag[coupled])),
                     # more rain, more sinking / downslope motion (k < 0 with the GeoEyes sign)
                     "share_negative_k": None if not coupled.any() else round(float((k[coupled] > 0).mean()), 3)},
        "accelerating_cells": int(accel.sum()), "opposite_motion_cells": int(opposite.sum()),
        "reference": reference,
        "rain": {"source": rain_m.source, "res_deg": rain_m.res, "months": rain_m.periods,
                 "climate_years": list(p.climate_years), "pixels": pixels},
        "groundwater": gw["summary"],
        "warnings": warnings,
        "method": "docs/en/research/rainfall-insar-hazard.md",
    }
    atomic_write_json(out / "hazard.json", summary)
    m = Manifest(kind="hazard", id=product.name, engine=SCHEMA,
                 inputs=[InputRef("product", str(product), _sha(product / "manifest.json"))],
                 params=summary["params"], metrics={"n_cells": nc, "cells_significant": int(coupled.sum())})
    m.add_outputs(out, outputs)
    m.write(out)
    say("done")
    return summary


def _groundwater(p: HazardParams, y: np.ndarray, dates: np.ndarray, cells: Cells, can_couple: bool,
                 cache: Path | None, token: str, say, warnings: list[str]) -> dict:
    """Coupling of the series in the hazard direction with GLDAS groundwater storage
    (docs/en/research/groundwater-insar.md):
    d = a + b·t + g·GWS(t − τ), tested like the rainfall. A diagnostic: it does not change the hazard level (the
    0.25° storage is regional; the pumping that drives subsidence is local)."""
    nc = y.shape[0]
    cols = {"gw_lag_months": np.full(nc, -1, np.int8), "gw_r": np.full(nc, np.nan, np.float32),
            "gw_p": np.full(nc, np.nan, np.float32), "gw_q": np.full(nc, np.nan, np.float32),
            "gw_k_mm_per_100mm": np.full(nc, np.nan, np.float32), "gw_k_se": np.full(nc, np.nan, np.float32),
            "gw_coupled": np.zeros(nc, bool), "gw_row": np.full(nc, -1, np.int16),
            "gw_col": np.full(nc, -1, np.int16)}
    none = {"columns": cols, "grid": None}
    if p.groundwater == "off":
        return none | {"summary": {"used": False, "reason": "off"}}
    if not token or cache is None:
        if p.groundwater == "gldas":
            raise ConfigError("[postprocess.hazard] groundwater = gldas needs EARTHDATA_TOKEN")
        return none | {"summary": {"used": False, "reason": "no EARTHDATA_TOKEN"}}
    from geoeyes.ancillary import groundwater
    try:
        say("groundwater: GLDAS storage (NASA Harmony; the first run takes a few minutes)")
        g = groundwater.monthly_grid(cache, [cells.lon.min(), cells.lat.min(), cells.lon.max(), cells.lat.max()],
                                     _months_before(dates[0], p.max_lag_months), date.fromisoformat(str(dates[-1])),
                                     token, progress=say)
    except Exception as exc:
        if p.groundwater == "gldas":
            raise
        warnings.append(f"groundwater not read ({exc})")
        log.warning("hazard: groundwater: %s", exc)
        return none | {"summary": {"used": False, "reason": str(exc)}}
    gr, gc = g.pixel(cells.lon, cells.lat)
    cols["gw_row"], cols["gw_col"] = gr.astype(np.int16), gc.astype(np.int16)
    t0 = np.datetime64(f"{g.periods[0]}-01")
    t_obs = (dates - t0).astype(np.float64)
    end = str(np.datetime64(str(dates[-1]), "M"))
    span = [i for i, m in enumerate(g.periods) if m <= end]
    pval = np.full(nc, np.nan)
    pixels = []
    for row, col in sorted({(int(a), int(b)) for a, b in zip(gr, gc, strict=True)}):
        sel = (gr == row) & (gc == col)
        series = g.mm[span, row, col]
        s, changes = coupling.storage(series, [g.periods[i] for i in span], t0)
        ok = np.isfinite(series)
        trend = float(np.polyfit(s.t_days / coupling.DAYS_PER_YEAR, s.values, 1)[0]) if ok.sum() >= 12 else None
        lon_p, lat_p = g.centre(row, col)
        info = {"row": row, "col": col, "lon": round(lon_p, 3), "lat": round(lat_p, 3), "cells": int(sel.sum()),
                "mean_mm": round(s.mean_month_mm, 0), "missing": round(s.missing, 3),
                "trend_mm_yr": None if trend is None else round(trend, 1), "assessed": False}
        pixels.append(info)
        if not can_couple or s.missing > 0.2 or not ok.any():
            continue
        # storage is published months late: the test uses the observations it covers (never storage held flat)
        within = t_obs <= s.t_days[-1] + 15
        span_in = (t_obs[within][-1] - t_obs[0]) / coupling.DAYS_PER_MONTH if within.any() else 0.0
        if span_in < p.min_span_months or within.sum() < p.min_epochs:
            continue
        info["until"] = str(dates[within][-1])
        res = coupling.couple(y[sel][:, within], t_obs[within], s, changes, p.max_lag_months, p.n_surrogates,
                              seed=row * 1000 + col + 7)
        cols["gw_lag_months"][sel] = res.lag_months
        cols["gw_r"][sel], cols["gw_k_mm_per_100mm"][sel] = res.r, 100 * res.k
        cols["gw_k_se"][sel], pval[sel] = 100 * res.k_se, res.p
        info["assessed"] = True
    qval = coupling.fdr_bh(pval) if p.fdr else pval
    coupled = (qval <= p.alpha) & np.isfinite(cols["gw_k_mm_per_100mm"])
    cols["gw_p"], cols["gw_q"], cols["gw_coupled"] = pval.astype(np.float32), qval.astype(np.float32), coupled
    if not any(px["assessed"] for px in pixels):
        warnings.append("groundwater coupling not assessed: GLDAS storage does not cover the observations yet "
                        "(published with a lag of a few months) or the series are too short")
    elif any(px.get("until", str(dates[-1])) < str(dates[-1]) for px in pixels if px["assessed"]):
        until = min(px["until"] for px in pixels if px["assessed"])
        warnings.append(f"groundwater coupling tested on the observations up to {until} (GLDAS is published "
                        "with a lag)")
    k = cols["gw_k_mm_per_100mm"]
    say(f"groundwater coupling significant in {int(coupled.sum())} of {int(np.isfinite(pval).sum())} assessed cells")
    trends = [px["trend_mm_yr"] for px in pixels if px["trend_mm_yr"] is not None]
    summary = {"used": True, "source": g.source, "res_deg": g.res, "months": g.periods,
               "cells_tested": int(np.isfinite(pval).sum()), "cells_significant": int(coupled.sum()),
               "lag_months_median": None if not coupled.any() else float(np.median(cols["gw_lag_months"][coupled])),
               # ground that rises and falls with the storage (elastic aquifer): g > 0 with the GeoEyes sign,
               # g < 0 in the hazard direction used here
               "share_positive_g": None if not coupled.any() else round(float((k[coupled] < 0).mean()), 3),
               "trend_mm_yr": None if not trends else round(float(np.mean(trends)), 1), "pixels": pixels}
    return {"columns": cols, "grid": g, "summary": summary}


def _product_reference(product: Path) -> dict:
    """The reference of the product's velocities, from its manifest: ``{"kind": "point" | "scene mean" |
    "unknown"}``."""
    f = product / "manifest.json"
    ref = (json.loads(f.read_text(encoding="utf-8")).get("metrics") or {}).get("reference") if f.exists() else None
    if isinstance(ref, dict):
        return {"kind": "point", **{k: ref[k] for k in ("lon", "lat", "n_ps") if k in ref}}
    if isinstance(ref, str):
        return {"kind": ref}
    return {"kind": "unknown"}


def _rain(p: HazardParams, bbox: list[float], first: date, last: date, cache: Path, say, warnings: list[str]):
    """(monthly, annual) rainfall grids: CHIRPS, or ERA5 when asked or when CHIRPS cannot be read (``auto``)."""
    if p.rain_source not in ("auto", "chirps", "era5"):
        raise ConfigError(f"[postprocess.hazard] rain_source: auto | chirps | era5, not {p.rain_source!r}")
    if p.rain_source != "era5":
        say("rainfall: CHIRPS monthly per pixel")
        rain_m = rainfall.monthly_grid(cache, bbox, first, last)
        say(f"rainfall: CHIRPS annual totals {p.climate_years[0]}-{p.climate_years[1]}")
        rain_y = rainfall.annual_grid(cache, bbox, *p.climate_years)
        refused = sorted({g.refused for g in (rain_m, rain_y) if g.refused})
        # usable: most months of the period and most climate years read
        usable = np.isfinite(rain_m.mm).any(axis=(1, 2)).mean() >= 0.8 and \
            np.isfinite(rain_y.mm).any(axis=(1, 2)).mean() >= 0.8
        if usable or p.rain_source == "chirps":
            warnings += refused
            return rain_m, rain_y
        warnings.append("CHIRPS could not be read" + (f" ({refused[0]})" if refused else "") +
                        ": ERA5 reanalysis used instead (smoother monthly extremes)")
    say("rainfall: ERA5 daily (Open-Meteo archive)")
    start = min(first, date(p.climate_years[0], 1, 1))
    end = min(last, date.today())
    m, y = rainfall.era5_grid(cache, bbox, start, end)
    keep_m = [i for i, k in enumerate(m.periods) if k >= f"{first:%Y-%m}"]
    keep_y = [i for i, k in enumerate(y.periods) if p.climate_years[0] <= int(k) <= p.climate_years[1]]
    return (rainfall.RainGrid([m.periods[i] for i in keep_m], m.mm[keep_m], m.west, m.north, m.res, source=m.source),
            rainfall.RainGrid([y.periods[i] for i in keep_y], y.mm[keep_y], y.west, y.north, y.res, source=y.source))


def _sha(path: Path) -> str:
    return sha256_file(path) if path.exists() else ""


def _write_gpkg(path: Path, table: pd.DataFrame, cell_m: float, lat0: float) -> None:
    """Cell squares (EPSG:4326) with every attribute, for QGIS."""
    import geopandas as gpd
    from shapely import box
    hx = 0.5 * cell_m / (M_PER_DEG_LON * math.cos(math.radians(lat0)))
    hy = 0.5 * cell_m / M_PER_DEG_LAT
    geom = box(table["lon"] - hx, table["lat"] - hy, table["lon"] + hx, table["lat"] + hy)
    gdf = gpd.GeoDataFrame(table.assign(hazard_level=[zoning.LEVELS[v] if v >= 0 else "not assessed"
                                                       for v in table["hazard"]]),
                           geometry=geom, crs="EPSG:4326")
    path.unlink(missing_ok=True)
    gdf.to_file(path, layer="hazard_cells", driver="GPKG")


def read_summary(folder: Path) -> dict | None:
    f = folder / "hazard.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def up_positive(summary: dict | None) -> bool:
    """Whether an analysis already has the GeoEyes sign; analyses made before (schema 1) are positive in the hazard
    direction and their ``SIGNED`` columns and series are negated when read (``read_cells``)."""
    return bool(summary and summary.get("sign") == SIGN)


def read_cells(folder: Path, summary: dict | None = None) -> pd.DataFrame:
    """``cells.parquet`` with the GeoEyes sign, whatever version wrote it."""
    cells = pd.read_parquet(folder / "cells.parquet")
    if not up_positive(summary if summary is not None else read_summary(folder)):
        for c in SIGNED:
            if c in cells:
                cells[c] = -cells[c]
    return cells
