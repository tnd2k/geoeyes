# Kinds of motion and risk to buildings

Status: v1 implemented 2026-10-26.
Code: `geoeyes.ml.behaviour` (`geoeyes behaviour`), `geoeyes.ml.risk` (`geoeyes risk`), `geoeyes.api.behaviour`.
Web app: layers "Kind of motion", "Date of change" and "Risk to buildings" on the Thematic analysis page;
Principles, chapter 3.
Related: [rainfall-insar-hazard.md](rainfall-insar-hazard.md) (the zoning these analyses start from; step R6
"from hazard to risk" of its research plan).

## Contents

1. [Question](#1-question)
2. [Kinds of motion](#2-kinds-of-motion)
3. [Risk to buildings](#3-risk-to-buildings)
4. [First results](#4-first-results)
5. [Limitations](#5-limitations)
6. [Research sequence](#6-research-sequence)
7. [References](#7-references)

## 1. Question

The hazard zoning rates each 100 m cell by one number, its rate, crossed with what the motion can do to buildings.
Two questions stay open:

- **Q1. How does each place move?** A steady rate, a recent onset, a seasonal cycle and a motion that fades all
  call for different actions, yet they can share one rate.
- **Q2. What does the hazard mean for what stands on the ground?** A fast-sinking empty field and a fast-sinking
  school have the same hazard and very different risks.

## 2. Kinds of motion

### 2.1 Models

Every cell's series (the series of the zoning, `cells_ts.npy`, GeoEyes sign) is fitted by least squares with seven
models, each with a physical reading:

| Class | Model | Reading |
|---|---|---|
| stable | d = a | no motion beyond the stability threshold of the zoning |
| steady | d = a + b·t | constant rate: aquifer compaction, creep |
| seasonal | d = a + b·t + c·sin 2πt + e·cos 2πt | annual cycle on the trend: recharge and pumping, thermal dilation |
| speeding | d = a + b·t + c·t², \|rate\| growing | the motion grows |
| slowing | d = a + b·t + c·t², \|rate\| fading | consolidation after a load |
| onset | d = a + b·t + h·(t − t₀)₊ | a change of rate at t₀: a new load, a new well, the end of works |
| step | d = a + b·t + δ·H(t − t₀) | a jump at t₀: a sudden event, or an unwrapping error |

The approach follows the automated classification of PS time series by Berti et al. (2013), with model selection
in place of their sequence of statistical tests.

- Speeding and slowing compare the size of the rate at the end with the size at the start, so they follow the
  cell's own motion in either direction.
- The seasonal model needs about a year of data (`min_span_seasonal_yr` = 0.9).

### 2.2 Model selection

A richer model always fits a little better. The models are compared with the Bayesian information criterion
(Schwarz 1978):

    BIC = n · ln(RSS / n) + k · ln n

- A richer model is kept only when it lowers the BIC by at least `min_delta_bic` = 6 compared with the straight
  line, the threshold Kass & Raftery (1995) call strong evidence.
- Otherwise the cell is steady, or stable when its linear rate is below the stability threshold of the zoning
  (max(2 mm/yr, 2σ)).
- For the onset and the step, the epoch of the change is a parameter (k counts it). Every epoch is tried, with
  `edge_epochs` = 3 epochs kept on each side.
- All cells are fitted at once (vectorised least squares): a few tenths of a second for 45,000 cells.

**Caveat (2026-11-05): ΔBIC = 6 overstates the evidence for onsets and steps.** (`ml/behaviour.py`, ~l. 103–118.)
- The change epoch is grid-searched over every epoch and charged as one ordinary parameter (k = 4). A searched
  change point is a non-regular parameter: the best of ~n − 6 fits lowers the RSS more than one free parameter does,
  so the BIC penalty is too small and onsets and steps are favoured.
- The BIC assumes independent residuals. The atmosphere left in the series is correlated in space and time, so the
  effective n is smaller than the number of epochs.
- "Strong evidence" in Kass & Raftery's sense does not hold under either point. The classes are indicative.

Plan: calibrate the ΔBIC threshold per model on null simulations (steady series plus noise with the series' own
spatial and temporal correlation, e.g. from stable cells), or by permutation of the residuals, so that the
false-alarm rate of each class is known.

### 2.3 Changes shared by many cells

The ground rarely changes everywhere on one date. One acquisition with a strong atmosphere, or an unwrapping
error, shifts many cells together. When the changes (onset or step) on one date reach both 5 times the median per
date (and at least 20 cells) and a quarter of all changes, the date is flagged
(`shared_change_dates`, with a warning). Its onsets and steps are read as data problems first. The web app does
not use them as examples.

### 2.4 Outputs

`analyses/behaviour/<product>/`:

- `behaviour.parquet`: one row per cell of the zoning, in the same order. Columns: class, date of change, rates
  before and after, acceleration, seasonal amplitude, jump, ΔBIC.
- `behaviour_fit.npy`: the kept model per cell.
- `behaviour.json`: counts, changes by month, flagged dates, warnings.

## 3. Risk to buildings

Risk crosses the hazard with what is exposed and how much it suffers (UNDRR 2016 terminology).

### 3.1 Hazard H (0–4)

- **From the building's own InSAR points** (geoeyes buildings), when it holds at least `min_points_own` = 5
  persistent scatterers on flat ground:
  - intensity from its vertical rate, with the classes of the zoning;
  - damage potential S = the larger of the class of its own angular distortion β (1/500, 1/300, 1/150) and the class
    of its own rigid tilt (`tilt_breaks` 1/500, 1/250, 1/100), each when significant; else the S of its cell;
  - the hazard matrix of the zoning.
- **From its analysis cell** otherwise: the level of the cell that holds its centroid.

**Fixed in code (2026-11-05): β is now an angular distortion, tilt is classed apart.** Before, the building β was
the gradient of the plane fitted to its PS (a rigid-body tilt) and the cell β a ground slope, both classed with the
angular-distortion limits of Bjerrum (1963) and Skempton & MacDonald (1956), which a uniform tilt does not reach
(Burland & Wroth 1974; Boscardin & Cording 1989). Now:
- *Building* (`ml/buildings.py::tilt_and_distortion`): the plane gives `tilt_10yr`; β (`beta_10yr`) is the P90 of the
  relative rotation |r_i − r_j| / d_ij of the plane residuals over PS pairs ≥ 5 m apart, × 10 yr, kept only when it
  is ≥ 2 × the P90 that PS noise alone gives (σ from `vel_std_mm_yr`, else the nearest-neighbour scatter).
- *Risk* (`ml/risk.py`): β classed by `distortion_breaks`, tilt by `tilt_breaks` = 1/500, 1/250, 1/100 (Burland 1995:
  tilt noticeable beyond ~1/250, serious near 1/100); S = the larger.
- *Cell β* (`hazard/zoning.py::angular_distortion`): the change of slope across the cell, max of the second
  difference |v₊ − 2v + v₋| over the 4 directions per cell spacing, × T; a uniform ground slope gives 0.

The result tables in this document (§4) were computed with the old method and need a rerun. The classes stay
screening classes, not a structural assessment.
- **Not assessed:** buildings outside every cell.
- Each building carries its `source`.

### 3.2 Exposure E (1–3)

- Gross floor area = footprint × floors, a proxy of the people and value inside.
- Floors come from the Overture height (3 m a floor). Without a height, the median number of floors of the buildings
  of the area that have one is used.
- Heights missing in Overture are filled (2026-11-05, working tree, not yet committed) from the GlobalBuildingAtlas
  footprint that holds the building's centroid (Source Cooperative; `gba_heights` = true by default, needs the
  open-data cache; `opendata/coop.py::fill_heights`). `risk.parquet` gains `height_source` (overture / gba /
  assumed). The §4 results predate this.
- E1 < 300 m² ≤ E2 < 3,000 m² ≤ E3.

### 3.3 Vulnerability V (1–3)

The structural type and the foundations, which drive the fragility of a building (Peduto et al. 2017), are not in
open data. The proxies are size and slenderness:

- **V3:** height ≥ 21 m (7 floors), or length (√footprint) ≥ 30 m. Long buildings span more differential
  settlement; tall ones turn a small tilt into a large offset at the top (Burland & Wroth 1974).
- **V1:** small (< 60 m²) low buildings.
- **V2:** the others.

### 3.4 Consequence and risk

| C = CONSEQUENCE[E][V] | V1 | V2 | V3 |
|---|---|---|---|
| E1 | 1 | 1 | 2 |
| E2 | 1 | 2 | 3 |
| E3 | 2 | 3 | 3 |

| R = RISK[H][C] | C1 | C2 | C3 |
|---|---|---|---|
| H0 very low | 0 | 0 | 1 |
| H1 low | 0 | 1 | 1 |
| H2 moderate | 1 | 2 | 2 |
| H3 high | 2 | 3 | 4 |
| H4 very high | 3 | 4 | 4 |

Every threshold is a parameter (`[postprocess.risk]`). The levels are screening levels, not a structural
assessment.

### 3.5 Outputs

`analyses/risk/<product>/`:

- `risk.parquet`: one row per Overture building. Columns: Overture (GERS) id, position, footprint, height, floors,
  source, own points, vertical rate, β, H, E, V, C, R.
- `risk.json`: counts by level and by source, share of known heights, warnings.

## 4. First results

Runs of 2026-10-26 with the default parameters.

**Kinds of motion** (cells of 100 m):

| Product | Epochs | Stable | Steady | Seasonal | Speeding | Slowing | Onset | Step | Flagged date |
|---|---|---|---|---|---|---|---|---|---|
| Hanoi S1 v4, 2025-10 → 2026-10 | 26 | 11,639 | 2,732 | 308 | 5 | 25 | 194 | 168 | 2026-09-09 |
| Mây Chai S1 v1, 2025-10 → 2026-10 | 24 | 7,357 | 2,025 | 10 | 0 | 2 | 20 | 11 | – |
| Mexico S1 v7, 2024-05 → 2024-10 | 16 | 975 | 42,371 | 0 | 38 | 66 | 544 | 225 | 2024-06-08 |
| Hanoi CSK v3, 2011-07 → 2014-12 | 18 | 4,896 | 872 | 46 | 105 | 67 | 88 | 288 | 2014-01-10 |

- **Mexico City sinks steadily almost everywhere.** 42,371 of 44,219 classified cells are steady, as expected
  from the compaction of the lacustrine clays. No seasonal cell: the series cover six months.
- **Hanoi S1 is mostly stable**, with 308 seasonal cells over one year.
- **Each product has one flagged date**, which gathers most of its changes: 171 cells on 2026-09-09 for Hanoi S1,
  466 on 2024-06-08 for Mexico. These are the acquisitions to check first.

**Risk to buildings:**

| Product | Buildings | Own points | From cell | Very high | High | Moderate | Low | Very low | Heights known |
|---|---|---|---|---|---|---|---|---|---|
| Hanoi S1 v4 | 450,198 | 8,268 | 350,904 | 1 | 6 | 1,023 | 16,470 | 341,672 | 2 % |
| Mexico S1 v7 | 1,663,658 | 21,329 | 1,311,046 ¹ | 27,321 | 345,439 | 888,714 | 11,651 | 46,942 | 0 % |

¹ Checked 2026-11-05 in `risk.parquet` / `risk.json`: 12,308 of the Mexico buildings rated "from cell" lie in a cell
without a hazard level (hazard −1), so they have no risk level. Assessed: 1,320,067 = the sum of the five levels.
Hanoi adds up (359,172). Heights known: runs before the GlobalBuildingAtlas fill (§3.2).

- **Mexico:** most buildings are at moderate or high risk. This follows from the hazard (steady sinking of 100 to
  350 mm/yr, after the GNSS tie) more than from the buildings.
- **Hanoi:** the area of the product is stable relative to the scene mean, so almost every building is at very
  low risk.
- **Heights:** they are almost never known in Overture over these areas, so in these runs the exposure rests on the
  footprint alone (the GlobalBuildingAtlas fill of §3.2 came later; not yet rerun).

## 5. Limitations

- **Short series.** One year cannot separate a seasonal cycle from a trend change, and six months (Mexico) cannot
  show a season at all. The classes firm up with every new acquisition.
- **Model set.** A cell that slows and then reverses (a half cycle) can be read as slowing; a cell with two changes
  keeps the strongest one.
- **Steps.** A step of several millimetres between two dates is more often an unwrapping error than ground motion.
- **Hazard of the buildings.** Buildings rated from their cell carry a 100 m average; only the ones with their own
  points (2 % in Hanoi, 1 % in Mexico) are rated individually.
- **Exposure and vulnerability.** These are proxies: no heights, no structural type, no foundations, no
  occupancy. The risk map says where to inspect, not what will crack.
- **β is tilt, not distortion (2026-11-05).** The damage-potential classes use angular-distortion limits on a tilt
  (building) or a ground slope (cell); see §3.1. Indicative only until the curvature / deflection fix.
- **Model selection (2026-11-05).** ΔBIC = 6 is under-penalised for the searched change epoch and assumes
  independent residuals (§2.2); the onset / step counts are upper bounds until calibrated on null simulations.

## 6. Research sequence

- **B1 — Onsets against works.** Set the onset dates against building permits and construction dates (a new
  building loads soft soil: an onset followed by a slowing motion is expected).
  Criterion: most onsets in built-up areas fall within a year of a permit.
- **B2 — Longer series.** Rerun on multi-year Sentinel-1 stacks (2016 →). Criterion: the seasonal class appears
  where heads oscillate (Hanoi riverbanks).
- **R1 — Heights.** Bring heights from Google Open Buildings 2.5D, a city model or lidar, so that the exposure
  separates houses from towers.
- **R2 — Validation against damage.** Survey cracks on a sample of streets and compare with β and the risk levels.
  Criterion: damage increases with the level, as in empirical fragility curves (Peduto et al. 2017).
- **R3 — Structural type.** Bring the structural type from the cadastre or field mapping and replace the
  vulnerability proxy with fragility curves per type.

## 7. References

- Berti, M., Corsini, A., Franceschini, S., Iannacone, J. P. (2013). Automated classification of Persistent
  Scatterers Interferometry time series. *Natural Hazards and Earth System Sciences* 13, 1945–1958.
- Bjerrum, L. (1963). Allowable settlement of structures. *Proceedings of the 3rd European Conference on Soil
  Mechanics and Foundation Engineering*, Wiesbaden, 2, 135–137.
- Boscardin, M. D., Cording, E. J. (1989). Building response to excavation-induced settlement. *Journal of
  Geotechnical Engineering* 115(1), 1–21.
- Burland, J. B. (1995). Assessment of risk of damage to buildings due to tunnelling and excavation. Invited special
  lecture, *1st International Conference on Earthquake Geotechnical Engineering* (IS-Tokyo '95).
- Burland, J. B., Broms, B. B., de Mello, V. F. B. (1977). Behaviour of foundations and structures. *Proceedings of
  the 9th International Conference on Soil Mechanics and Foundation Engineering*, Tokyo, 2, 495–546.
- Burland, J. B., Wroth, C. P. (1974). Settlement of buildings and associated damage. *Proceedings of the
  Conference on Settlement of Structures*, Cambridge, 611–654.
- Kass, R. E., Raftery, A. E. (1995). Bayes factors. *Journal of the American Statistical Association* 90(430),
  773–795.
- Peduto, D., Nicodemo, G., Maccabiani, J., Ferlisi, S. (2017). Multi-scale analysis of settlement-induced building
  damage using damage surveys and DInSAR data: a case study in The Netherlands. *Engineering Geology* 218,
  117–133.
- Schwarz, G. (1978). Estimating the dimension of a model. *The Annals of Statistics* 6(2), 461–464.
- Skempton, A. W., MacDonald, D. H. (1956). The allowable settlements of buildings. *Proceedings of the Institution
  of Civil Engineers* 5(6), 727–768.
- UNDRR (2016). Report of the open-ended intergovernmental expert working group on indicators and terminology
  relating to disaster risk reduction. United Nations General Assembly, A/71/644.
