# Skill: corner reflector validation (Sentinel-1)

> Check that installed trihedral corner reflectors are seen where and as strongly as expected on every Sentinel-1
> acquisition: required pointing, expected vs measured RCS, position of the peak, signal-to-clutter ratio and
> coherence at the reflector. Status: operational for Sentinel-1 IW bursts (port of the legacy CR report, checked
> bit-identical on RCS, SCR and coherence). Last checked against the code: 2026-11-01. CLI: `geoeyes cr-report`.
> Web app: project → **Validation** → Corner reflectors → **Build CR report**.

## 1. When to use it

- **Questions.** Is each reflector visible on each pass, pointed correctly for that track, and stable between
  acquisitions? Where does its peak fall relative to its surveyed position? How should it be pointed for a track?
- **Decisions.** Re-point or re-level a reflector; keep it as a reference point or a GNSS co-location target
  (research step G4 of [gnss-calibration.md](gnss-calibration.md)); accept an acquisition for the reflector series.
- **Use it** after installing or moving reflectors, after each field visit (with the set-up log), and to plan the
  pointing for a new track (the `pointing` table works even before installation).
- **Not covered by the code:** displacement time series of the reflector (read the nearest point of the product),
  other sensors than Sentinel-1, cross-pol data (VV only).

## 2. Data to prepare

| Item | Required? | Source / how to get it | Format, where it goes | Notes |
|---|---|---|---|---|
| Reflector list | yes | field survey (GNSS) of each reflector | CSV, path in `[validation.corner_reflector] points` (relative to the project folder, e.g. `geom/points.csv`). Columns (case-insensitive): `lon`/`longitude`, `lat`/`latitude` required; optional `name`/`id`/`target_name`, `height`/`h`/`elevation`/`elev`/`alt`/`altitude`/`altitude_m` (ellipsoidal m), `edge_m`/`size_m`/`edge`/`target_size_m` | without height 0 m is used (warning): a wrong height shifts the predicted position; without a name, `CR<row>` |
| Set-up log | optional, strongly advised | field notes of every installation or adjustment | CSV in `[validation.corner_reflector] setup` (e.g. `geom/cr_setup.csv`). Columns: `valid_from`/`from`/`date`/`datetime` (`YYYY-MM-DD[ HH:MM]`, local time), `face_azimuth_deg`/`azimuth_deg`/`azimuth`, `base_tilt_deg`/`tilt_deg`/`tilt`; optional `name`/`id` (default `*` = every reflector), `note`/`ghi_chu`/`description` | each row holds until the next row of the same reflector; without a row the reflector is assumed pointed as required (`setup_source = "assumed"`) |
| Time zone of the log | optional | – | `[validation.corner_reflector] timezone` (IANA name) | default `Asia/Ho_Chi_Minh` |
| Default edge length | optional | reflector drawings: inner edge of the triangular trihedral | `[validation.corner_reflector] edge_m` | default 0.8 m |
| Date window | optional | – | `start`, `end` (`YYYY-MM-DD`) | default `start` = the day before the first set-up entry; `end` open |
| Sentinel-1 bursts covering the reflectors | yes | phase `acquire` from ASF (`[acquire] date_range`, the track's `relative_orbit`), NASA Earthdata token in `EARTHDATA_TOKEN`; the AOI must contain the reflectors | `archive/sentinel1/<track_id>/…/<SLC>/` with `bursts.json`, `IWn_VV_<burst>.tiff`, `<SLC>_VV.xml` (annotation and calibration), or the folder in `[acquire] archive` | only VV bursts are read; only Sentinel-1 tracks of the project |
| `typst` Python package | for the PDF | in the `insar` environment | – | `--no-pdf` writes JSON, CSV and figures only |

Example:

```toml
[validation.corner_reflector]
points = "geom/points.csv"
setup = "geom/cr_setup.csv"
timezone = "Asia/Ho_Chi_Minh"
edge_m = 0.8
start = ""
end = ""
```

Checklist:

- [ ] heights are **ellipsoidal** (not above the geoid), in metres, from a survey of the reflector;
- [ ] `edge_m` is the inner edge of the trihedral (per reflector or the default);
- [ ] the set-up log has local times in the `timezone` given, and one row per change;
- [ ] the archive holds the acquisitions of the window, with bursts covering the reflectors.

## 3. Method

Per reflector and per acquisition (`validation/corner_reflector/pipeline.py`):

1. **Location.** Range-Doppler on the burst's orbit (state vectors of the burst annotation; `scenes()` applies no
   precise orbit): zero-Doppler time and slant range of the reflector at its height give (line, sample), the
   subswath and burst, the LOS azimuth and elevation (ground → satellite) and the incidence. Acquisitions that do not
   image the reflector are skipped.
