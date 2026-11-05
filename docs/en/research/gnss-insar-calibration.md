# GNSS (Nevada Geodetic Laboratory) to validate and calibrate InSAR time series

> Research note and method of `geoeyes gnss` (package `geoeyes.validation.gnss`, web app: Processing →
> Validation → GNSS, and "GNSS tie" on the Thematic analysis page).
> Status: **v1 implemented 2026-10-25**, results on the GeoEyes test projects in §6.
> Related: [rainfall-insar-hazard.md](rainfall-insar-hazard.md) (the hazard intensities need a stable reference);
> decision record ADR-025.

## Contents

1. [Question](#1-question)
2. [Background](#2-background)
3. [Data: NGL](#3-data-ngl)
4. [Method (v1, implemented)](#4-method-v1-implemented)
5. [Parameters](#5-parameters)
6. [Results on the GeoEyes projects](#6-results-on-the-geoeyes-projects)
7. [Answer: can GNSS calibrate the InSAR series?](#7-answer-can-gnss-calibrate-the-insar-series)
8. [Limitations](#8-limitations)
9. [Research sequence](#9-research-sequence)
10. [Implementation](#10-implementation)
11. [References](#11-references)

---

## 1. Question

1. **Validation.** Do the InSAR series agree with independent GNSS positions: in rate, and in shape?
2. **Calibration.** Can GNSS correct the InSAR series? In particular:
   - the **reference** (InSAR is relative to a point or to the scene mean);
   - long-wavelength **ramps**;
   - **common-mode** errors per date.
3. **Use.** Is the result good enough to put the hazard intensities on stable ground (rainfall–InSAR hazard
   note, §4.3)?

## 2. Background

- **InSAR is relative.** InSAR measures one component of motion (the line of sight, LOS) relative to a reference
  point or area, and to a reference date.
  - Orbital errors leave long-wavelength ramps that grow with distance (Fattahi & Amelung 2014).
  - The reference itself may move. GeoEyes products referenced to the *scene mean* have a rate offset equal to
    minus the mean motion of the scene.
- **GNSS** gives 3-D positions in a global frame (here IGS20 / ITRF2020), daily, at one point. Its daily noise is
  white plus flicker noise, so white-noise velocity sigmas are too small (Mao et al. 1999; Williams et al. 2004).
  Annual signals bias velocities estimated over short spans (Blewitt & Lavallée 2002).
- **Projection.** ENU motion is projected onto the LOS with the unit vector from the ground to the satellite
  (Wright et al. 2004).
- **Combinations.** Published GNSS–InSAR combinations range from a simple reference tie to full integration:
  - "GPS Imaging" interpolates GNSS vertical rates into maps, GNSS only (Hammond et al. 2016; global: Hammond et
    al. 2021). Hammond et al. (2018) combine it with InSAR: GNSS gives the frame, InSAR the detail.
  - Tong et al. (2013) Remove / Filter / Restore the long wavelengths with GPS; after integration, InSAR matches
    GPS within 1.5 mm/yr (mean absolute deviation).
  - Neely et al. (2020) correct each epoch with cGPS (GInSAR). Xu et al. (2021) use GNSS for the long wavelengths
    and InSAR for the short ones.
  - Shen & Liu (2020) estimate the InSAR ramps and offsets jointly.
  - Weiss et al. (2020) tie Sentinel-1 velocities over Anatolia to GNSS.
  - For PSI and subsidence: Farolfi et al. (2019); review of European studies by Del Soldato et al. (2021).
- **The monument problem.** A GNSS antenna and the persistent scatterers near it are not the same object. The
  antenna may sit on a roof, the PS on other buildings or on the ground (Dheenathayalan et al. 2016, 2018).
  - Corner reflectors or transponders next to the GNSS antenna solve this (Parker et al. 2017; Mahapatra et al.
    2018).
  - Without them, the comparison uses the median of the PS within a radius, and its spread is reported.
- **Mexico City.**
  - It subsides at up to about 40 cm/yr: Cabral-Cano et al. (2008); Chaussard et al. (2014); Cigna & Tapete
    (2021); Solano-Rojas et al. (2020).
  - It has a dense cGNSS network (TLALOCNet, Cabral-Cano et al. 2018). This makes it the natural test case.
- **Hanoi.** Dang et al. (2014) mapped its subsidence with ALOS.

## 3. Data: NGL

The Nevada Geodetic Laboratory (University of Nevada, Reno) processes GNSS stations worldwide with GipsyX. Since
August 2025 its solutions are in **IGS20**; the IGS14 products are frozen. NGL asks users to cite:

- Blewitt, Hammond & Kreemer (2018);
- the data DOI of each station (on its station page);
- Blewitt et al. (2016) when the MIDAS velocities are used.

| Data | URL (https only; plain http redirects to a broken host) |
|---|---|
| Station list | `https://geodesy.unr.edu/NGLStationPages/DataHoldings.txt` (station, lat, lon 0–360°, height, XYZ, first / last day, solutions) |
| Equipment and earthquake steps | `https://geodesy.unr.edu/NGLStationPages/steps.txt` |
| Daily positions | `https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/<SITE>.tenv3` |
| MIDAS velocities | `https://geodesy.unr.edu/gps_timeseries/IGS20/midas/midas.IGS.txt` (columns 9–11: E, N, U velocity in m/yr; 12–14: their sigmas) |

**tenv3** has 23 columns, documented in `gps_timeseries/readmes/README_tenv3.txt`: site, date, decimal year, MJD,
GPS week and day, the reference meridian, then the east, north and up coordinates.

- Each coordinate is an integer part plus a fractional part (m) in a local frame; the integer part is reset only
  for jumps of more than 10 m.
- Then come the antenna height, the sigmas, the correlations, and the nominal latitude, longitude and height.
  Longitudes below −180 are wrapped (−254.16 = 105.84° E).

**Stations over the test projects** (from `DataHoldings.txt`, 2026-10-25):

| Area | Station | Data | Overlaps |
|---|---|---|---|
| Hanoi | **HUMG** (21.072 N, 105.774 E) | 2024-01 → 2026-09 | Hanoi S1 2025-10 → 2026-10 |
| Hanoi | **JNAV** (21.005 N, 105.844 E) | 2014-01 → 2026-09, with gaps; moved in Oct 2025 | Hanoi S1; Hanoi CSK only in 2014 (2 epochs) |
| Hanoi | HNOI, HN_0, SIVN, VN3P, TEC0 | ended 2016–2021 | none |
| Mexico City | **MMX1** (19.432 N, 99.068 W) | 2008-04 → 2026-10 | Mexico S1 2024-05 → 2024-10 |
| Mexico City | ICMX, MXTX | to 2026-01 / 2025-02 | outside the S1 product's extent |
| Mexico City | about 15 others (UNIP, TNGF, UTUL, MXTM, …) | ended before 2024 | none |

## 4. Method (v1, implemented)

### 4.1 Stations and cleaning

Stations are those of `DataHoldings.txt` inside the product's extent, with data over its period. Each station's
daily positions over the period (±30 days) are cleaned:

1. **Outliers.** Days beyond 5 robust sigmas (MAD) from a 15-day running median are dropped, per component.
2. **Segments.** The series is split at:
   - NGL equipment changes (`steps.txt`, type 1);
   - day-to-day jumps above max(15 mm horizontal / 30 mm vertical, 5 σ).
   Segments shorter than 30 days are dropped.
3. **Re-joining.** Segments are re-joined with one common linear trend and one offset per segment.
   - This keeps the rate of a station that moved under the same name. JNAV moved by about 250 m and 11 m in
     height in October 2025, with jumps on 2025-10-12 and 2025-10-27.
   - It assumes both monuments move alike: the result says so.

### 4.2 Matching InSAR and GNSS

- **InSAR.** The median series of the points within `radius_m` (100 m) of the antenna, with at least
  `min_points` (5) points. Their spread is kept.
- **GNSS.** The cleaned positions are averaged over ±`window_days` (3) around each InSAR date.
- **Projection.** The GNSS is projected on the median LOS unit vector **l** (ground → satellite) of those points,
  in two ways:
  - **full:** d = e·l_e + n·l_n + u·l_u, the complete motion in IGS20. It includes the motion of the tectonic
    plate, about 31 mm/yr east in Hanoi (Sunda plate), which a relative InSAR product does not contain.
  - **vertical** (default): d = u·l_u. Within a scene, the horizontal motion is taken as the plate's, which is
    uniform and therefore part of the InSAR reference. What is compared and tied is the local vertical motion.
    This is the relevant quantity for subsidence.
  - *Caveat (2026-11-05):* this assumption fails in Mexico City. MMX1 moved +14.4 E / −3.3 N mm/yr over the S1
    period against −6.6 / +5.0 (MIDAS), a ~21 mm/yr east anomaly, ≈ −14 mm/yr in the LOS (l_e −0.69): more than the
    10 mm/yr target. Uniform plate motion is also not constant in the LOS, since **l** changes across the swath. See
    §8.3.
- **Common zero.** Both series are put on a common zero (their mean over the shared dates).

**Statistics** (shared dates only):

- InSAR and GNSS rates (OLS) and their difference, v_GNSS − v_InSAR;
- RMSE of the difference;
- RMSE once the linear trend of the difference is removed (agreement in shape);
- correlation;
- the MIDAS rate (whole record, robust) projected the same way, and its difference to InSAR.

### 4.3 Calibration and its check

The correction added to the InSAR LOS series is one of three kinds:

- **offset:** Δv = mean over the stations of (v_GNSS − v_InSAR), added to every point as Δv·t. This corrects the
  reference rate.
- **plane:** Δv = a + b·x + c·y fitted to the stations (at least 3). This corrects a ramp as well.
- **epoch:** c(t) = median over the stations of the series difference. This is a common-mode correction per date,
  as in GInSAR (Neely et al. 2020). It carries the daily GNSS noise into every point.

The GNSS rate (`gnss_rate`) comes from one of two sources:

- `window`: the rate over the InSAR period. It follows changes, such as accelerating subsidence.
- `midas`: NGL's long-term robust rate. It is less biased by seasons over short periods, but wrong where the
  motion changed.

**Leave-one-out check.** With two stations or more, each station is predicted by the calibration made without it.
The RMS of GNSS − InSAR at the left-out stations, before and after, is the honest measure of what the calibration
gives *where there is no station*. With one station the tie cannot be checked, and the result says so.

**Hazard.** `[postprocess.hazard] gnss_tie = true` adds the calibration to the cell series before they are
projected and classed. The reference of the hazard run then becomes "GNSS (stations)".

## 5. Parameters

`[validation.gnss]` of `project.toml`, or `geoeyes gnss --set key=value`, or the web form.

| Key | Default | Why |
|---|---|---|
| `radius_m` | 100 | A few PS around the antenna at Sentinel-1 / CSK density; small enough to stay on the same block |
| `min_points` | 5 | A robust median |
| `window_days` | 3 | GNSS days averaged around a SAR date; a week reduces the daily noise without smoothing seasons |
| `min_epochs` | 6 | Minimum shared dates for a rate |
| `los_mode` | vertical | §4.2: plate motion is uniform and cancels with the InSAR reference |
| `calibration` | offset | Robust with 1–2 stations; `plane` needs at least 3 |
| `gnss_rate` | window | Follows the motion of the InSAR period (Mexico City accelerates) |
| `stations`, `exclude` | all, none | Choose or reject stations, e.g. a moved antenna or a roof monument |

## 6. Results on the GeoEyes projects

All runs: 2026-10-25, default parameters, vertical projection.

### 6.1 Mexico City: Sentinel-1 asc 078, 2024-05 → 2024-10, station MMX1

| | Value |
|---|---|
| Points within 100 m · shared dates | 66 (median distance 64 m) · 14 |
| GNSS over the period (E / N / U) | +14.4 / −3.3 / **−364.3 mm/yr** |
| MIDAS 2008–2026 (E / N / U) | −6.6 / +5.0 / −265.0 mm/yr |
| InSAR rate (LOS) | −128.1 ± 10.8 mm/yr |
| GNSS vertical in the LOS | −258.2 ± 3.2 mm/yr |
| **GNSS − InSAR** | **−130.1 mm/yr** |
| RMSE · RMSE with the trend removed · correlation | 18.0 mm · **5.3 mm** · **0.96** |

**Reading.**

- **Shape.** The two series agree closely once the rate difference is removed: 5 mm residual, correlation 0.96.
  The InSAR follows the GNSS motion over the six months.
- **Rate.** The rate is off by −130 mm/yr in the LOS. The product is referenced to the scene mean, and most of
  the scene subsides, so the reference itself sinks. This is exactly the bias predicted in the rainfall–InSAR note
  (§7 there).
- **Long-term rate.** MIDAS gives −265 mm/yr over 18 years, but the station subsided at −364 mm/yr in 2024. A
  long-term rate would be wrong here, which is why `window` is the default.

**Hazard, with and without the GNSS tie (100 m cells).**

| | Product reference (scene mean) | GNSS tie (MMX1, offset) |
|---|---|---|
| Cells moving *up* (flagged, not rated) | 19 087 | 531 |
| Median sinking rate · P90 · P99 | n/a (relative) | **159 · 319 · 378 mm/yr** |
| Subsidence: high / very high | 113.9 / 10.7 km² | 394.7 / 28.5 km² |
| Subsidence: very low | 289.1 km² | 9.6 km² |

With the tie, the rates fall in the range published for Mexico City (up to about 40 cm/yr; Cigna & Tapete 2021;
Chaussard et al. 2014). The angular distortion does not depend on the reference, so it is unchanged.

The tie rests on one station and is not independently checked. ICMX and MXTX also recorded in 2024, but lie
outside this product's extent: a product covering them would allow a leave-one-out check.

*Superseded (2026-11-05):* that check (G3.1, §9.1) gives per-station offsets of −79 / −145 / −23 mm/yr and a
leave-one-out error of −94 mm/yr at MMX1. The single-station tie, and the hazard areas above, are not reliable.

### 6.2 Hanoi: Sentinel-1 desc 091, 2025-10 → 2026-10, stations HUMG and JNAV

| Station | Points · dates | InSAR (LOS) | GNSS vertical (LOS), period | GNSS − InSAR | RMSE detrended · corr | MIDAS vertical (LOS) |
|---|---|---|---|---|---|---|
| HUMG | 145 · 16 | +3.1 ± 2.0 | +9.1 ± 6.2 | +6.0 | 6.6 mm · 0.27 | −1.7 (2.7 yr) |
| JNAV (2 segments) | 159 · 21 | −3.3 ± 1.9 | +12.5 ± 4.6 | +15.8 | 7.0 mm · −0.33 | +0.1 (12.7 yr, two monuments) |

| Calibration | Offset | Leave-one-out RMS before → after |
|---|---|---|
| offset, GNSS rate over the period | +11.0 mm/yr | 12.0 → 9.8 mm/yr |
| offset, MIDAS rate | −0.7 mm/yr | 4.1 → **8.1** mm/yr (worse) |

**Reading.**

- The motion near both stations is small (a few mm/yr). One year of GNSS vertical is too noisy and too seasonal
  to compare at that level:
  - the rate sigmas of 5–6 mm/yr assume white noise, so they are optimistic;
  - the monsoon gives large annual vertical signals, from hydrological loading among other causes;
  - a one-year rate depends on the phase of that signal (Blewitt & Lavallée 2002).
- The correlations are low (0.27 and −0.33): there is no common signal to match. Both residuals are 6–7 mm.
- Measured against the long-term MIDAS rates, the uncalibrated InSAR already agrees within about 4 mm/yr (RMS).
  Tying it to one station and predicting the other doubles the error.
- **In Hanoi today, GNSS does not improve the InSAR, and the product should not be tied.** It needs either:
  - two or more years of GNSS and InSAR, so that the rate can be fitted with annual terms; or
  - more stations.

**Hanoi CSK (2011–2014).** No comparison is possible: JNAV only starts in 2014 and shares 2 dates with the stack.

## 7. Answer: can GNSS calibrate the InSAR series?

Yes, for the reference and its rate, under three conditions:

1. **The InSAR reference error is larger than the GNSS rate uncertainty.**
   - Mexico City: a 130 mm/yr reference bias against a GNSS rate known to a few mm/yr. The tie is decisive, and
     the shape agreement (5 mm, r = 0.96) shows that what remains is mostly a reference offset.
     *Superseded (2026-11-05):* with 3 stations (G3.1, §9.1) the offset is not constant (−79 / −145 / −23 mm/yr;
     leave-one-out error −94 mm/yr at MMX1), so the MMX1 tie is not decisive. The §6.1 hazard areas and the
     Calibrated layer (§7.3) rest on it.
   - Hanoi over one year: the bias is a few mm/yr and the GNSS uncertainty 5–6 mm/yr. The tie adds noise.
2. **The GNSS is projected consistently with what InSAR measures.**
   - The vertical projection removes the plate motion that the relative InSAR does not see. In Hanoi, the full
     3-D projection adds 16–19 mm/yr of Sunda-plate motion to the LOS (GNSS − InSAR: +24.9 instead of +6.0 at
     HUMG, +32.1 instead of +15.8 at JNAV).
   - A station that moved needs its segments handled.
3. **The calibration is checked where there is no station.** Leave-one-out needs at least two stations, and a
   ramp at least three. With one station the tie is plausible but unverified.

**Per-epoch calibration** (common mode) is implemented. With fewer than about 3–5 well-distributed stations it
injects the daily GNSS noise into every point, so it is not the default.

### 7.1 Can a calibration fitted in Mexico City be used in Vietnam? (2026-10-30)

**Why it matters.** Most NGL stations in Vietnam stopped between 2019 and 2021. None covers the current HCMC
product (2025–2026). A transferable calibration would let the Vietnamese products be tied without a local station.

**Test.** Five station–product pairs, vertical projection, `gnss_rate = window`:

- MMX1 on the Mexico City S1 asc 078 product;
- HUMG and JNAV on each of the two Hanoi S1 products, asc 128 and desc 091.

Two models of the relation are fitted on a source and applied to a target:

- **M1, offset:** g(t) = i(t) + Δv·t. This is the current calibration.
- **M2, offset and scale:** g(t) = k·i(t) + Δv·t + c. The scale k would be a gain of the processing, the only term
  that does not depend on the scene.

The script is [code/gnss_transfer.py](code/gnss_transfer.py).

| Source → target | Model | Rate residual at the target stations (mm/yr) | Series RMSE (mm) |
|---|---|---|---|
| none → Hanoi asc | – | 7.6 | 7.1 |
| **Mexico → Hanoi asc** | M1 | **134.0** | 39.6 |
| Mexico → Hanoi asc | M2 | 265.3 | 77.4 |
| Hanoi desc → Hanoi asc | M1 | 3.4 | 6.8 |
| none → Hanoi desc | – | 10.9 | 7.7 |
| **Mexico → Hanoi desc** | M1 | **137.4** | 41.2 |
| Mexico → Hanoi desc | M2 | 270.2 | 80.0 |
| Hanoi asc → Hanoi desc | M1 | 4.9 | 7.0 |

**Reading.**

1. **The Mexico equation does not transfer.** Applied to Hanoi it is about 15 times worse than no calibration.
   - The single coefficient, Δv = −126 mm/yr, is the motion of the Mexico product's own reference. That reference is
     the scene mean; the product's mean rate is +0.1 mm/yr, as it should be.
   - So Δv measures how much the Mexico City scene subsides as a whole. It is a property of that scene, not of the
     sensor or the processing, and it carries no information about another city.
2. **No processing gain can be learnt from Mexico.** M2 needs signals that are not a straight line.
   - At MMX1 the subsidence is linear over the six months, so i(t) and t are almost collinear (condition number about
     500).
   - The fitted k = −0.01 ± 0.09 is meaningless: the fit replaces the InSAR by a line.
   - A scale term is only identifiable with several stations moving at different rates, or with non-linear motion.
3. **What does transfer is within one city.** The Hanoi asc calibration applied to the Hanoi desc product, and the
   other way round, reduces the rate residual (10.9 → 4.9 and 7.6 → 3.4 mm/yr).
   - The two products cover the same city and period with the same kind of reference (scene mean), so their
     reference areas move alike.
   - The gain is of the order of the GNSS rate sigmas (3.5–6 mm/yr), so it is suggestive, not proven.
4. **The error level transfers.** The detrended residual is 5–8 mm in every pair, in Mexico and in Hanoi. It is the
   noise of Sentinel-1 PS medians against daily GNSS, and serves as an a-priori uncertainty for products without a
   station.

**Answer.** No: the calibration equation is not transferable across sites. Its coefficient is the motion of the
product's reference, which belongs to one scene. What transfers is:

- the **method**: vertical projection, segment handling, window rates, leave-one-out;
- the **error model**: 5–8 mm per epoch;
- **within a city**, the calibration between products that share the period and the kind of reference.

**For Vietnam without a current station, the options are:**

1. **A historical local calibration (G7).** Process Sentinel-1 over HCMC for 2017–2019, when HCMC, XC03, GOCO,
   LTHA, BTRE and VUNT recorded, and calibrate with leave-one-out on 3–6 stations.
   - Then test a temporal transfer to 2025–2026, using reference areas that do not move between the two periods,
     such as the same stable buildings.
   - Within one city this is defensible; across cities it is not.
2. **A stable reference instead of the scene mean.** Choose a `reference_bbox` on ground known to be stable, such as
   a Pleistocene terrace or a pile-founded structure. The products then need little or no tie, and Δv stays near 0
   by construction.
3. **New stations or reflectors.** Corner reflectors next to a GNSS antenna (G4), or one continuous station in each
   city.

### 7.2 A historical calibration of HCMC and its transfer to 2025–2026 (G7, 2026-10-31)

**Data.** Sentinel-1 desc 018 over HCMC, 2017-11 → 2019-09: 46 images, 2.3 million points, scene-mean reference
(project `hcm_hist_des`). Three NGL stations recorded in that period and have points within 100 m: HCMC, LTHA and
XC03 (GOCO, BTRE and VUNT have no usable overlap). Script: [code/gnss_g7.py](code/gnss_g7.py).

| Station | InSAR (vertical, mm/yr) | GNSS (mm/yr) | Difference | Epochs |
|---|---|---|---|---|
| HCMC | +0.5 | +6.9 ± 2.7 | +6.4 | 31 |
| LTHA | +2.2 | −0.7 ± 6.3 | −2.9 | 12 |
| XC03 | +0.1 | +5.5 ± 2.9 | +5.4 | 11 |

**Leave-one-out** (rate residual at the left-out station, RMS over the three):

| Model | HCMC | LTHA | XC03 | RMS (mm/yr) |
|---|---|---|---|---|
| none | +6.4 | −2.9 | +5.4 | 5.1 |
| M1, offset | +5.2 | −8.8 | +3.6 | **6.3** |
| M2, offset and scale | +4.5 | −6.9 | −0.7 | 4.8 |

**Transfer to 2025–2026** (project `hcm_test_des`, same track, smaller footprint in the centre). The two products are
tied through the 2017–2019 offset (+2.97 mm/yr) and the difference of the scene means over the two footprints
(+0.55 mm/yr). On the 243,894 20 m cells common to both:

- the rate change 2025 − 2017 has a median of −1.3 mm/yr (IQR 6.4);
- on the cells stable in 2017–2019 (|v| < 2 mm/yr) it is **+3.4** mm/yr;
- the tied 2025–2026 map has a median of **+3.9** mm/yr, i.e. the centre of HCMC would be rising.

**Reading.**

1. **Three stations do not determine an offset.** Their differences (−2.9 to +6.4 mm/yr) disagree by more than the
   offset itself. Their spread is that of the GNSS rate sigmas (2.7–6.3 mm/yr over the short 2017–2019 series).
   The offset fitted on all three, +3.0 mm/yr, has a standard error of about 2.9 mm/yr: it is not different from 0.
2. **The offset makes the left-out station worse.** M1 raises the leave-one-out RMS from 5.1 to 6.3 mm/yr.
   M2 lowers it slightly, but only by replacing the InSAR with a line: k is +0.05, −0.33 and −0.42, i.e.
   meaningless, as in §7.1.
3. **The transfer in time gives an implausible map.** A rising city centre contradicts every published HCMC rate.
   The cells that were stable in 2017–2019 would have started rising by 3 mm/yr. The tie adds the 2017–2019 offset,
   which is not significant, to a reference (the scene mean) whose motion changes with time and footprint.

**Answer.** No calibration is supported by the 2017–2019 stations, and none transfers to 2025–2026. The HCMC products
stay referenced to their scene mean, with the reference uncertainty stated: about ±3 mm/yr, the scatter of the three
stations. To tie them, the options 2 and 3 above remain: a stable reference area (a Pleistocene terrace or
pile-founded structures), or corner reflectors and a new continuous station.

### 7.3 Two sensors over Mexico City: Capella tied to Sentinel-1 (2026-11-01)

**Question.** The Capella product (`mexico_capella` v4: asc, left-looking, 18 images 2024-06-26 → 08-15, 241,165
points over 6 × 6 km of Iztapalapa) and the Sentinel-1 product (`mexico_s1` v7: asc 078, right-looking, 16 images
2024-05-03 → 10-30) show the same subsidence pattern with other velocities. No NGL station lies inside the Capella
product. Why do they differ, and can Capella be calibrated?

**Comparison** on the 1,734 common 100 m cells (median per cell):

| Comparison | Capella against S1 | Correlation |
|---|---|---|
| LOS, each over its own period | 1.29 × S1 + 36 mm/yr | 0.89 |
| S1 rate over the Capella period only (06-20 → 08-19) | 1.15 × S1 − 26 mm/yr | 0.89 |
| The same, both turned to vertical (v / los_u) | **1.07** × S1 | 0.89 |

**Reading.** The two products agree in space (correlation 0.89). They differ by three things, all known:

1. **Period.** Capella covers 50 days of the rainy season. The S1 rate over those same days is higher than its
   6-month rate by about 54 mm/yr over the common area. MMX1 shows the same: −364 mm/yr up over the S1 period
   against −265 mm/yr (MIDAS, 18 years). Subsidence in Mexico City is faster in the rainy season.
2. **Line of sight.** S1 LOS (e/n/u) = (−0.69, −0.15, 0.71), Capella (+0.47, −0.46, 0.76). The vertical
   sensitivity differs by 7 %, and east motion enters with opposite signs. Turned to vertical over the same period,
   the gain falls to 1.07.
3. **Reference.** Each product is zero at its own scene mean: the whole basin for S1, 6 × 6 km for Capella.
   This is also why S1 is far from MMX1. The shapes agree (correlation 0.96, 5.2 mm after detrending), but the
   rate differs by −126 mm/yr: the scene mean the InSAR takes as still subsides itself.

**Tie.** A product with no station can take its correction from another product of the same ground
(`geoeyes.validation.tie`). The reference product's rate is fitted over the target's dates only. Both are
turned to vertical rates, and the median over the common cells of (reference − target) is the correction, put back
in the target's LOS. The reference's own GNSS calibration is applied first, so the target is tied to the GNSS
through it. A gain is reported, not corrected. It comes from the periods or the geometries, not an error of
either product, so fitting it to one station would distort the whole map.

| Capella tie to S1 v7 | Value |
|---|---|
| Common 100 m cells | 1,731 |
| Correlation, gain (vertical) | 0.888, 1.07 |
| Correction | **−109.0 mm/yr LOS** (−144.3 vertical), through GNSS MMX1 |
| Spread over the cells (1.48 × MAD) | ±49.6 mm/yr |
| Without the S1 GNSS calibration | +26.5 mm/yr (tied to the S1 scene mean only) |

**Answer.** The differences are explained without any error of either product. Both can be put on the GNSS frame
with one rate each: S1 by MMX1 (−126.4 mm/yr), Capella by the tie (−109.0 mm/yr). Neither is checked independently:
only MMX1 recorded in 2024 inside the S1 product (MXTM, UFXN and UTUL stopped in 2019–2020). ICMX (3 km west) and
MXTX (5 km north) recorded in 2024. An S1 product enlarged to cover them would give the leave-one-out check (G3).

*Superseded (2026-11-05):* G3.1 (§9.1) did that check and the MMX1 offset does not hold for ICMX and MXTX
(−79 / −145 / −23 mm/yr; leave-one-out error −94 at MMX1). The −126.4 and −109.0 mm/yr ties, and the Calibrated
layer and the §6.1 hazard areas built on them, do not put either product on the GNSS frame.

The calibration is applied without changing the product files. On the map, the layer's **Calibrated** switch shows
the calibrated velocities and series (and the legend says so). In Validation, the calibration panel writes
`<product>_calibrated.gpkg` / `.csv` with `vel_los_cal_mm_yr` next to `vel_los_mm_yr`.

## 8. Limitations

1. **Monument and PS.** The median PS within 100 m may not move like the antenna's monument (roof or ground).
   Reflectors co-located with GNSS antennas would remove this (§9, G4).
2. **GNSS noise model.** Rate sigmas assume white noise and are optimistic (Williams et al. 2004). Flicker noise
   and annual terms are not modelled in v1.
3. **Vertical tie and horizontal motion.** The vertical tie assumes that local horizontal motion is negligible.
   Horizontal motion in subsidence bowls breaks this near the bowls' edges. Ascending + descending products would
   allow a 3-D comparison.
   - *(2026-11-05)* At MMX1 the local horizontal anomaly is ~21 mm/yr east (≈ −14 mm/yr LOS), above the 10 mm/yr
     target, and plate motion projects onto a varying **l** as a ramp across the swath. **TODO:** a `full − plate`
     mode that subtracts the plate (ITRF2020-PMM) or a regional reference velocity from the full ENU before
     projecting, so local horizontal motion is kept.
4. **Segment re-joining.** Re-joining segments assumes that both monuments of a moved station share the same rate.
5. **Few stations.** Calibration with one or two stations ties only the reference (offset). A ramp needs three or
   more stations around the scene.

## 9. Research sequence

| Step | Question | Method | Criterion |
|---|---|---|---|
| G1 (done) | Do InSAR and GNSS agree? | §4 per station, both projections | Shape RMSE ≲ InSAR noise; correlation > 0.8 where motion > noise. *(Fixed in code (2026-11-05): `corr` in `compare.py` is now the correlation of the two series after removing each one's own linear trend; the old de-meaned value is kept as `corr_with_trend`. Earlier tables used the old definition and must be recomputed)* |
| G2 (partial) | Does the GNSS tie improve the InSAR away from the stations? | Leave-one-out | RMS after < RMS before, with ≥ 3 stations. *(2026-11-05: §6.2 used only 2 stations; with 3 in G7 it failed, 5.1 → 6.3 mm/yr, §7.2)* |
| G3 | Longer and denser checks | Mexico City S1 product covering ICMX, MXTX and MMX1 (the only three NGL stations recording in 2024, §7.3); Hanoi ≥ 2 years | Leave-one-out with 3 stations; seasonal terms in both rates. Detailed plan: §9.1 |
| G4 | Monument effect | Corner reflectors next to HUMG / JNAV (the corner reflector module exists); PS selection by height | Reflector − GNSS < 2 mm/yr |
| G5 | Better GNSS rates | Flicker plus white noise (Williams et al. 2004), annual terms, common-mode filtering (Wdowinski et al. 1997; Dong et al. 2006) | Realistic sigmas |
| G6 | Full integration | Ramps per epoch (GInSAR, Neely et al. 2020), 3-D with asc + desc (Shen & Liu 2020) | Leave-one-out per epoch |
| G7 | Transfer of a calibration (§7.1): across sites it fails; can it work across time in one city? | S1 over HCMC 2017–2019 with HCMC, XC03, GOCO, LTHA, BTRE and VUNT; calibrate, then apply to 2025–2026 with the same reference areas | Leave-one-out over 3–6 stations in 2017–2019; the 2025–2026 rates stay plausible against published HCMC subsidence. **Done (§7.2): no; 3 stations do not determine an offset, and the transfer makes the centre rise** |

### 9.1 G3 plan: a GNSS reference benchmark for GeoEyes (written 2026-11-04)

**Goal.** One truly independent check, a leave-one-out with at least 3 stations, kept as a *fixed benchmark*: after
every engine change it is run again and compared. Mexico City is the only site that qualifies, because the subsidence
(up to ~360 mm/yr) is far above the GNSS noise. Hanoi is the opposite case (§6.2).

Each step ends at a review gate: the result is written in this section and the next step waits for approval.

| Step | Work | Pass criterion | Status |
|---|---|---|---|
| G3.0 | Feasibility: stations, burst coverage, disk | 3 stations recording in one period, inside one subswath | **Done** (below) |
| G3.1 | Pilot: same period 2024-05 → 2024-10, larger AOI covering the 3 stations | See below | **Fail** (2026-11-04), awaiting review |
| G3.1b | Diagnosis: APS, SCLA and unwrapping at the 3 stations, from the G3.1 `state.h5` | Find the cause | **Done** (2026-11-04) |
| G3.1c | Rerun with (b) the APS fitted on stable ground only, (c) ERA5 on every interferogram | Gain against GNSS moves towards 1 | **Done** (2026-11-04): (c) best, still a fail; awaiting review |
| G3.2 | Long series 2023-07 → 2025-01 with seasonal terms | Leave-one-out still passes with annual terms; rates agree with G3.1 within errors | Waiting |
| G3.3 | Freeze as a benchmark | A command reproduces the numbers and fails when a metric degrades | Waiting |
| G3.4 | Hanoi ≥ 2 years (S1 desc 091, HUMG + JNAV) | Shape correlation > 0.5 after the annual terms are removed, or a conclusion that it is not usable yet | Waiting |

**G3.0, feasibility (2026-11-04).**

- NGL stations in [−99.40, 19.10, −98.70, 19.70] with data since 2023:

  | Station | Lon, lat | Data | Note |
  |---|---|---|---|
  | MMX1 | −99.068, 19.432 | 2008-04 → 2026-10 | already used (§6.1) |
  | ICMX | −99.171, 19.406 | 2017-07 → 2026-01 | west of the current `mexico_s1` AOI |
  | MXTX | −98.876, 19.540 | 2019-08 → **2025-02** | north-east of the current AOI |
  | MXAJ | −98.759, 19.136 | 2017-07 → 2023-12 | stopped before 2024, not used |

- All three are inside IW3 of track 78 (bursts 165499–165500), already downloaded for `mexico_s1`, so G3.1 needs no
  new download. MXTX is only ~700 m from the east edge of burst 165500; G3.1 must check that it is inside the valid
  sample window.
- Disk: the `mexico_s1` run (16 scenes, 0.2° × 0.2°) takes ~2 GB of stack and ~2 GB of ps_runs. The G3.1 AOI is
  ~2× larger, so ~10 GB; drive D has 30 GB free. G3.2 (~48 scenes) needs ~35–45 GB including bursts, **more than is
  free**. At G3.2 a choice is needed: free space or another drive, or 1–2 scenes per month (`max_per_month`).

**G3.1, three-station pilot.**

- New project `mexico_g3`: every parameter of `mexico_s1` v7, only the AOI changed to [−99.20, 19.33, −98.85, 19.57].
  The reference stays the scene mean, so the reference offset shows clearly.
- Checks before the result is trusted:
  - ≥ 20 PS within 100 m of each station;
  - MXTX inside the valid samples of the burst;
  - on the area shared with `mexico_s1` v7, velocity correlation > 0.98 (the larger AOI must not change the earlier
    result apart from the reference offset).
- Run `geoeyes gnss mexico_g3` with `calibration = offset` and `plane` (3 stations are just enough for a plane).
- Pass criteria:
  - per station: shape correlation > 0.8 and detrended RMSE ≤ 8 mm (*fixed in code 2026-11-05:* `corr` is now
    detrended, see G1 in §9; the G3.1 "Corr (trend incl.)" values below are the old `corr_with_trend` and must be
    recomputed);
  - leave-one-out RMS after calibration < before;
  - leave-one-out RMS after calibration ≤ 10 mm/yr (~3% of the largest subsidence). Reported whether it passes or not.
- The result may be a fail; then the cause (monument, horizontal motion, few PS) is recorded instead of tuning
  parameters until it passes.

**G3.1 result (2026-11-04): fail.** Product `mexico_g3_sentinel1-asc-078_20240503_20241030_v1`, 3,632,594 PS, PS step
55 min. Check script: [code/gnss_g3.py](code/gnss_g3.py).

- Input checks: **pass.**
  - PS within 100 m: ICMX 174, MMX1 59, MXTX 33. The nearest PS to MXTX is 18 m away, so MXTX is inside the valid
    samples.
  - Against v7 on 35,708 shared 100 m cells: correlation 0.982, g3 = 0.887 × v7 − 8.0 mm/yr, median difference
    −10 mm/yr. The slope of 0.887 means the larger AOI *compresses* the velocity range by ~11%, beyond a constant
    offset (see hypothesis 2).
- Against GNSS (vertical projection, GNSS rate over the same 6-month window):

  | Station | InSAR LOS | GNSS LOS | Diff | Diff vs MIDAS | Corr (trend incl.) | Detrended RMSE |
  |---|---|---|---|---|---|---|
  | ICMX | +27.4 | −52.1 | −79.4 | −45.8 | **−0.46** | 7.7 mm |
  | MMX1 | −113.2 | −258.2 | −145.1 | −74.5 | 0.92 | 6.8 mm |
  | MXTX | −9.5 | −32.3 | −22.7 | +0.1 | **0.17** | **13.7 mm** |

  (mm/yr). Only MMX1 passes the per-station criteria.
- Leave-one-out with an offset: RMS 96.4 before → **75.0 mm/yr** after. That is better than before, but far from
  10 mm/yr. Per-station errors: ICMX +4.5, MMX1 −94.0, MXTX +89.5. A plane through 3 stations fits them exactly and
  tests nothing independently; leave-one-out for the plane (2 stations left) falls back to an offset and gives the
  same numbers.
- So the difference is **not a constant**. The MMX1 − ICMX velocity difference is −140 mm/yr in InSAR and −206 in
  GNSS: InSAR keeps only ~68% of the contrast between the two stations.

**Candidate causes** (not yet tested; no parameter is tuned to make it pass):

1. *A 6-month GNSS rate is dominated by the season.* The window vertical rate at MMX1 is −364 mm/yr against −265 from
   MIDAS (18 years); at ICMX it is −73 against −26 (from the LOS −52.1 / −18.4 and l_u ≈ 0.71; corrected
   2026-11-05, was −64). Against MIDAS the differences shrink to −46 / −75 / 0. Six months
   (the rainy season) cannot give a reference rate; this is what G3.2 is for.
2. *Height-linear APS removes part of the subsidence.* Each interferogram loses a phase term proportional to height,
   and 14 of 15 use it. In Mexico City the fast subsidence is on the low former lake bed and the stable ground is on
   the higher hills, so subsidence correlates with height and is partly taken as atmosphere. This would explain both
   the 0.68 ratio between stations and the 0.887 slope when the AOI changes: a larger AOI holds more mountain, which
   changes the phase–height coefficient. Test: rerun the APS step with `weather` or with no height term, and compare
   the slopes again.
3. *ICMX and MXTX may stand on different ground from the PS around them.* ICMX is on the edge of the western hills:
   InSAR gives +27 where GNSS gives −52. The PS map within 100 m needs a look.

**Proposal at the gate:** before G3.2, add G3.1b, a diagnosis of hypothesis 2 on the G3.1 data itself (rerun from the
APS step; no download needed). If the slope against GNSS moves towards 1, this is an engine fault and must be fixed
before the benchmark is frozen. G3.2 then still needs the disk decision for drive D (now ~10 GB free).

**G3.1b, diagnosis (2026-11-04).** The engine was not rerun: G3.1 deleted its step 1–5 checkpoints and drive D has no
room for a full run. Velocity is linear in the phase, so the velocity each term (APS, SCLA) removed is the slope over
time of that term in `state.h5`. Script: [code/gnss_g3_aps.py](code/gnss_g3_aps.py). The decomposition reproduces the
engine's `v_linear` to 1.5 mm/yr. Caveat: it ignores that pass 2 unwraps again.

- **Height-linear APS removes part of the subsidence: partly confirmed.** The velocity carried by the linear APS is
  −41 mm/yr per 100 m of height and correlates −0.81 with height, over a PS height range of only ~200 m. At the
  stations the APS changed the velocity by +20 (ICMX), +22 (MMX1) and −5 mm/yr (MXTX); positive means the APS
  *raised* it (wording corrected 2026-11-05, was "removed"). The near-equal +20 / +22 at ICMX / MMX1 already argue
  against the APS explaining the 0.68 contrast. Without the APS the result improves (PS medians from `state.h5`,
  not the product):

  | InSAR variant | vs GNSS window: gain, LOO RMS | vs MIDAS: gain, LOO RMS |
  |---|---|---|
  | as delivered | 0.58, 70.7 mm/yr (product: 75.0) | 0.73, 42.1 mm/yr (product: 46.1) |
  | no APS | 0.65, 55.5 | 0.81, 25.2 |
  | no APS, no SCLA | 0.67, 51.4 | 0.83, 23.4 |

- **The SCLA leaks velocity.** The scene-mean B⊥ correlates −0.47 with time, so over 6 months the look-angle error and
  the velocity are hard to separate. The SCLA term carries 14 mm/yr (scene std), −23 mm/yr at MXTX.
- **No cycle-slip pattern.** At MMX1 the InSAR − GNSS difference grows smoothly with time (−22 → +47 mm), with no
  ~28 mm steps. The MXTX series jumps ±20–40 mm between neighbouring dates, while the PS within 100 m agree closely
  (spread 2–3 mm). That is noise shared by the whole area, like atmosphere, not noise of single points.
- **The 10 mm/yr threshold of G3.1 could not be met with 6 months.** The InSAR rate standard errors at the stations
  are 13.6 / 13.2 / 26.7 mm/yr, so the expected leave-one-out RMS is ~20–30 mm/yr even with a perfect engine. The
  23–25 mm/yr without the APS sits at that noise level. This is a fault in how the G3.1 criterion was set, not in the
  engine.

**G3.1b conclusions.**

1. The linear APS, fitted per interferogram on every PS, is **a real engine fault** where subsidence correlates with
   height. It compresses the velocity range and depends on the AOI (the 0.887 slope when the AOI changes). The fix
   needs approval because it changes every project on the default. The options:
   - (a) estimate the phase–height coefficient jointly with a temporal deformation model, not per interferogram;
   - (b) fit only on stable ground (`aps_non_defo`), as StaMPS does;
   - (c) use ERA5 for every interferogram (`select = "all"`).
2. Six months is too short for a benchmark. G3.2 (18 months) cuts the rate error ~5× and weakens the B⊥–time
   correlation. The 10 mm/yr criterion stays for G3.2. For G3.1 a fair threshold is ≤ 2× the expected standard error,
   ~40 mm/yr: as delivered it is borderline against MIDAS (42), and without the APS it passes clearly (25).
   *(2026-11-05)* "~5×" is an optimistic upper bound: it assumes white noise and 46 scenes; the plan is 2 per month
   (~36 scenes, ≈ 4.5×), annual terms over 1.5 cycles inflate the SE, and correlated APS reduces the gain further.
   The expected SE must be computed with the annual terms in the design matrix. From the product (`compare.py`)
   the as-delivered LOO against MIDAS is 46.1, i.e. a fail at 40.

*Corrected after G3.1c:* the linear APS does remove signal, but it is **not** the main reason InSAR keeps only ~70% of
the contrast between the stations (see below).

**G3.1c, reruns with another APS (2026-11-04).** Same data and parameters as G3.1; only the atmosphere removal
changes. Checkpoints in `lean` mode because the disk was full (37 GB of the workspace `trash` were emptied, with the
owner's approval).

| | v1: linear APS on all PS, ERA5 where better (1/15) | v2 (b): APS fitted on the Sierra de Guadalupe hills only | v3 (c): ERA5 on every interferogram |
|---|---|---|---|
| Phase–height coefficient of the APS | −41 mm/yr per 100 m | −7 | (ERA5) |
| Velocity change by the APS at ICMX / MMX1 / MXTX (+ = raised) | +20 / +22 / −5 | −42 / −44 / −57 | +21 / +10 / −14 |
| InSAR ICMX / MMX1 / MXTX (mm/yr) | +27 / −113 / −10 | +19 / −104 / −3 | +26 / −143 / −19 |
| Gain vs GNSS window / MIDAS | 0.58 / 0.73 | 0.57 / 0.72 | **0.67 / 0.84** |
| LOO RMS vs GNSS window (after) | 75.0 | 77.9 | **63.4** |
| LOO RMS vs MIDAS (after) | 46.1 (42.1 from `state.h5`) | 36.2 | 37.8 |
| Corr (trend incl.) ICMX / MMX1 / MXTX | −0.46 / 0.92 / 0.17 | −0.31 / 0.95 / 0.09 | −0.34 / **0.97** / 0.27 |
| Against `mexico_s1` v7: corr, slope | 0.982, 0.887 | — | 0.904, 0.931 |

Reading the results:

- **(b) changes almost nothing.** Fitted on the hills, the APS removes about the same amount at all three stations,
  i.e. a constant that the offset calibration already handles. The compression between the stations is unchanged.
- **(c) is the best of the three.** The gain rises 0.58 → 0.67 against the GNSS window and 0.73 → 0.84 against MIDAS.
  The leave-one-out RMS falls 75 → 63 mm/yr. The shape correlation at MMX1 reaches 0.97, with a detrended RMSE of
  4.9 mm.
  - ERA5 also removes up to 20 mm/yr at ICMX. That is a real atmospheric trend from the dry to the wet season (05 →
    10). Over 6 months, InSAR data alone cannot separate it from velocity.
- **Still a fail, and the main cause is not yet identified.** After the offset, MMX1 is still ~70 mm/yr slower than
  GNSS. ICMX and MXTX have low shape correlation: their signal is small (−52 and −32 mm/yr LOS) against 6-month noise.
  The remaining causes:
  - a 6-month GNSS rate that is biased by the season against the long-term rate (hypothesis 1);
  - SCLA leaking velocity (B⊥–time correlation −0.47);
  - atmospheric noise shared by each area (MXTX).

  All three shrink sharply with a longer series.

**Proposal at the gate:**

1. Use (c) (`select = "all"`) for G3.2. Do not change the engine default for every project yet; that decision waits
   for G3.2 to confirm it on the long series.
2. Move to G3.2 (2023-07 → 2025-01). Drive D has ~27 GB free and C ~12 GB; G3.2 needs ~35–45 GB. It can fit with
   `checkpoints = "lean"`, a limit of 2 scenes per month (~36 scenes), and the G3.1 stack/ps_runs deleted at the start.

**G3.1d, why ICMX and MXTX do not follow GNSS (2026-11-04).** Offline on v3 (`state.h5`), script
[code/gnss_g3_ramp.py](code/gnss_g3_ramp.py).

- **Shape: cause found — a scene-wide ramp per epoch.** The PS within 100 m of each station agree to 2–5 mm, yet ICMX
  (west) and MXTX (east, ~34 km away, 31 km of it E–W) scatter in opposite directions on the same dates (2024-05-27: −26 / +69 mm).
  A plane fitted per epoch to the non-linear part of the displacement (each PS's own straight line removed) reaches
  ±16 mm per 10 km E–W, largest in May and late October, and explains 62% of the non-linear variance over the scene.
  It is the same before and after the ERA5 correction, so it is not troposphere ERA5 can see: ionosphere (2024 is
  the solar maximum, the ascending pass is in the evening, Mexico City lies under the equatorial anomaly) or orbit.

  | Station | residual InSAR − GNSS, detrended (std, mm) | corr with the plane | after removing the plane |
  |---|---|---|---|
  | ICMX | 10.0 | **0.92** | **3.8** |
  | MMX1 | 4.8 | 0.66 | 3.6 |
  | MXTX | 14.6 | 0.69 | 12.8 |

  MXTX is only partly explained: it sits 700 m from the burst edge, where a plane fitted over the scene is an
  extrapolation.
- **Is the processing wrong?** No implemented step was found wrong apart from the per-interferogram linear APS
  (G3.1b, fixed by (c)). The gap is a missing step: the engine, like StaMPS by default, has no ionosphere or ramp
  correction (`scla_deramp = "n"`). *Corrected in G3.1e:* step 8 does catch it, in `disp_scn_mm`; the validation
  read `disp_mm`.
- **Rates: not resolved.** The PS field around MMX1 is uniform out to 2 km (−128 to −143 mm/yr), so the station is
  not on a local spot. Against MIDAS, ICMX and MMX1 have the same offset (GNSS − InSAR −44 mm/yr) and the ICMX–MMX1 contrast is
  100%; against the 6-month GNSS rates it is 82%. MXTX is the outlier, ~55–65 mm/yr too low relative to ICMX, but its
  InSAR rate SE is 28.6 mm/yr (~2σ). A ramp that grows linearly in time would bias rates the same way and cannot be
  told apart from the subsidence bowl with InSAR alone on 6 months.

**Proposal:** (1) add an optional per-epoch ramp estimate on the non-linear part only (velocity untouched), to remove
the shape noise; (2) plan a split-spectrum ionosphere correction for S1 (needed for 2024–2025 data); (3) G3.2 tests
both on 18 months, where a linear-in-time ramp and the bowl separate better.

**G3.1e, plan for proposal (1) — revised before coding (2026-11-04).** Checking the engine first showed that step 8
already removes this ramp. SCN is the temporally high-passed phase (local linear fit, so a 6-month series keeps its
trend) low-passed in space with a 100 m Gaussian, which keeps every longer wavelength, the scene-wide ramp included.
The products carry the result as `disp_scn_mm`. On v3, station series from `disp_scn_mm`:

| Station | detrended RMSE `disp_mm` → `disp_scn_mm` (mm) | corr, `disp_scn_mm` (de-meaned, trend included) |
|---|---|---|
| ICMX | 10.0 → **2.6** | (corr of the raw series −0.86: the trend has the wrong sign, see rates) |
| MMX1 | 4.8 → **1.5** | 1.00 |
| MXTX | 14.7 → **3.8** | 0.47 |

Rates barely move (SCN keeps the trend by design): gain 0.62 / 0.79 and LOO 66 / 38 mm/yr against window / MIDAS.
So the gap is not in the engine but in the validation, which reads `disp_mm` only. Revised plan, replacing a new
deramp step:

1. `[validation.gnss] series = "scn" | "raw"` (default `"scn"`; a product without `disp_scn_mm` falls back to
   `"raw"` with a warning). The chosen series is recorded in `comparison.json` and in `series.npz`.
2. Unit tests: the parameter is validated, the SCN column is read, the fallback warns.
3. Rerun `geoeyes gnss mexico_g3` on v3 and record the numbers here.
4. Not changed: the engine, the products, the calibration that the web app applies to `disp_mm` (offset / plane are
   rate corrections and apply to either series).

The remaining open question is the rates (contrast and ICMX trend sign), which G3.2 addresses.

*Done (2026-11-04):* items 1–3. `geoeyes gnss mexico_g3` on v3 now reads `disp_scn_mm`: detrended RMSE ICMX 2.6,
MMX1 1.5, MXTX 3.8 mm (was 10.0 / 4.8 / 14.7); offset LOO 86.7 → 66.0 mm/yr (ICMX −5, MMX1 −78, MXTX +83). Unit
tests: 23 passed.

*Caveat (2026-11-05):* over a 6-month stack the SCN series is ≈ the linear trend plus sub-100 m noise: the
temporal high-pass of a 365-day local-linear fit is everything but the line, and through the 100 m Gaussian SCN
removes that non-linear part at every wavelength above 100 m. The drop 4.8 → 1.5 mm at MMX1 therefore mostly reflects the filter, not
InSAR–GNSS agreement, and the "1.00" above is the trend. Validation should use `raw`; SCN is a diagnostic only.
*Fixed in code (2026-11-05):* the default is now `series = "raw"` (`validation/gnss/compare.py`, output schema
`geoeyes.gnss/2`); `"scn"` stays available as an explicit diagnostic. The numbers above were computed with
`"scn"` and the old correlation and must be recomputed.

*The interferogram deramp of the old workflow* (`[ps] scla_deramp`, StaMPS): present in the engine — a plane, or a
quadratic when it fits clearly better, removed from every interferogram before the SCLA, the pass-2 unwrapping and
the velocity. It is on in the ICEYE and COSMO-SkyMed presets (`hanoi_csk`) and off for Sentinel-1 (`mexico_s1`,
`mexico_g3`). It removes the whole plane, the part that grows linearly in time included, so on a scene whose
subsidence bowl spans the frame it also removes the bowl's tilt and changes the rates. SCN removes only the part that
is not linear in time. Testing `scla_deramp = "y"` on the 18-month G3.2 is the clean way to see whether the
linear-in-time ramp is what compresses the station contrast.

**Review 2026-11-05** (directions for G3.2 onwards):

- The 3 benchmark stations are also the tuning set: variant (c) was chosen by leave-one-out on them, and its gap to
  v1 (63 vs 75 mm/yr) is below the ~23 mm/yr expected noise; against MIDAS variant (b) is best (36.2 vs 37.8). The
  choice of (c) is not yet supported by independent data.
- With n = 3, report confidence intervals (bootstrap or analytic) for the gain and the LOO RMS.
- "After < before" is a weak criterion against a scene-mean-referenced product: compare against a stable-area
  reference baseline (`reference_bbox`) instead.
- The pass threshold moved from 10 to ~40 mm/yr after the results were seen. Pre-register the G3.2 thresholds from
  the expected SE (annual terms included) before running it.
- The ionosphere attribution of G3.1d is speculative: a per-epoch plane fitted on the same PS can absorb bowl
  motion. Test it with a split-spectrum correction or a descending track.

**G3.2–G3.4** will be detailed once G3.1 is approved.

## 10. Implementation

| Part | Where |
|---|---|
| NGL station list, steps, tenv3, MIDAS (cached, https), cleaning and segments | `src/geoeyes/validation/gnss/ngl.py` |
| Matching, projections, statistics, calibration, leave-one-out, correction | `src/geoeyes/validation/gnss/compare.py` |
| CLI `geoeyes gnss <project> [--product ID] [--set key=value]` | `src/geoeyes/cli/main.py` |
| API `/api/projects/{p}/products/{id}/gnss[...]` | `src/geoeyes/api/gnss.py` (background runs: `api/jobs.py`) |
| Web app: project → Validation → GNSS (table, calibration, chart per station); Hazard → "GNSS tie" and stations on the map | `webapp/src/components/Gnss.tsx`, `webapp/src/pages/Hazard.tsx` |
| Hazard tie | `[postprocess.hazard] gnss_tie`, `src/geoeyes/hazard/assess.py` |
| Tie to another product (§7.3), the calibration applied (GNSS, else tie) | `src/geoeyes/validation/tie.py`; CLI `geoeyes tie <project> --reference P/ID`; API `/api/projects/{p}/products/{id}/tie` and `/export-calibrated` |
| Calibrated map layer and export | `cal=1` on the layer routes (`api/points.py`: cache `<product_id>@cal`); `export/vector.py` (`calibration=`); web app: Calibrated switch of a layer, `webapp/src/components/Calibration.tsx` |
| Tests (tenv3 parsing, moved antenna, synthetic reference offset recovered by a plane from 3 stations, leave-one-out, hazard tie; tie recovering a known offset across geometries and periods, calibrated layer and export) | `tests/unit/validation/test_gnss.py`, `tests/unit/validation/test_tie.py`, `tests/unit/hazard/test_hazard.py` |

The outputs go to `<project>/analyses/gnss/<product_id>/`: `comparison.json`, `series.npz` and `manifest.json`;
a tie to `<project>/analyses/tie/<product_id>/tie.json`.
NGL files are cached in `<workspace>/cache/gnss/ngl/`: positions for a day, lists for a week.

## 11. References

Every DOI below was checked on Crossref on 2026-10-25.

**NGL**

- Blewitt G, Hammond WC, Kreemer C (2018) Harnessing the GPS data explosion for interdisciplinary science. *Eos* 99. https://doi.org/10.1029/2018EO104623
- Blewitt G, Kreemer C, Hammond WC, Gazeaux J (2016) MIDAS robust trend estimator for accurate GPS station velocities without step detection. *J. Geophys. Res. Solid Earth* 121(3):2054–2068. https://doi.org/10.1002/2015JB012552

**GNSS and InSAR**

- Del Soldato M, Confuorto P, Bianchini S, Sbarra P, Casagli N (2021) Review of works combining GNSS and InSAR in Europe. *Remote Sensing* 13:1684. https://doi.org/10.3390/rs13091684
- Farolfi G, Del Soldato M, Bianchini S, Casagli N (2019) A procedure to use GNSS data to calibrate satellite PSI data for the study of subsidence: an example from the north-western Adriatic coast (Italy). *European Journal of Remote Sensing* 52:54–63. https://doi.org/10.1080/22797254.2019.1663710
- Fattahi H, Amelung F (2014) InSAR uncertainty due to orbital errors. *Geophysical Journal International* 199(1):549–560. https://doi.org/10.1093/gji/ggu276
- Hammond WC, Blewitt G, Kreemer C (2016) GPS Imaging of vertical land motion in California and Nevada: Implications for Sierra Nevada uplift. *J. Geophys. Res. Solid Earth* 121(10):7681–7703. https://doi.org/10.1002/2016JB013458
- Hammond WC, Burgette RJ, Johnson KM, Blewitt G (2018) Uplift of the Western Transverse Ranges and Ventura area of Southern California: a four-technique geodetic study combining GPS, InSAR, leveling, and tide gauges. *J. Geophys. Res. Solid Earth* 123(1):836–858. https://doi.org/10.1002/2017JB014499
- Hammond WC, Blewitt G, Kreemer C, Nerem RS (2021) GPS Imaging of global vertical land motion for studies of sea level rise. *J. Geophys. Res. Solid Earth* 126(7):e2021JB022355. https://doi.org/10.1029/2021JB022355
- Neely WR, Borsa AA, Silverii F (2020) GInSAR: a cGPS correction for enhanced InSAR time series. *IEEE Trans. Geoscience and Remote Sensing* 58(1):136–146. https://doi.org/10.1109/TGRS.2019.2934118
- Shen ZK, Liu Z (2020) Integration of GPS and InSAR data for resolving 3-dimensional crustal deformation. *Earth and Space Science* 7(4):e2019EA001036. https://doi.org/10.1029/2019EA001036
- Tong X, Sandwell DT, Smith-Konter B (2013) High-resolution interseismic velocity data along the San Andreas fault from GPS and InSAR. *J. Geophys. Res. Solid Earth* 118:369–389. https://doi.org/10.1029/2012JB009442
- Weiss JR, Walters RJ, Morishita Y, Wright TJ, Lazecky M, Wang H, Hussain E, Hooper AJ, Elliott JR, Rollins C, et al. (2020) High-resolution surface velocities and strain for Anatolia from Sentinel-1 InSAR and GNSS data. *Geophysical Research Letters* 47(17):e2020GL087376. https://doi.org/10.1029/2020GL087376
- Wright TJ, Parsons BE, Lu Z (2004) Toward mapping surface deformation in three dimensions using InSAR. *Geophysical Research Letters* 31(1). https://doi.org/10.1029/2003GL018827
- Xu X, Sandwell DT, Klein E, Bock Y (2021) Integrated Sentinel-1 InSAR and GNSS time-series along the San Andreas fault system. *J. Geophys. Res. Solid Earth* 126:e2021JB022579. https://doi.org/10.1029/2021JB022579

**Monuments and scatterers**

- Dheenathayalan P, Small D, Schubert A, Hanssen RF (2016) High-precision positioning of radar scatterers. *Journal of Geodesy* 90:403–422. https://doi.org/10.1007/s00190-015-0883-4
- Dheenathayalan P, Small D, Hanssen RF (2018) 3-D positioning and target association for medium-resolution SAR sensors. *IEEE Trans. Geoscience and Remote Sensing* 56:6841–6853. https://doi.org/10.1109/TGRS.2018.2844108
- Mahapatra P, van der Marel H, van Leijen F, Samiei-Esfahany S, Klees R, Hanssen R (2018) InSAR datum connection using GNSS-augmented radar transponders. *Journal of Geodesy* 92(1):21–32. https://doi.org/10.1007/s00190-017-1041-y
- Parker AL, Featherstone WE, Penna NT, Filmer MS, Garthwaite MC (2017) Practical considerations before installing ground-based geodetic infrastructure for integrated InSAR and cGNSS monitoring of vertical land motion. *Sensors* 17(8):1753. https://doi.org/10.3390/s17081753

**GNSS noise and rates**

- Blewitt G, Lavallée D (2002) Effect of annual signals on geodetic velocity. *J. Geophys. Res.* 107(B7). https://doi.org/10.1029/2001JB000570
- Dong D, Fang P, Bock Y, Webb F, Prawirodirdjo L, Kedar S, Jamason P (2006) Spatiotemporal filtering using principal component analysis and Karhunen-Loeve expansion approaches for regional GPS network analysis. *J. Geophys. Res.* 111:B03405. https://doi.org/10.1029/2005JB003806
- Mao A, Harrison CGA, Dixon TH (1999) Noise in GPS coordinate time series. *J. Geophys. Res.* 104(B2):2797–2816. https://doi.org/10.1029/1998JB900033
- Wdowinski S, Bock Y, Zhang J, Fang P, Genrich J (1997) Southern California permanent GPS geodetic array: spatial filtering of daily positions for estimating coseismic and postseismic displacements induced by the 1992 Landers earthquake. *J. Geophys. Res.* 102(B8):18057–18070. https://doi.org/10.1029/97JB01378
- Williams SDP, Bock Y, Fang P, Jamason P, Nikolaidis RM, Prawirodirdjo L, Miller M, Johnson DJ (2004) Error analysis of continuous GPS position time series. *J. Geophys. Res.* 109:B03412. https://doi.org/10.1029/2003JB002741

**Mexico City and Hanoi**

- Cabral-Cano E, Dixon TH, Miralles-Wilhelm F, Díaz-Molina O, Sánchez-Zamora O, Carande RE (2008) Space geodetic imaging of rapid ground subsidence in Mexico City. *GSA Bulletin* 120(11–12):1556–1566. https://doi.org/10.1130/B26001.1
- Cabral-Cano E, Pérez-Campos X, Márquez-Azúa B, Sergeeva MA, Salazar-Tlaczani L, DeMets C, Adams D, Galetzka J, Hodgkinson K, Feaux K, et al. (2018) TLALOCNet: a continuous GPS-Met backbone in Mexico for seismotectonic and atmospheric research. *Seismological Research Letters* 89(2A):373–381. https://doi.org/10.1785/0220170190
- Chaussard E, Wdowinski S, Cabral-Cano E, Amelung F (2014) Land subsidence in central Mexico detected by ALOS InSAR time-series. *Remote Sensing of Environment* 140:94–106. https://doi.org/10.1016/j.rse.2013.08.038
- Cigna F, Tapete D (2021) Present-day land subsidence rates, surface faulting hazard and risk in Mexico City with 2014–2020 Sentinel-1 IW InSAR. *Remote Sensing of Environment* 253:112161. https://doi.org/10.1016/j.rse.2020.112161
- Dang VK, Doubre C, Weber C, Gourmelen N, Masson F (2014) Recent land subsidence caused by the rapid urban development in the Hanoi region (Vietnam) using ALOS InSAR data. *Natural Hazards and Earth System Sciences* 14(3):657–674. https://doi.org/10.5194/nhess-14-657-2014
- Solano-Rojas D, Wdowinski S, Cabral-Cano E, Osmanoğlu B (2020) Detecting differential ground displacements of civil structures in fast-subsiding metropolises with interferometric SAR and band-pass filtering. *Scientific Reports* 10:15460. https://doi.org/10.1038/s41598-020-72293-z
