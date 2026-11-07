"""Weather models for the tropospheric correction: what each one covers, how fine it is and whether GeoEyes fetches
it by itself. The web app lists them for a project (coverage of its area and dates); ``geoeyes atmosphere`` tries
the usable ones on a product.

Outside Europe there is no free, automatically downloadable model finer than ERA5 for past dates: the 9 km
ECMWF IFS (the model behind GACOS) is open only as a rolling real-time archive (open-meteo serves its history at
0.25 deg, ERA5's grid, without the pressure levels at 9 km); the national high-resolution models are regional
(HRRR: United States, CARRA: Arctic, BARRA2: Australia) and listed here as not yet supported. GACOS covers the
globe but is ordered by e-mail (manual step: the products are then read from a folder).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import numpy as np


@dataclass(frozen=True)
class WeatherModel:
    key: str
    name: str
    provider: str
    region: str                  # global | europe | conus | arctic | australia
    resolution_km: float
    step_h: int                  # analyses every step_h hours
    start: date
    latency_days: int            # typical delay before a date is published
    access: str                  # auto: downloaded by GeoEyes; manual: ordered by the user; planned: not supported
    note: str = ""

    def covers_area(self, lon, lat) -> bool | None:
        """None when unknown (regional models not supported yet)."""
        lon, lat = np.atleast_1d(lon), np.atleast_1d(lat)
        if self.region == "global":
            return True
        if self.key == "cerra":
            from geoeyes.processing.atmosphere import cerra
            return cerra.covers(lon, lat)
        box = _BOXES.get(self.region)
        if box is None:
            return None
        w, s, e, n = box
        return bool(np.all((lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)))

    def covers_dates(self, dates: list[date], today: date | None = None) -> bool:
        today = today or date.today()
        return min(dates) >= self.start and max(dates) <= today - timedelta(days=self.latency_days)


# approximate rectangles of the regional models not supported yet (only to tell the user they exist)
_BOXES = {"conus": (-134.1, 21.1, -60.9, 52.6), "arctic": (-180.0, 55.0, 180.0, 90.0),
          "australia": (88.0, -57.0, 207.0, 13.0)}

MODELS: dict[str, WeatherModel] = {m.key: m for m in (
    WeatherModel("era5", "ERA5", "ECMWF / Copernicus C3S", "global", 31.0, 1, date(1940, 1, 1), 6, "auto",
                 "global reanalysis, hourly; CDS API"),
    WeatherModel("cerra", "CERRA", "SMHI / Copernicus C3S", "europe", 5.5, 3, date(1984, 9, 1), 45, "auto",
                 "European regional reanalysis, 3-hourly; CDS API (whole-domain GRIB, ~125 MB per analysis)"),
    WeatherModel("gacos", "GACOS", "Newcastle University", "global", 9.0, 1, date(2016, 1, 1), 2, "manual",
                 "ECMWF HRES + interpolation; ordered on the GACOS website, products put in [atmosphere.gacos] dir"),
    WeatherModel("hrrr", "HRRR", "NOAA", "conus", 3.0, 1, date(2014, 9, 30), 1, "planned",
                 "United States only; open on AWS"),
    WeatherModel("carra", "CARRA", "Copernicus C3S", "arctic", 2.5, 3, date(1991, 1, 1), 45, "planned",
                 "Arctic regional reanalysis; CDS API"),
    WeatherModel("barra2", "BARRA2", "Bureau of Meteorology", "australia", 12.0, 1, date(1979, 1, 1), 60, "planned",
                 "Australian regional reanalysis; NCI"),
)}


def catalogue(lon, lat, dates: list[date], today: date | None = None) -> list[dict]:
    """Every model with its coverage of the points and the dates (``usable``: GeoEyes can apply it here)."""
    out = []
    for m in MODELS.values():
        area = m.covers_area(lon, lat)
        when = m.covers_dates(dates, today)
        out.append({**asdict(m), "start": m.start.isoformat(), "covers_area": area, "covers_dates": when,
                    "usable": m.access == "auto" and bool(area) and when})
    return out


__all__ = ["MODELS", "WeatherModel", "catalogue"]
