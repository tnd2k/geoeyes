// Types and calls of the GeoEyes API (src/geoeyes/api). Same origin: served by `geoeyes serve`, proxied by Vite in dev.

export type Status = "new" | "idle" | "done" | "interrupted" | "failed" | "running" | "invalid";

export interface PhaseRecord {
  status: string;
  seconds?: number | null;
  updated?: string | null;
  run_id?: string | null;
  error?: string | null;
}

export interface ProductBrief {
  id: string;
  version: string;
  created?: string;
  n_points?: number;
  epochs?: number;
  first?: string;
  last?: string;
  vel_min?: number;
  vel_max?: number;
  engine?: string;
  confidence?: "high" | "medium" | "low" | null;
  issues: string[];
  report: boolean;
}

export interface Track {
  track_id: string;
  sensor: string;
  direction: string;
  relative_orbit?: number | null;
  subswaths: string[];
  phases: Record<string, PhaseRecord>;
  product: ProductBrief | null;
  status: Status;
}

export interface RunRecord {
  id: string;
  status: string;
  phases: { phase: string; track: string; status: string; seconds?: number; error?: string }[];
  seconds: number | null;
  error: string | null;
}

export interface ProjectSummary {
  name: string;
  description?: string;
  method?: string;
  bbox?: [number, number, number, number] | null;
  status: Status;
  error?: string;
  running?: { pid: number; started: string; run_id: string | null } | null;
  date_range?: [string, string] | null;
  last_run?: RunRecord | null;
  alerts?: number;
  tracks: Track[];
}

export interface Folder {
  name: string;
  projects: string[];
  folders: Folder[];
}

export interface FolderTree {
  folders: Folder[];
  projects: string[];
}

export interface HazardLevelCount {
  cells: number;
  km2: number;
}

export interface HazardSummary {
  product_id: string;
  created: string;
  params: Record<string, unknown> & { cell_m: number; horizon_yr: number; max_lag_months: number; alpha: number; rain_source: string };
  dates: string[];
  span_months: number;
  n_cells: number;
  n_points: number;
  bounds: [number, number, number, number];
  dem: string;
  levels: string[];
  by_level: Record<"subsidence" | "landslide", Record<string, HazardLevelCount | number>>;
  coupling: {
    assessed: boolean;
    cells_tested: number;
    cells_significant: number;
    cells_p_below_alpha: number;
    fdr: boolean;
    lag_months_median: number | null;
    share_positive_k: number | null;
  };
  accelerating_cells: number;
  opposite_motion_cells: number;
  reference: {
    kind: string;
    bbox?: number[];
    cells?: number;
    lon?: number;
    lat?: number;
    stations?: string[];
    calibration?: string;
    rate_offset_mm_yr?: number;
    loo_rms_after_mm_yr?: number | null;
  };
  rain: {
    source: string;
    res_deg: number;
    months: string[];
    climate_years: [number, number];
    pixels: { lon: number; lat: number; cells: number; mean_month_mm: number; missing: number; annual: { p10: number; p50: number; p90: number } | null; assessed: boolean }[];
  };
  groundwater?: GroundwaterSummary;
  warnings: string[];
}

export interface BehaviourSummary {
  classes: string[];
  counts: Record<string, number>;
  not_assessed: number;
  dates: string[];
  changes_by_month: Record<string, number>;
  shared_change_dates: string[];
  warnings: string[];
  created: string;
  hazard_created?: string;
}

export interface RiskSummary {
  levels: string[];
  n_buildings: number;
  assessed: number;
  by_source: Record<string, number>;
  by_risk: Record<string, number>;
  footprint_km2_by_risk: Record<string, number>;
  height_known_share: number;
  median_floors_assumed: number;
  consequence_matrix: number[][];
  risk_matrix: number[][];
  params: Record<string, unknown>;
  warnings: string[];
  created: string;
}

export interface AnalysisStatus<S> {
  summary: S | null;
  running: boolean;
  failed: boolean;
  log: string[];
}

export interface LinesSummary {
  n_lines: number;
  n_stations: number;
  by_kind: Record<string, { lines: number; km: number; covered_share: number | null; flagged_stations: number }>;
  hotspots: { line: number; kind: string; name: string; beta_max: number; v_min_mm_yr: number; flagged: number }[];
  params: { step_m: number; buffer_m: number; span_m: number; horizon_yr: number };
  created: string;
}

export interface ConsolidationSummary {
  sinking_cells: number;
  consolidating: number;
  remaining_mm: { median: number; p90: number; max: number } | null;
  tau_yr_median: number | null;
  check: { cells?: number; train_epochs?: number; test_epochs?: number; mae_curve_mm?: number; mae_line_mm?: number; curve_better_share?: number };
  created: string;
}

