# Skill: regional landslide susceptibility from an inventory

> Which slopes fail when a storm hits, learnt from mapped landslide polygons on a 30 m grid (and later with
> rainfall and pre-event InSAR)? Status: research; steps L0 (inventory, footprints, area–frequency) and L1 (labels)
> are implemented, L2–L7 (predictors, models, rain, InSAR, thresholds, hindcast) are not. Last checked 2026-11-01.
> CLI: `geoeyes landslide inventory | audit | labels [--study <name>]`. Web app: none yet.

## 1. When to use it

- The question: where do *rapid*, rainfall-triggered landslides start, given an inventory of mapped polygons from
  past storms (Das 2024: Ketsana 2009, Podul 2013, Molave 2020 in central Vietnam)? The answer will be a 30 m
  susceptibility map validated by spatial blocks and by transfer between events.
- It supports land-use and early-warning planning at the scale of districts and provinces.
- Not this skill: slow slope motion measured by InSAR (that is the `landslide` mode of
  [hazard-zoning.md](hazard-zoning.md)), and the InSAR-labelled susceptibility of
  [susceptibility-and-forecast.md](susceptibility-and-forecast.md). Here the labels come from an inventory, not
  from InSAR.
- Not usable yet as a product: only the labels exist. Use it now to prepare and audit an inventory, and to build
  reproducible training labels.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Mapped landslide polygons (Das 2024) | yes (audit, labels) | Zenodo 15596033, `Landslide_data_V2.zip` (CC-BY-4.0) | unzip to `<workspace>/cache/opendata/landslide/das2024/raw/Landslide_data/Landslide_data/` (shapefiles `Ketsana_landslides/kesana_landslides/Ketsana_landslides.shp`, `Podul_landslides/Podul_landslides/Podul_landslides.shp`, `Molave_landslides/Molave_landslides/Molave_landslides.shp`) | `geoeyes landslide inventory` turns them into `inventories/landslide/central_vn_das2024.gpkg` |
| NASA Global Landslide Catalog export | yes (`inventory`) | data.nasa.gov, CSV | `<workspace>/cache/opendata/landslide/nasa_glc.csv` | columns read: `latitude`, `longitude`, `country_name`, `event_date`, `location_accuracy`, `landslide_category`, `landslide_trigger`, `storm_name`, … |
| Curated reported events | optional | collected by hand (news, AHA Centre ADINet) | `<workspace>/inventories/landslide/curated_events.csv` (UTF-8): `date` (YYYY-MM-DD or YYYY-MM), `lat`, `lon`, `accuracy` (`exact`, `1km`, `5km`, `commune`, `10km`, `district`, `province`…), `type`, `place`, `trigger`, `fatalities`, `source`, `url`, `notes` | editable; rebuilt into `vietnam.csv` |
| Province boundaries | yes (`inventory`) | geoBoundaries VNM ADM1 (63 provinces, before 2025) | `<workspace>/cache/opendata/boundaries/vnm_adm1.geojson` (`shapeName`) | used to drop points outside Vietnam and name the province |
| Copernicus GLO-30 DEM | yes (audit, labels) | downloaded automatically, once per 1° tile | `<workspace>/cache/dem/copernicus-30/` | heights for the scarp point and slopes |
| Study area | yes (labels) | drawn or computed by you (the pilot is the intersection of two Sentinel-1 bursts, made by the L0 script) | a GeoPackage layer with a `name` column, e.g. `studies/landslide_central_vn/l0/pilot.gpkg`, layer `pilot`, row `bursts` | not made by the CLI |
| Event footprints | yes (labels) | `geoeyes landslide audit` | `studies/<name>/audit/footprints.gpkg`, layer `footprints` (`event`, `variant` = `near` / `hull` / `hull_shrunk`) | the mapped extent is not published: approximated |
| Study file | yes (labels) | written by you | `studies/<name>/study.toml`, schema `geoeyes.landslide_study/1` (below) | paths relative to the workspace root |

`study.toml` (the one in use):

