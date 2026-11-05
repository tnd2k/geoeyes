"""When did the vegetation go? Dating the Sentinel-2 objects and the inventory polygons (docs/en/research/
landslide-susceptibility.md L3b.7, step 1).

A pair of dry-season composites cannot tell a landslide from a clearing; the date can. Swidden and plantation
clearing happen in the dry season, landslides in the rain events of September–December. For every object:

* the NDVI of each clear Sentinel-2 scene (SCL 4 / 5; at least ``MIN_CLEAR`` of the object's pixels clear), over the
  whole span of the two composite windows, rainy season included;
* the loss bracket: the last date still vegetated (NDVI ≥ its own before-level − ``DROP`` / 3) before the first date
  bare (NDVI ≤ before-level − ``DROP``) that stays bare at the next clear date;
* the class: ``rain_season`` when the bracket lies within ``RAIN_MONTHS`` and is ≤ ``MAX_BRACKET_DAYS`` long,
  ``dry_season`` when it lies within the other months, ``undated`` otherwise (too wide, or never clearly lost).

Output: ``scars/dating_<event>.parquet`` (one row per object: bracket, class, number of clear dates) and
``scars/dating.json`` (class shares, and the cross-table with the inventory for the calibration event).
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

MIN_CLEAR = 0.6          # share of the object's pixels clear in a scene
DROP = 0.25              # NDVI drop that counts as bare
MAX_BRACKET_DAYS = 120
RAIN_MONTHS = (9, 10, 11, 12)
MAX_CLOUD = 90.0         # scenes are judged per object, not per tile


def label_raster(polys_lonlat, grid) -> np.ndarray:
    """Object number (row + 1) per pixel of the UTM grid."""
    from rasterio.features import rasterize
    g = polys_lonlat.to_crs(grid.epsg)
    return rasterize(((geom, i + 1) for i, geom in enumerate(g.geometry.values)), out_shape=(grid.ny, grid.nx),
                     transform=grid.transform, fill=0, dtype="int32")


def series(items: list[dict], grid, lab: np.ndarray, n: int, workers: int = 6, progress=None) -> pd.DataFrame:
    """Per scene and object: share of clear pixels and mean NDVI over them (long table)."""
    from concurrent.futures import ThreadPoolExecutor

    from geoeyes.landslide.scars import _safe_read
    say = progress or (lambda m: None)
    size = np.bincount(lab.ravel(), minlength=n + 1).astype(float)
    rows = []

    def one(it):
        r = _safe_read(it, grid)
        if r is None:
            return None
        nd, _, rs, cs = r
        lb = lab[rs, cs]
        ok = (nd != -32768) & (lb > 0)
        cnt = np.bincount(lb[ok], minlength=n + 1)
        s = np.bincount(lb[ok], weights=nd[ok] / 1e4, minlength=n + 1)
        return it["properties"]["datetime"][:10], cnt, s

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for res in ex.map(one, items):
            done += 1
            if done % 25 == 0 or done == len(items):
                say(f"  dating: {done}/{len(items)} scenes read")
            if res is None:
                continue
            d, cnt, s = res
            frac = np.divide(cnt, size, out=np.zeros_like(size), where=size > 0)
            keep = np.flatnonzero(frac[1:] >= MIN_CLEAR) + 1
            for k in keep:
                rows.append((int(k), d, float(s[k] / cnt[k])))
    t = pd.DataFrame(rows, columns=["obj", "date", "ndvi"])
    # two scenes of one day (two tiles, two processings): their mean
    return t.groupby(["obj", "date"], as_index=False).ndvi.mean().sort_values(["obj", "date"])


def bracket(dates: list[date], ndvi: np.ndarray, before_end: date) -> tuple[date | None, date | None, float]:
    """(last vegetated, first lasting bare, before-level) of one object's series."""
    pre = ndvi[[d <= before_end for d in dates]]
    level = float(np.median(pre)) if len(pre) else float(np.max(ndvi))
    bare = ndvi <= level - DROP
    veg = ndvi >= level - DROP / 3
    for k in range(len(dates)):
        if bare[k] and (k + 1 == len(dates) or bare[k + 1]):
            last_veg = next((dates[j] for j in range(k - 1, -1, -1) if veg[j]), None)
            return last_veg, dates[k], level
    return None, None, level


