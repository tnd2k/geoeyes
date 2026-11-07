# Landslide susceptibility with rainfall and InSAR (Vietnam)

> Research note and implementation plan. Separate study from
> [`rainfall-insar-hazard.md`](rainfall-insar-hazard.md) (zoning of *slow* ground motion): this one is about
> rainfall-triggered *rapid* landslides, labelled by inventories. The two share data (DEM, rainfall, InSAR products,
> thematic layers) and code (`geoeyes.ml.layers.Grid`, spatial block cross-validation).
> Status (2026-11-05): **L0–L5 run on the pilot area** (gates L0–L3b closed; L3c C1, C3, C5 done; L4 and L5
> reported 2026-11-03 / 2026-11-04: H2 and H3 not supported); L6 code exists, not reported; L5b, L7, L8, L9 not
> started (L7 and L9 now superseded by [`landslide-forecast-system.md`](landslide-forecast-system.md)). Plan first
> written 2026-11-01. Each step (§5) ends with a review by the project owner before the next one starts.
>
> **Review 2026-11-05: direction.** (1) The 2025 test is no longer independent (it dropped Hansen and picked the
> champion): hold out the 156 rain-dated objects (L3b.7) and use them once. (2) Hansen / Landsat is not
> illumination-independent (sun-synchronous ~10:00; baseline scars lean SE), so B1 cannot fully exclude an
> illumination artefact. (3) Negatives come only from the `near` footprint: calibration and classes are not valid
> outside the sampled domain; state it, or add negatives outside. (4) L6 thresholds are unstable (116 events ≤ 5 km,
> errors up to 25 km, two regions, leave-one-year-out): report events per region, bootstrap, consider pooling.
> (5) H5 / L5b: count the later failures (power check) before spending disk.

## Contents

