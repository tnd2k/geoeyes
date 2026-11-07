# Groundwater and InSAR on the Choshui River alluvial fan

> Research plan (2026-11-05). Status: **C0 accepted; C1 done, awaiting review**. Each step ends with a review gate; the next
> step starts only after the owner has reviewed the result.
> Companion notes: [groundwater-insar.md](groundwater-insar.md) (coupling with modelled storage, GLDAS/GRACE),
> [two-geometries-and-soft-soil.md](two-geometries-and-soft-soil.md) (ascending + descending decomposition),
> [ramp-selection.md](ramp-selection.md) (removing trends without removing the bowl),
> [gnss-insar-calibration.md](gnss-insar-calibration.md) (GNSS checks).

## Contents

1. [Why this study](#1-why-this-study)
2. [Data received](#2-data-received)
3. [Questions and hypotheses](#3-questions-and-hypotheses)
4. [Principles](#4-principles)
5. [Steps C0–C8](#5-steps-c0c8)
6. [Risks and confounders](#6-risks-and-confounders)
7. [Resources](#7-resources)
8. [What a finding would look like](#8-what-a-finding-would-look-like)
9. [References](#9-references)

## 1. Why this study

The Hanoi and Mekong tests of [groundwater-insar.md](groundwater-insar.md) could not answer whether the motion
follows the heads: there was no measured head, only modelled storage (GLDAS) or rainfall as a proxy, and the lag
window (0–6 months) only probes the elastic response. The Choshui River alluvial fan (濁水溪沖積扇, Changhua and
Yunlin, Taiwan) is the opposite case:

- a dense, long, **multi-depth** monitoring network: 315 wells at 104 stations, most stations with 2–5 wells
  screened in different aquifers, daily heads 2001–2024;
- one of the best documented pumping-induced subsidence areas in the world (rates of several cm/yr in inland
  Yunlin in the 2010s; the high-speed railway crosses the bowl), so the signal is large;
- 11 years of Sentinel-1 in two geometries.

It is therefore the place where the GeoEyes chain can be tested against an *independent physical driver*, not
against another InSAR product, and where the methods of the hazard notes (coupling, decomposition, behaviour,
lines) can be pushed to physical parameters (skeletal storage, lag, which aquifer compacts).

## 2. Data received

Audit of 2026-11-05 (read-only, metadata and summaries).

### 2.1 Groundwater (`20240828_GWL_CRFP_model.h5`, 46 MB)

- HDF5 written 2024-08-28 from the Excel files of the monitoring network ("Transform GWL data from Excel to HDF5").
- Root dataset `date`: daily, 2001-01-01 → 2024-12-31 (8,766 days). Values end on 2024-08-20.
- One group per station (104): `X`, `Y` in TWD97 / TM2 (EPSG:3826), address, basin, number of wells.
  Three stations have no metadata (`GANYUAN`, `XIABANTIAN`, `ZHONGLIAO`), one has wrong coordinates (latitude 0).
- One subgroup per well (315): `Well_Depth(m)`, `Well_Elev(m)`, `Well_Screen(m)` (missing for most wells rebuilt
  after 2011), `FIRST_OBS`, `LAST_OBS`, `Status`; datasets `measure/daily_value` (head, m; values from about −45
  to +10 m, so heads relative to mean sea level — to confirm) and `measure/model` (a modelled or gap-filled head;
  at ANHE(1) it correlates 0.94 with the measured head, RMS difference 0.9 m — **meaning to ask the data owner**).
- Many wells were replaced around 2011–2012: the old ID (`…11`, to 2010-12) and the new one (`…12`, from 2012-01)
  are the same well number at the same station, with a one-year gap and a possibly different depth or datum.
- Depths: < 50 m 58 wells, 50–100 m 68, 100–150 m 74, 150–200 m 35, 200–300 m 68, > 300 m 5. 233 wells have
  ≥ 1,500 valid days in 2015–2024. 99 of the 101 located stations lie inside the InSAR frame.
- The well number at a station (1), (2), (3), (4) grows with depth (ANHE: 40–52, 72–90, 144–156, 260–278 m): it
  probably is the aquifer index of the fan's layered system. To verify in C0.

### 2.2 InSAR (MintPy on HyP3, for comparison only)

| | Ascending | Descending |
|---|---|---|
| Track | 69 | 105 |
| Epochs | 433 (2015-01-14 → 2026-06-09) | 441 (2015-01-16 → 2026-06-11) |
| Grid | 2728 × 2053 at 40 m, UTM 50N (EPSG:32650) | 2817 × 2053 at 40 m |
| File | `timeseries_SET_ERA5_ramp_demErr-001.h5` (9.9 GB) | `…-002.h5` (10.6 GB) |
| Troposphere | `height_correlation` | `pyaps` (ERA5) |
| Reference | `auto` (row 1749, col 1436) | 23.7612 N, 120.6809 E |

Both: solid-earth tide, **linear deramp**, DEM-error correction, `var` weights, unwrapping-error correction by
bridging + phase closure, 2 × 10 looks. `geometryGeo.h5` (incidence, azimuth, height, water mask) and the MintPy
configs are included.

Remarks:
- The two tracks are not processed alike (troposphere, reference), although both file names say "ERA5".
- A linear deramp over a 80 × 110 km frame removes part of a bowl of the same size
  ([ramp-selection.md](ramp-selection.md) §2): the long-wavelength subsidence of this product is not reliable.
- The groundwater series end in 2024-08; the overlap with InSAR is 2015-01 → 2024-08 (9.6 years).

Data location: the originals stay in `Downloads`; working copies go to
`geoeyes_workspace/studies/choshui_gw/data/` in C0.

## 3. Questions and hypotheses

- **Q1. Which aquifers compact?** At a station with wells in aquifers 1–4, the vertical motion is best explained by
  the heads of which aquifer(s), with which lag?
  - *H1*: the deeper confined aquifers (2–3) explain more of the long-term subsidence than aquifer 1, in the distal
    and middle fan; in the proximal fan (unconfined, coarse) the coupling is weak.
- **Q2. Elastic and inelastic storage.** Can the seasonal amplitude ratio (vertical motion / head) give the elastic
  skeletal storage S_ke·b, and the long-term motion when heads are below their previous minimum give the inelastic
  S_kv·b (Hoffmann et al. 2001; Chen et al. 2016; Smith et al. 2017)?
  - *H2*: S_ke·b is of order 10⁻⁴–10⁻³ and S_kv/S_ke ≫ 1 where the aquitards are thick; the share of permanent
    compaction is mapped, not assumed.
- **Q3. Lag.** The delay between head and compaction measures the aquitard drainage time τ ∝ b²/c_v.
  - *H3*: τ grows from the apex to the coast (thicker clays); a τ of months is elastic aquifer response, a τ of
    years is aquitard drainage (seasonal vs delayed; compare [two-geometries-and-soft-soil.md](two-geometries-and-soft-soil.md) §4.3).
- **Q4. Prediction.** Do the heads predict the subsidence at stations and in years left out?
  - *H4*: a head-driven model beats a linear trend on held-out years (2023–2024) and held-out stations.
- **Q2b. The 2021 drought** (added after C0). 140 wells fell below their pre-2015 minimum in 2021.
  - *H5*: where they did, InSAR shows extra subsidence in 2021 that does not recover in 2022; where they did not,
    the 2021 dip recovers. This is a direct test of inelastic compaction.
- **Q5. Horizontal motion.** Is there east–west motion towards the centres of the head depression
  (three-dimensional compaction)?
- **Q6. Our method.** Which GeoEyes processing choices (APS, ramp `auto`, SCN, reference, engine) preserve the
  signal that the heads predict, and which remove or distort it? The heads are the arbiter, not the MintPy product.

## 4. Principles

- **Groundwater is the independent variable.** No InSAR product (ours or MintPy) is the truth; both are judged by
  how well they agree with the heads *and* with each other, and by GNSS where available.
- **Pre-register.** The criteria of each step are written before the step is run (as in the landslide plan).
- **Hold out.** Years 2023-01 → 2024-08 and a spatial block of stations are held out until C6.
- **Same sign everywhere.** GeoEyes sign: sinking negative. Heads in m (up positive).
- **One step at a time**, with the owner's review between steps.

## 5. Steps C0–C8

### C0. Data audit and catalogue (gate: owner review)

- Copy the data to `geoeyes_workspace/studies/choshui_gw/data/` (originals untouched).
- Well catalogue (`wells.parquet`): station, well, lon/lat (EPSG:3826 → 4326 and → 32650), ground and well
  elevation, depth, screen, first/last observation, status, number of valid days in the overlap.
- Join old and new IDs of the same well number (2011–2012 rebuild): check the datum and the depth, flag a step.
- Aquifer index: test "well number = aquifer" against depth and screen; find the hydrogeological layer boundaries
  per station (Central Geological Survey / Water Resources Agency reports, to obtain) — until then, the well
  number is used and the assumption is stated.
- QC per series: spikes, flat runs, datum jumps; monthly and 12-day resampling (median) to the InSAR epochs.
- `model` series: ask the data owner what it is; use only `daily_value` until answered.
- Head summary maps: long-term trend per aquifer 2015–2024, seasonal amplitude and phase, historical minimum
  (pre-consolidation proxy) since 2001.
- **Gate:** catalogue, QC report, head maps; open questions to the data owner (meaning of `model`, datum, aquifer
  boundaries, any multi-layer compaction wells or levelling).

**C0 outcome (2026-11-05, reviewed and accepted the same day: aquifer from screen or depth, number as a fallback;
new IDs only for 2015–2024; H5 added to §3).** Script `code/choshui_c0.py`; outputs and the full report in
`geoeyes_workspace/studies/choshui_gw/c0/` (`c0_audit.md`).
- 233 wells at 94 stations are usable in the overlap (≥ 1,500 valid days, located): well no. 1 92, no. 2 79,
  no. 3 39, no. 4 21. Five stations lack coordinates. 13 wells lack a depth, among them the three TUKU wells at
  the centre of the bowl.
- `model` is a gap-filled head: it fills 2006 and runs past the last observation. Only `daily_value` is used.
- Depth by well number (medians 62, 129, 201, 261 m) shows four levels, and depth grows with the number at 86 %
  of the stations. Proposed: assign the aquifer from the screen or depth, with the number as a fallback.
- The 2011–2012 rebuild: 37 of 62 pairs changed depth by more than 5 m, so old and new IDs are not joined for
  2015–2024. The well-head elevation fell by a median 0.19 m between the surveys (at equal depth), which may be
  measured subsidence of the 2000s (to confirm).
- QC: the abrupt steps are mostly pumping drawdowns (seasonal swings of 10–20 m in Yunlin), so they are kept.
  Spikes and flat runs are removed.
- **Timing:** the lowest head is in April–May, and it comes later with depth. Relative to well no. 1, no. 3 is
  1.1 months later (95 % CI 0.6–1.4) and no. 4 is 1.4 months later (0.6–2.0). This is the depth-dependent phase
  that C4 must find in the motion.
- **The 2021 drought:** 187 of 233 wells have their 2015–2024 low in 2021, a median 2.4 m below the 2015–2020
  lows. 140 wells fall below their pre-2015 minimum, by a median of 2.3 m. This is a natural test of inelastic
  compaction, proposed as H5:
  - *H5:* where 2021 heads fell below the previous minimum, InSAR shows extra subsidence in 2021 that does not
    recover in 2022.
  - Where they did not, the 2021 dip recovers.

### C1. The MintPy product as a foreign product (gate)

- Small reader for MintPy `timeseries` + `geometryGeo` (read windows only: the files are 10 GB each), giving the
  GeoEyes product layout (points or grid, velocity, series, LOS unit vector) so the analysis modules can run on it.
- Velocity and series at the well stations (median within a radius, 200 m to start).
- Not used as truth; it is one of the candidates judged in C4 and C7.
- **Gate:** reader with a unit test, LOS velocity maps of both tracks, a first look at head vs motion at 5
  stations (no statistics yet).

**C1 outcome (2026-11-05, awaiting review).** Reader `geoeyes.products.foreign.import_mintpy` (3 unit tests);
study script `code/choshui_c1.py`; report `studies/choshui_gw/c1/c1_report.md`.
- **Products.** Two products in `projects/choshui_mintpy/products/`, made of 200 m blocks: 88,737 points
  (asc) and 87,110 (desc). Their LOS vector comes from MintPy's angles (l_e −0.56 / +0.56). Both are marked
  foreign and are found by `geoeyes decompose`.
- **The bowl.** One bowl dominates, in inland Yunlin (Tuku–Yuanchang). It reaches −89 mm/yr LOS on asc and −68
  on desc; LUNZI sinks about −69 mm/yr vertical, about 0.7 m in 11 years.
- **Station series.** All 94 well stations have a series on both tracks, from the native pixels within 200 m.
  - The tracks agree in pattern (r = 0.97), but asc − desc = −7.7 mm/yr in vertical projection.
  - That gap is not a reference effect, since the two reference pixels are 250 m apart. It is either westward
    motion of the plain or a processing difference (troposphere: height correlation vs ERA5; linear deramp of
    each track). It goes to C3, with GNSS.
- **The descending gap.** Descending has a **168-day gap** (2022-02-08 → 2022-07-26, after the loss of
  Sentinel-1B). Its series runs flatter than ascending after 2022, so it is not yet usable for H5 or the
  decomposition after 2022-02. C2 must bridge the gap with long pairs, or treat the two segments apart.
- **Uneven sampling.** 6-day sampling in 2018–2021 and 12-day otherwise, so the analyses use the 12-day bins
  of C0.
- **Missing files.** There is no coherence mask in the delivery: ask for `temporalCoherence.h5` and
  `velocity.h5`.

### C2. GeoEyes processing of a core area (gate)

- Area: the inland Yunlin bowl plus a stable reference in the eastern foothills, sized to the disk budget (§7).
  The full frame is not processed.
- Both tracks (asc 69, desc 105), 2015-01 → 2026-06, 12-day sampling at most (24-day if the disk demands it).
- Engine: SBAS (distributed scatterers dominate in farmland) and `ps_lite` on the same stack, to compare.
- Ramp: `scla_deramp = "auto"` **with a stable area** (`deramp_non_defo` over the foothills) — under the rule of
  2026-11-05 a planar trend is not removed without it. A run without deramp is kept for C7.
- Reference: the stable area; GNSS check with `geoeyes gnss` on the NGL stations of the area.
- **Gate:** products of both tracks, GNSS comparison (raw series), coverage at the wells, disk used.

**C2 design (2026-11-05, before any download).**
- **Engines.** `ps_lite` is the Capella workflow, so for Sentinel-1 the two engines are **SBAS** (`method =
  "sbas"`) and **PSI** (`method = "psi"`), both on the same stack.
- **Area.** AOI `[120.31, 23.58, 120.65, 23.78]`: 60 usable wells at 28 stations, among them LUNZI, TUKU and
  the Douliu tableland in the east as the stable area. The bursts were searched on ASF:
  - asc 69: IW1 bursts 146196 and 146197, i.e. 2 bursts per date, 440 dates on ASF;
  - desc 105: IW2 bursts 224319–224321, i.e. 3 bursts per date with `subswaths = ["IW2"]`, 453 dates on ASF.
    The full-resolution IW3 corner in the north-west is left out.
- **Sampling.** `max_per_month = 1`, which gives about 138 dates (asc) and 132 dates (desc) for 2015-01 →
  2026-06. That is one date a month, enough for the April–May head minimum and the 2021 drought.
- **Disk.** About 0.148 GB per burst file (VV only), measured on the archive; the first estimate of 0.12 GB was
  low.
  - Raw bursts: asc about 41 GB (276 bursts), desc about 59 GB (396 bursts). The stacks are cropped to the AOI, about 4–6 GB each.
  - The two tracks run **one after the other**. Once a track's stack is built and checked, its raw bursts (the
    ones downloaded for this study) are deleted. Peak use is about 65–70 GB (the descending track), against 81 GB
    free.
- **Started 2026-11-05:** asc 69 acquisition and stack (`geoeyes run choshui_s1 --track sentinel1-asc-069 --to
  build_stack`).

**C2 progress (2026-11-06): ascending done; descending processed, its bowl is too shallow (open).**
- **Data.**
  - Raw: 276 bursts, 34 GB. Stack: 127 dates (2015-12 → 2026-06), 22 GB.
  - The 11 dates of 2015 are skipped: their scenes lack one of the two bursts.
  - Fix: early-2015 IPF annotations write the FM rate as `c0, c1, c2`. The reader now accepts that form
    (`sensors/sentinel1/burst.py`, test added).
- **SBAS, three runs** on the same stack:

  | Run | Settings | Points | Stations ≤ 300 m | vs MintPy at stations |
  |---|---|---|---|---|
  | v1 | 2 × 8 looks, coherence 0.7 / 0.3 | 33,984 | 9 / 28 | r = 0.81, slope 0.42 |
  | v2 | 4 × 16 looks, 0.5 / 0.2 | 62,452 | 26 / 28 | r = 0.93, slope 0.61 |
  | v3 | as v2, no per-pair phase–height fit | 61,999 | 26 / 28 | r = 0.96, slope 0.75 |

  - With one date a month the shortest pairs are 24–60 days. Paddy fields lose coherence over that time, so
    2 × 8 looks keep almost no farmland.
  - The per-pair stratified-troposphere fit removes part of the bowl, which lies lower than the reference
    tableland. This is a first C7 finding about a GeoEyes default.
- **GNSS** (NGL, vertical, 3 stations in the AOI: DNAN, GUKN, S103).
  - v3 is offset by −5.8 mm/yr: the Douliu reference itself sinks. After the offset the RMS is 1.9 mm/yr. At DNAN:
    GNSS −11.9, GeoEyes −14.4, MintPy −22.3 mm/yr.
  - The MintPy ascending product against 31 NGL stations: median +3.3, RMS about 21 mm/yr after the offset (HUWE +31).
  - So the 0.75 slope against MintPy is mostly MintPy's overestimate on ascending, consistent with the
    −7.7 mm/yr asc − desc gap of C1.
  - Only 3 stations: this is an indication, not yet a validation.
- **v3 is the working ascending product**: `choshui_s1_sentinel1-asc-069_20151204_20260609_v3`, GNSS offset −5.8 mm/yr.
- **Descending data.** Raw 579 files, about 56 GB (deleted after stacking). Stack 131 dates (2015-01 → 2026-06),
  about 27 GB. Two engine faults were found and fixed on the way:
  - On 53 dates the three AOI bursts lie in two consecutive slices of the same datatake. The stack builder kept one
    folder per date and dropped those dates as incomplete. It now also reads the other slices of the datatake
    (`processing/stack/native/s1_stack.py: datatake_slices`, `aoi_burst_ids`; test added). Only 2017-11-01 is
    really incomplete (ASF serves two of the three bursts).
  - Three dates lie off the orbital tube: 2015-04-22 (B⊥ −248 m), 2024-04-10 (−435 m), 2025-05-05 (−397 m).
    Within 150 m they reach the other dates only through 786–1260-day pairs, which are incoherent, so every pixel
    lost those dates and the first two runs kept 0 points. SBAS now leaves out the dates of a network subset
    that pairs of at most one year cannot reach, if it is small (fewer than max(3, 10 %) of the dates)
    (`processing/sbas/runner.py: baseline_outliers`; tests added). The ascending network is unchanged by it.
- **Descending coherence is low.** Median pair coherence 0.13–0.23 at 4 × 16 looks, also on the reference
  tableland; a plausible cause is dew at the 05:50 local pass (ascending: about 18:00). In 223 of 378 pairs the
  3 × 3 reference had fewer than 3 valid pixels and the whole pair became NaN. SBAS now falls back to an
  11 × 11 window (about 600 m) around the same point; all 378 pairs are referenced.
- **SBAS descending v1** (v3 settings of the ascending run, 128 dates, 378 pairs, longest 396 days):
  76,077 points, temporal coherence p50 0.77 / p90 0.91; the share of pairs with a value is low (p50 0.19,
  p90 0.84), so the points are the coherent fifth of the area.
  - At the stations against MintPy desc: 25 / 28, r = 0.905, slope 0.50.
  - **The bowl is too shallow on descending.** Vertical-equivalent rates (LOS / cos θ) at the stations, GeoEyes
    desc against GeoEyes asc v3: slope 0.61 (r = 0.94). MintPy desc against MintPy asc: 0.88. In the bowl
    centre GeoEyes desc gives about −24 mm/yr where asc gives about −35 (XIUTAN −19 vs −36).
  - GNSS: ERLN (in the bowl, −32.9 mm/yr vertical) gets +1.3 on desc; DNAN −6.3 against −10.5; JSAN +6.2
    against +0.7. The offset calibration (−14.6 mm/yr) is driven by ERLN and is not used.
  - Leading hypothesis: in the bowl the low coherence leaves few pairs per pixel and the closure mask
    (9.6 million values masked) keeps mostly the short pairs; unwrapping errors or a bias toward the coherent
    (less subsiding) pixels of each block then flatten the rate. To test next, cheapest first: the per-pixel
    pair count and closure share inside the bowl; a run at 8 × 32 looks; `min_pair_coherence` 0.15.
  - **The descending product is not usable for C3 yet.**
  - **Diagnosis (same day).**
    - Rank of the pixel networks: rejected. Each point now records `n_pairs` and `rank_deficit` (intervals its own
      valid pairs leave untied; the minimum-norm solution pulls them toward 0). 63 % of the points have a deficit,
      but in the bowl full-rank points are as shallow as the others (HONGLUN −22.3 vs −19.1, TUKU −20.6 vs −21.0).
    - Short-pair phase bias ("fading signal"): partly confirmed. By period the desc / asc ratio is 0.53 in
      2018–2020 (S1B, 12-day pairs) and 0.88 in 2021–2022 (no S1B; 0.91 expected for vertical motion). With
      `[network.sbas] min_temporal_days = 48` (new option; 375 pairs, median 96 days; desc v3, 52,111 points,
      temporal coherence p50 0.62) the desc / asc vertical slope rises from 0.61 to 0.70 (r = 0.96) and XIUTAN
      from −19 to −31 mm/yr.
    - Still 0.70, not about 1: the bias explains part of the gap. The ascending run keeps its 24-day pairs and may
      carry the same bias with the other sign of error; the next test is asc with the same 48-day minimum, then
      the desc / asc ratio of the two unbiased runs.
    - **Asc v4 (same 48-day minimum, 2026-11-06).** 368 pairs, 38,241 points (v3: 61,999); stations with ≥ 3
      points within 300 m: 29 (v3: 37; XIUTAN lost). Rates at the stations barely move: asc v4 / asc v3 slope
      through 0 = 1.02 (r = 0.98; HONGLUN −35.2 → −34.7, TUKU −39.4 → −39.3 mm/yr). **The ascending track carries
      no short-pair bias in its rate**; dropping the 24-day pairs only costs points.
    - Desc v3 / asc v4, vertical-equivalent at 22 stations: OLS slope 0.83, through 0 0.80, r = 0.95 (desc v3 /
      asc v3 by the same method: 0.76 / 0.85). By period, through 0: 0.75 (2016–17), 0.73 (2018–20), 0.92
      (2021–22), 0.84 (2023–26). Station medians of points within 300 m (script differs from the 0.70 above).
    - So about 0.8 remains, and it is still lowest in the S1B years. Two readings remain: a residual desc bias
      (12-day revisit still enters through the 48–96-day pairs of the low-coherence dawn pass), or real horizontal
      motion toward the bowl, which raises one track's vertical-equivalent and lowers the other's. C3's
      asc + desc decomposition separates them: a bias leaves an east–west field without the bowl's radial pattern.
    - Station rates of all four runs: `studies/choshui_gw/c2_station_rates_v4.csv`.
    - ERLN (GNSS −32.9 mm/yr) stays far from every InSAR product (GeoEyes desc v3 about +3, MintPy asc −18.8):
      a local monument effect is likely; it is not used as an arbiter until checked.
- **The 2022 gap** (168 days) is bridged by ordinary pairs up to 396 days; closure dropped no pair.
- **Reference and ramp.**
  - SBAS: `reference` on the Douliu tableland, checked against the head-flat stations.
  - PSI: `scla_deramp = "auto"` with `deramp_non_defo` over the same area.

### C3. Vertical and east–west (gate)

- `geoeyes decompose` for each product pair (ours, MintPy), on a common grid and common dates (12-day bins).
- North–south is not resolved; its leakage is bounded with the GNSS horizontals.
- **Gate:** vertical and east–west maps and series at the wells; their uncertainty.

### C4. Coupling at the well stations (gate)

Pre-registered before running. At each station with a vertical series and heads:
1. **Seasonal (elastic) part:** band-pass (0.5–2 cycles/yr) both series; amplitude ratio and phase lag per aquifer;
   S_ke·b = Δb / Δh with its bootstrap interval. Criterion: the phase lag is consistent between the two tracks and
   with the head phase (otherwise the seasonal motion is tropospheric, §6).
2. **Long-term (inelastic) part:** compaction rate against the time below the historical minimum head;
   S_kv·b where heads reach new minima.
3. **Which aquifer:** regression of the vertical displacement on the heads of aquifers 1–4 (lagged, non-negative
   coefficients), compared by cross-validated skill over years; report the share of variance per aquifer.
4. **Controls:** stations whose heads barely move (they must show little motion), and points between stations.
- Statistics: years blocked (no random split), intervals from a block bootstrap, the number of stations behind
  every number.
- **Gate:** table per station and aquifer; maps of S_ke·b, S_kv·b, lag; H1–H3 answered or not.

### C5. Spatial patterns (gate)

- Interpolate the C4 parameters (with their uncertainty) over the fan; compare with apex → coast position and with
  clay thickness where borehole logs can be obtained.
- Infrastructure: `geoeyes lines` along the high-speed railway and the main dykes, with the new distortion
  criterion (change of slope, [lines-and-consolidation.md](lines-and-consolidation.md)).
- East–west motion against the head depression centres (Q5).
- **Gate:** maps, and the list of patterns that hold in both products and both tracks.

### C6. Prediction and scenarios (gate)

- Head-driven model of vertical motion per station: elastic + inelastic (hysteresis with the historical minimum),
  optionally a 1-D aquitard diffusion with τ from C4.
- Verification: held-out years 2023–2024 and held-out stations (spatial blocks), against a linear-trend baseline.
- Scenarios: heads held at their 2024 level, recovering by 1 m/yr, falling at the 2015–2024 rate.
- **Gate:** skill table with intervals (H4), scenario maps with uncertainty.

### C7. What our processing does to the signal (gate)

- For each variant (MintPy as delivered; GeoEyes with and without APS, with ramp `auto` and with a full linear
  deramp, SBAS vs `ps_lite`, raw vs SCN series), the agreement with the head-predicted motion of C6 at the
  stations: seasonal phase and amplitude, long-term rate, east–west.
- Expected: a full linear deramp shrinks the bowl; SCN over short windows removes seasonal motion
  ([gnss-insar-calibration.md](gnss-insar-calibration.md) G3.1e); a height-correlated troposphere correction may
  remove part of a bowl that correlates with topography.
- **Gate:** the ranking of variants by agreement with the heads; defaults to revise in GeoEyes, if any.

### C8. Write-up

- Results note (EN/VI) and, if the findings hold, the outline of a paper (see
  [paper-ideas.md](../../vi/research/paper-ideas.md)).

## 6. Risks and confounders

- **Seasonal troposphere vs seasonal heads.** Taiwan's wet season (May–September) drives a seasonal tropospheric
  delay that can mimic or cancel an elastic seasonal motion. Checks: phase consistency between ascending and
  descending (the troposphere differs between 06 and 18 local time passes), stations with flat heads as controls,
  amplitude vs topography.
- **Datum and rebuild of wells (2011–2012):** steps in the heads would appear as false inelastic events.
- **Aquifer assignment:** missing screens after the rebuild; layer boundaries vary over the fan.
- **Point sampling:** wells are points, InSAR is a 40 m (or coarser) average; a radius test (100–500 m) is part
  of C4.
- **Missing compaction data:** without multi-layer compaction wells, "which aquifer compacts" is inferred from
  heads, not measured.
- **Disk:** 81 GB free on D: (2026-11-05); the SLC stack of the full frame does not fit (§7).
- **Data licence:** the data were shared for research; ask before publishing station-level figures.

## 7. Resources

- Disk: about 0.14 GB per burst and date (measured on the Quang Nam stack). A core area of 3 bursts per track at
  12-day sampling (about 270 dates to 2026-06) needs about 110 GB of raw bursts per track: too much. Options in C2:
  2 bursts per track at 24-day sampling (about 135 dates, about 75 GB for both tracks, still close to the free
  space), stacking one period at a time and deleting the raw bursts once stacked, or freeing space on D:. To decide
  at the C2 gate.
- Compute: the existing SBAS and `ps_lite` engines; nothing new except the MintPy reader (C1) and the coupling
  analysis (C4), which reuses `hazard.coupling`.
- From the data owner: meaning of `model`, head datum, aquifer boundaries per station, any compaction-well or
  levelling data, permission to publish.

## 8. What a finding would look like

- "In the middle fan the long-term subsidence follows aquifer 2–3 heads with a lag of N months; S_kv/S_ke ≈ K;
  X % of the 2015–2024 compaction is permanent" — with intervals and the number of stations.
- "Heads alone predict the 2023–2024 subsidence at held-out stations within Y mm/yr, better than the trend."
- "A full linear deramp removes Z % of the bowl; ramp `auto` with a stable area keeps it" — a statement about our
  method, judged by the heads.

## 9. References

Details to check on Crossref before use in a paper.

- Chen, J., Knight, R., Zebker, H. A., & Schreüder, W. A. (2016). Confined aquifer head measurements and storage
  properties in the San Luis Valley, Colorado, from spaceborne InSAR observations. *Water Resources Research*, 52.
- Galloway, D. L., & Burbey, T. J. (2011). Review: Regional land subsidence accompanying groundwater extraction.
  *Hydrogeology Journal*, 19, 1459–1486.
- Hoffmann, J., Zebker, H. A., Galloway, D. L., & Amelung, F. (2001). Seasonal subsidence and rebound in Las Vegas
  Valley, Nevada, observed by synthetic aperture radar interferometry. *Water Resources Research*, 37, 1551–1566.
- Hung, W.-C., Hwang, C., Chang, C.-P., Yen, J.-Y., Liu, C.-H., & Yang, W.-H. (2010). Monitoring severe aquifer-system
  compaction and land subsidence in Taiwan using multiple sensors: Yunlin, the southern Choushui River Alluvial
  Fan. *Environmental Earth Sciences*, 59, 1535–1548.
- Smith, R. G., Knight, R., Chen, J., Reeves, J. A., Zebker, H. A., Farr, T., & Liu, Z. (2017). Estimating the
  permanent loss of groundwater storage in the southern San Joaquin Valley, California. *Water Resources Research*,
  53, 2133–2148.
