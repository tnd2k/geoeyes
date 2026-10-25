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
    products/<project>_<track>_<first>_<last>_v<N>/   immutable product + report.pdf
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