export interface DecomposeProduct {
  id: string;
  project: string;
  track: string;
  sensor: string;
  first: string;
  last: string;
  los: [number, number, number];
  overlap_days: number | null;
  overlap_share: number | null;
}

type Stats = { min: number; p02: number; median: number; p98: number; max: number };

export interface DecomposeSummary {
  products: DecomposeProduct[];
  n_cells: number;
  up_mm_yr: Stats;
  east_mm_yr: Stats;
  sigma_up_median: number;
  sigma_east_median: number;
  horizontal_share: number;
  vertical_only_bias: Record<string, { median_mm_yr: number; p90_abs_mm_yr: number }>;
  ramps?: { id: string; mm_yr_per_km: [number, number]; span_mm_yr: number; removed: boolean }[];
  params: { cell_m: number; horizontal_mm_yr: number };
  warnings: string[];
  created: string;
}

export interface GeologySummary {
  source: "raster" | "boreholes" | "open";
  source_label: string;
  boreholes: number | null;
  cells: number;
  covered: number;
  thickness_m: { min: number; median: number; max: number } | null;
  spearman_rho: number | null;
  sinking_cells: number;
  by_class: { from_m: number; to_m: number; cells: number; median_rate_mm_yr: number | null; moving_share: number | null }[];
  consolidation_cv: { cells?: number; median_m2_yr?: number; p10_m2_yr?: number; p90_m2_yr?: number; within_range_share?: number; range_m2_yr?: [number, number] };
  params: { moving_mm_yr: number; drainage: string };
  warnings: string[];
  created: string;
}

export type AnalysisKind = "behaviour" | "risk" | "lines" | "consolidation" | "decompose" | "geology";

export interface BehaviourStatus {
  behaviour: AnalysisStatus<BehaviourSummary>;
  risk: AnalysisStatus<RiskSummary>;
  lines: AnalysisStatus<LinesSummary>;
  consolidation: AnalysisStatus<ConsolidationSummary>;
  decompose: AnalysisStatus<DecomposeSummary>;
  geology: AnalysisStatus<GeologySummary>;
  buildings: boolean;
}

export interface LineProfile {
  line: number;
  kind: string;
  name: string;
  length_m: number;
  covered_share: number;
  beta_max: number | null;
  loss_mm: number | null;
  chainage_m: number[];
  v_vert_mm_yr: (number | null)[];
  n_points: number[];
  beta: (number | null)[];
  horizon_yr: number;
}

export interface ConsolidationCell {
  cell: number;
  consolidating: boolean;
  dates: string[];
  settlement_mm: (number | null)[];
  tau_yr: number | null;
  settled_mm: number | null;
  final_mm: number | null;
  remaining_mm: number | null;
  t90_from_now_yr: number | null;
  delta_bic: number | null;
  curve_t_yr?: number[];
  curve_mm?: number[];
  asaoka: { prev: number[]; next: number[]; b0: number | null; b1: number | null; final: number | null; step_days?: number };
}

export interface BehaviourCell {
  cell: number;
  class: string;
  change_date: string | null;
  rate_mm_yr: number | null;
  rate_before_mm_yr: number | null;
  rate_after_mm_yr: number | null;
  acc_mm_yr2: number | null;
  seasonal_amp_mm: number | null;
  jump_mm: number | null;
  delta_bic: number | null;
  fit_mm: (number | null)[];
  dates: string[];
}

export interface RiskBuilding {
  id: string;
  lon: number;
  lat: number;
  area_m2: number;
  height_m: number | null;
  floors: number;
  height_known: boolean;
  source: "building" | "cell" | "none";
  points: number;
  v_vert_mm_yr: number | null;
  beta_10yr: number | null;
  hazard: number;
  exposure: number;
  vulnerability: number;
  consequence: number;
  risk: number;
}

export interface LearnParams {
  first: string;
  second: string;
  row0: number;
  col0: number;
  rows: number;
  cols: number;
  looks_az: number;
  looks_rg: number;
  coh_win?: number;
  coh_thr?: number;
  alpha?: number;
  fft?: number;
  passes?: number;
  linked?: boolean;
  ref_row?: number;
  ref_col?: number;
  exercise?: boolean;
}

export interface LearnStack {
  stack_id: string;
  error?: string;
  sensor: string;
  track: string;
  pass_direction?: string;
  look_side?: string;
  wavelength_m: number;
  reference_date: string;
  dates: string[];
  bperp_m: number[];
  shape: [number, number];
  spacing_m: { azimuth: number; range_slant: number; range_ground: number };
  incidence_deg: number;
  heading_deg?: number;
  linked: boolean;
  default: LearnParams;
  coreg_residual?: number[][];
  esd_shift?: number[];
}

