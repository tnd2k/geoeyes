// Corridor brush (docs/*/research/corridor-processing.md, K2): set the width first, hold the left button and drag
// along the route; the stroke is drawn as a line of that width in metres (round caps and joints), which is exactly
// the buffer the server computes, and strokes that touch join into one corridor. Alt + drag erases, Space + drag
// moves the map, Ctrl+Z / Ctrl+Y undo and redo. The polygon itself always comes from the server (preview).
import type maplibregl from "maplibre-gl";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { api, type CorridorDraft, type CorridorPreview } from "../api";
import { t, ts } from "../i18n";
import { Button } from "../ui";

export type BrushMode = "brush" | "erase";
const SRC_POLY = "corridor-poly";
const SRC_LIVE = "corridor-live";
const SRC_STROKES = "corridor-strokes";
const EMPTY = { type: "FeatureCollection" as const, features: [] };
export const WIDTHS = [250, 500, 1000, 2000, 5000];
const BRUSH = "#1f7fd6";
const ERASER = "#e5484d";

export const emptyDraft = (width_m = 1000): CorridorDraft => ({ strokes: [], erase: [], polygons: [], width_m });
const hasContent = (d: CorridorDraft) => d.strokes.length > 0 || d.polygons.length > 0;

/** Ground distance in metres between two [lon, lat] (equirectangular: strokes are drawn in small steps). */
function metres(a: number[], b: number[]): number {
  const k = Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
  return Math.hypot((b[0] - a[0]) * k, b[1] - a[1]) * 111_320;
}

/** MapLibre line width (px) that is ``w`` metres on the ground at latitude ``lat``, at every zoom (512 px tiles). */
function widthExpr(w: number, lat: number) {
  const mpp = (z: number) => (40_075_016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** z);
  return ["interpolate", ["exponential", 2], ["zoom"], 0, w / mpp(0), 24, w / mpp(24)] as unknown as number;
}

function lineFC(strokes: number[][][]) {
  return {
    type: "FeatureCollection" as const,
    features: strokes.map((s) => ({
      type: "Feature" as const,
      properties: {},
      geometry: s.length > 1 ? { type: "LineString" as const, coordinates: s } : { type: "Point" as const, coordinates: s[0] },
    })),
  };
}

