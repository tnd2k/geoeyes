# Skill: validate InSAR against GNSS and tie it to a terrestrial frame

> Compare an InSAR product with the daily GNSS positions of the Nevada Geodetic Laboratory (NGL, IGS20 frame), fit a
> rate (or ramp, or per-epoch) correction from the stations, check it by leave-one-out, and pass it on to products
> with no station by a tie to another product. Status: operational (v1; research steps G1, G2, G7 done). Last checked
> against the code: 2026-11-01 (`validation/tie.py` is new, not yet committed). CLI: `geoeyes gnss`, `geoeyes tie`.
> Web app: project → **Validation** → GNSS and Calibration panels; Explorer → **Calibrated** switch of a layer;
> In-depth analysis → Thematic analysis → "GNSS tie".

## 1. When to use it

- **Questions.** Do the InSAR series agree with GNSS in rate and in shape? Is the product's reference (a point or
  the scene mean) itself moving, and by how much? Can a product with no station inside be put on the same footing?
- **Decisions.** Publish the product as relative or tied to GNSS; set `[postprocess.hazard] gnss_tie = true`
  ([hazard-zoning.md](hazard-zoning.md)); export calibrated files.
- **Use it** when an NGL station inside the product recorded over its period, and the reference error is expected to
  be larger than the GNSS rate uncertainty (Mexico City: a 130 mm/yr reference bias).
- **Do not tie** when the motion near the stations is a few mm/yr over one year of data (Hanoi, §6.2 of the research
  note): the tie adds noise. Do not transfer a calibration across cities: its coefficient is the motion of one
  scene's reference (research note §7.1, §7.2).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| InSAR product | yes | `geoeyes run` ([insar-processing.md](insar-processing.md)) | `products/<id>/points.parquet` with `point_uid`, `lon`, `lat`, `los_e`, `los_n`, `los_u`, `vel_los_mm_yr`; `timeseries.parquet` (`point_uid`, `date`, `disp_mm`) | without `los_e/n/u` the comparison stops; LOS unit vector points ground → satellite |
| NGL station list | automatic | `https://geodesy.unr.edu/NGLStationPages/DataHoldings.txt` (no account, https only) | cache `<workspace>/cache/gnss/ngl/DataHoldings.txt`, refreshed after 7 days | stations **inside the product's lon/lat extent** with data overlapping its period |
| Equipment steps | automatic | `https://geodesy.unr.edu/NGLStationPages/steps.txt` | cache, 7 days | type 1 (equipment) used; earthquakes left to the jump detection |
| Daily positions | automatic | `https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/<SITE>.tenv3` | cache `<SITE>.tenv3`, refreshed after 1 day | IGS20 frame (NGL since August 2025) |
| MIDAS velocities | automatic | `https://geodesy.unr.edu/gps_timeseries/IGS20/midas/midas.IGS.txt` | cache, 7 days | used for `gnss_rate = "midas"` and reported always |
| Parameters | optional | – | `[validation.gnss]` in project.toml, or `geoeyes gnss --set key=value`, or the web form | §3.5 |
| Reference product for a tie | for `geoeyes tie` | another product over the same ground, any project of the workspace, ideally GNSS-calibrated itself | `--reference <project>/<product_id>` | at least 3 of its dates around the target period, at least 10 common cells |

When the network is down, cached files are used (with a warning); without a cache the run stops.

Checklist:

- [ ] `DataHoldings.txt` lists a station inside the product extent over its dates (the web panel shows the found
      stations, with the reason when one is not compared);
- [ ] the product has `los_e`, `los_n`, `los_u`;
- [ ] stations known to be bad (roof monument, moved antenna) put in `exclude`;
- [ ] for a tie: the reference product overlaps the target in space and its dates bracket the target's period.

## 3. Method

### 3.1 Stations and cleaning (`validation/gnss/ngl.py`)

Over the product period ±30 days, per station:

1. **Outliers:** per component, days beyond 5 robust sigmas (1.4826·MAD, floor 0.1 mm) from a 15-day running
   median are dropped.
2. **Segments:** breaks at NGL equipment changes and at day-to-day jumps larger than max(15 mm horizontal / 30 mm
   vertical, 5·σ); segments shorter than 30 days are dropped; fewer than 30 days in the window: station rejected.
