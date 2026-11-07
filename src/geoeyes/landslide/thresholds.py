"""L6 of the landslide study: rainfall thresholds for the reported landslides of Vietnam (Q2, H4).

Rain: CHIRPS v3 daily ``sat`` (0.05°, 1998 →) over Vietnam, cached per year in
``<cache>/rainfall/chirps3_sat_vn_<year>.npz`` (uint16, 0.1 mm; the whole country, so L7 / L9 read the same files).

Events: ``vietnam.csv`` rows with day precision, slope types (riverbank collapses out), location within 25 km, plus
the three Das dates; north (≥ 19.5° N) and centre (11–19.5° N). Reports of the same day on the same pixel count once.

Rainfall events (simplified CTRL-T, Melillo et al. 2018): wet days ≥ 1 mm, an event ends after ≥ 2 dry days. A
landslide takes the event that holds its day or ended the day before, its E and D counted up to the landslide day.
Non-landslide sample: every rainfall event of the rainy season (north May–Oct, centre Sep–Dec) at the same pixels
from 2007, except those within ±3 days of a reported landslide within 25 km.

Thresholds:
- E = α·D^β at 5 % non-exceedance of the landslide events (frequentist, Brunetti et al. 2010: the log-log fit
  shifted by the 5 % quantile of a Gaussian of its residuals), bootstrap intervals;
- antecedent rain A5 / A10 / A30 as a percentile of the same pixel's climatology within ±15 calendar days
  (1998 →), the threshold of maximum TSS between landslide days and rainy-season days without a nearby report.
Validation: leave-one-year-out (the thresholds fitted without the year, scored on it).
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/{y}/chirps-v3.0.sat.{y}.{m:02d}.{d:02d}.tif"
SOURCE = "CHIRPS v3.0 daily sat (Climate Hazards Center, UC Santa Barbara), 0.05°"
VN_BOX = (102.0, 8.0, 110.0, 23.5)
RES = 0.05
FIRST_YEAR = 1998
THREADS = 3                        # 6 got throttled (random days refused)
TAIL_DAYS = 90                     # days this recent may not be published yet: read one by one, stop at the first gap
WET_MM = 1.0
DRY_GAP = 2
REGIONS = {"north": (19.5, 90.0), "centre": (11.0, 19.5)}
SEASON = {"north": (5, 10), "centre": (9, 12)}
SAMPLE_FROM = 2007
EXCLUDE_DAYS, EXCLUDE_KM = 3, 25.0
MAX_ACCURACY_M = 25_000
SLOPE_TYPES = {"landslide", "debris_flow", "mudslide", "rock_fall", "complex", "flash_flood_landslide"}
ANTECEDENT = (5, 10, 30)                # L0 gate (2026-11-05); L4 results were computed with 3/7/30
CLIM_HALF_WINDOW = 15
ED_PROB = 0.05
N_BOOT = 1000
DAS_EVENTS = {"Ketsana": ("2009-09-29", 15.10, 107.90), "Podul": ("2013-11-15", 15.10, 107.90),
              "Molave": ("2020-10-28", 15.10, 107.90)}


# ---------------------------------------------------------------- rain
def _shape() -> tuple[int, int]:
    w, s, e, n = VN_BOX
    return round((n - s) / RES), round((e - w) / RES)


def _read_day(day: pd.Timestamp, attempts: int = 4, wait: float = 2.0) -> np.ndarray | None:
    import rasterio
    from rasterio.windows import from_bounds

    from geoeyes.ml.layers import _ENV
    url = URL.format(y=day.year, m=day.month, d=day.day)
    err = ""
    for attempt in range(attempts):
        try:
            with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + url) as src:
                win = from_bounds(*VN_BOX, src.transform).round_offsets().round_lengths()
                a = src.read(1, window=win, boundless=True).astype(np.float32)
                if src.nodata is not None:
                    a[a == src.nodata] = np.nan
            a[a < 0] = np.nan
            return a
        except Exception as exc:                                   # 404 = not published; else retry
            if "404" in str(exc):
                return None
            err = str(exc)[:120]
            time.sleep(wait * (attempt + 1))
    log.warning("CHIRPS %s: not read after %d attempts (%s)", day.date(), attempts, err)
    return None


def _repair(f: Path, mm: np.ndarray, dates: list[str], progress=None) -> np.ndarray:
    """Days missing from a cached year (the server throttles parallel clients) read again one at a time, slowly;
    the file is rewritten with what came back."""
    miss = [k for k in range(len(dates)) if np.isnan(mm[k]).all()]
    if not miss:
        _save(f, mm, dates, complete=True, repaired=True)
        return mm
    h, w = _shape()
    got = 0
    for k in miss:
        a = _read_day(pd.Timestamp(dates[k]), attempts=6, wait=5.0)
        if a is not None:
            mm[k] = a[:h, :w]
            got += 1
        time.sleep(0.5)
    _save(f, mm, dates, complete=True, repaired=True)
    if progress:
        progress(f"L6: CHIRPS {dates[0][:4]}: {got}/{len(miss)} missing days read again")
    return mm


def _save(f: Path, mm: np.ndarray, dates: list[str], complete: bool, repaired: bool) -> None:
    q = np.where(np.isfinite(mm), np.clip(np.round(mm * 10), 0, np.iinfo(np.uint16).max - 1),
                 np.iinfo(np.uint16).max).astype(np.uint16)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, mm=q, dates=np.array(dates), complete=np.array(complete), repaired=np.array(repaired))


def year_grid(cache: Path, year: int, progress=None) -> tuple[np.ndarray, list[str]]:
    """Daily rain (mm, float32, NaN = missing) of one year over ``VN_BOX``; a year still running is not cached
    beyond its last published day and is asked again next time."""
    f = cache / f"chirps3_sat_vn_{year}.npz"
    today = pd.Timestamp.today().normalize()
    h, w = _shape()
    old_mm, old_dates = np.zeros((0, h, w), np.float32), []
    if f.exists():
        z = np.load(f)
        dates = [str(d) for d in z["dates"]]
        mm = z["mm"].astype(np.float32) / 10.0
        mm[z["mm"] == np.iinfo(np.uint16).max] = np.nan
        if z.get("complete", np.array(False)).item():
            if not z.get("repaired", np.array(False)).item():          # one slow pass over the missing days
                mm = _repair(f, mm, dates, progress)
            return mm, dates
        old_mm, old_dates = mm, dates             # year cached while running: only the days after it are read
    first = pd.Timestamp(old_dates[-1]) + pd.Timedelta(days=1) if old_dates else pd.Timestamp(f"{year}-01-01")
    days = pd.date_range(first, min(pd.Timestamp(f"{year}-12-31"), today - pd.Timedelta(days=1)))
    # days surely published are read in parallel; the recent tail one at a time up to the first day not
    # published, since every request for an absent file counts as "probing" for the server's CrowdSec
    sure = days[days < today - pd.Timedelta(days=TAIL_DAYS)]
    with ThreadPoolExecutor(THREADS) as ex:
        arrs = list(ex.map(_read_day, sure))
    for day in days[len(sure):]:
        a = _read_day(day)
        if a is None:
            break
        arrs.append(a)
    mm = np.full((len(arrs), h, w), np.nan, np.float32)
    for k, a in enumerate(arrs):
        if a is not None:
            mm[k] = a[:h, :w]
    keep = len(arrs)
    while keep and arrs[keep - 1] is None:                         # unpublished tail
        keep -= 1
    mm = np.concatenate([old_mm, mm[:keep]])
    dates = old_dates + [d.date().isoformat() for d in days[:keep]]
    _save(f, mm, dates, complete=bool(dates) and dates[-1] == f"{year}-12-31", repaired=False)
    if progress:
        progress(f"L6: CHIRPS {year}: {len(dates)} days, {int(np.isnan(mm).all(axis=(1, 2)).sum())} missing")
    return mm, dates


def pixel_of(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    w, _, _, n = VN_BOX
    return (np.floor((n - np.asarray(lat)) / RES).astype(int), np.floor((np.asarray(lon) - w) / RES).astype(int))


def pixel_series(cache: Path, rows: np.ndarray, cols: np.ndarray, first: int, last: int,
                 progress=None) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Daily rain (days, n_pixels) at the given pixels, years ``first``–``last``."""
    out, dates = [], []
    for y in range(first, last + 1):
        mm, d = year_grid(cache, y, progress)
        out.append(mm[:, rows, cols])
        dates += d
    return np.concatenate(out), pd.DatetimeIndex(dates)


