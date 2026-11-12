# Processing along a drawn corridor

Status (2026-11-12): plan written; owner said to go ahead.
- K0 done (§6); the owner approved the scope.
- **K1 done:**
  - `[aoi] corridor`, `geometry/corridor.py`, CLI `geoeyes corridor`;
  - bursts by polygon in acquire, build_stack and the wizard's ASF previews;
  - fingerprint;
  - tests.
- **K2 built, awaiting the owner's trial:**
  - brush in New project ("Corridor along a route") and the project tab "Processing area";
  - `/api/corridor/*`;
  - tests of the API; the brush itself is not browser-tested here. Owner's request: "process only along
a route drawn beforehand: the bursts are downloaded, clipped to the route, then the stack is built as usual". The owner
also asked for a brush tool on the map: set the width first, then hold the mouse button and drag along the route.
The buffer grows and joins up under the cursor. Companion: the QL6 corridor note in the project memory
(`ql6_km124_141`, owner's `INSAR_20241208_PSDS_v4.gpkg`).

## Contents

1. [Question](#1-question)
2. [Where the engine stands](#2-where-the-engine-stands)
3. [Design](#3-design)
4. [Steps and review gates](#4-steps-and-review-gates)
5. [Risks](#5-risks)
6. [K0 results](#6-k0-results)

## 1. Question

Roads, railways, canals and dykes are long and thin. The current engine processes a rectangle:

- the AOI bbox;
- in radar coordinates, the rectangle around it.

Along QL6 from Son La to Hoa Lac (~230 km) the rectangle is about 1.2 deg². That means:

- ~136 GB of raw bursts;
- ~400 GB of stack;
- 97 % of it is mountains nobody asked for.

Cutting the route into rectangles gives each piece its own reference. Then `geoeyes tie` must join them, and the
offsets accumulate along the chain.

Question: **can one stack, one reference and one product follow a corridor, at about the cost of the corridor
itself?**

## 2. Where the engine stands

| Part | Now | Corridor-ready? |
|---|---|---|
| Acquire (S1) | per burst: only bursts touching the AOI bbox | needs the polygon, not its bbox |
| Stack (`s1_stack._crop_to_aoi`) | rectangle of the radar grid around the AOI + 64 px margin; every 512 × 512 chunk written | no: dense |
| Geometry (lat, lon, hgt, incidence, range) | dense float32 arrays on the crop | no |
| Phase linking | per chunk over the whole crop | can skip chunks |
| PS / DS selection | every pixel of the crop | needs a mask |
| Unwrapping (IRLS grid) | sparse points on a grid | yes |
| Atmosphere (ERA5), export, web | per point | yes |

## 3. Design

### 3.1 The corridor

`[aoi] corridor = "corridor.geojson"` (in the project folder):

- a Polygon or MultiPolygon in WGS84;
- the bbox is derived from it, and an explicit bbox then only adds margin;
- `corridor_source` records how it was made: brush strokes plus width, or an imported line plus buffer.

The polygon is the union of the buffered strokes. It is computed on the server with shapely in the local UTM zone, so
the width is in metres everywhere.

### 3.2 Brush tool on the map (New project, and "Edit area" of a project)

- **Width first:** 100 m to 5 km (default 1000 m = 500 m on each side).
- **Brush:**
  - Hold the left button and drag along the route. Map panning is off while the brush is on; hold Space to pan.
  - Points are kept every ~¼ of the width on the ground, so a fast drag does not leave gaps.
  - The live preview is a deck.gl `PathLayer`: width in **metres** (`widthUnits: "meters"`, `getWidth = width`),
    round caps and joints. Drawn this way, it *is* the buffer of the polyline, so what is shown is what will be
    processed.
  - Each stroke is one polyline. Strokes that touch or overlap join into one corridor.
- **Eraser:** Alt + drag removes. The stroke is subtracted from the union.
- **Undo / redo:** Ctrl+Z / Ctrl+Y, per stroke.
- **Clear:** removes every stroke.
- **Import:** a line or polygon file (gpkg, kml/kmz, geojson, shp), e.g. the owner's QL6 line, buffered by the width.
- **Live figures** after each stroke (debounced server call):
  - corridor area and length;
  - Sentinel-1 tracks and bursts it touches;
  - raw and stack size estimate;
  - the share of the bbox it covers.
- **Snap to road (later, K2b):** a stroke near an OSM road follows the road (map matching on the OSM ways of the
  view, as the rivers tool reads OSM).

### 3.3 Sparse stack

- **Mask:** the corridor mask on the radar grid, from the reference lat/lon (`tops.reference_geometry`), dilated by
  the interpolation kernel and the phase-linking window.
- **Chunks:** the chunk list is the chunks that touch the mask. Only these are:
  - resampled;
  - written: zarr keeps no file for a chunk never written, and a read returns the fill value.
- **Chunk size:** smaller chunks follow a thin corridor more closely (e.g. 256 × 128). The size is set from the
  corridor in K0.
- **Geometry:** the geometry arrays are written chunk by chunk too. A dense lat/lon over 1.2 deg² would itself be
  tens of GB.
- **Attributes:** `corridor` (the polygon), `mask_chunks` (the chunk list) and `corridor_fraction`.
- **Coregistration:**
  - The geometric offsets are computed per chunk.
  - ESD uses the burst overlaps inside the mask; it falls back to the whole overlap when the corridor misses a
    burst overlap.

### 3.4 Downstream

- **Phase linking:** skips chunks outside the list, and pixels outside the mask inside a chunk.
- **PS / DS candidates:** only inside the mask.
- **QC images:** cropped to the mask's bbox.
- **Product:** carries the polygon (map outline, report).

### 3.5 Raw data (option)

`[acquire] keep_raw = false` deletes the raw bursts of a date once that date is in the stack. Peak disk is then a
few dates of raw. The cost: adding dates or rebuilding the stack downloads them again.

## 4. Steps and review gates

| Step | Work | Gate |
|---|---|---|
| K0 | Measure on `ql6_km124_141` (QL6 line, 1 km): chunk share for 512² / 256 × 128 / 128²; list every place that assumes a dense crop (stack, PL, selection, QC, exports, `geoeyes tie`) | **owner review** |
| K1 | `[aoi] corridor`: config, validation, burst selection by polygon, CLI `geoeyes corridor <project> --line X --width M` | unit tests |
| K2 | Web brush: width, drag, eraser, undo, import, live figures (`/api/corridor/preview`); New project + Edit area | **owner tries it** |
| K3 | Sparse stack: mask, chunk list, per-chunk resampling and geometry, ESD on the masked overlaps | unit tests + parity |
| K4 | Downstream masks: PL, selection, QC, product outline | unit tests |
| K5 | `keep_raw = false` | unit test |
| K6 | Validation: rerun `ql6_km124_141` with the corridor (QL6, 1 km) against v7: same points inside the corridor (positions identical), velocity difference NMAD < 0.3 mm/yr, disk and time; then the plan for the whole QL6 corridor | **owner review** |

**Parity rule for K3:** with the corridor equal to the bbox, the stack must be identical to the dense one (same SLC
bits).

## 5. Risks

- **Islands:** a thin corridor across forest or water can lose coherence over a stretch. The unwrapping grid then
  splits into islands that cannot be tied. Mitigations:
  - K0 measures the gaps on `ql6_km124_141`;
  - the tool can warn where the points thin out;
  - widen the brush there.
- **Ramps and troposphere on a long, thin strip:**
  - a plane fitted to a 2 km × 230 km strip is poorly conditioned across it;
  - `scla_deramp "auto"` and the ERA5 selection must be checked on K6.
- **Reference:** one reference point for 230 km; the atmosphere far from it is the largest error. A per-segment
  reference check (not a re-reference) goes in the report.
- **Brush performance:** a long stroke is thousands of points.
  - Points are thinned on the client: Douglas–Peucker at ~10 % of the width.
  - The server union is debounced.

## 6. K0 results

Scripts: `k0_corridor.py` (on the `ql6_km124_141` asc stack) and `k0_whole.py` (whole corridor, on a ground grid
turned by the heading: 14 m azimuth, 3.8 m ground range). Both are kept with the project analyses.

### 6.1 Share of the stack a corridor needs

`ql6_km124_141`:
- 16.8 km of road;
- radar grid 928 × 4225;
- mask dilated by the PL half-window (3, 9) + 4 px of resampling kernel.

| Half width | Pixels | Chunks 512² (now) | 256 × 128 | 128 × 128 |
|---|---|---|---|---|
| 250 m | 5.3 % | 44 % | 21 % | 13 % |
| 500 m | 9.0 % | 44 % | 24 % | 16 % |
| 1000 m | 16.5 % | 44 % | 32 % | 24 % |

Whole QL6, 104.05–105.82 E:
- 267 km of road;
- bbox 178 × 66 km, 11,691 km².

| Half width | Corridor | Chunks 512² | 256 × 128 | 128 × 128 |
|---|---|---|---|---|
| 500 m | 261 km² (2.2 % of the bbox) | 10.2 % | 5.4 % | 3.6 % |
| 1000 m | 512 km² (4.4 %) | 11.4 % | 6.8 % | 5.1 % |

Conclusions:
- The 512² chunks are too coarse for a corridor; use **128 × 128** for corridor stacks.
- The whole corridor stack falls from ~400 GB to ~20 GB.
- A small, tight bbox such as `ql6_km124_141` gains little: about 3×.

### 6.2 Islands

v7 inside the 1 km corridor of Km124+300–141+200:
- 100,344 points, 62,862 with coherence ≥ 0.6;
- a median of ~1,000 points per 200 m of road;
- no empty stretch. The one empty 200 m bin (Km131.7) is a 350 m straight edge of the OSM line, and points lie 6–12 m
  from the road there.

The island risk is low on this stretch. It still has to be checked on the forested parts of the whole corridor.

### 6.3 Code that assumes a dense rectangle (survey; line numbers to re-check at implementation)

- **Bbox only (B):**
  - the polygon field `AoiSection.file` exists but is unused;
  - burst search (`acquire.py`, `sentinel1/asf.py`, `build_stack.aoi_burst_ids`) intersects the bbox;
  - the stack fingerprint hashes only the bbox;
  - the DEM is loaded over bbox + 0.2°.
- **Whole-array reads (M), which must go chunk-wise:**
  - stack build: geometry arrays, burst `write_region`, seam / ionosphere fix per date, `reuse.block`;
  - stack QC;
  - phase linking: dense `pl_pair_coherence`, the Gaussian post-filter;
  - PS candidates: `_candidates`, `amplitude_dispersion`, `pair_coherence`, `ps/update.py`;
  - `ps_lite/inputs.py`, which loads the whole stack;
  - SBAS: dense `unw`;
  - raster export (`products/builder._rasters`);
  - incidence reads in the report and atmosphere validation.
- **Fill read as data (F):**
  - QC: spacing taken from the centre row, centre crops, amplitude stretch;
  - `edge_margin`, which knows only the rectangle border;
  - `ps_lite` geometry nodes and `occupied_band`;
  - SBAS: coherence percentile taken over empty cells.
- **Already fine:**
  - PS steps 2–8 (`SparseGrid`, `clap_at_points`);
  - `load_initial`, which drops NaN lon/lat;
  - ERA5 / CERRA / GACOS at the points;
  - the SHP test, which marks all-zero pixels invalid;
  - the QC coherence mask;
  - ESD and `bperp`, from whole bursts.

### 6.4 Proposed scope (for review)

1. **K1–K2 first:** the corridor polygon plus the web brush. Selecting bursts by the polygon already saves downloads,
   even with today's dense stack.
2. **K3–K4 for the owner's chain only:** Sentinel-1 TOPS stack, phase linking, PS / PSDS selection and export.
   - The sparse stack gets 128 × 128 chunks, a `valid_mask` and an `iter_chunks()` in `io/stack.py`.
   - `ps_lite` and `sbas` **refuse** a sparse stack with a clear message until they are ported.
3. **Parity rule unchanged:** a corridor equal to the bbox gives the same SLC bits as today.
