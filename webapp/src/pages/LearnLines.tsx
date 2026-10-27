// Principles, chapter 4: InSAR along dykes, railways and main roads (geoeyes lines) and the settlement still to
// come where the ground consolidates (geoeyes consolidation), one step per page as a wiki article, illustrated with
// a real product of the workspace. Method, thresholds and sources: docs/en/research/lines-and-consolidation.md.
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type ConsolidationCell, type ConsolidationSummary, type LineProfile, type LinesSummary, type Workspace } from "../api";
import { ChapterNav } from "../components/LearnKit";
import { lang, t } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { CONS_RGB, ConsolidationChart, LINE_KINDS, LINE_RGB, NA_RGB, ProfileChart, rgb, type Cells, type Consolidation, type RGB } from "./Hazard";
import { CellMap, Section } from "./LearnHazard";

// ------------------------------------------------------------------ figures
const KIND_RGB: Record<string, RGB> = { dyke: [76, 194, 255], railway: [245, 184, 75], embankment: [214, 51, 168], road: [147, 164, 191] };

interface Segments {
  n: number;
  buf: Float32Array; // lon1, lat1, lon2, lat2, β class, line
  kinds: Record<string, string>;
}

/** The segments of the lines on a canvas (no base map), coloured by kind or by β class. */
function LinesMap({ s, by }: { s: Segments; by: "kind" | "beta" }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const geo = useMemo(() => {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < s.n; i++) {
      for (const o of [0, 2]) {
        const x = s.buf[i * 6 + o], y = s.buf[i * 6 + o + 1];
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
    return { x0, x1, y0, y1, k: Math.cos((((y0 + y1) / 2) * Math.PI) / 180) };
  }, [s]);
  const W = 760;
  const H = Math.round((W * (geo.y1 - geo.y0)) / Math.max(1e-9, (geo.x1 - geo.x0) * geo.k));
  useEffect(() => {
    const el = cv.current;
    if (!el) return;
    el.width = W;
    el.height = H;
    const ctx = el.getContext("2d")!;
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, W, H);
    const X = (x: number) => ((x - geo.x0) / (geo.x1 - geo.x0)) * (W - 1);
    const Y = (y: number) => (1 - (y - geo.y0) / (geo.y1 - geo.y0)) * (H - 1);
    // grey and below-limit segments first, so that the flagged ones stay on top
    const passes = by === "kind" ? [0] : [-1, 0, 1, 2, 3];
    for (const pass of passes) {
      for (let i = 0; i < s.n; i++) {
        const o = i * 6;
        const cls = s.buf[o + 4];
        let col: RGB;
        let w = 1.2;
        if (by === "kind") col = KIND_RGB[s.kinds[String(s.buf[o + 5])]] ?? NA_RGB;
        else {
          if (cls !== pass) continue;
          col = cls >= 0 ? LINE_RGB[cls] : NA_RGB;
          w = cls >= 1 ? 3 : 1.2;
        }
        ctx.strokeStyle = rgb(col, by === "beta" && cls < 0 ? 0.55 : 1);
        ctx.lineWidth = w;
        ctx.beginPath();
        ctx.moveTo(X(s.buf[o]), Y(s.buf[o + 1]));
        ctx.lineTo(X(s.buf[o + 2]), Y(s.buf[o + 3]));
        ctx.stroke();
      }
    }
  }, [s, by, geo, H]);
  return <canvas ref={cv} className="block h-auto w-full max-w-[620px] rounded-lg border border-line" />;
}

