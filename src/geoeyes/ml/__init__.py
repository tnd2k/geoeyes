"""Machine learning on GeoEyes products (ARCHITECTURE §18).

* ``susceptibility``: statistical and machine-learning models that combine thematic layers (terrain, land cover,
  buildings, soil) to explain where InSAR sees the ground move and map where it could move;
  docs/en/research/ai-susceptibility.md.
* ``buildings``: InSAR velocity and tilt of every Overture building with persistent scatterers on it.
* ``forecast``: deformation forecasting of the cells, judged against simple baselines in a rolling-origin backtest;
  docs/en/research/ai-forecasting.md.
"""
from __future__ import annotations

import os
from typing import Any

# joblib (scikit-learn) counts physical cores with wmic, gone from Windows 11: it warns with a traceback each run
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))


def run_susceptibility(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.susceptibility import SusceptibilityParams, run
    params = SusceptibilityParams.from_dict({**dict(cfg.postprocess.susceptibility), **(overrides or {})})
    return run(project.product(product_id), project.analysis("susceptibility", product_id), params,
               hazard_dir=project.analysis("hazard", product_id), dem_source=cfg.stack.dem,
               dem_cache=ws.cache_dir("dem"), overture_cache=ws.cache_dir("overture"), progress=progress)


def run_buildings(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.buildings import analyse
    return analyse(project.product(product_id), project.analysis("buildings", product_id), ws.cache_dir("overture"),
                   progress=progress, **(overrides or {}))


def run_forecast(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None):
    from geoeyes.ml.forecast import ForecastParams, run
    params = ForecastParams.from_dict({**dict(cfg.postprocess.forecast), **(overrides or {})})
    return run(project.product(product_id), project.analysis("forecast", product_id), params,
               hazard_dir=project.analysis("hazard", product_id), progress=progress)
