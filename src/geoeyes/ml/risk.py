"""Risk to buildings: hazard × consequence for every Overture building of a product (docs/en/research/
behaviour-and-risk.md §3). Step R6 of the hazard research plan ("from hazard to risk").

* **Hazard H** (0–4, the levels of the zoning). From the building's own persistent scatterers when it has at least
  ``min_points_own`` of them (geoeyes buildings): intensity from its vertical rate, damage potential from its own
  significant tilt β, else from the angular distortion of its cell; otherwise the hazard level of the analysis
  cell that holds it. ``source`` says which.
* **Exposure E** (1–3): gross floor area = footprint × floors, floors from the height (3 m a floor) or, without a
  height, the median of the buildings of the area that have one. A proxy of the people and value inside.
* **Vulnerability V** (1–3): what the structure tolerates. Without the structural type (not in open data) the
  proxies are size and slenderness: long buildings span more differential settlement, tall ones turn a small tilt
  into a large lateral offset (Burland & Wroth 1974; Peduto et al. 2017 fragility curves rise with both).
* **Consequence C** = CONSEQUENCE[E][V], **risk R** = RISK[H][C] (0–4).

Every rule and threshold is a parameter; the classes are screening classes, not a structural assessment.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.risk/1"
LEVELS = ("very low", "low", "moderate", "high", "very high")
CONSEQUENCE = ((1, 1, 2), (1, 2, 3), (2, 3, 3))                   # [E-1][V-1] -> C
RISK = ((0, 0, 1), (0, 1, 1), (1, 2, 2), (2, 3, 4), (3, 4, 4))   # [H][C-1] -> R


@dataclass(frozen=True)
class RiskParams:
    """``[postprocess.risk]`` of project.toml (every key optional)."""

    min_points_own: int = 5                          # persistent scatterers on a building to use its own InSAR
    floor_height_m: float = 3.0
    exposure_breaks_m2: tuple[float, float] = (300.0, 3000.0)      # gross floor area: E1 < 300 ≤ E2 < 3000 ≤ E3
    tall_m: float = 21.0                             # ≥ 7 floors: V3
    long_m: float = 30.0                             # footprint length (√area) ≥ 30 m: V3
    small_m2: float = 60.0                           # small low buildings: V1

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> RiskParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.risk]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for k, v in d.items():
            default = getattr(cls, k)
            out[k] = tuple(float(x) for x in v) if isinstance(default, tuple) else type(default)(v)
        return cls(**out)


def exposure(area_m2: np.ndarray, floors: np.ndarray, p: RiskParams) -> np.ndarray:
    gfa = area_m2 * floors
    return (1 + np.searchsorted(np.asarray(p.exposure_breaks_m2), gfa, side="right")).astype(np.int8)


def vulnerability(area_m2: np.ndarray, height_m: np.ndarray, p: RiskParams) -> np.ndarray:
    tall = np.nan_to_num(height_m, nan=0.0) >= p.tall_m
    long = np.sqrt(area_m2) >= p.long_m
    small = (area_m2 < p.small_m2) & ~(np.nan_to_num(height_m, nan=0.0) > 2 * p.floor_height_m)
    return np.where(tall | long, 3, np.where(small, 1, 2)).astype(np.int8)


def combine(h: np.ndarray, e: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(consequence C, risk R); a hazard below 0 (not assessed) gives R = −1."""
    c = np.asarray(CONSEQUENCE, np.int8)[e - 1, v - 1]
    r = np.asarray(RISK, np.int8)[np.clip(h, 0, 4), c - 1]
    return c, np.where(h >= 0, r, -1).astype(np.int8)


