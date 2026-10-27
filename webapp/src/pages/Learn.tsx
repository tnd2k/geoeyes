// Principles, chapter 1: a learning path for newcomers through ONE interferometric pair of a project's stack (geoeyes.learn).
// From two single SLC scenes: amplitude, coregistration, raw interferogram, flat-earth and topographic phase,
// coherence, Goldstein filtering (the steps of the old flat_earth_gui), then GeoEyes unwrapping (IRLS), LOS
// displacement, and the velocity of the PS time series of the product. Every image is the multilooked crop in
// radar geometry; the cursor is linked across images. Method: docs/en/guide/learn-insar-pair.md.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import { Box, ChapterNav } from "../components/LearnKit";
import { api, type LearnPairMeta, type LearnParams, type LearnSeries, type LearnStack, type Workspace } from "../api";
import { t, ts } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { BehaviourChapter } from "./LearnBehaviour";
import { GeometryChapter } from "./LearnGeometry";
import { IonosphereChapter } from "./LearnIonosphere";
import { LinesChapter } from "./LearnLines";
import { HazardChapter } from "./LearnHazard";

type RGB = [number, number, number];
type Cmap = "gray" | "phase" | "viridis" | "terrain" | "sink_red" | "sink_red_rad";

// cyclic (twilight-like): the colour of −π and +π is the same, as a phase must be
const PHASE: RGB[] = [[226, 217, 226], [158, 184, 204], [99, 133, 194], [94, 72, 166], [72, 26, 91], [47, 20, 54], [94, 24, 64], [154, 52, 72], [194, 112, 92], [214, 171, 150], [226, 217, 226]];
const VIRIDIS: RGB[] = [[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137], [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37]];
const TERRAIN: RGB[] = [[51, 51, 153], [2, 152, 255], [1, 204, 102], [128, 230, 128], [255, 255, 153], [204, 187, 136], [128, 92, 84], [255, 255, 255]];
// diverging: red = away from the satellite (sinking), blue = toward it
const AWAY_TOWARD: RGB[] = [[103, 0, 31], [178, 24, 43], [214, 96, 77], [244, 165, 130], [253, 219, 199], [247, 247, 247], [209, 229, 240], [146, 197, 222], [67, 147, 195], [33, 102, 172], [5, 48, 97]];

function ramp(stops: RGB[], x: number): RGB {
  const v = Math.min(1, Math.max(0, x)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(v));
  const f = v - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

function color(cmap: Cmap, v: number, lo: number, hi: number): RGB {
  const x = (v - lo) / (hi - lo || 1);
  if (cmap === "gray") {
    const g = Math.min(1, Math.max(0, x)) * 255;
    return [g, g, g];
  }
  if (cmap === "phase") return ramp(PHASE, x);
  if (cmap === "viridis") return ramp(VIRIDIS, x);
  if (cmap === "terrain") return ramp(TERRAIN, x);
  // sink_red: values > 0 are toward the satellite (mm); sink_red_rad: phase > 0 is a range increase (away)
  return ramp(AWAY_TOWARD, cmap === "sink_red_rad" ? 1 - x : x);
}

interface Grid {
  meta: LearnPairMeta;
  layers: Record<string, Float32Array>;
}

interface PanelSpec {
  layer: string;
  title: string;
  cmap: Cmap;
  unit: string;
  range?: [number, number];
  mask?: boolean;            // dim the pixels below the coherence threshold
  residues?: string;         // overlay a residue layer
  composite?: boolean;       // amp1 in red, amp2 in green + blue
  blink?: boolean;           // alternate amp1 / amp2
  points?: boolean;          // PS of the product
  note?: string;
}

/** Full range, symmetric around 0 (never clipped: the extremes stay visible). */
function symmetric(r: [number, number]): [number, number] {
  const m = Math.max(Math.abs(r[0]), Math.abs(r[1])) || 1;
  return [-m, m];
}

function rangeOf(g: Grid, layer: string, cmap: Cmap): [number, number] {
  const s = g.meta.stats[layer];
  if (!s) return [0, 1];
  if (cmap === "phase") return [-Math.PI, Math.PI];
  if (cmap === "gray") return [s[2], s[3]];
  if (cmap === "viridis") return [0, 1];
  if (cmap === "sink_red" || cmap === "sink_red_rad") return symmetric([s[0], s[1]]);
  return [s[0], s[1]];
}

// ------------------------------------------------------------------ one image
function Panel({
  g,
  spec,
  hover,
  setHover,
  onPick,
  cohThr,
  pts,
  selected,
  refPix,
}: {
  g: Grid;
  spec: PanelSpec;
  hover: [number, number] | null;
  setHover: (h: [number, number] | null) => void;
  onPick?: (r: number, c: number) => void;
  cohThr: number;
  pts?: { rows: number[]; cols: number[]; vel: number[]; range: [number, number] };
  selected?: number | null;
  refPix?: [number, number] | null;
}) {
  const cv = useRef<HTMLCanvasElement>(null);
  const [h, w] = g.meta.shape;
  const [frame, setFrame] = useState(0);
  const range = useMemo(() => spec.range ?? rangeOf(g, spec.composite || spec.blink ? "amp1" : spec.layer, spec.cmap), [g, spec]);
  useEffect(() => {
    if (!spec.blink) return;
    const id = window.setInterval(() => setFrame((f) => 1 - f), 700);
    return () => window.clearInterval(id);
  }, [spec.blink]);
  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    c.width = w;
    c.height = h;
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(w, h);
    const L = g.layers;
    const data = spec.blink ? (frame ? L.amp2 : L.amp1) : L[spec.layer];
    const coh = L.coh;
    const [lo, hi] = range;
    for (let i = 0; i < w * h; i++) {
      let rgb: RGB;
      if (spec.composite) {
        const a = color("gray", L.amp1[i], lo, hi)[0];
        const b = color("gray", L.amp2[i], lo, hi)[0];
        rgb = [a, b, b];
      } else {
        const v = data[i];
        rgb = Number.isFinite(v) ? color(spec.cmap, v, lo, hi) : [40, 48, 62];
      }
      if (spec.points) rgb = [rgb[0] * 0.4, rgb[1] * 0.4, rgb[2] * 0.45];
      if (spec.mask && coh[i] < cohThr) rgb = [rgb[0] * 0.18 + 20, rgb[1] * 0.18 + 24, rgb[2] * 0.18 + 32];
      img.data[i * 4] = rgb[0];
      img.data[i * 4 + 1] = rgb[1];
      img.data[i * 4 + 2] = rgb[2];
      img.data[i * 4 + 3] = 255;
    }
    if (spec.residues) {
      const r = L[spec.residues];
      for (let i = 0; i < w * h; i++) {
        if (r[i] === 0) continue;
        const col: RGB = r[i] > 0 ? [255, 40, 40] : [40, 230, 255];
        img.data[i * 4] = col[0];
        img.data[i * 4 + 1] = col[1];
        img.data[i * 4 + 2] = col[2];
      }
    }
    if (spec.points && pts) {
      const [lo2, hi2] = symmetric(pts.range);
      pts.rows.forEach((rr, k) => {
        const i = rr * w + pts.cols[k];
        const col = color("sink_red", pts.vel[k], lo2, hi2);
        img.data[i * 4] = col[0];
        img.data[i * 4 + 1] = col[1];
        img.data[i * 4 + 2] = col[2];
      });
    }
    ctx.putImageData(img, 0, 0);
  }, [g, spec, frame, cohThr, pts, range, w, h]);

  const sx = g.meta.spacing_m.range_ground;
  const sy = g.meta.spacing_m.azimuth;
  const at = (e: React.MouseEvent): [number, number] => {
    const b = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const c = Math.min(w - 1, Math.max(0, Math.floor(((e.clientX - b.left) / b.width) * w)));
    const r = Math.min(h - 1, Math.max(0, Math.floor(((e.clientY - b.top) / b.height) * h)));
    return [r, c];
  };
  const mark = (rc: [number, number] | null | undefined, cls: string) =>
    rc && (
      <span
        className={`pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 ${cls}`}
        style={{ left: `${((rc[1] + 0.5) / w) * 100}%`, top: `${((rc[0] + 0.5) / h) * 100}%` }}
      />
    );
  const sel = selected != null && pts ? ([pts.rows[selected], pts.cols[selected]] as [number, number]) : null;
  return (
    <figure className="m-0 min-w-0">
      <figcaption className="mb-1 flex items-baseline gap-2 text-[12px]">
        <span className="font-semibold text-ink">{t(spec.title)}</span>
        {spec.note && <span className="text-faint">{t(spec.note)}</span>}
      </figcaption>
      <div
        className={`relative w-full overflow-hidden rounded-md border border-line ${onPick ? "cursor-crosshair" : "cursor-default"}`}
        style={{ aspectRatio: `${w * sx} / ${h * sy}` }}
        onMouseMove={(e) => setHover(at(e))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => onPick?.(...at(e))}
      >
        <canvas ref={cv} className="block h-full w-full [image-rendering:pixelated]" />
        {hover && (
          <>
            <span className="pointer-events-none absolute top-0 bottom-0 w-px bg-white/60" style={{ left: `${((hover[1] + 0.5) / w) * 100}%` }} />
            <span className="pointer-events-none absolute right-0 left-0 h-px bg-white/60" style={{ top: `${((hover[0] + 0.5) / h) * 100}%` }} />
          </>
        )}
        {mark(refPix, "border-white bg-black/40")}
        {mark(sel, "border-[#ffd34d] bg-transparent")}
      </div>
      <ColorBar spec={spec} range={spec.points && pts ? symmetric(pts.range) : range} />
    </figure>
  );
}

