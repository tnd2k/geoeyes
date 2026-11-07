# F0 — Requirements and criteria of the landslide forecast system (for sign-off)

> Step F0 of [`../landslide-forecast-system.md`](../landslide-forecast-system.md) §9. Status: **A1–A8 approved in
> principle, sign-off pending** (draft 2026-11-03; A1–A6 revised after review on 2026-11-05, before any hindcast was
> run). The other values are **proposed defaults**: the owner edits the "Decision" column where he wants a change.
> Once signed, the values are frozen and not changed after the hindcast is run.

## 1. Scope of the first version (v1)

| Item | Proposed | Decision |
|---|---|---|
| Area | the central provinces, with Quảng Nam – Kon Tum as the core (calibration area); the other provinces of region 3 (Phụ lục XII) at confidence "low" until local inventories exist | |
| Warning unit | the commune (boundaries after the 2025 reorganisation); slope units inside it for detail only | |
| Lead times | today, +24 h, +48 h, +72 h | |
| Operating season | September–December (centre) | |
| Main users | provincial and commune steering committees (PCTT & TKCN); the provincial hydro-meteorological service | |
| Legal role | advisory; the official level of Decision 18/2021 is the legal reference | |
| Shadow season | September–December 2027 | |

## 2. Acceptance criteria A1–A8

| # | Criterion | Proposed | Decision |
|---|---|---|---|
| A1 | Share of landslide days whose verification unit (district / warning zone, or a multi-day window) is at the warning level or above | ≥ 0.75, with its 95 % interval and the number of events | approved in principle; revised 2026-11-05 |
| A2 | False alarms: (a) region-wide false-alarm ratio; (b) warning days per commune and season | (a) ≤ FAR budget (to be agreed); (b) ≤ 5 | approved in principle; (a) added 2026-11-05 |
| A3 | Better than the Article 46 rule (levels mapped to their cross-validated observed frequencies) and than rain alone | Brier skill score > 0, 95 % interval above 0; PR-AUC, CSI / ETS, SEDI reported | approved in principle; revised 2026-11-05 |
| A4 | Reliability of the probabilities | inside the 90 % consistency band, bins with ≥ 10 events | approved in principle; revised 2026-11-05 |
| A5 | Predicted against observed landslide-days per unit-season (or probability bin); randomized PIT | 80 % interval of the counts holds 75–85 %; PIT uniform | approved in principle; revised 2026-11-05 (coverage of a binary outcome is meaningless) |
| A6 | A1 and A3 still hold at +24 h with the forecast rain (ECMWF ENS, TIGGE 2015–2025) | yes | approved in principle; archive changed 2026-11-05 |
| A7 | Run time; reproducibility | ≤ 5 min per province; same inputs, same output | approved in principle |
| A8 | Review panel acceptance | written | approved in principle (optional) |

*Why revised (2026-11-05):* 97 positive commune-days on 61 days in 11 seasons give a base rate of order 10⁻⁴; with
A2 (b) alone A1 can pass with a FAR above 0.99, ROC AUC is inflated by true negatives and A4 cannot fail on empty
bins. Details: §1 of the design. Thresholds of the levels are chosen inside the leave-one-season-out folds.

**Warning budget** (sets the probability thresholds of the levels, A2): proposed **≤ 5 false-alarm days per commune
and season**, and a **region-wide false-alarm ratio** to be agreed with the users (2026-11-05). A larger budget makes A1 easier; a smaller one misses more. This trade-off is the users' decision,
not the model's.

## 3. Operations targets (§8 of the design)

| Item | Proposed | Decision |
|---|---|---|
| Routine bulletin times | 07:00 and 19:00 local time. Estimate: the 12 UTC ENS is available about 03:00 local, the 00 UTC run about 15:00; F2 measures the real times | |
| Storm mode | runs every 3 h, bulletins every 6 h and at once on a level change | |
| Storm-mode triggers | P(> 100 mm / 24 h) ≥ 30 % in a unit; or an official warning; or Article 46 level ≥ 1 | |
| Time budget | bulletin ≤ T0 + 5 h (storm ≤ T0 + 4.5 h) | |
| Warning lead time | counted in days (reports dated to the day, ± 1): ≥ 50 % of landslide days warned ≥ 1 day ahead (revised 2026-11-05; was median ≥ 12 h) | |
| Indicator levels (green / amber / red) | as in §8.6 | |
| Maximum ages of the layers | as in §8.2 | |
| Readiness review | every year before 15 August | |

## 4. Infrastructure and organisation

| Item | Proposed | Decision |
|---|---|---|
| Operating site | a cloud server as the primary, a server at the agency as the backup; never a personal workstation | |
| Delivery channel | two channels: the province's official channel and SMS / Zalo; recipients listed by the province | |
| Duty roster | one main forecaster and one deputy for the rainy season | |
| Review panel | engineering geologist, hydro-meteorological forecaster, statistician, provincial PCTT representative (names to be proposed by the owner) | |
| Terms of use | the sentence of §1, printed in every bulletin and in the model card | |

## 5. Data needed from the owner (§10 of the design)

| Data | Why | Status |
|---|---|---|
| 1:50,000 zoning maps (VIGMR) | Article 46 hazard zones, baseline | missing |
| Geological map 1:200,000 / 1:50,000 and faults | the last lever of the susceptibility map (C4) | missing |
| KTTV daily rain gauges 2015–2025 | error of satellite rain (F2, R2) | missing |
| Dated landslide records (VIGMR, provinces) | catalogue for the trigger model (F1) | missing; news harvest under way |
| GSMaP account (JAXA, free) | second rain product, 4 h latency | **done** (2026-11-03) |
| Commune boundaries after 2025 | warning units | official source needed |

## 6. Risk register

See [`risk-register.md`](risk-register.md): 20 risks with their initial scores; the owner confirms or edits L and I.

## Sign-off

| | Name | Date | Notes |
|---|---|---|---|
| Owner | | | |