/** The Asaoka construction: each reading against the previous one; the fitted line meets s_i = s_(i−1) at the end. */
function AsaokaChart({ a }: { a: ConsolidationCell["asaoka"] }) {
  if (!a.prev.length || a.b0 == null || a.b1 == null) return <p className="text-[12.5px] text-muted">{t("Too few readings for the Asaoka construction.")}</p>;
  const W = 340;
  const H = 300;
  const all = [...a.prev, ...a.next, ...(a.final != null ? [a.final] : [])];
  const lo = Math.min(0, ...all);
  const hi = Math.max(...all) * 1.05 || 1;
  const X = (v: number) => 40 + ((v - lo) / (hi - lo)) * (W - 52);
  const Y = (v: number) => H - 30 - ((v - lo) / (hi - lo)) * (H - 44);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[340px]">
      <rect x={40} y={14} width={W - 52} height={H - 44} fill="none" stroke="#22324d" />
      <line x1={X(lo)} y1={Y(lo)} x2={X(hi)} y2={Y(hi)} stroke="#93a4bf" strokeDasharray="4 3" />
      <line x1={X(lo)} y1={Y(a.b0 + a.b1 * lo)} x2={X(hi)} y2={Y(a.b0 + a.b1 * hi)} stroke="#f46d43" strokeWidth="1.8" />
      {a.prev.map((p, i) => (
        <circle key={i} cx={X(p)} cy={Y(a.next[i])} r={3} fill="#4cc2ff" />
      ))}
      {a.final != null && a.final <= hi && <circle cx={X(a.final)} cy={Y(a.final)} r={5} fill="none" stroke="#fde725" strokeWidth="2" />}
      <text x={X(hi)} y={Y(hi) - 4} fill="#93a4bf" fontSize="10" textAnchor="end">sᵢ = sᵢ₋₁</text>
      <text x={40} y={H - 8} fill="#93a4bf" fontSize="10">{lo.toFixed(0)}</text>
      <text x={W - 12} y={H - 8} fill="#93a4bf" fontSize="10" textAnchor="end">{hi.toFixed(0)}</text>
      <text x={(W + 28) / 2} y={H - 8} fill="#93a4bf" fontSize="10" textAnchor="middle">{t("previous reading sᵢ₋₁, mm")}</text>
      <text x={12} y={(H - 16) / 2} fill="#93a4bf" fontSize="10" textAnchor="middle" transform={`rotate(-90 12 ${(H - 16) / 2})`}>
        {t("reading sᵢ, mm")}
      </text>
    </svg>
  );
}

function Bars({ items }: { items: { label: string; n: number; color: string; right: string }[] }) {
  const max = Math.max(1, ...items.map((i) => i.n));
  return (
    <div className="space-y-1">
      {items.map((i) => (
        <div key={i.label} className="grid grid-cols-[130px_minmax(0,1fr)_150px] items-center gap-2 text-[12.5px]">
          <span className="truncate text-ink-2">{i.label}</span>
          <span className="h-3 rounded-sm" style={{ width: `${Math.max(0.5, (100 * i.n) / max)}%`, background: i.color }} />
          <span className="text-right font-mono text-muted">{i.right}</span>
        </div>
      ))}
    </div>
  );
}

function Swatches({ items }: { items: [RGB, string][] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
      {items.map(([c, l]) => (
        <span key={l} className="flex items-center gap-1.5 text-ink-2">
          <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(c) }} />
          {l}
        </span>
      ))}
    </div>
  );
}

const ratio = (b: number | null | undefined) => (b ? `1/${Math.round(1 / b)}` : "–");

// ------------------------------------------------------------------ data
interface Data {
  lines?: LinesSummary;
  segments?: Segments;
  profile?: LineProfile;
  cons?: ConsolidationSummary;
  cells?: Cells;
  consCells?: Consolidation;
  example?: ConsolidationCell;
}

interface Step {
  title: string;
  goal: string;
  what: string[];
  formula?: string[];
  look: string[];
  layer?: string;
  needs?: "lines" | "consolidation";
  figures: { caption: string; render: (d: Data) => ReactNode }[];
  numbers?: (d: Data) => [string, string][];
}

