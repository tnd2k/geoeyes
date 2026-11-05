# Skill: hazard zoning of subsidence and slow landslides

> Rates every 100 m cell of an InSAR product from very low to very high hazard, from the motion in the expected
> direction (vertical or downslope), its response to rainfall and the differential settlement it implies.
> Status: operational screening tool (v1, research steps R0–R1 and part of R2 done). Last checked against the code
> 2026-11-01. CLI `geoeyes hazard`; web app **In-depth analysis → Thematic analysis**.

## 1. When to use it

- **Question.** Where does the ground move fast enough, in the direction that harms, to deserve attention; does the
  motion follow rainfall (or groundwater storage); where does the differential settlement exceed the damage limits?
- **Decision it supports.** Which areas to inspect first, where to look at time series, which areas need a better
  reference or a second geometry. It is the base layer of [behaviour-and-risk.md](behaviour-and-risk.md),
  [lines-and-consolidation.md](lines-and-consolidation.md) (consolidation), [decompose-and-soft-soil.md](decompose-and-soft-soil.md)
  (geology) and [susceptibility-and-forecast.md](susceptibility-and-forecast.md).
- **Not for.** Probabilistic hazard (no return period, no probability of failure: Fell et al. 2008), event-scale
  triggering of rapid landslides, a risk map (use [behaviour-and-risk.md](behaviour-and-risk.md)), or a reading of
  intensity classes on a product referenced to the scene mean without `reference_bbox` or `gnss_tie`.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Point product (PS/DS) | yes | [insar-processing.md](insar-processing.md): `geoeyes run` | `projects/<name>/products/<product_id>/` with `points.parquet` (columns `point_uid`, `lon`, `lat`, `los_e`, `los_n`, `los_u`, optional `temporal_coherence`), `timeseries.parquet`, `manifest.json` | Without `los_e/los_n/los_u` the run stops. ≥ 12 months and ≥ 12 epochs for the rainfall test, ≥ 18 months for acceleration |
| DEM | yes (else every cell is "subsidence") | `[stack].dem` of the project: `srtm-1` (default), `copernicus-30`, `lidar-3dep`, a folder of `.hgt` or a GeoTIFF; downloaded when missing | `[stack] dem`, or `[postprocess.hazard] dem = "<path or name>"` to override; cache `<workspace>/cache/dem` | A bare-earth DEM (FABDEM) reduces building artefacts in cities |
| Monthly and annual rainfall | yes (automatic) | CHIRPS v3 COGs from data.chc.ucsb.edu (0.05°); ERA5 daily via the Open-Meteo archive (0.25°) as fallback | `[postprocess.hazard] rain_source = "auto" \| "chirps" \| "era5"`; cache `<workspace>/cache/rainfall/chirps3_*.npz`, `era5_*.json` | Needs network on the first run. 30 annual files (1991–2020) plus one file per month |
| GLDAS groundwater storage | optional (diagnostic) | NASA GLDAS CLSM025 DA1 D v2.2, `GWS_tavg`, via Earthdata OPeNDAP (Harmony as fallback) | `EARTHDATA_TOKEN` in the environment or `.env`; `[postprocess.hazard] groundwater = "auto" \| "gldas" \| "off"`; cache `<workspace>/cache/groundwater/gldas_gws_*.npz` | Published months late: recent dates are left out of the test |
| Stable reference area | strongly recommended when the product is referenced to the scene mean | Known stable ground (bedrock, an old massive building cluster, a GNSS site), from geology maps or local knowledge | `[postprocess.hazard] reference_bbox = [w, s, e, n]` (degrees), or web field "Stable" | Must contain at least one cell. Ignored when `gnss_tie = true` |
| GNSS calibration | optional, replaces `reference_bbox` | [gnss-calibration.md](gnss-calibration.md): `geoeyes gnss <project> --product <id>` | `projects/<name>/analyses/gnss/<product_id>/`; `[postprocess.hazard] gnss_tie = true` | The run fails if the product has no calibration. One station = not checked independently (warning) |
| Landslide susceptibility raster | optional | Your own map, classes 0..3 | GeoTIFF, any CRS; `[postprocess.hazard] susceptibility = "<path>"` | Replaces the slope placeholder (15° / 25° / 35°) for landslide cells. Values outside 0..3 are ignored |

