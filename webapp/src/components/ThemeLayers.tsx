// Thematic layers on the results map: the outputs of a product's analyses drawn over its points, with their own
// legend in the product's card and, on a click, the same detail panel as on the analysis page.
//   cells (100 m) of the hazard zoning: hazard level, kind of motion (behaviour), remaining settlement (consolidation)
//   grids of the machine-learning page: susceptibility class, forecast change
//   buildings at risk (points), dykes / railways / main roads by differential settlement (segments)
// The colours are those of the analysis pages (Hazard: cellColor, Machine learning: the diverging change scale), so a
// cell reads the same everywhere.
import { LineLayer, ScatterplotLayer, SolidPolygonLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type GridMeta, type HazardCellsMeta, type HazardSummary } from "../api";
import type { LegendSpec } from "../legend";
import { t } from "../i18n";
import { DIVERGING, ForecastChart, ramp } from "../pages/Ai";
import {
  BEH_CLASSES,
  BEH_LABELS,
  BEH_RGB,
  CellPanel,
  cellColor,
  CONS_RGB,
  LEVEL_RGB,
  LEVELS,
  LINE_RGB,
  LAG_RGB,
  hazardLegendSpec,
  SpecLegend,
  LinePanel,
  bin,
  EAST_RGB,
  MOTION_BREAKS,
  NA_RGB,
  RATE_RGB,
  RiskPanel,
  SOIL_RGB,
  VIEWS,
  type Behaviour,
  type Cells,
  type Consolidation,
  type Geology,
  type View,
} from "../pages/Hazard";
import { fmt } from "../ui";

export type ThemeKind = "hazard" | "behaviour" | "consolidation" | "geology" | "decompose" | "susceptibility" | "forecast" | "risk" | "lines";
export const THEME_KINDS: ThemeKind[] = ["hazard", "behaviour", "consolidation", "geology", "decompose", "susceptibility", "forecast", "risk", "lines"];
export const THEME_LABEL: Record<ThemeKind, string> = {
  hazard: "Hazard zoning",
  behaviour: "Kind of motion",
  consolidation: "Remaining settlement",
  geology: "Soft-soil thickness",
  decompose: "Vertical and east-west motion",
  susceptibility: "Susceptibility",
  forecast: "Deformation forecast",
  risk: "Buildings at risk",
  lines: "Dykes and lines",
};

export interface Theme {
  key: string; // `${project}/${product}#${kind}`
  project: string;
  product: string;
  kind: ThemeKind;
  visible: boolean;
  opacity: number;
  horizon?: number; // forecast: days
  view?: View; // hazard, behaviour, decompose: which view of the analysis
}

/** The views a layer can show (the first is its default), as on the Thematic analysis page. */
export const THEME_VIEWS: Partial<Record<ThemeKind, View[]>> = {
  hazard: ["hazard", "intensity", "secondary", "rate", "coupling", "lag", "groundwater", "mode"],
  behaviour: ["behaviour", "change"],
  decompose: ["up", "east"],
};
const viewOf = (th: Theme): View => (th.view && THEME_VIEWS[th.kind]?.includes(th.view) ? th.view : (THEME_VIEWS[th.kind]?.[0] ?? (th.kind as View)));

interface Grid {
  meta: GridMeta | HazardCellsMeta;
  buf: Float32Array;
  f: Record<string, number>;
  polys: { i: number; ring: number[][] }[];
}

export interface ThemeData {
  kind: ThemeKind;
  bounds: [number, number, number, number] | null;
  grid?: Grid; // cell kinds
  beh?: Behaviour & { first: string; last: string };
  cons?: Consolidation;
  geo?: Geology;
  horizons: number[];
  lim: Record<number, number>; // forecast: colour limit (P98 of |change|) per horizon
  points?: { n: number; pos: Float32Array; col: Uint8Array; rad: Float32Array; risk: Int8Array };
  segments?: { n: number; src: Float32Array; dst: Float32Array; col: Uint8Array; wid: Float32Array; line: Int32Array; kind: Int8Array };
}

export interface ThemeSel {
  key: string;
  i: number;
}

const STORE = "geoeyes.themes";

