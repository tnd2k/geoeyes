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
    ("sbas", "looks_az", "Azimuth looks of the SBAS grid (Sentinel-1: 1 look ≈ 14 m)"),
    ("sbas", "looks_rg", "Range looks of the SBAS grid (Sentinel-1: 1 look ≈ 2.3 m slant, ≈ 3.7 m ground)"),
    ("sbas", "reference", "Stable reference point (lon, lat); empty = the most coherent 10 % of pixels"),
    ("sbas", "source", "auto: phase-linked SLC when phase linking is on; slc or linked to force one"),
    ("sbas", "n_nearest", "Pairs per date with the next N dates (when max_temporal_days = 0)"),
    ("sbas", "min_pair_coherence", "A pixel of a pair below this coherence has no value in that pair"),
    ("sbas", "min_pair_fraction", "A pixel needs a value in this share of the pairs"),
    ("sbas", "min_mean_coherence", "Output mask: mean coherence of the pairs"),
    ("sbas", "min_temporal_coherence", "Output mask: temporal coherence of the inversion"),
    ("sbas", "troposphere", "Per pair, remove the phase linear in height (can absorb a bowl lower than the "
                            "reference)"),
    ("sbas", "goldstein_alpha", "Goldstein filter strength before unwrapping (0 = off)"),
    ("atmosphere", "method", "Weather-model APS for step 7: none, era5 (needs ~/.cdsapirc), cerra or gacos"),
    ("atmosphere", "select", "auto: weather correction kept only where it reduces the phase; all: everywhere"),
    ("export", "formats", "GIS formats written for each product"),
    ("report", "copy_to", "Folder the PDF report is also copied to ('' = none)"),
]
# titles of the TOML sections, numbered by the pipeline phase that reads them (the form shows them in that order)
SECTION_TITLES = {"project": "Project", "aoi": "Area of interest", "acquire": "1 · Acquisition",
                  "network": "2 · Stack: interferogram network", "stack": "2 · Stack: coregistration",
                  "phase_linking": "3 · Phase linking (distributed scatterers)",
                  "selection": "4 · PS step 1 · candidates", "atmosphere": "4 · PS step 7 · weather-model atmosphere",
                  "sbas": "4 · SBAS (in place of PS when method = sbas)", "export": "5 · Export",
                  "report": "6 · Report",
                  "ps": "4 · Point engine (StaMPS parameters)"}
# the [ps] table in groups, by StaMPS step: (form id, title, keys). Keys not listed land in the last group.
PS_GROUPS: list[tuple[str, str, list[str]]] = [
    ("ps-gamma", "4 · PS step 2 · temporal coherence and DEM error",
     ["max_topo_err", "filter_grid_size", "filter_weighting", "clap_win", "clap_low_pass_wavelength", "clap_alpha",
      "clap_beta", "gamma_change_convergence", "gamma_max_iterations", "dem_error_ambiguity",
      "dem_error_amb_auto_threshold", "dem_error_amb_q_reject", "dem_error_amb_q_ok", "dem_error_spatial_lambda",
      "dem_error_spatial_iters"]),
    ("ps-select", "4 · PS step 3 · point selection",
     ["select_method", "percent_rand", "density_rand", "gamma_min_threshold", "gamma_stdev_reject",
      "select_nr_scaling", "slc_osf", "reest_smoothing_flag"]),
    ("ps-weed", "4 · PS step 4 · weeding",
     ["weed_time_win", "weed_standard_dev", "weed_zero_elevation", "weed_neighbours", "weed_adjacent_keep_per_group",
      "weed_noisy_check"]),
    ("ps-ref", "4 · PS step 5 · reference area", ["ref_centre_lonlat", "ref_radius", "ref_auto"]),
    ("ps-unwrap", "4 · PS step 6 · unwrapping",
     ["unwrap_patch_phase", "unwrap_grid_size", "unwrap_prefilter_flag", "unwrap_grid_filter",
      "unwrap_grid_filter_sigma", "unwrap_grid_filter_unit", "unwrap_gold_n_win", "unwrap_gold_alpha",
      "unwrap_gold_coh_floor", "unwrap_time_win", "unwrap_la_error_flag", "unwrap_edge_velocity",
      "unwrap_max_edge_velocity", "unwrap_model_cycles", "unwrap_ps_rate", "unwrap_ps_rate_max_arc",
      "unwrap_ps_rate_min_ifg", "unwrap_irls_iter", "unwrap_irls_target_rms", "unwrap_irls_epsilon",
      "unwrap_align_constant"]),
    ("ps-scla", "4 · PS step 7 · DEM error, orbit ramps and atmosphere",
     ["subtr_tropo", "scla_deramp", "ramp_auto_allow_planar"]),
    ("ps-scn", "4 · PS step 8 · spatially correlated noise (SCN)", ["scn_time_win", "scn_wavelength", "scn_time_fit"]),
    ("ps-misc", "4 · PS · memory and compatibility",
     ["topofit_chunk_pixels", "ps_select_smooth_chunk_pixels", "weed_noise_ifg_chunk", "legacy_quirks"]),
]
# the order of the form: the pipeline; "@<id>" = a [ps] group
ORDER = ["project", "aoi", "acquire", "network", "stack", "phase_linking", "selection", "@ps-gamma", "@ps-select",
         "@ps-weed", "@ps-ref", "@ps-unwrap", "@ps-scla", "atmosphere", "@ps-scn", "@ps-misc", "sbas", "export",
         "report"]
