"""Satellite orbit: state vectors and their interpolation.

Positions/velocities are ECEF (m, m/s), times UTC. Interpolation is Hermite (position + velocity,
cubic per interval) over the vectors bracketing the requested time — sub-millimetre for the
10 s spacing of Sentinel-1 precise orbits. ``zero_doppler_time`` solves for the azimuth time at
which a ground point is perpendicular to the velocity (zero-Doppler geometry, S1/TSX/CSK/ALOS).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from geoeyes.core.errors import DataError


@dataclass(frozen=True)
class StateVectors:
    t0: datetime                 # reference epoch (UTC); times are seconds since t0
    t: np.ndarray                # (n,) float64 seconds
    pos: np.ndarray              # (n, 3) ECEF m
    vel: np.ndarray              # (n, 3) ECEF m/s

    def __post_init__(self):
        if len(self.t) < 4:
            raise DataError("need at least 4 state vectors")
        if np.any(np.diff(self.t) <= 0):
            raise DataError("state vector times must be strictly increasing")

    @classmethod
    def from_lists(cls, times: list[datetime], pos, vel) -> StateVectors:
        order = np.argsort([t.timestamp() for t in times])
        times = [times[i] for i in order]
        t0 = times[0]
        t = np.array([(x - t0).total_seconds() for x in times], np.float64)
        _, keep = np.unique(t, return_index=True)
        return cls(t0, t[keep], np.asarray(pos, np.float64)[order][keep], np.asarray(vel, np.float64)[order][keep])

    def seconds(self, when: datetime) -> float:
        return (when - self.t0).total_seconds()

    def covers(self, t: float | np.ndarray, margin: float = 0.0) -> bool:
        t = np.asarray(t)
        return bool(t.min() >= self.t[0] - margin and t.max() <= self.t[-1] + margin)

    def interpolate(self, t) -> tuple[np.ndarray, np.ndarray]:
        """Position and velocity at seconds ``t`` since ``t0`` (scalar or array), Hermite."""
        t = np.atleast_1d(np.asarray(t, np.float64))
        if not self.covers(t, margin=1e-6):
            raise DataError(f"time outside orbit span [{self.t[0]:.1f}, {self.t[-1]:.1f}] s")
        i = np.clip(np.searchsorted(self.t, t) - 1, 0, len(self.t) - 2)
        t0, t1 = self.t[i], self.t[i + 1]
        h = (t1 - t0)[:, None]
        s = ((t - t0) / (t1 - t0))[:, None]
        p0, p1 = self.pos[i], self.pos[i + 1]
        v0, v1 = self.vel[i] * h, self.vel[i + 1] * h
        h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
        pos = h00 * p0 + h10 * v0 + h01 * p1 + h11 * v1
        d00, d10, d01, d11 = 6 * s**2 - 6 * s, 3 * s**2 - 4 * s + 1, -6 * s**2 + 6 * s, 3 * s**2 - 2 * s
        vel = (d00 * p0 + d10 * v0 + d01 * p1 + d11 * v1) / h
        return pos, vel

    def zero_doppler_time(self, target_ecef, t_guess, *, tol: float = 1e-9, max_iter: int = 30) -> np.ndarray:
        """Azimuth time(s) where (target - sat) · v_sat = 0; Newton on f(t) = (X - S(t))·V(t)."""
        x = np.atleast_2d(np.asarray(target_ecef, np.float64))
        t = np.broadcast_to(np.asarray(t_guess, np.float64), (len(x),)).copy()
        for _ in range(max_iter):
            p, v = self.interpolate(t)
            d = x - p
            f = np.einsum("ij,ij->i", d, v)
            # df/dt ≈ -|v|^2 (acceleration term is ~1e-3 relative; Newton still converges quadratically enough)
            step = f / np.einsum("ij,ij->i", v, v)
            t = t + step
            if np.max(np.abs(step)) < tol:
                break
        return t

    def slant_range(self, target_ecef, t) -> np.ndarray:
        p, _ = self.interpolate(t)
        return np.linalg.norm(np.atleast_2d(target_ecef) - p, axis=1)