/** Switch a thematic layer on for the results map (from an analysis page, before showing the product there). */
export function addTheme(project: string, product: string, kind: ThemeKind, view?: View) {
  const key = `${project}/${product}#${kind}`;
  try {
    const ts: Theme[] = JSON.parse(localStorage.getItem(STORE) ?? "[]");
    const rest = Array.isArray(ts) ? ts.filter((x) => x.key !== key) : [];
    localStorage.setItem(STORE, JSON.stringify([...rest, { key, project, product, kind, visible: true, opacity: 0.75, view }]));
  } catch {
    /* storage unavailable: the product alone is shown */
  }
}

/** Make a map of a thematic layer: switched on, and the subject of the map export (its legend and title). */
export function composeTheme(project: string, product: string, kind: ThemeKind, view?: View) {
  addTheme(project, product, kind, view);
  try {
    sessionStorage.setItem(COMPOSE_SUBJECT, `${project}/${product}#${kind}`);
  } catch {
    /* storage unavailable: the subject is chosen on the page */
  }
}
export const COMPOSE_SUBJECT = "geoeyes.compose.subject";

/** The thematic layers on the map (kept by the browser, like the product layers). */
export function useThemes() {
  const [themes, setThemes] = useState<Theme[]>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(STORE) ?? "[]");
      return Array.isArray(v) ? v.filter((x) => THEME_KINDS.includes(x.kind)) : [];
    } catch {
      return [];
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(themes));
    } catch {
      /* storage unavailable */
    }
  }, [themes]);
  const toggle = (project: string, product: string, kind: ThemeKind) => {
    const key = `${project}/${product}#${kind}`;
    setThemes((ts) => (ts.some((x) => x.key === key) ? ts.filter((x) => x.key !== key) : [...ts, { key, project, product, kind, visible: true, opacity: 0.75 }]));
  };
  const update = (key: string, patch: Partial<Theme>) => setThemes((ts) => ts.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  const dropProduct = (project: string, product: string) => setThemes((ts) => ts.filter((x) => x.project !== project || x.product !== product));
  return { themes, toggle, update, dropProduct };
}

/** Which thematic layers a product has (its analyses that ran). */
export function useAvailable(project: string, product: string): ThemeKind[] {
  const hz = useQuery({ queryKey: ["avail-hazard", project, product], queryFn: () => api.hazard(project, product), staleTime: 60_000 });
  const ai = useQuery({ queryKey: ["avail-ai", project, product], queryFn: () => api.ai(project, product), staleTime: 60_000 });
  const an = useQuery({ queryKey: ["avail-analyses", project, product], queryFn: () => api.behaviour(project, product), staleTime: 60_000 });
  const has: Record<ThemeKind, boolean> = {
    hazard: !!hz.data?.summary,
    behaviour: !!hz.data?.summary && !!an.data?.behaviour.summary,
    consolidation: !!hz.data?.summary && !!an.data?.consolidation.summary,
    geology: !!hz.data?.summary && !!an.data?.geology.summary,
    decompose: !!an.data?.decompose.summary,
    susceptibility: !!ai.data?.susceptibility.summary,
    forecast: !!ai.data?.forecast.summary,
    risk: !!an.data?.risk.summary,
    lines: !!an.data?.lines.summary,
  };
  return THEME_KINDS.filter((k) => has[k]);
}

function grid(meta: GridMeta | HazardCellsMeta, buf: Float32Array): { g: Grid; bounds: [number, number, number, number] } {
  const F = meta.fields.length;
  const f = Object.fromEntries(meta.fields.map((n, i) => [n, i]));
  const latc = (meta as { lat0?: number }).lat0 ?? meta.origin[1]; // the forecast grid has no lat0
  const hx = (0.5 * meta.cell_m) / (111320 * Math.cos((latc * Math.PI) / 180));
  const hy = (0.5 * meta.cell_m) / 110540;
  const [lon0, lat0] = meta.origin;
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const polys = Array.from({ length: meta.n }, (_, i) => {
    const x = lon0 + buf[i * F + f.dlon];
    const y = lat0 + buf[i * F + f.dlat];
    w = Math.min(w, x - hx);
    e = Math.max(e, x + hx);
    s = Math.min(s, y - hy);
    n = Math.max(n, y + hy);
    return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
  });
  return { g: { meta, buf, f, polys }, bounds: [w, s, e, n] };
}

