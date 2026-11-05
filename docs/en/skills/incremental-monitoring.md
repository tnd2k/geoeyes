# Skill: incremental processing, monitoring and early warning

> Keep a project up to date as new acquisitions arrive (a new date in minutes instead of a full run), raise
> deformation alerts on the latest product, and hand the result to people without GIS (Google Earth, 3D Tiles);
> order GACOS troposphere products for the new dates. Status: operational for Sentinel-1 with the `ps` engine. Last
> checked 2026-11-01. CLI: `geoeyes plan / run` (incremental by itself), `geoeyes gacos-order`. Web app: project page
> → Monitoring tab (next acquisitions, scheduled run, alert rules).

## 1. When to use it

- A project has had a full run and new acquisitions keep coming (S1: every 6–12 days): add them cheaply, produce a new
  product version, check alert rules.
- You need an early warning: points whose latest date departs from their trend, or whose velocity crosses a limit.
- You must share the velocity with people who only have Google Earth or a web browser.
- Not for: a first run (see [insar-processing.md](insar-processing.md)); projects with phase linking or `ps_lite`
  (the point update is not used: every new date means a full engine run, the stack is still extended
  incrementally).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| A project with a full run | yes | [insar-processing.md](insar-processing.md) | `ps_runs/<track_id>/state.h5`, `manifest.json` with `config_fingerprint` | the update extends this run |
| New acquisitions | yes | S1: ASF through `acquire`; others: new `YYYYMMDD/` folders; open data: `geoeyes opendata sync` | as in [insar-processing.md](insar-processing.md) §2 | `[acquire] date_range` must include them (move its end date forward) |
| `EARTHDATA_TOKEN` | yes (S1) | NASA Earthdata | environment / `.env` | bursts and POEORB |
| Incremental settings | optional | defaults fit | `[stack] incremental = true`, `[ps_update] enabled = true`, `full_every = 4` | |
| Alert rules | optional | your thresholds | `[postprocess.alerts] rules = [{ name, kind, threshold, min_points, bbox }]` | written by the Monitoring tab too |
| Schedule | optional | Windows Task Scheduler (from the web app) or cron | task `GeoEyes\<project>` | Windows only from the web app |
| GACOS products | optional | ordered on http://www.gacos.net (no API), sent by e-mail | `[atmosphere.gacos] dir`: `<YYYYMMDD>.ztd` + `.ztd.rsc`, or `<YYYYMMDD>.ztd.tif` | with `[atmosphere] method = "gacos"` |
| Export formats | optional | — | `[export] formats = ["gpkg", "pmtiles", "kmz", "3dtiles"]` | default `["gpkg", "pmtiles"]` |
| Web server | for alerts, 3D viewer | `geoeyes serve` | http://localhost:8765 | alerts are evaluated by the server |

Checklist:

- [ ] Last full run *done*; `geoeyes plan <project>` shows the new dates and, on the `ps` line,
      `incremental update: N new date(s)`.
- [ ] `[acquire] date_range` covers the new dates; same reference date, AOI, DEM, subswaths as the last build.
- [ ] Alert rules saved (Monitoring tab or `project.toml`).
- [ ] GACOS: products for the new dates in `[atmosphere.gacos] dir` (`geoeyes gacos-order` lists the missing ones).

## 3. Method

**Incremental stack** (`controller/phases/build_stack.py`, `reusable`). With `[stack] incremental = true`, a build
copies the coregistered dates of the existing store when it was built with the same reference date, AOI, DEM and
subswaths (stack fingerprint recomputed with its stored scene signatures), the reference scene is unchanged, and the
date's own files (S1: only the bursts the stack uses, plus the annotation) have the same names and sizes. A S1 date
coregistered without POEORB is redone once its precise orbit is published (checked for dates ≥ 15 days old). With
`[network] reference = "auto"` the reference of the first build is kept.

**Incremental point update** (`processing/ps/update.py`, engine `geoeyes-ps-update/1`). Used when only dates after
the last date of the previous `ps` run were added. Kept: the points, their look-angle error K (from scla = K·B⊥),
master term C, reference and velocity model. For each new date d and point:

```
φ_obs  = arg(slc_ref · conj(slc_d))
φ_topo = K · B⊥_d                               B⊥_d from the stack height sensitivity kh
φ_pred = −(v·t_d + c) / (λ/4π)                  linear fit of the previous series
r      = wrap(φ_obs − φ_topo − φ_pred − C)
φ_uw   = φ_topo + φ_pred + C + unwrap_space(r)  IRLS on the unwrap grid, each point snapped to φ_obs + 2πk
d      = −(φ_uw − φ_topo − APS − C) · λ/4π
```

- Spatial unwrapping: grid of `[ps] unwrap_grid_size` (default 10 m), Gaussian prefilter with a fixed window of 16
  and α 0.8 (not `unwrap_gold_n_win`), weights = coherence² of the smoothed cells (clipped 0.05–1), refined IRLS,
  `unwrap_align_constant` honoured.