Checklist before running:

- [ ] The product has `los_e`, `los_n`, `los_u` and a time series; its span and number of epochs are known.
- [ ] You know how the product is referenced (point, scene mean): `manifest.json` → `metrics.reference`.
- [ ] If scene mean: a stable `reference_bbox` is chosen, or `geoeyes gnss` has run and `gnss_tie = true`.
- [ ] Network access to data.chc.ucsb.edu and archive-api.open-meteo.com (first run), Earthdata for GLDAS.
- [ ] The DEM of the project is the one you want (a DSM gives false slopes at building edges).
- [ ] Parameters you change are written in `[postprocess.hazard]` (unknown keys stop the run).

## 3. Method

Code: `src/geoeyes/hazard/assess.py` (`HazardParams`, `assess`). Parameter names below are the keys of
`[postprocess.hazard]`.

1. **Cells.** Points are binned into squares of `cell_m` (100 m; allowed 5–5000) on a local metric grid. A cell
   needs `min_points` (3) points. It keeps the median LOS series, the median LOS unit vector (renormalised) and the
   median coherence.
2. **Reference.** With `gnss_tie`, the GNSS correction of the product is added to every series. Else with
   `reference_bbox`, the median series of the cells inside is subtracted from all. Else the product's reference is
   kept; a scene-mean reference raises a warning.
3. **Terrain and mode.** The DEM is smoothed with a Gaussian of σ = half a cell, then the slope is taken over one
   cell (central differences). `slope ≥ landslide_min_slope_deg` (10°) → `landslide` mode, else `subsidence`.
4. **Motion in the hazard direction** (positive = sinking or downslope inside the analysis):
   - subsidence: y = −d_LOS / l_u (cells with |l_u| < 0.1 are not assessed);
   - landslide: y = d_LOS / (**s**·**l**), **s** the steepest-descent unit vector; not assessed when
     |**s**·**l**| < `min_sensitivity` (0.3).
   - One least-squares fit with [1, t, ½t²] (t centred, quadratic only with ≥ 6 epochs) gives the rate (mm/yr) and
     its σ, and the acceleration and its σ.
   - Stability threshold per cell: max(`stable_floor_mm_yr` 2, `stable_sigma` 2 × σ).
5. **Rainfall.** Monthly rainfall per pixel from `max_lag_months` (6) before the first date to the last date;
   annual totals over `climate_years` (1991, 2020) give P10 and P90 (needs ≥ 10 years). With `auto`, ERA5 replaces
   CHIRPS when fewer than 80 % of the months or of the climate years could be read.
   - CRD(t) = Σ(P_month − P̄), P̄ = mean over the window, linear within a month; missing months count as P̄; a
     pixel with > 20 % missing months is not tested.
6. **Rainfall coupling** (`coupling.py`), per cell, only when span ≥ `min_span_months` (12) and epochs ≥
   `min_epochs` (12):

       y(t) = a + b·t + k·CRD(t − τ) + ε,   τ ∈ {0 … max_lag_months}

   - τ = the lag with the largest |partial correlation| r of y and CRD given [1, t].
   - p = share of `n_surrogates` (500) phase-randomised rainfall anomalies (Ebisuzaki 1997) whose best |r| reaches
     the observed one; with fewer than 10 exceedances, p from a normal fit to the Fisher z of the null.
   - q = Benjamini–Hochberg over all tested cells (`fdr` = true). **Coupled** when q ≤ `alpha` (0.05).
   - Scenario in coupled cells: rate_dry = b + k·(P10 − 12·P̄), rate_wet = b + k·(P90 − 12·P̄).
