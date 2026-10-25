"""COSMO-SkyMed SCS_B / SCS_U reader (HDF5, zero-Doppler slant-range geometry).

Times in the file are seconds since the root attribute ``Reference UTC``. Image ``S01/SBI`` is
(lines, samples, 2) int16 (I, Q); lines run early→late, columns near→far. The four corner
coordinates of ``SBI`` serve as tie points for geocoding.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np

from geoeyes.core.errors import SensorError
from geoeyes.geometry.orbit import StateVectors
from geoeyes.sensors.base import C, DopplerPoly, RadarGrid, TiePoints, heading_from_orbit


def _s(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def find_h5(scene_dir: str | Path) -> Path:
    hits = sorted(Path(scene_dir).rglob("CSK*_SCS_*.h5"))
    if not hits:
        raise SensorError(f"{scene_dir}: no CSK SCS HDF5")
    return hits[0]


def read_metadata(h5_path: str | Path, swath: str = "S01") -> RadarGrid:
    with h5py.File(h5_path, "r") as f:
        a = f.attrs
        if _s(a.get("Product Type", b"")) not in ("SCS_B", "SCS_U"):
            raise SensorError(f"{h5_path}: product type {_s(a.get('Product Type'))} is not SCS")
        ref = datetime.strptime(_s(a["Reference UTC"])[:26], "%Y-%m-%d %H:%M:%S.%f")
        sbi = f[f"{swath}/SBI"]
        b = sbi.attrs
        lines, samples = int(sbi.shape[0]), int(sbi.shape[1])
        sv_t = [ref + timedelta(seconds=float(t)) for t in a["State Vectors Times"]]
        orbit = StateVectors.from_lists(sv_t, a["ECEF Satellite Position"], a["ECEF Satellite Velocity"])
        start = ref + timedelta(seconds=float(b["Zero Doppler Azimuth First Time"]))
        corners = [b[f"{k} Geodetic Coordinates"]
                   for k in ("Top Left", "Top Right", "Bottom Left", "Bottom Right")]
        grid = TiePoints(np.array([0.0, 0.0, lines - 1.0, lines - 1.0]),
                         np.array([0.0, samples - 1.0, 0.0, samples - 1.0]),
                         np.array([c[0] for c in corners]), np.array([c[1] for c in corners]))
        dop = DopplerPoly(float(a["Range Polynomial Reference Time"]),
                          tuple(float(x) for x in a["Centroid vs Range Time Polynomial"]))
        ati = float(b["Line Time Interval"])
        return RadarGrid(
            sensor="cosmo_skymed", scene_id=Path(h5_path).stem, sensing_start=start, azimuth_time_interval=ati,
            slant_range_time=float(b["Zero Doppler Range First Time"]),
            range_sampling_rate=1.0 / float(b["Column Time Interval"]),
            lines=lines, samples=samples, wavelength=float(a["Radar Wavelength"]), orbit=orbit,
            look_side=_s(a["Look Side"]).strip().lower(), pass_direction=_s(a["Orbit Direction"]).strip().lower(),
            heading_deg=heading_from_orbit(orbit, orbit.seconds(start) + lines / 2.0 * ati), grid=grid,
            doppler=dop, polarization=_s(f[swath].attrs.get("Polarisation", b"")),
            azimuth_pixel_spacing=float(b["Line Spacing"]),
            range_pixel_spacing=C / 2.0 * float(b["Column Time Interval"]))


def read_slc(h5_path: str | Path, window: tuple[int, int, int, int] | None = None, swath: str = "S01") -> np.ndarray:
    with h5py.File(h5_path, "r") as f:
        d = f[f"{swath}/SBI"]
        l0, l1, s0, s1 = window if window is not None else (0, d.shape[0], 0, d.shape[1])
        iq = d[l0:l1, s0:s1, :].astype(np.float32)
    return (iq[..., 0] + 1j * iq[..., 1]).astype(np.complex64)


__all__ = ["C", "find_h5", "read_metadata", "read_slc"]
