"""Difference of two products on a common grid (web app "Compare").

Points of two products are never the same scatterers (other sensor, other stack, other selection), so both are
reduced to the median velocity in square cells of ``cell_m`` metres, and the difference B - A is taken where both
have points. The two products have their own reference area: ``align=True`` removes the median difference.
Different tracks see the ground along different lines of sight: the difference then also contains geometry.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from geoeyes.api import points


def _cells(lon: np.ndarray, lat: np.ndarray, vel: np.ndarray, lat0: float, cell_m: float) -> pd.Series:
    kx = np.floor(lon * 111_320.0 * np.cos(np.radians(lat0)) / cell_m).astype(np.int64)
    ky = np.floor(lat * 110_540.0 / cell_m).astype(np.int64)
    return pd.Series(vel).groupby([kx, ky]).median()


@lru_cache(maxsize=8)
def difference(folder_a: str, folder_b: str, cell_m: float = 50.0, align: bool = True) -> tuple[dict, bytes]:
    """(meta, float32 x 5 per cell: lon - lon0, lat - lat0, B - A, A, B); cached, the JSON and the binary
    endpoints ask for the same comparison one after the other."""
    a = points._arrays(str(folder_a))[0]
    b = points._arrays(str(folder_b))[0]
    lat0 = float(np.median(np.concatenate([a["lat"], b["lat"]])))
    ga = _cells(a["lon"], a["lat"], a["vel"], lat0, cell_m)
    gb = _cells(b["lon"], b["lat"], b["vel"], lat0, cell_m)
    both = ga.index.intersection(gb.index)
    meta: dict = {"cell_m": cell_m, "align": align, "n_a": int(ga.size), "n_b": int(gb.size), "n": int(both.size)}
    if both.size == 0:
        return meta, b""
    va, vb = ga.loc[both].to_numpy(np.float64), gb.loc[both].to_numpy(np.float64)
    diff = vb - va
    offset = float(np.median(diff))
    if align:
        diff = diff - offset
    kx = np.array([k[0] for k in both], np.float64)
    ky = np.array([k[1] for k in both], np.float64)
    lon = (kx + 0.5) * cell_m / (111_320.0 * np.cos(np.radians(lat0)))
    lat = (ky + 0.5) * cell_m / 110_540.0
    lon0, lat0r = float(np.round(np.median(lon), 4)), float(np.round(np.median(lat), 4))
    corr = float(np.corrcoef(va, vb)[0, 1]) if both.size > 2 and va.std() > 0 and vb.std() > 0 else None
    meta.update({
        "origin": [lon0, lat0r], "offset": round(offset, 3), "classes": points.classes(diff.astype(np.float32)),
        "vel_min": float(diff.min()), "vel_max": float(diff.max()),
        "stats": {"mean": round(float(diff.mean()), 3), "median": round(float(np.median(diff)), 3),
                  "std": round(float(diff.std()), 3), "rmse": round(float(np.sqrt(np.mean(diff ** 2))), 3),
                  "p05": round(float(np.percentile(diff, 5)), 3), "p95": round(float(np.percentile(diff, 95)), 3),
                  "corr": None if corr is None else round(corr, 3)},
        "bounds": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]})
    buf = np.column_stack([lon - lon0, lat - lat0r, diff, va, vb]).astype(np.float32).tobytes()
    return meta, buf
