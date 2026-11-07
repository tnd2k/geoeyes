# Skill: coregistration quality check of a stack

> Is the coregistered stack good enough to process? For every date against the reference: amplitude, wrapped
> interferogram, coherence, the offset left by the coregistration and the amplitude correlation. Status:
> operational (new, 2026-11). Last checked 2026-11-01. CLI: `geoeyes stack-qc <project> [--stack ID]`. Web app:
> project page → Stack tab (*Check the stack* / *Check again*).

## 1. When to use it

- After `build_stack` and before the point engine: a misregistered date ruins its interferogram and, through the
  unwrapping, the whole series.
- When a product looks wrong (a date of noise, a blocky velocity map) and you need to know whether the stack or the
  PS processing is at fault.
- After a change of the coregistration (`[stack] coreg_model`, a new engine version, new scenes).
- It decides: process as is, drop a date (`[acquire] date_range`, remove its folder, `[ps_lite] exclude_dates`), or
  fix the coregistration. It does not judge the phase-linked SLC (`slc_linked`), nor the PS selection.

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Coregistered stack | yes | phase `build_stack` of [insar-processing.md](insar-processing.md) | `projects/<name>/stacks/<stack_id>/stack.zarr` with `slc` (date, y, x) | stack id `<track_id>-ref<YYYYMMDD>` |
| Reference date | auto | stack attribute `reference_date` | — | if missing: the date of smallest |B⊥| |
| `bperp`, `kh` | optional | written by the builders | stack variables | without `kh` the height of ambiguity is empty; without `bperp`, 0 |
| Pixel spacing, incidence | optional | stack attributes `azimuth_pixel_spacing_m`, `range_pixel_spacing_m`, variable `geometry_incidence` (else attribute `incidence_deg`, else 40°) | — | sets the looks |
| Disk | yes | — | `stacks/<stack_id>/qc/` | three PNG per date + `qc.json`, a few MB |

Checklist:

- [ ] `build_stack` is *done* in `geoeyes status <project>`.
- [ ] The stack id is known (`stacks/` folder names), or let the command take every stack of the project.
- [ ] Sentinel-1: the check is not run by itself (large stacks); start it by hand.

## 3. Method

Code: `src/geoeyes/processing/stack/qc.py` (`stack_qc(store, size=1200, crop=2048)`).

1. **Looks.** Ground-range spacing g_r = r / max(sin θ, 0.2) with θ the median incidence of the central line; ground
   size of an output pixel c = max(n_y·a, n_x·g_r) / `size`; looks (l_y, l_x) = (round(c / a), round(c / g_r)), at
   least 1. The image is about 1200 pixels on its longer side, with square ground cells.
2. **Amplitude** of each date: 10·log10(Σ|s|² / (l_y·l_x)) in dB, displayed with a 2–98 % stretch (image only).
3. **Interferogram** against the reference, as stored: I = Σ_looks r·conj(s). The stack SLC is already flattened (the
   geometric phase of orbits + DEM removed): what remains is topography left by the DEM, motion, atmosphere and
   noise. Wrapped phase arg I shown from −π to π.
4. **Coherence** over the looks: γ = |Σ r·s*| / sqrt(Σ|r|² · Σ|s|²); per date `coherence_mean` and
   `coherence_p90`.