- APS of the new date: the weather model (ERA5 / CERRA / GACOS) when it has data for > 50 % of the points and leaves
  a smaller residual variance than the linear phase-height fit, else the linear fit.
- Referencing as the engine (reference points or scene mean); velocity, acceleration and fit RMSE refitted over all
  dates, weighted by the per-date phase noise (new dates: the median noise); the engine's high-pass correction of
  the velocity is carried over; the SCN of new dates is 0.

A full run instead when: parameters changed (`[ps]`, `[selection]`, `[atmosphere]`, `[ps_lite]`, engine version),
another stack (new reference), dates of the previous run re-coregistered, a new date before the last one, phase
linking on, engine `ps_lite`, more than `full_every` dates added since the last full run, `[ps_update] enabled =
false`, or `--force ps`.

**Alerts** (`api/monitor.py`). Rules of `[postprocess.alerts]`, evaluated on the latest product of each track:

| `kind` | Value tested per point | Fires when |
|---|---|---|
| `velocity_below` / `velocity_above` | `vel_los_mm_yr` | ≥ `min_points` points with value ≤ / ≥ `threshold` (mm/yr) |
| `deviation_below` / `deviation_above` | displacement of the latest date minus the least-squares line through the earlier dates (mm) | ≥ `min_points` points with value ≤ / ≥ `threshold` (mm) |

`min_points` defaults to 10; an optional `bbox = [west, south, east, north]` restricts the points; deviation rules
need at least 7 dates. A result gives the count, the points tested, the most extreme value and the centroid of the
hits. Rules are evaluated by the web server (Monitoring tab, project list), not by `geoeyes run`; nothing is sent
by e-mail (ADR-008).

**Next acquisitions** (S1 tracks): the last acquisition of each satellite in the archive + 12-day steps (satellites
not seen for 60 days are left out), marked *planned* / *not planned* from ESA's acquisition plan.

**Scheduled run** (Windows): task `GeoEyes\<project>` running `python -m geoeyes.cli.main --workspace <ws> run
<project>` daily or weekly at `HH:MM` (default 02:00, Monday), while the user is logged on. Elsewhere: cron.

