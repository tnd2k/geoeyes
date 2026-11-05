"""Exposure: the people and buildings on subsiding ground and in the flooded area of an event, from open layers of
Source Cooperative (``geoeyes.opendata.coop``) set against a product.

Cells are those of GHS-POP (3", ~90 m), the population layer:

* **subsidence**: the median vertical rate of the product's points in each cell (v_LOS / l_u, at least
  ``min_points``); population and GlobalBuildingAtlas buildings (centres, heights) summed per class of
  ``breaks_mm_yr`` (sinking, GeoEyes sign: negative). Cells without points are "not observed": their people are
  reported, not guessed.
* **flood of an event** (``flood_month``, ``YYYY-MM``, 2017-2024): JRC Global Surface Water water of that month
  where ``dry_month`` saw land (permanent water and rivers left out); the flooded share of each population cell from
  the 30 m pixels inside it. Monthly composites from Landsat / Sentinel-2: cloud hides part of a monsoon month
  ("no observation" pixels are counted apart) and short floods may be missed. Rainfall of the month from CHIRPS
  daily. The rates of the points on flooded and dry ground are compared (idea 4: does the sinking ground flood?).
* **river flood scenario** (``glofas_rp``, 0 = none): GloFAS depth of the ``glofas_rp``-year flood. A global
  model at 90 m without the dykes: in a diked delta (Red River, Hanoi) it maps the floodplain the dykes protect,
  an upper bound.

Outputs ``exposure.json`` and ``exposure_cells.parquet`` (one row per population cell over the product).
"""
from __future__ import annotations

import itertools
import json
import logging
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.exposure/1"


@dataclass(frozen=True)
class ExposureParams:
    """``[postprocess.exposure]`` of project.toml (every key optional)."""

    min_points: int = 3                                            # points in a population cell to give it a rate
    breaks_mm_yr: tuple[float, ...] = (5.0, 10.0, 20.0, 50.0)      # sinking classes (vertical, mm/yr)
    buildings: bool = True                                         # GlobalBuildingAtlas buildings per class
    flood_month: str = ""                                          # YYYY-MM of an event, "" = no flood part
    dry_month: str = ""                                            # YYYY-MM of reference (default: same month - 6)
    glofas_rp: int = 0                                             # GloFAS return period (10 ... 500), 0 = none

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ExposureParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.exposure]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for k, v in d.items():
            default = getattr(cls, k)
            out[k] = tuple(float(x) for x in v) if isinstance(default, tuple) else \
                (str(v).lower() in ("1", "true", "yes") if isinstance(default, bool) else type(default)(v))
        return cls(**out)


def class_labels(breaks: tuple[float, ...]) -> list[str]:
    b = [f"{v:g}" for v in breaks]
    return [f"< {b[0]}"] + [f"{lo}-{hi}" for lo, hi in itertools.pairwise(b)] + [f">= {b[-1]}"]


def _dry(month: str) -> str:
    y, m = (int(v) for v in month.split("-"))
    m -= 6
    if m < 1:
        y, m = y - 1, m + 12
    return f"{max(y, 2017)}-{m:02d}"                 # before the mirror's first year: the same month of 2017


