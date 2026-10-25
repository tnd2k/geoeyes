"""Gather what the report shows from a product and the artifacts it was made from (ARCHITECTURE §13.3).

Sources, all written by the pipeline: the product (manifest, STAC item, points, time series), the PS run it
came from (manifest, params, state for the per-interferogram quality), the stack (dates, baselines, sensor
attributes; optional — a stack may be deleted after the product exists), the project configuration and the
run records (phase durations). Nothing is recomputed except summary statistics.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from geoeyes.io.manifest import Manifest, read_json

log = logging.getLogger(__name__)


def _band(wavelength: float | None) -> str:
    if not wavelength:
        return ""
    return "X" if wavelength < 0.04 else "C" if wavelength < 0.08 else "S" if wavelength < 0.15 else "L"


def _project_root(product: Path) -> Path:
    return product.parent.parent                   # <project>/products/<product_id>


def _stack(ps_manifest: Manifest) -> dict[str, Any]:
    from geoeyes.io.stack import StackStore
    uri = next((i.uri for i in ps_manifest.inputs if i.kind == "stack"), "")
    st = StackStore(uri) if uri else None
    if st is None or not st.exists():
        return {}
    ds = st.open()
    a = dict(ds.attrs)
    dates = [d.astype("datetime64[D]").astype(object) for d in ds["date"].values]
    bperp = ds["bperp"].values.astype(float) if "bperp" in ds else np.full(len(dates), np.nan)
    return {"path": uri, "attrs": a, "dates": dates, "bperp": bperp, "shape": [int(ds.sizes.get("y", 0)),
                                                                                int(ds.sizes.get("x", 0))]}


def _per_date(ps_dir: Path, ps_manifest: Manifest, stack: dict) -> list[dict]:
    """One row per acquisition: baseline, noise, used / weather APS flags, APS variance reduction."""
    import h5py
    ref = ps_manifest.metrics.get("reference_date")
    rows: dict[str, dict] = {}
    if stack:
        for d, b in zip(stack["dates"], stack["bperp"], strict=True):
            rows[str(d)] = {"date": str(d), "bperp_m": round(float(b), 1)}
    for p in ps_manifest.extra.get("pairs", []):                 # ps_lite
        r = rows.setdefault(p["date"], {"date": p["date"]})
        r.update(bperp_m=p.get("bperp_m", r.get("bperp_m")), noise=p.get("phase_std_rad"), noise_unit="rad",
                 used=bool(p.get("used", True)), weather=bool(p.get("weather_aps")))
    state = ps_dir / "state.h5"
    if state.exists():
        with h5py.File(state, "r") as h:
            if "time/ifg_std_deg" in h:                          # ps engine: noise per epoch
                for d, s in zip(h["time/epoch_dates"][()], h["time/ifg_std_deg"][()], strict=True):
                    d = d.decode() if isinstance(d, bytes) else str(d)
                    d = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
                    rows.setdefault(d, {"date": d}).update(noise=round(float(s), 1), noise_unit="deg")
    out = sorted(rows.values(), key=lambda r: r["date"])
    for r in out:
        r["reference"] = r["date"] == ref
        r.setdefault("used", True)
    return out


def _phase_times(project: Path, track: str) -> list[dict]:
    """Duration of the last completed run of each phase of the track, from the project state (written as each
    phase ends, so it includes the run the report is part of; the run manifest is written only at its end)."""
    state = project / ".state" / "state.json"
    phases = read_json(state).get("phases", {}) if state.exists() else {}
    last: dict[str, dict] = {}
    for key, r in phases.items():
        t, _, phase = key.rpartition("/")
        if t == track and r.get("status") == "done" and phase != "report":
            last[phase] = {"phase": phase, "seconds": r.get("seconds"), "run_id": r.get("run_id")}
    order = ["build_stack", "phase_linking", "ps", "build_product", "export"]
    return sorted(last.values(), key=lambda r: order.index(r["phase"]) if r["phase"] in order else 99)


def _area_km2(lon, lat) -> float:
    """Area covered by points: 100 m cells holding at least one point."""
    lat0 = np.radians(np.nanmean(lat))
    x = np.floor((lon - np.nanmin(lon)) * 111_320 * np.cos(lat0) / 100).astype(np.int64)
    y = np.floor((lat - np.nanmin(lat)) * 110_540 / 100).astype(np.int64)
    return float(np.unique(x * 1_000_003 + y).size * 0.01)


def _stats(pts) -> dict[str, Any]:
    v = pts["vel_los_mm_yr"].to_numpy(float)
    q = lambda a, p: float(np.nanpercentile(a, p))                       # noqa: E731
    out = {"n_points": int(len(pts)), "n_ps": int((pts["type"] == "PS").sum()),
           "n_ds": int((pts["type"] == "DS").sum()),
           "vel": {k: round(q(v, p), 2) for k, p in (("p01", 1), ("p02", 2), ("p50", 50), ("p98", 98),
                                                       ("p99", 99))},
           "vel_min": round(float(np.nanmin(v)), 2), "vel_max": round(float(np.nanmax(v)), 2)}
    for col, key in (("vel_std_mm_yr", "vel_std"), ("temporal_coherence", "tcoh"), ("dem_err_m", "dem_err"),
                     ("residual_sigma_mm", "residual_sigma"), ("seasonal_amp_mm", "seasonal_amp")):
        if col in pts and pts[col].notna().any():
            a = pts[col].to_numpy(float)
            out[key] = {"p05": round(q(a, 5), 2), "p50": round(q(a, 50), 2), "p95": round(q(a, 95), 2)}
    area = _area_km2(pts["lon"].to_numpy(float), pts["lat"].to_numpy(float))
    out["area_km2"] = round(area, 1)
    out["density_per_km2"] = round(len(pts) / area, 0) if area else None
    return out


def _clusters(pts, ts) -> list[dict]:
    """Representative time series: mean ± std of the fastest-moving 0.5 % in each direction and of stable
    high-coherence points (|v| in the lowest 10 %), with their centroid."""
    v = pts["vel_los_mm_yr"].to_numpy(float)
    tc = pts["temporal_coherence"].to_numpy(float)
    lo, hi = np.nanpercentile(v, [0.5, 99.5])
    stable = (np.abs(v) <= np.nanpercentile(np.abs(v), 10)) & (tc >= np.nanpercentile(tc, 50))
    groups = [("fastest motion away from the satellite", v <= lo), ("fastest motion toward the satellite", v >= hi),
              ("stable points", stable)]
    wide = ts.pivot(index="point_uid", columns="date", values="disp_mm")
    out = []
    for label, m in groups:
        uid = pts.loc[m, "point_uid"]
        sub = wide.reindex(uid).to_numpy(float)
        if not len(uid):
            continue
        out.append({"label": label, "n": int(m.sum()), "lon": float(pts.loc[m, "lon"].median()),
                    "lat": float(pts.loc[m, "lat"].median()), "vel_mm_yr": round(float(np.nanmedian(v[m])), 1),
                    "dates": [str(d.date()) if hasattr(d, "date") else str(d) for d in wide.columns],
                    "mean_mm": np.nanmean(sub, axis=0).round(2).tolist(),
                    "std_mm": np.nanstd(sub, axis=0).round(2).tolist()})
    return out


def confidence(n_dates: int, span_days: float, used_frac: float, stats: dict) -> dict[str, Any]:
    """High / medium / low with the reasons (simple, stated rules; not a calibrated uncertainty)."""
    issues, notes = [], []
    if n_dates < 10:
        issues.append(f"only {n_dates} acquisitions")
    elif n_dates < 20:
        notes.append(f"{n_dates} acquisitions: enough for a mean velocity, few for non-linear motion")
    if span_days < 180:
        issues.append(f"time span {span_days:.0f} days: the velocity extrapolates a short series to a year "
                      "and seasonal motion cannot be separated")
    elif span_days < 365:
        notes.append(f"time span {span_days:.0f} days (< 1 year): seasonal motion is not separated")
    if used_frac < 0.8:
        issues.append(f"{used_frac:.0%} of the interferograms used (the others failed the noise test)")
    vs = (stats.get("vel_std") or {}).get("p50")
    spread = (stats["vel"]["p98"] - stats["vel"]["p02"]) / 2
    if vs is not None and spread > 0 and vs > 0.3 * spread:
        issues.append(f"median velocity uncertainty {vs:.1f} mm/yr is large against the signal "
                      f"(P2–P98 half-range {spread:.1f} mm/yr)")
    med = stats["vel"]["p50"]
    if spread > 0 and abs(med) > 0.5 * spread:
        issues.append(f"median velocity {med:+.1f} mm/yr is far from zero: most points move relative to the "
                      "reference area, which may itself be moving")
    tc = (stats.get("tcoh") or {}).get("p50")
    if tc is not None and tc < 0.5:
        issues.append(f"median temporal coherence {tc:.2f}")
    level = "high" if not issues else "medium" if len(issues) == 1 else "low"
    return {"level": level, "issues": issues, "notes": notes}


def findings(stats: dict, clusters: list[dict], span_days: float) -> list[str]:
    v = stats["vel"]
    out = [f"{stats['n_points']:,} measurement points ({stats['n_ds']:,} distributed scatterers), "
           f"{stats['density_per_km2']:,.0f} points per km² over {stats['area_km2']:,.1f} km²."]
    out.append(f"LOS velocity from {stats['vel_min']:+.1f} to {stats['vel_max']:+.1f} mm/yr (minimum and maximum "
               f"over all points), median {v['p50']:+.1f} mm/yr relative to the reference area.")
    for c in clusters[:2]:
        if abs(c["vel_mm_yr"]) > 2 * max((stats.get("vel_std") or {}).get("p50", 0), 0.5):
            out.append(f"The {c['label']} ({c['n']:,} points, median {c['vel_mm_yr']:+.1f} mm/yr) is centred near "
                       f"{c['lat']:.4f}° N, {c['lon']:.4f}° E.")
    vs = (stats.get("vel_std") or {}).get("p50")
    if vs is not None:
        out.append(f"Median velocity standard error {vs:.1f} mm/yr; median temporal coherence "
                   f"{(stats.get('tcoh') or {}).get('p50', float('nan')):.2f}.")
    if span_days < 365:
        out.append(f"The series covers {span_days:.0f} days: velocities are mean rates over that period.")
    return out


def collect(product: str | Path) -> dict[str, Any]:
    from geoeyes.config.loader import load
    from geoeyes.io.points import read_points, read_timeseries
    from geoeyes.report import methods
    product = Path(product)
    pm = Manifest.read(product)
    item = read_json(product / "item.json")
    props = item["properties"]
    ps_dir = Path(next(i.uri for i in pm.inputs if i.kind == "ps_run"))
    psm = Manifest.read(ps_dir)
    params = read_json(ps_dir / "params.json") if (ps_dir / "params.json").exists() else {}
    stack = _stack(psm)
    a = stack.get("attrs", {})
    root = _project_root(product)
    cfg = load(root / "project.toml") if (root / "project.toml").exists() else None
    track = props.get("geoeyes:track", "")

    pts = read_points(product / "points.parquet")
    ts = read_timeseries(product / "timeseries.parquet")
    stats = _stats(pts)
    clusters = _clusters(pts, ts)
    rows = _per_date(ps_dir, psm, stack)
    d0, d1 = date.fromisoformat(props["geoeyes:first_date"]), date.fromisoformat(props["geoeyes:last_date"])
    span = (d1 - d0).days
    ifg_rows = [r for r in rows if not r["reference"]]
    used_frac = sum(r["used"] for r in ifg_rows) / max(len(ifg_rows), 1)
    ref_date = psm.metrics.get("reference_date", a.get("reference_date", ""))
    for r in rows:
        r["days"] = (date.fromisoformat(r["date"]) - date.fromisoformat(str(ref_date))).days if ref_date else None

    sensor = props.get("geoeyes:sensor", a.get("sensor", ""))
    wl = a.get("wavelength_m")
    acq = {"sensor": sensor, "mode": a.get("mode", ""), "polarization": a.get("polarization", ""),
           "wavelength_m": wl, "band": _band(wl), "heading_deg": a.get("heading_deg"),
           "pass_direction": a.get("pass_direction", ""), "look_side": a.get("look_side", ""),
           "first": str(d0), "last": str(d1), "span_days": span, "n_dates": props.get("geoeyes:epochs"),
           "reference_date": str(ref_date), "orbit": a.get("orbit", ""), "dem": a.get("dem", ""),
           "stack_engine": a.get("engine", ""), "stack_shape": stack.get("shape"),
           "subswath": a.get("subswath", ""), "scenes": a.get("scenes") or {}, "burst_ids": a.get("burst_ids", [])}
    data = {
        "schema": "geoeyes.report/1",
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "product_id": pm.id, "project": props.get("geoeyes:project", ""), "track": track,
        "description": cfg.project.description if cfg else "",
        "bbox": item.get("bbox"), "aoi_bbox": list(cfg.aoi.bbox) if cfg and cfg.aoi.bbox else None,
        "software": pm.software, "ps_engine": psm.engine,
        "acquisition": acq, "dates": rows, "stats": stats, "clusters": clusters,
        "reference": psm.metrics.get("reference") or pm.metrics.get("reference"),
        "aps": psm.metrics.get("aps", ""), "ifgs_used": f"{sum(r['used'] for r in ifg_rows)}/{len(ifg_rows)}",
        "ps_counts": psm.metrics.get("ps", {}), "ps_runtime_s": psm.metrics.get("runtime_s"),
        "confidence": confidence(len(rows) or int(props.get("geoeyes:epochs", 0)), span, used_frac, stats),
        "phases": _phase_times(root, track),
        "files": [{"path": f.path, "sha256": f.sha256, "bytes": f.bytes} for f in pm.outputs],
        "inputs": [{"kind": i.kind, "uri": i.uri, "sha256": i.sha256} for i in pm.inputs],
    }
    data["findings"] = findings(stats, clusters, span)
    data["method"] = methods.describe(cfg, psm, params, a)
    data["limitations"] = methods.limitations(data)
    data["references"] = methods.references(data["method"])
    return data