/** The data of a thematic layer, decoded and with its colour scales (once per load). */
export async function loadTheme(th: Theme): Promise<ThemeData> {
  const base: ThemeData = { kind: th.kind, bounds: null, horizons: [], lim: {} };
  const { project: p, product: id } = th;
  if (th.kind === "decompose") {
    const { meta, buf } = await api.decomposeCells(p, id);
    // absolute lon / lat per cell (no origin): a grid of its own
    const F = meta.fields.length;
    const f = Object.fromEntries(meta.fields.map((n, i) => [n, i]));
    const hx = meta.dlon / 2;
    const hy = meta.dlat / 2;
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    const polys = Array.from({ length: meta.n }, (_, i) => {
      const x = buf[i * F];
      const y = buf[i * F + 1];
      w = Math.min(w, x - hx);
      e = Math.max(e, x + hx);
      s = Math.min(s, y - hy);
      n = Math.max(n, y + hy);
      return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
    });
    const gm = { origin: [0, 0], fields: meta.fields, n: meta.n, cell_m: 0, lat0: 0 } as unknown as GridMeta;
    return { ...base, grid: { meta: gm, buf, f, polys }, bounds: meta.n ? [w, s, e, n] : null };
  }
  if (th.kind === "hazard" || th.kind === "behaviour" || th.kind === "consolidation" || th.kind === "geology") {
    const { meta, buf } = await api.hazardCells(p, id);
    const { g, bounds } = grid(meta, buf);
    const out: ThemeData = { ...base, grid: g, bounds };
    if (th.kind === "behaviour") {
      const b = await api.behaviourCells(p, id);
      out.beh = { buf: b.buf, span: (Date.parse(b.meta.last_date) - Date.parse(b.meta.first_date)) / 86400000, first: b.meta.first_date, last: b.meta.last_date };
    }
    if (th.kind === "consolidation") {
      const c = await api.consolidationCells(p, id);
      out.cons = { buf: c.buf, max: c.meta.summary.remaining_mm?.p90 ?? 1 };
    }
    if (th.kind === "geology") {
      const gl = await api.geologyCells(p, id);
      const tk = gl.meta.summary.thickness_m;
      out.geo = { buf: gl.buf, min: tk?.min ?? 0, max: tk?.max ?? 1 };
    }
    return out;
  }
  if (th.kind === "susceptibility" || th.kind === "forecast") {
    const { meta, buf } = await api.aiGrid(p, id, th.kind === "forecast" ? "forecast/cells" : "susceptibility/grid");
    const { g, bounds } = grid(meta, buf);
    const out: ThemeData = { ...base, grid: g, bounds };
    if (th.kind === "forecast") {
      out.horizons = (meta as GridMeta).horizons ?? meta.fields.filter((k) => /^c\d+$/.test(k)).map((k) => Number(k.slice(1)));
      const F = meta.fields.length;
      for (const h of out.horizons) {
        const vals: number[] = [];
        for (let i = 0; i < meta.n; i += 3) {
          const v = Math.abs(buf[i * F + g.f[`c${h}`]]);
          if (Number.isFinite(v)) vals.push(v);
        }
        vals.sort((a, b) => a - b);
        out.lim[h] = vals[Math.floor(vals.length * 0.98)] || 1;
      }
    }
    return out;
  }
  if (th.kind === "risk") {
    const { meta, view: dv } = await api.riskBuildings(p, id);
    const n = meta.n;
    const pos = new Float32Array(n * 2);
    const col = new Uint8Array(n * 4);
    const rad = new Float32Array(n);
    const risk = new Int8Array(n);
    let w = Infinity, s = Infinity, e = -Infinity, nn = -Infinity;
    for (let i = 0; i < n; i++) {
      const o = i * meta.record;
      const x = meta.origin[0] + dv.getFloat32(o, true);
      const y = meta.origin[1] + dv.getFloat32(o + 4, true);
      pos.set([x, y], i * 2);
      const r = dv.getUint8(o + 8) - 1;
      risk[i] = r;
      const c = r >= 0 ? LEVEL_RGB[r] : NA_RGB;
      col.set([c[0], c[1], c[2], r >= 0 ? 235 : 120], i * 4);
      rad[i] = dv.getUint8(o + 11) / 2;
      w = Math.min(w, x);
      e = Math.max(e, x);
      s = Math.min(s, y);
      nn = Math.max(nn, y);
    }
    return { ...base, points: { n, pos, col, rad, risk }, bounds: n ? [w, s, e, nn] : null };
  }
  const { meta, buf } = await api.lineSegments(p, id);
  const n = meta.n;
  const src = new Float32Array(n * 2);
  const dst = new Float32Array(n * 2);
  const col = new Uint8Array(n * 4);
  const wid = new Float32Array(n);
  const line = new Int32Array(n);
  const kind = new Int8Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * 6;
    src.set([buf[o], buf[o + 1]], i * 2);
    dst.set([buf[o + 2], buf[o + 3]], i * 2);
    const k = buf[o + 4];
    kind[i] = k;
    const c = k >= 0 ? LINE_RGB[k] : NA_RGB;
    col.set([c[0], c[1], c[2], k >= 0 ? 255 : 150], i * 4);
    wid[i] = k >= 1 ? 5 : k === 0 ? 3 : 2;
    line[i] = buf[o + 5];
  }
  return { ...base, segments: { n, src, dst, col, wid, line, kind }, bounds: null };
}

