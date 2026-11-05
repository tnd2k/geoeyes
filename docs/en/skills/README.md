# Skills: one problem, one reproducible recipe

Each skill takes one problem GeoEyes solves and says what someone needs to solve it again, on another area or with
another sensor:

1. **the data to prepare**, with where each item comes from, its format and where it goes;
2. **the method inside**, as computed by the code: formulas, thresholds and their defaults;
3. **the steps**: commands, web-app path, run times, the files each step writes;

and then how to read the outputs, the quality checks, the limits, and what to change on a new area. The research
notes ([../research/](../research/)) say *why* a method was chosen and what it found. The guides
([../guide/](../guide/)) cover a tool in depth. A skill is the operating sheet that ties them together.

Vietnamese: [../../vi/skills/README.md](../../vi/skills/README.md).

## Skills

| # | Skill | Problem it answers | Main commands |
|---|---|---|---|
| 1 | [insar-processing.md](insar-processing.md) | A SAR stack (Sentinel-1, COSMO-SkyMed, Capella, ICEYE, Umbra; TerraSAR-X and ALOS have presets but no stack builder yet) to a velocity product | `geoeyes check / plan / run / status` |
| 2 | [opendata-stacks.md](opendata-stacks.md) | Find open X-band stacks (ICEYE, Capella, Umbra) and turn one into a project | `geoeyes opendata` |
| 3 | [stack-qc.md](stack-qc.md) | Is the coregistered stack good enough to process? | `geoeyes stack-qc` |
| 4 | [atmosphere.md](atmosphere.md) | Choose and apply a tropospheric correction (ERA5, CERRA, GACOS) | `geoeyes atmosphere`, `gacos-order` |
| 5 | [ionosphere.md](ionosphere.md) | Recognise and correct ionospheric phase (split-spectrum, native Sentinel-1 IW stacks) | `[stack] ionosphere` |
| 6 | [gnss-calibration.md](gnss-calibration.md) | Validate InSAR against GNSS and tie it to a terrestrial frame | `geoeyes gnss`, `geoeyes tie` |
| 7 | [corner-reflector.md](corner-reflector.md) | Validate with corner reflectors (position, RCS, signal-to-clutter, coherence) | `geoeyes cr-report` |
| 8 | [incremental-monitoring.md](incremental-monitoring.md) | Add new dates in minutes and raise early warnings | `geoeyes run` (incremental), alerts |
| 9 | [hazard-zoning.md](hazard-zoning.md) | Subsidence and landslide hazard zoning from InSAR, rainfall and groundwater | `geoeyes hazard` |
| 10 | [behaviour-and-risk.md](behaviour-and-risk.md) | Kind of motion of each cell; velocity and tilt per building; risk to buildings | `geoeyes behaviour / buildings / risk` |
| 11 | [lines-and-consolidation.md](lines-and-consolidation.md) | Differential settlement along dykes, railways, roads; settlement still to come | `geoeyes lines / consolidation` |
| 12 | [decompose-and-soft-soil.md](decompose-and-soft-soil.md) | Vertical and east-west motion from two geometries; soft-soil thickness against subsidence | `geoeyes decompose / geology` |
| 13 | [susceptibility-and-forecast.md](susceptibility-and-forecast.md) | Where the ground could move (ML susceptibility); deformation forecast | `geoeyes susceptibility / forecast` |
| 14 | [landslide-susceptibility.md](landslide-susceptibility.md) | Regional landslide susceptibility from an inventory and terrain layers | `geoeyes landslide` |
| 15 | [flood-reports.md](flood-reports.md) | Reported flood locations against subsidence; today's flood outlook | `geoeyes floods` |
| 16 | [exposure-and-flood-layers.md](exposure-and-flood-layers.md) | People and buildings on sinking ground and in a flood (Source Cooperative layers) | `geoeyes exposure`, `geoeyes coop` |

Dependencies: 1 comes first. 3 to 7 check or improve its product. 9 is needed by 10 to 13. 16 reads any product
and is better after 9 and 10.

## Template of a skill

Every skill has these sections, in this order, so that two skills read the same way:

```
# Skill: <title>

> One sentence: the problem. Status (operational / research), last checked date, CLI and web-app entry points.

## 1. When to use it
   The question it answers, the decision it supports, when not to use it.
## 2. Data to prepare
   Table: item | required? | source / how to get it | format, where it goes (path or project.toml key) | notes.
   Then a checklist to tick before running.
## 3. Method
   What the code computes, step by step, with the formulas, thresholds and defaults (parameter names as in
   project.toml), and the published methods it follows.
## 4. Steps
   Numbered: the command (or web-app path), what it does, how long it takes, the files it writes.
## 5. Outputs and how to read them
   Files, fields, map layers; what a value means.
## 6. Quality checks
   What to verify before trusting or publishing the result (numbers, plots, acceptance criteria).
## 7. Limits and pitfalls
## 8. On a new area or sensor
   What to change (parameters, data), what carries over, known local habits.
## 9. References
   Code (file paths), guides and research notes, papers.
```

Parameter names, file names and commands are written exactly as in the code. A skill describes what the code does
now. When code and a skill disagree, the code wins and the skill is corrected.
