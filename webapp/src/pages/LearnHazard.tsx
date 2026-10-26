// Principles, chapter 2: how the hazard map of the Thematic analysis page is made (geoeyes.hazard), one step per
// page, written as a wiki article and illustrated with the real cells of a hazard zoning already run in the
// workspace (maps of the cells, distributions with the thresholds, the series of a typical cell).
// Method, defaults and sources: docs/en/research/rainfall-insar-hazard.md and groundwater-insar.md.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type HazardCell, type HazardSummary, type Workspace } from "../api";
import { ChapterNav } from "../components/LearnKit";
import { lang, t } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { CellChart, cellColor, DEFAULT_MATRIX, LEVEL_RGB, LEVELS, Legend, MatrixFigure, rgb, type Cells, type RGB, type View } from "./Hazard";

// ------------------------------------------------------------------ figures
type MapKind = View | "points" | "slope";

const VIRIDIS: RGB[] = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
const SLOPE: RGB[] = [[26, 152, 80], [145, 207, 96], [254, 224, 139], [252, 141, 89], [215, 48, 39]];

function ramp(stops: RGB[], x: number): RGB {
  const v = Math.min(1, Math.max(0, x)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(v));
  const f = v - i;
  return [0, 1, 2].map((k) => stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) as RGB;
}

/** The cells of the zoning on a canvas, as squares on a local metric grid (no base map). */
function CellMap({ c, kind }: { c: Cells; kind: MapKind }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const F = c.meta.fields.length;
  const g = (i: number, name: string) => c.buf[i * F + c.f[name]];
  const kx = 111_320 * Math.cos((c.meta.lat0 * Math.PI) / 180);
  const geo = useMemo(() => {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < c.meta.n; i++) {
      const x = g(i, "dlon") * kx;
      const y = g(i, "dlat") * 110_540;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    return { x0, x1, y0, y1 };
  }, [c]); // eslint-disable-line react-hooks/exhaustive-deps
  const W = 760;
  const cell = c.meta.cell_m;
  const span = Math.max(geo.x1 - geo.x0 + cell, geo.y1 - geo.y0 + cell);
  const s = W / span;
  const H = Math.round((geo.y1 - geo.y0 + cell) * s);
  const Wd = Math.round((geo.x1 - geo.x0 + cell) * s);
  useEffect(() => {
    const el = cv.current;
    if (!el) return;
    el.width = Wd;
    el.height = H;
    const ctx = el.getContext("2d")!;
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, Wd, H);
    const n = c.meta.n;
    const maxPts = Math.log10(Math.max(...Array.from({ length: n }, (_, i) => g(i, "n_points"))) || 10);
    const px = Math.max(1, Math.ceil(cell * s));
    for (let i = 0; i < n; i++) {
      let col: RGB;
      let a = 1;
      if (kind === "points") col = ramp(VIRIDIS, Math.log10(g(i, "n_points")) / maxPts);
      else if (kind === "slope") {
        const v = g(i, "slope_deg");
        col = Number.isFinite(v) ? ramp(SLOPE, v / 30) : [75, 90, 115];
      } else {
        const [r, gg, b, al] = cellColor(c, i, kind);
        col = [r, gg, b];
        a = al / 255;
      }
      ctx.fillStyle = rgb(col, a);
      ctx.fillRect(Math.floor((g(i, "dlon") * kx - geo.x0) * s), Math.floor(H - (g(i, "dlat") * 110_540 - geo.y0 + cell) * s), px, px);
    }
  }, [c, kind, geo, Wd, H, s, cell]); // eslint-disable-line react-hooks/exhaustive-deps
  const km = Math.max(1, Math.round(span / 5000));
  return (
    <div className="relative w-full max-w-[620px] overflow-hidden rounded-lg border border-line">
      <canvas ref={cv} className="block h-auto w-full" />
      <div className="absolute bottom-2 left-2 rounded bg-black/50 px-1.5 py-0.5 font-mono text-[10.5px] text-white">
        <span className="inline-block border-x border-b border-white align-middle" style={{ width: (km * 1000 * s * 100) / Wd + "%", minWidth: 20, height: 5 }} /> {km} km
      </div>
    </div>
  );
}

