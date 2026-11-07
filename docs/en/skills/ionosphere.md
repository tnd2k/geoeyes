# Skill: recognise and correct the ionospheric phase

> Tell an ionospheric ramp from motion, troposphere, orbit or a subswath step, remove it from Sentinel-1 stacks by
> range split-spectrum, and accept or reject the result. Status: operational for Sentinel-1 IW with the native
> stack builder; no correction for other sensors (stripmap, L band). Last checked against the code: 2026-11-01.
> Settings: `[stack] ionosphere`, `ionosphere_model`, `ionosphere_smooth_m`. Web app: project → Settings; checks
> in the product report; Principles → chapter 6 (`#/learn-ionosphere`).

## 1. When to use it

- **Question.** Is a broad ramp or a straight step on a velocity map ionosphere, and is it gone after correction?
- **Decision.** Turn `[stack] ionosphere = "split_spectrum"` on (and which model), keep a plane removal in the
  decomposition, or look elsewhere (troposphere, unwrapping).
- **Suspect the ionosphere** when two or more hold ([guide](../guide/ionosphere.md) §1): magnetic latitude 5–25°
  (equatorial anomaly crests) or polar; local time afternoon to early night (S1 ascending ≈ 18:00); near solar
  maximum (cycle 25: 2024–2026); L band; area larger than 10 km. The report check flags a product as risky when
  |latitude| < 30° and the mean local pass time is 14:00–23:00 (`report/qc.py`).
- **Do not use it** for patches of 1–10 km or height-correlated signal (troposphere: [atmosphere.md](atmosphere.md)),
  nor on a stack that does not span the dates of interest. On non-Sentinel-1 tracks the setting is ignored.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Sentinel-1 IW SLC bursts of the track | yes | phase `acquire` from ASF with `[acquire] date_range` and the track's `relative_orbit`; needs a NASA Earthdata token | `archive/sentinel1/<track_id>/<year>/<SLC>/` (`bursts.json`, `IWn_POL_<burst>.tiff`, XML); token in `EARTHDATA_TOKEN` (machine-wide or `.env`) | the range bandwidth must be in the annotation, otherwise the build stops (`DataError`) |
| Precise orbits (POEORB) | yes | fetched automatically with the same token | `<workspace>/cache/orbits` | the geometric phase must be exact: about half its error leaks into the estimate |
| Native stack builder | yes | `[stack] engine = "native"` (default) | project.toml | SNAP stacks are not supported |
| A second geometry over the same area | strongly advised | another track (asc + desc) in the same project | `[[tracks]]` | the decisive test: a ramp seen in one geometry only cannot be motion |
| GNSS stations | optional | NGL ([gnss-calibration.md](gnss-calibration.md)) | – | an independent gradient check |
| TEC level (GIM, CODE IONEX) | optional | external (e.g. CODE / CDDIS IONEX files) | not read by GeoEyes | gives the TEC level only (2.5° × 5°), not gradients over 15 km |

Checklist:

- [ ] the track is Sentinel-1 IW, stack engine `native`;
- [ ] the pass is at risk (local time, latitude) or a ramp already shows up in one geometry only;
- [ ] Earthdata token set; precise orbits available;
- [ ] a second geometry or GNSS to judge the result.

## 3. Method

### 3.1 Range split-spectrum (Gomba et al. 2016), `processing/stack/native/iono.py`

- Two sub-bands, centred at f_L = f₀ − B/3 and f_H = f₀ + B/3, each B/3 wide (cosine taper on 10 % of the width);
  B is the smallest processed range bandwidth of the subswaths used.
- Each sub-band interferogram φ_k = φ_nd·f_k/f₀ + φ_iono·f₀/f_k. Both sub-bands are flattened with the
  **full-band** geometric phase (the resampling has already put the secondary echo on the reference pixel).
- Ionospheric phase at f₀:
  φ_iono = f_L·f_H / (f₀·(f_H² − f_L²)) · (φ_L·f_H − φ_H·f_L), computed as a·φ_L − b·(φ_H − φ_L) with
  a = f_L·f_H/(f₀(f_H + f_L)) and b = f_L²·f_H/(f₀(f_H² − f_L²)). Noise amplification ≈ f₀/(2(f_H − f_L)), ~90×.
- **Cells.** The sums are formed on coarse cells of 450 m (looks = 450 m / azimuth spacing × 450 m / ground range
  spacing, ≈ 32 × 122 pixels) over the **whole bursts**, not only the crop (≈ 45 × 175 km in Hanoi).
- **Cells used.** Low-band coherence ≥ 0.3 (then φ_L is unwrapped by weighted IRLS) and cross-band coherence
  g ≥ 0.7; fewer than 30 such cells raises an error for that date.
