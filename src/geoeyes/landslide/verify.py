"""Independent check of the landslide inventories (docs/en/research/landslide-susceptibility.md §5 L2b).

L2a found a strong, event-specific aspect signal in the Das (2024) inventory. Is it in the slopes, or in the
mapping? Sources independent of one optical mapping:

    B1  Hansen GFC (Landsat): forest loss in the event year and the next, against years without a big storm
    B2  Sentinel-1 (Molave): σ⁰ log-ratio and coherence loss across the October 2020 storms, both tracks, with the
        layover / shadow / strong-foreshortening cells masked from the local incidence. Forested slopes are
        distributed scatterers: the pair coherences are formed over each pixel's SHP family with the phase-linking
        test and window (``processing.phase_linking.runner.pair_coherence``), the boxcar ones kept for comparison,
        and the phase-linking temporal coherence reported
    B3  size: the aspect amplitude of L2a by landslide area (revegetation, A5, hits small scars first)
    B4  ALOS PALSAR around Ketsana: availability only

The key measure of B1 and B2 is the **capture rate**: of the scars an independent source sees (connected cells,
≤ ``MAX_PATCH_HA``, on slopes ≥ ``MIN_SLOPE_DEG``), the share that touches a Das polygon, by aspect. An inventory that
misses scars on some slopes captures fewer of them there; a storm that hit some slopes harder does not change the
capture rate. The occurrence of the independent scars by aspect (event years against baseline years for B1) tells
whether the storm itself favoured an aspect.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.landslide import aspect as asp

log = logging.getLogger(__name__)

MIN_SLOPE_DEG = 15.0
MAX_PATCH_HA = 5.0
LOSS_FRACTION = 0.5                     # a 30 m cell is lost when at least half of its Hansen pixels are
SECTORS8 = 8
# Hansen lossyear codes (year − 2000): the event year and the next; a baseline of years without a big storm
HANSEN_YEARS = {"Ketsana": {"event": (9, 10), "baseline": (11, 12)},
                "Podul": {"event": (13, 14), "baseline": (11, 12)},
                "Molave": {"event": (20, 21), "baseline": (17, 18)}}
CHANGE_Z = 2.0
MIN_PIXELS = 10                         # SLC pixels in a 30 m cell for its σ⁰
MIN_SHP_PIXELS = 5                      # of them with an SHP family (phase-linking test) for the coherence
VALID_INCIDENCE = (15.0, 80.0)          # local incidence (degrees) outside which a cell is masked
S1_EVENT = ("2020-10-05", "2020-11-01")  # last date before the storms, first after


# ---------------------------------------------------------------- grid helpers
def _context(study):
    from geoeyes.landslide.labels import grid_for, study_area
    area = study_area(study)
    return area, grid_for(area.bounds, study.labels.cell_m)


def _predictors(study, event: str) -> pd.DataFrame:
    p = pd.read_parquet(study.step_dir("predictors") / f"predictors_{event}.parquet")
    p["theta"] = np.degrees(np.arctan2(p.aspect_sin, p.aspect_cos)) % 360
    return p


def polygon_cells(study, event: str, grid, area) -> tuple[np.ndarray, pd.DataFrame]:
    """Grid mask of the event's polygons grown by one cell, and its scarp positives (src_fid, cell)."""
    import geopandas as gpd
    from scipy.ndimage import binary_dilation

    from geoeyes.landslide.labels import cells_in
    polys = gpd.read_file(study.inventory, layer="polygons").to_crs(4326)
    polys = polys[(polys.event == event) & polys.geometry.intersects(area)]
    m = np.zeros(len(grid), bool)
    for g in polys.geometry:
        m[cells_in(grid, g)] = True
    m = binary_dilation(m.reshape(grid.ny, grid.nx), np.ones((3, 3), bool)).ravel()
    lab = pd.read_parquet(study.step_dir("labels") / f"labels_{event}.parquet")
    pos = lab[(lab.label == 1) & (lab.variant == "scarp")][["src_fid", "cell", "area_m2"]]
    return m, pos


