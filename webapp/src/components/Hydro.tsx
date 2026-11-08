// River network (OpenStreetMap waterways) and watersheds (HydroBASINS level 12) under the products, for reading
// floods and subsidence against the drainage: fetched for the current view (snapped on the server, cached there).
import { PathLayer, SolidPolygonLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import type maplibregl from "maplibre-gl";
import { useEffect, useState, type RefObject } from "react";
import { api, type HydroFeature } from "../api";
import { t } from "../i18n";

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
const BASIN_LINE: [number, number, number, number] = [124, 92, 214, 210];
const BASIN_FILL: [number, number, number, number] = [124, 92, 214, 16];
const MAX_SPAN = 6; // degrees: the server refuses larger views
export const HYDRO_CREDIT = "Rivers: OpenStreetMap (ODbL) · Watersheds: HydroBASINS (Lehner & Grill 2013)";

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
      getFillColor: BASIN_FILL,
      pickable: !opts.idPrefix,
    }),
    new PathLayer<Ring>({
      id: id("basin-line"),
      extensions: ext,
      data: rings,
      getPath: (d) => d.path as never,
      getColor: BASIN_LINE,
      getWidth: 1.6 * k,
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