3. **Re-joining:** one common linear trend and one offset per segment (keeps the rate of a moved antenna such as
   JNAV, Hanoi, 2025-10). Position taken at the end of the window.

### 3.2 Matching (`validation/gnss/compare.py`)

- InSAR: median series of the points within `radius_m` of the antenna, at least `min_points`; their spread is kept.
- GNSS: ENU averaged over ±`window_days` around each InSAR date.
- LOS unit vector **l** = median of the points' (`los_e`, `los_n`, `los_u`), normalised. Two projections:
  - `full`: d = e·l_e + n·l_n + u·l_u (includes plate motion in IGS20, e.g. ~31 mm/yr east in Hanoi);
  - `vertical` (default): d = u·l_u (horizontal motion taken as uniform over the scene, hence part of the InSAR
    reference).
- At least `min_epochs` shared dates; both series put on a common zero (their mean over the shared dates).
- Statistics per mode: OLS rates and standard errors, `rate_diff_mm_yr` = v_GNSS − v_InSAR, `rmse_mm`,
  `rmse_detrended_mm` (after removing the linear trend of the difference: agreement in shape), `corr` (of the two series after each one's own linear trend is removed; schema 2,
  2026-11-05), `corr_with_trend` (the former trend-dominated value); MIDAS rate
  projected the same way and `rate_diff_midas_mm_yr`.

### 3.3 Calibration (`calibration`)

With Δv_i = rate difference of station i (`window`: over the InSAR period; `midas`: against the MIDAS rate):

- `offset`: Δv = mean_i Δv_i, added to every point as Δv·t;
- `plane`: Δv = a + b·x + c·y (x, y in km from the product centre), needs ≥ 3 stations (else falls back to
  `offset` with a warning);
- `epoch`: c(t) = median over the stations of the series difference (common mode per date, interpolated over gaps,
  zero at the first date); one station carries its daily noise into every point (warning).

**Leave-one-out** (≥ 2 stations): each station predicted by the calibration fitted without it; reported
`loo_rms_before_mm_yr` and `loo_rms_after_mm_yr`. With one station: a warning that the tie cannot be checked.

The correction applied to a series is `correction(calib, dates, lon, lat)`: rate·t (with the plane terms), or the
epoch series.

### 3.4 Tie to another product (`validation/tie.py`)

For a target product with no station:

1. **Period:** the reference product's rate is fitted over its acquisitions from the last one ≤ the target's first
   date to the first one ≥ its last date (warning when it does not reach that far; at least 3 dates).
2. The reference's own calibration (`active_calibration`: GNSS, else its own tie) is added first.
3. **LOS:** both rates turned vertical, v / `los_u`.
4. **Space:** medians on `cell_m` cells (CLI `--cell`, default 100 m; web 20–1000 m), cells with ≥ `min_points` = 3
   points of each product; ≥ 10 common cells required.
5. Correction: Δv_vert = median over cells of (reference − target); LOS correction = Δv_vert × median `los_u` of the
   target. Spread = 1.4826·MAD. A gain (slope of target vs reference) is reported, not corrected.
6. Warnings: correlation < 0.5 ("the tie is uncertain"); |gain − 1| > 0.25.

The result has the keys of a GNSS calibration (`kind = "offset"`, `source = "tie"`). The calibration **applied** to
a product is its GNSS calibration if any, else its tie.

### 3.5 Parameters (`[validation.gnss]`)

| Key | Default | Meaning |
|---|---|---|
| `source` | `ngl` | only NGL |
| `radius_m` | 100 | InSAR points around the antenna (web: 50, 100, 200, 300) |
| `min_points` | 5 | points needed in the radius |
| `window_days` | 3 | GNSS days averaged around each InSAR date (±) |
| `min_epochs` | 6 | shared dates needed |
| `los_mode` | `vertical` | `vertical` \| `full` |
| `calibration` | `offset` | `offset` \| `plane` \| `epoch` |
| `gnss_rate` | `window` | `window` \| `midas` |
| `series` | `raw` | `raw` (`disp_mm`, use it for validation) \| `scn` (`disp_scn_mm`: spatially correlated noise removed, incl. the per-epoch scene ramp; trend kept — a diagnostic only: on short stacks it is close to the trend, so the shape check becomes circular); a product without `disp_scn_mm` falls back to `raw` with a warning. The column used is in `comparison.json` → `insar_column` |
| `stations`, `exclude` | all, none | site codes (upper case) |