export interface LearnPairMeta {
  params: Required<LearnParams>;
  shape: [number, number];
  layers: string[];
  variable: string;
  spacing_m: { azimuth: number; range_ground: number };
  wavelength_m: number;
  days: number;
  bperp_m: number;
  height_of_ambiguity_m: number | null;
  kh_rad_per_m: number;
  incidence_deg: number;
  flat_fringes_per_km_range: number;
  fringes_per_km: { raw: number; after_flat: number; diff: number };
  dem_range_m: [number, number];
  topo_range_rad: number;
  coherence_median: number;
  kept_share: number;
  residues: { diff: number; filt: number };
  unwrap: { method: string; pcg_rms: number; reference: { kind: string; row?: number; col?: number } };
  mm_per_fringe: number;
  bounds: [number, number, number, number];
  stats: Record<string, [number, number, number, number]>;
}

export interface LearnPoints {
  product: string | null;
  uids: string[];
  rows: number[];
  cols: number[];
  vel: number[];
  vel_range: [number, number] | null;
}

export interface LearnSeries {
  uid: string;
  dates: string[];
  disp_mm: number[];
  fit_mm: number[];
  vel_mm_yr: number;
  vel_product_mm_yr: number | null;
  vel_std_mm_yr: number | null;
}

export interface LearnIonoDate {
  date: string;
  local_hour: number | null;
  esd_lines: number;
  iono_mm_per_km: [number, number] | null;
  iono_se_mm_per_km: [number, number] | null;
  iono_cells: number | null;
  seam_rad: Record<string, number> | null;
  seam_consistency: Record<string, number> | null;
  anchor: string | null;
}

export interface LearnIonosphere {
  stack_id: string;
  track: string;
  pass_direction?: string;
  reference_date: string;
  lon: number;
  lat: number;
  wavelength_m: number;
  mm_per_rad: number;
  ionosphere: string;
  ionosphere_model: string | null;
  ionosphere_smooth_m: number | null;
  subswath: string | null;
  seams: { col: number; subswath: string }[];
  shape: [number, number];
  size_km: [number, number];
  has_field: boolean;
  dates: LearnIonoDate[];
}

export interface LearnIonoField {
  date: string;
  shape: [number, number];
  mm: number[];
}

export interface GroundwaterSummary {
  used: boolean;
  reason?: string;
  source?: string;
  res_deg?: number;
  months?: string[];
  cells_tested?: number;
  cells_significant?: number;
  lag_months_median?: number | null;
  share_negative_k?: number | null;
  trend_mm_yr?: number | null;
  pixels?: { lon: number; lat: number; cells: number; mean_mm: number; missing: number; trend_mm_yr: number | null; assessed: boolean }[];
}

export interface ModelScores {
  auc: number | null;
  ap: number | null;
  brier: number | null;
}

export interface SusceptibilitySummary {
  product_id: string;
  created: string;
  params: { label_rate: number; mode: string; block_m: number; folds: number; exclude: string[] };
  grid: { cells: number; cell_m: number; lat0: number; bounds: number[] };
  labels: { cells: number; moving: number; share: number; reference: { kind: string } | null };
  predictors: string[];
  layers: Record<string, { group: string; label: string; unit: string }>;
  models: Record<string, { spatial_cv: ModelScores; random_cv: ModelScores; importance: Record<string, number> }>;
  chosen: string;
  odds_ratio_per_sd: Record<string, number>;
  classes: number[];
  outside_share: number;
  warnings: string[];
  sources: string[];
}

export interface ForecastSummary {
  product_id: string;
  created: string;
  params: { cell_m: number; horizons_days: number[]; n_origins: number };
  dates: string[];
  last_date: string;
  n_cells: number;
  horizons_days: number[];
  chosen: string;
  rain: boolean;
  groundwater?: boolean;
  backtest: {
    cuts_days: number[];
    mae_mm: Record<string, Record<string, number | null>>;
    skill: Record<string, Record<string, number | null>>;
    coverage: Record<string, Record<string, number | null>>;
    interval_mm: Record<string, Record<string, number | null>>;
  };
}

export interface AiTaskStatus<S> {
  summary: S | null;
  running: boolean;
  failed: boolean;
  log: string[];
}

export interface AiStatus {
  susceptibility: AiTaskStatus<SusceptibilitySummary>;
  forecast: AiTaskStatus<ForecastSummary>;
  hazard: boolean;
}

export interface GridMeta {
  origin: [number, number];
  fields: string[];
  n: number;
  cell_m: number;
  lat0: number;
  stats?: Record<string, { min: number | null; max: number | null; p02: number | null; p98: number | null }>;
  horizons?: number[];
}

export interface ForecastCell {
  cell: number;
  dates: string[];
  series_mm: (number | null)[];
  forecast: { date: string; horizon_days: number; change_mm: number | null; lo80: number | null; hi80: number | null; lo95: number | null; hi95: number | null }[];
  chosen: string;
  last_date: string;
}