# ---------------------------------------------------------------- events
def landslide_events(inventory: Path) -> pd.DataFrame:
    t = pd.read_csv(inventory)
    t = t[(t.date_precision == "day") & t.type.isin(SLOPE_TYPES)]
    t = t[t.accuracy_m.isna() | (t.accuracy_m <= MAX_ACCURACY_M)]
    das = pd.DataFrame([{"date": d, "lat": la, "lon": lo, "type": "landslide", "source_db": "das2024", "place": k}
                        for k, (d, la, lo) in DAS_EVENTS.items()])
    t = pd.concat([t[["date", "lat", "lon", "type", "source_db", "place"]], das], ignore_index=True)
    t["date"] = pd.to_datetime(t.date)
    t["region"] = None
    for name, (lo, hi) in REGIONS.items():
        t.loc[(t.lat >= lo) & (t.lat < hi), "region"] = name
    t = t[t.region.notna()].copy()
    t["row"], t["col"] = pixel_of(t.lat, t.lon)
    return t.drop_duplicates(["date", "row", "col"]).reset_index(drop=True)


def rain_events(r: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) day indices of the rainfall events of one daily series (inclusive)."""
    wet = np.nan_to_num(r) >= WET_MM
    out, start, dry = [], None, 0
    for k, w in enumerate(wet):
        if w:
            if start is None:
                start = k
            dry, last = 0, k
        elif start is not None:
            dry += 1
            if dry >= DRY_GAP:
                out.append((start, last))
                start = None
    if start is not None:
        out.append((start, last))
    return out


def triggering(events: list[tuple[int, int]], k: int) -> tuple[int, int] | None:
    """The event holding day ``k`` or ending the day before, cut at ``k``."""
    for s, e in events:
        if s <= k <= e:
            return s, k
        if e == k - 1:
            return s, e
    return None


def antecedent(r: np.ndarray, n: int) -> np.ndarray:
    """Sum of the ``n`` days ending on each day (NaN as 0)."""
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r))])
    out = np.full(len(r), np.nan)
    out[n - 1:] = c[n:] - c[:-n]
    return out


def percentile_of(a: np.ndarray, dates: pd.DatetimeIndex, half: int = CLIM_HALF_WINDOW) -> np.ndarray:
    """Each day's value as a percentile (0–100) of the same series within ±``half`` calendar days, all years."""
    doy = dates.dayofyear.to_numpy()
    out = np.full(len(a), np.nan)
    ok = np.isfinite(a)
    for d in range(1, 367):
        dist = np.abs(doy - d)
        dist = np.minimum(dist, 366 - dist)
        pool = np.sort(a[ok & (dist <= half)])
        sel = ok & (doy == d)
        if pool.size and sel.any():
            out[sel] = 100.0 * np.searchsorted(pool, a[sel], side="right") / pool.size
    return out


