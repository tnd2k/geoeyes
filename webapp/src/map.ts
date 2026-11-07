// What the Explorer and the map composer share: base maps, product layers (one binary array of points, or vector
// tiles for large products), velocity colours (QGIS Pretty Breaks classes from the API, jet_r).
import { COORDINATE_SYSTEM, type Layer } from "@deck.gl/core";
import { _TerrainExtension as TerrainExtension, ClipExtension, DataFilterExtension } from "@deck.gl/extensions";
import { MVTLayer, TerrainLayer } from "@deck.gl/geo-layers";
import { ColumnLayer, ScatterplotLayer, type ScatterplotLayerProps } from "@deck.gl/layers";
import type maplibregl from "maplibre-gl";
import { api, type LayerMeta, type VelClass, type VelKind } from "./api";
import { rangeClasses } from "./classes";
import type { MapLayer } from "./state";
import { themeColor } from "./theme";

// deck.gl compares a layer's `data` by identity: a new `{length, attributes}` object at each rebuild of the layer list
// (zoom, hover, swipe) made it upload every point buffer to the GPU again. One object per pair of source arrays.
const BINARY = new WeakMap<object, WeakMap<object, unknown>>();
export function binaryData<T>(a: object, b: object, make: () => T): T {
  let inner = BINARY.get(a);
  if (!inner) BINARY.set(a, (inner = new WeakMap()));
  let v = inner.get(b) as T | undefined;
  if (v === undefined) inner.set(b, (v = make()));
  return v;
}

export type Base = "dark" | "light" | "satellite" | "none";

/** Base map a map opens with (light gray canvas: the points and footprints read best on it). */
export const DEFAULT_BASE: Exclude<Base, "none"> = "light";

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

export function mapStyle(base: Base, background = themeColor("bg")): maplibregl.StyleSpecification {
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

/** Raster source + layer of a base map, for pages that build their own style around it (source / layer id "base"). */
export function baseSource(base: Exclude<Base, "none">): maplibregl.RasterSourceSpecification {
  const b = BASES[base];
  return { type: "raster", tiles: b.tiles, tileSize: 256, attribution: b.attribution, maxzoom: b.maxzoom };
}

/** Switch the "base" source of such a style to another base map, keeping the page's own layers. */
export function switchBase(m: maplibregl.Map, base: Base) {
  const src = m.getSource("base") as maplibregl.RasterTileSource | undefined;
  if (!src || !m.getLayer("base")) return;
  m.setLayoutProperty("base", "visibility", base === "none" ? "none" : "visible");
  if (base === "none") return;
  src.setTiles(BASES[base].tiles);
  m.setPaintProperty("base", "raster-saturation", base === "satellite" ? -0.35 : 0);
  m.setPaintProperty("base", "raster-brightness-max", base === "satellite" ? 0.8 : 1);
}

export type RenderMode = "auto" | "points" | "tiles";

export type LayerData =
  | { kind: "points"; meta: LayerMeta; buf: Float32Array; colors: Uint8Array; coh?: Float32Array }
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

/** RGB per point of a displacement frame (int16 in 1/scale mm, −32768 = none: dark grey). */
export function colorizeFrame(frame: Int16Array, scale: number, classes: VelClass[]): Uint8Array {
  const colors = new Uint8Array(frame.length * 3);
  for (let i = 0; i < frame.length; i++) {
    const c = frame[i] === -32768 ? [40, 48, 64] : classColor(classes, frame[i] / scale);
    colors[i * 3] = c[0];
    colors[i * 3 + 1] = c[1];
    colors[i * 3 + 2] = c[2];
  }
  return colors;
}

// ------------------------------------------------------------------ lines on the map (profiles)
const M_LAT = 110_540;
const mLon = (lat: number) => 111_320 * Math.cos((lat * Math.PI) / 180);

/** Length (m) of each segment of a polyline [[lon, lat], ...]. */
export function segmentLengths(line: [number, number][]): number[] {
  return line.slice(1).map((b, i) => {
    const a = line[i];
    return Math.hypot((b[0] - a[0]) * mLon((a[1] + b[1]) / 2), (b[1] - a[1]) * M_LAT);
  });
}

/** The position at distance `d` (m) along a polyline. */
export function pointAlong(line: [number, number][], d: number): [number, number] {
  const L = segmentLengths(line);
  let rest = Math.max(0, d);
  for (let i = 0; i < L.length; i++) {
    if (rest <= L[i] || i === L.length - 1) {
      const f = L[i] ? Math.min(1, rest / L[i]) : 0;
      return [line[i][0] + f * (line[i + 1][0] - line[i][0]), line[i][1] + f * (line[i + 1][1] - line[i][1])];
    }
    rest -= L[i];
  }
  return line[0];
}

const terrainTiles = new Map<string, Promise<ImageData | null>>();

function terrainTile(z: number, x: number, y: number): Promise<ImageData | null> {
  const key = `${z}/${x}/${y}`;
  let p = terrainTiles.get(key);
  if (!p) {
    p = fetch(TERRAIN_TILES.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y)))
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(r.statusText))))
      .then((b) => createImageBitmap(b))
      .then((img) => {
        const c = new OffscreenCanvas(img.width, img.height);
        const ctx = c.getContext("2d")!;
        ctx.drawImage(img, 0, 0);
        return ctx.getImageData(0, 0, img.width, img.height);
      })
      .catch(() => null);
    terrainTiles.set(key, p);
  }
  return p;
}