```toml
schema = "geoeyes.landslide_study/1"
[study]
name = "landslide_central_vn"
[inventory]
polygons = "inventories/landslide/central_vn_das2024.gpkg"
citation = "Das, R. (2024) ... https://doi.org/10.5281/zenodo.15596033 (CC-BY-4.0)"
[area]
file = "studies/landslide_central_vn/l0/pilot.gpkg"
layer = "pilot"
name = "bursts"
[footprints]
file = "studies/landslide_central_vn/audit/footprints.gpkg"
main = "near"
sensitivity = "hull"
[[events]]          # oldest first: reactivations look back at the earlier events
name = "Ketsana"
date = "2009-09-29"
[[events]]
name = "Molave"
date = "2020-10-28"
[labels]
cell_m = 30.0
negative_buffer_m = 60.0
ratio = 1.0
draws = 10
seed = 0
```

Checklist:

- [ ] The raw inventory and the GLC CSV are in `cache/opendata/landslide/`, the boundaries in
      `cache/opendata/boundaries/`.
- [ ] `geoeyes landslide inventory` has written `central_vn_das2024.gpkg` (layers `polygons`, `points`).
- [ ] `geoeyes landslide audit` has written `footprints.gpkg`, and you looked at it against images of each event.
- [ ] The study area GeoPackage has a row whose `name` matches `[area] name`.
- [ ] `[[events]]` names match the `event` column of the polygons, oldest first; every event has polygons in the
      area.
- [ ] Network access for the GLO-30 tiles on the first run.

## 3. Method

### 3.1 Inventories (`geoeyes landslide inventory`, `landslide.inventory`)

- **Reported events → `vietnam.csv` / `.geojson`.** GLC rows inside 102–110° E, 8–23.5° N, plus the curated rows.
  A point outside every province by more than 0.03° (~3 km, for simplified coastlines) is dropped. Two rows within
  2 days and 10 km are one event: the more precise location is kept (curated before GLC at equal precision), the
  other goes to `also_in`. `usable = 1` for a slope failure (`landslide`, `debris_flow`, `mudslide`, `rock_fall`,
  `complex`, `flash_flood_landslide`) located to 5 km or better. `id` = SHA-1 of date and position.
- **Polygons → `central_vn_das2024.gpkg`.** WGS84; `area_m2` in the source UTM zone; invalid geometries repaired
  (`valid = 0`), only polygon parts kept; `points` = a point inside each polygon; `province` by spatial join.

### 3.2 Audit, L0 (`geoeyes landslide audit`)

- **Footprints** per event, from the inside points in the UTM zone: `near` = union of 1 km buffers, closed by
  +1.5 km / −1.5 km (gaps under 3 km filled); `hull` = concave hull (ratio 0.3) + 1 km; `hull_shrunk` = hull − 1 km.
  Each minus the connected flat land (GLO-30 slope < 5°) larger than 1 km². L0 found the hull enclosing large
  unmapped areas for Ketsana, so `near` is the main footprint and `hull` the sensitivity variant.
- **Area–frequency** per event: quantiles, the density peak (rollover) on 40 log bins from 10 m² to 1 km², the
  count below 900 m² (one cell), and the power-law tail (Clauset et al. 2009): the `x_min` minimising the
  Kolmogorov–Smirnov distance over 60 quantiles (5–90 %, at least 50 in the tail) and α = 1 + n / Σ ln(A / x_min).
- **Overlaps**: polygons of one event intersecting another event's (reactivations), and pairs inside an event
  (overlapping area > 1 m², shared edge, point touch).

### 3.3 Labels, L1 (`geoeyes landslide labels`, `landslide.labels`)

- **Grid**: `Grid(cell_m=30)` of `geoeyes.ml.layers` over the study area's bounds (`lat0` = middle latitude);
  heights from GLO-30 at the cell centres; slope from their gradient.