function ColorBar({ spec, range }: { spec: PanelSpec; range: [number, number] }) {
  if (spec.composite || spec.blink) return null;
  const cm = spec.points ? "sink_red" : spec.cmap;
  const stops = Array.from({ length: 12 }, (_, i) => {
    const c = color(cm, range[0] + ((range[1] - range[0]) * i) / 11, range[0], range[1]);
    return `rgb(${c.map(Math.round).join(",")}) ${(i / 11) * 100}%`;
  }).join(",");
  const f = (v: number) => (cm === "phase" ? (v < 0 ? "−π" : "+π") : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1));
  return (
    <div className="mt-1">
      <div className="h-2 rounded-sm" style={{ background: `linear-gradient(90deg,${stops})` }} />
      <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
        <span>{f(range[0])}</span>
        <span>{t(spec.points ? "mm/yr" : spec.unit)}</span>
        <span>{f(range[1])}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ the steps
interface Step {
  id: string;
  title: string;
  goal: string;
  panels: PanelSpec[];
  what: string[];
  formula?: string[];
  look: string[];
  metrics?: (g: Grid, s: LearnStack) => [string, string][];
  controls?: ("pair" | "coh" | "filter" | "ref" | "linked" | "exercise")[];
  profile?: boolean;
  velocity?: boolean;
}

const STEPS: Step[] = [
  {
    id: "setup",
    title: "Choose the pair and the area",
    goal: "Pick two acquisitions of the stack and a small area to follow through every step.",
    panels: [],
    what: [
      "A stack holds many SAR scenes of the same place, taken from almost the same orbit at different dates.",
      "An interferogram compares two of them: the first and the second scene of the pair.",
      "Short time between the dates and a small perpendicular baseline (B⊥, the distance between the two orbits) keep the two scenes alike: the result is cleaner.",
    ],
    look: ["Click two points of the baseline plot to form a pair.", "Click the amplitude image to move the area; the window size sets how much ground you see."],
    controls: ["pair"],
  },
  {
    id: "scenes",
    title: "Two single SLC scenes",
    goal: "See what one radar scene holds: a complex number per pixel, with an amplitude and a phase.",
    panels: [
      { layer: "amp1", title: "Amplitude, scene 1", cmap: "gray", unit: "dB" },
      { layer: "amp2", title: "Amplitude, scene 2", cmap: "gray", unit: "dB" },
    ],
    what: [
      "A single-look complex (SLC) image stores, for each pixel, how strongly the ground echoes the radar (amplitude) and where in its wave cycle the echo comes back (phase).",
      "Amplitude shows the scene: bright buildings and corners, dark water and smooth roads. The granular texture is speckle, not noise of the instrument.",
      "The phase of one scene alone looks random: it mixes the distance to the satellite with the arrangement of scatterers inside the pixel. It becomes useful only when two scenes are compared.",
    ],
    look: ["Both amplitudes look almost the same: the geometry did not change much.", "Images are in radar geometry: rows are azimuth (along the orbit), columns are range (away from the satellite); north is not up."],
    metrics: (g, s) => [
      ["Sensor", fmt.sensor(s.sensor)],
      ["Wavelength", `${(s.wavelength_m * 100).toFixed(2)} cm`],
      ["Incidence", `${s.incidence_deg.toFixed(1)}°`],
      ["Pixel (az × ground rg)", `${s.spacing_m.azimuth.toFixed(1)} × ${s.spacing_m.range_ground.toFixed(1)} m`],
      ["Looks (az × rg)", `${g.meta.params.looks_az} × ${g.meta.params.looks_rg}`],
    ],
    controls: ["linked"],
  },
  {
    id: "coreg",
    title: "Coregistration",
    goal: "Make every pixel of scene 2 look at the same ground as the same pixel of scene 1.",
    panels: [
      { layer: "amp1", title: "Colour composite", cmap: "gray", unit: "dB", composite: true, note: "red = scene 1, cyan = scene 2" },
      { layer: "amp1", title: "Blink", cmap: "gray", unit: "dB", blink: true, note: "scene 1 ↔ scene 2" },
    ],
    what: [
      "The two orbits differ slightly, so the same building falls on different pixels in the two scenes. Coregistration resamples scene 2 onto the grid of scene 1.",
      "GeoEyes does it geometrically: with the precise orbits and the DEM, it computes where every pixel of scene 1 lies in scene 2, then corrects the remaining offset by matching the images (and, for Sentinel-1, with the enhanced spectral diversity across bursts).",
      "The accuracy needed is about a tenth of a pixel: worse, and the phases of the two scenes no longer belong to the same scatterers.",
    ],
    look: ["In the composite, aligned features are grey; a misalignment would show red and cyan edges.", "In the blink, nothing should jump: only the speckle flickers."],
    metrics: (g, s) => {
      const i = s.dates.indexOf(g.meta.params.second);
      const out: [string, string][] = [];
      if (s.coreg_residual && i >= 0) out.push(["Residual offset after geometry (az, rg)", `${s.coreg_residual[i].map((v) => v.toFixed(3)).join(", ")} px`]);
      if (s.esd_shift && i >= 0 && s.esd_shift[i] != null) out.push(["ESD azimuth shift", `${s.esd_shift[i].toFixed(4)} px`]);
      out.push(["Reference grid", s.reference_date]);
      return out;
    },
  },
  {
    id: "raw",
    title: "Raw interferogram",
    goal: "Multiply scene 1 by the conjugate of scene 2: the phase difference appears as fringes.",
    panels: [
      { layer: "raw", title: "Raw interferometric phase", cmap: "phase", unit: "rad" },
      { layer: "amp1", title: "Amplitude, scene 1", cmap: "gray", unit: "dB" },
    ],
    what: [
      "Each fringe (one full colour cycle) is a change of 2π in phase difference, half a wavelength of change in distance.",
      "The raw phase adds up several contributions: the curvature of the Earth seen from two orbits (flat earth), the topography, the ground motion between the dates, the atmosphere, and noise.",
      "The next steps remove the parts we can model, so that the motion remains.",
      "GeoEyes removes the flat earth and the topography already during coregistration; here they are added back from the stored geometry so that you can see them.",
    ],
    formula: ["I = s₁ · s₂*", "φ = arg(I) = φ_flat + φ_topo + φ_motion + φ_atmosphere + φ_noise"],
    look: ["Dense, regular fringes running along the azimuth: mostly the flat-earth phase."],
    metrics: (g) => [
      ["Pair", `${g.meta.params.first} → ${g.meta.params.second} (${g.meta.days} ${t("days")})`],
      ["B⊥", `${g.meta.bperp_m.toFixed(1)} m`],
      ["Fringes per km (raw)", g.meta.fringes_per_km.raw.toFixed(2)],
    ],
  },
  {
    id: "flat",
    title: "Remove the flat-earth phase",
    goal: "Remove the fringes the geometry alone would produce on a smooth Earth.",
    panels: [
      { layer: "flat", title: "Flat-earth phase (model)", cmap: "phase", unit: "rad" },
      { layer: "after_flat", title: "After removing it", cmap: "phase", unit: "rad" },
    ],
    what: [
      "From two orbits a baseline B⊥ apart, the distance to a smooth Earth changes steadily across the swath: regular fringes along range.",
      "Their rate is known from the orbits: the larger B⊥, the denser the fringes.",
    ],
    formula: ["kₕ = 4π B⊥ / (λ R sin θ)", "dφ_flat / dr = kₕ · cos θ", "φ' = arg(I · e^(−jφ_flat))"],
    look: ["The dense regular fringes are gone; what remains follows the relief, the motion and the atmosphere."],
    metrics: (g) => [
      ["B⊥", `${g.meta.bperp_m.toFixed(1)} m`],
      ["Predicted flat-earth fringes per km", g.meta.flat_fringes_per_km_range.toFixed(2)],
      ["Fringes per km, before → after", `${g.meta.fringes_per_km.raw.toFixed(2)} → ${g.meta.fringes_per_km.after_flat.toFixed(2)}`],
    ],
  },
  {
    id: "topo",
    title: "Remove the topographic phase",
    goal: "Remove the phase of the relief with a digital elevation model (DEM).",
    panels: [
      { layer: "dem", title: "DEM height", cmap: "terrain", unit: "m", note: "ellipsoidal" },
      { layer: "topo", title: "Topographic phase (model)", cmap: "phase", unit: "rad" },
      { layer: "diff", title: "Differential interferogram", cmap: "phase", unit: "rad" },
    ],
    what: [
      "A point higher up is seen at a slightly different angle from the two orbits: its phase changes with its height.",
      "The height of ambiguity is the height difference that makes one fringe: with a large one, the relief hardly shows.",
      "An error of the DEM (buildings missing from SRTM, for example) leaves a phase proportional to B⊥: GeoEyes estimates it per point later, in the time series.",
    ],
    formula: ["φ_topo = kₕ · h", "height of ambiguity = 2π / kₕ = λ R sin θ / (2 B⊥)", "φ_diff = arg(I · e^(−j(φ_flat + φ_topo)))"],
    look: ["Fringes that followed the hills disappear; on flat ground the change is small.", "What remains: motion, atmosphere (smooth, km-scale) and noise."],
    metrics: (g) => [
      ["Height of ambiguity", g.meta.height_of_ambiguity_m ? `${g.meta.height_of_ambiguity_m.toFixed(0)} m` : "–"],
      ["DEM range", `${g.meta.dem_range_m[0].toFixed(0)} … ${g.meta.dem_range_m[1].toFixed(0)} m`],
      ["Topographic phase across the area", `${g.meta.topo_range_rad.toFixed(2)} rad`],
      ["Fringes per km (differential)", g.meta.fringes_per_km.diff.toFixed(2)],
    ],
  },
  {
    id: "coh",
    title: "Coherence and multilooking",
    goal: "Measure where the phase can be trusted.",
    panels: [
      { layer: "coh", title: "Coherence", cmap: "viridis", unit: "0–1" },
      { layer: "diff", title: "Differential phase, low coherence dimmed", cmap: "phase", unit: "rad", mask: true },
    ],
    what: [
      "Coherence compares the two scenes in a small window: 1 when they are alike, near 0 when the ground changed (vegetation, water, construction) or the scatterers decorrelated.",
      "Multilooking averages neighbouring pixels of the interferogram: less noise, coarser pixels.",
      "Low-coherence areas carry no usable phase: they are dimmed here and weigh little in the unwrapping.",
      "The threshold chosen here carries on: the filter, the unwrapping and the displacement of the next steps only use the pixels at or above it.",
    ],
    formula: ["γ = |Σ s₁ s₂*| / √(Σ|s₁|² · Σ|s₂|²)"],
    look: ["Buildings and roads stay coherent; fields, water and trees do not.", "Move the threshold and see which areas survive."],
    metrics: (g) => [
      ["Median coherence", g.meta.coherence_median.toFixed(2)],
      ["Window", `${g.meta.params.coh_win} × ${g.meta.params.coh_win} ${t("multilooked pixels")}`],
    ],
    controls: ["coh"],
  },
  {
    id: "filter",
    title: "Phase filtering (Goldstein)",
    goal: "Reduce the phase noise so that the fringes become continuous.",
    panels: [
      { layer: "diff_kept", title: "Before filtering", cmap: "phase", unit: "rad", residues: "res_diff", note: "dots: residues" },
      { layer: "filt", title: "After the Goldstein filter", cmap: "phase", unit: "rad", residues: "res_filt", note: "dots: residues" },
    ],
    what: [
      "The Goldstein filter works in small windows of the spectrum: it keeps the dominant fringe pattern and damps the rest; α sets how strongly (0 = no filter, 1 = strong).",
      "A residue is a 2×2 loop whose phase differences do not add up to zero: there, unwrapping is ambiguous. Red = +1, cyan = −1.",
      "Filtering removes most residues, but too strong a filter also smooths real motion and invents fringes in noise.",
    ],
    formula: ["Z(u,v) ← Z(u,v) · |S(u,v)|^α  (per window, S = smoothed spectrum)", "residue = Σ wrap(Δφ) around a 2×2 loop / 2π ∈ {−1, 0, +1}"],
    look: ["Residues gather in the noisy, low-coherence areas.", "Compare α = 0.3 and 0.9: fewer residues, but smoother details."],
    metrics: (g) => [
      ["Residues, before → after", `${fmt.int(g.meta.residues.diff)} → ${fmt.int(g.meta.residues.filt)}`],
      ["Pixels kept (γ ≥ threshold)", `${(g.meta.kept_share * 100).toFixed(0)} % · γ ≥ ${g.meta.params.coh_thr}`],
      ["α · window · passes", `${g.meta.params.alpha} · ${g.meta.params.fft} · ${g.meta.params.passes}`],
    ],
    controls: ["filter"],
  },
  {
    id: "unwrap",
    title: "Phase unwrapping",
    goal: "Turn the wrapped phase (−π…π) into a continuous phase by adding the right multiple of 2π to each pixel.",
    panels: [
      { layer: "filt", title: "Wrapped (filtered)", cmap: "phase", unit: "rad" },
      { layer: "unw", title: "Unwrapped", cmap: "sink_red_rad", unit: "rad" },
    ],
    what: [
      "The measured phase only knows its value modulo 2π: a jump from +π to −π can be a real step or just the next fringe.",
      "Unwrapping assumes the true phase changes by less than π between neighbours and integrates the phase differences over the image.",
      "GeoEyes uses an iteratively reweighted least-squares solver (IRLS): it finds the continuous surface whose gradients best match the wrapped gradients, trusting coherent pixels more (weights = γ²).",
      "The result is relative: a reference point (by default, the median of the most coherent 10 %) is set to zero. Click an image to choose another.",
      "Only the pixels kept at the coherence step are unwrapped. Patches cut off from the rest by low coherence may be off by a whole number of cycles.",
    ],
    formula: ["φ_unw = φ_wrapped + 2π·k,  k integer", "min Σ w · (∇φ_unw − wrap(∇φ_wrapped))²"],
    look: ["The profile below follows the row under the cursor: the sawtooth of the wrapped phase becomes one smooth curve.", "Where residues were many, the unwrapped surface may contain errors of a whole cycle."],
    metrics: (g) => [
      ["Method", ts(g.meta.unwrap.method)],
      ["Reference", g.meta.unwrap.reference.kind === "pixel" ? `${t("pixel")} (${g.meta.unwrap.reference.row}, ${g.meta.unwrap.reference.col})` : t("median of the most coherent 10 %")],
      ["Solver residual (RMS)", g.meta.unwrap.pcg_rms.toExponential(1)],
      ["Pixels kept (γ ≥ threshold)", `${(g.meta.kept_share * 100).toFixed(0)} % · γ ≥ ${g.meta.params.coh_thr}`],
    ],
    controls: ["ref", "exercise"],
    profile: true,
  },
  {
    id: "disp",
    title: "From phase to displacement",
    goal: "Convert the unwrapped phase into millimetres of motion along the line of sight.",
    panels: [
      { layer: "disp", title: "LOS displacement", cmap: "sink_red", unit: "mm" },
      { layer: "coh", title: "Coherence", cmap: "viridis", unit: "0–1" },
    ],
    what: [
      "The radar measures the change of distance along its line of sight (LOS), not the vertical or horizontal motion directly.",
      "One fringe is half a wavelength of change in distance: the signal travels there and back.",
      "In GeoEyes, positive = toward the satellite (e.g. uplift), negative = away (e.g. sinking).",
      "One pair also holds the atmosphere of both dates: its delay can mimic centimetres of motion over a few kilometres.",
    ],
    formula: ["d_LOS = −φ_unw · λ / (4π)", "1 fringe = λ / 2"],
    look: ["Compare the pattern with the coherence: trust only the coherent areas.", "Divide by the time between the dates for a rate, keeping the atmosphere in mind."],
    metrics: (g) => {
      const s = g.meta.stats.disp;
      return [
        ["1 fringe", `${g.meta.mm_per_fringe.toFixed(1)} mm`],
        ["Range", s ? `${s[0].toFixed(1)} … ${s[1].toFixed(1)} mm` : "–"],
        ["Time between the dates", `${g.meta.days} ${t("days")}`],
        ["Pixels kept (γ ≥ threshold)", `${(g.meta.kept_share * 100).toFixed(0)} % · γ ≥ ${g.meta.params.coh_thr}`],
      ];
    },
    controls: ["ref"],
  },
  {
    id: "velocity",
    title: "Velocity from the time series",
    goal: "See why GeoEyes uses all the scenes of the stack to estimate a velocity.",
    panels: [{ layer: "amp1", title: "PS velocity of the product", cmap: "gray", unit: "mm/yr", points: true }],
    what: [
      "With N scenes, GeoEyes forms the interferograms of the whole stack, keeps the points whose phase stays reliable over time (persistent scatterers), and unwraps in space and time.",
      "It then removes the DEM error of each point and the atmosphere, which is random from one date to the next but smooth in space.",
      "The velocity is the slope of a line fitted to the displacement series of each point: one pair gives one difference, the stack gives a trend.",
    ],
    formula: ["d(t) = d₀ + v · t + ε", "v from least squares over all dates"],
    look: ["Click a point: its series and the fitted line appear, with the rate a single pair would suggest at the same place.", "Velocities are relative to the reference of the product."],
    velocity: true,
  },
];

// ------------------------------------------------------------------ setup widgets
function BaselinePlot({ s, first, second, onPick }: { s: LearnStack; first: string; second: string; onPick: (d: string) => void }) {
  const W = 760;
  const H = 210;
  const pad = { l: 48, r: 12, t: 12, b: 26 };
  const ts = s.dates.map((d) => Date.parse(d));
  const t0 = Math.min(...ts);
  const t1 = Math.max(...ts);
  const b0 = Math.min(...s.bperp_m);
  const b1 = Math.max(...s.bperp_m);
  const X = (v: number) => pad.l + ((v - t0) / (t1 - t0 || 1)) * (W - pad.l - pad.r);
  const Y = (v: number) => pad.t + (1 - (v - b0) / (b1 - b0 || 1)) * (H - pad.t - pad.b);
  const i1 = s.dates.indexOf(first);
  const i2 = s.dates.indexOf(second);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("Baseline plot")}>
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#22324d" />
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={H - pad.b} stroke="#22324d" />
      <text x={6} y={pad.t + 8} fill="#93a4bf" fontSize="12">B⊥ m</text>
      <text x={pad.l} y={H - 6} fill="#93a4bf" fontSize="12">{s.dates[0]}</text>
      <text x={W - pad.r} y={H - 6} fill="#93a4bf" fontSize="12" textAnchor="end">{s.dates[s.dates.length - 1]}</text>
      <text x={pad.l - 4} y={Y(b1) + 3} fill="#93a4bf" fontSize="12" textAnchor="end">{b1.toFixed(0)}</text>
      <text x={pad.l - 4} y={Y(b0) + 3} fill="#93a4bf" fontSize="12" textAnchor="end">{b0.toFixed(0)}</text>
      {i1 >= 0 && i2 >= 0 && <line x1={X(ts[i1])} y1={Y(s.bperp_m[i1])} x2={X(ts[i2])} y2={Y(s.bperp_m[i2])} stroke="#ffd34d" strokeWidth="2" />}
      {s.dates.map((d, i) => {
        const on = d === first || d === second;
        return (
          <g key={d} className="cursor-pointer" onClick={() => onPick(d)}>
            <title>{`${d} · B⊥ ${s.bperp_m[i].toFixed(0)} m${d === s.reference_date ? ` · ${t("stack reference")}` : ""}`}</title>
            <circle cx={X(ts[i])} cy={Y(s.bperp_m[i])} r={on ? 6 : 4.5} fill={on ? "#ffd34d" : d === s.reference_date ? "#4cc2ff" : "#93a4bf"} stroke="#0b1220" />
          </g>
        );
      })}
    </svg>
  );
}