@dataclass
class Samples:
    ls: pd.DataFrame        # landslide events: region, year, E, D, A5/A10/A30 (mm and percentile)
    ev: pd.DataFrame        # non-landslide rainfall events: region, year, E, D
    days: pd.DataFrame      # non-landslide rainy-season days: region, year, A*/A*_pct


def build_samples(cache: Path, events: pd.DataFrame, last_year: int, progress=None) -> Samples:
    pix = events[["row", "col"]].drop_duplicates().reset_index(drop=True)
    rain, dates = pixel_series(cache, pix.row.to_numpy(), pix.col.to_numpy(), FIRST_YEAR, last_year, progress)
    pid = {(r, c): i for i, (r, c) in enumerate(zip(pix.row, pix.col, strict=True))}
    events = events.assign(pid=[pid[(r, c)] for r, c in zip(events.row, events.col, strict=True)])
    day_ix = {d: i for i, d in enumerate(dates)}
    lat = events.groupby("pid").lat.first()
    lon = events.groupby("pid").lon.first()
    region = events.groupby("pid").region.first()
    ls_rows, ev_rows, day_rows = [], [], []
    rep = events[["date", "lat", "lon"]].to_numpy()
    for p in range(len(pix)):
        r = rain[:, p]
        evs = rain_events(r)
        ant = {n: antecedent(r, n) for n in ANTECEDENT}
        pct = {n: percentile_of(ant[n], dates) for n in ANTECEDENT}
        reg = region[p]
        for x in events[events.pid == p].itertuples():
            k = day_ix.get(x.date)
            if k is None:
                continue
            tr = triggering(evs, k)
            rec = {"region": reg, "year": x.date.year, "date": x.date.date().isoformat(), "pid": p,
                   "source_db": x.source_db, "E": np.nan, "D": 0}
            if tr is not None:
                rec["E"], rec["D"] = float(np.nansum(r[tr[0]:tr[1] + 1])), tr[1] - tr[0] + 1
            for n in ANTECEDENT:
                rec[f"A{n}"], rec[f"A{n}_pct"] = ant[n][k], pct[n][k]
            ls_rows.append(rec)
        # reports within 25 km of this pixel: their days (±3) are excluded from the negatives
        km = 111.0 * np.hypot((rep[:, 1].astype(float) - lat[p]),
                              (rep[:, 2].astype(float) - lon[p]) * np.cos(np.radians(lat[p])))
        bad = np.zeros(len(dates), bool)
        for d in rep[km <= EXCLUDE_KM, 0]:
            k = day_ix.get(pd.Timestamp(d))
            if k is not None:
                bad[max(0, k - EXCLUDE_DAYS):k + EXCLUDE_DAYS + 1] = True
        m0, m1 = SEASON[reg]
        months = dates.month.to_numpy()
        season = (months >= m0) & (months <= m1) & (dates.year.to_numpy() >= SAMPLE_FROM)
        for s, e in evs:
            if season[e] and not bad[s:e + 1].any():
                ev_rows.append({"region": reg, "year": int(dates[e].year), "pid": p,
                                "E": float(np.nansum(r[s:e + 1])), "D": e - s + 1})
        ok = season & ~bad
        day_rows.append(pd.DataFrame({"region": reg, "year": dates.year.to_numpy()[ok], "pid": p,
                                      **{f"A{n}": ant[n][ok] for n in ANTECEDENT},
                                      **{f"A{n}_pct": pct[n][ok] for n in ANTECEDENT}}))
    return Samples(pd.DataFrame(ls_rows), pd.DataFrame(ev_rows), pd.concat(day_rows, ignore_index=True))