SUGGESTIONS = {("atmosphere", "method"): ["none", "era5", "cerra", "gacos"],
               ("stack", "dem"): ["srtm-1", "copernicus-30"], ("network", "reference"): ["auto"],
               ("ps", "max_topo_err"): ["auto", "auto_master"], ("ps", "unwrap_time_win"): ["auto"],
               ("ps", "unwrap_grid_filter_sigma"): ["auto", "cells"], ("ps", "ref_radius"): ["inf"]}
# [ps] keys that take a number or one of these words (set from the data when the engine runs)
PS_WORDS = {"max_topo_err": {"auto", "auto_master"}, "unwrap_time_win": {"auto"},
            "unwrap_grid_filter_sigma": {"auto", "cells"}, "ref_radius": {"inf"}}
# [ps] keys with a fixed set of values (the form offers all of them, not only y / n)
PS_OPTIONS = {"scla_deramp": ["n", "y", "auto"], "unwrap_ps_rate": ["auto", "y", "n"],
              "unwrap_grid_filter": ["gaussian", "goldstein", "none"], "select_method": ["PERCENT", "DENSITY"],
              "scn_time_fit": ["linear", "mean"], "select_nr_scaling": ["low_coherence", "population"],
              "filter_weighting": ["P-square", "SNR"]}