2. **Chip and calibration.** A chip of ±48 lines × ±192 samples is read; β⁰ = |DN|² / A² with A from the
   beta-nought LUT of the calibration block.
3. **RCS (integrated energy, `measure.py`).** Peak search within ±1 line × ±2 samples of the predicted position
   (`CELL_SEARCH`); energy of the main lobe in a 3 × 5 window minus the clutter level (median β⁰ of the chip outside
   a cross of ±4 lines / ±10 samples around the peak), times the pixel area (range × azimuth spacing):
   RCS = 10·log₁₀[(Σβ⁰ − 15·clutter)·Δr·Δa] dBsm; SCR = energy / (15·clutter·Δr·Δa) in dB. Sub-pixel peak by a
   parabola. A wider search (±2 × ±8, `NEAR_SEARCH`) flags a stronger scatterer nearby.
4. **Position.** The peak is geocoded at the reflector height; offsets north/east and total (m) from the surveyed
   position.
5. **Expected RCS (`trihedral.py`, Knott).** Edges of a base-plate trihedral facing `face_azimuth_deg` with its base
   tilted `base_tilt_deg` (front edge raised): boresight elevation = 35.26° + tilt. With the direction cosines
   l ≤ m ≤ n of the radar direction on the three edges and inner edge a:
   A = 4·l·m·a²/(l+m+n) if l+m ≤ n, else A = a²·[(l+m+n) − 2/(l+m+n)]; RCS = 4π·A²/λ²; 0 when l ≤ 0 (the satellite
   sees the back). On boresight RCS = 4π·a⁴/(3λ²) (≈ 27.5 dBsm for a = 0.8 m at C band).
6. **Tolerance.** `within_tolerance` when |measured − expected| ≤ 3 dB (`TOLERANCE_DB`).
7. **Required pointing.** Per reflector and track, from the latest acquisition: face azimuth = LOS azimuth,
   boresight elevation = LOS elevation, base tilt = LOS elevation − 35.26°.
8. **Coherence.** Per reflector, track and subswath: every date pair up to 10 dates (`MAX_PAIRS_ALL`), consecutive
   pairs above. Chips are deramped in azimuth (TOPS Doppler), aligned by amplitude cross-correlation (sub-pixel,
   Fourier shift), the dominant fringe removed per 32 × 128 block, coherence in a 3 × 5 window: at the reflector
   peak, and median / P90 over the chip (8 lines and 24 samples trimmed at the edges).

## 4. Steps

1. **Configure** `[validation.corner_reflector]` (Settings → project.toml in the web app, or the file) and put the
   CSVs in the project (e.g. `geom/`).
2. **Make sure the bursts are there**: `geoeyes run <project> --only acquire` (or a full run) with a `date_range`
   covering the window.
3. **Run.**
   ```
   geoeyes cr-report <project> [--track ID] [--no-pdf]
   ```
   Web: project → **Validation** → Corner reflectors → **Build CR report** (background; the log is shown while it
   runs). One report per Sentinel-1 track. Time: one chip per reflector and acquisition plus the coherence pairs;
   short compared with processing, not measured here. The CLI prints per track
   `<n> observation(s), <k> within tolerance -> <pdf>`.
4. **Read** the report in the Validation tab (list of reports, tables, figures, PDF) or in the folder below.

Files written in `<project>/validation/corner_reflector/<YYYYmmdd-HHMMSS>_<track>/`:
`cr_report.json`, `observations.csv`, `coherence.csv`, `pointing.csv`, `<name>_chips.png`, `<name>_rcs.png` per
reflector, `cr_report.pdf` (Typst).

## 5. Outputs and how to read them

