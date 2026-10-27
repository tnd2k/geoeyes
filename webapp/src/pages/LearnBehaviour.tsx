// Principles, chapter 3: the kind of motion of every cell (geoeyes behaviour) and the risk to buildings
// (geoeyes risk), one step per page as a wiki article, illustrated with a real zoning of the workspace.
// Method, thresholds and sources: docs/en/research/behaviour-and-risk.md.
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type HazardCell, type Workspace } from "../api";
import { ChapterNav } from "../components/LearnKit";
import { lang, t, ts } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { BEH_CLASSES, BEH_LABELS, BEH_RGB, CellChart, LEVEL_RGB, LEVELS, NA_RGB, rgb, type Behaviour, type Cells } from "./Hazard";
import { CellMap, Section } from "./LearnHazard";

// ------------------------------------------------------------------ figures
/** The seven kinds of motion as small multiples (sinking drawn downwards). */
function ShapesFigure() {
  const W = 150;
  const H = 90;
  const N = 60;
  const shape: Record<string, (x: number) => number> = {
    stable: (x) => 0.04 * Math.sin(x * 40),
    steady: (x) => -0.8 * x,
    seasonal: (x) => -0.5 * x + 0.22 * Math.sin(2 * Math.PI * 2 * x),
    speeding: (x) => -0.9 * x * x,
    slowing: (x) => -0.9 * (1 - (1 - x) * (1 - x)),
    onset: (x) => (x < 0.5 ? -0.05 * x : -0.025 - 1.6 * (x - 0.5)),
    step: (x) => -0.25 * x - (x >= 0.55 ? 0.45 : 0),
  };
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {BEH_CLASSES.map((c, i) => {
        const pts = Array.from({ length: N }, (_, k) => {
          const x = k / (N - 1);
          return `${k ? "L" : "M"}${(8 + x * (W - 16)).toFixed(1)},${(14 + (-shape[c](x) / 1.05) * (H - 24)).toFixed(1)}`;
        }).join("");
        return (
          <div key={c} className="rounded-lg border border-line bg-panel p-2">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
              <line x1={8} x2={W - 8} y1={14} y2={14} stroke="#22324d" strokeDasharray="3 3" />
              <path d={pts} fill="none" stroke={rgb(BEH_RGB[i])} strokeWidth="2.5" />
            </svg>
            <div className="mt-1 flex items-center gap-1.5 text-[12px] text-ink-2">
              <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: rgb(BEH_RGB[i]) }} />
              {t(BEH_LABELS[c])}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Horizontal bars: count per category. */
function Bars({ items }: { items: { label: string; n: number; color: string; note?: string }[] }) {
  const max = Math.max(1, ...items.map((i) => i.n));
  return (
    <div className="space-y-1">
      {items.map((i) => (
        <div key={i.label} className="grid grid-cols-[170px_minmax(0,1fr)_80px] items-center gap-2 text-[12.5px]">
          <span className="truncate text-ink-2" title={i.note}>
            {i.label}
          </span>
          <span className="h-3 rounded-sm" style={{ width: `${Math.max(0.5, (100 * i.n) / max)}%`, background: i.color }} />
          <span className="text-right font-mono text-muted">{fmt.int(i.n)}</span>
        </div>
      ))}
    </div>
  );
}

/** Changes of rate by month, the dates shared by many cells marked. */
function ChangesChart({ byMonth, shared }: { byMonth: Record<string, number>; shared: string[] }) {
  const months = Object.keys(byMonth).sort();
  if (!months.length) return <p className="text-[12.5px] text-muted">{t("No cell changes its rate in this period.")}</p>;
  const max = Math.max(...months.map((m) => byMonth[m]));
  const sharedMonths = new Set(shared.map((d) => d.slice(0, 7)));
  const W = 760;
  const H = 150;
  const bw = (W - 40) / months.length;
  return (
    <svg viewBox={`0 0 ${W} ${H + 24}`} className="w-full">
      <line x1={30} x2={W - 10} y1={H} y2={H} stroke="#22324d" />
      {months.map((m, i) => {
        const h = (byMonth[m] / max) * (H - 16);
        return (
          <g key={m}>
            <rect x={30 + i * bw + 1} y={H - h} width={Math.max(2, bw - 2)} height={h} fill={sharedMonths.has(m) ? "#f5b84b" : "#d633a8"} />
            {(months.length <= 14 || i % Math.ceil(months.length / 12) === 0) && (
              <text x={30 + (i + 0.5) * bw} y={H + 14} fill="#93a4bf" fontSize="10.5" textAnchor="middle">
                {m}
              </text>
            )}
          </g>
        );
      })}
      <text x={26} y={14} fill="#93a4bf" fontSize="11" textAnchor="end">
        {max}
      </text>
    </svg>
  );
}

/** A small matrix with row and column labels. */
function Grid({ title, rows, cols, cells, color }: { title: string; rows: string[]; cols: string[]; cells: number[][]; color: (v: number) => string }) {
  return (
    <figure className="m-0 w-fit rounded-xl border border-line bg-panel p-3">
      <div className="mb-1.5 text-[11px] font-semibold tracking-[1px] text-muted uppercase">{t(title)}</div>
      <div className="grid gap-[3px]" style={{ gridTemplateColumns: `auto repeat(${cols.length}, 34px)` }}>
        <span />
        {cols.map((c) => (
          <span key={c} className="text-center font-mono text-[11px] text-muted">
            {c}
          </span>
        ))}
        {rows.map((r, i) => (
          <div key={r} className="contents">
            <span className="pr-1 text-right text-[11px] text-muted">{r}</span>
            {cells[i].map((v, j) => (
              <span key={j} className="flex h-7 items-center justify-center rounded-[4px] font-mono text-[12px] font-semibold text-[#0b1220]" style={{ background: color(v) }}>
                {v}
              </span>
            ))}
          </div>
        ))}
      </div>
    </figure>
  );
}

/** Every building as a dot, coloured by its risk (no base map). */
function BuildingMap({ data }: { data: { n: number; pos: Float32Array; risk: Int8Array } }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const geo = useMemo(() => {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < data.n; i++) {
      const x = data.pos[i * 2], y = data.pos[i * 2 + 1];
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
    const k = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
    return { x0, x1, y0, y1, k };
  }, [data]);
  const W = 620;
  const H = Math.round((W * (geo.y1 - geo.y0)) / Math.max(1e-9, (geo.x1 - geo.x0) * geo.k));
  useEffect(() => {
    const el = cv.current;
    if (!el) return;
    el.width = W;
    el.height = H;
    const ctx = el.getContext("2d")!;
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, W, H);
    // the lower levels first, so that the high ones stay visible on top
    for (const lv of [-1, 0, 1, 2, 3, 4]) {
      const c = lv >= 0 ? LEVEL_RGB[lv] : NA_RGB;
      ctx.fillStyle = rgb(c, lv >= 0 ? 1 : 0.5);
      for (let i = 0; i < data.n; i++) {
        if (data.risk[i] !== lv) continue;
        const x = ((data.pos[i * 2] - geo.x0) / (geo.x1 - geo.x0)) * (W - 1);
        const y = (1 - (data.pos[i * 2 + 1] - geo.y0) / (geo.y1 - geo.y0)) * (H - 1);
        ctx.fillRect(x, y, lv >= 3 ? 2.2 : 1, lv >= 3 ? 2.2 : 1);
      }
    }
  }, [data, geo, H]);
  return <canvas ref={cv} className="block h-auto w-full max-w-[620px] rounded-lg border border-line" />;
}

// ------------------------------------------------------------------ data
interface Data {
  project: string;
  product: string;
  label: string;
  cells?: Cells;
  beh?: Behaviour & { first: string; last: string; meta: { classes: string[] } };
  behSummary?: { counts: Record<string, number>; changes_by_month: Record<string, number>; shared_change_dates: string[]; warnings: string[]; not_assessed: number };
  risk?: { n: number; pos: Float32Array; risk: Int8Array };
  riskSummary?: { n_buildings: number; assessed: number; by_source: Record<string, number>; by_risk: Record<string, number>; height_known_share: number; median_floors_assumed: number; consequence_matrix: number[][]; risk_matrix: number[][]; warnings: string[] };
}

interface Step {
  title: string;
  goal: string;
  what: string[];
  formula?: string[];
  look: string[];
  layer?: string; // the layer of the Thematic analysis page this step explains
  needs?: "behaviour" | "risk";
  figures: { caption: string; render: (d: Data, ex: Record<string, { cell: HazardCell; fit: (number | null)[] }>) => ReactNode }[];
  numbers?: (d: Data) => [string, string][];
}

const CONSEQUENCE = [[1, 1, 2], [1, 2, 3], [2, 3, 3]];
const RISK = [[0, 0, 1], [0, 1, 1], [1, 2, 2], [2, 3, 4], [3, 4, 4]];

function Example({ c }: { c?: { cell: HazardCell; fit: (number | null)[] } }) {
  return c ? <CellChart c={c.cell} model={c.fit} compact /> : <p className="text-[12.5px] text-muted">{t("Loading the example cell…")}</p>;
}

const STEPS: Step[] = [
  {
    title: "A rate is not enough",
    goal: "Two places can sink at the same rate for very different reasons; the shape of the series tells them apart.",
    what: [
      "The zoning rates each cell by one number, its rate. A cell that sinks steadily, one that started sinking last month and one that rises and falls with the seasons can all have the same rate.",
      "The shape matters for what to do: a steady rate (aquifer compaction) calls for monitoring the pumping, an onset (new load, new well) for finding what changed at that date, a slowing motion (consolidation after construction) for checking that it fades as expected.",
      "GeoEyes fits seven simple models to the series of every cell; each has a physical reading.",
    ],
    look: ["Each shape below is drawn with sinking downwards, as on the series charts."],
    figures: [{ caption: "The seven kinds of motion: stable, steady, seasonal, speeding up, slowing down, onset (a change of rate at a date) and step (a jump).", render: () => <ShapesFigure /> }],
  },
  {
    title: "Choosing the model",
    goal: "Keep the simplest model that the data really support.",
    what: [
      "Each model is fitted by least squares to the series of every cell. A richer model always fits a little better, so the comparison uses the Bayesian information criterion (BIC), which charges every extra parameter.",
      "A richer model is kept only when it lowers the BIC by at least 6 compared with a straight line, what Kass & Raftery (1995) call strong evidence. Otherwise the cell is steady, or stable when its rate is below the stability threshold of the zoning.",
      "For the onset and the step, the date of the change is a parameter too: every epoch is tried, a few epochs from each end, and the best one kept.",
      "The classes follow the cell's own motion: speeding up means faster sinking for a sinking cell, and faster uplift for a rising one.",
    ],
    formula: ["BIC = n · ln(RSS / n) + k · ln n", "keep the richer model if BIC_line − BIC_model ≥ 6", "onset: d = a + b·t + h·(t − t₀)₊    step: d = a + b·t + δ·H(t − t₀)"],
    look: ["Click a cell on the layer “Kind of motion”: its series with the kept model and the evidence (ΔBIC)."],
    layer: "behaviour",
    needs: "behaviour",
    figures: [
      {
        caption: "How many cells of each kind.",
        render: (d) => <Bars items={BEH_CLASSES.map((c, i) => ({ label: t(BEH_LABELS[c]), n: d.behSummary?.counts[c] ?? 0, color: rgb(BEH_RGB[i]) }))} />,
      },
      ...BEH_CLASSES.filter((c) => c !== "stable" && c !== "steady").map((c) => ({
        caption: `${BEH_LABELS[c]}: a typical cell, its series and the kept model.`,
        render: (_d: Data, ex: Record<string, { cell: HazardCell; fit: (number | null)[] }>) => (ex[c] === undefined ? <p className="text-[12.5px] text-muted">{t("No cell of this kind here.")}</p> : <Example c={ex[c]} />),
      })),
    ],
    numbers: (d) => BEH_CLASSES.map((c) => [BEH_LABELS[c], fmt.int(d.behSummary?.counts[c] ?? 0)] as [string, string]),
  },
  {
    title: "Map of the kinds of motion",
    goal: "See where each kind of motion happens.",
    what: [
      "Steady motion usually covers wide areas: the compaction of an aquifer system acts at the scale of the basin.",
      "Onsets and slowing motions are local: a building site, a new embankment, a new well. Seasonal cells follow the water: river banks, irrigated land.",
      "Steps deserve a check before any reading: a jump of several millimetres between two dates is more often an unwrapping error than a real event.",
    ],
    look: ["Layer “Kind of motion” on the Thematic analysis page."],
    layer: "behaviour",
    needs: "behaviour",
    figures: [
      {
        caption: "The kind of motion of each cell.",
        render: (d) => (
          <>
            <CellMap c={d.cells!} kind="behaviour" b={d.beh} />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
              {BEH_CLASSES.map((c, i) => (
                <span key={c} className="flex items-center gap-1.5 text-ink-2">
                  <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(BEH_RGB[i]) }} />
                  {t(BEH_LABELS[c])}
                </span>
              ))}
            </div>
          </>
        ),
      },
    ],
    numbers: (d) => [
      ["Cells classified", fmt.int(Object.values(d.behSummary?.counts ?? {}).reduce((a, b) => a + b, 0))],
      ["Not assessed", fmt.int(d.behSummary?.not_assessed ?? 0)],
    ],
  },
  {
    title: "Date of change",
    goal: "Date the onsets and the steps, and tell the ground from the acquisition.",
    what: [
      "For an onset or a step, the epoch that fits best is the date of the change: it can be set against the dates of works, new wells or heavy rain.",
      "A change shared by many cells on the same date is suspicious: the ground rarely changes everywhere at once, while one acquisition with a strong atmosphere or an unwrapping error shifts all the cells together. GeoEyes flags such dates.",
    ],
    look: ["Layer “Date of change”: from the first date (dark) to the last (yellow).", "Read the flagged dates as data problems first."],
    layer: "change",
    needs: "behaviour",
    figures: [
      {
        caption: "The date of change of each cell (onset or step).",
        render: (d) => (
          <>
            <CellMap c={d.cells!} kind="change" b={d.beh} />
            <div className="mt-1 max-w-[360px]">
              <div className="h-2 rounded-sm" style={{ background: "linear-gradient(90deg,#440154,#414487,#2a788e,#22a884,#7ad151,#bddf26,#fde725)" }} />
              <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
                <span>{d.beh?.first}</span>
                <span>{d.beh?.last}</span>
              </div>
            </div>
          </>
        ),
      },
      {
        caption: "Changes by month; orange: a date shared by so many cells that it points to the acquisition.",
        render: (d) => (
          <>
            <ChangesChart byMonth={d.behSummary?.changes_by_month ?? {}} shared={d.behSummary?.shared_change_dates ?? []} />
            {(d.behSummary?.warnings ?? []).map((w) => (
              <p key={w} className="mt-1 mb-0 text-[12px] leading-snug text-[#f5d08b]">
                {ts(w)}
              </p>
            ))}
          </>
        ),
      },
      { caption: "An onset cell: its rate changes at the date of change.", render: (_d, ex) => (ex.onset === undefined ? <p className="text-[12.5px] text-muted">{t("No cell of this kind here.")}</p> : <Example c={ex.onset} />) },
    ],
    numbers: (d) => [
      ["Onsets", fmt.int(d.behSummary?.counts.onset ?? 0)],
      ["Steps", fmt.int(d.behSummary?.counts.step ?? 0)],
      ["Shared change dates", d.behSummary?.shared_change_dates.length ? d.behSummary.shared_change_dates.join(", ") : "–"],
    ],
  },
  {
    title: "From hazard to risk",
    goal: "Turn the hazard of a place into the risk for what stands on it.",
    what: [
      "Risk crosses the hazard with what is exposed to it and how much that suffers (UNDRR terminology; the hazard → risk step of the research plan). A fast-sinking empty field is a hazard; a fast-sinking school is a risk.",
      "Hazard: from the building's own persistent scatterers when it has at least 5 of them (its sinking rate, and its own tilt β when significant), else the level of the analysis cell that holds it.",
      "Exposure: the gross floor area, footprint × floors, a proxy of the people and value inside: E1 below 300 m², E3 from 3,000 m².",
      "Vulnerability: the structural type is not in open data, so the proxies are size and slenderness. Long buildings span more differential settlement, tall ones turn a small tilt into a large offset at the top (Burland & Wroth 1974; Peduto et al. 2017).",
    ],
    formula: ["E: footprint × floors < 300 ≤ E2 < 3000 ≤ E3 (m²)", "V3: height ≥ 21 m or length ≥ 30 m; V1: < 60 m² and low", "C = CONSEQUENCE[E][V],  R = RISK[H][C]"],
    look: ["Every threshold is a parameter of the project ([postprocess.risk])."],
    layer: "risk",
    figures: [
      {
        caption: "Consequence from exposure and vulnerability, then risk from hazard and consequence.",
        render: () => (
          <div className="flex flex-wrap gap-4">
            <Grid title="Consequence" rows={["E1", "E2", "E3"]} cols={["V1", "V2", "V3"]} cells={CONSEQUENCE} color={(v) => ["", "#91cf60", "#fee08b", "#fc8d59"][v]} />
            <Grid title="Risk" rows={["H0", "H1", "H2", "H3", "H4"]} cols={["C1", "C2", "C3"]} cells={RISK} color={(v) => rgb(LEVEL_RGB[v])} />
          </div>
        ),
      },
    ],
  },
  {
    title: "Risk to buildings",
    goal: "See which buildings call for attention first.",
    what: [
      "Every Overture building of the area gets a risk level. High and very high levels come from a high hazard (fast sinking, strong distortion) where the consequence is large.",
      "Buildings rated from their own InSAR points are the most reliable; the others carry the hazard of their 100 m cell.",
      "Heights are rarely known in open data over our areas: the floor area then assumes the median number of floors, which flattens the exposure.",
    ],
    look: ["Layer “Risk to buildings”: click a building for its hazard, exposure, vulnerability and the source of its hazard."],
    layer: "risk",
    needs: "risk",
    figures: [
      {
        caption: "Risk level of every building (dots; high and very high drawn larger).",
        render: (d) => (
          <>
            <BuildingMap data={d.risk!} />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
              {[4, 3, 2, 1, 0].map((i) => (
                <span key={i} className="flex items-center gap-1.5 text-ink-2">
                  <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(LEVEL_RGB[i]) }} />
                  {t(LEVELS[i])}
                </span>
              ))}
            </div>
          </>
        ),
      },
      {
        caption: "Buildings by risk level.",
        render: (d) => <Bars items={[4, 3, 2, 1, 0].map((k) => ({ label: t(LEVELS[k]), n: d.riskSummary?.by_risk[LEVELS[k].toLowerCase()] ?? 0, color: rgb(LEVEL_RGB[k]) }))} />,
      },
    ],
    numbers: (d) => [
      ["Buildings", fmt.int(d.riskSummary?.n_buildings ?? 0)],
      ["Hazard from their own points", fmt.int(d.riskSummary?.by_source.building ?? 0)],
      ["Hazard from their cell", fmt.int(d.riskSummary?.by_source.cell ?? 0)],
      ["Heights known", `${Math.round(100 * (d.riskSummary?.height_known_share ?? 0))} %`],
    ],
  },
  {
    title: "Limits and checks",
    goal: "Know what these maps can and cannot say.",
    what: [
      "Kinds of motion: a short series (one year) cannot separate a seasonal cycle from a trend change; the classes become firmer with every new acquisition. Steps and shared change dates must be checked against the data before any reading.",
      "Risk: the classes are screening classes. Without the structural type, the foundations and the real heights, the vulnerability is a proxy; the risk map tells where to look, not what will crack.",
      "Checks that would make them firmer: damage surveys of a few streets (cracks against β), building permits and works dates against the onsets, heights from a city model or lidar, and the structural type from the cadastre.",
    ],
    look: ["Use the maps to choose where to inspect, then confirm on the ground."],
    figures: [],
  },
];