export interface HazardStatus {
  summary: HazardSummary | null;
  running: boolean;
  failed: boolean;
  log: string[];
}

export interface HazardCellsMeta {
  origin: [number, number];
  fields: string[];
  n: number;
  cell_m: number;
  lat0: number;
}

export interface HazardCell {
  cell: number;
  lon: number;
  lat: number;
  n_points: number;
  mode: "subsidence" | "landslide";
  slope_deg: number | null;
  sensitivity: number | null;
  rate_mm_yr: number | null;
  rate_se_mm_yr: number | null;
  stable_mm_yr: number | null;
  acc_mm_yr2: number | null;
  accelerating: boolean;
  opposite_motion: boolean;
  rain_lag_months: number;
  rain_r: number | null;
  rain_p: number | null;
  rain_q: number | null;
  rain_k_mm_per_100mm: number | null;
  rain_k_se: number | null;
  rain_coupled: boolean;
  trend_rain_corrected_mm_yr: number | null;
  rate_dry_year_mm_yr: number | null;
  rate_wet_year_mm_yr: number | null;
  intensity_observed: number;
  intensity: number;
  angular_distortion: number | null;
  susceptibility: number | null;
  secondary: number;
  hazard: number;
  dates: string[];
  series_mm: (number | null)[];
  linear_mm?: (number | null)[];
  rain_model_mm?: (number | null)[];
  crd_lagged_mm?: (number | null)[];
  rain: { months: string[]; mm: (number | null)[]; crd_mm: (number | null)[]; source: string; pixel: HazardSummary["rain"]["pixels"][number] | null };
  gw_lag_months?: number;
  gw_r?: number | null;
  gw_p?: number | null;
  gw_q?: number | null;
  gw_k_mm_per_100mm?: number | null;
  gw_k_se?: number | null;
  gw_coupled?: boolean;
  gw_model_mm?: (number | null)[];
  groundwater?: { months: string[]; anomaly_mm: (number | null)[]; source: string; pixel: NonNullable<GroundwaterSummary["pixels"]>[number] | null };
}

export interface GnssStats {
  n_epochs: number;
  rate_insar_mm_yr: number;
  rate_insar_se: number;
  rate_gnss_mm_yr: number;
  rate_gnss_se: number;
  rate_diff_mm_yr: number;
  rate_diff_midas_mm_yr?: number;
  rmse_mm: number;
  rmse_detrended_mm: number;
  corr: number | null;
}

export interface GnssStation {
  site: string;
  lon: number;
  lat: number;
  first: string;
  last: string;
  used: boolean;
  reason?: string;
  segments?: number;
  jumps?: string[];
  outliers?: number;
  notes?: string[];
  n_points?: number;
  n_epochs?: number;
  median_distance_m?: number;
  los?: number[];
  gnss_rate_enu_mm_yr?: number[];
  vertical?: GnssStats;
  full?: GnssStats;
  midas?: { years: number; enu_mm_yr: number[]; sigma_mm_yr: number[]; los_full_mm_yr: number; los_vertical_mm_yr: number; note?: string } | null;
}

export interface GnssCalibration {
  kind: "offset" | "plane" | "epoch";
  los_mode: "vertical" | "full";
  gnss_rate: "window" | "midas";
  stations: string[];
  rate_coef: number[];
  rate_offset_mm_yr: number;
  leave_one_out?: { site: string; rate_diff_before_mm_yr: number; rate_diff_after_mm_yr: number }[];
  loo_rms_before_mm_yr?: number;
  loo_rms_after_mm_yr?: number;
}

export interface GnssSummary {
  product_id: string;
  created: string;
  params: { radius_m: number; los_mode: string; calibration: string; gnss_rate: string; window_days: number; min_points: number };
  source: string;
  frame: string;
  dates: string[];
  stations: GnssStation[];
  calibration: GnssCalibration | null;
  warnings: string[];
}

export interface GnssStatus {
  summary: GnssSummary | null;
  running: boolean;
  failed: boolean;
  log: string[];
}

export interface GnssSeries {
  site: string;
  dates: string[];
  day: string[];
  spread_mm: (number | null)[];
  insar_vertical_mm: (number | null)[];
  insar_full_mm: (number | null)[];
  vertical: { gnss_mm: (number | null)[]; daily_mm: (number | null)[] };
  full: { gnss_mm: (number | null)[]; daily_mm: (number | null)[] };
}

export interface Workspace {
  root: string;
  tree: FolderTree;
  projects: Record<string, ProjectSummary>;
}

export interface ProjectDetail extends ProjectSummary {
  config_toml: string;
  settings: { key: string; value: string; own: boolean }[];
  runs: RunRecord[];
  products: ProductBrief[];
  exports: Record<string, string[]>;
  web_run_log: string[];
}

