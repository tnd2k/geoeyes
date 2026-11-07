# Skill: open X-band stacks (ICEYE, Capella, Umbra) to a project

> Find repeat-pass stacks in the open STAC catalogs of ICEYE, Capella and Umbra, download the part over an area and
> turn it into a GeoEyes project. Status: operational. Last checked 2026-11-01. CLI: `geoeyes opendata sync |
> sources | scenes | stacks | show | fetch | project`. Web app: Projects → Open data.

## 1. When to use it

- You want high-resolution X-band InSAR without buying data, or a test stack for the stripmap / spotlight chain.
- The question is "is there an open repeat-pass stack over this place, how many dates, how often?", then "process it".
- Not for: Sentinel-1 (its bursts come from ASF through `[acquire] date_range`, see
  [insar-processing.md](insar-processing.md)); stacks marked *search only* (no GeoEyes reader for the product);
  the flood and exposure layers of Source Cooperative (`geoeyes coop`, see exposure-and-flood-layers skill).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Internet access to AWS S3 (us-west-2) | yes | public buckets, no account or key | — | ICEYE `iceye-open-data-catalog`, Capella `capella-open-data`, Umbra `umbra-open-data-catalog` (all CC-BY 4.0) |
| Workspace | yes | as for any project | `GEOEYES_WORKSPACE` | the index goes to `<workspace>/cache/opendata/` |
| Local open-data index | yes | `geoeyes opendata sync` (or the web page, by itself) | `<workspace>/cache/opendata/<source>.json`, `places.json` | refreshed by the web app when older than 24 h |
| AOI | yes (fetch, project) | a box inside the stack's common footprint | `--bbox=W,S,E,N` → `[aoi] bbox` | write `--bbox=` with `=` when the west longitude is negative |
| Stack id | yes | `geoeyes opendata stacks` | `[acquire] opendata = "<source>:<name>"` | e.g. `iceye:x53-sm-ar-26-28.2n016.7w` |
| DEM | auto (ICEYE, Umbra) | `[stack] dem` (project) or `--dem` (fetch, default `copernicus-30`) | cache `<workspace>/cache/dem` | gives the lowest / highest height of the AOI for the cut window |
| Cut margin | optional | `[acquire] opendata_margin_m` or `--margin` | metres around the AOI | defaults ICEYE 500 m, Umbra 50 m (`opendata/fetch.py MARGIN_M`); Capella is not cut |
| Project name and method | yes (project) | your choice | `geoeyes opendata project <stack> <name>`; `--method` | default `ps_lite` for Capella and Umbra, `psi` for ICEYE |
| Credit | yes (publication) | provider licence | "© ICEYE", "© Capella Space", "© Umbra" on maps and reports | ICEYE warns its open catalog may hold experimental products |

Checklist:

- [ ] `geoeyes opendata sources` shows a recent `synced` time and a scene count per source.
- [ ] The stack is *supported* (`--supported`) and has enough dates (≥ 3; in practice 15+ for `psi`, short
      spotlight stacks go to `ps_lite`).
- [ ] The AOI lies inside the common footprint of every date (red outline in the web app).
- [ ] Umbra: AOI small (0.15 m pixels: 200 m × 200 m ≈ 1300 × 1500 px) and on stable structures.
- [ ] Disk: Capella downloads whole scenes, 0.3–1.5 GB per date.

## 3. Method

**Index.** `sync` walks each catalog (`opendata/crawl.py`), fetches only the item URLs not yet indexed (STAC items
of these catalogs are immutable; 32 parallel requests) and drops items no longer listed. Each item becomes a scene
record: source, id, item URL, datetime, platform, mode, orbit state, look side, incidence, look azimuth,
polarisation, provider ground track (`capella:rgt_id`), bbox, footprint, product format and asset URLs
(`opendata/sources.py`). ICEYE items need the `slc-cog` and `slc-json` assets, Capella `sar:product_type = SLC`
with a polarisation asset, Umbra a `*SICD*.nitf` asset. After `sync`, stack centres are named by reverse geocoding
(Nominatim, Photon as fallback, ≤ 1 request/s, cached by centre rounded to 0.1°).

**Stacks** (`opendata/stacks.py`, from STAC geometry only).

1. Group scenes by source, satellite (ICEYE: one satellite per stack) or provider ground track (Capella; Umbra mixes
   satellites), imaging mode, orbit state, look side.
