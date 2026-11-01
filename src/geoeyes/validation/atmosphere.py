"""Weather models tried on a product (``geoeyes atmosphere``; web app: project page, Atmosphere tab).

Without running the pipeline again: the unwrapped phase of the ``ps`` run behind the product, minus a linear
motion and a look-angle error per point (what is left is mostly atmosphere and noise), is compared with the APS
each model predicts at the points. Per interferogram: the scatter (mm) of that residual with no APS, with the
engine's linear (height-correlated) APS and with every usable weather model (``processing.atmosphere.models``),
each centred per interferogram as in the engine; the correlation of the residual with height; and gridded maps
(observed residual, model APS, residual after the model) for the page.

Outputs in ``analyses/atmosphere/<product>/``: ``atmosphere.json`` (catalogue, statistics) and ``grids.npz``.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from geoeyes.io.manifest import Manifest, atomic_write_json, read_json

log = logging.getLogger(__name__)

DEFAULTS = {"models": "auto", "max_points": 200_000, "grid": 256, "seed": 0}


def _inputs(product: Path) -> tuple[Path, Path]:
    pm = Manifest.read(product)
    ps_dir = Path(next(i.uri for i in pm.inputs if i.kind == "ps_run"))
    psm = Manifest.read(ps_dir)
    stack = Path(next(i.uri for i in psm.inputs if i.kind == "stack"))
    return ps_dir, stack


def _detrended(ph: np.ndarray, t_yr: np.ndarray, bperp: np.ndarray) -> np.ndarray:
    from geoeyes.processing.ps.aps import _detrend_parts
    r = _detrend_parts(ph, t_yr, bperp)[0]
    return r - np.nanmean(r, axis=0)


def _grid(lon, lat, values: np.ndarray, size: int) -> tuple[np.ndarray, list[float]]:
    """Mean of ``values`` (n, k) on a size x size lon/lat grid: (k, size, size) float32 (NaN = empty), bounds."""
    w, e, s, n = float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max())
    ix = np.clip(((lon - w) / max(e - w, 1e-12) * size).astype(int), 0, size - 1)
    iy = np.clip(((n - lat) / max(n - s, 1e-12) * size).astype(int), 0, size - 1)
    flat = iy * size + ix
    out = np.empty((values.shape[1], size, size), np.float32)
    for k in range(values.shape[1]):
        v = values[:, k]
        ok = np.isfinite(v)
        s_ = np.bincount(flat[ok], weights=v[ok], minlength=size * size)
        c = np.bincount(flat[ok], minlength=size * size).astype(np.float64)
        out[k] = np.where(c > 0, s_ / np.maximum(c, 1), np.nan).reshape(size, size)
    return out, [w, s, e, n]


def run_atmosphere(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None,
                   progress=None) -> dict:
    """Try the weather models on one product of ``project``; returns the summary written to ``atmosphere.json``."""
    import xarray as xr

    from geoeyes.io.state import StateStore
    from geoeyes.processing.atmosphere.models import catalogue
    from geoeyes.processing.atmosphere.times import acquisition_times
    from geoeyes.processing.atmosphere.weather import WeatherParams, weather_aps
    from geoeyes.processing.ps.aps import centre_weather

    say = progress or (lambda msg: log.info(msg))
    p = {**DEFAULTS, **(overrides or {})}
    product = project.product(product_id)
    out = project.analysis("atmosphere", product_id)
    out.mkdir(parents=True, exist_ok=True)
    ps_dir, stack_path = _inputs(product)
    from geoeyes.processing.ps.runner import STATE_SCHEMA
    st = StateStore(ps_dir / "state.h5", STATE_SCHEMA)
    try:
        ph_uw = st.read("phase/unwrapped")
    except Exception as exc:
        raise ValueError(f"{ps_dir.name}: no unwrapped phase in state.h5 (the StaMPS-type ps engine only)") from exc
    lon, lat, hgt = st.read("ps/lon"), st.read("ps/lat"), st.read("ps/height_m")
    line, sample = st.read("ps/line"), st.read("ps/sample")
    scla, aps_lin, bperp = st.read("phase/scla"), st.read("phase/aps_linear"), st.read("ps/bperp")
    epochs = [date.fromisoformat(d.decode() if isinstance(d, bytes) else str(d)) for d in st.read("time/epoch_dates")]
    ifg_dates = [date.fromisoformat(d.decode() if isinstance(d, bytes) else str(d)) for d in st.read("time/ifg_dates")]
    ds = xr.open_zarr(stack_path, consolidated=False)
    attrs = dict(ds.attrs)
    master = date.fromisoformat(str(attrs["reference_date"])[:10])
    mi = epochs.index(master)
    wl = float(attrs["wavelength_m"])
    rows = np.flatnonzero(np.all(np.isfinite(ph_uw), axis=1))
    if rows.size > int(p["max_points"]):
        rows = np.sort(np.random.default_rng(int(p["seed"])).choice(rows, int(p["max_points"]), replace=False))
    inc = np.radians(ds["geometry_incidence"].values[line[rows], sample[rows]].astype(np.float64))
    lon_s, lat_s, hgt_s = lon[rows].astype(np.float64), lat[rows].astype(np.float64), hgt[rows].astype(np.float64)
    ph = (ph_uw[rows] - scla[rows]).astype(np.float64)
    t_yr = np.array([(d - master).days for d in ifg_dates], np.float64) / 365.25
    b = bperp[rows].astype(np.float64)
    to_mm = wl / (4 * np.pi) * 1e3
    say(f"{rows.size} of {ph_uw.shape[0]} points, {len(ifg_dates)} interferograms")

    cat = catalogue(lon_s, lat_s, epochs)
    wanted = p["models"]
    if wanted == "auto":
        names = [m["key"] for m in cat if m["usable"]]
        if dict(cfg.atmosphere.gacos).get("dir"):
            names.append("gacos")                       # ordered by the user, read from the folder
    else:
        names = [str(m) for m in (wanted if isinstance(wanted, list) else str(wanted).split(","))]
    base = WeatherParams.from_section(cfg.atmosphere, ws.cache)
    times = acquisition_times(attrs, epochs, base.fallback_utc)

    residual = {"none": _detrended(ph, t_yr, b)}
    aps = {"linear": np.delete(aps_lin[rows].astype(np.float64), mi, axis=1) if aps_lin.shape[1] == len(epochs)
           else aps_lin[rows].astype(np.float64)}
    residual["linear"] = _detrended(ph - aps["linear"], t_yr, b)
    errors: dict[str, str] = {}
    for name in dict.fromkeys(names):
        say(f"{name}: delays at the points")
        try:
            wp = dataclasses.replace(base, method=name)
            full = weather_aps(wp, lon=lon_s, lat=lat_s, hgt=hgt_s, incidence=inc, times=times, master_ix=mi,
                               wavelength=wl)
            full = centre_weather(ph, full, mi)
            a = np.delete(full, mi, axis=1)
        except Exception as exc:                          # a model that fails does not stop the others
            errors[name] = f"{type(exc).__name__}: {exc}"
            say(f"{name}: failed ({errors[name]})")
            continue
        aps[name] = a
        residual[name] = _detrended(ph - np.where(np.isfinite(a), a, aps["linear"]), t_yr, b)

    def r_h(r):
        return [float(np.corrcoef(hgt_s[np.isfinite(r[:, k])], r[np.isfinite(r[:, k]), k])[0, 1])
                if np.isfinite(r[:, k]).sum() > 10 else None for k in range(r.shape[1])]

    per_model = {}
    for name, r in residual.items():
        std = np.nanstd(r, axis=0) * to_mm
        a = aps.get(name)
        per_model[name] = {
            "std_mm": [round(float(x), 3) for x in std],
            "r_height": [None if v is None else round(v, 3) for v in r_h(r)],
            "aps_std_mm": None if a is None else [round(float(x), 3) for x in np.nanstd(a, axis=0) * to_mm],
            "coverage": None if a is None else round(float(np.isfinite(a).mean()), 4),
        }
    none = np.asarray(per_model["none"]["std_mm"])
    for m in per_model.values():
        s_ = np.asarray(m["std_mm"])
        m["median_std_mm"] = round(float(np.median(s_)), 3)
        m["reduction_pct"] = round(float(np.median(100.0 * (1.0 - s_**2 / np.maximum(none**2, 1e-12)))), 1)
        m["best_ifgs"] = 0
    keys = list(per_model)
    best = np.argmin(np.stack([per_model[k]["std_mm"] for k in keys]), axis=0)
    for k in best:
        per_model[keys[k]]["best_ifgs"] += 1

    say("maps")
    size = int(p["grid"])
    layers = {"obs": residual["none"]}
    for name in aps:
        layers[f"aps:{name}"] = aps[name] - np.nanmean(aps[name], axis=0)
        layers[f"res:{name}"] = residual[name]
    grids, bounds = {}, None
    for key, v in layers.items():
        g, bounds = _grid(lon_s, lat_s, v * to_mm, size)
        grids[key.replace(":", "__")] = g
    np.savez_compressed(out / "grids.npz", **grids)

    summary = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"), "product": product_id, "ps_run": ps_dir.name,
        "params": p, "points": int(rows.size), "points_total": int(ph_uw.shape[0]), "wavelength_m": wl,
        "reference_date": master.isoformat(), "ifg_dates": [d.isoformat() for d in ifg_dates],
        "acquisition_utc": {d.isoformat(): times[d].strftime("%H:%M") for d in epochs},
        "current_method": str(cfg.atmosphere.method), "catalogue": cat, "tried": list(aps), "errors": errors,
        "models": per_model, "grid": {"size": size, "bounds": bounds, "layers": list(layers)},
        "span_days": (max(epochs) - min(epochs)).days,
    }
    from geoeyes.processing.atmosphere import cerra
    summary["outlines"] = {"cerra": cerra.outline()}
    atomic_write_json(out / "atmosphere.json", summary)
    return summary


def read_summary(folder: Path) -> dict | None:
    f = Path(folder) / "atmosphere.json"
    return read_json(f) if f.exists() else None


__all__ = ["DEFAULTS", "read_summary", "run_atmosphere"]
