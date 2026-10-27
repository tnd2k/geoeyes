// Principles, chapter 6: the ionosphere (where it bites, its signatures, the range split-spectrum) and the phase
// steps at the subswath seams, one step per page, illustrated with the per-date records of a real stack
// (geoeyes.learn.ionosphere). Method and acceptance criteria: docs/en/guide/ionosphere.md.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type LearnIonosphere, type Workspace } from "../api";
import { ChapterNav } from "../components/LearnKit";
import { lang, t } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { Section } from "./LearnHazard";

const AZ = "#4cc2ff";
const RG = "#f5b84b";
const STEP = "#d6604d";

/** Blue (negative) … grey … red (positive) for v in [-1, 1]. */
function diverging(v: number): string {
  const x = Math.max(-1, Math.min(1, v));
  const mix = (a: number[], b: number[], f: number) => a.map((c, i) => Math.round(c + (b[i] - c) * f));
  const c = x < 0 ? mix([127, 139, 160], [33, 102, 172], -x) : mix([127, 139, 160], [178, 24, 43], x);
  return `rgb(${c.join(",")})`;
}

const short = (d: string) => d.slice(2, 7);

// ------------------------------------------------------------------ figures
/** The local time of the passes of every stack of the workspace on a 24 h line, the risky hours shaded. */
function LocalTimeFigure({ all, sel }: { all: LearnIonosphere[]; sel: LearnIonosphere }) {
  const W = 620;
  const H = 70 + 22 * all.length;
  const X = (h: number) => 20 + ((W - 40) * h) / 24;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[640px]">
      <rect x={X(14)} y={10} width={X(23) - X(14)} height={H - 40} fill="#3a1f1f" opacity={0.6} />
      <text x={(X(14) + X(23)) / 2} y={24} fill="#f4a582" fontSize="11" textAnchor="middle">{t("afternoon, dusk, early night: high TEC, fast changes")}</text>
      {[0, 6, 12, 18, 24].map((h) => (
        <g key={h}>
          <line x1={X(h)} x2={X(h)} y1={H - 32} y2={H - 26} stroke="#93a4bf" />
          <text x={X(h)} y={H - 12} fill="#93a4bf" fontSize="11" textAnchor="middle">{`${h}:00`}</text>
        </g>
      ))}
      <line x1={X(0)} x2={X(24)} y1={H - 30} y2={H - 30} stroke="#93a4bf" />
      {all.map((s, i) => {
        const hs = s.dates.map((d) => d.local_hour).filter((h): h is number => h != null);
        const h = hs.length ? hs.reduce((a, b) => a + b, 0) / hs.length : null;
        const y = 44 + 22 * i;
        const on = s.stack_id === sel.stack_id;
        return h == null ? null : (
          <g key={s.stack_id}>
            <circle cx={X(h)} cy={y} r={on ? 6 : 4.5} fill={s.pass_direction === "ascending" ? AZ : RG} stroke={on ? "#e6edf7" : "none"} strokeWidth="1.5" />
            <text x={X(h) + (h < 12 ? 10 : -10)} y={y + 4} fill={on ? "#e6edf7" : "#93a4bf"} fontSize="11.5" textAnchor={h < 12 ? "start" : "end"}>
              {s.track} · {Math.floor(h)}:{String(Math.round((h % 1) * 60)).padStart(2, "0")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** The ionospheric gradient removed on each date, along track and across, with its formal error. */
function GradientChart({ s }: { s: LearnIonosphere }) {
  const rows = s.dates.filter((d) => d.iono_mm_per_km);
  const W = 640;
  const H = 240;
  const m = { l: 44, r: 10, t: 12, b: 36 };
  const lim = Math.max(0.5, ...rows.flatMap((d) => d.iono_mm_per_km!.map((v, i) => Math.abs(v) + (d.iono_se_mm_per_km?.[i] ?? 0))));
  const X = (i: number) => m.l + ((W - m.l - m.r) * (i + 0.5)) / Math.max(1, rows.length);
  const Y = (v: number) => m.t + ((H - m.t - m.b) * (lim - v)) / (2 * lim);
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[660px]">
        {[-lim, -lim / 2, 0, lim / 2, lim].map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke={v === 0 ? "#93a4bf" : "#22324d"} strokeDasharray={v === 0 ? undefined : "3 3"} />
            <text x={m.l - 6} y={Y(v) + 4} fill="#93a4bf" fontSize="10.5" textAnchor="end">{v.toFixed(1)}</text>
          </g>
        ))}
        {rows.map((d, i) =>
          [0, 1].map((k) => {
            const v = d.iono_mm_per_km![k];
            const e = d.iono_se_mm_per_km?.[k] ?? 0;
            const x = X(i) + (k ? 4 : -4);
            const c = k ? RG : AZ;
            return (
              <g key={`${d.date}${k}`}>
                <line x1={x} x2={x} y1={Y(v - e)} y2={Y(v + e)} stroke={c} />
                <circle cx={x} cy={Y(v)} r={3} fill={c} />
              </g>
            );
          }),
        )}
        {rows.map((d, i) => (i % 3 === 0 ? <text key={d.date} x={X(i)} y={H - 18} fill="#93a4bf" fontSize="10.5" textAnchor="middle">{short(d.date)}</text> : null))}
        <text x={14} y={H / 2} fill="#93a4bf" fontSize="11" transform={`rotate(-90 14 ${H / 2})`} textAnchor="middle">mm/km</text>
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-4 text-[12px] text-ink-2">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full" style={{ background: AZ }} />{t("along track (azimuth)")}</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full" style={{ background: RG }} />{t("across (range)")}</span>
      </div>
    </>
  );
}

/** The ionospheric phase removed on one date, as mm of LOS over the crop (radar geometry). */
function FieldMap({ project, s }: { project: string; s: LearnIonosphere }) {
  const dates = s.dates.filter((d) => d.iono_mm_per_km).map((d) => d.date);
  const [date, setDate] = useState(dates[0] ?? "");
  useEffect(() => {
    if (!dates.includes(date)) setDate(dates[0] ?? "");
  }, [dates, date]);
  const f = useQuery({ queryKey: ["learn-iono-field", project, s.stack_id, date], queryFn: () => api.learnIonoField(project, s.stack_id, date), enabled: !!date && s.has_field, staleTime: Infinity });
  const cv = useRef<HTMLCanvasElement>(null);
  const lim = useMemo(() => (f.data ? Math.max(0.5, ...f.data.mm.map(Math.abs)) : 1), [f.data]);
  useEffect(() => {
    const el = cv.current;
    if (!el || !f.data) return;
    const [ny, nx] = f.data.shape;
    el.width = nx;
    el.height = ny;
    const ctx = el.getContext("2d")!;
    f.data.mm.forEach((v, i) => {
      ctx.fillStyle = diverging(v / lim);
      ctx.fillRect(i % nx, Math.floor(i / nx), 1, 1);
    });
  }, [f.data, lim]);
  if (!s.has_field) return <p className="text-[13px] text-muted">{t("This stack has no ionospheric correction.")}</p>;
  return (
    <div>
      <select value={date} onChange={(e) => setDate(e.target.value)} className="mb-2 h-8 rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink">
        {dates.map((d) => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
      <div className="relative w-full max-w-[420px]">
        <canvas ref={cv} className="block aspect-square h-auto w-full rounded-lg border border-line [image-rendering:pixelated]" />
        {s.seams.map((x) => (
          <div key={x.col} className="absolute top-0 bottom-0 border-l border-dashed border-white/70" style={{ left: `${(100 * x.col) / s.shape[1]}%` }} title={x.subswath} />
        ))}
      </div>
      <div className="mt-1 max-w-[420px]">
        <div className="h-2 rounded-sm" style={{ background: `linear-gradient(90deg,${diverging(-1)},${diverging(0)},${diverging(1)})` }} />
        <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
          <span>{(-lim).toFixed(1)}</span>
          <span>mm</span>
          <span>{lim.toFixed(1)}</span>
        </div>
      </div>
    </div>
  );
}

/** The phase step measured across each subswath seam, per date, with the ESD of the date. */
function SeamChart({ s }: { s: LearnIonosphere }) {
  const rows = s.dates.filter((d) => d.seam_rad);
  const W = 640;
  const H = 230;
  const m = { l: 44, r: 10, t: 12, b: 36 };
  const vals = rows.flatMap((d) => Object.values(d.seam_rad!));
  const lim = Math.max(0.5, ...vals.map(Math.abs));
  const X = (i: number) => m.l + ((W - m.l - m.r) * (i + 0.5)) / Math.max(1, rows.length);
  const bw = Math.max(3, (W - m.l - m.r) / Math.max(1, rows.length) - 6);
  const Y = (v: number) => m.t + ((H - m.t - m.b) * (lim - v)) / (2 * lim);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[660px]">
      {[-lim, 0, lim].map((v) => (
        <g key={v}>
          <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke={v === 0 ? "#93a4bf" : "#22324d"} strokeDasharray={v === 0 ? undefined : "3 3"} />
          <text x={m.l - 6} y={Y(v) + 4} fill="#93a4bf" fontSize="10.5" textAnchor="end">{v.toFixed(1)}</text>
        </g>
      ))}
      {rows.map((d, i) => {
        const v = Object.values(d.seam_rad!)[0];
        return <rect key={d.date} x={X(i) - bw / 2} width={bw} y={Math.min(Y(0), Y(v))} height={Math.abs(Y(v) - Y(0))} fill={Math.abs(v) > 1 ? STEP : "#7f8ba0"} />;
      })}
      {rows.map((d, i) => (i % 3 === 0 ? <text key={d.date} x={X(i)} y={H - 18} fill="#93a4bf" fontSize="10.5" textAnchor="middle">{short(d.date)}</text> : null))}
      <text x={14} y={H / 2} fill="#93a4bf" fontSize="11" transform={`rotate(-90 14 ${H / 2})`} textAnchor="middle">rad</text>
    </svg>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="max-w-[860px] overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} className="border-b border-line-2 px-2 py-1.5 text-left font-semibold text-ink">{t(h)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r[0]}>
              {r.map((c, i) => (
                <td key={i} className={`border-b border-line px-2 py-1.5 align-top ${i === 0 ? "font-semibold text-ink-2" : "text-ink-2"}`}>{t(c)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SIGNATURES = (
  <Table
    head={["Signature", "Ionosphere", "Troposphere", "Orbit", "Subswath step", "Real motion"]}
    rows={[
      ["Shape", "broad ramp, often along track; 10–100 km", "patches of 1–10 km, or scaling with height", "plane", "straight line along track, at a seam", "follows geology and structures"],
      ["In both geometries", "no: only the afternoon or evening one", "yes, stronger in the afternoon one", "not necessarily", "only where a seam is in the area", "yes, consistent with the line of sight"],
      ["Date to date", "changes sign and size", "random, strong in the wet season", "constant per date", "two levels: ≈ 0 or a constant", "accumulates steadily"],
      ["Dispersive", "yes", "no", "no", "no", "no"],
      ["ESD", "azimuth shift follows the along-track ramp", "no", "no", "ESD differs between the subswaths", "no"],
    ]}
  />
);

const CRITERIA = (
  <Table
    head={["Criterion", "Pass", "Look again"]}
    rows={[
      ["Velocity gradient difference between the two tracks (each axis)", "< 0.3 mm/yr/km", "> 0.5"],
      ["Velocity step across a subswath seam", "< 2 mm/yr", "> 4"],
      ["Decomposition without plane removal: east/up correlation", "|r| < 0.3", "|r| > 0.5"],
      ["Decomposition: cells with significant horizontal motion", "< 10 %", "> 15 %"],
      ["Per date: ramp left against the ionospheric gradient removed", "|r| < 0.3", "|r| > 0.5: wrong scale"],
    ]}
  />
);

// ------------------------------------------------------------------ steps
interface Data {
  project: string;
  s: LearnIonosphere;
  all: LearnIonosphere[];
}

interface Step {
  title: string;
  goal: string;
  what: string[];
  formula?: string[];
  look: string[];
  figures: { caption: string; render: (d: Data) => ReactNode }[];
  numbers?: (d: Data) => [string, string][];
}

const corrected = (s: LearnIonosphere) => s.dates.filter((d) => d.iono_mm_per_km);
const median = (a: number[]) => {
  const b = [...a].sort((x, y) => x - y);
  return b.length ? (b.length % 2 ? b[(b.length - 1) / 2] : (b[b.length / 2 - 1] + b[b.length / 2]) / 2) : NaN;
};

const STEPS: Step[] = [
  {
    title: "Where the ionosphere bites",
    goal: "Know when a ramp on a velocity map may come from the ionosphere rather than from the ground.",
    what: [
      "The ionosphere, 60–1000 km above the ground, holds free electrons. They advance the phase of the radar wave in proportion to the total electron content (TEC) along the path, and inversely to the frequency: the delay is dispersive.",
      "The TEC is highest in the afternoon and early night, near the two crests of the equatorial ionization anomaly (magnetic latitudes 5–25°), and near the maximum of the solar cycle (cycle 25: 2024–2026). Sentinel-1 ascending passes are near 18:00 local time, descending ones near 06:00.",
      "One interferogram sees only the difference of TEC between its two dates and across the image. A difference that changes over the area becomes a ramp; a trend of the ramps over the dates becomes a ramp in the velocity.",
      "At L band (ALOS-2, NISAR) the phase is about 4 times larger than at C band, about 18 times in millimetres.",
    ],
    formula: ["φ_iono = −4π · 40.31 · TEC / (c · f)", "1 TECU of difference at C band ≈ 3.1 rad ≈ 14 mm"],
    look: ["A pass in the shaded hours over a low-latitude area: expect ionospheric ramps.", "A ramp in one track only, the evening one: suspect the ionosphere first."],
    figures: [{ caption: "Mean local time of the passes of the stacks of the workspace; the stack shown is outlined.", render: (d) => <LocalTimeFigure all={d.all} sel={d.s} /> }],
    numbers: (d) => {
      const hs = d.s.dates.map((x) => x.local_hour).filter((h): h is number => h != null);
      const h = hs.length ? hs.reduce((a, b) => a + b, 0) / hs.length : null;
      return [
        ["Track", d.s.track],
        ["Local time of the passes", h != null ? `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}` : "–"],
        ["Latitude", `${d.s.lat.toFixed(2)}°`],
        ["Acquisitions", fmt.int(d.s.dates.length)],
      ];
    },
  },
  {
    title: "Signatures",
    goal: "Tell an ionospheric ramp from the troposphere, the orbit, a subswath step and real motion.",
    what: [
      "Each error leaves its own pattern. The table sums up the shape, whether both geometries see it, how it changes from date to date, and whether it is dispersive.",
      "Two tests decide. First, compare the two geometries: vertical motion appears almost alike in both, and north-south motion hardly enters either line of sight; a north-south ramp in one track only cannot be motion. Second, the split-spectrum: only the ionosphere is dispersive.",
      "A strong azimuth gradient of the ionosphere also shifts the TOPS bursts along track: the enhanced spectral diversity (ESD) of the coregistration follows the along-track ramp of the date.",
    ],
    look: ["A straight line along the flight direction: compare its column with the subswath seams before anything else; it is not a fault."],
    figures: [{ caption: "Signatures of the errors that make ramps and lines on a velocity map.", render: () => SIGNATURES }],
  },
  {
    title: "Range split-spectrum",
    goal: "Separate the dispersive (ionospheric) phase from the rest with two sub-bands of the same images.",
    what: [
      "The range band of each scene is cut into a low and a high sub-band, a third of the bandwidth apart. The non-dispersive phase (motion, troposphere, orbit) scales with the frequency, the ionospheric one with its inverse: two equations, two unknowns.",
      "The separation amplifies the phase noise about 95 times at C band. GeoEyes therefore averages coarse cells over the whole bursts (about 45 × 175 km), weights them by the coherence of the two sub-bands, and fits a smooth surface: by default a plane around the area, Gaussian-weighted over 10 km.",
      "The estimate is removed from the stored scenes date by date, before the point processing. It is set in the project: [stack] ionosphere = \"split_spectrum\".",
    ],
    formula: ["φ_iono = a · φ_low − b · (φ_high − φ_low)", "a = f_L·f_H / (f0·(f_L + f_H)),   b = f_L²·f_H / (f0·(f_H² − f_L²))"],
    look: ["The gradient of each date and its error: a few tenths of a mm/km is common at dusk; an error above 0.2 mm/km means a weak date.", "The map: a smooth ramp; the dashed line is the subswath seam."],
    figures: [
      { caption: "Ionospheric gradient removed on each date, in mm of LOS per km, with its formal error.", render: (d) => (corrected(d.s).length ? <GradientChart s={d.s} /> : <p className="text-[13px] text-muted">{t("This stack has no ionospheric correction.")}</p>) },
      { caption: "Ionospheric phase removed on one date, over the area (radar geometry: rows along track, columns across).", render: (d) => <FieldMap project={d.project} s={d.s} /> },
    ],
    numbers: (d) => {
      const r = corrected(d.s);
      if (!r.length) return [["Ionospheric correction", t("none")]];
      return [
        ["Model", `${d.s.ionosphere_model ?? "–"} · ${((d.s.ionosphere_smooth_m ?? 0) / 1000).toFixed(0)} km`],
        ["Dates corrected", `${r.length} / ${d.s.dates.length}`],
        ["Along track, median |gradient|", `${median(r.map((x) => Math.abs(x.iono_mm_per_km![0]))).toFixed(2)} mm/km`],
        ["Across, median |gradient|", `${median(r.map((x) => Math.abs(x.iono_mm_per_km![1]))).toFixed(2)} mm/km`],
        ["Formal error, median", `${median(r.map((x) => x.iono_se_mm_per_km?.[0] ?? NaN)).toFixed(2)} mm/km`],
      ];
    },
  },
  {
    title: "Subswath seams",
    goal: "See why a straight line can appear where two subswaths meet, and how GeoEyes removes it.",
    what: [
      "A Sentinel-1 TOPS scene has three subswaths (IW1–IW3), each coregistered and flattened apart, then cut and pasted in the middle of their overlap.",
      "On some dates the interferogram of one subswath is offset by a constant against its neighbour: in Hanoi, −2.2 rad on 9 of 25 dates, on exactly the dates whose ESD differs between the subswaths. The mosaic turns the constant into a step, the time series into a velocity: a straight line of 6–10 mm/yr along the seam. Its root cause is not known.",
      "GeoEyes measures the step across each seam, date by date (two strips of 40 columns, per block of 32 lines, coherence-weighted), and removes it before the mosaic, the widest subswath as anchor. The same step is taken out of the low sub-band before the split-spectrum; otherwise about half of it would pass into the ionospheric estimate.",
    ],
    formula: ["step = arg Σ γ · e^{i(φ_right − φ_left)}", "leak into the ionosphere without the fix: a · step ≈ 0.5 · step"],
    look: ["Two levels only: about 0 or a constant. Bars above 1 rad in absolute value are the shifted dates.", "A consistency below 0.3 means the step could not be measured: the date is kept as it is and a warning is logged."],
    figures: [{ caption: "Phase step across the seam on each date (rad); red: the dates offset by a constant.", render: (d) => (d.s.seams.length ? <SeamChart s={d.s} /> : <p className="text-[13px] text-muted">{t("No subswath seam crosses the area of this stack.")}</p>) }],
    numbers: (d) => {
      const r = d.s.dates.filter((x) => x.seam_rad);
      if (!d.s.seams.length) return [["Subswaths", d.s.subswath ?? "–"]];
      return [
        ["Subswaths", d.s.subswath ?? "–"],
        ["Anchor", r[0]?.anchor ?? "–"],
        ["Dates with a step > 1 rad", `${r.filter((x) => Math.abs(Object.values(x.seam_rad!)[0]) > 1).length} / ${r.length}`],
        ["Consistency, median", median(r.map((x) => Object.values(x.seam_consistency ?? {})[0] ?? NaN)).toFixed(2)],
      ];
    },
  },
  {
    title: "Diagnose and accept",
    goal: "Decide whether a product is clean enough, and what to do when it is not.",
    what: [
      "Compare the velocity planes of the two tracks over their common area; the decomposition warns when one is more than twice the other.",
      "Fit a plane to every interferogram: if the ramp is already in the unwrapped phase, and not from ERA5 or the DEM error, it is in the images. Set it against the local time, the TEC level of the global maps, and the ESD of each date.",
      "Then apply the criteria. When the ramp left is not related to the ionospheric gradient removed, what is left is not ionosphere: look at the troposphere, unwrapping and odd dates. Until it is explained, remove a plane before the decomposition ([postprocess.decompose] deramp = \"plane\"), and say so in the report.",
    ],
    look: ["In Hanoi the ramp left after correction is barely related to the ionospheric gradient removed (r = 0.18) and largest in summer: most likely evening convection that ERA5 misses."],
    figures: [{ caption: "Acceptance criteria against the other geometry or GNSS.", render: () => CRITERIA }],
  },
  {
    title: "Limits",
    goal: "Know what the correction can and cannot remove.",
    what: [
      "At C band the split-spectrum is noisy: only smooth forms can be estimated, not structures of a few km such as post-sunset plasma bubbles.",
      "The local model assumes a nearly linear ionosphere within about 10 km of the area.",
      "The geometric phase must be recomputed exactly before splitting: about half of its error passes into the estimate.",
      "Ionospheric scintillation decorrelates the signal; no correction brings it back.",
      "Subswath steps can be measured only where both sides of the seam are coherent (towns); over farmland or water they may not be.",
    ],
    look: ["Check a corrected product against the other geometry or GNSS before reading north-south gradients of one track."],
    figures: [],
  },
];

// ------------------------------------------------------------------ page
export function IonosphereChapter({ ws, step }: { ws: Workspace | undefined; step?: number }) {
  const k = Math.min(STEPS.length - 1, Math.max(0, step ?? 0));
  const S = STEPS[k];
  const go = (i: number) => (window.location.hash = href({ page: "learn", chapter: "ionosphere", step: i }));

  const projects = useMemo(() => Object.values(ws?.projects ?? {}).map((p) => p.name), [ws]);
  const lists = useQueries({ queries: projects.map((p) => ({ queryKey: ["learn-stacks", p], queryFn: () => api.learnStacks(p), staleTime: 60_000 })) });
  const stacks = useMemo(
    () => projects.flatMap((p, i) => (lists[i].data?.stacks ?? []).filter((s) => !s.error).map((s) => ({ project: p, stack: s.stack_id }))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projects, lists.map((q) => q.dataUpdatedAt).join()],
  );
  const sums = useQueries({ queries: stacks.map((s) => ({ queryKey: ["learn-iono", s.project, s.stack], queryFn: () => api.learnIonosphere(s.project, s.stack), staleTime: 60_000 })) });
  const ready = stacks.map((s, i) => ({ ...s, sum: sums[i].data })).filter((s): s is typeof s & { sum: LearnIonosphere } => !!s.sum);
  // by default a corrected stack with a seam in its area
  const score = (s: LearnIonosphere) => (s.ionosphere !== "none" ? 2 : 0) + (s.seams.length ? 1 : 0) + (s.pass_direction === "ascending" ? 0.5 : 0);
  const [choice, setChoice] = useState("");
  const sel = ready.find((s) => `${s.project}/${s.stack}` === choice) ?? [...ready].sort((a, b) => score(b.sum) - score(a.sum))[0];
  const data: Data | undefined = sel && { project: sel.project, s: sel.sum, all: ready.filter((r) => r.project === sel.project).map((r) => r.sum) };

  let fig = 0;
  return (
    <div className="flex h-full min-h-0">
      <ChapterNav current="ionosphere" steps={STEPS.map((s) => s.title)} step={k} onStep={go} />
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
                    <p className="text-[13px] text-muted">{t("No stack in the workspace yet: run a processing up to the stack, then come back.")}</p>
                  ) : (
                    <div className="space-y-6">
                      {S.figures.map((f) => {
                        fig += 1;
                        return (
                          <figure key={f.caption} className="m-0 max-w-[860px]">
                            {f.render(data)}
                            <figcaption className="mt-2 text-[12.5px] leading-snug text-muted">
                              <span className="font-semibold text-ink-2">
                                {t("Figure")} 6.{k}.{fig}.
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
                </div>
              </Section>
              <div className="mt-6 text-[12px] text-faint">
                {t("Full method, diagnosis and acceptance criteria:")} docs/{lang()}/guide/ionosphere.md
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
                  <select value={sel ? `${sel.project}/${sel.stack}` : ""} onChange={(e) => setChoice(e.target.value)} className="mt-2 h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink">
                    {ready.map((s) => (
                      <option key={`${s.project}/${s.stack}`} value={`${s.project}/${s.stack}`}>
                        {s.project} · {s.stack}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="mt-1 mb-0 text-[12px] text-muted">{t("none yet")}</p>
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
