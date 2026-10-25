"""Date conversions. GeoEyes stores acquisition dates as ``datetime64[D]``; these helpers read the
legacy encodings (``YYYYMMDD`` strings, Python ordinals, MATLAB datenums) found in StaMPS outputs."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np

MATLAB_DATENUM_OFFSET = 366  # datenum(d) == d.toordinal() + 366


def parse_yyyymmdd(value: str | int) -> date:
    return datetime.strptime(str(value), "%Y%m%d").date()


def format_yyyymmdd(d: date | np.datetime64) -> str:
    if isinstance(d, np.datetime64):
        d = d.astype("datetime64[D]").item()
    return d.strftime("%Y%m%d")


def from_datenum(datenum: float) -> date:
    return date.fromordinal(int(datenum) - MATLAB_DATENUM_OFFSET)


def to_datenum(d: date) -> int:
    return d.toordinal() + MATLAB_DATENUM_OFFSET


def to_datetime64(dates) -> np.ndarray:
    """Any iterable of ``date`` / ``YYYYMMDD`` / ISO strings -> ``datetime64[D]`` array."""
    out = []
    for d in dates:
        if isinstance(d, str) and len(d) == 8 and d.isdigit():
            d = parse_yyyymmdd(d)
        out.append(np.datetime64(d, "D"))
    return np.array(out, dtype="datetime64[D]")


def decimal_years(dates: np.ndarray, reference: np.datetime64 | None = None) -> np.ndarray:
    """Time in years (365.25 d) relative to ``reference`` (default: first date)."""
    d = np.asarray(dates, dtype="datetime64[D]")
    ref = d[0] if reference is None else np.datetime64(reference, "D")
    return (d - ref).astype(np.float64) / 365.25
