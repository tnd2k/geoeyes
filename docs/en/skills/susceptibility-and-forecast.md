# Skill: ground-motion susceptibility and deformation forecast

> Where else could the ground move, given where InSAR sees it move, and how much will a cell move in the next
> months? Status: research (both run end to end; the forecast rarely beats the "no change" baseline so far). Last
> checked 2026-11-01. CLI: `geoeyes susceptibility`, `geoeyes forecast`. Web app: In-depth analysis → Machine
> learning research (`#/ai/<project>/<product>/susceptibility` or `/forecast`).

## 1. When to use it

- **Susceptibility** answers: which combination of terrain, land cover, buildings, soil and soft-soil thickness
  goes with the cells InSAR sees sinking (or moving downslope), and which cells *without* InSAR points (vegetation,
  water edges) look like them. Use it to extend a subsidence map into areas InSAR cannot measure and to rank the
  thematic layers by how much they explain.
- **Forecast** answers: how much will each cell's line-of-sight displacement change over a few horizons, and does
  any model do better than "no change" or "the same trend"? Use it to set expectations for the next acquisitions
  and to test whether rainfall or groundwater add predictive skill.
- Do not use susceptibility as a causal map: groundwater pumping, the main driver of urban subsidence, is not a
  layer. Do not use the forecast as a warning by itself: read the backtest first (§6). Neither replaces the hazard
  zoning ([hazard-zoning.md](hazard-zoning.md)), which susceptibility needs as its labels.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| InSAR product | yes | `geoeyes run` ([insar-processing.md](insar-processing.md)) | `<project>/products/<product_id>/points.parquet` with `los_e`, `los_n`, `los_u`; `timeseries.parquet` | the forecast reads it directly; the susceptibility through the hazard cells |
| Hazard analysis of the same product | yes for susceptibility; optional for forecast | `geoeyes hazard <project> --product <id>` | `<project>/analyses/hazard/<product_id>/hazard.json`, `cells.parquet`, `rain.npz`, `groundwater.npz` (if GLDAS was read) | gives the grid (`cell_m`, `bounds`, `lat0`), the labels (`rate_mm_yr`, `mode`, `n_points`), and the rain / groundwater drivers of the forecast |
| DEM | yes (susceptibility) | the project's `[stack] dem` (SRTM 1″ / Copernicus GLO-30), downloaded on demand | `<workspace>/cache/dem/` | a surface model: buildings are in it |
| ESA WorldCover 10 m 2021 v200 | automatic | read over HTTPS (`esa-worldcover.s3.eu-central-1.amazonaws.com`, 3° tiles) | not cached: read each time the layers are rebuilt | network needed on the first run |
| Overture Maps buildings | automatic | `geoeyes.ml.overture` | `<workspace>/cache/overture/` | heights are often missing (Hanoi: 1.4 %) |
| SoilGrids 2.0 clay 0–5 cm | automatic | `files.isric.org` VRT, 250 m | not cached | |
| Soft-soil thickness | optional | `[postprocess.geology]`: `raster` (GeoTIFF, m), `boreholes` (CSV `lon, lat, thickness_m`), else `open_fallback = true` (Pelletier et al. 2016) | paths relative to the project; cache `<workspace>/cache/geology/` | the open fallback needs `EARTHDATA_TOKEN`; see [decompose-and-soft-soil.md](decompose-and-soft-soil.md) |
| Parameters | optional | `[postprocess.susceptibility]`, `[postprocess.forecast]` in `project.toml`, or `--set KEY=VALUE` | TOML | unknown keys are rejected |

Checklist:

- [ ] The product exists and is the one you mean (`geoeyes status <project>`; otherwise pass `--product`).
- [ ] `geoeyes hazard` has run on that product (`analyses/hazard/<product_id>/hazard.json` exists).
- [ ] The hazard's `cell_m` is the cell you want for the susceptibility grid (it is reused as is).
- [ ] The rates span more than the noise: at least 20 labelled cells at or above `label_rate` and 20 below.
- [ ] For the forecast: the series span at least `min_history_days` + the longest horizon (more than ~6 months).
- [ ] Network access for WorldCover, SoilGrids and Overture on the first susceptibility run.

## 3. Method

### 3.1 Susceptibility (`geoeyes.ml.susceptibility`, `geoeyes.ml.layers`)

1. **Grid.** The hazard grid (`cell_m`, `lat0` from `hazard.json`), extended to every cell of the product's
   bounding rectangle, with or without InSAR points (`Grid`: cell index `kx = floor(lon · 111320 cos(lat0) / cell_m)`,
   `ky = floor(lat · 110540 / cell_m)`).
