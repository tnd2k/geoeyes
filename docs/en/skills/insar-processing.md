# Skill: InSAR processing, from a SAR stack to a velocity product

> Turn a stack of SAR acquisitions over an area into a versioned point product: LOS velocity, displacement time
> series, quality figures, GIS exports and a PDF report. Status: operational (Sentinel-1, COSMO-SkyMed, Capella,
> ICEYE, Umbra); TerraSAR-X and ALOS are declared but blocked (no stack builder yet). Last checked 2026-11-01.
> CLI: `geoeyes check / plan / run / status / report`. Web app: Projects → New project, then the project page
> (Pipeline, Stack, Runs, Settings tabs).

## 1. When to use it

- You have, or can download, at least 3 acquisitions of one track (in practice 15+ for persistent scatterers) and
  want the ground motion along the line of sight (LOS) at points, with a time series per point.
- It is the first skill of the chain: [stack-qc.md](stack-qc.md), atmosphere, GNSS calibration, hazard zoning and
  the other analyses all read its stack or its product.
- Not for: a single interferogram (see ../guide/learn-insar-pair.md), SBAS small-baseline networks (`method = "sbas"`
  is accepted by the schema but not implemented), TerraSAR-X or ALOS data (no native stack builder: `geoeyes plan`
  reports `build_stack` as *blocked*).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Workspace root | yes | any folder with space (stacks are tens of GB for S1) | `GEOEYES_WORKSPACE` in `.env` or the environment; or `--workspace` | holds `archive/`, `cache/`, `projects/` |
