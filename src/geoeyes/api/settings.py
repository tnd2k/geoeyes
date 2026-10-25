"""Project settings for the web app: a form described from the configuration schema, edits written back into
``project.toml`` with tomlkit (comments and layout kept), new projects, and ASF previews for the wizard.

Every write is validated by the core loader first; the previous file is kept as
``.state/project.toml.<timestamp>.bak``.
"""
from __future__ import annotations

import math
import shutil
import tomllib
from datetime import date, datetime, timedelta
from typing import Any

import tomlkit

from geoeyes.config.loader import load, load_dict
from geoeyes.config.schema import ProjectConfig
from geoeyes.core.errors import ConfigError
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

# (section, key, help) shown in the form, in this order; ps.* (StaMPS parameters) are appended from the engine
# defaults
FIELDS: list[tuple[str, str, str]] = [
    ("project", "description", "Free text shown in the tree, the overview and the report"),
    ("project", "method", "psi: persistent scatterers; psds: PS + distributed scatterers (phase linking)"),
    ("aoi", "bbox", "West, south, east, north (WGS84 degrees)"),
    ("acquire", "date_range", "Sentinel-1 acquisitions between these dates are downloaded from ASF"),
    ("acquire", "max_per_month", "Keep the first N acquisitions of each month (0 = all)"),
    ("acquire", "archive", "Folder of raw scenes shared by projects ('' = workspace archive)"),
    ("network", "reference", "Reference date of the stack ('auto' = the most central acquisition)"),
    ("network", "max_perp_m", "Largest perpendicular baseline kept (m)"),
    ("network", "max_temporal_days", "Largest temporal baseline kept (days, 0 = no limit)"),
    ("stack", "dem", "srtm-1 or copernicus-30 (downloaded when missing), a folder of .hgt or a GeoTIFF"),
    ("stack", "esd", "Enhanced spectral diversity (Sentinel-1 azimuth fine coregistration)"),
    ("stack", "multilook", "Range, azimuth looks (1, 1 = full resolution)"),
    ("stack", "incremental", "Keep coregistered dates when the stack is extended (same reference)"),
    ("selection", "da_threshold", "Amplitude dispersion threshold of the PS candidates"),
    ("selection", "robust_da", "Robust amplitude dispersion (median / MAD)"),
    ("selection", "ds_coherence_min", "Minimum coherence of a distributed scatterer"),
    ("selection", "water_mask", "Mask water before the selection"),
    ("phase_linking", "enabled", "Phase linking of distributed scatterers before the point engine"),
    ("phase_linking", "estimator", "Phase linking estimator"),
    ("phase_linking", "shp_test", "Statistically homogeneous pixels: ad = Anderson-Darling, ks = Kolmogorov-Smirnov"),
    ("phase_linking", "half_window", "Half window of the SHP search (rows, columns)"),
    ("phase_linking", "shp_alpha", "Significance level of the SHP test"),
    ("phase_linking", "min_shp", "Minimum number of SHP for a distributed scatterer"),
    ("phase_linking", "ps_da_max", "PS below this amplitude dispersion keep their own SLC (0 = link all)"),
    ("phase_linking", "gaussian_sigma", "Gaussian post-filter of the linked phase (0 = off)"),
    ("atmosphere", "method", "none, era5 (needs ~/.cdsapirc) or gacos"),
    ("atmosphere", "select", "auto: weather correction kept only where it reduces the phase; all: everywhere"),
    ("export", "formats", "GIS formats written for each product"),
    ("report", "copy_to", "Folder the PDF report is also copied to ('' = none)"),
]
SECTION_TITLES = {"project": "Project", "aoi": "Area of interest", "acquire": "Acquisition", "network": "Network",
                  "stack": "Stack", "selection": "Point selection", "phase_linking": "Phase linking",
                  "atmosphere": "Atmosphere", "export": "Export", "report": "Report",
                  "ps": "Point engine (StaMPS parameters)"}
