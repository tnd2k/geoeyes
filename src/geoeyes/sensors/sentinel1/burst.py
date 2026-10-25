"""Sentinel-1 IW burst: metadata from the ASF combined XML and the burst SLC GeoTIFF (ADR-023).

The ASF metadata file holds the full product annotation of every subswath of the source SLC; the
burst GeoTIFF holds exactly one burst (``linesPerBurst`` x ``samplesPerBurst``, CInt16). Times
are UTC; slant-range times are two-way (s).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np

from geoeyes.core.errors import DataError, SensorError
from geoeyes.geometry.orbit import StateVectors

C = 299_792_458.0


@dataclass(frozen=True)
class RangePoly:
    """Polynomial in two-way slant-range time: f(tau) = sum_k c_k (tau - t0)^k."""

    azimuth_time: datetime
    t0: float
    coeffs: tuple[float, ...]

    def __call__(self, tau):
        dt = np.asarray(tau, np.float64) - self.t0
        return np.polynomial.polynomial.polyval(dt, self.coeffs)


@dataclass(frozen=True)
class GeolocationGrid:
    azimuth_time: np.ndarray      # seconds since burst start
    slant_range_time: np.ndarray  # two-way s
    line: np.ndarray              # line in the burst (may be <0 / >lines for neighbours)
    pixel: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    height: np.ndarray
    incidence_deg: np.ndarray


@dataclass(frozen=True)
class BurstMetadata:
    slc_name: str
    mission: str                  # S1A / S1B / S1C
    subswath: str
    polarization: str
    burst_index: int              # 0-based index in the subswath (ASF ``burstIndex``)
    pass_direction: str           # Ascending / Descending
    heading_deg: float
    radar_frequency: float
    range_sampling_rate: float
    azimuth_steering_rate: float  # rad/s
    azimuth_time_interval: float  # s
    slant_range_time: float       # two-way time of the first sample, s
    range_pixel_spacing: float    # m
    azimuth_pixel_spacing: float  # m
    lines: int
    samples: int
    sensing_start: datetime       # azimuth time of the first line of the burst
    first_valid_sample: np.ndarray
    last_valid_sample: np.ndarray
    doppler: RangePoly            # data Doppler centroid (Hz)
    fm_rate: RangePoly            # azimuth FM rate (Hz/s)
    orbit: StateVectors           # annotation orbit (replace with precise POEORB when available)
    grid: GeolocationGrid
    incidence_mid_deg: float

    # ------------------------------------------------------------------ derived geometry
    @property
    def wavelength(self) -> float:
        return C / self.radar_frequency

    @property
    def near_range(self) -> float:
        return self.slant_range_time * C / 2

    @property
    def range_spacing_time(self) -> float:
        return 1.0 / self.range_sampling_rate

    @property
    def sensing_mid(self) -> datetime:
        return self.sensing_start + timedelta(seconds=self.lines * self.azimuth_time_interval / 2)

    @property
    def valid_window(self) -> tuple[int, int, int, int]:
        """(first_line, last_line + 1, first_sample, last_sample + 1) of valid data."""
        ok = np.flatnonzero(self.first_valid_sample >= 0)
        if not ok.size:
            raise DataError(f"{self.slc_name} {self.subswath} burst {self.burst_index}: no valid lines")
        l0, l1 = int(ok[0]), int(ok[-1]) + 1
        s0 = int(self.first_valid_sample[ok].max())
        s1 = int(self.last_valid_sample[ok].min()) + 1
        return l0, l1, s0, s1

    def line_time(self, line) -> np.ndarray:
        """Seconds since ``sensing_start`` of (fractional) burst lines."""
        return np.asarray(line, np.float64) * self.azimuth_time_interval

    def sample_range_time(self, sample) -> np.ndarray:
        return self.slant_range_time + np.asarray(sample, np.float64) * self.range_spacing_time

    def slant_range(self, sample) -> np.ndarray:
        return self.sample_range_time(sample) * C / 2

    def orbit_seconds(self, line=0.0) -> np.ndarray:
        """Orbit time (s since ``orbit.t0``) of burst lines."""
        return self.orbit.seconds(self.sensing_start) + self.line_time(line)


# ---------------------------------------------------------------------- parsing helpers
def _t(text: str) -> datetime:
    return datetime.fromisoformat(text.strip())


def _f(e: ET.Element, path: str) -> float:
    v = e.findtext(path)
    if v is None:
        raise SensorError(f"annotation: missing {path}")
    return float(v)


def _floats(text: str) -> tuple[float, ...]:
    return tuple(float(x) for x in text.split())


@lru_cache(maxsize=32)
def _annotation(xml_path: str, subswath: str, polarization: str) -> ET.Element:
    root = ET.parse(xml_path).getroot()
    md = root.find("metadata")
    if md is None:
        raise SensorError(f"{xml_path}: not an ASF burst metadata file")
    for c in md:
        if c.tag == "product" and c.findtext("swath") == subswath and c.findtext("polarisation") == polarization:
            content = c.find("content")
            if content is not None:
                return content
    raise SensorError(f"{xml_path}: no annotation for {subswath} {polarization}")


@dataclass
class Calibration:
    """beta-nought LUT of one subswath: ``beta0 = |DN|^2 / A^2`` with A interpolated from the grid."""

    azimuth_time: list[datetime]  # (n_vec,) azimuth time of each vector
    pixel: np.ndarray             # (n_pix,) samples of the vectors
    beta: np.ndarray              # (n_vec, n_pix) amplitude A

    def at(self, meta: BurstMetadata, line: float, sample: float) -> float:
        """A at a (fractional) burst line / sample: bilinear in (vector azimuth time, pixel)."""
        t = np.array([(a - meta.sensing_start).total_seconds() for a in self.azimuth_time])
        li = np.interp(line * meta.azimuth_time_interval, t, np.arange(len(t)))
        pi = np.interp(sample, self.pixel, np.arange(len(self.pixel)))
        i0, j0 = int(li), int(pi)
        i1, j1 = min(i0 + 1, len(t) - 1), min(j0 + 1, len(self.pixel) - 1)
        fi, fj = li - i0, pi - j0
        g = self.beta
        return float((g[i0, j0] * (1 - fj) + g[i0, j1] * fj) * (1 - fi) + (g[i1, j0] * (1 - fj) + g[i1, j1] * fj) * fi)


@lru_cache(maxsize=32)
def read_calibration(xml_path: str | Path, subswath: str, polarization: str) -> Calibration:
    """beta-nought calibration vectors of a subswath from an ASF burst metadata file."""
    root = ET.parse(str(xml_path)).getroot()
    for c in root.find("metadata"):
        if c.tag == "calibration" and c.findtext("swath") == subswath.upper() \
                and c.findtext("polarisation") == polarization.upper():
            vecs = c.findall("content/calibrationVectorList/calibrationVector")
            return Calibration(azimuth_time=[_t(v.findtext("azimuthTime")) for v in vecs],
                               pixel=np.array(vecs[0].findtext("pixel").split(), dtype=float),
                               beta=np.array([v.findtext("betaNought").split() for v in vecs], dtype=float))
    raise SensorError(f"{xml_path}: no calibration for {subswath} {polarization}")


def _nearest(polys: list[RangePoly], when: datetime) -> RangePoly:
    return min(polys, key=lambda p: abs((p.azimuth_time - when).total_seconds()))


def read_metadata(xml_path: str | Path, subswath: str, polarization: str, burst_index: int,
                  slc_name: str | None = None) -> BurstMetadata:
    ann = _annotation(str(xml_path), subswath.upper(), polarization.upper())
    gi = ann.find("generalAnnotation/productInformation")
    ii = ann.find("imageAnnotation/imageInformation")
    st = ann.find("swathTiming")
    if gi is None or ii is None or st is None:
        raise SensorError(f"{xml_path}: incomplete annotation")
    bursts = st.findall("burstList/burst")
    if not 0 <= burst_index < len(bursts):        # ASF burstIndex is 0-based (burst2safe uses it the same way)
        raise SensorError(f"burst index {burst_index} outside 0..{len(bursts) - 1}")
    b = bursts[burst_index]
    lines, samples = int(st.findtext("linesPerBurst")), int(st.findtext("samplesPerBurst"))
    fvs = np.array([int(x) for x in b.findtext("firstValidSample").split()], np.int32)
    lvs = np.array([int(x) for x in b.findtext("lastValidSample").split()], np.int32)
    start = _t(b.findtext("azimuthTime"))
    ati = _f(ii, "azimuthTimeInterval")
    mid = start + timedelta(seconds=lines * ati / 2)

    dcs = [RangePoly(_t(e.findtext("azimuthTime")), float(e.findtext("t0")), _floats(e.findtext("dataDcPolynomial")))
           for e in ann.findall("dopplerCentroid/dcEstimateList/dcEstimate")]
    fms = [RangePoly(_t(e.findtext("azimuthTime")), float(e.findtext("t0")),
                     _floats(e.findtext("azimuthFmRatePolynomial")))
           for e in ann.findall("generalAnnotation/azimuthFmRateList/azimuthFmRate")]
    if not dcs or not fms:
        raise SensorError(f"{xml_path}: missing Doppler / FM-rate estimates")

    osv = ann.findall("generalAnnotation/orbitList/orbit")
    orbit = StateVectors.from_lists(
        [_t(o.findtext("time")) for o in osv],
        [[float(o.findtext(f"position/{k}")) for k in "xyz"] for o in osv],
        [[float(o.findtext(f"velocity/{k}")) for k in "xyz"] for o in osv])

    pts = ann.findall("geolocationGrid/geolocationGridPointList/geolocationGridPoint")
    az = np.array([(_t(p.findtext("azimuthTime")) - start).total_seconds() for p in pts])
    line = np.array([float(p.findtext("line")) for p in pts]) - burst_index * lines
    span = lines * ati
    keep = (az >= -span) & (az <= 2 * span)
    sel = [p for p, k in zip(pts, keep, strict=True) if k]
    grid = GeolocationGrid(
        azimuth_time=az[keep], line=line[keep],
        slant_range_time=np.array([float(p.findtext("slantRangeTime")) for p in sel]),
        pixel=np.array([float(p.findtext("pixel")) for p in sel]),
        lat=np.array([float(p.findtext("latitude")) for p in sel]),
        lon=np.array([float(p.findtext("longitude")) for p in sel]),
        height=np.array([float(p.findtext("height")) for p in sel]),
        incidence_deg=np.array([float(p.findtext("incidenceAngle")) for p in sel]))

    header = ann.find("adsHeader")
    return BurstMetadata(
        slc_name=slc_name or Path(xml_path).stem.rsplit("_", 1)[0],
        mission=header.findtext("missionId") if header is not None else "",
        subswath=subswath.upper(), polarization=polarization.upper(), burst_index=burst_index,
        pass_direction=gi.findtext("pass"), heading_deg=_f(gi, "platformHeading"),
        radar_frequency=_f(gi, "radarFrequency"), range_sampling_rate=_f(gi, "rangeSamplingRate"),
        azimuth_steering_rate=np.deg2rad(_f(gi, "azimuthSteeringRate")),
        azimuth_time_interval=ati, slant_range_time=_f(ii, "slantRangeTime"),
        range_pixel_spacing=_f(ii, "rangePixelSpacing"), azimuth_pixel_spacing=_f(ii, "azimuthPixelSpacing"),
        lines=lines, samples=samples, sensing_start=start, first_valid_sample=fvs, last_valid_sample=lvs,
        doppler=_nearest(dcs, mid), fm_rate=_nearest(fms, mid), orbit=orbit, grid=grid,
        incidence_mid_deg=_f(ii, "incidenceAngleMidSwath"))


def read_slc(tiff_path: str | Path, window: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Burst SLC as complex64; ``window`` = (line0, line1, sample0, sample1)."""
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(tiff_path) as src:
        win = None
        if window is not None:
            l0, l1, s0, s1 = window
            win = Window(s0, l0, s1 - s0, l1 - l0)
        data = src.read(1, window=win)
    if np.iscomplexobj(data):
        return data.astype(np.complex64, copy=False)
    raise SensorError(f"{tiff_path}: expected a complex raster, got {data.dtype}")
