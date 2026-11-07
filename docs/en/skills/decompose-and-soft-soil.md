# Skill: vertical and east-west motion from two geometries; soft-soil thickness against subsidence

> Separates the vertical and east-west motion where the workspace holds two products that look at the same ground
> from opposite sides over the same period; and reads the thickness of the soft (compressible) layer under every
> hazard cell to compare it with the subsidence and to check consolidation time constants.
> Status: operational (v1, 2026-10-27); the open thickness grid is a placeholder. Last checked against the code
> 2026-11-01. CLI `geoeyes decompose`, `geoeyes geology`; web app **In-depth analysis → Thematic analysis**, layers
> "Vertical motion", "East-west motion", "Soft-soil thickness".

## 1. When to use it

- **Decompose.** Every single-product analysis (zoning, lines, buildings, consolidation) reads v_LOS / l_u as
  vertical. That fails where the ground moves sideways: around subsidence bowls and on slopes. Use `decompose` to
  measure the vertical motion and to know how wrong the single-geometry vertical is.
- **Geology.** Does the ground sink where the soft layer is thick? Use `geology` to compare thickness and sinking,
  and to test whether a "consolidating" cell is compatible with the layer under it.
- **Not for.** North-south motion (assumed zero), absolute velocities (the result is relative to the common area),
  pairs whose periods do not overlap, or a reading of the open global grid as a soft-layer map.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Product to decompose | yes | [insar-processing.md](insar-processing.md) | `projects/<name>/products/<track>_v<N>/` with `item.json` (bbox, `geoeyes:first_date`, `geoeyes:last_date`, track, project) and `points.parquet` (`lon`, `lat`, `vel_los_mm_yr`, `vel_std_mm_yr`, `los_e`, `los_n`, `los_u`) | |
| Partner product(s) | yes | A product of another track (or sensor) over the same area: add a track to the project ([insar-processing.md](insar-processing.md)) or use another project of the same workspace | Any `projects/*/products/*_v<N>/` of the workspace; the latest version of each (project, track) is considered | Must overlap in extent, overlap ≥ 50 % of the shorter period, and differ by \|Δl_e\| ≥ 0.5 |
| Hazard zoning of the product | yes for `geology` | [hazard-zoning.md](hazard-zoning.md) | `projects/<name>/analyses/hazard/<id>/` | Thickness is read at its cell centres |
| Consolidation analysis | optional for `geology` | [lines-and-consolidation.md](lines-and-consolidation.md): `geoeyes consolidation` | `projects/<name>/analyses/consolidation/<id>/consolidation.parquet` | Needed for the c_v check; must come from the same zoning (same number of cells) |
| Soft-soil thickness map | preferred | Geological survey map of the soft layer (Hanoi: Holocene clay and peat of the Hải Hưng and Thái Bình formations, e.g. Phi & Strokova 2017), digitised | GeoTIFF of metres, any CRS; `[postprocess.geology] raster = "geom/soft_soil.tif"` (path relative to the project folder) | First source used when set |
| Boreholes | alternative | Borehole logs: depth of the base of the soft layer | CSV with `lon`, `lat`, `thickness_m` (optional `name`); `[postprocess.geology] boreholes = "geom/boreholes.csv"` | ≥ 3 boreholes. Used only when `raster` is empty |
| Open grid | fallback (default) | Pelletier et al. 2016, sediment thickness above bedrock on lowlands, 1 km, capped at 50 m (NASA ORNL DAAC) | Downloaded once to `<workspace>/cache/geology/pelletier2016_lowland_sediment_thickness.tif`; needs `EARTHDATA_TOKEN` | `open_fallback = true`. A depth to bedrock, not the soft layer |
| Parameters | optional | – | `[postprocess.decompose]`, `[postprocess.geology]` | Unknown keys stop the run |

Checklist before running:

- [ ] Both geometries are processed in the same workspace, with overlapping periods (check `first`/`last`).
- [ ] Each product's own quality is known; a ramp in one product becomes east-west motion (Hanoi asc 128).
- [ ] `deramp = "plane"` is decided (the plane also removes any real tilt of the area).
- [ ] For geology: a raster or boreholes in the project folder, or `EARTHDATA_TOKEN` for the open grid.
- [ ] For the c_v check: `geoeyes consolidation` was run after the current zoning.

## 3. Method

### 3.1 Decomposition (`src/geoeyes/ml/decompose.py`, `DecomposeParams`)

A product measures v_LOS = e·l_e + n·l_n + u·l_u (unit vector ground → satellite); n is assumed 0
(|l_n| ≈ 0.1–0.15 for Sentinel-1).

1. **Partners.** Latest version of every (project, track) in the workspace, other than the product's own track,
   with overlapping bbox, overlap ≥ `min_overlap_share` (0.5) of the shorter period and |Δl_e| ≥
   `min_east_contrast` (0.5). Sorted by overlap days.
