"""Step 1 — load the PS candidates (legacy ``_ps_load_initial_gamma``, single-master).

Per-candidate perpendicular baselines from the TCN baseline and its along-track rate, master epoch
inserted as a unit-phase column, candidates projected to a local metric frame (rotated to the radar
heading when that tightens the extent) and sorted by (y, x).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from geoeyes.processing.ps.geometry import llh2local


@dataclass(frozen=True)
class RadarParams:
    """Master-image geometry (the ``.rslc.par`` items StaMPS uses)."""

    range_pixel_spacing: float
    near_range: float
    center_range: float
    sar_to_earth_center: float
    earth_radius_below_sensor: float
    azimuth_lines: float
    prf: float
    heading: float

    @classmethod
    def from_par(cls, par: dict[str, str]) -> RadarParams:
        return cls(*(float(par[k]) for k in (
            "range_pixel_spacing", "near_range_slc", "center_range_slc", "sar_to_earth_center",
            "earth_radius_below_sensor", "azimuth_lines", "prf", "heading")))


@dataclass
class PsLoad:
    """Step-1 state. ``day`` holds proleptic ordinals (``date.toordinal``); indices are 0-based."""

    ij: np.ndarray            # (n_ps, 3) [id, line, sample]
    lonlat: np.ndarray        # (n_ps, 2) float32
    xy: np.ndarray            # (n_ps, 3) float32 [id, x, y] in m, mm-rounded
    ph: np.ndarray            # (n_ps, n_ifg) complex64, master column = 1
    bperp: np.ndarray         # (n_ifg,) mean perpendicular baseline per epoch, 0 at the master
    bperp_mat: np.ndarray     # (n_ps, n_sec) float32, secondaries only
    day: np.ndarray           # (n_ifg,) int ordinals
    master_ix: int
    master_day: int
    ifgday: np.ndarray        # (n_ifg, 2) [master, epoch] ordinals
    ifgday_ix: np.ndarray     # (n_ifg, 2) 0-based indices into ``day``
    sort_ix: np.ndarray       # order applied after the lon/lat filter
    cand_ix: np.ndarray       # (n_ps,) input-candidate index of every row
    forced: np.ndarray        # (n_ps,) bool
    ll0: np.ndarray           # (2,) float32 projection origin
    la: np.ndarray            # (n_ps,) incidence angle (rad); the legacy engine stores it as "la"
    mean_incidence: float
    mean_range: float
    hgt: np.ndarray | None
    da: np.ndarray | None
    coh: np.ndarray | None    # (n_ps,) clipped prior coherence

    @property
    def n_ps(self) -> int:
        return self.ij.shape[0]

    @property
    def n_ifg(self) -> int:
        return self.ph.shape[1]


def stamps_geometry(ij: np.ndarray, radar: RadarParams, baselines: list[tuple[np.ndarray, np.ndarray]]):
    """Legacy (``.rslc.par`` + ``.base``) per-candidate geometry: perpendicular baseline
    bc·cos(look) - bn·sin(look) from the TCN baseline and its rate (ps_load_initial_gamma.m) and the
    incidence angle, both from a spherical-Earth model. Returns (bperp_mat (n, n_sec) float32, inc (n,))."""
    r = radar
    rg = r.near_range + ij[:, 2] * r.range_pixel_spacing
    se, re = r.sar_to_earth_center, r.earth_radius_below_sensor
    look = np.arccos((se**2 + rg**2 - re**2) / (2 * se * rg))
    inc = np.arccos((se**2 - re**2 - rg**2) / (2 * re * rg))
    t_az = (ij[:, 1] - (r.azimuth_lines / 2 - 0.5)) / r.prf
    bperp_mat = np.zeros((ij.shape[0], len(baselines)), np.float32)
    for k, (b, rate) in enumerate(baselines):
        bc = b[1] + rate[1] * t_az
        bn = b[2] + rate[2] * t_az
        bperp_mat[:, k] = bc * np.cos(look) - bn * np.sin(look)
    return bperp_mat, inc


def load_initial(*, ij: np.ndarray, lonlat: np.ndarray, ph: np.ndarray, master: date, secondaries: list[date],
                 baselines: list[tuple[np.ndarray, np.ndarray]] | None = None, radar: RadarParams | None = None,
                 bperp_mat: np.ndarray | None = None, inc: np.ndarray | None = None, heading: float | None = None,
                 mean_range: float | None = None,
                 hgt: np.ndarray | None = None, da: np.ndarray | None = None, coh: np.ndarray | None = None,
                 forced: np.ndarray | None = None, coh_eps: float = 1e-6, log=None) -> PsLoad:
    """``ph`` (n, n_sec) holds master·conj(secondary) per date in ``secondaries`` (ascending; the
    master itself may be present as a master-master column). Geometry either from the legacy ``radar`` +
    ``baselines`` (TCN, rate), or given directly: ``bperp_mat`` (n, n_sec) m, ``inc`` (n,) rad, ``heading``
    (deg) and ``mean_range`` (m)."""
    ij = np.asarray(ij)
    n = ij.shape[0]
    forced = np.zeros(n, bool) if forced is None else np.asarray(forced, bool)
    sec_day = np.array([d.toordinal() for d in secondaries])
    if np.any(np.diff(sec_day) <= 0):
        raise ValueError("secondary dates must be strictly ascending")
    m_day = master.toordinal()
    if bperp_mat is None:
        bperp_mat, inc = stamps_geometry(ij, radar, baselines)
        heading, mean_range = radar.heading, radar.center_range
    bperp_mat = np.asarray(bperp_mat, np.float32)
    inc = np.asarray(inc, np.float64)

    # drop interferograms that are empty at every candidate (the master-master column is legitimately 0)
    keep = ~np.all(np.abs(ph) == 0, axis=0) | (sec_day == m_day)
    if not keep.all() and log:
        log.warning("dropping %d empty interferogram(s): %s", int((~keep).sum()),
                    [secondaries[i].isoformat() for i in np.flatnonzero(~keep)])
    ph, bperp_mat, sec_day = ph[:, keep], bperp_mat[:, keep], sec_day[keep]
    bperp = bperp_mat.mean(axis=0, dtype=np.float64)    # legacy: float32 accumulation, ~0.4 % off
    master_ix = int(np.sum(sec_day < m_day))
    if master_ix < sec_day.size and sec_day[master_ix] == m_day:
        day = sec_day
        ph = ph.copy()
        ph[:, master_ix] = 1
    else:
        day = np.insert(sec_day, master_ix, m_day)
        bperp = np.insert(bperp, master_ix, 0.0)
        ph = np.insert(ph, master_ix, np.ones(n, np.complex64), axis=1)

    # candidates with a position (forced points are always kept)
    lonlat = np.asarray(lonlat, np.float32)
    ok = ~np.isnan(lonlat).any(axis=1) | (forced & np.isfinite(lonlat).all(axis=1))
    rows = np.flatnonzero(ok)
    ll = lonlat[rows]
    ll0 = (ll.max(axis=0) + ll.min(axis=0)) / 2
    xy = llh2local(ll, ll0) * 1000
    theta = np.radians(180 - heading)
    if theta > np.pi:
        theta -= 2 * np.pi
    rot = np.array([[np.cos(theta), np.sin(theta)], [-np.sin(theta), np.cos(theta)]])
    xy_rot = xy @ rot.T
    if np.ptp(xy_rot[:, 0]) < np.ptp(xy[:, 0]) and np.ptp(xy_rot[:, 1]) < np.ptp(xy[:, 1]):
        xy = xy_rot
    sort_ix = np.lexsort((xy[:, 0], xy[:, 1]))
    rows = rows[sort_ix]
    xy = np.round(xy[sort_ix] * 1000) / 1000

    # drop candidates with NaN phase or zero longitude (forced points kept)
    ok = (~np.isnan(ph[rows]).any(axis=1) & (lonlat[rows, 0] != 0)) | forced[rows]
    rows, xy = rows[ok], xy[ok]
    n_ps = rows.size
    ids = np.arange(n_ps)
    ij = ij[rows].copy()
    ij[:, 0] = ids

    ifgday = np.column_stack([np.full(day.size, m_day), day])
    _, inv = np.unique(ifgday.reshape(-1), return_inverse=True)
    pick = (lambda a: None if a is None else np.asarray(a)[rows])  # noqa: E731
    coh_ps = None
    if coh is not None:
        c = np.nan_to_num(np.asarray(coh, np.float64)[rows], nan=0.0, posinf=1.0, neginf=0.0)
        coh_ps = np.clip(c, coh_eps, 1.0 - coh_eps).astype(np.float32)
    return PsLoad(
        ij=ij, lonlat=lonlat[rows], xy=np.column_stack([ids, xy]).astype(np.float32), ph=ph[rows],
        bperp=bperp, bperp_mat=bperp_mat[rows], day=day, master_ix=master_ix, master_day=m_day,
        ifgday=ifgday, ifgday_ix=inv.reshape(-1, 2), sort_ix=sort_ix, cand_ix=rows, forced=forced[rows], ll0=ll0,
        la=inc[rows], mean_incidence=float(inc.mean()), mean_range=float(mean_range),
        hgt=pick(hgt), da=pick(da), coh=coh_ps)
