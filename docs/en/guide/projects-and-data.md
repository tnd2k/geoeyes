# Declaring a project and its data

A GeoEyes project is one folder with one file, `project.toml`. Everything the processing writes goes next to it;
raw imagery lives in the shared workspace archive.

## 1. Workspace

`GEOEYES_WORKSPACE` (in `.env` or the environment) points to the workspace root:

```
<workspace>/
  archive/<sensor>/<track_id>/...      raw scenes, shared by every project (see §3)
  cache/                               orbits, ERA5, ... (re-downloadable)
  projects/<name>/
    project.toml                       the declaration (the only file you write)
    geom/                              optional inputs: corner reflector list, set-up log
    stacks/<track>-ref<YYYYMMDD>/      coregistered stack (Zarr)
    ps_runs/<track>/                   point engine output (state, points, time series, QC figures)
    products/<project>_<track>_<first>_<last>_v<N>/   immutable product + report.pdf, report.json, indicators.json (§6)
    exports/<product>/                 GeoPackage (styled for QGIS), CSV
    validation/corner_reflector/       corner reflector reports
    runs/<run_id>/                     run record: manifest, log.jsonl, one log per phase
    .state/                            phase status (what is up to date)
```

`<track_id>` is `<sensor>-<asc|desc>[-<relative orbit, 3 digits>]`, e.g. `sentinel1-desc-091`, `cosmo_skymed-asc`,
`capella-asc`.

## 2. `project.toml`

Only a few lines are required; the rest comes from the sensor preset and the defaults. Minimal Sentinel-1
project (this is `projects/hanoi_s1`):

```toml
schema = "geoeyes.project/1"

[project]
name = "hanoi_s1"                 # = the folder name: a-z, 0-9, _ -
method = "psi"                    # psi | psds (phase linking + distributed scatterers) | ps_lite (Capella)

[aoi]
bbox = [105.76, 20.97, 105.89, 21.07]     # west, south, east, north (WGS84 degrees)

[[tracks]]
sensor = "sentinel1"              # sentinel1 | cosmo_skymed | capella
direction = "descending"          # ascending | descending
relative_orbit = 91               # Sentinel-1: required for the download

[acquire]
date_range = [2025-10-01, 2026-10-23]
max_per_month = 3                 # optional thinning: the first N acquisitions of each month

[atmosphere]
method = "era5"                   # none (linear APS) | era5 | gacos
```

`geoeyes check <project>` validates the file and the environment. The most used optional sections:

| Section | Keys | Notes |
|---|---|---|
| `[network]` | `reference` | `"auto"` (median date, then kept when new scenes arrive) or a date |
| `[stack]` | `dem` | `"srtm-1"` (default: SRTM 1" tiles in `~/.snap/auxdata/dem/SRTM 1Sec HGT`, missing tiles downloaded from the ESA mirror), `"copernicus-30"` (Copernicus GLO-30 from AWS open data into `<workspace>/cache/dem`; also above 60° N/S), a folder of `.hgt` tiles, or a GeoTIFF (EPSG:4326, EGM2008 heights) |
| `[[tracks]]` | `subswaths` | Sentinel-1: restrict to e.g. `["IW2"]` |
| `[phase_linking]` | `enabled`, `estimator`, `shp_test`, `half_window`, `gaussian_sigma` | `enabled = true` for long X-band stacks (COSMO-SkyMed); defaults `adaptive`, `ad` |
| `[selection]` | `da_threshold`, `ds_coherence_min` | PS amplitude dispersion; DS from phase linking |
| `[ps]` | StaMPS parameter names | e.g. `unwrap_grid_size` (10 m default), `max_topo_err`, `scla_deramp`, reference box `ref_lon`/`ref_lat` |
| `[atmosphere]` | `method`, `select`, `era5`, `gacos` | `select = "auto"`: weather model only where it beats the linear APS |
| `[export]` | `formats` | `["gpkg"]`, add `"csv"` |
| `[report]` | `copy_to` | also copy the PDF report to this folder |
| `[validation.corner_reflector]` | `points`, `setup`, `timezone`, `edge_m` | see §4 |

The full commented files of `projects/mexico_s1`, `mexico_capella` and `hanoi_csk` show every section with its
effective value.

## 3. Raw data per sensor

**Sentinel-1** — nothing to copy. With `[acquire] date_range` and the track's `relative_orbit`, phase `acquire`
finds the bursts covering the AOI on ASF and downloads them into `archive/sentinel1/<track_id>/<year>/<SLC>/`
(one folder per acquisition: `bursts.json`, `IWn_POL_<burst>.tiff`, the metadata XML). It needs a NASA Earthdata
token in `EARTHDATA_TOKEN`. Precise orbits (POEORB) are fetched automatically. Without `date_range` the archive is
used as it is.

**COSMO-SkyMed** — one folder per acquisition date holding the HDF5 product (SCS_B / SCS_U):

```
archive/cosmo_skymed/<track_id>/          or any folder named in [acquire] archive
  20111017/CSKS2_SCS_B_HI_03_HH_RA_SF_20111017225221_20111017225229.h5
  20111220/...
```

**Capella** — one folder per acquisition date holding the SLC GeoTIFF and its extended JSON metadata:

```
archive/capella/<track_id>/
  20240626/CAPELLA_C14_SM_SLC_HH_20240626150051_20240626150055.tif
           CAPELLA_C14_SM_SLC_HH_20240626150051_20240626150055_extended.json
```

Folder names must start with `YYYYMMDD`; at least 3 dates are needed (in practice 15+ for PS). To use data stored
elsewhere, set `[acquire] archive = "D:/path/to/folders"`.

## 4. Corner reflectors (optional, Sentinel-1)

```toml
[validation.corner_reflector]
points = "geom/points.csv"        # name, lat, lon, height (ellipsoidal m), edge_m
setup = "geom/cr_setup.csv"       # name, valid_from, face_azimuth_deg, base_tilt_deg, note  (local time)
timezone = "Asia/Ho_Chi_Minh"
```

`geoeyes cr-report <project>` measures every reflector on every acquisition of the archive (RCS, position,
coherence) and writes `validation/corner_reflector/<time>_<track>/cr_report.pdf`.

## 5. Running

```
geoeyes check  <project>          # configuration + environment
geoeyes plan   <project>          # what would run and why (new scenes, changed parameters)
geoeyes run    <project>          # acquire -> build_stack -> [phase_linking] -> ps -> build_product -> export -> report
geoeyes status <project>
```

Re-running is cheap: a phase runs only when its inputs or parameters changed. New acquisitions (on ASF, or new
date folders) are detected by `plan`; the stack is extended incrementally while the reference date is kept (a new
reference rebuilds it), and the later phases produce a new product version. Use `--force <phase>` to re-run a
phase, `--from` / `--to` / `--only` to select phases, `--track` for one track of a multi-track project.

**Skipping phases.** `--skip <phase>` (or `--skip <track>/<phase>`, repeatable) leaves a phase as it is: it is not
even checked (a skipped `acquire` does not search ASF) and its state does not make the following phases run. On
the project page, the switch at the top right of each phase card does the same for the runs started there (the
choice is remembered per project in the browser).

**Steps of the point engine.** The `ps` engine saves a checkpoint after each of its 8 steps
(`ps_runs/<track>/checkpoints/step<N>.pkl`): 1 candidates, 2 estimate gamma, 3 select, 4 weed, 5 correct phase,
6 unwrap pass 1, 7 unwrap pass 2, 8 velocity, SCN and outputs. A run that was stopped, killed or failed resumes after
the last finished step, as long as the stack and the parameters of that step and the steps before it are unchanged
(changing an unwrapping parameter keeps steps 1-5, for example). `--ps-from N` computes step N and the following ones
again; `--ps-to N` stops after step N (the phase is then *paused* and the next run continues from N + 1). The `ps`
card shows the saved steps and has the same two choices.

`[ps] unwrap_time_win = "auto"` sets the time window of the space-time unwrapping from the data: a quarter of the span, at least four sampling intervals, between 60 and 730 days (the value used is recorded in the run's `params.json`). The StaMPS default of 730 days suits stacks of several years; on a shorter stack the temporal model is almost a straight line, weakest at both ends of the series.

```bash
geoeyes run hcm_hist_des --skip acquire --skip build_stack          # straight to ps
geoeyes run hcm_hist_des --skip acquire --ps-from 6 --ps-to 6       # unwrap pass 1 again, then stop
```

## 6. Report

The `report` phase (or `geoeyes report <project> [--product <id>]`, at any time) writes three files into the product
folder: `report.pdf`, `report.json` (every value shown) and `indicators.json`. The PDF has two parts:

- **Part A — Assessment**, in plain language for city officials and residents: a one-page summary (what sinks or
  rises, where, how fast, how sure, what to do first, with the vertical velocity map); the **hot spots** (connected
  100 m cells moving faster than 5 mm/yr or twice the median error, each with its place, rate, trend — accelerating,
  slowing, seasonal or steady — and its series); the **impacts** read from the analyses already run on the product
  (`hazard`, `behaviour`, `buildings`, `risk`, `lines`, the flood inventory of `geoeyes floods`, the groundwater
  coupling of `hazard`); **how sure are we** (confidence, images, GNSS agreement of `geoeyes gnss`, processing checks,
  what to check on the ground); **recommendations** and the **indicator table**.
- **Part B — Technical appendix**: technical summary, data, method, quality checks, results, limitations, provenance,
  product files, references (sections B.1–B.6).

An analysis that has not been run is named in its section with the command that runs it, so a section is never
silently missing; run the analyses first, then `geoeyes report`, to have them in the report. Rates in Part A are
vertical (v_LOS / l_u, the ground assumed to move only up or down), negative = sinking; Part B keeps the line of
sight. Place names come from offline caches only (stack places, OSM line names of `geoeyes lines`, located flood
reports): the report makes no network request.

`indicators.json` (schema `geoeyes.indicators/1`) holds the same indicators in every report, for comparing reports
over time and as the input of a digital twin. Every key is always present; `value` is `null` when the analysis
behind it was not run (`source: "not assessed"`):

| Keys | Unit | |
|---|---|---|
| `area_monitored_km2`, `points_n`, `points_density_per_km2` | km², count, 1/km² | coverage |
| `period_first`, `period_last`, `period_days`, `images_n` | date, days, count | period |
| `vel_p01/p05/p50/p95/p99_mm_yr`, `vel_min/max_mm_yr`, `vel_std_p50_mm_yr` | mm/yr | point rates (`velocity_basis`) |
| `sinking_rate_max_mm_yr`, `area_sinking_over_{5,10,20}_mm_yr_km2`, `area_rising_over_{5,10,20}_mm_yr_km2` | mm/yr, km² | 100 m cells with ≥ 3 points |
| `hotspots_sinking_n`, `hotspots_rising_n`, `hotspot_threshold_mm_yr` | count, mm/yr | hot spots |
| `hazard_{subsidence,landslide}_{very_low…very_high}_km2`, `hazard_accelerating_cells_n`, `hazard_rain_coupled_cells_n` | km², count | `geoeyes hazard` |
| `groundwater_coupled_cells_n`, `groundwater_storage_trend_mm_yr` | count, mm/yr | `hazard` with GLDAS |
| `motion_{stable,steady,seasonal,speeding,slowing,onset,step}_cells_n` | count | `geoeyes behaviour` |
| `buildings_with_points_n`, `buildings_sinking_over_{5,10,20}_mm_yr_n`, `buildings_tilt_over_1_{500,300}_n` | count | `geoeyes buildings` |
| `buildings_risk_{very_low…very_high}_n` | count | `geoeyes risk` |
| `lines_km`, `lines_flagged_stations_n` | km, count | `geoeyes lines` |
| `flood_reports_n`, `flood_reports_in_sinking_n` | count | `geoeyes floods` |
| `gnss_stations_n`, `gnss_rate_diff_rms_mm_yr` | count, mm/yr | `geoeyes gnss` |
| `qc_review_n`, `confidence` | count, level | quality checks, confidence rules |

Each entry is `{"value", "unit", "description", "source"}`; the file also carries `velocity_basis` (`vertical` or
`los`), the product id, project, track and bounding box.
