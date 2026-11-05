# Landslide forecast system for central Vietnam — design and work plan

> Design document. Status: **F0–F2 under way** (plan 2026-11-03; F0–F2 started 2026-11-03, §9.1; reviewed
> 2026-11-05). It turns the research of
> [`landslide-susceptibility.md`](landslide-susceptibility.md) (steps L0–L9) into a forecast that people can use.
> Owner's requirement (2026-11-03): *it must truly succeed and become a usable forecasting system: reliable, with
> full uncertainty, defensible from an expert's point of view, professional. Other topics can wait.*
> Each step (§9) ends with a review by the owner before the next one starts.

> **Review 2026-11-05: direction.**
> - *Rarity*: A1–A5 are verified at district / warning-zone scale or on multi-day windows; the commune is for display.
> - *Alert fatigue*: the false-alarm budget is agreed region-wide as a false-alarm ratio (FAR), not only per commune.
> - *Reporting bias*: one full season and one province (ideally with Sentinel-2 dated scars) are held out as the
>   final test before F9.
> - *InSAR*: the operations design of §8.3 is frozen until L5 shows skill (coverage < 15 %; C-band coherence ~0.1 at
>   36 days under forest).
> - *KTTV gauges* are the critical path: escalate now; fallback provincial gauges / the NCHMF radar.
> - *Latency*: measured in real time, hourly, in the 2026 season (half-hourly IMERG, hourly GSMaP).

## Contents

