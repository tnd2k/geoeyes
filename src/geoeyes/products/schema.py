"""Columns of a point product (ARCHITECTURE §10.4), the same for every sensor and engine.

Signs: LOS velocity and displacement positive toward the satellite; ``los_e/n/u`` is the unit vector from the
ground toward the satellite, so a 3-D motion m (east, north, up) is seen as m · los. Time series (``timeseries
.parquet``) are 0 at each point's first date (since geoeyes-product/3; earlier products: 0 at the stack's reference
date ``reference_date``), relative to the reference area in space.
"""
from __future__ import annotations

SCHEMA = "geoeyes.points/1"

# name -> (pandas dtype, unit, description)
COLUMNS: dict[str, tuple[str, str, str]] = {
    "point_uid": ("string", "", "stable point id: <track>:<geohash>:<height>"),
    "track_id": ("string", "", ""),
    "stack_id": ("string", "", ""),
    "lon": ("float64", "deg", "EPSG:4326"),
    "lat": ("float64", "deg", "EPSG:4326"),
    "height_m": ("float32", "m", "orthometric height: DEM + height error"),
    "type": ("category", "", "PS | DS"),
    "vel_los_mm_yr": ("float32", "mm/yr", "LOS velocity, + toward the satellite"),
    "vel_std_mm_yr": ("float32", "mm/yr", "standard error of the velocity fit"),
    "acc_los_mm_yr2": ("float32", "mm/yr2", "LOS acceleration (quadratic fit)"),
    "temporal_coherence": ("float32", "", ""),
    "amp_dispersion": ("float32", "", ""),
    "dem_err_m": ("float32", "m", "height error vs the DEM"),
    "seasonal_amp_mm": ("float32", "mm", "annual amplitude (NaN for series shorter than ~10 months)"),
    "seasonal_phase_day": ("float32", "day", "day of year of the annual maximum"),
    "fit_rmse_mm": ("float32", "mm", "RMSE of the engine's velocity fit"),
    "residual_sigma_mm": ("float32", "mm", "std of the time series about linear + annual model"),
    "los_e": ("float32", "", "unit vector ground -> satellite, east"),
    "los_n": ("float32", "", "north"),
    "los_u": ("float32", "", "up"),
    "incidence_deg": ("float32", "deg", ""),
    "heading_deg": ("float32", "deg", "satellite heading (flight direction, from north)"),
}
EXTRA_PREFIX = "extra_"            # engine-specific columns, outside the schema contract