def patches(mask: np.ndarray, grid, cell_m: float, max_ha: float = MAX_PATCH_HA) -> np.ndarray:
    """Label of the connected (8-neighbour) patches of ``mask`` no larger than ``max_ha`` (0 elsewhere)."""
    from scipy import ndimage
    lab, n = ndimage.label(mask.reshape(grid.ny, grid.nx), np.ones((3, 3), int))
    lab = lab.ravel()
    size = np.bincount(lab, minlength=n + 1) * cell_m * cell_m / 1e4
    keep = (size <= max_ha) & (np.arange(n + 1) > 0)
    return np.where(keep[lab], lab, 0)


def patch_table(lab: np.ndarray, pred: pd.DataFrame, das: np.ndarray, cell_m: float) -> pd.DataFrame:
    """One row per patch: its highest cell's slope, aspect and base terms, its size, whether it touches Das."""
    p = pred.set_index("cell")
    cells = np.flatnonzero(lab)
    df = pd.DataFrame({"patch": lab[cells], "cell": cells}).join(p, on="cell", how="inner")
    df["das"] = das[df.cell.to_numpy()]
    g = df.groupby("patch")
    top = df.loc[g["height_m"].idxmax()].set_index("patch")
    out = top[["cell", "slope_deg", "theta", *asp.BASE_TERMS]].copy()
    out["cells"] = g.size()
    out["area_ha"] = out["cells"] * cell_m * cell_m / 1e4
    out["captured"] = g["das"].any().astype(int)
    return out.reset_index()


