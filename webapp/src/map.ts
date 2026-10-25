// What the Explorer and the map composer share: base maps, product layers (one binary array of points, or vector
// tiles for large products), velocity colours (QGIS Pretty Breaks classes from the API, jet_r).
import { COORDINATE_SYSTEM, type Layer } from "@deck.gl/core";
import { ClipExtension } from "@deck.gl/extensions";
import { MVTLayer } from "@deck.gl/geo-layers";
import { ScatterplotLayer, type ScatterplotLayerProps } from "@deck.gl/layers";
import type maplibregl from "maplibre-gl";
import { api, type LayerMeta, type VelClass } from "./api";
import type { MapLayer } from "./state";

export type Base = "dark" | "light" | "satellite" | "none";

export const BASES: Record<Exclude<Base, "none">, { label: string; tiles: string[]; attribution: string; maxzoom: number }> = {
  dark: {
    label: "Dark",
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
    maxzoom: 16,
  },
  light: {
    label: "Light",
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
    maxzoom: 16,
  },
  satellite: {
    label: "Satellite",
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    maxzoom: 19,
  },
};

export function mapStyle(base: Base, background = "#0b1220"): maplibregl.StyleSpecification {
  if (base === "none") return { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": background } }] };
  const b = BASES[base];
  return {
    version: 8,
    sources: { base: { type: "raster", tiles: b.tiles, tileSize: 256, attribution: b.attribution, maxzoom: b.maxzoom } },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": background } },
      { id: "base", type: "raster", source: "base", paint: base === "satellite" ? { "raster-saturation": -0.35, "raster-brightness-max": 0.8 } : {} },
    ],
  };
}

export type RenderMode = "auto" | "points" | "tiles";

export type LayerData =
  | { kind: "points"; meta: LayerMeta; buf: Float32Array; colors: Uint8Array }
  | { kind: "tiles"; meta: LayerMeta };

/** Class colour of a value (upper bounds inclusive, as QGIS). */
export function classColor(classes: VelClass[], v: number): [number, number, number] {
  let k = 0;
  while (k < classes.length - 1 && v > classes[k].hi) k++;
  return classes[k].color;
}

/** RGB per record of `buf` (records of `stride` floats, value at `at`) from the Pretty Breaks classes. */
export function colorize(buf: Float32Array, stride: number, at: number, classes: VelClass[]): Uint8Array {
  const n = Math.floor(buf.length / stride);
  const colors = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) {
    const c = classColor(classes, buf[i * stride + at]);
    colors[i * 3] = c[0];
    colors[i * 3 + 1] = c[1];
    colors[i * 3 + 2] = c[2];
  }
  return colors;
}

export async function loadLayer(project: string, product: string, mode: RenderMode = "auto"): Promise<LayerData> {
  const meta = await api.layer(project, product);
  if (mode === "tiles" || (mode === "auto" && meta.tiles.recommended)) {
    if (!meta.tiles.available) meta.tiles = { ...meta.tiles, ...(await api.buildTiles(project, product)) };
    return { kind: "tiles", meta };
  }
  const buf = await api.layerPoints(project, product);
  return { kind: "points", meta, buf, colors: colorize(buf, 3, 2, meta.classes) };
}

export const CLIP = new ClipExtension();

interface Feature {
  id?: number;
  properties: { v?: number; s?: number; c?: number };
}

/** deck.gl layer of a product; `clipLon`: [west, east] longitudes kept (swipe), `onPick`: product row index. */
export function productLayer(
  l: MapLayer,
  d: LayerData,
  o: {
    pickable?: boolean;
    onPick?: (index: number) => void;
    clipLon?: [number, number] | null;
    idPrefix?: string;
    pixelScale?: number;      // print export: screen-pixel sizes scaled to the export resolution
  } = {},
): Layer {
  const px = o.pixelScale ?? 1;
  // the kind in the id: deck.gl matches layers by id and would hand the state of a points layer to a tile layer
  const id = `${o.idPrefix ?? "pts-"}${l.key}#${d.kind}`;
  const common = {
    id,
    opacity: l.opacity,
    pickable: o.pickable ?? true,
    autoHighlight: o.pickable ?? true,
    highlightColor: [255, 255, 255, 255] as [number, number, number, number],
  };
  if (d.kind === "tiles") {
    const classes = d.meta.classes;
    return new MVTLayer({
      ...common,
      data: api.tileUrl(l.project, l.product),
      minZoom: d.meta.tiles.min_zoom ?? 0,
      maxZoom: d.meta.tiles.max_zoom ?? 14,
      binary: false,
      pointType: "circle",
      getFillColor: (f: Feature) => classColor(classes, f.properties.v ?? 0),
      getPointRadius: Math.max(1, d.meta.marker_m / 2),
      pointRadiusUnits: "meters",
      pointRadiusMinPixels: 1.1 * px,
      pointRadiusMaxPixels: 9 * px,
      stroked: false,
      updateTriggers: { getFillColor: classes },
      onClick: (info: { object?: Feature }) => {
        const fid = info.object?.id;
        if (fid != null && o.onPick) o.onPick(Number(fid));
      },
      ...(o.clipLon ? { extensions: [CLIP], clipBounds: [o.clipLon[0], -90, o.clipLon[1], 90] } : {}),
    } as never) as unknown as Layer;
  }
  const origin = d.meta.origin;
  const props: ScatterplotLayerProps = {
    ...common,
    data: {
      length: d.meta.n,
      attributes: {
        getPosition: { value: d.buf, size: 2, stride: 12, offset: 0 },
        getFillColor: { value: d.colors, size: 3, normalized: true },
      },
    } as unknown as ScatterplotLayerProps["data"],
    coordinateSystem: COORDINATE_SYSTEM.LNGLAT_OFFSETS,
    coordinateOrigin: [origin[0], origin[1], 0],
    radiusUnits: "meters",
    getRadius: Math.max(1, d.meta.marker_m / 2),
    radiusMinPixels: 1.1 * px,
    radiusMaxPixels: 9 * px,
    stroked: false,
    onClick: (info) => {
      if (info.index >= 0 && o.onPick) o.onPick(info.index);
    },
    ...(o.clipLon
      ? { extensions: [CLIP], clipBounds: [o.clipLon[0] - origin[0], -1e3, o.clipLon[1] - origin[0], 1e3] }
      : {}),
  };
  return new ScatterplotLayer(props) as unknown as Layer;
}

/** Velocity under the cursor of a picked product layer (tooltip), whatever its kind. */
export function pickedVelocity(d: LayerData, index: number, object: unknown): number | null {
  if (d.kind === "tiles") return (object as Feature | undefined)?.properties?.v ?? null;
  return index >= 0 ? d.buf[index * 3 + 2] : null;
}
