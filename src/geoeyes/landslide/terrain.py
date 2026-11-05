"""Terrain derivatives on a study grid (docs/en/research/landslide-susceptibility.md §5 L2).

The DEM is sampled once at the cell centres of a ``ml.layers.Grid`` (bilinear), with a margin around the study area
so that the windows and the catchments do not stop at its edge; every derivative is computed on that raster
(rows go north, spacing ``cell_m``) and cut back to the study grid:

    slope_deg, aspect_sin (eastness of the downslope direction), aspect_cos (northness)
    profile_curv                 Zevenbergen & Thorne (1987), 1/100 m, along the slope: > 0 convex (the slope steepens
                                 downslope, a hilltop), < 0 concave (it eases, a footslope)
    plan_curv                    across the slope: > 0 laterally concave, flow converges (hollows), < 0 laterally
                                 convex, flow diverges (spurs)
    tpi_150, tpi_500             height − mean height within a square of side 2r + 1 cell (m)
    relief_300                   max − min height within a 300 m square (m)
    flow_acc_km2                 D8 contributing area after priority-flood filling with an epsilon (Barnes et al. 2014)
    twi                          ln(a / tan β), a = contributing area per unit contour width (m), β ≥ 0.1°
    dist_stream_m                distance to a cell draining ≥ ``stream_km2`` (and the 0.1 / 1 km² variants)

Hillslope scale (L3b.2):

    slope_s90                    slope of the DEM smoothed over 90 m (box filter)
    profile_curv_s150, plan_curv_s150   curvatures of the DEM smoothed over 150 m
    hand_m                       height above the nearest drainage: above the first cell draining ≥ ``stream_km2``
                                 on the D8 path (Rennó et al. 2008)
    upslope_slope_deg            mean slope of the contributing area (D8, the cell included)
    spi                          stream power index ln(a · tan β)
    tpi_1000, relief_1000        position and relief at 1 km
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from geoeyes.ml.layers import M_PER_DEG_LAT, Grid

OFF8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
STREAM_KM2 = (0.5, 0.1, 1.0)            # the first one is the default (plan §7), the others its sensitivity
MARGIN_M = 3000.0


def padded_grid(grid: Grid, margin_m: float = MARGIN_M) -> tuple[Grid, int, int]:
    """A grid with the same cells as ``grid`` grown by ``margin_m``; returns it and the column / row offset of
    ``grid`` inside it."""
    dlon, dlat = margin_m / grid.kx_m, margin_m / M_PER_DEG_LAT
    w, s, e, n = grid.bounds
    big = Grid([w - dlon, s - dlat, e + dlon, n + dlat], grid.cell_m, grid.lat0)
    return big, grid.x0 - big.x0, grid.y0 - big.y0


def raster(grid: Grid, values: np.ndarray) -> np.ndarray:
    return np.asarray(values).reshape(grid.ny, grid.nx)


def crop(a: np.ndarray, grid: Grid, ox: int, oy: int) -> np.ndarray:
    return a[oy:oy + grid.ny, ox:ox + grid.nx].ravel()


def zevenbergen_thorne(h: np.ndarray, d: float) -> dict[str, np.ndarray]:
    """Slope, aspect and curvatures of a raster with rows going north (spacing ``d``)."""
    p = np.pad(h.astype(np.float64), 1, mode="edge")
    z5 = p[1:-1, 1:-1]
    zn, zs = p[2:, 1:-1], p[:-2, 1:-1]            # north (row + 1), south
    zw, ze = p[1:-1, :-2], p[1:-1, 2:]
    znw, zne, zsw, zse = p[2:, :-2], p[2:, 2:], p[:-2, :-2], p[:-2, 2:]
    dd = ((zw + ze) / 2 - z5) / d ** 2
    ee = ((zn + zs) / 2 - z5) / d ** 2
    ff = (-znw + zne + zsw - zse) / (4 * d ** 2)
    gx = (ze - zw) / (2 * d)                        # dz/dx (east)
    gy = (zn - zs) / (2 * d)                        # dz/dy (north)
    g2 = gx ** 2 + gy ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        prof = np.where(g2 > 0, -2 * (dd * gx ** 2 + ee * gy ** 2 + ff * gx * gy) / g2, 0.0)
        plan = np.where(g2 > 0, 2 * (dd * gy ** 2 + ee * gx ** 2 - ff * gx * gy) / g2, 0.0)
        norm = np.sqrt(g2)
        asin = np.where(norm > 0, -gx / norm, 0.0)    # downslope direction: −gradient
        acos = np.where(norm > 0, -gy / norm, 0.0)
    return {"slope_deg": np.degrees(np.arctan(norm)), "aspect_sin": asin, "aspect_cos": acos,
            "profile_curv": prof * 100, "plan_curv": plan * 100}


def tpi(h: np.ndarray, d: float, radius_m: float) -> np.ndarray:
    from scipy.ndimage import uniform_filter
    k = 2 * max(1, round(radius_m / d)) + 1
    return h - uniform_filter(h.astype(np.float64), size=k, mode="nearest")


def relief(h: np.ndarray, d: float, size_m: float) -> np.ndarray:
    from scipy.ndimage import maximum_filter, minimum_filter
    k = max(3, round(size_m / d) | 1)
    return maximum_filter(h, size=k, mode="nearest") - minimum_filter(h, size=k, mode="nearest")


def fill_depressions(h: np.ndarray, eps: float = 1e-3) -> np.ndarray:
    """Priority-flood from the edges with an epsilon (Barnes, Lehman & Mulla 2014): every cell drains to the edge
    through strictly lower cells."""
    ny, nx = h.shape
    z = h.astype(np.float64).ravel().copy()
    done = np.zeros(ny * nx, bool)
    heap: list[tuple[float, int]] = []
    edge = np.zeros((ny, nx), bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    for i in np.flatnonzero(edge.ravel()):
        done[i] = True
        heap.append((z[i], int(i)))
    heapq.heapify(heap)
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        zc, i = pop(heap)
        r, c = divmod(i, nx)
        for dr, dc in OFF8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < ny and 0 <= cc < nx:
                j = rr * nx + cc
                if not done[j]:
                    done[j] = True
                    if z[j] <= zc:
                        z[j] = zc + eps
                    push(heap, (z[j], j))
    return z.reshape(ny, nx)


def d8_receivers(zf: np.ndarray, d: float) -> np.ndarray:
    """Index of the steepest-descent neighbour of every cell (-1: none, an outlet on the edge)."""
    ny, nx = zf.shape
    p = np.pad(zf, 1, mode="constant", constant_values=np.inf)
    best = np.zeros((ny, nx))
    rec = np.full((ny, nx), -1, np.int64)
    rows, cols = np.indices((ny, nx))
    for dr, dc in OFF8:
        nb = p[1 + dr:1 + dr + ny, 1 + dc:1 + dc + nx]
        drop = (zf - nb) / (d * math.hypot(dr, dc))
        better = drop > best
        best = np.where(better, drop, best)
        rec = np.where(better, (rows + dr) * nx + (cols + dc), rec)
    return rec.ravel()


def flow_accumulation(zf: np.ndarray, rec: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """Number of cells draining through each cell (itself included), upstream first; with ``weights``, the sum of
    the weights of those cells."""
    acc = np.ones(zf.size) if weights is None else np.asarray(weights, np.float64).ravel().copy()
    for i in np.argsort(-zf.ravel(), kind="stable"):
        j = rec[i]
        if j >= 0:
            acc[j] += acc[i]
    return acc.reshape(zf.shape)


def height_above_drainage(h: np.ndarray, zf: np.ndarray, rec: np.ndarray, stream: np.ndarray) -> np.ndarray:
    """HAND: height of each cell above the first stream cell on its D8 path (downstream first; a path that leaves the
    raster without meeting a stream ends at its outlet)."""
    hf = h.ravel()
    st = stream.ravel()
    base = np.empty(hf.size)
    for i in np.argsort(zf.ravel(), kind="stable"):
        j = rec[i]
        base[i] = hf[i] if st[i] or j < 0 else base[j]
    return np.maximum(hf - base, 0.0).reshape(h.shape)


def terrain_layers(grid: Grid, dem, stream_km2=STREAM_KM2, margin_m: float = MARGIN_M,
                   progress=None) -> dict[str, np.ndarray]:
    """Every terrain layer at the cells of ``grid`` (``dem``: a ``geometry.dem.Dem`` covering the padded grid)."""
    from scipy.ndimage import distance_transform_edt
    say = progress or (lambda m: None)
    big, ox, oy = padded_grid(grid, margin_m)
    d = grid.cell_m
    h = raster(big, dem.orthometric(big.lat, big.lon))
    if np.isnan(h).any():
        h = np.where(np.isnan(h), np.nanmin(h), h)
    out = {"height_m": h}
    out.update(zevenbergen_thorne(h, d))
    out["tpi_150"] = tpi(h, d, 150.0)
    out["tpi_500"] = tpi(h, d, 500.0)
    out["relief_300"] = relief(h, d, 300.0)
    say(f"terrain: filling depressions on {big.nx} x {big.ny} cells")
    zf = fill_depressions(h)
    rec = d8_receivers(zf, d)
    acc = flow_accumulation(zf, rec)
    area_m2 = acc * d * d
    out["flow_acc_km2"] = area_m2 / 1e6
    tanb = np.tan(np.radians(np.maximum(out["slope_deg"], 0.1)))
    out["twi"] = np.log(area_m2 / d / tanb)
    for k, thr in enumerate(stream_km2):
        name = "dist_stream_m" if k == 0 else f"dist_stream_{str(thr).replace('.', 'p')}_m"
        out[name] = distance_transform_edt(area_m2 < thr * 1e6) * d
    out.update(hillslope_layers(h, zf, rec, acc, out["slope_deg"], d, stream_km2[0]))
    return {k: crop(v, grid, ox, oy).astype(np.float32) for k, v in out.items()}


GEOMORPHON_FLAT_DEG = 1.0
# Jasiewicz & Stepinski (2013), table 2: landform by (number of "−", number of "+") of the 8 directions
_GM = [  # rows: n_minus 0..8, columns: n_plus 0..8
    ["FL", "FL", "FL", "FS", "FS", "VL", "VL", "VL", "PT"],
    ["FL", "FL", "FS", "FS", "FS", "VL", "VL", "PT"],
    ["FL", "SH", "SL", "SL", "HL", "HL", "VL"],
    ["SH", "SH", "SL", "SL", "SL", "HL"],
    ["SH", "SH", "SP", "SL", "SL"],
    ["RI", "RI", "SP", "SP"],
    ["RI", "RI", "RI"],
    ["RI", "RI"],
    ["PK"]]
GEOMORPHON_CODES = {k: i for i, k in enumerate(("FL", "PK", "RI", "SH", "SP", "SL", "HL", "FS", "VL", "PT"))}


def _shift(a: np.ndarray, dr: int, dc: int, fill=np.nan) -> np.ndarray:
    """``a`` moved so that out[r, c] = a[r + dr, c + dc] (``fill`` outside)."""
    out = np.full(a.shape, fill, np.float64)
    ny, nx = a.shape
    r0, r1 = max(0, -dr), min(ny, ny - dr)
    c0, c1 = max(0, -dc), min(nx, nx - dc)
    if r0 < r1 and c0 < c1:
        out[r0:r1, c0:c1] = a[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
    return out


def geomorphons(h: np.ndarray, d: float, lookup_m: float,
                flat_deg: float = GEOMORPHON_FLAT_DEG) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Counts of the 8 directions in which the terrain rises ("+") and falls ("−") within ``lookup_m``, and the
    geomorphon class code (``GEOMORPHON_CODES``)."""
    n = max(1, round(lookup_m / d))
    t = math.tan(math.radians(flat_deg))
    plus = np.zeros(h.shape, np.int8)
    minus = np.zeros(h.shape, np.int8)
    hf = h.astype(np.float64)
    for dr, dc in OFF8:
        step = d * math.hypot(dr, dc)
        up = np.full(h.shape, -np.inf)
        down = np.full(h.shape, -np.inf)
        for k in range(1, n + 1):
            z = _shift(hf, dr * k, dc * k)
            g = (z - hf) / (step * k)
            up = np.fmax(up, g)
            down = np.fmax(down, -g)
        plus += ((up - down) > t).astype(np.int8)
        minus += ((down - up) > t).astype(np.int8)
    code = np.zeros(h.shape, np.int8)
    for m in range(9):
        for p in range(9 - m):
            code[(minus == m) & (plus == p)] = GEOMORPHON_CODES[_GM[m][p]]
    return plus, minus, code


