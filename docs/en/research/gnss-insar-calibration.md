# GNSS (Nevada Geodetic Laboratory) to validate and calibrate InSAR time series

> Research note and method of `geoeyes gnss` (package `geoeyes.validation.gnss`, web app: project page →
> Validation → GNSS, and "GNSS tie" on the Hazard page).
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
  - Hammond et al. (2016, 2018) give GNSS the frame and InSAR the detail ("GPS Imaging").
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

## 8. Limitations

1. **Monument and PS.** The median PS within 100 m may not move like the antenna's monument (roof or ground).
   Reflectors co-located with GNSS antennas would remove this (§9, G4).
2. **GNSS noise model.** Rate sigmas assume white noise and are optimistic (Williams et al. 2004). Flicker noise
   and annual terms are not modelled in v1.
3. **Vertical tie and horizontal motion.** The vertical tie assumes that local horizontal motion is negligible.
   Horizontal motion in subsidence bowls breaks this near the bowls' edges. Ascending + descending products would
   allow a 3-D comparison.
4. **Segment re-joining.** Re-joining segments assumes that both monuments of a moved station share the same rate.
5. **Few stations.** Calibration with one or two stations ties only the reference (offset). A ramp needs three or
   more stations around the scene.

## 9. Research sequence

| Step | Question | Method | Criterion |
|---|---|---|---|
| G1 (done) | Do InSAR and GNSS agree? | §4 per station, both projections | Shape RMSE ≲ InSAR noise; correlation > 0.8 where motion > noise |
| G2 (done) | Does the GNSS tie improve the InSAR away from the stations? | Leave-one-out | RMS after < RMS before, with ≥ 3 stations |
| G3 | Longer and denser checks | Mexico City S1 product covering ICMX, MXTX and MMX1; Hanoi ≥ 2 years | Leave-one-out with 3 stations; seasonal terms in both rates |
| G4 | Monument effect | Corner reflectors next to HUMG / JNAV (the corner reflector module exists); PS selection by height | Reflector − GNSS < 2 mm/yr |
| G5 | Better GNSS rates | Flicker plus white noise (Williams et al. 2004), annual terms, common-mode filtering (Wdowinski et al. 1997; Dong et al. 2006) | Realistic sigmas |
| G6 | Full integration | Ramps per epoch (GInSAR, Neely et al. 2020), 3-D with asc + desc (Shen & Liu 2020) | Leave-one-out per epoch |

## 10. Implementation

| Part | Where |
|---|---|
| NGL station list, steps, tenv3, MIDAS (cached, https), cleaning and segments | `src/geoeyes/validation/gnss/ngl.py` |
| Matching, projections, statistics, calibration, leave-one-out, correction | `src/geoeyes/validation/gnss/compare.py` |
| CLI `geoeyes gnss <project> [--product ID] [--set key=value]` | `src/geoeyes/cli/main.py` |
| API `/api/projects/{p}/products/{id}/gnss[...]` | `src/geoeyes/api/gnss.py` (background runs: `api/jobs.py`) |
| Web app: project → Validation → GNSS (table, calibration, chart per station); Hazard → "GNSS tie" and stations on the map | `webapp/src/components/Gnss.tsx`, `webapp/src/pages/Hazard.tsx` |
| Hazard tie | `[postprocess.hazard] gnss_tie`, `src/geoeyes/hazard/assess.py` |
| Tests (tenv3 parsing, moved antenna, synthetic reference offset recovered by a plane from 3 stations, leave-one-out, hazard tie) | `tests/unit/validation/test_gnss.py`, `tests/unit/hazard/test_hazard.py` |

The outputs go to `<project>/analyses/gnss/<product_id>/`: `comparison.json`, `series.npz` and `manifest.json`.
NGL files are cached in `<workspace>/cache/gnss/ngl/`: positions for a day, lists for a week.

## 11. References

Every DOI below was checked on Crossref on 2026-10-25.

**NGL**

- Blewitt G, Hammond WC, Kreemer C (2018) Harnessing the GPS data explosion for interdisciplinary science. *Eos* 99. https://doi.org/10.1029/2018EO104623
- Blewitt G, Kreemer C, Hammond WC, Gazeaux J (2016) MIDAS robust trend estimator for accurate GPS station velocities without step detection. *J. Geophys. Res. Solid Earth* 121(3):2054–2068. https://doi.org/10.1002/2015JB012552
- Blewitt G (2024) An improved equation of latitude and a global system of graticule distance coordinates. *Journal of Geodesy* 98:6. https://doi.org/10.1007/s00190-023-01815-0

**GNSS and InSAR**

- Del Soldato M, Confuorto P, Bianchini S, Sbarra P, Casagli N (2021) Review of works combining GNSS and InSAR in Europe. *Remote Sensing* 13:1684. https://doi.org/10.3390/rs13091684
- Farolfi G, Del Soldato M, Bianchini S, Casagli N (2019) A procedure to use GNSS data to calibrate satellite PSI data for the study of subsidence: an example from the north-western Adriatic coast (Italy). *European Journal of Remote Sensing* 52:54–63. https://doi.org/10.1080/22797254.2019.1663710
- Fattahi H, Amelung F (2014) InSAR uncertainty due to orbital errors. *Geophysical Journal International* 199(1):549–560. https://doi.org/10.1093/gji/ggu276
- Hammond WC, Blewitt G, Kreemer C (2016) GPS Imaging of vertical land motion in California and Nevada. *J. Geophys. Res. Solid Earth* 121(10):7681–7703. https://doi.org/10.1002/2016JB013458
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
