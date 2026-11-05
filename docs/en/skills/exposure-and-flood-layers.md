# Skill: people and buildings on sinking ground and in a flood (Source Cooperative layers)

> How many people and buildings stand on ground sinking at 5, 10, 20 mm/yr or more; how many were in the flooded
> area of an event month, or would be in a modelled river flood? Open global layers from Source Cooperative read
> over the product's area only. Status: operational (screening). Last checked 2026-11-01. CLI: `geoeyes exposure`,
> `geoeyes coop sync | search | layers | get`. Web app: Projects → Source Cooperative; In-depth analysis → Thematic
> analysis → layer "People and buildings exposed".

## 1. When to use it

- To turn a velocity product into numbers a decision maker reads: residents and buildings per sinking class, and
  how many of them are not observed by InSAR.
- To set the sinking ground against a past flood (the month of an event, e.g. Typhoon Yagi, 2024-09) or a river
  flood scenario (GloFAS return period).
- To find other open layers on Source Cooperative (catalog search, also with Vietnamese words) and read one over an
  area for QGIS.
- Not for damage estimates or building-level risk (use `geoeyes risk`, [behaviour-and-risk.md](behaviour-and-risk.md)),
  not for urban flood mapping (monthly optical water misses street floods), not for flood forecasting.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| InSAR product | yes | `geoeyes run` ([insar-processing.md](insar-processing.md)) | `<project>/products/<product_id>/points.parquet` with `lon`, `lat`, `vel_los_mm_yr`, `los_u` | the analysis area is the bounding box of the points |
| GHS-POP R2023A, 2025 epoch, 3″ | automatic | `wfp/jrc-ghsl-pop` | `<workspace>/cache/sourcecoop/ghsl-pop/<bbox>.tif` | residents per ~90 m cell: the exposure cells |
| GlobalBuildingAtlas LoD1 | automatic (`buildings = true`) | `tge-labs/globalbuildingatlas-lod1`, 5° GeoParquet tiles, row groups filtered on bbox (DuckDB over HTTP) | `cache/sourcecoop/gba-buildings/<bbox>_points.parquet` (centres and heights) | failure leaves the population part alone, with a warning |
| JRC Global Surface Water monthly, 30 m | with `flood_month` | `epoch/jrc-global-surface-water-monthly`, 2017-01 … 2024-12 | `cache/sourcecoop/gsw-monthly/<YYYY-MM>_<bbox>.tif` (1 land, 2 water, NaN not observed) | event month and dry month |
| CHIRPS v3 daily (RNL), 0.05° | with `flood_month` | `wfp/chirps-rnl-daily` | `cache/sourcecoop/chirps-daily/<bbox>.json` (AOI mean and max per day) | the CHC server throttles; this mirror does not |
| NASA GPM IMERG late, half-hourly, 0.1° | optional (with `flood_month`) | `dynamical/nasa-imerg-analysis-late` (Icechunk 2 store) | `cache/sourcecoop/imerg-late/<bbox>_<from>_<to>.npz` | needs a Python ≥ 3.12 with icechunk ≥ 2 (below) |
| JRC GloFAS flood depth, 90 m | with `glofas_rp` | `nlebovits/jrc-glofas`, return periods 10, 20, 50, 75, 100, 200, 500 yr | `cache/sourcecoop/glofas-depth/rp<N>_<bbox>.tif`, tile list `tiles.json` | no dykes |
| Icechunk interpreter | optional | `conda create -p <envs>/icechunk -c conda-forge python=3.12 "icechunk>=2.3" xarray zarr numpy` | `.env`: `GEOEYES_ICECHUNK_PYTHON=<envs>/icechunk/python.exe` | without it IMERG is skipped; CHIRPS stands alone |
| Catalog index | for `coop search` | `geoeyes coop sync` (site map + public API) | `<workspace>/cache/opendata/source_coop.json` | stale after 24 h; `search` re-syncs by itself |
| Parameters | optional | `[postprocess.exposure]` in `project.toml` or `--set` | TOML | `min_points`, `breaks_mm_yr`, `buildings`, `flood_month`, `dry_month`, `glofas_rp` |

No account or key: every object is public at `https://data.source.coop/<account>/<product>/<path>`.