def vrm(slope_deg: np.ndarray, asin: np.ndarray, acos: np.ndarray, size: int) -> np.ndarray:
    """Vector ruggedness (Sappington et al. 2007): 1 − |mean unit normal| over a ``size`` × ``size`` window."""
    from scipy.ndimage import uniform_filter
    s = np.radians(slope_deg)
    xy = np.sin(s)
    comp = [xy * asin, xy * acos, np.cos(s)]
    m = [uniform_filter(c, size, mode="nearest") for c in comp]
    return 1.0 - np.sqrt(m[0] ** 2 + m[1] ** 2 + m[2] ** 2)


def convergence_index(asin: np.ndarray, acos: np.ndarray) -> np.ndarray:
    """Köthe & Lehmeier (1993): mean over the 8 neighbours of the angle (deg) between the neighbour's downslope
    direction and the direction from it to the centre, minus 90: −90 = full convergence (a hollow), +90 = full
    divergence (a ridge)."""
    acc = np.zeros(asin.shape)
    for dr, dc in OFF8:
        ex, ny_ = -dc / math.hypot(dr, dc), -dr / math.hypot(dr, dc)     # neighbour -> centre (east, north)
        ax, ay = _shift(asin, dr, dc, 0.0), _shift(acos, dr, dc, 0.0)
        cos = np.clip(ax * ex + ay * ny_, -1, 1)
        acc += np.degrees(np.arccos(cos))
    return acc / 8 - 90.0


