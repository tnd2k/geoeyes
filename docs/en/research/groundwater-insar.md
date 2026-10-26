# Groundwater storage and InSAR

Status: v1 implemented (GLDAS groundwater coupling in the hazard zoning, groundwater features in the forecast).
Code: `geoeyes.ancillary.groundwater`, `geoeyes.hazard.assess._groundwater`, `geoeyes.hazard.coupling.storage`,
`geoeyes.ml.forecast._gws_features`. Companion notes: [rainfall-insar-hazard.md](rainfall-insar-hazard.md)
(the coupling test reused here), [ai-forecasting.md](ai-forecasting.md).

## Contents

1. [Question](#1-question)
2. [Background](#2-background)
3. [Which NASA groundwater data can be used](#3-which-nasa-groundwater-data-can-be-used)
4. [Method (v1)](#4-method-v1)
5. [First results](#5-first-results)
6. [Limitations](#6-limitations)
7. [Research sequence](#7-research-sequence)
8. [References](#8-references)

## 1. Question

Groundwater pumping is the main driver of subsidence in the deltas and basins GeoEyes works on (Hanoi, the
Mekong delta, Mexico City). In the rainfall coupling (rainfall note §4.3) the groundwater is only an implied link:
rain recharges the aquifer, and the heads follow the cumulative rainfall departure. The NASA Earthdata
groundwater page lists open products that estimate groundwater storage directly. The questions are:

- **Q1.** Can these products be read automatically for any project area?
- **Q2.** Does the InSAR motion follow the groundwater storage, beyond its steady trend, and with what lag and sign?
- **Q3.** Do groundwater features improve the deformation forecast?
- **Q4.** Can groundwater serve as a *spatial* layer of the susceptibility models?

## 2. Background

- **Aquifer-system compaction.** When heads fall, the effective stress on the clays rises and they compact.
  The compaction is partly elastic (it rebounds when heads recover) and partly inelastic (permanent once heads
  drop below their previous lowest level) (Galloway & Burbey 2011). InSAR sees both:
  - seasonal subsidence and rebound that follow pumping and recharge (Hoffmann et al. 2001; Chaussard et al. 2014);
  - a long-term trend from inelastic compaction (Minderhoud et al. 2017 for the Mekong delta; Bui et al. 2021 for
    Hanoi).
- **Satellite gravity.** GRACE (2002–2017) and GRACE-FO (2018–) measure changes of terrestrial water storage. The
  mascon solutions are about 3° in effective resolution, gridded at 0.5° (Watkins et al. 2015). A land-surface
  model separates the groundwater part from the soil moisture, snow and surface water.
- **GLDAS with GRACE data assimilation.** GLDAS (Rodell et al. 2004) uses the Catchment land-surface model with
  GRACE assimilated (Li et al. 2019). It gives daily groundwater storage at 0.25°, with GRACE-scale information
  downscaled by the model physics.
- **GRACE and InSAR together.** Studies of Central Mexico (Castellazzi et al. 2016) and the Central Valley
  (Ojha et al. 2018) combine the regional storage loss from GRACE with the local subsidence from InSAR. GRACE
  gives the volume and its timing; InSAR gives where the ground responds.

## 3. Which NASA groundwater data can be used

Survey of the products and tools listed on the Earthdata groundwater page, tested on 2026-10-25:

| Product / tool | Resolution | Period | Coverage | Access tested | Use in GeoEyes |
|---|---|---|---|---|---|
| **GLDAS CLSM025 DA1 D v2.2**, `GWS_tavg` | 0.25°, daily | 2003 → (months of lag) | global land | Harmony subsetting with the Earthdata token: works | **chosen** |
| GRACE / GRACE-FO JPL mascon RL06.3 | 0.5° grid, ~3° effective | 2002 →, monthly, gap 2017–2018 | global | PO.DAAC (token) | later (R-G2): independent check |
| GES DISC Data Rods (time series at a point) | as the model | as the model | global | redirected to a login page: does not work with a token | no |
| NLDAS / NCA-LDAS | 0.125° | 1979 → | United States only | – | no (outside our areas) |
| USGS / national well records | wells | varies | national | not open for Vietnam | when the user has them |

**Answer to Q1.** Yes. GLDAS `GWS_tavg` is read through NASA Harmony (OGC coverages API): one asynchronous job
per year with a bounding box and time range, one netCDF4 file per day. GeoEyes averages the days to months per
0.25° pixel and caches them in `<workspace>/cache/groundwater`. A month counts once at most two days are missing.
The first run for an area takes several minutes (Harmony runs the yearly jobs in parallel); later runs read the
cache. It needs `EARTHDATA_TOKEN`, the same token as the DEM and orbit downloads.

## 4. Method (v1)

### 4.1 Coupling with the InSAR series (hazard zoning)

Per analysis cell, on the series along the expected motion (GeoEyes sign: negative = sinking on flat ground,
downslope on slopes), with the storage S of the cell's 0.25° pixel:

    d(t) = a + b·t + g·S(t − τ) + ε

- Groundwater storage is a state, not a flux, so S plays the role that the cumulative rainfall departure plays
  in the rainfall model (`coupling.storage`). S is given at mid-month and is linear in between.
- The lag τ runs from 0 to `max_lag_months` and is chosen by the largest partial correlation once [1, t] is
  removed.
- Significance: as for rainfall, the lag search is repeated on phase-randomised surrogates (Ebisuzaki 1997) of
  the monthly storage changes, then a Benjamini–Hochberg false discovery rate is applied over the map.
- Expected sign: in subsidence mode, **g > 0** means the ground rises and falls with the storage, sinking more
  when storage falls (an elastic aquifer response). The summary reports the share of significant cells with
  g > 0.
- GLDAS is published months late. The test only uses the InSAR dates the storage covers, and only when they
  still span `min_span_months` and `min_epochs`; a warning gives the last date used.
- **The coupling does not change the hazard level.** The storage is regional, so it explains *when* the ground
  moves, not *where* it is more dangerous. It is a diagnostic layer: "Groundwater coupling" on the Thematic analysis page,
  with its own block in the cell panel and its fitted model in the cell chart.
- Parameter: `[postprocess.hazard] groundwater = "auto" | "gldas" | "off"`.
  - `auto` (default): used when the token is set; a failure only adds a warning.
  - `gldas`: required; a failure stops the run.
- Outputs:
  - columns `gw_*` in `cells.parquet`;
  - `groundwater.npz` (monthly storage per pixel);
  - `groundwater` in `hazard.json` (cells tested and significant, median lag, share of g > 0, storage trend per
    pixel).

### 4.2 Features of the forecast

When the hazard analysis holds `groundwater.npz`, the global gradient-boosting forecast gets three more
features, all taken from the AOI-mean storage of the last month published before the origin:

- `gws_anom`: that month's departure from the mean;
- `gws_d3`: the change over the last 3 months;
- `gws_d12`: the change over the last 12 months.

The "last published" rule is the same in training and at the forecast origin, so the publication lag does not
leak future values or create a gap. As with every feature, they only matter if the model beats the baselines in
the rolling-origin backtest (ai-forecasting.md).

### 4.3 Not a spatial predictor (Q4)

An urban AOI holds a few 0.25° pixels (Hanoi: 2 × 2), so as a susceptibility layer the storage would act as a
coarse location code, not as a cause. The same holds for the rainfall climatology, which is excluded by default
for this reason. Groundwater is therefore not a susceptibility layer. A real spatial layer needs the pumping
(wells, abstraction permits) or piezometric heads (R-G3).

## 5. First results

Hazard zoning with `groundwater = "auto"`, 2026-10-26 (default parameters: 100 m cells, lag 0–6 months, FDR 0.05):

| Product | InSAR period | GLDAS pixels | Storage | Cells tested | Significant (FDR) |
|---|---|---|---|---|---|
| Hanoi CSK v3 | 2011-07 → 2014-12 (18 scenes) | 2 | complete; trend +27 to +42 mm/yr | 6,362 | 0 |
| Hanoi S1 v4 | 2025-10 → 2026-10 (26 scenes) | 4 | published to 2026-08; trend −16 to −4 mm/yr | 0 (not assessed) | – |

- **Access works (Q1).** Both areas were read through Harmony; Hanoi CSK took four yearly jobs, Hanoi S1 two.
- **Hanoi CSK: no coupling.** None of the 6,362 cells follows the storage once the trend is removed. This matches
  the rest of the analysis of this area (central Hanoi): its rates stay within ±3 mm/yr (P5–P95) relative to the
  scene mean, and no cell couples with the rainfall either. The storage rose over 2011–2014 while the area stayed
  stable, so the two trends say nothing about each other here.
- **Hanoi S1: not assessed yet.** GLDAS was published up to August 2026, so the storage covers about 11 months of
  the series, below the 12 months a seasonal test needs. The storage itself shows a clear season of about 300 mm:
  highest in October 2025 (about 1,880 mm), lowest in April–June 2026 (about 1,610 mm). The test will run once the
  remaining months are published, with no change to the method.
- **Next:** the areas with fast subsidence (Hoàng Mai, Thanh Trì, Hà Đông; Mexico City) and longer series are
  where Q2 can be answered.

## 6. Limitations

- **Scale.** 0.25° storage, with GRACE information at about 300 km. Local cones of depression in a city are
  invisible; the coupling finds cells whose motion shares the *timing* of the regional storage.
- **Model, not observation.** GLDAS storage is a model state constrained by GRACE, not a measured head. Where
  the model's aquifer is unrealistic (managed pumping, confined aquifers), its seasonality may be wrong.
- **Lag of publication.** The coupling of a recent product can only use its older dates.
- **Collinearity with the trend.** A storage trend and a subsidence trend cannot be separated by one series:
  [1, t] is removed first, so only the non-linear, mostly seasonal part is tested. Both trends are reported side
  by side for interpretation, not as a causal link.
- **Thermal and rainfall confounders.** Seasonal storage, rainfall and temperature move together. R-G1 separates
  them.

## 7. Research sequence

- **R-G0 — Access and audit** *(done)*: Harmony access, monthly cache, publication lag, pixel coverage of each
  AOI.
- **R-G1 — Attribution** *(next)*: joint model d = a + b·t + k·CRD(t − τ₁) + g·S(t − τ₂) + c·T(t) on the same
  cells. Criterion: g stays significant with rainfall and temperature in the model (links to rainfall note R2).
- **R-G2 — Independent storage**: repeat with the GRACE/GRACE-FO JPL mascons. Criterion: same sign and lag in
  the coupled areas.
- **R-G3 — Heads and pumping**: piezometric records (Hanoi: national monitoring network, Bui et al. 2021) and
  abstraction data. Estimate the skeletal storage coefficient from InSAR and heads (Chaussard et al. 2014;
  Smith & Knight 2019); a pumping map would be a real spatial layer for the susceptibility models.
- **R-G4 — Forecast value**: compare the backtest with and without groundwater features on long series (CSK
  2011–2014, Sentinel-1 2016 →). Criterion: lower MAE at the 3–6 month horizons.

## 8. References

- Bui, L. K., Le, P. V. V., Dao, P. D., Long, N. Q., Pham, H. V., Tran, H. H., Xie, L. (2021). Recent land
  deformation detected by Sentinel-1A InSAR data (2016–2020) over Hanoi, Vietnam, and the relationship with
  groundwater level change. *GIScience & Remote Sensing* 58(2), 161–179.
- Castellazzi, P., Arroyo-Domínguez, N., Martel, R., Calderhead, A. I., Normand, J. C. L., Gárfias, J., Rivera, A.
  (2016). Land subsidence in major cities of Central Mexico: interpreting InSAR-derived land subsidence mapping
  with hydrogeological data. *International Journal of Applied Earth Observation and Geoinformation* 47, 102–111.
- Castellazzi, P., Martel, R., Rivera, A., Huang, J., Pavlic, G., Calderhead, A. I., Chaussard, E., Garfias, J.,
  Salas, J. (2016). Groundwater depletion in Central Mexico: use of GRACE and InSAR to support water resources
  management. *Water Resources Research* 52, 5985–6003.
- Chaussard, E., Bürgmann, R., Shirzaei, M., Fielding, E. J., Baker, B. (2014). Predictability of hydraulic head
  changes and characterization of aquifer-system and fault properties from InSAR-derived ground deformation.
  *Journal of Geophysical Research: Solid Earth* 119, 6572–6590.
- Ebisuzaki, W. (1997). A method to estimate the statistical significance of a correlation when the data are
  serially correlated. *Journal of Climate* 10, 2147–2153.
- Galloway, D. L., Burbey, T. J. (2011). Review: Regional land subsidence accompanying groundwater extraction.
  *Hydrogeology Journal* 19, 1459–1486.
- Hoffmann, J., Zebker, H. A., Galloway, D. L., Amelung, F. (2001). Seasonal subsidence and rebound in Las Vegas
  Valley, Nevada, observed by synthetic aperture radar interferometry. *Water Resources Research* 37(6),
  1551–1566.
- Li, B., Rodell, M., Kumar, S., Beaudoing, H. K., Getirana, A., Zaitchik, B. F., et al. (2019). Global GRACE data
  assimilation for groundwater and drought monitoring: advances and challenges. *Water Resources Research* 55,
  7564–7586.
- Minderhoud, P. S. J., Erkens, G., Pham, V. H., Bui, V. T., Erban, L., Kooi, H., Stouthamer, E. (2017). Impacts
  of 25 years of groundwater extraction on subsidence in the Mekong delta, Vietnam. *Environmental Research
  Letters* 12, 064006.
- Ojha, C., Shirzaei, M., Werth, S., Argus, D. F., Farr, T. G. (2018). Sustained groundwater loss in California's
  Central Valley exacerbated by intense drought periods. *Water Resources Research* 54, 4449–4460.
- Rodell, M., Houser, P. R., Jambor, U., Gottschalck, J., Mitchell, K., Meng, C.-J., et al. (2004). The Global
  Land Data Assimilation System. *Bulletin of the American Meteorological Society* 85(3), 381–394.
- Smith, R., Knight, R. (2019). Modeling land subsidence using InSAR and airborne electromagnetic data. *Water
  Resources Research* 55, 2801–2819.
- Watkins, M. M., Wiese, D. N., Yuan, D.-N., Boening, C., Landerer, F. W. (2015). Improved methods for observing
  Earth's time variable mass distribution with GRACE using spherical cap mascons. *Journal of Geophysical
  Research: Solid Earth* 120, 2648–2671.
- Data: Li, B., Beaudoing, H., Rodell, M. (2020). GLDAS Catchment Land Surface Model L4 daily 0.25 × 0.25 degree
  GRACE-DA1 V2.2. Goddard Earth Sciences Data and Information Services Center (GES DISC),
  doi:10.5067/TXBMLX370XX8.