def run(product: Path, out: Path, params: ExposureParams, *, cache: Path, icechunk_python: str | None = None,
        progress=None) -> dict:
    from geoeyes.opendata import coop
    say = progress or (lambda m: log.info("%s", m))
    pts = pq.read_table(product / "points.parquet", columns=["lon", "lat", "vel_los_mm_yr", "los_u"]).to_pandas()
    if pts.empty:
        raise DataError(f"{product.name}: no point")
    bbox = [float(pts.lon.min()), float(pts.lat.min()), float(pts.lon.max()), float(pts.lat.max())]
    v_vert = pts.vel_los_mm_yr.to_numpy(np.float64) / np.clip(pts.los_u.to_numpy(np.float64), 0.2, None)

    say("population: GHS-POP R2023A (Source Cooperative)")
    pop = coop.ghsl_pop(cache, bbox)
    ny, nx = pop.data.shape
    people = np.nan_to_num(pop.data.astype(np.float64)).ravel()
    r, c, ok = pop.pixel(pts.lon, pts.lat)
    cell = (r * nx + c)[ok]
    vv = v_vert[ok]
    order = np.argsort(cell, kind="stable")
    cell, vv = cell[order], vv[order]
    starts = np.flatnonzero(np.r_[True, cell[1:] != cell[:-1]])
    n_pts = np.zeros(ny * nx, np.int32)
    rate = np.full(ny * nx, np.nan)
    for a, z in zip(starts, np.r_[starts[1:], len(cell)], strict=True):
        n_pts[cell[a]] = z - a
        if z - a >= params.min_points:
            rate[cell[a]] = float(np.median(vv[a:z]))
    labels = class_labels(params.breaks_mm_yr)
    observed = np.isfinite(rate)
    cls = np.where(observed, np.searchsorted(np.asarray(params.breaks_mm_yr), -np.nan_to_num(rate), side="right"), -1)

    rows = []
    for k, lab in enumerate(labels):
        m = cls == k
        rows.append({"class": lab, "cells": int(m.sum()), "people": round(float(people[m].sum()))})
    sub = {"breaks_mm_yr": list(params.breaks_mm_yr), "classes": rows,
           "people_observed": round(float(people[observed].sum())),
           "people_not_observed": round(float(people[~observed].sum())),
           "people_total": round(float(people.sum())), "cells_observed": int(observed.sum())}

    bld_cls = None
    if params.buildings:
        try:
            say("buildings: GlobalBuildingAtlas LoD1 (Source Cooperative)")
            g = coop.gba_buildings(cache, bbox, geometry=False, progress=say)
            br, bc, bok = pop.pixel(g["lon"], g["lat"])
            bcell = np.where(bok, br * nx + bc, -1)
            bld_cls = np.where(bok, cls[np.clip(bcell, 0, None)], -2)
            h = g["height_m"].to_numpy(np.float64)
            for k, row in enumerate(rows):
                m = bld_cls == k
                row["buildings"] = int(m.sum())
                row["buildings_over_21m"] = int((m & (h >= 21)).sum())
            sub["buildings_observed"] = int((bld_cls >= 0).sum())
            sub["buildings_not_observed"] = int((bld_cls == -1).sum())
        except Exception as exc:                     # the population part stands on its own
            log.warning("GlobalBuildingAtlas unavailable: %s", exc)
            sub["warning"] = f"buildings unavailable: {exc}"

    lon_c = pop.west + (np.arange(nx) + 0.5) * pop.res
    lat_c = pop.north - (np.arange(ny) + 0.5) * pop.res
    table = pd.DataFrame({"lon": np.tile(lon_c, ny), "lat": np.repeat(lat_c, nx), "people": people.astype(np.float32),
                          "points": n_pts, "v_vert_mm_yr": rate.astype(np.float32), "class": cls.astype(np.int8)})
    summary = {"schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
               "params": asdict(params), "bbox": bbox, "cell_deg": pop.res, "subsidence": sub,
               "credits": [coop.LAYERS["ghsl-pop"].credit]
               + ([coop.LAYERS["gba-buildings"].credit] if bld_cls is not None else []),
               "method": "geoeyes.hazard.exposure"}

    if params.flood_month:
        summary["flood"] = _flood(params, cache, bbox, pop, people, table, pts, v_vert, say)
        summary["credits"] += [coop.LAYERS["gsw-monthly"].credit, coop.LAYERS["chirps-daily"].credit]
        peak = _peak_30min(cache, bbox, params.flood_month, icechunk_python, say)
        summary["flood"]["rain_peak_30min"] = peak
        if peak:
            summary["credits"].append(coop.LAYERS["imerg"].credit)
    if params.glofas_rp:
        say(f"GloFAS river flood depth, {params.glofas_rp}-year return period")
        d = coop.glofas_depth(cache, bbox, params.glofas_rp)
        rr, cc, inside = d.pixel(table["lon"], table["lat"])
        depth = np.where(inside, d.data[rr, cc], np.nan)
        table["glofas_depth_m"] = depth.astype(np.float32)
        wet = np.isfinite(depth)
        summary["glofas"] = {
            "return_period": params.glofas_rp, "people": round(float(people[wet].sum())),
            "people_over_1m": round(float(people[wet & (depth >= 1)].sum())),
            "people_on_sinking_ground": round(float(people[wet & (cls >= 1)].sum())),
            "note": "global model without dykes: in a diked delta, an upper bound"}
        summary["credits"].append(coop.LAYERS["glofas-depth"].credit)

    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "exposure_cells.parquet", index=False)
    atomic_write_json(out / "exposure.json", summary)
    m = Manifest(kind="exposure", id=product.name, engine=SCHEMA, inputs=[InputRef("product", str(product))],
                 params=summary["params"], metrics={"people_observed": sub["people_observed"]})
    m.add_outputs(out, ["exposure_cells.parquet", "exposure.json"])
    m.write(out)
    say("exposure: " + ", ".join(f"{r_['class']} mm/yr {r_['people']:,} people" for r_ in rows))
    return summary


