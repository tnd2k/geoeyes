"""GNSS daily positions from the Nevada Geodetic Laboratory (NGL, University of Nevada, Reno): station list and
``tenv3`` time series in the IGS20 frame, cached under ``<workspace>/cache/gnss/ngl``
(docs/en/research/gnss-insar-calibration.md §3).

``tenv3`` columns: site, YYMMMDD, decimal year, MJD, GPS week, day, reference longitude, then east / north / up
as an integer part (e0, n0, u0, m) plus a fractional part (m) from a local reference point, antenna height,
sigmas, correlations, and latitude / longitude / height of the day.

Positions are cleaned before use: equipment changes listed by NGL (``steps.txt``) and jumps found in the series
split it into segments; segments are re-joined by a common linear trend with one offset per segment (a station
moved under the same name, as JNAV in Hanoi in 2025, keeps its rate but not its position); daily outliers beyond
5 robust sigmas of a running median are dropped.
"""
from __future__ import annotations

import io
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.core.errors import DataError

log = logging.getLogger(__name__)

BASE = "https://geodesy.unr.edu"
STATIONS_URL = f"{BASE}/NGLStationPages/DataHoldings.txt"
STEPS_URL = f"{BASE}/NGLStationPages/steps.txt"
TENV3_URL = f"{BASE}/gps_timeseries/IGS20/tenv3/IGS20/{{site}}.tenv3"
MIDAS_URL = f"{BASE}/gps_timeseries/IGS20/midas/midas.IGS.txt"
FRAME = "IGS20"
SOURCE = "Nevada Geodetic Laboratory (NGL), daily GNSS positions, IGS20 frame (geodesy.unr.edu)"
MAX_AGE_S = {"stations": 7 * 86400, "steps": 7 * 86400, "series": 86400, "midas": 7 * 86400}
_COLS = ["site", "ymd", "yr", "mjd", "week", "day", "reflon", "e0", "east", "n0", "north", "u0", "up", "ant",
         "sig_e", "sig_n", "sig_u", "corr_en", "corr_eu", "corr_nu", "lat", "lon", "height"]
_MJD0 = np.datetime64("1858-11-17")


def _get(url: str, dest: Path, max_age_s: float) -> Path:
    """``url`` cached in ``dest``, downloaded again when older than ``max_age_s`` (the cached copy is kept if the
    server cannot be reached)."""
    if dest.exists() and time.time() - dest.stat().st_mtime < max_age_s:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "GeoEyes (InSAR validation)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    except Exception as exc:
        if dest.exists():
            log.warning("NGL %s unreachable (%s): cached copy used", url, exc)
            return dest
        raise DataError(f"NGL: cannot read {url}: {exc}") from None
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def stations(cache: Path) -> pd.DataFrame:
    """Every NGL station: site, lat, lon (-180..180), height, first and last day."""
    f = _get(STATIONS_URL, cache / "DataHoldings.txt", MAX_AGE_S["stations"])
    rows = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        p = line.split()
        if len(p) < 11:
            continue
        try:
            lon = float(p[2])
            rows.append((p[0], float(p[1]), lon - 360 if lon > 180 else lon, float(p[3]), p[7], p[8], int(p[10])))
        except ValueError:
            continue
    df = pd.DataFrame(rows, columns=["site", "lat", "lon", "height", "first", "last", "n_days"])
    df["first"] = pd.to_datetime(df["first"], errors="coerce")
    df["last"] = pd.to_datetime(df["last"], errors="coerce")
    return df


def stations_in(cache: Path, bbox: list[float], start, end, margin_deg: float = 0.0) -> pd.DataFrame:
    """Stations inside ``bbox`` (+ margin) with data overlapping ``start``..``end``."""
    w, s, e, n = bbox
    df = stations(cache)
    inside = df["lon"].between(w - margin_deg, e + margin_deg) & df["lat"].between(s - margin_deg, n + margin_deg)
    overlap = (df["first"] <= pd.Timestamp(end)) & (df["last"] >= pd.Timestamp(start))
    return df[inside & overlap].reset_index(drop=True)


def midas(cache: Path, site: str) -> dict | None:
    """NGL's MIDAS velocity of a station (Blewitt et al. 2016; robust to steps, outliers and seasons, over the
    whole record): ``{"first", "last", "years", "enu_mm_yr", "sigma_mm_yr"}``, None if NGL has none."""
    f = _get(MIDAS_URL, cache / "midas.IGS.txt", MAX_AGE_S["midas"])
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        p = line.split()
        if len(p) >= 14 and p[0] == site:
            return {"first": float(p[2]), "last": float(p[3]), "years": float(p[4]),
                    "enu_mm_yr": [round(float(v) * 1000, 2) for v in p[8:11]],
                    "sigma_mm_yr": [round(float(v) * 1000, 2) for v in p[11:14]]}
    return None


def equipment_steps(cache: Path, site: str) -> list[np.datetime64]:
    """Days of equipment / log changes of a station (NGL steps.txt, type 1); earthquakes (type 2) are left to
    the jump detection."""
    f = _get(STEPS_URL, cache / "steps.txt", MAX_AGE_S["steps"])
    out = set()
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        p = line.split()
        if len(p) >= 3 and p[0] == site and p[2] == "1":
            try:
                out.add(np.datetime64(pd.to_datetime(p[1], format="%y%b%d").date()))
            except ValueError:
                continue
    return sorted(out)


