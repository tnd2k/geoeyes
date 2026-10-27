// Principles, chapter 5: the vertical and east-west motion from two viewing geometries (geoeyes decompose) and the
// soft-soil thickness under the cells (geoeyes geology), one step per page as a wiki article, illustrated with a
// real product of the workspace. Method and sources: docs/en/research/two-geometries-and-soft-soil.md.
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type DecomposeSummary, type GeologySummary, type Workspace } from "../api";
import { ChapterNav } from "../components/LearnKit";
import { lang, t } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { EAST_RGB, MOTION_BREAKS, rgb, SOIL_RGB, type Cells, type Geology, type RGB } from "./Hazard";
import { CellMap, Section } from "./LearnHazard";

// the classes of the rate (as the Thematic analysis page): blue rising … red sinking
const RATE_RGB: RGB[] = [[33, 102, 172], [67, 147, 195], [146, 197, 222], [127, 139, 160], [244, 165, 130], [214, 96, 77], [178, 24, 43]];
const PRODUCT_RGB: RGB[] = [[76, 194, 255], [245, 184, 75], [214, 51, 168]];
const bin = (v: number, breaks: number[]) => breaks.filter((b) => v >= b).length;

interface Dec {
  meta: { n: number; fields: string[]; dlon: number; dlat: number; summary: DecomposeSummary };
  buf: Float32Array;
  F: number;
  f: Record<string, number>;
}

// ------------------------------------------------------------------ figures
/** The lines of sight of the products in the east-up plane, from the ground to the satellite. */
function GeometryFigure({ s }: { s: DecomposeSummary }) {
  const W = 560;
  const H = 230;
  const ox = W / 2;
  const oy = H - 30;
  const L = 150;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[620px]">
      <line x1={20} x2={W - 20} y1={oy} y2={oy} stroke="#93a4bf" />
      <text x={W - 20} y={oy + 16} fill="#93a4bf" fontSize="11" textAnchor="end">{t("east")} →</text>
      <text x={20} y={oy + 16} fill="#93a4bf" fontSize="11">← {t("west")}</text>
      <line x1={ox} x2={ox} y1={oy} y2={12} stroke="#22324d" strokeDasharray="3 3" />
      <text x={ox + 4} y={20} fill="#93a4bf" fontSize="11">{t("up")}</text>
      {s.products.map((p, k) => {
        const n = Math.hypot(p.los[0], p.los[2]) || 1;
        const x = ox + (L * p.los[0]) / n;
        const y = oy - (L * p.los[2]) / n;
        const c = rgb(PRODUCT_RGB[k % PRODUCT_RGB.length]);
        return (
          <g key={p.id}>
            <line x1={ox} y1={oy} x2={x} y2={y} stroke={c} strokeWidth="2.5" />
            <circle cx={x} cy={y} r={6} fill={c} />
            <text x={x + (p.los[0] > 0 ? 10 : -10)} y={y + 4} fill={c} fontSize="11.5" textAnchor={p.los[0] > 0 ? "start" : "end"}>
              {p.track}
            </text>
            <text x={x + (p.los[0] > 0 ? 10 : -10)} y={y + 18} fill="#93a4bf" fontSize="10.5" fontFamily="JetBrains Mono, monospace" textAnchor={p.los[0] > 0 ? "start" : "end"}>
              l_e {p.los[0] > 0 ? "+" : ""}{p.los[0].toFixed(2)} · l_u {p.los[2].toFixed(2)}
            </text>
          </g>
        );
      })}
      <circle cx={ox} cy={oy} r={4} fill="#e6edf7" />
    </svg>
  );
}

