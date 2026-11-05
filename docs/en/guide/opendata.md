# Open data: finding and processing open SAR stacks

For people who want to process high-resolution X-band data without buying it. It lists the open catalogs GeoEyes
searches, how a repeat-pass stack is recognised, and the steps from a search to a processed project. Design:
[ADR-028](../architecture/decisions.md).

## Contents

1. [The catalogs](#1-the-catalogs)
2. [What makes a stack](#2-what-makes-a-stack)
3. [From the command line](#3-from-the-command-line)
4. [In the web app](#4-in-the-web-app)
5. [What the acquire phase downloads](#5-what-the-acquire-phase-downloads)
6. [ICEYE SLC-COG](#6-iceye-slc-cog)
6b. [Umbra SICD](#6b-umbra-sicd)
7. [Known stacks (October 2026)](#7-known-stacks-october-2026)
8. [Source Cooperative: flood and exposure layers](#8-source-cooperative-flood-and-exposure-layers)

## 1. The catalogs

| Source | Catalog (static STAC on AWS, CC-BY 4.0) | Complex product | GeoEyes |
|---|---|---|---|
| ICEYE Open Data | `iceye-open-data-catalog` (us-west-2) | SLC-COG: amplitude + phase GeoTIFF, STAC metadata | processed (`iceye`) |
| Capella Space Open Data | `capella-open-data` (us-west-2) | SLC GeoTIFF + `*_extended.json` | processed (`capella`, method `ps_lite`) |
| Umbra Open Data | `umbra-open-data-catalog` (us-west-2) | SICD NITF (PFA spotlight, 0.15 m) | processed (`umbra`, method `ps_lite`) |

No account is needed. Credit the provider ("© ICEYE", "© Capella Space", "© Umbra") in what you publish. ICEYE warns
that its open catalog may hold experimental products.

## 2. What makes a stack

Interferometry needs repeat passes: the same orbit (within a few hundred metres), the same beam, the same look.
From the STAC items alone, scenes are grouped when they share:

- the source and the **satellite** (ICEYE, Umbra: each satellite has its own ground track) or the provider's
  **repeat ground track** (Capella `capella:rgt_id`, which may span several satellites);
- the imaging mode, pass direction and look side;
- an incidence within **±1°** and a look azimuth within **±3°** of the stack's first scene;
- a footprint overlapping the first scene's by **at least 50 %** of the smaller one.

The perpendicular baselines are only known once the products are read: `build_stack` writes them to the log and
leaves out the scenes outside the reference geometry (`check_geometry`). A stack id is built from its first scene
and does not depend on the search area: `iceye:x53-sm-ar-26-28.2n016.7w` = ICEYE-X53, stripmap, ascending,
right-looking, 26° incidence, centred at 28.2° N 16.7° W. Capella ids end in a short hash of the ground track.

## 3. From the command line

```
geoeyes opendata sync                                    # index every catalog (~1–2 min the first time)
geoeyes opendata sources                                 # scenes per source, last sync
geoeyes opendata stacks --supported                      # every stack GeoEyes can process
geoeyes opendata stacks --bbox=-16.68,28.24,-16.60,28.30 # stacks whose scenes cover this area
geoeyes opendata show iceye:x53-sm-ar-26-28.2n016.7w     # dates, platforms, incidence, footprint
geoeyes opendata project iceye:x53-sm-ar-26-28.2n016.7w tenerife_iceye --bbox=-16.645,28.215,-16.630,28.228
geoeyes run tenerife_iceye
```

Write `--bbox=` with the equals sign: a value starting with `-` (western longitude) would otherwise be taken for an
option. `geoeyes opendata fetch <id> --bbox=...` downloads the scenes without creating a project
(`<workspace>/archive/<sensor>/<sensor>-<asc|desc>/`).

The project written by `opendata project`:

```toml
[aoi]
bbox = [-16.645, 28.215, -16.63, 28.228]

[[tracks]]
sensor = "iceye"
direction = "ascending"

[acquire]
opendata = "iceye:x53-sm-ar-26-28.2n016.7w"
# opendata_margin_m = 500        # around the AOI when the product can be cut (ICEYE)
# date_range = [2026-02-18, 2026-02-21]
# max_per_month = 0
```

## 4. In the web app

Tab **Open data** of the **Projects** page (top bar; also the link "Start from open data" above the project list). Nothing to search: the server indexes the catalogs by itself the first time the page
opens and then once a day (*Refresh the list* forces it), and lists every stack GeoEyes can process, named by place
("Los Angeles, California, United States"; names from OpenStreetMap, Nominatim or Photon), most dates first. On the
map each stack is a dot (ICEYE blue, Capella orange, Umbra violet; size = number of dates), its footprint appears when
zoomed in. The filters (text, source, mode, "only over an area") are optional.

Click a stack (in the list or on the map): the map zooms to it, an area to process is proposed (ICEYE: ~3 km around
the centre, cut on download; Capella: most of the footprint, whole scenes are downloaded anyway) with the download
size, and a project name is filled in. *Draw another area* to change it, then *Process this stack*: the project is
written and its pipeline opens.

## 5. What the acquire phase downloads

With `[acquire] opendata`, the `acquire` phase takes the stack's scenes that **cover the whole AOI** (then
`date_range` and `max_per_month`) and writes one folder per date, `<archive>/<sensor>/<track>/YYYYMMDD/`, with
`opendata.json` once complete. A folder already fetched with the same item, AOI and margin is not fetched again;
a new date on the catalog (after `geoeyes opendata sync`) re-runs the phase for that date only, and `build_stack`
adds it incrementally.

| Source | Downloaded | Size per date |
|---|---|---|
| ICEYE | the window covering the AOI + `opendata_margin_m`, read with HTTP range requests from the COG | ~10 MB for 1.5 km × 1.5 km, ~3.6 GB for a whole stripmap scene |
| Umbra | the window covering the AOI + `opendata_margin_m` (default 50 m), read row by row with HTTP range requests from the SICD NITF | ~30 MB for 200 m × 200 m, ~7 GB for a whole scene |
| Capella | the whole SLC and its extended metadata | ~0.3–1.5 GB |

The ICEYE window is computed with the product's RPC model at the lowest and highest DEM height over the AOI
(`[stack] dem`): on a volcano the range window grows with the relief.

## 6. ICEYE SLC-COG

- Two uint16 bands `AMPLITUDE` and `PHASE` with GDAL scale / offset (phase −π..π): sample = amplitude · e^(j·phase).
  The 16-bit phase step is 0.005°, negligible.
- The raster is stored **shadows-down**: TIFF rows are range samples (near → far), TIFF columns azimuth lines
  (early → late). The reader transposes to the GeoEyes convention (lines = azimuth).
- Geometry: `iceye:zero_doppler_start_datetime`, 1 / `iceye:processing_prf` per line, `iceye:range_near`,
  `sar:pixel_spacing_range` (slant), precise state vectors in ECEF, Doppler centroid polynomial. Checked against
  the RPC delivered with the product: < 0.3 pixel in both directions.
- A cut scene carries `geoeyes:crop` (row / column of the cut in the original TIFF) in its `*_SLC.json`.

## 6b. Umbra SICD

- SICD = NITF 2.1 with the complex image (I / Q float32) and the SICD XML. GeoEyes reads both itself
  (`sensors/sicd`), from a local file or straight from S3 (range requests). The Umbra STAC items carry no file links:
  the SICD is found under `sar-data/task-data/<umbra:task_id>/`.
- Umbra images are **spotlight, polar format (PFA) on a slant plane**, not a zero-Doppler grid: the geometry follows
  the SICD image projections (R / Rdot contour at the centre-of-aperture time), checked against NGA's sarpy. The
  stack is built by `processing/stack/native/sicd_stack.py` (design: [ADR-029](../architecture/decisions.md)).
- Expect little coherence except on stable structures: the repeat passes differ in look angle by 1–2° for an angular
  aperture of ~4.5°, the baselines reach kilometres (height ambiguity below a metre for 7 km), and water / container
  yards change between dates. Keep the AOI small (0.15 m pixels: 200 m × 200 m is already 1300 × 1500 pixels) and
  on buildings, roads, quays.

## 7. Known stacks (October 2026)

From `geoeyes opendata stacks` on 2026-10-28 (72 stacks of ≥ 3 dates: 65 Capella, 2 ICEYE, 5 Umbra):

| Stack | Dates | Period | Gap | Notes |
|---|---|---|---|---|
| `iceye:x53-sm-ar-26-28.2n016.7w` | 19 | 2026-02-11 → 03-01 | 1 d | Tenerife (Teide), stripmap 3 m, B⊥ −873..+75 m, ICEYE interferograms / coherence included |
| `iceye:x53-sm-dl-14-21.2s055.6e` | 4 | 2026-03-19 → 05-27 | 5 d | Réunion (Piton de la Fournaise), steep incidence 14.5° |
| Capella, 34.8° N 118.1° W | 95 | 2024-11 → 2025-11 | 3 d | spotlight, the longest open stack |
| Capella, 19.4° N 155.3° W | 35–60 | 2025 | 3 d | Kīlauea, ascending and descending |
| `capella:c14-sm-al-41-19.4n099.0w-…` | 18 | 2024-06-26 → 08-15 | 3 d | Mexico City, stripmap (the `mexico_capella` data) |

## 8. Source Cooperative: flood and exposure layers

[Source Cooperative](https://source.coop) hosts about 560 open products, all public over HTTPS
(`https://data.source.coop/<account>/<product>/...`, no account or key). It holds no SAR stack GeoEyes can process,
but several layers that set the motion against floods and against people and buildings. GeoEyes indexes the
whole catalog (`<workspace>/cache/opendata/source_coop.json`, refreshed daily) and reads six layers over an area
only (COG range requests; Parquet row groups filtered on their bbox), cached in `<workspace>/cache/sourcecoop/`:

| Key | Product | Use in GeoEyes |
|---|---|---|
| `gsw-monthly` | `epoch/jrc-global-surface-water-monthly` (30 m, 2017-2024) | water of an event month against a dry month |
| `glofas-depth` | `nlebovits/jrc-glofas` (90 m, RP 10-500 yr) | river flood depth scenario (no dykes: an upper bound in a diked delta) |
| `chirps-daily` | `wfp/chirps-rnl-daily` (0.05°, 1981-) | daily rainfall of the event; the CHC server throttles, this mirror does not |
| `imerg` | `dynamical/nasa-imerg-analysis-late` (0.1°, 30 min, 1998-) | rain intensity of the event, half hour by half hour (Icechunk store) |
| `ghsl-pop` | `wfp/jrc-ghsl-pop` (3", 2025) | residents on subsiding ground and in the flood |
| `gba-buildings` | `tge-labs/globalbuildingatlas-lod1` | a height for every building: fills the Overture heights in `geoeyes risk` |

```
geoeyes coop search lũ lụt                      # the catalog (Vietnamese words of the usual topics are understood)
geoeyes coop layers
geoeyes coop get gsw-monthly --bbox 105.7,20.95,105.95,21.1 --month 2024-09
geoeyes coop get chirps-daily --bbox 105.7,20.95,105.95,21.1 --from 2024-09-05 --to 2024-09-12
geoeyes coop get glofas-depth --bbox=-99.25,19.3,-99.0,19.5 --rp 100      # "=" when the bbox starts with "-"
geoeyes coop get imerg --bbox 105.7,20.95,105.95,21.1 --from 2024-09-06 --to 2024-09-08
geoeyes exposure hanoi_s1 --set flood_month=2024-09 --set glofas_rp=100
```

`geoeyes exposure` (`[postprocess.exposure]`) writes `analyses/exposure/<product>/exposure.json` and
`exposure_cells.parquet`: people and buildings per class of vertical rate (breaks 5 / 10 / 20 / 50 mm/yr, on the
GHS-POP cells, at least 3 points a cell), the people of cells without points apart; with `flood_month`, the flooded
area (water that month where `dry_month`, default six months earlier, saw land), the people in it, the median rate
of the points on flooded and dry ground and the month's rainfall; with `glofas_rp`, the people in the modelled
river flood. `geoeyes risk` takes the missing heights from GlobalBuildingAtlas (`gba_heights = false` turns it
off): in Hanoi Overture has a height for 1.4 % of the buildings, 67 % with GlobalBuildingAtlas.

IMERG is published as an Icechunk 2 store, and icechunk 2 needs Python 3.12. When the GeoEyes environment is older,
a small separate environment runs the reader (`geoeyes/opendata/imerg_reader.py`, no GeoEyes import) and
`GEOEYES_ICECHUNK_PYTHON` points at it:

```
conda create -p <envs>/icechunk -c conda-forge python=3.12 "icechunk>=2.3" xarray zarr numpy
GEOEYES_ICECHUNK_PYTHON=<envs>/icechunk/python.exe            # in .env
```

`geoeyes exposure` with `flood_month` adds the most intense half hour of the month (`rain_peak_30min`, AOI mean,
UTC); without the interpreter it is left out and the daily CHIRPS rainfall stands alone. IMERG "late" is
satellite-only (the gauge adjustment comes with the "final" run, months later): for Yagi over Hanoi it gives
79 mm on 7 September against 226 mm for CHIRPS. Read it for the timing and the intensity pattern of the rain, and
the daily totals from CHIRPS.

What the layers can and cannot say. Global Surface Water is a monthly composite of Landsat and Sentinel-2: for
Typhoon Yagi (Hanoi, September 2024) it maps 0.05 km² of new water over the city while CHIRPS gives 680 mm in the
month (226 mm on 7 September); cloud and the short life of street flooding hide it. Urban floods need the SAR
amplitude of the day (docs/vi/research/paper-ideas.md §4). GloFAS ignores the dykes: over Hanoi it floods the
protected plain (1.3 million people for the 100-year flood), a bound, not a forecast.

In the web app: Projects → Source Cooperative (search, the layers and their credits); In-depth analysis → Thematic analysis → layer "People and buildings exposed" (run with a flood month and a GloFAS return period, the cells on the map coloured by sinking class, flood share or river-flood depth, and the counts in the legend).