export interface PlanStep {
  track: string;
  phase: string;
  action: "run" | "up-to-date" | "disabled" | "blocked";
  reason: string;
}

export interface LogLine {
  ts: string;
  level: string;
  phase?: string | null;
  track?: string | null;
  msg: string;
  event?: string | null;
}

export interface VelClass {
  lo: number;
  hi: number;
  color: [number, number, number];
  count: number;
}

export interface LayerMeta {
  tiles: { available: boolean; recommended: boolean; min_zoom?: number; max_zoom?: number };
  product_id: string;
  n: number;
  origin: [number, number];
  marker_m: number;
  heading_deg?: number | null;
  look_azimuth_deg?: number | null;
  bounds: [number, number, number, number];
  dates: string[];
  vel_min: number;
  vel_max: number;
  classes: VelClass[];
}

export interface PointInfo {
  index: number;
  lon: number;
  lat: number;
  vel: number;
  vel_std_mm_yr: number | null;
  temporal_coherence: number | null;
  height_m: number | null;
  acc_los_mm_yr2: number | null;
  seasonal_amp_mm: number | null;
  dem_err_m: number | null;
  disp_mm: (number | null)[];
  disp_scn_mm?: (number | null)[] | null;    // spatially correlated noise (residual atmosphere) removed
}

export interface AreaInfo {
  n: number;
  vel_mean?: number;
  vel_min?: number;
  vel_max?: number;
  mean_mm?: (number | null)[];
  std_mm?: (number | null)[];
  mean_scn_mm?: (number | null)[];
}

export interface ReportDate {
  date: string;
  bperp_m?: number | null;
  used?: boolean;
  reference?: boolean;
}

export interface ProductReport {
  id: string;
  brief: ProductBrief | null;
  files: string[];
  report: {
    acquisition?: { sensor: string; band: string; first: string; last: string; n_dates: number };
    dates?: ReportDate[];
    confidence?: { level: string; issues: string[]; notes: string[] };
    stats?: Record<string, unknown>;
    [k: string]: unknown;
  };
}

export interface FieldSpec {
  key: string;
  help: string;
  kind: "bool" | "int" | "number" | "string" | "enum" | "multi" | "daterange" | "pair" | "bbox" | "list";
  options?: string[];
  nullable: boolean;
  min?: number | null;
  max?: number | null;
  suggest?: string[] | null;
  value: unknown;
  default: unknown;
  own: boolean;
}

export interface SettingsSpec {
  sections: { name: string; title: string; fields: FieldSpec[] }[];
  toml: string;
  tracks: Record<string, unknown>[];
}

export interface AsfTrack {
  track_id: string;
  relative_orbit: number;
  direction: string;
  subswaths: string[];
  coverage: number | null;
  last: string;
}

export interface AsfPreview {
  acquisitions: number;
  bursts: number;
  gb: number;
  burst_ids: string[];
  dates: string[];
  months: Record<string, number>;
  platforms: string[];
}

export interface NewProject {
  name: string;
  folder?: string;
  description?: string;
  method: string;
  track: { sensor: string; direction: string; relative_orbit?: number | null; subswaths?: string[] };
  bbox?: number[] | null;
  date_range?: [string, string] | null;
  max_per_month?: number;
  archive?: string;
  atmosphere?: string;
}

export interface CompareMeta {
  cell_m: number;
  align: boolean;
  n_a: number;
  n_b: number;
  n: number;
  origin?: [number, number];
  offset?: number;
  classes?: VelClass[];
  vel_min?: number;
  vel_max?: number;
  bounds?: [number, number, number, number];
  stats?: { mean: number; median: number; std: number; rmse: number; p05: number; p95: number; corr: number | null };
}

export interface CrObservation {
  reflector: string;
  date: string;
  platform: string;
  expected_dbsm: number | null;
  measured_dbsm: number | null;
  difference_db: number | null;
  scr_db: number | null;
  within_tolerance: boolean;
  offset_m: number | null;
  setup_note?: string;
}

export interface CrReport {
  id: string;
  pdf: boolean;
  files: string[];
  report: {
    generated_at: string;
    tolerance_db: number;
    reflectors: { name: string; lat: number; lon: number }[];
    acquisitions: { date: string }[];
    observations: CrObservation[];
    coherence: { reflector: string; date_1: string; date_2: string; at_reflector: number; area_median: number }[];
    warnings: string[];
  };
}

export interface AlertRule {
  name: string;
  kind: "velocity_below" | "velocity_above";
  threshold: number;
  min_points: number;
  bbox?: number[];
}

export interface AlertResult extends AlertRule {
  track: string;
  product: string;
  n: number;
  of: number;
  triggered: boolean;
  worst?: number;
  lon?: number;
  lat?: number;
}

