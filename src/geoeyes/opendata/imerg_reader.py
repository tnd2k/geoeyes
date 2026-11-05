"""NASA GPM IMERG half-hourly precipitation over a box, from the Icechunk store dynamical.org publishes on Source
Cooperative (``dynamical/nasa-imerg-analysis-{late,early}``: 0.1°, 1998 to present, 30 min).

Standalone on purpose: no GeoEyes import, only icechunk (>= 2), xarray and numpy, so that it runs in a separate
Python >= 3.12 when the GeoEyes environment is older (``GEOEYES_ICECHUNK_PYTHON``)::

    python imerg_reader.py late WEST SOUTH EAST NORTH 2024-09-06 2024-09-09 out.npz

writes ``time`` (ISO strings, UTC, start of each half hour), ``mean_mm_h`` (mean over the cells whose centre lies in
the box, at least the nearest cell) and ``max_mm_h`` (wettest cell).
"""
from __future__ import annotations

import sys

ENDPOINT = "https://data.source.coop"
BUCKET = "dynamical"
PREFIX = "nasa-imerg-analysis-{run}/v0.1.0.icechunk"
VAR = "precipitation_surface"           # kg m-2 s-1 = mm/s


def read(run: str, w: float, s: float, e: float, n: float, start: str, end: str):
    import icechunk
    import numpy as np
    import xarray as xr
    st = icechunk.s3_storage(bucket=BUCKET, prefix=PREFIX.format(run=run), endpoint_url=ENDPOINT, anonymous=True,
                             force_path_style=True, region="us-west-2")
    ds = xr.open_zarr(icechunk.Repository.open(st).readonly_session("main").store, chunks=None)
    lat, lon = ds["latitude"].values, ds["longitude"].values
    rows = np.flatnonzero((lat >= s) & (lat <= n))
    cols = np.flatnonzero((lon >= w) & (lon <= e))
    if rows.size == 0:
        rows = np.array([int(np.argmin(np.abs(lat - (s + n) / 2)))])
    if cols.size == 0:
        cols = np.array([int(np.argmin(np.abs(lon - (w + e) / 2)))])
    a = ds[VAR].isel(latitude=slice(rows.min(), rows.max() + 1), longitude=slice(cols.min(), cols.max() + 1)) \
        .sel(time=slice(start, end)).load()
    v = a.values.reshape(a.shape[0], -1) * 3600.0            # mm/h
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # half hours without any value: NaN
        mean, peak = np.nanmean(v, axis=1), np.nanmax(v, axis=1)
    times = np.array([str(t)[:19] for t in a["time"].values])
    return times, mean.astype("float32"), peak.astype("float32"), ds.attrs.get("attribution", "")


def main(argv: list[str]) -> int:
    run, w, s, e, n, start, end, out = argv
    import numpy as np
    times, mean, peak, attribution = read(run, float(w), float(s), float(e), float(n), start, end)
    np.savez(out, time=times, mean_mm_h=mean, max_mm_h=peak, attribution=np.array(attribution))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
