# Skill: reported flood locations against subsidence, and today's flood outlook

> Does the ground subside where the city floods? Keep the officially reported flood spots of HCMC and Hanoi as a
> located inventory, read the velocity of a product around each one, and see a transparent 24-hour outlook from
> forecast rain, tide and subsidence. Status: operational (inventory, map, outlook); the outlook is a reference, not
> a flood forecast. Last checked 2026-11-01. CLI: `geoeyes floods import | locate | list`. Web app: Explorer →
> toolbar button **Reported floods** (map, tooltips, panel **FLOOD OUTLOOK · 24 H**); also on the map composer.

## 1. When to use it

- To set the places a city announces as flooded (traffic police PC08, Department of Construction in HCMC; Hanoi
  Drainage Company bulletins) against the InSAR motion: are flood spots on faster-sinking ground than their
  surroundings?
- To keep one inventory for the whole workspace, editable in Excel, rebuilt and re-located after each new list.
- To give a same-day, explainable "how likely is flooding at this spot" from free forecasts.
- Not for flood extent or depth mapping (a reported location is a spot, often a road low point), and not as a
  warning service: no hydraulic model, no drainage, no gauge. For flooded area and people exposed use
  [exposure-and-flood-layers.md](exposure-and-flood-layers.md).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Announcement text | yes | copy the list from the official article (PC08 Công an TP.HCM, Sở Xây dựng; Công ty Thoát nước Hà Nội) | a UTF-8 text file anywhere, passed to `geoeyes floods import <file>` | keep headings ("mưa", "triều") and the `-` / `+` bullets as published; Hanoi bulletins are sentences: `--prose` |
| Metadata of the list | recommended | the article | `--reported YYYY-MM-DD`, `--source "<who>"`, `--url <article>` | part of each row's id: the same list imported twice adds nothing |
| Region | yes | `hcmc` (default) or `hanoi` | `--region` | the only two defined (`REGIONS`: search bbox and city name) |
| Inventory | produced | `geoeyes floods import` | `<workspace>/inventories/flood/<region>.csv` (UTF-8 with BOM, opens in Excel) | editable; `geom_wkt` overrides the placement |
| Located inventory | produced | `geoeyes floods locate` | `<workspace>/inventories/flood/<region>.geojson` | cache of OSM and Nominatim answers in `<workspace>/cache/osm/flood/` |
| InSAR product | optional | `geoeyes run` | shown on the Explorer map (the top product) | velocity around each spot; subsidence bonus of the outlook |
| Network | yes | Overpass (`overpass-api.de`), Nominatim (1 request/s), Open-Meteo forecast and Marine | — | only for `locate` and the outlook |

Do not read sources that forbid it (nuoclen.com forbids automated access in its `robots.txt`).

Checklist:

- [ ] The text file is UTF-8 and keeps the headings and bullets.
- [ ] `--region hanoi` (and `--prose` for Drainage Company bulletins) for Hanoi; HCMC is the default.
- [ ] `--reported`, `--source`, `--url` given.
- [ ] After import, run `locate` **with the same `--region`** (it also defaults to `hcmc`).
- [ ] Rows marked `ambiguous` or `none` reviewed; `geom_wkt` filled where you know the place.

## 3. Method

### 3.1 Import (`parse_list`, `parse_prose`, `parse_item`)

- **Cause**: a non-bullet heading containing "mưa" → `rain`, "triều" → `tide`, both → `rain_tide`; `--cause`
  forces one cause; `--prose` defaults to `rain`.
- **Groups**: `- Đường X:` opens a group; the following `+` lines, and `-` lines starting with "Đoạn", "Giao", "Từ",
  "Hướng", "Trước", "Số", are on street X.
- **Kinds**: "Đường A, (đoạn) từ B đến|về|ra|tới C" → `segment`; "Giao lộ A - B", "Ngã tư A - B", "Đường A - B",
  "Giao B" under A → `junction`; "Số 69 Trịnh Thị Dối", "Trước số 139" → `address`; "Đường X", "Quốc lộ 50" →
  `street`; anything else → `place`. A ward in brackets ("(phường Tam Bình)") goes to `ward`; other brackets to
  `notes`.
- **Prose** (Hanoi): the text before ":" (basin, if shorter than 60 characters) goes to `notes`; items split on ","
  and ";" outside brackets; a bare name is a street; "A – B" a junction; "(từ … đến …)" makes a segment; a landmark in
  brackets places the row on the street near it; "phường/xã …" items join the previous one.
- **Row id** = first 10 hex of SHA-1 of `region|cause|text|reported|source`; existing ids are skipped.

### 3.2 Locate (`locate`, `Locator`)