2. **Common support.**
   - `support = "cells"` (default): grid of `cell_m` (100 m) in degrees over the common bbox; per product and
     cell the median v_LOS and LOS vector, if ≥ `min_points` (3). σ = max(1.4826·MAD/√n, median
     `vel_std_mm_yr`/√n, `sigma_floor_mm_yr` 0.5).
   - `support = "points"`: at each point of the product inside the common bbox, per product the median of up to
     `max_neighbours` (16) points within `radius_m` (20 m); same σ rule.
   - At least 10 locations seen by all products, else the run stops.
3. **Ramps.** A plane a + b·x + c·y is fitted to each product's velocities (outliers > 3 MAD dropped, 3 passes).
   With `deramp = "plane"` it is removed. With `deramp = "none"`, a warning is raised when the largest plane span
   exceeds `ramp_warning_mm_yr` (5) and twice the smallest.
4. **Common reference.** Each product minus the median of its velocities over the common locations.
5. **Solution.** Weighted least squares per location of [l_e, l_u]·[e, u] = v_LOS (weights 1/σ²), with σ_e and σ_u
   from the normal matrix.
6. **Horizontal flag:** |e| ≥ `horizontal_mm_yr` (5) and |e| ≥ 2σ_e. **Single-geometry error:** v_LOS / l_u − u per
   product (median and P90 of |·|).

### 3.2 Soft-soil thickness (`src/geoeyes/ancillary/geology.py`, `GeologyParams`; `src/geoeyes/ml/geology.py`)

1. **Thickness** at each zoning cell from the first available source: `raster` (sampled, negatives and nodata →
   NaN), else `boreholes` (inverse distance, power `idw_power` 2, `idw_neighbours` 8, NaN beyond
   `max_borehole_km` 3 km of the nearest), else the open grid if `open_fallback`.
2. **Rate by thickness class:** `bins` (5) quantile classes; per class the median rate of the sinking cells
   (subsidence mode, rate < 0) and the share of cells with rate ≤ −`moving_mm_yr` (5). Needs ≥ 5 × `bins` cells.
3. **Spearman ρ** between thickness and sinking (−rate) of the sinking cells (≥ 20 cells, non-constant thickness).
4. **Consolidation check** for consolidating cells: Terzaghi's first term τ = 4·H_dr² / (π²·c_v), so
   c_v = 4·H_dr² / (π²·τ), H_dr = H/2 with `drainage = "double"` (H with `"single"`). Compared with 0.1–10 m²/yr
   for soft clays (Holtz & Kovacs 1981).

Published basis: Wright et al. 2004 and Fuhrmann & Garthwaite 2019 (multi-geometry decomposition), Pelletier et al.
2016, Terzaghi 1925, Holtz & Kovacs 1981.

## 4. Steps

1. **Second geometry.** Process the other track over the same period (Hanoi: asc 128 added to `hanoi_s1` next to
   desc 091).
2. **Decide the ramp handling**, e.g. in `project.toml` of the product's project:

   ```toml
   [postprocess.decompose]
   deramp = "plane"        # as in hanoi_s1
   # support = "points"    # 20 m neighbourhoods, no GeoTIFF
   ```
3. **Decompose.** `geoeyes decompose <project> --product <id>` (e.g. `--set deramp=plane --set cell_m=50`).
   Web: Thematic analysis → layer "Vertical motion" or "East-west motion" → **Separate vertical and east-west**.
   Run time not benchmarked (reads the points of every product). Writes `projects/<name>/analyses/decompose/<id>/`:
   `decompose.parquet`, `decompose.json`, `up.tif` and `east.tif` (cells support only), `manifest.json`.
4. **Zoning** (for geology): `geoeyes hazard <project> --product <id>`; optionally `geoeyes consolidation`.
5. **Thickness source**, e.g.:

   ```toml
   [postprocess.geology]
   raster = "geom/soft_soil.tif"          # or: boreholes = "geom/boreholes.csv"
   drainage = "double"
   ```
6. **Geology.** `geoeyes geology <project> --product <id>`. Web: layer "Soft-soil thickness" → **Read the
   soft-soil thickness**. The first open-grid run downloads the global grid once. Writes
   `projects/<name>/analyses/geology/<id>/`: `geology.parquet`, `geology.json`, `manifest.json`.
7. The thickness also enters the susceptibility model as `soft_soil_m`
   ([susceptibility-and-forecast.md](susceptibility-and-forecast.md)).

## 5. Outputs and how to read them

**`decompose.parquet`**: `cell`, `lon`, `lat`, `up`, `east`, `sigma_up`, `sigma_east` (mm/yr; up positive, east
positive), per product k: `v_los_k` (after reference and deramp), `n_k`, `vert_only_k` (what that product alone
calls vertical), and `horizontal`. **`decompose.json`**: products (id, track, sensor, period, LOS, overlap),
`grid`, `up_mm_yr` and `east_mm_yr` (min, p02, median, p98, max), median σ, `horizontal_share`,
`vertical_only_bias` per product, `ramps` (mm/yr per km, span, removed), warnings. `up.tif`, `east.tif`: EPSG:4326,
mm/yr.

