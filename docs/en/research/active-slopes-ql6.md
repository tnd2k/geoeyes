# Active slopes along QL6 — automatic delineation from InSAR: design and work plan

> Plan, 2026-11-13. Owner's question: *can the ql6_km124_141 output delineate the slopes at risk of sliding
> automatically?* Answer given the same day: partly — InSAR delineates **slopes that move slowly and are seen by the
> satellite**; it says nothing where it does not see, and rapid rock / cut-slope failures often move too little
> beforehand. The plan builds a product that states both: *active* slopes from InSAR, and *not measured* slopes from
> geometry and terrain, checked against the surveyed landslides. Steps Q0–Q7, each ending with the owner's review
> (memory: plan before steps). Q1 started on 2026-11-13.

## Contents

1. [Where we stand](#1-where-we-stand)
2. [What the product is, and what it is not](#2-what-the-product-is-and-what-it-is-not)
3. [Method](#3-method)
4. [Acceptance criteria](#4-acceptance-criteria)
5. [Work plan Q0–Q7](#5-work-plan-q0q7)
6. [Risks and limits](#6-risks-and-limits)
7. [References](#7-references)

## 1. Where we stand

- **Data.** Project `ql6_km124_141`: S1 asc 128 frame 64, 103 dates 2023-01..2026-10, PSDS (phase linking
  [3, 9], DA 0.6, DS coherence 0.5, ERA5, GLO-30), product v7 (`scla_deramp = auto` with the planar trend removed):
  ~1.24 M points. Descending track 91 frame 522 declared, not processed before 2026-11-13.
- **Slope analysis so far.** `hazard.terrain`: slope and steepest descent from GLO-30, LOS sensitivity to a motion
  down the slope, visibility (slope ≥ 10°, |sensitivity| ≥ 0.3, no layover / shadow), downslope rate. Web map:
  velocity kind "slope". A scratch analysis (`analyses/slope_v7_zones.csv`) gave 18 zones of ≥ 10 points with a
  downslope rate ≥ 5 mm/yr; all are weak (5–8 mm/yr, ~2× the noise).
- **Ground truth.** VIPHAP survey of 2026-06-03 (`inventories/landslide/surveys/ql6_viphap_2026.geojson`): 7 sites
  Km118+600..147+450, 4 of them on the analysed stretch (Km124+300, 125+940, 128+400, 129+500). Official km = OSM
  chainage + 14.2 km.
- **First check (2026-11-13), zones made without looking at the survey.** Distance from each surveyed site to the
  nearest zone: 30 m (Km129+500), 98 m (Km124+300), 210 m (Km128+400), 617 m (Km125+940). Within 100 m: 2 of 4 sites
  against 7 % of random points on the road (binomial p ≈ 0.03); within 300 m: 3 of 4 against 34 %. A real signal,
  four sites: not proof.

## 2. What the product is, and what it is not

**It is** a map of slope units along the road in four classes, each with its reasons:

| Class | Meaning |
|---|---|
| **Active** | InSAR measures a downslope motion above the noise (§3.4), on enough points, consistent in time and, where both tracks see the slope, in both geometries |
| **Not measured, susceptible** | steep or cut slope (§3.5) that neither track sees (layover, shadow, motion across the LOS) or that has no coherent point (forest) |
| **Measured, stable** | seen, enough points, no motion above the noise |
| **Low** | gentle slope, away from cuts |

**It is not** a forecast of failure, a time of failure or a run-out. Rapid failures (rock fall, cut-slope collapse)
can occur in "measured, stable" units. The time dimension belongs to the forecast system
([`landslide-forecast-system.md`](landslide-forecast-system.md)); this product can later feed it as a modifier.

## 3. Method

### 3.1 Two geometries (Q1)

The descending track 91 (bursts 091_194267/194268 IW3, ~110 dates) is processed with the settings of asc v7
(PSDS, same phase-linking window, ERA5, `scla_deramp auto`, geolocation off). The two tracks see different slopes:
Km124+300 (aspect 253°) gives 21 % of a downslope motion to the ascending LOS and 78 % to the descending one.
QC: residual ramp, geolocation against the amplitude / DEM simulation, offset between tracks on common stable ground.

### 3.2 Visibility (Q2)

For every 30 m terrain cell and each track: LOS sensitivity to a downslope motion, local incidence (layover /
shadow), and the density of coherent points. The union gives the "seen by asc / desc / both / neither" map; a unit
seen by neither cannot be "measured, stable".

### 3.3 Downslope rate from two tracks (Q3)

Points of both tracks are binned on a common grid (50 m cells, the slope-unit scale of the road cuts). Assuming motion
along the steepest descent (one unknown, d), each track gives v_LOS = s · d (s = sensitivity): with both, d is a
weighted least-squares estimate and the misfit tests the assumption (a large misfit = motion not along the slope, or
an artefact). With one track, d = v_LOS / s where |s| ≥ 0.3, flagged "one geometry". The vertical / east-west
decomposition (`geoeyes decompose`) is computed too, for the report.

### 3.4 Active zones (Q4)

Following the active-deformation-area method (Barra et al. 2017; Tomás et al. 2019):
- **noise**: σ of d on visible, coherent cells of gentle slope away from the road (or Mai Chau town), per track;
- **threshold**: |d| ≥ k·σ with k fixed in Q0 (proposed 2), and the cell's own uncertainty below the threshold;
- **clustering**: neighbouring active cells (≤ 50 m) joined; a zone needs ≥ N points (proposed 10) and ≥ 3 cells;
- **quality index** 1–4: noise, isolation, agreement of the two tracks, time-series consistency;
- **time series**: linear / accelerating / step (the classes of `geoeyes behaviour`), the date of a change.

Output: `zones.gpkg` (polygon, area, median d with its interval, points, geometries that see it, quality, behaviour,
official km, distance to the road).

### 3.5 Static layer (Q5)

At the same cells: slope, cut slopes (road buffer 50 m and slope ≥ 35°, or a sharp break of slope beside the road),
curvature, upslope area, land cover (WorldCover), geology (GLiM; the 1:50,000 map if obtained), and the
susceptibility of the landslide study ([`landslide-susceptibility.md`](landslide-susceptibility.md)) where it
transfers. These set "susceptible" for the units InSAR does not measure.

### 3.6 Combination (Q5)

The four classes of §2 from (visible, active zone, susceptible). No weights are tuned on the survey: four sites cannot
fit a model.

## 4. Acceptance criteria

Fixed now, before Q4 is run; reported with the number of sites behind each.

| # | Criterion | Target |
|---|---|---|
| Q-A1 | Surveyed sites on the stretch in an "active" or "not measured, susceptible" unit (within 100 m) | ≥ 3 of 4, and above chance (permutation of the sites along the road, p < 0.05) |
| Q-A2 | Share of the road length flagged "active" | ≤ 15 % (an alert that covers the whole road says nothing) |
| Q-A3 | "Active" zones confirmed by a field or image check (a sample of the zones not in the survey) | ≥ 50 % with visible signs (cracks, scarps, tilted walls, repairs) |
| Q-A4 | Both tracks agree where both see a zone (sign and magnitude within 2σ) | ≥ 70 % of such zones |
| Q-A5 | Reproducible: same inputs give the same zones; run time on the stretch | yes; ≤ 10 min after the products exist |

If a criterion fails, the report says so and the product is issued with that limit stated, not tuned until it passes.

## 5. Work plan Q0–Q7

| Step | Content | Output | Gate |
|---|---|---|---|
| **Q0** Baseline | Freeze §4 and the thresholds of §3.4; inventory audit (VIPHAP 7 sites with type and date; add the news catalogue of the forecast study, Sentinel-2 scars after the 2025 rains, owner's records); chance level by permutation | `q0_baseline.md` | owner signs §4 |
| **Q1** Descending | Track 91 PSDS as asc v7; QC (ramp, geolocation, offsets between tracks) | product desc v1, QC note | QC passes |
| **Q2** Visibility | asc / desc / both / neither map at 30 m; points per cell | `visibility.tif`, share of the stretch seen | owner review |
| **Q3** Downslope rate | common 50 m grid; two-track least squares with misfit; one-track fallback; decomposition | `downslope.gpkg` | misfit map reviewed |
| **Q4** Active zones | noise, threshold, clusters, quality index, behaviour | `zones.gpkg`, `q4_zones.md` | Q-A1, Q-A2, Q-A4 |
| **Q5** Static layer and classes | cut slopes, terrain, land cover, geology, susceptibility; the four classes | `slope_units.gpkg` | owner review of the map |
| **Q6** Verification | Q-A1..A4 with intervals; field / image check list of the zones not surveyed; sensitivity to k and N reported (not tuned) | `q6_verification.md` | owner decides on use |
| **Q7** Automation | `geoeyes slopes <project>` (zones + classes + report), web layer, update with new dates; then the whole corridor (corridor processing K2–K3) | command, docs | A5, owner |

## 6. Risks and limits

- **Rapid failures.** Rock falls and cut-slope collapses often give no measurable precursor at C band; "measured,
  stable" never means safe. Printed on every map.
- **Forest.** 86 % tree cover: many slopes have no coherent point → "not measured", not "stable".
- **Geometry.** One track sees only part of a slope's motion (21 % at Km124+300 ascending); slopes along the track
  direction are poorly seen by both.
- **Few validation sites.** Four sites on the stretch: Q-A1 has little power; Q-A3 (field / image check) carries the
  weight, and more inventory (Q0) is the way to stronger tests.
- **Ramps and troposphere.** Weak zones (5–8 mm/yr) are close to residual ramp and stratified delay over ~900 m of
  relief; the noise σ of §3.4 is measured after them, and the two-track agreement (Q-A4) guards against them.
- **Disk.** Descending raw ~32 GB plus its stack; D: had 112 GB free on 2026-11-13.

## 7. References

Cited from memory on 2026-11-13; volume and pages to be checked on Crossref in Q0.

- Barra, A. et al. (2017). A methodology to detect and update active deformation areas based on Sentinel-1 SAR images.
  *Remote Sensing* 9(10), 1002.
- Tomás, R. et al. (2019). Semi-automatic identification and pre-screening of geological–geotechnical deformational
  processes using persistent scatterer interferometry datasets. *Remote Sensing* 11(14), 1675.
- Notti, D. et al. (2014). A methodology for improving landslide PSI data analysis. *International Journal of Remote
  Sensing* 35(6), 2186–2214 (R-index, visibility of slopes).
- Cascini, L. et al. (2010). Advanced low- and full-resolution DInSAR map generation for slow-moving landslide
  analysis at different scales. *Engineering Geology* 112, 29–42.
