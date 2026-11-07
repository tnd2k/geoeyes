"""ICEYE SLC-COG reader (ICEYE processor >= 1.14, the format of the ICEYE Open Data catalog).

The GeoTIFF holds two uint16 bands, ``AMPLITUDE`` and ``PHASE``, each with a GDAL scale / offset (phase: -π..π);
the complex sample is ``amplitude · exp(j · phase)``. The raster is stored ``shadows-down``: TIFF rows are range
samples (near -> far, spacing ``sar:pixel_spacing_range`` from ``iceye:range_near``) and TIFF columns are azimuth
lines (early -> late, one per ``1 / iceye:processing_prf`` from ``iceye:zero_doppler_start_datetime``). The reader
transposes, so the ``RadarGrid`` and ``read_slc`` use the GeoEyes convention (lines = azimuth, samples = range).

Metadata: the STAC item ``*_SLC.json`` next to the TIFF (the same properties are in the TIFF tag
``ICEYE_PROPERTIES``). Zero-Doppler grid; the Doppler centroid polynomial (Hz, in two-way range time from the
first sample) is kept for the deramping of the resampling. The RPC model of the product gives the tie points.

A scene cut to an AOI by ``geoeyes.opendata.fetch`` carries ``geoeyes:crop`` (``row0``, ``col0`` of the cut in
the original TIFF): the grid starts at that range sample / azimuth line.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from geoeyes.core.errors import SensorError
from geoeyes.geometry.orbit import StateVectors
from geoeyes.sensors.base import C, DopplerPoly, RadarGrid, TiePoints, heading_from_orbit


def _t(s: str) -> datetime:
    """ISO timestamp with 'Z' (UTC) -> naive UTC datetime, microseconds kept."""
    s = s.rstrip("Z")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s)


def find_files(scene_dir: str | Path) -> tuple[Path, Path]:
    d = Path(scene_dir)
    js = sorted(d.glob("ICEYE_*_SLC.json"))
    if not js:
        raise SensorError(f"{d}: no ICEYE SLC-COG metadata (ICEYE_*_SLC.json)")
    tif = js[0].with_suffix(".tif")
    if not tif.exists():
        raise SensorError(f"{d}: missing {tif.name}")
    return tif, js[0]


def properties(meta_json: str | Path) -> dict:
    return json.loads(Path(meta_json).read_text(encoding="utf-8"))["properties"]


# RPC00B term order (GDAL / NITF): L = longitude, P = latitude, H = height, all normalised
def _rpc_terms(L, P, H):
    return np.stack([np.ones_like(L), L, P, H, L * P, L * H, P * H, L * L, P * P, H * H, P * L * H, L ** 3, L * P * P,
                     L * H * H, L * L * P, P ** 3, P * H * H, L * L * H, P * P * H, H ** 3])


def rpc_to_tiff(p: dict, lat, lon, h) -> tuple[np.ndarray, np.ndarray]:
    """TIFF (row, col) of ground points from the product's RPC model, in the (cropped) file's pixels."""
    r = p["iceye:rpc"]
    L = (np.asarray(lon, float) - r["long_off"]) / r["long_scale"]
    P = (np.asarray(lat, float) - r["lat_off"]) / r["lat_scale"]
    H = (np.asarray(h, float) - r["height_off"]) / r["height_scale"]
    t = _rpc_terms(L, P, H)
    row = (np.tensordot(r["line_num_coeff"], t, 1) / np.tensordot(r["line_den_coeff"], t, 1)) * r["line_scale"] \
        + r["line_off"]
    col = (np.tensordot(r["samp_num_coeff"], t, 1) / np.tensordot(r["samp_den_coeff"], t, 1)) * r["samp_scale"] \
        + r["samp_off"]
    crop = p.get("geoeyes:crop") or {}
    return row - crop.get("row0", 0), col - crop.get("col0", 0)


def read_metadata(meta_json: str | Path) -> RadarGrid:
    p = properties(meta_json)
    if p.get("sar:product_type") != "SLC-COG":
        raise SensorError(f"{meta_json}: product type {p.get('sar:product_type')!r} is not SLC-COG")
    if p.get("iceye:orientation") != "shadows-down":
        raise SensorError(f"{meta_json}: unsupported raster orientation {p.get('iceye:orientation')!r}")
    if p.get("iceye:coordinate_frame", "ecef") != "ecef":
        raise SensorError(f"{meta_json}: state vectors not in ECEF")
    sv = p["iceye:orbit_states"]
    orbit = StateVectors.from_lists([_t(s["time"]) for s in sv], [s["position"] for s in sv],
                                    [s["velocity"] for s in sv])
    crop = p.get("geoeyes:crop") or {}
    cols, rows = int(p["proj:shape"][0]), int(p["proj:shape"][1])        # ICEYE lists (width, height)
    lines, samples = int(crop.get("cols", cols)), int(crop.get("rows", rows))
    ati = 1.0 / float(p["iceye:processing_prf"])
    dr = float(p["sar:pixel_spacing_range"])
    start = _t(p["iceye:zero_doppler_start_datetime"]) + timedelta(seconds=crop.get("col0", 0) * ati)
    tau0 = 2.0 * (float(p["iceye:range_near"]) + crop.get("row0", 0) * dr) / C
    # Doppler centroid: ICEYE gives one polynomial per time, in range time from the first sample of the full image
    dc = np.asarray(p.get("iceye:doppler_centroid_coeffs") or [[0.0]], float)
    doppler = DopplerPoly(2.0 * float(p["iceye:range_near"]) / C, tuple(np.median(dc, axis=0)))
    ring = np.asarray(json.loads(Path(meta_json).read_text(encoding="utf-8"))["geometry"]["coordinates"][0], float)
    h = float(p.get("iceye:average_scene_height", 0.0))
    row, col = rpc_to_tiff(p, ring[:, 1], ring[:, 0], np.full(len(ring), h))
    grid = TiePoints(col, row, ring[:, 1], ring[:, 0])
    pol = (p.get("sar:polarizations") or [""])[0]
    return RadarGrid(
        sensor="iceye", scene_id=Path(meta_json).name.removesuffix("_SLC.json"), sensing_start=start,
        azimuth_time_interval=ati, slant_range_time=tau0, range_sampling_rate=C / (2.0 * dr),
        lines=lines, samples=samples, wavelength=C / float(p["sar:center_frequency"]), orbit=orbit,
        look_side=str(p["sar:observation_direction"]).lower(), pass_direction=str(p["sat:orbit_state"]).lower(),
        heading_deg=heading_from_orbit(orbit, orbit.seconds(start) + lines / 2.0 * ati), grid=grid,
        doppler=doppler, polarization=pol, azimuth_pixel_spacing=float(p["sar:pixel_spacing_azimuth"]),
        range_pixel_spacing=dr)


def _bands(src) -> tuple[int, int]:
    names = [str(src.tags(i).get("NAME", "")).upper() for i in (1, 2)]
    if names != ["AMPLITUDE", "PHASE"]:
        raise SensorError(f"{src.name}: expected bands AMPLITUDE, PHASE, got {names}")
    return 1, 2


def read_slc(tif: str | Path, window: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Complex64 (lines = azimuth, samples = range); ``window`` (l0, l1, s0, s1) in that convention."""
    import warnings

    import rasterio
    from rasterio.errors import NotGeoreferencedWarning
    from rasterio.windows import Window
    with warnings.catch_warnings():                      # a cut scene has no georeferencing (radar geometry)
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        src = rasterio.open(tif)
    with src:
        ba, bp = _bands(src)
        l0, l1, s0, s1 = window if window is not None else (0, src.width, 0, src.height)
        win = Window(l0, s0, l1 - l0, s1 - s0)             # col_off = azimuth line, row_off = range sample
        amp = src.read(ba, window=win).astype(np.float32) * src.scales[ba - 1] + src.offsets[ba - 1]
        pha = src.read(bp, window=win).astype(np.float32) * src.scales[bp - 1] + src.offsets[bp - 1]
    return (amp * np.exp(1j * pha)).T.astype(np.complex64)


__all__ = ["find_files", "properties", "read_metadata", "read_slc", "rpc_to_tiff"]
