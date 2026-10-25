# GeoEyes — Architecture Decision Records (ADR)

> Status: **Accepted** (settled) · **Proposed** (proposed; applied by default unless there is an objection) · **Open** (awaiting the project owner's decision).
> To change an Accepted ADR: add a new ADR "Supersedes ADR-xxx"; do not edit the old content.

| ADR | Title | Status |
|---|---|---|
| 001 | Product name GeoEyes, remove the VINSAR / former-organisation labels | Accepted |
| 002 | A single `src/geoeyes` package, no `sys.path` | Accepted |
| 003 | Controller based on a phase DAG | Accepted |
| 004 | Storage formats: Zarr / HDF5-schema / GeoParquet / COG / STAC | Accepted |
| 005 | Radar geometry: Capella drops TC before IFG; TSX not yet | Accepted (Capella) / Open (TSX) |
| 006 | Native engine replaces SNAP GPT; SNAP is a transitional backend | Accepted |
| 007 | Drop PostGIS/GeoServer publishing | Accepted |
| 008 | Drop notifications; structured logging | Accepted |
| 009 | Long-term storage: immutable products + STAC + DuckDB | Accepted |
| 010 | Scientific report, rendered with Typst | Accepted |
| 011 | Configuration `project.toml` + pydantic | Accepted |
| 012 | reference/secondary terminology | Accepted |
| 013 | Sensor scope: S1, CSK, ALOS-PALSAR, Capella, TSX | Accepted (ALOS generation: Open) |
| 014 | GPU: CuPy for kernels, torch only for ML | Accepted |
| 015 | Language: English | Accepted |
| 016 | Drop SOP codes & all organisational information | Accepted |
| 017 | Legacy data: re-run with the new pipeline | Accepted |
| 018 | Stable `point_uid` | Accepted |
| 019 | Own GeoEyes licence; replace Triangle with Delaunay | Accepted |
| 020 | Capella workflow = the `ps_stack` method (`ps_stack_gui.py`) | Accepted |
| 021 | No git until the repo is clean | Accepted |
| 022 | Drop the desktop GUI; webapp frozen, rebuilt later | Accepted |
| 023 | Sentinel-1 downloaded per burst (ASF burst API), processed natively directly on bursts | Accepted |

---

### ADR-001 — Product name GeoEyes
**Context.** 611 occurrences / 124 files carry the labels `vinsar`/`VINSAR` or the former organisation's name, including env vars, API fields, localStorage keys and ISO metadata defaults.
**Decision.** Product `GeoEyes`; package/CLI `geoeyes`; env prefix `GEOEYES_`. No compatibility aliases are kept for the old names (the repo has not been released). No default organisational information remains (see ADR-016).
**Consequences.** Machines currently running must update their `.env` (`geoeyes migrate env` is provided). Replacement table: `migration-map.md` §11.

### ADR-002 — A single package, src-layout
**Decision.** `src/geoeyes/` installed with `pip install -e .`; remove all 107 occurrences of `sys.path.insert/append`; apps live in `apps/`, vendored code in `third_party/`. Layer boundaries are checked with `import-linter`.

### ADR-003 — Controller based on a phase DAG
**Context.** `vinsar.py` orchestrates through a chain of `if control[...]`; phase linking has to be inserted in the middle of snap2stamps, so the code temporarily overwrites `control.json` and then restores it from a backup.
**Decision.** Each step is a `Phase` declaring `requires`/`produces`; the planner builds the DAG; resume is based on artifacts + fingerprints. Config is immutable within a run.
**Consequences.** Drop `__vinsar_bak`, `left-off.txt`, `--publish-only`; `--start-step` → `--from <phase>`.

### ADR-004 — Storage formats
**Decision.** Stack: Zarr v3. PS engine state: HDF5 with a schema (natural shapes, StaMPS names, units in `attrs`). Points: GeoParquet; time series: long-format Parquet. Product rasters: COG. Metadata: STAC + ISO 19139. Provenance: JSON manifest. Legacy formats only keep readers in `io/legacy`.
**Alternatives considered.** HDF5 for everything (simple, like MintPy) — rejected because parallel writes & object storage are worse than Zarr for large stacks. NetCDF — equivalent to HDF5, no added benefit.

### ADR-005 — Radar geometry *(Accepted for Capella · Open for TSX)*
**Context.** S1/CSK form IFGs in radar geometry; TSX/Capella currently terrain-correct **before** forming IFGs (map geometry, 2 m).
**Decision (2026-10-21).** S1, CSK, ALOS, **Capella**: processed in radar geometry, geocoding via LUT (`GEOMETRY`) when building the product — Capella drops the TC step before IFG. **TSX**: keep map geometry (TC before IFG) until verification is complete; therefore `StackEngine` supports `stack.geometry = "radar" | "map"`, defaulting per sensor preset (`terrasar_x` → `map`).
**Consequences.** The PS engine and post-processing must work with both: in `map` mode, `GEOMETRY` is a regular map grid (lat/lon directly, no LUT needed). The TSX golden test runs both modes so the decision can be made later.

### ADR-006 — Native engine replaces SNAP GPT
**Decision.** `StackEngine` has two implementations: `native` (target) and `snap` (transitional: runs the old graphs and then imports DIMAP into the StackStore). Native does stripmap/spotlight first (Capella, CSK, ALOS), TOPS later. Switch the default once the ARCHITECTURE §16.3 threshold is reached; then delete `snap`.
**Alternatives considered.** ISCE3 / s1reader / COMPASS as runtime dependencies — powerful but heavy (conda-only, C++), hard to customise; kept as a **verification reference**, not a runtime dependency. Small libraries may be used for side tasks (e.g. downloading EOF orbits).

### ADR-007 — Drop PostGIS/GeoServer publishing
**Decision.** Delete `to_postgis`, `to_geoserver`, `_publish_*`, `publish_status.json`, `dbschema`, `map_id`, DB/GeoServer env vars, and the SQLAlchemy dependency. Retrieval is replaced by the catalog (ADR-009).

### ADR-008 — Drop notifications, structured logging
**Decision.** Delete `ops/notify.py` and all `VINSAR_NOTIFY_*`/`SMTP_*` variables. Centralised logging: console + `log.jsonl` + per-phase text logs; run/phase/track/tile context; `print` is forbidden in the library.

### ADR-009 — Long-term storage & retrieval *(Proposed)*
**Proposed decision.** Immutable products with version and checksum; static STAC catalog; DuckDB (spatial) index reading Parquet directly, rebuildable; archive/hot/warm/tmp tiers with a retention policy; `fsspec` for NAS/S3/MinIO; `catalog bundle` for hand-over.
**Rationale.** No database server needed; a single file, offline, fast enough for tens of millions of points; open standards.

### ADR-010 — Scientific report, Typst *(Proposed)*
**Proposed decision.** Report structure per ARCHITECTURE §13.2; data only from manifest + metrics + product; vector matplotlib figures; rendered with Typst (PyPI package `typst`, self-contained binary).
**Alternatives considered.** ReportLab (current) — manual layout, no equations/citations. LaTeX — high quality but heavy installation on Windows. WeasyPrint (HTML→PDF) — requires GTK on Windows.
**Consequences.** Operational information (gates G0–G6) becomes an optional appendix.

### ADR-011 — `project.toml` + pydantic *(Proposed)*
**Proposed decision.** Merge `in.json` + `control.json` into `project.toml`; `config.json` (state written by the pipeline) is replaced by `.state/state.json` + manifest. The pydantic schema is the source of truth and generates the JSON Schema for the webapp. Keep StaMPS parameter names in `[ps.*]`.

### ADR-012 — reference/secondary *(Proposed)*
**Proposed decision.** Replace `master/slave` in code, config, directory names, documentation and reports. Legacy readers still understand the old names.

### ADR-013 — Sensor scope *(Accepted · ALOS generation: Open)*
**Decision (2026-10-21).** Sentinel-1, COSMO-SkyMed, ALOS-PALSAR, Capella, **TerraSAR-X (kept)**. TSX is refactored like the other sensors (the old TSX fork of `flow.py` is not carried over; TSX uses the unified PS engine and so gets SBAS/step 8 automatically).
**ALOS generation (still open, not blocking).** ALOS-1 PALSAR (2006–2011, archive data only), ALOS-2 PALSAR-2 (2014–, CEOS L1.1), ALOS-4 PALSAR-3 (launched 2024; L1.1 format to be verified). The project owner **already has sample data**; ALOS is done **last** (Phase 4b, after S1/CSK/Capella/TSX are stable) — the specific generation will be determined from the sample data at that time. Readers are designed as per-generation plug-ins. ScanSAR is out of the initial scope.

### ADR-014 — GPU *(Proposed)*
**Proposed decision.** Array kernels: NumPy/Numba (CPU) ↔ CuPy (GPU) via `core.compute`. Torch only for ML models. Every kernel has a CPU path.

### ADR-015 — Language: English *(Accepted)*
**Decision (2026-10-21).** Code, comments, docstrings, logs, CLI, documentation, PDF reports: **English**. Reports need no i18n (drop `report/i18n/`). The current architecture documents (in Vietnamese) will be translated into English after the project owner has finished reviewing v0.1.
**Consequences.** Vietnamese strings in the current code (PDF reports, `modules/ops` README, PR template, webapp UI…) are translated during the refactor.

### ADR-016 — Drop SOP codes & organisational information *(Accepted)*
**Decision (2026-10-21).** No organisation is attached to the project any more. Delete the former operating procedure code, the SOP-style G0–G6 gate/sign-off blocks, `VINSAR_EVIDENCE_DIR`, and all organisation names/e-mails. `[project].organization` becomes **optional**; ISO 19139 metadata only fills in the contact when one is declared (STAC is the primary metadata). The report's operational appendix keeps only preflight + run times.

### ADR-017 — Legacy data: re-run *(Accepted)*
**Decision (2026-10-21).** Old results are not converted; projects are re-run from the original images with the new pipeline.
**Consequences.** Drop `geoeyes migrate legacy` (converter). `io/legacy/*` keeps only the **readers** needed to (1) let golden tests compare old ↔ new output, (2) let the transitional `snap` engine import DIMAP. Delete `io/legacy` when Phase 5 is complete. The original images in `data/` must be kept (moved to `$WS/archive`). `geoeyes migrate config` (in.json → project.toml) is still kept so configurations do not have to be rewritten by hand.

### ADR-018 — Stable `point_uid` *(Proposed)*
`<track_id>:<geohash9>:<round(height_m)>`, deduplicated within a product; matched across versions by uid, then by nearest neighbour. Allows time series to be tracked across multiple monitoring runs.

### ADR-019 — Own GeoEyes licence *(Accepted)*
**Decision (2026-10-21).** GeoEyes uses its own licence written by the project owner (`LICENSE` at the root).
- **Triangle** → replaced by `scipy.spatial.Delaunay` (edges taken from `simplices`); delete `third_party/triangle` and the binaries.
- **L1-regularized least squares** (`mintpy_l1regls.py`): the algorithm is public knowledge and free to use. However, the current file is a source-code port (MintPy ← CVXOPT example, both GPL-3), so **rewrite it cleanly** from the algorithm (e.g. ADMM/IRLS on `scipy`, or `cvxpy`/`scipy.optimize` if needed) instead of keeping the ported code; there is then no GPL constraint. Drop the `cvxopt` dependency if nothing else uses it.
- **appsigsolv**, `stsa`: check the licence when moving them; `stsa` is replaced by a self-written SAFE annotation reader (ADR-006).

### ADR-020 — Capella workflow = the `ps_stack` method *(Accepted, revised 2026-10-21)*
**Decision.** The official Capella workflow is the method in `modules/ps_stack` (GUI: `tools/ps_stack_gui.py`), **not** `tools/capella_ifg_gui.py`.

**Method (`ps_stack.run_stack`, current):**
1. Stack: the coreg pairs `<coreg_master>_<sec>.dim` (radar geometry — `flat_earth.corner_check` rejects terrain-corrected data) are read as epochs on the coreg master grid; the **reference epoch is chosen independently** of the coreg master (`auto` = the epoch with the smallest maximum perpendicular baseline).
2. Geometry: terrain points of the pixel grid on the DEM (once), the range from every epoch to them; each interferogram has a reference phase −4π/λ·(R_ref − R_k) and height sensitivity `kh`; the sign convention is detected automatically.
3. A single data read pass: D_A + **range spectral diversity** (sub-band) per pixel → PS candidates → at most 1 PS per cell → wrapped phase minus the reference phase.
4. Unwrap each interferogram on the PS grid with **two-pass refined IRLS**: pass 1 → PS height error via a **periodogram** over baseline; pass 2 on the height-removed phase, weighted by stability (Goldstein, space-time costs, optional linear tropo, remove plane) → refine height, recover the ambiguity of each PS.
5. Reference area (chosen automatically by D_A or given); **weighted least-squares inversion** per PS: LOS velocity, height error, reference-epoch term; APS = residual after spatial Gaussian filtering (σ m); per-interferogram quality (phase std) → reject/down-weight; filter PS by phase stability & phase std.
6. Current output: `ps.gpkg`, `ps_stack.npz`, `pairs.csv`, `summary.json`, PNG.

**Target design.**
- `processing/ps_lite/` = the method above, split by step: `geometry.py` (reference phase, `kh`, sign — uses `geometry/*`), `candidates.py` (D_A + spectral diversity, `calibration_factors`, `occupied_band`), `unwrap.py` (two passes + periodogram, uses `unwrap/irls.py` and `unwrap/grid.py`), `invert.py` (reference area, weighted LS, APS spatial filter, ifg quality), `runner.py` (replaces `run_stack`).
- Input taken from the StackStore (`SLC_STACK` + `GEOMETRY`) instead of reading `.dim` directly; output is a `PointSet` → `postprocess` → `build_product` (replacing `ps.gpkg`/`npz`/`summary.json`). The per-pair quality table (`pairs.csv`) → `QualityMetrics` for the report.
- Preset `capella` in `controller/pipelines.py`: `acquire → plan_network → build_stack (radar geometry, no TC) → select_candidates(ps_lite) → ps_lite → postprocess → build_product → report`. `phase_linking`, `atmosphere` (ERA5/GACOS) are optional plug-ins.
- Parameters keep the names & defaults of `run_stack` in `[ps_lite]` of `project.toml` (`da_max=0.4`, `sd_max=0.45`, `ps_cell=[4,6]`, `uw_cell=[16,24]`, `unwrap_method`, `tcoh_min=0.7`, `aps_sigma_m=1000`, …).
- **Capella no longer uses the StaMPS engine** (`processing/ps`, `flow.py`) — only the `capella` preset. Consequence: `capella/stamps/flow.py` is deleted (its specific parts already exist in `csk/stamps/flow.py`, 71 lines differ); the Capella StaMPS handoff (`snap2stamps/capella/bin/_3_stamps_export.py`, `_4_stamps_prep.py`, `capella/stamps/synth_sbas_pairs.py`, `prestamps/capella_pscands_geo.py`, `capella/tomo/*`, `phasingpy.ps_export_gis_capella_2d_lon_geo`, `unwrap/irls_solver_capella.py` if ps_lite does not use `unwrap_method="capella"`) is deleted or only the shared parts are kept. The coreg part of `snap2stamps/capella` (TIF→DIMAP conversion, Doppler patching, coreg **without TC**) remains the `snap` engine of `build_stack` until Phase 5.
- ps_lite is an independent engine, also usable for other sensors if desired, but by default only Capella.
- **Drop `unwrap_2d_pipeline`** (the 2D unwrapping pipeline built specifically for Capella, 4913 lines) together with `unwrap_2d_{da,gaussian,geotiff,plot,gis_export}` and everything depending on it (`phuw_2d.mat`, `unwrap_2d_*` parameters, `phase_images/`). Keep `unwrap_2d_goldstein` → `stack/native/filters.py`, `unwrap_2d_coherence` → `stack/native/coherence.py` (used by other code).
- **Uniform storage.** Capella must have the same storage structure as every sensor: `stacks/<stack_id>/stack.zarr` → `ps_runs/<psrun_id>/` (manifest + params + `state.h5` with the ps_lite schema + `pairs.parquet`) → `products/<product_id>/` with the same `points.parquet`/`timeseries.parquet`/COG/STAC/manifest/report schema. Engine differences live only in `state.h5` and the `engine` field of the manifest (ARCHITECTURE §10.3).
- `tools/ps_stack_gui.py` → `apps/gui/ps_lite_viewer.py` (choose epochs, parameters, run via the controller, view map & time series).
- `tools/capella_ifg_gui.py` is **not** part of the workflow: kept as an IFG exploration tool (`apps/gui/ifg_explorer.py`); the algorithms in it (cross-correlation coreg, Lanczos, DCT/branch-cut unwrapping…) are only a **reference** for the native engine (Phase 5), moved into the library when actually needed.

### ADR-023 — Sentinel-1 per burst, native *(Accepted 2026-10-22)*
**Context.** A full IW SLC is ~4.5–7 GB, while an AOI usually only needs a few bursts (~150 MB/burst). ASF provides burst SLCs on demand: `https://sentinel1-burst.asf.alaska.edu/<SLC>/<IWx>/<POL>/<burstIndex>.tiff` (CInt16 GeoTIFF, 1 burst) + `.xml` at the same path (combined metadata of the whole SLC: product annotation of every subswath, calibration, noise, rfi, manifest). Search: ASF search API `dataset=SLC-BURST` (filter by `fullBurstID` `<track>_<relBurst>_<IWx>`, AOI, date). Download requires `EARTHDATA_TOKEN` (Bearer) + URS cookie.
**Decision.**
- The S1 `acquire` flow downloads **bursts**, not full SLCs: select burst IDs from the AOI once (the same `relativeBurstID` across all epochs → consistent stack), download `.tiff` + `.xml` (the xml is shared by all bursts of the same SLC/pol) into `$WS/archive/sentinel1/<track>/<YYYY>/<SLC>/`.
- The `native` engine reads bursts directly (`sensors/sentinel1/burst.py`): annotation → timing, Doppler, FM rate, geolocation grid, valid window; precise orbits (POEORB) downloaded separately into `cache/orbits`.
- SAFE built with `burst2safe` is used only for **golden/cross-checking** against the old SNAP pipeline (SNAP TOPSAR-Split requires multi-subswath products → needs bursts with the same ID in IW1–IW3).
- The `asf_search` library is not used (CMR fails on this machine) — the API is called directly.
**Consequences.** Downloaded data is ~20–40 times lighter; the native S1 pipeline starts from bursts (Phase 5 is pulled forward to run in parallel with Phase 4 for S1).

### ADR-022 — Drop the desktop GUI; webapp rebuilt later *(Accepted 2026-10-21)*
**Decision.**
- **Desktop GUI**: delete entirely (`tools/*_gui.py`, viewers, `modules/pta/cr_target_gui.py`) together with the dependencies used only by the GUI (`customtkinter`, `pywinstyles`, `pyperclip`, possibly `opencv-contrib-python`). Algorithms the pipeline needs have been/will be moved into the library (only `_split_spectrum_common.py` needs a new port → `atmosphere/ionosphere.py`). Maintenance CLIs → `geoeyes` commands.
- **Webapp**: not migrated. Frozen during Phases 1–8 (no changes, excluded from tests), moved out of the repo before `git init`, kept in the backup. Rebuilt later with the project owner on the core's public API (ARCHITECTURE §15.2).
**Consequences.** The refactor scope is significantly smaller; the core is no longer bound to compatibility with the old webapp API (e.g. `v_vinsar_mm_yr`, router `results/publish`) → free to rename/change schemas. QC visualisation relies on the PDF report, QGIS and notebooks.

### ADR-021 — No git until the repo is clean
**Decision (project owner).** No `git init` until the end of Phase 9. To compensate: zip backup of the code before each major batch of changes; golden tests are the main safety net.