PS_HELP = {
    "max_topo_err": "Largest DEM error searched (m); auto = median height of ambiguity / 4 (baselines about their "
                    "median); auto_master = the same about the master (legacy CSK / ICEYE)",
    "filter_grid_size": "Grid cell (m) of the adaptive phase filter that estimates the neighbourhood phase",
    "filter_weighting": "Weighting of the PS in that filter: P-square (coherence) or SNR",
    "clap_win": "Window (grid cells) of the CLAP adaptive filter",
    "clap_low_pass_wavelength": "Low-pass wavelength (m) of the CLAP filter",
    "clap_alpha": "CLAP: weight of the adaptive (spectral) part",
    "clap_beta": "CLAP: exponent of the spectral weighting",
    "gamma_change_convergence": "Stop iterating when the mean temporal coherence changes less than this",
    "gamma_max_iterations": "Most iterations of the coherence estimation",
    "dem_error_ambiguity": "y: score the DEM-error fit for ambiguity and regularise it spatially (legacy CSK)",
    "dem_error_amb_auto_threshold": "Ambiguity thresholds from the data (with dem_error_ambiguity)",
    "dem_error_amb_q_reject": "Ambiguity score below which the DEM error is rejected",
    "dem_error_amb_q_ok": "Ambiguity score above which the DEM error is trusted",
    "dem_error_spatial_lambda": "Weight of the spatial regularisation of the DEM error",
    "dem_error_spatial_iters": "Iterations of the spatial regularisation",
    "select_method": "PERCENT: share of random phase allowed; DENSITY: random points per km²",
    "percent_rand": "PERCENT: % of the selected points allowed to be random phase",
    "density_rand": "DENSITY: random-phase points per km² allowed",
    "gamma_min_threshold": "Lowest coherence threshold, whatever the amplitude dispersion",
    "gamma_stdev_reject": "Drop points whose coherence varies more than this between iterations (0 = off)",
    "select_nr_scaling": "How the random-phase histogram is scaled: low_coherence or population (legacy CSK)",
    "slc_osf": "SLC oversampling factor (1 = none)",
    "reest_smoothing_flag": "Re-estimate the coherence of the selected points with their neighbourhood phase",
    "weed_time_win": "Time window (days) of the smoothing used to judge the phase noise of a point",
    "weed_standard_dev": "Drop points whose phase noise (rad) against their neighbours is above this",
    "weed_zero_elevation": "Drop points at zero height (sea, DEM voids)",
    "weed_neighbours": "Of adjacent pixels keep only the best one",
    "weed_adjacent_keep_per_group": "Points kept per group of adjacent pixels",
    "weed_noisy_check": "Drop points that are noisy against their neighbours",
    "ref_centre_lonlat": "Centre (lon, lat) of the reference area; 0, 0 = no area (all points, or ref_auto)",
    "ref_radius": "Radius (m) of the reference area around that centre; inf = all points",
    "ref_auto": "y: reference = the stable periphery of the scene (when no centre is given)",
    "unwrap_patch_phase": "n: the grid unwraps the phase of each point (StaMPS default); y: the smoother patch "
                          "phase, then each point's residual (legacy)",
    "unwrap_grid_size": "Cell (m) of the unwrapping grid (10 m usual; 50 m HCMC)",
    "unwrap_prefilter_flag": "Filter the grid phase before unwrapping",
    "unwrap_grid_filter": "Grid prefilter: gaussian, goldstein (coherence-adaptive) or none",
    "unwrap_grid_filter_sigma": "σ of the Gaussian prefilter (m); auto = (unwrap_gold_n_win / 8) × 10 m, the same "
                                "at any grid size; cells = the legacy σ in cells (grows with the grid)",
    "unwrap_grid_filter_unit": "y: filter the unit phasor of each cell (a cell of many points no longer outweighs "
                               "its neighbours)",
    "unwrap_gold_n_win": "Window (cells) of the Goldstein filter; also sets the Gaussian σ in auto",
    "unwrap_gold_alpha": "Strength of the Goldstein filter (0-1)",
    "unwrap_gold_coh_floor": "Coherence below which the Goldstein filter acts at full strength",
    "unwrap_time_win": "Time window (days) of the space-time unwrapping; auto = a quarter of the data span "
                       "(at least 4 sampling intervals, 60-730)",
    "unwrap_la_error_flag": "Estimate the look-angle (DEM) error in the space-time unwrapping",
    "unwrap_edge_velocity": "Unwrap each grid edge in time by its linear rate first (keeps fast motion)",
    "unwrap_max_edge_velocity": "Largest rate searched for an edge (mm/yr, line of sight)",
    "unwrap_model_cycles": "The IRLS takes the cycle count of each grid step from the edge model",
    "unwrap_ps_rate": "Linear rate of every point from the point network, removed before the grid and added back "
                      "(a road faster than its cell keeps its cycles); auto = with >= unwrap_ps_rate_min_ifg "
                      "interferograms and a reliable network",
    "unwrap_ps_rate_max_arc": "Longest arc (m) between two points of that network",
    "unwrap_ps_rate_min_ifg": "Fewest interferograms for unwrap_ps_rate = auto",
    "unwrap_irls_iter": "Most iterations of the IRLS spatial unwrapping",
    "unwrap_irls_target_rms": "IRLS stops below this residual (rad)",
    "unwrap_irls_epsilon": "IRLS weight floor",
    "unwrap_align_constant": "Align the IRLS constant before snapping to the wrapped phase (avoids one-cycle region "
                             "slips near ±π)",
    "subtr_tropo": "Remove the atmosphere (APS) from the velocity: linear in height, or the weather model of "
                   "[atmosphere]; n on flat deltas, where it can absorb subsidence (v-do)",
    "scla_deramp": "Orbit ramps: n = keep, y = remove a plane per interferogram, auto = remove the part that changes "
                   "between dates",
    "ramp_auto_allow_planar": "auto may also remove a steady planar trend without a stable area",
    "scn_time_win": "Time window (days) of the SCN temporal filter (step 8)",
    "scn_wavelength": "Spatial wavelength (m) of the SCN filter",
    "scn_time_fit": "SCN temporal low-pass: linear (keeps the trend) or mean (StaMPS)",
    "topofit_chunk_pixels": "Points per block in step 2 (memory)",
    "ps_select_smooth_chunk_pixels": "Points per block in step 3 (memory)",
    "weed_noise_ifg_chunk": "Interferograms per block in step 4 (memory)",
    "legacy_quirks": "y: reproduce the legacy engine with its bugs (parity tests only)",
}


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