def classify(lo: date | None, hi: date | None) -> str:
    if lo is None or hi is None or (hi - lo).days > MAX_BRACKET_DAYS:
        return "undated"
    months = {(lo.month + k - 1) % 12 + 1 for k in range((hi.year - lo.year) * 12 + hi.month - lo.month + 1)}
    if months <= set(RAIN_MONTHS):
        return "rain_season"
    if not months & set(RAIN_MONTHS):
        return "dry_season"
    return "undated"


def date_objects(polys, grid, before: tuple[str, str], after: tuple[str, str], bbox, progress=None) -> pd.DataFrame:
    """The bracket and class of every polygon (lon / lat; row order) over ``before[0]`` → ``after[1]``."""
    from geoeyes.landslide.scars import search
    say = progress or (lambda m: None)
    lab = label_raster(polys, grid)
    items = search(bbox, before[0], after[1], max_cloud=MAX_CLOUD)
    latest: dict = {}
    for it in items:                             # one processing per tile and day (as scars.pick)
        k = (it["properties"].get("s2:mgrs_tile"), it["properties"]["datetime"][:10])
        if k not in latest or it["properties"].get("created", "") > latest[k]["properties"].get("created", ""):
            latest[k] = it
    say(f"dating: {len(polys)} objects, {len(latest)} scenes {before[0]} → {after[1]}")
    t = series(list(latest.values()), grid, lab, len(polys), progress=say)
    b_end = date.fromisoformat(before[1])
    out = []
    for k in range(1, len(polys) + 1):
        g = t[t.obj == k]
        ds = [date.fromisoformat(x) for x in g.date]
        lo, hi, level = bracket(ds, g.ndvi.to_numpy(), b_end) if len(g) else (None, None, np.nan)
        out.append({"row": k - 1, "clear_dates": int(len(g)), "ndvi_before": round(level, 3),
                    "last_vegetated": lo, "first_bare": hi, "timing": classify(lo, hi)})
    return pd.DataFrame(out)


# the growing season after each event: a landslide scar stays bare for a year or more, a swidden field or a harvest
# greens up within the next season
PERSIST_WINDOWS = {"Molave": ("2021-05-01", "2021-09-30"), "S2_2025": ("2026-05-01", "2026-09-30")}
PERSIST_FRACTION = 0.5     # still bare: NDVI below the before-level by at least this share of DROP


def later_ndvi(polys, grid, window: tuple[str, str], bbox, progress=None) -> pd.DataFrame:
    """Median NDVI of each polygon over the clear scenes of ``window`` (row order) and their number."""
    from geoeyes.landslide.scars import search
    lab = label_raster(polys, grid)
    items = search(bbox, window[0], window[1], max_cloud=MAX_CLOUD)
    latest: dict = {}
    for it in items:
        k = (it["properties"].get("s2:mgrs_tile"), it["properties"]["datetime"][:10])
        if k not in latest or it["properties"].get("created", "") > latest[k]["properties"].get("created", ""):
            latest[k] = it
    t = series(list(latest.values()), grid, lab, len(polys), progress=progress)
    g = t.groupby("obj").ndvi.agg(["median", "size"])
    out = pd.DataFrame({"row": np.arange(len(polys))})
    out["ndvi_later"] = g["median"].reindex(np.arange(1, len(polys) + 1)).to_numpy()
    out["later_dates"] = g["size"].reindex(np.arange(1, len(polys) + 1)).fillna(0).astype(int).to_numpy()
    return out


def persistent(ndvi_before, ndvi_later) -> np.ndarray:
    """True: still bare in the next growing season; False: green again; NA: no clear view."""
    b, a = np.asarray(ndvi_before, float), np.asarray(ndvi_later, float)
    out = pd.array(a <= b - PERSIST_FRACTION * DROP, dtype="boolean")
    out[np.isnan(a) | np.isnan(b)] = pd.NA
    return out


