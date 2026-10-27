"""InSAR along linear infrastructure: dykes, railways and main roads from OpenStreetMap (docs/en/research/
lines-and-consolidation.md §2).

1. The lines: OSM ways over the product (Overpass API, cached): ``man_made=dyke`` or a road named "Đê …" (dykes,
   e.g. the Red River dykes of Hanoi, mapped as streets), ``embankment=yes`` roads, ``railway=rail`` and
   motorway / trunk / primary roads. Ways of the same kind and name that touch are chained into one line.
2. Stations every ``step_m`` along each line; at each, the median vertical rate (v_LOS / l_u, GeoEyes sign) of the
   persistent scatterers within ``buffer_m``, when there are at least ``min_points``.
3. Differential settlement along the line: between stations ``span_m`` apart, β = |Δv|·T / L over the horizon T,
   compared with the damage limits of the zoning (1/500, 1/300, 1/150). For dykes, the crest lost in T years.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json

log = logging.getLogger(__name__)

SCHEMA = "geoeyes.lines/1"
OVERPASS = "https://overpass-api.de/api/interpreter"
KINDS = ("dyke", "railway", "embankment", "road")
M_LAT = 110_540.0
M_LON = 111_320.0


@dataclass(frozen=True)
class LinesParams:
    """``[postprocess.lines]`` of project.toml (every key optional)."""

    step_m: float = 50.0              # station spacing
    buffer_m: float = 30.0            # persistent scatterers within this distance of the line
    min_points: int = 3
    span_m: float = 100.0             # differential settlement between stations this far apart
    horizon_yr: float = 10.0
    distortion_breaks: tuple[float, float, float] = (1 / 500, 1 / 300, 1 / 150)
    roads: bool = True                # main roads too (dykes, railways and embankments always)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> LinesParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[postprocess.lines]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for k, v in d.items():
            default = getattr(cls, k)
            out[k] = tuple(float(x) for x in v) if isinstance(default, tuple) else type(default)(v)
        return cls(**out)


def overpass_ways(bbox: list[float], cache: Path, roads: bool, progress=None) -> list[dict]:
    """OSM ways of linear infrastructure over ``bbox`` (w, s, e, n), with tags and geometry; cached per bbox."""
    w, s, e, n = bbox
    box = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    road = f'way["highway"~"^(motorway|trunk|primary)$"]{box};' if roads else ""
    query = (f'[out:json][timeout:180];(way["man_made"="dyke"]{box};way["highway"]["name"~"^Đê "]{box};'
             f'way["embankment"="yes"]["highway"]{box};way["railway"="rail"]{box};{road});out tags geom;')
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"overpass_{hashlib.sha1(query.encode()).hexdigest()[:16]}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    if progress:
        progress("lines: OpenStreetMap ways from the Overpass API (a minute the first time)")
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers={"User-Agent": "GeoEyes (InSAR analysis)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                ways = [el for el in json.loads(r.read())["elements"] if el.get("type") == "way" and el.get("geometry")]
            break
        except OSError as exc:                     # Overpass sheds load with 429 / 504: wait and retry
            if attempt == 2:
                raise DataError(f"Overpass API unavailable: {exc}") from exc
            time.sleep(20 * (attempt + 1))
    f.write_text(json.dumps(ways), encoding="utf-8")
    return ways


def _kind(tags: dict) -> str:
    if tags.get("man_made") == "dyke" or str(tags.get("name", "")).startswith("Đê "):
        return "dyke"
    if tags.get("railway") == "rail":
        return "railway"
    if tags.get("embankment") == "yes":
        return "embankment"
    return "road"


def chain(ways: list[dict]) -> list[dict]:
    """Ways of the same kind and name that share an end node chained into lines (greedy, longest first)."""
    groups: dict[tuple, list[list[tuple[float, float]]]] = {}
    for w in ways:
        tags = w.get("tags", {})
        name = tags.get("name") or tags.get("ref") or f"way {w['id']}"
        coords = [(p["lon"], p["lat"]) for p in w["geometry"]]
        if len(coords) >= 2:
            groups.setdefault((_kind(tags), name), []).append(coords)
    lines = []
    for (kind, name), parts in groups.items():
        parts = [list(p) for p in parts]
        while parts:
            line = parts.pop(0)
            grown = True
            while grown:
                grown = False
                for i, p in enumerate(parts):
                    if p[0] == line[-1]:
                        line += p[1:]
                    elif p[-1] == line[-1]:
                        line += p[::-1][1:]
                    elif p[-1] == line[0]:
                        line = p[:-1] + line
                    elif p[0] == line[0]:
                        line = p[::-1][:-1] + line
                    else:
                        continue
                    parts.pop(i)
                    grown = True
                    break
            lines.append({"kind": kind, "name": name, "coords": np.array(line)})
    return lines


def stations(coords: np.ndarray, step_m: float, lat0: float) -> tuple[np.ndarray, np.ndarray]:
    """(chainage m, lon/lat) of points every ``step_m`` along a polyline."""
    kx = M_LON * math.cos(math.radians(lat0))
    xy = np.column_stack([coords[:, 0] * kx, coords[:, 1] * M_LAT])
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] < step_m:
        return np.zeros(0), np.zeros((0, 2))
    ch = np.arange(0.0, cum[-1] + 1e-6, step_m)
    lon = np.interp(ch, cum, coords[:, 0])
    lat = np.interp(ch, cum, coords[:, 1])
    return ch, np.column_stack([lon, lat])


def run(product: Path, out: Path, params: LinesParams, *, cache: Path, progress=None) -> dict:
    """Profiles of the linear infrastructure over ``product`` into ``out``."""
    from scipy.spatial import cKDTree

    from geoeyes.hazard import zoning
    say = progress or (lambda m: log.info("%s", m))
    pts = pq.read_table(product / "points.parquet", columns=["lon", "lat", "vel_los_mm_yr", "los_u"]).to_pandas()
    if pts.empty:
        raise DataError(f"{product.name}: no points")
    w, s, e, n = pts.lon.min(), pts.lat.min(), pts.lon.max(), pts.lat.max()
    lat0 = float(np.median(pts.lat))
    kx = M_LON * math.cos(math.radians(lat0))
    v = pts.vel_los_mm_yr.to_numpy(np.float64) / np.clip(pts.los_u.to_numpy(np.float64), 0.2, None)
    tree = cKDTree(np.column_stack([pts.lon.to_numpy() * kx, pts.lat.to_numpy() * M_LAT]))
    ways = overpass_ways([w, s, e, n], cache, params.roads, say)
    lines = chain(ways)
    say(f"{len(ways)} OSM ways -> {len(lines)} lines")
    k = max(1, round(params.span_m / params.step_m))
    rows, lrows = [], []
    for li, ln in enumerate(lines):
        ch, ll = stations(ln["coords"], params.step_m, lat0)
        if not len(ch):
            continue
        near = tree.query_ball_point(np.column_stack([ll[:, 0] * kx, ll[:, 1] * M_LAT]), r=params.buffer_m)
        cnt = np.array([len(i) for i in near])
        vv = np.array([np.median(v[i]) if len(i) >= params.min_points else np.nan for i in near])
        beta = np.full(len(ch), np.nan)
        if len(ch) > k:
            dv = np.abs(vv[k:] - vv[:-k])
            beta[k:] = dv * params.horizon_yr / 1000.0 / (ch[k:] - ch[:-k])
        cls = zoning.classify(beta, params.distortion_breaks)
        rows.append(pd.DataFrame({"line": np.int32(li), "chainage_m": ch.astype(np.float32), "lon": ll[:, 0],
                                  "lat": ll[:, 1], "n_points": cnt.astype(np.int32),
                                  "v_vert_mm_yr": vv.astype(np.float32), "beta": beta.astype(np.float32),
                                  "beta_class": cls}))
        covered = np.isfinite(vv)
        lrows.append({"line": li, "kind": ln["kind"], "name": ln["name"], "length_m": float(ch[-1]),
                      "stations": int(len(ch)), "covered_share": round(float(covered.mean()), 3),
                      "v_min_mm_yr": float(np.nanmin(vv)) if covered.any() else np.nan,
                      "v_median_mm_yr": float(np.nanmedian(vv)) if covered.any() else np.nan,
                      "beta_max": float(np.nanmax(beta)) if np.isfinite(beta).any() else np.nan,
                      "flagged": int((cls >= 1).sum()),
                      # crest (or track) lowered over the horizon, at the fastest-sinking station
                      "loss_mm": float(max(0.0, -np.nanmin(vv)) * params.horizon_yr) if covered.any() else np.nan})
    if not rows:
        raise DataError("no OSM line long enough over the product")
    st = pd.concat(rows, ignore_index=True)
    lt = pd.DataFrame(lrows)
    out.mkdir(parents=True, exist_ok=True)
    st.to_parquet(out / "stations.parquet", index=False)
    lt.to_parquet(out / "lines.parquet", index=False)
    hot = lt[lt.flagged > 0].sort_values("beta_max", ascending=False).head(20)
    summary = {
        "schema": SCHEMA, "product_id": product.name, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": asdict(params), "kinds": list(KINDS), "n_lines": len(lt), "n_stations": len(st),
        "by_kind": {kd: _by_kind(lt, st, kd) for kd in KINDS},
        "hotspots": [{"line": int(r.line), "kind": r.kind, "name": r.name, "beta_max": round(float(r.beta_max), 5),
                      "v_min_mm_yr": round(float(r.v_min_mm_yr), 1), "flagged": int(r.flagged)}
                     for r in hot.itertuples()],
        "sign": "negative = sinking", "source": "© OpenStreetMap contributors (ODbL)",
        "method": "docs/en/research/lines-and-consolidation.md",
    }
    atomic_write_json(out / "lines.json", summary)
    m = Manifest(kind="lines", id=product.name, engine=SCHEMA, inputs=[InputRef("product", str(product))],
                 params=summary["params"], metrics={"lines": len(lt), "stations": len(st)})
    m.add_outputs(out, ["stations.parquet", "lines.parquet", "lines.json"])
    m.write(out)
    say(f"{len(lt)} lines, {len(st)} stations, {int((st.beta_class >= 1).sum())} stations beyond 1/500")
    return summary


def _by_kind(lt: pd.DataFrame, st: pd.DataFrame, kind: str) -> dict:
    sel = lt.kind == kind
    on = st.line.isin(lt.line[sel])
    return {"lines": int(sel.sum()), "km": round(float(lt.length_m[sel].sum()) / 1000, 1),
            "covered_share": round(float(st.v_vert_mm_yr[on].notna().mean()), 3) if sel.any() else None,
            "flagged_stations": int(st.beta_class[on].ge(1).sum())}


def read_summary(folder: Path) -> dict | None:
    f = folder / "lines.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