const horizonOf = (th: Theme, d: ThemeData) => th.horizon ?? d.horizons[d.horizons.length - 1];
const val = (g: Grid, i: number, name: string) => g.buf[i * g.meta.fields.length + g.f[name]];

function cellRgba(th: Theme, d: ThemeData, i: number): [number, number, number, number] {
  const g = d.grid!;
  const cells = { meta: g.meta, buf: g.buf, f: g.f } as Cells;
  switch (th.kind) {
    case "hazard":
      return cellColor(cells, i, viewOf(th));
    case "behaviour":
      return cellColor(cells, i, viewOf(th), d.beh);
    case "consolidation":
      return cellColor(cells, i, "consolidation", undefined, d.cons);
    case "geology":
      return cellColor(cells, i, "soft_soil", undefined, undefined, d.geo);
    case "decompose": {
      const v = val(g, i, viewOf(th));
      if (!Number.isFinite(v)) return [...NA_RGB, 45];
      // the classes of the rate: red sinking, blue rising; green east, purple west
      return [...(viewOf(th) === "up" ? RATE_RGB[bin(-v, MOTION_BREAKS)] : EAST_RGB[bin(v, MOTION_BREAKS)]), 225];
    }
    case "susceptibility": {
      const p = val(g, i, "probability");
      if (!Number.isFinite(p)) return [...NA_RGB, 40];
      return [...LEVEL_RGB[Math.min(4, Math.max(0, val(g, i, "class")))], val(g, i, "outside") > 0 ? 90 : 215];
    }
    default: {
      const h = horizonOf(th, d);
      const v = val(g, i, `c${h}`);
      if (!Number.isFinite(v)) return [...NA_RGB, 50];
      return [...ramp(DIVERGING, 0.5 + v / (2 * d.lim[h])), 220];
    }
  }
}

/** deck.gl layers of the visible thematic layers; `onPick(key, index)` on a click. */
export function themeLayers(themes: Theme[], data: Record<string, ThemeData | undefined>, sel: ThemeSel | null, onPick: (key: string, i: number) => void) {
  return themes
    .filter((th) => th.visible && data[th.key])
    .map((th) => {
      const d = data[th.key]!;
      const id = `theme-${th.key}-${th.horizon ?? ""}-${th.view ?? ""}`;
      const picked = sel?.key === th.key ? sel.i : -1;
      const common = {
        id,
        opacity: th.opacity,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 140] as [number, number, number, number],
        onClick: (info: { index: number }) => {
          if (info.index >= 0) onPick(th.key, info.index);
        },
      };
      if (d.points) {
        const p = d.points;
        return new ScatterplotLayer({
          ...common,
          data: { length: p.n, attributes: { getPosition: { value: p.pos, size: 2 }, getFillColor: { value: p.col, size: 4, normalized: true }, getRadius: { value: p.rad, size: 1 } } } as never,
          radiusUnits: "meters",
          radiusMinPixels: 1.5,
        });
      }
      if (d.segments) {
        const s = d.segments;
        return new LineLayer({
          ...common,
          data: { length: s.n, attributes: { getSourcePosition: { value: s.src, size: 2 }, getTargetPosition: { value: s.dst, size: 2 }, getColor: { value: s.col, size: 4, normalized: true }, getWidth: { value: s.wid, size: 1 } } } as never,
          widthUnits: "pixels",
        });
      }
      return new SolidPolygonLayer<{ i: number; ring: number[][] }>({
        ...common,
        data: d.grid!.polys,
        getPolygon: (q) => q.ring as never,
        getFillColor: (q) => (q.i === picked ? [255, 255, 255, 255] : cellRgba(th, d, q.i)),
        updateTriggers: { getFillColor: [picked] },
      });
    });
}