1. [What "usable" means](#1-what-usable-means)
2. [Where we stand](#2-where-we-stand)
3. [Expert framing](#3-expert-framing)
4. [System design](#4-system-design)
5. [Uncertainty](#5-uncertainty)
6. [Verification](#6-verification)
7. [Expert review, operation and governance](#7-expert-review-operation-and-governance)
8. [Operations strategy: cadence, readiness, timeliness, indicators](#8-operations-strategy-cadence-readiness-timeliness-indicators)
   (8.7: scenarios, risks and responses)
9. [Work plan F0–F9](#9-work-plan-f0f9)
10. [Data and decisions needed from the owner](#10-data-and-decisions-needed-from-the-owner)
11. [Risks](#11-risks)
12. [References](#12-references)

---

## 1. What "usable" means

**Users and decisions.**
- The provincial and commune steering committees for disaster prevention (Ban chỉ huy PCTT & TKCN) decide whether
  to warn, close roads or evacuate.
- The hydro-meteorological service issues the official warning bulletins and risk levels (Decision 18/2021/QĐ-TTg).
- The system supports these people. It does not replace the official bulletin.

**The forecast.** For every *warning unit* (a commune; slope units inside it for detail) and every lead time (today,
+24 h, +48 h, +72 h):
- the probability that at least one landslide occurs in the unit, with an interval;
- a warning level that maps one-to-one to the risk levels of Article 46 of Decision 18/2021;
- the drivers: how much rain, which slopes, how this compares with past landslide days;
- a confidence statement (high / medium / low), with its reasons.

The 30 m susceptibility map is a supporting layer. It shows where in the unit to look; it is not the forecast.

**Acceptance criteria.** All are fixed before the hindcast (§6) is run, and are not changed after.
*Revised after review on 2026-11-05, before any hindcast was run* (A1–A6: rarity, binary outcomes, baseline
probability, forecast archive); the first version of 2026-11-03 had A1 per commune only, A2 per commune only, A5 as interval coverage of binary outcomes and A6 on the open ENS archive 2024–2025.

| # | Criterion | Target |
|---|---|---|
| A1 | Event detection: share of landslide days (hindcast 2015–2025) whose verification unit (district / warning zone, or a multi-day window) is at the warning level or above | ≥ 0.75, with its 95 % interval and the number of events |
| A2 | False alarms: (a) region-wide false-alarm ratio at the warning level (false alarms / all warnings); (b) warning days per commune and rainy season | (a) ≤ the FAR budget agreed in F0; (b) ≤ 5; both reported against the reporting bias (§11) |
| A3 | Skill over the official rule (Article 46 with the zone proxy, each level mapped to its cross-validated observed hindcast frequency) and over rain alone | Brier skill score > 0, 95 % interval above 0; PR-AUC, CSI / ETS and SEDI reported against the same baselines |
| A4 | Reliability: forecast probability against observed frequency | inside the 90 % consistency band, on bins holding at least 10 events (sparse bins merged); events per bin stated |
| A5 | Honest uncertainty: predicted against observed landslide-days per unit-season (or per probability bin), and the randomized PIT of the binary outcomes | the 80 % interval of the counts holds 75–85 %; randomized PIT not distinguishable from uniform |
| A6 | Lead time: A1 and A3 still hold at +24 h with the forecast rain (ECMWF ENS, TIGGE archive 2015–2025) | yes |
| A7 | Operations: a forecast run after the rain data arrive | ≤ 5 min per province; same inputs give the same output |
| A8 | Expert review: the independent review panel (§7) accepts the method and the map | written acceptance |

If a criterion cannot be met, the report says so. The product is then issued with a narrower scope (for example
the pilot area only, or 0–24 h only); it is not tuned until the criterion passes.

**Rarity and test power (2026-11-05).** The F1 catalogue holds 97 positive commune-days on 61 distinct days in 11
seasons (§9.1), against millions of commune-days: a base rate of order 10⁻⁴ or less. Hence:
- under A2 (b) alone, A1 can pass with a FAR above 0.99 (≤ 5 false alarms × hundreds of communes against ~9 events a
  season); A2 (a) closes this;
- ROC AUC is inflated by the true negatives; PR-AUC, CSI / ETS and SEDI (Ferro & Stephenson 2011), which do not reward
  them, are reported beside it;
- reliability bins above ~0.01 are nearly empty, so A4 could not fail; bins are merged until each holds ≥ 10 events;
- every criterion states the number of events behind it and the power of its test (for 61 independent days, the
  95 % interval of a POD of 0.75 is about ± 0.11).

## 2. Where we stand

| Part | Result so far | Meaning for the system |
|---|---|---|
| Inventories | Das 2024 polygons for Ketsana (2009) and Molave (2020); reliability flags; Sentinel-2 scars | good *where*; few *when* |
| Susceptibility (L3, L3b, L3c) | pooled RF 0.73 AUC on 5 km blocks; transfer 0.66–0.72; settings (C1), 18 more terrain layers (C3) and other labels or negatives (C5) add < 0.01 | usable as a relative layer; must be calibrated and given its uncertainty; geology and faults missing |
| Rain as a spatial predictor (L4) | no gain beyond location (p = 0.23) | rain belongs to the *time* part, not to the map |
| Rain thresholds (L6) | code ready, run paused (CHIRPS download) | central to the system; must be on the operational rain product |
| InSAR (L3b.7, L5) | post-event: no signal on the scars; pre-event L5 running | optional modifier, not a core input |

The weak point is not the map. It is the time dimension: few dated landslides, rain products not yet chosen and
checked, no verification of forecasts yet. The plan therefore puts the trigger model and the verification first.

## 3. Expert framing

**Terms** (Fell et al. 2008): *susceptibility* = where; *hazard* = where and when, with a probability; *risk* adds
exposure and vulnerability. The system forecasts **hazard**: the probability of landslide occurrence in a unit and a
time window. It does not forecast runout, size, damage or the failure of a single slope.

**Official framework.** Decision 18/2021/QĐ-TTg, Article 46: the risk level for flash floods and landslides
(levels 1–3) is set from:
- the forecast rain over 24 h (100–200, 200–400, > 400 mm);
- the rain of the days before (1–2 days, more than 2 days);
- the hazard zone of the area (low, medium, high, very high), from the 1:50,000 zoning maps;
- the region (khu vực 1–4; Quảng Nam, Kon Tum and Thừa Thiên Huế are in region 3, Phụ lục XII).

The system works inside this framework:
- its susceptibility classes are calibrated so that they can stand in for the hazard zones where the 1:50,000 map
  does not exist, and compared with it where it does;
- its rain inputs are the same quantities (24 h forecast, antecedent rain);
- its probability then says *how likely* a landslide is within the level. That is what Article 46 lacks: a level
  without a probability, and without uncertainty.

The rule of Article 46 itself, applied with our zones, is the **baseline** every model must beat (A3).

**Regional early warning practice** (Piciullo et al. 2018; Guzzetti et al. 2020): the systems that work operate on
warning units, not pixels; combine a rain trigger model with a static susceptibility; verify every season against
an inventory; and keep a forecaster in the loop. The Norwegian service (Krøgli et al. 2018) is the model of a mature
operation: hydro-meteorological thresholds, daily expert assessment, published verification. NASA LHASA 2
(Stanley et al. 2021; its first version, Kirschbaum & Stanley 2018, combined a susceptibility map and a rain
percentile in a decision matrix) shows the machine-learning route on global data, with probabilistic outputs.

**What the system does not claim.** It does not predict which slope fails. A probability per commune-day is the
honest resolution of the data: dated reports are located to a few km, the observed rain products are 5–11 km, and the
ECMWF ENS forecast is 0.25° (~28 km).

## 4. System design

The system has four components, chained in this order:

| Component | Kind | Inputs | Output |
|---|---|---|---|
| **S** Susceptibility | static, updated yearly | terrain, forest, geology, landslide inventory | 30 m ensemble → susceptibility density per unit, with an interval |
| **R** Rain | dynamic, daily (hourly in storms) | observed (GSMaP / IMERG), forecast (ECMWF ENS, 51 members) | bias-corrected rain fields, as an ensemble |
| **T** Trigger model | dynamic | S and R | P(landslide in the unit on the day \| rain, susceptibility) |
| **H** Output | dynamic | T | per unit and lead time: probability + interval, Article 46 level, drivers, confidence |

After H: forecaster review → bulletin, map, log (used for verification).

**S — Susceptibility (static).**
- The L3c champion, completed with geology and faults (C4) and the C5 labels, refitted on every event.
- An ensemble (§5): negative draws × bootstrap of the polygons by block × two model families (random forest,
  logistic). Each member is calibrated.
- Aggregated per warning unit to a *susceptibility density*: the expected share of slope cells that would fail in
  a storm of the calibration events, with its interval.
- Classes low / medium / high / very high on fixed quantiles of the calibration events, to stand in for the hazard
  zones of Article 46.

**R — Rain.**
- Observed: one operational product (GSMaP NRT or IMERG Early, chosen in F2 against gauges); CHIRPS for the
  climatology.
- Forecast: ECMWF open data, the 51-member ensemble at 0.25° (open since February 2024), 15 days; quantile mapping
  to the observed product per pixel and lead time.
- The quantities: 24 h total, 72 h total, antecedent rain A3 / A7 / A30 as climatological percentiles, rain event E
  and duration D (L6).
- Observed rain also has an error. It is carried as an ensemble too: the product's error against gauges (F2) gives
  perturbed fields. *Not counted twice (2026-11-05):* a T fitted on the noisy satellite rain already absorbs that
  error in its coefficients (with attenuated slopes); the fields are perturbed only if T is fitted on a reference rain
  field (gauges or a gauge-merged product), otherwise the error enters as an errors-in-variables term in the fit of T.

**T — Trigger model.** The probability of at least one landslide in a unit on a day, given the rain and the unit's
susceptibility. Three candidates of rising complexity, all fitted on the same unit-days and verified the same way:
1. **Article 46 rule** with our zones (baseline, no fit).
2. **Bayesian threshold model**: logistic in log E, log D, A7 percentile and the unit's susceptibility density,
   with regional terms (north / centre) and weakly informative priors (the literature E–D curves). Its posterior
   gives the threshold uncertainty directly.
3. **Gradient boosting on unit-days** (LHASA 2 style) with monotonic constraints (more rain, more susceptibility,
   never less hazard).

The simplest candidate that meets A1–A6 is kept: an expert can read a threshold model and check it against the
literature; a boosted model must earn its place by a clear verification gain.

**Relation to L6, L7 and L9 of the susceptibility study (2026-11-05).** F5 and F8 supersede L7 and L9 of
[`landslide-susceptibility.md`](landslide-susceptibility.md). L7 rejects multiplying the susceptibility and rain
probabilities because the two models are calibrated on different populations; T avoids that issue by fitting both
terms jointly, in one model, on the same unit-days (candidates 2 and 3). The L9 choices (IFS deterministic to 10 days;
InSAR every 12 days raising the class) are replaced by the ENS members of R and by the InSAR rule of §8.3. The L6
thresholds (E–D at 5 % non-exceedance, A7 at maximum TSS) enter F5 as a baseline and as a feature; the two
calibrations are reconciled in F5.

**Labels for T.** A unit-day is positive when a landslide is known in the unit on that day (± the date accuracy).
Sources: the dated reports (`vietnam.csv`, news, the VIGMR records if obtained), Das 2024 events with their dated
storms, the Sentinel-2 scars dated by `scars.py` (season, then the storm by Sentinel-1). Each source keeps its own
accuracy flags; the reporting bias is modelled, not ignored (§11).

**H — Output.**
- Probability per unit and lead time: the mean over the Monte Carlo draws (a coherent probability), and the 10–90 %
  interval as the spread (2026-11-05: the mean, not the median).
- Level: the Article 46 level computed from the same inputs, and the system's level from the probability, with the
  thresholds of probability set by the verification (the hit and false-alarm budget chosen with the users in F0). The
  thresholds are chosen inside each leave-one-season-out fold, so that the season scored never sets its own
  thresholds (2026-11-05).
  When the two differ, the bulletin shows both and why.
- Drivers: rain of the last 24 / 72 h and forecast, its return period, the susceptibility class, the past landslide
  days most like today (analogues).
- Confidence: high / medium / low, from the width of the interval and the data state (missing rain, ensemble spread,
  unit outside the calibration area).

## 5. Uncertainty

Every source is named, quantified and carried to the forecast. None is left out because it is hard.

| Source | Kind | How it is quantified | How it reaches the forecast |
|---|---|---|---|
| Inventory: which slopes failed, mapping extent | epistemic | footprint variants (main / shrunk), reliable vs all polygons, negatives off unmapped scars | S ensemble members |
| Inventory: dates of the reports | aleatory | the date accuracy of each record; ± 1 day windows | T labels as intervals; sensitivity run |
| Reporting bias (roads, villages, deaths) | epistemic | exposure covariate (roads, population) in T; rate checked against the Sentinel-2 seasons | A2 stated as an upper bound; bias term reported |
| Predictors (DEM, forest, geology) | epistemic | GLO-30 vs AW3D30; geology map vs GLiM | S ensemble members (DEM variant) |
| Susceptibility model: sampling, parameters | aleatory + epistemic | negative draws, block bootstrap of the polygons, two model families | S ensemble (≥ 50 members) |
| Model transfer in space and time | epistemic | Ketsana ↔ Molave transfer, leave-one-season-out in T | widened intervals outside the calibration area; confidence "low" |
| Observed rain | aleatory | product vs gauges (F2): error model per intensity class | perturbed rain members only if T is fitted on a reference rain field; otherwise errors-in-variables in T (not counted twice, §4) |
| Forecast rain | aleatory | ECMWF ENS, 51 members, after quantile mapping | rain members per lead time |
| Trigger thresholds / coefficients | epistemic | Bayesian posterior (candidate 2) or bootstrap (candidate 3) | T posterior draws |

**Propagation.** Monte Carlo: for each unit and lead time, draw a susceptibility member, a rain member and a set of
trigger coefficients; compute the probability; repeat (about 1,000 draws). The result is a distribution of the
probability. The bulletin gives its mean (the coherent probability) and its 10–90 % interval as the spread. The cost
is small: a few hundred units × 1,000 draws per run.

**Calibration of the uncertainty itself.** An interval is useful only if it is right as often as it says. A single
outcome is 0 or 1, so the coverage of a probability interval by it, or a plain PIT, means nothing (2026-11-05). A5
checks instead, on the hindcast: (a) the counts: predicted against observed landslide-days per unit-season, or per
probability bin, with the 80 % interval of the predicted count; (b) the randomized PIT of the binary outcomes; and A4
checks the reliability of the mean probability. If the intervals are too narrow, a variance inflation factor is
fitted on the hindcast and stated in the model card.

**Communication.**
- Never a bare number: "probability 0.18 (0.09–0.31), level 2, confidence medium: heavy rain forecast with a wide
  spread between members".
- Words and numbers together, using one fixed vocabulary, so the same number always gets the same word. The
  vocabulary is tied to the warning levels and their probability thresholds (one phrase per level, set in F0 with
  the users), not to the IPCC likelihood scale: on that scale 0.1–0.3 is "unlikely", which is wrong for a warning
  whose base rate is of order 10⁻⁴ (2026-11-05).

## 6. Verification

**Hindcast design.**
- Seasons 2015–2025 (the period of the landslide report catalogue, F1; the rain products, IMERG V07 and GSMaP, go
  back to 2000), rainy seasons of the centre (September–December), and the north as a transfer check only.
- Strictly out of sample: leave-one-season-out for T, with the probability thresholds of the levels chosen inside
  each fold (2026-11-05); S refitted without the events of the season scored when they are in its training data.
- Final test (2026-11-05): one full season and one province (ideally with Sentinel-2 dated scars) held out of all
  fitting and threshold choice, scored once before F9.
- Two modes: with *observed* rain (the best case: "nowcast") and with archived ECMWF ENS forecasts (A6): the TIGGE
  archive (ECMWF ENS since 2006, research use) for 2015–2025; the open-data archive (0.25° since February 2024) only
  for the operational check. Quantile mapping of the ENS is pooled by region and intensity class, not fitted per
  pixel and lead time on two seasons (too thin for the extremes).

**Units of verification.**
- Unit-day (scored at district / warning-zone scale or on multi-day windows; the commune for display): Brier score,
  Brier skill score against climatology, rain only and the Article 46 rule (its levels mapped to their
  cross-validated observed frequencies); ROC AUC; PR-AUC, CSI / ETS and SEDI (rare events); TSS, POD and
  false-alarm ratio at each warning level; reliability diagram.
- Event-based: for each known landslide day, was the unit warned, and how many days ahead (the reports are dated to
  the day, ± 1, so lead time is counted in days, not hours)?
- Season-based: number of warnings per commune and season — the "warning budget" the users can live with.

**Baselines.** Climatology (seasonal frequency per unit), rain only (no susceptibility), the Article 46 rule with our
zones, and the 1:50,000 zones of VIGMR where available. A model that does not beat Article 46 on A3 is not
deployed.

**Report.** One verification report per season with the same tables and figures, the A1–A6 table, and the cases
the system missed, each examined by hand (rain product failure, unreported event, wrong zone).

## 7. Expert review, operation and governance

**Documents that make the system auditable.**
- *Model card* per version: purpose, training data and its biases, scores of §6, known failure modes, the variance
  inflation factor, the code version and the data hashes.
- *Data sheet* per input: source, licence, latency, error against gauges or the reference, fallback.
- *Standard operating procedure*: daily schedule, what the forecaster checks, when and how to override, how a
  bulletin is issued, what to do when an input is missing.
- *Decision records* (ADRs) for every choice that changes the forecast.

**Forecaster in the loop.**
- The daily run proposes a level for every unit; the forecaster confirms or changes it.
- An override needs a reason from a fixed list (local report, field observation, rain product failure, other) and is
  logged.
- The overrides are verified like the model, so the system learns where expert knowledge adds skill.

**Independent review panel** (A8): an engineering geologist familiar with central Vietnam, a hydro-meteorological
forecaster, a statistician, and a user from a provincial steering committee. They review the method (F0), the
susceptibility map in the field on a sample of units (F3), and the verification report before operation (F8).

**Field check of the map.** A stratified sample of units (by class and by model agreement) is visited or checked on
very-high-resolution images by a geologist; the share of "very high" units the geologist agrees with is reported.

**Operation.**
- Champion / challenger: a new model version runs in shadow beside the running one for a full season and replaces it
  only if it is better on §6.
- Monitoring: input latency and gaps, the share of units at each level against the climatology, drift of the
  predictors.
- Fallbacks: when the observed rain product is missing, the previous product or the forecast's first day, with the
  confidence lowered to "low"; never silent.
- Reproducibility (A7): every run writes a manifest (inputs, hashes, model version, code version); a rerun gives the
  same output.

## 8. Operations strategy: cadence, readiness, timeliness, indicators

A forecast system fails more often from stale or late data than from a weak model. This section fixes, for every
input and every product, *when* it is updated or reprocessed, *how ready* it is, *how fast* the system must react,
and the *indicators* that measure each of these. The targets are frozen in F0 with A1–A8, measured from the run
logs (every run writes a manifest, §7), and reported every week in the season and in the season report.

### 8.1 The operating year and the operating modes

Central Vietnam has its main rainy season from September to December. The year is organised around it:

| Months | Phase | Work |
|---|---|---|
| January – February | post-season | season verification report (§6); reports of the season into the catalogue; first Sentinel-2 scar mapping when clear composites allow |
| March – June | maintenance | refit S and T on the new catalogue (challengers); yearly layers (forest, NDVI composite, roads snapshot); InSAR stack rebuilt on the new window; rain bias correction refitted |
| July – August | readiness | readiness review (§8.6); dry run on the last season; champion frozen by 15 August; SOP rehearsal (replay of a past storm, e.g. October 2020) |
| September – December | operation | routine and storm modes below |

**Modes in the season.**

| Mode | When it starts | Runs | Bulletins |
|---|---|---|---|
| **Routine** | the season | twice a day, on the 00 and 12 UTC ECMWF ensemble and the latest observed rain | 2 per day, at fixed local times set in F0 |
| **Storm** | any one of: ensemble probability of > 100 mm / 24 h ≥ 30 % in a unit; an official heavy-rain or typhoon warning for the area; Article 46 level ≥ 1 in the forecast | every 3 h on the hourly observed rain (GSMaP NRT; GSMaP_NOW as an uncertain nowcast) | every 6 h, and at once on a level change (Decision 18, Art. 16: a landslide warning is issued as soon as the possibility is detected) |
| **Post-event** | a day at level ≥ 2, or a reported landslide | normal runs continue | within 7 days: reports collected; Sentinel-1 change map from the first acquisition after the storm (≤ 12 days; 6 if confirmed, §8.3); Sentinel-2 scars when cloud-free; the InSAR decision of §8.3; the event added to verification |

The thresholds that switch the modes are themselves checked each season (how often storm mode was on, and whether
the landslide days fell inside it).

### 8.2 Update and reprocessing policy, layer by layer

Every layer has a normal cadence, the events that force an earlier update, and a **maximum age**. A layer older than
its maximum age is *stale*: the run still goes on, the confidence is lowered and the staleness is shown in the
bulletin.

| Layer | Normal cadence | Forced update when | Maximum age |
|---|---|---|---|
| Observed rain (operational product) | hourly | — | 6 h for a run (else the fallback, confidence "low") |
| Forecast rain (ECMWF ENS) | 00 and 12 UTC runs | — | 18 h |
| Rain bias correction and error model | refitted before each season; checked monthly against the gauges | monthly bias outside ± 20 % or correlation lower than the fitted value by 0.1 | 12 months |
| Rain climatology (CHIRPS, percentiles) | one year appended each January | a new CHIRPS version | 15 months |
| DEM and terrain layers | static | a new DEM release; a storm that changes the terrain (scars larger than 1 ha: local update of those cells) | — |
| Forest / land cover | yearly (dry-season Sentinel-2 composite; Hansen when released) | large clearing seen in the post-event mapping | 18 months |
| Roads (for the reporting-bias term) | yearly snapshot, dated, before the season | — | 12 months |
| Geology, faults | on a new map | — | — |
| Warning units (communes) | on an official boundary change | — | — |
| Event catalogue | reports daily in the season; Sentinel-2 mapping after the season and after major storms | a level-≥ 2 storm | one season |
| Susceptibility model S | refitted yearly after the catalogue update (challenger, §7) | new positives > 20 % of the training set (a major event) | 2 seasons |
| Trigger model T | refitted yearly after the season | A1 or A3 fails on the running season | 2 seasons |
| InSAR activity | each Sentinel-1 acquisition (§8.3) | §8.3 | 24 days (2 repeats at 12 days) |

A refitted model never replaces the running one in the season. It waits for the readiness review, unless the running
model fails a gate (then the previous champion is restored, not an untested one).

### 8.3 InSAR: when to update, when to process again

**Role.** InSAR shows slopes that are already moving. It enters the forecast as a modifier only if L5 (H3) shows that
it adds skill; until then it is a layer the forecaster sees, not an input of T. The strategy below holds in both
cases. *Frozen (2026-11-05):* this design is not built further until L5 shows skill (coverage < 15 % of the slope
cells; C-band coherence ~0.1 at 36 days under forest).

**Acquisitions.** Sentinel-1C and 1D fly since 24 June 2026 (Sentinel-1A ended on 29–30 June 2026). A 6-day repeat
over Vietnam is not sourced: even with 1A + 1B the area had 12 days. The plan assumes **12 days** unless the
Sentinel-1C/1D observation scenario confirms 6 days for this area (2026-11-05). Track 120 descending first, track
55 ascending second.

**Three levels of processing** (the GeoEyes `ps` engine and its incremental update, `[ps_update]`):

| Level | What | When | Cost |
|---|---|---|---|
| **1 Incremental** | the new acquisition appended to the existing points (`ps_update`) | every acquisition (12 days; 6 if confirmed) | minutes |
| **2 Full engine run** | all engine steps again on the current stack (selection, DEM error, APS re-estimated) | every 4 appended dates (`full_every = 4`, ~48 days at 12 days), or when a QC indicator below fails | hours |
| **3 Stack rebuilt** | a new stack: new window, new reference date, phase linking again | yearly in March–June on a rolling 2-year window; after a decorrelating event; after a change of sensor, orbit or processing parameters | ~1 day per track |

**Triggers of a level-2 run** (any one, measured at each incremental update on stable points and slope units):
- the median temporal coherence over the slope units falls by more than 0.05 from the last full run;
- the RMS of the difference between the incremental and the last full velocity on stable points exceeds 2 mm/yr;
- the number of points falls by more than 20 %;
- the median neighbour residual of the velocity rises above 3 mm/yr (1.9 mm/yr on the L5b run);
- the reference area moves (its velocity against GNSS or its neighbours exceeds 2 mm/yr).

**Triggers of a level-3 rebuild after an event:** more than 30 % of the slope units lose coherence in the pair across
the storm, or the post-event mapping finds scars in more than 5 % of the units. The time series is then cut: a new
segment starts after the event, and the activity before and after is compared (L5b), never fitted as one series.

**Readiness of InSAR for the forecast:** an activity layer is "current" when its last acquisition is at most 24 days
old and it covers at least 10 % of the slope cells of a unit (the L5 coverage gate); otherwise the unit shows "no
InSAR information", which is not the same as "stable".

### 8.4 Data readiness

**Six dimensions, the same for every input.**

| Dimension | Question | Indicator |
|---|---|---|
| Availability | does it exist for our area and period? | yes / partial / no |
| Latency | how long after the observation does it arrive? | p50 and p95 of the delay, measured |
| Completeness | does every expected file arrive before the run's cut-off? | on-time share in the season |
| Continuity | are there gaps (days, members, bursts)? | gap days per season |
| Quality | how close is it to the reference? | bias and correlation against gauges / GNSS / field |
| Fallback | what replaces it when missing? | named product, and how often it was used |

**Current assessment (2026-11-03).** The nominal latencies are from the providers; F2 measures the real ones on our
connection for a full season before any target is signed.

| Input | Availability | Nominal latency | Status | What is missing |
|---|---|---|---|---|
| GSMaP NRT (hourly, 0.1°) | yes | 4 h | partial | check against gauges in the mountains (F2) |
| GSMaP_NOW (Himawari area) | yes | ~0 h | partial | lower accuracy than NRT: nowcast only, with wider intervals |
| IMERG Early / Late / Final | yes | 4 h / ~14 h / ~3.5 months nominal (in practice longer: Final for October–December 2025 was not yet published on 2026-11-04, §9.1) | partial | same check; Final only for the archive |
| CHIRPS (daily, 0.05°) | yes, from 1981 | weeks (final) | ready | climatology only |
| ECMWF ENS open data (0.25°, 51 members) | from February 2024 at 0.25° | release times to be measured | partial | the open archive is short (2024–2025: 34 positive commune-days, too few for A6); A6 is tested on the TIGGE archive of ECMWF ENS (since 2006, research use) for 2015–2025 (2026-11-05) |
| Rain gauges (KTTV) | research mirror only (imech.info, 2026-11-05): 220 stations in the core box | unknown | for calibration, not operation | official source (owner, §10) |
| Sentinel-1 (bursts, ASF) | yes, 12-day repeat (6 if the S1C/S1D scenario confirms it, §8.3) | to be measured (hours to a day) | ready | — |
| Sentinel-2 | yes | ~1 day | partial | cloud in the rainy season: post-season mapping only |
| Dated landslide reports | sparse | days | partial | VIGMR / provincial records (§10) |
| 1:50,000 zoning (VIGMR) | not obtained | — | missing | owner (§10) |
| Geology, faults | GLiM only | — | partial | owner (§10) |
| Commune boundaries after 2025 | to be collected | — | partial | official source |

**Readiness rule.** An input enters operation only when it is "ready": availability yes, latency p95 within its
budget (§8.5), on-time share ≥ 98 % over the last 30 days of the dry run, quality stated, fallback named and tested.

### 8.5 Timeliness: is the system fast enough?

**The time budget of one forecast** (routine mode; storm mode in brackets). T0 is the end of the rain hour being
observed.

| Stage | Budget |
|---|---|
| observed rain available | T0 + 4 h (product latency) |
| download and checks | ≤ 10 min |
| forecast run (all units, Monte Carlo, maps) | ≤ 5 min per province (A7) |
| forecaster review | ≤ 30 min (≤ 15 min) |
| bulletin published | ≤ T0 + 5 h (≤ T0 + 4.5 h) |

**Reaction to a storm.**
- Storm mode switches on within 1 h of its trigger (§8.1).
- A level change is published within 30 min of the run that finds it.

**Warning lead time**, measured on every known landslide (hindcast, then the shadow season):
- the number of days from the first bulletin at the warning level to the landslide day. The reports are dated to
  the day (± 1), so lead time is counted in whole days, not hours (2026-11-05);
- target: at least 50 % of the landslide days warned ≥ 1 day ahead, i.e. in a bulletin of the day before or earlier
  (with the forecast rain, A6).

A warning that arrives after the landslide counts as a miss in A1 for that lead time.

### 8.6 Indicators: how each part is measured

The indicators are computed automatically from the run manifests and the logs. Each one has a target (green), an
alert level (amber: the next weekly review discusses it), and a failure level (red: act now, record in the log).

| Group | Indicator | Target | Amber | Red |
|---|---|---|---|---|
| Data readiness | on-time share of each critical input (rain obs, ENS) | ≥ 98 % | < 98 % | < 95 % |
| | latency p95 of each critical input | within budget | budget + 1 h | budget + 3 h |
| | spatial completeness (units with valid rain) | 100 % | < 100 % | < 95 % |
| | fallback rate (runs on a fallback input) | ≤ 2 % | > 2 % | > 10 % |
| | stale layers (older than their maximum age, §8.2) | 0 | 1 non-critical | any critical |
| | rain bias against gauges (monthly) | within ± 20 % | ± 20–35 % | beyond ± 35 % |
| Timeliness | bulletins published on time | ≥ 99 % | < 99 % | < 95 % |
| | observation-to-bulletin delay p95 | ≤ 5 h | ≤ 6 h | > 6 h |
| | run time per province | ≤ 5 min | ≤ 15 min | > 15 min |
| | storm-mode switch delay | ≤ 1 h | ≤ 2 h | > 2 h |
| | warning lead time (share of known landslide days warned ≥ 1 day ahead) | ≥ 50 % | 30–50 % | < 30 % |
| Service reliability | successful scheduled runs | ≥ 99.5 % | < 99.5 % | < 98 % |
| | silent failures (a run that failed without an alert) | 0 | — | ≥ 1 |
| | time to restore after a failure | ≤ 2 h | ≤ 6 h | > 6 h |
| | weekly reproducibility rerun (same output hash) | identical | — | different |
| Forecast quality | A1–A5 on the season so far (rolling) | as A1–A5 | one criterion below | two below |
| | share of unit-days at each level against the climatology | within ± 50 % | ± 50–100 % | beyond |
| InSAR | delay from acquisition to updated activity layer | ≤ 2 days | ≤ 4 days | > 6 days |
| | slope units with InSAR information | stated per season | − 10 % | − 25 % |
| | QC triggers of §8.3 | none | one | two or more |
| Human loop | overrides with a reason | 100 % | — | < 100 % |
| | overrides that improved the forecast (verified) | reported | — | — |

**Reviews.**
- Daily in the season: the run log and any red indicator.
- Weekly in the season: all indicators on one page (the `Hazard` page of the web app gets an operations tab).
- After the season: the season report — verification (§6) and these indicators, with the actions for the next
  season.
- **Readiness review, August (go / no-go):** every critical input "ready" (§8.4) over the last 30 days; the dry run
  on the last season meets A1–A6; the model card and the SOP signed; the storm replay rehearsed. A "no-go" item is
  either fixed or the season runs with a stated, narrower scope.

### 8.7 Scenarios, risks and responses

The worst day for the system is the day it matters most: a typhoon cuts the power and the internet, the rain product
is late or wrong, the forecaster is in the field, and the hazard is at its highest. The design must still deliver a
usable product on that day. This section gives the method (a risk register), the principle (a degradation ladder),
the responses (playbooks) and the proof (drills).

**Lessons already learnt in this project** (each one is an entry below):
- the disk filled during a run when a project was moved to the trash by copying (2026-11-03);
- a password was printed in a log and had to be changed;
- the ASF burst service was unavailable for days (L3b.7);
- the CHIRPS server refused parallel downloads (L6).

#### Risk register

Each risk is scored for likelihood L and impact I (1–5; impact 5 = a missed warning on a day with casualties). The
score is L × I. Each entry names how the risk is *detected* (an indicator of §8.6 where possible), how it is
*prevented*, and the *response* (a playbook below). The register is reviewed at the readiness review and after every
incident. The initial scores are the owner's to confirm in F0.

| # | Risk | L | I | Score | Detection | Prevention | Response |
|---|---|---|---|---|---|---|---|
| R1 | Power or internet lost at the operating site during a storm | 4 | 5 | 20 | heartbeat from the backup site | the operational chain runs on a cloud instance, with a second instance in another region; the workstation is not the operational site | P1 |
| R2 | Satellite rain far below the real rain in an orographic extreme (a silent failure: no error, a wrong low level) | 4 | 5 | 20 | gauge reports above the product; the forecast rain of the last 24 h far above the observed | gauge check (F2); the level never lower than the one from the forecast rain of the previous run; storm mode on official warnings, whatever our rain says | P2 |
| R3 | Rain beyond the training range (a record storm, e.g. October 2020) | 3 | 5 | 15 | inputs outside the range of the hindcast | monotonic models; the probability capped at the highest calibrated class with the label "beyond experience" | P3 |
| R4 | Too many false alarms: users stop listening | 4 | 4 | 16 | warnings per commune and season against the budget (A2) | the budget agreed in F0; the levels set by verification; the confidence statement | P4 |
| R5 | A landslide with casualties in a unit that was not warned | 3 | 5 | 15 | reports, media | A1; the forecaster override; Article 46 shown beside our level | P5 |
| R6 | Observed rain late or missing | 4 | 3 | 12 | on-time share, latency p95 | two products (GSMaP and IMERG): independent for provider outages, not for errors (they share the PMW sensors and the GEO IR) | ladder level 1 |
| R7 | Forecast rain (ENS) late or missing | 3 | 3 | 9 | on-time share | GFS ensemble as the second source | ladder level 2 |
| R8 | The forecasts miss the track of a typhoon | 3 | 4 | 12 | ensemble spread; official track bulletins | probabilities from the ensemble, not the mean; storm mode on official warnings | P2 |
| R9 | Disk full, process crash, corrupted output | 3 | 4 | 12 | preflight free-space check before every run; output checksums | separate data and operational volumes; free space ≥ 3 × the largest run; the trash never copies (fixed 2026-11-03) | P6 |
| R10 | A software release breaks the chain | 3 | 4 | 12 | the weekly reproducibility rerun; tests in CI | no release in the season except fixes; the previous version kept ready to restore | P6 |
| R11 | A provider changes format, version, access or credentials (token expired, Earthdata login) | 3 | 3 | 9 | download errors; provider notices checked at the readiness review | data sheets with a second source; credentials in a vault, renewed before the season; never printed in logs | P6 |
| R12 | Credentials or the server compromised | 2 | 4 | 8 | access logs | secrets outside the code and the logs; least privilege; renewed every season | P6 |
| R13 | Time errors (UTC vs local day, daylight boundaries of 24 h totals) | 3 | 4 | 12 | unit tests on the day boundary; replay tests | one time convention (UTC inside, ICT in the bulletin), tested | P6 |
| R14 | No forecaster available (night, field, illness) | 3 | 4 | 12 | the review not done before the deadline | roster with a deputy; the bulletin goes out automatically with "not reviewed" after the deadline + 30 min | P1 |
| R15 | The bulletin does not reach the communes | 3 | 5 | 15 | delivery receipts | two channels (the official channel of the province and SMS / Zalo list), receipts logged | P1 |
| R16 | Users read the probability wrong (0.2 read as "safe") | 3 | 4 | 12 | user feedback, exercises | the level leads, the probability supports it; fixed words for numbers; training before the season | P4 |
| R17 | Our level contradicts the official bulletin | 4 | 3 | 12 | automatic comparison in every run | the two are always shown together, with the reason of the difference; the official level stays the legal reference | P4 |
| R18 | Susceptibility out of date after a major event (new scars, new roads) | 3 | 3 | 9 | post-event mapping (§8.1) | the forced updates of §8.2 | layer update |
| R19 | Model drift (land use, climate) | 2 | 3 | 6 | rolling A1–A5; level frequencies against the climatology | yearly refit, champion / challenger | refit |
| R20 | Responsibility: a decision taken on our product goes wrong | 2 | 5 | 10 | — | the product is advisory; the terms of use and the limits are written in the bulletin and in the model card; agreed in F0 | — |

#### Degradation ladder

The system never stops; it steps down and says so. Each step is tested in the drills.

| Level | Condition | What is issued | Confidence |
|---|---|---|---|
| 0 Full | all inputs ready | the full product of §4 | as computed |
| 1 No observed rain | the observed product late or missing | the antecedent rain from the forecast's first day and the last observed; the interval widened | at most "medium" |
| 2 No ENS | the ECMWF ensemble missing | GFS ensemble; if that fails too, the official deterministic rain forecast of the service | at most "medium" / "low" |
| 3 No computing | the operational site and its backup down | the **precomputed lookup table**: for every unit, the level for each bin of 24 h rain and antecedent rain, printed in the SOP and stored offline; the forecaster applies it to the official rain forecast by hand | "low" |
| 4 Nothing of ours | no table, no data | the official Article 46 level only | — |

The lookup table of level 3 is recomputed with every model version and is part of the release; it is what makes the
system usable during a power cut.

#### Playbooks

Each playbook is one page in the SOP, with the first actions, the people to call, and the checks.

| # | Situation | First 30 minutes | Then | Back to normal |
|---|---|---|---|---|
| P1 | Operating site, forecaster or delivery fails during a storm | switch to the backup instance (automatic) or to the lookup table (level 3); call the deputy forecaster; send by the second channel | bulletins every 6 h on the available level; log every step | the primary restored and checked by a rerun; incident review within 7 days |
| P2 | The rain is probably wrong (gauges, reports or the forecast say much more) | raise the level to the one given by the higher source; mark "rain product doubtful" | compare with the gauges and the radar of the service if available; keep the higher level until two products agree | the case added to the gauge check; the error model refitted after the season |
| P3 | Rain beyond experience | issue the highest level with "beyond the range of past events"; tell the users that the probability is a lower bound | storm mode; post-event mapping first | the event added to training after the season |
| P4 | Warning fatigue, or our level contradicts the official one | show both levels and the reason; the forecaster decides and records why | review the warning budget with the users after the storm | levels re-set by verification at the end of the season |
| P5 | Unwarned landslide with casualties | collect the facts (time, place, rain, our bulletins) within 24 h | the case review: data, model, communication | the actions in the register; published in the season report |
| P6 | Technical failure (disk, release, provider, credentials, time) | restore the previous version or input; run the preflight checks; rerun | find the root cause; fix with a test that reproduces it | the reproducibility rerun passes; the register updated |

#### Drills and incident reviews

- **Before every season (August):** a tabletop replay of a past storm (October 2020 for the centre) with the users;
  a failover drill (stop the primary instance, run on the backup, then on the lookup table); a check of every
  credential and every provider notice.
- **In the season:** one unannounced failover test in a calm week.
- **After every incident:** a blameless review within 7 days — what happened, why, what changes — written in the
  register; the same failure must not happen twice.
- **Indicators** (added to §8.6): drills done before the season (all); incidents reviewed within 7 days (100 %);
  repeated incidents (0).

## 9. Work plan F0–F9

Each step ends with a short report and the owner's review. The InSAR steps (L5, L5b) continue in the background as an
optional module; they do not block the system.

| Step | Content | Builds on | Output | Gate |
|---|---|---|---|---|
| **F0** Requirements | users, warning units (communes after the 2025 reorganisation), lead times, the warning budget, A1–A8 frozen with the operations targets of §8 (bulletin times, latency budgets, indicator levels); the risk register of §8.7 scored; terms of use; contact with the review panel | §1, §3, §8 | `f0_requirements.md`, `risk_register.md` | owner signs A1–A8, §8 targets and the register |
| **F1** Event catalogue | every dated landslide in one schema with location and date accuracy (O2): `vietnam.csv`, Das events, Sentinel-2 scars dated per storm, VIGMR records if obtained; unit-day labels | L0, L3b, O2 | `catalogue.parquet`, audit report | enough positive unit-days for T (target ≥ 150 in the centre) |
| **F2** Rain | archive 2015–2025 of GSMaP NRT and IMERG Early over central Vietnam; check against gauges (KTTV stations if obtained, else the GHCN-D / GSOD stations, which are not independent of the products, §9.1); choose the operational product; error model; ECMWF ENS archive (TIGGE) and quantile mapping pooled by region and intensity; latency and on-time share of each product measured on our connection (§8.4) | L6 code, O3 | `rain/` archive, `f2_rain_check.md`, data sheets | product chosen, error model stated, readiness table filled with measured values |
| **F3** Susceptibility final | C4 (geology, faults, rivers, roads before the event), C5 (labels), C6 (champion); the ensemble; calibration to density; classes; comparison with the 1:50,000 zones; field check sample | L3c | model card v1, `susceptibility_<year>.tif` + interval | panel review of the map |
| **F4** Static store | every cell of the provinces (O1), unit aggregation (commune and slope units) | O1 | `base/static/`, `units.gpkg` | full coverage, run time |
| **F5** Trigger model | L6 thresholds on the F2 product; candidates 1–3 of §4 on unit-days; leave-one-season-out | L6, F1, F2, F3 | `trigger/` fits, `f5_report.md` | A1, A3 on observed rain |
| **F6** Uncertainty | the Monte Carlo chain of §5; coverage check; variance inflation | F3, F5 | `uncertainty.md`, calibrated chain | A4, A5 |
| **F7** Hindcast and verification | 2015–2025 with observed rain and with forecasts; all baselines; missed-case analysis | F5, F6 | `verification_2015_2025.md` | A1–A6 |
| **F8** Operational chain | `geoeyes landslide forecast`: daily run, bulletin per unit, map, run log; modes and layer policy of §8.1–8.3; the indicators of §8.6 and their operations tab; the cloud instance and its backup, the degradation ladder and the lookup table, the playbooks of §8.7; the web app's `Hazard` page; SOP, model card, data sheets | L9 | the service, documents | A7, panel review (A8), first readiness review with a failover drill |
| **F9** Shadow season | a full rainy season in shadow (September–December 2027), forecasts logged and verified, every §8.6 indicator measured, before any official use | F8 | season verification and operations report | owner decides on use |

**Order and timing.** F0, F1 and F2 first (they decide whether the time model can be built at all); F3 in parallel
with F2; then F5–F7; F8 last. F9 cannot start before September 2027. The 2026 season still in progress (November) can
already serve as a first test of F5 once the rain archive exists.

### 9.1 F0–F2 in detail (started 2026-11-03)

**F0.** For sign-off: [`landslide-forecast/f0-requirements.md`](landslide-forecast/f0-requirements.md) (scope,
A1–A8 approved in principle, revised 2026-11-05 before any hindcast, sign-off pending; operations targets,
infrastructure, data needed) and the living
[`landslide-forecast/risk-register.md`](landslide-forecast/risk-register.md) (scores, prevention status, incident log).

**F1 — Event catalogue.** Starting point: `vietnam.csv` has 72 day-dated slope failures in the centre since 2015, on
54 distinct days (2016–2019: 2–3 per year, an artefact of reporting). Target: ≥ 150 positive unit-days.
1. *News and situation reports*, 2015–2025, harvested per storm and province (three parallel passes: 2015–2018,
   2019–2021, 2022–2025); every record with its source URL and a quote stating the date and place.
2. *Merge* with `vietnam.csv`; the same commune within ± 1 day is one event.
3. *Geocoding* to the commune (pre-2025 boundaries; the record keeps the commune, its centroid and the commune size
   as the location accuracy). Records located only to a district stay in the catalogue for the regional thresholds
   but not in the commune-day labels.
4. *Audit*: a random 20 % of the records re-read against their source; the share confirmed is reported.
5. *Unit-day labels* and the count against the target; the gaps by year and province.
6. *Supplement* (later, if short): Sentinel-2 scars dated to a storm with the Sentinel-1 series; the owner's VIGMR
   and provincial records.

**F1 interim result (2026-11-03, `geoeyes landslide catalogue`; `<study>/catalogue/f1_report.md`).**
- News harvest: 215 records (2015–2018: 29; 2019–2021: 83; 2022–2025: 103), each with its source and a quote; all
  placed (GADM communes; OpenStreetMap for passes and post-2025 communes, with name and type checks after a manual
  check found wrong OSM answers for road names and homonyms).
- Catalogue: 291 records → 258 events; **97 positive commune-days on 61 distinct days** (before: 54 days). Target
  150: **not met**. Gaps: 2015 (none), 2019 (2), and Gia Lai, Ninh Thuận, Phú Yên, Đà Nẵng, Bình Định.
- Storm-scale labels from the polygon inventory: Ketsana 22 communes (8,053 landslides), Molave 20 (11,011). Every
  mapped commune has landslides (the footprints are drawn around them), so these give *densities* (landslides per
  km² mapped) for a dose–response with the storm rain, not presence / absence.
- Consequence for F5: the day-scale trigger model must pool the regions with informative priors (candidate 2); the
  storm densities calibrate the susceptibility × rain response; the VIGMR / provincial records (§10) are the way to
  the target.

**F2 — Rain.**
0. *GSMaP v8* (owner's JAXA account, 2026-11-03): NRT and Gauge-NRT daily at 0.1°, the same cell centres as IMERG.
   On 2020-10-28 over the centre, GSMaP NRT gives 307 mm/day at most against 164 mm/day for IMERG Early: the choice
   of the product moves the warning level, hence the gauge check before any choice (R2).
   *Result, IMERG Early against Final* (2026-11-04, `geoeyes landslide raincheck`; September–December 2015–2025,
   6.5 M pixel-days; Final for October–December 2025 not yet published, although its nominal latency is ~3.5
   months: in practice Final has lagged far behind, to be checked against the GES DISC notices): totals 1.03, correlation 0.93, 99th
   percentile 1.005: the same scale, so thresholds fitted on the archive hold for Early online. Heavy days are
   misplaced: POD 0.72 / FAR 0.29 at ≥ 100 mm, 0.60 / 0.58 at ≥ 200 mm — hence spatial smoothing and the rain error
   members of §5. Final is the same algorithm with a monthly gauge adjustment, not an independent reference: the
   gauges (and GSMaP) decide.
   *Result, the four products* (2026-11-04, `geoeyes landslide rainproducts`; same season and years; all four
   archives complete except Final October–December 2025; `rain_f2/f2_products.md`):

   | against IMERG Final | totals | corr | p99 | POD / FAR ≥ 100 mm | POD / FAR ≥ 200 mm | frequency bias ≥ 200 mm |
   |---|---|---|---|---|---|---|
   | IMERG Early | 1.03 | 0.93 | 1.01 | 0.72 / 0.29 | 0.60 / 0.58 | 1.4 |
   | GSMaP NRT | 0.90 | 0.80 | 1.21 | 0.67 / 0.54 | 0.58 / 0.80 | 2.9 |
   | GSMaP Gauge | 1.00 | 0.82 | 1.29 | 0.72 / 0.56 | 0.63 / 0.81 | 3.3 |

   Core box (Quảng Nam – Kon Tum) gives the same picture. Storm days, core maximum (mm/day): Ketsana 2009-09-29 Early
   412, GSMaP NRT 397, Final 489; Podul 2013-11-15 Early **774**, GSMaP 484, Final 375; Molave 2020-10-28 Early 164,
   GSMaP **307**, Final 169.
   Reading: (a) GSMaP has slightly lower totals but **sharper extremes**: three times as many ≥ 200 mm pixel-days as
   Final; (b) the products disagree by a factor up to two on single storm days, and not always in the same
   direction (Podul: IMERG highest; Molave: GSMaP highest); (c) the two gauge-adjusted products (Final, GSMaP Gauge)
   disagree as much as the raw ones, so "gauge-adjusted" does not mean "right" in these mountains.
   Consequences for the design: (1) thresholds are **product-specific**: a threshold fitted on Final must not be
   applied to GSMaP (and the reverse); each operational product gets its own calibration of T, or a quantile
   mapping onto the reference product; (2) the spread between products is a measured part of the observed-rain
   uncertainty and enters the rain members of §5 (not only the within-product error); (3) no product is chosen yet:
   IMERG Early stays the candidate (same scale as the archive, smaller false alarms), GSMaP NRT the second source
   (R6: independent for provider outages, not for errors, since both use the same PMW sensors — GMI, AMSR2, SSMIS,
   MHS — and GEO IR) and the storm-time hourly feed; the choice waits for the gauge check (step 3), which is now
   the critical path of F2.
1. *IMERG V07 daily archive*, Early (candidate operational) and Final (gauge-adjusted reference), 2015–2025, over
   104.5–110° E × 10.5–20° N (`landslide/satrain.py`, `geoeyes landslide rainarchive`): server-side subsets through
   the cloud OPeNDAP service (~40 kB per day). Days are UTC (07–07 local): converted where used (R13).
2. *GSMaP NRT and Gauge*: **done** (2026-11-04): daily archives 2015–2025, 2009 and 2013, no missing day
   (`gsmap_nrt`, `gsmap_gauge` runs of `rainarchive`).
3. *Quality*: Early against Final first (bias, correlation, extremes per intensity class); then against gauges
   (GHCN-D / GSOD stations, few in the mountains; the KTTV network if obtained). *Overlap (2026-11-05):* GHCN-D /
   GSOD stations feed GPCC and CPC, which adjust IMERG Final and GSMaP Gauge, and CHIRPS uses them directly; they are
   not an independent check of those products. Only KTTV stations not shared on the GTS are independent.
   *KTTV gauges, first result (2026-11-05).* Source: solieukttv.imech.info, a third-party mirror of KTTV data
   ("reference, for research"), crawled politely (one session, 4 s pause, cached per station) into
   `cache/gauges/kttv_imech/`. Core box: 371 stations listed, 232 with rain data: 31 manual stations (6-hourly
   totals at 01/07/13/19 local, 2015–2025; the 19:00 value is a residual of the daily total, the only negative
   values) and 198 automatic stations (hourly, **cumulative** since 20:00 local, 2023–2025; differenced to hourly
   totals). Days rebuilt as UTC days (07–07 local); lag test: correlation peaks at lag 0 (0.71 automatic, 0.44
   manual). QC: days with a negative value or an unexplained fall dropped; one duplicate; 2 gauge-days flagged by
   the neighbour test (≥ 150 mm, median of ≥ 3 neighbours within 15 km < 15 %) and dropped. 72,019 gauge-days,
   220 stations, September–December, satellite at the gauge pixel:

   | against gauges | totals | corr | POD / FAR ≥ 100 mm | POD / FAR ≥ 200 mm | satellite / gauge on gauge days ≥ 100 mm (median) |
   |---|---|---|---|---|---|
   | IMERG Early | 1.00 | 0.53 | 0.43 / 0.58 | 0.23 / 0.68 | 0.51 |
   | GSMaP NRT | 0.77 | 0.51 | 0.35 / 0.61 | 0.21 / 0.72 | 0.44 |
   | GSMaP Gauge | 0.85 | 0.52 | 0.41 / 0.61 | 0.26 / 0.72 | 0.50 |
   | IMERG Final | 0.92 | 0.56 | 0.42 / 0.55 | 0.17 / 0.55 | 0.52 |

   Pixel means of ≥ 3 gauges (less point-versus-area mismatch, 3,872 pixel-days): correlation 0.70–0.75, POD
   ≥ 100 mm 0.36–0.53, satellite / gauge on heavy days 0.54–0.67. By elevation the picture does not change
   (< 200 m: 169 stations; 200–600 m: 44; > 600 m: only 7). Heaviest network days: 2017-11-04 gauge mean 250 mm,
   products 136–196; 2018-12-09 233 mm, products 60–92. Molave 2020-10-28: gauge mean 55 mm (max 229), GSMaP 95–101,
   IMERG 53–63. Trà My alone (orographic) gets about half the gauge total in every product.
   Reading: (a) the **seasonal totals are nearly right** (0.77–1.00) but the **heavy days are halved**: the error
   is conditional on intensity, not a constant factor, and a single scale factor would not fix it; (b) at the point
   scale no product detects more than a quarter of the ≥ 200 mm days, and more than half of its own ≥ 200 mm days
   are false; (c) IMERG Early is not worse than Final, GSMaP NRT is the lowest. Consequences: (1) R2 is confirmed
   as a real, measured risk; (2) thresholds must be fitted on the product used in operation (the bias is then
   partly inside T) and the observed-rain error model must be **conditional on intensity** (§5); (3) the gauges are
   an input candidate in their own right (automatic stations hourly since 2023), pending an official source.
   Limits: the mirror is not an official KTTV service (licence and latency unknown, not usable for operation as
   is); automatic stations cover only three seasons; few stations above 600 m. Scripts in the session scratchpad;
   to move into `landslide/gauges.py` with tests before any use in F3.
4. *Latency*: the arrival time of each Early day measured for a full season (§8.4); in the 2026 season, measured in
   real time every hour (half-hourly IMERG, hourly GSMaP).
5. *ECMWF ENS*: the TIGGE archive (since 2006, research use) for the 2015–2025 hindcast, the open-data archive from
   2024 for the operational feed; quantile mapping to the observed product pooled by region and intensity class.
6. *Data sheets* of every input (§7).

## 10. Data and decisions needed from the owner

| Need | Why | Fallback |
|---|---|---|
| The 1:50,000 zoning maps (VIGMR) for Quảng Nam, Kon Tum, Thừa Thiên Huế | hazard zones of Article 46, baseline, comparison | our classes stand in, labelled as such |
| Geological map 1:200,000 / 1:50,000 and faults | C4: the largest missing predictor | DEM lineaments + GEM faults, labelled a proxy |
| Rain gauge data (KTTV), daily, 2015–2025 — critical path, escalate now (2026-11-05); a research mirror (imech.info) gave 220 stations for the first check (§9.1, step 3), an official source and licence are still needed | error model of the rain products (F2) | provincial gauges / the NCHMF radar; GHCN-D / GSOD stations (few in the mountains, and not independent of IMERG Final, GSMaP Gauge, CHIRPS) |
| Dated landslide records (VIGMR, provinces, news archive) | positive unit-days (F1) | `vietnam.csv` + Sentinel-2 dating |
| Commune boundaries after the 2025 reorganisation | warning units | the 2024 boundaries, mapped forward |
| The warning budget the users accept (false alarms per season) | sets the probability thresholds of the levels | a budget chosen by the owner, stated in F0 |
| Names for the review panel | A8 | the owner's own review, stated as such |
| Confirmation of the scores (L, I) of the risk register, §8.7 | priority of the prevention work; signed in F0 | the initial scores of §8.7 |
| Operating site: cloud server (with a backup in another region) or a server at the agency | R1: power and internet lost in a storm; cost; data rules | proposed: cloud as the primary, the agency's server as the backup; a personal workstation is never the operating site |
| Delivery channel to the communes (the province's official channel, SMS, Zalo…) and the recipients | R15: the bulletin must reach the commune, with a receipt | two channels in parallel, recipients listed by the province |
| ~~GSMaP account (JAXA, free)~~ **obtained 2026-11-03** | second rain product, 4 h latency (R6) | — |
| Terms of responsibility and use | R20: the product is advisory; the official level of Decision 18/2021 stays the legal reference | this sentence, printed in every bulletin and in the model card |

## 11. Risks

- **Too few dated landslides for T** (the main risk). Mitigation: the Sentinel-2 dating of scars per storm, regional
  pooling with partial pooling (hierarchical priors), and the Article 46 rule as a fallback that is always available.
- **Reporting bias.** Reports follow roads and deaths. The forecast is then a forecast of *reported* landslides;
  the bias term in T and the Sentinel-2 seasons (complete in space, not biased to roads) measure how large it is.
- **Rain product error in the mountains.** Satellite rain underestimates orographic extremes. Mitigation: the gauge
  check of F2, the error ensemble, and thresholds fitted on the same product used online.
- **Transfer.** The susceptibility model is trained on Quảng Nam – Kon Tum. Outside it, the confidence is "low" until
  local inventories are added (the north needs its own inventory; L8).
- **Province reorganisation (2025).** The regions of Phụ lục XII name the provinces before the merger; the mapping of
  the new units to the regions must be checked against any amendment of Decision 18.
- **Short forecast archive.** The open ECMWF ensemble at 0.25° starts in February 2024 (two seasons, 34 positive
  commune-days: too few for A6). A6 is therefore tested on the TIGGE archive of ECMWF ENS (since 2006, research use)
  for 2015–2025 (2026-11-05); the report states the number of cases behind A6.
- **Data service changes.** Products change version, latency or access (the Sentinel-1A end in 2026, the 0.4° to
  0.25° change of ECMWF in 2024). Each data sheet names a fallback, and the readiness review checks the notices of
  every provider before the season.
- **Over-tuning.** A1–A8 are frozen in F0 (revised once, 2026-11-05, before any hindcast), the hindcast is out of
  sample with the level thresholds chosen inside the folds, one season and one province are held out as a final
  test, and the shadow season (F9) is the last test.

## 12. References

Every DOI below was checked on Crossref on 2026-11-03.

- Ferro C.A.T., Stephenson D.B. (2011). Extremal dependence indices: improved verification measures for
  deterministic forecasts of rare binary events. *Weather and Forecasting* 26, 699–713.
  https://doi.org/10.1175/WAF-D-10-05030.1 (added 2026-11-05)
- Fell R., Corominas J., Bonnard C., Cascini L., Leroi E., Savage W.Z. (2008). Guidelines for landslide
  susceptibility, hazard and risk zoning for land use planning. *Engineering Geology* 102, 85–98.
  https://doi.org/10.1016/j.enggeo.2008.03.022
- Guzzetti F., Gariano S.L., Peruccacci S., Brunetti M.T., Marchesini I., Rossi M., Melillo M. (2020). Geographical
  landslide early warning systems. *Earth-Science Reviews* 200, 102973.
  https://doi.org/10.1016/j.earscirev.2019.102973
- Kirschbaum D., Stanley T. (2018). Satellite-based assessment of rainfall-triggered landslide hazard for situational
  awareness. *Earth's Future* 6, 505–523. https://doi.org/10.1002/2017EF000715
- Krøgli I.K., Devoli G., Colleuille H., Boje S., Sund M., Engen I.K. (2018). The Norwegian forecasting and warning
  service for rainfall- and snowmelt-induced landslides. *Natural Hazards and Earth System Sciences* 18, 1427–1450.
  https://doi.org/10.5194/nhess-18-1427-2018
- Piciullo L., Calvello M., Cepeda J.M. (2018). Territorial early warning systems for rainfall-induced landslides.
  *Earth-Science Reviews* 179, 228–247. https://doi.org/10.1016/j.earscirev.2018.02.013
- Stanley T.A., Kirschbaum D.B., Benz G., Emberson R.A., Amatya P.M., Medwedeff W., Clark M.K. (2021). Data-driven
  landslide nowcasting at the global scale. *Frontiers in Earth Science* 9, 640043.
  https://doi.org/10.3389/feart.2021.640043
- Data: IMERG V07 daily (GPM_3IMERGDE / DL / DF), NASA GES DISC, read through the Earthdata cloud OPeNDAP service.
- Data: TIGGE archive (ECMWF ensemble forecasts since 2006), ECMWF, for research use (added 2026-11-05).
- Thủ tướng Chính phủ (2021). Quyết định 18/2021/QĐ-TTg quy định về dự báo, cảnh báo, truyền tin thiên tai và cấp độ
  rủi ro thiên tai (Điều 46; Phụ lục XII, Bảng 5–6). In force from 2021-07-01; replaces Decision 44/2014/QĐ-TTg.
- The method references of the research steps (Brunetti et al. 2010, Steger et al. 2016, Meyer et al. 2019, …) are
  in [`landslide-susceptibility.md`](landslide-susceptibility.md) §9.
