// Hazard kit: the colours, legends, charts and panels of the analysis cells, shared by the thematic-analysis page,
// the thematic layers of the maps and the Learn chapters (moved out of pages/Hazard.tsx: the maps no longer load
// the page, and the page and the thematic layers no longer import each other).
import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import { type BehaviourCell, type AnalysisKind, type BehaviourStatus, type BehaviourSummary, type AnalysisStatus, type ExposureSummary, type ConsolidationCell, type ConsolidationSummary, type DecomposeSummary, type GeologySummary, type HazardCell, type HazardCellsMeta, type HazardSummary, type LineProfile, type LinesSummary, type RiskBuilding, type RiskSummary } from "../api";
import type { LegendSpec } from "../legend";
import { RainBars } from "./RainBars";
import { t, ts } from "../i18n";
import { href } from "../state";
import { Button, fmt } from "../ui";
import { themeColor } from "../theme";

export type RGB = [number, number, number];

export const LEVELS = ["Very low", "Low", "Moderate", "High", "Very high"];
export const LEVEL_RGB: RGB[] = [
  [26, 152, 80],
  [145, 207, 96],
  [254, 224, 139],
  [252, 141, 89],
  [215, 48, 39],
];
export const NA_RGB: RGB = [75, 90, 115];
export const CLASS_RGB: RGB[] = [[75, 90, 115], [254, 224, 139], [252, 141, 89], [215, 48, 39]];
export const SEC_RGB: RGB[] = [[75, 90, 115], [194, 165, 207], [153, 112, 171], [118, 42, 131]];
export const RATE_BREAKS = [-30, -10, -2, 2, 10, 30];
export const RATE_RGB: RGB[] = [[33, 102, 172], [67, 147, 195], [146, 197, 222], [127, 139, 160], [244, 165, 130], [214, 96, 77], [178, 24, 43]];
export const LAG_RGB: RGB[] = [[68, 1, 84], [65, 68, 135], [42, 120, 142], [34, 168, 132], [122, 209, 81], [189, 223, 38], [253, 231, 37]];
export const DEFAULT_MATRIX = [
  [0, 0, 1, 1],
  [1, 1, 2, 3],
  [2, 2, 3, 4],
  [3, 3, 4, 4],
];

export type View = "hazard" | "intensity" | "secondary" | "rate" | "coupling" | "lag" | "groundwater" | "mode" | "behaviour" | "change" | "risk" | "lines" | "consolidation" | "up" | "east" | "soft_soil" | "exposure";
export interface ViewInfo {
  id: View;
  label: string;
  what: string;          // what the map shows
  read: string[];        // how to read it
}
export const VIEWS: ViewInfo[] = [
  {
    id: "hazard",
    label: "Hazard level",
    what: "The final level of each 100 m cell: how fast the ground moves (InSAR intensity) combined with what the motion can do (distortion for subsidence, slope for landslides).",
    read: [
      "Red cells need attention first: fast motion where it bends buildings or on steep ground.",
      "Read the level in the matrix: intensity (rows) × damage potential (columns).",
      "Grey cells were not assessed (too few points, or a slope the satellite cannot see).",
    ],
  },
  {
    id: "intensity",
    label: "Intensity (InSAR)",
    what: "How fast each cell moves in the direction that matters (sinking on flat ground, down the slope on hillsides), in four classes.",
    read: [
      "I0: within the measurement noise (stable). I1 to I3: slow to fast motion.",
      "A cell goes up one class if its motion follows the rain and a dry or wet year would make it faster, or if it accelerates.",
      "Rates are relative to the product's reference: tie it to GNSS for absolute values.",
    ],
  },
  {
    id: "secondary",
    label: "Damage potential",
    what: "What the motion can do. Subsidence: how much the ground bends between neighbouring cells over the horizon (angular distortion, compared with building-damage limits). Landslides: how steep the ground is.",
    read: [
      "S1 and above: differential settlement beyond the safe limit for buildings (1/500); S3: structural damage (1/150).",
      "Independent of the reference: it only uses differences between neighbouring cells.",
    ],
  },
  {
    id: "rate",
    label: "Rate",
    what: "The velocity of each cell in mm per year, along the expected motion: vertical on flat ground, along the slope on hillsides. As everywhere in GeoEyes, negative means sinking or moving down the slope.",
    read: [
      "Red: sinking (or moving down the slope). Blue: rising (or apparent upslope motion). Grey: about stable.",
      "Values are relative to the product's reference area: a reference that moves shifts the whole map.",
    ],
  },
  {
    id: "coupling",
    label: "Rain coupling",
    what: "Where the ground motion follows the rainfall, after removing its steady trend: the correlation between the motion and the accumulated rainfall surplus or deficit of the previous months.",
    read: [
      "Only statistically significant cells are coloured (tested against random rainfall timing, corrected for the number of cells).",
      "Red: more rain, more motion (e.g. wetter slopes slide faster). Blue: more rain, less sinking or uplift (e.g. aquifer recharge).",
      "Grey: no detectable link, or a series too short (less than a year).",
    ],
  },
  {
    id: "lag",
    label: "Rain lag",
    what: "For cells where the motion follows the rain: how many months after the rain the motion responds.",
    read: [
      "0–1 month: fast response (shallow ground). Longer lags: deeper water, slower recharge or drainage.",
      "Only significant cells are coloured.",
    ],
  },
  {
    id: "groundwater",
    label: "Groundwater coupling",
    what: "Where the ground motion follows the groundwater storage of the region (NASA GLDAS, with GRACE satellite gravity), after removing its steady trend.",
    read: [
      "Blue: the ground sinks more when storage falls and recovers when it rises, the elastic response of an aquifer system. Red: the opposite sign.",
      "The storage grid is 0.25° (about 27 km): it shows when the region gains or loses water, not where wells pump. Read it as a regional driver, not as a local cause.",
      "Only statistically significant cells are coloured; this layer does not change the hazard level.",
    ],
  },
  {
    id: "behaviour",
    label: "Kind of motion",
    what: "How each cell moves over time, from the simplest model its series supports: stable, steady, seasonal, speeding up, slowing down, a change of rate (onset) or a jump (step).",
    read: [
      "Steady: a constant rate. Seasonal: an annual cycle on the trend. Speeding up or slowing down: the motion grows or fades.",
      "Onset: the rate changes at a date (layer “Date of change”). Step: a sudden jump, an event or an unwrapping error to check.",
      "Click a cell: its series with the model that was kept.",
    ],
  },
  {
    id: "change",
    label: "Date of change",
    what: "For the cells whose motion changes (onset or step): when the change happens.",
    read: [
      "From the first date (dark) to the last (yellow); grey: no change.",
      "Many cells changing on the same date point to that acquisition (atmosphere, unwrapping) rather than to the ground.",
    ],
  },
  {
    id: "risk",
    label: "Risk to buildings",
    what: "Every building of the area: its hazard (from its own InSAR points, else from its cell) crossed with the consequence (floor area and a vulnerability proxy).",
    read: [
      "Red buildings first: a high hazard where the consequence is high.",
      "Building heights are rarely in open data: without one, the floor area assumes the median number of floors of the area.",
      "A screening map, not a structural assessment.",
    ],
  },
  {
    id: "exposure",
    label: "People and buildings exposed",
    what: "Population cells of about 90 m (GHS-POP 2025): their sinking class from the product's points, how many people live there, and with a flood month or a river-flood scenario, the share of the cell under water.",
    read: [
      "Colour: the sinking class of the cell; the stronger the colour, the more people live in it. Grey: no point in the cell (not observed).",
      "Switch to the flood of the month (blue: share of the cell flooded) or to the river-flood scenario (GloFAS depth).",
      "Global Surface Water is a monthly optical composite: cloud and short urban floods escape it. GloFAS ignores the dykes: an upper bound in a diked delta.",
    ],
  },
  {
    id: "lines",
    label: "Infrastructure lines",
    what: "Dykes, railways and main roads from OpenStreetMap, with the differential settlement along them: between stations 100 m apart, the angular distortion it would cause in 10 years.",
    read: [
      "Purple: beyond the damage limits (1/500, 1/300, 1/150). Green: below. Grey: too few InSAR points along the line.",
      "Click a line: its profile of vertical rate along the chainage.",
      "Dykes often carry few persistent scatterers (grass and trees on the slopes): grey stretches are common there.",
    ],
  },
  {
    id: "consolidation",
    label: "Remaining settlement",
    what: "For the cells that settle towards an end (consolidation of soft soil under a new load): the settlement still to come after the last date.",
    read: [
      "Only the cells where a fading curve fits much better than a straight line are coloured.",
      "Click a cell: its settlement, the curve projected ahead until it levels off and the Asaoka construction.",
      "A year of data sees only the start of most consolidation: read the values as estimates that firm up with longer series.",
    ],
  },
  {
    id: "up",
    label: "Vertical motion",
    what: "The vertical motion, separated from the east-west motion with a product that sees the area from the other side (ascending and descending).",
    read: [
      "Red: sinking; blue: rising, relative to the median of the area seen by both products.",
      "One geometry gives only its line of sight: its vertical projection takes any east-west motion for vertical.",
      "Hover a cell: the vertical and east-west motion with their uncertainty, and what each product alone would say.",
    ],
  },
  {
    id: "east",
    label: "East-west motion",
    what: "The horizontal motion along east-west, from the same decomposition. The north-south motion is assumed zero: polar orbits hardly see it.",
    read: [
      "Green: towards the east; purple: towards the west.",
      "Around a subsidence bowl the ground also moves sideways, towards the centre; on slopes it moves downhill.",
      "Values within twice their uncertainty are not significant.",
    ],
  },
  {
    id: "soft_soil",
    label: "Soft-soil thickness",
    what: "The thickness of the compressible layer under each cell, from a map or boreholes of the project, or else from an open global grid.",
    read: [
      "Thicker soft soil sinks more for the same drop of the water table, and consolidates more slowly.",
      "The open grid (Pelletier et al. 2016) is the depth to bedrock capped at 50 m: in a delta it hardly varies. Set a map or boreholes in the project for a real layer.",
    ],
  },
  {
    id: "mode",
    label: "Mode",
    what: "Which process each cell is assessed for, from the terrain slope.",
    read: ["Blue: flat ground, assessed as subsidence (vertical motion).", "Orange: slopes above the threshold, assessed as landslide (motion down the slope)."],
  },
];