function ThumbPicker({ name, s, p, onCentre }: { name: string; s: LearnStack; p: LearnParams; onCentre: (r: number, c: number) => void }) {
  const q = useQuery({ queryKey: ["learn-thumb", name, s.stack_id], queryFn: () => api.learnThumb(name, s.stack_id), staleTime: Infinity });
  const cv = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!q.data || !cv.current) return;
    const [h, w] = q.data.meta.shape;
    const c = cv.current;
    c.width = w;
    c.height = h;
    const d = q.data.data;
    const sorted = Array.from(d).filter(Number.isFinite).sort((a, b) => a - b);
    const lo = sorted[Math.floor(sorted.length * 0.02)];
    const hi = sorted[Math.floor(sorted.length * 0.98)];
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(w, h);
    for (let i = 0; i < w * h; i++) {
      const g = color("gray", d[i], lo, hi)[0];
      img.data.set([g, g, g, 255], i * 4);
    }
    ctx.putImageData(img, 0, 0);
  }, [q.data]);
  if (!q.data) return <div className="py-8 text-center text-[12px] text-muted">{q.error ? (q.error as Error).message : t("Loading the scene…")}</div>;
  const [h, w] = q.data.meta.shape;
  const f = q.data.meta.factor;
  return (
    <div
      className="relative w-full cursor-crosshair overflow-hidden rounded-md border border-line"
      style={{ aspectRatio: `${w * s.spacing_m.range_ground} / ${h * s.spacing_m.azimuth}` }}
      onClick={(e) => {
        const b = e.currentTarget.getBoundingClientRect();
        onCentre(((e.clientY - b.top) / b.height) * h * f, ((e.clientX - b.left) / b.width) * w * f);
      }}
    >
      <canvas ref={cv} className="block h-full w-full" />
      <span
        className="pointer-events-none absolute border-2 border-[#ffd34d]"
        style={{ left: `${(p.col0 / (w * f)) * 100}%`, top: `${(p.row0 / (h * f)) * 100}%`, width: `${(p.cols / (w * f)) * 100}%`, height: `${(p.rows / (h * f)) * 100}%` }}
      />
    </div>
  );
}

