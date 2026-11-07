# Site advisor: from an area to a processing recipe

Asked by the owner on 2026-11-07. There are about 120 processing parameters, and it is easy to forget what each
one is for. The goal: pick an area, and see at once what that area needs (which corrections and which method)
and how to set the parameters, with the reason for each choice. It must run **without an LLM**, so it costs no
tokens: deterministic rules on measured site properties.

## 1. What exists already

- A one-line help for every form field (`api/settings.py` `FIELDS`, `PS_GROUPS`, Vietnamese titles).
- Data-driven `auto` modes that already act as site rules inside the engine: `scla_deramp = "auto"` (ramp
  selection), `subtr_tropo` / `[atmosphere] select = "auto"` (APS selection), `[sbas] troposphere = "auto"`
  (relief < 100 m → off), `max_topo_err = "auto"`, `unwrap_time_win = "auto"`.
- Site layers: terrain (`landslide/terrain.py`), geology (`ancillary/geology.py`), land cover and predictors
  (`landslide/predictors.py`, `ml/layers.py`), water mask, DEM download.
- The owner's settings recorded in memory and in the project files: unwrap grid 10 m (HCMC 50 m), PL `ad` +
  `adaptive`, IRLS unwrapping, CSK chain without wavelet / FAMM.

What is missing: one place that ties a site property to a parameter, and says why.

## 2. Design

Three parts, all plain Python and data files.

1. **Parameter catalogue** `advisor/params.toml` (TOML like the rest of the project), one entry per parameter: section, key, phase, purpose,
   benefit, cost / risk, typical values, related parameters, en + vi. The form help is generated from it (one
   source instead of two).
2. **Site profile** `geoeyes.advisor.profile(bbox, sensor)` → a small dict of measured properties, cached per AOI:
   - terrain: relief p5–p95, median slope, share of slopes > 20°;
   - land cover: urban / vegetation / cropland / water shares (ESA WorldCover);
   - climate: Köppen class, mean humidity and rain season (ERA5 climatology);
   - geology: soft sediments share (existing geology layer);
   - data: sensor, wavelength, number of dates, revisit, baseline spread (from the ASF search or the stack).
3. **Rules** `advisor/rules.toml`: `if` (conditions on the profile) → `set` (parameter values) + `why`
   (en + vi) + `source` (paper, ADR, or the project where it was learned). Examples:
   - urban share > 0.5 → `method = psi`, `da_threshold = 0.4`, `unwrap_grid_size = 10`;
   - vegetation share > 0.5 and C-band → `psds`, phase linking on (`ad`, `adaptive`), or `sbas`;
   - relief > 500 m → `[atmosphere] method = era5`, `subtr_tropo = auto`; relief < 100 m → troposphere off;
   - soft sediments > 0.3 and urban (HCMC, Hanoi) → fast subsidence: `unwrap_ps_rate`, `unwrap_grid_size = 50`
     for HCMC, `scn_time_fit = linear`;
   - slope > 20° on a large share → landslide mode: `hazard` downslope projection, ascending + descending;
   - fewer than about 20 dates → warn (SHP test and point rates unreliable; `ps_lite` is for Capella / Umbra only,
     the schema refuses it for Sentinel-1).
   Rules are ordered; a later, more specific rule overrides an earlier one; conflicts are listed, not hidden.

Output: a **recipe** — the parameter values, each with its reason and the rule that set it, plus a diff against
the current `project.toml`. The owner applies it in one click or field by field.

### Where it is shown, with no tokens

- Web app: the wizard (new project) and the settings form, a panel "Advisor" beside each section; each field
  shows "suggested: X, because …".
- CLI: `geoeyes advise <project>` or `geoeyes advise --bbox W S E N`, text or TOML.
- MCP (optional, step V5): a tiny local MCP server wrapping the same functions, so Claude can query the catalogue
  and the recipe in a session. The rules engine never calls an LLM; the MCP only lets an LLM read it when wanted.

### Learning from finished projects

Each project already has its `project.toml` and QC results. A command `geoeyes advise --learn` collects the
settings the owner kept after review (hcm_d18, hp_maychai, mexico_s1, hanoi_s1…) together with the site profile,
and shows where the rules disagree with what was actually used. Rules are edited by hand from that report; no
automatic fitting (too few projects).

## 3. Steps (a review gate after each)

- [x] **V0** (done 2026-11-07) Catalogue: `src/geoeyes/advisor/params.toml`, 105 entries (help, use, risk,
  typical, related; en + vi), read by `advisor/catalog.py`, the form ("why?" under each field, search over the
  texts) and `geoeyes params`; tests `tests/unit/advisor/test_param_catalog.py`. Was: write `params.yaml` for every field in the form (from `FIELDS`, the StaMPS docs and the
  ADRs), generate the form help from it. No behaviour change.