def run(product: Path, out: Path, params: RiskParams, *, hazard_dir: Path, buildings_dir: Path, overture_cache: Path,
        progress=None) -> dict:
    """Risk of every building over ``product`` into ``out``."""
    from geoeyes.hazard import zoning
    from geoeyes.hazard.assess import read_cells
    from geoeyes.hazard.assess import read_summary as hazard_summary
    from geoeyes.hazard.terrain import M_PER_DEG_LAT, M_PER_DEG_LON
    from geoeyes.ml import overture
    say = progress or (lambda m: log.info("%s", m))
    hz = hazard_summary(hazard_dir)
    if hz is None:
        raise DataError(f"no hazard zoning of {product.name}: run geoeyes hazard first")
    cells = read_cells(hazard_dir, hz)
    hp = hz["params"]
    cell_m, lat0 = float(hp["cell_m"]), float(hz["lat0"])
    kxm = M_PER_DEG_LON * math.cos(math.radians(lat0)) / cell_m
    kym = M_PER_DEG_LAT / cell_m

    def key(lon, lat):
        kx = np.floor(np.asarray(lon) * kxm).astype(np.int64)
        return kx * 10_000_019 + np.floor(np.asarray(lat) * kym).astype(np.int64)

    cell_of = pd.Series(np.arange(len(cells)), index=key(cells["lon"], cells["lat"]))
    cell_of = cell_of[~cell_of.index.duplicated()]

    w, s, e, n = hz["bounds"]
    pad = cell_m / M_PER_DEG_LAT
    blds = overture.buildings([w - pad, s - pad, e + pad, n + pad], overture_cache, progress=say)
    if not blds:
        raise DataError("no Overture building over the product")
    t = pd.DataFrame({"id": [str(b["gers"] or b["id"]) for b in blds], "lon": [b["lon"] for b in blds],
                      "lat": [b["lat"] for b in blds], "area_m2": [b["area_m2"] for b in blds],
                      "height_m": [b["height_m"] for b in blds]}).drop_duplicates("id")
    say(f"{len(t)} buildings over the product")
    t["cell"] = cell_of.reindex(key(t["lon"], t["lat"])).to_numpy()
    own = None
    if (buildings_dir / "buildings.parquet").exists():
        own = pd.read_parquet(buildings_dir / "buildings.parquet", columns=["id", "n", "v_vert", "beta_10yr"])
        t = t.merge(own, on="id", how="left")
    else:
        t["n"], t["v_vert"], t["beta_10yr"] = np.nan, np.nan, np.nan
        say("no building analysis (geoeyes buildings): every hazard comes from the cells")

    # ---- hazard: own InSAR where the building carries enough points, else its cell
    ci = t["cell"].to_numpy()
    has_cell = np.isfinite(ci)
    cidx = np.where(has_cell, ci, 0).astype(int)
    col = {c: np.where(has_cell, cells[c].to_numpy()[cidx], np.nan) for c in ("hazard", "secondary", "stable_mm_yr")}
    mode = np.where(has_cell, cells["mode"].to_numpy()[cidx], "")
    h = np.where(has_cell, col["hazard"], -1).astype(np.int8)
    source = np.where(has_cell, "cell", "none").astype(object)
    use_own = (np.nan_to_num(t["n"].to_numpy(), nan=0) >= params.min_points_own) & (mode != "landslide")
    if use_own.any():
        sinking = -t["v_vert"].to_numpy()                          # GeoEyes sign: sinking is negative
        stable = np.maximum(2.0, np.nan_to_num(col["stable_mm_yr"], nan=2.0))
        i_own = zoning.intensity_class(sinking, stable, hp.get("subsidence_breaks", (10.0, 30.0)))
        beta = t["beta_10yr"].to_numpy()
        breaks = hp.get("distortion_breaks", (1 / 500, 1 / 300, 1 / 150))
        s_own = np.where(np.isfinite(beta), zoning.classify(beta, breaks),
                         np.nan_to_num(col["secondary"], nan=0)).astype(np.int8)
        lvl = zoning.hazard_level(i_own, s_own, hp.get("matrix", zoning.DEFAULT_MATRIX))
        h = np.where(use_own & (lvl >= 0), lvl, h).astype(np.int8)
        source = np.where(use_own & (lvl >= 0), "building", source)

    # ---- exposure and vulnerability
    area = t["area_m2"].to_numpy(np.float64)
    height = t["height_m"].to_numpy(np.float64)
    known = np.isfinite(height) & (height > 0)
    floors_known = np.maximum(1, np.round(height / params.floor_height_m))
    median_floors = float(np.median(floors_known[known])) if known.any() else 2.0
    floors = np.where(known, floors_known, median_floors)
    e_cls = exposure(area, floors, params)
    v_cls = vulnerability(area, height, params)
    c_cls, r_cls = combine(h, e_cls, v_cls)

    table = pd.DataFrame({
        "id": t["id"], "lon": t["lon"], "lat": t["lat"], "area_m2": area.astype(np.float32),
        "height_m": height.astype(np.float32), "floors": floors.astype(np.float32), "height_known": known,
        "source": source, "points": np.nan_to_num(t["n"].to_numpy(), nan=0).astype(np.int32),
        "v_vert_mm_yr": t["v_vert"].astype(np.float32), "beta_10yr": t["beta_10yr"].astype(np.float32),
        "hazard": h, "exposure": e_cls, "vulnerability": v_cls, "consequence": c_cls, "risk": r_cls,
    })
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / "risk.parquet", index=False)
    assessed = r_cls >= 0
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "hazard_created": hz.get("created"), "params": asdict(params), "levels": list(LEVELS),
        "consequence_matrix": [list(r) for r in CONSEQUENCE], "risk_matrix": [list(r) for r in RISK],
        "n_buildings": len(table), "assessed": int(assessed.sum()),
        "by_source": {k: int((source == k).sum()) for k in ("building", "cell", "none")},
        "by_risk": {LEVELS[k]: int((r_cls == k).sum()) for k in range(5)},
        "footprint_km2_by_risk": {LEVELS[k]: round(float(area[r_cls == k].sum()) / 1e6, 3) for k in range(5)},
        "height_known_share": round(float(known.mean()), 3), "median_floors_assumed": median_floors,
        "warnings": ([] if own is not None else ["no building analysis: hazards from the cells only"])
        + ([f"heights known for {known.mean():.0%} of the buildings: the others count {median_floors:g} floors"]
           if known.mean() < 0.5 else []),
        "method": "docs/en/research/behaviour-and-risk.md",
    }
    atomic_write_json(out / "risk.json", summary)
    m = Manifest(kind="risk", id=product.name, engine=SCHEMA, inputs=[InputRef("hazard", str(hazard_dir))],
                 params=summary["params"], metrics=summary["by_risk"])
    m.add_outputs(out, ["risk.parquet", "risk.json"])
    m.write(out)
    say("risk: " + ", ".join(f"{k} {v}" for k, v in summary["by_risk"].items()))
    return summary


def read_summary(folder: Path) -> dict | None:
    f = folder / "risk.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
