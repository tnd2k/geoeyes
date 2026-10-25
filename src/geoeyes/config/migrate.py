"""Legacy ``in.json`` + ``control.json`` -> ``project.toml`` (lossless).

The legacy file is first completed with the legacy template (``config/template.json`` of the former
repository, passed as ``template``) the way the old code did, then mapped section by section. Keys with no home
in the new schema are kept under
``[legacy.<section>]``; dropped keys (publishing, organisation — ADR-007/016) are listed in the
returned ``MigrationReport``.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from geoeyes.config.loader import deep_merge
from geoeyes.config.schema import Method, Sensor

ITYPE_SENSOR = {1: Sensor.SENTINEL1, 2: Sensor.TERRASAR_X, 3: Sensor.CAPELLA, 4: Sensor.COSMO_SKYMED}
INSARCORE_METHOD = {"PSI": Method.PSI, "SBAS": Method.SBAS, "PSDS": Method.PSDS, "COMSAR": Method.COMSAR}
DROPPED = {("project", "dbschema"), ("project", "map_id"), ("project", "engine")}
_UNSET = "__unset__"


@dataclass
class MigrationReport:
    dropped: list[str] = field(default_factory=list)
    legacy: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _date(v: str) -> date:
    return datetime.strptime(str(v), "%Y%m%d").date()


def _yn(v) -> bool:
    return str(v).strip().lower() in ("y", "yes", "1", "true")


def _pop(d: dict, key: str, default=None):
    return d.pop(key, default) if isinstance(d, dict) else default


def _clean_unset(d):
    if isinstance(d, dict):
        return {k: _clean_unset(v) for k, v in d.items() if v != _UNSET}
    return d


def complete_legacy(in_json: dict, template: dict | None) -> dict:
    return _clean_unset(deep_merge(template, in_json) if template else copy.deepcopy(in_json))


def migrate(in_json: dict, control: dict | None = None, *, template: dict | None = None,
            name: str | None = None) -> tuple[dict, MigrationReport]:
    """Return (project.toml dict, report)."""
    rep = MigrationReport()
    src = complete_legacy(in_json, template)
    out: dict[str, Any] = {"schema": "geoeyes.project/1"}

    prj = src.pop("project", {})
    itype = int(prj.pop("itype", 1))
    sensor = ITYPE_SENSOR.get(itype, Sensor.SENTINEL1)
    core = str(prj.pop("insarcore", "PSI")).upper()
    method = Method.PS_LITE if sensor is Sensor.CAPELLA else INSARCORE_METHOD.get(core, Method.PSI)
    if sensor is Sensor.CAPELLA and core != "PS_LITE":
        rep.notes.append(f"Capella insarcore {core} -> method ps_lite (ADR-020)")
    pname = (name or str(prj.pop("name", "project"))).lower()
    prj.pop("name", None)
    for k in ("dbschema", "map_id", "engine"):
        if k in prj:
            rep.dropped.append(f"project.{k}")
            prj.pop(k)
    out["project"] = {"name": pname, "method": method.value}
    if prj:
        out.setdefault("legacy", {})["project"] = prj

    # --- search -> aoi, tracks, acquire
    s = src.pop("search", {})
    bbox = s.pop("bbox", None)
    out["aoi"] = {"bbox": list(bbox)} if bbox else {}
    direction = str(s.pop("direction", "") or "").upper()
    frame = s.pop("frame", None)
    frames = (frame if isinstance(frame, list) else [frame, frame]) if frame not in (None, "", []) else [None, None]
    dirs = [direction] if direction in ("ASCENDING", "DESCENDING") else ["DESCENDING", "ASCENDING"]
    snap = src.pop("snap", {})
    sub = str(snap.pop("subswath", "") or "")
    subswaths = [x.strip().upper() for x in sub.replace(";", ",").split(",") if x.strip()]
    tracks = []
    for d in dirs:
        t: dict[str, Any] = {"sensor": sensor.value, "direction": d.lower()}
        f = frames[0] if d == "DESCENDING" else frames[-1]
        if f not in (None, "") and sensor is Sensor.SENTINEL1:
            t["frame"] = int(f)
        if subswaths and sensor is Sensor.SENTINEL1:
            t["subswaths"] = subswaths
        tracks.append(t)
    out["tracks"] = tracks
    acq: dict[str, Any] = {}
    dr = s.pop("download_range", None)
    if dr and len(dr) == 2:
        acq["date_range"] = [_date(dr[0]), _date(dr[1])]
    if "max_date" in s:
        acq["max_per_month"] = int(s.pop("max_date") or 0)
    root = s.pop("imagery_root", "")
    if root:
        acq["archive"] = root
    out["acquire"] = acq
    if s:
        out.setdefault("legacy", {})["search"] = s

    # --- snap -> network, stack
    stamps = src.pop("stamps", {})
    pp = dict(stamps.pop("ps_parms", {}))
    master = snap.pop("master", "")
    net: dict[str, Any] = {"reference": _date(master) if master else "auto",
                           "max_perp_m": float(snap.pop("max_perp", 150.0))}
    sb: dict[str, Any] = {}
    if "synth_redundant_pairs" in pp:
        sb["redundant_pairs"] = _yn(pp.pop("synth_redundant_pairs"))
    if "synth_redundant_pairs_max_days" in pp:
        sb["redundant_max_days"] = int(pp.pop("synth_redundant_pairs_max_days"))
    if "sbas_slave_max_temp_days" in snap:
        sb["max_temporal_days"] = int(snap.pop("sbas_slave_max_temp_days"))
    if sb:
        net["sbas"] = sb
    out["network"] = net
    stack: dict[str, Any] = {"engine": "snap"}
    for old, new, conv in (("reestimate", "reestimate", bool), ("renew", "renew", bool),
                           ("byteswap", "byteswap", int), ("esd_estimate", "esd", bool),
                           ("merge_subswaths_enabled", "merge_subswaths", bool),
                           ("merge_subswaths_max_match_dist_deg", "merge_subswaths_max_match_dist_deg", float)):
        if old in snap:
            stack[new] = conv(snap.pop(old))
    if "process_range" in snap:
        stack["process_range"] = [str(x) for x in snap.pop("process_range") or []]
    robust = snap.pop("robust_da", None)
    if snap:
        stack["options"] = snap               # sensor-specific coreg keys (e.g. Capella master scoring)
    out["stack"] = stack

    # --- phase linking (phase_linking + gaussian_postfilter + nlinsar + tomo + vsar)
    pl_src = src.pop("phase_linking", {})
    tomo = src.pop("tomo", {})
    vsar = src.pop("vsar", {})
    gpf = src.pop("gaussian_postfilter", {})
    nl = src.pop("nlinsar", {})
    pl: dict[str, Any] = {"enabled": bool(pl_src.pop("enabled", False))}
    if "algorithm" in pl_src:
        pl["estimator"] = str(pl_src.pop("algorithm")).lower()
    if "half_win" in pl_src:
        pl["half_window"] = list(pl_src.pop("half_win"))
    for k in ("min_shp", "shp_alpha", "adaptive_coherence_threshold", "tile_size"):
        if k in pl_src:
            pl[k] = pl_src.pop(k)
    if _yn(pl_src.pop("shp_use_tomo", "n")):
        pl["shp_test"] = str(tomo.get("shp_test", "ad")).lower()
    if int(tomo.get("type", 0) or 0) > 0:
        pl["enabled"] = True
        pl["estimator"] = "comsar" if int(tomo.get("unified", 0) or 0) else "psds"
        pl["ministack_size"] = int(tomo.get("ministack_size", 5))
    if gpf.get("enabled"):
        pl["gaussian_sigma"] = float(gpf.get("sigma", 1.5))
    if nl.pop("enabled", False):
        pl["nlinsar"] = nl
    opts = {}
    if pl_src:
        opts["phase_linking"] = pl_src
    if tomo:
        opts["tomo"] = tomo
    if vsar:
        opts["vsar"] = vsar
    if opts:
        pl["options"] = opts
    out["phase_linking"] = pl

    # --- selection
    wm = src.pop("water_mask", {})
    sel: dict[str, Any] = {"da_threshold": float(stamps.pop("da_threshold", 0.4))}
    if robust is not None:
        sel["robust_da"] = bool(robust)
    for k in ("forced_points", "mask"):
        if stamps.get(k):
            sel[k] = stamps.pop(k)
        else:
            stamps.pop(k, None)
    if wm.pop("enabled", False):
        sel["water_mask"] = "static" if wm.get("mask_source") == "static" else "model"
    if wm:
        sel["water_model"] = wm
    out["selection"] = sel

    # --- atmosphere (StaMPS tropo_method codes kept as-is)
    out["atmosphere"] = {"method": str(pp.pop("tropo_method", "none")),
                         "era5": stamps.pop("aps_ecmwf", {}), "gacos": stamps.pop("aps_gacos", {})}

    # --- engine parameters
    if method is not Method.PS_LITE:
        out["ps"] = pp
    elif pp:
        out.setdefault("legacy", {})["ps_parms"] = pp
        rep.notes.append("StaMPS ps_parms kept under [legacy.ps_parms]: Capella uses ps_lite")

    # --- postprocess, validation
    alert = stamps.pop("alert", {})
    out["postprocess"] = {"alerts": alert} if alert else {}
    cr = src.pop("crlink", {})
    out["validation"] = {"gnss": cr} if any(v for k, v in cr.items() if k != "n_rovers") else {}

    for k in ("output_object", "result_folder"):
        if k in stamps:
            out.setdefault("legacy", {}).setdefault("stamps", {})[k] = stamps.pop(k)
    if stamps:
        out.setdefault("legacy", {}).setdefault("stamps", {}).update(stamps)

    # --- overrides
    ov = src.pop("subswath_overrides", {}) or {}
    if ov:
        out["overrides"] = {k.upper(): _override(v) for k, v in ov.items()}

    # --- control.json -> pipeline
    if control:
        disabled = []
        if not control.get("water_mask_run", False):
            disabled.append("water_mask")
        if not control.get("crlink_run", False):
            disabled.append("validate")
        out["pipeline"] = {"disabled": disabled}
        out.setdefault("legacy", {})["control"] = control
        rep.notes.append("control.json manager_run flags are resume hints for the old runner; the "
                         "controller decides from artifacts (kept under [legacy.control])")

    # anything left at top level (e.g. a stray max_topo_err written by old exporters)
    for k, v in src.items():
        out.setdefault("legacy", {})[k] = v
    rep.legacy = sorted(out.get("legacy", {}))
    return out, rep


def _override(v: dict) -> dict:
    """Legacy subswath override ({"stamps": {...}}) -> new sections."""
    o: dict[str, Any] = {}
    st = dict(v.get("stamps", {}))
    if "ps_parms" in st:
        o["ps"] = st.pop("ps_parms")
    if "da_threshold" in st:
        o["selection"] = {"da_threshold": st.pop("da_threshold")}
    if "alert" in st:
        o["postprocess"] = {"alerts": st.pop("alert")}
    if st:
        o["legacy"] = {"stamps": st}
    return o


def migrate_files(control_dir: str | Path, template: str | Path | None = None) -> tuple[dict, MigrationReport]:
    control_dir = Path(control_dir)
    in_json = json.loads((control_dir / "in.json").read_text(encoding="utf-8"))
    ctl_path = control_dir / "control.json"
    control = json.loads(ctl_path.read_text(encoding="utf-8")) if ctl_path.exists() else None
    tpl = json.loads(Path(template).read_text(encoding="utf-8")) if template else None
    return migrate(in_json, control, template=tpl, name=control_dir.name)
