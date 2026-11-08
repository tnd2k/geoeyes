// App state shared by the tree, the map and the pages: the route (hash) and the map layers (like QGIS layers).
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { VelKind } from "./api";

export type Route =
  | { page: "overview" }
  | { page: "explorer" }
  | { page: "new" }
  | { page: "compose" }
  | { page: "opendata" }
  | { page: "coop" }
  | { page: "hazard"; name?: string; product?: string; cell?: number; view?: string }
  | { page: "ai"; name?: string; product?: string; tab?: string }
  | { page: "learn"; name?: string; stack?: string; step?: number; chapter?: "hazard" | "behaviour" | "lines" | "geometry" | "ionosphere" }
  | { page: "project"; name: string; tab?: string };

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "explorer") return { page: "explorer" };
  if (parts[0] === "new") return { page: "new" };
  if (parts[0] === "compose") return { page: "compose" };
  if (parts[0] === "opendata") return { page: "opendata" };
  if (parts[0] === "coop") return { page: "coop" };
  if (["learn-hazard", "learn-behaviour", "learn-lines", "learn-geometry", "learn-ionosphere"].includes(parts[0]))
    return { page: "learn", chapter: parts[0].slice(6) as "hazard" | "behaviour" | "lines" | "geometry" | "ionosphere", step: parts[1] ? Number(parts[1]) : undefined };
  if (parts[0] === "learn")
    return { page: "learn", name: parts[1] || undefined, stack: parts[2] || undefined, step: parts[3] ? Number(parts[3]) : undefined };
  if (parts[0] === "ai") return { page: "ai", name: parts[1] || undefined, product: parts[2] || undefined, tab: parts[3] || undefined };
  if (parts[0] === "hazard") {
    // #/hazard/<project>/<product>[/<layer>][/<cell>]
    const rest = parts.slice(3).filter(Boolean);
    const num = rest.find((p) => /^\d+$/.test(p));
    const view = rest.find((p) => !/^\d+$/.test(p));
    return { page: "hazard", name: parts[1] || undefined, product: parts[2] || undefined, cell: num != null ? Number(num) : undefined, view };
  }
  if (parts[0] === "project" && parts[1]) return { page: "project", name: parts[1], tab: parts[2] };
  return { page: "overview" };
}

export function href(r: Route): string {
  if (r.page === "explorer") return "#/explorer";
  if (r.page === "new") return "#/new";
  if (r.page === "compose") return "#/compose";
  if (r.page === "opendata") return "#/opendata";
  if (r.page === "coop") return "#/coop";
  if (r.page === "learn" && r.chapter) return `#/learn-${r.chapter}${r.step != null ? `/${r.step}` : ""}`;
  if (r.page === "learn")
    return r.name
      ? `#/learn/${encodeURIComponent(r.name)}${r.stack ? `/${encodeURIComponent(r.stack)}${r.step != null ? `/${r.step}` : ""}` : ""}`
      : "#/learn";
  if (r.page === "ai")
    return r.name && r.product ? `#/ai/${encodeURIComponent(r.name)}/${encodeURIComponent(r.product)}${r.tab ? `/${r.tab}` : ""}` : "#/ai";
  if (r.page === "hazard")
    return r.name && r.product
      ? `#/hazard/${encodeURIComponent(r.name)}/${encodeURIComponent(r.product)}${r.view ? `/${r.view}` : ""}${r.cell != null ? `/${r.cell}` : ""}`
      : "#/hazard";
  if (r.page === "project") return `#/project/${encodeURIComponent(r.name)}${r.tab ? `/${r.tab}` : ""}`;
  return "#/";
}

export interface MapLayer {
  key: string;            // `${project}/${product}`
  project: string;
  product: string;
  visible: boolean;
  opacity: number;
  mode?: "auto" | "points" | "tiles";   // points: one binary array; tiles: PMTiles (auto: tiles above 2.5 M points)
  calibrated?: boolean;                 // the calibrated velocities and series (GNSS, else a tie; points only)
  range?: [number, number] | null;      // colour classes over this range (mm/yr) in place of the full min-max
  vel?: VelKind | null;                 // a StaMPS velocity kind in place of the product velocity (points only)
  cohMin?: number;                      // points below this temporal coherence are hidden (0 / unset: all shown)
}

export interface Selection {
  layer: string;          // MapLayer.key
  index: number;
}