5. **Offset left** on a central crop at full resolution (2048 × 2048, or the image if smaller):
   - coarse integer offset (`sicd_stack.coarse_offset`, window `min(1024, crop)`): phase correlation of
     log(1+|a|) in 9 windows centred at 25 / 50 / 75 % of each axis; a window counts if its error < 0.97 and the
     secondary has ≤ 20 % zeros; median shift; accepted only if ≥ max(2, half of the windows) agree within 3 px,
     else 0;
   - if the coarse offset is zero: sub-pixel residual (`stripmap.residual_offset`): amplitude phase correlation on
     256-px tiles every 128 px, upsampling 20, tiles with > 5 % zeros skipped, tiles kept if error < 0.9, median
     of ≥ 4 tiles, else 0;
   - reported as `offset_lines`, `offset_samples` (pixels; convention: to add to the secondary's line / sample).
6. **Amplitude correlation** on the crop: Pearson correlation of log(1+|r|) and log(1+|s|).
7. **Height of ambiguity**: HoA = 2π / median|kh| over the 128 × 128 pixels at the crop centre (m); `bperp_m` from
   the stack.

Grading used by the web table (`webapp/src/components/StackQc.tsx`):

| Figure | Good | Review | Bad |
|---|---|---|---|
| max(|offset_lines|, |offset_samples|) | ≤ 0.1 px | ≤ 1 px | > 1 px |
| `coherence_mean` | ≥ 0.4 | ≥ 0.2 | < 0.2 |

`build_stack` runs the check at the end for every sensor but Sentinel-1 and logs a warning when the largest offset
exceeds 1 px ("the coregistration failed for some of them"); a failure of the check never fails the build.

The unit test (`tests/unit/processing/test_stack_qc.py`) builds a synthetic 3-date stack (1200 × 1000 px, a fringe
ramp, bright targets): the well-registered date must give coherence > 0.6 and offsets < 0.2 px, the date shifted by
40 lines coherence < 0.3 and an offset of 40 ± 1 lines, and the three PNG plus `qc.json` must be written.

## 4. Steps

1. **Run the check.** `geoeyes stack-qc <project>` (every stack in `stacks/`) or `--stack <stack_id>` (repeatable).
   About a minute or two for a spotlight stack (`api/app.py`); longer for large S1 stacks (every date is read in full
   once). Web app: Stack tab → *Check the stack*; with several stacks, choose one in the list first.
2. **Read the table.** CLI prints per date: `Bperp`, `HoA`, coherence mean (p90), offset lines / samples, amplitude
   corr, and the output folder. Web app: the same table, coloured with the thresholds above.
3. **Look at the images.** Click a date row: amplitude, interferogram, coherence side by side; click an image for
   full size.
4. **Decide.** All good → `geoeyes run <project>` continues to `ps`. A bad date → see §6.
5. **After a rebuild,** check again: the page warns "The stack was rebuilt after this check" when the store is newer
   than `qc.json` by more than 60 s.

Files written: `stacks/<stack_id>/qc/amp_<date>.png`, `ifg_<date>.png`, `coh_<date>.png` (not for the reference) and
`qc.json`.

## 5. Outputs and how to read them

`qc.json` (schema `geoeyes.stack_qc/1`): `stack`, `created`, `reference_date`, `shape`, `looks`, `image_shape`,
`crop` (rows / columns of the crop), `orientation` (radar geometry: rows = azimuth lines, columns = range samples)
and `dates`: `date`, `days` (from the first date), `reference`, `bperp_m`, and for the secondaries
`coherence_mean`, `coherence_p90`, `height_of_ambiguity_m`, `offset_lines`, `offset_samples`, `amplitude_corr`.

- Interferogram: fringes or a smooth phase where the coherence is high is a good date; dense fringes that follow
  the relief at a large |B⊥| (small HoA) are DEM error, not misregistration.
- Coherence image: decorrelation that follows land cover (water, vegetation) is normal; a uniformly dark date is not.
- Amplitude correlation: compare with the best pair of the stack; a date far below the others while its amplitude
  shows the same buildings is misregistered.
- Offset: tens of pixels with noise in the interferogram = coregistration failed for that date (the Umbra case
  before the coarse search: acquisitions placed 15–25 m apart by their orbits, ../guide/projects-and-data.md §5).

## 6. Quality checks

Accept the stack when, for every secondary date: offset ≤ 0.1 px, coherence and amplitude correlation in line with
the dates of similar B⊥ and time span, and the interferogram coherent where the amplitude shows stable structures.
Then:

- one date bad, others good: drop it (remove its folder or exclude it by `date_range`; `ps_lite`:
  `[ps_lite] exclude_dates`) and rebuild;
- offsets of a few tenths of a pixel growing with height in steep terrain: try `[stack] coreg_model = "terrain"`;
- many dates bad: check the DEM, the orbits (S1 POEORB), the scene geometry (beam, PRF, incidence), and the build log.

## 7. Limits and pitfalls

- An offset of exactly 0.00 can mean "not measured": fewer than 4 correlating tiles (water, featureless crop) or
  coarse windows that disagree. Read it with the coherence and the amplitude correlation.
- When a coarse offset is found, the sub-pixel residual is not measured: the value is an integer.
- Offsets and amplitude correlation come from the central crop only; a misregistration elsewhere (edges, other
  relief) is seen only in the coherence and interferogram images.
- Coherence over few looks is biased upward; compare dates with one another, not with an absolute value.
- The check reads `slc`, not `slc_linked`: it says nothing about phase linking.
- Not run by itself for Sentinel-1; the stack check is informative and never blocks a run.

## 8. On a new area or sensor

- Thresholds are the same for every sensor; what changes is the expected coherence (X-band over vegetation, long
  time spans, Umbra look-angle differences give low values on good dates).
- For a spotlight stack, a coherent date should show the buildings and roads of the amplitude image in the
  coherence image.
- `size` and `crop` are function arguments (`stack_qc(store, size=..., crop=...)`), not project settings.

## 9. References

- Code: `src/geoeyes/processing/stack/qc.py`, `processing/stack/native/sicd_stack.py` (`coarse_offset`),
  `processing/stack/native/stripmap.py` (`residual_offset`), `controller/phases/build_stack.py` (automatic check),
  `cli/main.py` (`cmd_stack_qc`), `api/app.py` (`/api/projects/{name}/stacks`, `/stacks/{sid}/qc`),
  `webapp/src/components/StackQc.tsx`, `tests/unit/processing/test_stack_qc.py`.
- Guide: ../guide/projects-and-data.md §5 (Checking the stack before the points). Decisions: ADR-029.
- Skills: [insar-processing.md](insar-processing.md), [opendata-stacks.md](opendata-stacks.md).
- Touzi et al. 1999 (coherence estimation and its bias); Guizar-Sicairos et al. 2008 (sub-pixel phase correlation,
  used by `skimage.registration.phase_cross_correlation`).
