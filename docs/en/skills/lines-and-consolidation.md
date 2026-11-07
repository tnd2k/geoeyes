# Skill: differential settlement along lines, and consolidation still to come

> Profiles the InSAR vertical rate along dykes, embankments, railways and main roads (OpenStreetMap) and flags
> where the settlement changes fast enough along the line to harm it; separately, fits a consolidation curve to
> the sinking cells to estimate the settlement still to come and how long it takes.
> Status: operational screening (v1, 2026-10-26). Last checked against the code 2026-11-01.
> CLI `geoeyes lines`, `geoeyes consolidation`; web app **In-depth analysis → Thematic analysis**, layers
> "Infrastructure lines" and "Remaining settlement".

## 1. When to use it

- **Lines.** What harms a dyke, a track or a road is sinking that *changes along it*: a dip in a dyke crest is where
  water overtops first; a dip under a track bends the rails. Use `lines` to find those stretches and the crest
  lost over a horizon.
- **Consolidation.** Soft soil under a new load settles fast, then slower, towards an end; pumping-driven
  subsidence goes on as long as pumping does. Use `consolidation` to separate the two and to estimate the final
  and remaining settlement of the cells that settle towards an end.
- **Not for.** Long, gentle bends over kilometres (β is local at 100 m: use the crest lost), lines absent from
  OSM, or a consolidation reading on series that do not contain the bend of the curve (one year usually does not).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Point product | yes for `lines` | [insar-processing.md](insar-processing.md) | `projects/<name>/products/<id>/points.parquet` with `lon`, `lat`, `vel_los_mm_yr`, `los_u` | PS density on the structure decides the coverage |
| OSM lines | yes for `lines` (automatic) | Overpass API (`overpass-api.de`), one query over the product bbox | cache `<workspace>/cache/osm/overpass_<hash>.json` | ODbL, credit © OpenStreetMap contributors. Delete the cache file to re-read OSM |
| Hazard zoning of the product | yes for `consolidation` | [hazard-zoning.md](hazard-zoning.md): `geoeyes hazard <project> --product <id>` | `projects/<name>/analyses/hazard/<id>/` (`hazard.json`, `cells.parquet`, `cells_ts.npy`) | Uses the cell series, `rate_mm_yr` and `mode`. ≥ 8 epochs |
| Better dyke lines | optional | Official dyke routes, crest tracing from a DEM (research L1) | Not read by the code: add them to OSM, or compare outside GeoEyes | Hanoi: only 15.7 km of dykes mapped, 21 % covered (research note §4.1) |
| Parameters | optional | – | `[postprocess.lines]`, `[postprocess.consolidation]` | Unknown keys stop the run |

Checklist before running:

- [ ] Network access to the Overpass API (first run; the server sheds load with 429/504, the code retries 3 times).
- [ ] The product's reference is known; rates along a line are relative to it.
- [ ] For consolidation: the zoning is current, has ≥ 8 epochs, and its span covers the expected time constant.
- [ ] You accept the vertical-only assumption (v_LOS / l_u), or have a decomposition for comparison
  ([decompose-and-soft-soil.md](decompose-and-soft-soil.md)).

## 3. Method

### 3.1 Lines (`src/geoeyes/ml/lines.py`, `LinesParams`)

1. **OSM ways** over the product bbox: `man_made=dyke` or a `highway` named "Đê …" → `dyke`; `railway=rail` →
   `railway`; `embankment=yes` on a highway → `embankment`; `highway=motorway|trunk|primary` → `road` (only with
   `roads` = true). Ways of the same kind and name (or `ref`) sharing an end node are chained, greedily.
2. **Stations** every `step_m` (50 m) along each line (lines shorter than one step are skipped). At each, the
   median of v_vert = v_LOS / max(l_u, 0.2) of the points within `buffer_m` (30 m), if ≥ `min_points` (3).
   GeoEyes sign: negative = sinking.
