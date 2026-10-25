"""Point product from a PS run (``ps`` or ``ps_lite``): ``products/<product_id>/``, immutable::

    points.parquet       GeoParquet, columns of ``products.schema`` (+ ``extra_*`` engine columns)
    timeseries.parquet   long format (point_uid, date, disp_mm[, disp_scn_mm: spatially correlated noise removed]),
                         zero at each point's first date (the PS run gives them relative to the stack's reference
                         date; ``zero_reference``)
    rasters/velocity.tif rasters/ps_density.tif    COG, EPSG:4326, mean LOS velocity / points per cell
    item.json            STAC 1.0 Item
    manifest.json

Every product of a track is a new version (``..._v<N>``); the time-series statistics (velocity standard error,
acceleration when the engine has none, annual amplitude / phase, residual sigma) are computed here the same way
for every engine.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.core.errors import DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.io.points import read_points, read_timeseries, write_points, write_timeseries
from geoeyes.products.schema import COLUMNS, EXTRA_PREFIX, SCHEMA

log = logging.getLogger(__name__)
ENGINE = "geoeyes-product/3"          # /2: timeseries.parquet also carries disp_scn_mm (ps engine)
                                      # /3: series zero at the first date (were zero at the stack reference date)
_EXTRA = {"vel_los_scn_mm_yr": "vel_scn_mm_yr", "vel_linear_mm_yr": "vel_linear_mm_yr",
          "spectral_diversity": "spectral_diversity", "phase_std_rad": "phase_std_rad"}


def zero_reference(disp: np.ndarray | None) -> np.ndarray | None:
    """Series (points, dates) moved so that each point is 0 at its first date with a value (time zero at the start
    of the series, as delivered displacement products are; the PS engines give them relative to the stack's
    reference date). Offsets only: velocities and every other fit are unchanged."""
    if disp is None:
        return None
    d = np.asarray(disp, np.float32)
    ok = np.isfinite(d)
    first = np.argmax(ok, axis=1)
    base = d[np.arange(d.shape[0]), first]
    base[~ok.any(axis=1)] = 0.0
    return (d - base[:, None]).astype(np.float32)


def los_vector(incidence_deg, heading_deg: float, look_side: str):
    """Unit vector from the ground to the satellite (east, north, up)."""
    inc = np.radians(np.asarray(incidence_deg, np.float64))
    look = heading_deg + (90.0 if str(look_side).lower() == "right" else -90.0)
    az = np.radians(look + 180.0)                    # ground -> satellite azimuth
    return np.sin(inc) * np.sin(az), np.sin(inc) * np.cos(az), np.cos(inc)


def timeseries_stats(disp: np.ndarray, dates: np.ndarray) -> dict[str, np.ndarray]:
    """Per point (rows of ``disp`` (n, T) mm): velocity standard error, quadratic acceleration, annual amplitude
    and day of maximum (series >= 300 days), residual std about linear (+ annual) model. NaN rows -> NaN."""
    d = np.asarray(dates, "datetime64[D]")
    y0 = np.datetime64(f"{d[0].astype(object).year}-01-01", "D")
    t = (d - y0).astype(np.float64) / 365.25
    tc = t - t.mean()
    n, T = disp.shape
    ok = np.all(np.isfinite(disp), axis=1)
    out = {k: np.full(n, np.nan, np.float32) for k in ("vel_std", "acc", "amp", "phase_day", "sigma")}
    if T < 4 or not ok.any():
        return out
    y = disp[ok].astype(np.float64).T                                   # (T, m)

    def fit(g):
        """Coefficients, residual std (dof-corrected) and the velocity (column 1) standard error."""
        m, *_ = np.linalg.lstsq(g, y, rcond=None)
        r = y - g @ m
        s = np.sqrt((r**2).sum(axis=0) / max(T - g.shape[1], 1))
        return m, s, s * np.sqrt(np.linalg.pinv(g.T @ g)[1, 1])

    _, sig, vstd = fit(np.column_stack([np.ones(T), tc]))
    if T >= 5:
        m2, *_ = fit(np.column_stack([np.ones(T), tc, tc**2]))
        out["acc"][ok] = 2.0 * m2[2]
    if (d[-1] - d[0]).astype(int) >= 300 and T >= 6:    # annual term: velocity error and residual about it
        w = 2 * np.pi * t
        m3, sig, vstd = fit(np.column_stack([np.ones(T), tc, np.sin(w), np.cos(w)]))
        s, c = m3[2], m3[3]
        out["amp"][ok] = np.hypot(s, c)
        out["phase_day"][ok] = (np.arctan2(s, c) / (2 * np.pi) % 1.0) * 365.25
    out["vel_std"][ok], out["sigma"][ok] = vstd, sig
    return out


def _cell_size_deg(lon, lat) -> tuple[float, float]:
    from scipy.spatial import cKDTree
    k = 111320.0 * np.cos(np.radians(np.nanmean(lat)))
    xy = np.column_stack([lon * k, lat * 110574.0])
    sample = xy[np.random.default_rng(0).choice(len(xy), min(20000, len(xy)), replace=False)]
    dist = cKDTree(xy).query(sample, k=2)[0][:, 1]
    cell_m = float(np.clip(3.0 * np.median(dist), 10.0, 200.0))
    return cell_m / k, cell_m / 110574.0


def _rasters(out: Path, lon, lat, v) -> list[Path]:
    from rasterio.transform import from_origin

    from geoeyes.io.raster import write_cog
    dx, dy = _cell_size_deg(lon, lat)
    west, north = float(np.min(lon)) - dx / 2, float(np.max(lat)) + dy / 2
    nx = int(np.ceil((np.max(lon) - west) / dx)) + 1
    ny = int(np.ceil((north - np.min(lat)) / dy)) + 1
    j = np.clip(((lon - west) / dx).astype(int), 0, nx - 1)
    i = np.clip(((north - lat) / dy).astype(int), 0, ny - 1)
    flat = i * nx + j
    cnt = np.bincount(flat, minlength=ny * nx).reshape(ny, nx).astype(np.float32)
    vs = np.bincount(flat, weights=np.nan_to_num(v), minlength=ny * nx).reshape(ny, nx)
    vel = np.where(cnt > 0, vs / np.maximum(cnt, 1), np.nan).astype(np.float32)
    tr = from_origin(west, north, dx, dy)
    return [write_cog(out / "velocity.tif", vel, tr, description="mean LOS velocity", units="mm/yr"),
            write_cog(out / "ps_density.tif", np.where(cnt > 0, cnt, np.nan), tr, description="points per cell",
                      units="count")]


def next_product_id(products_root: Path, prefix: str) -> str:
    n = [int(p.name.rsplit("_v", 1)[1]) for p in Path(products_root).glob(f"{prefix}_v*")
         if p.name.rsplit("_v", 1)[1].isdigit()]
    return f"{prefix}_v{max(n, default=0) + 1}"


def _load_run(ps_run: Path, track_id: str):
    """(points table in product columns without the time-series statistics, dates, displacement, manifest,
    stack attributes) of one PS run."""
    src = Manifest.read(ps_run)
    gdf = read_points(ps_run / "points.parquet")
    if gdf.empty:
        raise DataError(f"{ps_run}: no points")
    ts = read_timeseries(ps_run / "timeseries.parquet")
    wide = ts.pivot(index="point_uid", columns="date", values="disp_mm")
    dates = np.asarray(wide.columns, "datetime64[D]")
    disp = wide.reindex(gdf["point_uid"].to_numpy()).to_numpy(np.float32)
    stack_path = next((i.uri for i in src.inputs if i.kind == "stack"), "")
    attrs = {}
    if stack_path and Path(stack_path).exists():
        from geoeyes.io.stack import StackStore
        attrs = StackStore(stack_path).attrs
    heading = float(attrs.get("heading_deg", np.nan))
    inc = gdf["incidence_deg"].to_numpy(np.float64) if "incidence_deg" in gdf else np.full(len(gdf), np.nan)
    le, ln, lu = los_vector(inc, heading, str(attrs.get("look_side", "right")))

    def col(name, fallback=np.nan):
        return gdf[name].to_numpy() if name in gdf else np.full(len(gdf), fallback)

    p = pd.DataFrame({
        "point_uid": gdf["point_uid"].to_numpy(), "track_id": track_id, "stack_id": attrs.get("stack_id", ""),
        "lon": gdf["lon"].to_numpy(np.float64), "lat": gdf["lat"].to_numpy(np.float64),
        "height_m": col("height_m"), "type": col("type", "PS"), "vel_los_mm_yr": col("vel_los_mm_yr"),
        "vel_std_mm_yr": col("vel_std_mm_yr"), "acc_los_mm_yr2": col("acc_mm_yr2"),
        "temporal_coherence": col("temporal_coherence"), "amp_dispersion": col("amp_dispersion"),
        "dem_err_m": col("dem_err_m"), "fit_rmse_mm": col("fit_rmse_mm"), "los_e": le, "los_n": ln, "los_u": lu,
        "incidence_deg": inc, "heading_deg": heading})
    for k, v in _EXTRA.items():
        if k in gdf:
            p[EXTRA_PREFIX + v] = gdf[k].to_numpy(np.float32)
    return p, dates, disp, src, attrs, _scn_series(ps_run, ts, gdf, dates)


def _scn_series(ps_run: Path, ts, gdf, dates) -> np.ndarray | None:
    """Time series with the spatially correlated noise removed (``ps`` engine): from the run's time series, or,
    for runs written before it carried them, from ``state.h5`` matched on the radar position of each point."""
    uid = gdf["point_uid"].to_numpy()
    if "disp_scn_mm" in ts:
        wide = ts.pivot(index="point_uid", columns="date", values="disp_scn_mm")
        return wide.reindex(uid).to_numpy(np.float32)
    state = ps_run / "state.h5"
    if not state.exists() or "line" not in gdf or "sample" not in gdf:
        return None
    import h5py
    with h5py.File(state, "r") as f:
        if "velocity/disp_scn_mm" not in f or "ps/line" not in f:
            return None
        scn = f["velocity/disp_scn_mm"][()]
        key = f["ps/line"][()].astype(np.int64) * 1_000_000 + f["ps/sample"][()].astype(np.int64)
        epochs = [d.decode() for d in f["time/epoch_dates"][()]]
    if scn.shape[1] != len(dates) or epochs != [str(d) for d in dates]:
        return None
    row = {k: i for i, k in reversed(list(enumerate(key)))}   # first PS at a pixel, as the points kept
    want = gdf["line"].to_numpy(np.int64) * 1_000_000 + gdf["sample"].to_numpy(np.int64)
    idx = np.array([row.get(k, -1) for k in want])
    if (idx < 0).any():
        return None
    return scn[idx].astype(np.float32)


def build_product(ps_run: str | Path, products_root: str | Path, *, project: str, track_id: str,
                  run_id: str = "") -> dict:
    """Product from the PS run of a track (subswaths are merged in the stack, before point processing)."""
    ps_run, products_root = Path(ps_run), Path(products_root)
    p, dates, disp, src, attrs, disp_scn = _load_run(ps_run, track_id)
    st = timeseries_stats(disp, dates)
    p["vel_std_mm_yr"] = p["vel_std_mm_yr"].where(p["vel_std_mm_yr"].notna(), pd.Series(st["vel_std"]))
    p["acc_los_mm_yr2"] = p["acc_los_mm_yr2"].where(p["acc_los_mm_yr2"].notna(), pd.Series(st["acc"]))
    p["seasonal_amp_mm"], p["seasonal_phase_day"], p["residual_sigma_mm"] = st["amp"], st["phase_day"], st["sigma"]
    extras = [c for c in p.columns if c.startswith(EXTRA_PREFIX)]
    p = p[[*COLUMNS, *extras]].copy()
    for c, (dtype, _, _) in COLUMNS.items():
        p[c] = p[c].astype(dtype)
    import geopandas as gpd
    out_gdf = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p["lon"], p["lat"]), crs="EPSG:4326")

    d0, d1 = dates[0].astype(object), dates[-1].astype(object)
    pid = next_product_id(products_root, f"{project}_{track_id}_{d0:%Y%m%d}_{d1:%Y%m%d}")
    out = products_root / pid
    out.mkdir(parents=True)
    v = p["vel_los_mm_yr"].to_numpy(np.float64)
    metrics = {"n_points": len(p), "n_ds": int((p["type"] == "DS").sum()), "epochs": len(dates),
               "first_date": str(d0), "last_date": str(d1), "engine": src.engine,
               "vel_min_mm_yr": float(np.nanmin(v)), "vel_max_mm_yr": float(np.nanmax(v)),
               "vel_p02_mm_yr": float(np.nanpercentile(v, 2)), "vel_median_mm_yr": float(np.nanmedian(v)),
               "vel_p98_mm_yr": float(np.nanpercentile(v, 98)),
               "vel_std_median_mm_yr": float(np.nanmedian(p["vel_std_mm_yr"])),
               "coherence_median": float(np.nanmedian(p["temporal_coherence"])),
               "reference": src.metrics.get("reference", ""), "aps": src.metrics.get("aps", "")}
    write_points(out / "points.parquet", out_gdf, metadata={"schema": SCHEMA, "product_id": pid,
                                                            "sign_convention": "LOS + toward the satellite",
                                                            "reference_date": src.metrics.get("reference_date"),
                                                            "time_zero": "first date"})
    write_timeseries(out / "timeseries.parquet", p["point_uid"].to_numpy(), dates, zero_reference(disp),
                     disp_scn_mm=zero_reference(disp_scn))
    rasters = _rasters(out / "rasters", p["lon"].to_numpy(), p["lat"].to_numpy(), v)
    bbox = [float(p["lon"].min()), float(p["lat"].min()), float(p["lon"].max()), float(p["lat"].max())]
    item = {"type": "Feature", "stac_version": "1.0.0", "id": pid, "bbox": bbox,
            "geometry": {"type": "Polygon", "coordinates": [[[bbox[0], bbox[1]], [bbox[2], bbox[1]],
                                                             [bbox[2], bbox[3]], [bbox[0], bbox[3]],
                                                             [bbox[0], bbox[1]]]]},
            "properties": {"datetime": None, "start_datetime": f"{d0}T00:00:00Z", "end_datetime": f"{d1}T23:59:59Z",
                           "geoeyes:project": project, "geoeyes:track": track_id,
                           "geoeyes:sensor": attrs.get("sensor", ""), "geoeyes:engine": src.engine,
                           "geoeyes:schema": SCHEMA, **{f"geoeyes:{k}": v_ for k, v_ in metrics.items()
                                                        if isinstance(v_, (int, float, str))}},
            "assets": {"points": {"href": "./points.parquet", "type": "application/vnd.apache.parquet",
                                  "roles": ["data"], "title": "measurement points (GeoParquet)"},
                       "timeseries": {"href": "./timeseries.parquet", "type": "application/vnd.apache.parquet",
                                      "roles": ["data"], "title": "displacement time series (long format)"},
                       "velocity": {"href": "./rasters/velocity.tif",
                                    "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                                    "roles": ["data", "visual"], "title": "mean LOS velocity (mm/yr)"},
                       "ps_density": {"href": "./rasters/ps_density.tif",
                                      "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                                      "roles": ["data"], "title": "points per cell"}},
            "links": []}
    atomic_write_json(out / "item.json", item)
    m = Manifest(kind="product", id=pid, run_id=run_id, engine=ENGINE,
                 inputs=[InputRef("ps_run", str(ps_run), next((o.sha256 for o in src.outputs
                                                               if o.path == "points.parquet"), ""))],
                 metrics=metrics)
    m.add_outputs(out, ["points.parquet", "timeseries.parquet", "item.json", *(r.relative_to(out) for r in rasters)])
    m.write(out)
    log.info("product %s: %d points (%d DS), %s..%s", pid, len(p), metrics["n_ds"], d0, d1)
    return {"product_id": pid, "path": str(out), **metrics}


__all__ = ["build_product", "los_vector", "timeseries_stats"]