2. Inside a group, in time order, a scene joins the first cluster whose reference (its earliest scene) has an
   incidence within `incidence_tol` (ICEYE, Capella 1°; Umbra 4°), a look azimuth within `azimuth_tol` (3°), and a
   footprint overlap ≥ 50 % of the smaller footprint.
3. One scene per date (the first). With `--bbox`, only the scenes whose footprint covers the AOI count; the stack is
   kept if it still has ≥ `--min-scenes` (3) dates. Clusters are formed from all scenes, so the id does not depend on
   the AOI.
4. Id: `<source>:<platform>-<mode>-<pass><look>-<incidence>-<lat><lon>[-t<hash of the ground track>]`, e.g.
   `iceye:x53-sm-ar-26-28.2n016.7w` (X53, stripmap, ascending, right-looking, 26°, 28.2° N 16.7° W); a second cluster
   with the same fields gets `-2`. Summary: dates, first / last, median and minimum gap, incidence range, common
   footprint (intersection of all footprints), `supported` (the source has a GeoEyes reader).

**Download** (`opendata/fetch.py`), one folder per date `<root>/YYYYMMDD/`:

- ICEYE SLC-COG: the TIFF window covering the AOI computed with the product RPC on an 11 × 11 grid of the AOI at the
  lowest and highest DEM ellipsoidal heights (−50 m / +50 m; without DEM: average scene height ± 300 m), plus the
  margin (range samples = margin·sin(incidence) / range pixel spacing, lines = margin / azimuth pixel spacing), read
  in 512-row strips with HTTP range requests and written as a smaller SLC-COG; `geoeyes:crop` added to the JSON.
  A window under 64 × 64 px means the AOI is not in the scene.
- Umbra SICD: the NITF found under `sar-data/task-data/<umbra:task_id>/` (collect within 10 min of the item), window
  from the SICD image projection at the same heights, read row by row, written as `*SICD*.tif` (complex64) + chip
  XML (`FirstRow / FirstCol`).
- Capella: the SLC GeoTIFF and `*_extended.json` as delivered.
- `opendata.json` (stack, AOI, margin, item, bytes) is written when a date is complete; a folder with the same
  request is not fetched again.

**In a project.** `[acquire] opendata` enables `acquire` (when `[acquire] archive` is empty). The phase recomputes
the stack with the project AOI (`min_scenes = 1`), keeps the scenes covering the whole AOI, applies `date_range` and
`max_per_month`, and fetches into `<workspace>/archive/<sensor>/<track_id>/`. Its fingerprint is the item list,
AOI and margin: a new date in the catalog (after `sync`) fetches that date only and `build_stack` adds it
incrementally. Then [insar-processing.md](insar-processing.md) applies, with the geometry checks of the builders
(ICEYE: heading ≤ 2°, near range ≤ 3 %, PRF ≤ 0.5 % of the reference; Umbra: incidence ≤ 3°, reference at the
central incidence).

## 4. Steps

1. **Index the catalogs.** `geoeyes opendata sync` (≈ 1–2 min the first time, seconds after) → prints scenes, new,
   removed, unreadable per source. `geoeyes opendata sources` shows the state. Web app: opening Projects → *Open
   data* does it by itself (and daily); *Refresh the list* forces it.
2. **Find a stack.** `geoeyes opendata stacks --supported` (all), or `geoeyes opendata stacks --bbox=-16.68,28.24,
   -16.60,28.30` (covering an area); filters `--source`, `--from`, `--to`, `--mode`, `--min-scenes`. Scenes:
   `geoeyes opendata scenes --bbox=...`. Web app: list sorted by number of dates, dot per stack on the map (ICEYE
   blue, Capella orange, Umbra violet).
3. **Inspect.** `geoeyes opendata show <stack id>`: JSON with dates, platforms, incidence, gaps, bbox, scenes.
4. **Create the project.** `geoeyes opendata project <stack id> <name> --bbox=W,S,E,N [--method psi|ps_lite]`
   (seconds) → `projects/<name>/project.toml` with `[aoi] bbox`, `[[tracks]] sensor, direction`, `[acquire]
   opendata`. Web app: click a stack → proposed area (ICEYE ~3 km around the centre, Umbra ~150 m, Capella most of
   the footprint) and download size → *Draw another area* if needed → name → *Process this stack* (writes the
   project with `[atmosphere] method = "none"`, opens its pipeline).