# ---------------------------------------------------------------- tests on patches and cells
def capture_test(pt: pd.DataFrame) -> dict:
    """Capture rate by 8 aspect sectors and a logistic model of capture ~ slope spline + base terms + log size +
    harmonics: does the inventory capture independent scars less on some aspects?"""
    from scipy.stats import chi2
    pt = pt[pt.slope_deg >= MIN_SLOPE_DEG].reset_index(drop=True)
    out = {"patches": int(len(pt)), "captured": int(pt.captured.sum())}
    if len(pt) < 50 or pt.captured.nunique() < 2:
        return {**out, "note": "too few patches"}
    s = ((pt.theta + 180 / SECTORS8) % 360 // (360 / SECTORS8)).astype(int)
    out["rate_by_sector"] = [round(float(pt.captured[s == k].mean()), 3) if (s == k).any() else None
                             for k in range(SECTORS8)]
    out["n_by_sector"] = [int((s == k).sum()) for k in range(SECTORS8)]
    y, w = pt.captured.to_numpy(float), np.ones(len(pt))
    base = np.column_stack([asp.base_design(pt), np.log(pt.area_ha.to_numpy())])
    _, d0 = asp.logit(base, y, w)
    beta, d1 = asp.logit(np.column_stack([base, asp.harmonics(pt.theta.to_numpy())]), y, w)
    amp, az = asp.first_harmonic(beta[-4:])
    return {**out, "lr": round(d0 - d1, 1), "p": float(chi2.sf(d0 - d1, 4)), "amplitude": round(amp, 3),
            "azimuth_deg": round(az, 1)}


def occurrence_test(cells: pd.DataFrame, y: np.ndarray, n_neg: int = 20000, seed: int = 0) -> dict:
    """Aspect harmonics of the occurrence of scar cells (y = 1) against the other cells (sampled), over the base
    terms: did the storm (or the clearing) favour an aspect?"""
    from scipy.stats import chi2
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    if len(pos) < 30:
        return {"cells": int(len(pos)), "note": "too few cells"}
    neg = rng.choice(neg, min(n_neg, len(neg)), replace=False)
    t = cells.iloc[np.r_[pos, neg]].reset_index(drop=True)
    yy = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
    w = np.ones(len(yy))                    # a random sample of the other cells: no weights needed for the aspect terms
    base = asp.base_design(t)
    _, d0 = asp.logit(base, yy, w)
    beta, d1 = asp.logit(np.column_stack([base, asp.harmonics(t.theta.to_numpy())]), yy, w)
    amp, az = asp.first_harmonic(beta[-4:])
    fr = asp.sector_ratio(t.theta.to_numpy(), yy.astype(int), w, n=SECTORS8)
    return {"cells": int(len(pos)), "lr": round(d0 - d1, 1), "p": float(chi2.sf(d0 - d1, 4)),
            "amplitude": round(amp, 3), "azimuth_deg": round(az, 1), "fr_by_sector": np.round(fr, 3).tolist()}


# ---------------------------------------------------------------- B1 Hansen
def hansen_loss(grid, years: tuple[int, ...]) -> np.ndarray:
    """Fraction of the Hansen pixels of each cell lost in ``years`` (lossyear codes)."""
    import rasterio
    from rasterio.windows import from_bounds

    from geoeyes.landslide.predictors import HANSEN, _hansen_tiles
    from geoeyes.ml.layers import _ENV
    n = len(grid)
    count, lost = np.zeros(n), np.zeros(n)
    w, s, e, nn = grid.bounds
    for tile in _hansen_tiles(grid.bounds):
        with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + HANSEN.format(layer="lossyear", tile=tile)) as src:
            win = from_bounds(w, s, e, nn, src.transform).round_offsets().round_lengths()
            ly = src.read(1, window=win)
            tr = src.window_transform(win)
        rows, cols = np.indices(ly.shape)
        idx = grid.cell_of((tr.c + (cols + 0.5) * tr.a).ravel(), (tr.f + (rows + 0.5) * tr.e).ravel())
        ok = idx >= 0
        count += np.bincount(idx[ok], minlength=n)
        lost += np.bincount(idx[ok], weights=np.isin(ly.ravel()[ok], years).astype(float), minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return lost / count


def b1_hansen(study, event: str, grid, area) -> dict:
    yrs = HANSEN_YEARS[event]
    pred = _predictors(study, event)
    pred = pred[pred[f"in_{study.footprint_main}_{event}"]].reset_index(drop=True)
    das, pos = polygon_cells(study, event, grid, area)
    out = {"years": {k: [2000 + y for y in v] for k, v in yrs.items()}}
    # Das polygons seen by Landsat: at least one event-year loss pixel in the polygon's scarp cell or its neighbours
    ev = hansen_loss(grid, yrs["event"])
    for kind in ("event", "baseline"):
        frac = ev if kind == "event" else hansen_loss(grid, yrs["baseline"])
        lost = np.zeros(len(grid), bool)
        lost[pred.cell.to_numpy()] = (frac[pred.cell.to_numpy()] >= LOSS_FRACTION) & \
            (pred.slope_deg.to_numpy() >= MIN_SLOPE_DEG)
        lab = patches(lost, grid, grid.cell_m)
        pt = patch_table(lab, pred, das, grid.cell_m)
        y = (lab[pred.cell.to_numpy()] > 0).astype(int)
        steep = (pred.slope_deg >= MIN_SLOPE_DEG).to_numpy()
        out[kind] = {"capture": capture_test(pt),
                     "occurrence": occurrence_test(pred[steep & ~das[pred.cell.to_numpy()]].reset_index(drop=True),
                                                   y[steep & ~das[pred.cell.to_numpy()]])}
    p = pred.set_index("cell")
    seen = pd.Series(ev[pos.cell.to_numpy()] > 0, index=pos.index)
    th = p.reindex(pos.cell.to_numpy())["theta"].to_numpy()
    s = ((th + 180 / SECTORS8) % 360 // (360 / SECTORS8))
    out["das_seen_by_landsat"] = {"share": round(float(seen.mean()), 3),
                                  "by_sector": [round(float(seen[s == k].mean()), 3) if (s == k).any() else None
                                                for k in range(SECTORS8)]}
    return out


# ---------------------------------------------------------------- B2 Sentinel-1
def local_incidence(slope_deg, theta_deg, inc_deg, heading_deg) -> np.ndarray:
    """Local incidence (degrees) of a right-looking SAR: the ellipsoid incidence minus the slope facing the
    satellite (negative: layover; ≥ 90: shadow)."""
    sat_az = (heading_deg - 90.0) % 360                  # direction from the ground to the satellite
    toward = np.degrees(np.arctan(np.tan(np.radians(slope_deg)) * np.cos(np.radians(theta_deg - sat_az))))
    return inc_deg - toward


def s1_change(store: Path, grid, cells: np.ndarray, event=S1_EVENT, block: int = 512) -> pd.DataFrame:
    """Per grid cell (``cells``): σ⁰ log-ratio after / before the storms, coherence of the pair across the storms
    and of a pair before them with the same span, mean incidence, number of SLC pixels."""
    from geoeyes.io.stack import StackStore
    st = StackStore(store)
    ds = st.open()
    dates = pd.to_datetime(ds["date"].values)
    before = [i for i, d in enumerate(dates) if d <= pd.Timestamp(event[0])]
    after = [i for i, d in enumerate(dates) if d >= pd.Timestamp(event[1])]
    if len(before) < 2 or not after:
        raise ValueError(f"{store}: needs two dates before {event[0]} and one after {event[1]}")
    a0, a1 = before[-1], after[0]
    span = dates[a1] - dates[a0]
    p0 = min(before[:-1], key=lambda i: abs((dates[a0] - dates[i]) - span))
    pre_pair, across = (p0, a0), (a0, a1)
    # coherence of the two pairs over each pixel's SHP family: kept by phase linking ([phase_linking] store_pairs),
    # else formed again with the stack's phase-linking test and window
    from geoeyes.processing.phase_linking.runner import (
        DONE_ATTR,
        PAIRS_VAR,
        PhaseLinkingParams,
        pair_coherence,
        stored_pairs,
    )
    done = st.attrs.get(DONE_ATTR)
    names = [f"{dates[i].date()}/{dates[j].date()}" for i, j in (pre_pair, across)]
    kept = stored_pairs(st)
    if all(n in kept for n in names):
        shp = st.read(PAIRS_VAR, pl_pair=[kept[n] for n in names])
        source = "phase linking (stored)"
    else:
        plp = PhaseLinkingParams(**{k: tuple(tuple(x) if isinstance(x, list) else x for x in v)
                                    if isinstance(v, list) else v for k, v in done.items()
                                    if k in PhaseLinkingParams.__dataclass_fields__ and k != "store_pairs"}) \
            if isinstance(done, dict) else PhaseLinkingParams()
        shp = pair_coherence(st, [pre_pair, across], plp)
        source = "SHP formed again"
    has_tcoh = "pl_temporal_coherence" in ds.data_vars
    n = len(grid)
    sums = {k: np.zeros(n) for k in ("pre_pow", "post_pow", "n", "inc", "c0r", "c0i", "c0a", "c0b",
                                     "c1r", "c1i", "c1a", "c1b", "s0", "s1", "ns", "tc", "ntc")}
    ny = ds.sizes["y"]
    for r0 in range(0, ny, block):
        sl = slice(r0, min(r0 + block, ny))
        lat = ds["geometry_lat"].isel(y=sl).values.ravel()
        lon = ds["geometry_lon"].isel(y=sl).values.ravel()
        idx = grid.cell_of(lon, lat)
        ok = idx >= 0
        ii = idx[ok]

        def add(k, v, ii=ii, ok=ok):
            sums[k] += np.bincount(ii, weights=v[ok], minlength=n)
        slc = {i: ds["slc"].isel(date=i, y=sl).values.ravel() for i in set(before + after)}
        add("n", np.ones(ok.size))
        add("inc", ds["geometry_incidence"].isel(y=sl).values.ravel().astype(float))
        add("pre_pow", np.mean([np.abs(slc[i]) ** 2 for i in before], axis=0))
        add("post_pow", np.mean([np.abs(slc[i]) ** 2 for i in after], axis=0))
        for tag, (i, j) in (("c0", pre_pair), ("c1", across)):
            x = slc[i] * np.conj(slc[j])
            add(f"{tag}r", x.real)
            add(f"{tag}i", x.imag)
            add(f"{tag}a", np.abs(slc[i]) ** 2)
            add(f"{tag}b", np.abs(slc[j]) ** 2)
        s0, s1 = shp[0, sl].ravel(), shp[1, sl].ravel()
        good = np.isfinite(s0) & np.isfinite(s1)
        add("s0", np.where(good, s0, 0.0))
        add("s1", np.where(good, s1, 0.0))
        add("ns", good.astype(float))
        if has_tcoh:
            tc = ds["pl_temporal_coherence"].isel(y=sl).values.ravel().astype(float)
            add("tc", np.nan_to_num(tc))
            add("ntc", np.isfinite(tc).astype(float))
    c = cells
    with np.errstate(invalid="ignore", divide="ignore"):
        out = pd.DataFrame({
            "cell": c, "n_px": sums["n"][c], "inc": sums["inc"][c] / sums["n"][c],
            "log_ratio_db": 10 * np.log10(sums["post_pow"][c] / sums["pre_pow"][c]),
            "box_coh_before": np.hypot(sums["c0r"][c], sums["c0i"][c]) / np.sqrt(sums["c0a"][c] * sums["c0b"][c]),
            "box_coh_across": np.hypot(sums["c1r"][c], sums["c1i"][c]) / np.sqrt(sums["c1a"][c] * sums["c1b"][c]),
            "n_shp_px": sums["ns"][c],
            "coh_before": sums["s0"][c] / sums["ns"][c], "coh_across": sums["s1"][c] / sums["ns"][c],
            "pl_tcoh": sums["tc"][c] / sums["ntc"][c] if has_tcoh else np.nan})
    out.attrs.update({"before": [str(dates[i].date()) for i in before], "after": [str(dates[i].date()) for i in after],
                      "pair_before": [str(dates[i].date()) for i in pre_pair],
                      "pair_across": [str(dates[i].date()) for i in across],
                      "heading_deg": float(st.attrs.get("heading_deg", 0.0)), "coherence": f"shp, {source}",
                      "phase_linking": done if isinstance(done, dict) else None})
    return out


def _robust_z(x: np.ndarray) -> np.ndarray:
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med)) * 1.4826
    return (x - med) / (mad if mad > 0 else np.nan)


