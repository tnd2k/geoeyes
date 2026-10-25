# Rainfall and InSAR for subsidence and landslide hazard zoning

> Research note and method of `geoeyes hazard` (package `geoeyes.hazard`, web app page **Hazard**).
> Status: **v1 implemented 2026-10-25**, first results on the GeoEyes test projects (§7).
> Decision record: ADR-024 in [`docs/en/architecture/decisions.md`](../architecture/decisions.md).

## Contents

1. [Question and scope](#1-question-and-scope)
2. [Background: what the literature establishes](#2-background-what-the-literature-establishes)
3. [Hypotheses](#3-hypotheses)
4. [Method (v1, implemented)](#4-method-v1-implemented)
5. [Parameters and where each default comes from](#5-parameters-and-where-each-default-comes-from)
6. [Research sequence](#6-research-sequence)
7. [First results on the GeoEyes projects](#7-first-results-on-the-geoeyes-projects)
8. [Limitations](#8-limitations)
9. [Implementation](#9-implementation)
10. [References](#10-references)

---

## 1. Question and scope

**Question.** Can InSAR displacement time series, combined with rainfall, give a zoning of the ground-motion hazard
(subsidence and slow-moving landslides) that is (a) traceable to published practice, (b) explicit about what rain
adds to what InSAR alone shows, and (c) reproducible on every GeoEyes product?

**Scope of v1.**

- Inputs: one GeoEyes point product (PS/DS points, LOS displacement series, LOS unit vector), a DEM, and gridded
  rainfall (CHIRPS v3, ERA5 as fallback).
- Two processes: **subsidence** on flat ground and **slow-moving landslides** on slopes. Both are *slow* processes,
  the regime InSAR measures (mm/yr to a few dm/yr).
- Output: a **hazard level** (very low to very high) per analysis cell. This is a *hazard* map in the qualitative,
  matrix sense used with PSI (Cigna et al. 2013), not a probabilistic hazard in the sense of Fell et al. (2008):
  v1 gives no return period or probability of failure. It is also not a *risk* map. Exposure and vulnerability are
  outside v1 (§6, R6).

**Out of scope in v1** (listed in the research sequence): event-scale rainfall triggering of rapid landslides
(intensity–duration thresholds, nowcasting), statistical susceptibility models, 3-D decomposition from two
geometries, and calibration of the classes against damage or landslide inventories.

## 2. Background: what the literature establishes

### 2.1 Hazard, susceptibility, zoning

- Hazard zonation and its terminology go back to Varnes and the IAEG Commission (1984). Fell et al. (2008) set the
  JTC-1 guidelines that distinguish **susceptibility** (where), **hazard** (where, how often, how large) and
  **risk** (with exposure and vulnerability) for land-use planning.
- **PSI activity and intensity matrices.** Cigna, Bianchini & Casagli (2013) assess landslide activity and intensity
  from PSI. They project the LOS velocity on the slope (V_SLOPE = V_LOS / L2S). They compare it with two
  thresholds: V_ACT (moving or not) and V_INT, the Cruden & Varnes "extremely slow / very slow" boundary at
  16 mm/yr. In their Calabria case V_INT is reduced to 13 mm/yr to allow for averaging. They combine the result in
  matrices with the state recorded in the inventory.
  - Bianchini et al. (2012) use PSI to screen large areas for landslide "hotspots".
  - Ciampalini et al. (2016) refine a Random-Forest susceptibility map with PSInSAR velocities through a
    contingency matrix. **The design of v1 follows this line: InSAR intensity × a second factor, combined in an
    explicit matrix.**
- **Active deformation areas (ADA).** These works turn PSI maps into mapped units and classify them:
  - Barra et al. (2017) set the stability threshold at 2σ of the velocity map, need at least 1.5 years of data,
    and add a quality index.
  - Tomás et al. (2019) use k·σ with k = 1–2 and need at least 3 PS per ADA.
  - Navarro et al. (2020, ADAtools) classify ADAs with simple terrain rules. A potential landslide needs a slope
    ≥ 5°; potential subsidence needs a slope ≤ 10° on Quaternary deposits.
  - Solari et al. (2020) review more than 250 Italian applications.
- **Velocity scale.** Cruden & Varnes (1996), reproduced in Hungr et al. (2014): extremely slow < 16 mm/yr, very
  slow 16 mm/yr – 1.6 m/yr, slow up to 13 m/month. InSAR covers the first two classes.

### 2.2 Subsidence: rate, differential settlement and damage

- **Global hazard.** Herrera-García et al. (2021) map the global threat of land subsidence. They combine
  susceptibility factors (lithology, slope, land cover, climate) with the probability of groundwater depletion.
- **Damage from differential settlement.** Damage to buildings and networks follows *differential* settlement
  (angular distortion) more than the rate itself:
  - Skempton & MacDonald (1956) give 1/300 for the first cracking and 1/150 for structural damage.
  - Bjerrum (1963) gives 1/500 as a safe limit where no cracking is acceptable. These values are quoted here from
    secondary sources (§10).
  - Fernández-Torres et al. (2020, 2022) apply them to InSAR in Mexico City. They compute the subsidence horizontal
    gradient, convert it to angular distortion, and use 0.002 rad (1/500) as the damage threshold.
  - Cigna & Tapete (2021) map surface faulting hazard in Mexico City from Sentinel-1 gradients.
- **Groundwater and seasonal motion.** In aquifer systems the ground follows the hydraulic head: elastic seasonal
  uplift and subsidence follow recharge and pumping, and inelastic compaction follows long-term depletion.
  - Hoffmann et al. (2001) and Chaussard et al. (2014) show seasonal deformation in phase with head. Chaussard et
    al. (2014, 2017) predict heads from InSAR and use cross-correlation to relate deformation to water levels and
    drought.
  - Tomás et al. (2010), Ezquerro et al. (2014), Bonì et al. (2015) and Béjar-Pizarro et al. (2017) relate PSI
    subsidence to piezometric levels in Spain.
- **Hanoi.**
  - Dang et al. (2014), with ALOS 2007–2011, find subsidence of up to 68 mm/yr. Since 2008 they also find seasonal
    up / down transients linked to recharge in the rainy season and pumping in the dry season. This is a direct
    rainfall → aquifer → ground link for the city of the GeoEyes test projects.
  - Bui et al. (2021) relate Sentinel-1 deformation in 2016–2020 to falling heads.
  - Nguyen et al. (2022) and Bateson et al. (2023) add the long-term and construction-induced parts.
  - In the Mekong delta: Erban et al. (2014) and Minderhoud et al. (2017).
- **Rainfall as a recharge proxy.** The cumulative rainfall departure (CRD) method follows water-level change with
  the running sum of rainfall minus its mean (Bredenkamp et al. 1995; Xu & van Tonder 2001). GeoEyes uses it as
  the forcing term (§4.3).

### 2.3 Slow landslides and rainfall

- Lacroix, Handwerger & Bièvre (2020) review slow-moving landslides:
  - They move at mm/yr to m/yr, typically in clay-rich materials and with strong seasonal rainfall.
  - Their speed follows pore pressure. For example, the Maca landslide does 90% of its yearly motion in the 5-month
    wet season.
- Handwerger et al. (2013) observed, with InSAR, rainfall and lidar on ten landslides in California:
  - The landslides accelerate **with a delay** after the onset of the rains, within about 40 days.
  - They test pore-pressure diffusion, with a response time that scales with depth²/diffusivity.
- Later work extends this:
  - Handwerger et al. (2016, 2019) cover rate-weakening friction and the shift from drought to extreme rainfall
    that drove the Mud Creek failure.
  - Bennett et al. (2016) show drought slowing earthflows.
  - Bayer et al. (2018) find different seasonal responses by lithology in the Apennines with COSMO-SkyMed and
    Sentinel-1.
  - Hu et al. (2020) quantify hydro-meteorological forcing in 4-D.
- **Precursors.** Acceleration matters most:
  - Intrieri et al. (2018) detected the acceleration before the Maoxian failure in Sentinel-1 data.
  - The inverse-velocity method extrapolates 1/v to zero (Fukuzono 1985; Voight 1988, 1989).
- **Data gaps.** In steep monsoon terrain InSAR loses coherence in the wet season (Bekaert et al. 2020, Nepal).
- **Rainfall thresholds** for *triggering* rapid, shallow landslides are a separate, event-scale tool:
  - intensity–duration thresholds (Caine 1980; Guzzetti et al. 2008; review by Segoni et al. 2018);
  - antecedent rainfall models (Crozier 1999; Glade 2000);
  - global nowcasts (LHASA, Kirschbaum & Stanley 2018).
- **Vietnam.** Rainfall-triggered landslides in the northern mountains are well documented, e.g. Mu Cang Chai,
  August 2023. The only InSAR landslide monitoring found there is a conference study in Yen Bai (Tran et al. 2021).
  No peer-reviewed InSAR time-series study of slow landslides in northern Vietnam was found: this is a gap.

### 2.4 Statistics with thousands of series

- Correlating motion with rainfall is not trivial: both are serially correlated, and both have a seasonal cycle.
  - A naive correlation test overstates significance. Ebisuzaki (1997) builds the null distribution from
    phase-randomised surrogates, which keep the spectrum and randomise the timing.
- A map tests thousands of cells, so about 5% would pass p < 0.05 by chance alone. The false discovery rate (FDR)
  procedure handles this: Benjamini & Hochberg (1995), valid under positive dependence (Benjamini & Yekutieli
  2001). Wilks (2016) shows how routinely maps overstate significance without it.
- Permutation p-values cannot go below 1/(S+1) with S surrogates. With few exceedances, the tail of the null
  distribution can be approximated (Knijnenburg et al. 2009).
- **Confounders.** In a monsoon climate, rain and temperature peak together. Thermal dilation of structures also
  shows in InSAR series (Fornaro et al. 2013), so a rainfall correlation is not proof of a hydrological cause.

### 2.5 Rainfall data

- **CHIRPS** (Funk et al. 2015; v3: Funk et al. 2026): infrared and station rainfall at 0.05°, from 1981.
  - v3 has monthly COGs, and daily products disaggregated with IMERG or ERA5. Its readme recommends pentad or
    monthly totals over the daily values.
  - v2 is retired after December 2026.
- **ERA5** (Hersbach et al. 2020): 0.25° reanalysis, used through the Open-Meteo archive API (Zippenfenig 2024) as
  the fallback. A reanalysis smooths convective peaks. Over Hanoi in June 2011, ERA5 has 224 mm and CHIRPS 430 mm.
  The annual climate is close: P10 / P50 / P90 = 1442 / 1673 / 2162 mm for ERA5 against 1416 / 1633 / 2065 mm for
  CHIRPS.
- **GPM IMERG** (Huffman et al. 2020, 2023): 0.1° daily, the natural input for event-scale work (R5).

## 3. Hypotheses

- **H1 (rate).** The InSAR rate in the direction of the expected motion is the first indicator of hazard intensity:
  vertical for subsidence, downslope for landslides.
- **H2 (differential).** For subsidence, damage potential follows the angular distortion accumulated over a
  horizon. It depends only on rate *differences*, so it does not depend on the reference of the product.
- **H3 (rainfall coupling).** Where motion responds to rainfall, the detrended displacement follows the lagged
  cumulative rainfall departure: d(t) = a + b·t + k·CRD(t − τ).
  - For aquifer systems k < 0: rain gives uplift, i.e. less sinking.
  - For landslides k > 0: rain gives more downslope motion.
  - The lag τ reflects recharge or pore-pressure diffusion. The response k then allows a **scenario**: the rate in a
    dry (P10) or wet (P90) year.
- **H4 (escalation).** A significant, rain-coupled response or a significant acceleration in the hazard direction
  raises the hazard above what the mean rate shows.

H3 is tested, not assumed: it is accepted only where the surrogate test passes at the map-wide FDR.

## 4. Method (v1, implemented)

### 4.1 Analysis cells

- Points are reduced to square cells of `cell_m` metres (default 100 m) on a local metric grid.
- Each cell keeps the median LOS series, the median LOS unit vector and the median coherence of its points.
- A cell needs `min_points` points (default 3, as Tomás et al. 2019 for an ADA).
- Cells are the unit of the map. They make the series robust and the significance tests tractable, and they match
  the scale of the slope and gradient computations.

### 4.2 Terrain and mode

- **Slope.** The DEM of the project (`[stack].dem`: SRTM 1″, Copernicus GLO-30 or a file) is smoothed with a
  Gaussian of σ = half a cell. The slope is then taken over one cell.
- **Why smooth.** Surface models carry buildings and trees, so cities would otherwise show steep slopes at building
  edges. A bare-earth DEM (FABDEM, Hawker et al. 2022) is the better input where available.
- **Mode.** A cell is in `landslide` mode if its slope ≥ `landslide_min_slope_deg` (default 10°), else in
  `subsidence` mode.
  - ADAtools uses ≥ 5° for potential landslides and ≤ 10° for subsidence. v1 takes the upper bound so that dikes and
    urban DSM artefacts stay in subsidence mode.
  - Hanoi's smoothed slopes have a 99th percentile of 4.3°.

### 4.3 Motion in the hazard direction and rainfall coupling

**Projection.** Let **l** be the LOS unit vector from the ground to the satellite, and d_LOS the LOS displacement
(positive toward the satellite).

- **Subsidence cells:** y = −d_LOS / l_u (vertical motion assumed, sinking positive).
- **Landslide cells:** y = d_LOS / (**s**·**l**). **s** is the unit vector of steepest descent, so downslope is
  positive. This is the L2S projection of Cigna et al. (2013).
  - Cells with |**s**·**l**| < `min_sensitivity` (0.3) are not assessed. There the line of sight sees less than 30%
    of a downslope motion, and the projection would amplify noise more than three times.

**Rate and stability.** A linear fit gives the rate (mm/yr) and its standard error σ. A quadratic fit gives the
acceleration. A cell is stable (I0) when its rate is below max(2 mm/yr, 2σ), as in:

- Barra et al. (2017): 2σ;
- Cigna et al. (2013): ±2 mm/yr band.

**Reference.** Intensities need rates relative to stable ground.

- Products referenced to a point keep it.
- Products referenced to the *scene mean* get a warning, because their rates are relative.
- `reference_bbox` re-references the series to the median of the cells over a known stable area.
- Motion against the hazard direction (rate < −threshold) is **flagged** (`opposite_motion`), not rated.

**Rainfall.**

- **Monthly data.** Monthly rainfall comes from the cell's CHIRPS pixel, from `max_lag_months` before the first
  acquisition to the last one.
- **Annual totals.** Annual totals over the WMO normal 1991–2020 give the dry-year (P10) and wet-year (P90)
  rainfall of each pixel.
- **Fallback.** If CHIRPS cannot be read, ERA5 is used, and the summary says so.
- **CRD.** CRD(t) = Σ(P_month − P̄), where P̄ is the mean over the analysis window. It is linear within a month.
  Missing months count as P̄; a pixel with more than 20% missing is not assessed.

**Coupling model.** The model, per cell, is

    y(t) = a + b·t + k·CRD(t − τ) + ε,       τ ∈ {0, 1, …, max_lag_months}

If the rate anomaly follows the lagged rainfall anomaly, v(t) − b = k·(P(t − τ) − P̄), then its integral is exactly
this model. One form therefore serves aquifer heads (Bredenkamp; Xu & van Tonder) and landslide velocity
(Handwerger et al. 2013).

- **b** is the trend corrected for rainfall.
- **k** is the sensitivity, in mm of displacement per mm of rainfall departure (reported per 100 mm).
- **τ** is chosen by the largest |partial correlation| of y and CRD(t − τ) given [1, t].

**Significance.**

1. The lag search is repeated on `n_surrogates` (500) phase-randomised copies of the monthly rainfall anomaly
   (Ebisuzaki 1997). Each surrogate keeps the spectrum and has a random timing.
2. p is the share of surrogates whose best |r| reaches the observed |r|. Because the lag is chosen again in every
   surrogate, the test already includes the choice of the lag.
3. When fewer than 10 surrogates reach it, p comes from a normal fit to the Fisher z of the null maximum
   (after Knijnenburg et al. 2009). Without this tail, p could not go below 1/501, and a map-wide FDR could never
   reach a small coupled area. The unit test `test_assess_end_to_end` shows this case.
4. A cell is **coupled** when its Benjamini–Hochberg q ≤ `alpha` (0.05) over all tested cells.

**Requirements.** Coupling needs at least `min_span_months` (12) and `min_epochs` (12): at least one seasonal cycle.

**Rainfall scenario.** In coupled cells:

    rate_dry = b + k·(P10_annual − 12·P̄)
    rate_wet = b + k·(P90_annual − 12·P̄)

This is the rate of a dry or wet year according to the fitted response. Extrapolating a linear response to extreme
years is a first-order assumption (§8).

### 4.4 Classes

**Intensity I.** The rate is taken in the hazard direction. Where the coupling is significant, the worse of the
observed, dry-year and wet-year rates is used.

| Class | Subsidence (vertical, mm/yr) | Landslide (downslope, mm/yr) |
|---|---|---|
| I0 | < max(2, 2σ) or opposite motion | < max(2, 2σ) or opposite motion |
| I1 | stability … 10 | stability … 16 (extremely slow, Cruden & Varnes) |
| I2 | 10 … 30 | 16 … 160 (lower very slow) |
| I3 | ≥ 30 | ≥ 160 (upper very slow, near the InSAR limit) |

A significant acceleration in the hazard direction raises I by one class (Intrieri et al. 2018). Significant means
|acceleration / its error| ≥ 3 over at least 18 months.

**Secondary class S.**

- **Subsidence: angular distortion.** β = max over the 8 neighbouring cells of |v_i − v_j| · T / L, with
  T = `horizon_yr` (10 years) and L the distance between cell centres. The classes follow the damage limits:

| Class | β | Meaning |
|---|---|---|
| S0 | < 1/500 | below Bjerrum's safe limit |
| S1 | 1/500 … 1/300 | beyond the safe limit (Fernández-Torres et al. 2020: 0.002 rad) |
| S2 | 1/300 … 1/150 | first cracking (Skempton & MacDonald) |
| S3 | ≥ 1/150 | structural damage (Skempton & MacDonald) |

- **Landslide: susceptibility.** The classes 0–3 come from the user's raster (`susceptibility`) if given. Otherwise
  slope classes 15° / 25° / 35° are a placeholder until a real susceptibility model exists (R4).

### 4.5 Hazard matrix

The default hazard matrix (an expert choice, configurable as `matrix`) gives the level for each pair of intensity
and secondary class:

| | S0 | S1 | S2 | S3 |
|---|---|---|---|---|
| **I3** | high | high | very high | very high |
| **I2** | moderate | moderate | high | very high |
| **I1** | low | low | moderate | high |
| **I0** | very low | very low | low | low |

- The InSAR intensity dominates the level.
- The secondary factor raises it at the high end, as in the PSI-based matrices of Cigna et al. (2013) and
  Ciampalini et al. (2016).
- A stable cell on a steep slope or in a high-distortion zone stays "low", not "very low": this is the *potential*
  signal of Ciampalini et al.

### 4.6 Outputs

The outputs go to `<project>/analyses/hazard/<product_id>/`:

- `cells.parquet`: one row per cell, with every intermediate value (rate, σ, stability threshold, acceleration,
  lag, r, p, q, k, rain-corrected trend, dry / wet-year rates, I observed and final, β, S, level, flags);
- `cells_ts.npy`: the series in the motion direction;
- `rain.npz`: monthly and annual grids;
- `hazard.json`: parameters, summary, sources and warnings;
- `hazard.gpkg`: cell squares for QGIS;
- `manifest.json`: with the product as input.

Products stay immutable; an analysis can be re-run with other parameters.

## 5. Parameters and where each default comes from

All parameters are under `[postprocess.hazard]` of `project.toml`, are overridable with `geoeyes hazard --set
key=value`, and can be changed in the web app.

| Key | Default | Source / reason |
|---|---|---|
| `cell_m` | 100 | Analysis scale. It must stay above the DSM building scale, and it is the L of the angular distortion |
| `min_points` | 3 | Tomás et al. 2019 (≥ 3 PS per ADA); Cigna et al. 2013 (3–5 PS per landslide) |
| `stable_floor_mm_yr`, `stable_sigma` | 2, 2 | Cigna et al. 2013 (±2 mm/yr band); Barra et al. 2017 (2σ) |
| `subsidence_breaks` | 10, 30 | **Local choice, to be calibrated (R3).** 30 mm/yr is 0.3 m over the 10-year horizon |
| `landslide_breaks` | 16, 160 | Cruden & Varnes 1996: 16 mm/yr; very slow split at its logarithmic midpoint |
| `distortion_breaks` | 1/500, 1/300, 1/150 | Bjerrum 1963; Skempton & MacDonald 1956; Fernández-Torres et al. 2020 |
| `horizon_yr` | 10 | Planning horizon. With `horizon_yr = 1`, β is the annual horizontal gradient |
| `landslide_min_slope_deg` | 10 | ADAtools rules (landslide ≥ 5°, subsidence ≤ 10°), upper bound |
| `min_sensitivity` | 0.3 | L2S projection (Cigna et al. 2013); caps noise amplification at 3.3 |
| `slope_breaks` | 15, 25, 35 | **Placeholder.** Replace with a susceptibility raster (R4) |
| `max_lag_months` | 6 | Lags of weeks to months (Handwerger et al. 2013; Dang et al. 2014 seasonal transients) |
| `n_surrogates`, `alpha`, `fdr` | 500, 0.05, true | Ebisuzaki 1997; Benjamini & Hochberg 1995; Wilks 2016 |
| `min_span_months`, `min_epochs` | 12, 12 | One seasonal cycle at least. Barra et al. (2017) ask 1.5 years for ADAs |
| `accel_t`, `accel_min_span_months` | 3, 18 | Conservative significance of a quadratic term over at least 1.5 years |
| `climate_years` | 1991, 2020 | WMO standard normal |
| `rain_source` | auto | CHIRPS (gauge-blended, 0.05°); ERA5 if CHIRPS cannot be read |
| `reference_bbox` | none | Stable ground for intensities (§4.3) |
| `gnss_tie` | false | Add the GNSS calibration of the product ([gnss-insar-calibration.md](gnss-insar-calibration.md)) |
| `matrix` | §4.5 | Expert matrix in the style of Cigna et al. 2013 |

## 6. Research sequence

The work is planned in seven steps, R0 to R6. Each step lists its question, inputs, method, output and acceptance
criterion. v1 covers R0 and R1, and the computational part of R2, as an operational screening tool. The other
steps are needed before the map can support decisions.

### R0 — Data audit and reference *(done in v1, per run)*

- **Question:** is the product fit for a hazard reading?
- **Method:**
  - check the span (≥ 12 months for coupling, ≥ 18 for acceleration), the number of epochs and the cell coverage;
  - check the reference: a point, the scene mean, or a stable area;
  - check the availability of rainfall and its source.
- **Output:** the warnings in `hazard.json`.
- **Criterion:** no intensity map is read without stable-ground referencing.
- **Added 2026-10-25:** GNSS ties (`gnss_tie`, [gnss-insar-calibration.md](gnss-insar-calibration.md)).
- **To add:** a check of the reference area against the geology.

### R1 — Rainfall–deformation diagnostics *(done in v1)*

- **Question:** where, and with what lag and sign, does motion follow rainfall?
- **Method:** the CRD model with the surrogate test and the FDR (§4.3), cell by cell, and per mode.
- **Output:**
  - maps of r, τ and k; the coupled share;
  - the dry / wet-year rates.
- **Criterion:**
  - the method recovers a planted response with the right lag and k (unit tests: ≥ 95% of the planted cells, no
    more than 5% false alarms on noise);
  - on real data, the raw share of p < α must exceed α before the coupled cells are interpreted.

### R2 — Attribution: rainfall, groundwater, temperature

- **Question:** is the coupling hydrological?
- **Method:**
  - add ERA5 2 m temperature as a second regressor, d = a + b·t + k·CRD(t − τ) + c·T(t), to separate thermal
    dilation (Fornaro et al. 2013);
  - compare with piezometric records where they exist (Hanoi: Bui et al. 2021; Spain: Béjar-Pizarro et al. 2017);
  - compare ascending and descending products to separate vertical and horizontal motion.
- **Output:** for each coupled area, the part explained by rainfall, by temperature and by heads.
- **Criterion:** the rainfall coefficient stays significant with temperature in the model.

### R3 — Calibration of the classes

- **Question:** do the class limits separate damaged from undamaged ground?
- **Method:**
  - build an inventory: building cracks and damage reports, road or pipe repairs, mapped landslides with their
    state;
  - choose the intensity limits and the matrix that best separate the inventory, with ROC curves and AUC per class
    limit, on half of the area; test on the other half.
- **Output:** local `subsidence_breaks`, `landslide_breaks` and `matrix`, with their AUC.
- **Criterion:** AUC on the test half ≥ 0.7, and a stable ranking between the halves.

### R4 — Susceptibility model for landslides

- **Question:** where would landslides occur, with or without current motion?
- **Method:**
  - statistical or machine-learning susceptibility (review: Reichenbach et al. 2018), using slope, curvature,
    lithology, land cover, distance to roads and rivers, and an inventory;
  - its classes 0–3 replace the slope proxy through `susceptibility`;
  - refinement with InSAR as in Ciampalini et al. (2016).
- **Output:** a susceptibility raster, and the refined matrix.
- **Criterion:** the success and prediction rates of the model on held-out landslides.

### R5 — Event-scale triggering and early warning

- **Question:** when is a landslide likely to be triggered?
- **Method:**
  - daily rainfall (CHIRPS v3 daily or IMERG) with intensity–duration or antecedent thresholds (Caine 1980;
    Guzzetti et al. 2008; Segoni et al. 2018; Glade 2000), calibrated on Vietnamese events (e.g. Mu Cang Chai,
    2023);
  - combined with susceptibility in a LHASA-like nowcast (Kirschbaum & Stanley 2018);
  - for accelerating InSAR cells, the inverse-velocity check (Fukuzono 1985; Voight 1989; Intrieri et al. 2018);
  - connected to the alerts of the web app.
- **Output:** alerts per area and time.
- **Criterion:** probability of detection and false alarm ratio on past events.

### R6 — From hazard to risk

- **Question:** what is exposed?
- **Method:**
  - cross the hazard with buildings, networks and population: risk = hazard × exposure × vulnerability (Fell et al.
    2008);
  - see Fernández-Torres et al. (2020, 2022) for the subsidence-risk index of Mexico City.
- **Output:** risk zoning at planning scale.

## 7. First results on the GeoEyes projects

The four products were run with the defaults on 2026-10-25, with 100 m cells and products referenced as they are.
CHIRPS was read for Hanoi CSK. For the other three products the CHIRPS server refused requests (throttling), so
ERA5 was used and the summary says so.

| Product | Period | Epochs | Cells | Coupling tested · p < 0.05 raw · significant (FDR) | β ≥ 1/500 | Hazard (km²) |
|---|---|---|---|---|---|---|
| Hanoi CSK asc v3 | 2011-07 → 2014-12 (41 mo) | 18 | 6 362 | 6 362 · 233 (3.7%) · **0** | 0 | very low 58.2, low 5.5 |
| Hanoi S1 desc 091 v4 | 2025-10 → 2026-10 (12.5 mo) | 26 | 15 071 | 15 071 · 251 (1.7%) · **0** | 0 | very low 136.1, low 11.6, moderate 3.0 |
| Mexico S1 asc 078 v6 | 2024-05 → 2024-10 (6 mo) | 16 | 44 750 | not assessed (< 12 months) | 9 314 | subsidence high 113.9, very high 10.7 |
| Mexico Capella asc v4 | 2024-06 → 2024-08 (1.6 mo) | 18 | 1 735 | not assessed | 1 132 | subsidence high 1.9, very high 1.9 |

**Reading.**

- **Hanoi, no rainfall coupling.** No rainfall coupling is detectable in either Hanoi product: the raw share of
  p < 0.05 is *below* 5%, as expected under the null.
  - The CSK sampling (18 irregular epochs, about 3 per wet season) and a single S1 year are thin for a seasonal
    signal.
  - Both products are referenced to the scene mean. Dang et al. (2014) found the seasonal transients in the
    subsiding outskirts (Hoang Mai, Ha Dong, Hoai Duc); the CSK AOI is the city centre.
  - **This is a negative result, not a failure.** R1 needs a longer S1 series over the outskirts, referenced to
    stable ground.
- **Mexico City, the reference.** The differential settlement exceeds Bjerrum's 1/500 over the 10-year horizon in
  9 314 S1 cells (93 km²), and 1/150 (structural damage) in 122 cells.
  - Both Mexico products are relative: S1 to the scene mean, Capella to a point in the subsiding area. As a result
    19 087 S1 cells appear to move *up*.
  - This is why intensity is directional, and why the run warns. Re-run with a `reference_bbox` on stable volcanic
    rock before reading the intensities. β does not depend on the reference.
- **Mexico S1, landslide cells.** The 912 cells in landslide mode on the volcanic hills of the S1 scene come from a
  single geometry, so vertical subsidence on slopes can be read as downslope motion (§8).

## 8. Limitations

1. **One geometry.** The motion is assumed vertical (subsidence) or downslope (landslide). Horizontal motion in
   subsidence bowls, or subsidence on slopes, is misattributed. An ascending and descending decomposition (R2)
   removes this.
2. **Reference.** Intensity classes are only as good as the stable-ground reference (§4.3, §7).
3. **Linear response.** The rainfall scenario extrapolates a linear k to dry and wet years. Landslide response is
   non-linear: thresholds, rate-weakening and runaway failure (Handwerger et al. 2016, 2019). Aquifer response
   also depends on pumping, which rainfall does not capture.
4. **Correlation is not cause.** Rain and temperature co-vary in monsoon climates (R2).
5. **Coarse rainfall.** CHIRPS has 0.05° pixels (about 5.5 km); ERA5 has 0.25° and smooths convective peaks. The
   coupling is per rainfall pixel, not per slope.
6. **Coherence gaps.** Wet-season decorrelation biases sampling on vegetated slopes (Bekaert et al. 2020). The cells
   that remain may be the stable ones.
7. **Uncalibrated limits.** The subsidence intensity limits, the slope placeholder and the matrix are expert
   choices until R3 and R4.
8. **DSM.** SRTM and GLO-30 include buildings. The smoothing reduces artefacts but does not remove them (use
   FABDEM).
9. **Not a probability.** The levels are qualitative hazard classes, not annual probabilities (Fell et al. 2008).

## 9. Implementation

| Part | Where |
|---|---|
| Rainfall grids (CHIRPS monthly and annual per pixel, ERA5 fallback, cache, polite reading) | `src/geoeyes/ancillary/rainfall.py` |
| CRD, coupling model, surrogates, tail p-value, FDR, linear and quadratic fits | `src/geoeyes/hazard/coupling.py` |
| Slope and downslope vector from the smoothed DEM; susceptibility raster | `src/geoeyes/hazard/terrain.py` |
| Classes, angular distortion, matrix | `src/geoeyes/hazard/zoning.py` |
| Orchestration, parameters, outputs | `src/geoeyes/hazard/assess.py` |
| CLI `geoeyes hazard <project> [--product ID] [--set key=value]` | `src/geoeyes/cli/main.py` |
| API `/api/projects/{p}/products/{id}/hazard[...]` | `src/geoeyes/api/hazard.py` |
| Web page **Hazard** (map, views, legend and matrix, cell panel, method) | `webapp/src/pages/Hazard.tsx` |
| Tests (planted-response recovery, surrogates, FDR, classes, end to end, re-referencing) | `tests/unit/hazard/test_hazard.py` |

**CHIRPS access.** The Climate Hazards Center server throttles clients that read many files at once: its
`robots.txt` sets a 10 s crawl delay. GeoEyes therefore reads one file at a time, caches every published period for
good (`<workspace>/cache/rainfall/chirps3_*.npz`), and stops at the first refusal. A run blocked by the server falls
back to ERA5 and says so.

Example configuration:

```toml
[postprocess.hazard]
cell_m = 100
horizon_yr = 10
reference_bbox = [105.770, 21.010, 105.780, 21.020]   # stable ground (example)
susceptibility = "D:/data/landslide_susceptibility_classes.tif"   # optional, classes 0..3
```

## 10. References

Each DOI below was checked on Crossref or DataCite in October 2026. Entries marked † are cited from library
catalogues or secondary sources: their numbers come from the papers that quote them, not from the original.

**Hazard frameworks and PSI methods**

- Barra A, Solari L, Béjar-Pizarro M, Monserrat O, Bianchini S, Herrera G, Crosetto M, Sarro R, et al. (2017) A methodology to detect and update active deformation areas based on Sentinel-1 SAR images. *Remote Sensing* 9(10):1002. https://doi.org/10.3390/rs9101002
- Bianchini S, Cigna F, Righini G, Proietti C, Casagli N (2012) Landslide HotSpot Mapping by means of Persistent Scatterer Interferometry. *Environmental Earth Sciences* 67(4):1155–1172. https://doi.org/10.1007/s12665-012-1559-5
- Ciampalini A, Raspini F, Lagomarsino D, Catani F, Casagli N (2016) Landslide susceptibility map refinement using PSInSAR data. *Remote Sensing of Environment* 184:302–315. https://doi.org/10.1016/j.rse.2016.07.018
- Cigna F, Bianchini S, Casagli N (2013) How to assess landslide activity and intensity with Persistent Scatterer Interferometry (PSI): the PSI-based matrix approach. *Landslides* 10(3):267–283. https://doi.org/10.1007/s10346-012-0335-7
- Cruden DM, Varnes DJ (1996) Landslide types and processes. In: Turner AK, Schuster RL (eds) *Landslides: Investigation and Mitigation*, TRB Special Report 247, 36–75. †
- Fell R, Corominas J, Bonnard C, Cascini L, Leroi E, Savage WZ (2008) Guidelines for landslide susceptibility, hazard and risk zoning for land use planning. *Engineering Geology* 102(3–4):85–98. https://doi.org/10.1016/j.enggeo.2008.03.022
- Hungr O, Leroueil S, Picarelli L (2014) The Varnes classification of landslide types, an update. *Landslides* 11(2):167–194. https://doi.org/10.1007/s10346-013-0436-y
- Navarro JA, Tomás R, Barra A, Pagán JI, Reyes-Carmona C, Solari L, Vinielles JL, Falco S, et al. (2020) ADAtools: Automatic detection and classification of active deformation areas from PSI displacement maps. *ISPRS Int. J. Geo-Information* 9(10):584. https://doi.org/10.3390/ijgi9100584
- Notti D, Herrera G, Bianchini S, Meisina C, García-Davalillo JC, Zucca F (2014) A methodology for improving landslide PSI data analysis. *Int. J. Remote Sensing* 35(6):2186–2214. https://doi.org/10.1080/01431161.2014.889864
- Reichenbach P, Rossi M, Malamud BD, Mihir M, Guzzetti F (2018) A review of statistically-based landslide susceptibility models. *Earth-Science Reviews* 180:60–91. https://doi.org/10.1016/j.earscirev.2018.03.001
- Solari L, Del Soldato M, Raspini F, Barra A, Bianchini S, Confuorto P, Casagli N, Crosetto M (2020) Review of satellite interferometry for landslide detection in Italy. *Remote Sensing* 12(8):1351. https://doi.org/10.3390/rs12081351
- Tomás R, Pagán JI, Navarro JA, Cano M, Pastor JL, Riquelme A, Cuevas-González M, Crosetto M, et al. (2019) Semi-automatic identification and pre-screening of geological–geotechnical deformational processes using persistent scatterer interferometry datasets. *Remote Sensing* 11(14):1675. https://doi.org/10.3390/rs11141675
- Varnes DJ, IAEG Commission on Landslides (1984) *Landslide hazard zonation: a review of principles and practice.* UNESCO, Natural Hazards 3. †

**Subsidence, damage and groundwater**

- Bateson L, Novellino A, Hussain E, Arnhardt R, Nguyen HK, et al. (2023) Urban development induced subsidence in deltaic environments: a case study in Hanoi, Vietnam. *Int. J. Applied Earth Observation and Geoinformation* 125:103585. https://doi.org/10.1016/j.jag.2023.103585
- Béjar-Pizarro M, Ezquerro P, Herrera G, Tomás R, Guardiola-Albert C, et al. (2017) Mapping groundwater level and aquifer storage variations from InSAR measurements in the Madrid aquifer, Central Spain. *Journal of Hydrology* 547:678–689. https://doi.org/10.1016/j.jhydrol.2017.02.011
- Bjerrum L (1963) Allowable settlement of structures. *Proc. European Conf. on Soil Mechanics and Foundation Engineering*, Wiesbaden, vol. 2. †
- Bonì R, Herrera G, Meisina C, et al. (2015) Twenty-year advanced DInSAR analysis of severe land subsidence: the Alto Guadalentín Basin (Spain) case study. *Engineering Geology* 198:40–52. https://doi.org/10.1016/j.enggeo.2015.08.014
- Bredenkamp DB, Botha LJ, van Tonder GJ (1995) *Manual on quantitative estimation of groundwater recharge and aquifer storativity.* Water Research Commission TT 73/95, Pretoria. †
- Bui LK, Le PV, Dao PD, Long NQ, Pham HV, Tran HH, Xie L (2021) Recent land deformation detected by Sentinel-1A InSAR data (2016–2020) over Hanoi, Vietnam, and the relationship with groundwater level change. *GIScience & Remote Sensing* 58(2):161–179. https://doi.org/10.1080/15481603.2020.1868198
- Chaussard E, Bürgmann R, Shirzaei M, Fielding EJ, Baker B (2014) Predictability of hydraulic head changes and characterization of aquifer-system and fault properties from InSAR-derived ground deformation. *J. Geophys. Res. Solid Earth* 119(8):6572–6590. https://doi.org/10.1002/2014JB011266
- Chaussard E, Milillo P, Bürgmann R, Perissin D, Fielding EJ, Baker B (2017) Remote sensing of ground deformation for monitoring groundwater management practices: application to the Santa Clara Valley during the 2012–2015 California drought. *J. Geophys. Res. Solid Earth* 122(10):8566–8582. https://doi.org/10.1002/2017JB014676
- Cigna F, Tapete D (2021) Present-day land subsidence rates, surface faulting hazard and risk in Mexico City with 2014–2020 Sentinel-1 IW InSAR. *Remote Sensing of Environment* 253:112161. https://doi.org/10.1016/j.rse.2020.112161
- Dang VK, Doubre C, Weber C, Gourmelen N, Masson F (2014) Recent land subsidence caused by the rapid urban development in the Hanoi region (Vietnam) using ALOS InSAR data. *Natural Hazards and Earth System Sciences* 14(3):657–674. https://doi.org/10.5194/nhess-14-657-2014
- Erban LE, Gorelick SM, Zebker HA (2014) Groundwater extraction, land subsidence, and sea-level rise in the Mekong Delta, Vietnam. *Environmental Research Letters* 9(8):084010. https://doi.org/10.1088/1748-9326/9/8/084010
- Ezquerro P, Herrera G, Marchamalo M, Tomás R, Béjar-Pizarro M, Martínez R (2014) A quasi-elastic aquifer deformational behavior: Madrid aquifer case study. *Journal of Hydrology* 519:1192–1204. https://doi.org/10.1016/j.jhydrol.2014.08.040
- Fernández-Torres E, Cabral-Cano E, Solano-Rojas D, Havazli E, Salazar-Tlaczani L (2020) Land subsidence risk maps and InSAR based angular distortion structural vulnerability assessment: an example in Mexico City. *Proc. IAHS* 382:583–587. https://doi.org/10.5194/piahs-382-583-2020
- Fernández-Torres E, Cabral-Cano E, Novelo-Casanova DA, Solano-Rojas D, Havazli E, Salazar-Tlaczani L (2022) Risk assessment of land subsidence and associated faulting in Mexico City using InSAR. *Natural Hazards* 112(1):37–55. https://doi.org/10.1007/s11069-021-05171-0
- Herrera-García G, Ezquerro P, Tomás R, Béjar-Pizarro M, López-Vinielles J, Rossi M, Mateos RM, Carreón-Freyre D, et al. (2021) Mapping the global threat of land subsidence. *Science* 371(6524):34–36. https://doi.org/10.1126/science.abb8549
- Hoffmann J, Zebker HA, Galloway DL, Amelung F (2001) Seasonal subsidence and rebound in Las Vegas Valley, Nevada, observed by synthetic aperture radar interferometry. *Water Resources Research* 37(6):1551–1566. https://doi.org/10.1029/2000WR900404
- Minderhoud PSJ, Erkens G, Pham VH, Bui VT, Erban L, Kooi H, Stouthamer E (2017) Impacts of 25 years of groundwater extraction on subsidence in the Mekong delta, Vietnam. *Environmental Research Letters* 12:064006. https://doi.org/10.1088/1748-9326/aa7146
- Nguyen M, Lin Y-N, Tran QC, Ni C-F, Chan Y-C, Tseng K-H, Chang C-P (2022) Assessment of long-term ground subsidence and groundwater depletion in Hanoi, Vietnam. *Engineering Geology* 299:106555. https://doi.org/10.1016/j.enggeo.2022.106555
- Skempton AW, MacDonald DH (1956) The allowable settlements of buildings. *Proc. Institution of Civil Engineers* 5(6):727–768. https://doi.org/10.1680/ipeds.1956.12202
- Tomás R, Herrera G, Lopez-Sanchez JM, Vicente F, Cuenca A, Mallorquí JJ (2010) Study of the land subsidence in Orihuela City (SE Spain) using PSI data: distribution, evolution and correlation with conditioning and triggering factors. *Engineering Geology* 115(1–2):105–121. https://doi.org/10.1016/j.enggeo.2010.06.004
- Xu Y, van Tonder GJ (2001) Estimation of recharge using a revised CRD method. *Water SA* 27(3):341–343. https://doi.org/10.4314/wsa.v27i3.4977

**Slow landslides, rainfall and failure forecasting**

- Bayer B, Simoni A, Mulas M, Corsini A, Schmidt D (2018) Deformation responses of slow moving landslides to seasonal rainfall in the Northern Apennines, measured by InSAR. *Geomorphology* 308:293–306. https://doi.org/10.1016/j.geomorph.2018.02.020
- Bekaert DPS, Handwerger AL, Agram P, Kirschbaum DB (2020) InSAR-based detection method for mapping and monitoring slow-moving landslides in remote regions with steep and mountainous terrain: an application to Nepal. *Remote Sensing of Environment* 249:111983. https://doi.org/10.1016/j.rse.2020.111983
- Bennett GL, Roering JJ, Mackey BH, Handwerger AL, Schmidt DA, Guillod BP (2016) Historic drought puts the brakes on earthflows in Northern California. *Geophysical Research Letters* 43(11):5725–5731. https://doi.org/10.1002/2016GL068378
- Caine N (1980) The rainfall intensity–duration control of shallow landslides and debris flows. *Geografiska Annaler A* 62(1–2):23–27. https://doi.org/10.1080/04353676.1980.11879996
- Crozier MJ (1999) Prediction of rainfall-triggered landslides: a test of the Antecedent Water Status Model. *Earth Surface Processes and Landforms* 24(9):825–833. https://doi.org/10.1002/(SICI)1096-9837(199908)24:9<825::AID-ESP14>3.0.CO;2-M
- Fukuzono T (1985) A method to predict the time of slope failure caused by rainfall using the inverse number of velocity of surface displacement. *J. Japan Landslide Society* 22(2):8–13. https://doi.org/10.3313/jls1964.22.2_8
- Glade T (2000) Applying probability determination to refine landslide-triggering rainfall thresholds using an empirical "Antecedent Daily Rainfall Model". *Pure and Applied Geophysics* 157(6–8):1059–1079. https://doi.org/10.1007/s000240050017 (Crossref lists Glade alone; often cited with Crozier & Smith)
- Guzzetti F, Peruccacci S, Rossi M, Stark CP (2008) The rainfall intensity–duration control of shallow landslides and debris flows: an update. *Landslides* 5(1):3–17. https://doi.org/10.1007/s10346-007-0112-1
- Handwerger AL, Roering JJ, Schmidt DA (2013) Controls on the seasonal deformation of slow-moving landslides. *Earth and Planetary Science Letters* 377–378:239–247. https://doi.org/10.1016/j.epsl.2013.06.047
- Handwerger AL, Rempel AW, Skarbek RM, Roering JJ, Hilley GE (2016) Rate-weakening friction characterizes both slow sliding and catastrophic failure of landslides. *PNAS* 113(37):10281–10286. https://doi.org/10.1073/pnas.1607009113
- Handwerger AL, Huang M-H, Fielding EJ, Booth AM, Bürgmann R (2019) A shift from drought to extreme rainfall drives a stable landslide to catastrophic failure. *Scientific Reports* 9:1569. https://doi.org/10.1038/s41598-018-38300-0
- Hu X, Bürgmann R, Schulz WH, Fielding EJ (2020) Four-dimensional surface motions of the Slumgullion landslide and quantification of hydrometeorological forcing. *Nature Communications* 11:2792. https://doi.org/10.1038/s41467-020-16617-7
- Intrieri E, Raspini F, Fumagalli A, Lu P, Del Conte S, Farina P, Allievi J, Ferretti A, Casagli N (2018) The Maoxian landslide as seen from space: detecting precursors of failure with Sentinel-1 data. *Landslides* 15(1):123–133. https://doi.org/10.1007/s10346-017-0915-7
- Kirschbaum D, Stanley T (2018) Satellite-based assessment of rainfall-triggered landslide hazard for situational awareness. *Earth's Future* 6(3):505–523. https://doi.org/10.1002/2017EF000715
- Lacroix P, Handwerger AL, Bièvre G (2020) Life and death of slow-moving landslides. *Nature Reviews Earth & Environment* 1(8):404–419. https://doi.org/10.1038/s43017-020-0072-8
- Segoni S, Piciullo L, Gariano SL (2018) A review of the recent literature on rainfall thresholds for landslide occurrence. *Landslides* 15(8):1483–1501. https://doi.org/10.1007/s10346-018-0966-4
- Tomás R, Li Z, Liu P, Singleton A, Hoey T, Cheng X (2014) Spatiotemporal characteristics of the Huangtupo landslide in the Three Gorges region (China) constrained by radar interferometry. *Geophysical Journal International* 197(1):213–232. https://doi.org/10.1093/gji/ggu017
- Tran VA, Truong XQ, Nguyen DA, Longoni L, Yordanov V (2021) Landslides monitoring with time series of Sentinel-1 imagery in Yen Bai province, Vietnam. *ISPRS Archives* XLVI-4/W2-2021:197–203. https://doi.org/10.5194/isprs-archives-XLVI-4-W2-2021-197-2021
- Voight B (1988) A method for prediction of volcanic eruptions. *Nature* 332:125–130. https://doi.org/10.1038/332125a0
- Voight B (1989) A relation to describe rate-dependent material failure. *Science* 243(4888):200–203. https://doi.org/10.1126/science.243.4888.200

**Statistics**

- Benjamini Y, Hochberg Y (1995) Controlling the false discovery rate: a practical and powerful approach to multiple testing. *J. Royal Statistical Society B* 57(1):289–300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
- Benjamini Y, Yekutieli D (2001) The control of the false discovery rate in multiple testing under dependency. *Annals of Statistics* 29(4):1165–1188. https://doi.org/10.1214/aos/1013699998
- Ebisuzaki W (1997) A method to estimate the statistical significance of a correlation when the data are serially correlated. *Journal of Climate* 10(9):2147–2153. https://doi.org/10.1175/1520-0442(1997)010<2147:AMTETS>2.0.CO;2
- Knijnenburg TA, Wessels LFA, Reinders MJT, Shmulevich I (2009) Fewer permutations, more accurate P-values. *Bioinformatics* 25(12):i161–i168. https://doi.org/10.1093/bioinformatics/btp211
- Wilks DS (2016) "The stippling shows statistically significant grid points": how research results are routinely overstated and overinterpreted, and what to do about it. *Bulletin of the American Meteorological Society* 97(12):2263–2273. https://doi.org/10.1175/BAMS-D-15-00267.1

**Data and confounders**

- Fornaro G, Reale D, Verde S (2013) Bridge thermal dilation monitoring with millimeter sensitivity via multidimensional SAR imaging. *IEEE Geoscience and Remote Sensing Letters* 10(4):677–681. https://doi.org/10.1109/LGRS.2012.2218214
- Funk C, Peterson P, Landsfeld M, Pedreros D, Verdin J, Shukla S, Husak G, Rowland J, Harrison L, Hoell A, Michaelsen J (2015) The climate hazards infrared precipitation with stations — a new environmental record for monitoring extremes. *Scientific Data* 2:150066. https://doi.org/10.1038/sdata.2015.66
- Funk C, Peterson P, Harrison L, Saldivar R, Landsfeld M, Pedreros D, Shukla S, Fink A, et al. (2026) The Climate Hazards Center Infrared Precipitation with Stations, Version 3. *Scientific Data* 13:718. https://doi.org/10.1038/s41597-026-07096-4
- Hawker L, Uhe P, Paulo L, Sosa J, Savage J, Sampson C, Neal J (2022) A 30 m global map of elevation with forests and buildings removed. *Environmental Research Letters* 17:024016. https://doi.org/10.1088/1748-9326/ac4d4f
- Hersbach H, Bell B, Berrisford P, et al. (2020) The ERA5 global reanalysis. *Quarterly Journal of the Royal Meteorological Society* 146(730):1999–2049. https://doi.org/10.1002/qj.3803
- Huffman GJ, Bolvin DT, Braithwaite D, Hsu K-L, Joyce RJ, Kidd C, Nelkin EJ, Sorooshian S, Stocker EF, Tan J, Wolff DB, Xie P (2020) Integrated Multi-satellite Retrievals for the Global Precipitation Measurement (GPM) mission (IMERG). In: *Satellite Precipitation Measurement*, Advances in Global Change Research 67:343–353. https://doi.org/10.1007/978-3-030-24568-9_19
- Huffman GJ, Stocker EF, Bolvin DT, Nelkin EJ, Tan J (2023) GPM IMERG Final Precipitation L3 1 day 0.1° × 0.1° V07 (GPM_3IMERGDF). NASA GES DISC. https://doi.org/10.5067/GPM/IMERGDF/DAY/07
- Zippenfenig P (2024) Open-Meteo.com Weather API. Zenodo. https://doi.org/10.5281/zenodo.7970649

**Still to read in full before quoting any of their numbers:** the matrix rules of Ciampalini et al. (2016), the
gradient thresholds of Cigna & Tapete (2021), the I–D equation of Guzzetti et al. (2008), and the Bjerrum (1963)
pages. v1 does not depend on any of these numbers.