# ---------------------------------------------------------------- thresholds
def ed_threshold(E: np.ndarray, D: np.ndarray, prob: float = ED_PROB) -> tuple[float, float]:
    """(α, β) of E = α·D^β at the ``prob`` non-exceedance of the landslide events (Gaussian of the log residuals)."""
    from scipy.stats import norm
    x, y = np.log10(D), np.log10(E)
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b * x)
    return float(10 ** (a + res.mean() + norm.ppf(prob) * res.std(ddof=1))), float(b)


def tss(pos: np.ndarray, neg: np.ndarray) -> dict:
    """Hit rate, false alarm rate and TSS of 'above' flags on positives and negatives."""
    h, f = float(np.mean(pos)) if len(pos) else np.nan, float(np.mean(neg)) if len(neg) else np.nan
    return {"hit_rate": round(h, 3), "false_alarm": round(f, 4), "tss": round(h - f, 3)}


def best_cut(pos: np.ndarray, neg: np.ndarray) -> tuple[float, dict]:
    """The cut (value ≥ cut = alarm) of maximum TSS."""
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    cand = np.unique(np.quantile(pos, np.linspace(0, 1, 201)))
    sc = [(np.mean(pos >= c) - np.mean(neg >= c), c) for c in cand]
    _, c = max(sc)
    return float(c), tss(pos >= c, neg >= c)