const STEPS: Step[] = [
  {
    title: "Lines on the map",
    goal: "Follow the motion along the structures that are long, continuous and sensitive to differential settlement.",
    what: [
      "A dyke, a railway or an elevated road suffers less from sinking as such than from sinking that changes along it: a dip in a dyke crest is where the water overtops first, a dip under a track bends the rails.",
      "GeoEyes reads the lines from OpenStreetMap over the product: dykes (man_made=dyke, or the streets named “Đê …” that run on the Red River dykes in Hanoi), embankments, railways and motorway, trunk and primary roads. Pieces of the same kind and name that touch are chained into one line.",
      "Stations are placed every 50 m along each line. At each, the median vertical rate of the persistent scatterers within 30 m is kept, when there are at least 3 of them; elsewhere the line is not covered.",
    ],
    formula: ["v_vert = v_LOS / l_u   (GeoEyes sign: negative = sinking)", "station: median of the points within 30 m, at least 3"],
    look: ["Grey stretches are not missing motion but missing points: vegetation, water and steep slopes return few persistent scatterers."],
    layer: "lines",
    needs: "lines",
    figures: [
      {
        caption: "The lines of the area by kind.",
        render: (d) => (
          <>
            <LinesMap s={d.segments!} by="kind" />
            <Swatches items={Object.entries(KIND_RGB).filter(([k]) => d.lines?.by_kind[k]?.lines).map(([k, c]) => [c, t(LINE_KINDS[k])] as [RGB, string])} />
          </>
        ),
      },
      {
        caption: "Length of each kind and the share covered by InSAR stations.",
        render: (d) => (
          <Bars
            items={Object.entries(d.lines?.by_kind ?? {})
              .filter(([, v]) => v.lines)
              .map(([k, v]) => ({ label: t(LINE_KINDS[k] ?? k), n: v.km, color: rgb(KIND_RGB[k] ?? NA_RGB), right: `${fmt.num(v.km, 1)} km · ${v.covered_share != null ? Math.round(100 * v.covered_share) : "–"} %` }))}
          />
        ),
      },
    ],
    numbers: (d) => [
      ["Lines", fmt.int(d.lines?.n_lines ?? 0)],
      ["Stations", fmt.int(d.lines?.n_stations ?? 0)],
      ...Object.entries(d.lines?.by_kind ?? {})
        .filter(([, v]) => v.lines)
        .map(([k, v]) => [LINE_KINDS[k] ?? k, `${fmt.num(v.km, 1)} km`] as [string, string]),
    ],
  },
  {
    title: "Profile along a line",
    goal: "Read the motion of a line as a profile, and measure how much it bends.",
    what: [
      "Along the chainage, the vertical rate of the stations draws the profile of the line. A uniform rate lowers the whole line without bending it; what matters for the structure is the difference between neighbouring stations.",
      "Between two stations 100 m apart, the difference of rate accumulated over 10 years, divided by the distance, is an angular distortion β, the measure of the damage limits of Skempton & MacDonald (1956) and Bjerrum (1963): 1/500 safe limit, 1/300 first cracks, 1/150 structural damage.",
      "For a dyke, the lowest rate along it also gives the crest lost in 10 years: the freeboard against the design flood shrinks by as much.",
    ],
    formula: ["β = |v(x + L) − v(x)| · T / L,   L = 100 m,  T = 10 yr", "crest lost = |min v| · T"],
    look: ["The shaded bars mark the stations beyond 1/500, coloured as the damage classes.", "Click a line on the layer “Infrastructure lines” for its own profile."],
    layer: "lines",
    needs: "lines",
    figures: [
      {
        caption: "Profile of the line with the largest distortion of the area: vertical rate along the chainage.",
        render: (d) =>
          d.profile ? (
            <>
              <div className="mb-1 text-[13px] font-semibold text-ink">
                {d.profile.name} <span className="font-normal text-muted">· {t(LINE_KINDS[d.profile.kind] ?? d.profile.kind)}</span>
              </div>
              <div className="max-w-[620px]">
                <ProfileChart p={d.profile} />
              </div>
            </>
          ) : (
            <p className="text-[12.5px] text-muted">{t("No line is beyond the damage limits here.")}</p>
          ),
      },
    ],
    numbers: (d) =>
      d.profile
        ? [
            ["Line", d.profile.name],
            ["Length", `${fmt.num(d.profile.length_m / 1000, 1)} km`],
            ["Covered by InSAR", `${Math.round(100 * d.profile.covered_share)} %`],
            ["Largest distortion in 10 years", ratio(d.profile.beta_max)],
            ["Lowered in 10 years, at most", d.profile.loss_mm != null ? `${fmt.num(d.profile.loss_mm, 0)} mm` : "–"],
          ]
        : [],
  },
  {
    title: "Where the lines bend",
    goal: "Find the stretches to inspect first.",
    what: [
      "Coloured by the damage class of β, the lines show where the ground changes rate over a short distance: the edge of a subsidence bowl, a crossing over a buried channel, a bridge approach on fresh fill.",
      "The table ranks the lines by their largest distortion. A line with many flagged stations calls for a survey; a single flagged station may also be a few odd points and deserves a look at the data first.",
    ],
    look: ["Purple: beyond the damage limits. Green: below. Grey: too few InSAR points."],
    layer: "lines",
    needs: "lines",
    figures: [
      {
        caption: "Angular distortion along the lines in 10 years, by damage class.",
        render: (d) => (
          <>
            <LinesMap s={d.segments!} by="beta" />
            <Swatches items={[[LINE_RGB[3], "≥ 1/150"], [LINE_RGB[2], "1/300 – 1/150"], [LINE_RGB[1], "1/500 – 1/300"], [LINE_RGB[0], "< 1/500"], [NA_RGB, t("too few InSAR points")]]} />
          </>
        ),
      },
      {
        caption: "The lines with the largest distortion.",
        render: (d) => (
          <table className="w-full max-w-[760px] border-collapse text-[12.5px]">
            <thead>
              <tr className="text-left text-[11px] tracking-[0.8px] text-muted uppercase">
                <th className="py-1 font-semibold">{t("Line")}</th>
                <th className="py-1 font-semibold">{t("Kind")}</th>
                <th className="py-1 text-right font-semibold">β max</th>
                <th className="py-1 text-right font-semibold">{t("Lowest rate, mm/yr")}</th>
                <th className="py-1 text-right font-semibold">{t("Flagged stations")}</th>
              </tr>
            </thead>
            <tbody>
              {(d.lines?.hotspots ?? []).slice(0, 10).map((h) => (
                <tr key={h.line} className="border-t border-line">
                  <td className="py-1 text-ink-2">{h.name}</td>
                  <td className="py-1 text-muted">{t(LINE_KINDS[h.kind] ?? h.kind)}</td>
                  <td className="py-1 text-right font-mono text-ink-2">{ratio(h.beta_max)}</td>
                  <td className="py-1 text-right font-mono text-ink-2">{fmt.num(h.v_min_mm_yr, 1)}</td>
                  <td className="py-1 text-right font-mono text-ink-2">{h.flagged}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ),
      },
    ],
    numbers: (d) =>
      Object.entries(d.lines?.by_kind ?? {})
        .filter(([, v]) => v.lines)
        .map(([k, v]) => [`${t(LINE_KINDS[k] ?? k)} · ${t("stations beyond 1/500")}`, fmt.int(v.flagged_stations)] as [string, string]),
  },
  {
    title: "Settling towards an end",
    goal: "Tell a ground that will keep sinking from one that is finishing its settlement.",
    what: [
      "Soft clay loaded by a new building or embankment squeezes its water out slowly: it settles fast at first, then slower and slower towards a final settlement (primary consolidation, Terzaghi 1925). Pumping an aquifer, on the other hand, keeps the ground sinking as long as the pumping goes on.",
      "The first-order consolidation curve has three parameters: the settlement at the start c, the settlement still available A, and the time constant τ. GeoEyes fits it to every sinking cell (τ tried on a grid from 18 days to 30 years) and keeps it when it beats a straight line by ΔBIC ≥ 6, with τ within the reach of the data.",
      "Asaoka (1978) reads the same curve graphically: readings at a fixed interval, each plotted against the previous one, fall on a straight line, which meets the diagonal sᵢ = sᵢ₋₁ at the final settlement.",
    ],
    formula: ["s(t) = c + A · (1 − e^(−t/τ))", "final = c + A,   still to come = A · e^(−T/τ),   90 % at τ · ln 10", "Asaoka: sᵢ = β₀ + β₁ · sᵢ₋₁,   final = β₀ / (1 − β₁),   β₁ = e^(−Δt/τ)"],
    look: ["Click a coloured cell on the layer “Remaining settlement”: its curve projected ahead until it levels off."],
    layer: "consolidation",
    needs: "consolidation",
    figures: [
      {
        caption: "The cell with the most settlement still to come: its settlement (dots) and the fitted curve projected ahead until it levels off.",
        render: (d) => (d.example ? <div className="max-w-[460px]"><ConsolidationChart c={d.example} /></div> : <p className="text-[12.5px] text-muted">{t("No cell consolidates in this product.")}</p>),
      },
      {
        caption: "The Asaoka construction of the same cell (readings at a fixed interval); the yellow circle marks the final settlement.",
        render: (d) => (d.example ? <AsaokaChart a={d.example.asaoka} /> : null),
      },
    ],
    numbers: (d) =>
      d.example
        ? [
            ["Settled so far", `${fmt.num(d.example.settled_mm, 0)} mm`],
            ["Still to come", `${fmt.num(d.example.remaining_mm, 0)} mm`],
            ["Final settlement", `${fmt.num(d.example.final_mm, 0)} mm`],
            ["Time constant τ", `${fmt.num(d.example.tau_yr, 2)} ${t("yr")}`],
            ["Asaoka final", d.example.asaoka.final != null ? `${fmt.num(d.example.asaoka.final, 0)} mm` : "–"],
          ]
        : [],
  },
  {
    title: "Settlement still to come",
    goal: "Map where the ground has not finished settling, and check the curves on dates they have not seen.",
    what: [
      "Each consolidating cell is coloured by the settlement still to come after the last date. These are the places where a new structure would still be dragged down, or where a dyke or a road built on fresh fill will need topping up.",
      "The check is a forecast: the curve and the straight line are both fitted on the first 70 % of the dates, and both predict the rest. On cells chosen because the curve fits them, the curve is favoured; the check tells whether it also predicts, not whether the choice is right.",
    ],
    look: ["Layer “Remaining settlement” on the Thematic analysis page."],
    layer: "consolidation",
    needs: "consolidation",
    figures: [
      {
        caption: "Settlement still to come of the consolidating cells (grey: not consolidating).",
        render: (d) => (
          <>
            <CellMap c={d.cells!} kind="consolidation" cons={d.consCells} />
            <div className="mt-1 max-w-[360px]">
              <div className="h-2 rounded-sm" style={{ background: `linear-gradient(90deg,${CONS_RGB.map((x) => rgb(x)).join(",")})` }} />
              <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
                <span>0</span>
                <span>{t("mm still to come")}</span>
                <span>{d.cons?.remaining_mm ? fmt.num(d.cons.remaining_mm.p90, 0) : "–"}</span>
              </div>
            </div>
          </>
        ),
      },
    ],
    numbers: (d) => [
      ["Sinking cells", fmt.int(d.cons?.sinking_cells ?? 0)],
      ["Consolidating", fmt.int(d.cons?.consolidating ?? 0)],
      ["Still to come, median", d.cons?.remaining_mm ? `${fmt.num(d.cons.remaining_mm.median, 0)} mm` : "–"],
      ["Still to come, max", d.cons?.remaining_mm ? `${fmt.num(d.cons.remaining_mm.max, 0)} mm` : "–"],
      ["Check: error of the curve", d.cons?.check.mae_curve_mm != null ? `${d.cons.check.mae_curve_mm} mm` : "–"],
      ["Check: error of the line", d.cons?.check.mae_line_mm != null ? `${d.cons.check.mae_line_mm} mm` : "–"],
    ],
  },
  {
    title: "Limits and checks",
    goal: "Know what these profiles and curves can and cannot say.",
    what: [
      "Lines: OpenStreetMap is complete for railways and main roads, less so for dykes; many dyke slopes are grassed and return few persistent scatterers, so their coverage is often low. The rates are relative to the reference of the product and vertical only under the assumption of no horizontal motion.",
      "Consolidation: one year of data sees only the start of most consolidation. The curve is kept only where the data clearly bend; elsewhere a cell may still be consolidating with a τ too long to be seen. Final settlements firm up with every new year of acquisitions.",
      "Checks that would make them firmer: levelling along the dykes and the tracks, the dates and the fill heights of the works near the consolidating cells, and boreholes for the thickness of soft clay.",
    ],
    look: ["Use the lines to choose the stretches to survey, and the remaining settlement to plan where to watch."],
    figures: [],
  },
];

// ------------------------------------------------------------------ page
export function LinesChapter({ ws, step }: { ws: Workspace | undefined; step?: number }) {
  const qc = useQueryClient();
  const k = Math.min(STEPS.length - 1, Math.max(0, step ?? 0));
  const S = STEPS[k];
  const go = (i: number) => (window.location.hash = href({ page: "learn", chapter: "lines", step: i }));

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
  // by default the product with both analyses, the most flagged stations and consolidating cells
  const score = (p: (typeof products)[number]) => {
    const st = statuses[products.indexOf(p)].data;
    const l = st?.lines.summary;
    const c = st?.consolidation.summary;
    const flagged = l ? Object.values(l.by_kind).reduce((a, v) => a + v.flagged_stations, 0) / Math.max(1, l.n_stations) : 0;
    return (l ? 2 : 0) + (c ? 1 : 0) + Math.min(1, (c?.consolidating ?? 0) / 20) + flagged;
  };
  const [choice, setChoice] = useState("");
  const sel = ready.find((p) => p.product === choice) ?? [...ready].sort((a, b) => score(b) - score(a))[0];
  const st = sel ? statuses[products.indexOf(sel)] : undefined;
  const hz = sel ? zoned[products.indexOf(sel)].data?.summary : undefined;
  const lines = st?.data?.lines.summary ?? undefined;
  const cons = st?.data?.consolidation.summary ?? undefined;
  const running = !!(st?.data?.lines.running || st?.data?.consolidation.running);
  useEffect(() => {
    if (!running || !sel) return;
    const id = window.setInterval(() => qc.invalidateQueries({ queryKey: ["behaviour", sel.project, sel.product] }), 2000);
    return () => window.clearInterval(id);
  }, [running, sel, qc]);

  const segments = useQuery({
    queryKey: ["line-segments-learn", sel?.project, sel?.product, lines?.created],
    queryFn: async (): Promise<Segments> => {
      const { meta, buf } = await api.lineSegments(sel!.project, sel!.product);
      return { n: meta.n, buf, kinds: Object.fromEntries(Object.entries(meta.kinds).map(([a, b]) => [String(a), b])) };
    },
    enabled: !!sel && !!lines && S.needs === "lines",
    staleTime: Infinity,
  });
  const top = lines?.hotspots[0]?.line;
  const profile = useQuery({
    queryKey: ["line-profile", sel?.project, sel?.product, lines?.created, top],
    queryFn: () => api.lineProfile(sel!.project, sel!.product, top!),
    enabled: !!sel && top != null && k === 1,
    staleTime: Infinity,
  });
  const cells = useQuery({
    queryKey: ["hazard-cells", sel?.project, sel?.product, hz?.created],
    queryFn: async (): Promise<Cells> => {
      const { meta, buf } = await api.hazardCells(sel!.project, sel!.product);
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!sel && !!hz && S.needs === "consolidation",
    staleTime: Infinity,
  });
  const consCells = useQuery({
    queryKey: ["consolidation-cells", sel?.project, sel?.product, cons?.created],
    queryFn: async (): Promise<Consolidation> => {
      const { meta, buf } = await api.consolidationCells(sel!.project, sel!.product);
      return { buf, max: meta.summary.remaining_mm?.p90 ?? 1 };
    },
    enabled: !!sel && !!cons && S.needs === "consolidation",
    staleTime: Infinity,
  });
  // the example: the cell with the most settlement still to come
  const best = useMemo(() => {
    const b = consCells.data?.buf;
    if (!b) return undefined;
    let i0: number | undefined;
    for (let i = 0; i < b.length / 2; i++) if (Number.isFinite(b[i * 2]) && (i0 === undefined || b[i * 2] > b[i0 * 2])) i0 = i;
    return i0;
  }, [consCells.data]);
  const example = useQuery({
    queryKey: ["consolidation-cell", sel?.project, sel?.product, cons?.created, best],
    queryFn: () => api.consolidationCell(sel!.project, sel!.product, best!),
    enabled: !!sel && best !== undefined && k === 3,
    staleTime: Infinity,
  });

  const data: Data | undefined = sel && { lines, segments: segments.data, profile: profile.data, cons, cells: cells.data, consCells: consCells.data, example: example.data };
  const missing = S.needs === "lines" ? !lines : S.needs === "consolidation" ? !cons : false;
  const loading = S.needs === "lines" ? !segments.data || (k === 1 && top != null && !profile.data) : S.needs === "consolidation" ? !cells.data || !consCells.data || (k === 3 && best !== undefined && !example.data) : false;
  const run = async (kind: "lines" | "consolidation") => {
    if (!sel) return;
    await api.analysisRun(sel.project, sel.product, kind);
    await qc.invalidateQueries({ queryKey: ["behaviour", sel.project, sel.product] });
  };

  let fig = 0;
  return (
    <div className="flex h-full min-h-0">
      <ChapterNav current="lines" steps={STEPS.map((s) => s.title)} step={k} onStep={go} />
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
                      <p className="m-0">{S.needs === "lines" ? t("The infrastructure lines of this product are not profiled yet.") : t("The consolidation of this product is not analysed yet.")}</p>
                      <Button variant="primary" disabled={running} onClick={() => run(S.needs!)}>
                        {running ? t("Running…") : S.needs === "lines" ? t("Profile the infrastructure lines") : t("Analyse the consolidation")}
                      </Button>
                    </div>
                  ) : loading ? (
                    <p className="text-[13px] text-muted">{t("Loading the cells…")}</p>
                  ) : (
                    <div className="space-y-6">
                      {S.figures.map((f) => {
                        fig += 1;
                        return (
                          <figure key={f.caption} className="m-0 max-w-[860px]">
                            {f.render(data)}
                            <figcaption className="mt-2 text-[12.5px] leading-snug text-muted">
                              <span className="font-semibold text-ink-2">
                                {t("Figure")} 4.{k}.{fig}.
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
                {t("Full method, sources and research plan:")} docs/{lang()}/research/lines-and-consolidation.md
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
              {data && S.numbers && !missing && !loading && S.numbers(data).length > 0 && (
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