export interface Schedule {
  supported: boolean;
  enabled?: boolean;
  next_run?: string;
  last_run?: string;
  last_result?: string;
  schedule?: string;
  time?: string;
  days?: string;
  status?: string;
}

export interface Monitoring {
  next: {
    track: string;
    last: Record<string, string>;
    next: { date: string; platform: string; status: "planned" | "not planned" | "predicted"; time?: string; mode?: string; polarisation?: string }[];
    plan_until: Record<string, string>;
    note: string;
  }[];
  schedule: Schedule;
  rules: AlertRule[];
  alerts: AlertResult[];
}

export interface CatalogProduct {
  id: string;
  project: string;
  track: string;
  sensor: string;
  first_date: string;
  last_date: string;
  n_points: number;
  confidence: string | null;
  latest: boolean;
  in_area?: { n: number; vel_min: number; vel_max: number; vel_median: number; n_below?: number };
}

export class AuthError extends Error {}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (r.status === 401 && !url.endsWith("/api/login")) {
    window.dispatchEvent(new Event("geoeyes:login"));
    throw new AuthError("login required");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const P = (name: string) => `/api/projects/${encodeURIComponent(name)}`;

export const api = {
  workspace: () => request<Workspace>("/api/workspace"),
  saveFolders: (tree: FolderTree) =>
    request<FolderTree>("/api/folders", { ...json(tree), method: "PUT" }),
  project: (name: string) => request<ProjectDetail>(P(name)),
  plan: (name: string, force: string[] = []) =>
    request<{ steps: PlanStep[] }>(`${P(name)}/plan?force=${force.join(",")}`),
  run: (name: string, body: { tracks?: string[]; force?: string[]; only?: string } = {}) =>
    request<{ pid: number }>(`${P(name)}/run`, json(body)),
  stop: (name: string) => request<{ stopped: boolean }>(`${P(name)}/stop`, json({})),
  log: (name: string, run: string, after: number) =>
    request<{ lines: LogLine[]; next: number }>(`${P(name)}/runs/${run}/log?after=${after}`),
  product: (name: string, pid: string) => request<ProductReport>(`${P(name)}/products/${pid}`),
  layer: (name: string, pid: string) => request<LayerMeta>(`${P(name)}/products/${pid}/layer`),
  layerPoints: async (name: string, pid: string) => {
    const r = await fetch(`${P(name)}/products/${pid}/layer/points.bin`);
    if (!r.ok) throw new Error(`points: ${r.statusText}`);
    return new Float32Array(await r.arrayBuffer());
  },
  buildTiles: (name: string, pid: string) =>
    request<{ available: boolean; min_zoom: number; max_zoom: number }>(`${P(name)}/products/${pid}/tiles`, json({})),
  tileUrl: (name: string, pid: string) => `${P(name)}/products/${pid}/tiles/{z}/{x}/{y}.pbf`,
  pmtilesUrl: (name: string, pid: string) => `${P(name)}/products/${pid}/tiles.pmtiles`,
  point: (name: string, pid: string, i: number) =>
    request<PointInfo>(`${P(name)}/products/${pid}/layer/points/${i}`),
  area: (name: string, pid: string, ring: [number, number][]) =>
    request<AreaInfo>(`${P(name)}/products/${pid}/layer/area`, json({ ring })),
  fileUrl: (name: string, pid: string, rel: string) => `${P(name)}/products/${pid}/files/${rel}`,
  exportUrl: (name: string, pid: string, file: string) => `${P(name)}/exports/${pid}/${file}`,

  health: () => request<{ ok: boolean; version: string; auth_required: boolean; authenticated: boolean }>("/api/health"),
  login: (token: string) => request<{ ok: boolean }>("/api/login", json({ token })),

  settings: (name: string) => request<SettingsSpec>(`${P(name)}/settings`),
  patchSettings: (name: string, changes: Record<string, unknown>) =>
    request<SettingsSpec>(`${P(name)}/settings`, { ...json(changes), method: "PATCH" }),
  putToml: (name: string, toml: string) => request<SettingsSpec>(`${P(name)}/config`, { ...json({ toml }), method: "PUT" }),
  createProject: (spec: NewProject) => request<{ name: string }>("/api/projects", json(spec)),
  trashProjects: (names: string[]) =>
    request<{ trashed: { name: string; trash: string }[]; tree: FolderTree }>("/api/projects/trash", json({ names })),
  asfTracks: (bbox: number[]) => request<{ tracks: AsfTrack[] }>("/api/asf/tracks", json({ bbox })),
  asfPreview: (spec: { bbox: number[]; direction: string; relative_orbit: number; date_range: [string, string]; max_per_month: number; subswaths?: string[] }) =>
    request<AsfPreview>("/api/asf/preview", json(spec)),

  compare: (a: string, b: string, cell: number, align: boolean) =>
    request<CompareMeta>(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&cell=${cell}&align=${align}`),
  compareBin: async (a: string, b: string, cell: number, align: boolean) => {
    const r = await fetch(`/api/compare.bin?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&cell=${cell}&align=${align}`);
    if (!r.ok) throw new Error(`compare: ${r.statusText}`);
    return new Float32Array(await r.arrayBuffer());
  },

  catalogSearch: (bbox: number[], opts: { all?: boolean; vel_below?: number } = {}) =>
    request<{ products: CatalogProduct[] }>(
      `/api/catalog/search?bbox=${bbox.map((v) => v.toFixed(5)).join(",")}${opts.all ? "&all=true" : ""}${
        opts.vel_below != null ? `&vel_below=${opts.vel_below}` : ""
      }`,
    ),
  activity: () =>
    request<{ jobs: { project: string; kind: "hazard" | "gnss" | "susceptibility" | "forecast"; product: string; started: string; finished: string | null; state: "running" | "done" | "failed" }[] }>(
      "/api/activity",
    ),
  rainfall: (name: string, pid: string) =>
    request<{ source: string; months: { month: string; mm: number | null }[] }>(`${P(name)}/products/${pid}/rainfall`),
  gnss: (name: string, pid: string) => request<GnssStatus>(`${P(name)}/products/${pid}/gnss`),
  gnssRun: (name: string, pid: string, params: Record<string, unknown>) =>
    request<{ pid: number; already?: boolean }>(`${P(name)}/products/${pid}/gnss`, json({ params })),
  gnssStation: (name: string, pid: string, site: string) => request<GnssSeries>(`${P(name)}/products/${pid}/gnss/stations/${site}`),
  ai: (name: string, pid: string) => request<AiStatus>(`${P(name)}/products/${pid}/ai`),
  aiRun: (name: string, pid: string, task: "susceptibility" | "forecast", params: Record<string, unknown>) =>
    request<{ pid: number; already?: boolean }>(`${P(name)}/products/${pid}/ai/${task}`, json({ params })),
  aiGrid: async (name: string, pid: string, which: "susceptibility/grid" | "forecast/cells") => {
    const meta = await request<GridMeta>(`${P(name)}/products/${pid}/ai/${which}`);
    const r = await fetch(`${P(name)}/products/${pid}/ai/${which}.bin`);
    if (!r.ok) throw new Error(`ai grid: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  aiForecastCell: (name: string, pid: string, i: number) => request<ForecastCell>(`${P(name)}/products/${pid}/ai/forecast/cells/${i}`),
  hazard: (name: string, pid: string) => request<HazardStatus>(`${P(name)}/products/${pid}/hazard`),
  hazardRun: (name: string, pid: string, params: Record<string, unknown>) =>
    request<{ pid: number; already?: boolean }>(`${P(name)}/products/${pid}/hazard`, json({ params })),
  hazardCells: async (name: string, pid: string) => {
    const meta = await request<HazardCellsMeta>(`${P(name)}/products/${pid}/hazard/cells`);
    const r = await fetch(`${P(name)}/products/${pid}/hazard/cells.bin`);
    if (!r.ok) throw new Error(`hazard cells: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  learnStacks: (name: string) => request<{ stacks: LearnStack[] }>(`${P(name)}/learn`),
  learnThumb: async (name: string, stack: string) => {
    const meta = await request<{ shape: [number, number]; factor: number; date: string }>(`${P(name)}/learn/${stack}/thumb`);
    const r = await fetch(`${P(name)}/learn/${stack}/thumb.bin`);
    if (!r.ok) throw new Error(`thumbnail: ${r.statusText}`);
    return { meta, data: new Float32Array(await r.arrayBuffer()) };
  },
  learnPair: async (name: string, stack: string, p: LearnParams) => {
    const q = new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)])).toString();
    const meta = await request<LearnPairMeta>(`${P(name)}/learn/${stack}/pair?${q}`);
    const r = await fetch(`${P(name)}/learn/${stack}/pair.bin?${q}`);
    if (!r.ok) throw new Error(`pair: ${r.statusText}`);
    const buf = new Float32Array(await r.arrayBuffer());
    const n = meta.shape[0] * meta.shape[1];
    const layers: Record<string, Float32Array> = {};
    meta.layers.forEach((k, i) => (layers[k] = buf.subarray(i * n, (i + 1) * n)));
    return { meta, layers };
  },
  learnPoints: (name: string, stack: string, p: LearnParams) =>
    request<LearnPoints>(`${P(name)}/learn/${stack}/points?${new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)])).toString()}`),
  learnSeries: (name: string, pid: string, uid: string) =>
    request<LearnSeries>(`${P(name)}/learn/series/${encodeURIComponent(pid)}/${encodeURIComponent(uid)}`),
  learnIonosphere: (name: string, stack: string) => request<LearnIonosphere>(`${P(name)}/learn/${stack}/ionosphere`),
  learnIonoField: (name: string, stack: string, date: string) =>
    request<LearnIonoField>(`${P(name)}/learn/${stack}/ionosphere?date=${encodeURIComponent(date)}`),
  behaviour: (name: string, pid: string) => request<BehaviourStatus>(`${P(name)}/products/${pid}/behaviour`),
  analysisRun: (name: string, pid: string, kind: AnalysisKind) =>
    request<{ pid: number }>(`${P(name)}/products/${pid}/analysis/${kind}`, json({ params: {} })),
  behaviourCells: async (name: string, pid: string) => {
    const meta = await request<{ n: number; classes: string[]; first_date: string; last_date: string; hazard_created?: string }>(`${P(name)}/products/${pid}/behaviour/cells`);
    const r = await fetch(`${P(name)}/products/${pid}/behaviour/cells.bin`);
    if (!r.ok) throw new Error(`behaviour: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  behaviourCell: (name: string, pid: string, i: number) => request<BehaviourCell>(`${P(name)}/products/${pid}/behaviour/cells/${i}`),
  riskBuildings: async (name: string, pid: string) => {
    const meta = await request<{ origin: [number, number]; n: number; record: number; sources: string[]; warnings: string[] }>(`${P(name)}/products/${pid}/risk/buildings`);
    const r = await fetch(`${P(name)}/products/${pid}/risk/buildings.bin`);
    if (!r.ok) throw new Error(`risk: ${r.statusText}`);
    return { meta, view: new DataView(await r.arrayBuffer()) };
  },
  lineSegments: async (name: string, pid: string) => {
    const meta = await request<{ n: number; kinds: Record<string, string> }>(`${P(name)}/products/${pid}/lines/segments`);
    const r = await fetch(`${P(name)}/products/${pid}/lines/segments.bin`);
    if (!r.ok) throw new Error(`lines: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  lineProfile: (name: string, pid: string, line: number) => request<LineProfile>(`${P(name)}/products/${pid}/lines/${line}`),
  consolidationCells: async (name: string, pid: string) => {
    const meta = await request<{ n: number; summary: ConsolidationSummary }>(`${P(name)}/products/${pid}/consolidation/cells`);
    const r = await fetch(`${P(name)}/products/${pid}/consolidation/cells.bin`);
    if (!r.ok) throw new Error(`consolidation: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  decomposeCells: async (name: string, pid: string) => {
    const meta = await request<{ n: number; fields: string[]; dlon: number; dlat: number; summary: DecomposeSummary }>(`${P(name)}/products/${pid}/decompose/cells`);
    const r = await fetch(`${P(name)}/products/${pid}/decompose/cells.bin`);
    if (!r.ok) throw new Error(`decompose: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  geologyCells: async (name: string, pid: string) => {
    const meta = await request<{ n: number; summary: GeologySummary }>(`${P(name)}/products/${pid}/geology/cells`);
    const r = await fetch(`${P(name)}/products/${pid}/geology/cells.bin`);
    if (!r.ok) throw new Error(`geology: ${r.statusText}`);
    return { meta, buf: new Float32Array(await r.arrayBuffer()) };
  },
  consolidationCell: (name: string, pid: string, i: number) => request<ConsolidationCell>(`${P(name)}/products/${pid}/consolidation/cells/${i}`),
  riskBuilding: (name: string, pid: string, i: number) => request<RiskBuilding>(`${P(name)}/products/${pid}/risk/buildings/${i}`),
  hazardCell: (name: string, pid: string, i: number) => request<HazardCell>(`${P(name)}/products/${pid}/hazard/cells/${i}`),
  hazardFile: (name: string, pid: string, file: string) => `${P(name)}/products/${pid}/hazard/files/${file}`,
  monitor: (name: string) => request<Monitoring>(`${P(name)}/monitor`),
  setSchedule: (name: string, body: { frequency: string; time: string; day: string }) =>
    request<Schedule>(`${P(name)}/schedule`, { ...json(body), method: "PUT" }),
  setAlerts: (name: string, rules: AlertRule[]) =>
    request<{ rules: AlertRule[]; alerts: AlertResult[] }>(`${P(name)}/alerts`, { ...json({ rules }), method: "PUT" }),
  validation: (name: string) =>
    request<{ configured: boolean; config: Record<string, unknown>; reports: CrReport[]; log: string[] }>(`${P(name)}/validation`),
  crReport: (name: string) => request<{ pid: number }>(`${P(name)}/cr-report`, json({})),
  validationFile: (name: string, rid: string, file: string) => `${P(name)}/validation/${rid}/${file}`,
};
