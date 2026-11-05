# Skill: kinds of motion, motion per building and risk to buildings

> Says how each hazard cell moves (stable, steady, seasonal, speeding, slowing, onset, step, with the date of a
> change), gives the velocity and tilt of every building that carries persistent scatterers, and crosses the
> hazard with what stands on the ground to rate the risk to every building.
> Status: operational screening (v1, 2026-10-26). Last checked against the code 2026-11-01.
> CLI `geoeyes behaviour`, `geoeyes buildings`, `geoeyes risk`; web app **In-depth analysis → Thematic analysis**,
> layers "Kind of motion", "Date of change", "Risk to buildings".

## 1. When to use it

- **Kinds of motion** (`behaviour`). Two cells with the same rate can call for different actions: a steady
  compaction, a recent onset after works, a seasonal cycle, a motion that fades. Use it to find onsets and
  accelerations, and to flag acquisitions that shift many cells at once.
- **Buildings** (`buildings`). Velocity and tilt of individual buildings with enough persistent scatterers: which
  structures sink or tilt beyond the damage limits.
- **Risk** (`risk`). A sinking empty field and a sinking school have the same hazard and different risks. Use it to
  rank buildings for inspection.
- **Not for.** A structural assessment (no structural type, foundations or occupancy), damage prediction, or a
  reading of classes on a series shorter than about a year (seasonal) or with fewer than 9 epochs (refused).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Hazard zoning of the product | yes for `behaviour` and `risk` | [hazard-zoning.md](hazard-zoning.md): `geoeyes hazard <project> --product <id>` | `projects/<name>/analyses/hazard/<id>/` (`hazard.json`, `cells.parquet`, `cells_ts.npy`) | Behaviour uses its series and stability thresholds; risk uses its levels, classes, breaks and matrix |
| Point product | yes for `buildings` | [insar-processing.md](insar-processing.md) | `projects/<name>/products/<id>/points.parquet` with `lon`, `lat`, `vel_los_mm_yr`, `los_u` | Persistent scatterers on roofs and walls; DS-only products give few buildings |
| Overture building footprints | yes for `buildings` and `risk` (automatic) | Overture Maps buildings PMTiles, release `2026-10-21.0`, read tile by tile at z14 over HTTP | cache `<workspace>/cache/overture/<release>/` | Licence ODbL + CC BY 4.0: credit Overture, OpenStreetMap, Google, Microsoft |
| Building analysis | recommended for `risk` | `geoeyes buildings <project> --product <id>` | `projects/<name>/analyses/buildings/<id>/buildings.parquet` | Without it every building is rated from its cell (warning) |
| GlobalBuildingAtlas heights | optional, on by default | Source Cooperative layer `gba-buildings` (`tge-labs/globalbuildingatlas-lod1`), see [exposure-and-flood-layers.md](exposure-and-flood-layers.md) | `[postprocess.risk] gba_heights = true`; cache `<workspace>/cache/sourcecoop/` | Fills heights missing in Overture. Network errors leave the heights as they were |
| Parameters | optional | – | `[postprocess.behaviour]`, `[postprocess.risk]`; `buildings` takes `--set` only (no project.toml section) | Unknown keys stop `behaviour` and `risk` |

Checklist before running:

- [ ] The hazard zoning is current (re-run behaviour and risk after any new zoning).
- [ ] The zoning has ≥ 9 epochs (behaviour refuses fewer); ≥ 0.9 year span for the seasonal model.
- [ ] The zoning is referenced to stable ground (`reference_bbox` or `gnss_tie`): risk inherits its levels.
- [ ] Network access to the Overture bucket (first run) and Source Cooperative (heights).
- [ ] `geoeyes buildings` has run before `geoeyes risk`, so that buildings with their own points use them.

## 3. Method

### 3.1 Kinds of motion (`src/geoeyes/ml/behaviour.py`, `BehaviourParams`)

Each cell's series (`cells_ts.npy`, GeoEyes sign, t in years from the first date) is fitted by least squares with:

