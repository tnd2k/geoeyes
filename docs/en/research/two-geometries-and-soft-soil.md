# Two geometries and soft soil

Status: v1 implemented 2026-10-27.
Code: `geoeyes.ml.decompose` (`geoeyes decompose`), `geoeyes.ancillary.geology` and `geoeyes.ml.geology`
(`geoeyes geology`), the layer `soft_soil_m` of `geoeyes.ml.layers` (susceptibility), `geoeyes.api.behaviour`.
Web app: layers "Vertical motion", "East-west motion" and "Soft-soil thickness" on the Thematic analysis page;
Principles, chapter 5.
Related: [lines-and-consolidation.md](lines-and-consolidation.md) (the consolidation that the soft-soil thickness
checks), [groundwater-insar.md](groundwater-insar.md) (the water that the soft layer gives up).

## Contents

1. [Questions](#1-questions)
2. [Vertical and east-west motion](#2-vertical-and-east-west-motion)
3. [Soft-soil thickness](#3-soft-soil-thickness)
4. [First results](#4-first-results)
5. [Limitations](#5-limitations)
6. [Research sequence](#6-research-sequence)
7. [References](#7-references)

## 1. Questions

- **Q5. How much of the line-of-sight motion is vertical?** Every analysis of one product (zoning, lines,
  buildings, consolidation) reads v_LOS / l_u as vertical. That holds only where the ground does not move
  sideways. Around a subsidence bowl and on slopes, it does.
- **Q6. Does the ground sink where the soft layer is thick?** The susceptibility model knew the land cover and
  the buildings, but not the soil that compacts.

## 2. Vertical and east-west motion

### 2.1 Principle

A product measures v_LOS = e·l_e + n·l_n + u·l_u, where (l_e, l_n, l_u) is the unit vector from the ground to
the satellite (`los_e`, `los_n`, `los_u` of `points.parquet`).

Ascending Sentinel-1 passes look from the west (l_e ≈ −0.6), descending ones from the east (l_e ≈ +0.6). Two
products with opposite l_e therefore separate e and u.

The north component is assumed zero. Near-polar orbits are almost blind to it: |l_n| ≈ 0.1–0.15 for Sentinel-1.

### 2.2 Method

1. **Partners.** These are the products of the workspace, taking the latest version of each track, that meet all
   of these conditions:
   - their extent overlaps the product;
   - their common period is at least `min_overlap_share` = 50 % of the shorter one;
   - their look direction differs by |Δl_e| ≥ `min_east_contrast` = 0.5.

   Partners can come from other projects (Mexico City: Sentinel-1 and Capella).
2. **Common support.** The two products see different scatterers at different places, so they must be paired
   somewhere. With `support = "points"`, there is no grid: at every point of the product, each product gives the
   median of its points within `radius_m` (20 m). Mexico City at 15 m: 60,027 locations instead of 1,731 cells of
   100 m, with a median σ_up of 4.1 mm/yr instead of 1.5. With `support = "cells"` (default, also written as
   GeoTIFF), the grid has `cell_m` = 100 m cells, in degrees so that it can also be written as GeoTIFF. Each
   product gives, per cell, the median v_LOS and LOS vector of its points, when there are at least
   `min_points` = 3. The uncertainty of a cell is the largest of these:
   - 1.4826·MAD/√n;
   - the median formal σ/√n;
   - `sigma_floor_mm_yr` = 0.5.
3. **Common reference.** Each product is re-referred to the median of its own velocities over the cells seen by
   all the products. The result is therefore relative to the median motion of the common area.
4. **Solution.** Weighted least squares of [l_e, l_u]·[e, u] = v_LOS over the products, cell by cell, with the
   covariance of (e, u).
5. **Single-geometry error.** For each product, v_LOS / l_u is kept next to u: this is what that product alone
   would call vertical.

A cell has **significant** east-west motion when |e| ≥ `horizontal_mm_yr` = 5 and |e| ≥ 2σ_e.

Outputs, in `analyses/decompose/<product>/`:
- `decompose.parquet`;
- `up.tif`, `east.tif` (mm/yr, up positive, east positive);
- `decompose.json`: products, periods, ranges, uncertainty, the share of significant horizontal motion, and the
  error of each single-geometry vertical.

## 3. Soft-soil thickness

### 3.1 Sources

The first available source is used:

| Source | Configuration | Use |
|---|---|---|
| Map | `[postprocess.geology] raster = "geom/soft_soil.tif"` | thickness of the soft layer (m), any CRS |
| Boreholes | `[postprocess.geology] boreholes = "geom/boreholes.csv"` | columns `lon, lat, thickness_m`; inverse distance (power 2, 8 neighbours) up to `max_borehole_km` = 3 km |
| Open grid | default (`open_fallback = true`) | Pelletier et al. (2016), sediment thickness above bedrock on lowlands, 1 km, capped at 50 m; NASA ORNL DAAC (Earthdata) |

The open grid is not the soft layer. It is a modelled depth to bedrock. In a delta, most cells read the 50 m cap,
and the analysis says so in its warnings.

For Hanoi, the relevant layer is the Holocene clay and peat of the Hải Hưng and Thái Bình formations, up to about
35 m thick. Thickness maps and borehole sets exist in the literature but not as open data:
- BGS and Vietnamese partners: 271 boreholes and a 3D model;
- Phi & Strokova (2017).

### 3.2 Analyses

Per hazard cell (`analyses/geology/<product>/`):

- **Thickness** of the cell from the source.
- **Rate by thickness class** (quantiles): the median rate of the sinking cells and the share of cells moving
  faster than `moving_mm_yr` = 5. The Spearman ρ between thickness and sinking summarises the relation.
- **Consolidation check.** For the consolidating cells (`geoeyes consolidation`), the first term of Terzaghi's
  solution gives τ = 4·H_dr² / (π²·c_v), hence an implied c_v = 4·H_dr² / (π²·τ). H_dr = H/2 when the layer drains
  on both faces. Soft clays have c_v ≈ 0.1–10 m²/yr (Holtz & Kovacs 1981). A value far outside this range means
  either:
  - the thickness is not that of the consolidating layer; or
  - the cell is not consolidating.

### 3.3 In the susceptibility model

The thickness is the predictor `soft_soil_m` of the susceptibility model (group "geology"). Changing the source in
the project rebuilds the layers.

## 4. First results

### 4.1 Decomposition, Mexico City (Sentinel-1 asc 078 + Capella asc)

| | Sentinel-1 asc 078 | Capella asc |
|---|---|---|
| Period | 2024-05-03 → 2024-10-30 | 2024-06-26 → 2024-08-15 (50 days) |
| LOS (l_e, l_n, l_u) | (−0.69, −0.15, 0.71) | (+0.47, −0.46, 0.75) |

The two sensors look from opposite sides, so the pair is decomposable. Results over the common area:

- 1,731 common cells of 100 m;
- vertical −295 to +79 mm/yr;
- east-west −121 to +92 mm/yr;
- median σ: 1.5 mm/yr (vertical), 2.1 mm/yr (east-west).

**This result is not reliable.** The vertical map splits the area in two: the north sinks faster than −30 mm/yr,
and the south "rises" by more than +30 mm/yr. The east-west map shows the same kind of large-scale gradient. Both
are typical of a ramp, orbital or atmospheric, in a velocity estimated from 50 days of Capella data. They are not
ground motion.

The formal σ do not include such errors, so "significant east-west motion in 88 % of the cells" says nothing about
the ground. The Mexico City pair shows the method working, not a result. A Capella series covering the Sentinel-1
period is needed.

The Capella line of sight also has a large north component (l_n = −0.46). Assuming n = 0 is weaker for this pair
than for two Sentinel-1 tracks.

### 4.2 Decomposition, Hanoi (Sentinel-1 desc 091 + asc 128)

Ascending track 128 over the same area and period as descending track 91 was added to the project `hanoi_s1`:

| | Sentinel-1 desc 091 (v4) | Sentinel-1 asc 128 (v1) |
|---|---|---|
| Period | 2025-10-01 → 2026-10-15 | 2025-10-04 → 2026-10-18 |
| Points | 729,552 | 718,106 |
| LOS (l_e, l_u) | (+0.62, 0.78) | (−0.65, 0.76) |

**A ramp in the ascending product.** A plane fitted to each product's velocities over the common area spans
3.9 mm/yr for desc 091 and **26.9 mm/yr** for asc 128 (R² 0.11 against 0.60). A ground tilt would show in both
lines of sight alike (l_u ≈ 0.77 for both), so the tilt of asc 128 alone is an error: orbit, or atmosphere left
after the ERA5 correction. Decomposed as it is, this ramp becomes east-west motion:
- east-west from −11.7 to +11.4 mm/yr (p2–p98);
- "significant" in 41 % of the cells;
- east and up correlated at −0.80.

GeoEyes now detects such a ramp and warns. For Hanoi the plane is removed before the decomposition
(`deramp = "plane"` in the project). Results on 12,658 common cells of 100 m:

| | Without ramp removal | With ramp removal |
|---|---|---|
| Vertical, p2 … p98 (min) | −11.8 … +12.4 | **−10.3 … +5.9** (−27.5) mm/yr |
| East-west, p2 … p98 | −11.7 … +11.4 | −6.9 … +7.6 mm/yr |
| Cells with "significant" east-west | 41 % | 18 % |
| Correlation east / up | −0.80 | −0.59 |
| Single-geometry vertical off by (90 % of cells) | 7.7 / 8.4 mm/yr | 4.8 / 5.2 mm/yr |

**Is the remaining east-west motion real?** Two tests:
- It gathers around the fast-sinking cells: 41 % of the cells sinking faster than 10 mm/yr, 7 % of the stable
  ones. This would fit a ground converging towards the bowls.
- But it does **not** point towards them. Within 0.1–1.5 km of a fast-sinking cell, 48–53 % of the cells move
  towards it, which is chance.

It is therefore the remaining disagreement of the two products (non-planar atmosphere, unwrapping). An error in
one line of sight maps into both e and u, which also explains why it gathers where the motion is large.

The empirical noise of e is better read from the stable cells: median |e| = 1.8 mm/yr, i.e. σ_e ≈ 2.7 mm/yr, about
four times the formal 0.64. Only east-west motion above ~5–8 mm/yr should be read.

**What to keep for Hanoi:**
- The decomposed vertical: −27 mm/yr at most, with sinking areas consistent with the descending product.
- An error of about 5 mm/yr (90 % of cells) in the vertical projection of one product. This is an upper bound,
  since it includes the noise of the decomposition.
- No measurable horizontal motion at this precision.
- The ramp of asc 128 is ionospheric (below); until it is corrected, that product should not be used alone.

**Origin of the ramp: the ionosphere at dusk.** Five checks (scripts in the session, data in the workspace):

| Check | Result | Reading |
|---|---|---|
| Processing parameters of the two PS runs | identical | not a setting |
| Plane of each phase component, as a velocity (asc 128) | unwrapped phase ~20 mm/yr; ERA5 correction 1.7; DEM error 2.7; correlated noise 0.7 | already in the interferograms; not ERA5, not the DEM error |
| Plane of each interferogram | asc 2.0 mm/km (median), desc 0.8; mostly north-south; shrinking from autumn 2025 to autumn 2026 | an error of the ascending acquisitions, along the flight direction |
| Acquisition time; GIM vertical TEC over Hanoi (CODE IONEX, CDDIS) | asc 11:06 UTC = **18:06 local**, 39–111 TECU; desc 22:50 UTC = 05:50 local, 8–19 TECU | the ascending passes see ~6 times more ionosphere |
| ESD azimuth shift per date (stack) | asc mean 0.035 lines, desc 0.013; ESD against north ramp: asc **r = −0.56 (p = 0.003)**, desc r = +0.19 (p = 0.37) | an azimuth (north-south) ionospheric gradient shifts the TOPS bursts and bends the phase together |

Hanoi lies under the northern crest of the equatorial ionization anomaly. After sunset, near the maximum of solar
cycle 25, the electron content there is high and changes quickly in latitude. The ascending passes (18:06) catch
it, the descending ones (05:50) do not.

The per-date ramps change through the year (higher TEC in autumn 2025, lower in 2026). Their trend becomes a ramp
in the velocity. Orbits are ruled out: precise orbits for both tracks, except the last ascending date (restituted
orbit).

The GIM, at 2.5° × 5°, does not resolve gradients over 15 km: its predicted ramps are 15 times smaller and
uncorrelated with the measured ones. It only gives the TEC level.

**Correction.** The proper fix is the range split-spectrum (Gomba et al. 2016; Liang & Fielding 2017): two
sub-band interferograms separate the dispersive (ionospheric) phase. The stack stores flattened SLCs, so the
geometric phase must be recomputed exactly from the orbits before splitting: about half of any error in it leaks
into the ionospheric estimate. Until then, a plane removed per date or from the velocity (`deramp = "plane"`) takes
out the planar part, together with any real tilt of the area.

**Reprocessing (2026-10-26 … 28).** The split-spectrum was then implemented in the stack (`ionosphere = "split"`)
and asc 128 reprocessed several times:
- v2: plane over the crop only;
- v3: a local plane over the whole bursts (Gaussian weight of 10 km around the crop).

With the ionosphere removed, a second error stood out: a **straight step of 6–10 mm/yr along the IW2/IW3 seam**
(incidence 41.78°, parallel to the flight direction). The descending track, IW2 only, has no step there. It is not
a surface rupture. On 9 of the 25 dates the interferogram of IW3 is offset by a constant of about −2.2 rad
against IW2 (the other dates: ±0.2 rad). These are exactly the dates whose ESD differs by +0.012 lines between the
subswaths. The cut-and-paste mosaic turns that constant into a step, and the time series into a velocity.

The root cause is unknown. The step does not follow the mission (S1A/S1D), the IPF version, burst framing, timing
or Doppler.

The fix, in the merge:
- **v4:** per date, measure the phase step across each seam (two strips of 40 columns, coherence-weighted, per
  block of 32 lines) and remove it before the mosaic.
- **v6:** take the widest subswath as anchor, and take the same measured step out of the low sub-band of each
  subswath before the split-spectrum (`WideArea.shift`). A frequency-independent constant c would otherwise pass
  as a·c (a ≈ 0.5) into the ionospheric estimate.
- **v5 (rejected):** fitted the step as a free constant per subswath in the ionospheric model. It came out at
  ±4.6 rad even on dates without a step, trading off with the range gradient.

Same script for every product; step = median velocity within 0.08° of incidence on each side of the seam; gx, gy
from a plane over the area (mm/yr/km); E–U = decomposition with desc 091 v4:

| | Seam step | gx | gy | Std | Median σ | E–U with plane removed: horizontal / corr | E–U as is: horizontal / corr |
|---|---|---|---|---|---|---|---|
| v1 (no correction) | +8.0 | +0.75 | −1.50 | 8.17 | 3.92 | 17.8 % / −0.59 | 41 % / −0.80 |
| v3 (ionosphere) | +9.6 | +0.22 | −0.79 | 6.34 | 4.38 | | |
| v4 (+ seam) | +0.9 | −0.58 | −0.92 | 5.75 | 4.08 | 5.6 % / −0.26 | 17.1 % / −0.59 |
| v6 (+ step out of the sub-bands) | +1.4 | −0.49 | −0.77 | 5.21 | 3.89 | **4.2 % / −0.16** | 11.5 % / −0.51 |
| desc 091 v4 | — | −0.02 | −0.20 | 3.92 | 2.64 | | |

v6 is the product to use. About −0.8 mm/yr/km north-south is left, which the descending track does not have.
North-south motion hardly enters either line of sight, so this is still an error of the ascending track. It is not
ionosphere left over: per date it is barely correlated with the ionospheric gradient removed (r = 0.18) and varies
ten times more than that estimate's formal error; it is largest in summer. Most likely evening convection that ERA5
misses ([guide/ionosphere.md §6](../guide/ionosphere.md#6-the-hanoi-case)). Keep `deramp = "plane"` for the
decomposition.

With `support = "points"` (20 m), there are 572,309 locations with the same distribution (before ramp removal: σ_up
1.0, σ_e 1.2 mm/yr formal).

### 4.3 Soft-soil thickness (open grid) against sinking

| Product | Cells at the 50 m cap | Spearman ρ (thickness vs sinking) | Median rate by thickness class |
|---|---|---|---|
| Mexico City S1 | 59 % | **0.51** | 0–9 m: −97; 9–49 m: −116; 49–50 m: −204 mm/yr |
| Hanoi S1 | 92 % | −0.11 | one class (27–50 m): −2.6 mm/yr |
| Hanoi CSK | 82 % | 0.01 | one class |

**Mexico City.** Even the coarse open grid separates the lacustrine basin (thick, capped) from the volcanic
ranges (thin). The cells sink twice as fast where the deposits are thickest.

**Hanoi.** The grid is capped almost everywhere and says nothing. A Holocene thickness map is needed.

**Consolidation check.** The implied c_v of the consolidating cells is 830–1,000 m²/yr in every product, about
100 times the range of soft clays. With the bedrock depth (50 m) as H, the short τ (0.25 yr) of these cells
cannot be the consolidation of the whole column. Two readings are possible:
- they consolidate a thin layer near the surface (fill, a few metres);
- they are not consolidating.

The check works as intended: it rejects a thickness that cannot be the consolidating layer.

### 4.4 Susceptibility with soft-soil thickness

AUC by spatial cross-validation, with and without the layer `soft_soil_m` (open grid). All other layers and
settings are the same.

| Product | Model | Without | With |
|---|---|---|---|
| Mexico City S1 | gradient boosting (chosen) | 0.869 | **0.918** |
| | random forest | 0.777 | 0.894 |
| | logistic | 0.729 | 0.851 |
| Hanoi S1 | gradient boosting (chosen) | 0.718 | **0.734** |
| | random forest | 0.717 | 0.732 |
| | logistic | 0.698 | 0.708 |

- **Mexico City:** the thickness becomes the most important predictor (permutation importance 0.15, against 0.06
  for the next).
- **Hanoi:** the gain is small. It comes from the edges of the grid, where the thickness drops below the cap, and
  is not a reading of the soft layer.

## 5. Limitations

- **Period.** The decomposition assumes that the products see the same motion. Their periods must overlap; if not,
  constant rates are assumed and a warning is given.
- **North-south.** North-south motion is ignored; with an oblique sensor (Capella), part of it leaks into e and u.
- **Relative result.** The result is relative to the median of the common area. Tie it to a GNSS station for
  absolute values; the hazard GNSS tie is per product and is not carried over yet.
- **Formal uncertainties.** The uncertainties do not include ramps or atmosphere that differ between the products,
  and short series are the most affected.
- **Open grid.** The open thickness is a placeholder. The Mexico City relation shows that thickness matters, not
  that the grid is right; in Hanoi it carries no information.
- **Borehole interpolation.** Inverse distance draws no geology between boreholes: palaeochannels and terrace edges
  need a map.

## 6. Research sequence

| Step | Content |
|---|---|
| D1 | Hanoi asc 128 + desc 091: vertical and east-west over the same year; single-geometry error of the zoning |
| D2 | Use the decomposed vertical in the zoning, the lines and the buildings wherever two geometries exist |
| D3 | GNSS tie of the decomposition (horizontal velocities of the stations), and north from a third geometry |
| D4 | Time series decomposition on common monthly epochs |
| D5 | Ionospheric correction by range split-spectrum in the stack (exact geometric phase from the orbits); first on Hanoi asc 128, then on every dusk-pass product near the equatorial anomaly |
| G1 | Holocene soft-soil thickness of Hanoi: digitise a published map (e.g. Phi & Strokova 2017) or obtain the boreholes (BGS 3D model, Hanoi University of Mining and Geology) |
| G2 | Rate against thickness with the real map; c_v of the consolidating cells against laboratory values |
| G3 | Groundwater level observations (national monitoring network) with the thickness: settlement per metre of head drop |

## 7. References

- Gomba, G., Parizzi, A., De Zan, F., Eineder, M., & Bamler, R. (2016). Toward operational compensation of
  ionospheric effects in SAR interferograms: the split-spectrum method. *IEEE Transactions on Geoscience and Remote
  Sensing*, 54(3), 1446–1461.
- Liang, C., & Fielding, E. J. (2017). Measuring azimuth deformation with L-band ALOS-2 ScanSAR interferometry.
  *IEEE Transactions on Geoscience and Remote Sensing*, 55(5), 2725–2738.
- Fuhrmann, T., & Garthwaite, M. C. (2019). Resolving three-dimensional surface motion with InSAR: constraints
  from multi-geometry data fusion. *Remote Sensing*, 11(3), 241.
- Holtz, R. D., & Kovacs, W. D. (1981). *An Introduction to Geotechnical Engineering*. Prentice-Hall.
- Pelletier, J. D., et al. (2016). A gridded global data set of soil, intact regolith, and sedimentary deposit
  thicknesses for regional and global land surface modeling. *Journal of Advances in Modeling Earth Systems*, 8,
  41–65. Data: ORNL DAAC, doi:10.3334/ORNLDAAC/1304.
- Phi Hong Thinh, & Strokova, L. A. (2017). [Quaternary deposits, engineering-geological sections and maps of the
  thickness of soft soils of Hanoi; in Russian]. *Izvestiya Tomskogo Politekhnicheskogo Universiteta*, 328(4).
- Terzaghi, K. (1925). *Erdbaumechanik auf bodenphysikalischer Grundlage*. Deuticke, Vienna.
- Wright, T. J., Parsons, B. E., & Lu, Z. (2004). Toward mapping surface deformation in three dimensions using
  InSAR. *Geophysical Research Letters*, 31, L01607.