5. **Run.** `geoeyes run <name>`: `acquire` downloads (ICEYE ~10 MB per date for 1.5 km × 1.5 km, Umbra ~30 MB for
   200 m × 200 m, Capella 0.3–1.5 GB per date; ../guide/opendata.md §5), then the processing of
   [insar-processing.md](insar-processing.md).
6. **Download only** (no project): `geoeyes opendata fetch <stack id> --bbox=... [--track-id ID] [--margin M]
   [--dem copernicus-30]` → `<workspace>/archive/<sensor>/<sensor>-<asc|desc>/YYYYMMDD/`.

## 5. Outputs and how to read them

| File | Content |
|---|---|
| `<workspace>/cache/opendata/<source>.json` | `synced` time and scene records |
| `<workspace>/cache/opendata/places.json` | place names of stack centres ("" = no name, e.g. sea) |
| `<archive>/<sensor>/<track_id>/YYYYMMDD/` | ICEYE `ICEYE_*_SLC.tif` + `.json`; Umbra `*SICD*.tif` + `.xml` (or `.nitf`); Capella `.tif` + `_extended.json`; `opendata.json` |
| `projects/<name>/project.toml` | minimal declaration; the rest from the sensor preset |

`stacks` columns: id, dates, first..last, median gap (days), incidence range, place, "(search only: no reader)" when
unsupported. Known stacks on 2026-10-28 (../guide/opendata.md §7): 72 stacks of ≥ 3 dates (65 Capella, 2 ICEYE,
5 Umbra); e.g. `iceye:x53-sm-ar-26-28.2n016.7w`, Tenerife, 19 dates, 1-day gap, B⊥ −873..+75 m.

## 6. Quality checks

- Before processing: dates and gaps (`show`), incidence range (a wide range in a spotlight stack loses coherence).
- After `acquire`: every date folder has `opendata.json`; sizes as expected.
- `build_stack` log: "scene left out (not the reference geometry)" lines and the B⊥ of each date; ICEYE dates of
  another beam (PRF) are dropped on purpose (Tenerife 2026-02-27..03-01: coherence 0.16–0.23 against 0.4–0.8).
- The stack check runs by itself for these sensors: offsets < 0.1 px, no date of pure noise
  ([stack-qc.md](stack-qc.md)).

## 7. Limits and pitfalls

- Stacks are found from STAC geometry only; perpendicular baselines are known after reading the products.
- The stack id comes from the earliest scene of its cluster: an earlier scene added to the catalog would change it.
- `[acquire] archive` set together with `opendata` disables `acquire`.
- Umbra: repeat passes differ in look angle by 1–2° for a ~4.5° aperture, baselines of km (height of ambiguity below
  a metre), water and container yards decorrelate: expect coherence only on structures.
- Open catalogs may hold experimental products; the readers refuse unknown orientations or product types.
- Place names need the network at `sync`; `stacks` reads the cache only.

## 8. On a new area or sensor

- Choose the AOI on the map inside the common footprint; for ICEYE keep it a few km (cut download), for Umbra a few
  hundred metres on buildings, roads, quays.
- US Umbra stacks: `[stack] dem = "lidar-3dep"`; fix `[network] reference` at the central incidence if the automatic
  choice is not wanted (`lasvegas_umbra`: `reference = 2025-08-03`, 42.0°, every scene within 3°).
- ICEYE follows the COSMO-SkyMed preset (phase linking + Gaussian post-filter, `max_perp_m = 1000`; the
  experimental `unwrap_align_constant` is off, set `"y"` to try it, see [insar-processing.md](insar-processing.md) §3).
- A new source needs a `Source` entry (catalog roots, normaliser, tolerances), a fetcher and a sensor reader.

## 9. References

- Code: `src/geoeyes/opendata/{sources,crawl,index,stacks,fetch,places}.py`, `controller/phases/acquire.py`,
  `cli/main.py` (`cmd_opendata`), `api/opendata.py`, `webapp/src/pages/OpenData.tsx`, `sensors/iceye/slc_cog.py`,
  `sensors/sicd/`, `processing/stack/native/{stripmap,sicd_stack}.py`.
- Guide: ../guide/opendata.md. Decisions: ../architecture/decisions.md ADR-028, ADR-029.
- Skills: [insar-processing.md](insar-processing.md), [stack-qc.md](stack-qc.md).
- NGA SICD Volume 3 (image projections); ICEYE, Capella, Umbra open-data programme pages (licence CC-BY 4.0).
