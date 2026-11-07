# Risk register — landslide forecast system

> A living register: updated after every incident, at every readiness review (August), and whenever a measure is
> done. Method, detection and playbooks P1–P6: [`../landslide-forecast-system.md`](../landslide-forecast-system.md)
> §8.7. L (likelihood) and I (impact) on 1–5; score = L × I; impact 5 = a missed warning on a day with casualties.
> Prevention status: **done** / **in progress** / **not started** (the F step that does it). Initial scores
> 2026-11-03, to be confirmed by the owner (F0).

| # | Risk | L | I | Score | Prevention status | Next action | Step |
|---|---|---|---|---|---|---|---|
| R1 | Power / internet lost at the operating site in a storm | 4 | 5 | 20 | not started: the system runs on one workstation | choose the operating site (F0); cloud + backup | F8 |
| R2 | Satellite rain far too low in an extreme (silent failure) | 4 | 5 | 20 | **in progress**: four satellite products compared (2026-11-04); on storm days they differ by up to 2×, not in one direction (Podul: IMERG highest; Molave: GSMaP highest); **measured against 220 KTTV gauges** (imech.info mirror, 2026-11-05): seasonal totals 0.77–1.00, but on gauge days ≥ 100 mm the satellite gives about half, POD ≥ 200 mm 0.17–0.26 | intensity-conditional error model; an official gauge source (KTTV); the spread between products enters the uncertainty; the "never below the forecast rain" rule | F2, F5 |
| R4 | Too many false alarms, users stop listening | 4 | 4 | 16 | not started | warning budget (F0), agreed region-wide as a false-alarm ratio, not only per commune (2026-11-05) | F0, F7 |
| R3 | Rain beyond the training range | 3 | 5 | 15 | not started | monotonic models, "beyond experience" label | F5 |
| R5 | Unwarned landslide with casualties | 3 | 5 | 15 | not started | A1; Article 46 level shown beside ours | F7, F8 |
| R15 | Bulletin does not reach the communes | 3 | 5 | 15 | not started | choose channels (F0); receipts | F8 |
| R6 | Observed rain late / missing | 4 | 3 | 12 | **mostly done**: two sources reachable — IMERG (NASA) and GSMaP (JAXA, account 2026-11-03), independent for provider outages but not for errors (shared PMW sensors GMI, AMSR2, SSMIS, MHS and GEO IR; 2026-11-05); 2015–2025 archives complete for all four products (2026-11-04) | measure the real latency | F2 |
| R8 | Forecasts miss the typhoon track | 3 | 4 | 12 | not started | probabilities from the ENS members | F5 |
| R9 | Disk full, crash | 3 | 4 | 12 | **partly done**: free-space check before every phase; the trash never copies (2026-11-03, after the incident) | separate operational volume | F8 |
| R10 | A release breaks the chain | 3 | 4 | 12 | partly: the golden test caught the float32 DCT change (2026-11-03) | CI, release freeze in the season | F8 |
| R13 | Time errors (UTC / local) | 3 | 4 | 12 | not started; IMERG days are UTC (7 h offset) | UTC inside, day-boundary tests | F2 |
| R14 | No forecaster available | 3 | 4 | 12 | not started | roster; automatic "not reviewed" bulletin | F8 |
| R16 | Probability misread | 3 | 4 | 12 | not started | fixed vocabulary; training | F8 |
| R17 | Our level contradicts the official one | 4 | 3 | 12 | not started | show both, with the reason | F8 |
| R20 | Legal responsibility | 2 | 5 | 10 | not started | terms of use (F0) | F0 |
| R7 | Forecast rain (ENS) late / missing | 3 | 3 | 9 | not started | GFS as backup | F2 |
| R11 | Provider changes format / access | 3 | 3 | 9 | **happened**: the old `gpm1.gesdisc` OPeNDAP server no longer answers; moved to `opendap.earthdata.nasa.gov` (2026-11-03) | data sheets with a second source | F2 |
| R18 | Susceptibility stale after a major event | 3 | 3 | 9 | not started | forced updates of §8.2 | F8 |
| R12 | Credentials exposed | 2 | 4 | 8 | **happened** (a password printed in a log, changed) | vault; never printed | F8 |
| R19 | Model drift | 2 | 3 | 6 | not started | yearly refit | F8 |

## Incident log

| Date | Incident | Risk | Cause | Action | Closed |
|---|---|---|---|---|---|
| 2026-11-03 | Disk D full, the L5 run stopped | R9 | a project moved to the trash by copying (a held `.pmtiles` blocked the rename) | the trash only renames; free-space check before every phase; tested | yes |
| 2026-11-04 | Disk D full again inside the PS phase (step 7 save), L5 stopped after unwrapping | R9 | the 5 GB floor is checked only between phases; one PS phase writes > 10 GB of checkpoints | removed two duplicate trash copies (no data lost), resumed from step 6; open: a floor check before every checkpoint write and a separate volume (F8) | no |
| 2026-11-03 | CSK golden test: one point off by 1.65 mm/yr | R10 | float32 DCT in IRLS | reverted; test passes again | yes |
| 2026-11-03 | The old GES DISC OPeNDAP server does not answer | R11 | provider infrastructure change | cloud OPeNDAP through CMR | yes |
| before 2026-11-03 | Earthdata password printed in a log | R12 | a command read the credentials file | password changed; credentials files never printed | yes |
