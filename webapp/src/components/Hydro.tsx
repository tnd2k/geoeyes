// River network (OpenStreetMap waterways) and watersheds (HydroBASINS level 12) under the products, for reading
// floods and subsidence against the drainage: fetched for the current view (snapped on the server, cached there).
import { PathLayer, SolidPolygonLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import type maplibregl from "maplibre-gl";
import { useEffect, useState, type RefObject } from "react";
import { api, type HydroFeature } from "../api";
import { t } from "../i18n";
import { TERRAIN_TILES } from "../map";

const RIVER: Record<string, { w: number; c: [number, number, number] }> = {
  river: { w: 3.2, c: [29, 110, 214] },
  canal: { w: 2.6, c: [37, 140, 230] },
  tidal_channel: { w: 2.2, c: [37, 140, 230] },
  stream: { w: 1.6, c: [70, 160, 235] },
  drain: { w: 1.1, c: [96, 175, 240] },
  ditch: { w: 1.0, c: [96, 175, 240] },
};
const KIND_LABEL: Record<string, string> = {
  river: "river",
  canal: "canal",
  tidal_channel: "tidal channel",
  stream: "stream",
  drain: "drain",
  ditch: "ditch",
};
const BASIN_LINE: [number, number, number, number] = [92, 62, 170, 230];
// soft categorical fills, one per watershed (by its id), so the basins read apart over the relief
const BASIN_COLORS: [number, number, number][] = [
  [141, 211, 199], [190, 186, 218], [251, 128, 114], [128, 177, 211], [253, 180, 98], [179, 222, 105],
  [252, 205, 229], [188, 128, 189], [204, 235, 197], [255, 237, 111],
];
const basinColor = (f: HydroFeature): [number, number, number, number] => [...BASIN_COLORS[(f.properties.hybas_id ?? 0) % BASIN_COLORS.length], 70];
const MAX_SPAN = 6; // degrees: the server refuses larger views
export const HYDRO_CREDIT = "Rivers: OpenStreetMap (ODbL) · Watersheds: HydroBASINS (Lehner & Grill 2013) · Relief: Mapzen Terrain Tiles";
const DEM_SRC = "hydro-dem";
const SHADE = "hydro-hillshade";

/** Relief (hillshade of the Terrarium elevation tiles, as the 3D view) under the watersheds while ``on``; added
 * again after a base-map change (a new style drops it), below the first label layer. */
function useHillshade(map: RefObject<maplibregl.Map | null>, ready: boolean, on: boolean) {
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const add = () => {
      if (!on || !m.isStyleLoaded() || m.getLayer(SHADE)) return;
      if (!m.getSource(DEM_SRC))
        m.addSource(DEM_SRC, { type: "raster-dem", tiles: [TERRAIN_TILES], tileSize: 256, maxzoom: 14, encoding: "terrarium" });
      const label = m.getStyle().layers?.find((l) => l.type === "symbol")?.id;
      m.addLayer(
        { id: SHADE, type: "hillshade", source: DEM_SRC, paint: { "hillshade-exaggeration": 0.55, "hillshade-shadow-color": "#3b3b52", "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#5a5a70" } },
        label,
      );
    };
    const remove = () => {
      if (m.getLayer(SHADE)) m.removeLayer(SHADE);
      if (m.getSource(DEM_SRC)) m.removeSource(DEM_SRC);
    };
    if (on) {
      add();
      m.on("styledata", add);
      return () => {
        m.off("styledata", add);
        try {
          remove();
        } catch {
          /* map already removed */
        }
      };
    }
    try {
      remove();
    } catch {
      /* style not loaded */
    }
  }, [map, ready, on]);
}

/** The view's bounds (w, s, e, n) while ``on``, updated after every move; null when off or too large. */
function useViewBounds(map: RefObject<maplibregl.Map | null>, ready: boolean, on: boolean) {
  const [b, setB] = useState<number[] | null>(null);
  useEffect(() => {
    const m = map.current;
    if (!m || !on) return;
    const upd = () => {
      const x = m.getBounds();
      const v = [x.getWest(), x.getSouth(), x.getEast(), x.getNorth()];
      // a bit wider than the view, snapped to 0.05° (the server's cache cells): small pans ask nothing new
      const pad = Math.min(0.1, (v[2] - v[0]) * 0.1);
      const s = (x: number, up: boolean) => (up ? Math.ceil(x * 20) : Math.floor(x * 20)) / 20;
      setB([s(v[0] - pad, false), s(v[1] - pad, false), s(v[2] + pad, true), s(v[3] + pad, true)]);
    };
    upd();
    m.on("moveend", upd);
    return () => void m.off("moveend", upd);
  }, [map, ready, on]);
  if (!on || !b || b[2] - b[0] > MAX_SPAN || b[3] - b[1] > MAX_SPAN) return null;
  return b;
}

