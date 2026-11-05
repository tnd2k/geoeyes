"""Predictors of a landslide study on its grid (docs/en/research/landslide-susceptibility.md §5 L2).

Static layers (the same for every event):

    terrain       ``landslide.terrain`` on Copernicus GLO-30 (2011–2015: before Molave, after Ketsana), cell and
                  hillslope scale (L3b.2)
    lithology     GLiM at full resolution (Hartmann & Moosdorf 2012, ~1:3.75 M), one-hot ``lith_<class>``; classes
                  under ``rare_fraction`` of the cells merged into ``lith_other``
    soil          SoilGrids 2.0 clay and sand at 0–5 cm (g/kg, 250 m)
    regolith      Pelletier et al. (2016) hill-slope soil and regolith thickness (m, 1 km; Earthdata token)
    access        distance to an OSM road (today: a known bias, L3 runs with and without it)

Per event (state before the event): Hansen et al. (2013) Global Forest Change v1.12: ``tree_cover_2000`` (%),
``loss_before`` (fraction of the cell lost from 2001 to the year before the event), ``loss_before_300m`` (the same
over a 300 m square), ``tree_cover_event`` = tree cover × (1 − loss before). WorldCover is after every event: not
used. Event rainfall is L4.

Rows: the cells of the study area inside any footprint used by the labels. Screening on the label cells (scarp
positives and the first draw of the main footprint's negatives): Spearman |rho| > ``max_rho`` → the later layer of
PRIORITY is dropped; then, for the logistic model only, the largest VIF above ``max_vif`` is dropped until none is.
"""
from __future__ import annotations

import itertools
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from geoeyes.ml.layers import _ENV, M_PER_DEG_LAT, Grid

log = logging.getLogger(__name__)

GLIM_ZIP = "geology/glim/LiMW_GIS_2015.gdb.zip"           # relative to the workspace cache
GLIM_URL = "https://www.dropbox.com/s/9vuowtebp9f1iud/LiMW_GIS%202015.gdb.zip?dl=1"
GLIM_CLASSES = {"su": "unconsolidated sediments", "ss": "siliciclastic sedimentary", "sm": "mixed sedimentary",
                "sc": "carbonate sedimentary", "py": "pyroclastics", "ev": "evaporites", "mt": "metamorphics",
                "pa": "acid plutonic", "pi": "intermediate plutonic", "pb": "basic plutonic", "va": "acid volcanic",
                "vi": "intermediate volcanic", "vb": "basic volcanic", "ig": "ice and glaciers", "wb": "water bodies",
                "nd": "no data"}
HANSEN = ("https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/"
          "Hansen_GFC-2024-v1.12_{layer}_{tile}.tif")
SOILGRIDS = "https://files.isric.org/soilgrids/latest/data/{p}/{p}_0-5cm_mean.vrt"
ROAD_CLASSES = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|track"
PELLETIER = {"soil_thick_m": "pelletier2016_hillslope_soil_thickness.tif",
             "regolith_thick_m": "pelletier2016_hillslope_regolith_thickness.tif"}
# order of preference when two layers are collinear: the earlier one is kept (more direct, more interpretable)
PRIORITY = ("slope_deg", "slope_s90", "upslope_slope_deg", "relief_300", "relief_1000", "tpi_500", "tpi_150",
            "tpi_1000", "hand_m", "profile_curv", "profile_curv_s150", "plan_curv", "plan_curv_s150", "twi", "spi",
            "flow_acc_km2", "dist_stream_m", "height_m", "aspect_sin", "aspect_cos", "tree_cover_event", "loss_before",
            "loss_before_300m", "tree_cover_2000", "soil_clay", "soil_sand", "soil_thick_m", "regolith_thick_m",
            "dist_road_m")
SENSITIVITY_ONLY = ("dist_stream_0p1_m", "dist_stream_1p0_m")      # stream-threshold variants, not in the models
ALT_DEM = "aw3d30_"     # the terrain layers again on JAXA AW3D30 (voids from GLO-30): the DEM variant of L3b
MAX_RHO, MAX_VIF, RARE_FRACTION = 0.8, 5.0, 0.01


# ---------------------------------------------------------------- sources
def _nearest(grid: Grid, a: np.ndarray, tr) -> np.ndarray:
    r = np.clip(((grid.lat - tr.f) / tr.e).astype(int), 0, a.shape[0] - 1)
    c = np.clip(((grid.lon - tr.c) / tr.a).astype(int), 0, a.shape[1] - 1)
    return a[r, c]