/** Tooltip of an object under the cursor (layer id `theme-<key>-...`). */
export function themeTooltip(themes: Theme[], data: Record<string, ThemeData | undefined>, layerId: string, i: number): string | null {
  const th = themes.find((x) => layerId.startsWith(`theme-${x.key}-`));
  const d = th && data[th.key];
  if (!th || !d || i < 0) return null;
  const tail = `\n${th.project} · ${t("click for details")}`;
  if (d.points) {
    const r = d.points.risk[i];
    return `${t("Building")}: ${r >= 0 ? t("{level} risk", { level: t(LEVELS[r]) }) : t("not assessed")}${tail}`;
  }
  if (d.segments) {
    const k = d.segments.kind[i];
    return `${t("Line")} #${d.segments.line[i]}: ${k >= 3 ? t("structural damage") : k === 2 ? t("cracking") : k === 1 ? t("beyond the safe limit") : t("within the safe limit")}${tail}`;
  }
  const g = d.grid!;
  switch (th.kind) {
    case "hazard": {
      const lv = val(g, i, "hazard");
      const r = val(g, i, "rate_mm_yr");
      return `${t("Hazard")}: ${lv >= 0 ? t(LEVELS[lv]) : t("not assessed")}${Number.isFinite(r) ? `\n${fmt.vel(r)} mm/yr` : ""}${tail}`;
    }
    case "behaviour": {
      const k = d.beh ? d.beh.buf[i * 2] : -1;
      return `${t("Kind of motion")}: ${k >= 0 ? t(BEH_LABELS[BEH_CLASSES[k]]) : t("not assessed")}${tail}`;
    }
    case "consolidation": {
      const r = d.cons ? d.cons.buf[i * 2] : NaN;
      return `${t("Remaining settlement")}: ${Number.isFinite(r) ? `${r.toFixed(0)} mm` : "–"}${tail}`;
    }
    case "geology": {
      const h = d.geo ? d.geo.buf[i * 2] : NaN;
      return `${t("Soft-soil thickness")}: ${Number.isFinite(h) ? `${h.toFixed(0)} m` : "–"}${tail}`;
    }
    case "decompose": {
      const up = val(g, i, "up");
      const east = val(g, i, "east");
      return `${t("up")} ${Number.isFinite(up) ? fmt.vel(up) : "–"} · ${t("east")} ${Number.isFinite(east) ? fmt.vel(east) : "–"} mm/yr\n${th.project}`;
    }
    case "susceptibility": {
      const p = val(g, i, "probability");
      return `${t("Susceptibility")}: ${Number.isFinite(p) ? `${t(LEVELS[Math.max(0, Math.min(4, val(g, i, "class")))])} · ${(100 * p).toFixed(0)} %` : "–"}\n${th.project}`;
    }
    default: {
      const h = horizonOf(th, d);
      const v = val(g, i, `c${h}`);
      return `${t("Forecast change in {h} days", { h })}: ${Number.isFinite(v) ? `${v > 0 ? "+" : ""}${v.toFixed(1)} mm` : "–"}${tail}`;
    }
  }
}

/** The title of a thematic layer as shown in legends: its kind, and its view when it has several. */
export function themeTitle(th: Theme): string {
  const v = THEME_VIEWS[th.kind] && viewOf(th) !== THEME_VIEWS[th.kind]![0] ? VIEWS.find((x) => x.id === viewOf(th))?.label : undefined;
  return v ? `${t(THEME_LABEL[th.kind])} · ${t(v)}` : t(THEME_LABEL[th.kind]);
}

/** The legend of a thematic layer as data (its card and the map export draw it); ``hz``: the zoning summary of its
 * product (the hazard layer's classes come from its parameters). */