def b2_sentinel1(study, event: str, grid, area, stores: dict[str, Path]) -> dict:
    pred = _predictors(study, event)
    pred = pred[pred[f"in_{study.footprint_main}_{event}"]].reset_index(drop=True)
    das, pos = polygon_cells(study, event, grid, area)
    cells = pred.cell.to_numpy()
    changed = np.zeros(len(pred), bool)
    valid_any = np.zeros(len(pred), bool)
    out: dict = {"tracks": {}}
    for name, store in stores.items():
        ch = s1_change(store, grid, cells)
        li = local_incidence(pred.slope_deg.to_numpy(), pred.theta.to_numpy(), ch.inc.to_numpy(),
                             ch.attrs["heading_deg"])
        valid = (ch.n_px.to_numpy() >= MIN_PIXELS) & (ch.n_shp_px.to_numpy() >= MIN_SHP_PIXELS) & \
            (li >= VALID_INCIDENCE[0]) & (li <= VALID_INCIDENCE[1])
        dcoh = (ch.coh_before - ch.coh_across).to_numpy()
        dbox = (ch.box_coh_before - ch.box_coh_across).to_numpy()
        z_c = np.where(valid, _robust_z(np.where(valid, dcoh, np.nan)), np.nan)
        z_r = np.where(valid, np.abs(_robust_z(np.where(valid, ch.log_ratio_db.to_numpy(), np.nan))), np.nan)
        chg = valid & ((z_c > CHANGE_Z) | (z_r > CHANGE_Z))
        changed |= chg
        valid_any |= valid
        inside = das[cells]
        out["tracks"][name] = {**ch.attrs, "valid_share": round(float(valid.mean()), 3),
                               "changed_share": round(float(chg[valid].mean()), 4),
                               "changed_share_in_das": round(float(chg[valid & inside].mean()), 4),
                               "changed_share_outside": round(float(chg[valid & ~inside].mean()), 4),
                               "median_dcoh_in_das": round(float(np.nanmedian(dcoh[valid & inside])), 3),
                               "median_dcoh_outside": round(float(np.nanmedian(dcoh[valid & ~inside])), 3),
                               "median_box_dcoh_in_das": round(float(np.nanmedian(dbox[valid & inside])), 3),
                               "median_box_dcoh_outside": round(float(np.nanmedian(dbox[valid & ~inside])), 3),
                               "median_coh_before": round(float(np.nanmedian(ch.coh_before[valid])), 3),
                               "median_box_coh_before": round(float(np.nanmedian(ch.box_coh_before[valid])), 3),
                               "median_pl_tcoh_in_das": round(float(np.nanmedian(ch.pl_tcoh[valid & inside])), 3),
                               "median_pl_tcoh_outside": round(float(np.nanmedian(ch.pl_tcoh[valid & ~inside])), 3),
                               "median_lr_in_das": round(float(np.nanmedian(ch.log_ratio_db[valid & inside])), 2),
                               "median_lr_outside": round(float(np.nanmedian(ch.log_ratio_db[valid & ~inside])), 2)}
    mask = np.zeros(len(grid), bool)
    mask[cells[changed & (pred.slope_deg >= MIN_SLOPE_DEG).to_numpy()]] = True
    lab = patches(mask, grid, grid.cell_m)
    pt = patch_table(lab, pred, das, grid.cell_m)
    steep = (pred.slope_deg >= MIN_SLOPE_DEG).to_numpy() & valid_any
    y = (lab[cells] > 0).astype(int)
    out["valid_share_any_track"] = round(float(valid_any.mean()), 3)
    out["capture"] = capture_test(pt)
    out["occurrence"] = occurrence_test(pred[steep & ~das[cells]].reset_index(drop=True), y[steep & ~das[cells]])
    # Das polygons seen by SAR: the scarp cell or a neighbour changed
    hit = pd.Series(changed, index=cells)
    seen = hit.reindex(pos.cell.to_numpy()).fillna(False).to_numpy()
    th = pred.set_index("cell").reindex(pos.cell.to_numpy())["theta"].to_numpy()
    s = ((th + 180 / SECTORS8) % 360 // (360 / SECTORS8))
    out["das_seen_by_sar"] = {"share": round(float(seen.mean()), 3),
                              "by_sector": [round(float(seen[s == k].mean()), 3) if (s == k).any() else None
                                            for k in range(SECTORS8)]}
    return out


# ---------------------------------------------------------------- B3 size, B4 ALOS
SIZE_CLASSES = ((0, 900), (900, 3000), (3000, 1e9))


def b3_size(study, event: str, grid_nx: int) -> dict:
    t = asp.table(study, event, grid_nx)
    out = {}
    for lo, hi in SIZE_CLASSES:
        x = t[(t.label == 0) | ((t.area_m2 >= lo) & (t.area_m2 < hi))].reset_index(drop=True)
        if (x.label == 1).sum() < 50:
            continue
        c = asp.conditional(x, n_boot=50)["location free"]
        out[f"{lo:g}-{hi:g} m²"] = {"positives": int((x.label == 1).sum()), "amplitude": c["amplitude"],
                                    "amplitude_ci": c["amplitude_ci"], "azimuth_deg": c["azimuth_deg"],
                                    "p": c["p"]}
    return out


def b4_alos(lon: float, lat: float, start: str = "2009-07-01", end: str = "2009-12-31") -> dict:
    q = {"platform": "ALOS", "intersectsWith": f"POINT({lon:.4f} {lat:.4f})", "start": start, "end": end,
         "output": "jsonlite", "maxResults": 500}
    url = "https://api.daac.asf.alaska.edu/services/search/param?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=300) as r:
        res = json.load(r)["results"]
    rows = sorted({(x["startTime"][:10], x.get("beamModeType", ""), x.get("processingLevel", ""), x.get("pathNumber"))
                   for x in res})
    return {"window": [start, end], "products": len(res),
            "acquisitions": [{"date": d, "beam": b, "level": lv, "path": p} for d, b, lv, p in rows]}


# ---------------------------------------------------------------- the study step
def run_verify(study, stores: dict[str, Path], progress=None) -> dict:
    """L2b of a study: ``verify/verify.json``, ``verify.md``, manifest. ``stores``: the Sentinel-1 stacks across
    the October 2020 storms, by track name (empty: B2 left out)."""
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    say = progress or (lambda m: log.info("%s", m))
    area, grid = _context(study)
    out_dir = study.step_dir("verify")
    out_dir.mkdir(parents=True, exist_ok=True)
    res: dict = {"study": study.name, "citation": study.citation, "min_slope_deg": MIN_SLOPE_DEG,
                 "max_patch_ha": MAX_PATCH_HA, "events": {}}
    for name, _ in study.events:
        r: dict = {}
        say(f"verify {name}: B1 Hansen")
        r["b1_hansen"] = b1_hansen(study, name, grid, area)
        say(f"verify {name}: B3 size")
        r["b3_size"] = b3_size(study, name, grid.nx)
        if name == "Molave" and stores:
            say(f"verify {name}: B2 Sentinel-1")
            r["b2_sentinel1"] = b2_sentinel1(study, name, grid, area, stores)
        res["events"][name] = r
    say("verify: B4 ALOS")
    try:
        c = area.centroid
        res["b4_alos"] = b4_alos(c.x, c.y)
    except Exception as exc:
        res["b4_alos"] = {"error": str(exc)}
    atomic_write_json(out_dir / "verify.json", res)
    (out_dir / "verify.md").write_text(report_md(res), encoding="utf-8")
    m = Manifest(kind="landslide_verify", id=f"{study.name}/verify", engine="geoeyes.landslide.verify",
                 inputs=[InputRef("labels", str(study.step_dir("labels"))),
                         InputRef("predictors", str(study.step_dir("predictors"))),
                         InputRef("hansen", "Hansen GFC-2024-v1.12 lossyear"),
                         *[InputRef("stack", str(p)) for p in stores.values()]],
                 params={"min_slope_deg": MIN_SLOPE_DEG, "max_patch_ha": MAX_PATCH_HA, "loss_fraction": LOSS_FRACTION,
                         "hansen_years": HANSEN_YEARS, "change_z": CHANGE_Z, "valid_incidence": VALID_INCIDENCE})
    m.add_outputs(out_dir, ["verify.json", "verify.md"])
    m.write(out_dir)
    return res


def _sectors_line(v) -> str:
    names = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return ", ".join(f"{n} {x}" for n, x in zip(names, v, strict=True))


def report_md(res: dict) -> str:
    L = [f"# L2b independent check — {res['study']}", "", f"Inventory: {res['citation']}", "",
         f"Scars: connected cells ≤ {res['max_patch_ha']} ha on slopes ≥ {res['min_slope_deg']}°. Capture = the "
         "share of the independent scars that touch a Das polygon. Sectors: N, NE, E, SE, S, SW, W, NW.", ""]

    def cap(c, title):
        if "note" in c:
            return [f"- {title}: {c['patches']} patches — {c['note']}"]
        return [f"- {title}: {c['captured']} / {c['patches']} captured; aspect LR {c['lr']} (p {c['p']:.2g}), "
                f"highest capture towards {c['azimuth_deg']}° (amplitude {c['amplitude']})",
                f"  - capture by sector: {_sectors_line(c['rate_by_sector'])}",
                f"  - patches by sector: {_sectors_line(c['n_by_sector'])}"]

    def occ(o, title):
        if "note" in o:
            return [f"- {title}: {o['cells']} cells — {o['note']}"]
        return [f"- {title}: {o['cells']} cells; aspect LR {o['lr']} (p {o['p']:.2g}), highest odds towards "
                f"{o['azimuth_deg']}° (amplitude {o['amplitude']})",
                f"  - frequency ratio by sector: {_sectors_line(o['fr_by_sector'])}"]
    for ev, r in res["events"].items():
        L += [f"## {ev}", "", "### B1 Hansen GFC (Landsat)", ""]
        b1 = r["b1_hansen"]
        L += [f"Event years {b1['years']['event']}, baseline years {b1['years']['baseline']}.", ""]
        for kind in ("event", "baseline"):
            L += cap(b1[kind]["capture"], f"{kind} scars captured by Das")
            L += occ(b1[kind]["occurrence"], f"{kind} scars outside Das, occurrence")
        d = b1["das_seen_by_landsat"]
        L += [f"- Das polygons with event-year loss at the scarp: {d['share']:.1%}; by sector: "
              f"{_sectors_line(d['by_sector'])}", ""]
        if "b2_sentinel1" in r:
            b2 = r["b2_sentinel1"]
            L += ["### B2 Sentinel-1", ""]
            for t, v in b2["tracks"].items():
                L += [f"- {t}: before {v['before']}, after {v['after']}; pairs {v['pair_before']} / "
                      f"{v['pair_across']}; valid {v['valid_share']:.0%} of the cells; "
                      f"changed {v['changed_share']:.1%} "
                      f"(in Das {v['changed_share_in_das']:.1%}, outside {v['changed_share_outside']:.1%}); median "
                      f"SHP coherence loss in / out {v['median_dcoh_in_das']} / {v['median_dcoh_outside']} "
                      f"(boxcar {v['median_box_dcoh_in_das']} / {v['median_box_dcoh_outside']}); median coherence "
                      f"before, SHP {v['median_coh_before']} vs boxcar {v['median_box_coh_before']}; PL temporal "
                      f"coherence in / out {v['median_pl_tcoh_in_das']} / {v['median_pl_tcoh_outside']}; median "
                      f"log-ratio in / out {v['median_lr_in_das']} / {v['median_lr_outside']} dB"]
            L += [f"- valid in at least one track: {b2['valid_share_any_track']:.0%}"]
            L += cap(b2["capture"], "SAR change patches captured by Das")
            L += occ(b2["occurrence"], "SAR change outside Das, occurrence")
            d = b2["das_seen_by_sar"]
            L += [f"- Das polygons whose scarp cell changed: {d['share']:.1%}; by sector: "
                  f"{_sectors_line(d['by_sector'])}", ""]
        L += ["### B3 aspect amplitude by landslide size", "", "| Size | Positives | Amplitude [95 %] | Azimuth | p |",
              "|---|---|---|---|---|"]
        L += [f"| {k} | {v['positives']} | {v['amplitude']} [{v['amplitude_ci'][0]}–{v['amplitude_ci'][1]}] | "
              f"{v['azimuth_deg']}° | {v['p']:.2g} |" for k, v in r["b3_size"].items()]
        L.append("")
    a = res.get("b4_alos", {})
    L += ["## B4 ALOS PALSAR around Ketsana", ""]
    if "error" in a:
        L.append(f"- not checked: {a['error']}")
    else:
        L.append(f"- {a['products']} products {a['window'][0]} → {a['window'][1]}")
        L += [f"  - {x['date']} {x['beam']} {x['level']} path {x['path']}" for x in a["acquisitions"]]
    return "\n".join(L) + "\n"
