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
    # clap_win 16, filter_grid_size 10, PERCENT 80 %, unwrap_gold_n_win 16: the settings tuned on the HCMC
    # Sentinel-1 product (hcm_test_des, 2026-10), default for every sensor since 2026-10-30 (a preset may
    # still override them: CSK and ICEYE keep their own percent_rand and unwrap_gold_n_win)
    "max_topo_err": 20.0, "filter_grid_size": 10, "filter_weighting": "P-square", "clap_win": 16,
    "clap_low_pass_wavelength": 800, "clap_alpha": 1.0, "clap_beta": 0.3, "gamma_change_convergence": 0.005,
    "gamma_max_iterations": 3, "dem_error_amb_auto_threshold": "y", "dem_error_amb_q_reject": 0.10,
    "dem_error_amb_q_ok": 0.25, "dem_error_spatial_lambda": 0.5, "dem_error_spatial_huber_delta": None,
    "dem_error_spatial_iters": 5, "topofit_chunk_pixels": 200000,
    "select_method": "PERCENT", "percent_rand": 80, "density_rand": 2.0, "gamma_min_threshold": 0.3,
    "gamma_stdev_reject": 0.0, "drop_ifg_index": [], "slc_osf": 1, "reest_smoothing_flag": "y",
    "ps_select_smooth_chunk_pixels": 1024,
    "weed_time_win": 730, "weed_standard_dev": 1.0, "weed_max_noise": float("inf"), "weed_zero_elevation": "n",
    "weed_neighbours": "n", "weed_adjacent_keep_per_group": 1, "weed_arc_edge_chunk_cap": None,
    "weed_noise_ifg_chunk": 12,
    # unwrap_grid_size (m): StaMPS 200 aliases fast motion (S1 Mexico: Capella r 0.64 -> 0.86 at 10 m)
    "unwrap_grid_size": 10, "unwrap_gold_n_win": 16, "unwrap_gold_alpha": 0.8, "unwrap_gold_coh_floor": 0.2,
    "unwrap_prefilter_flag": "y", "unwrap_time_win": 730, "unwrap_la_error_flag": "y", "unwrap_irls_iter": 50,
    "unwrap_irls_target_rms": 0.01, "unwrap_irls_epsilon": 0.001,
    # align the IRLS constant before snapping to the wrapped phase (irls.enforce_congruence): avoids one-cycle region
    # slips of interferograms whose mean phase is near ±π (Tenerife ICEYE); changes the validated CSK Hanoi result
    # (89.6 % of the points matched), so off by default until assessed (memory: ps_lite / ps congruence align)
    "unwrap_align_constant": "n",
    # space-time unwrapping (steps/unwrap.py). The legacy model is fitted to the wrapped edge phase and the IRLS
    # follows the wrapped gradients: an edge whose phase difference passes ±π (20 mm/yr between its cells: after
    # ~250 days on S1) takes a wrong cycle count far from the master (VINSAR / HCMC Binh Chanh vs SARPROZ, 2026-11).
    # unwrap_edge_velocity: each edge is unwrapped in time by its linear rate (periodogram, up to
    # unwrap_max_edge_velocity mm/yr); unwrap_model_cycles: the IRLS takes the cycle count of each grid step from
    # that model (StaMPS's SNAPHU cost offsets). legacy_quirks = "y" turns both off (parity)
    "unwrap_edge_velocity": "y", "unwrap_max_edge_velocity": 100.0, "unwrap_model_cycles": "y",
    # unwrap_ps_rate: a linear rate per PS from the PS network (Delaunay arcs <= unwrap_ps_rate_max_arc m,
    # periodogram, L1 integration; unwrap/ps_rate.py) is removed before the grid and added back: a PS faster than
    # its cell (a subsiding road through fields) keeps its cycles (HCMC vs SARPROZ: v < -25 bias +3.9 -> +1.4
    # mm/yr). "auto": only with >= unwrap_ps_rate_min_ifg interferograms and >= half the arcs above chance (CSK
    # Hanoi, 17 ifgs, moved far from its golden with it). Off with legacy_quirks
    "unwrap_ps_rate": "auto", "unwrap_ps_rate_max_arc": 500.0, "unwrap_ps_rate_min_ifg": 40,
    # StaMPS unwrap_patch_phase: "n" (StaMPS default) grids the step-5 phase of the PS (ph_rc) and each PS adds its
    # wrapped residual to its cell; "y" grids the smoother step-4 patch phase and adds ph_rc − patch (the legacy
    # engine; a PS that moves unlike its ~160 m neighbourhood loses cycles). legacy_quirks = "y" keeps "y"
    "unwrap_patch_phase": "n",
    # scla_deramp: "n" | "y" (plane / quadratic of every interferogram removed) | "auto" (the part of the ramp that
    # changes between acquisitions always, its steady trend only where a stable background anchors one plane over
    # the whole frame; docs/en/research/ramp-selection.md). deramp_non_defo: lon/lat polygon of a user's stable
    # area for "auto" (the trend plane is fitted there). ramp_auto_allow_planar: "y" lets "auto" remove a trend that
    # passes the halves test without a stable area (a planar deformation field passes it too: off by default)
    "scla_deramp": "n", "deramp_non_defo": None, "ramp_auto_allow_planar": "n",
    "scn_time_win": 365, "scn_wavelength": 100, "subtr_tropo": "y",
    # SCN temporal low-pass: "linear" (local linear fit, keeps the deformation trend out of the noise) or "mean"
    # (StaMPS ps_scn_filt; leaks the trend into the SCN at the series ends and in series shorter than the window)
    "scn_time_fit": "linear",
    "weed_noisy_check": "y",
    # GeoEyes switches between classic StaMPS (defaults, as the legacy S1 engine) and the legacy CSK engine's
    # additions: topofit ambiguity score + spatial K regularisation, population-scaled random histogram
    "dem_error_ambiguity": "n", "select_nr_scaling": "low_coherence", "unwrap_grid_filter": "gaussian",
    # σ of the "gaussian" grid prefilter in metres. The legacy σ = unwrap_gold_n_win/8 cells grows with the grid:
    # 100 m at 50 m, which flattened the HCMC Binh Chanh subsidence (vs SARPROZ, 2026-11-07: v < -15 mm/yr bias
    # +14.7 -> +5.2). "auto" = the legacy σ at a 10 m grid, (unwrap_gold_n_win // 8) × 10 m: 20 m for S1 (16), 80 m
    # for CSK / ICEYE (64), whatever the grid (identical to the legacy filter at 10 m). "cells" (or legacy_quirks =
    # "y") keeps the legacy filter. unwrap_grid_filter_unit = "y": filter unit phasors per cell (a cell of many PS no
    # longer outweighs its neighbours); off by default: CSK Hanoi golden 0.939 / 0.41 -> 0.918 / 0.58 mm/yr
    "unwrap_grid_filter_sigma": "auto", "unwrap_grid_filter_unit": "n",
    # reference PS (StaMPS ps_setref; default = all PS); ref_auto = "y": stable scene periphery
    "ref_lon": [float("-inf"), float("inf")], "ref_lat": [float("-inf"), float("inf")],
    "ref_centre_lonlat": [0.0, 0.0], "ref_radius": float("inf"), "ref_auto": "n",
    # linear APS fitted only inside this lon/lat polygon [[lon, lat], ...] (StaMPS non_defo); None = all PS
    "aps_non_defo": None,
    # "y" reproduces the legacy bugs kept for the parity tests (docs/en/refactor/TODO.md, Phase 4, port log of
    # the ps engine)
    "legacy_quirks": "n",
}