Unknown keys are rejected (`n_rovers` from old configs is ignored).

## 4. Steps

1. **Compare.**
   ```
   geoeyes gnss <project> [--product ID] [--track ID] [--set radius_m=200] [--set calibration=plane]
   ```
   Web: project → **Validation** → GNSS panel → choose product and parameters → **Compare with GNSS** (background
   job). Time: seconds to a minute once the NGL files are cached (first run downloads one `tenv3` per station).
   Writes `analyses/gnss/<product>/comparison.json`, `series.npz`, `manifest.json`. CLI prints the stations
   compared and the calibration rate.
2. **Read** the station table (rates, RMSE, RMSE detrended, correlation, vs MIDAS), the chart per station (InSAR
   median, GNSS at the epochs, GNSS daily; `vertical` / `full`), the calibration line and the leave-one-out result.
3. **Tie a product with no station (optional).**
   ```
   geoeyes tie <project> --reference <ref_project>/<ref_product_id> [--product ID] [--cell 100]
   ```
   Web: Validation → Calibration panel → **Tie to another product** → choose the reference → **Tie** (a few seconds).
   Writes `analyses/tie/<product>/tie.json` and a manifest. **Remove the tie** deletes it.
4. **Use the calibration.**
   - map: Explorer → layer → **Calibrated** switch (layer cache `<product_id>@cal`, rebuilt when the calibration
     changes; product files untouched);
   - files: Calibration panel → **Write the calibrated GeoPackage + CSV** →
     `exports/<product>/<product>_calibrated.gpkg`, `.csv`, `.qml`;
   - hazard: `[postprocess.hazard] gnss_tie = true` or the "GNSS tie" box, then `geoeyes hazard`.

## 5. Outputs and how to read them

| File / field | Meaning |
|---|---|
| `comparison.json` → `stations[]` | per station: `used`, `reason` (why not), `n_points`, `median_distance_m`, `segments`, `jumps`, `outliers`, `los`, `gnss_rate_enu_mm_yr`, `full` / `vertical` statistics, `midas` |
| `…vertical.rate_diff_mm_yr` | GNSS − InSAR rate in LOS (mm/yr): the reference error at that station |
| `…rmse_detrended_mm`, `corr` | agreement in shape; 5–8 mm is the level seen for S1 PS medians against daily GNSS (research note §7.1) |
| `calibration` | `kind`, `los_mode`, `gnss_rate`, `stations`, `rate_coef`, `rate_offset_mm_yr`, `epoch_mm`, `leave_one_out`, `loo_rms_before/after_mm_yr`, `centre`, `lat0` |
| `warnings` | no station, one station, plane fallback, missing MIDAS |
| `series.npz` | per station: `insar`, `spread`, `gnss_full`, `gnss_vertical`, `day`, `enu_mm` |
| `tie.json` | `window`, `reference_dates`, `target_period`, `n_cells`, `corr`, `slope`, `intercept_mm_yr`, `spread_mm_yr`, `median_reference_mm_yr`, `median_target_mm_yr`, `calibration` (`rate_offset_mm_yr` LOS, `vertical_offset_mm_yr`, `reference_calibration`) |
| calibrated export | `vel_los_cal_mm_yr` next to `vel_los_mm_yr` (LS slope of the corrected series), `cal_source`, corrected `DYYYYMMDD` columns |

Signs: LOS positive toward the satellite. The `offset` correction equals the LOS rate of the product's own reference
as GNSS sees it: negative when the reference sinks (Mexico City S1, scene mean: −126.4 mm/yr, research note §7.3).

## 6. Quality checks

- At least one station `used`; reasons of the others understood.
- Shape agreement: `rmse_detrended_mm` near the InSAR noise and `corr` > 0.8 where the motion exceeds the noise
  (criterion G1). Mexico City MMX1: 5.3 mm, 0.96; Hanoi HUMG/JNAV: 0.27 / −0.33 (no common signal).
- Leave-one-out: `loo_rms_after_mm_yr` < `loo_rms_before_mm_yr`, with ≥ 3 stations (criterion G2). Hanoi offset:
  12.0 → 9.8; with MIDAS 4.1 → 8.1 (worse, do not tie). HCMC 2017–2019: 5.1 → 6.3 (worse).
