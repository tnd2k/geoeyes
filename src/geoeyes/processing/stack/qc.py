"""Quality check of a coregistered stack, to see the phase before any PS processing.

For every date against the reference, on the whole stack window, multilooked to about ``size`` pixels on the
longer side (looks chosen for square ground cells):

* the amplitude (dB, 2-98 % stretch);
* the interferogram ``slc[ref] · conj(slc[k])`` as stored (the geometric phase is already removed: what remains is
  topography left by the DEM, motion, atmosphere and noise), wrapped, after a Gaussian filter of the complex values
  (``ifg_sigma``, 2 multilooked pixels: the pattern shows through the noise of distributed scatterers);
* the coherence |Σ r·s*| / sqrt(Σ|r|² Σ|s|²) over the looks and a moving window of image cells, so that every
  estimate sums at least ``MIN_LOOKS`` pixels (a small stack keeps its full-resolution images);
* when the stack was phase-linked (``slc_linked``, the input of the point engine then), the same interferogram and
  coherence of the linked phase (``ifgL_`` / ``cohL_``), and the temporal coherence of the linking (``pl_tcoh.png``).

On a central crop at full resolution: the offset left between the reference and the date (coarse integer search,
then the sub-pixel residual), and the amplitude correlation. A good stack shows fringes or a smooth phase where
the coherence is high, offsets below a tenth of a pixel and amplitude correlations close to that of the best pair.

Written to ``<stack>/qc/``: ``amp_<date>.png``, ``ifg_<date>.png``, ``coh_<date>.png`` (and the linked ones) and
``qc.json``. What the unwrapping itself receives (the gridded, filtered phase of the selected points) is written by
the point engine to ``<ps_run>/qc/uw_<date>.png`` (``processing.ps.runner``).
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from geoeyes.io.stack import StackStore

BLOCK = 1024                     # lines read at a time
# fewest looks of a coherence estimate: one pixel gives |r·s*| / (|r||s|) = 1 whatever the data (a small stack sized
# to the 1200-pixel image got 1 x 1 looks), and 4 looks still give about 0.44 on pure noise; 16 looks (Sentinel-1:
# 2 x 8, about 28 x 30 m, the [sbas] cell) bring the noise floor down to about 0.22. The images keep their own looks;
# the coherence is summed over a moving window of image cells (``_coherence_window``) that reaches MIN_LOOKS.
MIN_LOOKS = 16


def _spacing(st: StackStore, ny: int) -> tuple[float, float]:
    """Azimuth and ground-range pixel spacing (m)."""
    a = st.attrs
    az = float(a.get("azimuth_pixel_spacing_m") or 1.0)
    rg = float(a.get("range_pixel_spacing_m") or 1.0)
    inc = math.radians(float(a.get("incidence_deg") or 40.0))
    if st.has("geometry_incidence"):
        g = st.open()["geometry_incidence"]
        inc = math.radians(float(np.nanmedian(g.isel(y=slice(ny // 2, ny // 2 + 1)).values)))
    return az, rg / max(math.sin(inc), 0.2)                 # ground range spacing


def _looks(az: float, gr: float, ny: int, nx: int, size: int) -> tuple[int, int]:
    """Looks of the images: about ``size`` pixels on the longer side, square ground cells."""
    cell = max(ny * az, nx * gr) / size                     # ground metres per output pixel
    cell = max(cell, az, gr)        # never below the coarser pixel: a small stack kept 1 x 1 looks, 14 x 3.7 m cells
    return max(int(round(cell / az)), 1), max(int(round(cell / gr)), 1)


def _coherence_window(ly: int, lx: int, az: float, gr: float) -> tuple[int, int]:
    """Moving window (image cells) of the coherence: at least MIN_LOOKS pixels, as square on the ground as the image
    cells allow (1 x 1 when the image cells already hold enough looks)."""
    cy, cx = ly * az, lx * gr                               # ground size of one image cell
    wy, wx = 1, 1
    while wy * wx * ly * lx < MIN_LOOKS:                    # grow the side that keeps the window closest to square
        if (wy + 1) * cy - wx * cx <= (wx + 1) * cx - wy * cy:
            wy += 1
        else:
            wx += 1
    return wy, wx


def _box(a: np.ndarray, wy: int, wx: int) -> np.ndarray:
    if wy == 1 and wx == 1:
        return a
    from scipy.ndimage import uniform_filter
    if np.iscomplexobj(a):
        return uniform_filter(a.real, (wy, wx), mode="nearest") + 1j * uniform_filter(a.imag, (wy, wx), mode="nearest")
    return uniform_filter(a, (wy, wx), mode="nearest")


def _ml(a: np.ndarray, ly: int, lx: int) -> np.ndarray:
    ny, nx = (a.shape[0] // ly) * ly, (a.shape[1] // lx) * lx
    return a[:ny, :nx].reshape(ny // ly, ly, nx // lx, lx).sum(axis=(1, 3))


def map_flips(attrs: dict) -> tuple[bool, bool]:
    """(rows, columns) to reverse so that a radar-grid image reads like a map, north up and east right: rows when
    the satellite flies north (ascending: the first line is the southernmost), columns when the range grows
    westward (descending right-looking, ascending left-looking). Without a heading: no flip."""
    h = attrs.get("heading_deg")
    if h is None:
        return False, False
    h = float(h)
    look = h + (90.0 if str(attrs.get("look_side", "right")).lower() == "right" else -90.0)
    return math.cos(math.radians(h)) > 0, math.sin(math.radians(look)) < 0


def _flips(st: StackStore, ds, attrs: dict) -> tuple[bool, bool]:
    """From the stack's own latitude / longitude grid when it has one (any sensor, any line order), else from the
    heading (``map_flips``)."""
    if st.has("geometry_lat") and st.has("geometry_lon"):
        la, lo = ds["geometry_lat"], ds["geometry_lon"]
        ny, nx = la.shape
        first, last = (float(np.nanmean(la.isel(y=i).values)) for i in (0, ny - 1))
        west, east = (float(np.nanmean(lo.isel(x=j).values)) for j in (0, nx - 1))
        if np.isfinite([first, last, west, east]).all():
            return first < last, west > east
    return map_flips(attrs)


def orientation_text(flip_rows: bool, flip_cols: bool) -> str:
    if not (flip_rows or flip_cols):
        return "radar geometry: rows = lines (azimuth), columns = samples (range)"
    turned = " and ".join(x for x, f in (("top-bottom", flip_rows), ("left-right", flip_cols)) if f)
    return (f"radar grid turned {turned} so that north is up and east right (not geocoded: tilted by the orbit "
            "heading)")


def _png(path: Path, img: np.ndarray, cmap: str, vmin: float, vmax: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.imsave(path, np.ma.masked_invalid(img), cmap=cmap, vmin=vmin, vmax=vmax)


def grid_map_flips(grid_ij: np.ndarray, lonlat: np.ndarray | None) -> tuple[bool, bool]:
    """(rows, columns) of an unwrapping grid to reverse so that its image reads like a map (north up, east right).
    The grid axes are the local frame of the points, which the load step may turn by about 180° - heading (StaMPS:
    ascending Sentinel-1 then has north at the first row and west at the last column). Measured from the points:
    ``grid_ij`` (n, 2) 1-based [row, col] cell of each point, ``lonlat`` (n, 2) its position. None: rows only."""
    if lonlat is None or len(lonlat) != len(grid_ij) or len(grid_ij) < 3:
        return True, False
    r, c = grid_ij[:, 0].astype(float), grid_ij[:, 1].astype(float)
    ll = np.asarray(lonlat, float)
    ok = np.isfinite(ll).all(axis=1)
    A = np.column_stack([np.ones(ok.sum()), r[ok], c[ok]])
    (_, lon_r, lon_c), *_ = np.linalg.lstsq(A, ll[ok, 0], rcond=None)
    (_, lat_r, lat_c), *_ = np.linalg.lstsq(A, ll[ok, 1], rcond=None)
    # image row 0 must be the northern edge: flip when north grows with the row; columns: flip when east falls
    north_by_row = lat_r if abs(lat_r) >= abs(lat_c) else lat_c
    east_by_col = lon_c if abs(lon_c) >= abs(lon_r) else lon_r
    return bool(north_by_row > 0), bool(east_by_col < 0)


def unwrap_grid_qc(grid, epoch_dates: list[str], master_ix: int, idx, out: Path, *, label: str = "",
                   lonlat: np.ndarray | None = None) -> dict:
    """The wrapped phase the point engine unwraps: its unwrapping grid (``processing.ps.unwrap.grid.UwGrid``, the
    filtered phase of the cells holding selected points, ``grid.ph[:, j]`` for epoch ``idx[j]``), north up and east
    right (``grid_map_flips`` with ``lonlat`` of the grid's points), written to ``out/uw_<date>.png`` with
    ``out/uw_qc.json``. Per interferogram, the share of neighbouring cell pairs whose phase differs by more than π/2:
    low on a smooth phase, near 0.5 on noise."""
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    gij = getattr(grid, "grid_ij", None)
    flip_rows, flip_cols = grid_map_flips(np.asarray(gij), lonlat) if gij is not None else (True, False)
    i, j = grid.ij[:, 0].astype(int), grid.ij[:, 1].astype(int)
    cell = np.full((grid.n_i, grid.n_j), -1, np.int64)
    cell[i, j] = np.arange(i.size)
    right = (cell[:, :-1] >= 0) & (cell[:, 1:] >= 0)
    down = (cell[:-1, :] >= 0) & (cell[1:, :] >= 0)
    pairs = [(cell[:, :-1][right], cell[:, 1:][right]), (cell[:-1, :][down], cell[1:, :][down])]
    for col, e in enumerate(np.asarray(idx)):
        if int(e) == master_ix:
            continue
        z = np.asarray(grid.ph[:, col])
        img = np.full((grid.n_i, grid.n_j), np.nan, np.float32)
        img[i, j] = np.angle(z)
        d = epoch_dates[int(e)]
        _png(out / f"uw_{d}.png", img[::-1 if flip_rows else 1, ::-1 if flip_cols else 1], "twilight", -np.pi, np.pi)
        jumps = np.concatenate([np.abs(np.angle(z[a] * np.conj(z[b]))) for a, b in pairs]) if i.size else np.array([])
        rows.append({"date": d, "jump_frac": round(float(np.mean(jumps > np.pi / 2)), 3) if jumps.size else None})
    summary = {"schema": "geoeyes.unwrap_qc/1", "created": datetime.now(UTC).isoformat(timespec="seconds"),
               "label": label, "reference_date": epoch_dates[master_ix], "cells": int(i.size),
               "grid_shape": [int(grid.n_i), int(grid.n_j)], "dates": rows,
               "image_flips": {"rows": flip_rows, "columns": flip_cols},
               "orientation": "unwrapping grid, north up and east right (tilted by the orbit heading)"}
    (out / "uw_qc.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


IFG_SIGMA = 2.0                  # Gaussian smoothing of the displayed interferograms, multilooked pixels


def smooth_phase(z: np.ndarray, sigma: float = IFG_SIGMA) -> np.ndarray:
    """Phase of the complex interferogram ``z`` after a Gaussian filter of its real and imaginary parts (smoothing
    the complex values, not the wrapped angles, so fringes are not broken at ±π); ``sigma`` = 0: the raw phase."""
    if sigma <= 0:
        return np.angle(z)
    from scipy.ndimage import gaussian_filter
    zz = np.nan_to_num(z)
    return np.angle(gaussian_filter(zz.real, sigma, mode="nearest") + 1j * gaussian_filter(zz.imag, sigma,
                                                                                            mode="nearest"))


def stack_qc(store: Path, out: Path | None = None, *, size: int = 1200, crop: int = 2048, progress=None,
             ifg_sigma: float = IFG_SIGMA) -> dict:
    """QC images and figures of the stack at ``store`` (a ``stack.zarr``); returns the summary (``qc.json``).
    ``ifg_sigma``: the Gaussian smoothing (multilooked pixels) of the interferogram images, so that the pattern shows
    through the noise of distributed scatterers; the coherence images and figures use the unsmoothed values."""
    from geoeyes.processing.stack.native.sicd_stack import coarse_offset
    from geoeyes.processing.stack.native.stripmap import residual_offset
    say = progress or (lambda msg: None)
    st = StackStore(store)
    ds = st.open()
    out = out or Path(store).parent / "qc"
    out.mkdir(parents=True, exist_ok=True)
    dates = [str(np.datetime64(d, "D")) for d in ds["date"].values]
    nt, ny, nx = ds["slc"].shape
    attrs = st.attrs
    ref_date = str(attrs.get("reference_date") or "")
    bp = ds["bperp"].values if "bperp" in ds else np.zeros(nt)
    ref = dates.index(ref_date) if ref_date in dates else int(np.argmin(np.abs(bp)))
    flip_rows, flip_cols = _flips(st, ds, attrs)

    def save(path: Path, img: np.ndarray, cmap: str, vmin: float, vmax: float) -> None:
        """An image of the radar grid turned toward the map: north up, east right (not geocoded)."""
        _png(path, img[::-1 if flip_rows else 1, ::-1 if flip_cols else 1], cmap, vmin, vmax)

    az, gr = _spacing(st, ny)
    ly, lx = _looks(az, gr, ny, nx, size)
    wy, wx = _coherence_window(ly, lx, az, gr)
    say(f"{nt} dates, {ny} x {nx} pixels, looks {ly} x {lx}, coherence window {wy} x {wx} cells")
    ny_ml, nx_ml = ny // ly, nx // lx
    y0 = (ny // ly) * ly

    # reference: power per look cell, and the central crop
    ref_pow = np.zeros((ny_ml, nx_ml))
    for r0 in range(0, y0, BLOCK - BLOCK % ly):
        r1 = min(r0 + BLOCK - BLOCK % ly, y0)
        r = ds["slc"].isel(date=ref, y=slice(r0, r1)).values
        ref_pow[r0 // ly:r1 // ly] = _ml(np.abs(r) ** 2, ly, lx)
    cy, cx, h = ny // 2, nx // 2, min(crop, ny, nx) // 2
    ref_crop = ds["slc"].isel(date=ref, y=slice(cy - h, cy + h), x=slice(cx - h, cx + h)).values

    def amp_corr(a, b):
        a, b = np.log1p(np.abs(a)), np.log1p(np.abs(b))
        a, b = a - a.mean(), b - b.mean()
        den = np.sqrt((a * a).sum() * (b * b).sum())
        return float((a * b).sum() / den) if den > 0 else 0.0     # an empty crop (no data): no correlation

    kh = ds.get("kh", None)
    linked = "slc_linked" in ds
    if linked:
        tc = ds["pl_temporal_coherence"].values if "pl_temporal_coherence" in ds else None
        if tc is not None:
            tcm = _ml(np.nan_to_num(tc[:y0]), ly, lx) / np.maximum(_ml(np.isfinite(tc[:y0]).astype(float), ly, lx), 1)
            save(out / "pl_tcoh.png", tcm, "viridis", 0.0, 1.0)
    rows = []
    t0 = np.datetime64(dates[0], "D")
    for k, d in enumerate(dates):
        say(f"{d} ({k + 1}/{nt})")
        cross = np.zeros((ny_ml, nx_ml), np.complex128)
        cross_l = np.zeros((ny_ml, nx_ml), np.complex128) if linked else None
        pw = np.zeros((ny_ml, nx_ml))
        for r0 in range(0, y0, BLOCK - BLOCK % ly):
            r1 = min(r0 + BLOCK - BLOCK % ly, y0)
            s = ds["slc"].isel(date=k, y=slice(r0, r1)).values
            pw[r0 // ly:r1 // ly] = _ml(np.abs(s) ** 2, ly, lx)
            if k != ref:
                r = ds["slc"].isel(date=ref, y=slice(r0, r1)).values
                cross[r0 // ly:r1 // ly] = _ml(r * np.conj(s), ly, lx)
                if linked:
                    rl = ds["slc_linked"].isel(date=ref, y=slice(r0, r1)).values
                    sl = ds["slc_linked"].isel(date=k, y=slice(r0, r1)).values
                    cross_l[r0 // ly:r1 // ly] = _ml(rl * np.conj(sl), ly, lx)
        amp = 10 * np.log10(pw / (ly * lx) + 1e-12)
        lo, hi = np.nanpercentile(amp, [2, 98])
        save(out / f"amp_{d}.png", amp, "gray", lo, hi)
        row = {"date": d, "days": int((np.datetime64(d, "D") - t0).astype(int)), "reference": k == ref,
               "bperp_m": round(float(bp[k]), 1)}
        if k != ref:
            valid = (ref_pow > 0) & (pw > 0)                 # cells with no data (zero padding) are not 0 coherence
            ref_box, pw_box = _box(ref_pow, wy, wx), _box(pw, wy, wx)
            with np.errstate(invalid="ignore", divide="ignore"):
                norm = np.where(valid, np.sqrt(ref_box * pw_box), np.nan)
            coh = np.minimum(np.abs(_box(cross, wy, wx)) / norm, 1.0)
            save(out / f"ifg_{d}.png", smooth_phase(cross, ifg_sigma), "twilight", -np.pi, np.pi)
            save(out / f"coh_{d}.png", coh, "magma", 0.0, 1.0)
            if linked:
                coh_l = np.minimum(np.abs(_box(cross_l, wy, wx)) / norm, 1.0)   # slc_linked keeps |slc|
                save(out / f"ifgL_{d}.png", smooth_phase(cross_l, ifg_sigma), "twilight", -np.pi, np.pi)
                save(out / f"cohL_{d}.png", coh_l, "magma", 0.0, 1.0)
                row["coherence_linked_mean"] = round(float(np.nanmean(coh_l)), 3)
            sec_crop = ds["slc"].isel(date=k, y=slice(cy - h, cy + h), x=slice(cx - h, cx + h)).values
            dl, dsm, _n_win = coarse_offset(ref_crop, sec_crop, win=min(1024, 2 * h))
            fl, fs, _n_tiles = residual_offset(ref_crop, sec_crop) if not (dl or dsm) else (0.0, 0.0, 0)
            khc = float(np.nanmedian(np.abs(kh.isel(date=k, y=slice(cy - 64, cy + 64), x=slice(cx - 64, cx + 64))
                                            .values))) if kh is not None else 0.0
            row.update({"coherence_mean": round(float(np.nanmean(coh)), 3),
                        "coherence_p90": round(float(np.nanpercentile(coh, 90)), 3),
                        "height_of_ambiguity_m": round(2 * math.pi / khc, 2) if khc > 0 else None,
                        "offset_lines": round(float(dl + fl), 3), "offset_samples": round(float(dsm + fs), 3),
                        "amplitude_corr": round(amp_corr(ref_crop, sec_crop), 3)})
        rows.append(row)
    summary = {"schema": "geoeyes.stack_qc/1", "stack": Path(store).parent.name,
               "created": datetime.now(UTC).isoformat(timespec="seconds"), "reference_date": dates[ref],
               "shape": [int(ny), int(nx)], "looks": [ly, lx], "coherence_window": [wy, wx], "min_looks": MIN_LOOKS,
               "image_shape": [int(ny_ml), int(nx_ml)],
               "ifg_smoothing_sigma_px": ifg_sigma,
               "crop": [int(cy - h), int(cy + h), int(cx - h), int(cx + h)], "dates": rows, "linked": linked,
               "image_flips": {"rows": flip_rows, "columns": flip_cols},
               "orientation": orientation_text(flip_rows, flip_cols)}
    (out / "qc.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
