"""Point products from time series made outside GeoEyes, so that the analysis modules (decompose, hazard,
behaviour, GNSS, lines) can run on them and compare them with GeoEyes products.

MintPy (``timeseries*.h5`` + ``geometryGeo.h5``, geocoded):
- ``timeseries`` (dates, rows, cols) in m, positive toward the satellite (GeoEyes sign); pixels that MintPy masked
  are all-zero series (the reference pixel is all-zero too and is kept);
- ``incidenceAngle`` and ``azimuthAngle`` in degrees; ``azimuthAngle`` is the azimuth of the ground-to-satellite
  vector, counter-clockwise from north (MintPy convention), so the LOS unit vector is
  e = −sin(inc)·sin(az), n = sin(inc)·cos(az), u = cos(inc);
- ``waterMask`` True on land.

The pixels are averaged in blocks of ``step`` × ``step`` (NaN-mean of the valid pixels, at least
``min_valid_share`` of the block valid), which keeps the product a manageable size (the Choshui stacks are
2.7k × 2k pixels × 433 dates). The product is written in the layout of ``products.builder`` (points, time series
zero at the first date, rasters, STAC item, manifest) with ``geoeyes:engine = "mintpy"`` and
``geoeyes:foreign = true``. It is not a GeoEyes measurement: it is a product to compare against.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.core.errors import DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
from geoeyes.io.points import write_points, write_timeseries
from geoeyes.products.builder import _rasters, next_product_id, timeseries_stats, zero_reference
from geoeyes.products.schema import COLUMNS, SCHEMA

log = logging.getLogger(__name__)
ENGINE = "geoeyes-foreign-mintpy/1"


def _attr(a, k, default=None):
    v = a.get(k, default)
    return v.decode() if isinstance(v, bytes) else v


def mintpy_los(incidence_deg, azimuth_deg):
    """Ground-to-satellite unit vector (east, north, up) from MintPy's incidence and azimuth angles."""
    inc, az = np.radians(np.asarray(incidence_deg, np.float64)), np.radians(np.asarray(azimuth_deg, np.float64))
    return -np.sin(inc) * np.sin(az), np.sin(inc) * np.cos(az), np.cos(inc)


def mintpy_meta(ts_path: str | Path) -> dict:
    """Grid, dates and processing attributes of a MintPy time-series file (no data read)."""
    import h5py
    with h5py.File(ts_path, "r") as f:
        a = dict(f.attrs)
        dates = np.array([np.datetime64(f"{s[:4]}-{s[4:6]}-{s[6:8]}") for s in
                          (d.decode() for d in f["date"][()])])
        shape = f["timeseries"].shape
    return {"dates": dates, "shape": shape, "epsg": int(_attr(a, "EPSG", 4326)),
            "x_first": float(_attr(a, "X_FIRST")), "y_first": float(_attr(a, "Y_FIRST")),
            "x_step": float(_attr(a, "X_STEP")), "y_step": float(_attr(a, "Y_STEP")),
            "orbit": str(_attr(a, "ORBIT_DIRECTION", "")).lower(), "relative_orbit": _attr(a, "relative_orbit", ""),
            "heading_deg": float(_attr(a, "HEADING", np.nan)), "wavelength_m": float(_attr(a, "WAVELENGTH", np.nan)),
            "ref_yx": (int(_attr(a, "REF_Y", -1)), int(_attr(a, "REF_X", -1))),
            "ref_date": _attr(a, "REF_DATE", ""), "unit": _attr(a, "UNIT", "m"),
            "processing": {k: _attr(a, k) for k in a if str(k).startswith("mintpy.") and k in (
                "mintpy.troposphericDelay.method", "mintpy.deramp", "mintpy.topographicResidual",
                "mintpy.solidEarthTide", "mintpy.reference.lalo", "mintpy.networkInversion.weightFunc",
                "mintpy.unwrapError.method", "mintpy.load.processor")}}