def fit_region(ls: pd.DataFrame, ev: pd.DataFrame, days: pd.DataFrame, rng=None, n_boot: int = N_BOOT) -> dict:
    out: dict = {"landslides": int(len(ls)), "with_rain_event": int(ls.E.notna().sum()),
                 "non_landslide_events": int(len(ev)), "negative_days": int(len(days))}
    e = ls[ls.E.notna() & (ls.D >= 1)]
    if len(e) >= 5:
        alpha, beta = ed_threshold(e.E.to_numpy(), e.D.to_numpy())
        out["ED"] = {"alpha": round(alpha, 2), "beta": round(beta, 3),
                     **tss(np.r_[alpha * e.D ** beta <= e.E, np.zeros(len(ls) - len(e), bool)],
                           (alpha * ev.D ** beta <= ev.E).to_numpy())}
        if rng is not None:
            boot = np.array([ed_threshold(*e.sample(len(e), replace=True, random_state=int(s))[["E", "D"]]
                                          .to_numpy().T)
                             for s in rng.integers(0, 2**31, n_boot)])
            out["ED"]["alpha_ci"] = [round(float(v), 2) for v in np.quantile(boot[:, 0], [0.025, 0.975])]
            out["ED"]["beta_ci"] = [round(float(v), 3) for v in np.quantile(boot[:, 1], [0.025, 0.975])]
    for n in ANTECEDENT:
        for col in (f"A{n}", f"A{n}_pct"):
            c, s = best_cut(ls[col].to_numpy(float), days[col].to_numpy(float))
            out[col] = {"cut": round(c, 2), **s}
    return out


def loyo(ls: pd.DataFrame, ev: pd.DataFrame, days: pd.DataFrame) -> dict:
    """Leave-one-year-out: E–D and A10 percentile thresholds fitted without the year, alarms counted on it."""
    hits = {"ED": [[], []], "A10_pct": [[], []]}
    for y in sorted(ls.year.unique()):
        tr_l, te_l = ls[ls.year != y], ls[ls.year == y]
        e = tr_l[tr_l.E.notna() & (tr_l.D >= 1)]
        if len(e) >= 5:
            a, b = ed_threshold(e.E.to_numpy(), e.D.to_numpy())
            hits["ED"][0] += list((a * te_l.D ** b <= te_l.E).fillna(False))
            hits["ED"][1] += list(ev[ev.year == y].eval("E >= @a * D ** @b"))
        c, _ = best_cut(tr_l.A10_pct.to_numpy(float), days[days.year != y].A10_pct.to_numpy(float))
        hits["A10_pct"][0] += list(te_l.A10_pct >= c)
        hits["A10_pct"][1] += list(days[days.year == y].A10_pct >= c)
    return {k: tss(np.array(p, bool), np.array(q, bool)) for k, (p, q) in hits.items()}


def run_thresholds(study, workspace: Path, cache_root: Path, progress=None) -> dict:
    """L6: ``thresholds/`` (thresholds.json, samples, l6_report.md, plots, manifest)."""
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.landslide.inventory import build_vietnam
    say = progress or (lambda m: log.info("%s", m))
    out_dir = study.step_dir("thresholds")
    out_dir.mkdir(parents=True, exist_ok=True)
    build_vietnam(workspace)
    inv = Path(workspace) / "inventories" / "landslide" / "vietnam.csv"
    events = landslide_events(inv)
    last = pd.Timestamp.today().year
    say(f"L6: {len(events)} landslide reports ({events.region.value_counts().to_dict()}); CHIRPS {FIRST_YEAR}–{last}")
    smp = build_samples(cache_root / "rainfall", events, last, say)
    rng = np.random.default_rng(0)
    res: dict = {"study": study.name, "source": SOURCE, "params": {
        "wet_mm": WET_MM, "dry_gap_days": DRY_GAP, "regions": REGIONS, "season": SEASON, "sample_from": SAMPLE_FROM,
        "exclude": [EXCLUDE_DAYS, EXCLUDE_KM], "max_accuracy_m": MAX_ACCURACY_M, "ed_prob": ED_PROB,
        "clim_half_window": CLIM_HALF_WINDOW, "first_year": FIRST_YEAR}, "regions": {}}
    for reg in [*REGIONS, "all"]:
        def sel(t, reg=reg):
            return (t if reg == "all" else t[t.region == reg])
        ls, ev, dy = sel(smp.ls), sel(smp.ev), sel(smp.days)
        say(f"L6 {reg}: {len(ls)} landslides, {len(ev)} non-landslide events, {len(dy)} negative days")
        r = fit_region(ls, ev, dy, rng)
        r["loyo"] = loyo(ls, ev, dy)
        res["regions"][reg] = r
    smp.ls.to_csv(out_dir / "landslide_rain.csv", index=False)
    files = plot_thresholds(smp, res, out_dir)
    atomic_write_json(out_dir / "thresholds.json", res)
    (out_dir / "l6_report.md").write_text(report_md(res), encoding="utf-8")
    m = Manifest(kind="landslide_thresholds", id=f"{study.name}/thresholds", engine="geoeyes.landslide.thresholds",
                 inputs=[InputRef("inventory", str(inv))], params=res["params"],
                 metrics={k: {"ED_tss": v.get("ED", {}).get("tss"), "A10_pct_tss": v["A10_pct"]["tss"],
                              "loyo": v["loyo"]} for k, v in res["regions"].items()})
    m.add_outputs(out_dir, [*files, "thresholds.json", "l6_report.md", "landslide_rain.csv"])
    m.write(out_dir)
    return res