| Project declaration | yes | written by hand or by the web app (Projects → New project) | `<workspace>/projects/<name>/project.toml`, `schema = "geoeyes.project/1"` | `name`: a-z, 0-9, `_`, `-`, ≤ 64 chars, = folder name |
| Method | yes | `psi` (also `psds`, same engine) or `ps_lite` | `[project] method` | Capella must use `ps_lite`; `ps_lite` only for Capella and Umbra (schema check) |
| AOI | yes | bounding box in WGS84 degrees | `[aoi] bbox = [west, south, east, north]` | required by `acquire` and `build_stack`; `[aoi] file` is not used by the native builders |
| Track | yes | sensor and pass direction; S1 also the relative orbit | `[[tracks]] sensor`, `direction`, `relative_orbit` (S1), optional `subswaths = ["IW2"]` | `track_id` = `<sensor>-<asc|desc>[-<orbit 3 digits>]`, e.g. `sentinel1-desc-091`, `cosmo_skymed-asc` |
| Sentinel-1 bursts | yes (S1) | downloaded by phase `acquire` from ASF (burst SLC, VV) | `[acquire] date_range = [start, end]`; files into `archive/sentinel1/<track_id>/<year>/<SLC>/` (`bursts.json`, `IWn_VV_<i>.tiff`, XML) | needs `EARTHDATA_TOKEN`; `[acquire] max_per_month` (S1 preset: 2) keeps the first N dates of each month |
| COSMO-SkyMed scenes | yes (CSK) | provider delivery (no download) | one folder per date `YYYYMMDD/` holding `CSK*_SCS_*.h5` (SCS_B / SCS_U), under `archive/cosmo_skymed/<track_id>/` or `[acquire] archive` | folder name exactly 8 digits |
| Capella scenes | yes (Capella) | provider or open data ([opendata-stacks.md](opendata-stacks.md)) | `YYYYMMDD/CAPELLA_*_SLC_*.tif` + `*_extended.json` | whole scenes |
| ICEYE scenes | yes (ICEYE) | provider or open data | `YYYYMMDD/ICEYE_*_SLC.json` + the `.tif` SLC-COG of the same name | open data: `[acquire] opendata = "<stack id>"` fetches and cuts them |
| Umbra scenes | yes (Umbra) | open data or provider | `YYYYMMDD/*SICD*.nitf`, or a cut `*SICD*.tif` + `*SICD*.xml` | `ps_lite` only |
| DEM | yes (auto) | `[stack] dem`: `srtm-1` (default, SRTM 1" tiles in `~/.snap/auxdata/dem/SRTM 1Sec HGT`, missing tiles downloaded), `copernicus-30` (GLO-30 into `<workspace>/cache/dem`), `lidar-3dep` (US only, USGS lidar top surface inside GLO-30, needs `laspy[lazrs]`), a folder of `.hgt`, or a GeoTIFF | loaded over the AOI ± 0.2° | GeoTIFF: EPSG:4326, heights above EGM2008; `copernicus-30` above 60° N/S |
| Precise orbits (S1) | auto | POEORB fetched into `<workspace>/cache/orbits` | none to place | a date built with RESORB / annotation orbits is re-coregistered once its POEORB exists (checked for dates ≥ 15 days old) |
| Weather model | optional | ERA5 (`~/.cdsapirc`), CERRA (Europe), GACOS (ordered by hand) | `[atmosphere] method = "era5" / "cerra" / "gacos"`, `[atmosphere.gacos] dir` | default `none` = linear phase-height APS; see atmosphere skill |
| Reference area | optional | known stable ground | `ps`: `[ps] ref_lon = [min, max]`, `ref_lat = [min, max]` or `ref_centre_lonlat` + `ref_radius`; `ps_lite`: `[ps_lite] ref_latlon`, `ref_radius_m` | default `ps`: every point (scene mean); `ps_lite`: chosen automatically from the amplitude dispersion |

Checklist before `geoeyes run`:

- [ ] `geoeyes check <project>` ends with `all checks passed` (packages, workspace, configuration, nothing *blocked*).
- [ ] S1: `relative_orbit` set, `EARTHDATA_TOKEN` available, `date_range` covers the period wanted.
- [ ] Commercial data: every date folder named `YYYYMMDD` and holding the files above; at least 3 dates inside
      `date_range`; the `direction` of `[[tracks]]` matches the reference scene (the build stops otherwise).
- [ ] AOI inside the footprint of every date (S1: the bursts are chosen on the reference acquisition).
- [ ] Phase linking wanted? `[phase_linking] enabled = true` (COSMO-SkyMed and ICEYE presets already set it).
- [ ] Disk: S1 stack of 26 dates over a city ≈ tens of GB; keep `stacks/` on a fast disk.

## 3. Method

**Pipeline.** Per track: `acquire` → `build_stack` → `phase_linking` (optional) → `ps` → `build_product` →
`export` → `report` (`controller/pipeline.py`). Each phase has a fingerprint of its inputs and parameters; `plan`
marks it *up-to-date* when the fingerprint is unchanged and its outputs exist, and a phase that runs makes every
following phase run. The effective configuration is the sensor preset (`config/presets/<sensor>.toml`, sensor of
the first track) deep-merged under `project.toml`.

**acquire.** S1 only (or an open-data stack). Enabled when the track is Sentinel-1, `[acquire] archive` is empty
and `date_range` is set. It searches ASF for the bursts covering the AOI on `relative_orbit`, thins them with
`max_per_month`, and downloads the missing ones. Offline, the catalogue of the last run is reused.

**build_stack** (native engine; `[stack] engine = "snap"` is refused).

- Reference date: `[network] reference = "auto"` takes the median date at the first build and keeps it while it is
  still an acquisition (Umbra: the date whose incidence keeps most scenes within 3°). Stack id
  `<track_id>-ref<YYYYMMDD>`, store `stacks/<stack_id>/stack.zarr`.
- Sentinel-1 (`s1_stack.py`): bursts of the reference acquisition intersecting the AOI + 0.01°, geometric
  coregistration with POEORB and the DEM, enhanced spectral diversity (always on; the schema key `[stack] esd` is
  not read), phase steps at subswath seams removed, optional split-spectrum ionosphere (`[stack] ionosphere =
  "split_spectrum"`, `ionosphere_model = "local"`, `ionosphere_smooth_m = 10000`).
- Stripmap / spotlight (`stripmap.py`: COSMO-SkyMed, Capella, ICEYE): geometric coregistration from orbits + DEM,
  then the residual offset from amplitude phase correlation on 256-px tiles (median, iterative 3-MAD rejection),
  one constant per date (`coreg_model = "constant"`) or a plane in height, line and sample (`"terrain"`). Dates
  are left out when pass or look side differ, heading differs by > 2°, near range by > 3 % (other beam), or (ICEYE)
  PRF by > 0.5 %.
- SICD (`sicd_stack.py`, Umbra): coarse integer offset (log-amplitude phase correlation on 9 windows of 2048 px,
  ±1024 px) then the residual offset; dates left out for another side / pass, incidence > 3° from the reference, or
  a non-zero `DeltaKCOAPoly`.
- The store holds `slc` flattened (geometric phase removed), `bperp`, `kh` (height sensitivity, rad/m), the
  geometry (`geometry_incidence`, `geometry_slant_range`, ...). For every sensor but S1, a stack check runs at the
  end ([stack-qc.md](stack-qc.md)).

**phase_linking** (`[phase_linking] enabled = true`; the method name `psds` alone does not switch it on).

- Homogeneous neighbours (SHP) in a window of `(2·half_window+1)²` pixels, `half_window = [7, 7]`: two-sample
  Anderson-Darling test on the amplitude series (`shp_test = "ad"`, `shp_alpha = 0.05`; `"ks"` also available).
- Pixels with ≥ `min_shp = 25` SHP and amplitude std/mean > `ps_da_max = 0.25` are linked; the others (PS) keep
  their SLC. Coherence matrix over the SHP, normalised by its diagonal.
- `estimator = "adaptive"`: EMI where the mean off-diagonal |C| > `adaptive_coherence_threshold = 0.6`, PTA
  (phase triangulation) elsewhere; `evd`, `emi`, `pta`/`mle` selectable; `psds`, `comsar`, `shp_test = "bws"` and
  `nlinsar` are not ported (the phase is blocked).
- Temporal coherence γ = Re Σ_{i<j} e^{j(arg C_ij − θ_i + θ_j)} / (n(n−1)/2), stored as `pl_temporal_coherence`;
  `slc_linked[k] = |slc[k]| · e^{j(arg slc[ref] + θ_k)}`.
- Optional Gaussian post-filter of each interferogram, `gaussian_sigma` pixels (0 = off; CSK and ICEYE presets 1.5),
  on the linked pixels only (`gaussian_scope = "linked"`).
- Optional `store_pairs = [["YYYY-MM-DD", "YYYY-MM-DD"], ...]`: |C_ij| of those date pairs over the SHP family,
  kept as `pl_pair_coherence` (`pl_pair`, y, x) with the attribute `pairs`, NaN where a pixel is not linked. It is
  formed in the same pass, so a change test over distributed scatterers needs no second SHP pass (the landslide
  study's `verify` reads it; without it, `runner.pair_coherence` forms the SHP again).

**ps engine** (`method = "psi"` or `"psds"`; StaMPS-type, `processing/ps/`, parameters `[ps]` with StaMPS names,
defaults in `processing/ps/params.py`). Eight checkpointed steps:

1. Candidates: amplitudes calibrated per date by the scene mean, D_A = sqrt(k·Σa²/(Σa)² − 1) ≤
   `[selection] da_threshold` (0.42), mean amplitude above an Otsu floor (water out). With phase linking and
   `[selection] ds_coherence_min` set (CSK / ICEYE presets 0.7): plus, per `ds_cell × ds_cell` block (3), the
   pixel of highest phase-linking γ.
2. Estimate γ (CLAP filter `clap_win = 16`, grid `filter_grid_size = 10` m, topographic error up to
   `max_topo_err = 20` m; `"auto"` = median height of ambiguity λ·R·sinθ / (2|B⊥|) divided by 4).
3. Select (`select_method = "PERCENT"`, `percent_rand = 80`, or `"DENSITY"` with `density_rand`).
4. Weed (`weed_standard_dev = 1.0`, `weed_max_noise = inf`, `weed_adjacent_keep_per_group = 1`).
5. Correct the phase (look-angle error, master term).
6. Unwrap pass 1 on a grid of `unwrap_grid_size = 10` m (Gaussian prefilter `unwrap_grid_filter = "gaussian"`,
   `unwrap_gold_n_win = 16`), space-time model with `unwrap_time_win = 730` days (`"auto"`: span / 4, at least 4
   sampling intervals, 60–730 days), refined IRLS (`unwrap_irls_iter = 50`, `unwrap_irls_target_rms = 0.01`,
   `unwrap_irls_epsilon = 0.001`).
   Since 2026-11-06 every edge of the grid is first unwrapped in time by its linear rate (`unwrap_edge_velocity =
   "y"`, periodogram up to `unwrap_max_edge_velocity = 100` mm/yr) and the IRLS takes the cycle count of each grid
   step from that model (`unwrap_model_cycles = "y"`, as the SNAPHU cost offsets of StaMPS). Before, the model was
   fitted to the wrapped phase and the IRLS followed the wrapped gradients: a cluster whose phase difference to its
   neighbours passed π (20 mm/yr: after ~250 days on S1) was a whole cycle off at the epochs far from the master.
   `legacy_quirks = "y"` turns both off.
   Since 2026-11-07 (HCMC Binh Chanh vs SARPROZ): the Gaussian grid prefilter has σ in metres
   (`unwrap_grid_filter_sigma = "auto"` = (`unwrap_gold_n_win` // 8) × 10 m, the legacy filter at a 10 m grid; the
   legacy σ in cells was 100 m at a 50 m grid and flattened the subsidence); and with ≥ 40 interferograms
   (`unwrap_ps_rate = "auto"`) a linear rate per PS from the PS network (Delaunay arcs ≤ 500 m, periodogram, L1
   integration) is removed before the grid and added back, so a road or canal bank faster than its cell keeps its
   cycles. On flat deltas consider `subtr_tropo = "n"` ([aps-selection.md](../research/aps-selection.md)).
7. Unwrap pass 2 (`subtr_tropo = "y"`) with the pass-1 smoothed look-angle error (`scla_deramp`) and the APS
   removed: the linear phase-height APS (fitted inside `aps_non_defo` when given), or the weather model, per
   interferogram where it explains the pass-1 residual better (`[atmosphere] select = "auto"`).
   `scla_deramp`: `"n"` keeps the ramps, `"y"` removes the whole plane / quadratic of every interferogram,
   `"auto"` (under test, [ramp selection](../research/ramp-selection.md)) removes the part that changes between
   acquisitions and the steady trend only where a stable background anchors one plane over the whole frame
   (`deramp_non_defo` = a user's stable polygon); its decision is in the manifest (`ramp`) and `figures/ramp.png`.
8. Velocity and spatially correlated noise (`scn_time_win = 365` days, `scn_wavelength = 100` m,
   `scn_time_fit = "linear"`); displacement d = −φ·λ/4π, then referenced to `ref_lon/ref_lat` or the scene mean.

Experimental: `unwrap_align_constant = "y"` aligns the IRLS constant before snapping to the wrapped phase (fixes
one-cycle region slips of interferograms with a mean phase near ±π, Tenerife ICEYE). Default `"n"`: it changed the
validated CSK Hanoi result (89.6 % of points matched, `params.py`), and it is to be assessed against SNAP+StaMPS
before wider use. Note that the ICEYE preset sets it to `"y"`.

**ps_lite** (`method = "ps_lite"`, Capella and Umbra, ADR-020; `[ps_lite]`). D_A ≤ `da_max = 0.4` and range
spectral diversity ≤ `sd_max = 0.45` above an amplitude floor (`amp_floor_pct = 10`), best PS per `ps_cell =
[4, 6]` pixels; its own reference epoch (`ref_date = "auto"`: the epoch with the smallest longest baseline); per
interferogram two-pass refined IRLS on a `uw_cell = [16, 24]`-pixel grid with Goldstein filtering (`gs_alpha =
0.8`, `gs_win = 32`) and a height-error periodogram between the passes; reference area of `ref_radius_m = 200` m;
weighted least squares per PS: φ_k = s·4π/λ·v·t_k + s·kh_k·dh + c + APS_k, APS = residual low-passed with a
Gaussian of `aps_sigma_m = 1000` m; interferograms with phase std > `ifg_std_max = 1.5` rad dropped; PS kept when
γ ≥ `tcoh_min = 0.7` and phase std ≤ `phase_std_max = 0.8` rad. It does not read `[ps]` (no `unwrap_grid_size`,
no `unwrap_align_constant`); fewer than 100 PS stops the run.

**build_product.** A new immutable folder `products/<project>_<track>_<first>_<last>_v<N>/` per run, the same
schema for every sensor and engine (`products/schema.py`): LOS velocity positive toward the satellite, time series
zero at each point's first date, seasonal amplitude, residual sigma, LOS unit vector.

**export.** `[export] formats` (default `["gpkg", "pmtiles"]`; also `csv`, `kmz`, `3dtiles`): GeoPackage with one
`DYYYYMMDD` column per date and the QGIS style embedded, plus `<product>.qml` always. Style: Pretty Breaks, 10
classes over the full min–max (no clipping), `jet_r`, circles without stroke, sized in metres from the point
spacing (`export/styles.py`).

## 4. Steps

1. **Workspace.** Set `GEOEYES_WORKSPACE` (copy `.env.example` to `.env`); S1: `EARTHDATA_TOKEN`. Once.
2. **Declare the project.** Write `projects/<name>/project.toml` (minimal S1 example in
   ../guide/projects-and-data.md §2), or web app Projects → *New project* (name, method, sensor, AOI drawn on the
   map, S1 track search). Commercial data: put the date folders in `archive/<sensor>/<track_id>/`.
3. **Check.** `geoeyes check <name>` (seconds): environment, configuration, blocked phases, `~/.cdsapirc` or the
   GACOS folder when a weather model is chosen.
4. **Plan.** `geoeyes plan <name>` (seconds; S1 queries ASF): one line per track and phase, `run` / `up-to-date` /
   `disabled` / `blocked` and why ("2 new scene(s) …; incremental: 26 coregistered date(s) kept").
5. **Run.** `geoeyes run <name>` (or the *Run* button on the Pipeline tab). Order of magnitude (from
   ../guide/incremental.md, Hanoi S1 ascending 128, 26 dates, ~730,000 points, split-spectrum ionosphere):
   `build_stack` 71 min, `ps` 12 min, `build_product` + `export` + `report` 2 min; Capella Mexico City, 18 dates:
   stack ~5 min (docs/en/refactor/TODO.md). Writes `stacks/`, `ps_runs/<track_id>/`, `products/<id>/`,
   `exports/<id>/`, `runs/<run_id>/` (manifest, `log.jsonl`, one log per phase), `.state/state.json`.
6. **Follow.** `geoeyes status <name>`: status and duration per phase, the last 5 runs, locks.
7. **Check the stack** before trusting the points: `geoeyes stack-qc <name>` or the Stack tab
   ([stack-qc.md](stack-qc.md)).
8. **Partial re-runs.** `--force PHASE`, `--from` / `--to` / `--only PHASE`, `--track ID`, `--skip PHASE` or
   `--skip TRACK/PHASE` (left as it is, not even checked). Engine steps: `--ps-from N` recomputes step N and later,
   `--ps-to N` stops after step N (phase *paused*); e.g. `geoeyes run hcm_hist_des --skip acquire --ps-from 6
   --ps-to 6` redoes unwrap pass 1 only. Changing an unwrapping parameter reuses steps 1–5 automatically.
9. **Report.** Written by the `report` phase; `geoeyes report <name> [--product ID]` rebuilds it after more
   analyses (`report.pdf`, `report.json`, `indicators.json` in the product folder).

## 5. Outputs and how to read them

| File | Content |
|---|---|
| `products/<id>/points.parquet` | GeoParquet, one row per point: `point_uid` (`<track>:<geohash>:<height>`), `lon`, `lat`, `height_m`, `type` (PS / DS), `vel_los_mm_yr` (+ toward the satellite), `vel_std_mm_yr`, `acc_los_mm_yr2`, `temporal_coherence`, `amp_dispersion`, `dem_err_m`, `seasonal_amp_mm`, `seasonal_phase_day`, `fit_rmse_mm`, `residual_sigma_mm`, `los_e/n/u`, `incidence_deg`, `heading_deg` |
| `products/<id>/timeseries.parquet` | long format `point_uid`, `date`, `disp_mm` (and the SCN-removed series), 0 at each point's first date |
| `products/<id>/rasters/velocity.tif`, `ps_density.tif` | COG: mean velocity and points per cell |
| `products/<id>/item.json`, `manifest.json` | STAC item (bbox, dates, metrics `vel_min/max/p02/median/p98_mm_yr`, `n_points`, `n_ds`), provenance |
| `products/<id>/report.pdf`, `report.json`, `indicators.json` | Part A assessment (vertical rates v_LOS / l_u), Part B technical appendix; indicators schema `geoeyes.indicators/1` |
| `ps_runs/<track_id>/` | engine state `state.h5`, `params.json` (effective values, `"auto"` resolved), `figures/*.png`, `checkpoints/step<N>.pkl` (ps); `pairs.parquet` (ps_lite) |
| `exports/<id>/` | `<id>.gpkg` (layer `points`, styled), `<id>.qml`, optional `.csv`, `.pmtiles`, `.kmz`, `3dtiles/` |

A negative `vel_los_mm_yr` is motion away from the satellite (subsidence for mostly vertical motion). Show the
true min–max of the velocity: the QGIS style and the engine figures (`velocity.png`, `velocity_scn.png`) use the
full range on purpose; do not clip colour scales to P2–P98.

## 6. Quality checks

- Stack: offsets < 0.1 px, coherence and amplitude correlation consistent across dates ([stack-qc.md](stack-qc.md)).
- `ps_runs/<track_id>/figures/`: velocity map with the reference points, the SCN-removed map on the same scale, APS
  and phase noise per interferogram; an interferogram with a noise far above the others points to a bad date.
- `ps_lite`: `pairs.parquet` (`unwrap_rms`, `islands`, `phase_std_rad`, `used`); dropped interferograms are logged.
- Product metrics in `item.json`: points count, share of DS, median coherence, `vel_std_median_mm_yr`; stable
  ground (reference area, known stable buildings) near 0 mm/yr.
- Unwrapping errors: patches offset by one cycle (λ/2 per date: 28 mm C-band, 15.5 mm X-band) in the time series,
  or blocks of opposite sign joined by long arcs (the HCMC case below).
- Report Part A *how sure are we*; independent check with GNSS (gnss-calibration skill) or a second track.

## 7. Limits and pitfalls

- TerraSAR-X, ALOS: presets only, `build_stack` blocked. `method = "sbas"` / `"comsar"`: same `ps` engine as `psi`.
- Schema keys accepted but not read by the native pipeline: `[network] max_perp_m` (the web Settings form labels it
  "Largest perpendicular baseline kept", but no date is dropped on it), `extent_min_ratio`, `[network.sbas]`,
  `[stack] geometry`, `esd`, `multilook`, `merge_subswaths*`, `byteswap`, `reestimate`, `renew`, `[selection]
  robust_da`, `forced_points`, `mask`, `water_mask`, `[phase_linking] ministack_size`, `[compute] memory_gb`,
  `[pipeline] disabled`.
- `[compute] backend` (`auto` | `numpy` | `cupy`; env `GEOEYES_COMPUTE_BACKEND` overrides): GPU only for the ps
  `topofit` (steps 2-3) and `clap_at_points` (step 3) so far (ADR-014); everything else runs on the CPU.
- A new reference date, AOI, DEM or subswath set re-coregisters every date (another stack folder).
- `max_per_month` on a shared archive: the dates chosen by this project's `acquire` win.
- X-band, small heights of ambiguity: use `max_topo_err = "auto"`; Umbra baselines of km give ambiguities below a
  metre: `lidar-3dep` where available, small AOIs on structures.
- A too-fine unwrapping grid over a sparse area joins blocks by long noisy arcs (HCMC: whole cycles off at 10 m).
- `geoeyes run` takes a project lock per track; a second run on the same tracks is refused.

## 8. On a new area or sensor

Change: `[aoi] bbox`, `[[tracks]]`, `date_range`, the reference area if stable ground is known, the DEM where SRTM is
poor (steep relief, > 60° latitude, US lidar). Keep the sensor preset unless a test says otherwise.

Known habits and decisions:

- `unwrap_grid_size = 10` m (now the default; the StaMPS 200 m aliased fast subsidence: S1 Mexico vs Capella r 0.64
  → 0.86, `params.py`). Exception, HCMC (`hcm_hist_des`): `unwrap_grid_size = 50` with `filter_grid_size = 50`,
  `percent_rand = 50`; at 10 m the west and east blocks were joined by long noisy arcs with whole cycles off;
  `unwrap_time_win = "auto"` changed nothing there and the align option moved the slips (project comments,
  2026-10-31 / 11-01).
- Phase linking: `shp_test = "ad"`, `estimator = "adaptive"` (defaults).
- COSMO-SkyMed chain: phase linking + Gaussian post-filter (`gaussian_sigma = 1.5`), nothing else: no wavelet, no
  FAMM, no Goldstein grid filter. The legacy CSK additions (`dem_error_ambiguity = "y"`, `select_nr_scaling =
  "population"`, `unwrap_grid_filter = "goldstein"`) made the Hanoi stack worse (fit RMSE 4.12 → 4.81 mm; velocity
  scatter 1.51 → 1.67 mm/yr; preset comment, 2026-10-23 ablation) and stay off.
- `unwrap_align_constant`: experimental, not a default for `ps` until compared with SNAP+StaMPS, ICEYE preset
  included (set `"y"` in a project to try it).
- Sentinel-1 dusk passes near the equatorial anomaly (Hanoi ascending 18:06 local): `[stack] ionosphere =
  "split_spectrum"`.
- Display: true min–max of VLOS; QGIS Pretty Breaks 10 classes, `jet_r`, no stroke.

## 9. References

- Code: `src/geoeyes/controller/pipeline.py`, `controller/phases/{acquire,build_stack,phase_linking,ps}.py`,
  `processing/stack/native/{s1_stack,stripmap,sicd_stack}.py`, `processing/phase_linking/{runner,estimators,shp}.py`,
  `processing/ps/{runner,params,candidates}.py`, `processing/ps_lite/{runner,ps,unwrap,invert}.py`,
  `products/{builder,schema}.py`, `export/{vector,styles}.py`, `config/schema.py`, `config/presets/*.toml`,
  `cli/main.py`.
- Guides: ../guide/projects-and-data.md, ../guide/incremental.md, ../guide/atmosphere.md, ../guide/ionosphere.md,
  ../guide/opendata.md. Architecture: ../architecture/decisions.md (ADR-005, -020, -023, -028, -029).
- Skills: [stack-qc.md](stack-qc.md), [opendata-stacks.md](opendata-stacks.md),
  [incremental-monitoring.md](incremental-monitoring.md), [atmosphere.md](atmosphere.md),
  [gnss-calibration.md](gnss-calibration.md).
- Papers: Hooper et al. 2004, 2007 (StaMPS); Ferretti et al. 2011 (SqueeSAR, SHP and phase linking); Ansari et al.
  2018 (EMI); Scholz & Stephens 1987 (k-sample Anderson-Darling).