- **Positives** per polygon (the initiation zone, Steger et al. 2016): `scarp` = the cell of the highest point among
  the cell centres inside the polygon and its vertices; `upper` = cells inside whose height is in the top
  `upper_fraction` (1/3) of the polygon's range (the scarp cell when none); `centroid` = the cell of the centroid
  (a point inside if the centroid falls outside), for comparison only. One positive per cell and variant;
  `n_polygons` counts polygons sharing it. `reactivated` = the polygon intersects a polygon of an earlier event of
  the study.
- **Negatives** per footprint variant (`main` and `sensitivity`): cells inside footprint ∩ study area, with a
  finite height, farther than `negative_buffer_m` (60 m) from every polygon of *that* event, and not a positive;
  `ratio` × positives drawn without replacement, `draws` times, each draw from `default_rng([seed, draw,
  variant, footprint])`. If the pool is smaller, all candidates are taken and the case is listed in `short`.
- **No slope filter**: flat negatives are kept; the slope distribution of positives and negatives is reported so
  that easy negatives can be judged.

## 4. Steps

1. **Inventory.** `geoeyes landslide inventory` → `inventories/landslide/vietnam.csv`, `vietnam.geojson`,
   `central_vn_das2024.gpkg`; prints the counts by source and per event. Seconds to a minute.
2. **Audit (L0).** `geoeyes landslide audit --study landslide_central_vn` → `studies/<name>/audit/footprints.gpkg`,
   `audit.json` (footprints, area–frequency, overlaps); prints area and landslides inside per footprint. Downloads
   the GLO-30 tiles over the whole inventory on the first run.
3. **Study area and `study.toml`.** Make the area GeoPackage and write the study file (§2). Look at the footprints
   in QGIS before choosing `main` and `sensitivity`.
4. **Labels (L1).** `geoeyes landslide labels --study landslide_central_vn [--set draws=5] [--set
   negative_buffer_m=90]` → `studies/<name>/labels/labels_<event>.parquet`, `labels.json`, `labels_<event>.png`
   (three 1.5 km windows per event: polygons, positives of each variant, negatives of draw 0), `manifest.json`.
   Prints polygons, positives per variant, candidates per footprint, and any `short` draw.
5. **Gate review.** Each step ends with a review by the project owner before the next one (research note §5).
   L2–L7 have no command yet.

## 5. Outputs and how to read them

- `labels_<event>.parquet`: `event, footprint, variant, draw, label, cell, lon, lat, height_m, slope_deg, src_fid,
  area_m2, n_polygons, reactivated`. Positives have `label = 1`, `footprint = ""`, `draw = -1`; negatives
  `label = 0`, one row per footprint, variant and draw. To train a model, take the positives of one variant and the
  negatives of the same variant, one footprint and one draw.
- `labels.json`: parameters, grid size, per event `polygons`, `positives` per variant, `candidates` per footprint,
  `short`, `reactivated_positives`, and `slope_deg` (n, P5, median, P95, share below 5°) of positives and negatives.
- `audit.json`: `footprints` (area_km2, n_inside / n_landslides per variant), `area_frequency`, `overlaps`.

Pilot result (2026-11-01; area 107.56–108.20° E, 15.00–15.21° N; grid 2270 × 768 cells of 30 m):

| Event | Polygons | Positives scarp / upper / centroid | Candidates `near` / `hull` | Reactivated | Slope, scarp positives (median) | Slope, `near` negatives (median) |
|---|---|---|---|---|---|---|
| Ketsana | 1 125 | 1 111 / 2 277 / 1 106 | 532 435 / 883 671 | 0 | 29.0° | 21.8° |
| Molave | 895 | 864 / 1 011 / 872 | 284 180 / 745 167 | 46 | 26.2° | 22.5° |

L0 on the whole inventory (`l0/l0_audit.md`): `near` footprints 2 501 km² (Ketsana), 480 km² (Podul), 1 772 km²
(Molave); power-law tails α ≈ 2.45–2.59; no rollover resolved; Ketsana less complete below about 1 000 m².

## 6. Quality checks

