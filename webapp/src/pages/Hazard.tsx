// Hazard: ground-motion hazard zoning of a product with rainfall (geoeyes hazard). Cells of the analysis grid
// coloured by hazard level or by one of its ingredients (InSAR intensity, angular distortion / slope, rainfall
// coupling); click a cell for its series in the motion direction, the rainfall of its pixel and the fitted models.
// Method and sources: docs/en/research/rainfall-insar-hazard.md.
import { LineLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import { api, type BehaviourCell, type AnalysisKind, type BehaviourStatus, type BehaviourSummary, type ConsolidationCell, type ConsolidationSummary, type DecomposeSummary, type GeologySummary, type HazardCell, type HazardCellsMeta, type HazardSummary, type LineProfile, type LinesSummary, type RiskBuilding, type RiskSummary, type Workspace } from "../api";
import { BasemapPicker } from "../components/BasemapPicker";
import { RainBars } from "../components/RainBars";
import { t, ts } from "../i18n";
import { mapStyle, type Base } from "../map";
import { useWarnings } from "../notify";
import { href, useApp } from "../state";
import { Button, ColumnToggle, fmt, Fold, usePersisted } from "../ui";

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
const CLASS_RGB: RGB[] = [[75, 90, 115], [254, 224, 139], [252, 141, 89], [215, 48, 39]];
const SEC_RGB: RGB[] = [[75, 90, 115], [194, 165, 207], [153, 112, 171], [118, 42, 131]];
const RATE_BREAKS = [-30, -10, -2, 2, 10, 30];
const RATE_RGB: RGB[] = [[33, 102, 172], [67, 147, 195], [146, 197, 222], [127, 139, 160], [244, 165, 130], [214, 96, 77], [178, 24, 43]];
const LAG_RGB: RGB[] = [[68, 1, 84], [65, 68, 135], [42, 120, 142], [34, 168, 132], [122, 209, 81], [189, 223, 38], [253, 231, 37]];
export const DEFAULT_MATRIX = [
  [0, 0, 1, 1],
  [1, 1, 2, 3],
  [2, 2, 3, 4],
  [3, 3, 4, 4],
];

export type View = "hazard" | "intensity" | "secondary" | "rate" | "coupling" | "lag" | "groundwater" | "mode" | "behaviour" | "change" | "risk" | "lines" | "consolidation" | "up" | "east" | "soft_soil";
interface ViewInfo {
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
const VIEW_GROUPS: [string, View[]][] = [
  ["Zoning", ["hazard"]],
  ["Components", ["intensity", "secondary", "rate", "mode"]],
  ["Water drivers", ["coupling", "lag", "groundwater"]],
  ["Kinds of motion and risk", ["behaviour", "change", "risk"]],
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
const ramp = (stops: RGB[], x: number): RGB => {
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

const signed = (v: number) => (v < 0 ? `−${-v}` : `${v}`);

export function rgb(c: RGB, a = 1) {
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`;
}

function bin(v: number, breaks: number[]) {
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
                className="flex h-6 items-center justify-center rounded-[4px] font-mono text-[11.5px] font-semibold text-[#0b1220]"
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

function About({ view }: { view: View }) {
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

function Swatches({ items }: { items: { color: RGB; label: string; alpha?: number }[] }) {
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

export function Legend({ view, s }: { view: View; s: HazardSummary }) {
  if (view === "behaviour" || view === "change" || view === "risk" || view === "lines" || view === "consolidation" || view === "up" || view === "east" || view === "soft_soil") return null; // BehaviourLegend
  const p = s.params as Record<string, number[] | number>;
  const sb = p.subsidence_breaks as number[];
  const lb = p.landslide_breaks as number[];
  const db = p.distortion_breaks as number[];
  const slb = p.slope_breaks as number[];
  const frac = (x: number) => `1/${Math.round(1 / x)}`;
  if (view === "hazard")
    return (
      <>
        <div className="mt-1 flex items-start justify-between gap-3">
          <Swatches items={[...LEVELS.map((l, i) => ({ color: LEVEL_RGB[i], label: t(l) })).reverse(), { color: NA_RGB, label: t("not assessed") }]} />
          <MatrixFigure matrix={(s.params.matrix as number[][]) ?? DEFAULT_MATRIX} />
        </div>
      </>
    );
  if (view === "intensity")
    return (
      <>
        <Swatches
          items={[
            { color: CLASS_RGB[3], label: `I3 · ${t("subsidence")} ≥ ${sb[1]} · ${t("landslide")} ≥ ${lb[1]} mm/yr` },
            { color: CLASS_RGB[2], label: `I2 · ${sb[0]}–${sb[1]} · ${lb[0]}–${lb[1]} mm/yr` },
            { color: CLASS_RGB[1], label: `I1 · ${t("above stability")} · < ${sb[0]} · < ${lb[0]} mm/yr` },
            { color: CLASS_RGB[0], label: `I0 · ${t("stable")}: < max(${p.stable_floor_mm_yr} mm/yr, ${p.stable_sigma}σ)` },
          ]}
        />
              </>
    );
  if (view === "secondary")
    return (
      <>
        <div className="mt-1 text-[11.5px] text-muted">{t("Subsidence: angular distortion in {n} years", { n: String(p.horizon_yr) })}</div>
        <Swatches
          items={[
            { color: SEC_RGB[3], label: `S3 ≥ ${frac(db[2])} · ${t("structural damage")}` },
            { color: SEC_RGB[2], label: `S2 ${frac(db[1])}–${frac(db[2])} · ${t("cracking")}` },
            { color: SEC_RGB[1], label: `S1 ${frac(db[0])}–${frac(db[1])} · ${t("beyond the safe limit")}` },
            { color: SEC_RGB[0], label: `S0 < ${frac(db[0])}` },
          ]}
        />
        <div className="mt-2 text-[11.5px] text-muted">{t("Landslide: susceptibility map, else slope classes {s}°", { s: slb.join(" / ") })}</div>
      </>
    );
  if (view === "rate")
    return (
      <Swatches
        items={RATE_RGB.map((c, i) => ({
          color: c,
          // colour i holds the rates r with −r in [B(i−1), B(i)): sinking (r < 0) is red
          label:
            (i === 0 ? `> ${-RATE_BREAKS[0]}` : i === RATE_RGB.length - 1 ? `≤ ${signed(-RATE_BREAKS[i - 1])}` : `${signed(-RATE_BREAKS[i])} … ${signed(-RATE_BREAKS[i - 1])}`) +
            " mm/yr" +
            (i === RATE_RGB.length - 1 ? ` · ${t("sinking / downslope, fast")}` : i === 3 ? ` · ${t("about stable")}` : i === 0 ? ` · ${t("rising / upslope")}` : ""),
        })).reverse()}
      />
    );
  if (view === "coupling")
    return (
      <>
        <Swatches
          items={[
            { color: RATE_RGB[6], label: `r < −0.8 · ${t("more rain, more motion")}` },
            { color: RATE_RGB[4], label: "−0.6 ≤ r < 0" },
            { color: RATE_RGB[2], label: "0 < r ≤ 0.6" },
            { color: RATE_RGB[0], label: `r > 0.8 · ${t("more rain, less sinking / uplift")}` },
            { color: NA_RGB, label: t("not significant / not assessed"), alpha: 0.35 },
          ]}
        />
        <p className="mt-2 text-[11px] leading-snug text-faint">d = a + b·t + k·CRD(t − τ) · FDR {String(p.alpha)}</p>
      </>
    );
  if (view === "groundwater") {
    const gw = s.groundwater;
    if (!gw?.used)
      return (
        <p className="mt-1 text-[12px] leading-snug text-muted">
          {gw?.reason === "no EARTHDATA_TOKEN"
            ? t("Groundwater needs an Earthdata login: set EARTHDATA_TOKEN and run the zoning again.")
            : gw?.reason === "off"
              ? t("Groundwater coupling is off in the parameters.")
              : t("No groundwater in this zoning: run it again.")}
        </p>
      );
    return (
      <>
        <Swatches
          items={[
            { color: RATE_RGB[6], label: `r < −0.8 · ${t("more storage, more motion")}` },
            { color: RATE_RGB[4], label: "−0.6 ≤ r < 0" },
            { color: RATE_RGB[2], label: "0 < r ≤ 0.6" },
            { color: RATE_RGB[0], label: `r > 0.8 · ${t("less storage, more sinking (aquifer)")}` },
            { color: NA_RGB, label: t("not significant / not assessed"), alpha: 0.35 },
          ]}
        />
        <p className="mt-2 text-[11px] leading-snug text-faint">
          d = a + b·t + g·GWS(t − τ) · {t("{n} of {m} cells significant", { n: gw.cells_significant ?? 0, m: gw.cells_tested ?? 0 })}
          {gw.trend_mm_yr != null && <> · {t("storage trend {v} mm/yr", { v: fmt.vel(gw.trend_mm_yr) })}</>}
        </p>
      </>
    );
  }
  if (view === "lag")
    return <Swatches items={[...LAG_RGB.map((c, i) => ({ color: c, label: t(i === 1 ? "{n} month" : "{n} months", { n: i }) })), { color: NA_RGB, label: t("not significant"), alpha: 0.35 }]} />;
  return (
    <Swatches
      items={[
        { color: [91, 155, 213], label: t("subsidence (vertical motion)") },
        { color: [192, 138, 62], label: t("landslide (slope ≥ {s}°, motion down the slope)", { s: String(p.landslide_min_slope_deg) }) },
      ]}
    />
  );
}

/** The series of a cell with its models; ``compact``: the series, the line and ``model`` only (no rainfall). */
export function CellChart({ c, model, compact = false }: { c: HazardCell; model?: (number | null)[]; compact?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const x = c.dates.map((d) => Date.parse(d) / 1000);
    const axis = { stroke: "#93a4bf", grid: { stroke: "#1a2740", width: 1 }, ticks: { stroke: "#22324d", width: 1 }, font: "11px Inter, system-ui, sans-serif" };
    const series: uPlot.Series[] = [
      {},
      { stroke: "#4cc2ff", width: 1.5, points: { show: true, size: 5, fill: "#4cc2ff", stroke: "#0b1220" }, spanGaps: true },
      { stroke: "#93a4bf", width: 1.2, dash: [4, 4], points: { show: false } },
    ];
    const data: (number | null)[][] = [x, c.series_mm, c.linear_mm ?? c.series_mm.map(() => null)];
    if (c.rain_model_mm && !compact) {
      series.push({ stroke: "#f5b84b", width: 1.8, points: { show: false } });
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
          { ...axis, size: 48, label: c.mode === "subsidence" ? t("mm (up +)") : t("mm (upslope +)"), labelSize: 14, labelFont: "11px Inter, sans-serif" },
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
          <span className="h-0.5 w-4 bg-[#4cc2ff]" /> {t("cell median")}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-4 border-t-2 border-dashed border-[#93a4bf]" /> {t("linear")}
        </span>
        {c.rain_model_mm && !compact && (
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4 bg-[#f5b84b]" /> {t("trend + k·CRD(t − {n} mo)", { n: c.rain_lag_months })}
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

function Swatch({ color, label }: { color: RGB; label: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span className="h-3 w-3 flex-none rounded-[3px]" style={{ background: rgb(color) }} />
      <span className="text-ink-2">{label}</span>
    </div>
  );
}

function BehaviourLegend({
  view,
  st,
  first,
  last,
  onRun,
}: {
  view: View;
  st: BehaviourStatus | undefined;
  first?: string;
  last?: string;
  onRun: (kind: AnalysisKind) => void;
}) {
  const kind = KIND_OF_VIEW[view] ?? "behaviour";
  const a = st?.[kind];
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
          <p key={w} className="mt-1.5 mb-0 text-[11.5px] leading-snug text-[#f5d08b]">{ts(w)}</p>
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
          <p key={w} className="mt-1.5 mb-0 text-[11.5px] leading-snug text-[#f5d08b]">{ts(w)}</p>
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
        <p key={w} className="mt-1 mb-0 text-[11.5px] leading-snug text-[#f5d08b]">{ts(w)}</p>
      ))}
      {again}
    </div>
  );
}

const KIND_OF_VIEW: Partial<Record<View, AnalysisKind>> = {
  behaviour: "behaviour", change: "behaviour", risk: "risk", lines: "lines", consolidation: "consolidation",
  up: "decompose", east: "decompose", soft_soil: "geology",
};
// per analysis: what the run does, and its button
const RUN_TEXT: Record<AnalysisKind, [string, string]> = {
  behaviour: ["Not classified yet. The run fits the kinds of motion to the series of the cells of this zoning (a few seconds).", "Classify the kinds of motion"],
  risk: ["Not assessed yet. The run reads every Overture building of the area (cached) and crosses its hazard with its consequence.", "Assess the risk to buildings"],
  lines: ["Not profiled yet. The run reads the dykes, railways and main roads of OpenStreetMap over the product (a minute the first time) and the InSAR points along them.", "Profile the infrastructure lines"],
  consolidation: ["Not analysed yet. The run fits a consolidation curve to the sinking cells of this zoning (a few seconds).", "Analyse the consolidation"],
  decompose: ["Not decomposed yet. The run looks in the workspace for a product that sees this area from the other side over the same period (an ascending track for a descending one), then separates the vertical and east-west motion.", "Separate vertical and east-west"],
  geology: ["Not read yet. The run takes the soft-soil thickness of the project (map or boreholes, else the open global grid) and compares it with the sinking of the cells.", "Read the soft-soil thickness"],
};

/** A colour bar with its true range (never clipped). */
function RangeBar({ stops, lo, hi, mid, unit }: { stops: RGB[]; lo: string; hi: string; mid?: string; unit: string }) {
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

function DecomposeLegend({ s, view, again }: { s: DecomposeSummary; view: "up" | "east"; again: React.ReactNode }) {
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
        <p key={w} className="mt-1 mb-0 text-[11.5px] leading-snug text-[#f5d08b]">{ts(w)}</p>
      ))}
      {again}
    </div>
  );
}

function GeologyLegend({ s, again }: { s: GeologySummary; again: React.ReactNode }) {
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
        <p key={w} className="mt-1 mb-0 text-[11.5px] leading-snug text-[#f5d08b]">{ts(w)}</p>
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
      <line x1={34} x2={W - 8} y1={Y(0)} y2={Y(0)} stroke="#22324d" strokeDasharray="3 3" />
      {p.beta.map((b, i) => (b != null && b >= 1 / 500 ? <rect key={i} x={X(p.chainage_m[i]) - 2} y={8} width={4} height={H - 26} fill={rgb(LINE_RGB[b >= 1 / 150 ? 3 : b >= 1 / 300 ? 2 : 1], 0.45)} /> : null))}
      <path d={d} fill="none" stroke="#4cc2ff" strokeWidth="1.6" />
      <text x={30} y={Y(hi) + 4} fill="#93a4bf" fontSize="10" textAnchor="end">{hi.toFixed(0)}</text>
      <text x={30} y={Y(lo) + 4} fill="#93a4bf" fontSize="10" textAnchor="end">{lo.toFixed(0)}</text>
      <text x={34} y={H - 4} fill="#93a4bf" fontSize="10">0</text>
      <text x={W - 8} y={H - 4} fill="#93a4bf" fontSize="10" textAnchor="end">{(L / 1000).toFixed(1)} km</text>
      <text x={(W + 26) / 2} y={H - 4} fill="#93a4bf" fontSize="10" textAnchor="middle">{t("vertical rate, mm/yr")}</text>
    </svg>
  );
}

function LinePanel({ p, onClose }: { p: LineProfile; onClose: () => void }) {
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
      <line x1={X(obs[obs.length - 1][0])} x2={X(obs[obs.length - 1][0])} y1={8} y2={H - 18} stroke="#22324d" strokeDasharray="3 3" />
      {cur.length > 0 && <path d={cur.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("")} fill="none" stroke="#f46d43" strokeWidth="2" />}
      {obs.map(([x, y], i) => (y == null ? null : <circle key={i} cx={X(x)} cy={Y(y)} r={2.6} fill="#4cc2ff" />))}
      <text x={30} y={Y(lo) + 4} fill="#93a4bf" fontSize="10" textAnchor="end">{lo.toFixed(0)}</text>
      <text x={30} y={Y(hi) + 4} fill="#93a4bf" fontSize="10" textAnchor="end">{hi.toFixed(0)}</text>
      <text x={34} y={H - 4} fill="#93a4bf" fontSize="10">{c.dates[0].slice(0, 7)}</text>
      <text x={W - 8} y={H - 4} fill="#93a4bf" fontSize="10" textAnchor="end">+{tmax.toFixed(1)} {t("yr")}</text>
      <text x={(W + 26) / 2} y={H - 4} fill="#93a4bf" fontSize="10" textAnchor="middle">{t("settlement, mm (down)")}</text>
    </svg>
  );
}

function RiskPanel({ b, onClose }: { b: RiskBuilding; onClose: () => void }) {
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
        {b.beta_10yr != null && <Row k={t("Tilt in 10 years (β)")} v={`1/${Math.round(1 / b.beta_10yr)}`} />}
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

function Row({ k, v, title }: { k: string; v: string; title?: string }) {
  return (
    <div className="contents" title={title}>
      <span className="text-muted">{k}</span>
      <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
    </div>
  );
}

function CellPanel({ c, beh, cons, onClose }: { c: HazardCell; beh?: BehaviourCell; cons?: ConsolidationCell; onClose: () => void }) {
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
          <Row k={t("Angular distortion")} v={frac(c.angular_distortion)} title={t("largest differential settlement to a neighbouring cell, over the horizon")} />
        ) : (
          <Row k={t("Slope / sensitivity")} v={`${fmt.num(c.slope_deg)}° / ${fmt.num(c.sensitivity, 2)}`} />
        )}
        <Row k={t("Damage potential")} v={`S${Math.max(0, c.secondary)}`} />
        <Row k={t("Acceleration")} v={`${fmt.vel(c.acc_mm_yr2)} mm/yr²${c.accelerating ? ` (${t("significant")})` : ""}`} />
      </div>
      {c.opposite_motion && (
        <div className="mt-2 rounded-md bg-[#2a2110] px-2 py-1 text-[11.5px] leading-snug text-[#f5d08b]">
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

function MethodLink() {
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

const PARAMS: { key: string; label: string; options: (number | string)[]; unit?: string }[] = [
  { key: "cell_m", label: "Cell", options: [50, 100, 200, 500], unit: "m" },
  { key: "horizon_yr", label: "Horizon", options: [5, 10, 20, 50], unit: "yr" },
  { key: "max_lag_months", label: "Max lag", options: [3, 6, 9, 12], unit: "mo" },
  { key: "alpha", label: "FDR", options: [0.01, 0.05, 0.1] },
  { key: "rain_source", label: "Rain", options: ["auto", "chirps", "era5"] },
  { key: "groundwater", label: "Groundwater", options: ["auto", "gldas", "off"] },
];

export function Hazard({ ws, project, product, cell: linked, layer }: { ws: Workspace | undefined; project?: string; product?: string; cell?: number; layer?: string }) {
  const { go, layers } = useApp();
  const qc = useQueryClient();
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const [base, setBase] = useState<Base>("dark");
  const asView = (v?: string): View => (VIEWS.some((x) => x.id === v) ? (v as View) : "hazard");
  const [view, setViewState] = useState<View>(asView(layer));
  useEffect(() => setViewState(asView(layer)), [layer]); // eslint-disable-line react-hooks/exhaustive-deps
  // the layer is part of the link (#/hazard/<project>/<product>/<layer>): the Principles page opens the one it explains
  const setView = (v: View) => {
    setViewState(v);
    if (project && product) window.history.replaceState(null, "", href({ page: "hazard", name: project, product, view: v === "hazard" ? undefined : v }));
  };
  const [sel, setSel] = useState<number | null>(null);
  const [params, setParams] = useState<Record<string, number | string>>({});
  const [busy, setBusy] = useState("");
  const [refBox, setRefBox] = useState("");
  const [leftOpen, setLeftOpen] = usePersisted("hazard.left", true);
  const [rightOpen, setRightOpen] = usePersisted("hazard.right", true);
  const [tie, setTie] = useState(false);

  // products that can be zoned: the latest product of each track
  const choices = useMemo(() => {
    const out: { project: string; product: string; label: string }[] = [];
    Object.values(ws?.projects ?? {}).forEach((p) =>
      p.tracks.forEach((tr) => tr.product && out.push({ project: p.name, product: tr.product.id, label: `${p.name} · ${fmt.sensor(tr.sensor)} ${t(tr.direction)} v${tr.product.version}` })),
    );
    return out;
  }, [ws]);
  useEffect(() => {
    if (project && product) return;
    const shown = layers.find((l) => l.visible && choices.some((c) => c.product === l.product));
    const pick = shown ? { project: shown.project, product: shown.product } : choices[0];
    if (pick) go({ page: "hazard", name: pick.project, product: pick.product });
  }, [project, product, layers, choices, go]);

  const status = useQuery({
    queryKey: ["hazard", project, product],
    queryFn: () => api.hazard(project!, product!),
    enabled: !!project && !!product,
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
  });
  const s = status.data?.summary ?? null;
  useWarnings(`hazard:${project}/${product}:${s?.created}`, `${t("Hazard zoning")} · ${project}`, s?.warnings, project && product ? `#/hazard/${encodeURIComponent(project)}/${encodeURIComponent(product)}` : undefined);
  const cells = useQuery({
    queryKey: ["hazard-cells", project, product, s?.created],
    queryFn: async (): Promise<Cells> => {
      const { meta, buf } = await api.hazardCells(project!, product!);
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!s,
    staleTime: Infinity,
  });
  // GNSS comparison of the product (geoeyes gnss): its stations on the map, and the "GNSS tie" of the run
  const gnss = useQuery({
    queryKey: ["gnss", project, product],
    queryFn: () => api.gnss(project!, product!),
    enabled: !!project && !!product,
  });
  const calib = gnss.data?.summary?.calibration ?? null;
  const stations = gnss.data?.summary?.stations ?? [];
  const cell = useQuery({
    queryKey: ["hazard-cell", project, product, s?.created, sel],
    queryFn: () => api.hazardCell(project!, product!, sel!),
    enabled: !!s && sel != null,
  });
  // kinds of motion and risk to buildings (geoeyes behaviour / risk)
  const [selB, setSelB] = useState<number | null>(null);
  const behStatus = useQuery({
    queryKey: ["behaviour", project, product],
    queryFn: () => api.behaviour(project!, product!),
    enabled: !!project && !!product,
    refetchInterval: (q) => {
      const d = q.state.data;
      return d && Object.values(d).some((x) => typeof x === "object" && x?.running) ? 2000 : false;
    },
  });
  const behSummary = behStatus.data?.behaviour.summary ?? null;
  const riskSummary = behStatus.data?.risk.summary ?? null;
  const behCells = useQuery({
    queryKey: ["behaviour-cells", project, product, behSummary?.created],
    queryFn: async (): Promise<Behaviour & { first: string; last: string }> => {
      const { meta, buf } = await api.behaviourCells(project!, product!);
      return { buf, span: (Date.parse(meta.last_date) - Date.parse(meta.first_date)) / 86400000, first: meta.first_date, last: meta.last_date };
    },
    enabled: !!behSummary && !!s,
    staleTime: Infinity,
  });
  const behCell = useQuery({
    queryKey: ["behaviour-cell", project, product, behSummary?.created, sel],
    queryFn: () => api.behaviourCell(project!, product!, sel!),
    enabled: !!behSummary && sel != null,
  });
  const riskData = useQuery({
    queryKey: ["risk-buildings", project, product, riskSummary?.created],
    queryFn: async () => {
      const { meta, view: dv } = await api.riskBuildings(project!, product!);
      const n = meta.n;
      const pos = new Float32Array(n * 2);
      const col = new Uint8Array(n * 4);
      const rad = new Float32Array(n);
      const risk = new Int8Array(n);
      for (let i = 0; i < n; i++) {
        const o = i * meta.record;
        pos[i * 2] = meta.origin[0] + dv.getFloat32(o, true);
        pos[i * 2 + 1] = meta.origin[1] + dv.getFloat32(o + 4, true);
        const r = dv.getUint8(o + 8) - 1;
        risk[i] = r;
        const c = r >= 0 ? LEVEL_RGB[r] : NA_RGB;
        col.set([c[0], c[1], c[2], r >= 0 ? 235 : 120], i * 4);
        rad[i] = dv.getUint8(o + 11) / 2;
      }
      return { n, pos, col, rad, risk };
    },
    enabled: !!riskSummary && view === "risk",
    staleTime: Infinity,
  });
  const building = useQuery({
    queryKey: ["risk-building", project, product, riskSummary?.created, selB],
    queryFn: () => api.riskBuilding(project!, product!, selB!),
    enabled: !!riskSummary && selB != null,
  });
  const linesSummary = behStatus.data?.lines.summary ?? null;
  const consSummary = behStatus.data?.consolidation.summary ?? null;
  const [selLine, setSelLine] = useState<number | null>(null);
  const linesData = useQuery({
    queryKey: ["line-segments", project, product, linesSummary?.created],
    queryFn: async () => {
      const { meta, buf } = await api.lineSegments(project!, product!);
      const n = meta.n;
      const src = new Float32Array(n * 2);
      const dst = new Float32Array(n * 2);
      const col = new Uint8Array(n * 4);
      const wid = new Float32Array(n);
      const line = new Int32Array(n);
      for (let i = 0; i < n; i++) {
        const o = i * 6;
        src.set([buf[o], buf[o + 1]], i * 2);
        dst.set([buf[o + 2], buf[o + 3]], i * 2);
        const k = buf[o + 4];
        const c = k >= 0 ? LINE_RGB[k] : NA_RGB;
        col.set([c[0], c[1], c[2], k >= 0 ? 255 : 150], i * 4);
        wid[i] = k >= 1 ? 5 : k === 0 ? 3 : 2;
        line[i] = buf[o + 5];
      }
      return { n, src, dst, col, wid, line };
    },
    enabled: !!linesSummary && view === "lines",
    staleTime: Infinity,
  });
  const lineProfile = useQuery({
    queryKey: ["line-profile", project, product, linesSummary?.created, selLine],
    queryFn: () => api.lineProfile(project!, product!, selLine!),
    enabled: !!linesSummary && selLine != null,
  });
  const consCells = useQuery({
    queryKey: ["consolidation-cells", project, product, consSummary?.created],
    queryFn: async (): Promise<Consolidation> => {
      const { meta, buf } = await api.consolidationCells(project!, product!);
      return { buf, max: meta.summary.remaining_mm?.p90 ?? 1 };
    },
    enabled: !!consSummary && !!s,
    staleTime: Infinity,
  });
  const consCell = useQuery({
    queryKey: ["consolidation-cell", project, product, consSummary?.created, sel],
    queryFn: () => api.consolidationCell(project!, product!, sel!),
    enabled: !!consSummary && sel != null,
  });
  const decSummary = behStatus.data?.decompose.summary ?? null;
  const geoSummary = behStatus.data?.geology.summary ?? null;
  const decData = useQuery({
    queryKey: ["decompose-cells", project, product, decSummary?.created],
    queryFn: async () => {
      const { meta, buf } = await api.decomposeCells(project!, product!);
      const F = meta.fields.length;
      const f = Object.fromEntries(meta.fields.map((n, i) => [n, i]));
      const hx = meta.dlon / 2;
      const hy = meta.dlat / 2;
      const polys = Array.from({ length: meta.n }, (_, i) => {
        const x = buf[i * F];
        const y = buf[i * F + 1];
        return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
      });
      return { meta, buf, F, f, polys };
    },
    enabled: !!decSummary && (view === "up" || view === "east"),
    staleTime: Infinity,
  });
  const geoCells = useQuery({
    queryKey: ["geology-cells", project, product, geoSummary?.created],
    queryFn: async (): Promise<Geology> => {
      const { meta, buf } = await api.geologyCells(project!, product!);
      const th = meta.summary.thickness_m;
      return { buf, min: th?.min ?? 0, max: th?.max ?? 1 };
    },
    enabled: !!geoSummary && view === "soft_soil",
    staleTime: Infinity,
  });
  const runAnalysis = async (kind: AnalysisKind) => {
    if (!project || !product) return;
    try {
      await api.analysisRun(project, product, kind);
      await qc.invalidateQueries({ queryKey: ["behaviour", project, product] });
    } catch (e) {
      setBusy(ts((e as Error).message));
    }
  };

  useEffect(() => {
    if (s) setParams(Object.fromEntries(PARAMS.map((p) => [p.key, s.params[p.key] as number | string])));
    setRefBox(s && Array.isArray(s.params.reference_bbox) ? (s.params.reference_bbox as number[]).join(", ") : "");
    setTie(!!s?.params.gnss_tie);
    setSel(linked ?? null);
  }, [s]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------ map
  useEffect(() => {
    if (!mapEl.current) return;
    const m = new maplibregl.Map({
      container: mapEl.current,
      style: mapStyle("dark"),
      center: [105.82, 21.02],
      zoom: 10,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    const ov = new MapboxOverlay({ interleaved: false, layers: [] });
    m.addControl(ov as unknown as maplibregl.IControl);
    map.current = m;
    overlay.current = ov;
    return () => {
      m.remove();
      map.current = null;
      overlay.current = null;
    };
  }, []);
  const firstBase = useRef(true);
  useEffect(() => {
    if (firstBase.current) {
      firstBase.current = false;
      return;
    }
    map.current?.setStyle(mapStyle(base));
  }, [base]);
  useEffect(() => {
    if (s && map.current) map.current.fitBounds(s.bounds, { padding: 60, duration: 600 });
  }, [s?.product_id, s?.created]); // eslint-disable-line react-hooks/exhaustive-deps

  const polys = useMemo(() => {
    const c = cells.data;
    if (!c) return null;
    const F = c.meta.fields.length;
    const hx = (0.5 * c.meta.cell_m) / (111320 * Math.cos((c.meta.lat0 * Math.PI) / 180));
    const hy = (0.5 * c.meta.cell_m) / 110540;
    const [lon0, lat0] = c.meta.origin;
    return Array.from({ length: c.meta.n }, (_, i) => {
      const x = lon0 + c.buf[i * F];
      const y = lat0 + c.buf[i * F + 1];
      return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
    });
  }, [cells.data]);

  useEffect(() => {
    const ov = overlay.current;
    const c = cells.data;
    if (!ov) return;
    if (!c || !polys) {
      ov.setProps({ layers: [] });
      return;
    }
    ov.setProps({
      layers: [
        ...(stations.length
          ? [
              new ScatterplotLayer<(typeof stations)[number]>({
                id: "gnss-stations",
                data: stations,
                getPosition: (d) => [d.lon, d.lat],
                getRadius: 7,
                radiusUnits: "pixels",
                getFillColor: (d) => (d.used ? [255, 255, 255, 255] : [140, 150, 170, 200]),
                getLineColor: [11, 18, 32, 255],
                lineWidthMinPixels: 2,
                stroked: true,
                pickable: true,
              }),
              new TextLayer<(typeof stations)[number]>({
                id: "gnss-labels",
                data: stations,
                getPosition: (d) => [d.lon, d.lat],
                getText: (d) => d.site,
                getSize: 12,
                getColor: [255, 255, 255, 255],
                getPixelOffset: [12, 0],
                getTextAnchor: "start",
                getAlignmentBaseline: "center",
                fontFamily: "JetBrains Mono, monospace",
                outlineWidth: 3,
                outlineColor: [11, 18, 32, 255],
                fontSettings: { sdf: true },
              }),
            ]
          : []),
        ...(view === "lines" && linesData.data
          ? [
              new LineLayer({
                id: "infrastructure-lines",
                data: {
                  length: linesData.data.n,
                  attributes: {
                    getSourcePosition: { value: linesData.data.src, size: 2 },
                    getTargetPosition: { value: linesData.data.dst, size: 2 },
                    getColor: { value: linesData.data.col, size: 4, normalized: true },
                    getWidth: { value: linesData.data.wid, size: 1 },
                  },
                },
                widthUnits: "pixels",
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 200],
                onClick: (info: { index: number }) => {
                  if (info.index >= 0) {
                    setSelLine(linesData.data!.line[info.index]);
                    setSel(null);
                    setSelB(null);
                  }
                },
              }),
            ]
          : []),
        ...((view === "up" || view === "east") && decData.data
          ? [
              new SolidPolygonLayer<{ i: number; ring: number[][] }>({
                id: "decompose-cells",
                data: decData.data.polys,
                getPolygon: (d) => d.ring as never,
                getFillColor: (d) => {
                  const D = decData.data!;
                  const v = D.buf[d.i * D.F + D.f[view]];
                  // the same classes as the rate: red sinking, blue rising; green east, purple west
                  return [...(view === "up" ? RATE_RGB[bin(-v, MOTION_BREAKS)] : EAST_RGB[bin(v, MOTION_BREAKS)]), 225] as never;
                },
                updateTriggers: { getFillColor: [view] },
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 120],
              }),
            ]
          : []),
        ...(view === "risk" && riskData.data
          ? [
              new ScatterplotLayer({
                id: "risk-buildings",
                data: {
                  length: riskData.data.n,
                  attributes: {
                    getPosition: { value: riskData.data.pos, size: 2 },
                    getFillColor: { value: riskData.data.col, size: 4, normalized: true },
                    getRadius: { value: riskData.data.rad, size: 1 },
                  },
                },
                radiusUnits: "meters",
                radiusMinPixels: 1.2,
                pickable: true,
                onClick: (info: { index: number }) => {
                  if (info.index >= 0) {
                    setSelB(info.index);
                    setSel(null);
                  }
                },
              }),
            ]
          : []),
        new SolidPolygonLayer<{ i: number; ring: number[][] }>({
          id: `hazard-${view}`,
          data: polys,
          getPolygon: (d) => d.ring as never,
          getFillColor: (d) => (d.i === sel ? [255, 255, 255, 255] : cellColor(c, d.i, view, behCells.data, consCells.data, geoCells.data)),
          updateTriggers: { getFillColor: [view, sel, behCells.data, consCells.data, geoCells.data] },
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 120],
          onClick: (info) => {
            if (info.object) {
              setSel(info.object.i);
              setSelB(null);
              setSelLine(null);
            }
          },
        }),
      ].reverse() as never,
      getTooltip: ({ object, layer, index }: { object?: { i: number } & Partial<(typeof stations)[number]>; layer?: { id: string } | null; index: number }) => {
        if (layer?.id === "decompose-cells" && decData.data && object) {
          const D = decData.data;
          const g = (n: string) => D.buf[object.i * D.F + D.f[n]];
          const prods = D.meta.summary.products;
          return {
            text: [
              `${t("vertical")} ${fmt.vel(g("up"))} ± ${g("sigma_up").toFixed(1)} mm/yr`,
              `${t("east-west")} ${fmt.vel(g("east"))} ± ${g("sigma_east").toFixed(1)} mm/yr`,
              ...prods.map((p, k) => `${t("{track} alone", { track: p.track })}: ${fmt.vel(g(`vert_only_${k}`))} mm/yr`),
            ].join("\n"),
            style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
          };
        }
        if (layer?.id === "infrastructure-lines" && linesData.data && index >= 0) {
          return {
            text: t("Click for the profile along the line"),
            style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
          };
        }
        if (layer?.id === "risk-buildings" && riskData.data && index >= 0) {
          const r = riskData.data.risk[index];
          return {
            text: r >= 0 ? t("{level} risk", { level: t(LEVELS[r]) }) : t("not assessed"),
            style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
          };
        }
        if (!object) return null;
        if (layer?.id === "gnss-stations") {
          const st = object as (typeof stations)[number];
          const v = st.vertical;
          return {
            text: `GNSS ${st.site}${st.used && v ? `
GNSS − InSAR ${fmt.vel(v.rate_diff_mm_yr)} mm/yr (LOS)` : `
${ts(st.reason ?? "")}`}`,
            style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
          };
        }
        const F = c.meta.fields.length;
        const g = (n: string) => c.buf[object.i * F + c.f[n]];
        const lv = g("hazard");
        const h = view === "soft_soil" && geoCells.data ? geoCells.data.buf[object.i * 2] : NaN;
        if (Number.isFinite(h))
          return {
            text: `${t("soft soil")} ${h.toFixed(0)} m\n${fmt.vel(g("rate_mm_yr"))} mm/yr`,
            style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
          };
        return {
          text: `${lv >= 0 ? t(LEVELS[lv]) : t("not assessed")} · I${g("intensity")} S${Math.max(0, g("secondary"))}\n${fmt.vel(g("rate_mm_yr"))} mm/yr${g("rain_coupled") > 0 ? ` · ${t("rain r {r}, lag {n} mo", { r: g("rain_r").toFixed(2), n: g("rain_lag_months") })}` : ""}`,
          style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
        };
      },
    });
  }, [cells.data, polys, view, sel, stations, behCells.data, riskData.data, linesData.data, consCells.data, decData.data, geoCells.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async () => {
    if (!project || !product) return;
    setBusy("");
    const box = refBox.split(/[\s,]+/).filter(Boolean).map(Number);
    if (box.length !== 0 && (box.length !== 4 || box.some((v) => !Number.isFinite(v)))) {
      setBusy(t("Reference area: west, south, east, north (degrees)"));
      return;
    }
    try {
      await api.hazardRun(project, product, { ...params, reference_bbox: box, gnss_tie: tie });
      await qc.invalidateQueries({ queryKey: ["hazard", project, product] });
    } catch (e) {
      const msg = (e as Error).message;
      // the page is newer than the running server (built files are read from disk, the API code is not)
      setBusy(/method not allowed|not found/i.test(msg) ? t("{msg}: the running server predates this page, restart geoeyes serve", { msg: ts(msg) }) : ts(msg));
    }
  };

  const running = !!status.data?.running;
  const by = s?.by_level;
  const km2 = (mode: "subsidence" | "landslide", lv: string) => (by?.[mode]?.[lv] as { km2: number } | undefined)?.km2 ?? 0;
  const total = s ? LEVELS.reduce((a, l) => a + km2("subsidence", l.toLowerCase()) + km2("landslide", l.toLowerCase()), 0) || 1 : 1;
  const climate = s?.rain.pixels.find((p) => p.annual)?.annual;

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div className="absolute inset-0">
        <div ref={mapEl} className="h-full w-full" />
      </div>

      {/* left: product, run, summary */}
      {!leftOpen && (
        <div className="absolute top-3 left-3 z-10">
          <ColumnToggle open={false} side="left" label={t("Hazard zoning")} onClick={() => setLeftOpen(true)} />
        </div>
      )}
      {leftOpen && (
        <div className="pointer-events-none absolute top-3 bottom-[184px] left-3 z-10 flex w-[min(350px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto">
          <Fold id="hazard.run" title={t("HAZARD ZONING")} extra={<ColumnToggle open side="left" label={t("zoning")} onClick={() => setLeftOpen(false)} />}>
            <select
              value={project && product ? `${project}/${product}` : ""}
              onChange={(e) => {
                const [n, ...rest] = e.target.value.split("/");
                go({ page: "hazard", name: n, product: rest.join("/") });
              }}
              aria-label={t("Product")}
              className="mt-2 h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink"
            >
              {choices.length === 0 && <option value="">{t("No product in the workspace")}</option>}
              {choices.map((c) => (
                <option key={`${c.project}/${c.product}`} value={`${c.project}/${c.product}`}>
                  {c.label}
                </option>
              ))}
            </select>
            <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
              {PARAMS.map((p) => (
                <label key={p.key} className="flex items-center gap-1.5 text-[12px] text-muted">
                  <span className="w-[76px] flex-none truncate" title={t(p.label)}>{t(p.label)}</span>
                  <select
                    value={String(params[p.key] ?? (p.key === "cell_m" ? 100 : p.key === "horizon_yr" ? 10 : p.key === "max_lag_months" ? 6 : p.key === "alpha" ? 0.05 : "auto"))}
                    onChange={(e) => setParams((v) => ({ ...v, [p.key]: typeof p.options[0] === "number" ? Number(e.target.value) : e.target.value }))}
                    className="h-7 min-w-0 flex-1 rounded-md border border-line-2 bg-[#0a1322] px-1 text-[12px] text-ink"
                  >
                    {p.options.map((o) => (
                      <option key={o} value={String(o)}>
                        {o}
                        {p.unit ? ` ${t(p.unit)}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <label
              className="mt-1.5 flex items-center gap-1.5 text-[12px] text-muted"
              title={t("Stable ground (e.g. bedrock, a GNSS station): the series are re-referenced to the median of its cells. Empty = the product's reference")}
            >
              <span className="w-[76px] flex-none truncate">{t("Stable")}</span>
              <input
                value={refBox}
                onChange={(e) => setRefBox(e.target.value)}
                placeholder={t("reference area: W, S, E, N (optional)")}
                className="h-7 min-w-0 flex-1 rounded-md border border-line-2 bg-[#0a1322] px-2 font-mono text-[11.5px] text-ink placeholder:font-sans placeholder:text-faint"
              />
            </label>
            <label
              className={`mt-1.5 flex items-center gap-1.5 text-[12px] ${calib ? "text-muted" : "text-faint"}`}
              title={t(
                "Add the GNSS calibration of this product (Project → Validation → GNSS) to the series before rating them: rates relative to the GNSS frame instead of the product's reference",
              )}
            >
              <span className="w-[76px] flex-none">GNSS</span>
              <input type="checkbox" className="ml-0.5 flex-none accent-[#4cc2ff]" disabled={!calib} checked={tie && !!calib} onChange={(e) => setTie(e.target.checked)} />
              <span className="flex-none whitespace-nowrap">{t("tie")}</span>
              <span className="min-w-0 truncate">
                {calib
                  ? `· ${calib.stations.join(", ")} (${fmt.vel(calib.rate_offset_mm_yr)} mm/yr${calib.loo_rms_after_mm_yr != null ? `, LOO ±${fmt.num(calib.loo_rms_after_mm_yr)}` : `, ${t("1 station")}`})`
                  : gnss.error
                    ? `· ${t("GNSS unavailable: restart geoeyes serve (the server predates this page)")}`
                    : `· ${t("no GNSS comparison of this product yet (Project → Validation → GNSS)")}`}
              </span>
            </label>
            <div className="mt-3 flex items-center gap-2">
              <Button variant="primary" disabled={!product || running} onClick={run}>
                {running ? t("Running…") : s ? t("Run again") : t("Run hazard zoning")}
              </Button>
              {s && (
                <a className="text-[12px] text-accent hover:underline" href={api.hazardFile(project!, product!, "hazard.gpkg")}>
                  GeoPackage
                </a>
              )}
              {s && (
                <a className="text-[12px] text-accent hover:underline" href={api.hazardFile(project!, product!, "cells.parquet")}>
                  Parquet
                </a>
              )}
            </div>
            {busy && <div className="mt-2 text-[12px] text-bad">{busy}</div>}
            {(running || status.data?.failed) && status.data!.log.length > 0 && (
              <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-line bg-[#070c16] p-2 font-mono text-[11px] text-[#a9b8cf]">
                {status.data!.log.join("\n")}
              </pre>
            )}
            {!s && !running && product && (
              <p className="mt-2 text-[12px] leading-snug text-muted">
                {t(
                  "Not zoned yet. The run reads the DEM and the rainfall (CHIRPS, cached; the first time takes a minute) and writes the cells under analyses/hazard of the project.",
                )}
              </p>
            )}
          </Fold>

          {s && (
            <Fold id="hazard.summary" title={t("SUMMARY")}>
              <div className="mt-1 text-[12px] text-ink-2">
                {t("{n} cells of {m} m · {p} points · {d0} → {d1} ({k} months)", {
                  n: fmt.int(s.n_cells),
                  m: String(s.params.cell_m),
                  p: fmt.int(s.n_points),
                  d0: s.dates[0],
                  d1: s.dates[s.dates.length - 1],
                  k: s.span_months,
                })}
              </div>
              <div className="mt-2 flex h-3 overflow-hidden rounded">
                {[...LEVELS].map((l, i) => {
                  const a = km2("subsidence", l.toLowerCase()) + km2("landslide", l.toLowerCase());
                  return a > 0 ? <span key={l} title={`${t(l)}: ${a.toFixed(2)} km²`} style={{ width: `${(100 * a) / total}%`, background: rgb(LEVEL_RGB[i]) }} /> : null;
                })}
              </div>
              <div className="mt-2 grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-0.5 text-[12px]">
                <span className="text-[11px] text-faint">{t("level")}</span>
                <span className="text-right text-[11px] text-faint">{t("subsidence")}</span>
                <span className="text-right text-[11px] text-faint">{t("landslide")}</span>
                {[...LEVELS].reverse().map((l) => (
                  <div key={l} className="contents">
                    <span className="text-muted">{t(l)}</span>
                    <span className="text-right font-mono text-[11.5px] text-ink-2">{km2("subsidence", l.toLowerCase()).toFixed(2)} km²</span>
                    <span className="text-right font-mono text-[11.5px] text-ink-2">{km2("landslide", l.toLowerCase()).toFixed(2)} km²</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 rounded-lg border border-line bg-panel-2 px-2.5 py-2 text-[12px] leading-snug">
                <div className="text-[11px] font-semibold tracking-[1px] text-muted">{t("RAINFALL")}</div>
                <div className="mt-1 text-ink-2">{ts(s.rain.source).split(" (")[0]}</div>
                {climate && (
                  <div className="text-muted">
                    {t("Annual {a}–{b}: dry year (P10)", { a: s.rain.climate_years[0], b: s.rain.climate_years[1] })} <span className="font-mono text-ink-2">{climate.p10}</span>,{" "}
                    {t("median")} <span className="font-mono text-ink-2">{climate.p50}</span>, {t("wet year (P90)")} <span className="font-mono text-ink-2">{climate.p90}</span> mm
                  </div>
                )}
                <div className="mt-1 text-muted">
                  {s.coupling.assessed ? (
                    <>
                      {t("Coupling tested in {n} cells:", { n: fmt.int(s.coupling.cells_tested) })}{" "}
                      <span className="text-ink-2">{t("{n} significant", { n: fmt.int(s.coupling.cells_significant) })}</span>{" "}
                      {t("at FDR {a} ({k} below p {a} before the map-wide correction)", { a: String(s.params.alpha), k: fmt.int(s.coupling.cells_p_below_alpha) })}
                      {s.coupling.lag_months_median != null ? t("; median lag {n} months", { n: s.coupling.lag_months_median }) : ""}.
                    </>
                  ) : (
                    t("Coupling not assessed: the series is shorter than a seasonal cycle.")
                  )}
                </div>
                {s.accelerating_cells > 0 && <div className="mt-1 text-muted">{t("{n} cells accelerate significantly.", { n: fmt.int(s.accelerating_cells) })}</div>}
              </div>
              <div className="mt-2 text-[12px] leading-snug text-muted">
                {t("Reference:")}{" "}
                <span className="text-ink-2">
                  {s.reference.kind === "gnss"
                    ? `GNSS ${s.reference.stations?.join(", ")} (${ts(s.reference.calibration ?? "")}, ${fmt.vel(s.reference.rate_offset_mm_yr)} mm/yr)`
                    : s.reference.kind === "reference_bbox"
                    ? t("stable area {b} ({n} cells)", { b: s.reference.bbox?.join(", "), n: s.reference.cells })
                    : s.reference.kind === "point"
                      ? t("product reference point {lon}, {lat}", { lon: fmt.num(s.reference.lon, 4), lat: fmt.num(s.reference.lat, 4) })
                      : t("product ({kind})", { kind: ts(s.reference.kind) })}
                </span>
                {s.opposite_motion_cells > 0 &&
                  ` · ${t("{n} cells move against the hazard direction (uplift / upslope), flagged, not rated", { n: fmt.int(s.opposite_motion_cells) })}`}
              </div>
              {s.warnings.length > 0 && (
                <div className="mt-2 flex items-center gap-1.5 rounded-md bg-[#2a2110] px-2 py-1 text-[11.5px] text-[#f5d08b]">
                  <span aria-hidden>!</span> {t("{n} warning(s): see the notifications", { n: s.warnings.length })}
                </div>
              )}
            </Fold>
          )}
          <MethodLink />
        </div>
      )}

      <BasemapPicker map={map} base={base} onChange={setBase} />

      {/* right: view, legend, cell */}
      {s && !rightOpen && (
        <div className="absolute top-3 right-3 z-10">
          <ColumnToggle open={false} side="right" label={t("Legend & cell")} onClick={() => setRightOpen(true)} />
        </div>
      )}
      {s && rightOpen && (
        <div className="pointer-events-none absolute top-3 right-3 bottom-3 z-10 flex w-[min(370px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto max-md:top-auto max-md:max-h-[45%]">
          <Fold id="hazard.legend" title={t("LAYERS")} extra={<ColumnToggle open side="right" label={t("legend")} onClick={() => setRightOpen(false)} />}>
            <select value={view} onChange={(e) => setView(e.target.value as View)} aria-label={t("Map layer")} className="h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink">
              {VIEW_GROUPS.map(([grp, ids]) => (
                <optgroup key={grp} label={t(grp)}>
                  {ids.map((id) => (
                    <option key={id} value={id}>
                      {t(VIEWS.find((v) => v.id === id)!.label)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <Legend view={view} s={s} />
            {(view === "behaviour" || view === "change" || view === "risk" || view === "lines" || view === "consolidation" || view === "up" || view === "east" || view === "soft_soil") && (
              <BehaviourLegend view={view} st={behStatus.data} first={behCells.data?.first} last={behCells.data?.last} onRun={runAnalysis} />
            )}
            <About view={view} />
            {cells.isLoading && <div className="mt-2 text-[12px] text-[#7cd2ff]">{t("Loading cells…")}</div>}
          </Fold>
          {sel != null && cell.data && <CellPanel c={cell.data} beh={behCell.data} cons={consCell.data} onClose={() => setSel(null)} />}
          {selLine != null && lineProfile.data && <LinePanel p={lineProfile.data} onClose={() => setSelLine(null)} />}
          {selB != null && building.data && <RiskPanel b={building.data} onClose={() => setSelB(null)} />}
          {sel != null && cell.isLoading && <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Loading cell…")}</div>}
          {sel == null && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Click a cell for its series, rainfall and the reasons of its level.")}</div>
          )}
        </div>
      )}
    </div>
  );
}