def run_persistence(study, progress=None) -> dict:
    """L3b.7 step 1b: the NDVI of every dated object in the growing season after the event; ``persistent`` and
    ``ndvi_later`` are added to ``scars/dating_<event>.parquet`` (and the Das file of the calibration event)."""
    import geopandas as gpd

    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide.labels import study_area
    from geoeyes.landslide.scars import CALIBRATION, UtmGrid
    say = progress or (lambda m: log.info("%s", m))
    area = study_area(study)
    grid = UtmGrid.around(area.bounds)
    out_dir = study.step_dir("scars")
    res: dict = {"windows": PERSIST_WINDOWS, "fraction": PERSIST_FRACTION, "events": {}}
    jobs = [(ev, out_dir / f"scars_{ev}.gpkg", out_dir / f"dating_{ev}.parquet") for ev in PERSIST_WINDOWS]
    das = gpd.read_file(study.inventory, layer="polygons")
    for ev, gpkg, dfile in jobs:
        if not (gpkg.exists() and dfile.exists()):
            continue
        sets = [(ev, gpd.read_file(gpkg, layer="polygons"), dfile)]
        if ev == CALIBRATION and (out_dir / f"dating_das_{ev}.parquet").exists():
            d_ev = das[(das.event == ev) & das.geometry.intersects(area)].reset_index(drop=True)
            sets.append((f"Das {ev}", d_ev, out_dir / f"dating_das_{ev}.parquet"))
        for name, polys, f in sets:
            say(f"persistence: {name}, {len(polys)} objects, {PERSIST_WINDOWS[ev]}")
            later = later_ndvi(polys, grid, PERSIST_WINDOWS[ev], area.bounds, say)
            d = pd.read_parquet(f).drop(columns=["ndvi_later", "later_dates", "persistent"], errors="ignore")
            d = d.merge(later, on="row", how="left")
            d["persistent"] = persistent(d.ndvi_before, d.ndvi_later)
            d.to_parquet(f, index=False)
            r = {"objects": int(len(d)), "persistent": d.persistent.value_counts(normalize=True, dropna=False)
                 .round(4).rename(str).to_dict(),
                 "by_timing": d.groupby("timing").persistent.mean().round(4).to_dict()}
            if "in_inventory" in d:
                r["by_inventory"] = d.groupby("in_inventory").persistent.mean().round(4).rename(str).to_dict()
            res["events"][name] = r
            say(f"{name}: {r}")
    atomic_write_json(out_dir / "persistence.json", res)
    return res


def run_dating(study, progress=None) -> dict:
    """Step 1 of L3b.7 for every event of ``scars.WINDOWS``: the Sentinel-2 objects, and for the calibration event
    the inventory polygons too."""
    import geopandas as gpd

    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.landslide.labels import study_area
    from geoeyes.landslide.scars import CALIBRATION, WINDOWS, UtmGrid
    say = progress or (lambda m: log.info("%s", m))
    area = study_area(study)
    grid = UtmGrid.around(area.bounds)
    out_dir = study.step_dir("scars")
    res: dict = {"params": {"min_clear": MIN_CLEAR, "drop": DROP, "max_bracket_days": MAX_BRACKET_DAYS,
                            "rain_months": RAIN_MONTHS}, "events": {}}
    for ev, (before, after) in WINDOWS.items():
        f = out_dir / f"scars_{ev}.gpkg"
        if not f.exists():
            continue
        polys = gpd.read_file(f, layer="polygons")
        d = date_objects(polys, grid, before, after, area.bounds, say)
        d["src_fid"] = polys.src_fid.to_numpy()
        for c in ("in_inventory", "strict"):
            if c in polys:
                d[c] = polys[c].to_numpy()
        d.to_parquet(out_dir / f"dating_{ev}.parquet", index=False)
        r = {"objects": int(len(d)), "timing": d.timing.value_counts(normalize=True).round(4).to_dict()}
        if "in_inventory" in d:
            r["by_inventory"] = (d.groupby("in_inventory").timing.value_counts(normalize=True).round(4)
                                 .unstack(fill_value=0).to_dict(orient="index"))
        res["events"][ev] = r
        say(f"{ev}: {r['timing']}")
        if ev == CALIBRATION:
            das = gpd.read_file(study.inventory, layer="polygons")
            das = das[(das.event == ev) & das.geometry.intersects(area)].reset_index(drop=True)
            dd = date_objects(das, grid, before, after, area.bounds, say)
            dd["src_fid"] = das.src_fid.to_numpy()
            dd.to_parquet(out_dir / f"dating_das_{ev}.parquet", index=False)
            res["events"][f"Das {ev}"] = {"objects": int(len(dd)),
                                          "timing": dd.timing.value_counts(normalize=True).round(4).to_dict()}
            say(f"Das {ev}: {res['events'][f'Das {ev}']['timing']}")
    atomic_write_json(out_dir / "dating.json", res)
    return res
