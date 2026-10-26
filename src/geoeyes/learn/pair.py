"""One pair of a stack, step by step: the layers behind each step of the learning path
(docs/en/guide/learn-insar-pair.md).

The SLCs of a GeoEyes stack are coregistered *and flattened*: each secondary is stored as ``res · exp(j·geom)`` with
``geom = 4π/λ (R_sec − R_ref)``, the phase of the reference surface and of the DEM, so ``slc_i · conj(slc_j)`` is
already the differential interferogram. To show the raw interferogram of the classic chain, the geometric phase
of the pair is rebuilt from what the stack keeps:

* topography: ``kh · h`` (``kh`` = d geom / dh, rad per m, stored per date; ``h`` = DEM height per pixel);
* flat earth: on a surface of constant height, a change dr of slant range changes the look angle as a change
  dh = dr · cos θ of height does, so d geom / dr = kh · cos θ; integrated along range.

Sign convention (stack attribute ``phase_convention``): a range increase d from date i to date j adds +4πd/λ to
``slc_i · conj(slc_j)``; displacement toward the satellite = −φ·λ/4π.

Every layer is returned on the multilooked crop (float32, row-major, NaN = no data).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from geoeyes.core.errors import ConfigError, DataError
from geoeyes.io.stack import StackStore

LAYERS = ("amp1", "amp2", "raw", "flat", "after_flat", "dem", "topo", "diff", "coh", "diff_kept", "filt", "unw", "disp",
          "res_diff", "res_filt", "lat", "lon", "filt_ex", "unw_ex")
MAX_PIXELS = 4_000_000            # full-resolution crop read at most (two SLCs + geometry)
MAX_GRID = 700                    # multilooked side at most


@dataclass(frozen=True)
class PairParams:
    first: str                    # earlier date YYYY-MM-DD
    second: str                   # later date
    row0: int                     # crop, full-resolution radar pixels
    col0: int
    rows: int
    cols: int
    looks_az: int = 1
    looks_rg: int = 1
    coh_win: int = 5              # coherence window, multilooked pixels
    coh_thr: float = 0.3          # pixels below: left out of the filter, the unwrapping and the displacement
    alpha: float = 0.6            # Goldstein exponent
    fft: int = 32                 # Goldstein window, multilooked pixels
    passes: int = 1
    linked: bool = False          # phase-linked SLCs (slc_linked) instead of the SLCs
    ref_row: int = -1             # reference pixel of the unwrapped phase (multilooked grid), -1 = automatic
    ref_col: int = -1
    exercise: bool = False        # also unwrap the raw phase, flat-earth fringes included (an unwrapping exercise)


def _store(path: Path) -> StackStore:
    s = StackStore(path)
    if not s.exists():
        raise DataError(f"no stack at {path}")
    return s


def _dates(ds) -> list[str]:
    return [str(np.datetime64(d, "D")) for d in ds["date"].values]


def _ground_spacing(attrs: dict, inc_deg: float) -> tuple[float, float]:
    """(azimuth, ground range) pixel spacing in metres."""
    gr = float(attrs["range_pixel_spacing_m"]) / math.sin(math.radians(inc_deg))
    return float(attrs["azimuth_pixel_spacing_m"]), gr


@lru_cache(maxsize=8)
def _overview(path: str, mtime: float) -> dict:
    s = _store(Path(path))
    ds = s.open()
    a = s.attrs
    dates = _dates(ds)
    ny, nx = int(ds.sizes["y"]), int(ds.sizes["x"])
    inc = float(np.nanmedian(s.read("geometry_incidence", y=slice(ny // 2 - 8, ny // 2 + 8),
                                    x=slice(nx // 2 - 8, nx // 2 + 8))))
    az, gr = _ground_spacing(a, inc)
    bperp = [float(v) for v in ds["bperp"].values]
    ref = str(a.get("reference_date"))
    # default pair: the reference and the acquisition closest to it in time (best coherence for a first look)
    t = np.array(dates, dtype="datetime64[D]")
    ri = dates.index(ref) if ref in dates else 0
    others = [i for i in range(len(dates)) if i != ri]
    j = min(others, key=lambda i: (abs(int((t[i] - t[ri]).astype(int))), abs(bperp[i] - bperp[ri]))) if others else ri
    first, second = sorted([dates[ri], dates[j]])
    side_m = min(3000.0, ny * az, nx * gr)                      # a 3 km window, or the whole stack if smaller
    rows, cols = min(ny, int(side_m / az)), min(nx, int(side_m / gr))
    target = max(az, gr, side_m / 400)                          # about 400 multilooked pixels across
    extra = {}
    if s.has("coreg_residual"):
        extra["coreg_residual"] = [[float(v) for v in r] for r in s.read("coreg_residual")]
    if s.has("esd_shift"):
        extra["esd_shift"] = [float(v) for v in np.ravel(s.read("esd_shift"))]
    return {
        "stack_id": Path(path).parent.name, "sensor": a.get("sensor"), "track": a.get("track"),
        "pass_direction": a.get("pass_direction"), "look_side": a.get("look_side"),
        "wavelength_m": float(a["wavelength_m"]), "reference_date": ref, "dates": dates, "bperp_m": bperp,
        "shape": [ny, nx], "spacing_m": {"azimuth": az, "range_slant": float(a["range_pixel_spacing_m"]),
                                         "range_ground": gr},
        "incidence_deg": inc, "heading_deg": a.get("heading_deg"), "linked": s.has("slc_linked"),
        "default": {"first": first, "second": second, "row0": (ny - rows) // 2, "col0": (nx - cols) // 2,
                    "rows": rows, "cols": cols, "looks_az": max(1, round(target / az)),
                    "looks_rg": max(1, round(target / gr))},
        **extra,
    }


def _mtime(stack_path: Path) -> float:
    f = stack_path / "zarr.json"
    return f.stat().st_mtime if f.exists() else 0.0


def overview(stack_path: Path) -> dict:
    """Dates, baselines, pixel spacing and a sensible default pair and crop of a stack."""
    return _overview(str(stack_path), _mtime(stack_path))


@lru_cache(maxsize=4)
def _thumbnail(path: str, mtime: float, width: int) -> tuple[dict, bytes]:
    s = _store(Path(path))
    ds = s.open()
    ref = str(s.attrs.get("reference_date"))
    dates = _dates(ds)
    i = dates.index(ref) if ref in dates else 0
    ny, nx = int(ds.sizes["y"]), int(ds.sizes["x"])
    f = max(1, math.ceil(max(ny, nx) / width))
    power = np.zeros((ny // f, nx // f), np.float64)
    step = 512 - 512 % f or f
    for y0 in range(0, (ny // f) * f, step):                     # by blocks of rows: a whole SLC is large
        y1 = min(y0 + step, (ny // f) * f)
        b = s.read("slc", date=i, y=slice(y0, y1), x=slice(0, (nx // f) * f))
        p = (np.abs(b) ** 2).reshape((y1 - y0) // f, f, nx // f, f).mean(axis=(1, 3))
        power[y0 // f:y1 // f] = p
    db = 10 * np.log10(np.maximum(power, 1e-12)).astype(np.float32)
    return {"shape": list(db.shape), "factor": f, "date": dates[i]}, db.tobytes()


def thumbnail(stack_path: Path, width: int = 480) -> tuple[dict, bytes]:
    """Amplitude (dB) of the reference SLC of the whole stack, block-averaged to about ``width`` pixels, to pick
    the crop."""
    return _thumbnail(str(stack_path), _mtime(stack_path), width)


# ---------------------------------------------------------------- helpers
def multilook(a: np.ndarray, la: int, lr: int) -> np.ndarray:
    """Block mean over ``la`` × ``lr`` pixels (edges that do not fill a block are dropped)."""
    h, w = (a.shape[0] // la) * la, (a.shape[1] // lr) * lr
    return a[:h, :w].reshape(h // la, la, w // lr, lr).mean(axis=(1, 3))


def boxcar(a: np.ndarray, win: int) -> np.ndarray:
    from scipy.ndimage import uniform_filter
    if np.iscomplexobj(a):
        return uniform_filter(a.real, win, mode="nearest") + 1j * uniform_filter(a.imag, win, mode="nearest")
    return uniform_filter(a, win, mode="nearest")


def flat_earth_phase(kh: np.ndarray, inc_deg: np.ndarray, slant_range: np.ndarray) -> np.ndarray:
    """Phase of the constant-height surface along range (rad), 0 at the centre of the grid: ∫ kh·cosθ dr."""
    g = kh * np.cos(np.radians(inc_deg))
    dr = np.diff(slant_range, axis=1)
    steps = 0.5 * (g[:, 1:] + g[:, :-1]) * dr                   # trapezoid along each row
    phi = np.concatenate([np.zeros((g.shape[0], 1)), np.cumsum(steps, axis=1)], axis=1)
    # rows differ by the azimuth variation of kh only: tie them at the centre column, then centre the grid
    c = phi.shape[1] // 2
    phi -= phi[:, c:c + 1]
    return phi - phi[phi.shape[0] // 2, c]


def residues(phase: np.ndarray) -> np.ndarray:
    """Phase residues (±1) of a wrapped grid: the sum of the wrapped differences around each 2×2 loop / 2π, on the
    grid of loops (h − 1, w − 1). Unwrapping is ambiguous only where they are."""
    def w(x):
        return np.angle(np.exp(1j * x))
    p = phase
    loop = (w(p[:-1, 1:] - p[:-1, :-1]) + w(p[1:, 1:] - p[:-1, 1:]) + w(p[1:, :-1] - p[1:, 1:])
            + w(p[:-1, :-1] - p[1:, :-1]))
    r = np.rint(loop / (2 * np.pi))
    r[~np.isfinite(r)] = 0
    return r.astype(np.float32)


def fringe_rate(phase_c: np.ndarray, spacing: tuple[float, float]) -> float:
    """Dominant fringe frequency (fringes per km) of a complex grid, from the peak of its 2-D spectrum."""
    z = np.nan_to_num(phase_c / np.maximum(np.abs(phase_c), 1e-12))
    h, w = z.shape
    spec = np.abs(np.fft.fft2(z - z.mean())) ** 2
    spec[0, 0] = 0
    i, j = np.unravel_index(np.argmax(spec), spec.shape)
    fy = (i if i <= h // 2 else i - h) / (h * spacing[0])
    fx = (j if j <= w // 2 else j - w) / (w * spacing[1])
    return float(math.hypot(fy, fx) * 1000)


def _pad(a: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    out = np.zeros(shape, np.float32)
    out[:a.shape[0], :a.shape[1]] = a
    return out


# ---------------------------------------------------------------- the pair
def _check(p: PairParams, ov: dict) -> PairParams:
    ny, nx = ov["shape"]
    if p.first not in ov["dates"] or p.second not in ov["dates"] or p.first == p.second:
        raise ConfigError("choose two different dates of the stack")
    if p.rows * p.cols > MAX_PIXELS:
        raise ConfigError(f"crop too large ({p.rows} × {p.cols}); at most {MAX_PIXELS:,} pixels")
    la, lr = max(1, p.looks_az), max(1, p.looks_rg)
    if p.rows // la > MAX_GRID or p.cols // lr > MAX_GRID:
        raise ConfigError(f"multilooked grid larger than {MAX_GRID} pixels: increase the looks")
    if p.rows // la < 16 or p.cols // lr < 16:
        raise ConfigError("multilooked grid smaller than 16 pixels: decrease the looks or enlarge the crop")
    row0 = int(np.clip(p.row0, 0, max(0, ny - p.rows)))
    col0 = int(np.clip(p.col0, 0, max(0, nx - p.cols)))
    return PairParams(**{**p.__dict__, "row0": row0, "col0": col0, "rows": min(p.rows, ny), "cols": min(p.cols, nx),
                         "looks_az": la, "looks_rg": lr, "coh_win": max(1, p.coh_win),
                         "fft": max(8, int(p.fft)), "passes": max(0, int(p.passes))})


def pair_layers(stack_path: Path, params: PairParams) -> tuple[dict, dict[str, np.ndarray]]:
    """(meta, layers) of the pair: every step of the learning path on the multilooked crop."""
    return _pair(str(stack_path), _mtime(stack_path), json.dumps(params.__dict__, sort_keys=True))


@lru_cache(maxsize=6)
def _pair(path: str, mtime: float, key: str) -> tuple[dict, dict[str, np.ndarray]]:
    from geoeyes.processing.ps.unwrap.irls import irls_unwrap_weighted
    from geoeyes.processing.unwrap.goldstein import goldstein
    stack_path = Path(path)
    ov = overview(stack_path)
    p = _check(PairParams(**json.loads(key)), ov)
    s = _store(stack_path)
    i, j = ov["dates"].index(p.first), ov["dates"].index(p.second)
    win = {"y": slice(p.row0, p.row0 + p.rows), "x": slice(p.col0, p.col0 + p.cols)}
    var = "slc_linked" if p.linked and s.has("slc_linked") else "slc"
    s1 = s.read(var, date=i, **win).astype(np.complex64)
    s2 = s.read(var, date=j, **win).astype(np.complex64)
    kh = s.read("kh", date=j, **win).astype(np.float64) - s.read("kh", date=i, **win).astype(np.float64)
    geo = {k: s.read(f"geometry_{k}", **win).astype(np.float64)
           for k in ("hgt", "incidence", "slant_range", "lat", "lon")}
    la, lr = p.looks_az, p.looks_rg

    def ml(a):
        return multilook(a, la, lr)

    # ---- the two scenes and the differential interferogram (what the stack stores)
    pw1, pw2 = ml(np.abs(s1) ** 2), ml(np.abs(s2) ** 2)
    ifg = ml(s1 * np.conj(s2))
    # ---- the geometric phase of the pair, rebuilt (module docstring)
    kh_m, h_m = ml(kh), ml(geo["hgt"])
    flat = flat_earth_phase(kh_m, ml(geo["incidence"]), ml(geo["slant_range"]))
    topo = kh_m * h_m
    topo_c = topo - topo[topo.shape[0] // 2, topo.shape[1] // 2]
    raw = ifg * np.exp(1j * (flat + topo_c))
    after_flat = ifg * np.exp(1j * topo_c)
    # ---- coherence: |Σ s1 s2*| / sqrt(Σ|s1|² Σ|s2|²) over the looks and a coh_win window
    coh = np.abs(boxcar(ifg, p.coh_win)) / np.sqrt(np.maximum(boxcar(pw1, p.coh_win) * boxcar(pw2, p.coh_win),
                                                                1e-30))
    coh = np.clip(coh, 0, 1)
    # ---- the pixels kept from here on: coherence at or above the threshold of the coherence step
    keep = coh >= p.coh_thr
    if keep.sum() < 16:
        raise ConfigError(f"fewer than 16 pixels with coherence ≥ {p.coh_thr:g}: lower the threshold")
    # ---- Goldstein filter of the unit phasors (the amplitude would weight bright scatterers); the pixels left out
    # weigh nothing in the spectra
    unit = np.where(keep, ifg / np.maximum(np.abs(ifg), 1e-30), 0)
    filt = np.angle(goldstein(unit, min(p.fft, min(unit.shape)), p.alpha, p.passes)) if p.passes else np.angle(unit)
    filt = np.where(keep, filt, np.nan)
    # ---- unwrapping: GeoEyes IRLS (the 2-D solver of the PS chain) weighted by the coherence, no data where left out
    unw, rms = irls_unwrap_weighted(filt.astype(np.float32), (coh ** 2).astype(np.float32))
    unw = np.where(keep, unw.astype(np.float64), np.nan)
    good = keep & (coh >= np.quantile(coh[keep], 0.9))
    ref_val = np.nan
    if 0 <= p.ref_row < unw.shape[0] and 0 <= p.ref_col < unw.shape[1]:
        r0, c0 = p.ref_row, p.ref_col
        around = unw[max(0, r0 - 1):r0 + 2, max(0, c0 - 1):c0 + 2]
        ref_val = float(np.nanmedian(around)) if np.isfinite(around).any() else np.nan
        ref = {"kind": "pixel", "row": r0, "col": c0}
    if not np.isfinite(ref_val):                               # automatic, or a clicked pixel that was left out
        ref_val = float(np.median(unw[good]))
        ref = {"kind": "coherent median", "share": 0.1}
    unw -= ref_val
    # exercise: the same filter and solver on the raw phase, whose dense flat-earth fringes make the sawtooth visible
    filt_ex = unw_ex = np.full(ifg.shape, np.nan)
    if p.exercise:
        unit_raw = np.where(keep, raw / np.maximum(np.abs(raw), 1e-30), 0)
        filt_ex = np.angle(goldstein(unit_raw, min(p.fft, min(unit_raw.shape)), p.alpha, max(1, p.passes)))
        filt_ex = np.where(keep, filt_ex, np.nan)
        unw_ex = irls_unwrap_weighted(filt_ex.astype(np.float32), (coh ** 2).astype(np.float32))[0].astype(np.float64)
        unw_ex = np.where(keep, unw_ex, np.nan)
        unw_ex -= float(np.median(unw_ex[good]))
    lam = ov["wavelength_m"]
    disp = -unw * lam / (4 * np.pi) * 1000                     # mm, + toward the satellite
    diff_kept = np.where(keep, np.angle(ifg), np.nan)
    rd, rf = residues(diff_kept), residues(filt)
    shape = ifg.shape
    layers = {
        "amp1": 10 * np.log10(np.maximum(pw1, 1e-30)), "amp2": 10 * np.log10(np.maximum(pw2, 1e-30)),
        "raw": np.angle(raw), "flat": np.angle(np.exp(1j * flat)), "after_flat": np.angle(after_flat),
        "dem": h_m, "topo": np.angle(np.exp(1j * topo_c)), "diff": np.angle(ifg), "coh": coh, "diff_kept": diff_kept,
        "filt": filt,
        "unw": unw, "disp": disp, "res_diff": _pad(rd, shape), "res_filt": _pad(rf, shape),
        "lat": ml(geo["lat"]), "lon": ml(geo["lon"]), "filt_ex": filt_ex, "unw_ex": unw_ex,
    }
    layers = {k: np.asarray(layers[k], np.float32) for k in LAYERS}
    spacing = (ov["spacing_m"]["azimuth"] * la, ov["spacing_m"]["range_ground"] * lr)
    t1, t2 = np.datetime64(p.first), np.datetime64(p.second)
    days = int((t2 - t1).astype(int))
    b = ov["bperp_m"][j] - ov["bperp_m"][i]
    kh_c = float(np.median(kh_m))
    inc_c = float(np.median(ml(geo["incidence"])))
    meta = {
        "params": p.__dict__, "shape": list(shape), "layers": list(LAYERS), "variable": var,
        "spacing_m": {"azimuth": spacing[0], "range_ground": spacing[1]},
        "pixel_m": {"azimuth": ov["spacing_m"]["azimuth"], "range_ground": ov["spacing_m"]["range_ground"]},
        "wavelength_m": lam, "days": days, "bperp_m": b,
        "height_of_ambiguity_m": float(2 * np.pi / abs(kh_c)) if kh_c else None,
        "kh_rad_per_m": kh_c, "incidence_deg": inc_c,
        # flat earth: d geom / dr = kh·cosθ per m of slant range, dr = sinθ per m of ground range
        "flat_fringes_per_km_range": float(abs(kh_c) * math.cos(math.radians(inc_c)) * math.sin(math.radians(inc_c))
                                           / (2 * np.pi) * 1000),
        "fringes_per_km": {"raw": fringe_rate(raw, spacing), "after_flat": fringe_rate(after_flat, spacing),
                           "diff": fringe_rate(ifg, spacing)},
        "dem_range_m": [float(np.nanmin(h_m)), float(np.nanmax(h_m))],
        "topo_range_rad": float(np.nanmax(topo) - np.nanmin(topo)),
        "coherence_median": float(np.median(coh)),
        "kept_share": float(keep.mean()),
        "residues": {"diff": int(np.abs(rd).sum()), "filt": int(np.abs(rf).sum())},
        "unwrap": {"method": "IRLS (GeoEyes, weights = coherence²)", "pcg_rms": float(rms), "reference": ref},
        "mm_per_fringe": lam / 2 * 1000,
        "bounds": [float(np.nanmin(layers["lon"])), float(np.nanmin(layers["lat"])), float(np.nanmax(layers["lon"])),
                   float(np.nanmax(layers["lat"]))],
        "stats": {k: [float(np.nanmin(v)), float(np.nanmax(v))] + [float(x) for x in np.nanpercentile(v, [2, 98])]
                  for k, v in layers.items() if np.isfinite(v).any()},
    }
    return meta, layers


# ---------------------------------------------------------------- velocity from the stack
def points_in_crop(project_root: Path, stack_path: Path, params: PairParams, product_id: str | None = None,
                   limit: int = 20000) -> dict:
    """PS of the project's product over the crop, placed on the multilooked grid (nearest pixel by lat/lon)."""
    import pyarrow.parquet as pq
    from scipy.spatial import cKDTree
    ov = overview(stack_path)
    meta, layers = pair_layers(stack_path, params)
    prod = _product_for(project_root, ov.get("track"), product_id)
    if prod is None:
        return {"product": None, "points": []}
    w, s, e, n = meta["bounds"]
    t = pq.read_table(prod / "points.parquet", columns=["point_uid", "lon", "lat", "vel_los_mm_yr"],
                      filters=[("lon", ">=", w), ("lon", "<=", e), ("lat", ">=", s), ("lat", "<=", n)]).to_pandas()
    if len(t) > limit:
        t = t.sample(limit, random_state=0)
    lat, lon = layers["lat"], layers["lon"]
    k = math.cos(math.radians(float(np.nanmedian(lat))))
    tree = cKDTree(np.column_stack([lon.ravel() * k, lat.ravel()]))
    d, idx = tree.query(np.column_stack([t.lon.to_numpy() * k, t.lat.to_numpy()]))
    pix = max(meta["spacing_m"]["azimuth"], meta["spacing_m"]["range_ground"]) / 111_000
    inside = d <= 1.5 * pix
    rows, cols = np.divmod(idx[inside], lat.shape[1])
    v = t.vel_los_mm_yr.to_numpy()[inside]
    return {"product": prod.name, "fields": ["row", "col", "vel"], "uids": t.point_uid.to_numpy()[inside].tolist(),
            "rows": rows.tolist(), "cols": cols.tolist(), "vel": [round(float(x), 2) for x in v],
            "vel_range": [float(v.min()), float(v.max())] if v.size else None}


