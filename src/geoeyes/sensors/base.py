"""Sensor-independent radar grid for zero-Doppler stripmap / spotlight SLCs (CSK, Capella, TSX, ALOS).

``RadarGrid`` exposes the same geometry interface as ``sentinel1.burst.BurstMetadata`` (orbit,
timing, range sampling, tie points in ``grid``), so the native geometry, coregistration and
height-sensitivity code is shared between TOPS bursts and stripmap scenes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from geoeyes.geometry.orbit import StateVectors

C = 299_792_458.0


@dataclass(frozen=True)
class TiePoints:
    """Known ground positions of some image pixels (initial guess for rdr2geo)."""

    line: np.ndarray
    pixel: np.ndarray
    lat: np.ndarray
    lon: np.ndarray


@dataclass(frozen=True)
class DopplerPoly:
    """Doppler centroid (Hz) as a polynomial in two-way slant-range time: sum c_k (tau - t0)^k."""

    t0: float
    coeffs: tuple[float, ...]

    def __call__(self, tau):
        return np.polynomial.polynomial.polyval(np.asarray(tau, np.float64) - self.t0, self.coeffs)


@dataclass(frozen=True)
class RadarGrid:
    sensor: str
    scene_id: str
    sensing_start: datetime            # azimuth (zero-Doppler) time of line 0, UTC
    azimuth_time_interval: float       # s per line
    slant_range_time: float            # two-way time of sample 0, s
    range_sampling_rate: float         # Hz (samples per two-way second)
    lines: int
    samples: int
    wavelength: float
    orbit: StateVectors
    look_side: str                     # "right" | "left"
    pass_direction: str                # "ascending" | "descending"
    heading_deg: float
    grid: TiePoints
    doppler: DopplerPoly | None = None
    polarization: str = ""
    azimuth_pixel_spacing: float = 0.0
    range_pixel_spacing: float = 0.0

    # same API as BurstMetadata ------------------------------------------------
    @property
    def near_range(self) -> float:
        return self.slant_range_time * C / 2

    @property
    def sensing_mid(self) -> datetime:
        return self.sensing_start + timedelta(seconds=self.lines * self.azimuth_time_interval / 2)

    @property
    def valid_window(self) -> tuple[int, int, int, int]:
        return 0, self.lines, 0, self.samples

    def line_time(self, line) -> np.ndarray:
        return np.asarray(line, np.float64) * self.azimuth_time_interval

    def sample_range_time(self, sample) -> np.ndarray:
        return self.slant_range_time + np.asarray(sample, np.float64) / self.range_sampling_rate

    def slant_range(self, sample) -> np.ndarray:
        return self.sample_range_time(sample) * C / 2

    def orbit_seconds(self, line=0.0) -> np.ndarray:
        return self.orbit.seconds(self.sensing_start) + self.line_time(line)


def heading_from_orbit(orbit: StateVectors, t: float) -> float:
    """Ground-track heading (deg from north, clockwise) from the velocity at orbit time ``t``."""
    from geoeyes.core.geodesy import ecef_to_llh, enu_basis
    p, v = orbit.interpolate(t)
    lat, lon, _ = ecef_to_llh(p)
    b = enu_basis(lat, lon)[0]
    ve, vn = float(b[0] @ v[0]), float(b[1] @ v[0])
    return float(np.degrees(np.arctan2(ve, vn)))
