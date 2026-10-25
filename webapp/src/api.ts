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
  rainfall: (name: string, pid: string) =>
    request<{ source: string; months: { month: string; mm: number | null }[] }>(`${P(name)}/products/${pid}/rainfall`),
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