def _flood(params: ExposureParams, cache: Path, bbox, pop, people, table, pts, v_vert, say) -> dict:
    from geoeyes.opendata import coop
    month, dry = params.flood_month, params.dry_month or _dry(params.flood_month)
    say(f"surface water: {month} against {dry} (JRC GSW, Source Cooperative)")
    ev, ref = coop.gsw_month(cache, bbox, month), coop.gsw_month(cache, bbox, dry)
    if ev.data.shape != ref.data.shape or abs(ev.west - ref.west) > ev.res / 2:
        from scipy.ndimage import zoom
        ref_data = zoom(np.nan_to_num(ref.data), (ev.data.shape[0] / ref.data.shape[0],
                                                  ev.data.shape[1] / ref.data.shape[1]), order=0)
        ref_data = np.where(ref_data == 0, np.nan, ref_data)
    else:
        ref_data = ref.data
    flooded = (ev.data == 2) & (ref_data == 1)
    unseen = ~np.isfinite(ev.data)
    ny, nx = pop.data.shape
    # population cell of every 30 m pixel: the flooded share of each cell
    lat = ev.north - (np.arange(ev.data.shape[0]) + 0.5) * ev.res
    lon = ev.west + (np.arange(ev.data.shape[1]) + 0.5) * ev.res
    rr = np.floor((pop.north - lat) / pop.res).astype(np.int64)
    cc = np.floor((lon - pop.west) / pop.res).astype(np.int64)
    okr, okc = (rr >= 0) & (rr < ny), (cc >= 0) & (cc < nx)
    idx = (np.clip(rr, 0, ny - 1)[:, None] * nx + np.clip(cc, 0, nx - 1)[None, :])
    valid = okr[:, None] & okc[None, :]
    total = np.bincount(idx[valid], minlength=ny * nx).astype(np.float64)
    wet = np.bincount(idx[valid & flooded], minlength=ny * nx)
    share = np.where(total > 0, wet / np.maximum(total, 1), 0.0)
    table["flooded_share"] = share.astype(np.float32)
    px_km2 = float(np.mean(ev.cell_area_m2())) / 1e6
    # rates of the points on flooded / dry ground
    r_, c_, ok = ev.pixel(pts.lon, pts.lat)
    on = ok & flooded[r_, c_]
    off = ok & ~flooded[r_, c_] & (ev.data[r_, c_] == 1)
    y, mo = (int(v) for v in month.split("-"))
    end = date(y + (mo == 12), mo % 12 + 1, 1).toordinal() - 1
    rain = coop.chirps_daily(cache, bbox, date(y, mo, 1), date.fromordinal(end), progress=say)
    mm = [d["mean_mm"] for d in rain["days"] if d["mean_mm"] is not None]
    wettest = max(rain["days"], key=lambda d: d["mean_mm"] or -1) if mm else None
    return {
        "month": month, "dry_month": dry,
        "flooded_km2": round(float(flooded.sum()) * px_km2, 2),
        "unobserved_share": round(float(unseen.mean()), 3),
        "people": round(float((people * share).sum())),
        "people_on_sinking_ground": round(float((people * share)[table["class"].to_numpy() >= 1].sum())),
        "points_flooded": int(on.sum()), "points_dry": int(off.sum()),
        "v_vert_flooded_mm_yr": round(float(np.median(v_vert[on])), 2) if on.sum() >= 10 else None,
        "v_vert_dry_mm_yr": round(float(np.median(v_vert[off])), 2) if off.sum() >= 10 else None,
        "rain_month_mm": round(float(sum(mm)), 1) if mm else None,
        "rain_wettest_day": {"date": wettest["date"], "mm": wettest["mean_mm"]} if wettest else None,
        "note": "monthly optical composite: cloud hides part of a monsoon month, short floods may be missed",
    }


def _peak_30min(cache: Path, bbox, month: str, python: str | None, say) -> dict | None:
    """The most intense half hour of the month over the AOI (IMERG late, AOI mean, mm/h); None when IMERG cannot be
    read (no icechunk 2 interpreter, no network): the daily CHIRPS rainfall stands alone then."""
    from geoeyes.opendata import coop
    y, mo = (int(v) for v in month.split("-"))
    last = date(y + (mo == 12), mo % 12 + 1, 1).toordinal() - 1
    try:
        r = coop.imerg_halfhourly(cache, bbox, date(y, mo, 1), date.fromordinal(last), python=python, progress=say)
    except Exception as exc:
        log.warning("IMERG half-hourly rainfall unavailable: %s", exc)
        return None
    steps = [s for s in r["steps"] if s["mean_mm_h"] is not None]
    if not steps:
        return None
    top = max(steps, key=lambda s: s["mean_mm_h"])
    return {"time": top["time"], "mm_h": top["mean_mm_h"], "max_cell_mm_h": top["max_mm_h"]}


def read_summary(folder: Path) -> dict | None:
    f = folder / "exposure.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