def read_tenv3(text: str) -> pd.DataFrame:
    """A tenv3 file -> one row per day: date, east / north / up (m, absolute in the local frame), sigmas (m),
    lat / lon / height."""
    df = pd.read_csv(io.StringIO(text), sep=r"\s+", skiprows=1, names=_COLS)
    if df.empty:
        raise DataError("empty tenv3 file")
    out = pd.DataFrame({
        "date": (_MJD0 + df["mjd"].to_numpy().astype("timedelta64[D]")).astype("datetime64[D]"),
        "east": df["e0"] + df["east"], "north": df["n0"] + df["north"], "up": df["u0"] + df["up"],
        "sig_e": df["sig_e"], "sig_n": df["sig_n"], "sig_u": df["sig_u"],
        "lat": df["lat"], "lon": ((df["lon"] + 180) % 360) - 180, "height": df["height"]})
    return out.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def series(cache: Path, site: str) -> pd.DataFrame:
    f = _get(TENV3_URL.format(site=site), cache / f"{site}.tenv3", MAX_AGE_S["series"])
    return read_tenv3(f.read_text(encoding="utf-8", errors="replace"))


@dataclass
class Cleaned:
    """Daily ENU displacement (m) of one station over a window, with its segments re-joined."""

    site: str
    date: np.ndarray                         # datetime64[D]
    enu: np.ndarray                          # (days, 3), m, relative to the first day
    sigma: np.ndarray                        # (days, 3), m
    lat: float
    lon: float
    segments: int = 1
    jumps: list[str] = field(default_factory=list)
    outliers: int = 0
    notes: list[str] = field(default_factory=list)


def clean(df: pd.DataFrame, site: str, start, end, steps: list[np.datetime64] | None = None,
          jump_m: tuple[float, float] = (0.015, 0.03), min_segment_days: int = 30) -> Cleaned:
    """The station's positions over ``start``..``end``, segmented at equipment changes and at day-to-day jumps
    larger than ``jump_m`` (horizontal, vertical) and 5 sigmas, outliers removed, segments re-joined."""
    w = df[(df["date"] >= np.datetime64(start, "D")) & (df["date"] <= np.datetime64(end, "D"))].reset_index(drop=True)
    if len(w) < min_segment_days:
        raise DataError(f"{site}: {len(w)} days of data in {start}..{end}")
    x = w[["east", "north", "up"]].to_numpy(np.float64)
    sig = w[["sig_e", "sig_n", "sig_u"]].to_numpy(np.float64)
    d = w["date"].to_numpy().astype("datetime64[D]")
    ll = w[["lat", "lon"]].to_numpy(np.float64)
    notes: list[str] = []

    # outliers: 5 robust sigmas from a 15-day running median, per component
    keep = np.ones(len(w), bool)
    for c in range(3):
        med = pd.Series(x[:, c]).rolling(15, center=True, min_periods=5).median().to_numpy()
        r = x[:, c] - med
        mad = 1.4826 * np.nanmedian(np.abs(r - np.nanmedian(r)))
        keep &= ~(np.abs(r) > 5 * max(mad, 1e-4))
    outliers = int((~keep).sum())
    x, sig, d, ll = x[keep], sig[keep], d[keep], ll[keep]

    # breaks: equipment changes, and jumps between consecutive days
    brk = np.zeros(len(d), bool)
    for s in steps or []:
        i = int(np.searchsorted(d, s))
        if 0 < i < len(d):
            brk[i] = True
    dx = np.abs(np.diff(x, axis=0))
    lim = np.maximum(np.array([jump_m[0], jump_m[0], jump_m[1]]),
                     5 * np.hypot(sig[1:], sig[:-1]))
    brk[1:] |= np.any(dx > lim, axis=1)
    jumps = [str(v) for v in d[brk]]
    seg = np.cumsum(brk)
    sizes = np.bincount(seg)
    good = sizes[seg] >= min_segment_days
    if not good.any():
        raise DataError(f"{site}: no segment of {min_segment_days} days without a jump in {start}..{end}")
    if (~good).any():
        notes.append(f"{int((~good).sum())} days in segments shorter than {min_segment_days} days dropped")
    x, sig, d, seg, ll = x[good], sig[good], d[good], seg[good], ll[good]
    _, seg = np.unique(seg, return_inverse=True)
    n_seg = int(seg.max()) + 1

    # one linear trend, one offset per segment: the segments are moved onto the first
    if n_seg > 1:
        t = (d - d[0]).astype(np.float64) / 365.25
        a = np.column_stack([t, np.eye(n_seg)[seg]])
        for c in range(3):
            coef, *_ = np.linalg.lstsq(a, x[:, c], rcond=None)
            x[:, c] -= coef[1:][seg] - coef[1]
        notes.append(f"{n_seg} segments re-joined (jumps or equipment changes: {', '.join(jumps[:6])})")
    lat, lon = ll[-1]                                     # where the antenna is at the end of the window
    return Cleaned(site, d, x - x[0], sig, float(lat), float(lon), n_seg, jumps, outliers, notes)
