# Skill: tropospheric correction (ERA5, CERRA, GACOS)

> Choose the weather model that best removes the tropospheric delay (APS) from a point product, check it on the
> product without processing again, and apply it. Status: operational (ERA5, CERRA, GACOS); HRRR, CARRA and
> BARRA2 are listed only. Last checked against the code: 2026-11-01. CLI: `geoeyes atmosphere`,
> `geoeyes gacos-order`. Web app: project page → **Atmosphere** tab.

## 1. When to use it

- **Question.** Does a weather model explain the atmospheric part of the unwrapped phase better than the engine's
  linear phase–height fit, and which one?
- **Decision.** The value of `[atmosphere] method` (`none`, `era5`, `cerra`, `gacos`) and of `select`
  (`auto`, `all`) before the final run of a project.
- **Use it** after a first run of the `ps` engine (StaMPS type) has given a product, when velocities show
  patches or height-correlated signal, in mountains, in the wet season, or on short stacks.
- **Do not use it**
  - to fix ramps at 10–100 km along track on dusk Sentinel-1 passes at low latitude: that is the ionosphere
    ([ionosphere.md](ionosphere.md));
  - to remove turbulent cells of a few km: no model resolves them (§7);
  - on a `ps_lite` product with `geoeyes atmosphere`: the comparison needs `phase/unwrapped` in the `ps` run's
    `state.h5`. `ps_lite` itself does accept `[atmosphere] method` (§3.5).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| A product of the `ps` engine | yes, for `geoeyes atmosphere` | `geoeyes run <project>` ([insar-processing.md](insar-processing.md)) | `products/<id>/` whose manifest points to `ps_runs/<id>/state.h5` | needs `phase/unwrapped`, `phase/scla`, `phase/aps_linear`, `ps/bperp` |
| Acquisition time (UTC) of every date | yes | the stack attribute `sensing_mid_utc` (native builders), else the time stamps in the scene names (CSK, Capella, S1) | automatic; otherwise `[atmosphere.era5] fallback_utc = "HH:MM:SS"` | the fallback key lives under `era5` but is used by every model and by `gacos-order` |
| Copernicus CDS account and key (ERA5, CERRA) | for `era5`, `cerra` | register at https://cds.climate.copernicus.eu, copy the personal access token from the profile page | `~/.cdsapirc` (on Windows `C:\Users\<you>\.cdsapirc`): two lines `url: https://cds.climate.copernicus.eu/api` and `key: <token>` | accept the licence of **each** dataset once on the CDS website (`reanalysis-era5-pressure-levels`, `reanalysis-cerra-pressure-levels`); `geoeyes check` reports whether `~/.cdsapirc` exists |
| `cdsapi` Python package | for `era5`, `cerra` | in the `insar` environment | – | – |
| ERA5 cache | automatic | downloaded per (date, hour) | `<workspace>/cache/era5/<YYYYMMDD>/era5_pl_<YYYYMMDD>_<HH>00.nc`, or `[atmosphere.era5] cache` | a cached file that does not cover the area (another project) is downloaded again |
| CERRA cache | automatic | one whole-domain GRIB per analysis (~125 MB) | `<workspace>/cache/cerra/<YYYYMMDD>/cerra_pl_<YYYYMMDD>_<HH>00.grib`, pending CDS requests in `pending.json`; or `[atmosphere.cerra] cache` | shared by every project in Europe; published 1–2 months after the date |
| GACOS products | for `gacos` | order on http://www.gacos.net (no API): area, UTC time, dates from `geoeyes gacos-order`; delivered by e-mail | unpack into one folder: `<YYYYMMDD>.ztd` + `<YYYYMMDD>.ztd.rsc`, or `<YYYYMMDD>.ztd.tif`; set `[atmosphere.gacos] dir` | dates without a file keep the linear APS |
| `[aoi] bbox` | for `gacos-order` | project.toml | `[aoi] bbox = [W, S, E, N]` | the order area is the bbox + 0.1° |

Checklist:

- [ ] the project has a `ps` product (`geoeyes status <project>`);
- [ ] `geoeyes check` shows `~/.cdsapirc`, and both CDS licences are accepted (ERA5, CERRA);
- [ ] the dates are inside each model's coverage: ERA5 from 1940 up to ~6 days ago, CERRA from 1984-09 up to
      ~45 days ago and only over its domain, GACOS from 2016 (catalogue in `processing/atmosphere/models.py`);