export function themeLegendSpec(th: Theme, d: ThemeData, hz?: HazardSummary): LegendSpec {
  const title = themeTitle(th);
  const levels = [...LEVELS.keys()].reverse().map((k) => ({ rgb: LEVEL_RGB[k], label: t(LEVELS[k]) }));
  // class k of bin(x, MOTION_BREAKS): x <= B0, B0..B1, ..., x > B5; up is coloured by bin(-v), east by bin(v)
  const B = MOTION_BREAKS;
  const span = (k: number, sign: 1 | -1) => {
    const lo = k === 0 ? -Infinity : B[k - 1];
    const hi = k === B.length ? Infinity : B[k];
    const [a, b] = sign > 0 ? [lo, hi] : [-hi, -lo];
    return a === -Infinity ? `≤ ${b}` : b === Infinity ? `≥ ${a}` : `${a} … ${b}`;
  };
  switch (th.kind) {
    case "hazard": {
      const s = hz ? hazardLegendSpec(viewOf(th), hz) : null;
      return s ? { ...s, title } : { title, items: levels };
    }
    case "susceptibility":
    case "risk":
      return { title, items: levels };
    case "behaviour":
      return viewOf(th) === "change"
        ? { title, ramp: { stops: LAG_RGB, lo: d.beh?.first ?? "", hi: d.beh?.last ?? "", unit: t("date of the change") } }
        : { title, items: BEH_CLASSES.map((c, k) => ({ rgb: BEH_RGB[k], label: t(BEH_LABELS[c]) })) };
    case "geology":
      return { title, ramp: { stops: SOIL_RGB, lo: (d.geo?.min ?? 0).toFixed(0), hi: (d.geo?.max ?? 0).toFixed(0), unit: t("m of soft soil") } };
    case "decompose":
      return viewOf(th) === "up"
        ? { title, items: RATE_RGB.map((c, k) => ({ rgb: c, label: span(k, -1) })), notes: [t("mm/yr: + up, − down (sinking)")] }
        : { title, items: EAST_RGB.map((c, k) => ({ rgb: c, label: span(k, 1) })), notes: [t("mm/yr: + east, − west")] };
    case "consolidation":
      return { title, ramp: { stops: CONS_RGB, lo: "0", hi: (d.cons?.max ?? 0).toFixed(0), unit: t("mm still to settle") } };
    case "lines":
      return {
        title,
        items: [
          { rgb: LINE_RGB[3], label: `≥ 1/150 · ${t("structural damage")}` },
          { rgb: LINE_RGB[2], label: `1/300 – 1/150 · ${t("cracking")}` },
          { rgb: LINE_RGB[1], label: `1/500 – 1/300 · ${t("beyond the safe limit")}` },
          { rgb: LINE_RGB[0], label: "< 1/500" },
        ],
      };
    default: {
      const h = horizonOf(th, d);
      return { title, ramp: { stops: DIVERGING, lo: `−${d.lim[h].toFixed(0)}`, hi: `+${d.lim[h].toFixed(0)}`, unit: t("mm in {n} days", { n: h }) } };
    }
  }
}

function ThemeLegend({ th, d }: { th: Theme; d: ThemeData }) {
  const hz = useQuery({ queryKey: ["avail-hazard", th.project, th.product], queryFn: () => api.hazard(th.project, th.product), staleTime: 60_000, enabled: th.kind === "hazard" });
  return (
    <div className="text-[11.5px]">
      <SpecLegend spec={themeLegendSpec(th, d, hz.data?.summary ?? undefined)} />
    </div>
  );
}