- **Fit.** Weighted least squares, weights g²/(1 − g²) (denominator floored at 10⁻³), 4 iterations rejecting cells
  beyond 3 × 1.4826 · MAD, then evaluated on the crop. `ionosphere_model`:
  - `local` (default): a plane centred on the crop, each cell also weighted by exp(−d²/(2·s²)) with
    s = `ionosphere_smooth_m` (10,000 m);
  - `plane` / `quadratic`: one surface over the whole bursts;
  - `smooth`: a Gaussian surface of width `ionosphere_smooth_m`.
- **Removal.** The phase is removed from the stored secondary SLC: slc·exp(j(φ_iono + seam steps)).

### 3.2 Subswath steps, `s1_stack.py`

For every seam inside the crop (at least 44 columns from its edges), per date: the phase of the interferogram on the
right side against the left side, 40 columns per side, 4 columns left out at the cut, in blocks of 32 lines,
averaged with the block coherences as weights. Output: step (rad), consistency (0–1), number of blocks.

- consistency < 0.3 or fewer than 8 blocks: not measurable, the step is kept and a warning logged;
- steps accumulate from near range and are removed against the widest subswath (the anchor);
- seam alignment is done on every native Sentinel-1 stack, with or without split-spectrum. With split-spectrum the
  step is also removed from the low sub-band before the estimate (`WideArea.shift`), otherwise about half of it would
  pass into φ_iono.

### 3.3 Acceptance criteria, `report/qc.py`

| Check | Pass | Look again |
|---|---|---|
| Velocity gradient difference with another track, each axis (over the common area, ≥ 1000 points each) | < 0.3 mm/yr/km | > 0.5 |
| Velocity step across a subswath seam (points within 0.08° of incidence on each side, ≥ 50 each) | < 2 mm/yr | > 4 |
| Decomposition without plane removal: east/up correlation | \|r\| < 0.3 | > 0.5 |
| Decomposition: cells with significant east-west motion | < 10 % | > 15 % |
| Per date, ramp left in the interferograms vs ionospheric gradient removed (≥ 6 dates) | \|r\| < 0.3 | > 0.5: wrong scale |

Between the two thresholds the status is `borderline`.

## 4. Steps

1. **Diagnose before correcting** ([guide](../guide/ionosphere.md) §3):
   - velocity plane of each track: `geoeyes decompose <project>` prints the ramp of every product and warns when
     one spans more than `ramp_warning_mm_yr` (5) and twice the other;
   - per interferogram, is the ramp already in `phase/unwrapped` of `ps_runs/<track>/state.h5`?
   - local pass time (`sensing_mid_utc` of the stack) and TEC level;
   - ESD per date (`esd_shift` of the stack) against the along-track ramp of each date;
   - a straight line along track: compare its column with `subswath_columns` of the stack. At a seam it is a
     subswath step, not the ionosphere and not a fault.
2. **Turn it on** (Settings tab or project.toml):
   ```toml
   [stack]
   ionosphere = "split_spectrum"      # none (default) | split_spectrum
   ionosphere_model = "local"         # local (default) | plane | quadratic | smooth
   ionosphere_smooth_m = 10000
   ```
3. **Rebuild the stack.** `geoeyes run <project> --track <track> --force build_stack`. A changed `ionosphere_key`
   (method, model, radius) makes the builder coregister every date again, then `ps` and the product follow. Time:
   a full stack build plus the sub-band filtering and resampling of every burst; not measured separately.
4. **Read the log**, one line per date:
   ```
   2025-10-04: ionosphere gradient (az, rg) [-0.1342, 0.0014] ± [0.0161, 0.0142] rad/km at the crop, 3898 cells over [45.6, 174.9] km
   2026-07-02 seam IW3: interferogram phase step -2.298 rad (consistency 0.96, 32 blocks) removed
   ```
   (examples from the [guide](../guide/ionosphere.md) §4.2–4.3).
5. **Judge.** Product report (`products/<id>/report.pdf`, quality checks) with the criteria of §3.3; web app
   Principles → chapter 6 for the per-date gradients, local times, ESD and seam steps of a stack.
6. **If it still fails:** `[postprocess.decompose] deramp = "plane"` removes a plane from each product before the
   decomposition (it also removes any real tilt: say so in the report).

## 5. Outputs and how to read them