2. **Layers** (one column each; a layer that cannot be read is left NaN and named in `warnings`):
   `height_m`, `slope_deg` (DEM); `lc_built`, `lc_crop`, `lc_tree`, `lc_grass`, `lc_water`, `lc_bare`,
   `lc_wetland` (WorldCover fraction of the cell, classes 50, 40, 10, 30, 80, 60, 90); `dist_water_m` (mean
   Euclidean distance of the cell's 10 m pixels to class 80); `bld_count`, `bld_cover` (roof area / cell area,
   clipped to 1), `bld_height_m` (area-weighted, where known) from Overture; `soil_clay` (g/kg, nearest 250 m pixel);
   `rain_annual_mm` (mean annual total of the hazard's `rain.npz`); `soft_soil_m`. The table is cached as
   `layers.parquet` and reused while the grid and the soft-soil sources are unchanged.
3. **Labels.** Hazard cells with `n_points >= min_points` (default 3) and a finite rate, of mode `mode`
   (`subsidence` default, `landslide`, or `all`). A cell is *moving* (label 1) when `−rate_mm_yr >= label_rate`
   (default 5 mm/yr; GeoEyes sign, negative = sinking / downslope), else 0. Cells without InSAR get no label.
4. **Predictors.** Every layer except `exclude` (default `["rain_annual_mm"]`: a 5–25 km grid only encodes position
   inside a city) and except empty or constant columns.
5. **Guard.** Fewer than 20 moving or 20 stable cells stops the run with the P5–P95 of the rates and a suggested
   `label_rate` (the P90 of the sinking rate), flagged when it is below twice the median rate error.
6. **Models** (scikit-learn, `seed` = 0): `logistic` (median imputation, standardisation, `LogisticRegression`,
   `class_weight="balanced"`, C = 1); `random_forest` (300 trees, `min_samples_leaf=5`, `max_features="sqrt"`,
   `balanced_subsample`); `gradient_boosting` (`HistGradientBoostingClassifier`, 300 iterations, learning rate
   0.05, 31 leaves, `min_samples_leaf=30`, L2 = 1, balanced).
7. **Evaluation.** Spatial blocks of `block_m` (default 1000 m): `block = (floor(kx·cell_m/block_m),
   floor(ky·cell_m/block_m))`; `GroupKFold` with `min(folds, n_blocks)` folds (`folds` = 5; fewer than 2 blocks
   stops the run). Scores of the held-out predictions: ROC AUC, average precision, Brier. The same with a shuffled
   `StratifiedKFold` (random CV) to show how much spatial autocorrelation inflates a naive score (Brenning 2005).
   Permutation importance on each held-out spatial fold (loss of AUC, 5 repeats), weighted by fold size.
8. **Choice and map.** The model with the best spatial AUC is `chosen`. All three are refitted on every labelled
   cell and predict every grid cell (`p_logistic`, `p_random_forest`, `p_gradient_boosting`); `probability` =
   the chosen one; `class` 0–4 = very low … very high at limits 0.2 / 0.4 / 0.6 / 0.8. `outside` = true where any
   predictor lies outside the 1–99 % range of the labelled cells (extrapolation). Logistic odds ratio per standard
   deviation = `exp(coef)`.

### 3.2 Forecast (`geoeyes.ml.forecast`)

1. **Cells.** The product's points in square cells of `cell_m` (default 100 m, at least `min_points` = 3): median
   LOS series per cell, set to 0 at the first date (mm, + toward the satellite). These are the forecast's own cells,
   not the hazard's.
2. **Horizons.** `horizons_days`, or by default 1/6, 1/3 and 1/2 of the span, rounded to 10 days, each between 10
   and 365.
3. **Models.** `last`: no change. `linear`: least-squares line of the history up to the origin t0, extrapolated
   (needs 3 dates). `seasonal`: line + annual sine and cosine (needs 5 dates and 1.5 years of history). `gbm`: one
   global `HistGradientBoostingRegressor` (absolute-error loss, 300 iterations, learning rate 0.06, 31 leaves,
   `min_samples_leaf=40`, L2 = 1, early stopping on 15 %) for every cell and horizon, on the features `d30`, `d60`,
   `d90`, `d180`, `d365` (change over the last k days), `rate_90`, `rate_all`, `acc` (quadratic term), `noise`
   (residual std of the line), `doy_sin`, `doy_cos`, `h`, `rain_1`, `rain_3`, `rain_6` (AOI-mean rain anomaly of
   the last 1 / 3 / 6 months, from the hazard's `rain.npz`), `gws_anom`, `gws_d3`, `gws_d12` (GLDAS groundwater
   of the last month published before t0: anomaly, 3- and 12-month change), `span`. At most `max_samples` = 400 000
   training rows (random subsample).
4. **Rolling-origin backtest.** `last_cut = t_end − h_max`, `step = max(h_max/2, 10 d)`, cut-offs
   `last_cut − k·step` for k < `n_origins` (3), kept when at least `min_history_days` (90) after the first date.
   For each cut-off the GBM is trained only on origins and targets up to it (trained if ≥ 200 rows); every model
   predicts the change cut → cut + h for every cell; error = prediction − truth.
5. **Choice.** MAE per model and horizon; `base_best[h]` = the lowest baseline MAE; score = mean over horizons of
   MAE / `base_best`; the lowest score is `chosen`. Skill = 1 − MAE / `base_best` (0 for the best baseline).
6. **Intervals.** Split-conformal (Vovk et al. 2005): half-width = the ⌈(n+1)·level⌉/n quantile of the chosen model's
   absolute backtest errors, for levels 0.8 and 0.95. Coverage is checked on the latest cut-off with widths from the
   earlier ones (needs 2 cut-offs or more).
7. **Final forecast** from the last date: the chosen baseline, or the GBM retrained on every origin.

## 4. Steps

1. **Hazard first.** `geoeyes hazard <project> --product <product_id>` → `analyses/hazard/<product_id>/`
   ([hazard-zoning.md](hazard-zoning.md)).
2. **Susceptibility.** `geoeyes susceptibility <project> [--product <id>] [--set label_rate=5] [--set block_m=1000]
   [--set mode=subsidence]`. Without `--product`, the latest product of each track. Web app: Machine learning
   research → pick the product → tab Susceptibility → threshold and block size → Run (disabled until the hazard
   exists). Run time: not recorded; the first run downloads the layers, later runs print "layers: reused" and only
   fit the models (three models × five folds plus the random CV). Writes in
   `<project>/analyses/susceptibility/<product_id>/`: `layers.parquet`, `layers.json`, `grid.parquet`,
   `models.joblib`, `susceptibility.json`, `manifest.json`.
3. **Forecast.** `geoeyes forecast <project> [--product <id>] [--set horizons_days=[30,90,180]]
   [--set n_origins=3]`. Web app: same page, tab Forecast → Run. Writes in
   `<project>/analyses/forecast/<product_id>/`: `forecast.parquet`, `cells_ts.npy`, `forecast.json`,
   `model.joblib` (only when the GBM is chosen), `manifest.json`.
4. **Map.** In the web app, "View on the results map" adds the result as a theme; "Make a map" opens the map
   composer.

## 5. Outputs and how to read them

| File / field | Meaning |
|---|---|
| `susceptibility.json` `labels` | labelled cells, moving cells, share, the hazard's reference |
| `models.<name>.spatial_cv` / `random_cv` | `auc`, `ap`, `brier`; the spatial one is the honest score for new areas |
| `models.<name>.importance` | mean loss of AUC when the layer is permuted on held-out blocks |
| `chosen`, `odds_ratio_per_sd` | the model mapped; logistic odds ratio per one standard deviation of each layer |
| `outside_share`, `warnings` | share of grid cells in extrapolation; layers not read or without information |
| `grid.parquet` | per grid cell: `kx, ky, lon, lat`, the layers, `rate_mm_yr`, `label` (1 / 0 / NaN), `p_*`, `probability`, `class` (0–4), `outside` |
| `forecast.parquet` | per cell and horizon: `cell, lon, lat, horizon_days, change_mm, lo80, hi80, lo95, hi95` (LOS mm, + toward the satellite, change from the last date) |
| `forecast.json` `backtest` | `cuts_days`, `mae_mm`, `skill`, `coverage`, `interval_mm` per model and horizon |

Web-app maps: *probability* (predicted from the layers only, also where InSAR has no points; hatched = outside the
training range), *label* (what InSAR observed: red moving, green below the threshold, grey no points), *outside*,
each layer as a thematic map; for the forecast, the change per horizon and the series of a clicked cell.

Example (runs of 2026-10-25/26, Hanoi S1 descending track 91, product `..._20251001_20261015_v4`):
susceptibility on 27 680 cells of 100 m, 15 071 labelled, 1 606 moving at 5 mm/yr (10.7 %); spatial AUC 0.708
(logistic), 0.732 (random forest), 0.734 (gradient boosting, chosen) against random-CV AUC 0.726 / 0.778 / 0.780;
31 % of the grid outside the training range; top importances `lc_built` and `bld_count` (≈ 0.05 each). Forecast of
15 071 cells, horizons 60 / 130 / 190 days, two cut-offs only: `last` chosen; GBM skill −0.66 / −0.67 / −0.39,
linear −0.21 / −0.65 / −0.83; 80 % interval coverage 47 % / 87 % / 47 %. On Hanoi COSMO-SkyMed 2011–2014 `last`
was also chosen; on Mexico City S1 (6 months) `linear`.

## 6. Quality checks

- **Spatial vs random AUC.** Report the spatial one. A large gap means the model learns position, not process.
  Spatial AUC below ~0.7 is weak; 0.5 is no skill.
- **Labels above the noise.** `label_rate` must sit above twice the typical `rate_se_mm_yr` of the hazard cells;
  the error message gives both numbers when the labels are too few.
- **Block size.** Try `block_m` of 2 and 3 × the default: if the AUC drops sharply, the 1 km blocks still leak.
- **Importance and odds ratios agree in sign and rank** with what is known (soft soil, recent built-up). A layer
  with high importance but no physical link (e.g. distance to water as a proxy for a district) is a warning.
- **`outside_share`** and the hatched cells: do not read probabilities there.
- **Forecast: skill > 0 at every horizon** before using any non-baseline model; with `last` chosen, report "no
  model beats persistence". Check `coverage` against 0.8 / 0.95; under-coverage (e.g. 47 %) means the intervals are
  too narrow. Fewer than 2 cut-offs gives no coverage check at all.

## 7. Limits and pitfalls

- Susceptibility is an association; the layers miss pumping, loading history and construction age.
- The DEM is a surface model: in cities `height_m` and `slope_deg` include buildings.
- WorldCover is 2021 and Overture is today: layers may postdate the motion.
- The labels inherit the hazard's reference (scene mean, GNSS) and its projection (vertical or downslope).
- Short series (one year) give few cut-offs and noisy MAE; the seasonal baseline needs 1.5 years and stays empty
  otherwise. The forecast is LOS, not vertical.
- Conformal intervals assume exchangeable errors, which time series are not: hence the coverage check.
- The research notes cited in the code (`docs/en/research/ai-susceptibility.md`, `ai-forecasting.md`) do not exist
  yet; this skill and the code are the reference.

## 8. On a new area or sensor

- Run the hazard with a `cell_m` that suits the point density (100 m for Sentinel-1; smaller for X-band). The
  susceptibility grid follows it.
- Adjust `label_rate` to the rates and noise of the area; use `mode = "landslide"` (with the hazard's slope rule)
  for slopes, `all` to pool both.
- Give a local soft-soil raster or boreholes in `[postprocess.geology]` where they exist.
- On a short X-band stack, set `horizons_days` explicitly (e.g. `[30, 60]`) and `min_history_days` lower only if
  you accept a weaker backtest.
- Carries over unchanged: the layers (global), the models, the block CV, the conformal intervals.

## 9. References

- Code: `src/geoeyes/ml/susceptibility.py`, `src/geoeyes/ml/layers.py`, `src/geoeyes/ml/forecast.py`,
  `src/geoeyes/ml/__init__.py` (`run_susceptibility`, `run_forecast`), `src/geoeyes/hazard/assess.py`
  (`load_cells`, `read_cells`), `webapp/src/pages/Ai.tsx`.
- Guides and notes: [hazard-zoning.md](hazard-zoning.md), [decompose-and-soft-soil.md](decompose-and-soft-soil.md),
  [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md),
  [../research/groundwater-insar.md](../research/groundwater-insar.md) §4.2 (groundwater features).
- Brenning, A. (2005). Spatial prediction models for landslide hazards: review, comparison and evaluation. NHESS 5,
  853–862. https://doi.org/10.5194/nhess-5-853-2005
- Vovk, V., Gammerman, A., Shafer, G. (2005). *Algorithmic Learning in a Random World*. Springer.
- Zanaga, D., et al. (2022). ESA WorldCover 10 m 2021 v200. https://doi.org/10.5281/zenodo.7254221
- Poggio, L., et al. (2021). SoilGrids 2.0. SOIL 7, 217–240. https://doi.org/10.5194/soil-7-217-2021
- Pelletier, J. D., et al. (2016). A gridded global data set of soil, intact regolith, and sedimentary deposit
  thicknesses. JAMES 8, 41–65. https://doi.org/10.1002/2015MS000526