// ------------------------------------------------------------------ charts
function Profile({ g, row, ex }: { g: Grid; row: number; ex: boolean }) {
  const [h, w] = g.meta.shape;
  if (row < 0 || row >= h) return null;
  const W = 640;
  const H = 150;
  const wr = Array.from(g.layers[ex ? "filt_ex" : "filt"].subarray(row * w, (row + 1) * w));
  const un = Array.from(g.layers[ex ? "unw_ex" : "unw"].subarray(row * w, (row + 1) * w));
  const lo = Math.min(-Math.PI, ...un.filter(Number.isFinite));
  const hi = Math.max(Math.PI, ...un.filter(Number.isFinite));
  const X = (i: number) => 36 + (i / (w - 1)) * (W - 46);
  const Y = (v: number) => 8 + (1 - (v - lo) / (hi - lo || 1)) * (H - 26);
  const path = (a: number[]) => a.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  return (
    <div className="rounded-lg border border-line bg-panel-2 p-2">
      <div className="mb-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="font-semibold text-ink">{t("Profile along row {r}", { r: row })}</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[#93a4bf]" /> {t("wrapped")}</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-[#ffd34d]" /> {t("unwrapped")}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {[-Math.PI, Math.PI].map((v) => (
          <g key={v}>
            <line x1={36} x2={W - 10} y1={Y(v)} y2={Y(v)} stroke="#22324d" strokeDasharray="3 3" />
            <text x={30} y={Y(v) + 3} fill="#93a4bf" fontSize="12" textAnchor="end">{v < 0 ? "−π" : "+π"}</text>
          </g>
        ))}
        {Y(Math.PI) - Y(hi) > 14 && <text x={30} y={Y(hi) + 8} fill="#93a4bf" fontSize="12" textAnchor="end">{hi.toFixed(0)}</text>}
        {Y(lo) - Y(-Math.PI) > 14 && <text x={30} y={Y(lo)} fill="#93a4bf" fontSize="12" textAnchor="end">{lo.toFixed(0)}</text>}
        <path d={path(wr)} fill="none" stroke="#93a4bf" strokeWidth="1" />
        <path d={path(un)} fill="none" stroke="#ffd34d" strokeWidth="1.6" />
        <text x={W - 10} y={H - 2} fill="#93a4bf" fontSize="12" textAnchor="end">{t("range →")} · rad</text>
      </svg>
    </div>
  );
}

