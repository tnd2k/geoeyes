# Learning path: one interferometric pair, step by step

The **Principles** page of the web app has two chapters:

- **Chapter 1 · One interferometric pair** (this guide) takes a newcomer from two single SLC scenes to a velocity.
  It uses one pair of an existing stack and a small area (1–5 km), and shows what every processing step does to
  the data.
- **Chapter 2 · Hazard zoning** (`#/learn-hazard/<step>`) explains, in eight steps, how the map of the Thematic
  analysis page is made: analysis cells, terrain and process, motion in the hazard direction, intensity,
  damage potential, hazard matrix, rainfall coupling and groundwater coupling. Method and sources:
  [rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md) and
  [groundwater-insar.md](../research/groundwater-insar.md).

- **Before unwrapping**, it follows the steps of the old `flat_earth_gui`:
  - raw interferogram;
  - flat-earth and topographic phase;
  - coherence;
  - Goldstein filtering.
- **The rest uses the GeoEyes algorithms:**
  - coregistration as done by the stack builder;
  - unwrapping with the IRLS solver of the PS chain;
  - velocity from the product's time series.

Code: `geoeyes.learn.pair` (computation), `geoeyes.api.learn` (API), `webapp/src/pages/Learn.tsx` (page).

## Opening it

1. Choose **Principles** in the top bar, then a project and one of its stacks in the left column. The project needs
   at least a stack; the last step also needs a product with points.
2. Step 0 picks the pair and the area:
   - the baseline plot shows every date against its perpendicular baseline, and two clicks form a pair;
   - the amplitude of the reference scene shows the whole stack, and a click moves the area;
   - the default pair is the stack reference and its nearest date (best coherence for a first look).

The link `#/learn/<project>/<stack>/<step>` opens a given step.

## The steps

All images are the multilooked crop **in radar geometry**: rows are azimuth and columns are range, so north is
not up. They are displayed with their ground aspect ratio. The cursor is linked across images, and a bar under the
images reads every layer at the cursor.

| # | Step | Images | What is computed | Try it |
|---|---|---|---|---|
| 0 | Pair and area | baseline plot, amplitude of the stack | default pair and looks (about 400 pixels across) | pair, window size, looks |
| 1 | Two SLC scenes | amplitude of each scene (dB) | multilooked power | phase-linked SLCs (CSK) |
| 2 | Coregistration | colour composite (scene 1 red, scene 2 cyan), blink | residual offset (stripmap) or ESD shift (Sentinel-1) from the stack | – |
| 3 | Raw interferogram | raw phase, amplitude | s₁·s₂* with the geometric phase added back (below) | – |
| 4 | Flat earth | model, phase after removal | ∫ kₕ cos θ dr; predicted against measured fringe rate | – |
| 5 | Topography | DEM, model kₕ·h, differential interferogram | height of ambiguity 2π/kₕ | – |
| 6 | Coherence | coherence, differential phase dimmed below a threshold | \|Σ s₁s₂*\| / √(Σ\|s₁\|² Σ\|s₂\|²) | window, threshold |
| 7 | Goldstein filter | phase before and after, residues as dots | `processing.unwrap.goldstein`; residue count | α, window, passes |
| 8 | Unwrapping | wrapped and unwrapped phase, profile along the cursor row | `processing.ps.unwrap.irls.irls_unwrap_weighted`, weights γ² | reference point; exercise (below) |
| 9 | Displacement | LOS displacement (mm), coherence | d = −φλ/4π; mm per fringe = λ/2 | reference point |
| 10 | Velocity | PS velocities of the product over the area | series of a clicked point, line fitted, rate of the pair alone | click a point |

**Unwrapping exercise (step 8).** Once the geometry is removed, a short pair over a city often has almost no
fringes left, so its unwrapping changes little. The exercise unwraps the *raw* phase with the same filter and
solver. Its dense flat-earth fringes turn the sawtooth of the wrapped phase into a visible ramp.

## The raw interferogram is rebuilt

The SLCs of a GeoEyes stack are coregistered **and flattened**:

- each secondary is stored as `res · exp(j·geom)`, with `geom = 4π/λ (R_sec − R_ref)` for the reference surface
  and the DEM;
- so `slc_i · conj(slc_j)` is already the differential interferogram;
- the raw data and the geometric phase are not kept.

To show the classic chain, the page rebuilds the geometric phase of the pair from the stored layers:

- **Topography:** `kₕ · h`, where `kₕ = d geom / dh` is stored per date (rad per m) and `h` is the DEM height per
  pixel (ellipsoidal). For a pair, `kₕ = kₕ,j − kₕ,i`.
- **Flat earth:** at constant height, a change dr of slant range changes the look angle as a height change
  dh = dr · cos θ does, so `d geom / dr = kₕ · cos θ`. It is integrated along range, with 0 at the centre of the
  area.

The raw phase is the differential phase plus both terms. It is an illustration, with these approximations:

- Earth curvature within the area is ignored.
- The model is relative: constants are removed.
- The flat-earth term does not include the small along-track change of the baseline.

The check is the fringe rate. On Hanoi CSK (B⊥ = 102 m) the model predicts 8.2 fringes/km. The raw phase shows 8.3,
and 0.5 remain after removal.

## Sign and units

- A range increase (motion away from the satellite) adds +4πd/λ to `slc_i · conj(slc_j)`.
- Displacement is −φλ/4π: positive toward the satellite. In the displacement and velocity images, red is away
  (sinking) and blue is toward.
- The velocity colour scale covers the full range of the points, symmetric around zero.
- The amplitude is stretched over its 2–98 % range.

## Limits

- **Pair and stack layers.** Step 10 uses the latest product of the stack's track. Its velocities are relative to
  the product's reference; the pair's displacement is relative to its own reference point. A difference between
  the two rates is expected: the pair also holds the atmosphere of both dates.
- **Coherence bias.** Coherence from a small window is biased upward where the true coherence is low.
- **2-D versus 3-D unwrapping.** The 2-D unwrapping here is that of one interferogram. The PS chain unwraps the
  persistent scatterers in space and time.
- **Size limits.** The crop is limited to 4 million full-resolution pixels and 700 multilooked pixels per side.

## API

| Route | Returns |
|---|---|
| `GET /api/projects/{p}/learn` | stacks with dates, baselines, spacing and the default pair and crop |
| `GET /api/projects/{p}/learn/{stack}/thumb(.bin)` | reference amplitude of the whole stack (float32) |
| `GET /api/projects/{p}/learn/{stack}/pair(.bin)?first&second&row0&col0&rows&cols&looks_az&looks_rg&…` | meta and layers (float32, one after the other in `meta.layers` order) |
| `GET /api/projects/{p}/learn/{stack}/points?…` | PS of the product over the crop, on the multilooked grid |
| `GET /api/projects/{p}/learn/series/{product}/{uid}` | series of one point and its fitted line |

The optional parameters are `coh_win`, `alpha`, `fft`, `passes`, `linked`, `ref_row`, `ref_col` and `exercise`.