def flow_length_up(zf: np.ndarray, rec: np.ndarray, d: float) -> np.ndarray:
    """Longest D8 flow path from a divide to each cell (m): the slope length."""
    ny, nx = zf.shape
    length = np.zeros(zf.size)
    for i in np.argsort(-zf.ravel(), kind="stable"):
        j = rec[i]
        if j >= 0:
            ri, ci = divmod(i, nx)
            rj, cj = divmod(int(j), nx)
            length[j] = max(length[j], length[i] + d * math.hypot(ri - rj, ci - cj))
    return length.reshape(ny, nx)


def relative_position(h: np.ndarray, d: float, size_m: float) -> np.ndarray:
    """(h − min) / (max − min) within a square of ``size_m``: 0 valley floor, 1 crest."""
    from scipy.ndimage import maximum_filter, minimum_filter
    k = max(3, round(size_m / d) | 1)
    lo, hi = minimum_filter(h, size=k, mode="nearest"), maximum_filter(h, size=k, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(hi > lo, (h - lo) / (hi - lo), 0.5)


def extra_layers(grid: Grid, dem, stream_km2: float = STREAM_KM2[0], margin_m: float = MARGIN_M,
                 progress=None) -> dict[str, np.ndarray]:
    """The terrain families of L3c C3 at the cells of ``grid``: roughness, landform, position, erosion, scale."""
    from scipy.ndimage import uniform_filter
    say = progress or (lambda m: None)
    big, ox, oy = padded_grid(grid, margin_m)
    d = grid.cell_m
    h = raster(big, dem.orthometric(big.lat, big.lon))
    if np.isnan(h).any():
        h = np.where(np.isnan(h), np.nanmin(h), h)
    zt = zevenbergen_thorne(h, d)
    out: dict[str, np.ndarray] = {}
    say("C3: roughness")
    diffs = [np.abs(_shift(h, dr, dc) - h) for dr, dc in OFF8]
    out["tri_m"] = np.nanmean(np.stack(diffs), axis=0)
    out["vrm_150"] = vrm(zt["slope_deg"], zt["aspect_sin"], zt["aspect_cos"], 5)
    out["vrm_450"] = vrm(zt["slope_deg"], zt["aspect_sin"], zt["aspect_cos"], 15)
    say("C3: geomorphons 150 / 500 m")
    for lm in (150, 500):
        p, m, c = geomorphons(h, d, lm)
        out[f"geom_plus_{lm}"], out[f"geom_minus_{lm}"], out[f"geomorphon_{lm}"] = p, m, c
    out["convergence"] = convergence_index(zt["aspect_sin"], zt["aspect_cos"])
    say("C3: slope position and length")
    out["rsp_500"] = relative_position(h, d, 500.0)
    out["rsp_1000"] = relative_position(h, d, 1000.0)
    zf = fill_depressions(h)
    rec = d8_receivers(zf, d)
    acc = flow_accumulation(zf, rec)
    out["flow_length_up_m"] = flow_length_up(zf, rec, d)
    a = np.minimum(acc * d, 1e6)                     # specific catchment area (m), capped on the rivers
    sb = np.sin(np.radians(np.maximum(zt["slope_deg"], 0.1)))
    out["ls_factor"] = (a / 22.13) ** 0.4 * (sb / 0.0896) ** 1.3          # Moore & Burch (1986)
    say("C3: slope and curvature at 150 / 300 m")
    for k, name in ((5, "s150"), (11, "s300")):
        z = zevenbergen_thorne(uniform_filter(h.astype(np.float64), k, mode="nearest"), d)
        out[f"slope_{name}"] = z["slope_deg"]
        if name == "s300":
            out["profile_curv_s300"], out["plan_curv_s300"] = z["profile_curv"], z["plan_curv"]
    return {k: crop(v, grid, ox, oy).astype(np.float32) for k, v in out.items()}


def hillslope_layers(h, zf, rec, acc, slope, d: float, stream_km2: float) -> dict[str, np.ndarray]:
    """The hillslope-scale layers of L3b.2 on the padded raster."""
    from scipy.ndimage import uniform_filter
    out = {"slope_s90": zevenbergen_thorne(uniform_filter(h.astype(np.float64), 3, mode="nearest"), d)["slope_deg"]}
    s150 = zevenbergen_thorne(uniform_filter(h.astype(np.float64), 5, mode="nearest"), d)
    out["profile_curv_s150"], out["plan_curv_s150"] = s150["profile_curv"], s150["plan_curv"]
    area_m2 = acc * d * d
    out["hand_m"] = height_above_drainage(h, zf, rec, area_m2 >= stream_km2 * 1e6)
    out["upslope_slope_deg"] = flow_accumulation(zf, rec, slope) / acc
    out["spi"] = np.log(area_m2 / d * np.tan(np.radians(np.maximum(slope, 0.1))))
    out["tpi_1000"] = tpi(h, d, 1000.0)
    out["relief_1000"] = relief(h, d, 1000.0)
    return out
