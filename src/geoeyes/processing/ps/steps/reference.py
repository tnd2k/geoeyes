"""Reference PS (legacy ``_ps_setref`` / ``_auto_stable_ref``): the PS whose mean phase is subtracted, so that
velocities and time series are relative to them.

``ref_lon`` / ``ref_lat`` box (StaMPS, open interval), optionally narrowed to ``ref_radius`` metres around
``ref_centre_lonlat``; ``auto``: the outermost 20 % of the PS (Chebyshev distance from the scene centre in
normalised lon/lat) and, of those, the more coherent half — a reference on the scene periphery, away from a
central deformation bowl that a scene-mean reference would flatten. No PS selected = all PS (StaMPS).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from geoeyes.processing.ps.geometry import llh2local

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceParams:
    lon: tuple[float, float] = (-np.inf, np.inf)
    lat: tuple[float, float] = (-np.inf, np.inf)
    centre_lonlat: tuple[float, float] = (0.0, 0.0)
    radius: float = np.inf               # m
    auto: bool = False

    @property
    def is_default(self) -> bool:
        """The whole scene (legacy default)."""
        return (not self.auto and np.isinf(self.radius) and np.all(np.isinf(self.lon)) and
                np.all(np.isinf(self.lat)))


def stable_periphery(lonlat: np.ndarray, coh: np.ndarray | None = None, edge_fraction: float = 0.2) -> np.ndarray:
    lon, lat = np.asarray(lonlat, np.float64).T
    lon_c, lat_c = (np.nanmax(lon) + np.nanmin(lon)) / 2, (np.nanmax(lat) + np.nanmin(lat)) / 2
    lon_r = max((np.nanmax(lon) - np.nanmin(lon)) / 2, 1e-9)
    lat_r = max((np.nanmax(lat) - np.nanmin(lat)) / 2, 1e-9)
    dist = np.maximum(np.abs(lon - lon_c) / lon_r, np.abs(lat - lat_c) / lat_r)
    edge = np.argsort(dist)[-max(10, int(np.round(edge_fraction * lon.size))):]
    if coh is not None:
        c = np.asarray(coh, np.float64).ravel()[edge]
        good = c >= np.nanpercentile(c, 50)
        if good.sum() >= 5:
            edge = edge[good]
    return np.sort(edge)


def reference_ps(lonlat: np.ndarray, params: ReferenceParams, coh: np.ndarray | None = None) -> np.ndarray:
    """0-based indices of the reference PS among ``lonlat`` (n, 2)."""
    p = params
    ll = np.asarray(lonlat, np.float64)
    if p.auto:
        ref = stable_periphery(ll, coh)
    else:
        ref = np.flatnonzero((ll[:, 0] > p.lon[0]) & (ll[:, 0] < p.lon[1]) & (ll[:, 1] > p.lat[0]) &
                             (ll[:, 1] < p.lat[1]))
        if np.isfinite(p.radius) and ref.size:
            c = np.asarray(p.centre_lonlat, np.float64)
            xy = llh2local(ll[ref], c) * 1000.0
            ref = ref[(xy**2).sum(axis=1) <= p.radius**2]
    if ref.size == 0:
        log.warning("no PS in the reference area: all PS used as reference")
        ref = np.arange(ll.shape[0])
    log.info("reference: %d PS%s", ref.size, " (stable periphery)" if p.auto else "")
    return ref
