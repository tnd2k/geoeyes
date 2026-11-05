# Choosing where to remove the interferogram ramp

Status (2026-11-05): D0 done, D1 done (`steps/ramp.py` + unit tests), **D2 wiring drafted, uncommitted, pending
review** (§5.3), with the three review limitations fixed in code (planar trend needs a stable area or override,
seasonal F-test, SCLA prior in pass 2); D3 / D4 not started, D4 gated on the parity check and the `mexico_g3` run. Plan written 2026-11-04. Owner's request: "a logic that chooses which areas need
`scla_deramp` and which do not". Companion note: [gnss-insar-calibration.md](gnss-insar-calibration.md) §9.1
(G3.1d / G3.1e, where the question came from).

## Contents

1. [Question](#1-question)
2. [Background](#2-background)
3. [Method: `scla_deramp = "auto"`](#3-method-scla_deramp--auto)
4. [Steps and review gates](#4-steps-and-review-gates)
5. [Results](#5-results)
6. [Limitations](#6-limitations)
7. [References](#7-references)

## 1. Question

`[ps] scla_deramp` is a yes/no switch per project, set by the sensor preset: on for ICEYE and COSMO-SkyMed, off for
Sentinel-1. Neither choice is right everywhere:

- **on** removes a plane (or quadratic) from every interferogram, *including the part that grows steadily in time*.
  Where the deformation is wider than the frame (the Mexico City bowl), that part is real tilt: removing it biases the
  rates;
- **off** keeps every ramp. In Mexico City 2024 (G3.1d) the per-epoch ramp reached ±16 mm per 10 km and dominated
  the series at stations 30 km apart; it was not in ERA5 (ionosphere or orbit).

Question: **can the engine decide, per project and from the data, which part of the ramp to remove, and say when it
cannot decide?**

## 2. Background

### 2.1 What the engine does now

- `steps/scla.py::deramp` fits per interferogram a weighted plane (degree 1), or `x² + y² + xy + c` when it lowers
  the RMS by ≥ 8% (`nonlinear_improvement`). It uses the pass-1 unwrapped phase after the APS, on all PS.
- The ramp array (`SclaResult.ph_ramp`) is then removed everywhere downstream:
  - the SCLA fit;
  - the pass-2 unwrapping (`unwrap.py`);
  - the velocity (`velocity.py::corrected_phase`);
  - the SCN (`scn_filt.py`).

  So changing *how the ramp is computed* is enough: nothing downstream has to change.
- The velocity high-pass ("step 7 HP") already removes a plane per epoch from the residual about the linear motion,
  but only for `v`, not for the series.
- Step 8 (SCN) removes the non-linear part of any long-wavelength signal from `disp_scn_mm` (G3.1e), but keeps the
  trend.

### 2.2 Where ramps come from

| Source | Size over a 30 km frame | In time |
|---|---|---|
| Orbit error | S1 precise orbits (~5 cm): a few mm; ICEYE / CSK: cm or more | random per acquisition |
| Ionosphere | C-band: up to cm at solar maximum (2024–2025), dusk passes, low latitudes; L-band: many cm | random, plus a seasonal / solar-cycle drift |
| Long-wavelength troposphere | mm–cm; ERA5 / GACOS remove part | random, plus seasonal |
| Solid-earth tide, plate motion | < 1 mm over 30 km | — |
| **Deformation wider than the frame** (basin bowl, interseismic gradient) | cm/yr | **steady (linear) or seasonal** |

The deformation that looks like a ramp is mostly **linear in time**. The nuisances are mostly **not**: they change
from one acquisition to the next. That is the handle for the decision.

### 2.3 What other tools do

- StaMPS: `scla_deramp` yes/no on all PS, as GeoEyes now.
- MintPy (Yunjun et al. 2019): `deramp` on the time series, fitted on the pixels of a mask, so the deforming area
  can be left out of the fit. The mask is chosen by the user.
- Fattahi & Amelung (2014): orbit ramps on long series average out into a velocity uncertainty, but do not vanish.

## 3. Method: `scla_deramp = "auto"`

New value; `"y"` and `"n"` stay exactly as they are (bit-identical).

### 3.1 Split each ramp into a trend and a rest

1. Per interferogram k, the ramp R_k(x, y) is estimated as now: same surface and degree, same pass-1 phase after the
   APS, all PS.
2. Each coefficient series over time (a_k, b_k, c_k, …) is fitted with a straight line in t_k, with the same weights
   as the velocity fit. Then R = **R_trend** (t_k × a fixed surface) + **R_rest**.

### 3.2 The rest: removed

R_rest changes from one acquisition to the next and is not steady deformation, so it is removed. This is what was
missing in Mexico, and it also helps the pass-2 unwrapping and the SCLA, because a ramp correlated with B⊥
otherwise leaks into the look-angle error.

Safeguard: a frame-wide *seasonal* deformation (a whole basin breathing with the pumping) would also sit in R_rest.
An annual sinusoid is fitted to the coefficient series. When it explains > 50% of their variance and the series
cover ≥ 1 year, the seasonal part is kept and a warning is written. D0 checks whether this ever triggers.

**Fixed in code (2026-11-05): the trigger no longer fires by chance on short series.** The old check
(`seasonal_fit`: sin, cos and a constant on the *already detrended* rest, from 5 epochs, > 50% of the variance)
fired on pure noise about half the time at n = 5 (E[R²] = 2/(n − 1)), tested the two gradients separately, and let
the line absorb part of the cycle. `ramp.py::seasonal_test` now, per gradient series (E-W, N-S):
- fits const + trend + annual sin + cos **jointly** (same weights as the velocity fit);
- F-tests the annual pair against const + trend (2 and n − 4 degrees of freedom);
- keeps the annual part when p < α / 2 (Bonferroni over the 2 gradients; `RampAutoParams.seasonal_alpha` = 0.01);
  the trend of that gradient is then the joint fit's slope.

It runs only when the series covers ≥ 1 year and has ≥ 12 epochs (`seasonal_min_epochs`). Under 1 year it does not
apply (no annual cycle to separate; recorded as "not applicable"). With ≥ 1 year but < 12 epochs the test cannot
run and `auto` is conservative: the annual part of the joint fit is kept untested (less is removed), with a warning
"seasonal safeguard not tested". On pure noise (n = 24) the test fires in about 1% of the series (unit test). The
record has the p-values (`seasonal_p`) and how the check ran (`seasonal_note`).

### 3.3 The trend: removed only where a stable background spans the frame

R_trend cannot be told apart from steady deformation by the phase alone. It is removed only when the scene shows a
stable background wide enough to anchor a plane:

1. Velocity of the pass-1 phase (after the APS, R_rest removed, R_trend kept), median per 500 m cell.
2. Robust plane fit over the cells: fit, keep the cells with |residual| < 2.5 × 1.4826 × MAD, refit; at most 10
   rounds. Local bowls and slides are sharp, so they drop out; a ramp is smooth, so it stays in the fit.
3. Stable cells: the kept cells with |residual| < max(5 mm/yr, 2 σ_cell).
4. **Coverage test.** It passes when all three hold:
   - stable cells cover ≥ 30% of the cells;
   - stable cells lie in ≥ 3 of the 4 quadrants of the frame;
   - along the direction of the fitted gradient, the stable cells span ≥ 60% of the frame's extent.
5. **Passes:** the trend surface is refitted on the stable cells only and removed. The deforming cells keep their
   own tilt.

   **Fails:** R_trend is kept, which is today's `"n"` for the trend. The QC says "trend ramp undetermined". It points
   to a GNSS `plane` calibration (≥ 3 stations; `geoeyes gnss`) or to a user polygon.
6. **User override:** `[ps] deramp_non_defo = [[lon, lat], …]` (one polygon, as `aps_non_defo`) replaces steps 2–3
   with "stable = inside the polygon". The coverage test is still run and reported.

Frames smaller than 5 km on both sides skip step 3 and keep R_trend. There, a ramp is not separable from local
motion.

**Fixed in code (2026-11-05): a planar trend needs an independent constraint.** The halves test that replaced steps
3–4 (§5.1, `ramp.py::frame_test`) asks whether one plane fits the whole frame. That detects curvature, not nuisance:
a *planar* deformation field (an interseismic gradient, §2.2; the LOS gradient of plate motion; a regional tilt)
passes it, and a *curved* steady nuisance (long-wavelength ionosphere) fails it and is kept. The test is safe when it
**keeps** a trend; when it passes it has only shown that the trend is planar. Rule now in `auto_ramp`:
- the trend is removed only with an independent constraint:
  - (a) GNSS: not wired. The PS engine has no access to the GNSS stations (they enter only in the validation step,
    `geoeyes gnss`); a GNSS `plane` check stays a manual step after the run;
  - (b) the user's stable area `[ps] deramp_non_defo` (lon/lat polygon, reused, no new parameter): the trend plane
    is fitted on the cells inside it and removed, whatever the halves test says;
  - (c) the explicit override `[ps] ramp_auto_allow_planar = "y"` (default `"n"`): the halves test alone removes
    the trend, as before;
- otherwise a trend that passes the halves test is kept, with reason "planar trend kept: no independent constraint
  (GNSS / stable area)". The record keeps `frame_test_passed` and the halves numbers, the QC figure shows the reason.

`RAMP_AUTO_VERSION` = 2, so old `auto` step-6 checkpoints are not reused.

### 3.4 What is recorded

- In `params.json` / the run manifest:
  - the coefficients per interferogram, and the split into trend and rest;
  - the seasonal check;
  - the coverage numbers and the decision with its reason.
- QC figure `figures/ramp.png`: E-W and N-S gradient per epoch (total, trend, rest), and the stable-cell map.
- One line in the product report: "ramp: rest removed; trend removed / kept (reason)".

### 3.5 What does not change

- `"y"` / `"n"` results and the existing parity tests.
- The preset defaults, until step D4.
- The SCN, the velocity high-pass and the GNSS comparison.

## 4. Steps and review gates

Each step ends at a gate: results go into §5 of this note and the owner reviews before the next step.

| Step | Work | Gate criterion |
|---|---|---|
| **D0** | Offline study on the four PS states on disk: `mexico_g3` v3, `mexico_s1`, `quangnam_l2b_a55`, `quangnam_l5_d120`. Script `code/ramp_auto.py`: ramp per epoch, split, seasonal check, coverage test, the decision auto would take. No engine change. | The decisions look physically sensible: Mexico is expected to keep or only partly remove the trend (bowl across the frame); Quang Nam is expected to pass (local slides on a stable mountain background). The thresholds of §3.3 are confirmed or changed. |
| **D1** | Pure functions (`steps/ramp.py`) + unit tests on synthetic scenes: (a) local bowl + random ramps + a trend ramp; (b) a bowl wider than the frame + random ramps; (c) no ramp; (d) a seasonal frame-wide signal. | (a) trend ramp recovered within 2 mm/yr per 10 km, bowl rate within 5%; (b) test fails, trend untouched, rest removed; (c) removed ramp ≈ 0 (< 0.5 mm/yr per 10 km); (d) seasonal part kept with a warning. |
| **D2** | Engine wiring: `scla_deramp = "auto"` in `params.py` / schema, `deramp_non_defo`, QC record and figure. Only the computation of `ph_ramp` changes. | Unit suite green; `"y"` / `"n"` bit-identical on the parity tests; one `auto` run of `mexico_g3` (from the step-6 checkpoint if kept, else full). |
| **D3** | Validation: G3.2 Mexico 18 months, `n` / `y` / `auto` against GNSS (leave-one-out, gain); Quang Nam `n` / `auto`, velocity scatter on the stable background. | `auto` is no worse than `n` by more than 10% on the GNSS leave-one-out, and no worse than `y` where the coverage test passes; on Quang Nam the stable-background scatter does not increase. |
| **D4** | Defaults: `auto` for the presets where D3 supports it; docs (skills/insar-processing, guides, ADR). | Owner's decision. |

## 5. Results

### 5.1 D0, offline study (2026-11-04)

Script [code/ramp_auto.py](code/ramp_auto.py), on the four PS states on disk (pass-2 phase; plane per
interferogram on 400k random PS; 500 m cells with ≥ 5 PS).

| Project | Series | Frame | Ramp gradient per ifg, std (mm/10 km) | Trend of the ramp (mm/yr per 10 km, E-W / N-S) | Rest, std |
|---|---|---|---|---|---|
| `mexico_g3` | 16 ep., 0.49 yr | 45 × 40 km | 7.9 / 7.2 | −16.4 / +2.2 | 7.4 / 7.2 |
| `mexico_s1` | 16 ep., 0.49 yr | 29 × 30 km | 6.8 / 7.5 | +14.6 / −22.1 | 6.3 / 6.5 |
| `quangnam_l2b_a55` | 7 ep., 0.21 yr | 44 × 16 km | 5.4 / 4.8 | +60.0 / +3.6 | 2.4 / 4.8 |
| `quangnam_l5_d120` | 24 ep., 0.95 yr | 74 × 49 km | 1.8 / 1.8 | −0.3 / −0.7 | 1.8 / 1.8 |

Findings:

1. **The coverage test of §3.3 as written does not work.**
   - With the threshold "2 × robust std of the cells", the threshold followed the deformation spread itself
     (73–134 mm/yr in Mexico), so almost every cell counted as stable and every project passed.
   - With a noise threshold, max(5, 2 × median PS scatter within a cell), Mexico had 22–29% stable cells and failed
     only on the arbitrary 30% share. The stable cells still lay in all 4 quadrants and spanned 85% of the frame.
   - Quadrants and span are no defence against a smooth bowl: the flank of a bowl wider than the frame looks like a
     plane locally.
2. **The decisive test is whether the plane depends on the frame.** A nuisance ramp is one plane over the whole
   frame. The same data cut differently must give the same gradient. Each half of the frame (W, E, S, N) therefore
   re-selects its own stable cells from scratch:

   | Project | Stable-cell plane, full frame (E-W / N-S) | Halves, E-W gradient | Consistent? |
   |---|---|---|---|
   | `mexico_g3` | −15.7 / +2.9 | −60, −8, −5, −30 | **no** (deviation 45 vs 5) |
   | `mexico_s1` | +33.7 / −5.4 | −49, +28, −11, +59 | **no** (92 vs 10) |
   | `mexico_g3` on the `mexico_s1` overlap | +77.5 / −89.3 | — | **no** |
   | `quangnam_l2b_a55` | +60.7 / +9.6 | +75, −5, +81, +43 | **no** (65 vs 18) |
   | `quangnam_l5_d120` | −0.5 / −1.1 | −4, +1, +1, −1 | **yes** (3.7 vs 5) |

   - Mexico: the same interferograms give −16, +34 or +78 mm/yr per 10 km depending on the frame. The "trend
     ramp" there is the bowl, not a nuisance, so keeping it is the right decision.
   - Quang Nam a55: 2.5 months, with velocity noise of 51 mm/yr within a cell; the trend cannot be anchored.
   - Quang Nam d120: a year of data with local slides on a stable mountain background; consistent, with a negligible
     trend.
3. **A GNSS caution.** On `mexico_g3`, removing the −15.7 plane brings the leave-one-out against MIDAS from 37.8 to
   15.3 mm/yr (window GNSS 62.5 → 45.8). That plane depends on the frame (finding 2), so this agreement at three
   stations is a coincidence of the frame, not evidence for the plane. It is not used.
4. **The engine's degree-2 surface lacks the linear terms.** It is `x² + y² + xy + c`, as StaMPS `ps_deramp`. With
   that form the quadratic is never better than the plane (median gain −129% to +1%), so degree 2 is never picked. A
   full quadratic (`x, y, x², y², xy`) gains 15–18% in Mexico, which is mostly the curvature of the bowl in the
   trend. Not changed in `y`; for `auto` the rest stays a plane until D1 shows that a quadratic rest helps.
5. **The seasonal check is untested.** No state covers ≥ 1 year (d120: 0.95 yr). G3.2 (18 months) is the first case.

**Revised rule for the gate (replaces §3.3 steps 3–4):**
- threshold = max(5 mm/yr, 2 × median PS scatter within a cell);
- the trend is removed only when all of these hold:
  - each of the 4 halves, selecting its own stable cells (≥ 30), gives a gradient within max(5 mm/yr per 10 km,
    30% of the full-frame gradient) of the full-frame plane;
  - the stable cells lie in ≥ 3 quadrants;
  - they span ≥ 60% of the frame;
- the 30% share criterion is dropped.

With this rule:
- Mexico (both frames) and Quang Nam a55 keep the trend;
- Quang Nam d120 removes it (−0.5 / −1.1 mm/yr per 10 km, harmless);
- every project removes the rest.

Caveat (2026-11-05): the rule alone would remove any trend that is planar over the frame, deformation included; it
was calibrated on frames without a tectonic gradient. Fixed in code: the trend is now removed only with a stable area
or the explicit override (§3.3). Quang Nam d120 therefore keeps its (negligible) trend under the default. This D0
study used the pass-2 phase with the SCLA removed; the engine now does the same in pass 2 (§5.3).

Figures (gradient per epoch, stable-cell map): `ramp_auto_<project>.png` in the session scratchpad, to be moved to
the workspace when the code moves to the engine. Rerun with the revised rule in the script (2026-11-05): same four
decisions; the reason for keeping the trend is "plane depends on the frame" in all three cases.

### 5.2 D1, pure functions and synthetic tests (2026-11-05)

Code: `src/geoeyes/processing/ps/steps/ramp.py` (`auto_ramp`, `RampAutoParams`, `RampAuto.summary()` for the
record), tests `tests/unit/processing/test_ps_ramp_auto.py` (11 tests, ~3 s). Scenes: 40 × 40 km, 60,000 PS,
24 epochs over 0.9 yr, PS noise 2 mm, random ramps 7 mm per 10 km per epoch (as Mexico).

| Case | Gate | Result |
|---|---|---|
| (a) local bowl −100 mm/yr + random ramps + trend ramp, 3 seeds | trend within 2 mm/yr per 10 km, bowl within 5% | trend error ≤ 0.06; bowl −98.6 vs −98.5 (≤ 0.2%) |
| (b) bowl wider than the frame + random ramps | test fails, trend untouched, rest removed | "plane depends on the frame" (halves −36 / −1 / −21 / −20 E-W); rest error ≤ 0.02 mm per 10 km |
| (c) no ramp | removed ramp < 0.5 | trend 0.05, rest ≤ 0.02 mm/yr per 10 km |
| (d) seasonal 10 mm per 10 km, 1.5 yr | seasonal part kept, warning | share 96%, kept with a warning; 0.6 mm per 10 km of the annual term removed |
| frame 4 × 4 km | trend kept | "frame < 5 km" |
| phase in rad, NaN rows | same ramp as in mm | yes; NaN rows stay NaN |

Findings:

1. **The stable-cell refit matters.** The trend fitted on all PS is biased by the bowl by ~1 mm/yr per 10 km. The
   refit on the stable cells brings this down to ≤ 0.06.
2. **A random ramp series has its own straight line in t.** A finite series cannot tell it apart from a trend, so
   the "true" trend in the tests is the input trend plus that line. Its size is σ_rest / √Σ(t − t̄)²:
   - about 5.6 mm/yr per 10 km in the test scene;
   - about **13 mm/yr per 10 km for `mexico_g3`** (7.4 mm per 10 km rest, 0.49 yr);
   - about 2.5–3 for the 18-month G3.2.

   Where the trend is kept (Mexico), this part of the ramp noise stays in the velocity, about ±30 mm/yr across the
   45 km frame on six months of data. Only a longer series or GNSS reduces it. This is one more reason for G3.2.
3. **Degree.** `auto` uses a plane for the rest. The engine's degree-2 surface is not used, because it lacks the
   linear terms (§5.1 finding 4).

### 5.3 D2, engine wiring (2026-11-05): drafted, uncommitted, pending review

What exists in the working tree (not committed; `steps/ramp.py` and its test file are untracked):

- `params.py`: `scla_deramp = "auto"` accepted next to `"y"` / `"n"`; `deramp_non_defo` (lon/lat polygon) parsed
  as `aps_non_defo`; `engine_params` sets `deramp_auto` / `deramp_non_defo`. No entry in the config schema yet.
- `runner.py::process`: builds a `DerampAuto` (t in years from the master, mm per rad, weights 1/ifg_std² as the
  velocity fit, the PS inside `deramp_non_defo`) and passes it to `calc_scla` in both passes. The step-6 checkpoint
  key gets `deramp_auto` (`RAMP_AUTO_VERSION`) and the polygon only under `auto`, so the `y` / `n` keys are unchanged.
- `scla.py::calc_scla`: with `auto`, `auto_ramp` replaces `deramp`; `SclaResult.ramp_auto` keeps the decision
  (`RampAuto.record()`), carried through `smooth_scla`.
- `runner.py`: one log line with the decision, `summary()` in the run record, and `figures/ramp.png`
  (`ramp.py::ramp_figure`; a failure only logs a warning).

**The `auto` run of `mexico_g3` (2026-11-05, reviewed code, `RAMP_AUTO_VERSION` 2).** Variant c (ERA5 on every
interferogram), steps 1–5 reused from the v3 run, written to a separate folder `ps_runs/sentinel1-asc-078_auto` (the
`n` run untouched); 3.63 M points, 1770 s.

- Decision: rest removed, **trend kept** ("plane depends on the frame"), as in D0. Halves (engine x / y axes):
  +19/+31, +36/−9, +23/−20, +2/+17 mm/yr per 10 km, max deviation 31 vs tolerance 5. Stable threshold 12.1 mm/yr
  (within-cell scatter 6.1; 6.9 before the SCLA prior), 1134 of 4981 cells stable.
- Seasonal: not applicable (0.49 yr).
- Against GNSS, same parameters as the v3 analysis (vertical, offset, window GNSS). The LOS was taken from the v3
  product, nearest point (the PS run has no LOS columns):

  | | `n` (v3) | `auto` |
  |---|---|---|
  | `disp_scn_mm`: detrended RMSE ICMX / MMX1 / MXTX (mm) | 2.6 / 1.5 / 3.8 | 2.5 / 1.5 / 3.9 |
  | `disp_scn_mm`: leave-one-out (mm/yr) | 66.0 | 74.2 |
  | `disp_mm` (raw): detrended RMSE ICMX / MMX1 / MXTX (mm) | 10.0 / 4.9 / 14.6 | **3.5** / 6.1 / 14.9 |
  | `disp_mm` (raw): leave-one-out (mm/yr) | 63.4 | 70.9 |
  | InSAR rate ICMX / MMX1 / MXTX (`disp_scn_mm`, mm/yr) | +26.0 / −131.4 / −13.0 | +21.8 / −128.7 / −23.7 |

  Reading:
  - Removing the rest cleans the raw series at ICMX (10.0 → 3.5 mm), but not at MXTX: the per-epoch noise there
    is not planar. The SCN still catches it (3.9 mm).
  - After the SCN the two runs are almost the same, because the SCN already removed the per-epoch ramp.
  - The leave-one-out grows by 8 mm/yr (12%). That is within the noise of the ramp trend (~13 mm/yr per 10 km on
    6 months, §5.2 finding 2). Three stations cannot show that `auto` is better or worse than `n`; D3 (18 months)
    can.
  - The large rate errors at ICMX and MMX1 are not from the ramp.
- The first run (pre-review code, `RAMP_AUTO_VERSION` 1) gave the same decision and the same GNSS numbers within
  0.2 mm/yr.
- Memory: the first run ran out of RAM in step 8 (29.7 GB) with a float64 (n, n_ifg) ramp. The `auto` ramp is now
  kept as float32.
- Labels: the engine's local frame is rotated to the heading, so the gradients and halves in the record and the
  figure are along x / y, not east / north. The figure labels are fixed.
- `y` / `n` parity: the legacy fixtures are not on this machine (the parity tests skip). The `y` / `n` branches are
  unchanged in code (`auto=None`) and their checkpoint keys are unchanged; a bit-identical check remains to be done
  when the fixtures are available.
- Operational note: with `resume_from`, checkpoints are read from the old folder, so a run stopped in the new folder
  restarts from step 6.
- **Ring pattern (owner, 2026-11-05): `auto` changed the unwrapping, and mostly for the worse.** The velocity map
  of `auto` shows arcs that `n` does not. `auto − n` (3.56 M PS matched on line/sample) is not a plane but patches
  with constant values and sharp, partly straight edges (±20–40 mm/yr). Per epoch, after a plane is taken out, the
  difference is an integer number of λ/2 (27.7 mm): ±1 cycle, on up to 27% of the PS (2024-08-19; 15% on
  2024-05-27, 13% on 2024-08-07). The patches are weakly connected areas (NW hills, the sparse east, across the
  airport and the lake). Where the runs differ (13 k of 30 k sampled PS), adding `auto`'s cycles to `n` makes the
  series rougher in 68% of the PS (quadratic-fit residual 11.1 → 11.9 mm). So these are unwrapping errors of `auto`.
  Mechanism: the per-ifg plane is a plain least-squares fit over all PS of the pass-1 unwrapped phase. It therefore
  also absorbs pass-1 cycle patches (the epochs with the largest rest, e.g. −24 mm per 10 km on 2024-05-27, are the
  epochs with the largest patches). Pass 2 takes that plane out of the wrapped phase before unwrapping
  (`steps/unwrap.py`). Across a long weak link (km), this shifts the phase difference by a large part of a cycle and
  flips the choice. A plane cannot draw a ring by itself; the ring is the edge of a patch that changed by one
  cycle. `y` does the same (same plane, same place). The ICMX gain above is real but smaller than this damage;
  the D2 reading "after the SCN the two runs are almost the same" was wrong for the map.
  Fixes (done 2026-11-05, `RAMP_AUTO_VERSION` 3): (1) under `auto` the ramp is removed after the unwrapping only
  (velocity, SCN); pass 2 no longer takes it out of the wrapped phase (`runner.py`; `y` keeps the StaMPS order);
  (2) the per-ifg plane is fitted robustly (`robust_epoch_planes`): cell medians (500 m), each cell's line in t
  taken out, plane of the residual with MAD rejection, the cells' lines added back as planes. Unit test: a corner
  one cycle off in one ifg tilts the plain plane by 2.7 mm per 10 km, the robust one by < 1.
  Rerun (`ps_runs/sentinel1-asc-078_auto3`, same decision: rest removed, trend kept). `auto3 − n` is now a smooth
  plane (the rest's own line in t) plus thin strips; PS one cycle off per epoch: ≤ 2.4% on 14 of 15 epochs (were
  up to 27%). One epoch keeps a patch: 2024-07-26 (12 days after the master), the subsidence bowl is +1 cycle in
  `auto3` (+11 mm relative to the surroundings: uplift in the bowl, so `auto3` is wrong there; `n` −8 mm). The
  SCLA of the two runs differs by only 1–6 mm on that epoch, so this is a marginal unwrapping (two near-equal
  solutions) that any small input change can flip, not the ramp. Against GNSS (same settings as above):

  | | `n` (v3) | `auto` (v2) | `auto3` |
  |---|---|---|---|
  | `disp_scn_mm`: detrended RMSE ICMX / MMX1 / MXTX (mm) | 2.6 / 1.5 / 3.8 | 2.5 / 1.5 / 3.9 | 2.6 / 1.5 / 3.8 |
  | `disp_scn_mm`: leave-one-out (mm/yr) | 66.0 | 74.2 | **56.5** |
  | `disp_mm` (raw): detrended RMSE ICMX / MMX1 / MXTX (mm) | 10.0 / 4.9 / 14.6 | 3.5 / 6.1 / 14.9 | 4.9 / 6.0 / 10.9 |
  | `disp_mm` (raw): leave-one-out (mm/yr) | 63.4 | 70.9 | **48.0** |

  Open: a check for marginal unwrapping (e.g. flag patches whose one-epoch cycle change makes the series
  smoother) would help `n` as much as `auto`; it is a separate item, not part of the ramp rule.

Fixes of 2026-11-05 (D2 review, code and unit tests; 17 tests): planar trend only with a constraint (§3.3), seasonal
F-test (§3.2), SCLA prior (below). `[ps] ramp_auto_allow_planar` added to `params.py` (the `[ps]` table is not in
the config schema).

**Fixed in code (2026-11-05): the engine now tests the phase D0 calibrated (pass 2).** `auto_ramp` runs inside
`calc_scla`, before the SCLA is estimated, so the DEM-error (B⊥-correlated) term was still in its input, while D0
(`code/ramp_auto.py`) used unwrapped − APS − SCLA. The DEM error raises the PS scatter within a cell, which sets the
stable threshold (max(5, 2 × scatter)). Now `calc_scla(scla_k_prior=…)`: in pass 2 the runner passes the smoothed
pass-1 K, and K·B⊥ is taken out of the phase the ramp is estimated on (the SCLA itself is still fitted on the full
phase). Pass 1 has no earlier SCLA and keeps the DEM error in the test; its ramp only feeds the pass-2 unwrapping,
the pass-2 decision is the one kept. Without `subtr_tropo` (one pass) the limitation remains.

## 6. Limitations

- **A steady nuisance under a frame-wide bowl stays unresolved.** A ramp that grows linearly in time is invisible to
  every phase-only test when the deformation covers the frame. The test reports this case instead of guessing; GNSS
  (`plane`, ≥ 3 stations) or a longer frame with a stable margin are the remedies.
- **The halves test detects curvature, not nuisance (fixed in code 2026-11-05, §3.3).** A planar trend is now kept
  unless the user gives a stable area or the override; the cost is that a true planar nuisance stays in the
  velocity without one. A curved long-wavelength ionosphere is still kept. GNSS is not wired into the engine.
  D4 stays gated on the `y` / `n` parity check and the `mexico_g3` run.
- The seasonal safeguard (fixed in code 2026-11-05, §3.2) cannot run under 12 epochs; there the annual part is kept
  untested.
- The pass-1 frame test still sees the DEM error (no earlier SCLA); pass 2 does not (§5.3).
- The plane / quadratic surface is a model. Ionospheric screens at solar maximum can have shorter wavelengths; those
  belong to the split-spectrum correction (TODO item 2 for L-band; S1 to be planned), not to the deramp.
- The 500 m cell and the thresholds were set in D0 on four states only (§5.1); D3 checks them on G3.2.
- With a short series, the straight-line part of the random ramps cannot be removed when the trend is kept
  (§5.2 finding 2).

## 7. References

- Hooper, A., Segall, P., Zebker, H. (2007). Persistent scatterer InSAR for crustal deformation analysis, with
  application to Volcán Alcedo, Galápagos. *JGR* 112, B07407.
- Fattahi, H., Amelung, F. (2014). InSAR uncertainty due to orbital errors. *GJI* 199, 549–560.
- Yunjun, Z., Fattahi, H., Amelung, F. (2019). Small baseline InSAR time series analysis: unwrapping error
  correction and noise reduction. *Computers & Geosciences* 133, 104331.
- Liang, C., Agram, P., Simons, M., Fielding, E. (2019). Ionospheric correction of InSAR time series analysis of
  C-band Sentinel-1 TOPS data. *IEEE TGRS* 57, 6755–6773.