/** A histogram of ``values`` with vertical threshold lines. */
function Histogram({
  values,
  lo,
  hi,
  bins = 40,
  lines = [],
  unit,
  log = false,
  color = () => "#4cc2ff",
}: {
  values: number[];
  lo: number;
  hi: number;
  bins?: number;
  lines?: { at: number; label: string }[];
  unit: string;
  log?: boolean;
  color?: (x: number) => string;
}) {
  const tf = (v: number) => (log ? Math.log10(v) : v);
  const a = tf(lo);
  const b = tf(hi);
  const counts = new Array(bins).fill(0);
  for (const v of values) {
    if (!Number.isFinite(v) || (log && v <= 0)) continue;
    const k = Math.floor(((tf(v) - a) / (b - a)) * bins);
    counts[Math.min(bins - 1, Math.max(0, k))]++;
  }
  const max = Math.max(1, ...counts);
  const Wd = 760;
  const H = 150;
  const X = (v: number) => 30 + ((tf(v) - a) / (b - a)) * (Wd - 40);
  const bw = (Wd - 40) / bins;
  const fmtv = (v: number) => (log ? `1/${Math.round(1 / v)}` : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(v % 1 ? 1 : 0));
  return (
    <svg viewBox={`0 0 ${Wd} ${H + 26}`} className="w-full">
      <line x1={30} x2={Wd - 10} y1={H} y2={H} stroke="#22324d" />
      {counts.map((n, i) => {
        const h = (n / max) * (H - 14);
        const mid = a + ((i + 0.5) / bins) * (b - a);
        return <rect key={i} x={30 + i * bw + 0.5} y={H - h} width={Math.max(1, bw - 1)} height={h} fill={color(log ? 10 ** mid : mid)} opacity={0.9} />;
      })}
      {lines.map((l) => (
        <g key={l.label}>
          <line x1={X(l.at)} x2={X(l.at)} y1={6} y2={H} stroke="#ffd34d" strokeDasharray="4 3" />
          <text x={X(l.at) + 3} y={14} fill="#ffd34d" fontSize="11">
            {l.label}
          </text>
        </g>
      ))}
      <text x={30} y={H + 16} fill="#93a4bf" fontSize="11">
        {fmtv(lo)}
      </text>
      <text x={Wd - 10} y={H + 16} fill="#93a4bf" fontSize="11" textAnchor="end">
        {fmtv(hi)}
      </text>
      <text x={(Wd + 20) / 2} y={H + 16} fill="#93a4bf" fontSize="11" textAnchor="middle">
        {t(unit)} · {t("cells")}
      </text>
    </svg>
  );
}

function ColorBar({ stops, lo, hi, unit }: { stops: RGB[]; lo: string; hi: string; unit: string }) {
  return (
    <div className="mt-1 max-w-[360px]">
      <div className="h-2 rounded-sm" style={{ background: `linear-gradient(90deg,${stops.map((c) => rgb(c)).join(",")})` }} />
      <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
        <span>{lo}</span>
        <span>{t(unit)}</span>
        <span>{hi}</span>
      </div>
    </div>
  );
}

/** Groundwater storage anomaly of the pixel of a cell, by month. */
function StorageChart({ c }: { c: HazardCell }) {
  const g = c.groundwater;
  if (!g) return null;
  const v = g.anomaly_mm.map((x) => (x == null ? NaN : x));
  const ok = v.filter(Number.isFinite);
  if (!ok.length) return null;
  const lo = Math.min(...ok);
  const hi = Math.max(...ok);
  const Wd = 760;
  const H = 150;
  const X = (i: number) => 40 + (i / Math.max(1, v.length - 1)) * (Wd - 50);
  const Y = (x: number) => 10 + (1 - (x - lo) / (hi - lo || 1)) * (H - 30);
  const d = v.map((x, i) => (Number.isFinite(x) ? `${i && Number.isFinite(v[i - 1]) ? "L" : "M"}${X(i).toFixed(1)},${Y(x).toFixed(1)}` : "")).join("");
  return (
    <svg viewBox={`0 0 ${Wd} ${H}`} className="w-full">
      <line x1={40} x2={Wd - 10} y1={Y(0)} y2={Y(0)} stroke="#22324d" strokeDasharray="3 3" />
      <path d={d} fill="none" stroke="#7ee0c3" strokeWidth="2" />
      <text x={34} y={Y(hi) + 4} fill="#93a4bf" fontSize="11" textAnchor="end">
        {hi.toFixed(0)}
      </text>
      <text x={34} y={Y(lo) + 4} fill="#93a4bf" fontSize="11" textAnchor="end">
        {lo.toFixed(0)}
      </text>
      <text x={40} y={H - 2} fill="#93a4bf" fontSize="11">
        {g.months[0]}
      </text>
      <text x={Wd - 10} y={H - 2} fill="#93a4bf" fontSize="11" textAnchor="end">
        {g.months[g.months.length - 1]}
      </text>
      <text x={(Wd + 30) / 2} y={H - 2} fill="#93a4bf" fontSize="11" textAnchor="middle">
        {t("storage anomaly, mm of water")}
      </text>
    </svg>
  );
}

