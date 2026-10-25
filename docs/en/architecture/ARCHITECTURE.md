# GeoEyes — Target architecture

> Status: **Design v0.1 (2026-10-21)** — not yet implemented.
> Related documents: [`decisions.md`](decisions.md) (ADR) · [`migration-map.md`](migration-map.md) (old file → new) · [`../refactor/TODO.md`](../refactor/TODO.md) (progress).
>
> This document describes the **destination**. Every refactor must bring the code to the exact location and the exact contract (interface) described here. If reality forces a deviation, update this document + add an ADR first, and only then change the code.

---

## Table of contents

1. [Goals & scope](#1-goals--scope)
2. [Current state summary](#2-current-state-summary)
3. [Architecture principles](#3-architecture-principles)
4. [Repo & package structure](#4-repo--package-structure)
5. [Domain model](#5-domain-model)
6. [Controller — Processing Phase Controller](#6-controller--processing-phase-controller)
7. [Sensors](#7-sensors)
8. [Processing — core processing chain](#8-processing--core-processing-chain)
9. [Post-processing](#9-post-processing)
10. [Storage: formats & schema](#10-storage-formats--schema)
11. [Workspace, long-term storage & retrieval](#11-workspace-long-term-storage--retrieval)
12. [Logging & observability](#12-logging--observability)
13. [Scientific report (PDF)](#13-scientific-report-pdf)
14. [Configuration](#14-configuration)
15. [Applications: CLI, QGIS](#15-applications-cli-qgis-gui-dropped-webapp-rebuilt-later)
16. [Testing & quality](#16-testing--quality)
17. [Dependencies](#17-dependencies)
18. [AI readiness](#18-ai-readiness)
19. [Migration roadmap](#19-migration-roadmap)
20. [Glossary](#20-glossary)

---

## 1. Goals & scope

**GeoEyes** is an end-to-end InSAR time-series processing system (PSI / SBAS / PS-DS): from raw SAR images to quality-controlled deformation products, long-term storage and scientific reports.

### Goals

| # | Goal | Measure |
|---|---|---|
| G1 | A single `geoeyes` package, clearly layered, no `sys.path` hacks | 0 `sys.path.insert/append`; layer dependencies checked with `import-linter` |
| G2 | One implementation per algorithm; sensor differences live in `SensorProfile` | No more per-sensor duplicate files (`flow.py` ×4, `synth_sbas_pairs.py` ×3, tomo ×2…) |
| G3 | Process the sensor's native format directly, SNAP GPT not mandatory | The `native` backend is the default; `snap` is only a transitional backend |
| G4 | Modern, schema-based, self-describing storage formats | Zarr / HDF5-schema / GeoParquet / COG / STAC; no more `.h5` masquerading as `.mat` |
| G5 | Long-term storage, retrievable by space/time/attributes | STAC catalog + DuckDB index; immutable products with checksums |
| G6 | Reproducible | Every product has a manifest: inputs, parameters, code version, hash |
| G7 | PDF report with scientific substance, so that outsiders can understand the workflow & results | Report structure §13 |
| G8 | Complete, structured logs | No `print` in the library; JSONL log per run |

### Required sensors

Sentinel-1 (TOPS IW) · COSMO-SkyMed (Stripmap/Spotlight, CSG) · **ALOS-PALSAR** (L-band; ALOS-2 first, ALOS-4/ALOS-1 later — ADR-013) · Capella (Spotlight/Stripmap) · TerraSAR-X/TanDEM-X.

Language of code, logs, documentation and reports: **English** (ADR-015).

### Out of scope (removed)

- Publishing to PostGIS / GeoServer (`to_postgis`, `to_geoserver`, `_publish_*`, `publish_status.json`, `dbschema`, `map_id`) — ADR-007.
- Teams / Telegram / SMTP / webhook notifications (`modules/ops/notify.py`) — ADR-008. Replaced by complete logging.
- All `vinsar` and `VINSAR_*` labels and the former organisation's name — ADR-001.

---

## 2. Current state summary

Only the points that shape the design are recorded here (per-file details: [`migration-map.md`](migration-map.md)).

| Area | Current state | Design consequence |
|---|---|---|
| Orchestration | `vinsar.py` ~700 lines in one function; stages hard-wired with `if control[...]`; phase linking is inserted in the middle of snap2stamps by **temporarily overwriting `control.json` + backup** | A real phase DAG is needed (§6) |
| Preprocessing | `modules/snap2stamps/{s1,tsx,csk,capella}`: calls `gpt` as a subprocess with graph XML and placeholder substitution; BEAM-DIMAP intermediates (`process/` ~70 GB for 1 project) | The `stack` backend has 2 engines: `snap` (temporary) and `native` (§8.3) |
| Reading native data | Already exists in scattered places: TSX annotation XML, CSK HDF5 attrs (h5py), Capella extended JSON, S1 burst (stsa); 4 different orbit interpolators | Consolidate into `sensors/*` + `geometry/orbit` (§7, §8.3) |
| Capella | SNAP+StaMPS pipeline in `snap2stamps/capella` (TC **before** IFG); single-reference PS pipeline `modules/ps_stack` (GUI `tools/ps_stack_gui.py`) running on the radar-geometry coregistration; exploration tool `tools/capella_ifg_gui.py` | `ps_stack` → `processing/ps_lite` = Capella workflow (ADR-020); GUI dropped (ADR-022) |
| Handoff → StaMPS | `stamps_prep.py`: GAMMA-style `rslc/diff0/geo` + big-endian `pscands.1.*` + binaries `selpsc_patch`, `calamp`… | Replaced by `selection/` reading directly from the StackStore (§8.5) |
| StaMPS engine | 4 × `flow.py` (10–17k lines); capella↔csk differ by 71 lines (rho, weed noise, diag); s1↔capella/csk ~2400 lines (unwrap prefilter, amb weighting, IW layout); tsx is an old fork lacking SBAS/step 8; `sbas_mintpy_mixin.py` imported by nobody | One engine `processing/ps` = merge of **s1 + csk**, differences become parameters (§8.6); Capella leaves StaMPS (ADR-020) |
| Phase linking / DS | `phase_linking/{s1,csk,capella}` (csk ≈ clone of s1), `python/s1/vsar`, `python/{s1,capella}/tomo` (byte-identical binaries) ; **overwrites RSLC in place + `.rslc.bak`** | A single package `processing/phase_linking`, writes output as a new variable in the stack (§8.4) |
| Post-processing | `phasingpy.py` 9039 lines, `StaMPSEXE` ~110 methods; backend selected via env `INSAR_ITYPE` at import time | Split by domain (§9) |
| State | `control/<p>/config.json` holds `current_result`, written from many places | Replaced by manifest + workspace state (§10.6) |
| Logging | ~4600 `print`; stdout tee in 3 different places; 12 files use `logging` | Centralised logging (§12) |
| Report | ReportLab, heavily operational (gates G0–G6, the former operating procedure) | Scientific report (§13) |

---

## 3. Architecture principles

1. **One-way layering.** Upper layers only import lower layers, never the reverse (§4.2). Checked automatically.
2. **Algorithms do not know about files.** Processing functions take/return in-memory objects (`xarray.Dataset`, `numpy`, `PointSet`…). Only `io/` knows file formats. A phase is where algorithms are connected to stores.
3. **Sensor differences are data, not code branches.** `if itype == 3` is forbidden outside `sensors/`. Algorithms read parameters from `SensorProfile` / config.
4. **Immutable & versioned.** Raw data and products are never modified in place. Every re-run creates a new version. No `.bak`.
5. **Reproducible.** Every artifact has a manifest: inputs (hash), parameters (hash), code version, environment.
6. **Resume based on artifacts, not flags.** A phase knows it is done when its output artifact exists and the input hash matches.
7. **A single source of truth for configuration.** `project.toml` (written by the user) → validated against a schema → an immutable `ProjectConfig` object passed down. No module reads config files on its own.
8. **The library does not `print`, does not `sys.exit`, does not read env directly.** Use `logging`, raise typed exceptions, receive settings via parameters.
9. **GPU is optional.** Every kernel has a CPU path; GPU is selected via `core.compute` (§8.9).
10. **Shared vocabulary.** The terms `reference/secondary` (not `master/slave`), `track`, `stack`, `pair`, `epoch` (§20).

---

## 4. Repo & package structure

### 4.1 Directory tree

```
geoeyes/                                  (repo root)
├─ pyproject.toml                         package, extras, ruff, pytest, import-linter
├─ README.md · CHANGELOG.md · LICENSE
├─ src/geoeyes/
│  ├─ __init__.py · _version.py
│  │
│  ├─ core/                               ── Layer 0: depends on nothing in geoeyes
│  │  ├─ logging.py                       logging configuration, context (run_id, phase, track, tile)
│  │  ├─ errors.py                        GeoEyesError, ConfigError, DataError, PhaseError…
│  │  ├─ types.py                         Epoch, BBox, OrbitDirection, LookSide, TrackId, PointId
│  │  ├─ units.py · timeutil.py           datenum/ordinal ↔ datetime, mm/rad/m
│  │  ├─ geodesy.py                       WGS84 ellipsoid, ECEF↔LLH, ENU, geoid
│  │  ├─ compute.py                       numpy/cupy backend selection, device, worker pool
│  │  └─ hashing.py                       file/array/params hashing for manifests
│  │
│  ├─ config/                             ── Layer 1
│  │  ├─ schema.py                        pydantic models: ProjectConfig and its sections
│  │  ├─ loader.py                        reads project.toml + preset + overrides (per-subswath)
│  │  ├─ settings.py                      GEOEYES_* env (pydantic-settings)
│  │  ├─ presets/{sentinel1,cosmo_skymed,alos,capella}.toml
│  │  └─ migrate.py                       in.json + control.json (old) → project.toml
│  │
│  ├─ io/                                 ── Layer 1: the ONLY place that knows file formats
│  │  ├─ stack.py                         StackStore (Zarr)
│  │  ├─ state.py                         StateStore (schema-based HDF5)
│  │  ├─ points.py                        PointStore (GeoParquet) + TimeSeriesStore
│  │  ├─ raster.py                        RasterStore (COG)
│  │  ├─ manifest.py                      Manifest read/write, atomic write
│  │  ├─ stac.py                          STAC Item/Collection
│  │  ├─ iso19139.py                      ISO 19115/19139 XML (from metadata_writer)
│  │  ├─ fs.py                            fsspec: local / S3 / MinIO
│  │  └─ legacy/                          READS old formats (only for conversion & comparison)
│  │     ├─ dimap.py · envi.py            BEAM-DIMAP, ENVI .img/.hdr
│  │     ├─ gamma.py                      .rslc/.diff/.base/.par (big-endian)
│  │     ├─ stamps_mat.py                 .mat & .h5-masquerading-as-.mat (from mat_io)
│  │     ├─ stamps_layout.py              INSAR_*_vN/{input,raw,process,output}
│  │     └─ convert.py                    legacy → new format
│  │
│  ├─ workspace/                          ── Layer 1
│  │  ├─ layout.py                        standard paths in the workspace (§11.1)
│  │  ├─ project.py                       Project = config + layout + state
│  │  └─ lock.py                          run lock per project/track
│  │
│  ├─ geometry/                           ── Layer 2: pure SAR geometry (native engine core)
│  │  ├─ orbit.py                         StateVectors, Hermite/Lagrange interpolation, zero-Doppler
│  │  ├─ dem.py                           DEM download/cache/crop (SRTM, Copernicus GLO-30), geoid
│  │  ├─ rdr2geo.py · geo2rdr.py          range-Doppler forward/inverse
│  │  ├─ baseline.py                      Bperp, Bpar, HoA, modelled coherence
│  │  ├─ lut.py                           geocoding LUT (lat/lon/hgt/inc/heading per pixel)
│  │  └─ los.py                           LOS vector, ENU↔LOS projection (from cr_los, gnss_los_compare)
│  │
│  ├─ sensors/                            ── Layer 2
│  │  ├─ base.py                          SensorProfile, SceneMetadata, AcquisitionMode
│  │  ├─ registry.py                      get_sensor("sentinel1"), detect_sensor(path)
│  │  ├─ sentinel1/   safe.py annotation.py bursts.py orbits.py search.py profile.py
│  │  ├─ cosmo_skymed/ hdf5.py archive.py profile.py
│  │  ├─ alos/        ceos.py profile.py          (ALOS-2 PALSAR-2 L1.1 first; ALOS-4, ALOS-1 as plug-ins)
│  │  ├─ capella/     slc.py stac.py profile.py
│  │  └─ terrasar_x/  annotation.py cosar.py profile.py
│  │
│  ├─ processing/                         ── Layer 3: core processing chain
│  │  ├─ acquire/      search.py download.py ingest.py archive_index.py
│  │  ├─ network/      reference.py pairs.py
│  │  ├─ stack/
│  │  │  ├─ engine.py                     StackEngine protocol
│  │  │  ├─ native/   coregister.py resample.py tops.py interferogram.py coherence.py multilook.py filters.py
│  │  │  └─ snap/     gpt.py graphs/*.xml importer.py      (transitional backend, to be deleted)
│  │  ├─ phase_linking/ shp.py estimators.py filters.py ds.py runner.py
│  │  ├─ selection/   amplitude.py candidates.py masks.py tiles.py
│  │  ├─ ps/                              unified StaMPS engine
│  │  │  ├─ params.py state.py driver.py merge.py plotting.py
│  │  │  ├─ steps/ s1_load.py s2_gamma.py s3_select.py s4_weed.py s5_correct.py
│  │  │  │         s6_unwrap.py s7_scla.py s8_scn.py
│  │  │  └─ sbas.py closure.py
│  │  ├─ ps_lite/     geometry.py candidates.py unwrap.py invert.py runner.py   (Capella workflow, from modules/ps_stack — ADR-020)
│  │  ├─ unwrap/      irls.py grid.py triangulation.py components.py
│  │  ├─ atmosphere/  era5/ gacos/ linear.py tca.py
│  │  ├─ inversion/   sbas.py temporal.py l1regls.py velocity.py
│  │  └─ masking/     water.py model.py      (water U-Net)
│  │
│  ├─ postprocess/                        ── Layer 4 (from phasingpy.py)
│  │  ├─ pointset.py                      PointSet: attributes + time series in memory
│  │  ├─ timeseries/  smoothing.py seasonal.py decomposition.py kalman.py velocity.py
│  │  ├─ quality/     dem_error.py geolocation.py residuals.py outliers.py sigsolv.py
│  │  ├─ geometry/    decompose3d.py merge_subswath.py overlap.py
│  │  ├─ reference.py                     reference point, zero-reference
│  │  └─ alerts.py                        deformation alerts (from ops/alerts + _apply_alert_levels)
│  │
│  ├─ hazard/                             ── Layer 4: hazard zoning with rainfall (ADR-024)
│  │  ├─ coupling.py terrain.py zoning.py assess.py   → <project>/analyses/hazard/<product_id>/
│  │
│  ├─ validation/                         ── Layer 4: external validation (gnss/: NGL comparison and calibration, ADR-025)
│  │  ├─ gnss/        compare.py sources.py     (crlink, gnss_los_compare)
│  │  └─ corner_reflector/ detection.py pta.py rcs.py measure.py report.py
│  │
│  ├─ products/                           ── Layer 5
│  │  ├─ schema.py                        standard columns of PointProduct (§10.4)
│  │  ├─ metrics.py                       QualityMetrics (for report & catalog)
│  │  └─ builder.py                       PointSet + rasters + metadata → immutable Product
│  │
│  ├─ export/                             ── Layer 5: derived formats
│  │  ├─ vector.py (GPKG/SHP/CSV) · styles.py (QML/SLD) · las.py · heatmap.py
│  │
│  ├─ catalog/                            ── Layer 5: long-term storage & retrieval
│  │  ├─ stac_catalog.py index.py query.py archive.py retention.py
│  │
│  ├─ report/                             ── Layer 5
│  │  ├─ collect.py figures/ templates/ render.py
│  │
│  ├─ controller/                         ── Layer 6
│  │  ├─ phase.py artifacts.py planner.py pipelines.py runner.py
│  │  ├─ guard.py history.py progress.py preflight.py scaffold.py schedule.py benchmark.py
│  │  └─ phases/   (Phase adapters for each step, §6.4)
│  │
│  └─ cli/                                ── Layer 7
│     └─ main.py                          `geoeyes ...` (§15.1)
│
├─ apps/                                  ── Layer 7: applications outside the core package
│  └─ qgis/   ps_plotter/ ts_decompose/    (desktop GUI dropped; webapp rebuilt later — ADR-022)
├─ LICENSE                                GeoEyes licence (ADR-019)
├─ third_party/                            vendored code, with original LICENSE
│  └─ appsigsolv/                          appsigsolv 0.1.0   (Triangle replaced by scipy Delaunay)
├─ tests/ unit/ golden/ contract/ fixtures/
├─ docs/  architecture/ refactor/ user/ science/
├─ scripts/  bootstrap.ps1 bootstrap.sh check_quality.ps1
└─ notebooks/
```

Data (`data/ process/ results/ logs/ .cache/ control/`) is **no longer** in the repo — it moves to the workspace (§11).

### 4.2 Dependency rules between layers

```
 7  cli · apps(qgis; future webapp)
 6  controller
 5  products · export · catalog · report
 4  postprocess · validation
 3  processing
 2  geometry · sensors
 1  config · io · workspace
 0  core
```

- Layer N only imports layers < N. Within the same layer: import only if it does not create a cycle.
- `apps/*` (and the future webapp) only use the public API: `geoeyes.controller`, `geoeyes.catalog`, `geoeyes.io`, `geoeyes.report`, `geoeyes.config`.
- `processing` does **not** import `postprocess`; `postprocess` does **not** import `controller`.
- Checked with `import-linter` in CI (“layers” contract).

---

## 5. Domain model

```
Project ─┬─ ProjectConfig
         ├─ Track* ──── Scene* (raw, immutable)
         │     └─ Stack* ── Network(reference, pairs)
         │            ├─ SLC stack (coregistered)      ┐
         │            ├─ IFG stack + coherence         │ StackStore (Zarr)
         │            ├─ Linked phase (optional)       │
         │            ├─ Geometry (lat/lon/hgt/inc/LUT)┘
         │            └─ PsRun* ── PsState (HDF5) ── tiles
         └─ Product* (immutable, versioned) ── PointSet + Rasters + Metadata + Report
Run* ── PhaseRecord* ── Artifact*
```

| Object | Definition | Identifier |
|---|---|---|
| `Project` | A study area (AOI) + configuration | `project` (slug `[a-z0-9_-]{1,64}`) |
| `Track` | A fixed observation geometry: sensor + orbit direction + relative orbit (+ frame) | `s1-desc-018`, `csk-asc-xxx`, `alos2-asc-148` |
| `Scene` | One original SLC image (one epoch) | `track_id/20240626` + original product ID |
| `Stack` | The set of scenes of one track (one subswath for S1) coregistered to one reference | `stack_id = <track>[-<iw>]-<ref_date>-<hash6>` |
| `Network` | Reference + list of pairs (single-reference PSI, SBAS, redundant) | within the stack |
| `PsRun` | One run of the PS/SBAS engine on one stack with one parameter set | `psrun_id` |
| `PointSet` | Set of measurement points (PS/DS) + time series, in memory | — |
| `Product` | Final result, **immutable**, versioned | `<project>_<track>_<method>_<first>_<last>_v<N>` |
| `Run` | One invocation of the controller | `run_id = YYYYMMDDTHHMMSS-<rand4>` |
| `Artifact` | Any phase output, with kind + path + hash | `ArtifactRef(kind, uri, sha256)` |

Replacing old concepts: sub-project `<name>_ASC/_DESC` → `Track`; `INSAR_<date>_NORMAL_vN` → `Stack` + `PsRun` + `Product`; `current_result` → `workspace state` (latest product per track, §10.6); `PATCH_n` → `tile`.

---

## 6. Controller — Processing Phase Controller

Replaces `vinsar.py`. The controller **contains no algorithms**; it plans, guards, executes and records.

### 6.1 The `Phase` contract

```python
class ArtifactKind(StrEnum):
    RAW_SCENES = "raw_scenes"; NETWORK = "network"
    SLC_STACK = "slc_stack"; IFG_STACK = "ifg_stack"; GEOMETRY = "geometry"
    LINKED_STACK = "linked_stack"; CANDIDATES = "candidates"
    PS_STATE = "ps_state"; UNWRAPPED = "unwrapped"; APS = "aps"; TIMESERIES = "timeseries"
    POINTSET = "pointset"; WATER_MASK = "water_mask"
    PRODUCT = "product"; REPORT = "report"; EXPORT = "export"

@dataclass(frozen=True)
class PhaseContext:
    project: Project          # config + layout
    track: Track | None       # None for project-level phases (decompose_3d, report)
    run: RunRecord            # run_id, logger, progress
    inputs: Mapping[ArtifactKind, ArtifactRef]

class Phase(Protocol):
    name: ClassVar[str]
    scope: ClassVar[Literal["track", "project"]]
    requires: ClassVar[tuple[ArtifactKind, ...]]
    produces: ClassVar[tuple[ArtifactKind, ...]]
    def enabled(self, cfg: ProjectConfig) -> bool: ...
    def fingerprint(self, ctx: PhaseContext) -> str: ...      # hash(input hashes + relevant params + phase version)
    def is_done(self, ctx: PhaseContext) -> bool: ...         # artifact exists & fingerprint matches
    def run(self, ctx: PhaseContext) -> Mapping[ArtifactKind, ArtifactRef]: ...
```

### 6.2 Standard phase list

| # | Phase | Scope | Requires | Produces | Replaces |
|---|---|---|---|---|---|
| 1 | `acquire` | track | — | RAW_SCENES | `_1_download`, CSK `_1_subset` (unpack), Capella STAC, TSX ingest |
| 2 | `plan_network` | track | RAW_SCENES | NETWORK | `*_master_sel.py` ×4, `synth_sbas_pairs` ×3, `_maybe_filter_pairs_by_extent` |
| 3 | `build_stack` | track | RAW_SCENES, NETWORK | SLC_STACK, GEOMETRY | split/apply-orbit/back-geocoding/ESD/coreg/TC (SNAP); Capella: coreg without TC (the input of the current `ps_stack`) |
| 4 | `interferograms` | track | SLC_STACK, GEOMETRY, NETWORK | IFG_STACK | `Interferogram`/`TopoPhaseRemoval` graph, StampsExport |
| 5 | `phase_linking` *(opt)* | track | SLC_STACK, NETWORK | LINKED_STACK | `phase_linking/*`, `vsar`, `tomo` |
| 6 | `water_mask` *(opt)* | track | SLC_STACK, GEOMETRY | WATER_MASK | `masking/processor` |
| 7 | `select_candidates` | track | SLC_STACK/LINKED_STACK, IFG_STACK, GEOMETRY, [WATER_MASK] | CANDIDATES | `stamps_prep`, `prestamps/*`, binaries `selpsc/calamp/psc*` |
| 8 | `ps_estimate` | track | CANDIDATES | PS_STATE | StaMPS step 1–5 |
| 9 | `unwrap` | track | PS_STATE | UNWRAPPED | step 6 (pass 1) |
| 10 | `atmosphere` *(opt)* | track | UNWRAPPED, GEOMETRY | APS | `_ensure_tca_for_tropo_method`, `_aps_linear`, ERA5/GACOS |
| 11 | `invert` | track | UNWRAPPED, [APS] | TIMESERIES | step 6 pass 2 (`subtr_tropo`), 7, 8, SBAS/MintPy |
| 12 | `postprocess` | track | TIMESERIES, GEOMETRY, [WATER_MASK] | POINTSET | `phasingpy._process_single_orbit` (dem_err, lonlat_err, smoothing, seasonal, alerts…) |
| 13 | `validate` *(opt)* | track | POINTSET | POINTSET (+metrics) | `crlink`, GNSS compare |
| 14 | `merge_subswaths` *(S1)* | track | POINTSET×IW | POINTSET | `_merge_subswath_outputs`, `_merge_overlap_*` |
| 15 | `decompose_3d` *(≥2 track)* | project | POINTSET×track | POINTSET (EW/UD) | `_run_3d_decomposition` |
| 16 | `build_product` | track/project | POINTSET | PRODUCT | `ps_export_gis` (the “provenance” part), metadata |
| 17 | `report` | project | PRODUCT* + run manifest | REPORT | `ops/run_report` |
| — | `export` *(on demand)* | product | PRODUCT | EXPORT | the GPKG/SHP/CSV/QML/LAS part of `ps_export_gis` |
| — | `archive` *(on demand)* | product | PRODUCT | — | new (§11) |

Notes:
- Phases 8–11 are the wrapped StaMPS engine; phase boundaries coincide with StaMPS's natural “resume” points (after step 5, after step 6, after step 8). Inside a phase there are still per-step checkpoints (replacing `left-off.txt`).
- Pass 2 of step 6/7 (`subtr_tropo=y`) belongs to the `invert` phase when `atmosphere` is enabled — no more scattered “ensure pass1 before step6y” logic.
- PSDS/ComSAR = `phase_linking` (estimator `psds`/`comsar`) + the same chain 7–11. No more separate `TomoSARControl` + `PSDS_Prep`.

### 6.3 Pipeline presets

`pipelines.py` defines the DAG according to `project.method`:

```
psi    : acquire → plan_network → build_stack → interferograms → [water_mask] → select_candidates
         → ps_estimate → unwrap → [atmosphere] → invert → postprocess → [validate]
         → [merge_subswaths] → build_product → [decompose_3d] → report
sbas   : as psi; plan_network builds a small-baseline network; invert uses SBAS/MintPy
psds   : as psi + phase_linking (estimator EMI/EVD/…) before select_candidates
comsar : as psds with the comsar estimator
capella: acquire → plan_network → build_stack (radar geometry, no TC) → select_candidates (ps_lite)
         → ps_lite → [phase_linking] [atmosphere] → postprocess → build_product → report   (ADR-020)
```

The `ps_lite` phase (replacing phases 8–11 in the `capella` preset): requires `SLC_STACK`, `GEOMETRY`, `CANDIDATES` → produces `TIMESERIES`. Algorithm = `modules/ps_stack.run_stack`: reference epoch independent of the coreg master, reference phase from the DEM, PS selection by D_A + range spectral diversity, two-pass refined-IRLS unwrapping with a height-error periodogram, weighted LS (velocity, ΔH, reference term), APS by spatial Gaussian filtering, per-interferogram quality weights.

Presets per sensor: **Capella → `capella` only** (does not go through the StaMPS engine — ADR-020); S1, CSK, TSX, ALOS → `psi` / `sbas` / `psds` / `comsar`. ps_lite can be enabled for other sensors if desired, but it is not the default.

The user enables/disables optional phases in `[pipeline]` of `project.toml` (replacing `control.json`). The planner checks that `requires` are satisfied before running and reports clear errors (replacing `validate_control`).

### 6.4 Runner & guard

```
geoeyes run <project> [--track T] [--from PHASE] [--to PHASE] [--only PHASE] [--force PHASE] [--dry-run]

Runner.run():
  cfg   = config.load(project)                       # validate schema
  plan  = planner.plan(cfg, from_, to, only)          # pruned DAG, per track
  with guard.acquire(project, tracks):                # lock + run record + log context
      for phase, track in plan.topological():
          ctx = PhaseContext(...)
          if not force and phase.is_done(ctx): record SKIPPED; continue
          with run.phase(phase.name, track):          # log file + progress + timing + metrics
              refs = phase.run(ctx)
          manifest.record(phase, refs, fingerprint)
  report phase (if in the plan) · history.finish(status)
```

- The old `--publish-only` → gone (publishing dropped). The old `--start-step N` → `--from unwrap|invert|…`; inside `ps_estimate` there is `--ps-step` for debugging.
- Lock: `workspace/<project>/.state/locks/<track>.lock` (from `ops/lock.py`).
- Phases run **in the same process**; heavy phases use the `core.compute` worker pool themselves. The webapp calls `geoeyes run` as a detached subprocess (keeping the current `job_launcher` model).
- `control.json` is not overwritten while running; configuration is immutable within a run.

### 6.5 Operations (from `modules/ops`)

| Component | Keep / change |
|---|---|
| `lock.py` | → `workspace/lock.py` |
| `run_history.py` | → `controller/history.py` (run record = run manifest, §10.6) |
| `progress.py` | → `controller/progress.py`; **drop** `StdoutWatcher` & the monkey-patch hook — progress comes from the structured event log (§12) |
| `preflight.py` | → `controller/preflight.py` (`geoeyes check`) ; drop the SNAP check when the engine is `native` |
| `validation.py` | → replaced by pydantic schema + planner |
| `scaffold.py` | → `controller/scaffold.py` (`geoeyes init`) |
| `schedule.py` | → `controller/schedule.py` (kept: periodic re-runs, task name `GeoEyes_<project>`) |
| `benchmark.py` | → `controller/benchmark.py` |
| `health.py` | → `products/metrics.py` (quality metrics computed **inside** the pipeline, without re-reading `.mat`) |
| `alerts.py` | → `postprocess/alerts.py` (rules) + `catalog/query.py` (version comparison) |
| `log_rotation.py`, `logpaths.py` | → `core/logging.py` + `catalog/retention.py` |
| `notify.py` | **Delete** (ADR-008) |
| `run_report.py` | → `report/` (redesigned, §13) |

---

## 7. Sensors

### 7.1 Contract

```python
class AcquisitionMode(StrEnum): TOPS = "tops"; STRIPMAP = "stripmap"; SPOTLIGHT = "spotlight"; SLIDING_SPOTLIGHT = "sliding_spotlight"

@dataclass(frozen=True)
class SceneMetadata:
    sensor: str; platform: str; mode: AcquisitionMode; polarization: str
    start: datetime; stop: datetime; direction: OrbitDirection; look_side: LookSide
    relative_orbit: int | None; frame: int | None
    wavelength_m: float; range_pixel_m: float; azimuth_pixel_m: float
    prf_hz: float; range_sampling_hz: float; near_range_m: float
    azimuth_time_interval_s: float; doppler_centroid: Poly2D; fm_rate: Poly2D | None
    state_vectors: StateVectors; footprint: Polygon
    bursts: tuple[Burst, ...] | None          # TOPS only
    calibration: CalibrationLUT | None
    source_uri: str; source_id: str

class SensorReader(Protocol):
    def detect(self, path: str) -> bool: ...
    def read_metadata(self, path: str) -> SceneMetadata: ...
    def read_slc(self, path: str, window: Window | None = None, burst: int | None = None) -> np.ndarray: ...  # complex64

@dataclass(frozen=True)
class SensorProfile:
    name: str; band: Literal["C","X","L"]; modes: frozenset[AcquisitionMode]
    reader: SensorReader
    defaults: Mapping[str, Any]               # per-sensor default parameters (rho, weed, half_win…)
    orbit_source: OrbitSource                 # embedded | precise_download
    archive: ArchiveHandler | None            # rar/zip/tar unpack
```

### 7.2 Individual sensors

| Sensor | Native format | Reader | Orbit | Notes |
|---|---|---|---|---|
| **Sentinel-1** IW SLC | SAFE (.zip): `measurement/*.tiff` CInt16, `annotation/*.xml`, `calibration/*.xml` | `sentinel1/safe.py` reads via `/vsizip/` (an example already exists in `cr_report/s1slc.py`); `bursts.py` replaces `stsa` | POEORB/RESORB `.EOF` downloaded from Copernicus Data Space; `orbits.py` (replaces Apply-Orbit-File) | TOPS: deramp/ESD (§8.3). Search/download from ASF (`asf_search`) |
| **COSMO-SkyMed** (CSK & CSG) | HDF5 L1A SCS_B/SCS_U; usually inside a `.rar` | `cosmo_skymed/hdf5.py` (h5py; attr reading already exists in `csk/_2_master_sel.py`) ; `archive.py` (UnRAR/7z/bsdtar) | Embedded state vectors (HDF5 attrs) | Stripmap/Spotlight. CSG (2nd gen) has different attr names → handled by the reader |
| **ALOS-PALSAR** (done last; generation determined from sample data) | ALOS-1/2: CEOS L1.1 SLC (`LED-*`, `IMG-HH-*`, `TRL-*`, `VOL-*`); ALOS-4: **L1.1 format to be verified with JAXA** | `alos/ceos.py` (**new**), plug-in reader per generation | Embedded in the leader file | L-band: less decorrelation over vegetation; significant ionosphere → split-spectrum (prototype `tools/_split_spectrum_common.py`); ScanSAR out of initial scope |
| **Capella** | SLC GeoTIFF CInt16 + `*_extended.json` (STAC) | `capella/slc.py` (from `bperp_bpar_from_capella_extended_json`, `fdc_hz_from_capella_extended_json`, `_update_doppler_coefficients`; see also `capella_ifg_gui.load_slc/parse_extended_json`) | State vectors in the extended JSON | High-resolution Spotlight; STAC download; pipeline preset `capella` (ADR-020); **radar geometry — no TC before IFG** (ADR-005) |
| **TerraSAR-X / TanDEM-X** | `TSX1_SAR__*` / `TDX1_SAR__*`: annotation XML + COSAR | `terrasar_x/` (XML parser already in `tsx/_1_master_sel.py`) | Embedded | Keep **map geometry** (TC before IFG) until verified (ADR-005); uses the unified PS engine, does not carry over the old `flow.py` fork |

### 7.3 Sensor differences found → turned into `defaults`

| Parameter | Current state | Target |
|---|---|---|
| `rho` (reference slant range) | capella: `parms['center_range_slc']` fallback 730000; csk: hard-coded 780000 | Computed from `SceneMetadata.near_range_m` + geometry; no constant |
| weed noise pass | csk disables it automatically when `weed_standard_dev`,`weed_max_noise` ≥ π (capella: always on — no longer relevant) | `defaults.ps.weed.*` in the preset |
| phase-linking `half_win` | capella [5,5]; s1/csk [7,7] | `defaults.phase_linking.half_window` |
| `robust_da` | default for CSK, Capella | `defaults.selection.robust_da` (CSK); Capella uses ps_lite's D_A + spectral diversity criterion |
| goldstein/gaussian unwrap prefilter, amb weighting | csk/capella branch of `flow.py` | Shared parameters `ps.unwrap_grid_filter`, `ps.dem_error_ambiguity` — usable by S1/CSK/TSX/ALOS. **Wavelet/FAMM not ported, not used anywhere** (project owner, 2026-10-24) |
| PS engine | 4 × `flow.py` + `ps_stack` | Capella → `ps_lite`; the rest → `ps` (StaMPS) |
| IW layout | s1 has `IW*/raw`; the others do not | Per-subswath stack is a general concept (`Stack.subswath`) |
| NL-InSAR | csk only | Optional filter in `phase_linking.filters` |
| IFG processing geometry | TSX, Capella: TC **before** IFG (map geometry); S1, CSK: radar geometry | `stack.geometry`: `radar` for S1, CSK, ALOS, Capella; `map` for TSX until verified (ADR-005) |

---

## 8. Processing — core processing chain

### 8.1 `acquire`

- `search.py`: contract `SceneSearch.search(aoi, date_range, track) -> list[SceneRef]` — S1 (ASF), Capella (STAC). CSK/ALOS/TSX: ingest from archive only.
- `download.py`: resume, retry, integrity check (`verify_slc_zip_integrity`), monthly limit (`max_per_month`).
- `ingest.py`: brings scenes into the workspace's `raw/` (or **references** a shared store, without copying).
- `archive_index.py`: index of the raw image store shared between projects (replaces `ImageryDB` SQLite + `_shared_repo`). Stores **raw images**, not SNAP split products.

### 8.2 `network`

- `reference.py`: **one** reference selection algorithm (replacing 4 versions): maximise total modelled coherence (Bperp, Btemp, ΔfDC) — `geometry/baseline.py`. Supports a fixed reference from config.
- `pairs.py`: PSI (single reference), SBAS (Bperp/Btemp thresholds, Delaunay, k-nearest), redundant pairs (from `synth_sbas_pairs` ×3), filtering by AOI coverage (`extent_min_ratio`).
- Output `NETWORK`: table `pairs.parquet` (ref, sec, bperp, btemp, dfdc, coh_model) + `network.json`.

### 8.3 `stack` — engine

```python
class StackEngine(Protocol):
    name: ClassVar[str]                       # "native" | "snap"
    def build(self, scenes, network, aoi, dem, cfg) -> tuple[StackRef, GeometryRef]: ...
    def interferograms(self, stack, geometry, network, cfg) -> StackRef: ...
```

**`native` engine** (target, ADR-006):

| Step | Module | Technical notes |
|---|---|---|
| Orbit | `geometry/orbit.py` | Cubic Hermite / 8-point Lagrange; precise orbit for S1 |
| DEM | `geometry/dem.py` | Copernicus GLO-30 (default), SRTM 1″; geoid EGM96/EGM2008 → ellipsoidal height; cached per tile |
| Reference geometry | `geometry/rdr2geo.py` | lat/lon/hgt/incidence/heading for every reference pixel → `GEOMETRY` |
| Geometric coreg | `stack/native/coregister.py` | geo2rdr for each secondary → range/azimuth offsets from the DEM |
| Refinement | `coregister.py` | Stripmap/Spotlight: residual amplitude (incoherent) cross-correlation; TOPS: **ESD** on burst overlap areas (requires ~0.001 px azimuth) |
| Resample | `stack/native/resample.py` | phase-preserving sinc/Lanczos; TOPS: deramp → resample → reramp |
| TOPS | `stack/native/tops.py` | burst selection by AOI, deburst, subswath merge (optional) |
| Interferogram | `stack/native/interferogram.py` | `ref × conj(sec)`; subtract flat-earth + topographic phase from geometry; outputs **topo-removed** phase + coherence |
| Multilook / filter | `multilook.py`, `filters.py` | Goldstein, boxcar, gaussian (gathered from `unwrap_2d_goldstein`, `_ifg_common`) |
| Coherence | `coherence.py` | windowed/adaptive estimation |

Existing code to gather: `modules/ps_stack/stack.py` + `utils/flat_earth.py` (pixel-grid geometry on the DEM, per-epoch range, reference phase — currently used in the Capella workflow), `tools/capella_ifg_gui.py` (reference: cross-correlation coreg, Lanczos, goldstein), `snap2stamps/capella/bin/_2_coreg_ifg.py` (`PythonTerrainCorrection`, `RangeDopplerGeocoding`, `OpenTopographyDem` — currently “dormant”), `utils/flat_earth.py`, `utils/cr_los.py` (`solve_zero_doppler`), `s1/bin/_2_master_sel.py` (`_interpolate_orbit`, `_zero_doppler_state`).

Kernels: NumPy + **Numba** (CPU), CuPy (optional GPU) via `core/compute.py`. Block-wise processing (Zarr chunks) so that memory is not a limit.

**`snap` engine** (transitional): wraps the existing graphs; after gpt finishes, `importer.py` reads BEAM-DIMAP → writes into the StackStore. This way every subsequent step uses the new format from the start, and native ↔ snap can be compared on the same format. Deleted once native meets the criteria (§16.3).

### 8.4 `phase_linking`

Merges `modules/phase_linking/*`, `python/s1/vsar/*`, `python/{s1,capella}/tomo/*`, `tools/phase_link_viewer.py` (EVD/EMI/PTA), `tools/_nlinsar_common.py`.

| Module | Contents |
|---|---|
| `shp.py` | SHP tests: KS, AD (`adtest`), BWS (`bwstest`) |
| `estimators.py` | EVD, EMI, MLE, PTA, ADAPTIVE, PSDS, ComSAR (ministack) |
| `filters.py` | NL-InSAR, gaussian postfilter |
| `ds.py` | DS selection (BroNum, coherence — `DSFilter`), PS+DS blending |
| `runner.py` | Tile-wise loop, CPU/GPU |

Output: variable `slc_linked` (complex64) + `coh_pl`, `bronum`, `shp_count` in the **same** StackStore. Does **not** overwrite the RSLC, no `.bak`, no `.done`.

### 8.5 `selection` (replaces `stamps_prep` + `prestamps` + binaries)

- `amplitude.py`: amplitude calibration (`calamp`), D_A, robust D_A (pure Python, replaces `calamp.exe`).
- `candidates.py`: selection of PS candidates (D_A) / SB (`selsbc`) / DS (from phase linking), forced points.
- `masks.py`: AOI, water (U-Net or static mask), exclusion zones.
- `tiles.py`: overlapping tiling (replaces `PATCH_n`, `patch.in`, `patch_noover.in`, `_8_find_optimal_patches`).
- Output `CANDIDATES`: a PointStore (ij, lon, lat, hgt, da, type, …) + pixel indices so the PS engine can read phase from the StackStore. **No more** big-endian `pscands.1.*`, `*.in`, `width.txt`, `rsc.txt`…

The binaries `selpsc_patch`, `selsbc_patch`, `psclonlat`, `pscdem`, `pscphase`, `calamp` (+ the duplicates in `capella/tomo`) are deleted once the Python version gives identical results (golden).

### 8.6 `ps` — unified StaMPS engine

Used for S1, CSK, TSX, ALOS (Capella uses `ps_lite` — ADR-020). Source: `python/s1/stamps/flow.py` as the **base** (the most complete), merging the features of the `csk/stamps/flow.py` branch (goldstein unwrap prefilter — wavelet/FAMM not ported, amb weighting, `_build_ifg_coh_grid`, `_regularize_k_ps_spatial`…) as parameters; `capella/stamps/flow.py` need not be read further (≈ csk); nothing is carried over from tsx except `_destripe_unwrapped_grid`, `_aps_fill_nan`, `_temporal_irls_phase_gpu` if needed.

```
ps/
  params.py      Parms (from prestamps/ps_parms.py): ~120 StaMPS parameters, original names kept for traceability
  state.py       PsState: schema of the step variables (§10.3), read/write via io.state
  steps/
    s1_load.py      ps_load_initial / sb_load_initial          → ps1, ph1, bp1, da1, la1, hgt1, inc1
    s2_gamma.py     ps_est_gamma_quick                          → pm1
    s3_select.py    ps_select                                   → select1
    s4_weed.py      ps_weed                                     → ps2, ph2, pm2, bp2, hgt2, la2, inc2, weed2
    s5_correct.py   ps_correct_phase, calc_ifg_std, merge tiles → rc2, ifgstd2
    s6_unwrap.py    ps_unwrap (grid, interp, space-time, stat costs, IRLS), SBAS network fix, closure
    s7_scla.py      calc_scla, smooth_scla, setref, deramp, SBAS epoch invert, velocity
    s8_scn.py       scn_filt
  sbas.py        SBAS helpers (from the `_sb_*` functions + `sbas_mintpy_mixin.py`)
  closure.py     MintPy closure-phase correction (`_mintpy_correct_phuw_sb_after_unwrap`, l1regls)
  merge.py       tile merging (ps_merge_patches)
  driver.py      run(state, steps, cfg) — replaces `run_normal` + `StaMPSStep.run`
  plotting.py    from plot_stamps.py (standard figures — also used by the report)
```

Principles:
- Each step is a **pure function**: `def weed(state: PsState, p: Parms, compute: Compute) -> PsState`.
- Variables are stored with their **natural shape** (no `(1,1)`, no `ps['n_ps'][0][0]`). Variable names keep the StaMPS names for cross-referencing with the scientific literature.
- Per-step checkpoints in `PsState` (replacing `left-off.txt`, `no_ps_info`, `psver`).
- MATLAB datenum removed: dates stored as `datetime64[D]` (the ordinal vs datenum issue in `phasingpy._d_column_labels_from_ts_day_array` disappears).
- Triangulation: `unwrap/triangulation.py` uses `scipy.spatial.Delaunay` (edges taken from `simplices`), replacing the Triangle binary (ADR-019). Checked on golden data: equivalent edge network → unwrapping results within tolerance.

### 8.7 `unwrap`, `atmosphere`, `inversion`

| Package | Source | Notes |
|---|---|---|
| `unwrap/irls.py` | `irls_solver.py` + `irls_solver_capella.py` | one solver, with options |
| `unwrap/grid.py` | `utils/unwrap_grid.py` | |
| *(dropped)* | `unwrap_2d_pipeline.py` + `_da/_gaussian/_geotiff/_plot/_gis_export` | separate 2D pipeline for Capella, no longer needed (ADR-020); `_goldstein` → `stack/native/filters.py`, `_coherence` → `stack/native/coherence.py` |
| `atmosphere/era5/`, `gacos/` | `meteo/aps_era5`, `aps_gacos` | write the APS into PsState, not via `tca*.mat`; acquisition time taken from `SceneMetadata` (drop `capella_time.py`, `csk_time.py`) |
| `atmosphere/linear.py` | `_aps_linear` | |
| `inversion/` | `sbas_inversion`, `sbas_temporal`, `mintpy_l1regls` (clean rewrite), `step7_velocity`, `mintpy_flow` | see licensing §17 |

### 8.8 `masking`

`masking/model.py` (U-Net), `water.py` (predict + static mask). It is the first ML phase — the template for future AI (§18).

### 8.9 Computation & GPU

`core/compute.py`:
```python
@dataclass(frozen=True)
class Compute:
    backend: Literal["numpy", "cupy"]; device: int | None; workers: int; memory_gb: float
    def xp(self): ...            # numpy or cupy
```
- Array kernels: NumPy/Numba (CPU) ↔ CuPy (GPU). Torch is only used for ML models (U-Net, NL-InSAR) — ADR-014.
- The `[compute]` config replaces `*_use_gpu`, `phase_linking.use_gpu`, `nlinsar.device`, `clap_gpu_only`, `topofit_gpu_only` (read by nobody).

---

## 9. Post-processing

Replaces `phasingpy.py`. The input is `TIMESERIES` (PsState) + `GEOMETRY`; the output is a `PointSet`. **No file reads/writes between steps.**

```python
@dataclass
class PointSet:
    attrs: pd.DataFrame          # 1 row / point, columns per products/schema.py
    dates: np.ndarray            # datetime64[D], T
    disp: np.ndarray             # (N, T) mm, LOS (+ towards the satellite)
    disp_std: np.ndarray | None
    crs: str = "EPSG:4326"
    meta: dict                   # track, reference point, sign convention, units
```

| Module | Functions (source in `StaMPSEXE`) |
|---|---|
| `timeseries/smoothing.py` | `_hampel_filter`, `_adaptive_savgol`, `_smooth_timeseries_yearly_gaussian`, `_smooth_timeseries_trend_preserving`, `_apply_ts_smooth_candidate`, `_auto_select_ts_smooth` |
| `timeseries/seasonal.py` | `extract_seasonal`, `_fit_annual_seasonal` |
| `timeseries/decomposition.py` | `_ts_update_ts_decomposition`, `update_ts_auto`, `compute_trend_from_result`, `utils/ts_decomposition.py` |
| `timeseries/kalman.py` | `utils/kalman_ts.py` |
| `timeseries/velocity.py` | `_recompute_velocity`, `_compute_fit_rmse`, `_compute_psi_from_phuw`, `_apply_dtr_detrend`, `_apply_omt_refinement` |
| `quality/dem_error.py` | `ps_dem_err`, `_k_ps_uw_per_ps_for_dem`, `_estimate_dem_err_time_domain`, `_evaluate_dem_err_rmse`, `_mask_dem_err_outliers` |
| `quality/geolocation.py` | `ps_lonlat_err`, `_terrain_slope_aspect_knn` |
| `quality/residuals.py` | `_compute_ps_residuals`, `_compute_residual_sigma`, `_spatial_std_vlos_mm_yr` |
| `quality/outliers.py` | `_filter_isolated_points`, `_filter_height_outliers`, `_dedup_by_lonlat_tolerance` |
| `quality/sigsolv.py` | `_apply_sigsol_cleaning` + `third_party/appsigsolv` (DIA/OMT) |
| `geometry/merge_subswath.py` | `_merge_subswath_outputs`, `_merge_subswath_dem_tifs`, `_subswath_outputs_ready` |
| `geometry/overlap.py` | `_merge_overlap_timeseries`, `_merge_overlap_seamline` |
| `geometry/decompose3d.py` | `_run_3d_decomposition`, `_decompose_vlos_and_displacement`, `_compute_has_matrix_eu`, `_fast_interpolate`, `_finalize_3d_results`, `_*3d_output*` (fingerprint → manifest) |
| `reference.py` | `_zero_reference_first_valid`, selecting/changing the reference point |
| `alerts.py` | `_load_alert_config`, `_extract_alert_scalar`, `_apply_alert_levels` + rules from `ops/alerts.py` |
| `export/*` | the file-writing part of `ps_export_gis` (≈1270 lines), `ps_export_gis_capella_2d_lon_geo`, `_write_vlos_qgis_style`, `_pretty_breaks`, `_save_*_shp/_tif`, `_save_height_point_cloud`, `_save_ps_heatmap_tif`, `_csvtoshp` |
| **Delete** | `_publish_*`, `_upload_*_postgis`, `_publish_desc_heatmap_to_geoserver`, `_publish_with_rollback`, `_publish_project_ids`, `_merged_publish_ready`, `_ensure_gnss_shp`(if it only serves publishing) |
| **Replaced by workspace/manifest** | `_normalize_to_main_folder`, `_discover_current_result_base`, `_detect_result_folders`, `_find_latest_result_folders`, `_is_stamps_complete`, `_archive_settings_to_output`, `_make_export_log_path` |

Backend selection via env `INSAR_ITYPE` at import time → **removed entirely**.

---

## 10. Storage: formats & schema

### 10.1 Overview

| Type | Format | Store | Rationale |
|---|---|---|---|
| Raw images | Kept in the provider's format (SAFE zip, HDF5, CEOS, GeoTIFF) | `raw/` (read-only) | Raw data is not altered |
| SLC/IFG/coherence/geometry stack | **Zarr v3** (chunked, Blosc-zstd compression) | `StackStore` | Parallel chunk-wise writes, lazy reads via xarray/dask, ready for object storage |
| PS engine state | Schema-based **HDF5** (`h5py`) | `StateStore` | Many medium-sized arrays, random access, one file/tile, can be opened with HDFView |
| Measurement points | **GeoParquet 1.1** | `PointStore` | Columnar, good compression, read directly by DuckDB/GeoPandas/QGIS |
| Point time series | Long-format **Parquet** | `TimeSeriesStore` | Queries by point/date with DuckDB |
| Product rasters | **COG** (cloud-optimised GeoTIFF) | `RasterStore` | GIS standard, partial reads over HTTP |
| Discovery metadata | **STAC 1.x** Item/Collection | catalog | Open standard for EO data |
| Compliance metadata | ISO 19115/19139 XML | product | Keeps the current requirement |
| Provenance | `manifest.json` | every artifact | Reproducibility, resume, auditing |
| GIS export | GPKG / SHP / CSV / QML / LAS | `exports/` | Derived, can be regenerated |

General conventions: UTF-8; times in ISO 8601 UTC; acquisition dates `datetime64[D]`; CRS stated explicitly in the metadata (EPSG:4326 for lon/lat; radar geometry records `crs="radar"` + LUT); units in `attrs["units"]`; LOS sign: **positive = towards the satellite** (recorded in metadata, restated in the report).

### 10.2 `StackStore` (Zarr)

```
stacks/<stack_id>/stack.zarr/
  zarr.json                       attrs: stack_id, track, sensor, mode, subswath, reference_date,
                                         wavelength_m, range/azimuth spacing, engine, engine_version,
                                         dem, created, manifest_sha256
  slc            (date, y, x)     complex64   chunks (1, 1024, 1024)
  slc_linked     (date, y, x)     complex64   [phase_linking]
  amp_cal        (date)           float32     amplitude calibration factor
  ifg            (pair, y, x)     complex64   flat-earth + topo removed
  coherence      (pair, y, x)     float16/32
  mean_amp, amp_disp  (y, x)      float32
  coh_pl, bronum, shp_count (y,x) float32/uint16  [phase_linking]
  water_prob     (y, x)           float32     [water_mask]
  geometry/ lat lon hgt incidence heading slant_range (y, x) float32/64
  coords: date (datetime64[D]), pair (str "YYYYMMDD_YYYYMMDD"), pair_ref, pair_sec,
          bperp (pair|date) float32, btemp (pair) int16, y, x (int, radar pixel)
```

- Spatial chunking (1024×1024, 1 date) for block-wise processing; the parameter is adjustable.
- **Implemented (S1 native, `processing/stack/native/s1_stack.py`)**: `slc` is stored in *flattened* form — the geometric phase 4π/λ(R_sec − R_ref) is already removed, so any interferogram = `slc[i]·conj(slc[j])` without needing a separate `ifg` variable; `bperp (date,y,x)` and `esd_shift (date)` are added; the `y` axis is the reference's debursted azimuth line, cropped to the AOI.
- One stack = one track (+ one subswath for S1).
- `StackStore` API: `open(stack_id) -> xr.Dataset` (lazy), `write_var(name, da, region=…)`, `has(name)`, `fingerprint(name)`.

### 10.3 `StateStore` (HDF5, PS engine)

```
ps_runs/<psrun_id>/
  manifest.json
  params.json                     full Parms (StaMPS names kept)
  tiles/<tile_id>.h5              /step1/{ij,lonlat,ph,bperp,da,la,hgt,inc,day,...}
                                  /step2/{coh_ps,K_ps,C_ps,...}  /step3/{ix,...}  /step4/{...}
                                  /step5/{ph_rc,ifg_std,...}
                                  attrs on each dataset: units, description, stamps_name
  merged.h5                       /step5…/step8 after merge: ph_uw, scla, scn, aps, ts, velocity…
  figures/                        PNG per step (from plotting.py) — input for the report
```

The schema is defined in `processing/ps/state.py` (variable name → dtype, shape, unit, description). The legacy loader (`io/legacy/stamps_mat.py`) maps `ps1.mat`, `pm2.mat`, `phuw2.mat`… onto this schema.

**ps_lite (Capella) uses the same storage structure** — only the schema inside the state file differs:

```
ps_runs/<psrun_id>/                     engine = "ps_lite" (recorded in the manifest)
  manifest.json · params.json           params = [ps_lite] parameters (run_stack names)
  state.h5                              replaces ps_stack.npz:
    /candidates/{line,sample,da,sd,amp}           /geometry/{kh,h_ortho,lat,lon}
    /phase/{wrapped,grid,unwrapped,tropo_removed}  /reference/{phase,lat,lon,n_ps}
    /inversion/{v_mm_yr,v_std_mm_yr,dh_m,c_rad,rmse_mm,phase_std,disp_mm,aps,tcoh}
    coords: date, ifg_date (datetime64[D]), ref_date
  pairs.parquet                         replaces pairs.csv: per-interferogram quality (bperp, hoa, unwrap_rms, phase_std, used, tropo…)
  figures/                              quicklooks
```

Regardless of the engine (`ps` or `ps_lite`), the `TIMESERIES` artifact enters `postprocess` through the same adapter → `PointSet` → `products/<product_id>/` with the **same** `points.parquet` / `timeseries.parquet` / COG / STAC / ISO / manifest / report (§10.4–10.6). The catalog, webapp, report and export do not distinguish between sensors or engines; the manifest records `engine` for traceability.

### 10.4 `PointStore` & `TimeSeriesStore` (GeoParquet / Parquet)

`points.parquet` — one row/point (schema `products/schema.py`, versioned):

| Column | Type | Description |
|---|---|---|
| `point_uid` | string | ID stable across versions (§11.5) |
| `track_id` · `stack_id` | string | |
| `geometry` | Point (WKB, EPSG:4326) | |
| `lon` `lat` | float64 | |
| `height_m` · `height_err_m` | float32 | ellipsoidal height after DEM error correction |
| `type` | category | PS / DS / FORCED |
| `vel_los_mm_yr` · `vel_std_mm_yr` | float32 | |
| `acc_los_mm_yr2` | float32 | |
| `temporal_coherence` | float32 | |
| `amp_dispersion` | float32 | |
| `dem_err_m` | float32 | |
| `seasonal_amp_mm` · `seasonal_phase_day` | float32 | |
| `fit_rmse_mm` · `residual_sigma_mm` | float32 | |
| `los_e` `los_n` `los_u` | float32 | unit LOS vector |
| `incidence_deg` · `heading_deg` | float32 | |
| `alert_level` · `cluster_id` | int8 / int32 | |
| `vel_ew_mm_yr` `vel_ud_mm_yr` | float32 | 3D products only |
| `extra_*` | | extensions, without breaking the schema |

`timeseries.parquet` — long format, sorted by `point_uid, date`:

| `point_uid` | `date` (date32) | `disp_mm` (float32) | `disp_std_mm` (float32, null) | `flags` (uint8) |

Why long format: the queries “time series of point X” and “all points at date D” are both fast in DuckDB; the wide `DYYYYMMDD` format remains only in exports (compatibility with the old QGIS plugin).

### 10.5 `RasterStore` (COG)

`velocity.tif`, `velocity_std.tif`, `coherence_mean.tif`, `ps_density.tif`, `heatmap.tif`, `dem_ps.tif` — float32, DEFLATE/ZSTD compression, overviews, explicit nodata, EPSG:4326 or UTM depending on the AOI.

### 10.6 Manifest & state

`manifest.json` (every artifact: stack, ps_run, product, run):

```json
{
  "schema": "geoeyes.manifest/1",
  "kind": "product",
  "id": "mexico_capella-asc-xxx_psi_20240626_20240815_v3",
  "created": "2026-10-21T08:00:00Z",
  "software": {"geoeyes": "1.0.0", "python": "3.11.9", "packages": {"numpy": "...", "...": "..."}},
  "run_id": "20261021T080000-a1b2",
  "inputs":  [{"kind": "timeseries", "uri": "ps_runs/…/merged.h5", "sha256": "…"}],
  "params":  {"sha256": "…", "snapshot": "params.json"},
  "outputs": [{"path": "points.parquet", "sha256": "…", "bytes": 123}],
  "metrics": {"n_points": 41234, "vel_std_median_mm_yr": 1.2, "...": "..."},
  "phases":  [{"name": "postprocess", "fingerprint": "…", "status": "ok", "duration_s": 312}]
}
```

`workspace/<project>/.state/state.json` (replaces `config.json` + `current_result`): current stack / latest product per track, written **only** by the controller (atomic write).

### 10.7 Legacy

- Old results are **not** converted; projects are re-run from the raw images (ADR-017). Raw images in `data/` are moved into `$WS/archive`.
- `io/legacy/*` is **read-only** and serves two purposes: golden tests (comparing old ↔ new output) and the transitional `snap` engine (DIMAP import). Deleted when Phase 5 is complete.
- `geoeyes migrate config` (in.json + control.json → project.toml) remains available.

---

## 11. Workspace, long-term storage & retrieval

### 11.1 Workspace layout

Code and data are fully separated. Data root: `GEOEYES_WORKSPACE` (e.g. `D:/geoeyes-data`).

```
$GEOEYES_WORKSPACE/
├─ archive/                              RAW IMAGE STORE shared by all projects (immutable)
│  └─ <sensor>/<track>/<YYYY>/<scene_id>/…    + archive_index.parquet
├─ projects/<project>/
│  ├─ project.toml                       configuration (user)
│  ├─ aoi.geojson
│  ├─ raw/                               links/references to scenes in archive/ (no copy)
│  ├─ stacks/<stack_id>/                 stack.zarr · network/ · manifest.json         [HOT]
│  ├─ ps_runs/<psrun_id>/                params.json · tiles/*.h5 · merged.h5 · figures/  [HOT]
│  ├─ products/<product_id>/             IMMUTABLE                                       [WARM]
│  │    points.parquet · timeseries.parquet · rasters/*.tif
│  │    item.json (STAC) · metadata.xml (ISO 19139) · manifest.json · report.pdf
│  ├─ exports/<product_id>/              gpkg · shp · csv · qml · las (can be regenerated)    [TMP]
│  ├─ runs/<run_id>/                     manifest.json · log.jsonl · logs/<phase>.log · progress.json · preflight.json
│  └─ .state/                            state.json · locks/
├─ catalog/                              catalog.json (STAC root) · index.duckdb
└─ cache/                                dem/ · orbits/ · era5/ · gacos/ (can be deleted at any time)
```

### 11.2 Storage tiers & lifecycle

| Tier | Contents | Lifecycle | Estimated size (based on the current `mexico`) |
|---|---|---|---|
| **Archive** (cold) | raw images | Kept permanently, or only a reference kept if an external store exists (ASF/Capella can be re-downloaded) | ~40 GB / project |
| **Hot** | `stacks/`, `ps_runs/` | Reproducible from archive + config → **can be deleted** once the product has been approved; keep the latest version per track for continued monitoring | replaces `process/` (~70 GB BEAM-DIMAP) with compressed Zarr — expected to be significantly smaller |
| **Warm** (products) | `products/` | **Immutable, kept permanently**; with checksums | MB–a few GB / version |
| **Tmp** | `exports/`, `cache/` | Delete freely | — |
| **Logs** | `runs/` | Kept for `GEOEYES_LOG_RETENTION_DAYS` (default 365) — manifests kept permanently, text logs gzip-compressed after 30 days | small |

`catalog/retention.py` enforces the policy (`geoeyes catalog prune --dry-run`), and never deletes a product that is referenced by `state.json` or marked `approved`.

### 11.3 Catalog & index

- **Static STAC**: `catalog/catalog.json` → one Collection per project → one Item per product. Extensions: `sar`, `sat`, `processing`, `projection`, `file` (checksum), `version`. Assets: `points`, `timeseries`, `velocity`, `report`, `metadata`.
- **DuckDB index** (`catalog/index.duckdb`, `spatial` extension): table `products` (from STAC), views `points` / `timeseries` reading the Parquet files directly (no data duplication). The index can be **fully rebuilt** from STAC + Parquet → it is not a source of truth and needs no backup.
- No database server needed (replaces PostGIS) — one file, runs offline, fast with tens of millions of points.

### 11.4 Retrieval

```bash
geoeyes catalog list [--project P] [--track T] [--since 2025-01-01]
geoeyes catalog search --bbox lon1,lat1,lon2,lat2 --date 2024-06..2024-12 --min-vel -10
geoeyes catalog ts <point_uid> [--product latest|<id>] [--format csv|json]
geoeyes catalog diff <product_a> <product_b>          # replaces ops/alerts.compare & tools/regression_check
geoeyes catalog export <product_id> --format gpkg|shp|csv|las [--crs EPSG:xxxx]
geoeyes catalog bundle <product_id> -o file.zip       # delivery package: data + STAC + ISO + report + SHA256SUMS
geoeyes catalog verify [<product_id>]                 # checksum verification of the whole store
geoeyes catalog prune [--dry-run]
```

Corresponding Python API (`geoeyes.catalog.query`): `search(...) -> list[ProductRef]`, `points(product, bbox=None, where=None) -> gpd.GeoDataFrame`, `timeseries(point_uids, product=None) -> pd.DataFrame`. The webapp backend uses this same API (replacing `shapefile_reader`, `inversion_reader` reading `.mat`, `results_manager`).

### 11.5 Stable point identifier (`point_uid`)

To compare/join time series between monitoring runs:
`point_uid = <track_id>:<geohash9(lat,lon)>:<round(height_m)>` (≈5 m) + de-duplication within the same product. `catalog diff` matches points between 2 products by `point_uid`, with a nearest-neighbour fallback (KD-tree, configurable threshold). ADR-018.

### 11.6 Backup & external storage

- `io/fs.py` uses `fsspec`: `products/` and `archive/` can be placed on NAS/S3/MinIO (set the URI in `GEOEYES_ARCHIVE_URI`, `GEOEYES_PRODUCTS_URI`).
- 3-2-1 recommended for `products/` + `archive/` (if the raw images cannot be re-downloaded: CSK, ALOS, TSX). `stacks/`, `ps_runs/`, `cache/`, `index.duckdb` do **not** need backup.
- The report can be copied automatically to a designated folder (`[report].copy_to`) — replaces `VINSAR_EVIDENCE_DIR`.

---

## 12. Logging & observability

- **Library**: `log = logging.getLogger(__name__)`; `print` is forbidden (ruff rule `T20`). The ~4600 `print` calls are replaced gradually.
- **Single configuration** in `core/logging.py`, called once by the CLI/controller:
  - Console: human-readable format, INFO level (CLI `-v/-q`).
  - `runs/<run_id>/log.jsonl`: every record, as JSON (ts, level, logger, msg, run_id, phase, track, tile, step, duration_ms, extra).
  - `runs/<run_id>/logs/<phase>[_<track>].log`: text version per phase (replaces `logs/<p>/workflow/<stage>_<ts>.log`).
- **Context** via `contextvars` (run_id, phase, track, tile, step) — attached automatically to every record, including from worker processes (QueueHandler).
- **Child processes** (gpt, triangle, unrar): stdout/stderr read line by line → logged with logger `geoeyes.ext.<tool>`.
- **Structured events** (`log.info("...", extra={"event": "phase_end", ...})`): `phase_start/phase_end/step_end/progress/metric/warning_quality`. `progress.json` and timing statistics (replacing `timing_log.py`, `processing_times.csv`, `StdoutWatcher`) are **derived** from these events.
- Errors: typed exceptions + full traceback in the log; the run's `manifest.json` records `status`, `failed_phase`, `error`.
- Dropped: `_TeeStream`, `console_log._Tee`, `_ThreadScopedStdout`, global stdout redirection.

---

## 13. Scientific report (PDF)

### 13.1 Goals

A person **not involved in the processing** reading the report must be able to answer: which data, how it was processed, what the main results are, how reliable they are, and where the limitations lie. At the same time, it must contain enough technical detail for an InSAR expert to assess and reproduce it.

### 13.2 Structure

| Section | Contents | Data source |
|---|---|---|
| **Cover page** | Project name, AOI, sensor/track, time span, product ID, software version, creation date | manifest |
| **Summary (1 page)** | 3–5 key findings (maximum velocity, deforming areas, trends), table of key figures (number of points, density, min/median/max velocity, median uncertainty), thumbnail map, **confidence statement** (high/medium/low + reasons) | metrics, product |
| **1. Area & data** | AOI map; scene table (date, ID, mode, pol); acquisition timeline; **baseline plot** (Bperp–time) + pair network; coverage | NETWORK, SceneMetadata |
| **2. Method** | **Processing-chain diagram generated automatically** from the executed DAG; description of each step (coreg, IFG, phase linking, PS/DS selection, unwrapping, APS, inversion, post-processing) with key parameters and **scientific citations**; table of key parameters; differences from the defaults | manifest phases, params |
| **3. Quality assessment** | Coherence distribution (histogram, per pair); PS/DS density; temporal coherence; IFG standard deviation; phase closure error & fraction of pairs with unwrapping errors; effectiveness of the atmospheric correction (variance reduction); residual RMS; DEM error distribution; reference point stability | QualityMetrics, figures |
| **4. Results** | LOS velocity map (+ uncertainty map); velocity histogram; time series of representative points/clusters (selected automatically by cluster/alert); alert zones; 3D EW/UD if 2 tracks are available | product |
| **5. Validation** *(if available)* | GNSS/CR comparison: scatter, bias, RMSE, station table | validation |
| **6. Interpretation & limitations** | LOS sign convention, reference point, directional sensitivity (insensitive to N-S), residual atmosphere, decorrelated areas, usage recommendations | template + metrics |
| **Appendix A** | Full parameters (diff against the preset) | params |
| **Appendix B** | Provenance: scene list + checksums, software/library versions, environment, duration of each phase | manifest |
| **Appendix C** | List of product files + SHA-256; formats & how to read them (GeoParquet/COG/STAC) | manifest |
| **Appendix D** | Glossary & references | static |
| **Appendix E** *(optional)* | Operational information: preflight, run time of each phase, machine resources (no more operating-procedure codes/gates/sign-off — ADR-016) | run manifest |

Fixed references in the template (BibTeX): Ferretti et al. 2001 (PS), Hooper et al. 2004/2007 (StaMPS), Berardino et al. 2002 (SBAS), Ferretti et al. 2011 (SqueeSAR), Ansari et al. 2018 (EMI/sequential), Yunjun et al. 2019 (MintPy), Goldstein & Werner 1998, Prats-Iraola et al. 2012 (TOPS ESD), Jolivet et al. 2011/2014 (ERA5/GACOS-type APS), Yu et al. 2018 (GACOS). Only steps that were actually run are cited.

### 13.3 Technical

- **Collection** (`report/collect.py`): reads only the manifest + `QualityMetrics` + product — does **not** re-read `.mat`/raw logs. Metrics are computed **inside** the pipeline (`products/metrics.py`).
- **Figures** (`report/figures/`): matplotlib, common style (fonts, non-misleading colormaps: `RdBu_r` symmetric around 0 for velocity, `viridis` for coherence), vector output (PDF/SVG) for sharp printing; maps have a scale bar, north arrow, LOS direction & heading annotation.
- **Render**: **Typst** (PyPI package `typst`, self-contained binary, runs well on Windows; proper maths & citations) — ADR-010. Templates in `report/templates/*.typ`, data passed as JSON.
- **Language**: English (ADR-015), no i18n.
- Output: `products/<id>/report.pdf` + `report.json` (the data used). `geoeyes report <product_id>` regenerates it at any time.
- The CR report (`cr_report/report.py`) shares the same engine & style.

---

## 14. Configuration

### 14.1 `project.toml` (replaces `in.json` + `control.json` + `config.json`)

```toml
schema = "geoeyes.project/1"

[project]
name = "mexico"
method = "psi"                    # psi | sbas | psds | comsar
description = "..."
# organization = { name = "...", email = "..." }   # optional; only used for the contact in ISO 19139 (ADR-016)

[aoi]
bbox = [-99.2, 19.3, -99.0, 19.5]   # or file = "aoi.geojson"

[[tracks]]
sensor = "capella"
direction = "ascending"
# sentinel1: relative_orbit, frame, subswaths = ["IW1","IW2"]

[acquire]
date_range = ["2024-06-01", "2024-12-31"]
max_per_month = 0
archive = "shared"                # shared | project

[network]
reference = "auto"                # or "2024-06-26"
max_perp_m = 150
max_temporal_days = 0
extent_min_ratio = 0.95
sbas = { max_perp_m = 200, max_temporal_days = 96, redundant = true }

[stack]
engine = "native"                 # native | snap (transitional)
dem = "copernicus-glo30"
multilook = [1, 1]

[phase_linking]
enabled = false
estimator = "emi"                 # evd | emi | mle | pta | psds | comsar
half_window = [7, 7]
shp_test = "ks"                   # ks | ad | bws

[selection]
da_threshold = 0.4
robust_da = true
forced_points = ""
water_mask = "model"              # none | model | static

[ps]                              # StaMPS parameters — original names kept in the sub-tables
[ps.gamma]  ...
[ps.weed]   ...
[ps.unwrap] ...
[ps.scla]   ...
[ps.scn]    ...

[atmosphere]
method = "era5"                   # none | linear | era5 | gacos | era5+linear

[postprocess]
smoothing = "auto"
seasonal = true
decompose_3d = "auto"
alerts = "alerts.toml"

[validation]
gnss = { enabled = false, source = "sftp" }

[report]
copy_to = ""

[export]
formats = ["gpkg"]

[compute]
backend = "auto"                  # auto | numpy | cupy
workers = 0                       # 0 = auto
memory_gb = 0

[pipeline]                        # replaces control.json
water_mask = true
validate = false
from = ""                         # optional default for `geoeyes run`

[overrides.IW1]                   # per-subswath deep-merge (keeps the apply_subswath_overrides feature)
ps.weed.noisy_check = false
```

- `config/schema.py`: pydantic v2, checks types/ranges/cross-constraints (replaces `validation.py`); generates a JSON Schema for the webapp (replaces the hand-written `settingsSchema.ts`).
- Sensor presets: `config/presets/<sensor>.toml` (replaces `presets/*.json` + `_comment` + `"__unset__"`).
- `geoeyes migrate config control/<project>/` converts the old `in.json` + `control.json` to `project.toml`.

### 14.2 Environment variables (`GEOEYES_*`, read **only** in `config/settings.py`)

| Variable | Used for |
|---|---|
| `GEOEYES_WORKSPACE` | workspace root |
| `GEOEYES_ARCHIVE_URI`, `GEOEYES_PRODUCTS_URI` | external storage (optional) |
| `GEOEYES_LOG_LEVEL`, `GEOEYES_LOG_RETENTION_DAYS` | logging |
| `GEOEYES_SNAP_GPT` | only with the `snap` engine |
| *(the future webapp defines its own variables)* | |
| `EARTHDATA_TOKEN`, `CDSAPI_*` / `~/.cdsapirc`, `GACOS_*`, `OT_API_KEY`, `CDSE_*` (orbit) | third-party credentials — keep the provider's standard names |
| `GEOEYES_GNSS_SFTP_{HOST,PORT,USER,PASS,REMOTE_FILE}` | GNSS source (validation) |

Removed: `VINSAR_PYTHON` (use `sys.executable`/venv), `VINSAR_NOTIFY_*`, `VINSAR_SMTP_*`, `VINSAR_PUBLISH_*`, `VINSAR_EVIDENCE_DIR` (→ `[report].copy_to`), `VINSAR_REGRESSION_DIR`, `VINSAR_TRIGGER`, `VINSAR_JOB_ID` (→ CLI parameter), `INSAR_ITYPE`, `INSAR_SUBSWATH_FILTER` (→ `--track`), `CloudIP`, `DBUser`, `DBName`, `DBPass`, `DBPort`, GeoServer variables.

---

## 15. Applications: CLI, QGIS (GUI dropped, webapp rebuilt later)

### 15.1 CLI `geoeyes`

```
geoeyes init <project> --sensor S [--aoi FILE]      create project.toml from a preset
geoeyes check [<project>]                           preflight of environment + project
geoeyes plan <project>                              print the DAG to be run (dry-run)
geoeyes run <project> [--track] [--from|--to|--only|--force]
geoeyes status <project>                            phase/track status, latest run
geoeyes report <product_id>
geoeyes catalog …                                   (§11.4)
geoeyes migrate config|legacy …
geoeyes schedule install|remove|list <project>
geoeyes benchmark
```

Uses `typer` (or `argparse` if a dependency is to be avoided). `vinsar.py` is deleted; no shim is kept.

### 15.2 Webapp — rebuilt later (ADR-022)

The current webapp is frozen and will not be migrated; it will be designed and rebuilt after the core is finished. The core prepares for this with stable contracts:
- Running & monitoring: `geoeyes run` (detached subprocess) + `runs/<run_id>/{manifest.json, log.jsonl, progress.json}`.
- Data: `geoeyes.catalog.query` (search, points, timeseries, diff) — no reading of internal files.
- Configuration: JSON Schema generated from `geoeyes.config.schema` → auto-generated forms.
- Report: `geoeyes.report`.
What is worth re-learning from the old webapp (S1 pass prediction, CHIRPS rainfall, background CR report, SSE live log) is recorded in `docs/en/refactor/webapp-notes.md` when the rebuild starts.

### 15.3 Desktop GUI — dropped (ADR-022)

All of `tools/*_gui.py`, `tools/*viewer*.py`, `modules/pta/cr_target_gui.py` are deleted. The algorithms needed by the pipeline already exist (or are moved) in the library; only `_split_spectrum_common.py` is ported (→ `atmosphere/ionosphere.py`). The maintenance CLIs become `geoeyes` commands. QC visualisation moves to: figures in the report (§13), QGIS (reading GeoParquet/GPKG), notebooks, and the future webapp.

### 15.4 QGIS plugins (`apps/qgis`)

Read GeoParquet (supported by QGIS ≥3.30) or the GPKG export; the decompose plugin uses the same model as `postprocess/timeseries/seasonal.py` (already noted as needing to be kept in sync).

---

## 16. Testing & quality

### 16.1 Test layers

| Type | Directory | Contents |
|---|---|---|
| Unit | `tests/unit/<package>/` | pure functions: orbit, geometry, estimators, PS steps, smoothing… |
| Contract | `tests/contract/` | every Store reads/writes the correct schema; every `SensorReader` returns valid `SceneMetadata`; every `Phase` declares consistent requires/produces |
| Golden | `tests/golden/` | small dataset per sensor (S1, CSK, Capella, ALOS) → compare output with a reference within tolerance |
| Boundary | `import-linter` | layer rules §4.2 |
| CLI | `tests/cli/` | `geoeyes` commands (init, plan, run --dry-run, catalog) |

### 16.2 Golden dataset

- One small cropped stack per sensor (≤ 10–15 epochs, AOI ~ 2×2 km) — enough to run end-to-end in under a few minutes.
- Stored outside the repo (`GEOEYES_TEST_DATA`), with manifest + checksums.
- Comparison metrics: number of PS (±%), velocity (RMSE, bias), time series (RMSE), coherence (median diff), IFG phase (circular std of the phase difference).

### 16.3 Native ↔ SNAP switch criteria

| Metric | Proposed threshold |
|---|---|
| Residual coreg offset (stripmap) | < 0.05 px |
| TOPS azimuth coreg offset after ESD | < 0.002 px |
| Circular std of the IFG phase difference (areas with coherence > 0.5) | < 0.3 rad |
| Median coherence difference | < 0.02 |
| PS velocity (common points) | RMSE < 1 mm/year, bias < 0.5 mm/year |

### 16.4 Tools

`ruff` (lint + format, including `T20` forbidding print in `src/`), `mypy` gradually (strict for `core`, `io`, `config`, `controller`), `pytest` + `pytest-xdist`, `import-linter`, CI on GitHub Actions (once git is in place).

---

## 17. Dependencies

`pyproject.toml` with extras:

| Group | Packages |
|---|---|
| core | numpy, scipy, pandas, xarray, zarr≥3, numcodecs, h5py, pyarrow, geopandas, shapely, pyproj, rasterio, numba, pydantic≥2, pydantic-settings, duckdb, fsspec, matplotlib, typst, lxml, tqdm (CLI), psutil |
| `[sar]` | asf-search, requests, tenacity, cdsapi, netcdf4 |
| `[gpu]` | cupy-cuda12x |
| `[ml]` | torch, torch-dct |
| `[gui]`, `[web]` | — (dropped; the future webapp declares its own dependencies) |
| `[snap]` | (no package; requires an external SNAP installation) — only for the transitional engine |
| `[cr]` | sct[recommended], sct-sentinel1-reader, sct-cosmo-reader |
| `[gnss]` | paramiko |
| dev | pytest, pytest-xdist, ruff, mypy, import-linter |

Dropped: `reportlab` (→ typst), `SQLAlchemy` (PostGIS dropped), `geocoder`, `pyperclip`, `jenkspy` (replaced by self-written quantile/pretty-breaks classification, or kept if Jenks is needed), `stsa` (git dependency — replaced by reading the SAFE annotation directly), `PyWavelets`/`statsmodels`/`cvxopt`/`joblib` (re-evaluated when moving the code: kept if actually used).

**Licensing** (ADR-019): GeoEyes uses its own licence. Triangle → `scipy.spatial.Delaunay`. L1-regularised LS is rewritten cleanly from the algorithm (no code ported from MintPy/CVXOPT is kept) → `cvxopt` dropped if nobody uses it anymore. appsigsolv: check the licence when moving it into `third_party/`.

---

## 18. AI readiness

The refactor does not build AI, but it leaves extension points in place so that the later AI plan does not have to tear down the architecture:

| Extension point | Already available thanks to the design |
|---|---|
| **Training data** | Immutable products + schema-based GeoParquet/Zarr + queryable catalog → `geoeyes.ml.datasets` builds datasets from the catalog (points, time series, IFG/coherence patches) |
| **Labels** | Add a `labels/` store (GeoParquet: point_uid/polygon, label, source, annotator) next to products |
| **Models** | `models/<name>/<version>/` + manifest (training data, metrics, weight hash) — template from the water U-Net (`masking/checkpoint`) |
| **Inference** | Each model is a `Phase` (`requires`/`produces`) — plugged into the DAG like any other phase |
| **Computation** | `core.compute` + extra `[ml]` (torch) separate from the processing kernels |
| **Report** | Structured `report.json` → interpretation sections can be generated automatically (under control) |

Potential AI applications (to be assessed by the later plan): unwrapping error detection, PS/DS classification & removal of noisy points, machine-learning atmospheric correction, anomaly/breakpoint detection in time series, deformation forecasting, automatic interpretation of results in the report, water/vegetation segmentation.

---

## 19. Migration roadmap

Order (details & progress in [`TODO.md`](../refactor/TODO.md)):

1. **Safety net** — backup, `pyproject.toml`, golden dataset + golden tests on the current code.
2. **Framework & I/O** — `core`, `config`, `io` (+ legacy readers & converter), `workspace`. Old code starts importing via the new package.
3. **Controller** — wrap the existing stages as Phases, preserving behaviour; stop overwriting `control.json`.
4. **Unified processing** — sensors; the `snap` engine writes the StackStore; `selection` replaces `stamps_prep`; merge `flow.py` (s1 + csk → `ps` engine; tsx migrated over; capella dropped); phase linking/vsar/tomo; `ps_stack` → `ps_lite` (Capella workflow, not via StaMPS).
4b. **ALOS-PALSAR** — done last, once the other sensors are stable (sample data already available).
5. **Post-processing** — split `phasingpy`; products/export; drop publish & notify.
6. **Native engine** — orbit/DEM/geometry → coreg/resample/IFG (stripmap first: Capella/CSK/ALOS, then TOPS) → meet §16.3 → native by default → delete the snap engine.
7. **Long-term storage** — catalog, index, retention, bundle.
8. **Scientific report.**
9. **Renaming & finishing** — GeoEyes, reference/secondary, tools clean-up, type hints, docs → `git init`.

The 4 ↔ 6 order is intentional: first unify everything **after** the stack on the new format (using SNAP as the source), and only then replace the part **before** the stack with native — so that only one variable changes at a time and there is always a golden reference to compare against.

---

## 20. Glossary

| Term | Meaning | Replaces |
|---|---|---|
| reference | the reference image of the stack | master |
| secondary | the remaining images | slave |
| track | sensor + orbit direction + relative orbit | sub-project `_ASC`/`_DESC` |
| stack | the coregistered SLCs of one track (+subswath) | `INSAR_*/raw`, `process/<p>/coreg` |
| pair | a (reference, secondary) pair forming an interferogram | `<m>_<s>` |
| tile | spatial block processed by the PS engine | `PATCH_n` |
| PS run | one run of the PS engine on a stack | `INSAR_*/process` |
| product | immutable, versioned final result | `INSAR_*/output`, `current_result` |
| phase | one step of the controller | stage (`manager_run`, `stamps_run`…) |
| LOS (+) | displacement towards the satellite is positive | — |