/** Legend and controls of a thematic layer, inside its product's card. */
export function ThemeCard({ th, d, error, onToggle, onUpdate }: { th: Theme; d?: ThemeData; error?: string; onToggle: () => void; onUpdate: (p: Partial<Theme>) => void }) {
  const h = d && d.kind === "forecast" ? horizonOf(th, d) : undefined;
  return (
    <div className="mt-2 rounded-md border border-line bg-panel px-2 py-1.5 text-[11.5px]">
      <div className="flex items-center gap-2">
        <input type="checkbox" className="h-3.5 w-3.5 accent-accent" checked={th.visible} onChange={(e) => onUpdate({ visible: e.target.checked })} aria-label={t("Show {product}", { product: t(THEME_LABEL[th.kind]) })} />
        <span className="min-w-0 flex-1 truncate font-medium">{t(THEME_LABEL[th.kind])}</span>
        {THEME_VIEWS[th.kind] && (
          <select value={viewOf(th)} onChange={(e) => onUpdate({ view: e.target.value as View })} aria-label={t("View")} className="h-6 max-w-[120px] rounded border border-line-2 bg-sunken px-1 text-[11px] text-ink-2">
            {THEME_VIEWS[th.kind]!.map((v) => (
              <option key={v} value={v}>
                {t(VIEWS.find((x) => x.id === v)?.label ?? v)}
              </option>
            ))}
          </select>
        )}
        {d && d.kind === "forecast" && (
          <select value={h} onChange={(e) => onUpdate({ horizon: Number(e.target.value) })} aria-label={t("Horizon")} className="h-6 rounded border border-line-2 bg-sunken px-1 text-[11px] text-ink-2">
            {d.horizons.map((x) => (
              <option key={x} value={x}>
                {t("{n} days", { n: x })}
              </option>
            ))}
          </select>
        )}
        <input type="range" min={0.1} max={1} step={0.05} value={th.opacity} onChange={(e) => onUpdate({ opacity: Number(e.target.value) })} aria-label={t("Opacity")} className="w-16 accent-accent" />
        <button type="button" onClick={onToggle} title={t("Remove from the map")} className="text-faint hover:text-bad">
          ×
        </button>
      </div>
      {error && <div className="mt-1 text-bad">{error}</div>}
      {!d && !error && <div className="mt-1 text-accent-ink">{t("Loading…")}</div>}
      {d && <ThemeLegend th={th} d={d} />}
    </div>
  );
}

/** The detail of a clicked cell, building or line: the panel of the analysis page it comes from. */
export function ThemeDetail({ th, d, i, onClose }: { th: Theme; d: ThemeData; i: number; onClose: () => void }) {
  const { project: p, product: id, kind } = th;
  const cellKind = kind === "hazard" || kind === "behaviour" || kind === "consolidation" || kind === "geology";
  const line = d.segments ? d.segments.line[i] : -1;
  const q = useQuery({
    queryKey: ["theme-detail", th.key, i],
    queryFn: async () => {
      if (cellKind) {
        const [c, beh, cons] = await Promise.all([
          api.hazardCell(p, id, i),
          api.behaviourCell(p, id, i).catch(() => undefined),
          api.consolidationCell(p, id, i).catch(() => undefined),
        ]);
        return { c, beh, cons };
      }
      if (kind === "forecast") return { f: await api.aiForecastCell(p, id, i) };
      if (kind === "risk") return { b: await api.riskBuilding(p, id, i) };
      if (kind === "lines") return { l: await api.lineProfile(p, id, line) };
      return {};
    },
    enabled: kind !== "susceptibility" && kind !== "decompose",
  });
  const box = "rounded-xl border border-line-2 bg-panel/95 p-3 text-[12.5px] shadow-xl shadow-black/30 backdrop-blur";
  const head = (title: string) => (
    <div className="flex items-center gap-2">
      <span className="font-semibold">{title}</span>
      <span className="text-muted">· {th.project}</span>
      <button type="button" className="ml-auto text-faint hover:text-ink" onClick={onClose} aria-label={t("Close")}>
        ×
      </button>
    </div>
  );
  if (kind === "susceptibility" || kind === "decompose")
    return (
      <div className={box}>
        {head(t(THEME_LABEL[kind]))}
        <div className="mt-1 whitespace-pre-line text-ink-2">{themeTooltip([th], { [th.key]: d }, `theme-${th.key}-`, i)}</div>
      </div>
    );
  if (q.isLoading) return <div className={`${box} text-accent-ink`}>{t("Loading…")}</div>;
  if (q.error) return <div className={`${box} text-bad`}>{(q.error as Error).message}</div>;
  const r = (q.data ?? {}) as {
    c?: Parameters<typeof CellPanel>[0]["c"];
    beh?: Parameters<typeof CellPanel>[0]["beh"];
    cons?: Parameters<typeof CellPanel>[0]["cons"];
    f?: Parameters<typeof ForecastChart>[0]["c"];
    b?: Parameters<typeof RiskPanel>[0]["b"];
    l?: Parameters<typeof LinePanel>[0]["p"];
  };
  if (r.c) return <CellPanel c={r.c} beh={r.beh} cons={r.cons} onClose={onClose} />;
  if (r.b) return <RiskPanel b={r.b} onClose={onClose} />;
  if (r.l) return <LinePanel p={r.l} onClose={onClose} />;
  if (r.f)
    return (
      <div className={box}>
        {head(t("Deformation forecast"))}
        <ForecastChart c={r.f} />
      </div>
    );
  return null;
}