def hoa_max_topo_err(bperp, wavelength: float, slant_range: float, incidence: float,
                     max_perp: float | None = None, about_master: bool = False) -> float:
    """``max_topo_err = "auto"``: median height of ambiguity λ·R·sinθ / (2|B⊥|), / 4, with B⊥ taken about the
    median B⊥ of the stack, not about the master: the look-angle term K·B⊥ only resolves the DEM error through
    the spread of the baselines (a constant added to every B⊥ goes into the constant C), so a master at the edge of
    the baseline distribution (hp_maychai: B⊥ −303..0 m) gave a search four times narrower (20 m vs 89 m) for the
    same data. ``about_master``: the master-relative B⊥ of the legacy CSK/TSX prep (``max_topo_err =
    "auto_master"``, kept by the CSK / ICEYE presets). ``max_perp``: baselines with |B⊥| >= max_perp left out."""
    b = np.asarray(bperp, np.float64).ravel()
    b = b[np.isfinite(b)]
    b = np.abs(b if about_master else b - np.median(b))
    b = b[b > 0]
    if max_perp is not None and np.any(b < max_perp):
        b = b[b < max_perp]
    if b.size == 0:
        raise ValueError("max_topo_err = 'auto' needs non-zero perpendicular baselines")
    return float(np.median(wavelength * slant_range * np.sin(incidence) / (2 * b)) / 4)


def auto_time_win(days) -> float:
    """``unwrap_time_win = "auto"``: the Gaussian time window of the space-time unwrapping from the span of the
    data. StaMPS's 730 days suits multi-year stacks; on a stack shorter than the window the temporal model is
    almost a straight line, weakest at both ends, and noisy arcs there can take a wrong cycle count. A quarter of
    the span, at least four sampling intervals (enough dates inside the window), between 60 and 730 days."""
    d = np.sort(np.unique(np.asarray(days, np.float64)))
    if d.size < 3:
        return 730.0
    span = float(d[-1] - d[0])
    step = float(np.median(np.diff(d)))
    return float(np.clip(round(max(span / 4, 4 * step)), 60, 730))


