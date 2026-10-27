"""Machine learning on GeoEyes products (ARCHITECTURE §18).

* ``susceptibility``: statistical and machine-learning models that combine thematic layers (terrain, land cover,
  buildings, soil) to explain where InSAR sees the ground move and map where it could move;
  docs/en/research/ai-susceptibility.md.
* ``buildings``: InSAR velocity and tilt of every Overture building with persistent scatterers on it.
* ``behaviour``: the kind of motion of every hazard cell (stable, steady, seasonal, speeding, slowing, onset, step)
  and the date of a change; ``risk``: hazard × consequence for every Overture building;
  docs/en/research/behaviour-and-risk.md.
* ``lines``: InSAR profiles along dykes, railways and main roads (OpenStreetMap) and their differential settlement;
  ``consolidation``: final and remaining settlement of the cells that settle towards an end;
  docs/en/research/lines-and-consolidation.md.
* ``decompose``: vertical and east-west motion from an ascending and a descending product (or any two look
  directions); ``geology``: soft-soil thickness of the cells against their subsidence;
  docs/en/research/two-geometries-and-soft-soil.md.
* ``forecast``: deformation forecasting of the cells, judged against simple baselines in a rolling-origin backtest;
  docs/en/research/ai-forecasting.md.
"""
from __future__ import annotations

import os
from typing import Any

# joblib (scikit-learn) counts physical cores with wmic, gone from Windows 11: it warns with a traceback each run
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))


def run_susceptibility(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ancillary.geology import GeologyParams
    from geoeyes.config.settings import load_settings
    from geoeyes.ml.susceptibility import SusceptibilityParams, run
    params = SusceptibilityParams.from_dict({**dict(cfg.postprocess.susceptibility), **(overrides or {})})
    geology = {"params": GeologyParams.from_dict(dict(cfg.postprocess.geology)), "project_dir": project.root,
               "cache": ws.cache_dir("geology"), "token": load_settings().earthdata_token}
    return run(project.product(product_id), project.analysis("susceptibility", product_id), params,
               hazard_dir=project.analysis("hazard", product_id), dem_source=cfg.stack.dem,
               dem_cache=ws.cache_dir("dem"), overture_cache=ws.cache_dir("overture"), geology=geology,
               progress=progress)


def run_buildings(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.buildings import analyse
    return analyse(project.product(product_id), project.analysis("buildings", product_id), ws.cache_dir("overture"),
                   progress=progress, **(overrides or {}))


def run_behaviour(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.behaviour import BehaviourParams, run
    params = BehaviourParams.from_dict({**dict(cfg.postprocess.behaviour), **(overrides or {})})
    return run(project.product(product_id), project.analysis("behaviour", product_id), params,
               hazard_dir=project.analysis("hazard", product_id), progress=progress)


def run_risk(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.risk import RiskParams, run
    params = RiskParams.from_dict({**dict(cfg.postprocess.risk), **(overrides or {})})
    return run(project.product(product_id), project.analysis("risk", product_id), params,
               hazard_dir=project.analysis("hazard", product_id),
               buildings_dir=project.analysis("buildings", product_id), overture_cache=ws.cache_dir("overture"),
               progress=progress)


def run_lines(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.lines import LinesParams, run
    params = LinesParams.from_dict({**dict(cfg.postprocess.lines), **(overrides or {})})
    return run(project.product(product_id), project.analysis("lines", product_id), params,
               cache=ws.cache_dir("osm"), progress=progress)


def run_consolidation(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.consolidation import ConsolidationParams, run
    params = ConsolidationParams.from_dict({**dict(cfg.postprocess.consolidation), **(overrides or {})})
    return run(project.product(product_id), project.analysis("consolidation", product_id), params,
               hazard_dir=project.analysis("hazard", product_id), progress=progress)


def run_decompose(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.decompose import DecomposeParams, run
    params = DecomposeParams.from_dict({**dict(cfg.postprocess.decompose), **(overrides or {})})
    return run(project.product(product_id), project.analysis("decompose", product_id), params,
               projects_root=ws.projects, progress=progress)


def run_geology(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ancillary.geology import GeologyParams
    from geoeyes.config.settings import load_settings
    from geoeyes.ml.geology import run
    params = GeologyParams.from_dict({**dict(cfg.postprocess.geology), **(overrides or {})})
    return run(project.product(product_id), project.analysis("geology", product_id), params,
               hazard_dir=project.analysis("hazard", product_id),
               consolidation_dir=project.analysis("consolidation", product_id), project_dir=project.root,
               cache=ws.cache_dir("geology"), token=load_settings().earthdata_token, progress=progress)


def run_forecast(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.forecast import ForecastParams, run
    params = ForecastParams.from_dict({**dict(cfg.postprocess.forecast), **(overrides or {})})
    return run(project.product(product_id), project.analysis("forecast", product_id), params,
               hazard_dir=project.analysis("hazard", product_id), progress=progress)