- [ ] for GACOS: the folder holds one file per date and `[atmosphere.gacos] dir` points to it;
- [ ] stacks with no per-date times (old stacks) have `[atmosphere.era5] fallback_utc`.

## 3. Method

### 3.1 Zenith delay at each point (ERA5, CERRA)

Per model column (TRAIN `aps_weather_model_SAR.m`, Jolivet et al. 2011), in `era5/delays.py`:

1. temperature T, relative humidity RH and geopotential at every pressure level are interpolated bilinearly
   to the point; geopotential is converted to geometric height with a latitude-dependent gravity;
2. the profile is resampled every 15 m up to `Z_TOP` = 15 km;
3. water-vapour pressure e = RH/100 · e_sat(T) (water/ice blend between 250.16 and 273.16 K);
4. wet delay ZWD(h) = 10⁻⁶ ∫ₕ^15 km [(k₂ − k₁·R_d/R_v)·e/T + k₃·e/T²] dz, hydrostatic delay
   ZHD(h) = 10⁻⁶ · k₁·R_d/g · (P(h) − P(15 km)), with k₁ = 0.776, k₂ = 0.716, k₃ = 3.75·10³ (Pa, K),
   R_d = 287.05, R_v = 461.495;
5. both are resampled to 5 m and read at the point height (clipped at 0 m).

ERA5: 20 pressure levels (1000 to 100 hPa), area = the points' bbox ± `buffer_deg` (2.0°), hourly. CERRA:
19 levels (no 650/550 hPa, but 825 hPa), 5.5 km Lambert grid, 3-hourly, read on a window of the points ±3 cells.

**Time.** Each acquisition takes the two analyses that bracket it (1 h for ERA5, 3 h for CERRA), linearly
weighted; the second one is skipped when the acquisition is within about one minute of the first.

### 3.2 GACOS

The zenith total delay grid of the date is interpolated bilinearly at the points; 0 is no-data. No height
interpolation is needed: GACOS is already at the surface.

### 3.3 From zenith delay to interferometric phase

`slant.py`: slant = zenith / cos θ (θ = incidence, clipped to [0.05, π/2 − 0.01] rad);
φ_SAR = −4π/λ · slant; the interferogram k of the stack (reference r) gets φ_k = φ_SAR[r] − φ_SAR[k]. Components:
`[atmosphere.era5] component = total` (default), `hydro` or `wet` (ERA5 and CERRA).

`centre_weather` then adds, per interferogram, the constant that makes (unwrapped phase − model) zero-mean over
the points, as the intercept of the linear APS does. Without it the scene-wide offset of the model would shift every
point on that date.

### 3.4 Choosing per interferogram: `select`

Inside the `ps` engine (`processing/ps/aps.py`), during the second unwrapping pass (`[ps] subtr_tropo = "y"`,
default):

- the linear APS is a weighted least-squares line φ = a·h + b per interferogram (`[ps] aps_non_defo`: fit only on
  a polygon of non-deforming ground);
- `select = "auto"` (default): `choose_aps` takes the pass-1 unwrapped phase, removes a linear motion and a
  look-angle (DEM) error per point (hat matrix h), and for every interferogram compares the centred variance of the
  residual with the weather APS and with the linear APS, the others held at their current choice
  (coordinate descent, up to 5 rounds, on at most 200,000 points). The model is kept where its variance is lower;
  the linear APS elsewhere and wherever the model has no data;
- `select = "all"`: the model everywhere it has data, linear elsewhere.

The log prints one line per interferogram (`APS <date>: weather|linear (residual …, − weather …, − linear …
rad2)`), and `summary.json` of the run lists `aps.weather_ifgs`.

### 3.5 Other engines

- `ps_lite`: the same models; with `auto`, the model is kept per interferogram where it beats **no** APS (ps_lite
  has no linear APS); its own `[ps_lite] tropo` is a separate phase–height option of the unwrapper.
- Incremental updates (`processing/ps/update.py`): each new date takes the model if it covers more than 50 % of
  the points and its residual variance is lower than with the linear APS.

### 3.6 Trying the models on a product (`geoeyes atmosphere`)

`validation/atmosphere.py`, nothing is processed again:

1. reads `phase/unwrapped − phase/scla` of the `ps` run; samples at most `max_points` (200,000, `seed` 0) points
   with finite phase;