def block_mean(a: np.ndarray, step: int) -> np.ndarray:
    """NaN-mean over the last two axes in ``step`` × ``step`` blocks (edges cropped)."""
    r, c = (a.shape[-2] // step) * step, (a.shape[-1] // step) * step
    b = a[..., :r, :c].reshape(*a.shape[:-2], r // step, step, c // step, step)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)           # all-NaN blocks give NaN
        return np.nanmean(b, axis=(-3, -1))


def read_mintpy_blocks(ts_path, geom_path, *, step: int = 5, min_valid_share: float = 0.5, rows_per_read: int = 0):
    """(dates, table of block points, displacement mm (points, dates)) of a MintPy stack, block-averaged."""
    import h5py
    from pyproj import Transformer
    meta = mintpy_meta(ts_path)
    _, ny, nx = meta["shape"]
    ry, rx = meta["ref_yx"]
    rows_per_read = rows_per_read or step * max(1, 40 // step)
    rows_per_read -= rows_per_read % step
    tables, disps = [], []
    with h5py.File(ts_path, "r") as f, h5py.File(geom_path, "r") as g:
        ts = f["timeseries"]
        land = g["waterMask"][()] if "waterMask" in g else np.ones((ny, nx), bool)
        for r0 in range(0, (ny // step) * step, rows_per_read):
            r1 = min(r0 + rows_per_read, (ny // step) * step)
            blk = ts[:, r0:r1, :].astype(np.float32) * (1000.0 if meta["unit"] == "m" else 1.0)
            bad = np.all(blk == 0, axis=0)
            if r0 <= ry < r1 and 0 <= rx < nx:
                bad[ry - r0, rx] = False
            bad |= ~land[r0:r1].astype(bool)
            blk[:, bad] = np.nan
            share = block_mean((~bad).astype(np.float32), step)
            d = block_mean(blk, step)                              # (nt, by, bx)
            geo = {k: block_mean(np.where(bad, np.nan, g[k][r0:r1, :].astype(np.float32)), step)
                   for k in ("incidenceAngle", "azimuthAngle", "height")}
            keep = (share >= min_valid_share) & np.all(np.isfinite(d), axis=0)
            iy, ix = np.nonzero(keep)
            row_c = r0 + iy * step + (step - 1) / 2.0
            col_c = ix * step + (step - 1) / 2.0
            tables.append(pd.DataFrame({
                "row": row_c, "col": col_c,
                "x": meta["x_first"] + (col_c + 0.5) * meta["x_step"],
                "y": meta["y_first"] + (row_c + 0.5) * meta["y_step"],
                "incidence_deg": geo["incidenceAngle"][iy, ix], "azimuth_deg": geo["azimuthAngle"][iy, ix],
                "height_m": geo["height"][iy, ix], "valid_share": share[iy, ix]}))
            disps.append(d[:, iy, ix].T)
            log.info("mintpy: rows %d-%d, %d points", r0, r1, len(iy))
    if not tables:
        raise DataError(f"{ts_path}: no valid pixels")
    t = pd.concat(tables, ignore_index=True)
    lon, lat = Transformer.from_crs(meta["epsg"], 4326, always_xy=True).transform(t["x"].to_numpy(), t["y"].to_numpy())
    t["lon"], t["lat"] = lon, lat
    return meta, t, np.concatenate(disps, axis=0).astype(np.float32)


def import_mintpy(ts_path: str | Path, geom_path: str | Path, products_root: str | Path, *, project: str,
                  track_id: str, step: int = 5, min_valid_share: float = 0.5) -> dict:
    """Product ``products_root/<project>_<track>_<first>_<last>_v<N>`` from a MintPy stack (see module doc)."""
    import geopandas as gpd

    from geoeyes.core.geodesy import geohash
    meta, t, disp = read_mintpy_blocks(ts_path, geom_path, step=step, min_valid_share=min_valid_share)
    uid = np.char.add(np.char.add(f"{track_id}:", geohash(t["lat"].to_numpy(), t["lon"].to_numpy())),
                      np.char.add(":", np.round(np.nan_to_num(t["height_m"].to_numpy())).astype(int).astype(str)))
    _, first = np.unique(uid, return_index=True)       # a geohash cell holding two blocks: the first is kept
    first = np.sort(first)
    t, disp, uid = t.iloc[first].reset_index(drop=True), disp[first], uid[first]
    dates = meta["dates"]
    tyr = (dates - dates[0]).astype(np.float64) / 365.25
    n = len(t)
    vel = np.full(n, np.nan, np.float32)
    stats = {k: np.full(n, np.nan, np.float32) for k in ("vel_std", "acc", "amp", "phase_day", "sigma")}
    g = np.column_stack([np.ones_like(tyr), tyr - tyr.mean()])
    for i0 in range(0, n, 20000):                      # in chunks: (dates × points) float64 per chunk
        sl = slice(i0, min(i0 + 20000, n))
        coef, *_ = np.linalg.lstsq(g, disp[sl].T.astype(np.float64), rcond=None)
        vel[sl] = coef[1]
        st = timeseries_stats(disp[sl], dates)
        for k in stats:
            stats[k][sl] = st[k]
    le, ln, lu = mintpy_los(t["incidence_deg"], t["azimuth_deg"])
    p = pd.DataFrame({
        "point_uid": uid, "track_id": track_id, "stack_id": f"mintpy:{Path(ts_path).name}",
        "lon": t["lon"].to_numpy(np.float64), "lat": t["lat"].to_numpy(np.float64), "height_m": t["height_m"],
        "type": "DS", "vel_los_mm_yr": vel, "vel_std_mm_yr": stats["vel_std"], "acc_los_mm_yr2": stats["acc"],
        "temporal_coherence": np.nan, "amp_dispersion": np.nan, "dem_err_m": np.nan,
        "seasonal_amp_mm": stats["amp"], "seasonal_phase_day": stats["phase_day"], "fit_rmse_mm": np.nan,
        "residual_sigma_mm": stats["sigma"], "los_e": le, "los_n": ln, "los_u": lu,
        "incidence_deg": t["incidence_deg"], "heading_deg": meta["heading_deg"]})
    p["extra_valid_share"] = t["valid_share"].to_numpy(np.float32)
    for c, (dtype, _, _) in COLUMNS.items():
        p[c] = p[c].astype(dtype)
    gdf = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p["lon"], p["lat"]), crs="EPSG:4326")

    products_root = Path(products_root)
    d0, d1 = dates[0].astype(object), dates[-1].astype(object)
    pid = next_product_id(products_root, f"{project}_{track_id}_{d0:%Y%m%d}_{d1:%Y%m%d}")
    out = products_root / pid
    out.mkdir(parents=True)
    v = p["vel_los_mm_yr"].to_numpy(np.float64)
    metrics = {"n_points": len(p), "n_ds": len(p), "epochs": len(dates), "first_date": str(d0), "last_date": str(d1),
               "engine": "mintpy", "vel_min_mm_yr": float(np.nanmin(v)), "vel_max_mm_yr": float(np.nanmax(v)),
               "vel_p02_mm_yr": float(np.nanpercentile(v, 2)), "vel_median_mm_yr": float(np.nanmedian(v)),
               "vel_p98_mm_yr": float(np.nanpercentile(v, 98)),
               "vel_std_median_mm_yr": float(np.nanmedian(p["vel_std_mm_yr"])), "block_px": step,
               "reference": f"MintPy pixel {meta['ref_yx']}", "aps": str(meta["processing"].get(
                   "mintpy.troposphericDelay.method", ""))}
    write_points(out / "points.parquet", gdf, metadata={"schema": SCHEMA, "product_id": pid, "foreign": "mintpy",
                                                        "sign_convention": "LOS + toward the satellite",
                                                        "reference_date": str(meta["ref_date"]),
                                                        "time_zero": "first date"})
    write_timeseries(out / "timeseries.parquet", p["point_uid"].to_numpy(), dates, zero_reference(disp))
    rasters = _rasters(out / "rasters", p["lon"].to_numpy(), p["lat"].to_numpy(), v)
    bbox = [float(p["lon"].min()), float(p["lat"].min()), float(p["lon"].max()), float(p["lat"].max())]
    item = {"type": "Feature", "stac_version": "1.0.0", "id": pid, "bbox": bbox,
            "geometry": {"type": "Polygon", "coordinates": [[[bbox[0], bbox[1]], [bbox[2], bbox[1]],
                                                             [bbox[2], bbox[3]], [bbox[0], bbox[3]],
                                                             [bbox[0], bbox[1]]]]},
            "properties": {"datetime": None, "start_datetime": f"{d0}T00:00:00Z", "end_datetime": f"{d1}T23:59:59Z",
                           "geoeyes:project": project, "geoeyes:track": track_id, "geoeyes:sensor": "sentinel1",
                           "geoeyes:engine": "mintpy", "geoeyes:foreign": True, "geoeyes:schema": SCHEMA,
                           "geoeyes:mintpy": {"source": str(ts_path), **meta["processing"]},
                           **{f"geoeyes:{k}": v_ for k, v_ in metrics.items() if isinstance(v_, (int, float, str))}},
            "assets": {"points": {"href": "./points.parquet", "type": "application/vnd.apache.parquet",
                                  "roles": ["data"]},
                       "timeseries": {"href": "./timeseries.parquet", "type": "application/vnd.apache.parquet",
                                      "roles": ["data"]},
                       "velocity": {"href": "./rasters/velocity.tif",
                                    "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                                    "roles": ["data", "visual"]}},
            "links": []}
    atomic_write_json(out / "item.json", item)
    m = Manifest(kind="product", id=pid, engine=ENGINE, inputs=[InputRef("mintpy_timeseries", str(ts_path), ""),
                                                                InputRef("mintpy_geometry", str(geom_path), "")],
                 metrics=metrics)
    m.add_outputs(out, ["points.parquet", "timeseries.parquet", "item.json", *(r.relative_to(out) for r in rasters)])
    m.write(out)
    log.info("mintpy product %s: %d points, %s..%s", pid, len(p), d0, d1)
    return {"product_id": pid, "path": str(out), **metrics}


__all__ = ["block_mean", "import_mintpy", "mintpy_los", "mintpy_meta", "read_mintpy_blocks"]