7. **Groundwater coupling** (diagnostic, does not change the level): the same test with GLDAS storage S at
   mid-month in place of the CRD, surrogates built from the monthly storage changes, only on the dates the storage
   covers (still ≥ 12 months and ≥ 12 epochs). Reported in `gw_*` columns.
8. **Intensity I** (in the hazard direction; for coupled cells the worse of observed, dry-year and wet-year rate):

   | Class | Subsidence, `subsidence_breaks` (10, 30) mm/yr | Landslide, `landslide_breaks` (16, 160) mm/yr |
   |---|---|---|
   | I0 | < stability threshold, or opposite motion | same |
   | I1 | threshold … 10 | threshold … 16 |
   | I2 | 10 … 30 | 16 … 160 |
   | I3 | ≥ 30 | ≥ 160 |

   - +1 class (max I3) when span ≥ `accel_min_span_months` (18), acc/σ_acc ≥ `accel_t` (3) and rate > 0.
   - Rate < −threshold → `opposite_motion` flag (uplift or apparent upslope), I0.
9. **Damage potential S.**
   - Subsidence: β = max over the 8 neighbours of |v_i − v_j| · `horizon_yr` (10) / L, L = centre distance;
     classes by `distortion_breaks` (1/500, 1/300, 1/150) → S0…S3. Independent of the reference.
   - Landslide: class 0..3 of `susceptibility` if given, else slope classes `slope_breaks` (15°, 25°, 35°).
10. **Hazard level** = `matrix`[I][S], levels 0 very low … 4 very high, −1 not assessed:

    | | S0 | S1 | S2 | S3 |
    |---|---|---|---|---|
    | I0 | very low | very low | low | low |
    | I1 | low | low | moderate | high |
    | I2 | moderate | moderate | high | very high |
    | I3 | high | high | very high | very high |

Published basis: Cigna et al. 2013 (PSI matrix, L2S projection), Barra et al. 2017 and Tomás et al. 2019 (stability,
≥ 3 PS), Navarro et al. 2020 (slope rules), Cruden & Varnes 1996 (16 mm/yr), Skempton & MacDonald 1956 and
Bjerrum 1963 (distortion), Bredenkamp et al. 1995 (CRD), Ebisuzaki 1997, Benjamini & Hochberg 1995, Knijnenburg
et al. 2009. Sources of every default: [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md) §5.

## 4. Steps

1. **Check the reference.** Read `metrics.reference` in `projects/<name>/products/<id>/manifest.json`. If it is
   `"scene mean"`, choose a stable box, or run `geoeyes gnss <project> --product <id>` first
   ([gnss-calibration.md](gnss-calibration.md)).
2. **Write the parameters** (only what differs from the defaults):

   ```toml
   [postprocess.hazard]
   cell_m = 100
   reference_bbox = [105.770, 21.010, 105.780, 21.020]   # stable ground (example from the research note)
   # gnss_tie = true
   # susceptibility = "D:/data/landslide_susceptibility_classes.tif"
   ```
3. **Run.**

   ```
   geoeyes hazard <project> --product <product_id>
   geoeyes hazard <project> --product <product_id> --set cell_m=50 --set rain_source=era5
   geoeyes hazard <project> --product <product_id> --set "reference_bbox=[105.77,21.01,105.78,21.02]"
   ```
   Without `--product`, the latest product of each track is used. `--set` values are read as JSON.
   Web app: **In-depth analysis → Thematic analysis**, choose project and product, set Cell (50/100/200/500 m),
   Horizon (5/10/20/50 yr), Max lag (3/6/9/12 mo), FDR (0.01/0.05/0.1), Rain, Groundwater, Stable (W, S, E, N),
   GNSS tie, then **Run hazard zoning**.
