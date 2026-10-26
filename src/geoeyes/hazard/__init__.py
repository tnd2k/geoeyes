"""Ground-motion hazard zoning from InSAR and rainfall (subsidence and slow landslides).

Method, sources and research plan: ``docs/en/research/rainfall-insar-hazard.md``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from geoeyes.hazard.assess import HazardParams, assess, read_summary


def run_hazard(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None) -> dict:
    """Hazard zoning of one product of ``project`` with ``[postprocess.hazard]`` (+ ``overrides``)."""
    from geoeyes.config.settings import load_settings
    params = HazardParams.from_dict({**dict(cfg.postprocess.hazard), **(overrides or {})})
    return assess(project.product(product_id), project.analysis("hazard", product_id), params,
                  rain_cache=ws.cache_dir("rainfall"), dem_cache=ws.cache_dir("dem"), dem_source=cfg.stack.dem,
                  gw_cache=ws.cache_dir("groundwater"), earthdata_token=load_settings().earthdata_token or "",
                  progress=progress)


def hazard_dir(project, product_id: str) -> Path:
    return project.analysis("hazard", product_id)


__all__ = ["HazardParams", "assess", "hazard_dir", "read_summary", "run_hazard"]
