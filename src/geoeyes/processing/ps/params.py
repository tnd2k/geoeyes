"""Engine parameters from a flat StaMPS-named table (project ``[ps]``, same keys as the legacy
``parms.json``), with the legacy defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from geoeyes.processing.ps.ambiguity import DemErrorParams
from geoeyes.processing.ps.steps.est_gamma import EstGammaParams
from geoeyes.processing.ps.steps.reference import ReferenceParams
from geoeyes.processing.ps.steps.select import SelectParams
from geoeyes.processing.ps.steps.unwrap import UnwrapParams
from geoeyes.processing.ps.steps.weed import WeedParams
from geoeyes.processing.ps.unwrap.spatial import SpatialParams

DEFAULTS: dict[str, Any] = {
    "max_topo_err": 20.0, "filter_grid_size": 50, "filter_weighting": "P-square", "clap_win": 32,
    "clap_low_pass_wavelength": 800, "clap_alpha": 1.0, "clap_beta": 0.3, "gamma_change_convergence": 0.005,
    "gamma_max_iterations": 3, "dem_error_amb_auto_threshold": "y", "dem_error_amb_q_reject": 0.10,
    "dem_error_amb_q_ok": 0.25, "dem_error_spatial_lambda": 0.5, "dem_error_spatial_huber_delta": None,
    "dem_error_spatial_iters": 5, "topofit_chunk_pixels": 200000,
    "select_method": "DENSITY", "percent_rand": 1.0, "density_rand": 2.0, "gamma_min_threshold": 0.3,
    "gamma_stdev_reject": 0.0, "drop_ifg_index": [], "slc_osf": 1, "reest_smoothing_flag": "y",
    "ps_select_smooth_chunk_pixels": 1024,
    "weed_time_win": 730, "weed_standard_dev": 1.0, "weed_max_noise": float("inf"), "weed_zero_elevation": "n",
    "weed_neighbours": "n", "weed_adjacent_keep_per_group": 1, "weed_arc_edge_chunk_cap": None,
    "weed_noise_ifg_chunk": 12,
    # unwrap_grid_size (m): StaMPS 200 aliases fast motion (S1 Mexico: Capella r 0.64 -> 0.86 at 10 m)
    "unwrap_grid_size": 10, "unwrap_gold_n_win": 32, "unwrap_gold_alpha": 0.8, "unwrap_gold_coh_floor": 0.2,
    "unwrap_prefilter_flag": "y", "unwrap_time_win": 730, "unwrap_la_error_flag": "y", "unwrap_irls_iter": 50,
    "unwrap_irls_target_rms": 0.01, "unwrap_irls_epsilon": 0.001,
    "scla_deramp": "n", "scn_time_win": 365, "scn_wavelength": 100, "subtr_tropo": "y",
    "weed_noisy_check": "y",
    # GeoEyes switches between classic StaMPS (defaults, as the legacy S1 engine) and the legacy CSK engine's
    # additions: topofit ambiguity score + spatial K regularisation, population-scaled random histogram
    "dem_error_ambiguity": "n", "select_nr_scaling": "low_coherence", "unwrap_grid_filter": "gaussian",
    # reference PS (StaMPS ps_setref; default = all PS); ref_auto = "y": stable scene periphery
    "ref_lon": [float("-inf"), float("inf")], "ref_lat": [float("-inf"), float("inf")],
    "ref_centre_lonlat": [0.0, 0.0], "ref_radius": float("inf"), "ref_auto": "n",
    # linear APS fitted only inside this lon/lat polygon [[lon, lat], ...] (StaMPS non_defo); None = all PS
    "aps_non_defo": None,
    # "y" reproduces the legacy bugs kept for the parity tests (docs/refactor/TODO.md, Phase 4, port log of the ps engine)
    "legacy_quirks": "n",
}


def hoa_max_topo_err(bperp, wavelength: float, slant_range: float, incidence: float,
                     max_perp: float | None = None) -> float:
    """``max_topo_err = "auto"`` of the legacy CSK/TSX prep: median height of ambiguity λ·R·sinθ / (2|B⊥|) of the
    reference-secondary pairs, / 4. ``max_perp``: pairs with |B⊥| >= max_perp left out of the median."""
    b = np.abs(np.asarray(bperp, np.float64))
    b = b[b > 0]
    if max_perp is not None and np.any(b < max_perp):
        b = b[b < max_perp]
    if b.size == 0:
        raise ValueError("max_topo_err = 'auto' needs non-zero perpendicular baselines")
    return float(np.median(wavelength * slant_range * np.sin(incidence) / (2 * b)) / 4)


def _yes(v) -> bool:
    return str(v).strip().lower() in ("y", "yes", "1", "true", "on")


def _pair(v) -> tuple[float, float]:
    a = np.asarray(v, np.float64).ravel()
    return float(a[0]), float(a[1])


def _indices(v) -> tuple[int, ...]:
    if v is None or v == "":
        return ()
    if isinstance(v, (list, tuple)):
        return tuple(int(x) for x in v)
    return tuple(int(x) for x in str(v).split())


@dataclass(frozen=True)
class EngineParams:
    est_gamma: EstGammaParams
    select: SelectParams
    weed: WeedParams
    unwrap: UnwrapParams
    scla_deramp: bool
    two_pass: bool                   # second unwrap pass with SCLA + linear APS removed
    scn_time_win: float
    scn_wavelength: float
    reference: ReferenceParams = field(default_factory=ReferenceParams)
    aps_non_defo: tuple | None = None   # lon/lat polygon of the linear-APS fit
    legacy: bool = False             # legacy bugs (parity): unweighted velocity, time-series epoch shift, ...


def engine_params(table: dict[str, Any] | None, *, wavelength: float, rho: float) -> EngineParams:
    pm = {**DEFAULTS, **(table or {})}
    hd = pm.get("dem_error_spatial_huber_delta")
    dem = DemErrorParams(
        enabled=_yes(pm["dem_error_ambiguity"]), amb_auto_threshold=_yes(pm["dem_error_amb_auto_threshold"]),
        amb_q_reject=float(pm["dem_error_amb_q_reject"]),
        amb_q_ok=float(pm["dem_error_amb_q_ok"]), spatial_lambda=float(pm["dem_error_spatial_lambda"]),
        spatial_huber_delta=float(hd) if hd not in (None, "") else None,
        spatial_iters=int(pm["dem_error_spatial_iters"]))
    drop = _indices(pm.get("drop_ifg_index"))
    edge_cap = pm.get("weed_arc_edge_chunk_cap")
    return EngineParams(
        est_gamma=EstGammaParams(
            wavelength=wavelength, rho=rho, max_topo_err=float(pm["max_topo_err"]),
            grid_size=float(pm["filter_grid_size"]), filter_weighting=str(pm["filter_weighting"]),
            clap_win=int(pm["clap_win"]), clap_low_pass_wavelength=float(pm["clap_low_pass_wavelength"]),
            clap_alpha=float(pm["clap_alpha"]), clap_beta=float(pm["clap_beta"]),
            gamma_change_convergence=float(pm["gamma_change_convergence"]),
            gamma_max_iterations=int(pm["gamma_max_iterations"]), dem_error=dem,
            chunk=int(pm.get("topofit_chunk_pixels") or 200000)),
        select=SelectParams(
            select_method=str(pm["select_method"]), percent_rand=float(pm["percent_rand"]),
            density_rand=float(pm["density_rand"]), gamma_min_threshold=float(pm["gamma_min_threshold"]),
            gamma_stdev_reject=float(pm["gamma_stdev_reject"]), drop_ifg_index=drop, clap_win=int(pm["clap_win"]),
            clap_alpha=float(pm["clap_alpha"]), clap_beta=float(pm["clap_beta"]), slc_osf=int(pm["slc_osf"]),
            resmooth=str(pm["reest_smoothing_flag"]) != "n", dem_error=dem,
            batch=int(pm.get("ps_select_smooth_chunk_pixels") or 1024), nr_scaling=str(pm["select_nr_scaling"]),
            legacy=_yes(pm["legacy_quirks"])),
        weed=WeedParams(
            time_win=float(pm["weed_time_win"]), weed_standard_dev=float(pm["weed_standard_dev"]),
            weed_max_noise=float(pm["weed_max_noise"]), weed_zero_elevation=_yes(pm["weed_zero_elevation"]),
            weed_neighbours=_yes(pm["weed_neighbours"]), keep_per_group=int(pm["weed_adjacent_keep_per_group"]),
            drop_ifg_index=drop, edge_chunk=int(edge_cap) if edge_cap not in (None, "") else None,
            ifg_chunk=int(pm.get("weed_noise_ifg_chunk") or 12), noisy_check=_yes(pm["weed_noisy_check"]),
            legacy=_yes(pm["legacy_quirks"])),
        unwrap=UnwrapParams(
            wavelength=wavelength, rho=rho, max_topo_err=float(pm["max_topo_err"]),
            grid_size=float(pm["unwrap_grid_size"]), prefilt_win=int(pm["unwrap_gold_n_win"]),
            gold_alpha=float(pm["unwrap_gold_alpha"]), coh_floor=float(pm["unwrap_gold_coh_floor"]),
            prefilter=str(pm["unwrap_grid_filter"]) if _yes(pm["unwrap_prefilter_flag"]) else "none",
            time_win=float(pm["unwrap_time_win"]),
            la_flag=_yes(pm["unwrap_la_error_flag"]), scla_deramp=_yes(pm["scla_deramp"]), drop_ifg_index=drop,
            spatial=SpatialParams(irls_iter=int(pm["unwrap_irls_iter"]),
                                  irls_target_rms=float(pm["unwrap_irls_target_rms"]),
                                  irls_epsilon=float(pm["unwrap_irls_epsilon"])),
            legacy=_yes(pm["legacy_quirks"])),
        scla_deramp=_yes(pm["scla_deramp"]), two_pass=_yes(pm["subtr_tropo"]),
        scn_time_win=float(pm["scn_time_win"]), scn_wavelength=float(pm["scn_wavelength"]),
        reference=ReferenceParams(lon=_pair(pm["ref_lon"]), lat=_pair(pm["ref_lat"]),
                                  centre_lonlat=_pair(pm["ref_centre_lonlat"]), radius=float(pm["ref_radius"]),
                                  auto=_yes(pm["ref_auto"])),
        aps_non_defo=None if pm["aps_non_defo"] in (None, "", []) else
        tuple(tuple(float(c) for c in pt) for pt in pm["aps_non_defo"]),
        legacy=_yes(pm["legacy_quirks"]))
