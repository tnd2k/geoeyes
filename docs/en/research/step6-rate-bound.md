# Step 6: bounding the rates from the data (plan, 2026-11-08)

## Problem

hcm_d18 v6 has a tail of very fast PS: −93 mm/yr at the extreme and 617 PS faster than −40 mm/yr. About half of
those PS drift away from the PS around them over the years. The spatial filter in the product (`[product]
spatial_filter`) removes 0.55 % of the PS but keeps the −93 cluster, because its neighbours are fast too.

The owner wants step 6 itself to stop producing these velocities, so the product no longer needs a hand-tuned
colour range (±20 mm/yr reads right for HCMC).

## Where step 6 makes a rate

Both places search a fixed range of ±`unwrap_max_edge_velocity` (100 mm/yr):

1. `space_time.edge_rates`: the linear rate of every grid edge. This is the rate *difference* between two
   adjacent cells, 50 m apart. A rate is accepted when its periodogram coherence is above chance and
   `min_gain` above rate 0.
2. `ps_rate.ps_rate_model`: the rate of every Delaunay arc between PS (up to 500 m). These are integrated by L1
   into one rate per PS.

The rate of an edge or arc is a velocity *gradient*. Even across the edge of a subsidence bowl it is rarely more
than a few mm/yr per 50 m. A noisy edge whose periodogram peaks far out (for example 60–90 mm/yr) can still pass
the chance test. Integrating it then puts a whole cluster of PS at that rate. The −93 tail sits just inside the
±100 bound, which supports this.

## Idea

Do not search the same ±100 mm/yr for every edge. Bound or penalise the rate *from the data*.

- **A. Data-driven bound.** First pass: compute the edge rates as now. Take the distribution of the *reliable*
  rates, scaled to the edge length. Then set the bound to `clip(c × P99(|rate|), floor, 100)` and search again
  within it. Edges whose best rate lies outside the bound get rate 0, which is the legacy model.
- **B. Penalised periodogram (recommended to try first).** Pick the trial rate that maximises
  `coh(r) − λ·|r| / r_scale`, so that a large rate wins only when it is clearly more coherent than a small one.
  `r_scale` comes from the reliable rates (as in A), so nothing is tuned by hand. This removes chance peaks far
  out without capping real fast gradients that are strongly coherent.
- **C. Rate per metre for the PS arcs.** In `ps_rate`, apply the bound to rate / arc length, because arcs range
  from about 10 m to 500 m.

## Steps (one at a time, review after each)

- **S0. Diagnostic.** Rerun hcm_d18 step 6 with the edge and arc rates saved. Check whether the PS of the tail
  (v < −40, especially the −93 cluster) sit behind edges or arcs whose accepted rate is large (> 20 mm/yr) and
  barely above chance. *If not, the cause is elsewhere and the plan changes.*
- **S1.** Implement B (and the bound in A as a guard) in `edge_rates`, behind `[ps] unwrap_rate_prior` =
  "auto" | "n". Add synthetic tests: a real bowl with steep edges is kept; a chance peak at 80 mm/yr on a noisy
  edge is rejected.
- **S2.** Apply C in `ps_rate_model`.
- **S3.** Rerun hcm_d18 steps 6–8 (lean checkpoints, about 4 GB). Compare with the current result: the tail
  (number of PS < −40 and min v), outlier epochs, how many PS the spatial filter still removes, and the stable
  NMAD. Check the CSK Hanoi golden case (17 ifg) and hanoi_s1_desc.
- **S4.** Decide the default, update the docs and the advisor, and note the result here.

## S0 result (2026-11-08): hypothesis rejected

I reran hcm_d18 steps 6–8 with v6 settings and recorded every periodogram decision
(`ps_exp/S0/s0_rates.npz`, deleted after the review).

- **The grid edges do not make the tail.** Only 2.6 % of the 110k edges get a rate at all. 23 edges are above
  40 mm/yr.
- **The PS rate model sets the tail velocity.** For 95 % of the PS faster than −40 mm/yr, the final velocity is
  within 10 mm/yr of their ps_rate model rate (correlation over all PS −0.988, sign of phase).
- **The arcs behind the fastest PS are not chance peaks.** 57 % of the arcs touching a PS faster than −60 mm/yr
  carry a rate above 20 mm/yr, against 0.42 % of all arcs. Their periodogram coherence is 0.17 above chance. It
  is also **0.21 above the best rate within ±20 mm/yr**, so a penalised periodogram (idea B) would not change
  them.
- **The fast PS come in tight groups.** The 48 PS faster than −60 mm/yr form 17 groups (links up to 60 m), of 3–6
  PS each with nearly the same rate. Examples:
  - 6 PS at 106.6972 E, 10.6833 N, −93 … −78 mm/yr;
  - 5 PS at 106.6821 E, 10.6951 N, −68 … −65 mm/yr.

  Only 2 of the 48 PS are alone. The 629 PS faster than −40 mm/yr form 133 groups, the largest of 28 PS.

**Conclusion.** The wrapped phase itself says these PS move coherently faster than the PS around them: single
structures or small blocks, likely new building on soft ground. Step 6 is not inventing them, and bounding the
rates in step 6 would remove real signal. Ideas A–C are therefore not implemented.

The tail is handled downstream instead:
- the product's spatial filter removes the isolated PS (0.55 % of all PS);
- the legend classes span P0.1–P99.9.

## Risk

Real fast local motion (a single building on new fill) has a steep gradient by nature. B keeps it only when it
is coherent. S0 and S3 must show how many such PS are lost.