| Field (`observations.csv`) | Meaning |
|---|---|
| `date`, `acquired_utc`, `acquired_local`, `platform`, `track`, `direction`, `swath`, `burst` | the acquisition |
| `los_azimuth_deg`, `los_elevation_deg`, `incidence_deg` | direction to the satellite at the reflector |
| `setup_face_azimuth_deg`, `setup_base_tilt_deg`, `setup_source` (`log` \| `assumed`), `setup_note` | set-up used for the expected RCS |
| `expected_dbsm`, `measured_dbsm`, `difference_db`, `within_tolerance` | expected vs measured RCS; `-inf` expected = the satellite sees the back ("CR faces away") |
| `scr_db` | signal-to-clutter ratio; higher = cleaner phase |
| `offset_north_m`, `offset_east_m`, `offset_m` | measured peak minus surveyed position |
| `nearby_dbsm`, `nearby_offset_m` | strongest response within ±2 × ±8 pixels |

`pointing.csv`: required face azimuth, boresight elevation, base tilt per reflector and track. `coherence.csv`:
`at_reflector`, `area_median`, `area_p90`, `offset_az_px`, `offset_rg_px` per date pair. Figures: β⁰ chips with
predicted and measured positions; RCS per date with the expected value ± 3 dB band and the boresight line. The PDF
summary gives per reflector the share within tolerance, the range of position offsets and of coherence, back-facing
dates, assumed set-ups and stronger neighbours.

## 6. Quality checks

- Measured RCS within ±3 dB of expected on the passes the reflector faces; a systematic deficit means mis-pointing,
  a wrong `edge_m`, or debris/water in the reflector.
- `offset_m` small and stable between dates; a constant offset suggests a wrong height or surveyed position.
  (Reference: the port agreed with the legacy report within ≤ 6 mm in peak position on S1D track 91, 3 dates;
  `docs/en/refactor/TODO.md`.)
- `scr_db` high and `at_reflector` coherence clearly above the chip's `area_median`.
- `nearby_dbsm` not above `measured_dbsm` + 1 dB close to the reflector: otherwise a building may dominate the cell.
- Entries with `setup_source = "assumed"` are expectations, not checks: complete the log.

## 7. Limits and pitfalls

- Sentinel-1 IW only, VV only, bursts from the archive; other sensors are skipped and a project without S1 fails.
- The burst annotation orbit is used, not POEORB (geolocation differences of the order of the legacy report's).
- Height errors move the predicted position, hence the search window (±1 × ±2 pixels) may miss the peak.
- A reflector facing one pass direction gives no expected RCS on the other: expected.
- The search window is fixed to one resolution cell; a stronger scatterer outside it is reported but not used.
- This module does not compute the reflector's displacement series: read the point of the product nearest to the
  reflector. `[selection] forced_points` exists in the schema but is not read by the engines (2026-11-01).

## 8. On a new area or sensor

- New site: change `timezone`, write `points` (ellipsoidal heights!) and `setup`, set the AOI and `date_range` so the
  bursts cover the reflectors. Run once before installation to get `pointing.csv` for each track.
- Co-locate reflectors with a GNSS antenna to address the monument problem (research step G4: reflector − GNSS
  < 2 mm/yr as criterion, [../research/gnss-insar-calibration.md](../research/gnss-insar-calibration.md) §9).
- Other sensors (CSK, Capella, ICEYE): not supported by this module.
- Carries over: tolerance (3 dB), search windows, coherence method.

## 9. References

- Code: `src/geoeyes/validation/corner_reflector/__init__.py` (`build_cr_report`, configuration),
  `inputs.py`, `pipeline.py`, `measure.py`, `trihedral.py`, `s1burst.py`, `report.py`, `cr_report.typ`;
  `src/geoeyes/cli/main.py` (`cmd_cr_report`); `webapp/src/components/Validation.tsx`; test
  `tests/unit/validation/test_corner_reflector.py`.
- Guides: [../guide/projects-and-data.md](../guide/projects-and-data.md) §4.
- Skills: [gnss-calibration.md](gnss-calibration.md), [insar-processing.md](insar-processing.md).
- Papers: Knott EF, Shaeffer JF, Tuley MT (2004) *Radar Cross Section*, 2nd ed., SciTech (trihedral RCS).
  Parker AL et al. (2017) *Sensors* 17:1753; Mahapatra P et al. (2018) *J. Geodesy* 92:21–32 (reflectors and
  transponders with GNSS; DOIs in the GNSS research note §11).
