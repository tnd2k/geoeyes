// Hazard: ground-motion hazard zoning of a product with rainfall (geoeyes hazard). Cells of the analysis grid
// coloured by hazard level or by one of its ingredients (InSAR intensity, angular distortion / slope, rainfall
// coupling); click a cell for its series in the motion direction, the rainfall of its pixel and the fitted models.
// Method and sources: docs/en/research/rainfall-insar-hazard.md.
import { ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import { api, type HazardCell, type HazardCellsMeta, type HazardSummary, type Workspace } from "../api";
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

export type View = "hazard" | "intensity" | "secondary" | "rate" | "coupling" | "lag" | "groundwater" | "mode";
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
];

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

export function cellColor(c: Cells, i: number, view: View): [number, number, number, number] {
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

export function CellChart({ c }: { c: HazardCell }) {
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
    if (c.rain_model_mm) {
      series.push({ stroke: "#f5b84b", width: 1.8, points: { show: false } });
      data.push(c.rain_model_mm);
    }
    if (c.gw_model_mm && c.gw_coupled) {
      series.push({ stroke: "#7ee0c3", width: 1.8, dash: [6, 3], points: { show: false } });
      data.push(c.gw_model_mm);
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
  }, [c]);
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
        {c.rain_model_mm && (
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4 bg-[#f5b84b]" /> {t("trend + k·CRD(t − {n} mo)", { n: c.rain_lag_months })}
          </span>
        )}
        {c.gw_model_mm && c.gw_coupled && (
          <span className="flex items-center gap-1">
            <span className="w-4 border-t-2 border-dashed border-[#7ee0c3]" /> {t("trend + g·GWS(t − {n} mo)", { n: c.gw_lag_months ?? 0 })}
          </span>
        )}
      </div>
      <div className="mt-2">
        <RainBars months={rainMonths} from={c.dates[0]} to={c.dates[c.dates.length - 1]} />
      </div>
      <div className="text-[11px] text-faint">{t("Monthly rainfall of the cell's pixel")} · {ts(c.rain.source).split(" (")[0]}</div>
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

function CellPanel({ c, onClose }: { c: HazardCell; onClose: () => void }) {
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
      <div className="mt-2">
        <CellChart c={c} />
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

export function Hazard({ ws, project, product, cell: linked }: { ws: Workspace | undefined; project?: string; product?: string; cell?: number }) {
  const { go, layers } = useApp();
  const qc = useQueryClient();
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const [base, setBase] = useState<Base>("dark");
  const [view, setView] = useState<View>("hazard");
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
        new SolidPolygonLayer<{ i: number; ring: number[][] }>({
          id: `hazard-${view}`,
          data: polys,
          getPolygon: (d) => d.ring as never,
          getFillColor: (d) => (d.i === sel ? [255, 255, 255, 255] : cellColor(c, d.i, view)),
          updateTriggers: { getFillColor: [view, sel] },
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 120],
          onClick: (info) => info.object && setSel(info.object.i),
        }),
      ].reverse() as never,
      getTooltip: ({ object, layer }: { object?: { i: number } & Partial<(typeof stations)[number]>; layer?: { id: string } | null }) => {
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
        return {
          text: `${lv >= 0 ? t(LEVELS[lv]) : t("not assessed")} · I${g("intensity")} S${Math.max(0, g("secondary"))}\n${fmt.vel(g("rate_mm_yr"))} mm/yr${g("rain_coupled") > 0 ? ` · ${t("rain r {r}, lag {n} mo", { r: g("rain_r").toFixed(2), n: g("rain_lag_months") })}` : ""}`,
          style: { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" },
        };
      },
    });
  }, [cells.data, polys, view, sel, stations]);

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
            <About view={view} />
            {cells.isLoading && <div className="mt-2 text-[12px] text-[#7cd2ff]">{t("Loading cells…")}</div>}
          </Fold>
          {sel != null && cell.data && <CellPanel c={cell.data} onClose={() => setSel(null)} />}
          {sel != null && cell.isLoading && <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Loading cell…")}</div>}
          {sel == null && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Click a cell for its series, rainfall and the reasons of its level.")}</div>
          )}
        </div>
      )}
    </div>
  );
}
