"""Satellite rain archive for the landslide forecast system (docs/en/research/landslide-forecast-system.md, F2).

GSMaP v8 daily at 0.1° (JAXA, FTP login in ``~/.netrc``; the same cell centres as IMERG): ``gsmap_nrt`` (~4 h
latency) and ``gsmap_gauge`` (the NRT calibrated with the CPC gauge analysis, also ~4 h). The files store the mean
rate of the UTC day in mm/h (x 24 here).

IMERG V07 daily (NASA GES DISC), three runs of the same algorithm:

* ``early`` — ~4 h latency: the candidate operational product;
* ``late`` — ~12 h latency;
* ``final`` — ~3.5 months latency, gauge-adjusted: the reference of the archive.

Granule names come from NASA CMR, one search per month (the version letter, V07A / V07B, changes between periods).
Each day is read as a server-side subset of the area through the cloud OPeNDAP service (DAP4 constraint, ~40 kB per
day instead of the 31 MB global file), with the Earthdata login of the user's ``.netrc``. The days are **UTC days**
(00–24 UTC = 07–07 local time): the conversion to local days is done where the rain is used, never here.

Cache: ``<cache>/rainfall/imerg_<run>_<box>_<year>.npz`` with ``mm`` (uint16, 0.1 mm; 65535 = missing), ``dates``,
``lat``, ``lon`` (cell centres) and ``complete``; a year is re-read only for its missing days.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
OPENDAP = "https://opendap.earthdata.nasa.gov/collections/{cid}/granules/{short}.07%3A{name}"
RUNS = {  # run -> (CMR short name, collection concept id)
    "early": ("GPM_3IMERGDE", "C2723754850-GES_DISC"),
    "late": ("GPM_3IMERGDL", "C2723754859-GES_DISC"),
    "final": ("GPM_3IMERGDF", "C2723754864-GES_DISC"),
}
RES = 0.1
LON0, LAT0 = -179.95, -89.95          # first cell centres of the IMERG grid (3600 x 1800)
CENTRAL_VN = (104.5, 10.5, 110.0, 20.0)   # lon_min, lat_min, lon_max, lat_max: the centre with a margin
MISSING = 65535
THREADS = 4
ATTEMPTS = 4


@dataclass
class RainArchive:
    run: str
    dates: list[date]
    lat: np.ndarray                   # (ny,) cell centres, south to north
    lon: np.ndarray                   # (nx,)
    mm: np.ndarray                    # (t, ny, nx) float32, NaN = missing

    def missing_days(self) -> list[date]:
        return [d for d, m in zip(self.dates, np.isnan(self.mm).all(axis=(1, 2)), strict=True) if m]


def box_index(box=CENTRAL_VN) -> tuple[int, int, int, int]:
    """Inclusive index ranges (i lon, j lat) of the IMERG cells whose centres lie inside ``box``."""
    w, s, e, n = box
    i0 = int(np.ceil((w - LON0) / RES - 1e-9))
    i1 = int(np.floor((e - LON0) / RES + 1e-9))
    j0 = int(np.ceil((s - LAT0) / RES - 1e-9))
    j1 = int(np.floor((n - LAT0) / RES + 1e-9))
    return i0, i1, j0, j1


def _session():
    import requests
    return requests.Session()      # the Earthdata login comes from ~/.netrc (never read or printed here)


def granules(run: str, year: int, month: int, session=None) -> dict[date, str]:
    """Day -> granule file name of a run, from CMR."""
    short, _ = RUNS[run]
    s = session or _session()
    start = date(year, month, 1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    for k in range(ATTEMPTS):
        try:
            r = s.get(CMR, params={"short_name": short, "version": "07", "page_size": 62,
                                   "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z"}, timeout=60)
            r.raise_for_status()
            out = {}
            for e in r.json()["feed"]["entry"]:
                name = e["title"].split(":")[-1]
                day = date.fromisoformat(e["time_start"][:10])
                if start <= day <= end and name.endswith(".nc4"):
                    out[day] = name
            return out
        except Exception as exc:                                # network: retried, then reported
            if k == ATTEMPTS - 1:
                raise
            log.debug("CMR %s %d-%02d: %s, retrying", run, year, month, exc)
            time.sleep(3 * (k + 1))
    return {}


def read_day(run: str, name: str, idx: tuple[int, int, int, int], session=None) -> np.ndarray | None:
    """Daily rain (mm, (ny, nx), south to north) of one granule over the index box; None when it cannot be read."""
    import io

    import h5py
    short, cid = RUNS[run]
    i0, i1, j0, j1 = idx
    url = OPENDAP.format(cid=cid, short=short, name=name) + ".dap.nc4"
    ce = f"/precipitation[0][{i0}:{i1}][{j0}:{j1}]"
    s = session or _session()
    for k in range(ATTEMPTS):
        try:
            r = s.get(url, params={"dap4.ce": ce}, timeout=180)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            with h5py.File(io.BytesIO(r.content), "r") as h:
                p = np.asarray(h["precipitation"][0], np.float32)      # (lon, lat)
            p[p < 0] = np.nan
            return p.T                                                  # (lat, lon)
        except Exception as exc:                                        # network: retried, then reported
            if k == ATTEMPTS - 1:
                log.warning("IMERG %s %s: %s", run, name, exc)
                return None
            time.sleep(3 * (k + 1))
    return None


# ---------------------------------------------------------------- GSMaP (JAXA FTP, login in ~/.netrc)
GSMAP_HOST = "hokusai.eorc.jaxa.jp"
GSMAP = {  # run -> path template of the 0.1-deg daily product, 00Z-23Z (mean rate in mm/h; x 24 = mm/day)
    "gsmap_nrt": "/realtime_ver/v8/daily0.1/00Z-23Z/{ym}/gsmap_nrt.{ymd}.0.1d.daily.00Z-23Z.dat.gz",
    "gsmap_gauge": "/realtime_ver/v8/daily0.1_G/00Z-23Z/{ym}/gsmap_gauge.{ymd}.0.1d.daily.00Z-23Z.dat.gz",
}
GSMAP_SHAPE = (1200, 3600)            # lat 59.95 N .. 59.95 S (stored north first, YREV), lon 0.05 .. 359.95 E
_ftp = __import__("threading").local()


def _gsmap_ftp():
    import ftplib
    import netrc
    import os
    if getattr(_ftp, "conn", None) is None:
        rc = os.path.expanduser("~/_netrc" if os.name == "nt" else "~/.netrc")
        login, _, password = netrc.netrc(rc).authenticators(GSMAP_HOST)
        f = ftplib.FTP(GSMAP_HOST, timeout=120)
        f.login(login, password)
        _ftp.conn = f
    return _ftp.conn


def gsmap_names(run: str, year: int, month: int, session=None) -> dict[date, str]:
    """Day -> FTP path of a GSMaP run (the names follow a fixed template: no listing needed)."""
    import calendar
    return {date(year, month, d): GSMAP[run].format(ym=f"{year}{month:02d}", ymd=f"{year}{month:02d}{d:02d}")
            for d in range(1, calendar.monthrange(year, month)[1] + 1)}


def gsmap_read_day(run: str, path: str, idx: tuple[int, int, int, int], session=None) -> np.ndarray | None:
    """Daily rain (mm, (ny, nx), south to north) of one GSMaP file over the IMERG index box (same cell centres)."""
    import ftplib
    import gzip
    import io
    i0, i1, j0, j1 = idx
    for k in range(ATTEMPTS):
        try:
            buf = io.BytesIO()
            _gsmap_ftp().retrbinary(f"RETR {path}", buf.write)
            a = np.frombuffer(gzip.decompress(buf.getvalue()), "<f4").reshape(GSMAP_SHAPE)[::-1]   # south first
            # IMERG index -> GSMaP: lon 0.05 + 0.1 i' = -179.95 + 0.1 i  =>  i' = i - 1800; lat row j' = j - 300
            sub = a[j0 - 300:j1 - 300 + 1, i0 - 1800:i1 - 1800 + 1].astype(np.float32) * 24.0
            sub[sub < 0] = np.nan
            return sub
        except ftplib.error_perm as exc:                             # 550: no such file (not produced)
            log.debug("GSMaP %s: %s", path, exc)
            return None
        except Exception as exc:                                     # network: a new connection, retried
            _ftp.conn = None
            if k == ATTEMPTS - 1:
                log.warning("GSMaP %s: %s", path, exc)
                return None
            time.sleep(3 * (k + 1))
    return None


def _cache_file(cache: Path, run: str, box, year: int) -> Path:
    return Path(cache) / "rainfall" / f"imerg_{run}_{'_'.join(f'{v:g}' for v in box)}_{year}.npz"


def _encode(mm: np.ndarray) -> np.ndarray:
    out = np.full(mm.shape, MISSING, np.uint16)
    ok = np.isfinite(mm)
    out[ok] = np.clip(np.round(mm[ok] * 10), 0, MISSING - 1).astype(np.uint16)
    return out


def _decode(raw: np.ndarray) -> np.ndarray:
    mm = raw.astype(np.float32) / 10
    mm[raw == MISSING] = np.nan
    return mm


def year_archive(run: str, year: int, cache: Path, box=CENTRAL_VN, progress=None, threads: int = THREADS,
                 reader=None, lister=None) -> RainArchive:
    """One year (UTC days) of a run over ``box``, from the cache, reading only the missing days."""
    say = progress or (lambda m: None)
    gs = run in GSMAP
    reader = reader or (gsmap_read_day if gs else read_day)
    lister = lister or (gsmap_names if gs else granules)
    if gs:
        threads = min(threads, 2)                                    # one FTP connection per thread: be gentle
    i0, i1, j0, j1 = idx = box_index(box)
    lat = LAT0 + RES * np.arange(j0, j1 + 1)
    lon = LON0 + RES * np.arange(i0, i1 + 1)
    days = [date(year, 1, 1) + timedelta(d) for d in range((date(year + 1, 1, 1) - date(year, 1, 1)).days)]
    days = [d for d in days if d <= date.today() - timedelta(days=1)]
    f = _cache_file(cache, run, box, year)
    mm = np.full((len(days), len(lat), len(lon)), np.nan, np.float32)
    if f.exists():
        with np.load(f, allow_pickle=False) as z:     # closed at once: Windows cannot replace an open file
            have = {date.fromisoformat(str(d)): k for k, d in enumerate(z["dates"])}
            old = _decode(z["mm"])
            was_complete = bool(z["complete"])
        for t, d in enumerate(days):
            if d in have:
                mm[t] = old[have[d]]
        if was_complete and len(have) >= len(days):
            return RainArchive(run, days, lat, lon, mm)
    todo = [t for t in range(len(days)) if np.isnan(mm[t]).all()]
    if todo:
        s = None if gs else _session()
        names: dict[date, str] = {}
        for m in sorted({days[t].month for t in todo}):
            names.update(lister(run, year, m, s))
        say(f"{run} {year}: reading {len(todo)} day(s)")

        def one(t):
            n = names.get(days[t])
            return t, (reader(run, n, idx, s) if n else None)

        with ThreadPoolExecutor(threads) as ex:
            for k, (t, p) in enumerate(ex.map(one, todo), 1):
                if p is not None and p.shape == mm.shape[1:]:
                    mm[t] = p
                if k % 50 == 0:
                    say(f"{run} {year}: {k}/{len(todo)}")
    missing = int(np.isnan(mm).all(axis=(1, 2)).sum())
    complete = missing == 0 and days[-1] == date(year, 12, 31)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".part.npz")
    np.savez_compressed(tmp, mm=_encode(mm), dates=np.array([d.isoformat() for d in days]), lat=lat, lon=lon,
                        complete=complete)
    tmp.replace(f)
    if missing:
        log.warning("%s %d: %d day(s) missing", run, year, missing)
    return RainArchive(run, days, lat, lon, mm)


def archive(run: str, years: list[int], cache: Path, box=CENTRAL_VN, progress=None) -> RainArchive:
    """Several years of a run, concatenated."""
    parts = [year_archive(run, y, cache, box, progress) for y in years]
    return RainArchive(run, [d for p in parts for d in p.dates], parts[0].lat, parts[0].lon,
                       np.concatenate([p.mm for p in parts]))


THRESHOLDS_MM = (50.0, 100.0, 200.0)
RAIN_MONTHS = (9, 10, 11, 12)


def compare(test: RainArchive, ref: RainArchive, months=RAIN_MONTHS) -> dict:
    """``test`` (e.g. Early) against ``ref`` (Final) on the days and pixels both have, in ``months``: bias, ratio
    of totals, correlation, and for each daily threshold the hit rate (POD), false alarm ratio (FAR) and frequency
    bias; the ratio of the 99th / 99.9th percentiles (the extremes the warnings depend on)."""
    common = sorted(set(test.dates) & set(ref.dates))
    common = [d for d in common if d.month in months]
    ti = [test.dates.index(d) for d in common]
    ri = [ref.dates.index(d) for d in common]
    a, b = test.mm[ti].ravel(), ref.mm[ri].ravel()
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    out = {"days": len(common), "pairs": int(ok.sum()), "mean_test": round(float(a.mean()), 2),
           "mean_ref": round(float(b.mean()), 2), "ratio_totals": round(float(a.sum() / b.sum()), 3),
           "corr": round(float(np.corrcoef(a, b)[0, 1]), 3),
           "p99_ratio": round(float(np.percentile(a, 99) / np.percentile(b, 99)), 3),
           "p999_ratio": round(float(np.percentile(a, 99.9) / np.percentile(b, 99.9)), 3), "thresholds": {}}
    for t in THRESHOLDS_MM:
        hit = int(((a >= t) & (b >= t)).sum())
        miss = int(((a < t) & (b >= t)).sum())
        fa = int(((a >= t) & (b < t)).sum())
        out["thresholds"][f"{t:g}"] = {
            "ref_events": hit + miss, "pod": round(hit / (hit + miss), 3) if hit + miss else None,
            "far": round(fa / (hit + fa), 3) if hit + fa else None,
            "freq_bias": round((hit + fa) / (hit + miss), 3) if hit + miss else None}
    return out


def run_check(study, cache: Path, years=range(2015, 2026), progress=None) -> dict:
    """F2 step 3 (first part): IMERG Early against Final over the centre in the rainy season, per year and pooled;
    ``<study>/rain_f2/f2_early_vs_final.json`` and ``.md``."""
    from geoeyes.io.manifest import atomic_write_json
    say = progress or (lambda m: log.info("%s", m))
    ys = list(years)
    e, f = archive("early", ys, cache, progress=say), archive("final", ys, cache, progress=say)
    res = {"box": CENTRAL_VN, "months": RAIN_MONTHS, "pooled": compare(e, f), "by_year": {}}
    for y in ys:
        ey = RainArchive("early", [d for d in e.dates if d.year == y], e.lat, e.lon,
                         e.mm[[k for k, d in enumerate(e.dates) if d.year == y]])
        fy = RainArchive("final", [d for d in f.dates if d.year == y], f.lat, f.lon,
                         f.mm[[k for k, d in enumerate(f.dates) if d.year == y]])
        if ey.dates and fy.dates:
            res["by_year"][y] = compare(ey, fy)
    out = study.step_dir("rain_f2")
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "f2_early_vs_final.json", res)
    (out / "f2_early_vs_final.md").write_text(check_md(res), encoding="utf-8")
    return res


def check_md(r: dict) -> str:
    p = r["pooled"]
    L = ["# F2 — IMERG Early against IMERG Final (central Vietnam, September–December)", "",
         f"Box {r['box']}; {p['days']} days, {p['pairs']:,} pixel-days. Final is gauge-adjusted (monthly): the "
         "reference here. Gauges are the next check.", "",
         f"- ratio of totals Early / Final: **{p['ratio_totals']}**; correlation {p['corr']}",
         f"- ratio of the 99th percentile: **{p['p99_ratio']}**; of the 99.9th: **{p['p999_ratio']}**", "",
         "| daily threshold (mm) | events in Final | POD | FAR | frequency bias |", "|---|---|---|---|---|"]
    for t, v in p["thresholds"].items():
        L.append(f"| ≥ {t} | {v['ref_events']:,} | {v['pod']} | {v['far']} | {v['freq_bias']} |")
    L += ["", "| year | ratio of totals | corr | p99 ratio | POD ≥ 100 mm | FAR ≥ 100 mm |",
          "|---|---|---|---|---|---|"]
    for y, v in r["by_year"].items():
        t = v["thresholds"]["100"]
        L.append(f"| {y} | {v['ratio_totals']} | {v['corr']} | {v['p99_ratio']} | {t['pod']} | {t['far']} |")
    return "\n".join(L) + "\n"


CORE_BOX = (107.2, 14.0, 108.8, 16.1)     # Quảng Nam – Kon Tum (the calibration area)
STORM_DAYS = {"Ketsana": ["2009-09-29", "2009-09-30"], "Podul": ["2013-11-15", "2013-11-16"],
              "Molave": ["2020-10-27", "2020-10-28", "2020-10-29"], "Oct 2020 rains": ["2020-10-10", "2020-10-11",
                                                                                       "2020-10-17", "2020-10-18"]}
PRODUCTS = ("early", "gsmap_nrt", "gsmap_gauge", "final")


def _years(a: RainArchive, ys) -> RainArchive:
    k = [i for i, d in enumerate(a.dates) if d.year in ys]
    return RainArchive(a.run, [a.dates[i] for i in k], a.lat, a.lon, a.mm[k])


def _core(a: RainArchive, box=CORE_BOX) -> tuple[np.ndarray, np.ndarray]:
    w, s, e, n = box
    return ((a.lat >= s) & (a.lat <= n)), ((a.lon >= w) & (a.lon <= e))


def storm_table(arcs: dict[str, RainArchive], box=CORE_BOX) -> dict:
    """Core-box maximum and mean (mm/day) of every product on the storm days."""
    out: dict = {}
    for storm, days in STORM_DAYS.items():
        for ds in days:
            d = date.fromisoformat(ds)
            row = {}
            for run, a in arcs.items():
                if d not in a.dates:
                    row[run] = None
                    continue
                jy, ix = _core(a, box)
                v = a.mm[a.dates.index(d)][np.ix_(jy, ix)]
                row[run] = None if np.isnan(v).all() else {"max": round(float(np.nanmax(v)), 1),
                                                            "mean": round(float(np.nanmean(v)), 1)}
            out[f"{storm} {ds}"] = row
    return out


def run_products(study, cache: Path, years=range(2015, 2026), progress=None) -> dict:
    """F2 step 3: every near-real-time product (IMERG Early, GSMaP NRT, GSMaP Gauge) against IMERG Final and
    against each other, September–December, over the centre and the core box; storm-day maxima.
    ``<study>/rain_f2/f2_products.json`` and ``.md``."""
    from geoeyes.io.manifest import atomic_write_json
    say = progress or (lambda m: log.info("%s", m))
    ys = list(years)
    extra = sorted({int(d[:4]) for v in STORM_DAYS.values() for d in v} - set(ys))
    arcs = {r: archive(r, ys + extra, cache, progress=say) for r in PRODUCTS}
    main = {r: _years(a, set(ys)) for r, a in arcs.items()}
    pairs = [("early", "final"), ("gsmap_nrt", "final"), ("gsmap_gauge", "final"), ("gsmap_nrt", "early"),
             ("gsmap_gauge", "early")]
    res: dict = {"box": CENTRAL_VN, "core_box": CORE_BOX, "months": RAIN_MONTHS, "years": ys,
                 "missing_days": {r: len(a.missing_days()) for r, a in main.items()}, "pooled": {}, "core": {},
                 "by_year": {}, "storms": storm_table(arcs)}
    for t, r in pairs:
        key = f"{t} vs {r}"
        res["pooled"][key] = compare(main[t], main[r])
        jy, ix = _core(main[t])
        ct = RainArchive(t, main[t].dates, main[t].lat[jy], main[t].lon[ix], main[t].mm[:, jy][:, :, ix])
        cr = RainArchive(r, main[r].dates, main[r].lat[jy], main[r].lon[ix], main[r].mm[:, jy][:, :, ix])
        res["core"][key] = compare(ct, cr)
        res["by_year"][key] = {y: compare(_years(main[t], {y}), _years(main[r], {y})) for y in ys}
        say(f"{key}: done")
    out = study.step_dir("rain_f2")
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "f2_products.json", res)
    (out / "f2_products.md").write_text(products_md(res), encoding="utf-8")
    return res


def products_md(r: dict) -> str:
    L = ["# F2 — near-real-time rain products against IMERG Final (central Vietnam, September–December)", "",
         f"Years {r['years'][0]}–{r['years'][-1]}; box {r['box']}; core {r['core_box']} (Quảng Nam – Kon Tum). "
         "IMERG Final and GSMaP Gauge are gauge-adjusted with global gauge sets (GPCC, CPC): neither is "
         "independent of the satellites. The decisive check is against KTTV gauges.", "",
         "Missing days: " + ", ".join(f"{k} {v}" for k, v in r["missing_days"].items()), ""]
    for scope in ("pooled", "core"):
        L += [f"## {'Whole box' if scope == 'pooled' else 'Core box'}", "",
              "| pair | ratio of totals | corr | p99 ratio | p99.9 ratio | POD/FAR ≥ 100 | POD/FAR ≥ 200 | "
              "freq bias ≥ 200 |", "|---|---|---|---|---|---|---|---|"]
        for k, v in r[scope].items():
            t1, t2 = v["thresholds"]["100"], v["thresholds"]["200"]
            L.append(f"| {k} | {v['ratio_totals']} | {v['corr']} | {v['p99_ratio']} | {v['p999_ratio']} | "
                     f"{t1['pod']} / {t1['far']} | {t2['pod']} / {t2['far']} | {t2['freq_bias']} |")
        L.append("")
    L += ["## Storm days, core box (max / mean mm per day)", "", "| day | " + " | ".join(PRODUCTS) + " |",
          "|---|" + "---|" * len(PRODUCTS)]
    for day, row in r["storms"].items():
        cells = [f"{v['max']} / {v['mean']}" if v else "—" for v in (row.get(p) for p in PRODUCTS)]
        L.append(f"| {day} | " + " | ".join(cells) + " |")
    L += ["", "## Ratio of totals per year (whole box, against Final)", "",
          "| year | " + " | ".join(k for k in r["by_year"] if k.endswith("final")) + " |",
          "|---|" + "---|" * sum(k.endswith("final") for k in r["by_year"])]
    for y in r["years"]:
        L.append(f"| {y} | " + " | ".join(str(v[y]["ratio_totals"]) for k, v in r["by_year"].items()
                                           if k.endswith("final")) + " |")
    return "\n".join(L) + "\n"


def run_archive(study_or_none, cache: Path, runs=("early", "final"), years=range(2015, 2026), progress=None) -> dict:
    """F2 step 1: the IMERG archive of the centre; a summary per run and year (days, missing, max)."""
    say = progress or (lambda m: log.info("%s", m))
    out: dict = {}
    for run in runs:
        out[run] = {}
        for y in years:
            a = year_archive(run, y, cache, progress=say)
            miss = len(a.missing_days())
            out[run][y] = {"days": len(a.dates), "missing": miss,
                           "max_mm_day": round(float(np.nanmax(a.mm)), 1) if miss < len(a.dates) else None}
            say(f"{run} {y}: {len(a.dates)} days, {miss} missing")
    return out