Checklist:

- [ ] The product has `los_u` and `vel_los_mm_yr` in `points.parquet`.
- [ ] Its reference is sound (GNSS tie or a stable reference): exposure counts depend on the zero of the velocity
      ([gnss-calibration.md](gnss-calibration.md)).
- [ ] `flood_month` is `YYYY-MM` between 2017-01 and 2024-12; `dry_month` chosen in the dry season if the default
      (six months earlier) is not dry.
- [ ] `glofas_rp` is one of 10, 20, 50, 75, 100, 200, 500, or 0.
- [ ] `GEOEYES_ICECHUNK_PYTHON` set if you want the half-hourly rain peak.
- [ ] Network access (first run reads everything; later runs use the cache).

## 3. Method

`geoeyes.hazard.exposure.run`, parameters `ExposureParams` (`[postprocess.exposure]`):

1. **Vertical rate per point**: `v_vert = vel_los_mm_yr / max(los_u, 0.2)`. This assumes the motion is vertical
   (true for most subsidence on flat ground; horizontal motion leaks into it).
2. **Cells** = GHS-POP pixels (3″, ~90 m) over the points' bounding box. A cell gets
   `v_vert_mm_yr` = median of its points' `v_vert` when it holds at least `min_points` (3); otherwise it is *not
   observed* (class −1) and its people are reported apart, not guessed.
3. **Sinking class**: `class = searchsorted(breaks_mm_yr, −v_vert, side="right")` with `breaks_mm_yr` =
   (5, 10, 20, 50) → classes `< 5` (0, which also holds stable and rising ground), `5-10`, `10-20`, `20-50`,
   `>= 50` mm/yr of sinking (GeoEyes sign: negative = sinking).
4. **Counts**: people per class (sum of GHS-POP); with `buildings`, GlobalBuildingAtlas buildings by the cell of
   their centre (bbox centre), per class, and those ≥ 21 m high (`buildings_over_21m`); buildings in unobserved cells
   apart.
5. **Flood of an event** (`flood_month`): `flooded = (water in flood_month) AND (land in dry_month)` on the GSW
   30 m grid (the dry month is resampled by nearest neighbour if its grid differs); permanent water and rivers drop
   out. `dry_month` defaults to six months earlier (not before 2017). Per population cell, `flooded_share` = flooded
   pixels / pixels of the cell; people flooded = Σ people × share; on sinking ground = the same over class ≥ 1.
   `flooded_km2` from the pixel area; `unobserved_share` = share of the event month's pixels with no observation.
   Points on flooded vs dry land (land in the event month, not flooded): median `v_vert` of each when ≥ 10 points.
   Rain: CHIRPS daily AOI mean summed over the month, and the wettest day. `rain_peak_30min`: the half hour with the
   highest AOI-mean IMERG late rate in the month (UTC, mm/h), with the wettest cell's rate.
6. **River flood scenario** (`glofas_rp`): GloFAS depth at each population cell centre (nearest 90 m pixel; dry =
   NaN). People in the flood, people at depth ≥ 1 m, people on sinking ground (class ≥ 1).

`geoeyes coop` (`geoeyes.opendata.coop`): `sync` reads the site map's accounts and each account's public products
(12 threads); `search` ranks products on every word of the query (title and product id weight 3, tags 2, account
1.5, description 1; a word of ≥ 4 letters also matches as a prefix, ≥ 6 as a substring; at least half the words
must match; +0.5 for a product with a GeoEyes reader). Vietnamese words of the usual topics are translated first,
accents removed ("dân số" → population, "nhà", "tòa nhà", "công trình" → building, "ngập", "lũ lụt" → flood,
"mưa" → rain, "lún" → subsidence, "trượt lở" → landslide, "độ cao" → elevation, "nước" → water, …). Readers fetch
only the AOI window: COG range requests snapped to the source pixel grid, Parquet row groups filtered on their bbox.

## 4. Steps

1. **(Optional) Explore the catalog.** `geoeyes coop sync` (prints products and accounts); `geoeyes coop search lũ lụt`;
   `geoeyes coop layers` (the six layers GeoEyes reads). Web app: Projects → Source Cooperative.
