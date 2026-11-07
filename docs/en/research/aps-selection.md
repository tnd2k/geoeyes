# Choosing whether to remove the atmospheric phase screen

Status (2026-11-07): plan written; **A0 done for `hcm_d18`** (§5.1), other cases pending; A1–A4 not started.
Owner's request: "an automatic way to decide whether to subtract the APS or not". Companion notes:
[ramp-selection.md](ramp-selection.md) (the same idea for the ramp), memory `hcm-d18-sarproz`.

## Contents

1. [Question](#1-question)
2. [Background](#2-background)
3. [Method: `subtr_tropo = "auto"`](#3-method-subtr_tropo--auto)
4. [Steps and review gates](#4-steps-and-review-gates)
5. [Results](#5-results)
6. [Limitations](#6-limitations)
7. [References](#7-references)

## 1. Question

`[ps] subtr_tropo = "y"` (the default) removes, per interferogram, the topography-correlated APS
`phase = a·h + b` (`aps.py::linear_aps`, StaMPS TRAIN `a_l`), or a weather-model APS (`[atmosphere]`). It is
removed twice: before the pass-2 unwrapping and from the velocity (`velocity.py::corrected_phase`), so the output
is StaMPS "v-dao".

On `hcm_d18` (HCMC, flat) the output agrees better with SARPROZ **without** it ("v-do": r 0.89 vs 0.84, stable-area
NMAD 1.0 vs 1.7 mm/yr, the +1.8 mm/yr offset and the ±5 mm/yr tilt gone). In mountains the same correction is
needed (stratified troposphere of cm per km of height).

Question: **can the engine decide from the data whether the APS helps, and keep it from changing the velocity when
it does not?**

## 2. Background

### 2.1 What the APS should and should not carry

| Part | Spatial | Temporal | Should change the velocity? |
|---|---|---|---|
| Stratified troposphere (a·h) | follows the terrain | seasonal + random | no (zero-mean over years) |
| Turbulent troposphere | km-scale, random | random per date | no |
| Deformation correlated with height | follows the land cover (fills, new builds are low; old city high) | **steady** | — this is signal |

A real APS has no multi-year trend. If the APS series of a point has a trend, the regression has absorbed
deformation that happens to correlate with height.

### 2.2 What the engine does now

- `linear_aps`: weighted line a·h + b per interferogram over all PS (or `aps_non_defo`), on the pass-1 unwrapped
  phase, deformation included.
- Weather APS (`[atmosphere] method`): `choose_aps` keeps it per interferogram only when it lowers the residual
  variance more than the linear APS: a per-date choice between two models, never "none".
- Step 8 SCN removes the spatially-correlated, temporally-uncorrelated part from the series (`disp_scn_mm`), with a
  local linear fit that keeps the trend: it cleans the series but leaves the velocity unchanged (−0.2 mm/yr on the
  fast `hcm_d18` points).
- "step 7 HP" (velocity high-pass): ±0.2 mm/yr on `hcm_d18`; not the cause.

### 2.3 What other tools do

- StaMPS / TRAIN (Bekaert et al. 2015): the user picks the correction (`a_l`, `a_e`, `a_p`, …) and judges it on the
  phase–height scatter; band-pass `a_p` estimates the phase–height ratio on short wavelengths to avoid deformation.
- MintPy (Yunjun et al. 2019): weather model or "height_correlation" on the time series, with an optional mask;
  the choice is the user's. GACOS users commonly judge by variance reduction (Yu et al. 2018).
- SARPROZ: APS estimated as the spatially low-pass, temporally high-pass residual after the motion model (like
  SCN): the velocity is in effect v-do.

## 3. Method: `subtr_tropo = "auto"`

New value; `"y"` and `"n"` stay bit-identical.

### 3.1 Check 1 — relief gate (cheap)

Terrain relief = p5–p95 of the stack DEM (`geometry_hgt`, bare terrain, no buildings) over the PS footprint. The
stratified delay change between two dates is at most ≈ k·Δh with k ≈ 10 mm/km (generous). If k·relief is below the
noise floor (1 mm), the a·h term cannot be measured: **APS off** ("relief 11 m").

Candidate threshold: relief < 100 m → off. Tuned in A0/A1.

### 3.2 Check 2 — leakage into the velocity

With the APS estimated as now:

1. v_aps = linear rate of the APS series at every PS (scene median removed: a uniform part is taken out by the
   reference anyway);
2. leakage when the spread p5–p95 of v_aps exceeds L mm/yr **and** |corr(v_aps, v_def)| > c, with v_def the rate of
   (unwrapped − SCLA) without APS.

Candidates: L = 1 mm/yr, c = 0.1.

### 3.3 Check 3 — does the APS help at all

Residual phase = pass-1 unwrapped − (c + v·t + K·B⊥) per PS (`aps._detrend_parts`, as `choose_aps`). Per
interferogram, the variance reduction by the APS. The trend is removed before, so leakage cannot pass for benefit.
APS useful when the median reduction is > 5 % (candidate).

### 3.4 Decision

| Relief | Helps (3.3) | Leaks (3.2) | Action |
|---|---|---|---|
| low | — | — | off |
| enough | no | — | off |
| enough | yes | no | on (as now) |
| enough | yes | yes | on, **APS detrended per PS** (its linear trend removed: cleans the series, leaves the rate) — or A2's estimate |

The decision, its numbers and the rule go into `resolved` (as `max_topo_err = "auto"`) and the report.

### 3.5 Estimating the APS without the deformation (A2)

Fit a·h on the pass-1 phase minus the pass-1 motion (v·t + K·B⊥ per PS), optionally band-passed (TRAIN `a_p`), so
the regression cannot take the steady part. Compare with the per-PS detrending of 3.4.

## 4. Steps and review gates

| Step | Content | Gate |
|---|---|---|
| A0 | Checks 1–3 on finished runs: `hcm_d18` (flat), a mountainous case (Choshui S1 PS run or ICEYE Tenerife), CSK Hanoi golden (flat, X-band). For each, output with / without APS against the reference (SARPROZ, GNSS, golden). | owner review of thresholds |
| A1 | `steps/aps_auto.py`: pure functions for checks 1–3 and the decision table; unit tests (flat + height-correlated subsidence → off; mountains + stratified delay → on; leak → detrend) | review |
| A2 | Deformation-free a·h estimate (3.5) vs per-PS detrending, on the A0 cases | review |
| A3 | Wiring: `subtr_tropo = "auto"` in `params.py` / `runner.py`, `resolved`, report text; parity: "y"/"n" unchanged; rerun the A0 cases | review |
| A4 | Default per preset (S1: "auto"?) after A3 | owner decision |

## 5. Results

### 5.1 A0 — `hcm_d18` (HCMC, S1 desc 18, 98 dates, run `ps_exp/new50`)

| Check | Value | Verdict |
|---|---|---|
| 1 relief | terrain p5–p95 **10.9 m**; PS height p5–p95 34.3 m (buildings, DEM error) | off |
| 2 leakage | v_aps p5..p95 −2.0..+2.8 mm/yr (spread **4.9**); corr(v_aps, v_def) **+0.25**; corr(v_aps, h) +0.28; corr(v_def, h) +0.17; trend = 26 % of the APS variance | leaks |
| 3 benefit | residual variance reduction median **+0.9 %**; > 5 % in 19 % of the ifgs; worse in 29 % | does not help |

All three say off. Against SARPROZ, v-do (no APS, orbit plane fitted on the stable north) vs v-dao: r 0.89 / 0.84,
bias 0.0 / +1.9, stable NMAD 1.0 / 1.7, v < −15 bias +2.7 / +5.3 mm/yr.

Engine runs (steps 6–8 again on the same steps 1–5, SARPROZ points within 20 m):

| Variant | all: r / bias | v < −15: r / bias | v < −25: bias | stable: bias |
|---|---|---|---|---|
| `subtr_tropo = "y"` (`new50`) | 0.84 / +1.94 | 0.58 / +5.33 | +7.00 | +1.60 |
| **`subtr_tropo = "n"`** (`new50_noaps`) | **0.89 / −0.06** | **0.60 / +1.96** | **+3.91** | **−0.21** |

Without the APS in both passes the engine itself gives the v-do agreement, without an orbit plane: the APS was the
whole offset and tilt.

Pending: a mountainous case and CSK Hanoi.

## 6. Limitations

- Thresholds from one flat case; a hilly city (Da Lat, Tenerife) is the test that matters.
- k = 10 mm/km is a generous bound for the dry/wet stratified delay; tropical wet seasons can exceed it locally.
- Check 2 needs the deformation rate without APS, itself from the pass-1 unwrapping.
- The reference (SARPROZ) is another processing, not ground truth; GNSS / levelling would settle it.

## 7. References

- Bekaert D. P. S., Walters R. J., Wright T. J., Hooper A. J., Parker D. J. (2015). Statistical comparison of InSAR
  tropospheric correction techniques. *Remote Sensing of Environment* 170, 40–47.
- Yu C., Li Z., Penna N. T., Crippa P. (2018). Generic atmospheric correction model for InSAR observations.
  *JGR Solid Earth* 123, 9202–9222.
- Yunjun Z., Fattahi H., Amelung F. (2019). Small baseline InSAR time series analysis: unwrapping error correction
  and noise reduction. *Computers & Geosciences* 133, 104331.
- Hooper A., Bekaert D., Spaans K., Arıkan M. (2012). Recent advances in SAR interferometry time series analysis
  for measuring crustal deformation. *Tectonophysics* 514–517, 1–13.
