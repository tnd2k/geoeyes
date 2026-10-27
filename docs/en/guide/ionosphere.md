# Ionosphere: recognise and correct

For people processing InSAR with GeoEyes. It helps decide whether a ramp or a stripe on a velocity map comes from
the ionosphere, and what to do about it. The figures come from Hanoi, Sentinel-1 ascending track 128 and descending
track 91, 2025-10 → 2026-10 ([two-geometries-and-soft-soil.md §4.2](../research/two-geometries-and-soft-soil.md)).

## Contents

1. [When to suspect the ionosphere](#1-when-to-suspect-the-ionosphere)
2. [Signatures](#2-signatures)
3. [Diagnosis, step by step](#3-diagnosis-step-by-step)
4. [Correction in GeoEyes](#4-correction-in-geoeyes)
5. [Acceptance criteria](#5-acceptance-criteria)
6. [The Hanoi case](#6-the-hanoi-case)
7. [Limitations](#7-limitations)

## 1. When to suspect the ionosphere

The ionospheric phase is proportional to the total electron content (TEC) and inversely proportional to frequency.
The risk is high when two or more of these hold:

| Factor | High risk | Low risk |
|---|---|---|
| Magnetic latitude | 5–25° (the crests of the equatorial ionization anomaly, EIA), polar regions | mid latitudes |
| Local acquisition time | afternoon, dusk, early night (Sentinel-1 ascending ≈ 18:00) | dawn (descending ≈ 06:00) |
| Solar cycle | near maximum (cycle 25: 2024–2026) | near minimum |
| Band | L (ALOS-2, NISAR): ~4 times C in phase, ~18 times in mm | C (Sentinel-1), X |
| Area | > 10 km, long strips along track | a few km |

Hanoi (21° N, magnetic latitude ≈ 11–14°), imaged at 18:06 near the maximum of cycle 25, is about the worst case at
C band. The GIM (CODE IONEX) gives 39–111 TECU at the ascending passes, against 8–19 TECU at the descending ones.

## 2. Signatures

| Signature | Ionosphere | Troposphere | Orbit | Subswath step | Real motion |
|---|---|---|---|---|---|
| Shape | broad ramp, often **along track**; wavelengths 10–100 km | patches of 1–10 km, or scaling with height | plane | **straight line** along track, exactly at an IW1/IW2/IW3 seam | follows geology, structures |
| In both geometries | no (only the afternoon/evening one) | yes, stronger in the afternoon one | not necessarily | only where a seam is in the area | **yes**, consistent with the LOS projection |
| Date to date | changes sign and size | random, strong in the wet season | constant per date | **two levels**: ≈ 0 or a constant (−2.2 rad in Hanoi) | accumulates steadily |
| Dispersive (seen by split-spectrum) | **yes** | no | no | no | no |
| ESD | azimuth shift correlated with the along-track ramp | no | no | ESD differs between the subswaths (+0.012 lines) | no |
| Inside TOPS bursts | strong gradients leave stripes at burst edges | no | no | no | no |

Two tests decide:
1. **Compare the two geometries.** Vertical motion appears almost alike in both (l_u ≈ 0.77). North-south motion
   hardly enters either line of sight (north coefficient ≈ 0.1). A north-south ramp in one geometry only therefore
   **cannot be motion**.
2. **Split-spectrum.** Only the ionosphere is dispersive. What is left after it is not ionosphere, unless the
   estimate is off (see §5).

## 3. Diagnosis, step by step

1. **Velocity plane of each track.** The decomposition (`[postprocess.decompose]`) prints the ramp of every product
   and warns when one is more than twice the other (`ramp_warning_mm_yr`). Hanoi at first: ascending 26.9 mm/yr,
   descending 3.9 over the common area.
2. **Plane of every interferogram** (`ps_runs/<track>/state.h5`: `phase/unwrapped` and the components `aps`, `scla`,
   `scn`). If the ramp is already in the unwrapped phase, and not from ERA5 or the DEM error, it is in the images.
3. **Acquisition time and TEC.** `sensing_mid_utc` of the stack, in local time; TEC level from the GIM. The GIM
   (2.5° × 5°) gives the level only, not gradients over 15 km.
4. **ESD per date** (`esd_shift` in the stack), against the along-track ramp of each date (Hanoi, before correction:
   r = −0.56, p = 0.003 ascending; +0.19, p = 0.37 descending).
5. **A straight line along track?** Compare its column with `subswath_columns` of the stack. At a seam, it is a
   subswath step (§4.3), not the ionosphere and certainly not a fault.

## 4. Correction in GeoEyes

### 4.1 Turning on split-spectrum

```toml
[stack]
ionosphere = "split_spectrum"      # none (default) | split_spectrum
ionosphere_model = "local"         # local (default) | plane | quadratic | smooth
ionosphere_smooth_m = 10000        # radius of the Gaussian weight around the crop
```

The band is split in three; the low and high sub-bands give two interferograms from which the dispersive part is
separated. The estimate uses the **whole bursts** (coarse cells of 32 × 122 pixels, about 45 × 175 km), not only the
crop, and is then evaluated on the crop.

Choosing the model:
- `local` (recommended): a plane around the crop, Gaussian-weighted by `ionosphere_smooth_m`. The dusk ionosphere has
  structure at 10–30 km that a surface over the whole bursts smooths away, while the crop alone (~15 km) is too
  noisy.
- `plane` / `quadratic`: one surface over the bursts, for a large crop or a quiet ionosphere.
- `smooth`: a Gaussian surface, to keep smaller structure when coherence allows.

Changing these keys forces a stack rebuild (`ionosphere_key`):
`geoeyes run <project> --track <track> --force build_stack`.

### 4.2 Reading the log

One line per date:

```
2025-10-04: ionosphere gradient (az, rg) [-0.1342, 0.0014] ± [0.0161, 0.0142] rad/km at the crop, 3898 cells over [45.6, 174.9] km
```

- Gradients in rad/km at the centre frequency; times 4.41 gives mm/km of LOS (C band).
- The ± is the formal error; about 0.015 rad/km (0.07 mm/km) is normal.
- `noise_rad` in the stack's `ionosphere_per_date`, about 10 rad per cell, is normal: split-spectrum amplifies phase
  noise about 95 times, compensated by thousands of cells.
- Fewer than a few hundred `kept` cells, or ± above 0.05 rad/km, means a weak estimate for that date: check
  coherence.

Stored in the stack: the variable `iono` (removed phase, per date) and the attribute `ionosphere_per_date`.

### 4.3 Subswath steps

When the crop spans two subswaths, GeoEyes measures the phase step across each seam, per date, and removes it before
the mosaic, with the widest subswath as anchor. The step does not depend on frequency, so it is also taken out of
the low sub-band before the split-spectrum; otherwise about half of it (a ≈ 0.5) would pass into the ionospheric
estimate.

```
2026-07-02 seam IW3: interferogram phase step -2.298 rad (consistency 0.96, 32 blocks) removed
```

- Consistency below 0.3 or fewer than 8 blocks: not measurable, the step is kept and a warning is logged.
- Per-date values: the stack attribute `subswath_phase_offsets`.
- The step has two levels (≈ 0 or a constant) and coincides with the dates whose ESD differs between the subswaths.
  Its root cause is unknown.

### 4.4 When split-spectrum is not enough: removing a plane

`[postprocess.decompose] deramp = "plane"` removes a plane from each product's velocities before the decomposition.
It also removes any real tilt of the area. Use it only when §5 fails, and say so in the report.

## 5. Acceptance criteria

Against the other geometry (or GNSS) over the common area:

| Criterion | Pass | Look again |
|---|---|---|
| Velocity gradient difference between the two tracks (each axis) | < 0.3 mm/yr/km | > 0.5 |
| Velocity step across a subswath seam | < 2 mm/yr | > 4 |
| Decomposition without plane removal: east/up correlation | \|r\| < 0.3 | \|r\| > 0.5 |
| Decomposition: cells with "significant" horizontal motion | < 10 % | > 15 % |
| Correlation, per date, of the ramp left with the ionospheric gradient removed | \|r\| < 0.3 | \|r\| > 0.5: wrong scale |

If only the last criterion passes, what is left is **not ionosphere**: look at the troposphere, unwrapping, odd
dates.

## 6. The Hanoi case

| Ascending 128 product | Seam step | gx / gy (mm/yr/km) | Decomposition as is: horizontal / r |
|---|---|---|---|
| v1, no correction | +8.0 | +0.75 / −1.50 | 41 % / −0.80 |
| v3, split-spectrum | +9.6 | +0.22 / −0.79 | |
| v4, + seam alignment | +0.9 | −0.58 / −0.92 | 17.1 % / −0.59 |
| v6, + step out of the sub-bands | +1.4 | −0.49 / −0.77 | 11.5 % / −0.51 |
| descending 91 (reference) | — | −0.02 / −0.20 | |

Split-spectrum removes a real signal: the removed along-track gradient varies by 0.49 mm/km between dates, with a
trend of 0.81 mm/km/yr (about 11 mm/yr over 14 km).

**What is left after v6 is not ionosphere.** Per date:
- The along-track ramp left is barely correlated with the ionospheric gradient removed (r = 0.18): not a
  proportional under-correction.
- It varies by 0.64 mm/km between dates, nearly 10 times the formal error of the ionospheric estimate (0.07 mm/km).
- The range ramp left is largest in summer 2026 (+2.4 … +3.6 and −3.0 mm/km on 07-14, 08-19, 08-31); the descending
  track in the same season: −0.3 … +0.9.

This residual is not dispersive, so it is most likely the **troposphere**: evening convection in the Hanoi wet
season that ERA5 (0.25°, hourly) misses. Some may come from unwrapping on the step dates.

For Hanoi: use v6, keep `deramp = "plane"` in the decomposition, and do not read north-south gradients of the
ascending track alone.

## 7. Limitations

- C-band split-spectrum is very noisy (~95× amplification): only smooth forms (a local plane) can be estimated, not
  structures of a few km such as post-sunset plasma bubbles.
- The `local` model assumes a nearly linear ionosphere within ~10 km of the crop.
- The geometric phase must be recomputed exactly before splitting: about half of its error passes into the estimate.
- Ionospheric scintillation decorrelates; split-spectrum cannot fix it.
- Subswath steps are measurable only where both sides of the seam are coherent (urban areas); over farmland or water
  they may not be.
