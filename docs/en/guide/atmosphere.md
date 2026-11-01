# Troposphere: choosing a weather model

The second unwrapping pass of the `ps` engine removes an atmospheric phase screen (APS): the engine's linear fit
of phase against height, or a weather model (`[atmosphere] method`). This page lists the models, says where each
one applies, and shows how to try them on a product before running a project again.

## Contents

1. [The models](#1-the-models)
2. [Outside Europe](#2-outside-europe)
3. [Trying the models on a product](#3-trying-the-models-on-a-product)
4. [Applying one](#4-applying-one)
5. [What a model cannot remove](#5-what-a-model-cannot-remove)

## 1. The models

| `method` | Model | Grid | Analyses | Area | Access |
|---|---|---|---|---|---|
| `none` | linear APS of the engine (phase vs height per interferogram) | – | – | everywhere | – |
| `era5` | ERA5 (ECMWF / C3S reanalysis) | 0.25° (~31 km) | hourly | globe | CDS API, automatic |
| `cerra` | CERRA (SMHI / C3S European regional reanalysis) | 5.5 km, Lambert | 3-hourly | Europe, North Africa, the Canaries, the Azores | CDS API, automatic |
| `gacos` | GACOS (ECMWF HRES + interpolation) | ~90 m output | per date | globe | ordered by e-mail ([guide](incremental.md#7-troposphere-ordering-gacos)) |

ERA5 and CERRA use the same CDS credentials (`~/.cdsapirc`); accept each dataset's licence once on the CDS website.
Both are computed the same way: delay profiles per model column (refractivity integrated to 15 km), interpolated
bilinearly to every point at its height, and linearly in time between the two analyses around the acquisition.

CERRA is published one to two months after the date (monthly updates). The CDS does not cut its Lambert grid: one
GRIB per analysis time holds the whole domain (~125 MB). The cache, `<workspace>/cache/cerra`, is shared by every
project in Europe. A daily stack bracketed by two analyses needs two files per date.

## 2. Outside Europe

No free model finer than ERA5 can be downloaded automatically for past dates:

- the 9 km ECMWF IFS (the model behind GACOS) is open only as a rolling real-time archive; open-meteo serves
  its history at 0.25° (ERA5's grid), without the 9 km pressure levels;
- the national high-resolution models are regional: HRRR (3 km, United States, on AWS), CARRA (2.5 km, Arctic,
  CDS), BARRA2 (12 km, Australia). The Atmosphere tab lists them as not yet supported.

Elsewhere (Vietnam, Mexico): ERA5, or GACOS ordered by hand. GNSS zenith delays (Nevada Geodetic Laboratory) are
a possible next step to correct ERA5 near the stations.

## 3. Trying the models on a product

Web app: project page, **Atmosphere** tab. It lists the models with their coverage of the product (area and
dates), shows the CERRA domain on a map, and **Try the models** runs:

```
geoeyes atmosphere <project> [--product ID] [--set models=["era5","cerra"]] [--set max_points=200000]
```

Nothing is processed again. The unwrapped phase of the `ps` run behind the product, minus a linear motion and a
DEM error per point, is mostly atmosphere and noise. Each model's APS at the points, centred per interferogram as
in the engine, is subtracted from it. The tab shows:

- the scatter (mm) left per interferogram and its median, with no APS, the linear APS and each model;
- the share of the variance removed, and on how many interferograms each model is the best;
- maps of one interferogram: observed residual, model APS, residual after the model, on one colour scale (full
  range).

Results: `analyses/atmosphere/<product>/atmosphere.json` and `grids.npz`. Only the StaMPS-type `ps` engine keeps
the unwrapped phase this needs.

## 4. Applying one

**Use** on a model row sets `[atmosphere] method` and runs the project again. Steps 1-5 of the point engine come
from their checkpoints (`ps_runs/<id>/checkpoints/step<N>.json` records the key of the parameters and the stack
they belong to), so only the unwrapping and the later steps run.

```toml
[atmosphere]
method = "cerra"
select = "auto"        # per interferogram, the model only where it beats the linear APS
cerra = { cache = "D:/geoeyes/cache/cerra" }    # optional
```

## 5. What a model cannot remove

A model removes the part of the delay it resolves: the height-stratified part, and turbulence larger than a few
of its cells. Turbulent cells of a few km, typical over mountains and in convective weather, are smaller than a
CERRA cell (5.5 km) and far smaller than an ERA5 cell. They stay in the phase. Over a short stack they then
dominate the velocity. On Tenerife (ICEYE, 15 days, 2026-02), ±2.5 mm of such atmosphere reads as ±60 mm/yr. In
that case a longer stack helps more than a finer model.
