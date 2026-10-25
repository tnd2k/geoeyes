"""Weather-model APS of the PS: (n, n_epoch) interferometric phase (rad, master column 0) from ERA5 or GACOS,
NaN where the model has no data (the caller fills those entries with the linear APS, as the legacy flow)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

from geoeyes.processing.atmosphere import era5, gacos
from geoeyes.processing.atmosphere.slant import zenith_to_ifg_phase

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeatherParams:
    method: str                                  # "era5" | "gacos"
    cache: Path | None = None                    # ERA5 NetCDF cache
    gacos_dir: Path | None = None
    component: str = "total"                     # ERA5: total | hydro | wet
    buffer_deg: float = 2.0
    auto_download: bool = True
    levels: tuple[str, ...] = field(default=era5.cds.LEVELS)
    workers: int = 4
    fallback_utc: str | None = None              # overpass time for stacks without per-date sensing times
    select: str = "auto"                         # auto: per interferogram vs the linear APS; all: every one

    @classmethod
    def from_section(cls, sec, cache_root: Path | None = None) -> WeatherParams:
        """From the project ``[atmosphere]`` section (``era5`` / ``gacos`` sub-tables)."""
        e, g = dict(sec.era5), dict(sec.gacos)
        cache = e.get("cache") or (Path(cache_root) / "era5" if cache_root else None)
        return cls(method=str(sec.method).lower(), cache=Path(cache) if cache else None,
                   gacos_dir=Path(g["dir"]) if g.get("dir") else None, component=str(e.get("component", "total")),
                   buffer_deg=float(e.get("buffer_deg", 2.0)), auto_download=bool(e.get("auto_download", True)),
                   levels=tuple(str(v) for v in e.get("pressure_levels") or era5.cds.LEVELS),
                   workers=int(e.get("workers", 4)), fallback_utc=e.get("fallback_utc") or None,
                   select=str(sec.select))


def weather_aps(p: WeatherParams, *, lon, lat, hgt, incidence, times: dict[date, datetime], master_ix: int,
                wavelength: float) -> np.ndarray:
    """``times`` in epoch order; ``hgt`` m above the geoid, ``incidence`` (n,) rad."""
    dates = list(times)
    if p.method == "era5":
        if p.cache is None:
            raise ValueError("ERA5 APS needs a cache folder ([atmosphere.era5] cache)")
        zhd, zwd = era5.zenith_delays(lon, lat, hgt, times, p.cache, buffer_deg=p.buffer_deg,
                                      auto_download=p.auto_download, levels=p.levels, workers=p.workers)
        zen = {"total": zhd + zwd, "hydro": zhd, "wet": zwd}[p.component]
    elif p.method == "gacos":
        if p.gacos_dir is None:
            raise ValueError("GACOS APS needs the product folder ([atmosphere.gacos] dir)")
        zen = gacos.zenith_delays(lon, lat, dates, p.gacos_dir)
    else:
        raise ValueError(f"weather APS method {p.method!r} (era5, gacos)")
    ph = zenith_to_ifg_phase(zen, incidence, wavelength, master_ix)
    ok = np.isfinite(ph)
    log.info("%s APS: %.1f %% of the PS x interferogram values available", p.method.upper(),
             100.0 * ok[:, np.arange(len(dates)) != master_ix].mean())
    return ph