| Where | What |
|---|---|
| stack variable `iono` (date, y, x), rad | ionospheric phase removed at f₀ |
| stack variable `iono_cells` | coarse sums per date (low, high·conj(low), \|low\|, \|cross\|): another model can be fitted later without reading the SLCs |
| stack attribute `ionosphere_per_date[date]` | `rad_per_km_az_rg` (gradient at the crop), `se_rad_per_km_az_rg`, `cells`, `kept`, `area_km`, `noise_rad`, `model` |
| attributes `ionosphere_bandwidth_hz`, `ionosphere_looks`, `ionosphere_model`, `ionosphere_smooth_m`, `ionosphere_key` | what was run |
| attribute `subswath_phase_offsets[date][IWn]` | `rad`, `consistency`, `blocks`, plus `anchor` |
| report quality checks | `pass` / `borderline` / `review` / `info` per criterion of §3.3 |

Reading: gradients in rad/km at f₀; × λ/(4π) (4.41 mm/rad at C band) gives mm/km of LOS. A formal error of about
0.015 rad/km is normal; `noise_rad` ≈ 10 rad per cell is normal (the ~90× amplification is compensated by thousands
of cells). Fewer than a few hundred `kept` cells or ± above 0.05 rad/km: a weak date, check coherence.

## 6. Quality checks

- Every criterion of §3.3 at `pass`, or `borderline` explained.
- The per-date correlation of the ramp left with the gradient removed is low (|r| < 0.3). If it is the only
  criterion that passes, what remains is **not** ionosphere: look at troposphere, unwrapping, odd dates.
- Seam steps: two levels (≈ 0 or a constant) are expected; the velocity step at the seam drops below 2 mm/yr.
- Hanoi asc 128 reference figures ([guide](../guide/ionosphere.md) §6): seam step +8.0 → +1.4 mm/yr; gradient
  gx/gy +0.75/−1.50 → −0.49/−0.77 mm/yr/km against −0.02/−0.20 for desc 091; horizontal share 41 % → 11.5 %.

## 7. Limits and pitfalls

- C-band split-spectrum is very noisy: only smooth forms (a local plane) are estimable, not post-sunset plasma
  bubbles of a few km.
- `local` assumes a nearly linear ionosphere within ~10 km of the crop.
- Scintillation decorrelates the phase; split-spectrum cannot fix it.
- Subswath steps are measurable only where both sides of the seam are coherent (urban areas), not over farmland or
  water. Their root cause is unknown.
- Split-spectrum removes a real signal (Hanoi: removed along-track gradient varies by 0.49 mm/km between dates), but
  the remaining Hanoi ramp is not dispersive: most likely evening troposphere.
- The docstring of `iono.py` still says "quadratic by default"; the default is `local` (schema and function).
- No ionospheric correction exists for stripmap or spotlight sensors (CSK, Capella, ICEYE, Umbra, TerraSAR-X) or
  for ALOS (L band) in GeoEyes: the setting is silently ignored for them.

## 8. On a new area or sensor

- **Low latitude, dusk pass (S1 ascending in Southeast Asia, Latin America):** turn it on from the first build.
- **Mid latitudes, dawn passes:** leave `none`; check the report's "Ionospheric correction" line.
- **Large crop or quiet ionosphere:** `plane` or `quadratic`; **high coherence, structure to keep:** `smooth`.
- **Carries over:** the criteria of §3.3 and the diagnosis order.
- **Local habit:** `projects/hanoi_s1` sets `ionosphere = "split_spectrum"` and `[postprocess.decompose] deramp =
  "plane"`; do not read north-south gradients of the ascending track alone.

## 9. References

- Code: `src/geoeyes/processing/stack/native/iono.py`, `src/geoeyes/processing/stack/native/s1_stack.py`
  (`seam_step`, split-spectrum loop), `src/geoeyes/controller/phases/build_stack.py`,
  `src/geoeyes/config/schema.py` (`StackSection`), `src/geoeyes/report/qc.py`, `src/geoeyes/learn/ionosphere.py`,
  `webapp/src/pages/LearnIonosphere.tsx`, `src/geoeyes/ml/decompose.py` (`deramp`, `ramp_warning_mm_yr`).
- Guides and notes: [../guide/ionosphere.md](../guide/ionosphere.md),
  [../research/two-geometries-and-soft-soil.md](../research/two-geometries-and-soft-soil.md) §4.2.
- Skills: [insar-processing.md](insar-processing.md), [atmosphere.md](atmosphere.md),
  [decompose-and-soft-soil.md](decompose-and-soft-soil.md), [gnss-calibration.md](gnss-calibration.md).
- Papers: Gomba G, Parizzi A, De Zan F, Eineder M, Bamler R (2016) Toward operational compensation of ionospheric
  effects in SAR interferograms: the split-spectrum method. *IEEE TGRS* 54(3):1446–1461.