- `n_inside` close to `n_landslides` for `near` and `hull` (L0: 8 742 of 8 744 Ketsana landslides inside;
  `hull_shrunk` loses 27 % of Podul's, which is why it was dropped).
- Footprints checked by eye against PlanetScope / Sentinel-2 images of each event: straight, image-like edges mean
  unmapped land.
- Positives per event close to the polygon count in the area (scarp variant); `short` empty.
- The slope distributions: positives clearly steeper than negatives, few positives below 5° (scarp: 0.2–0.5 %).
  Report the share of negatives below 5° (1.6–3.7 % here): they inflate the AUC.
- Quicklooks (`labels_<event>.png`): scarp triangles at the upper end of the polygons, negatives off the polygons.
- Area–frequency tail exponent in the usual range (~2.4, Malamud et al. 2004) and the completeness limit noted.

## 7. Limits and pitfalls

- **Unknown mapping extents**: negatives where nobody mapped teach the model that unmapped slopes are stable. Use
  `near`, and keep `hull` as the sensitivity test.
- **Inventory resolution differs between events** (RapidEye 5 m in 2009, PlanetScope 3 m in 2020): compare events on
  landslides ≥ 1 000 m² too.
- **Event dates are storm dates**, not per landslide; the Molave set likely spans the October 2020 storm sequence.
- **DEM after Ketsana** (GLO-30, 2011–2015): old scars may be in the terrain.
- **Negatives are only kept off the polygons of the same event**: a cell on an older event's polygon can be a
  negative; `reactivated` flags only positives.
- `audit` always runs on the whole workspace inventory, not on the study area, but writes into the study folder.
- The study area is not built by the CLI; `[area] layer` defaults to `pilot`.
- No predictors, models, rainfall thresholds or InSAR features are computed yet.

## 8. On a new area or sensor

- New inventory: write a builder like `build_das2024` (or convert to the same GeoPackage: layer `polygons` with
  `event`, `date`, `src_fid`, `area_m2`, `province`, `valid`), then point `[inventory] polygons` at it. `audit` reads
  `inventories/landslide/central_vn_das2024.gpkg` by name: a new inventory needs that path or a code change.
- New region of reported events: `VN_BBOX`, the boundaries file and the province names are Vietnam-specific.
- Keep: 30 m cells for GLO-30, scarp positives, 60 m buffer (two cells), 1:1 ratio, 10 draws, `near` footprints.
- For the north of Vietnam there is no open polygon inventory yet (Yagi 2024 needs mapping; VIGMR points on request).

## 9. References

- Code: `src/geoeyes/landslide/inventory.py`, `src/geoeyes/landslide/labels.py`, `src/geoeyes/landslide/study.py`,
  `src/geoeyes/cli/main.py` (`cmd_landslide`), `src/geoeyes/ml/layers.py` (`Grid`).
- Workspace: `inventories/landslide/SOURCES.md` (datasets checked), `studies/landslide_central_vn/l0/l0_audit.md`
  (L0 report and gate decisions).
- Research note: [../research/landslide-susceptibility.md](../research/landslide-susceptibility.md) (plan L0–L8,
  hypotheses, parameters).
- Das, R. (2024). Mapped landslides for Typhoon Ketsana, Molave and Tropical Storm Podul in central Vietnam
  [dataset]. Zenodo. https://doi.org/10.5281/zenodo.15596033
- Steger, S., Brenning, A., Bell, R., Glade, T. (2016). NHESS 16, 2729–2745. https://doi.org/10.5194/nhess-16-2729-2016
- Malamud, B. D., Turcotte, D. L., Guzzetti, F., Reichenbach, P. (2004). ESPL 29, 687–711.
  https://doi.org/10.1002/esp.1064
- Clauset, A., Shalizi, C. R., Newman, M. E. J. (2009). Power-law distributions in empirical data. SIAM Review 51,
  661–703. https://doi.org/10.1137/070710111
- Brenning, A. (2005). NHESS 5, 853–862. https://doi.org/10.5194/nhess-5-853-2005
- Kirschbaum, D., Stanley, T. (2018). Earth's Future 6, 505–523. https://doi.org/10.1002/2017EF000715