2. residual r = that phase minus a linear motion and a DEM error per point, centred per interferogram;
3. for `none`, `linear` and each model (`models = "auto"`: the catalogue's usable ones, plus `gacos` when
   `[atmosphere.gacos] dir` is set), the residual after removing the APS (centred as in the engine; linear where
   the model has no data);
4. per model: `std_mm` per interferogram (std of r × λ/4π), `median_std_mm`, `reduction_pct` = median over the
   interferograms of 100·(1 − σ²_model / σ²_none), `best_ifgs` (on how many it has the lowest std),
   `r_height` (correlation of the residual with height), `aps_std_mm`, `coverage`;
5. maps on a `grid` × `grid` (256) lon/lat grid: observed residual, APS and residual after each model.

A model that fails (no CDS key, no data) is reported in `errors` and does not stop the others.

## 4. Steps

1. **Check the access.** `geoeyes check <project>`: the line `~/.cdsapirc (Copernicus CDS key for ERA5)`.
2. **Look at the coverage.** Web app: project → **Atmosphere** → choose the product. The table lists every model
   with its area, dates and access (`downloaded by GeoEyes`, `ordered on the website…`, `outside its area`,
   `dates not published yet`, `not supported yet`), and a map of the CERRA domain.
3. **Order GACOS (optional, outside Europe).**
   ```
   geoeyes gacos-order <project> [--track ID]
   ```
   prints per track: area (N/S/W/E = bbox ± 0.1°), the mean UTC time of the dates, and the dates not yet in
   `[atmosphere.gacos] dir` (20 per block, to paste in the form). Enter them on http://www.gacos.net, unpack the
   e-mailed products into the folder, set `dir`. Delivery time depends on GACOS.
4. **Try the models.**
   ```
   geoeyes atmosphere <project> [--product ID] [--set models=["era5","cerra"]] [--set max_points=200000] [--set grid=256]
   ```
   or **Try the models** in the tab (runs in the background). Time: dominated by the downloads, one ERA5 file per
   date and analysis hour, two 125 MB CERRA files per date (each CDS run waits at most `max_wait_min` = 20 min in
   the queue; run again to collect the rest). Once cached, minutes. Writes
   `analyses/atmosphere/<product>/atmosphere.json` and `grids.npz`. The CLI prints per model
   `median_std_mm (reduction_pct %)`.
5. **Apply.** **Use** on a model row (sets `[atmosphere] method` and starts a run), or edit `project.toml`:
   ```toml
   [atmosphere]
   method = "era5"          # none | era5 | cerra | gacos
   select = "auto"
   era5 = { component = "total", buffer_deg = 2.0, workers = 4 }
   cerra = { max_wait_min = 20 }
   gacos = { dir = "D:/data/gacos/<project>_<track>" }
   ```
   then `geoeyes run <project>`. Steps 1–5 of the `ps` engine come from their checkpoints
   (`ps_runs/<id>/checkpoints/step<N>.json`), so only the unwrapping and later steps run. A new product version is
   written.

## 5. Outputs and how to read them

| File / field | Meaning |
|---|---|
| `atmosphere.json` → `models.<m>.median_std_mm` | median scatter (mm, LOS) of the residual left; lower is better |
| `models.<m>.reduction_pct` | median share of the residual variance removed vs no APS; negative = the model adds noise |
| `models.<m>.best_ifgs` | interferograms on which this model leaves the least scatter |
| `models.<m>.r_height` | per interferogram, correlation of the residual with height; close to 0 after a good model |
| `models.<m>.coverage` | share of (point, interferogram) values the model provides |
| `errors`, `catalogue`, `acquisition_utc`, `span_days` | failures, model coverage, times used, stack span |
| `grids.npz` (`obs`, `aps__<m>`, `res__<m>`) | maps per interferogram, mm, one colour scale for the three maps in the tab |
| run log / `ps_runs/<id>/summary.json` → `aps` | after applying: `method`, `select`, `weather_ifgs` (dates where the model was used) |

The tab marks the best model (lowest `median_std_mm`) and the one `in use`. A stack shorter than 90 days gets a
warning: a few mm of atmosphere become tens of mm/yr.

## 6. Quality checks

- `reduction_pct` of the chosen model > that of `linear`, and `best_ifgs` on a clear share of the interferograms.
- With `select = "auto"`, the share of interferograms that kept the model is reported. Recorded in the project
  comments: Mexico City S1 asc 078, ERA5 chosen for 5 of 15; Mexico City Capella, 10 of 17
  (`projects/mexico_s1`, `mexico_capella` `project.toml`).
