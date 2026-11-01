# Incremental processing and monitoring

For people who keep a project up to date as new Sentinel-1 acquisitions come in. It explains what a run redoes
when a date is added, how the incremental point update works and when it is not used, the early-warning alert,
and the exports for people without GIS software.

## Contents

1. [What a new acquisition costs](#1-what-a-new-acquisition-costs)
2. [Incremental stack](#2-incremental-stack)
3. [Incremental point update](#3-incremental-point-update)
4. [Early warning](#4-early-warning)
5. [A monitoring routine](#5-a-monitoring-routine)
6. [Exports: Google Earth and 3D Tiles](#6-exports-google-earth-and-3d-tiles)
7. [Troposphere: ordering GACOS](#7-troposphere-ordering-gacos)

## 1. What a new acquisition costs

Hanoi, Sentinel-1 ascending 128, 26 dates, about 730,000 points, split-spectrum ionosphere:

| Phase | Full run | One new date |
|---|---|---|
| acquire | downloads every burst | the new bursts only |
| build_stack | 71 min | ~3 min (estimate: 71 min / 26 dates): the new date coregistered, the others copied |
| ps | 12 min | **45 s** (incremental update) |
| build_product, export, report | 2 min | 2 min |

## 2. Incremental stack

`[stack] incremental = true` (default). A new build keeps the coregistered dates of the existing stack when:

- the reference date, the AOI, the DEM and the subswaths are the same (with `[network] reference = "auto"` the
  reference of the first build is kept while it is still an acquisition);
- the files of the date that the stack reads are unchanged, and its orbit was not upgraded (a precise orbit
  published since re-coregisters that date).

The raw archive is shared by every project. Since 2026-10 a scene is compared only on the bursts the stack uses:
another project downloading other bursts of the same acquisition (another AOI or subswath) no longer makes the
dates look changed. The burst list of a scene (`bursts.json`) is merged, no longer rewritten, by each download.

`geoeyes plan <project>` says what will be redone and why ("2 new scene(s): …; incremental: 26 coregistered
date(s) kept").

## 3. Incremental point update

```toml
[ps_update]
enabled = true        # default
full_every = 4        # a full engine run after this many dates added by updates
```

When only new dates were appended after the last date of the previous `ps` run, the `ps` phase adds them to that
run instead of running the engine on the whole stack. The plan shows it: `ps  run  …; incremental update: 1 new
date(s)`.

Kept from the previous run: the points (selection and weeding), their DEM error, the master error, the reference
and the velocity model. For each new date and point:

1. the wrapped phase of the reference against the new date, as the engine forms it;
2. minus the topographic phase of the point's DEM error, and the motion predicted by its linear fit;
3. the rest (atmosphere, unexpected motion, noise) unwrapped in space on the unwrapping grid (IRLS), each point
   snapped to its own wrapped phase + 2πk;
4. the atmosphere removed: the weather model (ERA5 / GACOS) or the linear phase-height fit, whichever leaves the
   smaller residual;
5. referenced as the engine does (reference points or the scene mean); velocity, acceleration and fit RMSE fitted
   again over all dates.

A full run instead of an update when: the parameters changed (`[ps]`, `[selection]`, `[atmosphere]`, engine
version), the stack was rebuilt (new reference, re-coregistered dates), a new date falls before the last date of
the run, phase linking is on, `full_every` dates were already added, or `--force ps`.

**Accuracy** (hold-out test, Hanoi asc 128: the full run without its last dates, updated with them):

| Dates added | Time | Displacement of the new dates vs full run | Velocity vs full run |
|---|---|---|---|
| 1 | 45 s | r 0.92, std 2.7 mm, 0.5 % of points beyond half a cycle | std 0.6 mm/yr |
| 3 | 62 s | r 0.83–0.93, std 2.7–3.6 mm, up to 1.2 % | std 1.4 mm/yr |

Part of the difference is not error of the update: a full run re-estimates the points, their DEM errors and the
APS of every date with the new data. What an update cannot do: find new stable points or drop lost ones, separate
the spatially correlated noise of the new dates (their SCN is 0: no temporal window after them yet). Hence
`full_every`.

## 4. Early warning

Alert rules (`[postprocess.alerts]`, Monitoring tab of the project page) are evaluated on the latest product:

| Kind | Fires when at least `min_points` points … |
|---|---|
| `velocity_below` / `velocity_above` | have a velocity beyond `threshold` (mm/yr) |
| `deviation_below` / `deviation_above` | on the **latest date** depart from the linear trend of the earlier dates by more than `threshold` (mm) |

The deviation rules react to one new acquisition, before it moves the velocity. They need at least 7 dates. A
single date can be atmosphere: read a triggered rule against the next acquisition, and against the other track.

```toml
[postprocess.alerts]
rules = [
  { name = "sudden sinking", kind = "deviation_below", threshold = -10.0, min_points = 30 },
]
```

## 5. A monitoring routine

1. Monitoring tab: schedule `geoeyes run` (daily or weekly, Windows Task Scheduler).
2. Each run: `acquire` downloads the new bursts; `build_stack` adds the new dates; `ps` updates; a new product
   version, export and report follow.
3. Every `full_every` dates, or after a change of parameters, the run is a full one (about 15 min more).
4. The report's quality checks (section 4.1) and the alerts are read on each new product.

## 6. Exports: Google Earth and 3D Tiles

```toml
[export]
formats = ["gpkg", "pmtiles", "kmz", "3dtiles"]
```

- `kmz` (Google Earth): the velocity as a ground overlay in the classes of the QGIS style, a legend, and the
  fastest points (1,500, both directions) as placemarks with their numbers and a few dates of their series.
- `3dtiles` (Cesium, ArcGIS, deck.gl): a 3D Tiles 1.0 point cloud at ellipsoidal height, coloured by class, with
  the velocity, height and coherence per point; `viewer.html` shows it over OpenStreetMap. Open it through the web
  app (`…/api/projects/<project>/exports/<product>/3dtiles/viewer.html`): a page opened from disk cannot read the
  tiles.

## 7. Troposphere: ordering GACOS

ERA5 (0.25°, hourly, interpolated to the acquisition time) misses the evening convection of the wet season in
Hanoi (docs/en/guide/ionosphere.md §6). GACOS (~90 m, from the ECMWF high-resolution model) does better in the
tropics but has no API: the products are ordered on http://www.gacos.net and arrive by e-mail.

```
geoeyes gacos-order <project> [--track ID]
```

prints what to enter in the form: area (the AOI + 0.1°), UTC time and the dates that have no product yet in
`[atmosphere.gacos] dir`. Then:

```toml
[atmosphere]
method = "gacos"
gacos = { dir = "D:/data/gacos/hanoi_asc128" }
```

With `select = "auto"` (default), each date takes GACOS only where it explains the residual phase better than the
linear fit; dates without a product keep the linear APS.