SUGGESTIONS = {("atmosphere", "method"): ["none", "era5", "gacos"], ("stack", "dem"): ["srtm-1", "copernicus-30"],
               ("network", "reference"): ["auto"]}


def _schema() -> dict:
    return ProjectConfig.model_json_schema()


def _resolve(schema: dict, node: dict) -> dict:
    if "$ref" in node:
        return schema["$defs"][node["$ref"].split("/")[-1]]
    return node


def _kind(schema: dict, prop: dict) -> dict:
    """Form widget of a schema property: bool, int, number, string, enum, multi, daterange, pair, bbox."""
    p = _resolve(schema, prop)
    opts = [_resolve(schema, o) for o in p.get("anyOf", [])]
    nullable = any(o.get("type") == "null" for o in opts)
    real = [o for o in opts if o.get("type") != "null"] or [p]
    first = real[0]
    if "enum" in first:
        return {"kind": "enum", "options": first["enum"], "nullable": nullable}
    t = first.get("type")
    if t == "array":
        items = first.get("prefixItems")
        if items and len(items) == 2 and items[0].get("format") == "date":
            return {"kind": "daterange", "nullable": nullable}
        if items and len(items) == 4:
            return {"kind": "bbox", "nullable": nullable}
        if items and len(items) == 2:
            return {"kind": "pair", "nullable": nullable}
        it = _resolve(schema, first.get("items", {}))
        if "enum" in it:
            return {"kind": "multi", "options": it["enum"], "nullable": nullable}
        return {"kind": "list", "nullable": nullable}
    if t == "boolean":
        return {"kind": "bool", "nullable": nullable}
    if t in ("integer", "number"):
        return {"kind": "int" if t == "integer" else "number", "nullable": nullable,
                "min": first.get("minimum", first.get("exclusiveMinimum")), "max": first.get("maximum")}
    return {"kind": "string", "nullable": nullable}


def _ps_kind(v: Any) -> dict | None:
    if isinstance(v, bool):
        return {"kind": "bool", "nullable": False}
    if isinstance(v, int):
        return {"kind": "int", "nullable": False}
    if isinstance(v, float) and math.isfinite(v):
        return {"kind": "number", "nullable": False}
    if isinstance(v, str):
        return {"kind": "enum", "options": ["y", "n"], "nullable": False} if v in ("y", "n") else \
            {"kind": "string", "nullable": False}
    return None


def _json(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (tuple, list)):
        return [_json(x) for x in v]
    if hasattr(v, "value"):                                    # enums
        return v.value
    return v


def _get(cfg, section: str, key: str) -> Any:
    if section == "ps":
        from geoeyes.processing.ps.params import DEFAULTS
        return {**DEFAULTS, **cfg.ps}.get(key)
    return getattr(getattr(cfg, section), key)


def _base(raw: dict) -> ProjectConfig:
    """The configuration a project would have with only its name, method and tracks (preset + defaults)."""
    return load_dict({k: raw[k] for k in ("schema", "project", "tracks") if k in raw})


def describe(project: ProjectLayout) -> dict:
    """Form description: sections → fields with widget, effective value, preset / default value, own flag."""
    from geoeyes.processing.ps.params import DEFAULTS
    text = project.config.read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    cfg = load(project.config)
    base = _base(raw)
    schema = _schema()
    rows = list(FIELDS) + [("ps", k, "") for k, v in DEFAULTS.items() if _ps_kind(v)]
    sections: dict[str, list] = {}
    for section, key, help_ in rows:
        if section == "ps":
            kind = _ps_kind(DEFAULTS[key])
        else:
            sec = _resolve(schema, schema["properties"][section])
            kind = _kind(schema, sec["properties"][key])
        sections.setdefault(section, []).append({
            "key": key, "help": help_, **kind, "suggest": SUGGESTIONS.get((section, key)),
            "value": _json(_get(cfg, section, key)), "default": _json(_get(base, section, key)),
            "own": key in (raw.get(section) or {})})
    return {"sections": [{"name": s, "title": SECTION_TITLES.get(s, s), "fields": f} for s, f in sections.items()],
            "toml": text, "tracks": raw.get("tracks", [])}


