"""Capella SLC reader.

The SLC is focused by backprojection onto a slant plane with a zero Doppler-centroid polynomial,
i.e. zero-Doppler geometry: rows are azimuth lines (``first_line_time`` + row · ``delta_line_time``),
columns range samples (``range_to_first_sample`` + col · ``delta_range_sample``). State vectors are
the precise orbit delivered with the product. Capella can look left or right
(``collect.radar.pointing``).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from geoeyes.core.errors import SensorError
from geoeyes.core.geodesy import ecef_to_llh
from geoeyes.geometry.orbit import StateVectors
from geoeyes.sensors.base import C, RadarGrid, TiePoints, heading_from_orbit


def _t(s: str) -> datetime:
    """Capella timestamps carry nanoseconds and 'Z'; keep microseconds, drop tz (UTC)."""
    s = s.rstrip("Z")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s)


def find_files(scene_dir: str | Path) -> tuple[Path, Path]:
    d = Path(scene_dir)
    js = sorted(d.glob("CAPELLA_*_SLC_*_extended.json"))
    if not js:
        raise SensorError(f"{d}: no Capella SLC extended metadata")
    tif = js[0].with_name(js[0].name.replace("_extended.json", ".tif"))
    if not tif.exists():
        raise SensorError(f"{d}: missing {tif.name}")
    return tif, js[0]


def read_metadata(extended_json: str | Path) -> RadarGrid:
    meta = json.loads(Path(extended_json).read_text(encoding="utf-8"))
    c = meta["collect"]
    img, geom, radar = c["image"], c["image"]["image_geometry"], c["radar"]
    if geom.get("type") != "slant_plane":
        raise SensorError(f"{extended_json}: unsupported image geometry {geom.get('type')!r}")
    dc = np.asarray(geom.get("doppler_centroid_polynomial", {}).get("coefficients", [[0]]), float)
    if np.any(dc != 0):
        raise SensorError(f"{extended_json}: non-zero Doppler centroid polynomial (not zero-Doppler geometry)")
    sv = c["state"]["state_vectors"]
    orbit = StateVectors.from_lists([_t(s["time"]) for s in sv], [s["position"] for s in sv],
                                    [s["velocity"] for s in sv])
    start = _t(geom["first_line_time"])
    target = np.asarray(img["center_pixel"]["target_position"], float)
    lat_c, lon_c, _ = ecef_to_llh(target)
    rows, cols = int(img["rows"]), int(img["columns"])
    grid = TiePoints(np.array([rows / 2.0]), np.array([cols / 2.0]), np.atleast_1d(lat_c), np.atleast_1d(lon_c))
    t_mid = orbit.seconds(start) + rows / 2.0 * float(geom["delta_line_time"])
    return RadarGrid(
        sensor="capella", scene_id=Path(extended_json).name.replace("_extended.json", ""),
        sensing_start=start, azimuth_time_interval=float(geom["delta_line_time"]),
        slant_range_time=2.0 * float(geom["range_to_first_sample"]) / C,
        range_sampling_rate=C / (2.0 * float(geom["delta_range_sample"])),
        lines=rows, samples=cols, wavelength=C / float(radar["center_frequency"]), orbit=orbit,
        look_side=str(radar["pointing"]).lower(), pass_direction=str(c["state"]["direction"]).lower(),
        heading_deg=heading_from_orbit(orbit, t_mid), grid=grid,
        polarization=f"{radar.get('transmit_polarization', '')}{radar.get('receive_polarization', '')}",
        azimuth_pixel_spacing=float(img.get("pixel_spacing_row", 0.0)),
        range_pixel_spacing=float(geom["delta_range_sample"]))


def read_slc(tif: str | Path, window: tuple[int, int, int, int] | None = None) -> np.ndarray:
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(tif) as src:
        win = None if window is None else Window(window[2], window[0], window[3] - window[2], window[1] - window[0])
        data = src.read(1, window=win)
    if not np.iscomplexobj(data):
        raise SensorError(f"{tif}: expected complex data, got {data.dtype}")
    return data.astype(np.complex64, copy=False)