/** The cells of the decomposition on a canvas (no base map), coloured by the vertical or east-west motion. */
function DecMap({ d, field }: { d: Dec; field: "up" | "east" }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const geo = useMemo(() => {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < d.meta.n; i++) {
      const x = d.buf[i * d.F], y = d.buf[i * d.F + 1];
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
    return { x0: x0 - d.meta.dlon / 2, x1: x1 + d.meta.dlon / 2, y0: y0 - d.meta.dlat / 2, y1: y1 + d.meta.dlat / 2 };
  }, [d]);
  const W = 620;
  const H = Math.round((W * (geo.y1 - geo.y0) * 110540) / Math.max(1e-9, (geo.x1 - geo.x0) * 111320 * Math.cos((((geo.y0 + geo.y1) / 2) * Math.PI) / 180)));
  useEffect(() => {
    const el = cv.current;
    if (!el) return;
    el.width = W;
    el.height = H;
    const ctx = el.getContext("2d")!;
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, W, H);
    const sx = W / (geo.x1 - geo.x0);
    const sy = H / (geo.y1 - geo.y0);
    const pw = Math.max(1, Math.ceil(d.meta.dlon * sx));
    const ph = Math.max(1, Math.ceil(d.meta.dlat * sy));
    for (let i = 0; i < d.meta.n; i++) {
      const v = d.buf[i * d.F + d.f[field]];
      ctx.fillStyle = rgb(field === "up" ? RATE_RGB[bin(-v, MOTION_BREAKS)] : EAST_RGB[bin(v, MOTION_BREAKS)]);
      const x = (d.buf[i * d.F] - d.meta.dlon / 2 - geo.x0) * sx;
      const y = (geo.y1 - d.buf[i * d.F + 1] - d.meta.dlat / 2) * sy;
      ctx.fillRect(Math.floor(x), Math.floor(y), pw, ph);
    }
  }, [d, field, geo, H]);
  return <canvas ref={cv} className="block h-auto w-full max-w-[620px] rounded-lg border border-line" />;
}

function ClassSwatches({ field }: { field: "up" | "east" }) {
  // from the most negative class (sinking, west) to the most positive (rising, east)
  const cols = field === "up" ? [...RATE_RGB].reverse() : EAST_RGB;
  const B = MOTION_BREAKS;
  const labs = cols.map((_, i) => (i === 0 ? `< ${B[0]}` : i === B.length ? `> ${B[B.length - 1]}` : `${B[i - 1]} … ${B[i]}`));
  return (
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px]">
      {cols.map((c, i) => (
        <span key={i} className="flex items-center gap-1 font-mono text-ink-2">
          <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(c) }} />
          {labs[i]}
        </span>
      ))}
      <span className="text-muted">mm/yr {field === "up" ? `(${t("up")} +)` : `(${t("east")} +)`}</span>
    </div>
  );
}

/** What each product alone would call vertical, against the decomposed vertical, one dot per cell. */
function BiasScatter({ d }: { d: Dec }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const prods = d.meta.summary.products;
  const W = 420;
  const H = 420;
  const [lo, hi] = useMemo(() => {
    let a = Infinity, b = -Infinity;
    for (let i = 0; i < d.meta.n; i++)
      for (const n of ["up", ...prods.map((_, k) => `vert_only_${k}`)]) {
        const v = d.buf[i * d.F + d.f[n]];
        if (Number.isFinite(v)) {
          a = Math.min(a, v);
          b = Math.max(b, v);
        }
      }
    return [a, b];
  }, [d, prods]);
  useEffect(() => {
    const el = cv.current;
    if (!el) return;
    el.width = W;
    el.height = H;
    const ctx = el.getContext("2d")!;
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, W, H);
    const P = (v: number) => 30 + ((v - lo) / (hi - lo || 1)) * (W - 50);
    ctx.strokeStyle = "#93a4bf";
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(P(lo), H - P(lo));
    ctx.lineTo(P(hi), H - P(hi));
    ctx.stroke();
    ctx.setLineDash([]);
    prods.forEach((_, k) => {
      ctx.fillStyle = rgb(PRODUCT_RGB[k % PRODUCT_RGB.length], 0.55);
      for (let i = 0; i < d.meta.n; i++) {
        const x = d.buf[i * d.F + d.f.up];
        const y = d.buf[i * d.F + d.f[`vert_only_${k}`]];
        ctx.fillRect(P(x) - 1, H - P(y) - 1, 2, 2);
      }
    });
    ctx.fillStyle = "#93a4bf";
    ctx.font = "11px sans-serif";
    ctx.fillText(t("decomposed vertical, mm/yr"), W / 2 - 60, H - 6);
    ctx.save();
    ctx.translate(12, H / 2 + 70);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(t("vertical projection of one product"), 0, 0);
    ctx.restore();
    ctx.fillText(lo.toFixed(0), 30, H - 18);
    ctx.fillText(hi.toFixed(0), W - 40, H - 18);
  }, [d, prods, lo, hi]);
  return (
    <>
      <canvas ref={cv} className="block h-auto w-full max-w-[420px] rounded-lg border border-line" />
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
        {prods.map((p, k) => (
          <span key={p.id} className="flex items-center gap-1.5 text-ink-2">
            <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(PRODUCT_RGB[k % PRODUCT_RGB.length]) }} />
            {p.project} · {p.track}
          </span>
        ))}
      </div>
    </>
  );
}