def soilgrids(grid: Grid, props=("clay", "sand")) -> dict[str, np.ndarray]:
    """SoilGrids 2.0 at 0–5 cm (g/kg), nearest 250 m pixel."""
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.windows import from_bounds
    out = {}
    for p in props:
        with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + SOILGRIDS.format(p=p)) as src, \
                WarpedVRT(src, crs="EPSG:4326") as vrt:
            win = from_bounds(*grid.bounds, vrt.transform).round_offsets().round_lengths()
            a = vrt.read(1, window=win).astype(np.float32)
            tr = vrt.window_transform(win)
        a[a <= 0] = np.nan
        out[f"soil_{p}"] = _nearest(grid, a, tr)
    return out


def pelletier(grid: Grid, cache: Path, token: str) -> dict[str, np.ndarray]:
    """Pelletier et al. (2016) hill-slope soil and regolith thickness (m), nearest 1 km pixel."""
    import rasterio
    from rasterio.windows import from_bounds

    from geoeyes.ancillary.geology import pelletier_file
    out = {}
    w, s, e, n = grid.bounds
    for col, name in PELLETIER.items():
        with rasterio.open(pelletier_file(cache, token, name)) as src:
            win = from_bounds(w - 0.01, s - 0.01, e + 0.01, n + 0.01, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win).astype(np.float32)
            tr = src.window_transform(win)
            if src.nodata is not None:
                a[a == src.nodata] = np.nan
        a[a < 0] = np.nan
        out[col] = _nearest(grid, a, tr)
    return out


def lithology(grid: Grid, glim_zip: Path) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    """GLiM class of every cell, one-hot; returns the layers and the fraction of the cells per class."""
    import pyogrio
    from pyproj import Transformer

    from geoeyes.landslide.labels import cells_in
    src = f"/vsizip/{glim_zip}/LiMW_GIS 2015.gdb"
    crs = pyogrio.read_info(src, layer="GLiM_export")["crs"]
    bb = Transformer.from_crs(4326, crs, always_xy=True).transform_bounds(*grid.bounds, densify_pts=21)
    g = pyogrio.read_dataframe(src, layer="GLiM_export", bbox=bb).to_crs(4326)
    code = np.full(len(grid), "nd", dtype=object)
    for xx, geom in zip(g["xx"], g.geometry, strict=True):
        code[cells_in(grid, geom)] = xx
    classes, counts = np.unique(code, return_counts=True)
    frac = {str(c): float(k) / len(grid) for c, k in zip(classes, counts, strict=True)}
    return {f"lith_{c}": (code == c).astype(np.float32) for c in classes}, frac


def osm_roads(grid: Grid, cache: Path, margin_m: float = 3000.0,
              progress=None) -> tuple[dict[str, np.ndarray], int]:
    """Distance (m) from each cell to an OSM road (``ROAD_CLASSES`` and their links), roads up to ``margin_m``
    outside the grid included; returns the layer and the number of OSM ways."""
    from scipy.ndimage import distance_transform_edt

    from geoeyes.landslide.terrain import crop, padded_grid
    from geoeyes.ml.lines import overpass
    big, ox, oy = padded_grid(grid, margin_m)
    w, s, e, n = big.bounds
    query = (f'[out:json][timeout:180];way["highway"~"^({ROAD_CLASSES})(_link)?$"]'
             f'({s:.5f},{w:.5f},{n:.5f},{e:.5f});out tags geom;')
    ways = overpass(query, cache, progress, "roads")
    on = np.zeros(len(big), bool)
    step = grid.cell_m / 3
    for way in ways:
        pts = np.array([(p["lon"], p["lat"]) for p in way["geometry"]])
        for (x0, y0), (x1, y1) in itertools.pairwise(pts):
            length = math.hypot((x1 - x0) * big.kx_m, (y1 - y0) * M_PER_DEG_LAT)
            t = np.linspace(0, 1, max(2, int(length / step) + 2))
            idx = big.cell_of(x0 + t * (x1 - x0), y0 + t * (y1 - y0))
            on[idx[idx >= 0]] = True
    dist = distance_transform_edt(~on.reshape(big.ny, big.nx)) * grid.cell_m if on.any() \
        else np.full((big.ny, big.nx), np.nan)
    return {"dist_road_m": crop(dist, grid, ox, oy).astype(np.float32)}, len(ways)