| Class | Model | Parameters k |
|---|---|---|
| stable / steady | d = a / d = a + b·t | 1 / 2 |
| seasonal | d = a + b·t + c·sin 2πt + e·cos 2πt (only if span ≥ `min_span_seasonal_yr` 0.9) | 4 |
| speeding / slowing | d = a + b·t + c·t² | 3 |
| onset | d = a + b·t + h·(t − t₀)₊ | 4 (t₀ counted) |
| step | d = a + b·t + δ·H(t − t₀) | 4 (t₀ counted) |

- BIC = n·ln(RSS/n) + k·ln n (Schwarz 1978). The richer model with the lowest BIC is kept only when it lowers the
  BIC of the line by ≥ `min_delta_bic` (6, "strong", Kass & Raftery 1995).
- Otherwise: steady if |b| ≥ the cell's stability threshold of the zoning (`stable_mm_yr`, i.e. max(2, 2σ)), else
  stable.
- Speeding when |b + 2c·t_end| > |b| (the motion grows in either direction), else slowing; `acc_mm_yr2` = 2c.
- t₀ is tried at every epoch leaving `edge_epochs` (3) on each side. At least 2·`edge_epochs` + 3 = 9 epochs.
- **Shared change dates.** A date gets a warning and goes to `shared_change_dates` when its onsets + steps reach
  ≥ max(20, 5 × the median per date) and ≥ 25 % of all changes: one acquisition (atmosphere, unwrapping) is more
  likely than ground.

### 3.2 Buildings (`src/geoeyes/ml/buildings.py`, `analyse`)

- Points falling *within* an Overture footprint are assigned to it; a building needs `min_points` (3).
- v_vert = v_LOS / max(l_u, 0.2); `v_los`, `v_vert` = medians; `spread` = P90 − P10 of v_vert.
- **Tilt** (≥ `min_points_tilt` 8 points spread over ≥ `min_extent_m` 20 m): plane v = a + b·x + c·y;
  |∇v| = √(b² + c²) (mm/yr per m) kept only when ≥ `tilt_t` (3) × its standard error.
  `tilt_10yr` = |∇v| · 10 / 1000: rigid tilt, classed with `tilt_breaks` (1/500, 1/250, 1/100; Burland 1995).
- **Angular distortion** (schema `buildings/2`, 2026-11-05): residuals r of the plane; `beta_10yr` = P90 of
  |r_i − r_j| / d_ij over pairs ≥ `min_pair_m` (5 m) apart × 10 / 1000 (relative rotation, rigid tilt removed);
  kept only when ≥ `beta_t` (2) × its noise floor (`distortion_noise`). Classed with `distortion_breaks`
  (1/500, 1/300, 1/150: Bjerrum 1963; Skempton & MacDonald 1956). Products written before this change hold the
  tilt in `beta_10yr`; rerun them.

### 3.3 Risk (`src/geoeyes/ml/risk.py`, `RiskParams`)

- **Hazard H (0–4).** Default: the level of the zoning cell that holds the building centroid (`source = "cell"`);
  no cell → not assessed (`none`). Own InSAR (`source = "building"`) when the building has ≥ `min_points_own` (5)
  points and is not in a landslide cell: I from −`v_vert` with the zoning's `subsidence_breaks` and stability
  threshold (≥ 2 mm/yr); S = the larger of the classes of its own `beta_10yr` and `tilt_10yr` when significant, else the cell's S; H = zoning `matrix`[I][S].
- **Exposure E (1–3).** Gross floor area = footprint × floors; floors = max(1, round(height / `floor_height_m`
  3)). Heights: Overture, else GlobalBuildingAtlas (`gba_heights`), else the median floors of the buildings with a
  height (2 if none). E1 < 300 m² ≤ E2 < 3000 m² ≤ E3 (`exposure_breaks_m2`).
- **Vulnerability V (1–3).** V3 if height ≥ `tall_m` (21) or √footprint ≥ `long_m` (30); V1 if footprint <
  `small_m2` (60) and height not above 2 × `floor_height_m` (unknown counts as low); else V2.