/** The median rate of the sinking cells and the share of moving cells per thickness class. */
function ClassChart({ s }: { s: GeologySummary }) {
  const b = s.by_class.filter((x) => x.median_rate_mm_yr != null);
  if (b.length < 2) return <p className="text-[12.5px] text-muted">{t("The thickness hardly varies here: no classes to compare.")}</p>;
  const max = Math.max(...b.map((x) => Math.abs(x.median_rate_mm_yr!)));
  return (
    <div className="max-w-[620px] space-y-1">
      {b.map((x) => (
        <div key={x.from_m} className="grid grid-cols-[110px_minmax(0,1fr)_150px] items-center gap-2 text-[12.5px]">
          <span className="font-mono text-ink-2">{x.from_m} – {x.to_m} m</span>
          <span className="h-3 rounded-sm bg-[#d6604d]" style={{ width: `${Math.max(1, (100 * Math.abs(x.median_rate_mm_yr!)) / max)}%` }} />
          <span className="text-right font-mono text-muted">
            {fmt.num(x.median_rate_mm_yr!, 1)} mm/yr · {x.moving_share != null ? Math.round(100 * x.moving_share) : "–"} %
          </span>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ data
interface Data {
  dec?: DecomposeSummary;
  decCells?: Dec;
  geo?: GeologySummary;
  cells?: Cells;
  geoCells?: Geology;
}

interface Step {
  title: string;
  goal: string;
  what: string[];
  formula?: string[];
  look: string[];
  layer?: string;
  needs?: "decompose" | "geology";
  figures: { caption: string; render: (d: Data) => ReactNode }[];
  numbers?: (d: Data) => [string, string][];
}

const STEPS: Step[] = [
  {
    title: "One line of sight",
    goal: "See why one InSAR product cannot tell sinking from sliding sideways.",
    what: [
      "A radar measures the motion of the ground along its line of sight only: the dot product of the motion with the unit vector that points from the ground to the satellite.",
      "Sentinel-1 looks sideways, about 30–45° from the vertical. Ascending passes look from the west, descending ones from the east: the same eastward motion lengthens one line of sight and shortens the other.",
      "With one product, GeoEyes divides the line-of-sight velocity by l_u to call it vertical. That holds only where the ground does not move sideways; around a subsidence bowl and on slopes it does.",
    ],
    formula: ["v_LOS = e · l_e + n · l_n + u · l_u", "one product: u ≈ v_LOS / l_u   (true only if e = n = 0)"],
    look: ["The two arrows below are the lines of sight of the products of this area: they lean to opposite sides."],
    needs: "decompose",
    figures: [{ caption: "The lines of sight of the products, from the ground to the satellite, in the east-up plane.", render: (d) => <GeometryFigure s={d.dec!} /> }],
    numbers: (d) =>
      (d.dec?.products ?? []).map((p) => [`${p.project} · ${p.track}`, `${p.first.slice(0, 7)} → ${p.last.slice(0, 7)}`] as [string, string]),
  },
  {
    title: "Vertical and east-west",
    goal: "Separate the vertical from the east-west motion with two products that look from opposite sides.",
    what: [
      "On a common grid of 100 m cells, each product gives the median line-of-sight velocity of its points and their median line-of-sight vector. Two equations, two unknowns: the vertical u and the east-west e.",
      "The north-south motion is assumed zero: polar orbits fly almost north-south and hardly see it (|l_n| ≈ 0.1).",
      "Each product has its own reference. Both are referred to the median of the area that they both cover, so the result is relative to the median motion of that area.",
      "The solution is weighted by the uncertainty of each cell velocity; the east-west component is less constrained than the vertical, because |l_e| < |l_u|.",
    ],
    formula: ["[ l_e,a  l_u,a ] [ e ]   [ v_a ]", "[ l_e,d  l_u,d ] [ u ] = [ v_d ]"],
    look: ["Layers “Vertical motion” and “East-west motion” on the Thematic analysis page; hover a cell for both components and their uncertainty."],
    layer: "up",
    needs: "decompose",
    figures: [
      { caption: "Vertical motion.", render: (d) => (<><DecMap d={d.decCells!} field="up" /><ClassSwatches field="up" /></>) },
      { caption: "East-west motion.", render: (d) => (<><DecMap d={d.decCells!} field="east" /><ClassSwatches field="east" /></>) },
    ],
    numbers: (d) =>
      d.dec
        ? [
            ["Cells", fmt.int(d.dec.n_cells)],
            ["Vertical, min … max", `${fmt.num(d.dec.up_mm_yr.min, 0)} … ${fmt.num(d.dec.up_mm_yr.max, 0)} mm/yr`],
            ["East-west, min … max", `${fmt.num(d.dec.east_mm_yr.min, 0)} … ${fmt.num(d.dec.east_mm_yr.max, 0)} mm/yr`],
            ["Uncertainty, vertical", `${d.dec.sigma_up_median} mm/yr`],
            ["Uncertainty, east-west", `${d.dec.sigma_east_median} mm/yr`],
            ["Significant east-west", `${fmt.num(100 * d.dec.horizontal_share, 1)} %`],
          ]
        : [],
  },
  {
    title: "What one geometry gets wrong",
    goal: "Measure how far the vertical projection of a single product is from the true vertical.",
    what: [
      "For every cell, the vertical projection of each product (v_LOS / l_u) is set against the decomposed vertical. On the diagonal, the product alone was right; off it, east-west motion was taken for vertical.",
      "An eastward motion e adds e · l_e / l_u to the vertical projection: about +0.8·e for a descending Sentinel-1 track and −0.8·e for an ascending one. The two products err in opposite directions.",
    ],
    formula: ["v_LOS / l_u = u + e · l_e / l_u"],
    look: ["Points far from the diagonal mark where the analyses of one product (zoning, lines, buildings) read a wrong vertical."],
    needs: "decompose",
    figures: [{ caption: "Vertical projection of each product against the decomposed vertical, one dot per cell; dashed: the diagonal.", render: (d) => <BiasScatter d={d.decCells!} /> }],
    numbers: (d) =>
      Object.entries(d.dec?.vertical_only_bias ?? {}).map(([id, b]) => {
        const p = d.dec!.products.find((x) => x.id === id);
        return [`${p?.track ?? id}: ${t("off by, 90 % of cells")}`, `${b.p90_abs_mm_yr} mm/yr`] as [string, string];
      }),
  },
  {
    title: "Soft soil under the cells",
    goal: "Bring in what decides how much the ground can sink: the thickness of the compressible layer.",
    what: [
      "In a delta, sinking comes from the compaction of young, soft clay and peat (in Hanoi the Holocene Hai Hung and Thai Binh formations) and of the aquitards between the aquifers. Under the same drop of the water table, a thicker soft layer sinks more.",
      "GeoEyes reads the thickness from the project when it has one: a map (GeoTIFF) or boreholes (CSV of lon, lat, thickness_m, interpolated by inverse distance up to 3 km from the nearest borehole).",
      "Without them it falls back on the open global grid of Pelletier et al. (2016): the thickness of the deposits above bedrock, 1 km, capped at 50 m. It is not the soft layer, and in a delta most cells read the cap; it is a placeholder that shows where a real map would go.",
    ],
    formula: ["[postprocess.geology] raster = \"geom/soft_soil.tif\"", "[postprocess.geology] boreholes = \"geom/boreholes.csv\""],
    look: ["Layer “Soft-soil thickness” on the Thematic analysis page; its legend names the source."],
    layer: "soft_soil",
    needs: "geology",
    figures: [
      {
        caption: "Soft-soil thickness of the cells.",
        render: (d) => (
          <>
            <CellMap c={d.cells!} kind="soft_soil" soil={d.geoCells} />
            <div className="mt-1 max-w-[360px]">
              <div className="h-2 rounded-sm" style={{ background: `linear-gradient(90deg,${SOIL_RGB.map((x) => rgb(x)).join(",")})` }} />
              <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
                <span>{d.geo?.thickness_m?.min ?? "–"}</span>
                <span>m</span>
                <span>{d.geo?.thickness_m?.max ?? "–"}</span>
              </div>
            </div>
          </>
        ),
      },
    ],
    numbers: (d) =>
      d.geo
        ? [
            ["Source", t(d.geo.source_label)],
            ["Cells with a value", `${fmt.int(d.geo.covered)} / ${fmt.int(d.geo.cells)}`],
            ["Thickness, median", d.geo.thickness_m ? `${d.geo.thickness_m.median} m` : "–"],
          ]
        : [],
  },
  {
    title: "Thickness and sinking",
    goal: "Check whether the cells sink faster where the soft soil is thicker, and whether the consolidation fits the thickness.",
    what: [
      "The sinking cells are grouped by thickness class (quantiles); for each class, the median rate and the share of cells moving faster than 5 mm/yr. The rank correlation (Spearman ρ) between thickness and sinking sums it up.",
      "For the consolidating cells of chapter 4, Terzaghi's theory ties the time constant to the drainage path: τ = 4·H_dr² / (π²·c_v). The thickness then implies a coefficient of consolidation c_v. Soft clays have 0.1–10 m²/yr (Holtz & Kovacs 1981): a value far outside means that the thickness is not that of the consolidating layer, or that the cell is not consolidating.",
    ],
    formula: ["c_v = 4 · H_dr² / (π² · τ),   H_dr = H / 2 (drained on both faces)"],
    look: ["A real soft-soil map should raise ρ and bring c_v into the range of clays; the open grid will not."],
    layer: "soft_soil",
    needs: "geology",
    figures: [{ caption: "Median rate of the sinking cells and share of moving cells, per thickness class.", render: (d) => <ClassChart s={d.geo!} /> }],
    numbers: (d) =>
      d.geo
        ? [
            ["Spearman ρ", d.geo.spearman_rho != null ? String(d.geo.spearman_rho) : "–"],
            ["Sinking cells", fmt.int(d.geo.sinking_cells)],
            ["Implied c_v, median", d.geo.consolidation_cv.median_m2_yr != null ? `${fmt.num(d.geo.consolidation_cv.median_m2_yr, 1)} m²/yr` : "–"],
            ["Within the range of clays", d.geo.consolidation_cv.within_range_share != null ? `${Math.round(100 * d.geo.consolidation_cv.within_range_share)} %` : "–"],
          ]
        : [],
  },
  {
    title: "Limits and checks",
    goal: "Know what the decomposition and the soft-soil layer can and cannot say.",
    what: [
      "Decomposition: the two products must cover the same period, or constant rates are assumed. North-south motion is ignored. The result is relative to the median motion of the common area: tie it to a GNSS station for absolute values. A short series of one product (a few weeks) makes its velocity, and the east-west motion, noisy.",
      "Soft soil: the open grid is a placeholder. A map of the Holocene thickness or the boreholes of the area (geological survey, universities, construction records) are needed before any reading of the relation.",
      "Checks that would make them firmer: GNSS stations with their horizontal velocities, a third geometry (another track or sensor), levelling, and boreholes near the cells that sink fastest.",
    ],
    look: ["Prefer the decomposed vertical wherever two geometries exist; set a soft-soil map in the project as soon as one is available."],
    figures: [],
  },
];

// ------------------------------------------------------------------ page
export function GeometryChapter({ ws, step }: { ws: Workspace | undefined; step?: number }) {
  const qc = useQueryClient();
  const k = Math.min(STEPS.length - 1, Math.max(0, step ?? 0));
  const S = STEPS[k];
  const go = (i: number) => (window.location.hash = href({ page: "learn", chapter: "geometry", step: i }));

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
  // by default the product with both analyses, the decomposition over the longest common period first
  const score = (p: (typeof products)[number]) => {
    const st = statuses[products.indexOf(p)].data;
    const common = Math.min(...(st?.decompose.summary?.products.slice(1).map((x) => x.overlap_days ?? 0) ?? [0]));
    return (st?.decompose.summary ? 2 + Math.min(1, common / 365) : 0) + (st?.geology.summary ? 1 : 0) + 0.5 * Math.abs(st?.geology.summary?.spearman_rho ?? 0);
  };
  const [choice, setChoice] = useState("");
  const sel = ready.find((p) => p.product === choice) ?? [...ready].sort((a, b) => score(b) - score(a))[0];
  const st = sel ? statuses[products.indexOf(sel)] : undefined;
  const hz = sel ? zoned[products.indexOf(sel)].data?.summary : undefined;
  const dec = st?.data?.decompose.summary ?? undefined;
  const geo = st?.data?.geology.summary ?? undefined;
  const running = !!(st?.data?.decompose.running || st?.data?.geology.running);
  useEffect(() => {
    if (!running || !sel) return;
    const id = window.setInterval(() => qc.invalidateQueries({ queryKey: ["behaviour", sel.project, sel.product] }), 2000);
    return () => window.clearInterval(id);
  }, [running, sel, qc]);

  const decCells = useQuery({
    queryKey: ["decompose-cells-learn", sel?.project, sel?.product, dec?.created],
    queryFn: async (): Promise<Dec> => {
      const { meta, buf } = await api.decomposeCells(sel!.project, sel!.product);
      return { meta, buf, F: meta.fields.length, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!sel && !!dec && S.needs === "decompose" && k > 0,
    staleTime: Infinity,
  });
  const cells = useQuery({
    queryKey: ["hazard-cells", sel?.project, sel?.product, hz?.created],
    queryFn: async (): Promise<Cells> => {
      const { meta, buf } = await api.hazardCells(sel!.project, sel!.product);
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!sel && !!hz && S.needs === "geology",
    staleTime: Infinity,
  });
  const geoCells = useQuery({
    queryKey: ["geology-cells", sel?.project, sel?.product, geo?.created],
    queryFn: async (): Promise<Geology> => {
      const { meta, buf } = await api.geologyCells(sel!.project, sel!.product);
      return { buf, min: meta.summary.thickness_m?.min ?? 0, max: meta.summary.thickness_m?.max ?? 1 };
    },
    enabled: !!sel && !!geo && S.needs === "geology",
    staleTime: Infinity,
  });

  const data: Data | undefined = sel && { dec, decCells: decCells.data, geo, cells: cells.data, geoCells: geoCells.data };
  const missing = S.needs === "decompose" ? !dec : S.needs === "geology" ? !geo : false;
  const loading = S.needs === "decompose" ? k > 0 && !decCells.data : S.needs === "geology" ? k === 3 && (!cells.data || !geoCells.data) : false;
  const run = async (kind: "decompose" | "geology") => {
    if (!sel) return;
    await api.analysisRun(sel.project, sel.product, kind);
    await qc.invalidateQueries({ queryKey: ["behaviour", sel.project, sel.product] });
  };

  let fig = 0;
  return (
    <div className="flex h-full min-h-0">
      <ChapterNav current="geometry" steps={STEPS.map((s) => s.title)} step={k} onStep={go} />
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
                  <div className="mt-4 max-w-[860px] rounded-lg border-l-4 border-accent bg-panel px-4 py-3 font-mono text-[14px] leading-loose whitespace-pre text-ink">
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
                      <p className="m-0">
                        {S.needs === "decompose"
                          ? t("The vertical and east-west motion of this product are not separated yet: it needs a product of the workspace that sees the area from the other side over the same period.")
                          : t("The soft-soil thickness of this product is not read yet.")}
                      </p>
                      <Button variant="primary" disabled={running} onClick={() => run(S.needs!)}>
                        {running ? t("Running…") : S.needs === "decompose" ? t("Separate vertical and east-west") : t("Read the soft-soil thickness")}
                      </Button>
                      {S.needs === "decompose" && st?.data?.decompose.failed && <p className="m-0 text-bad">{st.data.decompose.log.slice(-1)[0]}</p>}
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
                                {t("Figure")} 5.{k}.{fig}.
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
                {t("Full method, sources and research plan:")} docs/{lang()}/research/two-geometries-and-soft-soil.md
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
              {data && S.numbers && !missing && S.numbers(data).length > 0 && (
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