export function useHydro(map: RefObject<maplibregl.Map | null>, ready: boolean, on: boolean) {
  const bbox = useViewBounds(map, ready, on);
  useHillshade(map, ready, on);
  const key = bbox?.join(",");
  const rivers = useQuery({ queryKey: ["hydroRivers", key], queryFn: () => api.hydroRivers(bbox!), enabled: !!bbox, staleTime: Infinity, retry: 1 });
  const basins = useQuery({ queryKey: ["hydroBasins", key], queryFn: () => api.hydroBasins(bbox!), enabled: !!bbox, staleTime: Infinity, retry: 1 });
  const tooWide = on && !bbox;
  return { rivers: rivers.data, basins: basins.data, loading: rivers.isFetching || basins.isFetching, error: (rivers.error ?? basins.error) as Error | null, tooWide };
}

type Ring = { f: HydroFeature; path: number[][] };

/** Deck layers: watershed fill and outlines, then the rivers (widths by kind, a light casing under them).
 * ``pixelScale``: line widths for an export at print resolution (Compose); ``idPrefix``: distinct layer ids there. */
export function hydroLayers(
  rivers: HydroFeature[],
  basins: HydroFeature[],
  opts: { three: boolean; extensions: unknown[]; pixelScale?: number; idPrefix?: string },
) {
  const sfx = opts.three ? "-3d" : "";
  const k = opts.pixelScale ?? 1;
  const id = (name: string) => `${opts.idPrefix ?? ""}hydro-${name}${sfx}`;
  const ext = opts.extensions as never;
  const polys: { f: HydroFeature; polygon: number[][][] }[] = [];
  const rings: Ring[] = [];
  for (const f of basins) {
    const g = f.geometry;
    const parts = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
    for (const p of parts) {
      polys.push({ f, polygon: p });
      p.forEach((r) => rings.push({ f, path: r }));
    }
  }
  const lines = rivers.filter((f) => f.geometry.type === "LineString").map((f) => ({ f, path: f.geometry.coordinates as number[][] }));
  const style = (f: HydroFeature) => RIVER[f.properties.kind ?? ""] ?? RIVER.stream;
  return [
    new SolidPolygonLayer<{ f: HydroFeature; polygon: number[][][] }>({
      id: id("basin-fill"),
      extensions: ext,
      data: polys,
      getPolygon: (d) => d.polygon as never,
      getFillColor: (d) => basinColor(d.f),
      pickable: !opts.idPrefix,
    }),
    new PathLayer<Ring>({
      id: id("basin-line"),
      extensions: ext,
      data: rings,
      getPath: (d) => d.path as never,
      getColor: BASIN_LINE,
      getWidth: 2 * k,
      widthUnits: "pixels",
      jointRounded: true,
    }),
    new PathLayer<Ring>({
      id: id("river-casing"),
      extensions: ext,
      data: lines,
      getPath: (d) => d.path as never,
      getColor: [255, 255, 255, 150],
      getWidth: (d) => (style(d.f).w + 1.6) * k,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      updateTriggers: { getWidth: k },
    }),
    new PathLayer<Ring>({
      id: id("river"),
      extensions: ext,
      data: lines,
      getPath: (d) => d.path as never,
      getColor: (d) => [...style(d.f).c, 235],
      getWidth: (d) => style(d.f).w * k,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      pickable: !opts.idPrefix,
      updateTriggers: { getWidth: k },
    }),
  ];
}

export function hydroTooltip(layerId: string, object: unknown): string | null {
  const f = (object as { f?: HydroFeature } | null)?.f;
  if (!f) return null;
  const p = f.properties;
  if (layerId.startsWith("hydro-river")) return [p.name || t("(unnamed)"), t(KIND_LABEL[p.kind ?? ""] ?? p.kind ?? "")].join(" · ");
  if (layerId.startsWith("hydro-basin"))
    return `${t("Watershed")} ${p.hybas_id}\n${t("{a} km² · upstream {u} km²", { a: Math.round(p.area_km2 ?? 0), u: Math.round(p.up_area_km2 ?? 0) })}${p.coast ? `\n${t("coastal")}` : ""}`;
  return null;
}