4. **Run time.** Not benchmarked. The first run of an area is dominated by downloads: CHIRPS is read one file at a
   time (stops at the first refusal), GLDAS takes a few minutes on its first read (log message). Later runs read
   the caches. The surrogate test runs once per rainfall pixel, not per cell.
5. **Files written** in `projects/<name>/analyses/hazard/<product_id>/`: `cells.parquet`, `cells_ts.npy`,
   `rain.npz`, `groundwater.npz` (when GLDAS was read), `hazard.json`, `hazard.gpkg` (layer `hazard_cells`),
   `manifest.json`. The product itself is never modified; re-running overwrites the analysis.

## 5. Outputs and how to read them

Sign convention of every output (`hazard.json` `"sign"`, schema `geoeyes.hazard/2`): **negative = sinking or
downslope**, positive = uplift or upslope.

| Field (`cells.parquet`, also in `hazard.gpkg`) | Meaning |
|---|---|
| `mode` | `subsidence` or `landslide` |
| `slope_deg`, `sensitivity` | smoothed slope; l_u (subsidence) or **s**·**l** (landslide) |
| `rate_mm_yr`, `rate_se_mm_yr`, `stable_mm_yr` | rate in the hazard direction, its σ, the cell's stability threshold |
| `acc_mm_yr2`, `accelerating`, `opposite_motion` | acceleration; +1 class applied; motion against the hazard direction |
| `rain_lag_months`, `rain_r`, `rain_p`, `rain_q`, `rain_coupled` | lag τ, partial correlation, surrogate p, FDR q, significance |
| `rain_k_mm_per_100mm`, `trend_rain_corrected_mm_yr` | sensitivity k per 100 mm of rainfall departure; b |
| `rate_dry_year_mm_yr`, `rate_wet_year_mm_yr` | scenario rates (coupled cells) |
| `intensity_observed`, `intensity` | I from the observed rate; I after scenario and acceleration |
| `angular_distortion`, `susceptibility`, `secondary` | β; user class; S |
| `hazard` (gpkg: `hazard_level`) | level 0–4, −1 not assessed |
| `gw_*` | the same coupling fields against groundwater storage |

- **k sign.** With the GeoEyes sign, k < 0 means more rain → more sinking or downslope motion
  (`coupling.share_negative_k` in `hazard.json`). For groundwater, g > 0 means the ground rises and falls with the
  storage (elastic aquifer, `groundwater.share_positive_g`).
- `hazard.json`: parameters, `by_level` (cells and km² per mode and level), `coupling` (tested, p < α raw,
  significant, median lag), `accelerating_cells`, `opposite_motion_cells`, `reference`, `rain` (source, pixels,
  P10/P50/P90), `groundwater`, `warnings`.
- Web layers: Hazard level, Intensity (InSAR), Damage potential, Rate, Rain coupling, Rain lag, Groundwater
  coupling, Mode. Clicking a cell shows its series, fitted models and monthly rainfall.

## 6. Quality checks

- **Warnings first.** Read `hazard.json` `warnings`: scene-mean reference, coupling not assessed (span/epochs),
  CHIRPS refused (ERA5 used), partial rainfall months, groundwater coverage, no terrain.
- **Reference.** No intensity map is read without stable-ground referencing (research R0 criterion). A large
  `opposite_motion_cells` count (Mexico S1: 19 087 cells "up") means a relative reference.
- **Coupling plausibility.** The raw share of p < α (`cells_p_below_alpha` / `cells_tested`) must exceed α
  before coupled cells are interpreted (R1 criterion). Hanoi CSK: 3.7 %, Hanoi S1: 1.7 %, 0 significant: a null
  result (research note §7).
- **Rain source.** `rain.source`: ERA5 smooths convective peaks (Hanoi June 2011: ERA5 224 mm, CHIRPS 430 mm).
- **Mode map.** Landslide cells on flat urban ground point to DSM artefacts; check `slope_deg` against the
  terrain.
