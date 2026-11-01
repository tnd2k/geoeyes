// Reported flood locations (workspace inventory, `geoeyes floods`) over the products: lines for street segments,
// dots for junctions and places, coloured by cause; with a product shown, the velocity of its points around each one.
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { FloodCollection, FloodFeature, FloodLocated, FloodStats } from "../api";
import { t } from "../i18n";
import { fmt } from "../ui";

export const CAUSE_COLOR: Record<string, [number, number, number]> = {
  rain: [37, 99, 235],
  tide: [168, 85, 247],
  rain_tide: [8, 145, 178],
  "": [100, 116, 139],
};
const CAUSE_LABEL: Record<string, string> = { rain: "rain", tide: "high tide", rain_tide: "rain and tide", "": "unknown cause" };
// placed on the exact street stretch / junction, by a named place, or only near it (whole street, one end)
export const PRECISE: FloodLocated[] = ["exact", "manual", "place"];

export const causeLabel = (c: string) => t(CAUSE_LABEL[c] ?? c);

export function floodFeatures(fc: FloodCollection | undefined, precise: boolean): FloodFeature[] {
  return (fc?.features ?? []).filter((f) => f.geometry && (!precise || PRECISE.includes(f.properties.located)));
}

export function floodBounds(f: FloodFeature): [number, number, number, number] | null {
  const g = f.geometry;
  if (!g) return null;
  const pts: number[][] = g.type === "Point" ? [g.coordinates] : g.type === "LineString" ? g.coordinates : g.coordinates.flat();
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

type Path = { f: FloodFeature; path: number[][] };

export function floodLayers(
  features: FloodFeature[],
  opts: { selected: string | null; onPick: (id: string) => void; three: boolean; extensions: unknown[]; colorKey?: string; colorOf?: (f: FloodFeature) => [number, number, number] | undefined },
) {
  const paths: Path[] = [];
  const points: FloodFeature[] = [];
  for (const f of features) {
    const g = f.geometry!;
    if (g.type === "Point") points.push(f);
    else if (g.type === "LineString") paths.push({ f, path: g.coordinates });
    else g.coordinates.forEach((c) => paths.push({ f, path: c }));
  }
  const sfx = `${opts.three ? "-3d" : ""}-${opts.colorKey ?? "cause"}`;  // a new colouring: new layers (no stale colours)
  const color = (f: FloodFeature): [number, number, number, number] => [
    ...(opts.colorOf?.(f) ?? CAUSE_COLOR[f.properties.cause ?? ""]),
    PRECISE.includes(f.properties.located) ? 235 : 140,
  ];
  const sel = (f: FloodFeature) => f.id === opts.selected;
  const ext = opts.extensions as never;
  return [
    new PathLayer<Path>({
      id: `flood-casing${sfx}`,
      extensions: ext,
      data: paths,
      getPath: (d) => d.path as never,
      getColor: (d) => (sel(d.f) ? [255, 209, 102, 255] : [255, 255, 255, 200]),
      getWidth: (d) => (sel(d.f) ? 11 : 8),
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      updateTriggers: { getColor: opts.selected, getWidth: opts.selected },
    }),
    new PathLayer<Path>({
      id: `flood-lines${sfx}`,
      extensions: ext,
      data: paths,
      getPath: (d) => d.path as never,
      getColor: (d) => color(d.f),
      getWidth: 5,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      pickable: true,
      onClick: ({ object }) => object && opts.onPick(object.f.id),
    }),
    new ScatterplotLayer<FloodFeature>({
      id: `flood-points${sfx}`,
      extensions: ext,
      data: points,
      getPosition: (f) => (f.geometry as { coordinates: number[] }).coordinates as [number, number],
      getRadius: (f) => (sel(f) ? 10 : 7),
      radiusUnits: "pixels",
      getFillColor: (f) => color(f),
      stroked: true,
      getLineColor: (f) => (sel(f) ? [255, 209, 102] : [255, 255, 255]),
      lineWidthMinPixels: 2,
      pickable: true,
      onClick: ({ object }) => object && opts.onPick(object.id),
      updateTriggers: { getRadius: opts.selected, getLineColor: opts.selected },
    }),
  ];
}

export const locatedLabel = (l: FloodLocated) =>
  ({
    exact: t("placed on the reported stretch or junction"),
    manual: t("placed by hand"),
    place: t("placed at the named place"),
    approx: t("approximate: whole street or one end only"),
    ambiguous: t("street name found in several places"),
    none: t("not found on the map"),
  })[l];

export function floodTooltip(f: FloodFeature, stats?: FloodStats): string {
  const p = f.properties;
  const s = stats?.rows[f.id];
  const lines = [p.text, `${causeLabel(p.cause)} · ${p.reported} · ${p.source}`, locatedLabel(p.located)];
  if (s?.n)
    lines.push(
      t("{n} points within {r} m: median {v} mm/yr", { n: fmt.int(s.n), r: stats!.radius_m, v: fmt.vel(s.vel_median!) }) +
        (s.ring_median != null ? ` (${t("around: {v}", { v: fmt.vel(s.ring_median) })})` : ""),
    );
  else if (stats) lines.push(t("no point of the product within {r} m", { r: stats.radius_m }));
  return lines.join("\n");
}