3. **Angular distortion** between stations `span_m` (100 m) apart (k = round(span/step) stations):

       β = |v(x + L) − v(x)| · horizon_yr / (1000 · L)       horizon_yr = 10

   classified by `distortion_breaks` (1/500, 1/300, 1/150): 0 below the safe limit (Bjerrum), 1 beyond it,
   2 cracking, 3 structural damage (Skempton & MacDonald). A station is **flagged** at class ≥ 1.
4. **Crest lost** per line: max(0, −min v) × `horizon_yr` (mm), at the fastest-sinking station.

### 3.2 Consolidation (`src/geoeyes/ml/consolidation.py`, `ConsolidationParams`)

1. Settlement s = −d (positive down), set to 0 at the first date, for every zoning cell.
2. **Candidates:** `mode = subsidence` and `rate_mm_yr` ≤ −`min_rate_mm_yr` (2 mm/yr).
3. **Fit** (Terzaghi 1925, first order): s(t) = c + A·(1 − e^(−t/τ)); τ on a geometric grid of 80 values from
   0.05 to 30 years, (c, A) by least squares for each τ; the best τ is kept. A line s = a + b·t is fitted too.
4. **Consolidating** when all hold: candidate; ΔBIC = BIC_line − BIC_curve ≥ `min_delta_bic` (6), with k = 2
   for the line and 3 for the curve; A > 0; 0.05 yr < τ < `max_tau_factor` (5) × span.
5. **Results:** final = c + A; remaining after the last date T = A·e^(−T/τ); t90 from now = max(0, τ·ln 10 − T).
6. **Check (forecast):** both models fitted on the first m = max(6, round(`train_share` 0.7 × n)) epochs predict
   the rest (needs ≥ 3 test epochs); mean absolute errors and the share of cells where the curve wins.
7. **Asaoka (1978)**, drawn by the web app for one cell: readings resampled every round(span/8) days, clipped to
   12–60 days; line sᵢ = β₀ + β₁·sᵢ₋₁; final = β₀/(1 − β₁) when 0 < β₁ < 1. Not used in the classification.

## 4. Steps

1. **Lines.** `geoeyes lines <project> --product <id>` (e.g. `--set roads=false`, `--set span_m=200`).
   Web: Thematic analysis → layer "Infrastructure lines" → **Profile the infrastructure lines**. About a minute the
   first time (Overpass), then cached.
   Writes `projects/<name>/analyses/lines/<id>/`: `stations.parquet`, `lines.parquet`, `lines.json`,
   `manifest.json`.
2. **Zoning** (for consolidation): `geoeyes hazard <project> --product <id>` ([hazard-zoning.md](hazard-zoning.md)).
3. **Consolidation.** `geoeyes consolidation <project> --product <id>` (e.g. `--set min_rate_mm_yr=5`).
   Web: layer "Remaining settlement" → **Analyse the consolidation**. A few seconds (web app text).
   Writes `projects/<name>/analyses/consolidation/<id>/`: `consolidation.parquet`, `consolidation.json`,
   `manifest.json`.
4. Optional: `geoeyes geology` reads `consolidation.parquet` to check the implied c_v
   ([decompose-and-soft-soil.md](decompose-and-soft-soil.md)).

## 5. Outputs and how to read them

**`stations.parquet`**: `line`, `chainage_m`, `lon`, `lat`, `n_points`, `v_vert_mm_yr`, `beta` (NaN for the first
k stations and where a station has no rate), `beta_class` (−1 no value, 0–3).

**`lines.parquet`**: `line`, `kind`, `name`, `length_m`, `stations`, `covered_share`, `v_min_mm_yr`,
`v_median_mm_yr`, `beta_max`, `flagged`, `loss_mm` (crest or track lowered over the horizon).

**`lines.json`**: `by_kind` (lines, km, covered share, flagged stations), `hotspots` (the 20 flagged lines with the
largest β), source credit.