def _yes(v) -> bool:
    return str(v).strip().lower() in ("y", "yes", "1", "true", "on")


def _grid_filter_sigma(pm) -> float | None:
    """σ (m) of the "gaussian" grid prefilter; None = the legacy filter (σ in cells)."""
    v = str(pm["unwrap_grid_filter_sigma"]).strip().lower()
    if _yes(pm["legacy_quirks"]) or v == "cells":
        return None
    if v == "auto":
        return float(max(int(pm["unwrap_gold_n_win"]) // 8, 2) * 10)
    return float(v)


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
    scn_time_fit: str = "linear"     # mean (StaMPS, legacy) | linear
    reference: ReferenceParams = field(default_factory=ReferenceParams)
    aps_non_defo: tuple | None = None   # lon/lat polygon of the linear-APS fit
    legacy: bool = False             # legacy bugs (parity): unweighted velocity, time-series epoch shift, ...
    deramp_auto: bool = False        # scla_deramp = "auto" (scla_deramp is then True)
    deramp_non_defo: tuple | None = None   # lon/lat polygon of the stable area for "auto"
    deramp_allow_planar: bool = False      # "auto": remove a planar trend without a stable area


def _polygon(v) -> tuple | None:
    return None if v in (None, "", []) else tuple(tuple(float(c) for c in pt) for pt in v)


def deramp_mode(v) -> str:
    """``scla_deramp``: "auto", "y" or "n" (yes/no spellings accepted)."""
    s = str(v).strip().lower()
    if s == "auto":
        return "auto"
    if _yes(s):
        return "y"
    if s in ("n", "no", "0", "false", "off", "none", ""):
        return "n"
    raise ValueError(f"[ps] scla_deramp = {v!r}: expected \"y\", \"n\" or \"auto\"")


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
    mode = deramp_mode(pm["scla_deramp"])
    deramp_on = mode != "n"
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
            filter_sigma_m=_grid_filter_sigma(pm),
            filter_unit=_yes(pm["unwrap_grid_filter_unit"]) and not _yes(pm["legacy_quirks"]),
            time_win=float(pm["unwrap_time_win"]),
            la_flag=_yes(pm["unwrap_la_error_flag"]), scla_deramp=deramp_on, drop_ifg_index=drop,
            spatial=SpatialParams(irls_iter=int(pm["unwrap_irls_iter"]),
                                  irls_target_rms=float(pm["unwrap_irls_target_rms"]),
                                  irls_epsilon=float(pm["unwrap_irls_epsilon"]),
                                  align=_yes(pm.get("unwrap_align_constant", "n")),
                                  model_cycles=_yes(pm["unwrap_model_cycles"]) and not _yes(pm["legacy_quirks"])),
            legacy=_yes(pm["legacy_quirks"]),
            edge_rate_max=(float(pm["unwrap_max_edge_velocity"])
                           if _yes(pm["unwrap_edge_velocity"]) and not _yes(pm["legacy_quirks"]) else 0.0),
            patch_phase=_yes(pm["unwrap_patch_phase"]) or _yes(pm["legacy_quirks"]),
            ps_rate=("n" if _yes(pm["legacy_quirks"]) else
                     "auto" if str(pm["unwrap_ps_rate"]).strip().lower() == "auto" else
                     "y" if _yes(pm["unwrap_ps_rate"]) else "n"),
            ps_rate_max_arc=float(pm["unwrap_ps_rate_max_arc"]),
            ps_rate_min_ifg=int(pm["unwrap_ps_rate_min_ifg"])),
        scla_deramp=deramp_on, two_pass=_yes(pm["subtr_tropo"]),
        scn_time_win=float(pm["scn_time_win"]), scn_wavelength=float(pm["scn_wavelength"]),
        # the legacy engine (parity) has the StaMPS weighted mean
        scn_time_fit="mean" if _yes(pm["legacy_quirks"]) else str(pm["scn_time_fit"]),
        reference=ReferenceParams(lon=_pair(pm["ref_lon"]), lat=_pair(pm["ref_lat"]),
                                  centre_lonlat=_pair(pm["ref_centre_lonlat"]), radius=float(pm["ref_radius"]),
                                  auto=_yes(pm["ref_auto"])),
        aps_non_defo=_polygon(pm["aps_non_defo"]),
        legacy=_yes(pm["legacy_quirks"]),
        deramp_auto=mode == "auto", deramp_non_defo=_polygon(pm.get("deramp_non_defo")),
        deramp_allow_planar=_yes(pm.get("ramp_auto_allow_planar", "n")))