- **β is reference-free**, so the S classes can be read even on a relative product (Mexico S1: 9 314 cells
  ≥ 1/500 over 10 years, research note §7).

## 7. Limits and pitfalls

- **One geometry.** Motion is assumed vertical or downslope. Horizontal motion around bowls, or subsidence on
  slopes, is misattributed: decompose with two geometries ([decompose-and-soft-soil.md](decompose-and-soft-soil.md)).
- **Linear rainfall response** extrapolated to P10/P90 years; landslide and aquifer responses are non-linear.
- **Correlation is not cause.** Rain, temperature and storage co-vary in monsoon climates (R2 not done).
- **Coarse forcing.** CHIRPS ≈ 5.5 km pixels, ERA5 0.25°, GLDAS 0.25°: coupling is per rainfall pixel.
- **Uncalibrated classes.** `subsidence_breaks`, `slope_breaks` and `matrix` are expert choices until R3/R4.
- **Short series.** Under 12 months / 12 epochs the coupling is skipped; under 18 months no acceleration.
- **CHIRPS throttling.** The server refuses clients that read many files: a refusal stops the reading and `auto`
  falls back to ERA5. Re-run later to fill the cache.
- **Re-runs invalidate dependants.** Behaviour, risk, consolidation and geology read `cells.parquet`; re-run them
  after re-running the zoning.

## 8. On a new area or sensor

- **Change:** `reference_bbox` (or `gnss_tie`), `cell_m` (stay above the DSM building scale; it is the L of β),
  `dem` (bare-earth if available), `susceptibility` in mountain areas, `rain_source = "era5"` where CHIRPS has no
  coverage (CHIRPS covers land only; ocean pixels are no data).
- **Carries over:** the CRD model, the surrogate/FDR test, the distortion limits, the landslide breaks (Cruden &
  Varnes).
- **Calibrate locally:** `subsidence_breaks` and `matrix` against a damage inventory (research R3).
- **Sensor:** any product with a LOS vector works. X-band stacks of a few weeks (Capella, ICEYE) give no coupling
  and no acceleration; read only β and the rate.
- **Known habits:** Hanoi smoothed slopes have P99 = 4.3°, so almost every cell is in subsidence mode; Mexico City
  products need a stable box on the volcanic rock before reading intensities.

## 9. References

- Code: `src/geoeyes/hazard/assess.py`, `coupling.py`, `zoning.py`, `terrain.py`; `src/geoeyes/ancillary/rainfall.py`,
  `groundwater.py`; `src/geoeyes/api/hazard.py`; `webapp/src/pages/Hazard.tsx`, `LearnHazard.tsx` (Principles,
  chapter 2); tests `tests/unit/hazard/test_hazard.py`, `test_groundwater.py`.
- Research: [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md),
  [../research/groundwater-insar.md](../research/groundwater-insar.md); ADR-024 in
  [../architecture/decisions.md](../architecture/decisions.md).
- Skills: [insar-processing.md](insar-processing.md), [gnss-calibration.md](gnss-calibration.md),
  [behaviour-and-risk.md](behaviour-and-risk.md), [exposure-and-flood-layers.md](exposure-and-flood-layers.md).
- Papers: Cigna, Bianchini & Casagli 2013 (*Landslides* 10:267); Barra et al. 2017 (*Remote Sensing* 9:1002);
  Tomás et al. 2019 (*Remote Sensing* 11:1675); Navarro et al. 2020 (*IJGI* 9:584); Cruden & Varnes 1996;
  Skempton & MacDonald 1956; Bjerrum 1963; Fernández-Torres et al. 2020; Ebisuzaki 1997; Benjamini & Hochberg
  1995; Knijnenburg et al. 2009; Funk et al. 2026 (CHIRPS v3); Hersbach et al. 2020 (ERA5); Li et al. 2019
  (GLDAS DA). Full list in the research note §10.