/** Differential settlement between two neighbouring cells: the angular distortion β. */
function DistortionFigure() {
  return (
    <svg viewBox="0 0 600 220" className="w-full max-w-[620px]" role="img" aria-label={t("Angular distortion between two cells")}>
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0 10 5 0 10z" fill="#93a4bf" />
        </marker>
      </defs>
      <line x1="40" y1="120" x2="560" y2="120" stroke="#93a4bf" strokeDasharray="5 5" />
      <path d="M40 120 L200 122 L400 158 L560 160" fill="none" stroke="#f5b84b" strokeWidth="3" />
      <rect x="170" y="62" width="60" height="58" fill="#1a2740" stroke="#93a4bf" />
      <rect x="370" y="98" width="60" height="58" fill="#1a2740" stroke="#93a4bf" transform="rotate(4 400 158)" />
      <text x="200" y="56" fill="#e6edf7" fontSize="14" textAnchor="middle">a</text>
      <text x="400" y="90" fill="#e6edf7" fontSize="14" textAnchor="middle">b</text>
      <line x1="455" y1="122" x2="455" y2="157" stroke="#93a4bf" markerEnd="url(#arr)" />
      <text x="463" y="144" fill="#93a4bf" fontSize="13">Δs = |v_a − v_b| · T</text>
      <line x1="200" y1="190" x2="400" y2="190" stroke="#93a4bf" markerStart="url(#arr)" markerEnd="url(#arr)" />
      <text x="300" y="210" fill="#93a4bf" fontSize="13" textAnchor="middle">L ({t("distance between the cell centres")})</text>
      <text x="40" y="140" fill="#93a4bf" fontSize="12">{t("ground at the first date")}</text>
      <text x="560" y="178" fill="#f5b84b" fontSize="12" textAnchor="end">{t("after T years")}</text>
    </svg>
  );
}

// ------------------------------------------------------------------ the data of the illustrations
interface Data {
  s: HazardSummary;
  c: Cells;
  col: (name: string) => number[];
  label: string;
  project: string;
  product: string;
}

interface Fig {
  caption: string;
  render: (d: Data, example: HazardCell | undefined) => ReactNode;
}

interface Step {
  title: string;
  goal: string;
  what: string[];
  formula?: string[];
  look: string[];
  figures: Fig[];
  numbers?: (d: Data) => [string, string][];
  example?: "rain" | "gw";
  doc?: string;
}

const pct = (n: number, of: number) => (of ? `${((100 * n) / of).toFixed(0)} %` : "–");
const quant = (v: number[], q: number) => {
  const s = v.filter(Number.isFinite).sort((a, b) => a - b);
  return s.length ? s[Math.min(s.length - 1, Math.floor(q * s.length))] : NaN;
};
const count = (v: number[], f: (x: number) => boolean) => v.reduce((n, x) => n + (f(x) ? 1 : 0), 0);

function viewMap(kind: MapKind, legend: boolean): Fig["render"] {
  return (d) => (
    <>
      <CellMap c={d.c} kind={kind} />
      {legend && kind !== "points" && kind !== "slope" && (
        <div className="max-w-[460px]">
          <Legend view={kind} s={d.s} />
        </div>
      )}
      {kind === "points" && <ColorBar stops={VIRIDIS} lo="1" hi={String(Math.max(...d.col("n_points")))} unit="points per cell (log)" />}
      {kind === "slope" && <ColorBar stops={SLOPE} lo="0°" hi="≥ 30°" unit="slope" />}
    </>
  );
}

