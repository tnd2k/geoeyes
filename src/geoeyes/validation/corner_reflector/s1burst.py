"""One Sentinel-1 acquisition of the workspace archive (ASF burst folder) seen from a ground point.

Same interface as the legacy SAFE / DIMAP reader (``locate``, ``swath``, ``read_chip``,
``beta_nought_lut``, ``geocode``), on the native burst files: per burst its GeoTIFF and the ASF metadata
XML (annotation for timing and orbit, calibration for the beta-nought LUT). Lines and samples are those of
the burst raster. Range-Doppler: the zero-Doppler time and slant range of a point give its (line, sample).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

import numpy as np

from geoeyes.core.geodesy import enu_basis, llh_to_ecef
from geoeyes.sensors.sentinel1.burst import BurstMetadata, read_calibration, read_metadata, read_slc

C = 299792458.0


@dataclass
class Location:
    """Where a ground point falls in one burst of the acquisition."""
    swath: str
    burst: int                 # ASF burst index in the subswath
    line: float                # burst raster line
    sample: float
    los_azimuth_deg: float     # ground -> satellite
    los_elevation_deg: float
    incidence_deg: float
    slant_range_m: float


@dataclass
class BurstSwath:
    """One burst raster (the legacy reader's "swath": what lines and samples refer to)."""
    name: str
    burst: int
    meta: BurstMetadata
    tiff: Path
    xml: Path

    @property
    def range_spacing(self) -> float:
        return self.meta.range_pixel_spacing

    @property
    def azimuth_spacing(self) -> float:
        return self.meta.azimuth_pixel_spacing


class BurstScene:
    """An acquisition folder ``<SLC name>/`` holding ``bursts.json``, ``IWx_POL_<index>.tiff`` and the XML."""

    def __init__(self, folder: str | Path, polarization: str = "VV", orbits=None):
        self.path = Path(folder)
        refs = [r for r in json.loads((self.path / "bursts.json").read_text(encoding="utf-8"))
                if r["polarization"].upper() == polarization.upper()]
        if not refs:
            raise FileNotFoundError(f"{self.path}: no {polarization} bursts")
        self.swaths: list[BurstSwath] = []
        for r in refs:
            tif = self.path / f"{r['subswath']}_{r['polarization']}_{r['burst_index']}.tiff"
            xml = self.path / f"{r['slc_name']}_{r['polarization']}.xml"
            if not (tif.exists() and xml.exists()):
                continue
            meta = read_metadata(xml, r["subswath"], r["polarization"], r["burst_index"], r["slc_name"])
            if orbits is not None:
                from geoeyes.sensors.sentinel1.orbits import with_precise_orbit
                meta = with_precise_orbit(meta, orbits)
            self.swaths.append(BurstSwath(r["subswath"], int(r["burst_index"]), meta, tif, xml))
        if not self.swaths:
            raise FileNotFoundError(f"{self.path}: burst files missing")
        self.swaths.sort(key=lambda s: s.meta.sensing_start)
        m0 = self.swaths[0].meta
        self.platform = m0.slc_name[:3].upper()
        self.relative_orbit = int(refs[0].get("relative_orbit", -1))
        self.pass_direction = m0.pass_direction.lower()
        self.start_utc = m0.sensing_start.replace(tzinfo=UTC)
        self.wavelength = m0.wavelength

    @property
    def date(self) -> str:
        return self.start_utc.strftime("%Y-%m-%d")

    @property
    def label(self) -> str:
        return f"{self.platform} {self.date}"

    # ── geometry ────────────────────────────────────────────────────────────
    def pixel(self, sw: BurstSwath, lat: float, lon: float, h: float) -> tuple[float, float, float, np.ndarray]:
        """(line, sample, slant range, ECEF point) of a ground point in a burst raster."""
        m = sw.meta
        x = llh_to_ecef(np.array([lat]), np.array([lon]), np.array([h]))
        t0 = m.orbit.seconds(m.sensing_start)
        t = m.orbit.zero_doppler_time(x, np.array([t0 + m.lines * m.azimuth_time_interval / 2]))
        rng = float(m.orbit.slant_range(x, t)[0])
        line = (float(t[0]) - t0) / m.azimuth_time_interval
        sample = (2 * rng / C - m.slant_range_time) * m.range_sampling_rate
        return line, sample, rng, x[0]

    def locate(self, lat: float, lon: float, h: float) -> Location | None:
        """The burst that images (lat, lon, h) in its valid area, nearest mid-burst; None when none does."""
        best = None
        for sw in self.swaths:
            try:
                line, sample, rng, x = self.pixel(sw, lat, lon, h)
            except Exception:                    # point outside the orbit span of this burst
                continue
            l0, l1, s0, s1 = sw.meta.valid_window
            if not (l0 <= line < l1 and s0 <= sample < s1):
                continue
            score = abs(line - sw.meta.lines / 2)
            if best is None or score < best[0]:
                best = (score, sw, line, sample, rng, x)
        if best is None:
            return None
        _, sw, line, sample, rng, x = best
        m = sw.meta
        t = m.orbit.zero_doppler_time(x[None], np.array([m.orbit.seconds(m.sensing_start)
                                                         + line * m.azimuth_time_interval]))
        sat, _ = m.orbit.interpolate(t)
        v = sat[0] - x
        e, n, u = enu_basis(lat, lon) @ (v / np.linalg.norm(v))
        el = float(np.degrees(np.arcsin(u)))
        return Location(swath=sw.name, burst=sw.burst, line=line, sample=sample,
                        los_azimuth_deg=float(np.degrees(np.arctan2(e, n)) % 360), los_elevation_deg=el,
                        incidence_deg=90.0 - el, slant_range_m=rng)

    def swath(self, loc: Location) -> BurstSwath:
        return next(s for s in self.swaths if s.name == loc.swath and s.burst == loc.burst)

    def geocode(self, sw: BurstSwath, line: float, sample: float, h: float,
                guess: tuple[float, float]) -> tuple[float, float]:
        """(lat, lon) at height h of a burst pixel, by Newton iteration on ``pixel``."""
        lat, lon = guess
        for _ in range(8):
            l0, s0, *_ = self.pixel(sw, lat, lon, h)
            e = 1e-5
            la, sa, *_ = self.pixel(sw, lat + e, lon, h)
            lo, so, *_ = self.pixel(sw, lat, lon + e, h)
            jac = np.array([[(la - l0) / e, (lo - l0) / e], [(sa - s0) / e, (so - s0) / e]])
            d = np.linalg.solve(jac, [line - l0, sample - s0])
            lat, lon = lat + d[0], lon + d[1]
            if abs(d[0]) + abs(d[1]) < 1e-10:
                break
        return float(lat), float(lon)

    # ── pixels ──────────────────────────────────────────────────────────────
    def read_chip(self, sw: BurstSwath, line: int, sample: int, half_az: int, half_rg: int):
        """Complex chip centred on (line, sample), clipped to the burst. Returns (chip, first_line, first_sample)."""
        m = sw.meta
        r0, r1 = max(line - half_az, 0), min(line + half_az + 1, m.lines)
        c0, c1 = max(sample - half_rg, 0), min(sample + half_rg + 1, m.samples)
        return read_slc(sw.tiff, (r0, r1, c0, c1)), r0, c0

    def beta_nought_lut(self, sw: BurstSwath, line: float, sample: float) -> float:
        """Calibration amplitude A so that beta0 = |DN|^2 / A^2."""
        return read_calibration(sw.xml, sw.name, sw.meta.polarization).at(sw.meta, line, sample)


def scenes(root: str | Path, polarization: str = "VV") -> list[BurstScene]:
    """Every acquisition folder (with ``bursts.json``) under ``root``, sorted by time."""
    out = [BurstScene(p.parent, polarization) for p in sorted(Path(root).rglob("bursts.json"))]
    return sorted(out, key=lambda s: s.start_utc)