**`consolidation.parquet`** (one row per zoning cell): `consolidating`, `tau_yr`, `settled_mm`, `final_mm`,
`remaining_mm`, `t90_from_now_yr`, `c_mm`, `A_mm`, `delta_bic`. These values are **settlements, positive down**
(not the GeoEyes sign). **`consolidation.json`**: `sinking_cells`, `consolidating`, `remaining_mm` (median, p90,
max), `tau_yr_median`, `check` (`mae_curve_mm`, `mae_line_mm`, `curve_better_share`).

Reading: a grey stretch on a line is missing data, not stability. A consolidating cell with short τ and almost no
remaining settlement is a load that has nearly finished (Hanoi, research note §4.2).

## 6. Quality checks

- **Coverage** per kind (`covered_share`) before reading a line as safe.
- **Flagged stations** against the map: one isolated flagged station between two well-covered neighbours is
  plausible; a flagged station at the edge of coverage may be noise.
- **Consolidation check.** The check always favours the curve on the selected cells (selection bias, research
  note §3.3). It says whether the curve predicts, not whether the reading is right.
- **τ against the span.** τ close to half the span (Mexico S1: τ ≈ 0.27 yr on six months) is as well explained by a
  seasonal slowdown or a recent load: confirm with a longer series.
- **c_v plausibility** via `geoeyes geology`: values far outside 0.1–10 m²/yr reject the thickness or the reading.

## 7. Limits and pitfalls

- OSM completeness: railways and main roads are well mapped, dykes are not (often only the crest road).
- Dyke slopes and embankments return few scatterers.
- Rates are relative to the product reference and vertical only under the no-horizontal-motion assumption.
- β detects bends at the `span_m` scale only.
- The Overpass cache key is the query (bbox and `roads`): changing `roads` triggers a new download; OSM edits are
  not seen until the cache file is deleted.
- Consolidation needs the bend inside the data; secondary compression (creep) is not modelled, so the final
  settlement is a lower bound where creep matters.
- Re-run consolidation after the zoning is re-run (it reads `cells_ts.npy` and `rate_mm_yr`).

## 8. On a new area or sensor

- **Change:** `step_m` and `buffer_m` with point density (dense X-band: smaller); `span_m` to the bend scale of
  the structure; `horizon_yr` to the planning horizon; `roads = false` to keep only dykes, railways, embankments.
- **Local naming:** the dyke rule matches names starting with "Đê " (Vietnam); elsewhere dykes are read only from
  `man_made=dyke`.
- **Consolidation:** needs multi-year series (research C1: 3+ years of Sentinel-1 or COSMO-SkyMed over new urban
  areas). `min_rate_mm_yr` higher where the reference is uncertain.
- **Known results** (research note §4): Hanoi S1, 582 lines, one station beyond 1/500 (Đỗ Mười road, β 1/446);
  Mexico City S1, 570 lines, largest β 1/127 on Autopista México – Puebla.

## 9. References

- Code: `src/geoeyes/ml/lines.py`, `consolidation.py`; `src/geoeyes/hazard/zoning.py` (`classify`);
  `src/geoeyes/api/behaviour.py` (cell panel, Asaoka step); `webapp/src/pages/Hazard.tsx`, `LearnLines.tsx`
  (Principles, chapter 4); tests `tests/unit/ml/test_lines_consolidation.py`.
- Research: [../research/lines-and-consolidation.md](../research/lines-and-consolidation.md).
- Skills: [hazard-zoning.md](hazard-zoning.md), [behaviour-and-risk.md](behaviour-and-risk.md) ("slowing" is the
  shape consolidation makes precise), [decompose-and-soft-soil.md](decompose-and-soft-soil.md).
- Papers: Terzaghi 1925; Asaoka 1978 (*Soils and Foundations* 18(4):87); Skempton & MacDonald 1956; Bjerrum 1963;
  Kass & Raftery 1995; Tan 1971 (hyperbolic method, research C3).