def _hansen_tiles(bounds) -> list[str]:
    w, s, e, n = bounds
    tiles = []
    for top in range(int(math.ceil(s / 10) * 10), int(math.ceil(n / 10) * 10) + 10, 10):
        if top - 10 >= n:
            continue
        for left in range(int(math.floor(w / 10) * 10), int(math.floor(e / 10) * 10) + 10, 10):
            if left >= e:
                continue
            tiles.append(f"{abs(top):02d}{'N' if top >= 0 else 'S'}_{abs(left):03d}{'E' if left >= 0 else 'W'}")
    return tiles


def hansen(grid: Grid, event_year: int) -> dict[str, np.ndarray]:
    """Tree cover in 2000 and the forest loss before ``event_year``, aggregated from the 0.00025° pixels."""
    import rasterio
    from rasterio.windows import from_bounds
    from scipy.ndimage import uniform_filter
    n = len(grid)
    count, tc, lost = np.zeros(n), np.zeros(n), np.zeros(n)
    w, s, e, nn = grid.bounds
    for tile in _hansen_tiles(grid.bounds):
        arrs = {}
        for layer in ("treecover2000", "lossyear"):
            with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + HANSEN.format(layer=layer, tile=tile)) as src:
                win = from_bounds(w, s, e, nn, src.transform).round_offsets().round_lengths()
                arrs[layer] = src.read(1, window=win)
                tr = src.window_transform(win)
        rows, cols = np.indices(arrs["lossyear"].shape)
        idx = grid.cell_of((tr.c + (cols + 0.5) * tr.a).ravel(), (tr.f + (rows + 0.5) * tr.e).ravel())
        ok = idx >= 0
        ii = idx[ok]
        ly = arrs["lossyear"].ravel()[ok].astype(int)
        count += np.bincount(ii, minlength=n)
        tc += np.bincount(ii, weights=arrs["treecover2000"].ravel()[ok].astype(float), minlength=n)
        lost += np.bincount(ii, weights=((ly >= 1) & (ly <= event_year - 2001)).astype(float), minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        tree = tc / count
        loss = lost / count
    k = max(3, round(300 / grid.cell_m) | 1)
    loss300 = uniform_filter(np.nan_to_num(loss).reshape(grid.ny, grid.nx), size=k, mode="nearest").ravel()
    return {"tree_cover_2000": tree.astype(np.float32), "loss_before": loss.astype(np.float32),
            "loss_before_300m": loss300.astype(np.float32),
            "tree_cover_event": (tree * (1 - loss)).astype(np.float32)}


# ---------------------------------------------------------------- screening
def merge_rare(table: pd.DataFrame, fractions: dict[str, float], rare: float = RARE_FRACTION) -> list[str]:
    """Lithology classes under ``rare`` of the rows merged into ``lith_other``; returns the merged classes."""
    lith = [c for c in table if c.startswith("lith_")]
    share = {c: float(table[c].mean()) for c in lith}
    merged = [c for c in lith if share[c] < rare or c == "lith_nd"]
    if merged:
        table["lith_other"] = table[merged].max(axis=1).astype(np.float32)
        table.drop(columns=merged, inplace=True)
    return merged


def vif(x: np.ndarray) -> np.ndarray:
    """Variance inflation factors of the columns of ``x`` (diagonal of the inverse correlation matrix)."""
    r = np.corrcoef(x, rowvar=False)
    return np.diag(np.linalg.pinv(r))


def screen(sample: pd.DataFrame, columns: list[str], max_rho: float = MAX_RHO, max_vif: float = MAX_VIF) -> dict:
    """Collinearity screening on the label cells: dropped layers with the reason, the sets for the trees and for the
    logistic model."""
    cont = [c for c in columns if not c.startswith("lith_")]
    rank = {c: (PRIORITY.index(c) if c in PRIORITY else len(PRIORITY)) for c in cont}
    x = sample[cont].astype(float)
    x = x.loc[:, x.std() > 0]
    rho = x.rank().corr().abs()
    dropped: dict[str, str] = {}
    for a in sorted(rho.columns, key=rank.get):
        if a in dropped:
            continue
        for b in rho.columns:
            if b != a and b not in dropped and rank[b] > rank[a] and rho.loc[a, b] > max_rho:
                dropped[b] = f"Spearman |rho| = {rho.loc[a, b]:.2f} with {a}"
    constant = [c for c in cont if c not in x.columns]
    for c in constant:
        dropped[c] = "constant over the label cells"
    trees = [c for c in columns if c not in dropped]
    logit = [c for c in trees if not c.startswith("lith_")]
    vifs_out: dict[str, float] = {}
    while len(logit) > 1:
        z = sample[logit].astype(float)
        z = (z - z.mean()) / z.std()
        v = dict(zip(logit, vif(z.fillna(0).to_numpy()), strict=True))
        worst = max(v, key=lambda k: (v[k], rank.get(k, 0)))
        vifs_out = {k: round(float(val), 2) for k, val in v.items()}
        if v[worst] <= max_vif:
            break
        dropped.setdefault(worst, f"VIF = {v[worst]:.1f} (logistic model only)")
        logit.remove(worst)
    lith = [c for c in trees if c.startswith("lith_")]
    return {"dropped": dropped, "trees": trees, "logistic": logit + lith[1:],   # one class left out as reference
            "vif": vifs_out, "spearman": rho.round(2).to_dict()}


def univariate_auc(pos: pd.Series, neg: pd.Series) -> float | None:
    """Mann–Whitney AUC of one layer (0.5 = no separation; < 0.5: lower on the landslides)."""
    from scipy.stats import mannwhitneyu
    a, b = pos.dropna().to_numpy(), neg.dropna().to_numpy()
    if len(a) < 5 or len(b) < 5:
        return None
    return round(float(mannwhitneyu(a, b).statistic / (len(a) * len(b))), 3)


# ---------------------------------------------------------------- the study step
SOURCES = {"terrain": "Copernicus GLO-30 (AWS open data), 1″, EGM2008",
           "lithology": "GLiM, Hartmann & Moosdorf (2012), full resolution (LiMW_GIS 2015.gdb), ~1:3.75 M",
           "soil": "SoilGrids 2.0 (ISRIC), 0–5 cm mean, 250 m",
           "regolith": "Pelletier et al. (2016), ORNL DAAC Global_Soil_Regolith_Sediment, 1 km",
           "access": "OpenStreetMap via the Overpass API (today's roads)",
           "forest": "Hansen et al. (2013) Global Forest Change v1.12 (2001–2024), tile 0.00025°"}


def run_predictors(study, cache_root: Path, token: str = "", progress=None) -> dict:
    """L2 of a study: ``predictors/predictors_<event>.parquet`` (the cells inside the footprints of the labels),
    ``predictors.json`` (sources, coverage, screening, univariate AUC), ``predictors.md``, maps, manifest."""
    import geopandas as gpd
    import shapely

    from geoeyes.geometry.dem import load_copernicus30
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.landslide.labels import cells_in, grid_for, study_area
    from geoeyes.landslide.terrain import MARGIN_M, terrain_layers
    say = progress or (lambda m: log.info("%s", m))
    area = study_area(study)
    grid = grid_for(area.bounds, study.labels.cell_m)
    fps = gpd.read_file(study.footprints, layer="footprints")
    keep = np.zeros(len(grid), bool)
    flags = {}
    for name, _ in study.events:
        for v in (study.footprint_main, study.footprint_sensitivity):
            m = np.zeros(len(grid), bool)
            m[cells_in(grid, shapely.intersection(fps[(fps.event == name) & (fps.variant == v)].geometry.iloc[0],
                                                  area))] = True
            flags[f"in_{v}_{name}"] = m
            keep |= m
    rows = np.flatnonzero(keep)
    say(f"grid {grid.nx} x {grid.ny} cells of {grid.cell_m:.0f} m, {len(rows)} inside the footprints")

    pad = (MARGIN_M + 2000) / M_PER_DEG_LAT
    w, s, e, n = grid.bounds
    dem = load_copernicus30(s - pad, n + pad, w - pad, e + pad, cache_root / "dem" / "copernicus-30")
    static: dict[str, np.ndarray] = {}
    warnings: list[str] = []
    info: dict = {"sources": SOURCES}
    def alt_terrain():
        from dataclasses import fields

        from geoeyes.geometry.dem import CompositeDem, load_aw3d30
        aw = load_aw3d30(s - pad, n + pad, w - pad, e + pad, cache_root / "dem" / "aw3d30")
        info["aw3d30_void_fraction"] = round(float(np.isnan(aw.height).mean()), 5)
        comp = CompositeDem(**{f.name: getattr(dem, f.name) for f in fields(dem) if f.name != "fine"}, fine=aw)
        return {ALT_DEM + k: v for k, v in terrain_layers(grid, comp, progress=say).items()
                if not k.startswith("dist_stream_") or k == "dist_stream_m"}

    steps = [("terrain", lambda: terrain_layers(grid, dem, progress=say)),
             ("terrain_aw3d30", alt_terrain),
             ("lithology", lambda: lithology(grid, cache_root / GLIM_ZIP)),
             ("soil", lambda: soilgrids(grid)),
             ("regolith", lambda: pelletier(grid, cache_root / "geology", token)),
             ("access", lambda: osm_roads(grid, cache_root / "osm", progress=say))]
    for name, fn in steps:
        say(f"layer: {name}")
        try:
            res = fn()
        except Exception as exc:                               # a missing source leaves its columns out
            warnings.append(f"{name} not read ({exc})")
            log.warning("layer %s not read: %s", name, exc)
            continue
        if name == "lithology":
            res, info["lithology_fraction"] = res
        elif name == "access":
            res, info["osm_ways"] = res
        static.update(res)
    base = pd.DataFrame({"cell": rows, "lon": grid.lon[rows], "lat": grid.lat[rows]})
    for k, v in static.items():
        base[k] = v[rows]
    for k, v in flags.items():
        base[k] = v[rows]
    info["lithology_merged"] = merge_rare(base, info.get("lithology_fraction", {}))

    out_dir = study.step_dir("predictors")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"study": study.name, "citation": study.citation, "grid": {"nx": grid.nx, "ny": grid.ny,
                     "cell_m": grid.cell_m, "rows": int(len(rows))}, **info, "warnings": warnings, "events": {}}
    files = []
    for name, date in study.events:
        say(f"layer: forest (Hansen) before {name} ({date[:4]})")
        t = base.copy()
        try:
            for k, v in hansen(grid, int(date[:4])).items():
                t[k] = v[rows]
        except Exception as exc:
            warnings.append(f"forest for {name} not read ({exc})")
        t.to_parquet(out_dir / f"predictors_{name}.parquet", index=False)
        files.append(f"predictors_{name}.parquet")
        summary["events"][name] = _event_summary(study, name, t)
    summary["layers"] = _coverage(base, [c for c in base if c not in ("cell", "lon", "lat") and
                                         not c.startswith("in_")])
    files += plot_layers(study, grid, base, out_dir)
    atomic_write_json(out_dir / "predictors.json", summary)
    (out_dir / "predictors.md").write_text(report_md(summary), encoding="utf-8")
    files += ["predictors.json", "predictors.md"]
    m = Manifest(kind="landslide_predictors", id=f"{study.name}/predictors", engine="geoeyes.landslide.predictors",
                 inputs=[InputRef("area", f"{study.area_file}#{study.area_name}"),
                         InputRef("footprints", str(study.footprints)),
                         InputRef("labels", str(study.step_dir("labels"))),
                         *[InputRef(k, v) for k, v in SOURCES.items()]],
                 params={"max_rho": MAX_RHO, "max_vif": MAX_VIF, "rare_fraction": RARE_FRACTION},
                 metrics={ev: {"dropped": len(s["screen"]["dropped"]), "trees": len(s["screen"]["trees"]),
                               "logistic": len(s["screen"]["logistic"])} for ev, s in summary["events"].items()})
    m.add_outputs(out_dir, files)
    m.write(out_dir)
    return summary


