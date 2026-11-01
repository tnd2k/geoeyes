# Reported floods: an inventory to set against the motion

Flooding in HCMC is reported in lists of place names. The traffic police (PC08) and the Department of Construction publish them each rainy season, organised by cause (heavy rain, high tide). GeoEyes keeps those lists as an inventory for the whole workspace, places the locations on OpenStreetMap and shows them on the results map. This lets you set where the city floods against where the ground moves.

## The files

```
<workspace>/inventories/flood/<region>.csv       one row per reported location, as announced (editable)
<workspace>/inventories/flood/<region>.geojson   the same rows placed on the map
```

Each row has these columns:

| Column | What it holds |
|---|---|
| `text` | The announced wording, kept verbatim |
| `cause` | `rain`, `tide` or `rain_tide` |
| `kind` | `segment`, `junction`, `street`, `address` or `place` |
| `street`, `from`, `to`, `cross`, `place`, `ward` | The parts read from the wording |
| `reported`, `source`, `url` | When the list was published, who published it, and where |
| `depth_m`, `notes` | Flood depth if given, and any other remarks |
| `geom_wkt` | A geometry set by hand (see [Correcting a row](#correcting-a-row)) |

The CSV opens in Excel with Vietnamese text intact (it is saved as UTF-8 with a byte-order mark).

Two regions are defined:

- **`hcmc`** covers the merged city, including the former Bình Dương and Bà Rịa–Vũng Tàu.
- **`hanoi`** covers the merged capital. It is inland, so its outlook uses rain only.

The Hanoi Drainage Company writes its bulletins as sentences, for example `Lưu vực sông Nhuệ: Dương Đình Nghệ – Nam Trung Yên (sau Keangnam), Hoa Bằng (ngõ 99), …`. Import these with `--prose`:

```
geoeyes floods import bulletin.txt --prose --region hanoi --reported 2026-09-17 --source "Thoát nước Hà Nội"
```

In prose mode:

- the basin before ":" goes to `notes`;
- a bare name is read as a street;
- "A – B" is read as a junction;
- a stretch in brackets ("(từ … đến …)") makes the row a segment;
- a landmark in brackets ("(trường Chu Văn An)") places the row on the street, near that landmark.

A street name that exists in several districts is placed near the other spots of the same bulletin and basin, when those spots lie within 3 km of one of the namesakes.

Use only sources that allow it. nuoclen.com, for instance, forbids automated access to its API in its `robots.txt`, so GeoEyes does not read it.

## Adding a list

1. Copy the list from the announcement into a text file. Keep the headings and the `-` / `+` bullets as published.
2. Import the file:

   ```
   geoeyes floods import list.txt --reported 2026-10-06 --source "PC08 Công an TP.HCM" --url <article>
   ```

3. Place the new rows on the map (the command is described in [Placing rows on the map](#placing-rows-on-the-map)):

   ```
   geoeyes floods locate
   ```

How the import reads the text:

- **Cause.** A heading containing "mưa" sets the cause of the items below it to rain, "triều" to tide, and both words to rain and tide. Use `--cause` to set one cause for the whole file instead.
- **Items under a street.** A line such as `- Đường X:` opens a group. The `+` lines that follow, and `-` lines that start with "Đoạn" or "Giao", are locations on street X.
- **Wording recognised in an item:**

  | Wording | Read as |
  |---|---|
  | "Đường A, (đoạn) từ B đến C" | `segment` on street A |
  | "Giao lộ A - B", "Đường A - B", "Giao B" (under street A) | `junction` |
  | "Số 69 Trịnh Thị Dối", "Trước số 139" | `address` |
  | "Đường X" | `street` |
  | Anything else ("Ngã tư Bảy Hiền", "Chân cầu Lò Gốm") | `place` |

- **Ward.** A ward in brackets, such as "(phường Tam Bình)", is stored in `ward`. It is used to choose between streets that share a name.
- **Repeats.** Importing the same list twice adds nothing, because a row's id is built from its text, cause, date and source.

## Placing rows on the map

`geoeyes floods locate` reads the street geometry from OSM through Overpass and searches named places with Nominatim. Both are cached in `cache/osm/flood`. It records how each row was placed in `located`:

| `located` | Meaning |
|---|---|
| `exact` | The reported stretch, cut between the crossings with B and C, or the junction where the two streets meet (within 40 m) |
| `place` | Placed at a named place found by Nominatim (a market, a bridge, a roundabout), on the street if it lies within 400 m of it |
| `approx` | Only near the reported spot: the whole street, or a segment with only one end found |
| `ambiguous` | The street name exists in several parts of the city and no ward was given, so the row is not placed |
| `none` | Not found on OSM |
| `manual` | Taken from `geom_wkt` |

Nothing is guessed silently. A row that cannot be placed stays in the list without a geometry, and the map panel counts it.

## Correcting a row

To place a row by hand, put a WKT geometry in its `geom_wkt` column, then run `locate` again. For example:

- `POINT (106.7012 10.7769)`
- `LINESTRING (106.70 10.77, 106.71 10.78)`

The row is then marked `manual`.

## On the results map

The **Reported floods** button on the Explorer toolbar shows the inventory over the products:

- **Lines** are street stretches and **dots** are junctions and places. Blue means rain, purple means tide, and teal means both.
- **Faded features** are only approximately placed. Tick *only locations placed precisely* to hide them.
- **The panel** shows the velocity of the top product around each location: the median of its points within the chosen radius, the ring around the location (radius to 500 m), and the share of the product's points moving away from the satellite faster. Click a row to zoom to it and see its source.

The same figures come from `GET /api/projects/{name}/products/{pid}/floods?radius=100`.

## Flood outlook for the next 24 hours

With the layer on, a **Flood outlook · 24 h** panel opens on the left of the map. It shows the whole city by default and the selected location once you click one. It is a reference only. There is no hydraulic model and no gauge behind it, and its first card says so.

**Inputs:**

- **Rain:** the hourly forecast at each location from Open-Meteo, which blends several weather models.
- **Tide:** the hourly sea level off the river mouth from Open-Meteo Marine. This is a model value at sea, not the Phú An gauge; the river follows it a few hours later.
- **Subsidence:** with a product on the map, the median line-of-sight velocity of its points around the location.

**Score (0–100), designed to be transparent:**

1. A rain part *R* combines the rain over 24 h (full at 50 mm) and the heaviest hour (full at 25 mm). It is then scaled by the highest rain probability.
2. A tide part *T* places the coming peak between the median daily high tide of the last 30 days (0) and the highest tide of the month (1, a spring tide).
3. The two parts are weighted by the location's reported cause:

   | Cause | Rain weight | Tide weight |
   |---|---|---|
   | Rain | 0.8 | 0.2 |
   | Tide | 0.2 | 0.8 |
   | Both | 0.5 | 0.5 |

4. Subsidence adds 3, 6 or 10 points when the ground moves away from the satellite at 5, 10 or 20 mm/yr or more. For the whole city, the velocity is the median over its reported flood spots that the product covers (at least 3).

**Levels and depth classes:**

| Score | Level | Depth class |
|---|---|---|
| Below 20 | Low | Flooding unlikely |
| 20 to 44 | Watch | Possibly under 20 cm |
| 45 to 69 | High | Possibly 20–40 cm |
| 70 and above | Very high | Possibly over 40 cm |

The depth class is only a rough label tied to the level.

**Risk window.** It covers the hours of the next 24 that count for the location's cause: rain of at least 2 mm with a probability of at least 40 %, or a tide in the upper 40 % of the month's range.

**Map colours.** Locations are coloured by today's level (*colour the spots by today's risk*). Untick it to colour them by cause.

The data comes from `GET /api/floods/outlook?project=&product=`.

**Caching.** None of this is recomputed on a page reload:

| What | Where it is kept | Recomputed when |
|---|---|---|
| Velocity around the locations | On disk, `cache/web/<product>/floods_r<radius>.json` | The inventory or the product changes |
| Outlook | On disk, `cache/floods/` | After 30 minutes |
| Inventory, statistics and outlook | In the browser (local storage) | The browser shows them at once on reload, then refreshes them when they are stale |

## Reading the comparison

- **Location and street.** A reported location is where the flooding was noticed, often a low point of a road. It is not the outline of the flooded area. Whole streets (`approx`) mix stretches that flood with stretches that do not, so prefer the `exact` rows for any figure.
- **Velocity is along the line of sight (LOS).** Negative velocity is away from the satellite. On flat ground, which describes most of HCMC, this is mainly subsidence. Use `decompose` with a second geometry to separate vertical from horizontal motion.
- **Contrast with the ring.** A location subsiding faster than the ring around it is more telling than one that subsides like its whole district. Flooding also has causes that InSAR cannot see: drainage capacity, tide level, and paving.