def _toml_value(v: Any) -> Any:
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, str) and len(x) == 10 and x[4] == "-":
                try:
                    out.append(date.fromisoformat(x))
                    continue
                except ValueError:
                    pass
            out.append(x)
        return out
    return v


def _write(project: ProjectLayout, text: str) -> None:
    """Validate, back up the current file, write."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML: {exc}") from None
    cfg = load_dict(data)
    if cfg.project.name != project.name:
        raise ConfigError(f"[project] name must stay {project.name!r} (the project folder name)")
    if project.config.exists():
        project.state_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        shutil.copy2(project.config, project.state_dir / f"project.toml.{stamp}.bak")
    tmp = project.config.with_suffix(".toml.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(project.config)


def apply(project: ProjectLayout, changes: dict[str, Any]) -> dict:
    """``{"section.key": value}``; value ``None`` removes the key (back to the preset / default)."""
    doc = tomlkit.parse(project.config.read_text(encoding="utf-8"))
    for path, value in changes.items():
        section, _, key = path.partition(".")
        if section not in SECTION_TITLES or not key:
            raise ConfigError(f"cannot edit {path!r} here")
        if value is None or value == "":
            if section in doc and key in doc[section]:
                del doc[section][key]
            continue
        if section not in doc:
            doc.add(tomlkit.nl())
            doc[section] = tomlkit.table()
        doc[section][key] = _toml_value(value)
    _write(project, tomlkit.dumps(doc))
    return describe(project)


def save_toml(project: ProjectLayout, text: str) -> dict:
    _write(project, text)
    return describe(project)


# ---------------------------------------------------------------- new project
def create(ws: WorkspaceLayout, spec: dict) -> str:
    """New project folder and ``project.toml`` from the wizard; returns the project name."""
    from geoeyes.api import service
    name = str(spec.get("name", "")).strip()
    project = ws.project(name)                                   # validates the name
    if project.config.exists():
        raise ConfigError(f"project {name!r} already exists")
    tr = spec.get("track") or {}
    doc = tomlkit.document()
    doc.add(tomlkit.comment(f"{spec.get('description') or name} -- created from the web app; every parameter not"))
    doc.add(tomlkit.comment("written here comes from the sensor preset and the defaults."))
    doc["schema"] = "geoeyes.project/1"
    doc["project"] = {"name": name, "method": spec.get("method") or "psi",
                      **({"description": spec["description"]} if spec.get("description") else {})}
    if spec.get("bbox"):
        doc["aoi"] = {"bbox": [round(float(v), 5) for v in spec["bbox"]]}
    track = {"sensor": tr.get("sensor", "sentinel1"), "direction": tr.get("direction", "descending")}
    if tr.get("relative_orbit") not in (None, ""):
        track["relative_orbit"] = int(tr["relative_orbit"])
    if tr.get("subswaths"):
        track["subswaths"] = list(tr["subswaths"])
    doc["tracks"] = tomlkit.aot()
    doc["tracks"].append(tomlkit.item(track))
    acq = {}
    if spec.get("date_range"):
        acq["date_range"] = _toml_value(list(spec["date_range"]))
    if spec.get("max_per_month"):
        acq["max_per_month"] = int(spec["max_per_month"])
    if spec.get("archive"):
        acq["archive"] = str(spec["archive"])
    if acq:
        doc["acquire"] = acq
    if spec.get("atmosphere") and spec["atmosphere"] != "none":
        doc["atmosphere"] = {"method": spec["atmosphere"]}
    text = tomlkit.dumps(doc)
    load_dict(tomllib.loads(text))                               # invalid: nothing is created
    project.ensure()
    project.config.write_text(text, encoding="utf-8", newline="\n")
    folder = spec.get("folder")
    tree = service.folders(ws)
    if folder:
        parts = [p for p in str(folder).split("/") if p]

        def put(nodes: list, depth: int) -> list:
            for f in nodes:
                if f["name"] == parts[depth]:
                    if depth == len(parts) - 1:
                        f["projects"] = [p for p in f["projects"] if p != name] + [name]
                    else:
                        f["folders"] = put(f["folders"], depth + 1)
                    return nodes
            nodes.append({"name": parts[depth], "projects": [], "folders": []})
            return put(nodes, depth)

        tree["folders"] = put(tree["folders"], 0)
        tree["projects"] = [p for p in tree["projects"] if p != name]
    service.save_folders(ws, tree)
    return name


# ---------------------------------------------------------------- ASF previews
def asf_tracks(bbox: list[float]) -> list[dict]:
    """Sentinel-1 tracks over an AOI (bursts of the last 24 days): relative orbit, direction, subswaths, coverage."""
    from shapely import wkt
    from shapely.geometry import box
    from shapely.ops import unary_union

    from geoeyes.core.types import BBox
    from geoeyes.sensors.sentinel1.asf import search
    end = date.today()
    refs = search(start=end - timedelta(days=24), end=end, aoi=BBox.from_sequence(bbox))
    aoi = box(*bbox)
    out: dict[str, dict] = {}
    for r in refs:
        t = out.setdefault(r.track_id, {"track_id": r.track_id, "relative_orbit": r.relative_orbit,
                                        "direction": r.direction.value, "subswaths": set(), "foot": [],
                                        "last": r.date})
        t["subswaths"].add(r.subswath)
        t["last"] = max(t["last"], r.date)
        if r.footprint_wkt:
            t["foot"].append(wkt.loads(r.footprint_wkt))
    res = []
    for t in out.values():
        cover = unary_union(t["foot"]).intersection(aoi).area / aoi.area if t["foot"] and aoi.area else None
        res.append({"track_id": t["track_id"], "relative_orbit": t["relative_orbit"], "direction": t["direction"],
                    "subswaths": sorted(t["subswaths"]), "coverage": None if cover is None else round(cover, 3),
                    "last": t["last"].isoformat()})
    return sorted(res, key=lambda x: (-(x["coverage"] or 0), x["relative_orbit"]))


def asf_preview(spec: dict) -> dict:
    """Acquisitions the acquire phase would download for this AOI, track and dates (same code as the phase)."""
    from types import SimpleNamespace

    from geoeyes.controller.phases.acquire import catalogue
    raw = {"project": {"name": "preview", "method": "psi"}, "aoi": {"bbox": spec["bbox"]},
           "tracks": [{"sensor": "sentinel1", "direction": spec["direction"],
                       "relative_orbit": int(spec["relative_orbit"]),
                       **({"subswaths": spec["subswaths"]} if spec.get("subswaths") else {})}],
           "acquire": {"date_range": spec["date_range"], "max_per_month": int(spec.get("max_per_month") or 0)}}
    cfg = load_dict(raw)
    ctx = SimpleNamespace(cfg=cfg, track=cfg.tracks[0], track_id=cfg.tracks[0].track_id, cache={})
    refs = catalogue(ctx)
    dates = sorted({r.date for r in refs})
    months: dict[str, int] = {}
    for d in dates:
        months[d.strftime("%Y-%m")] = months.get(d.strftime("%Y-%m"), 0) + 1
    return {"acquisitions": len(dates), "bursts": len(refs), "gb": round(sum(r.bytes for r in refs) / 1e9, 1),
            "burst_ids": sorted({r.full_burst_id for r in refs}), "dates": [d.isoformat() for d in dates],
            "months": months, "platforms": sorted({r.platform for r in refs})}