const STEPS: Step[] = [
  {
    title: "Analysis cells",
    goal: "Group the persistent scatterers into square cells, so that each cell has one robust series.",
    what: [
      "The points of a product are irregular and noisy one by one. GeoEyes groups them into square cells (100 m by default) on a local metric grid and keeps the cells with at least a few points (3 by default).",
      "Each cell gets the median series of its points and the median of their line-of-sight vectors: one outlier point cannot move the cell.",
      "100 m matches the scale of a building block and of the differential settlement that damages buildings; a finer cell holds fewer points, a coarser one averages away local bowls.",
    ],
    formula: ["d_cell(t) = median of d_i(t) over the points of the cell"],
    look: ["On the Thematic analysis page, grey cells hold too few points.", "The cell size is a parameter of the run: Cell, 50 to 500 m."],
    figures: [
      { caption: "The cells of the product, coloured by the number of points they hold: dense in built-up areas, sparse in fields and water.", render: viewMap("points", true) },
      {
        caption: "How many points the cells hold.",
        render: (d) => <Histogram values={d.col("n_points")} lo={1} hi={Math.max(10, quant(d.col("n_points"), 0.99))} unit="points per cell" lines={[{ at: Number(d.s.params.min_points ?? 3), label: `min ${d.s.params.min_points ?? 3}` }]} />,
      },
    ],
    numbers: (d) => {
      const n = d.col("n_points");
      return [
        ["Cells", fmt.int(d.s.n_cells)],
        ["Points in the cells", fmt.int(d.s.n_points)],
        ["Points per cell, median", String(quant(n, 0.5))],
        ["Cell size", `${d.s.params.cell_m} m`],
      ];
    },
  },
  {
    title: "Terrain and process",
    goal: "Decide for each cell whether it is assessed for subsidence or for a slow landslide.",
    what: [
      "The slope of the DEM, smoothed to the cell size, decides which process a cell is assessed for.",
      "Flat cells (slope below 10°) are assessed for subsidence: vertical motion. Steeper cells are assessed for slow landslides: motion down the slope.",
      "The 10° rule follows the ADAtools practice (landslides above 5°, subsidence below 10°); the upper bound keeps the steep edges of buildings in a surface model out of the landslide class.",
    ],
    formula: ["slope = arctan |∇h|", "landslide if slope ≥ 10°, otherwise subsidence"],
    look: ["Layer “Mode”: blue = subsidence, orange = landslide."],
    figures: [
      { caption: "Slope of the DEM at the cell scale.", render: viewMap("slope", true) },
      {
        caption: "Distribution of the slope: cells right of the 10° line are assessed as landslides.",
        render: (d) => <Histogram values={d.col("slope_deg")} lo={0} hi={30} unit="°" lines={[{ at: 10, label: "10°" }]} color={(x) => rgb(ramp(SLOPE, x / 30))} />,
      },
      { caption: "The process each cell is assessed for.", render: viewMap("mode", true) },
    ],
    numbers: (d) => {
      const m = d.col("mode");
      return [
        ["Subsidence cells", `${fmt.int(count(m, (x) => x === 0))} (${pct(count(m, (x) => x === 0), m.length)})`],
        ["Landslide cells", `${fmt.int(count(m, (x) => x > 0))} (${pct(count(m, (x) => x > 0), m.length)})`],
        ["Median slope", `${quant(d.col("slope_deg"), 0.5).toFixed(1)}°`],
      ];
    },
  },
  {
    title: "Motion in the hazard direction",
    goal: "Turn the line-of-sight motion into the motion that matters for each process.",
    what: [
      "InSAR measures motion along the line of sight only. Each cell's series is projected on the direction that matters: vertical for subsidence, down the slope for landslides.",
      "Where the slope faces away from the satellite or runs along the orbit, the projection is small and would amplify the noise: below a sensitivity of 0.3 the cell is not assessed (Cigna et al. 2013).",
      "Sign: as everywhere in GeoEyes, negative means sinking or moving down the slope, positive means uplift or apparent upslope motion. The classes use how fast the cell moves in the hazard direction.",
    ],
    formula: ["d_vertical = d_LOS / u_LOS", "d_downslope = d_LOS / (s · u_LOS)", "assessed if |s · u_LOS| ≥ 0.3"],
    look: ["Layer “Rate”: red = sinking or downslope, blue = uplift or apparent upslope motion."],
    figures: [
      { caption: "Rate of each cell in the hazard direction.", render: viewMap("rate", true) },
      {
        caption: "Distribution of the rates; the band around zero is the stability floor (±2 mm/yr).",
        render: (d) => {
          const r = d.col("rate_mm_yr");
          const m = Math.max(5, Math.abs(quant(r, 0.01)), Math.abs(quant(r, 0.99)));
          return <Histogram values={r} lo={-m} hi={m} unit="mm/yr" lines={[{ at: -2, label: "−2" }, { at: 2, label: "+2" }]} color={(x) => (x <= -2 ? "#d6604d" : x >= 2 ? "#4393c3" : "#7f8ba0")} />;
        },
      },
    ],
    numbers: (d) => {
      const r = d.col("rate_mm_yr");
      return [
        ["Rate, 5th percentile", `${fmt.vel(quant(r, 0.05))} ${t("mm/yr")}`],
        ["Rate, median", `${fmt.vel(quant(r, 0.5))} ${t("mm/yr")}`],
        ["Rate, 95th percentile", `${fmt.vel(quant(r, 0.95))} ${t("mm/yr")}`],
        ["Reference", t(d.s.reference.kind)],
        ["Moving against the hazard direction", fmt.int(d.s.opposite_motion_cells)],
      ];
    },
  },
  {
    title: "Intensity",
    goal: "Rate how fast each cell moves, in four classes.",
    what: [
      "A linear fit (with an acceleration when the series is long enough) gives the rate of each cell in the hazard direction and its standard error σ.",
      "Stable (I0): below max(2 mm/yr, 2σ) (Barra et al. 2017). Subsidence classes I1–I3 break at 10 and 30 mm/yr; landslide classes follow Cruden & Varnes (1996): extremely slow below 16 mm/yr, very slow up to 160 mm/yr.",
      "A cell goes up one class if it accelerates significantly, or if its motion follows the rain and a dry or wet year would make it faster.",
    ],
    formula: ["I0: |v| < max(2, 2σ)", "subsidence, on the sinking rate −v: I1 < 10 ≤ I2 < 30 ≤ I3 (mm/yr)", "landslide, on the downslope rate −v: I1 < 16 ≤ I2 < 160 ≤ I3 (mm/yr)"],
    look: ["Layer “Intensity (InSAR)”.", "Rates are relative to the product's reference: tie them to GNSS or to a stable area for absolute classes."],
    figures: [
      { caption: "Intensity class of each cell.", render: viewMap("intensity", true) },
      {
        caption: "Sinking rates against the class limits of subsidence.",
        render: (d) => {
          const r = d.col("rate_mm_yr").filter((x) => x < 0).map((x) => -x);        // sinking rate
          return <Histogram values={r} lo={0} hi={Math.max(35, quant(r, 0.995))} unit="mm/yr of sinking" lines={[{ at: 2, label: "I1" }, { at: 10, label: "I2" }, { at: 30, label: "I3" }]} color={(x) => rgb(x >= 30 ? [215, 48, 39] : x >= 10 ? [252, 141, 89] : x >= 2 ? [254, 224, 139] : [75, 90, 115])} />;
        },
      },
    ],
    numbers: (d) => {
      const i = d.col("intensity");
      return [
        ...[0, 1, 2, 3].map((k) => [`I${k}`, `${fmt.int(count(i, (x) => x === k))} (${pct(count(i, (x) => x === k), i.length)})`] as [string, string]),
        ["Accelerating cells", fmt.int(d.s.accelerating_cells)],
      ];
    },
  },
  {
    title: "Damage potential",
    goal: "Assess how much the motion can damage buildings over time (subsidence), or how steep the moving ground is (landslides).",
    what: [
      "Subsidence: what damages a building is the difference of settlement between its parts. GeoEyes computes the angular distortion β between neighbouring cells, accumulated over the horizon (10 years by default).",
      "Limits from building damage studies: 1/500 safe limit (Bjerrum 1963), 1/300 cracking, 1/150 structural damage (Skempton & MacDonald 1956).",
      "Landslides: the slope classes 15°, 25° and 35° stand in for a susceptibility map until one is given.",
      "β only uses differences between cells: it does not depend on the reference of the product.",
    ],
    formula: ["β = |v_a − v_b| · T / L", "S1 ≥ 1/500, S2 ≥ 1/300, S3 ≥ 1/150"],
    look: ["Layer “Damage potential”."],
    figures: [
      { caption: "The angular distortion: differential settlement Δs over the distance L between two cells.", render: () => <DistortionFigure /> },
      { caption: "Damage potential of each cell.", render: viewMap("secondary", true) },
      {
        caption: "Angular distortion of the subsidence cells over the horizon, against the damage limits (log scale).",
        render: (d) => {
          const b = d.col("angular_distortion").filter((x) => x > 0);
          return <Histogram values={b} lo={1 / 20000} hi={1 / 50} log unit="β" lines={[{ at: 1 / 500, label: "1/500" }, { at: 1 / 300, label: "1/300" }, { at: 1 / 150, label: "1/150" }]} color={(x) => rgb(x >= 1 / 150 ? [118, 42, 131] : x >= 1 / 300 ? [153, 112, 171] : x >= 1 / 500 ? [194, 165, 207] : [75, 90, 115])} />;
        },
      },
    ],
    numbers: (d) => {
      const s = d.col("secondary");
      const b = d.col("angular_distortion").filter((x) => x > 0);
      const p95 = quant(b, 0.95);
      return [
        ...[0, 1, 2, 3].map((k) => [`S${k}`, `${fmt.int(count(s, (x) => x === k))} (${pct(count(s, (x) => x === k), s.length)})`] as [string, string]),
        ["β, 95th percentile", Number.isFinite(p95) && p95 > 0 ? `1/${Math.round(1 / p95)}` : "–"],
      ];
    },
  },
  {
    title: "Hazard matrix",
    goal: "Combine how fast the ground moves with what the motion can do.",
    what: [
      "The level crosses the intensity (rows) with the damage potential (columns), as in the PSI-based matrix approach (Cigna et al. 2013).",
      "Fast motion where it bends buildings, or on steep ground, comes first; slow motion on flat, uniform ground stays low.",
      "The matrix can be changed per project ([postprocess.hazard] matrix).",
    ],
    look: ["Layer “Hazard level”: red cells need attention first.", "The same matrix sits next to the legend on the Thematic analysis page."],
    figures: [
      {
        caption: "The hazard matrix: intensity (rows) × damage potential (columns) → level.",
        render: (d) => (
          <div className="w-fit rounded-xl border border-line bg-panel p-4">
            <MatrixFigure matrix={(d.s.params.matrix as number[][]) ?? DEFAULT_MATRIX} />
          </div>
        ),
      },
      {
        caption: "The hazard level of each cell: the result of the zoning.",
        render: (d) => (
          <>
            <CellMap c={d.c} kind="hazard" />
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
    ],
    numbers: (d) =>
      [4, 3, 2, 1, 0].map((lv) => {
        const by = d.s.by_level as Record<string, Record<string, { km2: number } | number>>;
        const km2 = ["subsidence", "landslide"].reduce((a, m) => a + (((by[m]?.[LEVELS[lv].toLowerCase()] as { km2: number } | undefined)?.km2) ?? 0), 0);
        return [LEVELS[lv], `${km2.toFixed(2)} km²`];
      }),
  },
  {
    title: "Rainfall coupling",
    goal: "Test whether the motion of each cell follows the rainfall, and with what delay.",
    what: [
      "Rainfall: CHIRPS v3 monthly per pixel (ERA5 when CHIRPS cannot be read).",
      "If the rate of motion follows the rainfall anomaly with a delay τ, the displacement follows the cumulative rainfall departure (CRD). b is the trend without the rain, k the sensitivity, τ the lag (0 to 6 months).",
      "Significance: the lag search is repeated on phase-randomised rainfall (same spectrum, random timing; Ebisuzaki 1997), and the false discovery rate is controlled over the whole map (Benjamini & Hochberg 1995).",
      "Where the coupling is significant, the rates of a dry (P10) and a wet (P90) year of the 1991–2020 climate are computed; the worse one can raise the intensity.",
    ],
    formula: ["CRD(t) = Σ (P_month − P̄)", "d(t) = a + b·t + k·CRD(t − τ) + ε"],
    look: ["Layers “Rain coupling” and “Rain lag”; the cell panel shows the rainfall and the fitted model."],
    example: "rain",
    figures: [
      { caption: "Cells whose motion follows the rainfall (significant after the false discovery rate); grey: no detectable link.", render: viewMap("coupling", true) },
      {
        caption: "The cell with the strongest link to the rainfall: its series, the linear trend, the rainfall model and the monthly rainfall of its pixel.",
        render: (_d, ex) => (ex ? <CellChart c={ex} /> : <p className="text-[12.5px] text-muted">{t("Loading the example cell…")}</p>),
      },
    ],
    numbers: (d) => [
      ["Cells tested", fmt.int(d.s.coupling.cells_tested)],
      ["Significant (FDR)", fmt.int(d.s.coupling.cells_significant)],
      ["p < 0.05 before the correction", fmt.int(d.s.coupling.cells_p_below_alpha)],
      ["Median lag", d.s.coupling.lag_months_median == null ? "–" : `${d.s.coupling.lag_months_median} ${t("months")}`],
    ],
  },
  {
    title: "Groundwater coupling",
    goal: "Test whether the motion follows the groundwater storage of the region.",
    what: [
      "Groundwater storage from NASA GLDAS (Catchment model with GRACE satellite gravity assimilated), 0.25°, averaged by month.",
      "The same test with the storage in place of the CRD. g > 0 means ground that rises and falls with the storage (sinking when it falls): the elastic response of an aquifer.",
      "A regional diagnostic: the storage grid is about 27 km, so it explains when the ground moves, not where. It does not change the hazard level.",
    ],
    formula: ["d(t) = a + b·t + g·GWS(t − τ) + ε"],
    look: ["Layer “Groundwater coupling”; it needs an Earthdata login (EARTHDATA_TOKEN)."],
    example: "gw",
    doc: "groundwater-insar.md",
    figures: [
      { caption: "Cells whose motion follows the groundwater storage; grey: no detectable link or not assessed.", render: viewMap("groundwater", true) },
      {
        caption: "Groundwater storage of the pixel of a typical cell, by month (departure from its mean).",
        render: (_d, ex) => (ex?.groundwater ? <StorageChart c={ex} /> : <p className="text-[12.5px] text-muted">{t("No groundwater in this zoning: run it again with an Earthdata login.")}</p>),
      },
    ],
    numbers: (d) => {
      const g = d.s.groundwater;
      if (!g?.used) return [["Groundwater", t("not used")]];
      return [
        ["Cells tested", fmt.int(g.cells_tested ?? 0)],
        ["Significant (FDR)", fmt.int(g.cells_significant ?? 0)],
        ["Storage trend", g.trend_mm_yr == null ? "–" : `${fmt.vel(g.trend_mm_yr)} mm/yr`],
        ["Storage published up to", g.months?.length ? g.months[g.months.length - 1] : "–"],
      ];
    },
  },
];

// ------------------------------------------------------------------ page
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="m-0 border-b border-line pb-1.5 text-[16px] font-semibold text-ink">{t(title)}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function useExample(d: Data | undefined, kind: "rain" | "gw" | undefined) {
  const i = useMemo(() => {
    if (!d || !kind) return -1;
    const r = d.col(kind === "rain" ? "rain_r" : "gw_r");
    const on = d.col(kind === "rain" ? "rain_coupled" : "gw_coupled");
    let best = -1;
    let bv = -1;
    for (let k = 0; k < r.length; k++) {
      const v = Math.abs(r[k]) + (on[k] > 0 ? 10 : 0);
      if (Number.isFinite(r[k]) && v > bv) {
        bv = v;
        best = k;
      }
    }
    if (best < 0) {
      // nothing assessed: the cell with the most points still shows the storage of its pixel
      const n = d.col("n_points");
      best = n.indexOf(Math.max(...n));
    }
    return best;
  }, [d, kind]);
  return useQuery({
    queryKey: ["hazard-cell", d?.project, d?.product, i, d?.s.created],
    queryFn: () => api.hazardCell(d!.project, d!.product, i),
    enabled: !!d && i >= 0,
    staleTime: Infinity,
  }).data;
}

export function HazardChapter({ ws, step }: { ws: Workspace | undefined; step?: number }) {
  const k = Math.min(STEPS.length - 1, Math.max(0, step ?? 0));
  const S = STEPS[k];
  const go = (i: number) => (window.location.hash = href({ page: "learn", chapter: "hazard", step: i }));

  // the products of the workspace that have a hazard zoning: the data of the illustrations
  const products = useMemo(() => {
    const out: { project: string; product: string; label: string }[] = [];
    Object.values(ws?.projects ?? {}).forEach((p) =>
      p.tracks.forEach((tr) => tr.product && out.push({ project: p.name, product: tr.product.id, label: `${p.name} · ${fmt.sensor(tr.sensor)} ${t(tr.direction)} v${tr.product.version}` })),
    );
    return out;
  }, [ws]);
  const statuses = useQueries({
    queries: products.map((p) => ({ queryKey: ["hazard", p.project, p.product], queryFn: () => api.hazard(p.project, p.product), staleTime: 60_000 })),
  });
  const zoned = products.filter((_, i) => statuses[i].data?.summary);
  // by default the zoning with the most ground at moderate hazard or above: it illustrates every step best
  const atRisk = (p: (typeof products)[number]) => {
    const by = (statuses[products.indexOf(p)].data?.summary?.by_level ?? {}) as Record<string, Record<string, { km2?: number } | number>>;
    return ["subsidence", "landslide"].reduce(
      (a, m) => a + ["moderate", "high", "very high"].reduce((b, l) => b + (((by[m]?.[l] as { km2?: number } | undefined)?.km2) ?? 0), 0),
      0,
    );
  };
  const [choice, setChoice] = useState("");
  const sel = zoned.find((p) => p.product === choice) ?? [...zoned].sort((a, b) => atRisk(b) - atRisk(a))[0];
  const summary = sel ? statuses[products.indexOf(sel)].data?.summary ?? undefined : undefined;
  const cellsQ = useQuery({
    queryKey: ["hazard-cells", sel?.project, sel?.product, summary?.created],
    queryFn: async (): Promise<Cells> => {
      const { meta, buf } = await api.hazardCells(sel!.project, sel!.product);
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!sel && !!summary,
    staleTime: Infinity,
  });
  const data: Data | undefined = useMemo(() => {
    const c = cellsQ.data;
    if (!c || !summary || !sel) return undefined;
    const F = c.meta.fields.length;
    const cache: Record<string, number[]> = {};
    const col = (name: string) =>
      (cache[name] ??= c.f[name] == null ? [] : Array.from({ length: c.meta.n }, (_, i) => c.buf[i * F + c.f[name]]));
    return { s: summary, c, col, label: sel.label, project: sel.project, product: sel.product };
  }, [cellsQ.data, summary, sel]);
  const example = useExample(data, S.example);

  let fig = 0;
  return (
    <div className="flex h-full min-h-0">
      <ChapterNav current="hazard" steps={STEPS.map((s) => s.title)} step={k} onStep={go} />
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

              <Section title="Illustrated on real data">
                {!zoned.length ? (
                  <p className="text-[13px] text-muted">{t("No product of the workspace has a hazard zoning yet: run one on the Thematic analysis page, then come back.")}</p>
                ) : !data ? (
                  <p className="text-[13px] text-muted">{t("Loading the cells…")}</p>
                ) : (
                  <div className="space-y-6">
                    {S.figures.map((f) => {
                      fig += 1;
                      return (
                        <figure key={f.caption} className="m-0 max-w-[860px]">
                          {f.render(data, example)}
                          <figcaption className="mt-2 text-[12.5px] leading-snug text-muted">
                            <span className="font-semibold text-ink-2">
                              {t("Figure")} 2.{k}.{fig}.
                            </span>{" "}
                            {t(f.caption)}
                          </figcaption>
                        </figure>
                      );
                    })}
                  </div>
                )}
              </Section>

              <Section title="What to look for">
                <div className="max-w-[860px] rounded-lg border border-[#2b4a73] bg-[#0f1d33] px-4 py-3">
                  <ul className="m-0 list-disc space-y-1 pl-4 text-[13.5px] leading-relaxed text-ink-2">
                    {S.look.map((w) => (
                      <li key={w}>{t(w)}</li>
                    ))}
                  </ul>
                  <a href={sel ? `#/hazard/${encodeURIComponent(sel.project)}/${encodeURIComponent(sel.product)}` : href({ page: "hazard" })} className="mt-3 inline-block no-underline">
                    <Button>{t("Open the Thematic analysis")}</Button>
                  </a>
                </div>
              </Section>

              <div className="mt-6 text-[12px] text-faint">
                {t("Full method, sources and research plan:")} docs/{lang()}/research/{S.doc ?? "rainfall-insar-hazard.md"}
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

            {/* side: the data used, and its numbers */}
            <aside className="mt-6 space-y-3 xl:sticky xl:top-4 xl:self-start">
              <div className="rounded-xl border border-line bg-panel p-3">
                <div className="text-[10.5px] font-semibold tracking-[1.2px] text-muted uppercase">{t("Data of the illustrations")}</div>
                {zoned.length ? (
                  <select
                    value={sel?.product ?? ""}
                    onChange={(e) => setChoice(e.target.value)}
                    className="mt-2 h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink"
                  >
                    {zoned.map((p) => (
                      <option key={p.product} value={p.product}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="mt-1 mb-0 text-[12px] text-muted">{t("none yet")}</p>
                )}
                {data && (
                  <p className="mt-2 mb-0 text-[11.5px] leading-snug text-faint">
                    {fmt.int(data.s.n_cells)} {t("cells")} · {data.s.dates[0]} → {data.s.dates[data.s.dates.length - 1]}
                  </p>
                )}
              </div>
              {data && S.numbers && (
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