**`geology.parquet`**: `cell`, `lon`, `lat`, `thickness_m`, `nearest_borehole_km` (boreholes), `cv_m2_yr`
(consolidating cells). **`geology.json`**: `source`, `thickness_m` (min, median, max), `spearman_rho`,
`spearman_p`, `by_class` (from_m, to_m, cells, median_rate_mm_yr, moving_share), `consolidation_cv` (median,
p10, p90, share within range), warnings.

Reading: ρ > 0 means thicker soft soil, faster sinking. Mexico City S1 with the open grid: ρ = 0.51, median rate
−97 / −116 / −204 mm/yr from thin to capped classes; Hanoi: 92 % of cells at the cap, ρ = −0.11, no information
(research note §4.3).

## 6. Quality checks

- **Ramps.** Compare `ramps[].span_mm_yr`: a tilt seen by one product only is an error (orbit, ionosphere,
  atmosphere). Hanoi asc 128 v1 spanned 26.9 mm/yr against 3.9 for desc 091.
- **Correlation of east and up.** A strong correlation (Hanoi without deramp: −0.80) betrays one line of sight's
  error mapped into both components (`report/qc.py` reports it).
- **Empirical noise of e** from stable cells: Hanoi median |e| = 1.8 mm/yr (σ_e ≈ 2.7, four times the formal
  0.64). Read east-west only above ~5–8 mm/yr there.
- **Does horizontal motion point to the bowls?** If not (Hanoi: 48–53 % towards, i.e. chance), it is residual
  disagreement, not ground motion.
- **Geology warnings:** open grid in use; > 50 % of cells at the 50 m cap.
- **c_v:** values ~100 times the soft-clay range (830–1,000 m²/yr in every test product) reject the thickness as
  the consolidating layer or the consolidation reading.

## 7. Limits and pitfalls

- Periods must overlap; otherwise constant rates are assumed (warning).
- North-south is ignored; an oblique sensor (Capella, l_n = −0.46 over Mexico City) leaks it into e and u.
- The result is relative to the median of the common area; the hazard GNSS tie is not carried over.
- Formal σ exclude ramps and atmosphere that differ between products; short X-band series are the worst
  (Mexico City S1 + 50-day Capella: not reliable, research note §4.1).
- `deramp = "plane"` also removes a real regional tilt.
- Partners are searched only among the latest product version of each track; `decompose` cannot be pointed at a
  chosen partner from the CLI.
- Borehole interpolation draws no geology between boreholes (palaeochannels need a map).
- The c_v check is skipped when `consolidation.parquet` does not have one row per current zoning cell.

## 8. On a new area or sensor

- **Decompose:** process a second geometry over the same period; set `deramp` after reading the ramps;
  `support = "points"` for dense X-band (Mexico City at 15 m: 60,027 locations instead of 1,731 cells);
  `horizontal_mm_yr` to the empirical noise of e.
- **Dusk passes near the equatorial anomaly** (Hanoi ascending, 18:06 local): expect ionospheric ramps; use the
  split-spectrum correction ([ionosphere.md](ionosphere.md)) and keep `deramp = "plane"`.
- **Geology:** obtain a soft-layer map or boreholes (Hanoi: BGS 3D model, 271 boreholes; Phi & Strokova 2017,
  research G1); set `drainage` from the stratigraphy; adjust `moving_mm_yr` and `bins`.

## 9. References

- Code: `src/geoeyes/ml/decompose.py`, `src/geoeyes/ml/geology.py`, `src/geoeyes/ancillary/geology.py`,
  `src/geoeyes/ml/layers.py` (`soft_soil_m`), `src/geoeyes/report/qc.py`; `webapp/src/pages/Hazard.tsx`,
  `LearnGeometry.tsx` (Principles, chapter 5); tests `tests/unit/ml/test_decompose_geology.py`.
- Research: [../research/two-geometries-and-soft-soil.md](../research/two-geometries-and-soft-soil.md);
  [../guide/ionosphere.md](../guide/ionosphere.md).
- Skills: [hazard-zoning.md](hazard-zoning.md), [lines-and-consolidation.md](lines-and-consolidation.md),
  [ionosphere.md](ionosphere.md), [gnss-calibration.md](gnss-calibration.md).
- Papers: Wright, Parsons & Lu 2004 (*GRL* 31:L01607); Fuhrmann & Garthwaite 2019 (*Remote Sensing* 11:241);
  Pelletier et al. 2016 (*JAMES* 8:41, data doi:10.3334/ORNLDAAC/1304); Terzaghi 1925; Holtz & Kovacs 1981;
  Phi & Strokova 2017; Gomba et al. 2016; Liang & Fielding 2017.