/** Ground height (m, Terrarium tiles at `zoom`) every `step` m along a polyline: [distance m, height m | null][]. */
export async function terrainProfile(line: [number, number][], step: number, zoom = 14): Promise<[number, number | null][]> {
  const total = segmentLengths(line).reduce((a, b) => a + b, 0);
  const n = Math.max(2, Math.min(2000, Math.ceil(total / step) + 1));
  const out: [number, number | null][] = [];
  const N = 2 ** zoom;
  for (let k = 0; k < n; k++) {
    const d = (total * k) / (n - 1);
    const [lon, lat] = pointAlong(line, d);
    const fx = ((lon + 180) / 360) * N;
    const r = (lat * Math.PI) / 180;
    const fy = ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * N;
    const img = await terrainTile(zoom, Math.floor(fx), Math.floor(fy));
    if (!img) {
      out.push([d, null]);
      continue;
    }
    const px = Math.min(img.width - 1, Math.floor((fx % 1) * img.width));
    const py = Math.min(img.height - 1, Math.floor((fy % 1) * img.height));
    const o = (py * img.width + px) * 4;
    out.push([d, img.data[o] * 256 + img.data[o + 1] + img.data[o + 2] / 256 - 32768]);
  }
  return out;
}

/** `cal`: the calibrated velocities (GNSS, else a tie to another product), always as points (the tiles hold the
 * product's own velocities). */
export const DEFAULT_VEL: VelKind = "do";

/** `vel`: a velocity kind, null for the product velocity, undefined for the default (v-do when the product carries
 * it, else the product velocity). */
export async function loadLayer(project: string, product: string, mode: RenderMode = "auto", cal = false, vel?: VelKind | null): Promise<LayerData> {
  let view = { cal, vel: vel === undefined ? DEFAULT_VEL : vel };
  let meta: LayerMeta;
  try {
    meta = await api.layer(project, product, view);
  } catch (e) {
    if (vel !== undefined) throw e;
    // the product has no v-do (SBAS, ps_lite, an older ps run): its own velocity
    view = { cal, vel: null };
    meta = await api.layer(project, product, view);
  }
  // v-do is the product velocity itself: the product's own layer (tiles possible, no second cache)
  if (view.vel && view.vel === meta.product_kind) {
    view = { cal, vel: null };
    meta = await api.layer(project, product, view);
  }
  vel = view.vel;
  // the tiles hold the product velocity: another kind is always read as points
  if (!cal && !vel && (mode === "tiles" || (mode === "auto" && meta.tiles.recommended))) {
    if (!meta.tiles.available) meta.tiles = { ...meta.tiles, ...(await api.buildTiles(project, product)) };
    return { kind: "tiles", meta };
  }
  const [buf, coh] = await Promise.all([
    api.layerPoints(project, product, view),
    api.layerCoherence(project, product, view).catch(() => undefined),   // an older server: no slider
  ]);
  return { kind: "points", meta, buf, colors: colorize(buf, 3, 2, meta.classes), coh };
}

const ranged = new WeakMap<LayerData, Map<string, LayerData>>();

/** The layer with the classes over a range the user chose ([lo, hi] mm/yr; points beyond take the end colours), or
 * as it is (`range` null: the product's full min-max). Cached: the same object for the same data and range. */