def _coverage(t: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    for c in cols:
        x = t[c].astype(float)
        ok = x.dropna()
        out[c] = {"missing": round(float(x.isna().mean()), 4),
                  **({"min": round(float(ok.min()), 3), "median": round(float(ok.median()), 3),
                      "max": round(float(ok.max()), 3)} if len(ok) else {})}
    return out


def _event_summary(study, event: str, t: pd.DataFrame) -> dict:
    """Screening and univariate AUC on the label cells of an event (scarp positives, first draw of the main
    footprint's negatives)."""
    lab = pd.read_parquet(study.step_dir("labels") / f"labels_{event}.parquet")
    lab = lab[((lab.label == 1) & (lab.variant == "scarp")) |
              ((lab.label == 0) & (lab.variant == "scarp") & (lab.draw == 0) & (lab.footprint == study.footprint_main))]
    s = lab[["cell", "label"]].merge(t, on="cell", how="left")
    cols = [c for c in t if c not in ("cell", "lon", "lat") and not c.startswith(("in_", ALT_DEM))
            and c not in SENSITIVITY_ONLY]
    alt = [c for c in t if c.startswith(ALT_DEM)]
    pos, neg = s[s.label == 1], s[s.label == 0]
    auc = {c: univariate_auc(pos[c], neg[c]) for c in cols + list(SENSITIVITY_ONLY) + alt if c in s}
    per_event = [c for c in ("tree_cover_2000", "loss_before", "loss_before_300m", "tree_cover_event") if c in t]
    return {"label_cells": {"positives": int(len(pos)), "negatives": int(len(neg)),
                            "without_predictors": int(s[cols[0]].isna().sum()) if cols else 0},
            "coverage": _coverage(t, per_event), "univariate_auc": auc, "screen": screen(s, cols)}


def plot_layers(study, grid: Grid, base: pd.DataFrame, out_dir: Path) -> list[str]:
    """Small multiples of the static layers over the study grid (cells outside the footprints blank)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = [c for c in base if c not in ("cell", "lon", "lat") and not c.startswith(("in_", "lith_", ALT_DEM))]
    k = int(math.ceil(len(cols) / 4))
    fig, axs = plt.subplots(k, 4, figsize=(18, 2.4 * k))
    step = max(1, grid.nx // 600)
    ext = grid.bounds[0], grid.bounds[2], grid.bounds[1], grid.bounds[3]
    for ax, c in zip(axs.ravel(), cols, strict=False):
        a = np.full(len(grid), np.nan, np.float32)
        a[base["cell"].to_numpy()] = base[c].to_numpy(np.float32)
        a = a.reshape(grid.ny, grid.nx)[::step, ::step]
        lo, hi = np.nanpercentile(a, [1, 99]) if np.isfinite(a).any() else (0, 1)
        im = ax.imshow(a, origin="lower", extent=ext, cmap="viridis", vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(c, fontsize=9)
        ax.tick_params(labelsize=6)
        fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01).ax.tick_params(labelsize=6)
    for ax in axs.ravel()[len(cols):]:
        ax.axis("off")
    fig.suptitle(f"L2 predictors, {study.name} (colour range: 1st–99th percentile)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "predictors_maps.png", dpi=90)
    plt.close(fig)
    return ["predictors_maps.png"]


def report_md(s: dict) -> str:
    lines = [f"# L2 predictors — {s['study']}", "", f"Inventory: {s['citation']}", "",
             f"Grid: {s['grid']['nx']} × {s['grid']['ny']} cells of {s['grid']['cell_m']:.0f} m; "
             f"{s['grid']['rows']} cells inside the footprints of the labels.", "", "## Sources", ""]
    lines += [f"- **{k}**: {v}" for k, v in s["sources"].items()]
    if s.get("warnings"):
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in s["warnings"]]
    lines += ["", "## Lithology (GLiM) over the study grid", ""]
    lines += [f"- `{k}` {GLIM_CLASSES.get(k, k)}: {v:.1%}" for k, v in
              sorted(s.get("lithology_fraction", {}).items(), key=lambda kv: -kv[1])]
    if s.get("lithology_merged"):
        lines += [f"- merged into `lith_other`: {', '.join(s['lithology_merged'])}"]
    lines += ["", "## Coverage (cells inside the footprints)", "", "| Layer | Missing | Min | Median | Max |",
              "|---|---|---|---|---|"]
    lines += [f"| {k} | {v['missing']:.1%} | {v.get('min', '')} | {v.get('median', '')} | {v.get('max', '')} |"
              for k, v in s["layers"].items()]
    for ev, e in s["events"].items():
        lines += ["", f"## {ev}", "", f"Label cells: {e['label_cells']}", "", "Layers of this event:", ""]
        lines += [f"- {k}: missing {v['missing']:.1%}, min {v.get('min', '')}, median {v.get('median', '')}, "
                  f"max {v.get('max', '')}" for k, v in e.get("coverage", {}).items()]
        lines += ["", "| Layer | Univariate AUC | Screening |", "|---|---|---|"]
        sc = e["screen"]
        for k, a in sorted(e["univariate_auc"].items(), key=lambda kv: -abs((kv[1] or 0.5) - 0.5)):
            lines.append(f"| {k} | {a} | {sc['dropped'].get(k, 'kept' if k in sc['trees'] else '—')} |")
        lines += ["", f"Trees ({len(e['screen']['trees'])}): {', '.join(e['screen']['trees'])}", "",
                  f"Logistic ({len(e['screen']['logistic'])}): {', '.join(e['screen']['logistic'])}"]
    return "\n".join(lines) + "\n"