// the views in the select box: the result, what it is made of, the water drivers
export const VIEW_GROUPS: [string, View[]][] = [
  ["Zoning", ["hazard"]],
  ["Components", ["intensity", "secondary", "rate", "mode"]],
  ["Water drivers", ["coupling", "lag", "groundwater"]],
  ["Kinds of motion and risk", ["behaviour", "change", "risk", "exposure"]],
  ["Infrastructure and consolidation", ["lines", "consolidation"]],
  ["Two geometries and soft soil", ["up", "east", "soft_soil"]],
];

/** Soft-soil thickness of the cells (same order as the cells). */
export interface Geology {
  buf: Float32Array; // thickness m, implied c_v m²/yr
  min: number;
  max: number;
}
export const SOIL_RGB: RGB[] = [[255, 247, 188], [254, 196, 79], [236, 112, 20], [153, 52, 4], [80, 30, 10]];
// east-west motion: purple towards the west, green towards the east (PRGn)
export const EAST_RGB: RGB[] = [[118, 42, 131], [153, 112, 171], [194, 165, 207], [127, 139, 160], [166, 219, 160], [90, 174, 97], [27, 120, 55]];
export const MOTION_BREAKS = RATE_BREAKS;

/** Remaining settlement of the consolidating cells (same order as the cells). */
export interface Consolidation {
  buf: Float32Array; // remaining mm, years to 90 %
  max: number;
}
export const CONS_RGB: RGB[] = [[254, 224, 139], [253, 174, 97], [244, 109, 67], [215, 48, 39], [165, 0, 38]];
// β classes of the lines: below 1/500, then the damage limits (as the damage potential)
export const LINE_RGB: RGB[] = [[26, 152, 80], [194, 165, 207], [153, 112, 171], [118, 42, 131]];

// kinds of motion (geoeyes behaviour), in the order of geoeyes.ml.behaviour.CLASSES
export const BEH_CLASSES = ["stable", "steady", "seasonal", "speeding", "slowing", "onset", "step"];
export const BEH_LABELS: Record<string, string> = {
  stable: "Stable",
  steady: "Steady",
  seasonal: "Seasonal",
  speeding: "Speeding up",
  slowing: "Slowing down",
  onset: "Onset (change of rate)",
  step: "Step (jump)",
};
export const BEH_RGB: RGB[] = [[127, 139, 160], [67, 147, 195], [53, 183, 121], [215, 48, 39], [253, 174, 97], [214, 51, 168], [140, 120, 210]];
export const ramp = (stops: RGB[], x: number): RGB => {
  const v = Math.min(1, Math.max(0, x)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(v));
  const f = v - i;
  return [0, 1, 2].map((k) => stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) as RGB;
};

/** The kinds of motion of the cells (same order as the cells): class index and change day per cell. */
export interface Behaviour {
  buf: Float32Array;
  span: number; // days from the first to the last date
}

export const signed = (v: number) => (v < 0 ? `−${-v}` : `${v}`);