- One station: plausible but unverified; say so wherever the tied product is used.
- `vertical` vs `full`: a large difference is plate motion (Hanoi: +16–19 mm/yr in LOS), not an InSAR error.
- Tie: `corr` ≥ 0.5, gain near 1, `spread_mm_yr` reported with the correction (Capella → S1 Mexico: 1,731 cells,
  0.888, gain 1.07, −109.0 mm/yr LOS, ±49.6 mm/yr; research note §7.3).
- After a hazard run with `gnss_tie`, rates fall in the published range (Mexico City: up to ~40 cm/yr).

## 7. Limits and pitfalls

- **Monument vs scatterers.** The median PS within 100 m may not move like the antenna (roof vs ground).
- **Optimistic GNSS sigmas.** White-noise rate errors; no flicker noise or annual terms in v1. A one-year rate
  depends on the phase of the seasonal signal.
- **Vertical tie** assumes negligible local horizontal motion; it breaks near the edges of subsidence bowls.
- **Re-joined segments** assume both monuments move alike.
- **`midas`** is wrong where the motion changed (MMX1: −364 mm/yr up in 2024 against −265 long-term).
- **`epoch`** with few stations injects daily GNSS noise into every point.
- **Stations are searched inside the product extent only** (no margin): a station just outside is not used.
- **Hazard `gnss_tie` reads only the GNSS comparison** of the product (`analyses/gnss/…`), not a tie: a product
  calibrated only by `geoeyes tie` cannot use `gnss_tie` (the run stops with "no GNSS calibration").
- A calibration is a property of one product and its reference; re-run after a new product version.

## 8. On a new area or sensor

- **First** list the NGL stations active over the period (DataHoldings first/last day). Many Vietnamese stations
  stopped in 2016–2021 (Hanoi: only HUMG, JNAV recent; HCMC: none for 2025–2026).
- **No station:** tie to a GNSS-calibrated product of the same ground and period (`geoeyes tie`), or use a stable
  `reference_bbox` in the hazard run; corner reflectors next to a new station ([corner-reflector.md](corner-reflector.md)).
- **Dense network (≥ 3 stations around the scene):** try `plane`; `epoch` only with 3–5 well-distributed stations.
- **Long series (≥ 2 years):** compare `window` and `midas`.
- **Carries over:** the method (vertical projection, segments, window rates, leave-one-out) and the error level
  (5–8 mm per epoch). **Does not carry over:** the calibration coefficient between cities.
- **Sensor:** nothing to change; the projection uses the product's own `los_e/n/u` (Capella left-looking and S1
  right-looking were compared this way in research note §7.3).

## 9. References

- Code: `src/geoeyes/validation/gnss/ngl.py`, `src/geoeyes/validation/gnss/compare.py`,
  `src/geoeyes/validation/tie.py`, `src/geoeyes/api/gnss.py`, `src/geoeyes/api/app.py` (`/tie`,
  `/export-calibrated`), `src/geoeyes/api/points.py`, `src/geoeyes/export/vector.py`, `src/geoeyes/hazard/assess.py`
  (`gnss_tie`), `webapp/src/components/Gnss.tsx`, `webapp/src/components/Calibration.tsx`; tests
  `tests/unit/validation/test_gnss.py`, `tests/unit/validation/test_tie.py`.
- Research: [../research/gnss-insar-calibration.md](../research/gnss-insar-calibration.md) (method §4, parameters §5,
  results §6–7), scripts [../research/code/gnss_transfer.py](../research/code/gnss_transfer.py) (transfer test §7.1)
  and [../research/code/gnss_g7.py](../research/code/gnss_g7.py) (HCMC 2017–2019, §7.2).
- Skills: [hazard-zoning.md](hazard-zoning.md), [corner-reflector.md](corner-reflector.md),
  [atmosphere.md](atmosphere.md), [ionosphere.md](ionosphere.md).
- Papers (DOIs in the research note §11): Blewitt, Hammond & Kreemer (2018) *Eos* 99; Blewitt et al. (2016) MIDAS,
  *JGR* 121; Neely et al. (2020) GInSAR, *IEEE TGRS* 58; Williams et al. (2004) *JGR* 109; Blewitt & Lavallée (2002)
  *JGR* 107; Wright et al. (2004) *GRL* 31; Farolfi et al. (2019) *EuJRS* 52.