# ---------------------------------------------------------------- outputs
def plot_thresholds(smp: Samples, res: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    regs = list(REGIONS)
    fig, axs = plt.subplots(2, len(regs), figsize=(6 * len(regs), 9))
    for j, reg in enumerate(regs):
        ax = axs[0, j]
        ev = smp.ev[smp.ev.region == reg]
        ls = smp.ls[(smp.ls.region == reg) & smp.ls.E.notna()]
        ax.scatter(ev.D, ev.E, s=3, c="0.75", label="rainfall events without a report", rasterized=True)
        ax.scatter(ls.D, ls.E, s=18, c="k", label="with a landslide")
        r = res["regions"][reg]
        if "ED" in r:
            d = np.logspace(0, np.log10(max(2, ev.D.max() if len(ev) else 30)), 50)
            ax.plot(d, r["ED"]["alpha"] * d ** r["ED"]["beta"], "k--",
                    label=f"E = {r['ED']['alpha']:.1f}·D^{r['ED']['beta']:.2f} (5 %), TSS {r['ED']['tss']}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("D (days)")
        ax.set_ylabel("E (mm)")
        ax.set_title(f"{reg}: cumulated event rain – duration")
        ax.legend(fontsize=8)
        ax = axs[1, j]
        dy = smp.days[smp.days.region == reg].A10_pct.dropna()
        lp = smp.ls[smp.ls.region == reg].A10_pct.dropna()
        ax.hist(dy, bins=50, range=(0, 100), density=True, color="0.75", label="rainy-season days")
        ax.hist(lp, bins=25, range=(0, 100), density=True, histtype="step", color="k", lw=2, label="landslide days")
        ax.axvline(r["A10_pct"]["cut"], color="k", ls="--",
                   label=f"cut {r['A10_pct']['cut']:.0f}, TSS {r['A10_pct']['tss']}")
        ax.set_xlabel("A10 percentile of the pixel climatology")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "thresholds.png", dpi=110)
    plt.close(fig)
    return ["thresholds.png"]


def report_md(res: dict) -> str:
    lines = [f"# L6 — rainfall thresholds ({res['study']})", "", f"Source: {res['source']}.", ""]
    lines += ["| region | landslides | with a rain event | E–D α · D^β (95 % CI) | E–D TSS | A5 % | A10 % | A30 % | "
              "A10 mm | LOYO E–D TSS | LOYO A10 % TSS |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for reg, r in res["regions"].items():
        ed = r.get("ED", {})
        edt = (f"{ed['alpha']} (" + "–".join(map(str, ed.get("alpha_ci", []))) + f") · D^{ed['beta']} ("
               + "–".join(map(str, ed.get("beta_ci", []))) + ")") if ed else "—"

        def cut(k, r=r):
            return f"≥ {r[k]['cut']:g}: TSS {r[k]['tss']} (H {r[k]['hit_rate']}, F {r[k]['false_alarm']})"
        lines.append(f"| {reg} | {r['landslides']} | {r['with_rain_event']} | {edt} | {ed.get('tss', '—')} | "
                     f"{cut('A5_pct')} | {cut('A10_pct')} | {cut('A30_pct')} | {cut('A10')} | "
                     f"{r['loyo'].get('ED', {}).get('tss', '—')} | {r['loyo']['A10_pct']['tss']} |")
    lines += ["", "TSS = hit rate − false alarm rate. The false alarm rate is an upper bound: the negative days "
              "include landslides nobody reported.", ""]
    return "\n".join(lines)