function SeriesChart({ s, pairRate }: { s: LearnSeries; pairRate: number | null }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const x = s.dates.map((d) => Date.parse(d) / 1000);
    const axis = { stroke: "#93a4bf", grid: { stroke: "#1a2740", width: 1 }, ticks: { stroke: "#22324d", width: 1 }, font: "11px Inter, system-ui, sans-serif" };
    const plot = new uPlot(
      {
        width: el.clientWidth,
        height: 190,
        padding: [8, 8, 0, 0],
        legend: { show: false },
        cursor: { drag: { x: false, y: false } },
        scales: { x: { time: true } },
        axes: [
          { ...axis, values: (_u, v) => v.map((z) => new Date(z * 1000).toISOString().slice(0, 7)) },
          { ...axis, size: 46, label: t("mm (LOS)"), labelSize: 14, labelFont: "11px Inter, sans-serif" },
        ],
        series: [
          {},
          { stroke: "#4cc2ff", width: 1.2, points: { show: true, size: 6, fill: "#4cc2ff", stroke: "#0b1220" } },
          { stroke: "#ffd34d", width: 2, points: { show: false } },
        ],
      },
      [x, s.disp_mm, s.fit_mm] as uPlot.AlignedData,
      el,
    );
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height: 190 }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [s]);
  return (
    <div className="rounded-lg border border-line bg-panel-2 p-2">
      <div ref={box} className="w-full" />
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
        <span className="flex items-center gap-1 text-muted"><span className="h-2 w-2 rounded-full bg-[#4cc2ff]" /> {t("displacement of the point (0 at the first date)")}</span>
        <span className="flex items-center gap-1 text-muted"><span className="h-0.5 w-4 bg-[#ffd34d]" /> {t("line fitted to all dates")}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
        <span className="text-muted">{t("Velocity from the series")}</span>
        <span className="text-right font-mono text-ink-2">{fmt.vel(s.vel_mm_yr)} mm/yr</span>
        <span className="text-muted">{t("Velocity of the product")}</span>
        <span className="text-right font-mono text-ink-2">{fmt.vel(s.vel_product_mm_yr)} ± {fmt.num(s.vel_std_mm_yr)} mm/yr</span>
        <span className="text-muted">{t("Rate from this pair alone")}</span>
        <span className="text-right font-mono text-ink-2">{pairRate == null ? "–" : `${fmt.vel(pairRate)} mm/yr`}</span>
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-faint">
        {t("The pair's rate holds the atmosphere of two dates and its own reference: it can differ widely from the trend of the whole series.")}
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ page
function Select({ label, value, options, onChange, title }: { label: string; value: string | number; options: (string | number)[]; onChange: (v: string) => void; title?: string }) {
  return (
    <label className="flex items-center justify-between gap-2 text-[12px]" title={title ? t(title) : undefined}>
      <span className="text-muted">{t(label)}</span>
      <select className="h-7 min-w-0 max-w-[150px] rounded-md border border-line-2 bg-[#0f1828] px-1.5 text-[12px] text-ink" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

const WINDOWS_KM = [1, 2, 3, 5];

function sizeFor(s: LearnStack, km: number) {
  const az = s.spacing_m.azimuth;
  const gr = s.spacing_m.range_ground;
  const rows = Math.min(s.shape[0], Math.round((km * 1000) / az));
  const cols = Math.min(s.shape[1], Math.round((km * 1000) / gr));
  const target = Math.max(az, gr, (km * 1000) / 400);
  return { rows, cols, looks_az: Math.max(1, Math.round(target / az)), looks_rg: Math.max(1, Math.round(target / gr)) };
}

/** The Principles page: chapter 1 (one pair, below), 2 (hazard zoning, pages/LearnHazard.tsx), 3 (kinds of motion
 * and risk, pages/LearnBehaviour.tsx), 4 (infrastructure lines and consolidation, pages/LearnLines.tsx), 5 (two
 * geometries and soft soil, pages/LearnGeometry.tsx), 6 (ionosphere and subswath seams, pages/LearnIonosphere.tsx). */
export function Learn({ chapter, ...rest }: { ws: Workspace | undefined; project?: string; stack?: string; step?: number; chapter?: "hazard" | "behaviour" | "lines" | "geometry" | "ionosphere" }) {
  if (chapter === "hazard") return <HazardChapter ws={rest.ws} step={rest.step} />;
  if (chapter === "behaviour") return <BehaviourChapter ws={rest.ws} step={rest.step} />;
  if (chapter === "lines") return <LinesChapter ws={rest.ws} step={rest.step} />;
  if (chapter === "geometry") return <GeometryChapter ws={rest.ws} step={rest.step} />;
  if (chapter === "ionosphere") return <IonosphereChapter ws={rest.ws} step={rest.step} />;
  return <PairChapter {...rest} />;
}

function PairChapter({ ws, project, stack, step }: { ws: Workspace | undefined; project?: string; stack?: string; step?: number }) {
  const projects = Object.keys(ws?.projects ?? {}).sort();
  const name = project ?? projects[0];
  const stacksQ = useQuery({ queryKey: ["learn-stacks", name], queryFn: () => api.learnStacks(name!), enabled: !!name });
  const stacks = (stacksQ.data?.stacks ?? []).filter((s) => !s.error);
  const st = stacks.find((s) => s.stack_id === stack) ?? stacks[0];
  const k = Math.min(STEPS.length - 1, Math.max(0, step ?? 0));
  const S = STEPS[k];
  const go = (i: number) => {
    window.location.hash = href({ page: "learn", name, stack: st?.stack_id, step: i });
  };

  const [p, setP] = useState<LearnParams | null>(null);
  const [km, setKm] = useState(3);
  const [hover, setHover] = useState<[number, number] | null>(null);
  const [pickSlot, setPickSlot] = useState(0);
  const [sel, setSel] = useState<number | null>(null);
  const [exercise, setExercise] = useState(false);
  useEffect(() => {
    if (st) {
      setP({ ...st.default, coh_win: 5, coh_thr: 0.3, alpha: 0.6, fft: 32, passes: 1, linked: false, ref_row: -1, ref_col: -1 });
      setKm(3);
      setSel(null);
    }
  }, [st?.stack_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // sliders change the query only when they settle
  const [debounced, setDebounced] = useState<LearnParams | null>(null);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(p), 350);
    return () => window.clearTimeout(id);
  }, [p]);
  const pairQ = useQuery({
    queryKey: ["learn-pair", name, st?.stack_id, debounced, S.id === "unwrap" && exercise],
    queryFn: () => api.learnPair(name!, st!.stack_id, { ...debounced!, exercise: S.id === "unwrap" && exercise }),
    enabled: !!name && !!st && !!debounced,
    staleTime: Infinity,
    placeholderData: (prev) => prev,
  });
  const g: Grid | undefined = pairQ.data;
  const exOn = S.id === "unwrap" && !!g?.meta.params.exercise;
  const panels = exOn ? S.panels.map((x) => ({ ...x, layer: x.layer === "filt" ? "filt_ex" : x.layer === "unw" ? "unw_ex" : x.layer })) : S.panels;
  const ptsQ = useQuery({
    queryKey: ["learn-points", name, st?.stack_id, debounced && { ...debounced, alpha: 0, coh_win: 0, ref_row: 0, ref_col: 0 }],
    queryFn: () => api.learnPoints(name!, st!.stack_id, debounced!),
    enabled: !!g && !!S.velocity,
    staleTime: Infinity,
  });
  const pts = useMemo(
    () => (ptsQ.data && ptsQ.data.vel_range ? { rows: ptsQ.data.rows, cols: ptsQ.data.cols, vel: ptsQ.data.vel, range: ptsQ.data.vel_range } : undefined),
    [ptsQ.data],
  );
  const seriesQ = useQuery({
    queryKey: ["learn-series", name, ptsQ.data?.product, sel],
    queryFn: () => api.learnSeries(name!, ptsQ.data!.product!, ptsQ.data!.uids[sel!]),
    enabled: sel != null && !!ptsQ.data?.product,
  });

  const set = (patch: Partial<LearnParams>) => setP((old) => (old ? { ...old, ...patch } : old));
  const setWindow = (kmNew: number) => {
    if (!st || !p) return;
    const z = sizeFor(st, kmNew);
    const cr = p.row0 + p.rows / 2;
    const cc = p.col0 + p.cols / 2;
    setKm(kmNew);
    set({ ...z, row0: Math.max(0, Math.round(cr - z.rows / 2)), col0: Math.max(0, Math.round(cc - z.cols / 2)), ref_row: -1, ref_col: -1 });
  };
  const pickDate = (d: string) => {
    if (!p) return;
    const other = pickSlot === 0 ? p.second : p.first;
    if (d === other) return;
    const [a, b] = [d, other].sort();
    set({ first: a, second: b, ref_row: -1, ref_col: -1 });
    setPickSlot(1 - pickSlot);
  };

  const readout = useMemo(() => {
    if (!g || !hover) return null;
    const i = hover[0] * g.meta.shape[1] + hover[1];
    const L = g.layers;
    const f = (v: number, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : "–");
    return [
      ["row, col", `${hover[0]}, ${hover[1]}`],
      ["lat, lon", `${f(L.lat[i], 5)}, ${f(L.lon[i], 5)}`],
      ["amp 1 / 2", `${f(L.amp1[i], 1)} / ${f(L.amp2[i], 1)} dB`],
      ["φ raw · diff · filt", `${f(L.raw[i])} · ${f(L.diff[i])} · ${f(L.filt[i])} rad`],
      ["h", `${f(L.dem[i], 1)} m`],
      ["γ", f(L.coh[i])],
      ["φ unw", `${f(L.unw[i])} rad`],
      ["d LOS", `${f(L.disp[i], 1)} mm`],
    ];
  }, [g, hover]);

  if (!ws) return <div className="p-6 text-muted">{t("Loading…")}</div>;
  const pairRate = (() => {
    if (!g || sel == null || !pts) return null;
    const v = g.layers.disp[pts.rows[sel] * g.meta.shape[1] + pts.cols[sel]];
    return Number.isFinite(v) && g.meta.days ? (v / g.meta.days) * 365.25 : null;
  })();

  return (
    <div className="flex h-full min-h-0">
      <ChapterNav current="pair" steps={STEPS.map((s) => s.title)} step={k} onStep={go}>
        <div className="mt-4 space-y-2 border-t border-line pt-3">
          <Select label="Project" value={name ?? ""} options={projects} onChange={(v) => (window.location.hash = href({ page: "learn", name: v, step: k }))} />
          {stacks.length > 0 && (
            <Select label="Stack" value={st?.stack_id ?? ""} options={stacks.map((s) => s.stack_id)} onChange={(v) => (window.location.hash = href({ page: "learn", name, stack: v, step: k }))} />
          )}
        </div>
      </ChapterNav>

      <div className="min-w-0 flex-1 overflow-y-auto p-4">
        <header className="flex flex-wrap items-baseline gap-3">
          <span className="font-mono text-[12px] text-faint">{t("Step {i} of {n}", { i: k, n: STEPS.length - 1 })}</span>
          <h1 className="m-0 text-[20px] font-bold tracking-tight">{t(S.title)}</h1>
          {g && (
            <span className="text-[12px] text-muted">
              {g.meta.params.first} → {g.meta.params.second} · {g.meta.days} {t("days")} · B⊥ {g.meta.bperp_m.toFixed(0)} m
              {k >= 7 && k <= 9 && ` · γ ≥ ${g.meta.params.coh_thr}`}
            </span>
          )}
          {pairQ.isFetching && <span className="text-[12px] text-accent">{t("computing…")}</span>}
        </header>
        <p className="mt-1 max-w-[900px] text-[13.5px] text-ink-2">{t(S.goal)}</p>

        {!name || stacksQ.isLoading ? (
          <div className="mt-6 text-muted">{t("Loading…")}</div>
        ) : !st ? (
          <div className="mt-6 max-w-[640px] rounded-xl border border-line bg-panel p-4 text-[13px] text-muted">
            {t("This project has no stack yet: run its processing up to the stack, or choose another project.")}
          </div>
        ) : (
          <div className="mt-3 grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0 space-y-3">
              {S.id === "setup" && p && (
                <div className="grid max-w-[1000px] gap-4">
                  <Box title="Pairs of the stack">
                    <BaselinePlot s={st} first={p.first} second={p.second} onPick={pickDate} />
                    <div className="mt-1 text-[11.5px] text-muted">
                      {t("Next click sets scene {n}.", { n: pickSlot + 1 })} <span className="text-[#4cc2ff]">●</span> {t("stack reference")} <span className="text-[#ffd34d]">●</span> {t("chosen pair")}
                    </div>
                  </Box>
                  <Box title="Area">
                    <ThumbPicker
                      name={name!}
                      s={st}
                      p={p}
                      onCentre={(r, c) => set({ row0: Math.max(0, Math.round(r - p.rows / 2)), col0: Math.max(0, Math.round(c - p.cols / 2)), ref_row: -1, ref_col: -1 })}
                    />
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <Select
                        label="Window"
                        value={km}
                        options={WINDOWS_KM.filter((v) => {
                          const z = sizeFor(st, v);
                          return z.rows * z.cols <= 4_000_000;
                        })}
                        onChange={(v) => setWindow(Number(v))}
                        title="Side of the area, km"
                      />
                      <Select label="Looks (az × rg)" value={`${p.looks_az}×${p.looks_rg}`} options={[...new Set([`${p.looks_az}×${p.looks_rg}`, "1×1", "1×4", "2×2", "2×8", "3×3", "4×4", "5×5"])]} onChange={(v) => { const [a, r] = v.split("×").map(Number); set({ looks_az: a, looks_rg: r }); }} />
                    </div>
                    <div className="mt-1 text-[11.5px] text-faint">
                      {t("Radar geometry: rows = azimuth, columns = range. {dir}, looking {side}.", { dir: st.pass_direction ?? "", side: st.look_side ?? "" })}
                    </div>
                  </Box>
                </div>
              )}

              {pairQ.error && <div className="rounded-lg border border-[#5c2424] bg-[#2a1414] px-3 py-2 text-[12.5px] text-[#ffb3b3]">{(pairQ.error as Error).message}</div>}

              {g && panels.length > 0 && (
                <div className={`grid gap-3 ${panels.length === 1 ? "max-w-[760px]" : panels.length === 2 ? "md:grid-cols-2" : "md:grid-cols-3"}`}>
                  {panels.map((spec, i) => (
                    <Panel
                      key={i}
                      g={g}
                      spec={spec}
                      hover={hover}
                      setHover={setHover}
                      cohThr={p?.coh_thr ?? 0.3}
                      pts={spec.points ? pts : undefined}
                      selected={spec.points ? sel : null}
                      refPix={S.controls?.includes("ref") && g.meta.params.ref_row >= 0 ? [g.meta.params.ref_row, g.meta.params.ref_col] : null}
                      onPick={
                        S.controls?.includes("ref")
                          ? (r, c) => set({ ref_row: r, ref_col: c })
                          : spec.points && pts
                            ? (r, c) => {
                                let best = -1;
                                let bd = 9;
                                pts.rows.forEach((rr, j) => {
                                  const d = (rr - r) ** 2 + (pts.cols[j] - c) ** 2;
                                  if (d < bd) {
                                    bd = d;
                                    best = j;
                                  }
                                });
                                if (best >= 0) setSel(best);
                              }
                            : undefined
                      }
                    />
                  ))}
                </div>
              )}

              {g && S.profile && <Profile g={g} row={hover ? hover[0] : Math.floor(g.meta.shape[0] / 2)} ex={exOn} />}
              {g && S.velocity && (
                <div className="max-w-[760px] space-y-2">
                  {ptsQ.isLoading && <div className="text-[12px] text-muted">{t("Loading the points…")}</div>}
                  {ptsQ.data && !ptsQ.data.product && <div className="text-[12.5px] text-muted">{t("No product with points for this stack yet: run the PS processing first.")}</div>}
                  {ptsQ.data?.product && (
                    <div className="text-[12px] text-muted">
                      {t("{n} points of {p} in the area.", { n: fmt.int(ptsQ.data.uids.length), p: ptsQ.data.product })} {sel == null && t("Click a point.")}
                    </div>
                  )}
                  {seriesQ.data && <SeriesChart s={seriesQ.data} pairRate={pairRate} />}
                </div>
              )}

              {g && readout && S.panels.length > 0 && (
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 rounded-lg border border-line bg-panel-2 px-3 py-1.5 font-mono text-[11.5px]">
                  {readout.map(([a, b]) => (
                    <span key={a}>
                      <span className="text-faint">{a}</span> <span className="text-ink-2">{b}</span>
                    </span>
                  ))}
                </div>
              )}

              <div className="flex gap-2 pt-1">
                <Button disabled={k === 0} onClick={() => go(k - 1)}>
                  ← {t("Previous")}
                </Button>
                <Button variant="primary" disabled={k === STEPS.length - 1} onClick={() => go(k + 1)}>
                  {t("Next")} →
                </Button>
              </div>
            </div>

            {/* explanation and controls */}
            <aside className="space-y-3">
              {p && S.controls?.includes("coh") && (
                <Box title="Adjust">
                  <div className="space-y-2">
                    <Select label="Coherence window" value={p.coh_win ?? 5} options={[3, 5, 7, 9, 11]} onChange={(v) => set({ coh_win: Number(v) })} />
                    <label className="block text-[12px]">
                      <span className="flex justify-between text-muted">
                        {t("Coherence threshold")} <span className="font-mono text-ink-2">{(p.coh_thr ?? 0.3).toFixed(2)}</span>
                      </span>
                      <input type="range" min={0} max={0.9} step={0.05} value={p.coh_thr ?? 0.3} onChange={(e) => set({ coh_thr: Number(e.target.value), ref_row: -1, ref_col: -1 })} className="w-full" />
                    </label>
                  </div>
                </Box>
              )}
              {p && S.controls?.includes("filter") && (
                <Box title="Adjust">
                  <div className="space-y-2">
                    <label className="block text-[12px]">
                      <span className="flex justify-between text-muted">
                        α <span className="font-mono text-ink-2">{(p.alpha ?? 0.6).toFixed(1)}</span>
                      </span>
                      <input type="range" min={0} max={1} step={0.1} value={p.alpha ?? 0.6} onChange={(e) => set({ alpha: Number(e.target.value) })} className="w-full" />
                    </label>
                    <Select label="Window (pixels)" value={p.fft ?? 32} options={[16, 32, 64]} onChange={(v) => set({ fft: Number(v) })} />
                    <Select label="Passes" value={p.passes ?? 1} options={[0, 1, 2, 3]} onChange={(v) => set({ passes: Number(v) })} />
                  </div>
                </Box>
              )}
              {p && S.controls?.includes("ref") && (
                <Box title="Adjust">
                  <p className="m-0 text-[12px] text-muted">{t("Click an image to set the reference point (white circle).")}</p>
                  {p.ref_row != null && p.ref_row >= 0 && (
                    <Button className="mt-2" onClick={() => set({ ref_row: -1, ref_col: -1 })}>
                      {t("Automatic reference")}
                    </Button>
                  )}
                </Box>
              )}
              {S.controls?.includes("exercise") && (
                <Box title="Exercise">
                  <label className="flex items-start gap-2 text-[12px] text-ink-2">
                    <input type="checkbox" className="mt-0.5" checked={exercise} onChange={(e) => setExercise(e.target.checked)} />
                    {t("Unwrap the raw phase, flat-earth fringes included: the sawtooth becomes a ramp")}
                  </label>
                  <p className="mt-1.5 mb-0 text-[11.5px] leading-snug text-faint">
                    {t("This pair has few fringes once the geometry is removed, so its unwrapping changes little. The raw phase shows what unwrapping does.")}
                  </p>
                </Box>
              )}
              {p && S.controls?.includes("linked") && st.linked && (
                <Box title="Adjust">
                  <label className="flex items-center gap-2 text-[12px] text-ink-2">
                    <input type="checkbox" checked={!!p.linked} onChange={(e) => set({ linked: e.target.checked })} />
                    {t("Use the phase-linked SLCs (less noise, used by the GeoEyes chain for this stack)")}
                  </label>
                </Box>
              )}
              <Box title="What happens">
                <ul className="m-0 list-disc space-y-1 pl-4 text-[12.5px] leading-snug text-ink-2">
                  {S.what.map((w) => (
                    <li key={w}>{t(w)}</li>
                  ))}
                </ul>
              </Box>
              {S.formula && (
                <Box title="Formula">
                  <div className="space-y-1 font-mono text-[12.5px] text-ink">
                    {S.formula.map((f) => (
                      <div key={f}>{t(f)}</div>
                    ))}
                  </div>
                </Box>
              )}
              <Box title="What to look for">
                <ul className="m-0 list-disc space-y-1 pl-4 text-[12.5px] leading-snug text-ink-2">
                  {S.look.map((w) => (
                    <li key={w}>{t(w)}</li>
                  ))}
                </ul>
              </Box>
              {g && S.metrics && (
                <Box title="Numbers">
                  <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-[12px]">
                    {S.metrics(g, st).map(([a, b]) => (
                      <div key={a} className="contents">
                        <span className="text-muted">{t(a)}</span>
                        <span className="text-right font-mono text-ink-2">{b}</span>
                      </div>
                    ))}
                  </div>
                </Box>
              )}
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
