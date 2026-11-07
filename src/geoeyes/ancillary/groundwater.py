"""Groundwater storage over an AOI from NASA GLDAS (Catchment model, GRACE / GRACE-FO data assimilation,
``GLDAS_CLSM025_DA1_D`` v2.2: daily, 0.25°, global from 2003; variable ``GWS_tavg``, mm of water), subset by NASA
Harmony (Earthdata login: ``EARTHDATA_TOKEN``) and cached as monthly means per pixel under
``<workspace>/cache/groundwater``.

The grid is coarse (~27 km; the GRACE information inside is coarser still, ~300 km): within a city it is a
*temporal* driver — the regional rise and fall of groundwater storage — not a map of where water is pumped.
That is how GeoEyes uses it: coupling with the InSAR series (hazard), features of the forecast
(docs/en/research/groundwater-insar.md).
"""
from __future__ import annotations

import calendar
import io
import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np

from geoeyes.ancillary.rainfall import RainGrid, _months
from geoeyes.core.errors import DataError

log = logging.getLogger(__name__)

SHORT_NAME = "GLDAS_CLSM025_DA1_D"
VERSION = "2.2"
VARIABLE = "GWS_tavg"
RES = 0.25
SOURCE = ("GLDAS Catchment Land Surface Model L4 daily 0.25° with GRACE data assimilation, v2.2 "
          "(GLDAS_CLSM025_DA1_D, NASA GES DISC), groundwater storage")
CMR = "https://cmr.earthdata.nasa.gov/search/collections.json"
HARMONY = "https://harmony.earthdata.nasa.gov"