- Street names (and their aliases: "30-4" → "30 tháng 4", "ĐT744" → "đt 744", "tỉnh lộ 744", "QL1" → "quốc lộ 1",
  "35" ↔ "số 35") are asked from Overpass in batches of 25 (`name`, `alt_name`, `old_name`, `ref` of highways, with
  "Đường/Phố/Ngõ" prefixes), cached per name; places from Nominatim (bounded to the region, `countrycodes=vn`,
  1.1 s between requests), cached per query.
- **junction**: the nearest meeting of the two streets within `JUNCTION_TOL_M` = 40 m → `exact`; else Nominatim on
  "A B" → `place`; else `none`.
- **segment**: each end is a junction with the street, else a Nominatim place within `ENDPOINT_TOL_M` = 400 m of the
  street, projected on it. With both ends (≥ 5 m apart), the stretch between them on every part of that street
  (both carriageways; parts within `SAME_STREET_GAP_M` = 2 km are one street) → `exact` if both ends are junctions,
  else `approx`. One end only → that point, `approx`. No end → the whole street.
- **street**: all its parts → `approx`. When the name exists in distinct places: if one group is ≥ 2 km long and
  ≥ `DOMINANT` = 4 × the next, it is taken; otherwise the group nearest the `ward` (via Nominatim), or `ambiguous`.
- **address / place**: Nominatim on "place street"; snapped to the street if within 400 m → `place`; else the whole
  street → `approx`.
- **geom_wkt** in the CSV → `manual`, no search.
- **Second pass** for `ambiguous`: the namesake nearest the median of the other located spots of the same bulletin
  (same `reported`, `source` and first note, at least 2) within 3 km → `approx`.

### 3.3 Velocity around a spot (`near_product`)

Lines are densified every 10 m. Points within `radius_m` (API default 100 m, clamped to 20–1000 m; the Explorer uses
100 m) give `n`, `vel_median`, `vel_p10` and `rank` = share of the product's points with a lower velocity than the
median (more negative = away from the satellite faster). The ring `radius_m`…`ring_m` (500 m) gives `ring_median`
and `contrast = vel_median − ring_median`. Velocities are LOS (mm/yr) of the web point cache of the product.

### 3.4 Outlook (`flood_outlook`)

For the next 24 hours from the current hour (local time, `Asia/Bangkok`):

- Rain from Open-Meteo (hourly precipitation and probability, forecasts shared on a 0.05° grid):
  `R = (0.5·min(rain_24h/50 mm, 1) + 0.5·min(max_hourly/25 mm, 1)) · (0.5 + 0.5·max_probability)`.
- Tide (HCMC only, Open-Meteo Marine sea level at 107.08° E, 10.33° N, a model off the river mouth):
  `T = clip((peak − median daily high of the last 30 days) / (highest of the last 30 days and next 3 − that median), 0, 1)`
  (the denominator is at least 0.1 m).
- `score = min(100, 100·(w_R·R + w_T·T) + bonus)`, weights by cause: rain 0.8 / 0.2, tide 0.2 / 0.8, both or
  unknown 0.5 / 0.5; Hanoi (no tide point) rain only 1.0 / 0. Bonus +3 / +6 / +10 for a median velocity around the
  spot ≤ −5 / −10 / −20 mm/yr. City level: the city centre's rain, cause `rain_tide` (Hanoi `rain_only`), and the
  median velocity over the city's spots covered by the product (at least 3).
- Levels: < 20 `low`, < 45 `watch`, < 70 `high`, else `very_high`; depth class `unlikely`, `< 20 cm`, `20–40 cm`,
  `> 40 cm` follows the level only.
- Risk window: hours with rain ≥ 2 mm at ≥ 40 % probability (if w_R ≥ 0.5) or tide ≥ median + 0.6·(range) (if
  w_T ≥ 0.5).

## 4. Steps

1. **Import a list.** `geoeyes floods import list.txt --reported 2026-10-06 --source "PC08 Công an TP.HCM" --url <article>`
   (HCMC), or `geoeyes floods import bulletin.txt --prose --region hanoi --reported 2026-09-17 --source "Thoát nước Hà Nội"`.
   Instant. Appends to `inventories/flood/<region>.csv`; prints locations read, new rows, total.
2. **Check the CSV** in Excel: `kind`, `street`, `from`, `to`, `cross` as expected; fix the wording or add
   `geom_wkt` (e.g. `POINT (106.7012 10.7769)`, `LINESTRING (106.70 10.77, 106.71 10.78)`).
3. **Locate.** `geoeyes floods locate --region <hcmc|hanoi>` → `inventories/flood/<region>.geojson`; prints the
   counts per `located`. First run: Overpass batches plus about one second per new Nominatim query; later runs
   read the cache (seconds).