- On the maps of a few interferograms: the model APS has the shape of the observed residual (height pattern, large
  patches); the residual after it is flatter.
- After the rerun: the velocity map loses patches that follow terrain or single dates; compare the two versions
  (Explorer, compare products) and against GNSS ([gnss-calibration.md](gnss-calibration.md)).
- No model rows with `coverage` far below 1 hidden behind a good median (dates missing from GACOS or CERRA).

## 7. Limits and pitfalls

- **Resolution.** A model removes the height-stratified delay and turbulence larger than a few of its cells. Cells
  of a few km (mountains, convection) are smaller than CERRA (5.5 km) and far smaller than ERA5 (~31 km). On
  Tenerife (ICEYE, 15 days, 2026-02), ±2.5 mm of such atmosphere reads as ±60 mm/yr ([guide](../guide/atmosphere.md)
  §5): a longer stack helps more than a finer model.
- **Tropical evening convection.** ERA5 misses it (Hanoi ascending, [ionosphere guide](../guide/ionosphere.md) §6);
  GACOS is the alternative.
- **CERRA latency and size.** 1–2 months after the date; ~125 MB per analysis; the CDS queue may need several runs
  (pending requests are kept in `pending.json`).
- **Wrong acquisition time.** A wrong `fallback_utc` puts the wrong analysis on every date.
- **Missing dates** fall back to the linear APS silently, except for a log warning: check `coverage`.
- `geoeyes atmosphere` reads the `ps` run behind the product; after a rerun it must be run again on the new product.
- The GACOS order form has no API: `gacos-order` only prints what to type.

## 8. On a new area or sensor

- **Europe, North Africa, Canaries, Azores:** try `cerra` against `era5`.
- **Elsewhere (Vietnam, Mexico):** `era5` (automatic) or `gacos` (ordered). No free model finer than ERA5 can be
  downloaded automatically for past dates outside Europe ([guide](../guide/atmosphere.md) §2).
- **Sensor:** nothing to change when the stack has `sensing_mid_utc` or time-stamped scene names; otherwise set
  `fallback_utc` to the overpass time.
- **Carries over:** `select = "auto"` (it protects against a model that is wrong on some dates), `component =
  "total"`, the caches (shared by every project of the workspace).
- **Local habits:** Hanoi S1 and Mexico City (S1, Capella) use `era5`; the Hanoi CSK project keeps `none`.

## 9. References

- Code: `src/geoeyes/processing/atmosphere/` (`models.py`, `weather.py`, `era5/`, `cerra.py`, `gacos.py`,
  `slant.py`, `times.py`), `src/geoeyes/processing/ps/aps.py`, `src/geoeyes/controller/phases/ps.py`
  (`weather_params`, legacy codes `a_e`, `a_eh`, `a_ew`, `a_gacos`), `src/geoeyes/validation/atmosphere.py`,
  `src/geoeyes/api/atmosphere.py`, `webapp/src/components/Atmosphere.tsx`, `src/geoeyes/config/schema.py`
  (`AtmosphereSection`).
- Guides: [../guide/atmosphere.md](../guide/atmosphere.md), [../guide/incremental.md](../guide/incremental.md) §7
  (ordering GACOS), [../guide/ionosphere.md](../guide/ionosphere.md).
- Skills: [insar-processing.md](insar-processing.md), [ionosphere.md](ionosphere.md),
  [gnss-calibration.md](gnss-calibration.md).
- Papers: Jolivet R, Grandin R, Lasserre C, Doin MP, Peltzer G (2011) Systematic InSAR tropospheric phase delay
  corrections from global meteorological reanalysis data. *GRL* 38:L17311. Yu C, Li Z, Penna NT, Crippa P (2018)
  Generic atmospheric correction model for InSAR observations (GACOS). *JGR Solid Earth* 123:9202–9222. Hersbach H
  et al. (2020) The ERA5 global reanalysis. *QJRMS* 146:1999–2049. Ridal M et al. (2024) CERRA, the Copernicus
  European Regional Reanalysis system. *QJRMS*. Bekaert DPS et al. (2015) Statistical comparison of InSAR
  tropospheric correction techniques (TRAIN). *RSE* 170:40–47.
