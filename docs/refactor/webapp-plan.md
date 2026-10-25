# New web application — plan

**Status (2026-10-25): MVP built.** `geoeyes serve` → http://localhost:8765 (never 5173; dev server 8766).
Done: `geoeyes.api` (workspace tree, folders, project status, plan, run / stop, run logs, product layers, point
and area series, files), front end in `webapp/` (project tree with folders and drag and drop, Overview, Explorer,
Project). Then: settings form described from the schema (edits written with tomlkit, comments kept, previous file
in `.state/`), raw `project.toml` editor, new-project wizard (AOI drawn on the map, Sentinel-1 tracks over it,
preview of the acquisitions with the acquire phase's own search), product comparison (swipe; difference B − A of
the median velocity per cell, median offset removed, warning when the lines of sight differ), corner reflector
reports (build, table, figures, PDF), token login when listening beyond this machine (`GEOEYES_WEB_TOKEN`).
Then (2026-10-25, third pass): map composer ("Map image": sheet A4/A3/slides, title, legend in the QGIS classes,
scale bar, north arrow, product details, credits; PNG or PDF at 150-300 dpi, rendered off screen at print size);
PMTiles (`export/pmtiles.py`, own MVT encoder; written by the export phase by default, read by QGIS 3.32+; the map
reads products above 2.5 M points as tiles, any layer can be switched to tiles); monitoring tab (next Sentinel-1
acquisitions from the archive, scheduled `geoeyes run` through the Windows Task Scheduler, deformation alert rules in
`[postprocess.alerts]` checked on the latest product, triggered alerts in the overview). Fourth pass: ESA's
published acquisition plan checks the 12-day forecast (planned / not planned / forecast), monthly CHIRPS v3
rainfall under the time series, SCN-removed series beside the displacement, workspace catalog ("Products here"),
coordinate frame and satellite flight / look arrows on map images.

The former webapp (FastAPI + React, 11 API groups, 5 pages) is frozen and will be replaced. It edited the
legacy files directly (`in.json`, `control.json`, `.mat`), needed Node and two processes at run time, and spread
its features over many small tools. The new one is a thin client of the GeoEyes core.

## Principles

1. **A thin layer over the core**: everything goes through the public API — controller `plan` / `run` / `status`,
   products (GeoParquet, STAC, COG), reports, run records. No internal files, no processing logic of its own.
2. **One question per screen**: what needs attention? what does this project still have to run, and why? where
   and how fast does the ground move? can the result be trusted?
3. **Map first**: InSAR data are spatial; tables support the map, not the other way round.
4. **One command to operate**: `geoeyes serve` — FastAPI serves the built single-page app on one port; no Node on
   the processing machine. Local-only by default; token login when exposed.

## Layout

A persistent **project tree** on the left (like a SaaS file browser or the QGIS browser / layers panels), and four
areas on the right.

### Project tree

```
Workspace
├─ Vietnam/                      folders: user-defined groups of projects (drag to reorganise)
│  └─ Hanoi/
│     ├─ hanoi_csk               project: status dot (up to date / new data / running / failed)
│     │  ├─ cosmo_skymed-asc     track
│     │  │  ├─ Data              acquisitions (dates, baselines), archive folder
│     │  │  ├─ Stack             coregistered stack (dates, reference, size)
│     │  │  ├─ PS run            points, QC figures
│     │  │  ├─ Products          v1, v2 ... (immutable versions; eye toggle = show on the map, like QGIS layers)
│     │  │  └─ Exports           GeoPackage / CSV downloads
│     │  ├─ Reports              PDF reports
│     │  ├─ Validation           corner reflector reports
│     │  └─ Settings             project.toml (form)
│     ├─ hanoi_s1
│     └─ hanoi_s1_desc
└─ Mexico/
   ├─ mexico_s1
   └─ mexico_capella
```

- Folders are workspace metadata (`<workspace>/projects/.folders.json`: folder tree + project order); a project
  folder on disk stays `projects/<name>/`, so moving a project between folders moves nothing on disk.
- Context menu per node: run, plan, open report, download, duplicate project, archive project.
- Product nodes carry an eye toggle and an opacity slider: several products (e.g. S1 and Capella over the same
  city, or v2 and v3) can be stacked on the map like QGIS layers.
- Search box filters the tree; badges show what changed (new acquisitions on ASF, failed phase).

### Areas

| Area | Content |
|---|---|
| **Overview** | Map of every project as a card: status, latest product, confidence level, largest velocity, new acquisitions. The first screen of the day |
| **Project** | Pipeline as a flow of the phases, each with its status and the reason `geoeyes plan` gives ("2 new acquisitions on ASF", "parameters changed"); Run button; live log (`runs/<id>/log.jsonl`); acquisition timeline and baselines; settings form generated from the `project.toml` schema, differences from the preset highlighted |
| **Explorer** (the main screen) | WebGL map of millions of points, jet_r Pretty Breaks as in QGIS and the reports; click a point → time series; draw an area → mean series; compare two products (difference or swipe); satellite or dark base map |
| **Results & validation** | Product versions, PDF report preview, GeoPackage / CSV downloads, corner reflector reports |

Dropped: sigsolv, `.mat` readers, QC tool catalogue, GeoServer publishing. Later: deformation alerts (Phase 6),
monitoring schedule, Sentinel-1 pass forecast, rainfall overlay.

## Visual design

- "Mission control": dark by default (light mode available), full-screen map, floating rounded panels, Inter.
- Status colours (green / amber / red) only for status, always with an icon and a label; the deformation colour
  scale identical to QGIS and the PDF report.
- Every number has its context: tooltips ("LOS, + toward the satellite, relative to the reference area"),
  confidence badge from the report.

## Technology

- Frontend: React + TypeScript + Vite, deck.gl + MapLibre, shadcn/ui (Radix) + Tailwind, TanStack Query,
  uPlot / ECharts for time series.
- Backend: `geoeyes.api` (FastAPI) over the controller and the products; background runs as `geoeyes run`
  subprocesses; logs streamed with SSE.
- Millions of points: `build_product` also writes the points as PMTiles (read tile by tile by the map); time series
  of a point or an area queried with DuckDB directly on the GeoParquet (the catalog of Phase 7).

## Roadmap

1. MVP: project tree, Overview, Explorer, Project status + Run, reports.
2. Settings form, new-project wizard (AOI drawn on the map, sensor, preview of the ASF acquisitions), corner
   reflector reports, folders management.
3. Alerts, monitoring schedule, pass forecast.

Core prerequisites: `geoeyes.api` (projects, status, products, point / time-series queries), PMTiles in the
product, DuckDB catalog, folder metadata.
