"""G3.1 checks (gnss-insar-calibration.md §9.1): mexico_g3 against mexico_s1 v7 and the PS around each station.

Usage:  python gnss_g3.py <mexico_g3 product dir> <mexico_s1 v7 product dir>

Prints:
- the PS count within 100 m of ICMX, MMX1 and MXTX, and the distance from each station to the nearest PS;
- on 100 m cells shared by the two products, the correlation and the median difference of the LOS velocity
  (the larger AOI must not change the earlier result apart from the reference offset).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

STATIONS = {"ICMX": (-99.1709, 19.4056), "MMX1": (-99.0684, 19.4317), "MXTX": (-98.8763, 19.5396)}
CELL_M = 100.0


def load(product: Path) -> dict[str, np.ndarray]:
    t = pq.read_table(product / "points.parquet", columns=["lon", "lat", "vel_los_mm_yr"])
    return {c: t.column(c).to_numpy() for c in t.column_names}


def metres(lon, lat, lon0, lat0):
    k = 111_320.0
    return (lon - lon0) * k * np.cos(np.radians(lat0)), (lat - lat0) * k


def cell_medians(p: dict, lon0: float, lat0: float) -> dict[tuple[int, int], float]:
    x, y = metres(p["lon"], p["lat"], lon0, lat0)
    ix, iy = np.floor(x / CELL_M).astype(np.int64), np.floor(y / CELL_M).astype(np.int64)
    key = ix * 1_000_000 + iy
    order = np.argsort(key, kind="stable")
    k, v = key[order], p["vel_los_mm_yr"][order]
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    meds = np.array([np.median(s) for s in np.split(v, starts[1:])])
    return dict(zip(k[starts].tolist(), meds.tolist()))


def main(g3_dir: str, v7_dir: str) -> None:
    g3, v7 = load(Path(g3_dir)), load(Path(v7_dir))
    print(f"points: mexico_g3 {len(g3['lon']):,}  mexico_s1 v7 {len(v7['lon']):,}")

    print("\nPS around the stations (mexico_g3)")
    for site, (lon, lat) in STATIONS.items():
        x, y = metres(g3["lon"], g3["lat"], lon, lat)
        d = np.hypot(x, y)
        n = int((d <= 100).sum())
        print(f"  {site}: {n:4d} PS within 100 m, nearest {d.min():7.1f} m, "
              f"median velocity {np.median(g3['vel_los_mm_yr'][d <= 100]) if n else float('nan'):8.1f} mm/yr")

    lon0, lat0 = -99.0, 19.4
    a, b = cell_medians(g3, lon0, lat0), cell_medians(v7, lon0, lat0)
    common = sorted(set(a) & set(b))
    va, vb = np.array([a[k] for k in common]), np.array([b[k] for k in common])
    r = np.corrcoef(va, vb)[0, 1]
    diff = va - vb
    slope = np.polyfit(vb, va, 1)
    print(f"\nshared 100 m cells: {len(common):,}")
    print(f"  correlation {r:.4f}   g3 = {slope[0]:.3f} x v7 + {slope[1]:.1f} mm/yr")
    print(f"  difference g3 - v7: median {np.median(diff):.1f}, 1.48*MAD "
          f"{1.4826 * np.median(np.abs(diff - np.median(diff))):.1f} mm/yr")


if __name__ == "__main__":
    main(*sys.argv[1:3])