2. **(Optional) Read a layer for QGIS.**
   `geoeyes coop get gsw-monthly --bbox 105.7,20.95,105.95,21.1 --month 2024-09`;
   `geoeyes coop get chirps-daily --bbox ... --from 2024-09-05 --to 2024-09-12` (≤ 10 years);
   `geoeyes coop get imerg --bbox ... --from 2024-09-06 --to 2024-09-08` (≤ 92 days; prints half hours ≥ 0.1 mm/h);
   `geoeyes coop get glofas-depth --bbox=-99.25,19.3,-99.0,19.5 --rp 100` ("=" when the bbox starts with "-");
   `geoeyes coop get ghsl-pop --bbox ...`; `geoeyes coop get gba-buildings --bbox ...`. Files go to
   `<workspace>/cache/sourcecoop/<layer>/`.
3. **Exposure.** `geoeyes exposure <project> [--product <id>] --set flood_month=2024-09 --set glofas_rp=100
   [--set dry_month=2024-03] [--set breaks_mm_yr=[5,10,20,50]] [--set buildings=false]`. Web app: In-depth analysis →
   Thematic analysis → group "Kinds of motion and risk" → "People and buildings exposed" → Flood month, GloFAS → "Count
   the people and buildings exposed". About 110 s on the first run for Hanoi (downloads); faster when cached. Writes
   `<project>/analyses/exposure/<product_id>/exposure.json`, `exposure_cells.parquet`, `manifest.json`.
4. **Building heights for the risk.** `geoeyes risk` fills missing Overture heights from GlobalBuildingAtlas
   (`gba_heights = true` by default; [behaviour-and-risk.md](behaviour-and-risk.md)).

## 5. Outputs and how to read them

- `exposure.json` → `subsidence.classes[]`: `class`, `cells`, `people`, `buildings`, `buildings_over_21m`;
  `people_observed`, `people_not_observed`, `people_total`, `cells_observed`, `buildings_observed`,
  `buildings_not_observed`. → `flood`: `month`, `dry_month`, `flooded_km2`, `unobserved_share`, `people`,
  `people_on_sinking_ground`, `points_flooded`, `points_dry`, `v_vert_flooded_mm_yr`, `v_vert_dry_mm_yr`,
  `rain_month_mm`, `rain_wettest_day`, `rain_peak_30min`. → `glofas`: `return_period`, `people`, `people_over_1m`,
  `people_on_sinking_ground`. Plus `credits` (cite them) and `params`.
- `exposure_cells.parquet`: per population cell `lon, lat, people, points, v_vert_mm_yr, class` (−1 not observed),
  and `flooded_share`, `glofas_depth_m` when asked.
- Web map: cells coloured by sinking class (grey = not observed), stronger where more people live (full colour at
  ~50 000 people/km²); switch to "Flood of the month" (share flooded: < 10 %, 10–30 %, 30–60 %, ≥ 60 %) or "River
  flood" (depth < 0.5, 0.5–1, 1–2, ≥ 2 m); counts in the legend.

Hanoi, S1 descending track 91, product `hanoi_s1_sentinel1-desc-091_20251001_20261015_v4` (one year of data):

| Sinking class (mm/yr) | People | Buildings |
|---|---|---|
| < 5 | 2 581 513 | 457 022 |
| 5–10 | 155 661 | 41 690 |
| 10–20 | 16 900 | 6 247 |
| 20–50 | 225 | 123 |
| ≥ 50 | 0 | 0 |
| not observed | 386 197 | 109 891 |

- Yagi, 2024-09 against the dry month 2024-03: GSW new water only 0.05 km², 20.7 % of the pixels unobserved; CHIRPS
  679.5 mm in the month, 226 mm on 2024-09-07. IMERG late peak 15.86 mm/h at 2024-09-09T12:30 UTC; IMERG late gives
  79 mm on 7 September against 226 mm for CHIRPS (satellite-only, not gauge-adjusted).
- GloFAS 100-year flood: 1 339 041 people, 1 005 341 at more than 1 m, 71 927 on sinking ground (no dykes: an upper
  bound).
- Overture gives a height for 1.4 % of Hanoi's buildings, 67 % with GlobalBuildingAtlas.

