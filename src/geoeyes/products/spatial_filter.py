"""Spatial outliers of a point product (``[product] spatial_filter``).

A point whose velocity sits far from the points around it is left out of the product: it is a PS whose phase
drifted away from its neighbours (unwrapping or noise), not ground motion, which is shared by the points of the
same ground. For every point, the neighbours are its ``k`` nearest points within ``radius_m``. The point is an
outlier when

    |v - median(v_neighbours)| > max(dv_min, z * 1.4826 * MAD(v_neighbours))

for any velocity kind given (the product velocity and the StaMPS kinds v-do / v-dao / v-dso). The MAD guard keeps
the points of real, uneven motion: within and at the edge of a subsidence bowl the neighbours spread too. A point
with fewer than ``min_neighbours`` neighbours is kept (it cannot be judged).

hcm_d18 v6 (450k PS, 2026-11-08): 0.52 % left out; of the PS faster than -60 mm/yr, about 60 %. These were single
PS drifting tens of mm away from their neighbours over the years.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpatialFilter:
    enabled: bool = True
    radius_m: float = 200.0
    k: int = 30
    min_neighbours: int = 8
    dv_min: float = 10.0          # mm/yr
    z: float = 4.0


def spatial_outliers(lon, lat, velocities, p: SpatialFilter = SpatialFilter(), chunk: int = 100_000) -> np.ndarray:
    """(n,) bool: the points left out. ``velocities``: one or more (n,) arrays (mm/yr); NaN values are not
    neighbours and are not judged."""
    from scipy.spatial import cKDTree
    lon, lat = np.asarray(lon, np.float64), np.asarray(lat, np.float64)
    n = lon.size
    out = np.zeros(n, bool)
    if n < p.min_neighbours + 1:
        return out
    lat0 = np.radians(np.nanmean(lat))
    xy = np.column_stack([lon * 111_320.0 * np.cos(lat0), lat * 110_540.0])
    tree = cKDTree(xy)
    for s in range(0, n, chunk):
        dist, idx = tree.query(xy[s:s + chunk], k=p.k + 1, distance_upper_bound=p.radius_m)
        dist, idx = dist[:, 1:], idx[:, 1:]                   # the point itself is the first
        near = np.isfinite(dist)
        idx = np.where(near, idx, 0)
        for v in velocities:
            v = np.asarray(v, np.float64)
            V = np.where(near, v[idx], np.nan)
            cnt = np.isfinite(V).sum(axis=1)
            judge = (cnt >= p.min_neighbours) & np.isfinite(v[s:s + chunk])
            if not judge.any():
                continue
            Vj = V[judge]
            med = np.nanmedian(Vj, axis=1)
            mad = 1.4826 * np.nanmedian(np.abs(Vj - med[:, None]), axis=1)
            bad = np.abs(v[s:s + chunk][judge] - med) > np.maximum(p.dv_min, p.z * mad)
            out[s + np.flatnonzero(judge)[bad]] = True
    return out
