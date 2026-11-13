# Resampling kernel of the native stacks (cubic spline vs Lanczos)

Started 2026-11-11, after the owner read that VINSAR-VIPHAP 1.1.1 resamples CSK with a "carrier-aware Lanczos"
kernel (`vinsar/core/csk_complex_resampling.py`, radius 4).

## Where we are

| | GeoEyes (`processing/stack/native/stripmap.py`, `tops.py`) | VINSAR 1.1.1 |
|---|---|---|
| Carrier | Doppler centroid removed **as a function of range**, f_dc(τ) (CSK "Centroid vs Range Time Polynomial"); TOPS: the full azimuth ramp | one **constant** f_dc / PRF (first coefficient only) |
| Kernel | cubic B-spline (`scipy.ndimage.map_coordinates`, order 3, prefiltered) | Lanczos, radius 4 (8 × 8 taps), weights normalised |

On the Hanoi CSK scene of 2011-07-01, f_dc goes from −751 to −660 Hz across the swath: VINSAR's constant is off by up to
57 Hz.

## Simulation (scratch `interp_cmp.py`, 2026-11-11)

Band-limited complex signal with the CSK parameters of that scene (PRF 3071 Hz, azimuth bandwidth 2580 Hz =
oversampling 1.19, range 117 / 146.25 MHz = 1.25, Hamming 0.80 / 0.68), 3000 random fractional positions, against
the exact value. Coherence loss 1 − |γ| / phase rms:

| Kernel | CSK azimuth | CSK range | S1 IW azimuth | S1 IW range |
|---|---|---|---|---|
| cubic spline (GeoEyes now) | 2.0e-3 / 6.9° | 6.3e-4 / 4.1° | 9.3e-5 / 1.6° | 4.7e-4 / 2.9° |
| Lanczos r = 4 (VINSAR, exact carrier) | 6.6e-4 / 4.0° | 1.3e-4 / 1.5° | 1.4e-5 / 0.7° | 4.4e-5 / 0.8° |
| Lanczos r = 8 | 6.0e-6 / 0.4° | 2.6e-6 / 0.2° | 6.2e-7 / 0.1° | 1.4e-6 / 0.2° |
| cubic spline, carrier not removed | 7.2e-2 / 33° | — | — | — |

The carrier matters most (both codes remove it); the kernel next: Lanczos 4 is 3–5 × better than the spline and
Lanczos 8 another ~100 ×. VINSAR's note "radius 4 verified better than 8/16/32" is not what a band-limited signal
shows (probably a match to SARPROZ rather than accuracy; not checked). Size of the effect: 6.9° at X band is about
0.3 mm LOS per image, small next to temporal decorrelation and atmosphere.

## Plan

- **K0** — `[stack] resample_kernel = "spline" | "lanczos"` (default `spline`: stacks keep their fingerprint) and
  `resample_radius` (8), one interpolator in `native/common.py` used by the stripmap builder (CSK, Capella, ICEYE);
  unit test on a carrier signal. TOPS / SICD / ionosphere sub-bands keep the spline until K2.
- **K1** — Hanoi CSK (golden case `csk_hanoi_pipeline`, scenes in `archive/cosmo_skymed/_incoming`): the pipeline with
  spline, Lanczos 4 and Lanczos 8; compare the interferometric coherence of the stack, PS count and temporal
  coherence, velocity noise, the match to the golden reference, and the time of the stack build.
  **Gate: owner review.**
- **K2** — if K1 shows a gain: the same kernel in `tops.resample_secondary` (and the ionosphere sub-bands), checked on
  an S1 stack (ql6_km124_141 or hcm_d18 rebuilt).
- **K3** — default per sensor (preset), golden references regenerated, docs (`projects-and-data.md`, params
  catalogue).

## Results

**K0 (2026-11-11, uncommitted).** `[stack] resample_kernel` / `resample_radius`, `native.common.interpolate`
(spline | lanczos, separable, chunked), used by `stripmap.resample`; the stack fingerprint takes the kernel only
when it is not `spline` (CSK / Capella / ICEYE). Tests `tests/unit/processing/test_resample_kernel.py` (2D band-limited
signal: Lanczos 8 < Lanczos 4 < spline; integer positions = samples; 0 outside). Unit suite 463 passed.

**K1 (2026-11-11).** Golden case `csk_hanoi_pipeline` (18 CSK HIMAGE scenes, AOI 2.6 × 2.6 km, phase linking +
Gaussian post-filter, ps engine), scratch `k1_csk.py`, outputs in `geoeyes_workspace/tmp/k1/`:

| | spline | Lanczos 4 | Lanczos 8 |
|---|---|---|---|
| time to build_product | 664 s | 1383 s | 1519 s |
| points (PS / DS) | 253,112 (230,713 / 22,399) | 253,124 (230,947 / 22,177) | 251,953 (229,711 / 22,242) |
| temporal coherence, median | 0.5507 | 0.5516 | 0.5522 |
| stack coherence 5 × 5, median | 0.3051 | 0.3031 | 0.3018 |
| velocity difference of PS < 30 m apart, NMAD | 0.382 mm/yr | 0.383 | 0.385 |

Same pixels, against the spline (PS / DS): temporal coherence +0.0006 / +0.0005 (Lanczos 4) and +0.0007 / +0.0007
(Lanczos 8), better at 51 % of the points; fit RMSE **+0.14 / +0.13 mm** and **+0.10 / +0.06 mm** (lower at only
37–45 %). The boxcar stack coherence is lower with Lanczos, as expected from an estimator that the spline's slight
low-pass biases upward (correlated neighbours), so it is not a fair measure here.

Reading: **no measurable gain on real CSK data.** The simulated gain (2e-3 of coherence, ~0.3 mm per image) is two
orders below the decorrelation of this stack (coherence ~0.3) and does not show; the fit RMSE is even slightly worse.
The cost is 2–2.3 × the run time. The velocities of the same PS differ between kernels by 0.7–0.9 mm/yr (NMAD),
far more than the interpolation error can explain (~0.1 mm/yr): the chain (unwrapping, DS selection, reference)
amplifies small input changes — a sensitivity worth a separate look.

Side finding: the spline run itself no longer matches the golden reference of 2026-11-07 (velocity RMSE 0.297 >
0.2 mm/yr; match 0.98, height and coherence within limits): a change of the PS engine since then, not the kernel.

**Cause found (2026-11-13).** Two runs of the same HEAD code are identical (RMSE 0): the chain is deterministic. Commit
`c4d3597` (just before `a9c49dc`) reproduces the golden exactly (RMSE 0), and so does HEAD with the phase-linking
`blas_threads(1)` turned off (RMSE 0, 99.96 % of the points matched). The cause is phase linking's move to one BLAS
thread per worker (`a9c49dc`, against the OpenBLAS crash with concurrent `eigh`): the rounding of EMI / `eigh`
changes at float level (temporal coherence 1.5e-7 apart), and the chain amplifies it to 0.297 mm/yr (bias 0.0003
mm/yr). The golden is regenerated with the current code; the 2026-11-07 reference is kept as
`expected_2026-11-07_blas_multithread`. This is also a measure of the chain sensitivity: a float-rounding
perturbation of the input gives about 0.3 mm/yr RMS in the velocities.

**Decision (owner, 2026-11-11): default `spline`.** The Lanczos option stays (`[stack] resample_kernel =
"lanczos"`, stripmap builder only); K2 and K3 are not done. Open instead: the chain sensitivity (the golden drift is explained, 2026-11-13, above).