- **Consequence and risk:**

  | C | V1 | V2 | V3 |
  |---|---|---|---|
  | E1 | 1 | 1 | 2 |
  | E2 | 1 | 2 | 3 |
  | E3 | 2 | 3 | 3 |

  | R | C1 | C2 | C3 |
  |---|---|---|---|
  | H0 very low | 0 | 0 | 1 |
  | H1 low | 0 | 1 | 1 |
  | H2 moderate | 1 | 2 | 2 |
  | H3 high | 2 | 3 | 4 |
  | H4 very high | 3 | 4 | 4 |

Published basis: Berti et al. 2013 (automated PS time-series classes), Schwarz 1978, Kass & Raftery 1995, Burland &
Wroth 1974, Peduto et al. 2017, UNDRR 2016 terminology.

## 4. Steps

1. **Zoning.** `geoeyes hazard <project> --product <id>` ([hazard-zoning.md](hazard-zoning.md)).
2. **Kinds of motion.** `geoeyes behaviour <project> --product <id>` (e.g. `--set min_delta_bic=10`).
   Web: Thematic analysis → layer "Kind of motion" → **Classify the kinds of motion**. Runs in seconds (all cells
   fitted at once; a few tenths of a second for 45,000 cells, research note §2.2).
   Writes `projects/<name>/analyses/behaviour/<id>/`: `behaviour.parquet`, `behaviour_fit.npy`, `behaviour.json`,
   `manifest.json`.
3. **Buildings.** `geoeyes buildings <project> --product <id>` (e.g. `--set min_points_tilt=10 --set tilt_t=4`).
   CLI only. The first run downloads the Overture tiles over the product (cached). Writes
   `projects/<name>/analyses/buildings/<id>/`: `buildings.parquet`, `buildings.json`, `manifest.json`.
4. **Risk.** `geoeyes risk <project> --product <id>` (e.g. `--set gba_heights=false`).
   Web: layer "Risk to buildings" → **Assess the risk to buildings**. Reads the Overture tiles (cached) and the
   GlobalBuildingAtlas heights. Writes `projects/<name>/analyses/risk/<id>/`: `risk.parquet`, `risk.json`,
   `manifest.json`.
5. Run times of `buildings` and `risk` are not benchmarked; they scale with the number of buildings (Hanoi S1:
   450,198; Mexico S1: 1,663,658) and the first download.

## 5. Outputs and how to read them

**`behaviour.parquet`** (one row per zoning cell, same order): `class` (or `not assessed`), `class_id`,
`change_date` (onset/step), `rate_mm_yr`, `rate_before_mm_yr` / `rate_after_mm_yr` (onset), `acc_mm_yr2`
(speeding/slowing), `seasonal_amp_mm`, `jump_mm` (step), `delta_bic`. `behaviour_fit.npy` = the kept model per
cell. `behaviour.json`: `counts`, `changes_by_month`, `shared_change_dates`, `warnings`. Sign: negative = sinking
or downslope; "speeding" means faster sinking for a sinking cell and faster uplift for a rising one.

**`buildings.parquet`**: `id` (Overture GERS id), `lon`, `lat`, `area_m2`, `height_m`, `n`, `v_los`, `v_vert`,
`spread`, `tilt`, `tilt_se`, `beta_10yr`. `buildings.json`: totals, `with_tilt`, `beta_over_1_500`, release and
credit.

**`risk.parquet`** (one row per Overture building): `id`, `lon`, `lat`, `area_m2`, `height_m`, `floors`,
`height_known`, `height_source` (`overture` / `gba` / `assumed`), `source` (`building` / `cell` / `none`),
`points`, `v_vert_mm_yr`, `beta_10yr`, `hazard`, `exposure`, `vulnerability`, `consequence`, `risk` (0–4, −1 not
assessed). `risk.json`: `by_risk`, `footprint_km2_by_risk`, `by_source`, `height_known_share`,
`height_from_gba`, `median_floors_assumed`, credits, warnings.

