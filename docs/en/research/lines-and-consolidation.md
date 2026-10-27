# Infrastructure lines and consolidation settlement

Status: v1 implemented 2026-10-26.
Code: `geoeyes.ml.lines` (`geoeyes lines`), `geoeyes.ml.consolidation` (`geoeyes consolidation`),
`geoeyes.api.behaviour`.
Web app: layers "Infrastructure lines" and "Remaining settlement" on the Thematic analysis page; Principles,
chapter 4.
Related: [rainfall-insar-hazard.md](rainfall-insar-hazard.md) (the zoning and the damage limits used here) and
[behaviour-and-risk.md](behaviour-and-risk.md) (the kinds of motion; "slowing down" is the shape that consolidation
makes precise).

## Contents

1. [Questions](#1-questions)
2. [InSAR along linear infrastructure](#2-insar-along-linear-infrastructure)
3. [Consolidation settlement](#3-consolidation-settlement)
4. [First results](#4-first-results)
5. [Limitations](#5-limitations)
6. [Research sequence](#6-research-sequence)
7. [References](#7-references)

## 1. Questions

- **Q3. Where do dykes, railways and main roads bend?** These structures are long and continuous. What harms them
  is less the sinking itself than sinking that changes along them:
  - a dip in a dyke crest is where the water overtops first;
  - a dip under a track bends the rails.
- **Q4. Where will the ground keep sinking, and by how much?** Soft soil under a new load settles towards an end.
  Pumping keeps the ground sinking as long as it goes on. The two call for different answers.

## 2. InSAR along linear infrastructure

### 2.1 Lines

The lines over the product come from OpenStreetMap through the Overpass API. The answer is cached in the
workspace, under `cache/osm/overpass_<hash>.json`. Four kinds are read:

| Kind | OSM tags |
|---|---|
| dyke | `man_made=dyke`, or a road whose name starts with "Đê " (the Red River dykes of Hanoi are mapped as streets) |
| embankment | road with `embankment=yes` |
| railway | `railway=rail` |
| road | `highway=motorway / trunk / primary` (with `roads = true`) |

Ways of the same kind and the same name (or `ref`) that share an end node are chained into one line.

### 2.2 Stations

Stations are placed every `step_m` = 50 m along each line. Each station keeps the median vertical rate of the
persistent scatterers within `buffer_m` = 30 m, when there are at least `min_points` = 3 of them:

    v_vert = v_LOS / l_u        (GeoEyes sign: negative = sinking)

The vertical projection assumes no horizontal motion. Where two geometries are fused, the decomposed vertical is
better.

### 2.3 Differential settlement

Between stations `span_m` = 100 m apart, the angular distortion over the horizon T = `horizon_yr` = 10 years is:

    β = |v(x + L) − v(x)| · T / L

β is compared with the damage limits of the zoning (Skempton & MacDonald 1956; Bjerrum 1963):

| β | Reading |
|---|---|
| < 1/500 | below the safe limit |
| 1/500 – 1/300 | beyond the safe limit |
| 1/300 – 1/150 | cracking |
| ≥ 1/150 | structural damage |

For a dyke, the crest lost over T is |min v|·T. The freeboard against the design flood shrinks by as much.

Outputs, in `analyses/lines/<product>/`:

- `stations.parquet`: line, chainage, position, number of points, v_vert, β, β class;
- `lines.parquet`: kind, name, length, covered share, lowest and median rate, largest β, flagged stations, crest
  lost;
- `lines.json`: the summary by kind and the 20 lines with the largest β.

## 3. Consolidation settlement

### 3.1 Model

Primary consolidation (Terzaghi 1925) settles fast at first, then slower and slower. To first order:

    s(t) = c + A · (1 − e^(−t/τ))

- final settlement = c + A;
- still to come after the last date T: A · e^(−T/τ);
- 90 % of A is reached at τ · ln 10.

The settlement of every cell is s = −d, set to 0 at the first date. τ is tried on a grid of 80 values from 0.05 to
30 years (geometric), and (c, A) is found by least squares for each τ.

A cell is **consolidating** when all of these hold:

- it sinks by at least `min_rate_mm_yr` = 2 mm/yr, in the subsidence mode;
- the curve beats a straight line by ΔBIC ≥ `min_delta_bic` = 6 ("strong evidence", Kass & Raftery 1995);
- A > 0;
- τ is below `max_tau_factor` = 5 times the span of the data. Beyond that, τ is not determined.

### 3.2 Asaoka

Asaoka (1978) reads the same curve graphically. Readings taken at a fixed interval Δt satisfy
sᵢ = β₀ + β₁ · sᵢ₋₁, with β₁ = e^(−Δt/τ). The line meets sᵢ = sᵢ₋₁ at the final settlement β₀ / (1 − β₁).

The web app draws this construction for every cell, with readings resampled at a fixed interval (an eighth of the span, between 12 and 60 days). It is an independent
look at the same data, not a second fit used in the classification.

### 3.3 Check

The check is a forecast. The curve and the line are both fitted on the first `train_share` = 70 % of the dates,
and both predict the rest. `consolidation.json` reports:

- the mean absolute error of each;
- the share of cells where the curve wins.

The cells are chosen because the curve fits them, so the check favours the curve. It tells whether the curve also
predicts, not whether the choice is right.

Outputs, in `analyses/consolidation/<product>/`:

- `consolidation.parquet`: per cell, whether it is consolidating, τ, settled, final, remaining, t90 from now, c,
  A, ΔBIC;
- `consolidation.json`: the summary.

## 4. First results

### 4.1 Lines

| Product | Lines | Stations | Dykes | Railways | Embankments | Roads |
|---|---|---|---|---|---|---|
| Hanoi S1 desc 091, 2025-10 → 2026-10 | 582 | 13,696 | 15.7 km, 21 % covered, 0 flagged | 71.4 km, 41 %, 0 | 60.7 km, 44 %, 0 | 507.9 km, 52 %, 1 |
| Mexico City S1 asc 078, 2024-05 → 2024-10 | 570 | 20,001 | none mapped | 83.2 km, 39 %, 65 | 22.4 km, 26 %, 7 | 866 km, 50 %, 612 |

"Flagged" counts the stations beyond 1/500.

**Hanoi.** Only one station is beyond 1/500, on Đỗ Mười road (β 1/446, lowest rate −17.7 mm/yr). The mapped
dykes are only 15.7 km, and only 21 % of them have InSAR points. To read the Red River dykes, the dyke lines need
completing first (the official dyke routes, or tracing the crest), and the radar coverage needs completing too
(corner reflectors, or a second geometry).

**Mexico City.** This is the classic subsidence of the lacustrine clays. The lines with the largest distortion
cross the edges of the subsidence bowl:

| Line | Kind | β max | Lowest rate | Flagged stations |
|---|---|---|---|---|
| Autopista México – Puebla | road | 1/127 | −62 mm/yr | 16 |
| Calzada General Ignacio Zaragoza | road | 1/148 | −217 mm/yr | 34 |
| Calzada Ermita Iztapalapa | road | 1/150 | −93 mm/yr | 31 + 34 (two carriageways) |
| Línea VK | railway | 1/154 | −204 mm/yr | 39 |

These places are consistent with the damage reported along Zaragoza and Ermita Iztapalapa and on Line A of the
Metro. A comparison with damage records is step L4 (§6).

### 4.2 Consolidation

| Product | Dates | Sinking cells | Consolidating | Remaining (median / max) | τ median | Check: curve / line |
|---|---|---|---|---|---|---|
| Hanoi S1 | 26 (1 yr) | 4,355 | 4 | 0.2 / 0.3 mm | 0.25 yr | 2.5 / 6.5 mm |
| Hanoi CSK | 18 (3.5 yr) | 745 | 4 | 0 / 0 mm | 0.24 yr | 2.7 / 6.0 mm |
| Mây Chai S1 | 24 (1 yr) | 3,485 | 0 | – | – | – |
| Mexico City S1 | 16 (0.5 yr) | 43,277 | 30 | 25 / 45 mm | 0.27 yr | 14.1 / 26.4 mm |

Few cells qualify, as expected. Most consolidation lasts years to decades, and one year of data sees only its
start. With τ well beyond the span, the curve is not distinguishable from a line.

The Hanoi cells qualify with short τ, and their settlement is almost complete. They read as recent fills that have
nearly finished.

The 30 Mexico City cells come from a six-month series. τ ≈ 0.27 yr is about half of that span. Two other
explanations are as likely as consolidation:

- a seasonal slowdown of pumping-driven subsidence;
- a recent load.

They must be checked with a longer series before any reading.

In every product, the check favours the curve on all the selected cells. This is expected from the selection
(§3.3).

## 5. Limitations

- **OSM completeness.** Railways and main roads are well mapped. Dykes are not: many are absent or mapped only as
  the road on their crest.
- **Coverage.** Dyke slopes (grass, trees) and many embankments return few persistent scatterers. A grey stretch
  is missing data, not stability.
- **Relative rates.** Rates are relative to the reference of the product. They are vertical only under the
  assumption of no horizontal motion.
- **β is local.** β between two stations 100 m apart detects bends at that scale. A long, gentle bend over several
  kilometres is not flagged, even when it lowers a dyke crest; the crest lost covers that case.
- **Short series.** Consolidation needs the bend of the curve to be inside the data. Final settlements and t90
  firm up with every new year of acquisitions.
- **Secondary compression.** Creep after primary consolidation goes on, roughly log-linear in time. The model
  does not include it, so the final settlement is a lower bound where creep matters.

## 6. Research sequence

| Step | Content |
|---|---|
| L1 | Complete the dyke lines: the official dyke routes of the Red River (Hanoi Department of Agriculture), or crest tracing from a DEM |
| L2 | Levelling along a dyke and a railway: validate the station rates and β |
| L3 | Profiles from the decomposed vertical where two geometries are fused |
| L4 | Damage records (track maintenance, road repairs) against β per line |
| C1 | Longer series (3+ years of Sentinel-1 or COSMO-SkyMed) over new urban areas: Hanoi west, Gia Lâm |
| C2 | Works dates and fill heights near the consolidating cells; boreholes for the soft-clay thickness |
| C3 | Hyperbolic method (Tan 1971) and a creep term, compared with the exponential model on the same cells |

## 7. References

- Asaoka, A. (1978). Observational procedure of settlement prediction. *Soils and Foundations*, 18(4), 87–101.
- Bjerrum, L. (1963). Allowable settlement of structures. *Proc. 3rd European Conf. Soil Mech. Found. Eng.*,
  Wiesbaden, 2, 135–137.
- Kass, R. E., & Raftery, A. E. (1995). Bayes factors. *Journal of the American Statistical Association*, 90(430),
  773–795.
- OpenStreetMap contributors. Data under the Open Database License (ODbL); © OpenStreetMap contributors.
- Skempton, A. W., & MacDonald, D. H. (1956). The allowable settlements of buildings. *Proc. Instn Civ. Engrs*,
  5(6), 727–768.
- Tan, S. B. (1971). An empirical method for estimating secondary and total settlement. *Proc. 4th Asian Regional
  Conf. Soil Mech. Found. Eng.*, Bangkok, 2, 147–151.
- Terzaghi, K. (1925). *Erdbaumechanik auf bodenphysikalischer Grundlage*. Deuticke, Vienna.