**Exports** (`export/`). `kmz`: the velocity rasterised at the marker size as a ground overlay (≤ 4000 px on the
longer side) in the classes of the QGIS style, a legend, and the 1,500 fastest points of both signs as placemarks
with their numbers and a small displacement chart. `3dtiles`: 3D Tiles 1.0 point cloud, root tile of 40,000 points
and child tiles of ≤ 150,000, ECEF positions at ellipsoidal height (height above EGM96 + geoid undulation), colour
of the velocity class, velocity / height / coherence per point, `viewer.html` with CesiumJS 1.120. `pmtiles`: vector
tiles (QGIS 3.32+, the web app's tiled mode). All use Pretty Breaks, 10 classes over min–max, `jet_r`.

**GACOS order** (`geoeyes gacos-order`, `processing/atmosphere/gacos.py`): area = AOI ± 0.1°, time = mean UTC
acquisition time of the dates, dates without a product yet in `[atmosphere.gacos] dir`. With `select = "auto"`,
GACOS is used per interferogram only where it explains the residual better than the linear fit.

## 4. Steps

1. **Once:** set `[export] formats`, alert rules (Monitoring tab → *Deformation alerts* → *Save rules*, or edit
   `[postprocess.alerts]`), and a schedule (Monitoring tab → *Scheduled run*: frequency, day, time → *Save*).
2. **Each new acquisition** (by the schedule, or by hand):
   - `geoeyes plan <project>`: "N new acquisition(s) on ASF"; `build_stack … incremental: K coregistered date(s)
     kept`; `ps … incremental update: N new date(s)`.
   - `geoeyes run <project>`. Times for one new date (Hanoi S1 ascending 128, 26 dates, ~730,000 points;
     ../guide/incremental.md): `acquire` the new bursts only, `build_stack` ~3 min (estimate), `ps` 45 s,
     `build_product` + `export` + `report` 2 min. Three dates: `ps` 62 s.
   - Writes: new dates in `stacks/<stack_id>/stack.zarr`; `ps_runs/<track_id>/` rewritten in place (`state.h5`,
     `points.parquet`, `timeseries.parquet`, `manifest.json`); a new product `products/<…>_v<N+1>/`; its exports
     and report.
3. **Every `full_every` dates** (or after a parameter change) the `ps` phase runs in full (Hanoi: 12 min).
4. **Read the alerts:** Monitoring tab (`geoeyes serve`, then the project). A triggered deviation rule is read
   against the next acquisition and the other track before acting.
5. **Share:** `exports/<product>/<product>.kmz` opens in Google Earth; the 3D viewer at
   `http://localhost:8765/api/projects/<project>/exports/<product>/3dtiles/viewer.html` (served by `geoeyes serve`).
6. **GACOS:** `geoeyes gacos-order <project> [--track ID]` prints area (N, S, W, E), UTC time and the dates (20 per
   block) to paste in the form; unpack the products into the folder of `[atmosphere.gacos] dir`, set `[atmosphere]
   method = "gacos"` (a change of `[atmosphere]` makes the next `ps` run a full one).

## 5. Outputs and how to read them

| File / field | Content |
|---|---|
| `ps_runs/<track_id>/manifest.json` → `metrics.update` | `base_run` (last full run), `dates_since_full`, `added` (dates added by updates), `weather_aps` (dates that took the weather model) |
| `ps_runs/<track_id>/manifest.json` → `engine` | `geoeyes-ps-update/1` after an update, the engine id after a full run |
| `products/<…>_v<N>/` | one new version per run; the previous ones stay |
| Alert result | `name`, `kind`, `threshold`, `min_points`, `n` (points beyond), `of` (points tested), `triggered`, `worst`, `lon`, `lat`, `date` (deviation rules), `note` ("fewer than 7 dates") |
| `exports/<id>/<id>.kmz` | overlay + legend + placemarks |
| `exports/<id>/3dtiles/` | `tileset.json`, `tiles/*.pnts`, `viewer.html` |

A deviation of −10 mm on 30 points at the latest date means those points sank 10 mm more than their trend
predicted: either motion or one date of atmosphere.

## 6. Quality checks

- Hold-out test of the update (Hanoi ascending 128, ../guide/incremental.md): 1 date added, displacement of the new
  date vs a full run r 0.92, std 2.7 mm, 0.5 % of points beyond half a cycle, velocity std 0.6 mm/yr; 3 dates
  r 0.83–0.93, std 2.7–3.6 mm, up to 1.2 %, velocity std 1.4 mm/yr. Part of the difference is the full run
  re-estimating the points, K and the APS.
- Log of the update: per date "unwrapped residual … rad (std), APS weather|linear, median motion vs prediction
  … mm"; a large median departure on one date is atmosphere or an unwrapping error until the next date confirms it.
- Compare the velocity map of the new version with the previous one (same colour classes, full min–max).
- Read the report's quality checks on each new product.

## 7. Limits and pitfalls

- An update cannot find new stable points or drop lost ones, re-estimate K and the APS of earlier dates, or separate
  the SCN of the new dates (it is 0): hence `full_every`.
- Phase linking or `ps_lite`: no point update; each new date runs the full engine.
- ERA5 of the last days may not be published yet: the update falls back to the linear APS for that date.
- Alerts are evaluated when the web server is asked (page open); a scheduled run alone produces the product but no
  notification. The Monitoring tab text "after every run" holds only when the page is viewed.
- The scheduled task runs only while the user is logged on; on other systems use cron.
- Next-acquisition forecast and the schedule from the web app: Sentinel-1 / Windows only.
- `viewer.html` opened from disk cannot read the tiles; open it through the server.
- A changed `[atmosphere]` (e.g. switching to GACOS) or any `[ps]` change makes the next run a full one.

## 8. On a new area or sensor

- Choose `full_every` from the accuracy wanted: 1 date per update keeps r ≈ 0.92 at Hanoi; more dates degrade
  (above).
- Set alert thresholds from the product's own noise: `vel_std_median_mm_yr` and the residual sigma of stable areas;
  `min_points` large enough that one noisy cluster does not fire; a `bbox` per asset (dyke, airport).
- The update uses the project's `unwrap_grid_size` (HCMC: 50 m, elsewhere 10 m) and `unwrap_align_constant`.
- Commercial sensors: new dates are new `YYYYMMDD/` folders; with phase linking (COSMO-SkyMed, ICEYE presets) each
  new date means a full run.

## 9. References

- Code: `src/geoeyes/processing/ps/update.py`, `controller/pipeline.py` (`PointEngine.update_plan`, `note`),
  `controller/phases/build_stack.py` (`reusable`, `orbit_upgrades`), `api/monitor.py`, `api/app.py`
  (`/api/projects/{name}/monitor`, `/alerts`, `/schedule`), `webapp/src/components/Monitor.tsx`,
  `export/{kmz,tiles3d,pmtiles,styles}.py`, `processing/atmosphere/gacos.py`, `cli/main.py` (`cmd_gacos_order`).
- Guides: ../guide/incremental.md, ../guide/atmosphere.md, ../guide/projects-and-data.md.
- Skills: [insar-processing.md](insar-processing.md), [atmosphere.md](atmosphere.md), [stack-qc.md](stack-qc.md).
- Yu et al. 2018 (GACOS); OGC 3D Tiles 1.0; Hooper 2008 (StaMPS space-time unwrapping).
