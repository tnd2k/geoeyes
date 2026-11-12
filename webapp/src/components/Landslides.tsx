// Landslide inventory over the products: the field surveys of the workspace (`geoeyes landslide survey`, coloured
// by the survey's own colour or its risk level, labelled by name) and the reported events (NASA GLC + curated, small
// violet dots); with a product shown, the velocity of its points around each one in the tooltip.
import { PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { FloodStats, LandslideCollection, LandslideFeature } from "../api";
import { t } from "../i18n";
import { fmt } from "../ui";

type RGB = [number, number, number];
const REPORTED: RGB = [139, 92, 246];
// risk levels as surveyed in Vietnamese, then common English ones
export const RISK_COLOR: [string, RGB][] = [
  ["rất cao", [231, 76, 60]],
  ["cao", [230, 126, 34]],
  ["trung bình", [241, 196, 15]],
  ["thấp", [46, 204, 113]],
  ["very high", [231, 76, 60]],
  ["high", [230, 126, 34]],
  ["medium", [241, 196, 15]],
  ["moderate", [241, 196, 15]],
  ["low", [46, 204, 113]],
];
const GREY: RGB = [148, 163, 184];

const str = (v: unknown) => (v == null ? "" : String(v));

function hex(s: string): RGB | undefined {
  const m = /^#?([0-9a-f]{6})$/i.exec(s.trim());
  if (!m) return undefined;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export const riskOf = (f: LandslideFeature) => str(f.properties.risk_level ?? f.properties.risk ?? f.properties.muc_do);

export function landslideColor(f: LandslideFeature): RGB {
  if (f.properties.layer === "reported") return REPORTED;
  const r = riskOf(f).toLowerCase();
  return RISK_COLOR.find(([k]) => k === r)?.[1] ?? hex(str(f.properties.color_hex ?? f.properties.color)) ?? GREY;
}

export const landslideName = (f: LandslideFeature) =>
  str(f.properties.name ?? f.properties.km_marker ?? f.properties.id ?? f.id.split(":").pop());

function anchor(f: LandslideFeature): [number, number] {
  const g = f.geometry;
  if (g.type === "Point") return [g.coordinates[0], g.coordinates[1]];
  const ring = g.type === "Polygon" ? g.coordinates[0] : g.type === "MultiPolygon" ? g.coordinates[0][0] : g.coordinates;
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
}

export function landslideBounds(f: LandslideFeature): [number, number, number, number] {
  const [x, y] = anchor(f);
  return [x - 0.004, y - 0.004, x + 0.004, y + 0.004];
}

export function landslideLayers(
  fc: LandslideCollection | undefined,
  opts: { selected: string | null; onPick: (id: string) => void; three: boolean; extensions: unknown[]; reported: boolean },
) {
  const feats = (fc?.features ?? []).filter((f) => opts.reported || f.properties.layer !== "reported");
  const survey = feats.filter((f) => f.properties.layer !== "reported");
  const reported = feats.filter((f) => f.properties.layer === "reported");
  const polys = survey.filter((f) => f.geometry.type === "Polygon" || f.geometry.type === "MultiPolygon");
  const sfx = opts.three ? "-3d" : "";
  const ext = opts.extensions as never;
  const sel = (f: LandslideFeature) => f.id === opts.selected;
  return [
    new PolygonLayer<LandslideFeature>({
      id: `landslide-polys${sfx}`,
      extensions: ext,
      data: polys,
      getPolygon: (f) => (f.geometry.type === "Polygon" ? f.geometry.coordinates : (f.geometry.coordinates as number[][][][])[0]) as never,
      getFillColor: (f) => [...landslideColor(f), 70],
      getLineColor: (f) => [...landslideColor(f), 255],
      lineWidthMinPixels: 2,
      pickable: true,
      onClick: ({ object }) => object && opts.onPick(object.id),
    }),
    new ScatterplotLayer<LandslideFeature>({
      id: `landslide-reported${sfx}`,
      extensions: ext,
      data: reported,
      getPosition: anchor,
      getRadius: (f) => (sel(f) ? 8 : 5),
      radiusUnits: "pixels",
      getFillColor: [...REPORTED, 210],
      stroked: true,
      getLineColor: (f) => (sel(f) ? [255, 209, 102] : [255, 255, 255]),
      lineWidthMinPixels: 1.5,
      pickable: true,
      onClick: ({ object }) => object && opts.onPick(object.id),
      updateTriggers: { getRadius: opts.selected, getLineColor: opts.selected },
    }),
    // surveyed sites: a ring in the risk colour around a dark centre (the owner's QGIS style, coloured)
    new ScatterplotLayer<LandslideFeature>({
      id: `landslide-survey${sfx}`,
      extensions: ext,
      data: survey,
      getPosition: anchor,
      getRadius: (f) => (sel(f) ? 11 : 8),
      radiusUnits: "pixels",
      getFillColor: (f) => [...landslideColor(f), 240],
      stroked: true,
      getLineColor: (f) => (sel(f) ? [255, 209, 102] : [17, 24, 39]),
      lineWidthMinPixels: 2,
      pickable: true,
      onClick: ({ object }) => object && opts.onPick(object.id),
      updateTriggers: { getRadius: opts.selected, getLineColor: opts.selected },
    }),
    new ScatterplotLayer<LandslideFeature>({
      id: `landslide-dot${sfx}`,
      extensions: ext,
      data: survey,
      getPosition: anchor,
      getRadius: 2,
      radiusUnits: "pixels",
      getFillColor: [17, 24, 39],
    }),
    new TextLayer<LandslideFeature>({
      id: `landslide-labels${sfx}`,
      extensions: ext,
      data: survey,
      getPosition: anchor,
      getText: (f) => `Km${landslideName(f)}`,
      getSize: 12,
      getColor: [17, 24, 39],
      getPixelOffset: [12, -10],
      getTextAnchor: "start",
      fontFamily: "Inter, system-ui, sans-serif",
      fontWeight: 600,
      outlineWidth: 3,
      outlineColor: [255, 255, 255, 230],
      fontSettings: { sdf: true },
      characterSet: "auto",
    }),
  ];
}

const SHOWN = [
  ["landslide_type", "Type"],
  ["risk_level", "Risk level"],
  ["current_status", "Site status"],
  ["material_type", "Material"],
  ["slope_height", "Slope height (m)"],
  ["landslide_length", "Length (m)"],
  ["landslide_width", "Width (m)"],
  ["crack_presence", "Cracks"],
  ["toe_erosion", "Toe erosion"],
  ["water_observed", "Water observed"],
  ["vegetation_cover", "Vegetation"],
] as const;

export function landslideTooltip(f: LandslideFeature, stats?: FloodStats): string {
  const p = f.properties;
  const lines: string[] = [];
  if (p.layer === "reported") {
    lines.push(`${str(p.date)} · ${str(p.place)}`, `${str(p.type)}${p.trigger ? ` · ${str(p.trigger)}` : ""}`);
    if (p.accuracy_m) lines.push(t("located to {m} m", { m: fmt.int(Number(p.accuracy_m)) }));
    lines.push(`${str(p.source_db)}${p.source ? ` · ${str(p.source)}` : ""}`);
  } else {
    lines.push(`${str(p.route) || ""} Km${landslideName(f)}`.trim());
    for (const [k, label] of SHOWN) if (p[k] != null && p[k] !== "") lines.push(`${t(label)}: ${str(p[k])}`);
    if (p.location_description) lines.push(str(p.location_description));
    lines.push(`${t("Survey")}: ${[p.survey_date, p.survey_team].filter(Boolean).map(str).join(" · ")}`);
  }
  const s = stats?.rows[f.id];
  if (s?.n)
    lines.push(
      t("{n} points within {r} m: median {v} mm/yr", { n: fmt.int(s.n), r: stats!.radius_m, v: fmt.vel(s.vel_median!) }) +
        (s.ring_median != null ? ` (${t("around: {v}", { v: fmt.vel(s.ring_median) })})` : ""),
    );
  else if (stats) lines.push(t("no point of the product within {r} m", { r: stats.radius_m }));
  return lines.join("\n");
}

/** Legend (map overlay while the tool is on): the risk colours found in the surveys, the reported events. */
export function LandslideLegend({ fc, reported, onReported }: { fc?: LandslideCollection; reported: boolean; onReported: (v: boolean) => void }) {
  const risks = Array.from(new Set((fc?.features ?? []).filter((f) => f.properties.layer !== "reported").map((f) => riskOf(f)).filter(Boolean)));
  const order = (r: string) => {
    const i = RISK_COLOR.findIndex(([k]) => k === r.toLowerCase());
    return i < 0 ? 99 : i;
  };
  risks.sort((a, b) => order(a) - order(b));
  const surveys = (fc?.layers ?? []).filter((l) => l.kind === "survey");
  const nRep = fc?.layers.find((l) => l.kind === "reported")?.n ?? 0;
  const sw = (c: RGB) => <span className="h-3 w-3 flex-none rounded-full border-2 border-[#111827]" style={{ background: `rgb(${c.join(",")})` }} />;
  return (
    <div className="pointer-events-auto rounded-lg border border-line-2 bg-panel/95 px-2.5 py-2 text-[11px] text-ink-2 shadow-lg shadow-black/30 backdrop-blur">
      <div className="mb-1 font-semibold text-ink">{t("Landslide inventory")}</div>
      {surveys.length === 0 && <div className="max-w-[200px] text-faint">{t("No field survey yet: geoeyes landslide survey --file <gpkg|kmz>")}</div>}
      {surveys.map((l) => (
        <div key={l.layer} className="text-faint">
          {t("Survey {name}: {n} sites", { name: l.layer, n: l.n })}
        </div>
      ))}
      {risks.map((r) => (
        <div key={r} className="flex items-center gap-2">
          {sw(RISK_COLOR.find(([k]) => k === r.toLowerCase())?.[1] ?? GREY)}
          <span>{r}</span>
        </div>
      ))}
      <label className="mt-1 flex items-center gap-2">
        <input type="checkbox" checked={reported} onChange={(e) => onReported(e.target.checked)} />
        <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: `rgb(${REPORTED.join(",")})` }} />
        {t("Reported events ({n})", { n: nRep })}
      </label>
    </div>
  );
}