const typing = (e: KeyboardEvent) => {
  const el = e.target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

/** The brush on a MapLibre map: history of drafts (undo/redo), the live stroke, the server preview. */
export function useCorridorBrush(
  map: RefObject<maplibregl.Map | null>,
  opts: { active: boolean; mode: BrushMode; width: number; initial?: CorridorDraft | null; visible?: boolean },
) {
  const [hist, setHist] = useState<{ list: CorridorDraft[]; i: number }>(() => ({ list: [opts.initial ?? emptyDraft(opts.width)], i: 0 }));
  const draft = { ...hist.list[hist.i], width_m: opts.width };
  const [preview, setPreview] = useState<CorridorPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cur = useRef<{ pts: number[][]; erase: boolean } | null>(null);
  const space = useRef(false);
  const live = useRef({ active: opts.active, mode: opts.mode, width: opts.width });
  live.current = { active: opts.active, mode: opts.mode, width: opts.width };

  const push = useCallback((f: (d: CorridorDraft) => CorridorDraft) => {
    setHist((h) => {
      const next = f(h.list[h.i]);
      const list = [...h.list.slice(0, h.i + 1), next].slice(-100);
      return { list, i: list.length - 1 };
    });
  }, []);
  const undo = useCallback(() => setHist((h) => ({ ...h, i: Math.max(0, h.i - 1) })), []);
  const redo = useCallback(() => setHist((h) => ({ ...h, i: Math.min(h.list.length - 1, h.i + 1) })), []);
  const clear = useCallback(() => push(() => emptyDraft(live.current.width)), [push]);
  const reset = useCallback((d: CorridorDraft | null) => setHist({ list: [d ?? emptyDraft(live.current.width)], i: 0 }), []);

  // the page creates its map in its own effect, after this hook's: wait for it
  const [m, setM] = useState<maplibregl.Map | null>(null);
  useEffect(() => {
    let raf = requestAnimationFrame(function wait() {
      if (map.current) setM(map.current);
      else raf = requestAnimationFrame(wait);
    });
    return () => cancelAnimationFrame(raf);
  }, [map]);

  // what the sources show, kept to fill them again when they are (re)created (style load, base-map change)
  const data = useRef<Record<string, unknown>>({ [SRC_POLY]: EMPTY, [SRC_STROKES]: EMPTY, [SRC_LIVE]: EMPTY });
  const setSource = useCallback(
    (id: string, d: unknown) => {
      data.current[id] = d;
      (m?.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(d as never);
    },
    [m],
  );

  // ------------------------------------------------------------ map sources and layers (again after a base change)
  useEffect(() => {
    if (!m) return;
    const add = () => {
      if (!m.isStyleLoaded() || m.getSource(SRC_POLY)) return;
      m.addSource(SRC_POLY, { type: "geojson", data: data.current[SRC_POLY] as never });
      m.addSource(SRC_STROKES, { type: "geojson", data: data.current[SRC_STROKES] as never });
      m.addSource(SRC_LIVE, { type: "geojson", data: EMPTY });
      m.addLayer({ id: "corridor-fill", type: "fill", source: SRC_POLY, paint: { "fill-color": BRUSH, "fill-opacity": 0.22 } });
      m.addLayer({ id: "corridor-outline", type: "line", source: SRC_POLY, paint: { "line-color": "#1f5fb0", "line-width": 2 } });
      // the strokes as drawn (thin), so the route reads inside the band
      m.addLayer({ id: "corridor-strokes", type: "line", source: SRC_STROKES, paint: { "line-color": "#1f5fb0", "line-width": 1, "line-dasharray": [2, 2] } });
      m.addLayer({
        id: "corridor-live",
        type: "line",
        source: SRC_LIVE,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": BRUSH, "line-opacity": 0.4, "line-width": 10 },
      });
    };
    add();
    m.on("styledata", add);
    m.on("load", add);
    return () => {
      m.off("styledata", add);
      m.off("load", add);
    };
  }, [m]);

  const visible = opts.visible ?? true;
  useEffect(() => {
    if (!m) return;
    const apply = () => {
      const v = visible ? "visible" : "none";
      for (const id of ["corridor-fill", "corridor-outline", "corridor-strokes", "corridor-live"])
        if (m.getLayer(id) && (m.getLayoutProperty(id, "visibility") ?? "visible") !== v) m.setLayoutProperty(id, "visibility", v);
    };
    apply();
    m.on("styledata", apply);
    return () => void m.off("styledata", apply);
  }, [m, visible]);

  // ------------------------------------------------------------ server preview (debounced)
  const key = JSON.stringify(draft);
  useEffect(() => {
    setSource(SRC_STROKES, lineFC(draft.strokes));
    if (!hasContent(draft)) {
      setPreview(null);
      setError(null);
      setSource(SRC_POLY, EMPTY);
      return;
    }
    let gone = false;
    const id = window.setTimeout(async () => {
      setBusy(true);
      try {
        const p = await api.corridorPreview(draft);
        if (gone) return;
        setPreview(p);
        setError(null);
        setSource(SRC_POLY, p.geometry ? { type: "Feature", properties: {}, geometry: p.geometry } : EMPTY);
      } catch (e) {
        if (!gone) setError(ts((e as Error).message));
      } finally {
        if (!gone) setBusy(false);
      }
    }, 220);
    return () => {
      gone = true;
      window.clearTimeout(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // ------------------------------------------------------------ mouse and keys
  useEffect(() => {
    if (!m) return;
    if (!opts.active) return;
    m.dragPan.disable();
    m.doubleClickZoom.disable();       // a quick second stroke must not zoom
    m.getCanvas().style.cursor = "crosshair";
    const paintLive = (pts: number[][], erase: boolean) => {
      if (!m.getLayer("corridor-live")) return;
      m.setPaintProperty("corridor-live", "line-color", erase ? ERASER : BRUSH);
      m.setPaintProperty("corridor-live", "line-width", widthExpr(live.current.width, pts[0][1]));
      setSource(SRC_LIVE, lineFC([pts.length > 1 ? pts : [pts[0], pts[0]]]));
    };
    const down = (e: maplibregl.MapMouseEvent) => {
      if (space.current || e.originalEvent.button !== 0) return;
      e.preventDefault();
      const p = [e.lngLat.lng, e.lngLat.lat];
      cur.current = { pts: [p], erase: live.current.mode === "erase" || e.originalEvent.altKey };
      paintLive(cur.current.pts, cur.current.erase);
    };
    const move = (e: maplibregl.MapMouseEvent) => {
      const c = cur.current;
      if (!c) return;
      const p = [e.lngLat.lng, e.lngLat.lat];
      // a point every quarter width on the ground: a fast drag leaves no gap, a slow one no pile of points
      if (metres(c.pts[c.pts.length - 1], p) >= live.current.width / 4) c.pts.push(p);
      paintLive([...c.pts, p], c.erase);
    };
    const up = (e: MouseEvent) => {
      const c = cur.current;
      if (!c) return;
      cur.current = null;
      const r = m.getCanvas().getBoundingClientRect();
      const ll = m.unproject([e.clientX - r.left, e.clientY - r.top]);
      const last = [ll.lng, ll.lat];
      const pts = metres(c.pts[c.pts.length - 1], last) > 1 ? [...c.pts, last] : c.pts;
      const stroke = pts.map((q) => [Math.round(q[0] * 1e6) / 1e6, Math.round(q[1] * 1e6) / 1e6]);
      setSource(SRC_LIVE, EMPTY);
      push((d) => (c.erase ? { ...d, erase: [...d.erase, stroke] } : { ...d, strokes: [...d.strokes, stroke] }));
    };
    const kdown = (e: KeyboardEvent) => {
      if (typing(e)) return;
      if (e.code === "Space" && !space.current) {
        space.current = true;
        m.dragPan.enable();
        m.getCanvas().style.cursor = "grab";
        e.preventDefault();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
      }
    };
    const kup = (e: KeyboardEvent) => {
      if (e.code !== "Space" || !space.current) return;
      space.current = false;
      m.dragPan.disable();
      m.getCanvas().style.cursor = "crosshair";
    };
    m.on("mousedown", down);
    m.on("mousemove", move);
    window.addEventListener("mouseup", up);
    window.addEventListener("keydown", kdown);
    window.addEventListener("keyup", kup);
    return () => {
      m.off("mousedown", down);
      m.off("mousemove", move);
      window.removeEventListener("mouseup", up);
      window.removeEventListener("keydown", kdown);
      window.removeEventListener("keyup", kup);
      cur.current = null;
      space.current = false;
      setSource(SRC_LIVE, EMPTY);
      m.dragPan.enable();
      m.doubleClickZoom.enable();
      m.getCanvas().style.cursor = "";
    };
  }, [m, opts.active, push, undo, redo, setSource]);

  /** A route file (gpkg, geojson, kml/kmz, zipped shapefile) added as strokes and polygons. */
  const importFile = useCallback(
    async (file: File) => {
      setError(null);
      setBusy(true);
      try {
        const b64 = await new Promise<string>((ok, bad) => {
          const r = new FileReader();
          r.onload = () => ok(String(r.result).split(",", 2)[1] ?? "");
          r.onerror = () => bad(r.error);
          r.readAsDataURL(file);
        });
        const got = await api.corridorImport(file.name, b64);
        push((d) => ({ ...d, strokes: [...d.strokes, ...got.strokes], polygons: [...d.polygons, ...got.polygons] }));
        const xs = got.strokes.flat().map((p) => p[0]);
        const ys = got.strokes.flat().map((p) => p[1]);
        if (xs.length && map.current)
          map.current.fitBounds([Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)], { padding: 60, duration: 600 });
      } catch (e) {
        setError(ts((e as Error).message));
      } finally {
        setBusy(false);
      }
    },
    [map, push],
  );

  return { draft, preview, busy, error, undo, redo, clear, reset, importFile, canUndo: hist.i > 0, canRedo: hist.i < hist.list.length - 1, empty: !hasContent(draft) };
}

export type Brush = ReturnType<typeof useCorridorBrush>;

/** The brush controls: on/off, brush or eraser, width, undo/redo/clear, route file, the figures of the corridor. */
export function CorridorTools({
  brush,
  active,
  onActive,
  mode,
  onMode,
  width,
  onWidth,
  bboxArea,
}: {
  brush: Brush;
  active: boolean;
  onActive: (v: boolean) => void;
  mode: BrushMode;
  onMode: (m: BrushMode) => void;
  width: number;
  onWidth: (w: number) => void;
  bboxArea?: number | null;
}) {
  const file = useRef<HTMLInputElement>(null);
  const info = brush.preview?.info;
  const seg = "h-8 rounded-md border px-2.5 text-[12.5px]";
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12.5px] font-medium text-ink-2">{t("Width")}</span>
        <select value={WIDTHS.includes(width) ? width : ""} onChange={(e) => e.target.value && onWidth(Number(e.target.value))} className="h-8 rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink">
          {WIDTHS.map((w) => (
            <option key={w} value={w}>
              {w >= 1000 ? `${w / 1000} km` : `${w} m`}
            </option>
          ))}
          {!WIDTHS.includes(width) && <option value="">{width} m</option>}
        </select>
        <input
          type="number"
          min={50}
          max={20000}
          step={50}
          value={width}
          onChange={(e) => Number(e.target.value) >= 50 && onWidth(Number(e.target.value))}
          className="h-8 w-24 rounded-md border border-line-2 bg-sunken px-2 font-mono text-[12.5px] text-ink"
          aria-label={t("Width (m)")}
        />
        <span className="text-[11.5px] text-faint">{t("full width: {h} m on each side", { h: Math.round(width / 2) })}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant={active ? "primary" : "ghost"} onClick={() => onActive(!active)}>
          {active ? t("Drawing… (click to stop)") : brush.empty ? t("Draw along the route") : t("Continue drawing")}
        </Button>
        <div className="flex gap-1" role="group" aria-label={t("Brush or eraser")}>
          <button type="button" aria-pressed={mode === "brush"} onClick={() => (onMode("brush"), onActive(true))} className={`${seg} ${mode === "brush" ? "border-accent bg-accent-bg text-accent-ink" : "border-line-2 text-ink-2 hover:bg-raised"}`}>
            {t("Brush")}
          </button>
          <button type="button" aria-pressed={mode === "erase"} onClick={() => (onMode("erase"), onActive(true))} className={`${seg} ${mode === "erase" ? "border-bad-line bg-bad-bg text-bad-ink" : "border-line-2 text-ink-2 hover:bg-raised"}`}>
            {t("Eraser")}
          </button>
        </div>
        <Button disabled={!brush.canUndo} onClick={brush.undo} title="Ctrl+Z">
          {t("Undo")}
        </Button>
        <Button disabled={!brush.canRedo} onClick={brush.redo} title="Ctrl+Y">
          {t("Redo")}
        </Button>
        <Button disabled={brush.empty} onClick={brush.clear}>
          {t("Clear")}
        </Button>
        <Button onClick={() => file.current?.click()}>{t("Import a route…")}</Button>
        <input
          ref={file}
          type="file"
          accept=".gpkg,.geojson,.json,.kml,.kmz,.zip"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void brush.importFile(f);
            e.target.value = "";
          }}
        />
      </div>
      {info && (
        <div className="rounded-lg border border-line bg-panel-2 px-3 py-2 text-[12.5px] text-ink-2">
          {t("Corridor: {len} km of route, {area} km²", { len: info.length_km.toFixed(1), area: info.area_km2.toFixed(1) })}
          {info.parts > 1 && <span className="text-warn"> · {t("{n} separate parts", { n: info.parts })}</span>}
          {bboxArea ? <span className="text-faint"> · {t("{p}% of the rectangle around it", { p: ((100 * info.area_km2) / bboxArea).toFixed(1) })}</span> : null}
          {brush.busy && <span className="text-faint"> · …</span>}
        </div>
      )}
      {brush.error && <div className="text-[12px] text-bad">{brush.error}</div>}
    </div>
  );
}

/** Map hint while the brush is on. */
export function BrushHint({ mode }: { mode: BrushMode }) {
  return (
    <div className="pointer-events-none absolute top-3 left-3 z-10 max-w-[360px] rounded-md bg-bg/85 px-3 py-1.5 text-[12px] leading-snug text-ink-2">
      {mode === "erase" ? t("Hold the left button and drag over the part to remove") : t("Hold the left button and drag along the route")}
      <span className="text-faint"> · {t("Alt + drag: erase · hold Space: move the map · Ctrl+Z: undo")}</span>
    </div>
  );
}

/** Area (km²) of the bbox [w, s, e, n] on the ground. */
export function bboxKm2(b: number[] | null | undefined): number | null {
  if (!b) return null;
  const k = Math.cos((((b[1] + b[3]) / 2) * Math.PI) / 180);
  return (b[2] - b[0]) * 111.32 * k * (b[3] - b[1]) * 110.57;
}