def _request(url: str, token: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "GeoEyes"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _collection(token: str) -> str:
    q = urllib.parse.urlencode({"short_name": SHORT_NAME, "version": VERSION})
    entries = json.loads(_request(f"{CMR}?{q}", token))["feed"]["entry"]
    if not entries:
        raise DataError(f"{SHORT_NAME} v{VERSION} not found in the NASA CMR")
    return entries[0]["id"]


def _snap(bbox: list[float]) -> tuple[float, float, float, float]:
    """The bbox grown to whole 0.25° pixels (pixel centres at x.125, x.375, ...)."""
    w, s, e, n = bbox
    f = 1 / RES
    return (float(np.floor(w * f) / f), float(np.floor(s * f) / f), float(np.ceil(e * f) / f),
            float(np.ceil(n * f) / f))


def _harmony_daily(token: str, box, first: date, last: date, progress=None,
                   timeout_s: int = 7200) -> dict[str, np.ndarray]:
    """Daily ``GWS_tavg`` blocks {YYYY-MM-DD: (ny, nx)} for ``first``..``last`` (one Harmony job)."""
    import xarray as xr
    cid = _collection(token)
    w, s, e, n = box
    q = (f"subset=lat({s}:{n})&subset=lon({w}:{e})"
         f"&subset=time(%22{first}T00:00:00Z%22:%22{last}T23:59:59Z%22)&format=application/x-netcdf4"
         "&skipPreview=true")                         # large jobs otherwise pause after a preview
    url = f"{HARMONY}/{cid}/ogc-api-coverages/1.0.0/collections/{VARIABLE}/coverage/rangeset?{q}"
    job = json.loads(_request(url, token))
    job_url = next((ln["href"] for ln in job.get("links", []) if ln.get("rel") == "self"), None) or \
        f"{HARMONY}/jobs/{job['jobID']}"
    t0 = time.time()
    while job.get("status") in ("accepted", "running", "running_with_errors", "previewing", "paused"):
        if job.get("status") == "paused":
            resume = next((ln["href"] for ln in job.get("links", []) if ln.get("rel") == "resumer"),
                          f"{HARMONY}/jobs/{job['jobID']}/resume")
            _request(resume, token)
        if time.time() - t0 > timeout_s:
            raise DataError(f"Harmony job {job.get('jobID')} not finished after {timeout_s} s")
        if progress:
            progress(f"groundwater: NASA Harmony {first.year}: {job.get('progress', 0)} %")
        time.sleep(15)
        job = json.loads(_request(job_url, token))
    if job.get("status") not in ("successful", "complete_with_errors"):
        raise DataError(f"Harmony job failed: {job.get('status')} {job.get('message')}")
    links, page = [], job
    while True:
        links += [ln["href"] for ln in page.get("links", []) if ln.get("rel") == "data"]
        nxt = next((ln["href"] for ln in page.get("links", []) if ln.get("rel") == "next"), None)
        if not nxt:
            break
        page = json.loads(_request(nxt, token))
    out: dict[str, np.ndarray] = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        for data in pool.map(lambda u: _request(u, token), links):
            ds = xr.open_dataset(io.BytesIO(data), engine="h5netcdf")
            a = ds[VARIABLE].values.astype(np.float32)
            a[a <= -9998] = np.nan
            lat = ds["lat"].values
            for i, tt in enumerate(ds["time"].values):
                block = a[i]
                if lat[0] < lat[-1]:                                  # rows from north to south, as RainGrid
                    block = block[::-1]
                out[str(np.datetime64(tt, "D"))] = block
    return out


OPENDAP = "https://opendap.earthdata.nasa.gov/collections"
GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
LAT0, LON0, NLAT = -60.0, -180.0, 600              # GLDAS 0.25° grid: lower-left corner, rows (lat ascending)


def _granules(cid: str, first: date, last: date) -> list[tuple[str, str]]:
    """(YYYY-MM-DD, granule UR) of every daily file in ``first``..``last`` (CMR, paged)."""
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({"collection_concept_id": cid, "page_size": 2000, "page_num": page,
                                    "temporal": f"{first}T00:00:00Z,{last}T23:59:59Z", "sort_key": "start_date"})
        req = urllib.request.Request(f"{GRANULES}?{q}", headers={"User-Agent": "GeoEyes"})
        with urllib.request.urlopen(req, timeout=120) as r:
            entries = json.loads(r.read())["feed"]["entry"]
        out += [(e["time_start"][:10], e["title"]) for e in entries]
        if len(entries) < 2000:
            return out
        page += 1


def _opendap_daily(token: str, box, first: date, last: date, progress=None, workers: int = 16) -> dict[str, np.ndarray]:
    """Daily ``GWS_tavg`` blocks {YYYY-MM-DD: (ny, nx)}: one tiny subset per day from the Earthdata Cloud OPeNDAP
    (a few kB each, 16 at a time: about a minute per year). Harmony queues the same subsetting server-side, which
    takes from minutes to an hour per year whatever the client machine."""
    from concurrent.futures import ThreadPoolExecutor
    cid = _collection(token)
    w, s, e, n = box
    i0, i1 = round((s - LAT0) / RES), round((n - LAT0) / RES) - 1
    j0, j1 = round((w - LON0) / RES), round((e - LON0) / RES) - 1
    ce = urllib.parse.quote(f"/{VARIABLE}[0:1:0][{i0}:1:{i1}][{j0}:1:{j1}]")
    days = _granules(cid, first, last)

    def one(item):
        day, ur = item
        url = f"{OPENDAP}/{cid}/granules/{urllib.parse.quote(ur, safe='')}.dap.csv?dap4.ce={ce}"
        for k in range(4):
            try:
                text = _request(url, token, timeout=90).decode("utf-8", "replace")
                break
            except Exception:                              # transient cloud errors: a few retries
                if k == 3:
                    raise
                time.sleep(2 * (k + 1))
        rows = [[float(v) for v in ln.split(",")[1:]] for ln in text.splitlines() if ln.startswith(f"/{VARIABLE}[")]
        a = np.asarray(rows, np.float32)
        a[a <= -9998] = np.nan
        return day, a[::-1]                                # rows from north to south, as RainGrid

    out: dict[str, np.ndarray] = {}
    with ThreadPoolExecutor(workers) as pool:
        for k, (day, a) in enumerate(pool.map(one, days), 1):
            out[day] = a
            if progress and (k % 30 == 0 or k == len(days)):
                progress(f"groundwater: GLDAS {first.year}: {k}/{len(days)} days")
    return out


def monthly_grid(cache: Path, bbox: list[float], start: date, end: date, token: str, progress=None) -> RainGrid:
    """Monthly mean groundwater storage (mm) per 0.25° pixel; months not published yet are NaN. Months already
    in the cache are not asked again."""
    if not token:
        raise DataError("EARTHDATA_TOKEN is required for the GLDAS groundwater data")
    box = _snap(bbox)
    ny, nx = round((box[3] - box[1]) / RES), round((box[2] - box[0]) / RES)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"gldas_gws_{'_'.join(f'{v:.2f}' for v in box)}.npz"
    known: dict[str, np.ndarray] = {}
    if f.exists():
        with np.load(f) as z:
            known = {str(k): z["mm"][i] for i, k in enumerate(z["keys"])}
    keys = [f"{y}-{m:02d}" for y, m in _months(start, end)]
    todo = [k for k in keys if k not in known]
    if todo:
        # one Harmony job per year, run side by side (a single job over years takes about an hour); every year is
        # cached as soon as it arrives, so an interrupted run resumes where it stopped
        years: dict[str, list[str]] = {}
        for k in todo:
            years.setdefault(k[:4], []).append(k)
        chunks = []
        for ks in years.values():
            y, m = map(int, ks[-1].split("-"))
            chunks.append((date.fromisoformat(f"{ks[0]}-01"),
                           min(date(y, m, calendar.monthrange(y, m)[1]), date.today())))
        if progress:
            progress(f"groundwater: GLDAS {chunks[0][0]} .. {chunks[-1][1]} over {box}, {len(chunks)} year(s)")
        # OPeNDAP subsets year by year (each year cached as soon as it is in); Harmony only if OPeNDAP fails
        for a, b in chunks:
            try:
                daily = _opendap_daily(token, box, a, b, progress)
            except Exception as exc:
                log.warning("groundwater: OPeNDAP failed for %s (%s: %s); falling back to Harmony", a.year,
                            type(exc).__name__, exc)
                daily = _harmony_daily(token, box, a, b, progress)
            known.update(_monthly(daily, (ny, nx)))
            if known:
                ks = sorted(known)
                np.savez(f, keys=np.array(ks), mm=np.stack([known[k] for k in ks]))
    mm = np.stack([known.get(k, np.full((ny, nx), np.nan, np.float32)) for k in keys]) if keys else \
        np.zeros((0, ny, nx), np.float32)
    return RainGrid(list(keys), mm.astype(np.float32), box[0], box[3], RES, source=SOURCE)


def _monthly(daily: dict[str, np.ndarray], shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Monthly means of daily blocks; a month counts once it is (almost) complete (GLDAS comes with a lag)."""
    by_month: dict[str, list[np.ndarray]] = {}
    for d, a in daily.items():
        by_month.setdefault(d[:7], []).append(a)
    out = {}
    for m, blocks in by_month.items():
        stack = np.stack(blocks)
        if stack.shape[1:] == shape and len(blocks) >= calendar.monthrange(*map(int, m.split("-")))[1] - 2:
            out[m] = np.nanmean(stack, axis=0).astype(np.float32)
    return out
