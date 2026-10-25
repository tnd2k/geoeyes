"""ps_lite inputs built from a StackStore (replaces the SNAP-DIMAP readers of modules/ps_stack/stack.py).

The stack's SLCs are coregistered and flattened (``slc[ref]·conj(slc[k])`` has no geometric phase
left), so every interferogram's reference phase is zero; ``kh`` comes from the stack's per-pixel
height sensitivity: kh(ref→k) = kh[k] - kh[ref].
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.interpolate import RectBivariateSpline, RegularGridInterpolator

from geoeyes.core.geodesy import llh_to_ecef


@dataclass
class Epoch:
    """One acquisition on the stack grid (in-memory complex array)."""

    date: date
    days: float                  # since the stack reference
    slc: np.ndarray              # (ny, nx) complex64

    @property
    def i(self) -> np.ndarray:
        return self.slc.real

    @property
    def q(self) -> np.ndarray:
        return self.slc.imag

    def read(self, l0, l1, s0, s1) -> np.ndarray:
        return self.slc[l0:l1, s0:s1]


@dataclass
class Ifg:
    """Interferogram ref · conj(sec) of two epochs."""

    ref: int
    sec: int
    date: date                   # of the secondary epoch
    days: float                  # sec - ref
    ref_phase: np.ndarray        # (ny, nx) on the geometry nodes; zero for a flattened stack
    kh_spline: RectBivariateSpline
    bperp: float
    hoa: float


@dataclass
class MasterGeometry:
    """Terrain points of the coarse geometry nodes (stack grid coordinates)."""

    lines: np.ndarray
    samples: np.ndarray
    X: np.ndarray                # (ny, nx, 3) ECEF
    R1: np.ndarray               # (ny, nx) reference slant range
    h_ell: np.ndarray
    h_ortho: np.ndarray
    unconverged: float = 0.0

    def interpolator(self, values: np.ndarray) -> RegularGridInterpolator:
        return RegularGridInterpolator((self.lines, self.samples), values, method="linear",
                                       bounds_error=False, fill_value=None)


@dataclass
class StackInputs:
    epochs: list[Epoch]
    geo: MasterGeometry
    kh: np.ndarray               # (n_epoch, ny_c, nx_c) on the geometry nodes, vs the stack reference
    bperp: np.ndarray            # (n_epoch,) at the stack centre, vs the stack reference
    lat: np.ndarray              # full-resolution geometry (ny, nx)
    lon: np.ndarray
    hgt: np.ndarray
    incidence: np.ndarray
    wavelength: float
    heading_deg: float
    attrs: dict


def load(store, *, geo_step: tuple[int, int] = (8, 12), geoid=None, slc_var: str = "slc") -> StackInputs:
    """Read a stack fully into memory (meant for AOI-cropped stacks); ``slc_var``: e.g. ``slc_linked``."""
    ds = store.open()
    dates = [np.datetime64(d, "D").item() for d in ds["date"].values]
    ref_day = date.fromisoformat(ds.attrs["reference_date"])
    slc = np.empty(ds[slc_var].shape, np.complex64)    # filled date by date: no dask concatenation copy
    for k in range(slc.shape[0]):
        slc[k] = ds[slc_var].isel(date=k).values
    epochs = [Epoch(d, float((d - ref_day).days), slc[k]) for k, d in enumerate(dates)]
    ny, nx = slc.shape[1:]
    lines = np.unique(np.r_[np.arange(0, ny, geo_step[0]), ny - 1])
    samples = np.unique(np.r_[np.arange(0, nx, geo_step[1]), nx - 1])
    lat = ds["geometry_lat"].values.astype(np.float64)
    lon = ds["geometry_lon"].values.astype(np.float64)
    hgt = ds["geometry_hgt"].values.astype(np.float64)
    sub = np.ix_(lines, samples)
    if geoid is None:
        from geoeyes.geometry.dem import Geoid
        geoid = Geoid()
    h_ortho = hgt[sub] - geoid.undulation(lat[sub], lon[sub])
    geo = MasterGeometry(lines.astype(float), samples.astype(float), llh_to_ecef(lat[sub], lon[sub], hgt[sub]),
                         ds["geometry_slant_range"].values[sub].astype(np.float64), hgt[sub], h_ortho)
    kh = ds["kh"].values[:, lines][:, :, samples].astype(np.float64)
    return StackInputs(epochs, geo, kh, ds["bperp"].values.astype(np.float64), lat, lon, hgt,
                       ds["geometry_incidence"].values.astype(np.float64), float(ds.attrs["wavelength_m"]),
                       float(ds.attrs.get("heading_deg", 0.0)), dict(ds.attrs))


def longest_baselines(bperp: np.ndarray) -> np.ndarray:
    """For each epoch taken as reference, its longest perpendicular baseline to the others (m)."""
    return np.abs(bperp[None, :] - bperp[:, None]).max(axis=1)


def make_ifgs(inp: StackInputs, ref: int) -> list[Ifg]:
    g = inp.geo
    iy, ix = len(g.lines) // 2, len(g.samples) // 2
    zero = np.zeros((len(g.lines), len(g.samples)), np.float32)
    out = []
    for k, e in enumerate(inp.epochs):
        if k == ref:
            continue
        kh = inp.kh[k] - inp.kh[ref]
        spl = RectBivariateSpline(g.lines, g.samples, kh, kx=3, ky=3)
        out.append(Ifg(ref, k, e.date, e.days - inp.epochs[ref].days, zero, spl,
                       float(inp.bperp[k] - inp.bperp[ref]), float(2 * np.pi / max(abs(kh[iy, ix]), 1e-9))))
    return out
