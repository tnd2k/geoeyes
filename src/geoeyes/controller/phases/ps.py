"""Phase ``ps``: the point engine on a StackStore, ``ps`` (StaMPS-type, ``[ps]`` + ``[selection]``) or ``ps_lite``
(``[ps_lite]``), on the phase-linked SLC when ``[phase_linking]`` is enabled."""
from __future__ import annotations

from pathlib import Path

from geoeyes.config.schema import Method
from geoeyes.controller.phases import phase_linking
from geoeyes.core.errors import PhaseError


def engine_of(cfg) -> str:
    return "ps_lite" if cfg.project.method is Method.PS_LITE else "ps"


def run(cfg, store, out_dir: str | Path, *, engine: str | None = None, run_id: str = "", track_id: str = "",
        psrun_id: str = "", cache_root: str | Path | None = None, resume_from: str | Path | None = None) -> dict:
    """``engine`` overrides the project method (e.g. ``ps_lite`` on a CSK stack); ``resume_from``: a previous
    ``ps`` run folder whose steps 1-5 are reused (unwrapping and later steps again)."""
    engine = engine or engine_of(cfg)
    slc_var = "slc"
    if cfg.phase_linking.enabled:
        if not phase_linking.is_done(cfg, store):
            raise PhaseError(engine, f"{store.path}: phase linking enabled but not done with the current "
                                     "[phase_linking] parameters; run phase_linking first")
        slc_var = "slc_linked"
    if engine == "ps_lite":
        from geoeyes.processing.ps_lite.runner import run as ps_lite_run
        return ps_lite_run(store, out_dir, cfg.ps_lite, run_id=run_id, track_id=track_id, psrun_id=psrun_id,
                           slc_var=slc_var, weather=weather_params(cfg, cache_root))
    if engine != "ps":
        raise PhaseError("ps", f"unknown point engine {engine!r} (ps, ps_lite)")
    from geoeyes.processing.ps.runner import run as ps_run
    sel = cfg.selection
    return ps_run(store, out_dir, dict(cfg.ps), da_max=sel.da_threshold, run_id=run_id, track_id=track_id,
                  psrun_id=psrun_id, slc_var=slc_var,
                  ds_tcoh_min=sel.ds_coherence_min if slc_var == "slc_linked" else None, ds_cell=sel.ds_cell,
                  weather=weather_params(cfg, cache_root), resume_from=resume_from)


def weather_params(cfg, cache_root: str | Path | None = None):
    """``[atmosphere] method = "era5" | "gacos"`` -> WeatherParams (None: the linear APS of the engine).
    The ERA5 cache defaults to ``<workspace>/cache/era5``."""
    import dataclasses

    from geoeyes.processing.atmosphere.weather import WeatherParams
    method = str(cfg.atmosphere.method).strip().lower()
    if method in ("none", "linear", "a_l", "n", ""):
        return None
    if method not in LEGACY_TROPO:
        raise PhaseError("ps", f"[atmosphere] method {cfg.atmosphere.method!r} (none, linear, era5, gacos)")
    if cache_root is None and not dict(cfg.atmosphere.era5).get("cache"):
        from geoeyes.config.settings import load_settings
        cache_root = load_settings().workspace_layout().cache
    kind, component = LEGACY_TROPO[method]
    p = WeatherParams.from_section(cfg.atmosphere, cache_root)
    return dataclasses.replace(p, method=kind, component=component or p.component)


# [atmosphere] method, including the StaMPS tropo_method codes kept by `geoeyes migrate config`
LEGACY_TROPO = {"era5": ("era5", None), "a_era5": ("era5", "total"), "a_e": ("era5", "total"),
                "a_era5-h": ("era5", "hydro"), "a_eh": ("era5", "hydro"), "a_era5-w": ("era5", "wet"),
                "a_ew": ("era5", "wet"), "gacos": ("gacos", None), "a_gacos": ("gacos", None)}