(The `exposure.json` on disk now is a later run with `glofas_rp = 500` and no flood month: 1 545 654 people,
1 224 053 > 1 m, 80 742 on sinking ground.)

## 6. Quality checks

- `people_total` close to the official population of the area covered (GHS-POP is modelled).
- `people_not_observed` and `buildings_not_observed`: state them next to every class count.
- The class limits are vertical rates: check that the product's reference makes 0 mm/yr mean stable ground; a
  shifted reference moves people between classes.
- Flood part: `unobserved_share` above ~20 % or `flooded_km2` near zero during a known flood means the monthly
  composite did not see it; do not report "no flood".
- `v_vert_flooded_mm_yr` against `v_vert_dry_mm_yr` only with enough points on each side (≥ 10 is the code's floor).
- IMERG late against CHIRPS: use IMERG for timing and intensity, CHIRPS for daily and monthly totals.
- GloFAS: say "without dykes, an upper bound" with every number in a diked delta.

## 7. Limits and pitfalls

- `v_vert` assumes vertical motion; with `los_u` small or horizontal motion (slopes) it is wrong. Use
  [decompose-and-soft-soil.md](decompose-and-soft-soil.md) where two geometries exist.
- GHS-POP counts residents (night-time), 2025 epoch, at ~90 m: not workers, not exact per building.
- GlobalBuildingAtlas centres are bbox centres; heights are modelled.
- GSW is a monthly Landsat / Sentinel-2 composite: cloud and short urban floods escape it (Yagi over Hanoi: 0.05 km²).
  Urban floods need SAR amplitude of the day (idea 4 in [../../vi/research/paper-ideas.md](../../vi/research/paper-ideas.md)).
- GSW months only 2017-01 to 2024-12 (the mirror); GloFAS ignores dykes; CHIRPS daily is pentad totals split by ERA5
  ratios; IMERG late is satellite-only. IMERG recent periods (ending within 3 days) are not cached.
- A one-year product gives noisy rates; the 5 mm/yr class limit is close to its noise.
- The analysis area is the bounding box of the points, not the AOI polygon: cells at the corners can be outside the
  coverage and count as not observed.

## 8. On a new area or sensor

- Every layer is global: nothing to change but the product. Mexico City needs `--bbox=` with "=" in `coop get`.
- Adjust `breaks_mm_yr` to the area (e.g. `[10, 50, 100, 200]` for Mexico City's fast subsidence) and `min_points` to
  the point density (X-band: more points per 90 m cell).
- Pick `flood_month` from a known event inside 2017–2024 and a `dry_month` of the same water regime.
- `glofas_rp`: 100 is a common planning scenario; check where dykes exist before quoting it.
- Known local habit: in Hanoi, report GloFAS only as the protected floodplain, and the event part with the GSW
  caveat.

## 9. References

- Code: `src/geoeyes/hazard/exposure.py`, `src/geoeyes/opendata/coop.py`, `src/geoeyes/opendata/imerg_reader.py`,
  `src/geoeyes/ml/__init__.py` (`run_exposure`), `src/geoeyes/cli/main.py` (`cmd_coop`), `src/geoeyes/config/settings.py`
  (`icechunk_python`), `webapp/src/pages/Hazard.tsx` (`ExposureLegend`), `webapp/src/pages/Coop.tsx`.
- Guide: [../guide/opendata.md](../guide/opendata.md) §8. Related skills: [flood-reports.md](flood-reports.md),
  [behaviour-and-risk.md](behaviour-and-risk.md), [hazard-zoning.md](hazard-zoning.md).
- Schiavina, M., et al. (2023). GHS-POP R2023A. EC JRC. https://doi.org/10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE
- Pekel, J.-F., Cottam, A., Gorelick, N., Belward, A. S. (2016). High-resolution mapping of global surface water and
  its long-term changes. Nature 540, 418–422. https://doi.org/10.1038/nature20584
- Zhu, X. X., et al. (2025). GlobalBuildingAtlas. TUM (mediatum 1782307).
- JRC CEMS-GloFAS v2.1.2 flood hazard maps (CC BY 4.0).
- Climate Hazards Center CHIRPS3, https://doi.org/10.15780/G2JQ0P.
- NASA GPM IMERG, processed by dynamical.org (CC BY 4.0).