interface AppState {
  route: Route;
  go: (r: Route) => void;
  layers: MapLayer[];
  showProduct: (project: string, product: string, opts?: { solo?: boolean; open?: boolean }) => void;
  toggleLayer: (key: string) => void;
  setOpacity: (key: string, opacity: number) => void;
  setMode: (key: string, mode: MapLayer["mode"]) => void;
  setCalibrated: (key: string, on: boolean) => void;
  setRange: (key: string, range: [number, number] | null) => void;
  setVel: (key: string, vel: VelKind | null) => void;
  setCohMin: (key: string, cohMin: number) => void;
  removeLayer: (key: string) => void;
  fixedRange: Record<string, boolean>;  // per project: every product's colours over ±FIXED_RANGE (comparable)
  setFixedRange: (project: string, on: boolean) => void;
  focus: string | null;   // layer to zoom to
  setFocus: (key: string | null) => void;
  selection: Selection | null;
  select: (s: Selection | null) => void;
}

const Ctx = createContext<AppState | null>(null);

const STORE = "geoeyes.layers";
const FIXED_STORE = "geoeyes.fixedRange";

/** The fixed colour range of a project (mm/yr): the same classes and colours for all its products and runs. */
export const FIXED_RANGE = 30;

/** The colour range a layer is drawn with: one chosen on its card, else the project's fixed ±30, else none (the
 * product's own min–max). */
export function layerRange(l: Pick<MapLayer, "project" | "range">, fixed: Record<string, boolean>): [number, number] | null {
  return l.range ?? (fixed[l.project] ? [-FIXED_RANGE, FIXED_RANGE] : null);
}

function loadFixed(): Record<string, boolean> {
  try {
    const v = JSON.parse(localStorage.getItem(FIXED_STORE) ?? "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch {
    return {};
  }
}

function loadLayers(): MapLayer[] {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) ?? "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  const [layers, setLayers] = useState<MapLayer[]>(loadLayers);
  const [focus, setFocus] = useState<string | null>(null);
  const [selection, select] = useState<Selection | null>(null);
  const [fixedRange, setFixed] = useState<Record<string, boolean>>(loadFixed);
  useEffect(() => {
    try {
      localStorage.setItem(FIXED_STORE, JSON.stringify(fixedRange));
    } catch {
      /* storage unavailable */
    }
  }, [fixedRange]);
  const setFixedRange = useCallback((project: string, on: boolean) => {
    setFixed((f) => ({ ...f, [project]: on }));
    // switched on: the project's range wins over ranges typed on its layer cards
    if (on) setLayers((ls) => ls.map((l) => (l.project === project && l.range ? { ...l, range: null } : l)));
  }, []);

  useEffect(() => {
    // #/map/<project>/<product>: link that shows a product on the map
    const on = () => {
      const m = location.hash.match(/^#\/map\/([^/]+)\/([^/]+)$/);
      if (m) showProduct(decodeURIComponent(m[1]), decodeURIComponent(m[2]), { open: true });
      else setRoute(parse(location.hash));
    };
    on();
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(layers));
    } catch {
      /* storage unavailable */
    }
  }, [layers]);

  const go = useCallback((r: Route) => {
    location.hash = href(r);
  }, []);

  const showProduct = useCallback(
    (project: string, product: string, opts: { solo?: boolean; open?: boolean } = {}) => {
      const key = `${project}/${product}`;
      setLayers((ls) => {
        const rest = ls.filter((l) => l.key !== key).map((l) => (opts.solo ? { ...l, visible: false } : l));
        const old = ls.find((l) => l.key === key);
        return [{ key, project, product, visible: true, opacity: old?.opacity ?? 1, mode: old?.mode, range: old?.range, vel: old?.vel, cohMin: old?.cohMin }, ...rest];
      });
      setFocus(key);
      if (opts.open) location.hash = href({ page: "explorer" });
    },
    [],
  );

  const value = useMemo<AppState>(
    () => ({
      route,
      go,
      layers,
      showProduct,
      toggleLayer: (key) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, visible: !l.visible } : l))),
      setOpacity: (key, opacity) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, opacity } : l))),
      setMode: (key, mode) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, mode } : l))),
      setCalibrated: (key, on) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, calibrated: on } : l))),
      setRange: (key, range) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, range } : l))),
      // another velocity: another min-max, the chosen colour range no longer fits it
      setVel: (key, vel) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, vel, range: null } : l))),
      setCohMin: (key, cohMin) => setLayers((ls) => ls.map((l) => (l.key === key ? { ...l, cohMin } : l))),
      removeLayer: (key) => {
        setLayers((ls) => ls.filter((l) => l.key !== key));
        select((s) => (s?.layer === key ? null : s));
      },
      fixedRange,
      setFixedRange,
      focus,
      setFocus,
      selection,
      select,
    }),
    [route, go, layers, showProduct, focus, selection, fixedRange, setFixedRange],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