// ------------------------------------------------------------------ page
export function BehaviourChapter({ ws, step }: { ws: Workspace | undefined; step?: number }) {
  const qc = useQueryClient();
  const k = Math.min(STEPS.length - 1, Math.max(0, step ?? 0));
  const S = STEPS[k];
  const go = (i: number) => (window.location.hash = href({ page: "learn", chapter: "behaviour", step: i }));

  const products = useMemo(() => {
    const out: { project: string; product: string; label: string }[] = [];
    Object.values(ws?.projects ?? {}).forEach((p) =>
      p.tracks.forEach((tr) => tr.product && out.push({ project: p.name, product: tr.product.id, label: `${p.name} · ${fmt.sensor(tr.sensor)} ${t(tr.direction)} v${tr.product.version}` })),
    );
    return out;
  }, [ws]);
  const zoned = useQueries({
    queries: products.map((p) => ({ queryKey: ["hazard", p.project, p.product], queryFn: () => api.hazard(p.project, p.product), staleTime: 60_000 })),
  });
  const statuses = useQueries({
    queries: products.map((p) => ({ queryKey: ["behaviour", p.project, p.product], queryFn: () => api.behaviour(p.project, p.product), staleTime: 10_000 })),
  });
  const ready = products.filter((_, i) => zoned[i].data?.summary);
  // by default the product with both analyses and the largest share of buildings at moderate risk or above
  const score = (p: (typeof products)[number]) => {
    const st = statuses[products.indexOf(p)].data;
    const r = st?.risk.summary;
    const high = r ? ["moderate", "high", "very high"].reduce((a, l) => a + (r.by_risk[l] ?? 0), 0) / Math.max(1, r.n_buildings) : 0;
    return (r ? 2 : 0) + (st?.behaviour.summary ? 1 : 0) + high;
  };
  const [choice, setChoice] = useState("");
  const sel = ready.find((p) => p.product === choice) ?? [...ready].sort((a, b) => score(b) - score(a))[0];
  const st = sel ? statuses[products.indexOf(sel)] : undefined;
  const hz = sel ? zoned[products.indexOf(sel)].data?.summary : undefined;
  const behSummary = st?.data?.behaviour.summary ?? undefined;
  const riskSummary = st?.data?.risk.summary ?? undefined;
  const running = !!(st?.data?.behaviour.running || st?.data?.risk.running);
  useEffect(() => {
    if (!running || !sel) return;
    const id = window.setInterval(() => qc.invalidateQueries({ queryKey: ["behaviour", sel.project, sel.product] }), 2000);
    return () => window.clearInterval(id);
  }, [running, sel, qc]);

  const cells = useQuery({
    queryKey: ["hazard-cells", sel?.project, sel?.product, hz?.created],
    queryFn: async (): Promise<Cells> => {
      const { meta, buf } = await api.hazardCells(sel!.project, sel!.product);
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!sel && !!hz,
    staleTime: Infinity,
  });
  const beh = useQuery({
    queryKey: ["behaviour-cells", sel?.project, sel?.product, behSummary?.created],
    queryFn: async () => {
      const { meta, buf } = await api.behaviourCells(sel!.project, sel!.product);
      return { buf, meta, span: (Date.parse(meta.last_date) - Date.parse(meta.first_date)) / 86400000, first: meta.first_date, last: meta.last_date };
    },
    enabled: !!sel && !!behSummary,
    staleTime: Infinity,
  });
  const risk = useQuery({
    queryKey: ["risk-buildings-learn", sel?.project, sel?.product, riskSummary?.created],
    queryFn: async () => {
      const { meta, view: dv } = await api.riskBuildings(sel!.project, sel!.product);
      const pos = new Float32Array(meta.n * 2);
      const r = new Int8Array(meta.n);
      for (let i = 0; i < meta.n; i++) {
        const o = i * meta.record;
        pos[i * 2] = meta.origin[0] + dv.getFloat32(o, true);
        pos[i * 2 + 1] = meta.origin[1] + dv.getFloat32(o + 4, true);
        r[i] = dv.getUint8(o + 8) - 1;
      }
      return { n: meta.n, pos, risk: r };
    },
    enabled: !!sel && !!riskSummary && S.needs === "risk",
    staleTime: Infinity,
  });

  // a typical cell of each kind: the one with the most points
  const typical = useMemo(() => {
    const out: Record<string, number> = {};
    const c = cells.data;
    const b = beh.data;
    if (!c || !b) return out;
    const F = c.meta.fields.length;
    const best: Record<string, number> = {};
    // an onset or a step on a date shared by many cells is the acquisition, not an example of the ground
    const d0 = Date.parse(b.first);
    const sharedDays = new Set((behSummary?.shared_change_dates ?? []).map((d) => Math.round((Date.parse(d) - d0) / 86400000)));
    for (let i = 0; i < c.meta.n; i++) {
      const cls = BEH_CLASSES[b.buf[i * 2]];
      if (!cls) continue;
      if ((cls === "onset" || cls === "step") && sharedDays.has(Math.round(b.buf[i * 2 + 1]))) continue;
      const n = c.buf[i * F + c.f.n_points];
      if (best[cls] === undefined || n > best[cls]) {
        best[cls] = n;
        out[cls] = i;
      }
    }
    return out;
  }, [cells.data, beh.data, behSummary]);
  const wanted = k === 1 ? BEH_CLASSES.filter((c) => c !== "stable" && c !== "steady") : k === 3 ? ["onset"] : [];
  const exQ = useQueries({
    queries: wanted.map((c) => ({
      queryKey: ["behaviour-example", sel?.project, sel?.product, behSummary?.created, typical[c]],
      queryFn: async () => {
        const [cell, b] = await Promise.all([api.hazardCell(sel!.project, sel!.product, typical[c]), api.behaviourCell(sel!.project, sel!.product, typical[c])]);
        return { cell, fit: b.fit_mm };
      },
      enabled: !!sel && typical[c] !== undefined,
      staleTime: Infinity,
    })),
  });
  // per kind: undefined = no cell of that kind here, null = still loading
  const ex: Record<string, { cell: HazardCell; fit: (number | null)[] }> = {};
  wanted.forEach((c, i) => {
    if (typical[c] !== undefined) ex[c] = exQ[i].data ?? (null as never);
  });

  const data: Data | undefined = sel && {
    project: sel.project,
    product: sel.product,
    label: sel.label,
    cells: cells.data,
    beh: beh.data,
    behSummary,
    risk: risk.data,
    riskSummary,
  };
  const missing = S.needs === "behaviour" ? !behSummary : S.needs === "risk" ? !riskSummary : false;
  const loading = S.needs === "behaviour" ? !cells.data || !beh.data : S.needs === "risk" ? !risk.data : false;
  const run = async (kind: "behaviour" | "risk") => {
    if (!sel) return;
    await api.analysisRun(sel.project, sel.product, kind);
    await qc.invalidateQueries({ queryKey: ["behaviour", sel.project, sel.product] });
  };

  let fig = 0;
  return (
    <div className="flex h-full min-h-0">
      <ChapterNav current="behaviour" steps={STEPS.map((s) => s.title)} step={k} onStep={go} />
      <div className="min-w-0 flex-1 overflow-y-auto">
        <article className="mx-auto max-w-[1180px] px-6 py-5">
          <div className="font-mono text-[12px] text-faint">{t("Step {i} of {n}", { i: k, n: STEPS.length - 1 })}</div>
          <h1 className="m-0 mt-1 text-[26px] font-bold tracking-tight">{t(S.title)}</h1>
          <p className="mt-1.5 max-w-[860px] text-[15px] leading-relaxed text-ink-2">{t(S.goal)}</p>
          <div className="grid gap-x-8 xl:grid-cols-[minmax(0,1fr)_300px]">
            <div className="min-w-0">
              <Section title="Principle">
                <div className="flex max-w-[860px] flex-col gap-3 text-[14px] leading-relaxed text-ink-2">
                  {S.what.map((w) => (
                    <p key={w} className="mt-0 mb-0">
                      {t(w)}
                    </p>
                  ))}
                </div>
                {S.formula && (
                  <div className="mt-4 max-w-[860px] rounded-lg border-l-4 border-accent bg-panel px-4 py-3 font-mono text-[14px] leading-loose text-ink">
                    {S.formula.map((f) => (
                      <div key={f}>{t(f)}</div>
                    ))}
                  </div>
                )}
              </Section>
              {S.figures.length > 0 && (
                <Section title="Illustrated on real data">
                  {!data ? (
                    <p className="text-[13px] text-muted">{t("No product of the workspace has a hazard zoning yet: run one on the Thematic analysis page, then come back.")}</p>
                  ) : missing ? (
                    <div className="max-w-[860px] space-y-2 text-[13px] text-muted">
                      <p className="m-0">{S.needs === "risk" ? t("The risk to buildings of this product is not assessed yet.") : t("The kinds of motion of this product are not classified yet.")}</p>
                      <Button variant="primary" disabled={running} onClick={() => run(S.needs!)}>
                        {running ? t("Running…") : S.needs === "risk" ? t("Assess the risk to buildings") : t("Classify the kinds of motion")}
                      </Button>
                    </div>
                  ) : loading && S.needs ? (
                    <p className="text-[13px] text-muted">{t("Loading the cells…")}</p>
                  ) : (
                    <div className="space-y-6">
                      {S.figures.map((f) => {
                        fig += 1;
                        return (
                          <figure key={f.caption} className="m-0 max-w-[860px]">
                            {f.render(data, ex)}
                            <figcaption className="mt-2 text-[12.5px] leading-snug text-muted">
                              <span className="font-semibold text-ink-2">
                                {t("Figure")} 3.{k}.{fig}.
                              </span>{" "}
                              {t(f.caption)}
                            </figcaption>
                          </figure>
                        );
                      })}
                    </div>
                  )}
                </Section>
              )}
              <Section title="What to look for">
                <div className="max-w-[860px] rounded-lg border border-[#2b4a73] bg-[#0f1d33] px-4 py-3">
                  <ul className="m-0 list-disc space-y-1 pl-4 text-[13.5px] leading-relaxed text-ink-2">
                    {S.look.map((w) => (
                      <li key={w}>{t(w)}</li>
                    ))}
                  </ul>
                  {S.layer && sel && (
                    <a href={href({ page: "hazard", name: sel.project, product: sel.product, view: S.layer })} className="mt-3 inline-block no-underline">
                      <Button>{t("Open the Thematic analysis")}</Button>
                    </a>
                  )}
                </div>
              </Section>
              <div className="mt-6 text-[12px] text-faint">
                {t("Full method, sources and research plan:")} docs/{lang()}/research/behaviour-and-risk.md
              </div>
              <nav className="mt-4 mb-8 flex flex-wrap justify-between gap-2 border-t border-line pt-4">
                <Button disabled={k === 0} onClick={() => go(k - 1)}>
                  ← {k > 0 ? t(STEPS[k - 1].title) : t("Previous")}
                </Button>
                <Button variant="primary" disabled={k === STEPS.length - 1} onClick={() => go(k + 1)}>
                  {k < STEPS.length - 1 ? t(STEPS[k + 1].title) : t("Next")} →
                </Button>
              </nav>
            </div>
            <aside className="mt-6 space-y-3 xl:sticky xl:top-4 xl:self-start">
              <div className="rounded-xl border border-line bg-panel p-3">
                <div className="text-[10.5px] font-semibold tracking-[1.2px] text-muted uppercase">{t("Data of the illustrations")}</div>
                {ready.length ? (
                  <select value={sel?.product ?? ""} onChange={(e) => setChoice(e.target.value)} className="mt-2 h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink">
                    {ready.map((p) => (
                      <option key={p.product} value={p.product}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="mt-1 mb-0 text-[12px] text-muted">{t("none yet")}</p>
                )}
              </div>
              {data && S.numbers && !missing && (
                <div className="rounded-xl border border-line bg-panel p-3">
                  <div className="text-[10.5px] font-semibold tracking-[1.2px] text-muted uppercase">{t("Numbers of this data")}</div>
                  <div className="mt-2 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[12.5px]">
                    {S.numbers(data).map(([a, b]) => (
                      <div key={a} className="contents">
                        <span className="text-muted">{t(a)}</span>
                        <span className="text-right font-mono text-ink-2">{b}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </aside>
          </div>
        </article>
      </div>
    </div>
  );
}
