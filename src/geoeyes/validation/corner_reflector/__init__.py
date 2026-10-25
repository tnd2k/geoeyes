"""Corner reflector (CR) identification report (port of the legacy ``modules.cr_report``).

From the project's reflector list and its Sentinel-1 bursts in the workspace archive, compute for every
reflector and acquisition:

* the pointing the reflector needs (face azimuth, boresight elevation, base tilt), from the orbit;
* the RCS it should give for the way it was set up (set-up log) -- triangular trihedral model;
* the RCS (dBsm), signal-to-clutter ratio and position measured on the SLC;
* the coherence at the reflector between acquisitions of the same track;

and write ``cr_report.json``, CSV tables, figures and a PDF under
``<project>/validation/corner_reflector/<timestamp>_<track>/``.

Configuration (``project.toml``)::

    [validation.corner_reflector]
    points = "geom/points.csv"       # lon, lat[, name, height (ellipsoidal m), edge_m]; relative to the project
    setup = "geom/cr_setup.csv"      # valid_from, face_azimuth_deg, base_tilt_deg[, name, note] (optional)
    timezone = "Asia/Ho_Chi_Minh"    # of the set-up log
    edge_m = 0.8                     # default inner edge length
    start = ""                       # YYYY-MM-DD; default: the day before the first set-up entry
    end = ""
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


def build_cr_report(cfg, project, workspace, *, tracks=None, pdf: bool = True) -> list[dict]:
    """One report per Sentinel-1 track of the project. Returns the written paths (+ ``summary``) per track."""
    from geoeyes.config.schema import Sensor
    from geoeyes.core.errors import ConfigError, DataError
    from geoeyes.validation.corner_reflector.inputs import DEFAULT_EDGE_M, DEFAULT_TZ, read_setup, read_targets
    from geoeyes.validation.corner_reflector.pipeline import run
    from geoeyes.validation.corner_reflector.report import write_report
    from geoeyes.validation.corner_reflector.s1burst import scenes as find_scenes
    c = dict(cfg.validation.corner_reflector)
    if not c.get("points"):
        raise ConfigError("[validation.corner_reflector] points (reflector CSV) is not set")

    def path(p: str) -> Path:
        return Path(p) if Path(p).is_absolute() else project.root / p

    tz = c.get("timezone") or DEFAULT_TZ
    targets = read_targets(path(c["points"]), float(c.get("edge_m") or DEFAULT_EDGE_M))
    setups = read_setup(path(c["setup"]), tz) if c.get("setup") else []
    start = c.get("start") or ((setups[0].valid_from - timedelta(days=1)).date().isoformat() if setups else "")
    end = c.get("end") or ""
    out = []
    for tr in cfg.tracks:
        if tr.sensor is not Sensor.SENTINEL1 or (tracks and tr.track_id not in tracks):
            continue
        root = Path(cfg.acquire.archive) if cfg.acquire.archive else workspace.archive / "sentinel1" / tr.track_id
        sc = [s for s in find_scenes(root) if (not start or s.date >= str(start)) and (not end or s.date <= str(end))]
        if not sc:
            raise DataError(f"{tr.track_id}: no Sentinel-1 acquisition in {root} between {start or '…'} and "
                            f"{end or '…'}")
        result = run(targets, sc, setups, tz)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        paths = write_report(result, project.root / "validation" / "corner_reflector" / f"{stamp}_{tr.track_id}",
                             cfg.project.name, pdf=pdf)
        obs = result["observations"]
        paths["summary"] = {"track": tr.track_id, "reflectors": len(targets),
                            "acquisitions": len(result["acquisitions"]), "observations": len(obs),
                            "within_tolerance": sum(o.within_tolerance for o in obs)}
        log.info("CR report %s: %d observation(s), %d within tolerance", paths["dir"], len(obs),
                 paths["summary"]["within_tolerance"])
        out.append(paths)
    if not out:
        raise DataError("no Sentinel-1 track in the project: the CR report reads Sentinel-1 bursts")
    return out


__all__ = ["build_cr_report"]