def point_series(project_root: Path, product_id: str, uid: str) -> dict:
    """Series of one PS and its linear fit (the velocity of the product)."""
    import pyarrow.parquet as pq
    prod = project_root / "products" / product_id
    pts = pq.read_table(prod / "points.parquet", columns=["point_uid", "vel_los_mm_yr", "vel_std_mm_yr"],
                        filters=[("point_uid", "==", uid)]).to_pandas()
    ts = pq.read_table(prod / "timeseries.parquet", columns=["date", "disp_mm"],
                       filters=[("point_uid", "==", uid)]).to_pandas().sort_values("date")
    if ts.empty:
        raise DataError(f"no series for point {uid}")
    dates = np.array(ts["date"].to_numpy(), dtype="datetime64[D]")
    y = ts["disp_mm"].to_numpy(np.float64)
    y = y - y[0]
    tyr = (dates - dates[0]).astype(float) / 365.25
    coef = np.polyfit(tyr, y, 1)
    return {"uid": uid, "dates": [str(d) for d in dates], "disp_mm": [round(float(v), 2) for v in y],
            "fit_mm": [round(float(v), 2) for v in np.polyval(coef, tyr)], "vel_mm_yr": float(coef[0]),
            "vel_product_mm_yr": float(pts.vel_los_mm_yr.iloc[0]) if len(pts) else None,
            "vel_std_mm_yr": float(pts.vel_std_mm_yr.iloc[0]) if len(pts) else None}


def _product_for(project_root: Path, track: str | None, product_id: str | None) -> Path | None:
    d = project_root / "products"
    if product_id:
        return d / product_id if (d / product_id / "points.parquet").exists() else None
    cands = [p for p in d.glob("*") if (p / "points.parquet").exists() and (not track or track in p.name)]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None