export function withRange(d: LayerData, range: [number, number] | null | undefined): LayerData {
  if (!range || !(range[1] > range[0])) return d;
  let m = ranged.get(d);
  if (!m) ranged.set(d, (m = new Map()));
  const key = `${range[0]}|${range[1]}`;
  let r = m.get(key);
  if (!r) {
    const classes = rangeClasses(range[0], range[1], d.kind === "points" ? { buf: d.buf, stride: 3, at: 2 } : undefined);
    const meta = { ...d.meta, classes, range };
    r = d.kind === "points" ? { ...d, meta, colors: colorize(d.buf, 3, 2, classes) } : { ...d, meta };
    m.clear(); // one chosen range at a time per layer
    m.set(key, r);
  }
  return r;
}

export const CLIP = new ClipExtension();
export const TERRAIN = new TerrainExtension();
// the coherence slider: points below the threshold are dropped on the GPU (no reload, no new buffers)
export const COH_FILTER = new DataFilterExtension({ filterSize: 1 });

const COH_VALUES = new WeakMap<Float32Array, Float32Array>();
/** The coherence per point as the filter reads it: NaN (no coherence) → −1, below any threshold. */
function cohValues(c: Float32Array): Float32Array {
  let v = COH_VALUES.get(c);
  if (!v) {
    v = new Float32Array(c.length);
    for (let i = 0; i < c.length; i++) v[i] = Number.isNaN(c[i]) ? -1 : c[i];
    COH_VALUES.set(c, v);
  }
  return v;
}

// 3D view: open elevation tiles (Mapzen Terrain Tiles on AWS Open Data, Terrarium encoding, ~30 m at zoom 12+)
export const TERRAIN_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
export const TERRAIN_ATTRIBUTION = "Terrain: Mapzen Terrain Tiles, AWS Open Data";

/** deck.gl terrain draped with the base map (the other deck layers sit on it with `TERRAIN`); `exaggeration` × the
 * true heights, so that flat deltas show their relief. */
export function terrainLayer(base: Base, exaggeration: number): Layer {
  const e = exaggeration;
  return new TerrainLayer({
    id: `terrain-${base}`,
    minZoom: 0,
    maxZoom: 15,
    elevationData: TERRAIN_TILES,
    texture: base === "none" ? null : BASES[base].tiles[0],
    elevationDecoder: { rScaler: 256 * e, gScaler: e, bScaler: e / 256, offset: -32768 * e },
    // in exaggerated metres: ~1.5 m of true height whatever the exaggeration (fewer triangles at ×5-×20)
    meshMaxError: Math.max(2, 1.5 * e),
    color: [26, 36, 56],
    operation: "terrain+draw",
    updateTriggers: { elevationDecoder: e },
  } as never) as unknown as Layer;
}

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
    terrain?: boolean;        // 3D view: on the terrain of `terrainLayer`
    colors?: Uint8Array;      // points: colours in place of the velocity classes (time animation)
  } = {},
): Layer {
  const px = o.pixelScale ?? 1;
  // the kind in the id: deck.gl matches layers by id and would hand the state of a points layer to a tile layer
  const id = `${o.idPrefix ?? "pts-"}${l.key}#${d.kind}${o.terrain ? "-3d" : ""}`;
  const cohMin = l.cohMin ?? 0;
  const cohOn = cohMin > 0 && (d.kind === "tiles" || !!d.coh);
  const ext = [...(o.clipLon ? [CLIP] : []), ...(o.terrain ? [TERRAIN] : []), ...(cohOn ? [COH_FILTER] : [])];
  // a point without a coherence (NaN; -1 in the filter) is hidden as soon as a threshold is set
  const filter = cohOn ? { filterRange: [cohMin, 1.01] as [number, number] } : {};
  const common = {
    id,
    opacity: l.opacity,
    pickable: o.pickable ?? true,
    autoHighlight: o.pickable ?? true,
    highlightColor: [255, 255, 255, 255] as [number, number, number, number],
    // 3D: the points drawn into the terrain's own texture ("drape"), not raised to its height ("offset", the default
    // of point layers): the terrain tiles overlap by a pixel and, on steep slopes, the higher edge hid a strip of
    // raised points along every tile border; draped, they are also not drawn again at every frame of a move
    // (no hover highlight there: every redraw of a draped layer draws it again into the cover of every terrain tile)
    ...(o.terrain ? { terrainDrawMode: "drape", autoHighlight: false } : {}),
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
      ...(cohOn ? { getFilterValue: (f: Feature) => f.properties.c ?? -1, ...filter } : {}),
      updateTriggers: { getFillColor: classes },
      onClick: (info: { object?: Feature }) => {
        const fid = info.object?.id;
        if (fid != null && o.onPick) o.onPick(Number(fid));
      },
      extensions: ext,
      ...(o.clipLon ? { clipBounds: [o.clipLon[0], -90, o.clipLon[1], 90] } : {}),
    } as never) as unknown as Layer;
  }
  const origin = d.meta.origin;
  const props: ScatterplotLayerProps = {
    ...common,
    data: (cohOn
      ? binaryData(o.colors ?? d.colors, d.coh!, () => ({
          length: d.meta.n,
          attributes: {
            getPosition: { value: d.buf, size: 2, stride: 12, offset: 0 },
            getFillColor: { value: o.colors ?? d.colors, size: 3, normalized: true },
            getFilterValue: { value: cohValues(d.coh!), size: 1 },
          },
        }))
      : binaryData(d.buf, o.colors ?? d.colors, () => ({
          length: d.meta.n,
          attributes: {
            getPosition: { value: d.buf, size: 2, stride: 12, offset: 0 },
            getFillColor: { value: o.colors ?? d.colors, size: 3, normalized: true },
          },
        }))) as unknown as ScatterplotLayerProps["data"],
    ...filter,
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
    extensions: ext,
    ...(o.clipLon ? { clipBounds: [o.clipLon[0] - origin[0], -1e3, o.clipLon[1] - origin[0], 1e3] } : {}),
  };
  return new ScatterplotLayer(props) as unknown as Layer;
}