4. **List.** `geoeyes floods list`: every located row of every region (id, cause, located, date, text).
5. **Web app.** Explorer → show a product → **Reported floods**. Lines = segments, dots = junctions and places;
   blue rain, purple tide, teal both; faded = approximately placed. Hover: points within 100 m, median velocity,
   ring median. The **FLOOD OUTLOOK · 24 H** panel shows the city, or the clicked spot; tick "colour the spots by
   today's risk (else by cause)". Results are cached: velocity in `cache/web/<product>/floods_r<radius>.json`
   (recomputed when the inventory or the product changes), outlook in `cache/floods/` (30 minutes).
6. **API.** `GET /api/floods`, `GET /api/projects/{name}/products/{pid}/floods?radius=100`,
   `GET /api/floods/outlook?project=&product=&radius=`.

## 5. Outputs and how to read them

- `<region>.csv` columns: `id, region, cause, kind, street, from, to, cross, place, ward, text, reported, source, url,
  depth_m, geom_wkt, notes`. `text` is the announced wording, verbatim.
- `<region>.geojson`: the same rows with a geometry (or null) and `located` = `exact` | `place` | `approx` |
  `ambiguous` | `none` | `manual`.
- Per spot (API): `n`, `vel_median`, `vel_p10`, `rank`, `ring_n`, `ring_median`, `contrast`; for the set:
  `product_median`, `n_located`, `n_with_points`, `median_of_rows`.
- Outlook: per spot and per city `score`, `level`, `depth`, `window`, `rain_24h_mm`, `rain_max_mm_h`,
  `rain_prob_max`, `tide_peak_m`, `tide_peak_time`, `parts` (R, T, weights, bonus), `velocity_mm_yr`, hourly rain.

Reading: a spot sinking faster than its ring (`contrast` < 0) says more than one sinking like its whole district.
LOS velocity on flat ground is mostly vertical; separate it with [decompose-and-soft-soil.md](decompose-and-soft-soil.md).

State of the workspace inventory (files of 2026-10-30): HCMC 134 rows (rain 83, tide 39, rain and tide 12): 37
`exact`, 12 `place`, 68 `approx`, 8 `ambiguous`, 9 `none`. Hanoi 94 rows: 6 `exact`, 13 `place`, 50 `approx`, 15
`ambiguous`, 10 `none`.

## 6. Quality checks

- Share of `exact` + `place` rows: use only those for figures; `approx` whole streets mix flooding and dry stretches.
- Every `ambiguous` and `none` row looked at; a `manual` geometry where the place is known.
- A few `exact` segments checked on the map against the announced "từ B đến C".
- `n` ≥ 3 points within the radius before quoting a spot's velocity; compare `median_of_rows` with
  `product_median` and with the ring medians, not with zero (the product's reference matters).
- The outlook's first card says it is a reference; check the tide source date and that the forecast was reachable
  (an error says "weather forecast unreachable").

## 7. Limits and pitfalls

- A reported location is where flooding was noticed, not the flooded area; lists favour main roads.
- OSM names vary (prefixes, numbers, old names): unmatched names stay `none` rather than guessed.
- `locate` defaults to `hcmc`: running it without `--region hanoi` after a Hanoi import leaves Hanoi stale (`GET /api/floods`
  returns `regions[].stale` = true when the CSV is newer than the GeoJSON; the web app does not show it yet).
- The tide is a sea-level model off the river mouth, not the Phú An gauge; the river lags it by a
  few hours. Hanoi has no tide term.
- The score thresholds (50 mm, 25 mm/h, weights, bonus) are design choices, not calibrated on observed floods.
- Flooding depends on drainage capacity, paving and tide, which InSAR does not see.

## 8. On a new area or sensor

- A new city needs code: an entry in `REGIONS` (bbox, name for place searches) in `ancillary/flood_reports.py`, and
  `CENTRE`, `NAME` and, for a coastal city, `TIDE_POINT` in `ancillary/flood_outlook.py`.
- Lists in another wording: extend `parse_item` / `parse_prose`; the locating rules carry over.
- Any InSAR product works (velocities are LOS of the web point cache); a denser X-band product gives more spots with
  `n` ≥ 3 at 100 m.
- Known local habits: HCMC lists are bulleted by cause; Hanoi bulletins are prose by basin.

## 9. References

- Code: `src/geoeyes/ancillary/flood_reports.py`, `src/geoeyes/ancillary/flood_outlook.py`,
  `src/geoeyes/cli/main.py` (`cmd_floods`), `src/geoeyes/api/app.py` (`/api/floods…`),
  `webapp/src/components/FloodReports.tsx`, `webapp/src/components/FloodHub.tsx`, `webapp/src/pages/Explorer.tsx`.
- Guide: [../guide/flood-reports.md](../guide/flood-reports.md).
- Related skills: [exposure-and-flood-layers.md](exposure-and-flood-layers.md), [hazard-zoning.md](hazard-zoning.md).
- Open-Meteo forecast and Marine APIs (https://open-meteo.com); OpenStreetMap contributors (ODbL) via Overpass and
  Nominatim.