Reading: a risk level says where to inspect first, not what will crack. In Mexico S1 (research note §4) most
buildings are moderate or high because of the hazard (steady sinking of 100–350 mm/yr after the GNSS tie), not
because of the buildings.

## 6. Quality checks

- **Shared change dates.** Check every date in `shared_change_dates` before reading onsets and steps (Hanoi S1:
  2026-09-09; Mexico S1: 2024-06-08; Hanoi CSK: 2014-01-10). Steps of several mm between two dates are more often
  unwrapping errors.
- **Class counts against the span.** No seasonal class under 0.9 year; with one year, seasonal and onset can be
  confused (research note §5).
- **Tilt.** Keep only `tilt` values (already filtered by `tilt_t`); compare `beta_10yr` with 1/500 and 1/300.
- **Height coverage.** `height_known_share` in `risk.json`: a warning is written below 50 %. In Hanoi Overture has
  a height for 1.4 % of the buildings, 67 % with GlobalBuildingAtlas ([../guide/opendata.md](../guide/opendata.md)).
- **Source mix.** `by_source`: only buildings with own points are rated individually (2 % in Hanoi, 1 % in Mexico,
  research note §5); the rest carry a 100 m cell average.
- **Reference of the zoning.** If the zoning is relative to the scene mean, the hazard and hence the risk are
  biased; fix the zoning first.

## 7. Limits and pitfalls

- Model set: a cell that slows then reverses can read as slowing; a cell with two changes keeps the strongest one.
- Behaviour, risk and consolidation must be re-run after the zoning is re-run (risk reads the cell levels).
- `beta_10yr` of buildings always uses 10 years, whatever `horizon_yr` the zoning used.
- Own-point hazard uses the vertical projection v_LOS / l_u (one geometry); buildings in landslide cells always
  take the cell level.
- Exposure and vulnerability are proxies: no structural type, foundations or occupancy.
- `geoeyes buildings` has no `[postprocess.buildings]` section: parameters go through `--set` only, and a wrong
  key fails as a Python argument error.

## 8. On a new area or sensor

- **Change:** `[postprocess.risk]` thresholds (`floor_height_m`, `tall_m`, `long_m`, `small_m2`,
  `exposure_breaks_m2`) to local building stock; `gba_heights = false` where GlobalBuildingAtlas is poor;
  `min_points_own` with sensor density (X-band gives many more points per roof than C-band).
- **Carries over:** the model set, BIC rule, consequence and risk matrices.
- **Sensor:** short X-band stacks (weeks) give stable/steady only; a C-band year is the minimum for seasonal.
- **Known results** (research note §4): Mexico City S1 42,371 of 44,219 cells steady; Hanoi S1 mostly stable with
  308 seasonal cells.

## 9. References

- Code: `src/geoeyes/ml/behaviour.py`, `buildings.py`, `risk.py`, `overture.py`; `src/geoeyes/opendata/coop.py`
  (`fill_heights`); `src/geoeyes/ml/__init__.py` (`run_behaviour`, `run_buildings`, `run_risk`);
  `src/geoeyes/api/behaviour.py`; `webapp/src/pages/Hazard.tsx`, `LearnBehaviour.tsx` (Principles, chapter 3);
  tests `tests/unit/ml/test_behaviour_risk.py`.
- Research: [../research/behaviour-and-risk.md](../research/behaviour-and-risk.md),
  [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md) (step R6).
- Guides: [../guide/opendata.md](../guide/opendata.md) (Source Cooperative layers).
- Skills: [hazard-zoning.md](hazard-zoning.md), [exposure-and-flood-layers.md](exposure-and-flood-layers.md),
  [lines-and-consolidation.md](lines-and-consolidation.md).
- Papers: Berti et al. 2013 (*NHESS* 13:1945); Schwarz 1978 (*Ann. Stat.* 6:461); Kass & Raftery 1995 (*JASA*
  90:773); Burland & Wroth 1974; Peduto et al. 2017 (*Eng. Geol.* 218:117); Skempton & MacDonald 1956; Bjerrum
  1963; UNDRR 2016 (A/71/644).