- [x] **V1** (done 2026-11-07) Site profile: `advisor/profile.py`, `geoeyes site <project> | --bbox=W,S,E,N
  [--lang vi] [--json]`; tests `tests/unit/advisor/test_site_profile.py`.
  - terrain: `ml.layers.terrain` on 30 m cells (coarser above 2.5 M cells); relief p5–p95 as `[sbas]
    troposphere = auto`; slope median / p90, share > 20° and > 35°;
  - land cover: `ml.layers.worldcover` shares; geology: GLiM shares (`landslide.predictors.lithology`), soft =
    "su";
  - climate: one Open-Meteo ERA5 request at the centre (10 complete years of daily rain, temperature, humidity);
    the Köppen-Geiger class is computed from the monthly climatology (Peel et al. 2007; where both the dry-summer
    and the dry-winter tests hold, the wetter half decides), so no climate map is downloaded;
  - data: per track from the stack QC (`stacks/*/qc/qc.json`: dates, span, revisit, largest gap, B⊥ p5–p95,
    median coherence, height of ambiguity; band from the wavelength); without a stack, the configured dates. A QC
    coherence of 1.0 on every date is flagged (seen on hp_maychai). Counting the ASF dates before a stack exists
    is left for V2 if a rule needs it.
  - Cache: terrain, land cover, geology per AOI + DEM in `cache/advisor/site_*.json`; the climate as its raw
    request (classes recomputed); data never cached. A part that fails is listed in `errors`.

  First profiles (2026-11-07):

  | AOI | relief | slope > 20° | land cover | soft sediments | Köppen, rain |
  |---|---|---|---|---|---|
  | hcm_d18 (HCMC SW) | 11.7 m | 0 % | built 58 %, tree 17 % | 100 % | Aw, 1887 mm |
  | hp_maychai (Hai Phong) | 10.2 m | 0 % | built 44 %, water 18 % | 100 % | Cwa, 1841 mm |
  | hanoi_s1_desc | 10.7 m | 0 % | built 30 %, tree 29 %, crop 28 % | 100 % | Cwa, 1852 mm |
  | Nam Tra My (Quang Nam) | 1162 m | 62 % | tree 90 % | 0 % | Af, 4328 mm |
  | Mexico City | 92 m | 1 % | built 72 % | 86 % | Cwb, 789 mm |
- [x] **V2** (done 2026-11-07, rules awaiting the owner's review one by one) Rules: `src/geoeyes/advisor/rules.toml`
  (16 rules, 3 named regions), evaluator `advisor/rules.py`, `geoeyes advise <project> | --bbox=W,S,E,N [--lang vi]
  [--json] [--apply]`; tests `tests/unit/advisor/test_rules.py`.
  - A condition is `<metric> <op> <value>` (no eval); a metric the profile lacks makes the rule "not evaluated".
  - Later rules win; the replaced value is shown. Notes advise without setting anything.
  - Against a project: changes, values already as the rules say, and values of project.toml no rule explains.
  - `--apply` writes the changes through the settings form code (validated, previous file in `.state/`).

  Results (2026-11-07): hcm_d18 and hp_maychai: **no change** (8 and 5 values already as the rules say; left
  unexplained: `da_threshold` 0.42 = default, the SARPROZ reference of hcm_d18). hanoi_s1_desc: one change,
  `acquire.max_per_month` 2 -> 0 (soft-urban-subsidence); data rules not evaluated (no stack yet). Nam Tra My:
  ERA5 + psds + phase linking (ad, adaptive) + DA 0.6 + copernicus-30, notes on tropical convection and asc + desc.
- [x] **V3** (done 2026-11-07) Web app: `GET /api/projects/{name}/advise` and `POST /api/advise {bbox}`
  (`api/advise.py`, same code as the CLI); `components/AdvisorPanel.tsx`.
  - Settings form: the panel above the sections (site summary, suggested changes with "use" / "put all in the
    form", values already as the rules say, notes, values no rule explains, "measure the site again"); under each
    field the rule's value, green when it holds, amber with "use" when not. "use" only fills the draft: nothing
    is written until Save.
  - New-project wizard: "Ask the site advisor" after the area; method, atmosphere and images per month go into
    their fields (the wizard's own default ERA5 is replaced on flat deltas), the other values are written into
    project.toml after creation when the box is ticked.
  - Tests `tests/unit/api/test_api_advise.py` (project, apply through the settings endpoint, bbox).
- [ ] **V4** `--learn` report comparing rules with finished projects.
- [ ] **V5** (optional) local MCP server `geoeyes-advisor` with tools `explain_param`, `site_profile`, `recipe`.

## 4. Difficulty

Moderate. V0 is mostly writing; V1 reuses existing readers (WorldCover and the ERA5 climatology are the only new
downloads); V2 is a few hundred lines. The hard part is not the code but the rules themselves: they must state
the owner's experience correctly, so V2 is reviewed rule by rule.