def _ps_kind(v: Any, key: str = "") -> dict | None:
    if key in PS_WORDS:
        return {"kind": "string", "nullable": False}
    if key in PS_OPTIONS:
        return {"kind": "enum", "options": PS_OPTIONS[key], "nullable": False}
    if key == "ref_centre_lonlat":
        return {"kind": "pair", "nullable": False}
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


def _safe(v: Any) -> Any:
    """JSON for the browser: infinite numbers as text."""
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v]
    return v


def _close(a: Any, b: Any) -> bool:
    try:
        return math.isclose(float(a), float(b))
    except (TypeError, ValueError):
        return False


def _used(project: ProjectLayout) -> dict[str, list[dict]]:
    """Per [ps] key, the value each track's last ps run used, when it differs from the configured one or was set
    from the data ("auto")."""
    import json

    from geoeyes.report.methods import effective_ps
    out: dict[str, list[dict]] = {}
    for f in sorted((project.root / "ps_runs").glob("*/params.json")):
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if "table" not in snap:                                  # ps_lite
            continue
        eff, resolved = effective_ps(snap), snap.get("resolved") or {}
        for k, v in eff.items():
            out.setdefault(k, []).append({"track": f.parent.name, "value": _json(_safe(v)),
                                          "auto": k in resolved})
    return out


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
    rows = list(FIELDS) + [("ps", k, PS_HELP.get(k, "")) for k, v in DEFAULTS.items() if _ps_kind(v, k)]
    used = _used(project)
    sections: dict[str, list] = {}
    for section, key, help_ in rows:
        if section == "ps":
            kind = _ps_kind(DEFAULTS[key], key)
        else:
            sec = _resolve(schema, schema["properties"][section])
            kind = _kind(schema, sec["properties"][key])
        value = _json(_safe(_get(cfg, section, key)))
        runs = []
        if section == "ps":
            for u in used.get(key, []):
                auto = u["auto"] or str(value).lower() == "auto"
                if auto or (str(u["value"]) != str(value) and not _close(u["value"], value)):
                    runs.append({**u, "auto": auto})
        sections.setdefault(section, []).append({
            "key": key, "help": help_, **kind, "suggest": SUGGESTIONS.get((section, key)),
            "value": value, "default": _json(_safe(_get(base, section, key))),
            "own": key in (raw.get(section) or {}), "used": runs or None})
    return {"sections": _ordered(sections), "toml": text, "tracks": raw.get("tracks", [])}


def _ordered(sections: dict[str, list]) -> list[dict]:
    """The form's sections in the pipeline order (``ORDER``), [ps] split into its StaMPS-step groups; ``name`` is
    the TOML section the fields are written to, ``id`` the form's own key."""
    ps = {f["key"]: f for f in sections.get("ps", [])}
    listed = {k for _, _, keys in PS_GROUPS for k in keys}
    out = []
    for item in ORDER:
        if item.startswith("@"):
            gid = item[1:]
            title, keys = next((t, k) for i, t, k in PS_GROUPS if i == gid)
            fields = [ps[k] for k in keys if k in ps]
            if gid == PS_GROUPS[-1][0]:                           # keys no group lists (new engine parameters)
                fields += [f for k, f in ps.items() if k not in listed]
            if fields:
                out.append({"name": "ps", "id": gid, "title": title, "fields": fields})
        elif item in sections:
            out.append({"name": item, "id": item, "title": SECTION_TITLES.get(item, item), "fields": sections[item]})
    seen = {s["name"] for s in out}
    out += [{"name": s, "id": s, "title": SECTION_TITLES.get(s, s), "fields": f}
            for s, f in sections.items() if s not in seen]
    return out


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
        if section == "ps" and key in PS_WORDS and isinstance(value, str):
            words = PS_WORDS[key]
            if value.strip().lower() in words:
                value = value.strip().lower()
                if value == "inf":
                    value = float("inf")
            else:
                try:
                    value = float(value)
                except ValueError:
                    raise ConfigError(f"[ps] {key}: a number or one of {', '.join(sorted(words))}, "
                                      f"not {value!r}") from None
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
    if spec.get("opendata"):
        acq["opendata"] = str(spec["opendata"])
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