1. [Questions and scope](#1-questions-and-scope)
2. [Background](#2-background)
3. [Data](#3-data)
4. [Hypotheses](#4-hypotheses)
5. [Method: steps L0–L9](#5-method-steps-l0l9) (L0–L7, then L9, then L8; inserted steps L2a, L2b, L3b, L3c, L5b)
6. [Implementation in GeoEyes](#6-implementation-in-geoeyes)
7. [Parameters and where each default comes from](#7-parameters-and-where-each-default-comes-from)
8. [Risks and limitations](#8-risks-and-limitations)
9. [References](#9-references)

---

## 1. Questions and scope

Four questions, each with its own labels:

| | Question | Labels | Answer |
|---|---|---|---|
| **Q1 where** | Which slopes fail when a storm hits? | mapped landslide polygons (Das 2024) | susceptibility map, 30 m |
| **Q2 when** | How much rain triggers landslides, per region? | dated landslide reports (`vietnam.csv`) | rainfall thresholds |
| **Q3 InSAR** | Does pre-event slope motion (InSAR) add anything to Q1? | the same polygons | Δ skill, importance |
| **Q4 after** | Which mapped landslides keep moving after the storm, and do they fail again? (added 2026-11-02, after Sui et al. 2026) | the Molave polygons; later reports | activity classes, validated (L5b) |

A last step combines Q1 and Q2 into a hazard indicator (where × when), in the manner of NASA LHASA, and hindcasts
it on reported events.

**Out of scope.** Runout and deposition, exposure and risk, the landslide mapping itself (a separate task for
Typhoon Yagi, §5 L8). The operational forecast service, out of scope at first, is now the goal (owner, 2026-11-03):
its design and plan are in [`landslide-forecast-system.md`](landslide-forecast-system.md) (F0–F9), which this note
feeds.

**Terms** (Fell et al. 2008): *susceptibility* = where (spatial probability, no time); *hazard* = where + how often
or when; *risk* = hazard × exposure × vulnerability.

## 2. Background

- **Statistical susceptibility models.** The review of Reichenbach et al. (2018) covers more than 500 papers. Their
  recommendations, adopted here:
  - spatially independent validation;
  - reporting of the inventory and of the mapping unit;
  - a few interpretable predictors rather than many;
  - a statement of what the absence of a landslide means.
- **Spatial cross-validation.** Brenning (2005) showed that random cross-validation overestimates the skill of
  susceptibility models because of spatial autocorrelation. Block cross-validation is the reference; `ml.susceptibility`
  already reports both.
- **Inventory errors.**
  - Sampling strategy: Hussin et al. (2016) show that the place sampled inside the polygon matters. Sampling the
    scarp area (the initiation zone) gives a different and more meaningful model than sampling the centroid or the
    whole polygon, which includes the runout. (Corrected 2026-11-05: this was attributed to Steger et al. 2016.)
  - Positional errors: Steger et al. (2016) show how errors in the position of the mapped polygons propagate into
    the model; hence the negative buffer of L1.
  - Systematic incompleteness: Steger et al. (2017) show that landslides mapped preferentially near roads or in
    unforested land are learnt by the model as "roads cause landslides".
  - Inventory completeness can be checked with the area–frequency distribution (Malamud et al. 2004; Guzzetti et
    al. 2012).
- **Mapping units.**
  - Grid cells are simple and match the DEM.
  - Slope units (Alvioli et al. 2016, `r.slopeunits`) follow the hydrological structure of the slopes and reduce
    autocorrelation. They are a secondary unit here.
- **Rainfall thresholds.**
  - Intensity–duration and cumulated event rainfall – duration (E–D) thresholds: Guzzetti et al. (2008), Brunetti
    et al. (2010; frequentist method, threshold at a non-exceedance probability), automated reconstruction of rainfall
    events CTRL-T (Melillo et al. 2018). Review: Segoni et al. (2018).
  - LHASA (Kirschbaum & Stanley 2018): a global decision tree, where the susceptibility class (Stanley & Kirschbaum
    2017) is combined with the 7-day antecedent rainfall percentile (IMERG). This is the model for the combination in
    L7.
- **InSAR and landslides.** The PSI activity / intensity matrices (Cigna et al. 2013), the refinement of
  susceptibility with PSI velocities (Ciampalini et al. 2016), and slow landslides and rain (Handwerger et al. 2013;
  Lacroix et al. 2020) are reviewed in [`rainfall-insar-hazard.md`](rainfall-insar-hazard.md) §2.1, §2.3.
  - Here the question is narrower: can slow motion *before* a storm help predict where rapid failures occur
    *during* it?
  - The answer is open. Some shallow failures have no precursor, while large slope deformations often do.
  - The canopy in central Vietnam makes it hard to measure in C-band.
  - Post-event activity of mapped landslides: Sui et al. (2026) combine U-Net mapping on GF-6 images with SBAS-InSAR
    (27 Sentinel-1 images) and station rain for about 4,200 landslides of the July 2024 Zixing rainstorm, and class
    them as stable / potential / active / rapid. They note that illumination and shadows affect the optical
    mapping (see L2a). Their open question, whether InSAR acceleration with antecedent rain separates active from
    reactivating landslides, is taken up here as Q4 (L5b), on the Molave polygons and with an answer to each of the
    limits of their study. It shares the method of the slow-motion study
    ([`rainfall-insar-hazard.md`](rainfall-insar-hazard.md)).
- **Vietnam.**
  - The inventory of Das (2024) was mapped from RapidEye and PlanetScope images (NC State; AGU 2022).
  - The national survey of VIGMR mapped landslide points at 1:50,000 since 2012, but the data are not open (see
    `inventories/landslide/SOURCES.md`).
  - No published study was found that combines a polygon inventory, InSAR and rainfall thresholds in Vietnam.

## 3. Data

### 3.1 Inventories (`<workspace>/inventories/landslide/`)

| File | Content | Use |
|---|---|---|
| `central_vn_das2024.gpkg` | 21,234 polygons and points: Ketsana 2009 (8,744), Podul 2013 (915), Molave 2020 (11,575); 107.50–108.44° E, 14.31–15.38° N; CC-BY-4.0 | Q1, Q3 labels |
| `vietnam.csv` / `.geojson` | 235 reported events 2007–2026 (NASA GLC 127, curated 108), 116 located to ≤ 5 km; one date each | Q2 labels, hindcast in L7 |
| `SOURCES.md` | the open datasets checked, the VIGMR GeoServer layers, what is not usable | — |

Event footprints, from the concave hull of each event's landslides (ratio 0.3). This is **not** the mapping extent,
which is not published.

| | Ketsana | Podul | Molave |
|---|---|---|---|
| Hull | 5,409 km² | 427 km² | 2,431 km² |
| Overlap with Molave | 878 km² (561 Ketsana / 6,252 Molave landslides inside) | 88 km² | — |
| Polygon area, median / p95 | 2,198 / 21,579 m² | 925 / 5,175 m² | 1,072 / 11,199 m² |

The Molave set probably covers the whole October 2020 sequence:
- Storms: Linfa, Nangka, Saudel and Molave, from 6 to 29 October.
- Rào Trăng 3 failed on 12–13 Oct, Trà Leng on 29 Oct.
- It is treated as the **October 2020 event set**, since the image dates of the mapping are not published.

### 3.2 Predictors

All predictors are sampled on the 30 m grid `Grid(cell_m=30)` of `geoeyes.ml.layers`. The time column says whether
the layer describes the state *before* each event (necessary to avoid leakage).

| Group | Layer | Source | Time | Note |
|---|---|---|---|---|
| Terrain | elevation, slope, aspect (sin, cos), plan / profile curvature, TPI (150 / 500 m), relief (300 m), TWI, flow accumulation, distance to stream | Copernicus GLO-30 (cache `dem/copernicus-30`) | DEM 2011–2015: after Ketsana, before Molave; the acquisitions span Podul (Nov 2013) | the DEM can contain old landslide scars (Ketsana, possibly Podul): a small, known bias |
| Lithology | lithological class, distance to faults | GLiM (Hartmann & Moosdorf 2012, ~1:3.75 M); Vietnam 1:200,000 geological map if available (L0) | static | GLiM is coarse: few classes over the footprint |
| Soil | clay, sand, depth to bedrock | SoilGrids 2.0 (250 m); global depth to bedrock (250 m) | static | coarse |
| Land cover | tree cover in 2000, forest loss before the event year | Hansen et al. (2013) Global Forest Change, 30 m | per event | WorldCover 2020 (v100) and 2021 (v200) are not before the events (2020 covers the whole year, Molave included): not used |
| Access | distance to road | OSM (today) | today | roads built after the event bias the model; run with and without |
| Rain (event) | rain over 3, 7 and 30 days before the event end, per pixel (L4 ran with these; the L0 gate set 5, 10 and 30 days for L6) | CHIRPS v3 daily (0.05°); GPM IMERG Final (0.1°) as a check | per event | about 80 CHIRPS pixels (~30 km² each) in the Molave hull, about 22 in the pilot: tested as a spatial proxy (L4) |
| InSAR (pre-event) | downslope velocity, its significance, temporal coherence, point density, seasonal acceleration | Sentinel-1, §3.3 | before the event | only Molave |

### 3.3 Sentinel-1 over the Molave footprint

ASF search, IW SLC, point 108.0° E 15.0° N, 2016-01-01 → 2020-10-27:

| Track | Direction | 2016 | 2017 | 2018 | 2019 | 2020 | Total |
|---|---|---|---|---|---|---|---|
| 55 | ascending | 15 | 23 | 29 | 31 | 25 | 123 |
| 120 | descending | 26 | 30 | 31 | 31 | 26 | 144 |

- Both geometries are available, with a 12-day repeat from 2017.
- Ketsana (2009) and Podul (2013) are before Sentinel-1, so the InSAR question (Q3) can only be tested on Molave.
- ALOS PALSAR (L-band, 2006–2011) could cover Ketsana; it is a later option, not in this plan.

### 3.4 Pilot area (decided at the L0 gate, 2026-11-01)

The whole chain L1–L7 runs first on a **pilot area**, then is extended. The pilot keeps the InSAR download within
the disk (one burst per track instead of 6–8) and tests the method on both events.

- **Area:** the intersection of the Sentinel-1 bursts `120_256591_IW3` (descending) and `055_116074_IW1`
  (ascending), clipped to the `near` footprints of Ketsana and Molave.
  - Extent: 107.60–108.20° E, 15.00–15.21° N, 666 km².
  - File: `studies/landslide_central_vn/l0/pilot.gpkg`.
- **Content:**

  | Event | Footprint in the pilot | Landslides |
  |---|---|---|
  | Ketsana | 523 km² | 1,111 |
  | Molave | 273 km² | 880 |
  | Overlap of the two | 130 km² | 207 Ketsana, 444 Molave |

  Podul lies outside the pilot.
- **InSAR (L5, L5b):** two years before and two years after the storms (owner's decision, 2026-11-02):
  - one burst per track, 12-day repeat;
  - L5: 2018-10-01 → 2020-09-30;
  - L5b: 2020-11-01 → 2022-10-31;
  - about 60 dates per period and track. That is about 8.5 GB of raw bursts per period for track 120 and a little
    less for track 55, to be counted with ASF at L5;
  - *measured (2026-11-05):* a burst is about 0.14 GB, but the track 120 archive holds three IW3 bursts per date
    for the pilot (about 0.4 GB per date; the 20 dates of 2021 take 8.1 GB), so about 25 GB of raw bursts per
    period. Processing comes on top: the 24-date L5 project `quangnam_l5_d120` takes 35 GB (coregistered stack
    21 GB, PS / DS runs 12 GB);
  - track 120 first.
- **Limits of the pilot:**
  - With 880 Molave landslides, the spatial blocks are few: about 70 blocks of 2 km and 11 of 5 km. The uncertainty
    of the AUC is reported, and H1 is not accepted or rejected on the pilot alone.
  - Lithology varies little over 666 km².

## 4. Hypotheses

- **H1 – terrain explains where.** A model of terrain, lithology, soil and land cover separates the Molave initiation
  zones from the stable slopes of the footprint, with spatial block AUC ≥ 0.80. It transfers between events:
  - trained on Ketsana and tested on Molave in their overlap, the AUC drops by less than 0.05 from the Molave block
    cross-validation;
  - and the reverse.
- **H2 – event rain adds to terrain.** The October 2020 rain per CHIRPS pixel improves the held-out AUC more than a
  random smooth field with the same spatial autocorrelation. If not, rain only acts as a spatial proxy over this
  small area (as for `rain_annual_mm` in `ml.susceptibility`).
- **H3 – pre-event InSAR adds to terrain.** On the slopes with InSAR coverage, the pre-event downslope velocity and
  coherence improve the held-out AUC (paired block bootstrap, 95 % interval excludes 0). A negative result is a
  result: it says what C-band can and cannot do on vegetated slopes.
- **H4 – rain thresholds.** For each region (northern mountains and central Vietnam), the antecedent rainfall (A10,
  A30 as percentiles of the local climatology; windows of 5, 10, 30 days from the L0 gate) and the E–D pair separate landslide days from other rainy-season
  days:
  - TSS ≥ 0.4 in leave-one-year-out validation;
  - the thresholds differ between the two regions.
- **H5 – post-event activity.** Among the Molave landslides with InSAR coverage, an activity class that uses the
  acceleration and the lagged response to antecedent rain (from two years of InSAR after the storm) separates the
  landslides (or their surroundings) that fail again after that window (2022-11 → 2026) from the others better than
  the mean velocity alone, and better than fixed velocity thresholds
  as in Sui et al. (2026).

## 5. Method: steps L0–L9

Each step lists its inputs, its operations, its outputs, its checks and its **review gate**. At the gate the
results are reported to the project owner, who decides whether the next step starts.

### L0 — Data audit and footprints

- **Inputs:** `central_vn_das2024.gpkg`, `vietnam.csv`, the Zenodo record and the AGU abstract.
- **Operations:**
  1. **Use the dataset as published** (CC-BY-4.0): every output, report and figure that uses it cites Das (2024),
     https://doi.org/10.5281/zenodo.15596033. The mapping extents and image dates are not published, and "no
     landslide" outside the mapped areas is unknown, so the footprints are approximated (2) and their effect is
     tested (L3, §8).
  2. Approximate the footprints:
     - take the concave hull of each event's landslides, buffered by 1 km;
     - clip it to the land that has slopes (> 5°);
     - check it by eye against PlanetScope / Sentinel-2 images of the event (clouds, gaps).
  3. Area–frequency distribution per event: the rollover area and the power-law tail (Malamud et al. 2004). It says
     down to which area each inventory is complete, and whether the three events are comparable.
  4. Overlaps:
     - Molave polygons that intersect Ketsana polygons are reactivations; count them and flag them.
     - Duplicates inside an event are polygons that touch; check whether they share an edge (split by mapping) or
       are separate.
  5. Check the availability:
     - CHIRPS v3 daily (URL and period);
     - IMERG Final daily (Earthdata account, already in `sensors/sentinel1/earthdata.py`);
     - Hansen GFC tiles (20N_100E);
     - GLiM, faults, the depth to bedrock layer;
     - the Vietnam 1:200,000 geological map.
  6. Count the Sentinel-1 bursts that cover the Molave footprint per track and date, and estimate the download
     (expected tens of GB per track with bursts, against several TB with full SLCs).
- **Outputs:** `footprints.gpkg` (one polygon per event, with how it was made), `l0_audit.md` (counts, area–frequency
  plots, overlaps, data availability, burst count and volume).
- **Gate:** footprints accepted; the list of predictors that can really be read.
- **Gate outcome (2026-11-01).** Report: `studies/landslide_central_vn/l0/l0_audit.md`. These decisions override the
  later steps where they differ:
  1. **Footprint.** The concave hull encloses large unmapped areas for Ketsana, with straight, image-like edges.
     - Main footprint: `near` (within 1 km of a mapped landslide, gaps < 3 km closed, minus flats > 1 km²).
     - Sensitivity variant: the hull + 1 km, replacing "hull shrunk by 1 km".
  2. **Completeness.** Ketsana (RapidEye 5 m) has fewer landslides below about 1,000 m² than Molave (PlanetScope
     3 m). The transfer test of L3 is also run on the landslides ≥ 1,000 m² only.
  3. **Rain.** Daily CHIRPS v3 is pentad totals split by ERA5 or IMERG daily ratios (UTC days), not an independent
     daily product.
     - L6 builds the rainfall events from IMERG Final daily.
     - CHIRPS gives the amounts and the climatology.
     - Antecedent windows are 5, 10 and 30 days.
  4. **Predictors.**
     - Lithology from GLiM at full resolution (1:3.75 M; no open Vietnamese digital map was found).
     - "Distance to faults" dropped: GEM has only 4 segments near the area.
     - Pelletier et al. (2016) hill-slope soil and regolith thickness added (1 km).
  5. **Disk.** The InSAR of the whole Molave footprint needs 70 GB (track 120) and 88 GB (track 55), against 21 GB
     free. The chain runs first on the pilot area of §3.4.

### L1 — Labels and samples

- **Positives (initiation zones).** For each polygon, on the 30 m grid:
  - (a) **default**: the highest grid cell inside the polygon (the scarp point; sampling strategies compared by
    Hussin et al. 2016);
  - (b) the cells of the upper third of the polygon's elevation range;
  - (c) the centroid (comparison only: it mixes source and runout).
  - Polygons smaller than one cell (< 900 m²) get variant (a) only.
  - The three variants are compared in L3 (AUC and the slope distribution of the positives).
- **Negatives.** Grid cells inside the event footprint, at more than 60 m (2 cells) from any polygon of that event.
  - No slope filter in the default: flat cells are easy negatives. Reported with and without slope < 5°, because
    easy negatives inflate the AUC.
  - Balanced 1:1 with the positives, drawn 10 times with different seeds. Report mean ± standard deviation.
  - The whole footprint is also predicted, for calibration: the prior correction of the logistic intercept to the
    real prevalence.
- **Reactivations.** Molave positives on a Ketsana polygon are kept, but marked (`reactivated`). A variant without
  them tells whether the model only learns old scars.
- **Outputs:** `labels_<event>.parquet` (cell, x, y, label, variant, seed, reactivated).
- **Gate:** the number of positives per event and variant; maps of a few sample areas with the polygons, scarp
  points and negatives.

### L2 — Predictors

- Build the layers of §3.2 on `Grid(cell_m=30)` over the union of the footprints, one table per event: land cover
  and rain depend on the event.
- **Terrain derivatives** from GLO-30:
  - The DEM is resampled once to the 30 m metric grid.
  - Curvatures and TPI are computed on that grid (Zevenbergen–Thorne).
  - TWI is ln(a / tan β), with a from D8 flow accumulation.
  - Streams are the cells where the flow accumulation is ≥ 0.5 km² (sensitivity test 0.1 and 1 km²).
- **Collinearity:** Spearman |ρ| > 0.8 → keep the more interpretable one; VIF < 5 for the logistic model.
- **Lithology:** one-hot, rare classes (< 1 % of the footprint) merged.
- **Outputs:** `predictors_<event>.parquet`, `predictors.md` (sources, versions, missing fraction per layer, maps).
- **Gate:** maps and histograms of each layer; layers dropped and why.
- **Gate outcome (2026-11-02).** Report: `studies/landslide_central_vn/predictors/predictors.md`.
  - 24 layers on 1.19 million cells.
  - Dropped by the screening: `flow_acc_km2` (ρ 0.86–0.90 with TWI), `tree_cover_2000` (with `tree_cover_event`),
    and `tpi_150` for the logistic model (VIF 5.4–5.8).
  - **Accepted by the owner (2026-11-02):** `regolith_thick_m` is left out of the L3 models. Its 1 km cells jump
    between 0 and the 50 m cap, and its univariate AUC is 0.52–0.54. `soil_thick_m` stays.
  - GLiM is uninformative here: basic plutonic covers 84 % of the pilot, and every class has an AUC of about 0.5.
  - Soil clay (250 m) separates Molave well (0.69) but not Ketsana (0.55): a possible location proxy, which the
    spatial blocks of L3 will test.
  - **Aspect** separates Ketsana (northness AUC 0.33: the landslides face south) much more than Molave (0.45) on
    the same ground. The owner asked for a dedicated study before L3: **L2a**.

### L2a — Aspect of the landslides (inserted at the L2 gate, 2026-11-02)

**Why.** Aspect is a common predictor of susceptibility. In an inventory mapped on optical images, it can describe
the mapping rather than the failures:
- Slopes that face away from the sun are darker or in shadow, so landslides there are missed. Liu et al. (2018)
  found that shadows covered 34 % of their Formosat-2 study area and recommend leaving shadowed areas out of the
  sampling. Sui et al. (2026) name illumination and shadows as a limit of their U-Net mapping.
- If such a bias goes into L3 unexamined, the model learns where the images were bright, and the susceptibility map
  inherits it.

**Facts that frame the study.**
- **Sun position** at the pilot (15.1° N), computed for the dry season (October–February), when cloud-free images
  are likely:
  - at about 11:00 local solar time (RapidEye): azimuth 146–159° (SE–SSE), elevation 49–62°;
  - at about 10:00 (PlanetScope): azimuth 126–142°, elevation 42–52°.
  - A slope shades itself only if it faces away from the sun (north-west) and is steeper than the sun's elevation,
    42–62°. That is rare here (95 % of the cells are below about 40°).
  - So if illumination matters, it acts through dimmer light and through shadows cast by neighbouring ridges, not
    through self-shadow.
- **The image dates of the mapping are not published.**
- **The effect is stronger with the higher sun.** Ketsana, mapped on RapidEye (5 m, about 11:00, higher sun), shows
  the stronger effect; Molave, mapped on PlanetScope (3 m, about 10:00, lower sun), the weaker one. At equal dates
  and resolution, illumination alone predicts the opposite. So either the seasons or the resolutions of the images
  differ enough, or the effect is not illumination. This is the first thing to explain.

**Hypotheses** (not exclusive):

| | Hypothesis | Same ground, two events | With slope | What decides |
|---|---|---|---|---|
| A0 | **Confounding**: aspect stands in for slope, relief, curvature or location | — | disappears when they are controlled | conditional model (2) |
| A1 | **Illumination at mapping**: fewer landslides found where the light was dim or cast shadows fell | differs (other dates, sensors) | strongest on steep slopes facing away from the sun | one illumination term fits as well as the aspect harmonics, with a plausible sun (3) |
| A2 | **Misregistration**: the inventory is shifted against GLO-30 (orthorectification on steep relief), so the scarp cells fall on the wrong side of ridges | differs (other images) | — | a non-zero best shift that changes the aspect signal (4) |
| A3 | **Storm exposure**: slopes facing into the wind during the heaviest rain get more rain (orographic enhancement) | differs with each storm's wind | — | a windward index from the storm track fits (5) |
| A4 | **Terrain or vegetation physics**: insolation, soil moisture, forest, rock structure | the same | stays when slope is controlled | the same signal for both events in their overlap (6) |

**Data.**
- The L1 labels (scarp positives; the main footprint's negatives, 10 draws) and the L2 predictors.
- Sun positions from the NOAA solar-position equations, for September–April × 09:30–11:30 local solar time.
- Cast shadows: the horizon angle of every cell towards the sun's azimuth, from GLO-30 on the padded grid.
- Storm tracks: IBTrACS v04r01, Western Pacific (Knapp et al. 2010), for Ketsana 2009 and for Molave and the other
  storms of October 2020.
  - The wind direction at the pilot, hour by hour, comes from the track with a parametric vortex (Holland 1980):
    tangential wind plus about 20° of inflow.
  - The days of heaviest rain come from IMERG daily, as in L6.

**Methods.**
1. **Description.** For each event:
   - the frequency ratio (positives / negatives) in 16 aspect sectors, over the 10 draws, with block-bootstrap
     intervals (2 km blocks);
   - rose diagrams by slope class (< 20°, 20–30°, 30–40°, ≥ 40°) and for both footprints (`near`, `hull`);
   - the same inside the Ketsana–Molave overlap only.
2. **Conditional model.** A logistic model of slope (spline), relief, curvatures and TWI, plus the aspect harmonics
   (sin θ, cos θ, sin 2θ, cos 2θ).
   - Likelihood-ratio test of the harmonics.
   - Amplitude and phase of the first harmonic, with a block bootstrap.
   - The same as a conditional logistic model with 2 km blocks as strata, which removes location.
3. **Illumination.** Compute cos i = cos z cos s + sin z sin s cos(φ_sun − θ) on a grid of suns (azimuth 90–200°,
   elevation 30–70°, steps of 5°).
   - Replace the harmonics by cos i, with and without a cos i × slope term, and compare the deviance and the AIC.
   - Report the best sun and whether it lies in the plausible range above.
   - For that sun, compare the share of positives and of negatives in cast shadow.
4. **Shift.** Move the inventory by (dx, dy) in [−90, 90] m, in steps of 15 m.
   - Criterion: the median slope of the scarp cells and the AUC of slope, mapped over the shifts.
   - Repeat 1–2 at the best shift.
5. **Storm exposure.** A windward index w = cos(θ − φ_from), where φ_from is the direction the wind comes from,
   weighted by the rain of each day of the event. It enters the model of 2 in place of the harmonics.
6. **Same ground.** The model of 2 on the overlap, with an event × aspect interaction. Under A4 the interaction is
   zero; under A1–A3 it is not.

**Outputs:** `aspect/` with `aspect.json`, `aspect.md`, rose diagrams, the illumination surface (deviance per sun),
the shift surface and the windward test. Code: `landslide/aspect.py`, `geoeyes landslide aspect`.

**Gate (decision for L3):**
- A1 or A2 supported:
  - aspect leaves the L3 models, or enters in a corrected form;
  - the negatives are drawn outside poorly lit cells, as Liu et al. (2018) recommend for shadows;
  - for A2, the inventory is shifted.
- A3 supported: an event-specific windward index replaces aspect and goes with the rain of L4.
- A4 supported: aspect stays as a terrain predictor.
- Inconclusive: L3 runs with and without aspect and reports both maps.

**Limits.**
- The image dates are unknown, so the illumination test fits the sun instead of knowing it.
- The illumination model ignores diffuse light and atmosphere.
- The vortex wind ignores the terrain.
- With 864 Molave positives in the pilot, 16-sector roses are noisy. The study can be repeated on the whole Das
  footprint, once L1 and L2 run there.

**Gate outcome (2026-11-02).** Report: `studies/landslide_central_vn/aspect/aspect.md`.

The signal, over slope, relief, curvature and TWI:
- Ketsana: landslides favour slopes facing south (176.7°, 95 % interval 164–188°; odds about 6.5 times those of
  slopes facing north).
- Molave: weak, towards 213°.

| | Result | Evidence |
|---|---|---|
| A0 | rejected for Ketsana; Molave's signal is mostly location | Ketsana keeps LR 143 with 2 km blocks as fixed effects; Molave drops from LR 31 to 14, and its azimuth moves from 213° to 128° |
| A1 | rejected for Molave; only partly consistent for Ketsana | see below |
| A2 | rejected | a 30 m shift of Ketsana to the south raises the AUC of slope from 0.70 to 0.73 but leaves the aspect signal unchanged; Molave's best shift is none |
| A3 | rejected in the vortex form | the windward index fits much worse than the harmonics, and with the opposite sign: Ketsana favours the lee slopes |
| A4 | rejected | on the same 130 km², the two events differ (event × harmonics LR 28, p = 1.2·10⁻⁵): 146° and amplitude 1.30 against 203° and 0.62 |

A1 in detail:
- Molave: the amplitude falls with slope (0.70 → 0.29), the opposite of what illumination predicts.
- Ketsana: the amplitude grows with slope, but less than predicted (1.64 times against 2.37). The best sun azimuth,
  175°, lies outside the plausible 126–159°.
- Cast shadows hold under 2.5 % of the cells at every plausible sun.
- Even on 2–20° slopes, Ketsana keeps an amplitude of 0.64 (odds about 3.6 times), where the illumination contrast
  between slopes facing south and north is only about 1.3.

Deviations from the plan:
- the shift step is 30 m (the grid), not 15 m;
- the daily rain is CHIRPS v3 `sat` (IMERG daily timing) instead of IMERG daily;
- two tests were added: the amplitude by slope class, and the cast shadows at four plausible suns.

New hypothesis **A5, revegetation before mapping**: if the Ketsana images were taken months after the storm, scars on
shaded, moister north-facing slopes may have greened first and been missed.

Decisions:
- **The L3 main model leaves aspect out**: its signal is specific to an event or an inventory and does not transfer
  between storms. A variant with aspect runs beside it.
- **L2b** checks the inventories with sources independent of the optical mapping, before L3.
- **Q4 / L5b**, the post-event activity after Sui et al. (2026), is added after L5.

### L2b — Independent check of the inventories (inserted at the L2a gate, 2026-11-02)

**Why.** L2a used one inventory per event, so it cannot tell "fewer landslides on north-facing slopes" from "fewer
mapped there". This is limitation 5 of the review of Sui et al. (2026): a classification needs an independent check.
Sources independent of one optical mapping:
- Landsat, through Hansen GFC: many dates in each annual composite. *Note (2026-11-05):* Landsat is
  sun-synchronous (about 10:00), so its illumination varies with the season only; it is a second optical view, not an
  illumination-free one;
- Sentinel-1 SAR: no dependence on sunlight, and little sensitivity to regrowth in the first weeks.

**Tests.**
1. **Hansen GFC, both events** (B1). Forest loss in the event year and the next one marks new bare ground: `lossyear`
   9–10 for Ketsana, 20–21 for Molave.
   - Inside the Das polygons: the share of polygons with event-year loss (Landsat detects the scar), by aspect
     sector.
   - Outside the polygons, inside the footprint: event-year loss on slopes ≥ 15°, in patches ≤ 5 ha (scars, not
     clearing), by aspect sector. These are candidate scars missed by the inventory.
   - Baseline: the same for loss in years without a big storm (Ketsana: 2005–2008 is not in GFC, so 2011–2012;
     Molave: 2017–2018).
   - The aspect pattern of the event years minus that of the baseline (difference in differences) separates storm
     scars from clearing.
   - Reading the result:
     - Hansen scars spread evenly over aspect while Das favours the south: an inventory artefact (A1 or A5).
     - Hansen also favours the south: the storm did.
2. **Sentinel-1 change, Molave** (B2). One burst per track (120, 55): three dates before and three after the
   October 2020 storms, for example track 120 on 2020-09-11, 09-23, 10-05 and 11-10, 11-22, 12-04 (about 1.7 GB for
   both tracks).
   - The change is the log-ratio of the mean σ⁰ after to before (speckle filtered, on the 30 m grid through the
     product's lat / lon) and the coherence loss of the pairs across the event against the pairs before it.
   - Cells in layover or radar shadow of each track are masked. Both tracks together remove the look-direction bias of
     SAR.
   - Measured, by aspect sector: the detection rate of the Das polygons, and the change cells outside the polygons.
     They are read as in 1.
3. **Size** (B3, A5). The aspect amplitude of L2a by polygon area (< 900, 900–3,000, ≥ 3,000 m²) for each event.
   Revegetation predicts a stronger signal for the small landslides; a property of the slopes predicts none.
4. **ALOS PALSAR for Ketsana** (B4, optional). Only an availability check: L-band images within about 46 days before
   and after 2009-09-29 over the pilot (ASF). If there are any, test 2 is repeated with them.

**Outputs:** `verify/` with `verify.json`, `verify.md`, maps of the independent scars, roses. Code:
`landslide/verify.py`, `geoeyes landslide verify`. The Sentinel-1 bursts go to the workspace archive as usual
(`processing/acquire/s1_bursts.py`).

**Gate:**
- Independent sources spread evenly while Das favours the south:
  - aspect stays out of L3;
  - the L3 report states which events' inventories are biased;
  - the transfer test Ketsana → Molave is read with that bias;
  - the independent scars can be added as positives in a variant.
- Independent sources also favour the south: the signal is the storm's. Aspect then enters L4 as an event-specific
  term, with the rain.

**Limits.**
- Hansen marks canopy loss on 30 m pixels: small scars (below one pixel) and scars in non-forest land are missed,
  and logging remains in the event years despite the baseline.
- C-band σ⁰ changes little between wet forest and wet soil (about 1–3 dB).
- The SAR mask removes steep slopes facing towards or away from each track, so each track loses different cells;
  the two tracks still share most of the moderate slopes. (Corrected 2026-11-05: the 20 % coverage of track 55 in
  the outcome below comes from the extent of its stack, AOI 15.11–15.21° N and IW1 only, not from the masks.)

**Gate outcome (2026-11-02).** Report: `studies/landslide_central_vn/verify/verify.md` (boxcar run kept as
`verify_boxcar.md`).

- **B1 Hansen (the main evidence).** Of the scars Landsat sees in the event years, Das captures:
  - Ketsana: about 40 % on south-facing slopes against about 15 % on north-facing ones (708 of 2,454 patches;
    aspect LR 154, p ≈ 10⁻³², towards 195°).
  - Molave: 20 % against 11 % (LR 22, p ≈ 10⁻⁴).
  - The Landsat scars themselves have the same aspect pattern in the event years as in the baseline years (Ketsana:
    towards 140° against 129°, amplitude 0.30 against 0.30). So the storm did not favour south-facing slopes.
- **B2 Sentinel-1 (inconclusive).**
  - Two stacks (track 120: 9 dates; track 55: 7 dates; Aug–Dec 2020), phase linking (adaptive, Anderson-Darling SHP).
  - Over the SHP families, the 36-day coherence before the storms is already about 0.10–0.12 (the boxcar's 0.30–0.32
    is its positive bias at low coherence). There is no coherence left to lose, and the coherence loss is 0.00
    inside and outside the polygons.
  - σ⁰ changes by about 0.1 dB.
  - The changed cells follow the SAR geometry: they favour slopes facing east, towards the descending track's
    satellite. Track 55 covers only about 20 % of the cells and cannot balance it.
- **B3 size.** Ketsana's aspect signal is the same at every size, so revegetation (A5) is not supported. Molave's is
  left only below 900 m².
- **B4 ALOS PALSAR: dropped.** ASF lists two PALSAR FBD scenes (2009-08-22, 2009-10-07), but GeoEyes has no PALSAR
  reader (ADR-013, ALOS generation open).

Decisions (accepted by the owner):
1. **The aspect signal is an artefact of the inventories.** It is strong for Ketsana and weak for Molave, and its
   mechanism is not identified (not revegetation; illumination only partly).
   - L3 leaves aspect out of the main model.
   - The Ketsana ↔ Molave transfer is read knowing that Ketsana lacks scars on north-facing slopes.
2. **The Landsat scars are not added as positives.** The baseline years hold about 1,100 loss patches (clearing),
   nearly half as many as the event years.
3. **C-band SAR over 36 days cannot check landslide scars under this forest.** This is also a warning for L5 / L5b:
   - the DS coherence is near the noise level;
   - the InSAR point coverage on forested slopes will be low.
   - The coverage gate of L5 (10 % of the slope cells) is likely to bind.

### L3 — Susceptibility models (Q1, H1)

- **Models**, the same as `ml.susceptibility`:
  - logistic regression (standardised predictors, odds ratio per standard deviation);
  - random forest and gradient boosting (scikit-learn, balanced class weights).
  - GBM is also run with monotonic constraints on slope and TWI, as a physical plausibility check.
- **Validation:**
  - spatial block cross-validation with blocks of 2 km and 5 km;
  - the block size is checked against the range of the semivariogram of the residuals (Roberts et al. 2017; as in
    blockCV, Valavi et al. 2019); spatial CV itself after Brenning (2005);
  - random cross-validation is reported beside it;
  - metrics: ROC AUC, average precision, Brier score, calibration curve.
- **Transfer between events:**
  - train on the whole Ketsana footprint, test on Molave inside the Ketsana–Molave overlap (878 km², 6,252 Molave
    landslides);
  - then Molave → Ketsana;
  - Podul only as an extra test (small).
- **Interpretation:** permutation importance on the held-out blocks, logistic odds ratios, partial dependence on
  slope, relief, TWI and lithology.
- **Variants:**
  - label variants (a / b / c);
  - with and without the distance to road;
  - with and without the reactivations;
  - slope < 5° negatives in or out.
- **Outputs:** `models/<event>/` (metrics.json, importance, calibration, susceptibility raster 30 m in 5 classes,
  0.2 / 0.4 / 0.6 / 0.8 as in `ml.susceptibility`), `l3_report.md`.
- **Gate:** H1 accepted or not; the choice of model, variant and block size used in L4–L7.

**Outcome (2026-11-02):**
- Spatial AUC, blocks of 2 km: Ketsana 0.74–0.77, Molave 0.73–0.77.
- Blocks of 5 km: Ketsana 0.71–0.73, Molave 0.64–0.70.
- Random CV: 0.76–0.86.
- Residual range: Ketsana 2.9 km, Molave 5.4 km. The 2 km blocks are below it, so the 2 km scores are optimistic.
- The Molave random forest leans on `soil_clay` (SoilGrids, 250 m) and on height. Its AUC falls from 0.77 to 0.66
  between the 2 km and the 5 km blocks, and its map shows the 250 m SoilGrids cells. These are location proxies.
- Transfer on the overlap: Ketsana → Molave 0.705 (logistic), against 0.761 within the event. Molave → Ketsana 0.627,
  against 0.780.
- H1 is not met on the pilot.
- The owner asked for a deeper attempt at a more accurate model, following the direction of Sui et al. (2026): the
  landslides of a later rain event as the test. Hence L3b.

### L3b — Toward an accurate and transferable model (inserted at the L3 gate, 2026-11-02)

Aim: a better model by the *honest* measure. That measure is spatial AUC with blocks no smaller than the residual
range, plus a test on landslides that no model has seen: a later rain event, mapped independently. A higher random-CV
AUC is not a goal.

**L3b.1 — Corrections from the L3 gate**
- **Main metric:** blocks of 5 km (`[models] blocks_m = [5000, 2000]`). The best model and the map are chosen on it.
- **Road distance out of the main model:**
  - its gain is ≤ 0.01;
  - it uses today's OSM roads;
  - it cannot be transferred.
  - It stays as a variant (`with_roads`).
- **New variants:**
  - `no_soil`: without `soil_clay`, `soil_sand`, `soil_thick_m`;
  - `no_height`;
  - `terrain_forest`: terrain and forest only.
  - If a variant's 5 km AUC is not lower (within one sd) or its transfer is better, its layers leave the main model.
- **Transfer:** the within-event AUC on the same cells is also computed for positives ≥ 1,000 m².

**L3b.2 — Terrain at the scale of the slope.** The L2 terrain is cell-scale (30 m). Landslide initiation depends on
the hillslope and its catchment, so these layers are added to `landslide.terrain`:
- `slope_s90`, `profile_curv_s150`, `plan_curv_s150`: slope and curvatures of the DEM smoothed over 90 m and 150 m
  (box filter);
- `hand_m`: height above the nearest drainage, following the D8 path to a cell draining ≥ 0.5 km² (Rennó et al. 2008);
- `upslope_slope_deg`: mean slope of the contributing area (D8, weighted by the cells);
- `spi`: stream power index ln(a · tan β);
- `tpi_1000`, `relief_1000`: position and relief at 1 km.

They enter the same screening (Spearman |ρ| > 0.8 by priority; VIF < 5 for the logistic model). L2 is re-run, and
the L1 labels are unchanged.

**L3b.3 — Pooled model.** Train one model on the Ketsana and Molave samples together:
- each row keeps the forest state before its own event;
- the spatial folds group the same blocks for both events, so that no block is in training for one event and in test
  for the other.
- Reported per event and on the independent test (L3b.5).
- The question: does pooling two events give a model that transfers better than either single-event model?

**L3b.4 — A third event mapped from Sentinel-2 (the direction of Sui et al. 2026).** The new module
`landslide/scars.py` maps new bare scars between two cloud-free composites:
- **Composites:** Sentinel-2 L2A from Earth Search (AWS open data), tiles 48PYB and 48PZB.
  - Per-pixel median of the clear observations (SCL classes 4 and 5) over a dry-season window.
  - Bands: red and NIR at 10 m, SWIR at 20 m.
- **Candidates:**
  - NDVI drop ≥ `dndvi`, NDVI after ≤ `ndvi_post`, NDVI before ≥ `ndvi_pre` (vegetated before);
  - slope ≥ 15°;
  - connected objects of ≥ `min_px` pixels.
  - Object shape: elongation along the fall line, and its position on the slope (the head above the foot).
- **Calibration on Molave:**
  - composites 2020-01-01 → 2020-10-05 (before) and 2020-11-15 → 2021-04-30 (after);
  - the thresholds are chosen to maximise the F1 score of the objects against the Das (2024) Molave polygons inside
    the pilot;
  - object precision, object recall by area class, and the confusion with clearing (Hansen loss in 2021–2022 at the
    same place) are reported.
- **Application to 2025:**
  - composites 2025-01-01 → 2025-10-20 and 2025-11-20 → 2026-04-30, the same thresholds;
  - this covers the record rains of late October – November 2025, Typhoon Kalmaegi, and the reported slides at Trà
    Leng, Trà Linh, Đèo Lò Xo and Phước Thành.
  - Output: `scars/scars_2025.gpkg` (polygons and the mapped extent: clear in both composites).
  - Each object carries its expected precision from the Molave calibration.
- **Reported events:** the news reports of 2015–2026 in and around the pilot (`inventories/landslide/`, with dates
  and the accuracy of their locations) are checked against the 2025 objects. They are also kept for L6.
- Limits:
  - a dry-season composite cannot date a scar within the season;
  - clearing for plantations also removes vegetation, hence the calibration and the precision estimate;
  - scars under 300 m² are missed.

**L3b.5 — Independent test.**
- Every model of L3, L3b.1–L3b.3 is trained on Ketsana, Molave or both, then predicts the 2025 objects:
  - scarp cells (highest cell of each object), against negatives drawn in the mapped extent > 60 m from any object;
  - forest state before 2025 (Hansen to 2024).
- The reported points are scored by the highest susceptibility within their location accuracy, against random points.
  This is a coarse check only.
- This is the test that decides which model is carried into L4–L7. A model that is better in cross-validation but not
  on 2025 is not preferred.

**L3b.6 — Reliability of the inventories and the terrain domain (owner, 2026-11-02).** Vegetation loss is not a
landslide, and Das (2024) is itself an interpretation of uncertain reliability. Both inventories are therefore
cleaned by the same terrain rules, and the models are trained and scored on the slopes only.
- **Measured in the pilot:**
  - Das polygons whose steepest cell is below 15° on both DEMs: Ketsana 3–4 %, Molave 10–11 %;
  - below 20°: Ketsana 8–9 %, Molave 21 %;
  - 20–23 % of the negatives are on slopes below 15°: easy negatives that inflate the AUC.
- **Reliability flag per polygon** (Das and Sentinel-2 alike), from terrain only:
  - *implausible*: the steepest cell < 15° on both GLO-30 and AW3D30, or wholly on a valley floor (every cell's
    HAND < 5 m) within 30 m of a stream draining ≥ 1 km² (bank erosion; a debris flow that runs down to a stream
    from higher up is not flagged);
  - *doubtful*: steepest cell 15–20°, or a vertical drop < 10 m over the polygon (10 m DEM sampling), or a Hansen
    loss in a non-event year at the same place (clearing);
  - *reliable*: the rest.
  - The rules use thresholds of physical plausibility, not the model's continuous layers. The share and the map of
    each class are reported per event.
- **Terrain domain:** positives *and* negatives restricted to cells with slope ≥ 15° (the domain of the warnings).
  The AUC then measures what matters — which slopes fail — not slope against flat land. The full-domain AUC is
  reported beside it.
- **Variants:**
  - main model on the reliable positives in the domain;
  - all positives in the domain;
  - all positives in the full domain (the L3 / L3b setting);
  - `no_forest` and `terrain_only`: without the Hansen layers (owner's question, 2026-11-02). The forest layers
    carry little weight, and their sign is against the physics (Molave: more tree cover, more mapped scars). This
    looks like detection bias: scars are seen in forest and missed in cleared land. Hansen also lags by a year.
    If the 2025 test does not drop without them, they leave the main model and the operational chain needs the
    terrain only.
  - **Outcome (owner, 2026-11-02): the Hansen layers leave the main model.** Without them the 5 km CV hardly
    moves (Ketsana 0.744 → 0.741, pooled 0.753 → 0.728), while the 2025 test rises for every source (pooled
    logistic 0.41 → 0.59 on all objects, 0.69 → 0.83 on the strict set; slope domain, soil still in).
  - The test of 2025 is scored the same way.
- **Aspect, again:** the Sentinel-2 inventory of 2025 does not share Das's mapping. If its reliable scars favour the
  same aspect as Das-Ketsana, aspect is physical and enters the model. If they do not, it stays out (L2b).
- **The Sentinel-2 detector** gets the same terrain plausibility rules on top of NDVI, so that a scar must also
  look like a landslide in the terrain.

**L3b.7 — Dating the objects and matching them with InSAR (owner, 2026-11-02).** A pair of dry-season composites
cannot tell *when* the vegetation went, and the date separates the processes best: swidden and plantation clearing
happen in the dry season (about January–April), landslides in the rain events (October–November). Optical change
alone cannot tell a scar from a clearing; ground motion can. Findings that led here (L3b.6 run):
- inside the slope domain, every model scores the Sentinel-2 objects of 2025 at AUC 0.42–0.55 (all objects, the
  first L3b.6 run with the Hansen layers still in; without them the pooled logistic reaches 0.59 on all objects and
  0.83 on the strict set, L3b.6 outcome above);
- the Molave objects that match no Das polygon score 0.56–0.58 under the Ketsana model, against 0.72 for those that
  match. Most unmatched objects are not landslides.
1. **Date of loss per object (Sentinel-2 time series, cheap).**
   - For every object, the NDVI of each clear scene (not the median) over the two windows.
   - The loss date is bracketed between the last vegetated and the first bare observation.
   - Classes: *in a rain event* (the bracket holds a day above the 95th percentile of daily rain in IMERG and no
     dry-season month), *dry season* (likely clearing), *undated* (bracket too wide).
   - The same for the Das polygons of Molave: it gives an independent date check of Das.
2. **Match with InSAR (Sentinel-1, costly; it shares the stacks of L5 / L5b).**
   - Processing (owner, 2026-11-02; an area rich in distributed scatterers). The owner asked for SBAS with phase
     linking. GeoEyes had no SBAS inversion then: `method = "sbas"` and `[network.sbas]` were configuration fields
     carried over from the old system, not used by any processing code. *Superseded (2026-11-03):* an SBAS engine
     now exists (`processing/sbas/runner.py`, engine `"sbas"` in `controller/pipeline.py`) and was used in the step 2
     outcome below; the PS / DS chain was run beside it. The chain as first planned:
     - phase linking `[phase_linking]` adaptive / `ad`. It estimates from every interferometric pair (the full
       coherence matrix), a superset of an SBAS small-baseline network;
     - `[selection] da_threshold = 0.6` (looser than the 0.42 default);
     - `ds_coherence_min = 0.5`, so that the linked distributed scatterers give points too.
     - A true SBAS inversion (multilooked small-baseline network, SVD) would be a separate development.
   - Window and disk:
     - track 120, IW3, the whole pilot (15.00–15.21 N), 2020-11-01 → 2021-10-31 (one year after Molave);
     - at most two scenes per month, about 24 dates and about 15 GB. *Measured (2026-11-05):* about 10 GB of raw
       bursts (three IW3 bursts per date, ≈ 0.4 GB), plus processing space (the 24-date L5 project took 35 GB:
       stack 21 GB, PS / DS runs 12 GB);
     - the second year of L5b and the post-2025 year follow when the first one is read.
   - Per polygon: the number of persistent and distributed scatterer points, their velocity along the steepest
     descent, the change of coherence and amplitude at the date of loss.
   - *Active* (motion above the stability threshold of `hazard.assess`) supports a landslide.
   - *Stable with points* is neutral: many shallow landslides fail once and stop.
   - *No points* says nothing.
   - The evidence only raises the reliability, never lowers it.
3. **Combined reliability:**
   - terrain (L3b.6) + date (1) + motion (2);
   - Das and Sentinel-2 in one scheme; the share of each class reported per event;
   - the test of 2025 and the season-by-season update of L9 use the objects that pass.
- **Step 1 outcome (2026-11-02, `landslide/dating.py`, `geoeyes landslide dating`; 164–167 scenes per window):**

  | Objects | rain season | dry season | undated |
  |---|---|---|---|
  | Sentinel-2, Molave year, matching Das | 74 % | 6 % | 20 % |
  | Sentinel-2, Molave year, not in Das | 34 % | 39 % | 27 % |
  | Das polygons, Molave | 57 % | 5 % | 38 % |
  | Sentinel-2, 2025 | 9 % (156) | 56 % | 35 % |

  - The dating works: the objects that match Das fall in the rain season.
  - Das-Molave holds few clearings (5 % dry season).
  - About a third of the unmatched Molave objects are rain-season losses, likely landslides Das missed.
  - Most Sentinel-2 objects of 2025 are clearings. The clean test is the 156 rain-dated objects (`rain_dated`
    subset of L3b.5).
- **Step 2 outcome (2026-11-03, project `quangnam_l5b_d120`, T120 IW3, 24 dates 2020-11-04 → 2021-10-24):**
  - SBAS (new engine, looks 4 × 16, refined IRLS, island linking): 23,275 points, almost none on the forested slopes
    (560 within 100 m of a Das polygon). C-band coherence on 60 m cells does not survive a year of tropical forest.
  - PS + DS (phase linking adaptive / `ad`): `da_threshold = 0.6` ran out of memory. Pure speckle has D_A ≈ 0.52, so
    0.6 took 23.5 M of ~52 M pixels; the run used 0.42 with DS (PL temporal coherence ≥ 0.5). Result: 2.93 M points
    (0.78 M DS), about one per 30 m cell even under forest (temporal coherence median 0.80 open, 0.65 forest > 70 %).
  - The velocity spread (p2–p98 ±16 mm/yr) is the same on every land cover and slope class and smooth over a few km
    (2 mm/yr from the 8 nearest points). It does not follow height (r = 0.00). It is a turbulent atmosphere /
    unwrapping background, not slope motion; one year of 24 dates does not average it out.
  - Test on the Das-Molave polygons: local anomaly (v minus the median within ±1.5 km), points with temporal
    coherence ≥ 0.7, projected on the downslope direction. 94 polygons on slopes ≥ 15° have ≥ 3 points; against
    the same polygons shifted 1–3 km (1,775 placebos): AUC 0.53 (p = 0.18), reliable only 0.54 (p = 0.14).
  - **Conclusion:** one year of C-band PS / DS does not separate the Das scars from their surroundings. InSAR stays
    an optional feature (not in the champion). Next tries, if any: a second year (longer series), the ascending
    track (other LOS), or L-band (NISAR / ALOS-2).
- Disk: the 2-year stacks for one burst per track need about 20–30 GB. Before step 2, the L2b stacks are removed or
  the stacks go to another disk. *Corrected (2026-11-05):* two years (~60 dates) of one track are about 25 GB of raw
  bursts (three bursts per date) and, at the L5 rate (35 GB per 24 dates), of the order of 85 GB of processing if
  run in one piece; hence segments, with the raw bursts and stacks of a finished segment deleted.

**Outputs:** `scars/` (composites, objects, `scars.md`), `models/` (re-run with L3b), `l3b_report.md`.

**Gate:**
- the main model and layer set;
- whether the Sentinel-2 inventory is good enough to be a test (object precision on Molave ≥ 0.6);
- whether H1 is met on the 2025 test (AUC ≥ 0.80).

**Outcome (owner, 2026-11-02): closed.**
- **Main model (the champion of O4):** random forest on Ketsana + Molave pooled (the owner chose RF over logistic
  the same day: the linear height term of the logistic model drove the high massifs to ~0 on the map). Reliable
  polygons only, slope domain ≥ 15°, GLO-30, **terrain layers only**: Hansen forest and SoilGrids out, roads and
  aspect out. Logistic regression is the challenger.
- Measures with reliable polygons in the domain, forest out (soil still in), blocks of 5 km:
  - CV: Ketsana 0.740 (RF) / 0.723 (logistic), Molave 0.704, pooled 0.726 / 0.709; residual ranges 2.4 / 2.6 km.
    (The RF baselines quoted later, Ketsana / Molave / pooled, differ by run: 0.738 / 0.691 / 0.725 in L3c is the terrain-only champion of
    `models/l3_report.md`, soil out; 0.736 / 0.710 / 0.725 in C1 is the `improve` harness with 10 draws. Note
    2026-11-05.)
  - Transfer, logistic: Ketsana → Molave **0.728**, against 0.712 within the event on the same cells (the H1
    criterion is met in this direction). Molave → Ketsana 0.661 against 0.734, a drop of 0.073 > 0.05: not met (it
    was 0.627 against 0.780 at L3). *Corrected 2026-11-05:* H1 requires both directions, so transfer is met one way
    only.
  - 2025 test, pooled logistic: 0.59 on all objects, 0.83 on the strict set; without soil 0.60 / 0.84.
- **AW3D30:** a sensitivity variant. It raises the Ketsana CV (0.793) but lowers Molave and the 2025 test.
- **H1 not met:** transfer holds one way only (Ketsana → Molave; Molave → Ketsana drops by 0.073); the spatial AUC
  (0.71–0.74) stays under 0.80. (Was "half met: transfer yes"; corrected 2026-11-05.) The 2025 test is not decisive while
  the Sentinel-2 objects mix landslides and clearings (L3b.7 and the visual check).
- Next: O1 (static layer store over the whole area); L3b.7 InSAR when ASF serves bursts again (with the new SBAS
  engine).

### L3c — Improving the random forest of the susceptibility layer (owner, 2026-11-03)

**Why.** The owner set the rain (L6) aside to improve the champion first: the pooled random forest scores 0.725
(5 km blocks; Ketsana 0.738, Molave 0.691), under the 0.80 of H1. The owner's own study (Truong et al. 2023, Văn Yên,
Yên Bái, RF; reference to be completed) used distances to rivers, faults and roads, which the champion does not have.

**Fixed protocol (every step is scored the same way, against the same baseline).**
- Data: the champion's (pooled, reliable polygons, slope ≥ 15°, terrain only), 10 draws of negatives.
- Scores: out-of-fold AUC on 5 km blocks (pooled and per event); transfer Ketsana → Molave and Molave → Ketsana; the
  2025 test on the strict and rain-dated sets (L3b.5).
- A change is kept when the pooled 5 km AUC rises by ≥ 0.01 with a paired block-bootstrap 95 % interval above 0
  (1,000 resamples of the 5 km blocks), and neither transfer falls by more than 0.01. Smaller gains are reported,
  not adopted.

**Steps (each one ends with a short report; the owner decides before the next).**
1. **C1 — Harness and tuning.** The paired comparison in code (`landslide/improve.py`), then the RF settings tuned
   by nested spatial CV (inner folds on blocks): `max_features` (sqrt, 0.2–0.6), `min_samples_leaf` (1–50),
   `max_depth`, `max_samples` (0.3–1.0), 500–1,000 trees. RF on few thousand rows is often limited by leaf size and
   by the share of features per split; the defaults (300 trees, leaf 5, sqrt) were never tuned.
2. **C2 — Spatial variable selection.** Forward selection scored by the spatial CV (Meyer et al. 2018, 2019): layers
   that help only with random folds describe location (height, relief at 1 km) and hurt transfer. The selected set
   is compared with the full set on the transfer and the 2025 test.
3. **C3 — More terrain.** Layers common in the susceptibility literature and missing here: roughness (TRI) and
   vector ruggedness (VRM); geomorphons (landform classes, Jasiewicz & Stepinski 2013) at 150 / 500 m; convergence
   index; distance to the ridge and to the drainage divide; slope length / LS factor; slope and curvature at more
   scales (60, 90, 150, 300 m). Each family enters as a block and is scored by the protocol.
4. **C4 — Distances to rivers, faults and roads (the owner's set).**
   - Rivers: `dist_stream_*` kept by force (the screen dropped it for Molave), plus mapped rivers when the owner has
     them.
   - Faults: distance and density (1 km) from the owner's 1:200,000 / 1:50,000 geological map if available; fallback
     DEM lineaments plus GEM Global Active Faults, labelled as a proxy.
   - Roads: only the roads that existed before each event (OSM history, or roads traced on the Landsat image of the
     year before). Today's roads stay out (L3 gate).
5. **C5 — Labels and sampling.**
   - Positives: scarp (now) against several cells per polygon (its upper third, weight 1/n per polygon) and the
     centroid. Compared on the shared tests only, since the CV AUC of different positives is not comparable.
   - Negatives: ratio 1 : 1 → 1 : 3 / 1 : 5 with class weights; negatives kept away from unmapped scars (the S2
     objects of L3b.4 not in Das).
6. **C6 — New champion.** The kept changes together, the full L3 run (`geoeyes landslide fit`), map, calibration
   (isotonic on the out-of-fold probabilities, for the five classes of O4), report.

**Outputs:** `models/improve/` (one JSON + markdown per step, the paired comparisons), the new champion in
`models/`.

**Gate:** the new champion layer set and settings; whether H1 (AUC ≥ 0.80) is within reach on terrain alone.

**C1 outcome (2026-11-03, `geoeyes landslide improve`; `models/improve/c1.md`).** Baseline 0.725 (Ketsana 0.736,
Molave 0.710; transfer K → M 0.721, M → K 0.663). Best of 30 settings (leaf 20, `max_features` 0.5, `max_samples`
0.5, 500 trees) 0.731: Δ +0.0056 (95 % +0.004 – +0.008), transfers −0.003 / −0.006; nested estimate 0.730.
Large leaves and subsampling always beat leaf 1 (0.718). **Not adopted** (under the 0.01 rule): the settings are not
the limit.

**C3 outcome (2026-11-03, `--step c3`; `models/improve/c3.md`; RF defaults).**

| added to the 18 champion layers | pooled | Δ (95 %) | K → M | M → K |
|---|---|---|---|---|
| roughness (TRI, VRM 150 / 450 m) | 0.730 | +0.0047 (+0.003 – +0.006) | 0.723 | 0.668 |
| landform (geomorphons 150 / 500 m, convergence) | 0.725 | −0.0006 (−0.002 – +0.001) | 0.720 | 0.672 |
| position (relative position 500 m / 1 km, flow length) | 0.727 | +0.0012 (0.000 – +0.002) | 0.721 | 0.672 |
| erosion (LS factor) | 0.725 | −0.0001 | 0.721 | 0.668 |
| scale (slope 150 / 300 m, curvatures 300 m) | 0.726 | +0.0010 (−0.000 – +0.002) | 0.719 | 0.668 |
| all 18 new layers | 0.733 | +0.0072 (+0.005 – +0.009) | 0.722 | 0.673 |

- No family passes the 0.01 rule; all of them together add +0.007, and the M → K transfer +0.010.
- **Reading:** terrain from a 30 m DEM is saturated near 0.73. The limit is elsewhere: what the layers cannot see
  (geology, faults, land use, roads — C4) and the labels themselves (one scarp cell per polygon, mapping noise — C5).

**C5 outcome (2026-11-03, `--step c5`; `models/improve/c5.md`).** Each variant is trained on its own rows and scored
on the champion rows (the scarp cells and their negatives) on the same 5 km blocks, so the comparison is paired.

| training rows | + / − | pooled | Δ (95 %) | K → M | M → K |
|---|---|---|---|---|---|
| champion (scarp, 1 : 1) | 1,487 / 1,559 | 0.725 | — | 0.721 | 0.663 |
| upper third, weight 1/n | 2,756 / 1,559 | 0.704 | −0.022 (−0.027 – −0.018) | 0.701 | 0.641 |
| centroid | 1,469 / 1,559 | 0.558 | −0.167 | 0.568 | 0.488 |
| whole polygon, weight 1/n | 8,404 / 1,559 | 0.568 | −0.158 | 0.607 | 0.485 |
| negatives 1 : 3 | 1,487 / 4,663 | 0.727 | +0.002 (0.000 – +0.004) | 0.727 | 0.668 |
| negatives 1 : 5 | 1,487 / 7,750 | 0.727 | +0.002 (−0.001 – +0.003) | 0.728 | 0.667 |
| negatives off unmapped Sentinel-2 scars | 1,487 / 1,526 | 0.726 | +0.001 (−0.001 – +0.002) | 0.721 | 0.659 |

- Nothing is kept. The scarp cell is the right positive: a model trained on centroids or whole polygons learns the
  runout and deposit zones and ranks initiation cells near chance (as the sampling comparison of Hussin et al. 2016
  leads one to expect). The scored set is the scarp
  cells, which favours the scarp training by construction; the size of the drop (−0.16) goes far beyond that.
- More negatives and cleaner negatives change nothing: the sampling is not the limit. Only 36 test negatives of
  Molave fall on unmapped scars.
- **L3c so far:** settings (C1), terrain (C3) and labels (C5) are exhausted near 0.73. The remaining lever is the
  information the layers lack: geology and faults (C4).

### L4 — Event rainfall as a predictor (H2)

- **Rain maps** per CHIRPS pixel for October 2020: the totals over 3, 7 and 30 days before 2020-10-29, and the
  maximum daily rain. (Run so, 2026-11-03; the L0 gate's 5 / 10 / 30-day pentad windows apply to L6.)
  - The same with IMERG, to check that the result does not depend on the product.
  - The same for Ketsana (around 2009-09-29) and Podul (around 2013-11-15), for the transfer.
- Add the rain maps to the L3 model. The spatial question is the hard part: about 80 pixels over the Molave hull,
  about 22 over the pilot (corrected 2026-11-05; was "about 120").
- **Null test:**
  - replace the rain by 100 random Gaussian fields with the same variogram;
  - H2 holds only if the gain from real rain exceeds the 95th percentile of the gains from random fields.
  - Blocks of 10 km, so that a block holds whole rain pixels.
- **Outputs:** `l4_report.md` (Δ AUC, null distribution, partial dependence on rain).
- **Gate:** whether the rain is kept in the spatial model, or only used in time (L6–L7).

**Outcome (2026-11-03, `landslide/rain.py`, `geoeyes landslide rain`; report `rain/l4_report.md`).**
- CHIRPS v3 daily `sat`, 10 × 17 pixels over the grid (padded); about 22 over the pilot itself (666 km² at ~30 km²
  per pixel; about 50 in its bounding box), not 120 (corrected 2026-11-05; was "about 65"). Rain
  relative to the event mean (`rain_*_rel`) on the champion data (pooled, reliable, slope ≥ 15°; 3,035 rows per draw,
  5 draws). Both events have the same smooth gradient, rain rising to the north-east (Molave 30 days 438–1,729 mm).
- Out-of-fold AUC, random forest, blocks 10 km / 5 km: terrain 0.720 / 0.726; + relative rain 0.757 / 0.777;
  + rain in mm 0.770 / 0.783; rain alone 0.646. Logistic: 0.696 → 0.713.
- Null test (100 phase-randomised fields, the same variogram): real gain +0.037, null mean +0.021, 95th percentile
  +0.058, p = 0.23. **H2 does not hold**: any smooth field of this size adds about as much, because it stands in for
  location (the blocks of the CV are smaller than the rain gradient).
- **Gate decision (proposed):** rain stays out of the spatial model; it enters in time (L6–L7: thresholds on the
  daily series for the forecast). IMERG was not run (no `icechunk` in the environment; 0.1° gives ~21 pixels, less
  information still: ~21 pixels over the Molave hull, ~6 over the pilot).

### L5 — Pre-event InSAR (Q3, H3)

- **Stacks:**
  - Sentinel-1 track 120 (descending) first, then 55 (ascending).
  - Period 2018-10-01 → 2020-09-30: two years (Barra et al. 2017 require ≥ 1.5 years). It ends before the October
    storms: **no image after 2020-10-05 enters the predictors**.
  - Bursts covering the Molave footprint only (`processing/acquire/s1_bursts.py`).
- **Processing:** distributed scatterers with phase linking (shp_test `ad`, estimator `adaptive`, the project
  defaults). The usual product, then the hazard analysis for the downslope velocity (`hazard/assess.py`: projection
  on the steepest descent, stability threshold, seasonal acceleration).
  - With both tracks: the 2-D decomposition of [`two-geometries-and-soft-soil.md`](two-geometries-and-soft-soil.md).
- **Coverage first:**
  - map the cells (100 m, as the hazard analysis) with ≥ 3 points, split by slope class and forest cover;
  - **if fewer than 10 % of the footprint's slope cells are covered, H3 is tested only on that subset and the result
    is labelled as such.**
- **Features per 30 m cell**, from the 100 m cell that holds it:
  - downslope velocity;
  - `moving` (|v| ≥ 2σ, Barra et al. 2017);
  - temporal coherence and point density;
  - seasonal acceleration (the rain coupling k of `hazard.coupling`);
  - `insar_covered` (0 / 1).
- **Test of H3:**
  - L3 model on the covered cells, with and without the InSAR features;
  - Δ AUC with a paired block bootstrap (1,000 resamples);
  - permutation importance;
  - the fraction of Molave initiation points that were on a "moving" cell, against the fraction of negatives.
- **Quality check, not a predictor:** the post-event coherence loss (one pair across 2020-10-29) over the mapped
  polygons, which says whether the inventory and the InSAR see the same slopes.
- **Outputs:** the InSAR projects, `insar_features.parquet`, `l5_report.md`. Actual names (2026-11-05):
  `projects/quangnam_l5_d120` (pre-event, track 120; the CLI default of `geoeyes landslide l5 --insar`),
  `quangnam_l5b_d120` (post-event, L3b.7 / L5b), `quangnam_l2b_a55` (track 55, L2b change test only); no track 55
  L5 project yet.
- **Gate:** coverage and H3, decided before any InSAR feature enters the combined model.
- **Outcome (2026-11-04, track 120 only; `geoeyes landslide l5`, `insar/l5_report.md`):**
  - Stack: 2019-10-11 → 2020-09-23, 24 images (two per month), 2.90 M points (0.75 M distributed scatterers);
    11.4 months instead of the two years planned (disk): the rain coupling (≥ 12 months) and the acceleration
    (≥ 18 months) cannot be estimated, so the features are rate, `moving`, coherence and point density.
  - Coverage of the Molave footprint's slope cells: **15.4 %** (forest 14.9 %, open 23.9 %): the gate is passed;
    74 of the 544 positive cells (14 %) are covered.
  - On a moving cell: 6.8 % of the positives against 4.8 % of the negatives (difference +0.019, 95 % −0.039 to
    +0.083): no evidence that the Molave landslides started on slopes already moving in the year before.
  - H3 on the covered rows (≈ 180 per draw, 10 draws): AUC 0.725 with the champion layers, 0.720 with InSAR added,
    Δ −0.005 (95 % −0.012 to +0.002). **H3 not supported** on the covered slopes; the test has low power (74
    positives) and says nothing about the forest, where C-band does not see the ground.
  - Decision: no InSAR feature enters the susceptibility model. InSAR stays in the forecast system as the activity
    layer of [`landslide-forecast-system.md` §8.2–8.3](landslide-forecast-system.md#82-update-and-reprocessing-policy-layer-by-layer)
    (forced updates, slopes already moving), not as a predictor. Track 55 and the second year would
    raise the power, not the coverage under the canopy; they are not run unless the owner asks.

### L5b — Post-event activity of the mapped landslides (Q4, H5; added 2026-11-02)

**Starting point.** Sui et al. (2026) classified about 4,200 landslides of the July 2024 Zixing rainstorm as stable /
potential / active / rapid with SBAS-InSAR. The review the owner shared lists five limits, and L5b answers each
one:

| Limit of Sui et al. (2026) | Answer in L5b |
|---|---|
| 1. No model of when or how likely a failure is | the activity classes are tested against later failures (hit rate, false alarms, relative risk) |
| 2. A short, sparse series (27 images in about a year) | 12-day series over two years after the storm (2020-11 → 2022-10), about 60 dates per track, and two tracks; plus the two years before (L5) as the reference |
| 3. One geometry: the LOS mixes horizontal and vertical motion | two tracks (55, 120): 2-D decomposition and the downslope projection of `hazard` |
| 4. Rain and deformation correlate, but that is no mechanism | a distributed-lag model of the downslope rate on the antecedent rain (lags 0–60 days, the coupling k of `hazard.coupling`), with the seasonal cycle removed first |
| 5. Fixed thresholds without independent validation | adaptive thresholds per landslide (2σ of the noise of a stable ring around it), checked against the reports of `vietnam.csv` after 2020 and the new scars of Sentinel-2 / Sentinel-1 |

**Data.**
- The Molave polygons of the pilot.
- The L5 stacks continued for two years after the storm: one stack per track, 2018-10 → 2022-10, processed in two
  segments (before and after the storms).
- Rain: CHIRPS and IMERG, as in L6.
- Later failures:
  - `vietnam.csv` rows within the pilot or within 5 km of it, in 2021–2026; the October–November 2025 storms over
    Quảng Nam are the main test;
  - new scars from Sentinel-2 (NDVI before / after each rainy season) and Sentinel-1 change, as in L2b.

**Steps.**
1. **Points per landslide:**
   - the points inside the polygon grown by 30 m (one cell);
   - a landslide with fewer than 3 points is "not covered", which is reported, not hidden;
   - landslides closer than 100 m are also grouped into clusters: most polygons are about one cell, and many have no
     point.
2. **Metrics per landslide or cluster:**
   - downslope velocity before and after the storm;
   - acceleration (the change of velocity between the halves of each year, and a piecewise trend with a break at
     each big storm);
   - cumulative displacement;
   - their uncertainty from the ring noise.
3. **Rain response:**
   - a distributed lag of the detrended, deseasoned downslope rate on daily rain (lags 0–60 days, smooth lag
     weights);
   - outputs: the gain, the lag of the peak and the share of variance explained, against a model with season only;
   - a GAM-like additive model (splines) first, as the review suggests, before anything more complex.
4. **Classes:**
   - stable: velocity within 2σ of the ring;
   - active: steady motion;
   - accelerating: a significant acceleration after a storm;
   - rain-responsive: a significant lagged gain.
   - The fixed thresholds of Sui et al. (2026) are computed beside them as the baseline.
5. **Validation (H5):** for each class, the share of landslides (or 100 m surroundings) that fail again **after the
   observation window**, 2022-11 → 2026. The classes are fixed before the failures they are tested on, so nothing of
   the future leaks into them. Failures inside the window (2020-11 → 2022-10) are reported apart.
   - Measures: relative risk against "stable", hit rate, false-alarm rate, each with a bootstrap interval.
   - The same for the mean velocity alone and for the fixed thresholds.

**Outputs:** `activity/` with `activity.parquet` (one row per landslide or cluster), `activity.json`, `activity.md`,
series plots of the representative landslides, the class map. Code: `landslide/activity.py`,
`geoeyes landslide activity`.

**Gate:** H5 on the pilot. If it holds, what the web app would show (a layer of activity classes on the `Hazard`
page) is decided with L7.

**Limits.**
- C-band coverage under the forest is poor: most Molave landslides may have no point, and those that do are biased
  towards bare and farmed slopes. The share covered is the first number reported.
- Later failures are few and reported unevenly (§8).
- Two years after the storm cover only two rainy seasons. The lagged rain response is therefore estimated on few
  events, and its intervals will be wide. The window can be extended later if the disk allows.
- Disk: 2018-10 → 2022-10 is about 120 dates × 0.14 GB ≈ 17 GB of raw bursts for track 120. It is processed in two
  segments, deleting the raw bursts of a finished segment, unless more disk is added. *Corrected (2026-11-05):* with
  three bursts per date it is about 120 × 0.4 GB ≈ 50 GB of raw bursts, plus processing (35 GB per 24 dates in L5).
  Before any of it, count the later failures in and near the pilot (H5 power check, review 2026-11-05).

### L6 — Rainfall thresholds (Q2, H4)

*Note (2026-11-05):* the thresholds are to be reconciled with the trigger model of
[`landslide-forecast-system.md`](landslide-forecast-system.md) F5 (fitted on the operational rain product of F2, on
unit-days, leave-one-season-out). See also the review of 2026-11-05 at the top (events per region, bootstrap,
pooling).

- **Events:** `vietnam.csv` rows with day precision.
  - The location error up to 25 km is acceptable here: a CHIRPS pixel is 5.5 km and an IMERG pixel 11 km.
  - Add the three Das dates.
  - Regions:
    - north: the mountains north of 19.5° N;
    - centre: 11–19.5° N, the Trường Sơn and the Central Highlands;
    - the delta (riverbank collapses) is excluded.
- **Daily rain** at each event's pixel: CHIRPS v3 daily 1981→ (climatology) and IMERG Final (check).
- **Rainfall events** (simplified CTRL-T, Melillo et al. 2018):
  - consecutive days with ≥ 1 mm, separated by ≥ 2 dry days;
  - E = event total, D = duration;
  - the event that ends on the landslide day, or the day before (date uncertainty of the reports).
- **Antecedent rain:** A5, A10, A30 (whole pentads, L0 gate) as percentiles of the same pixel's climatology for the
  same calendar window (LHASA uses the 7-day percentile). Changed in code (2026-11-05:
  `landslide/thresholds.py` and the L4 windows of `landslide/rain.py`); L4 results were computed with 3/7/30.
- **Non-landslide sample:**
  - all rainfall events in the rainy season (north May–Oct, centre Sep–Dec) at the same pixels, 2007–2026;
  - excluding those within ±3 days of any reported landslide within 25 km.
- **Thresholds:**
  - E = α D^β at the 5 % non-exceedance probability of the landslide events (frequentist method, Brunetti et al.
    2010), with bootstrap uncertainty of α and β;
  - the ROC-optimal A10 percentile (maximum TSS; A7 in the code so far);
  - per region.
- **Validation:** leave-one-year-out; TSS, hit rate, false alarm rate.
- **Biases, stated in the report:**
  - news reports favour roads and villages and fatal events;
  - GLC dates can be report dates;
  - the non-landslide days include unreported landslides, so the false alarm rate is an upper bound.
- **Daily CHIRPS** needs a new reader beside the monthly one in `ancillary/rainfall.py` (same caching, same
  throttling).
- **Outputs:** `thresholds.json` (per region: α, β, A7, their intervals, TSS), `l6_report.md` (E–D and ROC plots).
- **Gate:** H4; whether the regions are distinct; which threshold enters L7.

### L7 — Combination and hindcast

*Superseded (2026-11-05)* by [`landslide-forecast-system.md`](landslide-forecast-system.md) F5–F7: the combination
is a trigger model on unit-days with ECMWF ENS (51 members) as the forecast rain, and InSAR stays out of the trigger
model until L5 shows skill (it did not, L5 outcome). Kept here as the original plan.

- **Hazard indicator** per 30 m cell and day:
  - the susceptibility class from L3 (and L4 / L5 if accepted) × the rain class from L6 (below threshold, above
    the threshold, above the 95th percentile);
  - combined in an explicit matrix (decision tree) as in LHASA, not multiplied as probabilities: the two models are
    not calibrated on the same population.
- **Hindcast:**
  - **October–November 2020 over the Das footprint:** daily maps; the fraction of Molave initiation points in the
    "high" cells on the days before their (approximate) date. The pooled champion was trained on these points, so
    the susceptibility here must be out-of-fold (5 km blocks) or from a Ketsana-only model; in-sample scores are not
    a hindcast (2026-11-05).
  - **The 2017–2026 events of `vietnam.csv` in central Vietnam outside the footprint:** this is a transfer in space.
    Is the cell of each event "high" on its day, and how often are the cells "high" on days without reports?
- **Outputs:** `hindcast/` (daily rasters, scores), `l7_report.md`.
- **Gate:** whether the indicator is useful enough to put in the web app (`Hazard` page) or stays a research result.

### L9 — Operational forecasting chain (requirement stated by the owner, 2026-11-02)

*Superseded (2026-11-05)* by [`landslide-forecast-system.md`](landslide-forecast-system.md) F8 (operational
chain) and F9 (a shadow season, September–December 2027, before any use). Differences: forecast rain from ECMWF ENS
(51 members), not IFS / GFS; InSAR is not an input of the trigger model until L5 shows skill. The requirements and
the O1–O4 base below still hold.

The aim is not one susceptibility map. It is a forecast that is run again and again: repeatable, and fast enough for
warnings. This shapes every earlier step.

**Requirements**
- **R1 Repeatable.** Every product comes from versioned inputs and a frozen model artefact. The same inputs give the
  same output (seeded models, manifests with the hashes of the inputs and the code version).
- **R2 Fast.** The work is split in two:
  - *offline*: training, the static layers, validation — hours, run rarely;
  - *online*: the forecast — minutes, run every day (every 3 hours in an event).
  - Targets after the rain data arrive: the pilot ≤ 1 min, a province ≤ 5 min.
- **R3 Updated and checked.**
  - After each rainy season, the Sentinel-2 scars of `scars.py` give a new inventory, and every logged forecast is
    scored against it and against the reports (hit rate, false alarms, TSS).
  - A new model replaces the running one only if it is better on that season ("champion / challenger").

**Chain**
1. **Static layer store** per area: *every* grid cell, not only the inventory footprints as in L2.
   - Rebuilt when an input changes: the DEM, the yearly forest (Hansen, or a Sentinel-2 NDVI composite with no
     year of lag), the lithology.
2. **Model artefact** `models/<version>/`:
   - the fitted model, its layer list and a model card (training data, scores of L3b, calibration, seed, code
     version);
   - inference only loads it.
3. **Susceptibility raster** precomputed once per year (forest state) and per model version.
4. **Rain, online, on the rain grid** (~0.1°: a few hundred cells per province, so trivial to compute):
   - observed: GSMaP NRT (hourly, ~4 h latency) or IMERG Early (~4 h);
   - forecast: ECMWF open data (IFS 0.25°, up to 10 days), GFS as backup;
   - indices: the L6 event rain E and duration D, antecedent A7, forecast accumulation over 24 / 72 h.
5. **Combination** (the L7 matrix):
   - the rain class of each rain cell is looked up for every 30 m cell — a vectorised operation, about a second for
     a million cells;
   - the InSAR activity of L5 / L5b (updated every 12 days) raises the class of slopes that are already moving.
6. **Outputs:**
   - a daily cloud-optimised GeoTIFF;
   - a summary per commune (highest class, share of area in the high classes) for the warning bulletins;
   - the `Hazard` page of the web app;
   - a log of every run for R3.

**Consequences for the earlier steps**
- **Predictors must exist everywhere and be updatable.**
  - Today's roads are out (done at L3).
  - No layer may depend on an inventory's footprint.
  - Forest must have an operational source (Sentinel-2 composite) beside Hansen.
- **Calibrated probabilities.** The model feeds a decision matrix, so its probabilities must be calibrated (logistic,
  or GBM / RF with isotonic calibration). L3 reported Brier scores but no check of calibration at the low end; that check
  belongs to the isotonic step of C6 (L3c, planned). (Softened 2026-11-05.)
- **Thresholds on the operational rain product.** CHIRPS final arrives weeks late. L6 calibrates the thresholds on
  the product used online (GSMaP NRT / IMERG Early), or on its long record with a bias check against stations.
  Otherwise thresholds and forecasts are on different scales. CHIRPS stays for the climatology.
- **Code:**
  - split `run_fit` into `fit` (writes the artefact), `map` (applies it) and `forecast` (rain × susceptibility);
  - L2 on the whole area;
  - a compiled priority-flood (numba) for province-scale DEMs.

**Order (owner, 2026-11-02): the offline base first; InSAR and the online rain come last.** The base is built right
after the L3b gate, in four steps. Each is one command, writes a manifest, and is rebuilt only when its inputs change.
- **O1 Static layer store** `<study>/base/static/`:
  - one cloud-optimised GeoTIFF per layer over *every* cell of the area (30 m grid of L1);
  - terrain on GLO-30 and on AW3D30;
  - lithology classes, SoilGrids;
  - forest as a cube: tree cover 2000 and the fraction of each cell lost in each year 2001–2024 (Hansen), so the
    state before any date is a sum, not a new download;
  - the yearly Sentinel-2 dry-season NDVI composite from 2017 (forest without Hansen's lag, and the scar baseline).
  - Code: a compiled priority-flood (numba), so that a province is minutes, not hours.
- **O2 Event catalogue** `<study>/base/events/`:
  - every landslide inventory in one schema: Das 2024, the Sentinel-2 scars of each season (`scars.py`, with
    `strict`), the reported points (date, accuracy);
  - each with its mapped extent, so negatives can always be drawn.
- **O3 Rain archive** `<study>/base/rain/`:
  - daily (and hourly in events) rain over the area from the products used online (GSMaP NRT / IMERG Early, from
    2015);
  - IMERG Final and CHIRPS beside them for the bias check and the climatology.
- **O4 Model artefacts and susceptibility rasters** `<study>/base/models/<version>/`:
  - the model chosen at the L3b gate, fitted on every event of the catalogue, frozen with its card;
  - the susceptibility raster of each year (forest state) as a cloud-optimised GeoTIFF.
- Then, in this order: L4 and L6 on O3 (rain as a predictor, thresholds), L7 (matrix and hindcast); last, L5 / L5b
  (InSAR) and the online forecast. In practice L5 ran on 2026-11-04, before L6 (not yet reported; note 2026-11-05).

**Outputs:** `geoeyes landslide forecast --date … [--lead 72h]`, `forecast/<date>/` (raster, commune table, run
manifest), `l9_report.md` (run times, hindcast of the 2025 season as a dry run).

**Gate:**
- the run times meet R2;
- a full rerun reproduces the same raster (R1);
- the dry run of the 2025 season scores at least as well as the L7 hindcast.

### L8 — Northern Vietnam (blocked)

The model of L3 is not transferred to the north as it is: other lithology (metamorphic and granite of the Hoàng
Liên Sơn, limestone), other rainfall regime. It needs a northern polygon inventory:

1. **Typhoon Yagi (September 2024):** map the landslides from Sentinel-2 change (NDVI before / after, bare-soil
   index, slope mask) and Sentinel-1 amplitude change, as a separate task. It joins the idea of
   [`paper-ideas.md`](../../vi/research/paper-ideas.md) §4.
2. **VIGMR:** the point layer `<PROVINCE>:...diemtruot84` on `canhbaotruotlo.vn:8081`, on request.
3. **Than Uyên** (Lai Châu, Zenodo 19562697): the points of a published model, as a first test.

## 6. Implementation in GeoEyes

**Package `geoeyes.landslide`** (new). It reuses `geoeyes.ml.layers.Grid`, the block cross-validation and the model
code of `geoeyes.ml.susceptibility`, `geoeyes.ancillary.rainfall` and the InSAR products.

| Module | Content | Step |
|---|---|---|
| `inventory.py` | readers of the GeoPackage and the CSV, footprints, area–frequency | L0 |
| `labels.py` | scarp points / upper third / centroid, negatives, seeds | L1 |
| `terrain.py` | DEM derivatives on a `Grid` (slope, curvatures, TPI, TWI, streams) | L2 |
| `predictors.py` | time-aware layers per event (Hansen GFC, GLiM, SoilGrids, roads, rain maps) | L2, L4 |
| `aspect.py` | aspect roses, conditional and illumination models, inventory shift, windward index | L2a |
| `verify.py` | independent check of the inventories: Hansen event-year loss, Sentinel-1 change, size | L2b |
| `scars.py` | new scars between two Sentinel-2 composites, calibrated on an inventory event | L3b |
| `reliability.py` | terrain reliability flags of the polygons (Das and Sentinel-2) | L3b.6 |
| `dating.py` | date of vegetation loss per object from the Sentinel-2 series; persistence | L3b.7 |
| `screening.py` | screening of the Sentinel-2 objects: landslide or not | L3b.7 |
| `improve.py` | L3c harness: paired block-bootstrap comparisons, steps C1, C3, C5 | L3c |
| `rain.py` | event rain maps from CHIRPS v3 daily, null test with phase-randomised fields | L4 |
| `insar.py` | pre-event InSAR features on the study cells, coverage, H3 test | L5 |
| `model.py` | fits, spatial and transfer validation, the 2025 test, bootstrap | L3–L3b |
| `thresholds.py` | daily rain series, rainfall events, E–D and percentile thresholds | L6 |
| `catalogue.py` | event catalogue of dated landslides (forecast system F1) | F1 |
| `satrain.py` | satellite rain archive and product check, GSMaP / IMERG (forecast system F2) | F2 |
| `study.py` | the study file `study.toml` | all |
| `activity.py` (*planned*) | post-event activity per landslide: metrics, rain response, classes, validation | L5b |
| `hindcast.py` (*planned*) | matrix, daily maps, scores | L7 |
| `forecast.py` (*planned*) | static layer store, model artefacts, online rain, daily forecast, run log | L9 / F8 |

(Table brought up to date with `src/geoeyes/landslide/` on 2026-11-05.)

- **CLI:**
  - `geoeyes landslide <action> --study <name>` (default `landslide_central_vn`); actions in the code
    (2026-11-05): `inventory`, `audit`, `labels`, `layers`, `aspect`, `verify`, `scars`, `dating`, `persistence`,
    `reliability`, `fit`, `test`, `improve --step c1|c3|c5`, `rain`, `thresholds`, `l5 [--insar <project>]`,
    `catalogue`, `rainarchive`, `raincheck`, `rainproducts`. Planned: `activity`, `hindcast`, `forecast`;
  - the configuration is in a study file `studies/<name>/study.toml`: inventory, events, footprints, grid, model
    and threshold parameters.
- **Workspace layout:** `<workspace>/studies/landslide_central_vn/` (inputs referenced, every output with a
  `Manifest`, as `io.manifest`). The InSAR stacks stay normal projects (`projects/quangnam_l5_d120`, `quangnam_l5b_d120`,
  `quangnam_l2b_a55`).
- **Tests:** `tests/unit/landslide/`: synthetic polygons on a synthetic DEM (scarp point, negatives at distance),
  thresholds on synthetic rain series, block cross-validation without leakage.
- **Decision record:** ADR-030 (Proposed, 2026-11-01), written with L1.
- The two build scripts of the inventory (`inventories/landslide/build_*.py`) moved to `landslide.inventory` in L1
  (`geoeyes landslide inventory`); the rebuilt files are identical to the earlier ones.

## 7. Parameters and where each default comes from

| Parameter | Default | Reason |
|---|---|---|
| Cell size | 30 m | resolution of GLO-30 and Hansen GFC; median polygon ≈ 1,000–2,200 m² ≈ 1–2 cells |
| Positive sample | highest cell of the polygon | Hussin et al. (2016): the initiation zone, not the runout; confirmed by C5 (L3c) |
| Negative buffer | 60 m (2 cells) | keeps negatives off the edges of mapped polygons, whose position has a few cells of error |
| Positive : negative | 1 : 1, 10 draws | balanced fits; draws give the sampling spread; prevalence restored by prior correction |
| Blocks | 5 km main, 2 km beside (10 km for rain) | Brenning (2005); checked against the residual semivariogram (Roberts et al. 2017; Valavi et al. 2019) |
| Footprint | `near`: within 1 km of a mapped landslide, gaps < 3 km closed, flats > 1 km² removed (L0 gate) | the mapping extents are not published; sensitivity: concave hull (ratio 0.3) + 1 km |
| Stream threshold | 0.5 km² | a common channel initiation area for small mountain catchments; sensitivity 0.1 / 1 km² |
| InSAR period | 2018-10-01 → 2020-09-30 (L5); 2020-11-01 → 2022-10-31 (L5b) | two years each (owner's decision; Barra et al. 2017 require ≥ 1.5 years); L5 ends before the October 2020 storms |
| InSAR moving | \|v\| ≥ 2σ, ≥ 3 points per cell | Barra et al. (2017); Tomás et al. (2019); same as `hazard` |
| InSAR coverage gate | 10 % of slope cells | below it, H3 is answered for the covered subset only |
| Rain event separation | 2 dry days (< 1 mm) | simplified CTRL-T (Melillo et al. 2018) |
| Antecedent windows | 5, 10, 30 days | whole CHIRPS pentads (L0 gate) |
| Threshold | 5 % non-exceedance (E–D); max TSS (A10) | Brunetti et al. (2010); Kirschbaum & Stanley (2018) |
| Exclusion window | ±3 days, 25 km | report date uncertainty and location accuracy of the reports |
| Classes | 0.2 / 0.4 / 0.6 / 0.8 | as `ml.susceptibility` |

## 8. Risks and limitations

- **Unknown mapping extents** (the main risk). Negatives drawn where nobody looked teach the model that unmapped
  slopes are stable. Mitigation: the conservative `near` footprint (L0 gate), a sensitivity test with the concave
  hull + 1 km (L3), and a check by eye against the images of each event. The negatives come from the `near`
  footprint only, so the calibration and the classes hold only in the sampled domain (review 2026-11-05).
- **The Molave date.** The set probably mixes several October 2020 storms, so its event rain is a 30-day total, not
  one storm.
- **Time of the predictors.**
  - The DEM (2011–2015) is before Molave but after Ketsana, and spans Podul (2013): Ketsana and Podul scars may be
    in the DEM.
  - The OSM roads are from today.
  - Both are tested as variants, not ignored.
- **Coarse geology.** GLiM gives few classes over the footprint, so lithology may come out as unimportant only
  because it is poorly mapped. The VIGMR 1:200,000 map would change this.
- **Rainfall as a spatial proxy.** About 80 CHIRPS pixels over the Molave hull (about 22 over the pilot) are too few to separate rain from
  location; hence the null test (L4).
- **InSAR on vegetated slopes.**
  - C-band loses coherence under the canopy, so the covered slopes are biased towards bare and agricultural land.
  - H3 is therefore answered only for the covered slopes, and not for the forest.
  - L-band (ALOS-2, NISAR) would test the forest; it is not in this plan.
- **Reporting bias of `vietnam.csv`.** Events near roads and with victims are over-represented; the north and the
  centre are not sampled the same way. The thresholds are thresholds of *reported* landslides.
- **Transfer.** A model of three storms in Quảng Nam – Kon Tum describes those slopes and those storms; it is not a
  national map.

## 9. References

Every DOI below was checked on Crossref or DataCite on 2026-11-01; those added on 2026-11-05 (Hussin, Jasiewicz,
Meyer, Pelletier, Roberts, Valavi) on Crossref that day.

- Alvioli, M., Marchesini, I., Reichenbach, P., Rossi, M., Ardizzone, F., Fiorucci, F., Guzzetti, F. (2016).
  Automatic delineation of geomorphological slope units with r.slopeunits v1.0 and their optimization for landslide
  susceptibility modeling. *Geoscientific Model Development* 9, 3975–3991. https://doi.org/10.5194/gmd-9-3975-2016
- Brenning, A. (2005). Spatial prediction models for landslide hazards: review, comparison and evaluation. *Natural
  Hazards and Earth System Sciences* 5, 853–862. https://doi.org/10.5194/nhess-5-853-2005
- Brunetti, M. T., Peruccacci, S., Rossi, M., Luciani, S., Valigi, D., Guzzetti, F. (2010). Rainfall thresholds for
  the possible occurrence of landslides in Italy. *Natural Hazards and Earth System Sciences* 10, 447–458.
  https://doi.org/10.5194/nhess-10-447-2010
- Das, R. (2024). Mapped landslides for Typhoon Ketsana, Molave and Tropical Storm Podul in central Vietnam
  [dataset]. Zenodo. https://doi.org/10.5281/zenodo.15596033
- Fell, R., Corominas, J., Bonnard, C., Cascini, L., Leroi, E., Savage, W. Z. (2008). Guidelines for landslide
  susceptibility, hazard and risk zoning for land use planning. *Engineering Geology* 102, 85–98.
  https://doi.org/10.1016/j.enggeo.2008.03.022
- Funk, C., et al. (2015). The climate hazards infrared precipitation with stations — a new environmental record for
  monitoring extremes. *Scientific Data* 2, 150066. https://doi.org/10.1038/sdata.2015.66
- Guzzetti, F., Peruccacci, S., Rossi, M., Stark, C. P. (2008). The rainfall intensity–duration control of shallow
  landslides and debris flows: an update. *Landslides* 5, 3–17. https://doi.org/10.1007/s10346-007-0112-1
- Guzzetti, F., Mondini, A. C., Cardinali, M., Fiorucci, F., Santangelo, M., Chang, K.-T. (2012). Landslide
  inventory maps: new tools for an old problem. *Earth-Science Reviews* 112, 42–66.
  https://doi.org/10.1016/j.earscirev.2012.02.001
- Hansen, M. C., et al. (2013). High-resolution global maps of 21st-century forest cover change. *Science* 342,
  850–853. https://doi.org/10.1126/science.1244693
- Hartmann, J., Moosdorf, N. (2012). The new global lithological map database GLiM: a representation of rock
  properties at the Earth surface. *Geochemistry, Geophysics, Geosystems* 13, Q12004.
  https://doi.org/10.1029/2012GC004370
- Holland, G. J. (1980). An analytic model of the wind and pressure profiles in hurricanes. *Monthly Weather Review*
  108, 1212–1218. https://doi.org/10.1175/1520-0493(1980)108<1212:AAMOTW>2.0.CO;2
- Hussin, H. Y., Zumpano, V., Reichenbach, P., Sterlacchini, S., Micu, M., van Westen, C., Bălteanu, D. (2016).
  Different landslide sampling strategies in a grid-based bi-variate statistical susceptibility model.
  *Geomorphology* 253, 508–523. https://doi.org/10.1016/j.geomorph.2015.10.030
- Jasiewicz, J., Stepinski, T. F. (2013). Geomorphons — a pattern recognition approach to classification and
  mapping of landforms. *Geomorphology* 182, 147–156. https://doi.org/10.1016/j.geomorph.2012.11.005
- Kirschbaum, D., Stanley, T. (2018). Satellite-based assessment of rainfall-triggered landslide hazard for
  situational awareness. *Earth's Future* 6, 505–523. https://doi.org/10.1002/2017EF000715
- Knapp, K. R., Kruk, M. C., Levinson, D. H., Diamond, H. J., Neumann, C. J. (2010). The International Best Track
  Archive for Climate Stewardship (IBTrACS). *Bulletin of the American Meteorological Society* 91, 363–376.
  https://doi.org/10.1175/2009BAMS2755.1
- Liu, C., Luo, W., Chung, H., Yin, H., Yan, K. (2018). Influences of the shadow inventory on a landslide
  susceptibility model. *ISPRS International Journal of Geo-Information* 7, 374. https://doi.org/10.3390/ijgi7090374
- Malamud, B. D., Turcotte, D. L., Guzzetti, F., Reichenbach, P. (2004). Landslide inventories and their statistical
  properties. *Earth Surface Processes and Landforms* 29, 687–711. https://doi.org/10.1002/esp.1064
- Melillo, M., Brunetti, M. T., Peruccacci, S., Gariano, S. L., Roccati, A., Guzzetti, F. (2018). A tool for the
  automatic calculation of rainfall thresholds for landslide occurrence. *Environmental Modelling & Software* 105,
  230–243. https://doi.org/10.1016/j.envsoft.2018.03.024
- Meyer, H., Reudenbach, C., Hengl, T., Katurji, M., Nauss, T. (2018). Improving performance of spatio-temporal
  machine learning models using forward feature selection and target-oriented validation. *Environmental Modelling &
  Software* 101, 1–9. https://doi.org/10.1016/j.envsoft.2017.12.001
- Meyer, H., Reudenbach, C., Wöllauer, S., Nauss, T. (2019). Importance of spatial predictor variable selection in
  machine learning applications — moving from data reproduction to spatial prediction. *Ecological Modelling* 411,
  108815. https://doi.org/10.1016/j.ecolmodel.2019.108815
- Pelletier, J. D., Broxton, P. D., Hazenberg, P., Zeng, X., Troch, P. A., Niu, G.-Y., Williams, Z., Brunke, M. A.,
  Gochis, D. (2016). A gridded global data set of soil, intact regolith, and sedimentary deposit thicknesses for
  regional and global land surface modeling. *Journal of Advances in Modeling Earth Systems* 8, 41–65.
  https://doi.org/10.1002/2015MS000526
- Reichenbach, P., Rossi, M., Malamud, B. D., Mihir, M., Guzzetti, F. (2018). A review of statistically-based
  landslide susceptibility models. *Earth-Science Reviews* 180, 60–91. https://doi.org/10.1016/j.earscirev.2018.03.001
- Rennó, C. D., Nobre, A. D., Cuartas, L. A., Soares, J. V., Hodnett, M. G., Tomasella, J., Waterloo, M. J. (2008).
  HAND, a new terrain descriptor using SRTM-DEM: mapping terra-firme rainforest environments in Amazonia. *Remote
  Sensing of Environment* 112, 3469–3481. https://doi.org/10.1016/j.rse.2008.03.018
- Roberts, D. R., Bahn, V., Ciuti, S., Boyce, M. S., Elith, J., Guillera-Arroita, G., Hauenstein, S., Lahoz-Monfort,
  J. J., Schröder, B., Thuiller, W., Warton, D. I., Wintle, B. A., Hartig, F., Dormann, C. F. (2017).
  Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*
  40, 913–929. https://doi.org/10.1111/ecog.02881
- Segoni, S., Piciullo, L., Gariano, S. L. (2018). A review of the recent literature on rainfall thresholds for
  landslide occurrence. *Landslides* 15, 1483–1501. https://doi.org/10.1007/s10346-018-0966-4
- Stanley, T., Kirschbaum, D. B. (2017). A heuristic approach to global landslide susceptibility mapping. *Natural
  Hazards* 87, 145–164. https://doi.org/10.1007/s11069-017-2757-y
- Steger, S., Brenning, A., Bell, R., Glade, T. (2016). The propagation of inventory-based positional errors into
  statistical landslide susceptibility models. *Natural Hazards and Earth System Sciences* 16, 2729–2745.
  https://doi.org/10.5194/nhess-16-2729-2016
- Steger, S., Brenning, A., Bell, R., Glade, T. (2017). The influence of systematically incomplete shallow landslide
  inventories on statistical susceptibility models and suggestions for improvements. *Landslides* 14, 1767–1781.
  https://doi.org/10.1007/s10346-017-0820-0
- Sui, B., Fang, Y., Li, D., Zhang, Z., Chen, L., Du, D., Wang, T. (2026). Quantitative stability assessment of
  landslides following the 2024 Zixing rainstorm using time-series InSAR. *Remote Sensing* 18, 929.
  https://doi.org/10.3390/rs18060929
- Truong et al. (2023), random forest susceptibility, Văn Yên (Yên Bái): reference to be completed.
- Valavi, R., Elith, J., Lahoz-Monfort, J. J., Guillera-Arroita, G. (2019). blockCV: an R package for generating
  spatially or environmentally separated folds for k-fold cross-validation of species distribution models. *Methods
  in Ecology and Evolution* 10, 225–232. https://doi.org/10.1111/2041-210X.13107
- Zevenbergen, L. W., Thorne, C. R. (1987). Quantitative analysis of land surface topography. *Earth Surface
  Processes and Landforms* 12, 47–56. https://doi.org/10.1002/esp.3290120107
- InSAR and slow landslides (Barra et al. 2017; Cigna et al. 2013; Ciampalini et al. 2016; Handwerger et al. 2013;
  Lacroix et al. 2020; Tomás et al. 2019): see [`rainfall-insar-hazard.md`](rainfall-insar-hazard.md) §10.