export function rgb(c: RGB, a = 1) {
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`;
}

export function bin(v: number, breaks: number[]) {
  let k = 0;
  while (k < breaks.length && v >= breaks[k]) k++;
  return k;
}

export interface Cells {
  meta: HazardCellsMeta;
  buf: Float32Array;
  f: Record<string, number>;
}

export function cellColor(c: Cells, i: number, view: View, b?: Behaviour, cons?: Consolidation, geo?: Geology): [number, number, number, number] {
  const F = c.meta.fields.length;
  const g = (name: string) => c.buf[i * F + c.f[name]];
  const level = g("hazard");
  const coupled = g("rain_coupled") > 0;
  let col: RGB;
  let a = 215;
  switch (view) {
    case "hazard":
      col = level >= 0 ? LEVEL_RGB[level] : NA_RGB;
      break;
    case "intensity":
      col = g("intensity") >= 0 ? CLASS_RGB[g("intensity")] : NA_RGB;
      break;
    case "secondary":
      col = g("secondary") >= 0 ? SEC_RGB[g("secondary")] : NA_RGB;
      break;
    case "rate": {
      const r = g("rate_mm_yr");
      col = Number.isFinite(r) ? RATE_RGB[bin(-r, RATE_BREAKS)] : NA_RGB;     // red: sinking / downslope (< 0)
      break;
    }
    case "coupling": {
      const r = g("rain_r");
      if (!coupled || !Number.isFinite(r)) {
        col = NA_RGB;
        a = 70;
      } else col = r < 0 ? RATE_RGB[4 + Math.min(2, bin(Math.abs(r), [0.6, 0.8]))] : RATE_RGB[2 - Math.min(2, bin(Math.abs(r), [0.6, 0.8]))];
      break;
    }
    case "lag": {
      const l = g("rain_lag_months");
      if (!coupled || l < 0) {
        col = NA_RGB;
        a = 70;
      } else col = LAG_RGB[Math.min(6, l)];
      break;
    }
    case "groundwater": {
      const r = g("gw_r");
      if (!(g("gw_coupled") > 0) || !Number.isFinite(r)) {
        col = NA_RGB;
        a = 70;
      } else col = r < 0 ? RATE_RGB[4 + Math.min(2, bin(Math.abs(r), [0.6, 0.8]))] : RATE_RGB[2 - Math.min(2, bin(Math.abs(r), [0.6, 0.8]))];
      break;
    }
    case "behaviour": {
      const k = b ? b.buf[i * 2] : -1;
      col = k >= 0 ? BEH_RGB[k] : NA_RGB;
      if (k <= 0) a = 110;
      break;
    }
    case "change": {
      const d = b ? b.buf[i * 2 + 1] : -1;
      if (d < 0) {
        col = NA_RGB;
        a = 60;
      } else col = ramp(LAG_RGB, d / (b!.span || 1));
      break;
    }
    case "soft_soil": {
      const h = geo ? geo.buf[i * 2] : NaN;
      if (!Number.isFinite(h)) {
        col = NA_RGB;
        a = 45;
      } else col = ramp(SOIL_RGB, (h - geo!.min) / (geo!.max - geo!.min || 1));
      break;
    }
    case "risk":
    case "lines":
    case "up":
    case "east":
    case "exposure":
      col = NA_RGB; // the buildings / lines carry the colours; the cells stay as a faint background
      a = 45;
      break;
    case "consolidation": {
      const r = cons ? cons.buf[i * 2] : NaN;
      if (!Number.isFinite(r)) {
        col = NA_RGB;
        a = 45;
      } else col = ramp(CONS_RGB, r / (cons!.max || 1));
      break;
    }
    case "mode":
      col = g("mode") > 0 ? [192, 138, 62] : [91, 155, 213];
      break;
  }
  return [col[0], col[1], col[2], a];
}

export function MatrixFigure({ matrix }: { matrix: number[][] }) {
  return (
    <figure className="m-0" aria-label={t("Hazard matrix")}>
      <div className="grid grid-cols-[16px_auto_repeat(4,30px)] items-center gap-[3px]">
        <span className="row-span-4 self-stretch text-center text-[11px] text-muted [writing-mode:vertical-rl] rotate-180">{t("intensity")}</span>
        {[3, 2, 1, 0].map((i) => (
          <div key={i} className="contents">
            <span className="pr-1 text-right font-mono text-[11px] text-muted">I{i}</span>
            {matrix[i].map((lv, s) => (
              <span
                key={s}
                title={`I${i} × S${s} → ${t(LEVELS[lv])}`}
                className="flex h-6 items-center justify-center rounded-[4px] font-mono text-[11.5px] font-semibold text-on-accent"
                style={{ background: rgb(LEVEL_RGB[lv]) }}
              >
                {lv}
              </span>
            ))}
          </div>
        ))}
        <span />
        <span />
        {[0, 1, 2, 3].map((s) => (
          <span key={s} className="text-center font-mono text-[11px] text-muted">
            S{s}
          </span>
        ))}
      </div>
      <figcaption className="mt-1 pl-[40px] text-[11px] leading-tight text-muted">{t("damage potential")}</figcaption>
    </figure>
  );
}

export function About({ view }: { view: View }) {
  const v = VIEWS.find((x) => x.id === view)!;
  return (
    <div className="mt-3 rounded-lg border border-line bg-panel-2 px-2.5 py-2">
      <div className="text-[10.5px] font-semibold tracking-[1px] text-muted uppercase">{t("What this map shows")}</div>
      <p className="mt-1 text-[12px] leading-snug text-ink-2">{t(v.what)}</p>
      <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11.5px] leading-snug text-muted">
        {v.read.map((r) => (
          <li key={r}>{t(r)}</li>
        ))}
      </ul>
    </div>
  );
}

export function Swatches({ items }: { items: { color: RGB; label: string; alpha?: number }[] }) {
  return (
    <div className="mt-2 space-y-[3px]">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-2 text-[12px]">
          <span className="h-3 w-3 flex-none rounded-[3px]" style={{ background: rgb(it.color, it.alpha ?? 1) }} />
          <span className="text-ink-2">{it.label}</span>
        </div>
      ))}
    </div>
  );
}

/** The legend of a view of the zoning as data (the page and the map export draw it); null: the view has its own
 * legend (behaviour, buildings, lines...). */
export function hazardLegendSpec(view: View, s: HazardSummary): LegendSpec | null {
  if (view === "behaviour" || view === "change" || view === "risk" || view === "lines" || view === "consolidation" || view === "up" || view === "east" || view === "soft_soil" || view === "exposure") return null; // BehaviourLegend
  const title = t(VIEWS.find((x) => x.id === view)?.label ?? view);
  const p = s.params as Record<string, number[] | number>;
  const sb = p.subsidence_breaks as number[];
  const lb = p.landslide_breaks as number[];
  const db = p.distortion_breaks as number[];
  const slb = p.slope_breaks as number[];
  const frac = (x: number) => `1/${Math.round(1 / x)}`;
  const na = (label: string) => ({ rgb: NA_RGB, label, alpha: 0.35 });
  if (view === "hazard")
    return {
      title,
      items: [...LEVELS.map((l, i) => ({ rgb: LEVEL_RGB[i], label: t(l) })).reverse(), { rgb: NA_RGB, label: t("not assessed") }],
      matrix: (s.params.matrix as number[][]) ?? DEFAULT_MATRIX,
      matrixRgb: LEVEL_RGB,
    };
  if (view === "intensity")
    return {
      title,
      items: [
        { rgb: CLASS_RGB[3], label: `I3 · ${t("subsidence")} ≥ ${sb[1]} · ${t("landslide")} ≥ ${lb[1]} mm/yr` },
        { rgb: CLASS_RGB[2], label: `I2 · ${sb[0]}–${sb[1]} · ${lb[0]}–${lb[1]} mm/yr` },
        { rgb: CLASS_RGB[1], label: `I1 · ${t("above stability")} · < ${sb[0]} · < ${lb[0]} mm/yr` },
        { rgb: CLASS_RGB[0], label: `I0 · ${t("stable")}: < max(${p.stable_floor_mm_yr} mm/yr, ${p.stable_sigma}σ)` },
      ],
    };
  if (view === "secondary")
    return {
      title,
      head: t("Subsidence: angular distortion in {n} years", { n: String(p.horizon_yr) }),
      items: [
        { rgb: SEC_RGB[3], label: `S3 ≥ ${frac(db[2])} · ${t("structural damage")}` },
        { rgb: SEC_RGB[2], label: `S2 ${frac(db[1])}–${frac(db[2])} · ${t("cracking")}` },
        { rgb: SEC_RGB[1], label: `S1 ${frac(db[0])}–${frac(db[1])} · ${t("beyond the safe limit")}` },
        { rgb: SEC_RGB[0], label: `S0 < ${frac(db[0])}` },
      ],
      notes: [t("Landslide: susceptibility map, else slope classes {s}°", { s: slb.join(" / ") })],
    };
  if (view === "rate")
    return {
      title,
      items: RATE_RGB.map((c, i) => ({
        rgb: c,
        // colour i holds the rates r with −r in [B(i−1), B(i)): sinking (r < 0) is red
        label:
          (i === 0 ? `> ${-RATE_BREAKS[0]}` : i === RATE_RGB.length - 1 ? `≤ ${signed(-RATE_BREAKS[i - 1])}` : `${signed(-RATE_BREAKS[i])} … ${signed(-RATE_BREAKS[i - 1])}`) +
          " mm/yr" +
          (i === RATE_RGB.length - 1 ? ` · ${t("sinking / downslope, fast")}` : i === 3 ? ` · ${t("about stable")}` : i === 0 ? ` · ${t("rising / upslope")}` : ""),
      })).reverse(),
    };
  if (view === "coupling")
    return {
      title,
      items: [
        { rgb: RATE_RGB[6], label: `r < −0.8 · ${t("more rain, more motion")}` },
        { rgb: RATE_RGB[4], label: "−0.6 ≤ r < 0" },
        { rgb: RATE_RGB[2], label: "0 < r ≤ 0.6" },
        { rgb: RATE_RGB[0], label: `r > 0.8 · ${t("more rain, less sinking / uplift")}` },
        na(t("not significant / not assessed")),
      ],
      notes: [`d = a + b·t + k·CRD(t − τ) · FDR ${String(p.alpha)}`],
    };
  if (view === "groundwater") {
    const gw = s.groundwater;
    if (!gw?.used)
      return {
        title,
        text:
          gw?.reason === "no EARTHDATA_TOKEN"
            ? t("Groundwater needs an Earthdata login: set EARTHDATA_TOKEN and run the zoning again.")
            : gw?.reason === "off"
              ? t("Groundwater coupling is off in the parameters.")
              : t("No groundwater in this zoning: run it again."),
      };
    return {
      title,
      items: [
        { rgb: RATE_RGB[6], label: `r < −0.8 · ${t("more storage, more motion")}` },
        { rgb: RATE_RGB[4], label: "−0.6 ≤ r < 0" },
        { rgb: RATE_RGB[2], label: "0 < r ≤ 0.6" },
        { rgb: RATE_RGB[0], label: `r > 0.8 · ${t("less storage, more sinking (aquifer)")}` },
        na(t("not significant / not assessed")),
      ],
      notes: [
        `d = a + b·t + g·GWS(t − τ) · ${t("{n} of {m} cells significant", { n: gw.cells_significant ?? 0, m: gw.cells_tested ?? 0 })}` +
          (gw.trend_mm_yr != null ? ` · ${t("storage trend {v} mm/yr", { v: fmt.vel(gw.trend_mm_yr) })}` : ""),
      ],
    };
  }
  if (view === "lag")
    return { title, items: [...LAG_RGB.map((c, i) => ({ rgb: c, label: t(i === 1 ? "{n} month" : "{n} months", { n: i }) })), na(t("not significant"))] };
  return {
    title,
    items: [
      { rgb: [91, 155, 213], label: t("subsidence (vertical motion)") },
      { rgb: [192, 138, 62], label: t("landslide (slope ≥ {s}°, motion down the slope)", { s: String(p.landslide_min_slope_deg) }) },
    ],
  };
}

/** A legend described by a ``LegendSpec`` (without its title: the page shows the title elsewhere). */
export function SpecLegend({ spec }: { spec: LegendSpec }) {
  if (spec.text) return <p className="mt-1 text-[12px] leading-snug text-muted">{spec.text}</p>;
  const sw = spec.items && <Swatches items={spec.items.map((x) => ({ color: x.rgb as RGB, label: x.label, alpha: x.alpha }))} />;
  return (
    <>
      {spec.head && <div className="mt-1 text-[11.5px] text-muted">{spec.head}</div>}
      {spec.matrix ? (
        <div className="mt-1 flex items-start justify-between gap-3">
          {sw}
          <MatrixFigure matrix={spec.matrix} />
        </div>
      ) : (
        sw
      )}
      {spec.ramp && (
        <div className="mt-2">
          <div className="h-2.5 rounded" style={{ background: `linear-gradient(90deg, ${spec.ramp.stops.map((c) => `rgb(${c.join(",")})`).join(",")})` }} />
          <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-ink-2">
            <span>{spec.ramp.lo}</span>
            <span className="font-sans text-faint">{spec.ramp.unit}</span>
            <span>{spec.ramp.hi}</span>
          </div>
        </div>
      )}
      {spec.notes?.map((n) => (
        <p key={n} className="mt-2 text-[11px] leading-snug text-faint">
          {n}
        </p>
      ))}
    </>
  );
}

export function Legend({ view, s }: { view: View; s: HazardSummary }) {
  const spec = hazardLegendSpec(view, s);
  return spec ? <SpecLegend spec={spec} /> : null;
}

/** The series of a cell with its models; ``compact``: the series, the line and ``model`` only (no rainfall). */
export function CellChart({ c, model, compact = false }: { c: HazardCell; model?: (number | null)[]; compact?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const x = c.dates.map((d) => Date.parse(d) / 1000);
    const axis = { stroke: themeColor("muted"), grid: { stroke: themeColor("chip"), width: 1 }, ticks: { stroke: themeColor("line-2"), width: 1 }, font: "11px 'Lexend Variable', system-ui, sans-serif" };
    const series: uPlot.Series[] = [
      {},
      { stroke: themeColor("accent"), width: 1.5, points: { show: true, size: 5, fill: themeColor("accent"), stroke: themeColor("bg") }, spanGaps: true },
      { stroke: themeColor("muted"), width: 1.2, dash: [4, 4], points: { show: false } },
    ];
    const data: (number | null)[][] = [x, c.series_mm, c.linear_mm ?? c.series_mm.map(() => null)];
    if (c.rain_model_mm && !compact) {
      series.push({ stroke: themeColor("warn"), width: 1.8, points: { show: false } });
      data.push(c.rain_model_mm);
    }
    if (c.gw_model_mm && c.gw_coupled && !compact) {
      series.push({ stroke: "#7ee0c3", width: 1.8, dash: [6, 3], points: { show: false } });
      data.push(c.gw_model_mm);
    }
    if (model) {
      series.push({ stroke: "#d633a8", width: 2, points: { show: false } });
      data.push(model);
    }
    const plot = new uPlot(
      {
        width: el.clientWidth,
        height: 170,
        padding: [8, 8, 0, 0],
        legend: { show: false },
        cursor: { drag: { x: false, y: false } },
        scales: { x: { time: true } },
        axes: [
          { ...axis, values: (_u, t) => t.map((v) => new Date(v * 1000).toISOString().slice(0, 7)) },
          { ...axis, size: 48, label: c.mode === "subsidence" ? t("mm (up +)") : t("mm (upslope +)"), labelSize: 14, labelFont: "11px 'Lexend Variable', sans-serif" },
        ],
        series,
      },
      data as uPlot.AlignedData,
      el,
    );
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height: 170 }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [c, model, compact]);
  const rainMonths = c.rain.months.map((m, i) => ({ month: m, mm: c.rain.mm[i] }));
  return (
    <div>
      <div ref={box} className="w-full" />
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-accent" /> {t("cell median")}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-4 border-t-2 border-dashed border-muted" /> {t("linear")}
        </span>
        {c.rain_model_mm && !compact && (
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4 bg-warn" /> {t("trend + k·CRD(t − {n} mo)", { n: c.rain_lag_months })}
          </span>
        )}
        {c.gw_model_mm && c.gw_coupled && !compact && (
          <span className="flex items-center gap-1">
            <span className="w-4 border-t-2 border-dashed border-[#7ee0c3]" /> {t("trend + g·GWS(t − {n} mo)", { n: c.gw_lag_months ?? 0 })}
          </span>
        )}
        {model && (
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4 bg-[#d633a8]" /> {t("model of the kind of motion")}
          </span>
        )}
      </div>
      {!compact && (
        <>
          <div className="mt-2">
            <RainBars months={rainMonths} from={c.dates[0]} to={c.dates[c.dates.length - 1]} />
          </div>
          <div className="text-[11px] text-faint">{t("Monthly rainfall of the cell's pixel")} · {ts(c.rain.source).split(" (")[0]}</div>
        </>
      )}
    </div>
  );
}

export function Swatch({ color, label }: { color: RGB; label: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span className="h-3 w-3 flex-none rounded-[3px]" style={{ background: rgb(color) }} />
      <span className="text-ink-2">{label}</span>
    </div>
  );
}

export function BehaviourLegend({
  view,
  st,
  first,
  last,
  onRun,
  expMode,
  setExpMode,
}: {
  view: View;
  st: BehaviourStatus | undefined;
  first?: string;
  last?: string;
  onRun: (kind: AnalysisKind, params?: Record<string, unknown>) => void;
  expMode: ExpMode;
  setExpMode: (m: ExpMode) => void;
}) {
  const kind = KIND_OF_VIEW[view] ?? "behaviour";
  const a = st?.[kind];
  if (view === "exposure") return <ExposureLegend a={st?.exposure} mode={expMode} setMode={setExpMode} onRun={onRun} />;
  if (!a?.summary)
    return (
      <div className="mt-2 space-y-2 text-[12px] leading-snug text-muted">
        <p className="m-0">{t(RUN_TEXT[kind][0])}</p>
        {kind === "risk" && !st?.buildings && <p className="m-0 text-faint">{t("Tip: run the building analysis first (geoeyes buildings) so that buildings with their own InSAR points are rated from them.")}</p>}
        <Button variant="primary" disabled={a?.running} onClick={() => onRun(kind)}>
          {a?.running ? t("Running…") : t(RUN_TEXT[kind][1])}
        </Button>
        {a?.failed && <div className="text-bad">{a.log.slice(-1)[0]}</div>}
      </div>
    );
  const again = (
    <button type="button" className="mt-2 text-[11.5px] text-accent hover:underline disabled:opacity-50" disabled={a.running} onClick={() => onRun(kind)}>
      {a.running ? t("Running…") : t("Run again")}
    </button>
  );
  if (view === "behaviour") {
    const s = (a.summary as BehaviourSummary);
    return (
      <div className="mt-2 space-y-[3px]">
        {BEH_CLASSES.map((c, i) => (
          <Swatch key={c} color={BEH_RGB[i]} label={`${t(BEH_LABELS[c])} · ${fmt.int(s.counts[c] ?? 0)}`} />
        ))}
        {s.warnings.map((w) => (
          <p key={w} className="mt-1.5 mb-0 text-[11.5px] leading-snug text-warn-ink">{ts(w)}</p>
        ))}
        {again}
      </div>
    );
  }
  if (view === "change") {
    const s = (a.summary as BehaviourSummary);
    return (
      <div className="mt-2">
        <div className="h-2.5 rounded-sm" style={{ background: `linear-gradient(90deg,${LAG_RGB.map((c) => rgb(c)).join(",")})` }} />
        <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
          <span>{first}</span>
          <span>{last}</span>
        </div>
        <p className="mt-1.5 mb-0 text-[12px] text-ink-2">{t("{n} cells change (onset or step)", { n: fmt.int((s.counts.onset ?? 0) + (s.counts.step ?? 0)) })}</p>
        {s.warnings.map((w) => (
          <p key={w} className="mt-1.5 mb-0 text-[11.5px] leading-snug text-warn-ink">{ts(w)}</p>
        ))}
        {again}
      </div>
    );
  }
  if (view === "lines") {
    const l = a.summary as LinesSummary;
    return (
      <div className="mt-2 space-y-[3px]">
        <Swatch color={LINE_RGB[3]} label={`β ≥ 1/150 · ${t("structural damage")}`} />
        <Swatch color={LINE_RGB[2]} label={`1/300 – 1/150 · ${t("cracking")}`} />
        <Swatch color={LINE_RGB[1]} label={`1/500 – 1/300 · ${t("beyond the safe limit")}`} />
        <Swatch color={LINE_RGB[0]} label={`< 1/500`} />
        <Swatch color={NA_RGB} label={t("too few InSAR points")} />
        <div className="mt-2 grid grid-cols-[1fr_auto_auto] gap-x-3 text-[11.5px]">
          {Object.entries(l.by_kind)
            .filter(([, v]) => v.lines > 0)
            .map(([k, v]) => (
              <div key={k} className="contents">
                <span className="text-muted">{t(LINE_KINDS[k] ?? k)}</span>
                <span className="text-right font-mono text-ink-2">{v.km} km</span>
                <span className="text-right font-mono text-ink-2" title={t("stations beyond 1/500")}>
                  {v.flagged_stations}
                </span>
              </div>
            ))}
        </div>
        {again}
      </div>
    );
  }
  if (view === "consolidation") {
    const c = a.summary as ConsolidationSummary;
    return (
      <div className="mt-2">
        <div className="h-2.5 rounded-sm" style={{ background: `linear-gradient(90deg,${CONS_RGB.map((x) => rgb(x)).join(",")})` }} />
        <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
          <span>0</span>
          <span>{t("mm still to come")}</span>
          <span>{c.remaining_mm ? fmt.num(c.remaining_mm.p90, 0) : "–"}</span>
        </div>
        <p className="mt-1.5 mb-0 text-[12px] text-ink-2">{t("{n} of {m} sinking cells consolidate", { n: fmt.int(c.consolidating), m: fmt.int(c.sinking_cells) })}</p>
        {c.check.mae_curve_mm != null && (
          <p className="mt-1 mb-0 text-[11.5px] leading-snug text-muted">
            {t("Check on the last {n} dates: curve {a} mm, straight line {b} mm (mean error).", { n: c.check.test_epochs ?? 0, a: c.check.mae_curve_mm, b: c.check.mae_line_mm ?? "–" })}
          </p>
        )}
        {again}
      </div>
    );
  }
  if (view === "up" || view === "east") return <DecomposeLegend s={a.summary as DecomposeSummary} view={view} again={again} />;
  if (view === "soft_soil") return <GeologyLegend s={a.summary as GeologySummary} again={again} />;
  const r = a.summary as RiskSummary;
  return (
    <div className="mt-2 space-y-[3px]">
      {[4, 3, 2, 1, 0].map((k) => (
        <Swatch key={k} color={LEVEL_RGB[k]} label={`${t(LEVELS[k])} · ${fmt.int(r.by_risk[LEVELS[k].toLowerCase()] ?? 0)}`} />
      ))}
      <Swatch color={NA_RGB} label={`${t("not assessed")} · ${fmt.int(r.n_buildings - r.assessed)}`} />
      <p className="mt-1.5 mb-0 text-[11.5px] leading-snug text-muted">
        {t("{n} buildings: hazard from their own InSAR points for {a}, from their cell for {b}.", { n: fmt.int(r.n_buildings), a: fmt.int(r.by_source.building ?? 0), b: fmt.int(r.by_source.cell ?? 0) })}
      </p>
      {r.warnings.map((w) => (
        <p key={w} className="mt-1 mb-0 text-[11.5px] leading-snug text-warn-ink">{ts(w)}</p>
      ))}
      {again}
    </div>
  );
}

// ------------------------------------------------------------ exposure (geoeyes exposure)
export type ExpMode = "subsidence" | "flood" | "glofas";
export const EXP_RGB: RGB[] = [[150, 160, 178], RATE_RGB[4], RATE_RGB[5], RATE_RGB[6], [110, 10, 30]];
export const FLOOD_RGB: RGB[] = [[198, 219, 239], [107, 174, 214], [33, 113, 181], [8, 48, 107]];
export const EXP_F = { lon: 0, lat: 1, people: 2, points: 3, v: 4, cls: 5, flooded: 6, depth: 7 } as const;
export const FLOOD_BREAKS = { flood: [0.1, 0.3, 0.6], glofas: [0.5, 1, 2] } as const;
export const FLOOD_LABELS = { flood: ["< 10 %", "10–30 %", "30–60 %", "≥ 60 %"], glofas: ["< 0.5 m", "0.5–1 m", "1–2 m", "≥ 2 m"] } as const;
// opacity of a cell: [sparse, dense] (alpha 0-255); the colour strengthens with the people living in the cell
export const EXP_ALPHA = { dry: [25, 25], unseen: [20, 80], stable: [30, 110], sinking: [90, 250], flooded: [90, 240] } as const;
export const alphaOf = (k: keyof typeof EXP_ALPHA, dense: number) => Math.round(EXP_ALPHA[k][0] + (EXP_ALPHA[k][1] - EXP_ALPHA[k][0]) * dense);

export function expColor(buf: Float32Array, i: number, mode: ExpMode): [number, number, number, number] {
  const g = (k: keyof typeof EXP_F) => buf[i * 8 + EXP_F[k]];
  const dense = Math.min(1, Math.sqrt(Math.max(0, g("people")) / 400)); // ~ 50 000 people / km² at full colour
  if (mode === "flood" || mode === "glofas") {
    const v = mode === "flood" ? g("flooded") : g("depth");
    if (!Number.isFinite(v) || v <= 0) return [NA_RGB[0], NA_RGB[1], NA_RGB[2], alphaOf("dry", dense)];
    const c = FLOOD_RGB[bin(v, [...FLOOD_BREAKS[mode]])];
    return [c[0], c[1], c[2], alphaOf("flooded", dense)];
  }
  const k = g("cls");
  if (k < 0) return [NA_RGB[0], NA_RGB[1], NA_RGB[2], alphaOf("unseen", dense)];
  const c = EXP_RGB[k];
  return [c[0], c[1], c[2], alphaOf(k === 0 ? "stable" : "sinking", dense)];
}

/** A legend swatch as a dense cell looks on the map, over the panel. */
export function ExpSwatch({ c, alpha }: { c: RGB; alpha: number }) {
  return <span className="h-3 w-3 flex-none rounded-[3px] border border-line" style={{ background: rgb(c, alpha / 255) }} />;
}

export function ExposureLegend({
  a,
  mode,
  setMode,
  onRun,
}: {
  a?: AnalysisStatus<ExposureSummary>;
  mode: ExpMode;
  setMode: (m: ExpMode) => void;
  onRun: (kind: AnalysisKind, params?: Record<string, unknown>) => void;
}) {
  const s = a?.summary;
  const [month, setMonth] = useState(s?.params.flood_month ?? "");
  const [rp, setRp] = useState<number>(s?.params.glofas_rp ?? 0);
  useEffect(() => {
    if (s) {
      setMonth(s.params.flood_month ?? "");
      setRp(s.params.glofas_rp ?? 0);
    }
  }, [s?.created]); // eslint-disable-line react-hooks/exhaustive-deps
  const badMonth = !!month && !/^20(1[7-9]|2[0-4])-(0[1-9]|1[0-2])$/.test(month);
  const form = (
    <div className="mt-2 space-y-1.5 border-t border-line pt-2 text-[12px]">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-ink-2">
          {t("Flood month")}
          <input
            className="h-7 w-24 rounded border border-line-2 bg-sunken px-1.5 font-mono text-[12px]"
            placeholder="2024-09"
            value={month}
            onChange={(e) => setMonth(e.target.value.trim())}
            aria-invalid={badMonth}
          />
        </label>
        <label className="flex items-center gap-1.5 text-ink-2">
          GloFAS
          <select className="h-7 rounded border border-line-2 bg-sunken px-1 text-[12px]" value={rp} onChange={(e) => setRp(Number(e.target.value))}>
            <option value={0}>{t("none")}</option>
            {[10, 20, 50, 75, 100, 200, 500].map((r) => (
              <option key={r} value={r}>
                {t("{n} yr", { n: r })}
              </option>
            ))}
          </select>
        </label>
      </div>
      {badMonth && <div className="text-bad">{t("A month from 2017-01 to 2024-12 (the surface-water record).")}</div>}
      <Button variant={s ? "ghost" : "primary"} disabled={a?.running || badMonth} onClick={() => onRun("exposure", { flood_month: month, glofas_rp: rp })}>
        {a?.running ? t("Running…") : s ? t("Run again") : t("Count the people and buildings exposed")}
      </Button>
      {a?.failed && <div className="text-bad">{a.log.slice(-1)[0]}</div>}
      {a?.running && a.log.length > 0 && <div className="font-mono text-[11px] text-faint">{a.log.slice(-1)[0]}</div>}
    </div>
  );
  if (!s)
    return (
      <div className="mt-2 text-[12px] leading-snug text-muted">
        <p className="m-0">{t(RUN_TEXT.exposure[0])}</p>
        {form}
      </div>
    );
  const sub = s.subsidence;
  const modes: [ExpMode, string][] = [["subsidence", "Sinking"]];
  if (s.flood) modes.push(["flood", "Flood of the month"]);
  if (s.glofas) modes.push(["glofas", "River flood"]);
  const f = s.flood;
  return (
    <div className="mt-2 text-[12px]">
      {modes.length > 1 && (
        <div className="mb-2 flex gap-1" role="radiogroup" aria-label={t("Colour the cells by")}>
          {modes.map(([m, l]) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              onClick={() => setMode(m)}
              className={`rounded px-2 py-0.5 text-[11.5px] ${mode === m ? "bg-accent text-white" : "bg-sunken text-ink-2 hover:text-ink"}`}
            >
              {t(l)}
            </button>
          ))}
        </div>
      )}
      {mode !== "subsidence" && (
        <div className="mb-2 space-y-[3px]">
          <div className="text-[11px] text-faint">{t(mode === "flood" ? "share of the cell flooded" : "river flood depth (GloFAS)")}</div>
          {FLOOD_RGB.map((c, k) => (
            <div key={k} className="flex items-center gap-2">
              <ExpSwatch c={c} alpha={EXP_ALPHA.flooded[1]} />
              <span className="text-ink-2">{FLOOD_LABELS[mode][k]}</span>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <ExpSwatch c={NA_RGB} alpha={EXP_ALPHA.dry[1]} />
            <span className="text-muted">{t(mode === "flood" ? "no new water" : "dry")}</span>
          </div>
        </div>
      )}
      <p className="mt-0 mb-1.5 text-[11px] text-faint">{t("Stronger colour: more people in the cell.")}</p>
      <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-x-2 gap-y-[3px]">
        <span />
        <span className="text-[11px] text-faint">{t("sinking, mm/yr")}</span>
        <span className="text-right text-[11px] text-faint">{t("people")}</span>
        <span className="text-right text-[11px] text-faint">{t("buildings")}</span>
        {sub.classes.map((c, k) => (
          <div key={c.class} className="contents">
            {mode === "subsidence" ? <ExpSwatch c={EXP_RGB[k]} alpha={EXP_ALPHA[k === 0 ? "stable" : "sinking"][1]} /> : <span />}
            <span className="text-ink-2">{c.class}</span>
            <span className="text-right font-mono text-ink">{fmt.int(c.people)}</span>
            <span className="text-right font-mono text-ink-2">{c.buildings != null ? fmt.int(c.buildings) : "–"}</span>
          </div>
        ))}
        {mode === "subsidence" ? <ExpSwatch c={NA_RGB} alpha={EXP_ALPHA.unseen[1]} /> : <span />}
        <span className="text-muted">{t("not observed")}</span>
        <span className="text-right font-mono text-muted">{fmt.int(sub.people_not_observed)}</span>
        <span className="text-right font-mono text-muted">{sub.buildings_not_observed != null ? fmt.int(sub.buildings_not_observed) : "–"}</span>
      </div>
      {f && (
        <div className="mt-2 border-t border-line pt-2 leading-snug text-ink-2">
          <div className="font-medium text-ink">{t("Flood of {month}", { month: f.month })}</div>
          <div>
            {t("{km2} km² of new water against {dry}; {p} people in it ({q} on sinking ground).", {
              km2: f.flooded_km2,
              dry: f.dry_month,
              p: fmt.int(f.people),
              q: fmt.int(f.people_on_sinking_ground),
            })}
          </div>
          {f.rain_month_mm != null && (
            <div>
              {t("Rain: {mm} mm in the month, {d} mm on {date}.", { mm: fmt.int(f.rain_month_mm), d: f.rain_wettest_day?.mm ?? "–", date: f.rain_wettest_day?.date ?? "–" })}
              {f.rain_peak_30min && ` ${t("Peak {mmh} mm/h at {time} UTC (IMERG, 30 min).", { mmh: f.rain_peak_30min.mm_h, time: f.rain_peak_30min.time.replace("T", " ").slice(0, 16) })}`}
            </div>
          )}
          {f.v_vert_flooded_mm_yr != null && (
            <div>{t("Points on flooded ground: {a} mm/yr, on dry ground: {b} mm/yr (median).", { a: f.v_vert_flooded_mm_yr, b: f.v_vert_dry_mm_yr ?? "–" })}</div>
          )}
          <div className="text-[11.5px] text-warn-ink">
            {t("{u} of the area not observed that month; monthly optical composite: cloud hides part of a monsoon month, short floods may be missed.", {
              u: `${Math.round(f.unobserved_share * 100)} %`,
            })}
          </div>
        </div>
      )}
      {s.glofas && (
        <div className="mt-2 border-t border-line pt-2 leading-snug text-ink-2">
          <div className="font-medium text-ink">{t("River flood, {n}-year (GloFAS)", { n: s.glofas.return_period })}</div>
          <div>
            {t("{p} people in it, {q} under more than 1 m, {r} on sinking ground.", {
              p: fmt.int(s.glofas.people),
              q: fmt.int(s.glofas.people_over_1m),
              r: fmt.int(s.glofas.people_on_sinking_ground),
            })}
          </div>
          <div className="text-[11.5px] text-warn-ink">{t("Global model without dykes: in a diked delta, an upper bound.")}</div>
        </div>
      )}
      {sub.warning && <p className="mt-1.5 mb-0 text-[11.5px] text-warn-ink">{ts(sub.warning)}</p>}
      <p className="mt-2 mb-0 text-[10.5px] leading-snug text-faint">{s.credits.join(" · ")}</p>
      {form}
    </div>
  );
}

export const KIND_OF_VIEW: Partial<Record<View, AnalysisKind>> = {
  behaviour: "behaviour", change: "behaviour", risk: "risk", lines: "lines", consolidation: "consolidation",
  up: "decompose", east: "decompose", soft_soil: "geology", exposure: "exposure",
};
// per analysis: what the run does, and its button
export const RUN_TEXT: Record<AnalysisKind, [string, string]> = {
  behaviour: ["Not classified yet. The run fits the kinds of motion to the series of the cells of this zoning (a few seconds).", "Classify the kinds of motion"],
  risk: ["Not assessed yet. The run reads every Overture building of the area (cached) and crosses its hazard with its consequence.", "Assess the risk to buildings"],
  lines: ["Not profiled yet. The run reads the dykes, railways and main roads of OpenStreetMap over the product (a minute the first time) and the InSAR points along them.", "Profile the infrastructure lines"],
  consolidation: ["Not analysed yet. The run fits a consolidation curve to the sinking cells of this zoning (a few seconds).", "Analyse the consolidation"],
  decompose: ["Not decomposed yet. The run looks in the workspace for a product that sees this area from the other side over the same period (an ascending track for a descending one), then separates the vertical and east-west motion.", "Separate vertical and east-west"],
  exposure: ["Not counted yet. The run reads the population (GHS-POP) and the buildings (GlobalBuildingAtlas) of the area from Source Cooperative, and with a flood month the surface water and the rainfall of that month.", "Count the people and buildings exposed"],
  geology: ["Not read yet. The run takes the soft-soil thickness of the project (map or boreholes, else the open global grid) and compares it with the sinking of the cells.", "Read the soft-soil thickness"],
};

/** A colour bar with its true range (never clipped). */
export function RangeBar({ stops, lo, hi, mid, unit }: { stops: RGB[]; lo: string; hi: string; mid?: string; unit: string }) {
  return (
    <>
      <div className="h-2.5 rounded-sm" style={{ background: `linear-gradient(90deg,${stops.map((x) => rgb(x)).join(",")})` }} />
      <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-faint">
        <span>{lo}</span>
        <span>{mid ?? unit}</span>
        <span>{hi}</span>
      </div>
    </>
  );
}

export function DecomposeLegend({ s, view, again }: { s: DecomposeSummary; view: "up" | "east"; again: React.ReactNode }) {
  const st = view === "up" ? s.up_mm_yr : s.east_mm_yr;
  return (
    <div className="mt-2">
      {view === "up" ? (
        <RangeBar stops={[...RATE_RGB].reverse()} lo={`${fmt.num(st.min, 0)}`} hi={`${fmt.num(st.max, 0)}`} mid={t("mm/yr, up")} unit="" />
      ) : (
        <RangeBar stops={EAST_RGB} lo={`${t("west")} ${fmt.num(st.min, 0)}`} hi={`${fmt.num(st.max, 0)} ${t("east")}`} mid="mm/yr" unit="" />
      )}
      <p className="mt-1.5 mb-0 text-[11.5px] leading-snug text-muted">
        {t("{n} cells of {m} m, ±{a} mm/yr vertical, ±{b} mm/yr east-west (median 1 σ).", { n: fmt.int(s.n_cells), m: s.params.cell_m, a: s.sigma_up_median, b: s.sigma_east_median })}
      </p>
      {view === "east" && (
        <p className="mt-1 mb-0 text-[11.5px] leading-snug text-muted">
          {t("Significant east-west motion (≥ {v} mm/yr and 2 σ) in {p} % of the cells.", { v: s.params.horizontal_mm_yr, p: fmt.num(100 * s.horizontal_share, 1) })}
        </p>
      )}
      <div className="mt-2 space-y-1 text-[11.5px]">
        {s.products.map((p) => (
          <div key={p.id} className="leading-snug">
            <span className="text-ink-2">{p.project} · {p.track}</span>{" "}
            <span className="font-mono text-faint">l_e {p.los[0] > 0 ? "+" : ""}{p.los[0].toFixed(2)}</span>
            <div className="text-faint">
              {p.first} → {p.last}
              {s.vertical_only_bias[p.id] && ` · ${t("vertical projection off by {v} mm/yr (90 %)", { v: s.vertical_only_bias[p.id].p90_abs_mm_yr })}`}
            </div>
          </div>
        ))}
      </div>
      {s.ramps?.some((r) => r.removed) && (
        <p className="mt-1.5 mb-0 text-[11.5px] leading-snug text-muted">
          {t("A plane was removed from each product first (tilt over the area: {v} mm/yr).", { v: s.ramps.map((r) => r.span_mm_yr).join(" / ") })}
        </p>
      )}
      {s.warnings.map((w) => (
        <p key={w} className="mt-1 mb-0 text-[11.5px] leading-snug text-warn-ink">{ts(w)}</p>
      ))}
      {again}
    </div>
  );
}

export function GeologyLegend({ s, again }: { s: GeologySummary; again: React.ReactNode }) {
  const cv = s.consolidation_cv;
  return (
    <div className="mt-2">
      {s.thickness_m && <RangeBar stops={SOIL_RGB} lo={fmt.num(s.thickness_m.min, 0)} hi={fmt.num(s.thickness_m.max, 0)} unit="m" />}
      <p className="mt-1.5 mb-0 text-[11.5px] leading-snug text-muted">
        {t("Source")}: {t(s.source_label)}
        {s.boreholes ? ` · ${t("{n} boreholes", { n: s.boreholes })}` : ""}
      </p>
      {s.by_class.length > 1 && (
        <div className="mt-2 grid grid-cols-[1fr_auto_auto] gap-x-3 text-[11.5px]">
          <span className="text-faint">{t("thickness, m")}</span>
          <span className="text-right text-faint">{t("median rate")}</span>
          <span className="text-right text-faint">{t("moving")}</span>
          {s.by_class.map((b) => (
            <div key={b.from_m} className="contents">
              <span className="font-mono text-ink-2">{b.from_m} – {b.to_m}</span>
              <span className="text-right font-mono text-ink-2">{b.median_rate_mm_yr != null ? fmt.num(b.median_rate_mm_yr, 1) : "–"}</span>
              <span className="text-right font-mono text-ink-2">{b.moving_share != null ? `${Math.round(100 * b.moving_share)} %` : "–"}</span>
            </div>
          ))}
        </div>
      )}
      {s.spearman_rho != null && (
        <p className="mt-1.5 mb-0 text-[11.5px] leading-snug text-muted">
          {t("Thickness against sinking: Spearman ρ = {r} over {n} sinking cells.", { r: s.spearman_rho, n: fmt.int(s.sinking_cells) })}
        </p>
      )}
      {cv.median_m2_yr != null && (
        <p className="mt-1 mb-0 text-[11.5px] leading-snug text-muted">
          {t("Consolidating cells: implied c_v {v} m²/yr (soft clays: 0.1–10).", { v: fmt.num(cv.median_m2_yr, 1) })}
        </p>
      )}
      {s.warnings.map((w) => (
        <p key={w} className="mt-1 mb-0 text-[11.5px] leading-snug text-warn-ink">{ts(w)}</p>
      ))}
      {again}
    </div>
  );
}

export const LINE_KINDS: Record<string, string> = { dyke: "Dykes", railway: "Railways", embankment: "Embankments", road: "Main roads" };

/** The vertical rate along a line, the stations beyond the damage limits marked. */
export function ProfileChart({ p }: { p: LineProfile }) {
  const W = 340;
  const H = 150;
  const v = p.v_vert_mm_yr.map((x) => (x == null ? NaN : x));
  const ok = v.filter(Number.isFinite);
  if (!ok.length) return <p className="text-[12px] text-muted">{t("too few InSAR points")}</p>;
  const lo = Math.min(0, ...ok);
  const hi = Math.max(0, ...ok);
  const L = p.length_m || 1;
  const X = (c: number) => 34 + (c / L) * (W - 42);
  const Y = (y: number) => 8 + (1 - (y - lo) / (hi - lo || 1)) * (H - 26);
  const d = v.map((y, i) => (Number.isFinite(y) ? `${i && Number.isFinite(v[i - 1]) ? "L" : "M"}${X(p.chainage_m[i]).toFixed(1)},${Y(y).toFixed(1)}` : "")).join("");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <line x1={34} x2={W - 8} y1={Y(0)} y2={Y(0)} stroke="var(--c-line-2)" strokeDasharray="3 3" />
      {p.beta.map((b, i) => (b != null && b >= 1 / 500 ? <rect key={i} x={X(p.chainage_m[i]) - 2} y={8} width={4} height={H - 26} fill={rgb(LINE_RGB[b >= 1 / 150 ? 3 : b >= 1 / 300 ? 2 : 1], 0.45)} /> : null))}
      <path d={d} fill="none" stroke="var(--c-accent)" strokeWidth="1.6" />
      <text x={30} y={Y(hi) + 4} fill="var(--c-muted)" fontSize="10" textAnchor="end">{hi.toFixed(0)}</text>
      <text x={30} y={Y(lo) + 4} fill="var(--c-muted)" fontSize="10" textAnchor="end">{lo.toFixed(0)}</text>
      <text x={34} y={H - 4} fill="var(--c-muted)" fontSize="10">0</text>
      <text x={W - 8} y={H - 4} fill="var(--c-muted)" fontSize="10" textAnchor="end">{(L / 1000).toFixed(1)} km</text>
      <text x={(W + 26) / 2} y={H - 4} fill="var(--c-muted)" fontSize="10" textAnchor="middle">{t("vertical rate, mm/yr")}</text>
    </svg>
  );
}

export function LinePanel({ p, onClose }: { p: LineProfile; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-semibold">{p.name}</span>
        <span className="text-[11.5px] text-muted">· {t(LINE_KINDS[p.kind] ?? p.kind)}</span>
        <button type="button" className="ml-auto text-faint hover:text-ink" onClick={onClose} aria-label={t("Close")}>
          ×
        </button>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
        <Row k={t("Length")} v={`${fmt.num(p.length_m / 1000, 1)} km`} />
        <Row k={t("Covered by InSAR")} v={`${Math.round(100 * p.covered_share)} %`} />
        <Row k={t("Largest distortion in 10 years")} v={p.beta_max ? `1/${Math.round(1 / p.beta_max)}` : "–"} />
        <Row k={t("Lowered in 10 years, at most")} v={p.loss_mm != null ? `${fmt.num(p.loss_mm, 0)} mm` : "–"} />
      </div>
      <div className="mt-2">
        <ProfileChart p={p} />
      </div>
    </div>
  );
}

/** Settlement of a consolidating cell and its curve projected ahead (positive down). */
export function ConsolidationChart({ c }: { c: ConsolidationCell }) {
  const W = 340;
  const H = 150;
  const d0 = Date.parse(c.dates[0]);
  const obs = c.dates.map((d, i) => [(Date.parse(d) - d0) / (365.2425 * 86400000), c.settlement_mm[i]] as [number, number | null]);
  // the projection up to about five time constants past the last date (where the curve is flat), at most 5 years
  const tEnd = obs[obs.length - 1][0] + Math.max(1, 5 * (c.tau_yr ?? 1));
  const cur = (c.curve_t_yr ?? []).map((x, i) => [x, c.curve_mm![i]] as [number, number]).filter(([x]) => x <= tEnd);
  const ys = [...obs.map((o) => o[1]).filter((y): y is number => y != null), ...cur.map((x) => x[1]), 0];
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const tmax = Math.max(obs[obs.length - 1][0], cur.length ? cur[cur.length - 1][0] : 0);
  const X = (x: number) => 34 + (x / (tmax || 1)) * (W - 42);
  const Y = (y: number) => 8 + ((y - lo) / (hi - lo || 1)) * (H - 26); // settlement drawn downwards
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <line x1={X(obs[obs.length - 1][0])} x2={X(obs[obs.length - 1][0])} y1={8} y2={H - 18} stroke="var(--c-line-2)" strokeDasharray="3 3" />
      {cur.length > 0 && <path d={cur.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("")} fill="none" stroke="#f46d43" strokeWidth="2" />}
      {obs.map(([x, y], i) => (y == null ? null : <circle key={i} cx={X(x)} cy={Y(y)} r={2.6} fill="var(--c-accent)" />))}
      <text x={30} y={Y(lo) + 4} fill="var(--c-muted)" fontSize="10" textAnchor="end">{lo.toFixed(0)}</text>
      <text x={30} y={Y(hi) + 4} fill="var(--c-muted)" fontSize="10" textAnchor="end">{hi.toFixed(0)}</text>
      <text x={34} y={H - 4} fill="var(--c-muted)" fontSize="10">{c.dates[0].slice(0, 7)}</text>
      <text x={W - 8} y={H - 4} fill="var(--c-muted)" fontSize="10" textAnchor="end">+{tmax.toFixed(1)} {t("yr")}</text>
      <text x={(W + 26) / 2} y={H - 4} fill="var(--c-muted)" fontSize="10" textAnchor="middle">{t("settlement, mm (down)")}</text>
    </svg>
  );
}

export function RiskPanel({ b, onClose }: { b: RiskBuilding; onClose: () => void }) {
  const lv = b.risk;
  const cls = (k: number) => ["", t("low"), t("medium"), t("high")][k] ?? "–";
  return (
    <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(lv >= 0 ? LEVEL_RGB[lv] : NA_RGB) }} />
        <span className="text-[13px] font-semibold">{lv >= 0 ? t("{level} risk", { level: t(LEVELS[lv]) }) : t("Not assessed")}</span>
        <span className="text-[11.5px] text-muted">· {t("building")}</span>
        <button type="button" className="ml-auto text-faint hover:text-ink" onClick={onClose} aria-label={t("Close")}>
          ×
        </button>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
        <Row k={t("Hazard")} v={b.hazard >= 0 ? t(LEVELS[b.hazard]) : "–"} />
        <Row k={t("Hazard from")} v={b.source === "building" ? t("its own InSAR points ({n})", { n: b.points }) : b.source === "cell" ? t("its analysis cell") : "–"} />
        {b.v_vert_mm_yr != null && <Row k={t("Vertical rate")} v={`${fmt.vel(b.v_vert_mm_yr)} mm/yr`} />}
        {b.beta_10yr != null && <Row k={t("Angular distortion in 10 years (β)")} v={`1/${Math.round(1 / b.beta_10yr)}`} title={t("relative rotation within the building, after its rigid tilt is removed")} />}
        {b.tilt_10yr != null && <Row k={t("Tilt in 10 years")} v={`1/${Math.round(1 / b.tilt_10yr)}`} title={t("rigid tilt of the building (plane through its points)")} />}
        <Row k={t("Footprint")} v={`${fmt.int(Math.round(b.area_m2))} m²`} />
        <Row k={t("Floors")} v={b.height_known ? `${b.floors} (${fmt.num(b.height_m)} m)` : `${b.floors} (${t("assumed")})`} />
        <Row k={t("Exposure")} v={`E${b.exposure} · ${cls(b.exposure)}`} title={t("gross floor area: footprint × floors")} />
        <Row k={t("Vulnerability")} v={`V${b.vulnerability} · ${cls(b.vulnerability)}`} title={t("proxy from height and length: no structural type in open data")} />
        <Row k={t("Consequence")} v={`C${b.consequence}`} />
      </div>
      <div className="mt-2 font-mono text-[10.5px] break-all text-faint">{b.id}</div>
    </div>
  );
}

export function Row({ k, v, title }: { k: string; v: string; title?: string }) {
  return (
    <div className="contents" title={title}>
      <span className="text-muted">{k}</span>
      <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
    </div>
  );
}

export function CellPanel({ c, beh, cons, onClose }: { c: HazardCell; beh?: BehaviourCell; cons?: ConsolidationCell; onClose: () => void }) {
  const frac = (x: number | null) => (x == null || x <= 0 ? "–" : `1/${Math.round(1 / x)}`);
  const lv = c.hazard;
  return (
    <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-[3px]" style={{ background: rgb(lv >= 0 ? LEVEL_RGB[lv] : NA_RGB) }} />
        <span className="text-[13px] font-semibold">{lv >= 0 ? t("{level} hazard", { level: t(LEVELS[lv]) }) : t("Not assessed")}</span>
        <span className="text-[11.5px] text-muted">· {t("{mode} cell #{n}", { mode: t(c.mode), n: c.cell })}</span>
        <button type="button" className="ml-auto text-faint hover:text-ink" onClick={onClose} aria-label={t("Close")}>
          ×
        </button>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
        <Row k={t("Points in cell")} v={fmt.int(c.n_points)} />
        <Row
          k={c.mode === "subsidence" ? t("Rate (up +)") : t("Rate (upslope +)")}
          v={`${fmt.vel(c.rate_mm_yr)} ± ${fmt.num(c.rate_se_mm_yr)} mm/yr`}
        />
        <Row k={t("Stability threshold")} v={`${fmt.num(c.stable_mm_yr)} mm/yr`} />
        <Row k={t("Intensity")} v={t("I{a} observed → I{b}", { a: c.intensity_observed, b: c.intensity })} title={t("after the rainfall scenario and the acceleration")} />
        {c.mode === "subsidence" ? (
          <Row k={t("Angular distortion")} v={frac(c.angular_distortion)} title={t("largest change of slope across the cell, over the horizon")} />
        ) : (
          <Row k={t("Slope / sensitivity")} v={`${fmt.num(c.slope_deg)}° / ${fmt.num(c.sensitivity, 2)}`} />
        )}
        <Row k={t("Damage potential")} v={`S${Math.max(0, c.secondary)}`} />
        <Row k={t("Acceleration")} v={`${fmt.vel(c.acc_mm_yr2)} mm/yr²${c.accelerating ? ` (${t("significant")})` : ""}`} />
      </div>
      {c.opposite_motion && (
        <div className="mt-2 rounded-md bg-warn-bg px-2 py-1 text-[11.5px] leading-snug text-warn-ink">
          {t("Moves against the hazard direction ({dir}): check the reference area before reading it as stable.", {
            dir: c.mode === "subsidence" ? t("uplift") : t("apparent upslope motion"),
          })}
        </div>
      )}
      <div className="mt-2 rounded-lg border border-line bg-panel-2 px-2.5 py-2">
        <div className="text-[11px] font-semibold tracking-[1px] text-muted">{t("RAINFALL COUPLING")}</div>
        {c.rain_lag_months < 0 ? (
          <div className="mt-1 text-[12px] text-muted">{t("Not assessed (series too short or rainfall missing).")}</div>
        ) : (
          <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
            <Row k={t("Significant")} v={c.rain_coupled ? t("yes") : t("no")} />
            <Row k={t("r (partial) · lag")} v={`${fmt.num(c.rain_r, 2)} · ${t("{n} mo", { n: c.rain_lag_months })}`} />
            <Row k="p · q (FDR)" v={`${fmt.num(c.rain_p, 3)} · ${fmt.num(c.rain_q, 3)}`} />
            <Row k={t("k per 100 mm")} v={`${fmt.vel(c.rain_k_mm_per_100mm)} ± ${fmt.num(c.rain_k_se)} mm`} />
            <Row k={t("Trend w/o rain")} v={`${fmt.vel(c.trend_rain_corrected_mm_yr)} mm/yr`} />
            <Row k={t("Dry (P10) / wet (P90) yr")} v={`${fmt.vel(c.rate_dry_year_mm_yr)} / ${fmt.vel(c.rate_wet_year_mm_yr)}`} />
          </div>
        )}
      </div>
      {c.groundwater && (
        <div className="mt-2 rounded-lg border border-line bg-panel-2 px-2.5 py-2">
          <div className="text-[11px] font-semibold tracking-[1px] text-muted">{t("GROUNDWATER COUPLING")}</div>
          {(c.gw_lag_months ?? -1) < 0 ? (
            <div className="mt-1 text-[12px] text-muted">{t("Not assessed (storage not published for the whole period, or series too short).")}</div>
          ) : (
            <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
              <Row k={t("Significant")} v={c.gw_coupled ? t("yes") : t("no")} />
              <Row k={t("r (partial) · lag")} v={`${fmt.num(c.gw_r ?? null, 2)} · ${t("{n} mo", { n: c.gw_lag_months ?? 0 })}`} />
              <Row k="p · q (FDR)" v={`${fmt.num(c.gw_p ?? null, 3)} · ${fmt.num(c.gw_q ?? null, 3)}`} />
              <Row k={t("g per 100 mm storage")} v={`${fmt.vel(c.gw_k_mm_per_100mm ?? null)} ± ${fmt.num(c.gw_k_se ?? null)} mm`} />
              <Row k={t("Storage trend")} v={`${fmt.vel(c.groundwater.pixel?.trend_mm_yr ?? null)} mm/yr`} title={t("trend of the storage of the 0.25° pixel over the period")} />
            </div>
          )}
        </div>
      )}
      {beh && (
        <div className="mt-2 rounded-lg border border-line bg-panel-2 px-2.5 py-2">
          <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[1px] text-muted">
            {t("KIND OF MOTION")}
            <span className="ml-auto flex items-center gap-1.5 text-[12px] font-normal tracking-normal text-ink-2">
              <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: rgb(BEH_RGB[Math.max(0, BEH_CLASSES.indexOf(beh.class))]) }} />
              {t(BEH_LABELS[beh.class] ?? beh.class)}
            </span>
          </div>
          <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
            {beh.change_date && <Row k={t("Date of change")} v={beh.change_date} />}
            {beh.rate_before_mm_yr != null && <Row k={t("Rate before → after")} v={`${fmt.vel(beh.rate_before_mm_yr)} → ${fmt.vel(beh.rate_after_mm_yr)} mm/yr`} />}
            {beh.acc_mm_yr2 != null && <Row k={t("Acceleration")} v={`${fmt.vel(beh.acc_mm_yr2)} mm/yr²`} />}
            {beh.seasonal_amp_mm != null && <Row k={t("Seasonal amplitude")} v={`${fmt.num(beh.seasonal_amp_mm)} mm`} />}
            {beh.jump_mm != null && <Row k={t("Jump")} v={`${fmt.vel(beh.jump_mm)} mm`} />}
            {beh.delta_bic != null && beh.delta_bic > 0 && <Row k={t("Evidence (ΔBIC)")} v={fmt.num(beh.delta_bic)} title={t("how much better than a straight line the kept model fits (≥ 6: strong)")} />}
          </div>
        </div>
      )}
      {cons?.consolidating && (
        <div className="mt-2 rounded-lg border border-line bg-panel-2 px-2.5 py-2">
          <div className="text-[11px] font-semibold tracking-[1px] text-muted">{t("CONSOLIDATION")}</div>
          <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
            <Row k={t("Settled so far")} v={`${fmt.num(cons.settled_mm, 0)} mm`} />
            <Row k={t("Still to come")} v={`${fmt.num(cons.remaining_mm, 0)} mm`} />
            <Row k={t("Final settlement")} v={`${fmt.num(cons.final_mm, 0)} mm`} />
            <Row k={t("90 % reached in")} v={`${fmt.num(cons.t90_from_now_yr, 1)} ${t("yr")}`} />
          </div>
          <ConsolidationChart c={cons} />
        </div>
      )}
      <div className="mt-2">
        <CellChart c={c} model={beh?.fit_mm} />
      </div>
    </div>
  );
}

export function MethodLink() {
  return (
    <a
      href={href({ page: "learn", chapter: "hazard", step: 0 })}
      className="flex items-center gap-2 rounded-xl border border-line-2 bg-panel/95 px-3 py-2.5 no-underline shadow-xl shadow-black/30 backdrop-blur hover:bg-raised"
    >
      <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("HOW THIS MAP IS MADE")}</span>
      <span className="ml-auto text-[12px] text-accent">{t("Principles, chapter 2")} →</span>
    </a>
  );
}

export const PARAMS: { key: string; label: string; options: (number | string)[]; unit?: string }[] = [
  { key: "cell_m", label: "Cell", options: [50, 100, 200, 500], unit: "m" },
  { key: "horizon_yr", label: "Horizon", options: [5, 10, 20, 50], unit: "yr" },
  { key: "max_lag_months", label: "Max lag", options: [3, 6, 9, 12], unit: "mo" },
  { key: "alpha", label: "FDR", options: [0.01, 0.05, 0.1] },
  { key: "rain_source", label: "Rain", options: ["auto", "chirps", "era5"] },
  { key: "groundwater", label: "Groundwater", options: ["auto", "gldas", "off"] },
];