// zoomed out, a product is drawn as hexagons of the median velocity (binned on the server, `hexbins`); zoomed in, as
// its points. The level aims at hexagons about HEX_PX screen pixels wide; below POINTS_BELOW_M the points are shown.
export const HEX_PX = 11;
export const POINTS_BELOW_M = 100;

/** Hexagon size (m, centre to vertex) for a zoom at a latitude, or null: show the points. */
export function hexSize(sizes: number[] | undefined, zoom: number, lat: number): number | null {
  if (!sizes?.length) return null;
  const mpp = (156_543.03 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
  const target = HEX_PX * mpp;
  if (target < POINTS_BELOW_M) return null;
  return sizes.find((s) => s >= target) ?? sizes[sizes.length - 1];
}

/** deck.gl hexagons of a product: `buf` from `api.layerHex` (dlon, dlat, median, count per hexagon). */
export function hexLayer(l: MapLayer, meta: LayerMeta, buf: Float32Array, size: number, o: { onPick?: (lon: number, lat: number) => void; terrain?: boolean } = {}): Layer {
  const n = Math.floor(buf.length / 4);
  return new ColumnLayer({
    id: `hex-${l.key}-${size}${o.terrain ? "-3d" : ""}`,
    ...(o.terrain ? { extensions: [TERRAIN], terrainDrawMode: "drape" } : {}),   // 3D: on the terrain, not under it
    // cached: the colours were also computed again over every hexagon at each rebuild
    data: binaryData(buf, meta.classes, () => ({ length: n, attributes: { getPosition: { value: buf, size: 2, stride: 16, offset: 0 }, getFillColor: { value: colorize(buf, 4, 2, meta.classes), size: 3, normalized: true } } })) as never,
    coordinateSystem: COORDINATE_SYSTEM.LNGLAT_OFFSETS,
    coordinateOrigin: [meta.origin[0], meta.origin[1], 0],
    diskResolution: 6,
    angle: 0, // flat-top (a vertex east), as the server's bins
    radius: size,
    coverage: 0.94,
    extruded: false,
    opacity: l.opacity * 0.5, // the hexagons cover the base map: lighter than the points, roads and rivers show through
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 110],
    onClick: (info: { index: number }) => {
      if (info.index >= 0 && o.onPick) o.onPick(meta.origin[0] + buf[info.index * 4], meta.origin[1] + buf[info.index * 4 + 1]);
    },
  } as never) as unknown as Layer;
}

/** Velocity under the cursor of a picked product layer (tooltip), whatever its kind. */
export function pickedVelocity(d: LayerData, index: number, object: unknown): number | null {
  if (d.kind === "tiles") return (object as Feature | undefined)?.properties?.v ?? null;
  return index >= 0 ? d.buf[index * 3 + 2] : null;
}
