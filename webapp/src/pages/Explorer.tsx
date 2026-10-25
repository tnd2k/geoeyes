// Explorer: the map of the products shown in the tree (eye toggles), coloured like QGIS and the reports
// (Pretty Breaks over the full min–max, jet_r); click a point for its series, draw an area for the mean series.
import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer, SolidPolygonLayer, type ScatterplotLayerProps } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { useQueries, useQuery } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AreaInfo, type CatalogProduct, type CompareMeta, type LayerMeta, type Workspace } from "../api";
import { RainBars } from "../components/RainBars";
import { TimeSeries } from "../components/TimeSeries";
import { colorize, loadLayer, mapStyle, pickedVelocity, productLayer, type Base, type LayerData } from "../map";
import { useApp, type MapLayer } from "../state";
import { Button, Confidence, fmt } from "../ui";

type CompareMode = "off" | "swipe" | "diff";

interface Compare {
  mode: CompareMode;
  a: string;
  b: string;
  cell: number;
  align: boolean;
}

function Rain({ layer, meta }: { layer?: MapLayer; meta: LayerMeta }) {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem("geoeyes.rain") === "1";
    } catch {
      return false;
    }
  });
  const q = useQuery({
    queryKey: ["rain", layer?.key],
    queryFn: () => api.rainfall(layer!.project, layer!.product),
    enabled: on && !!layer,
    staleTime: Infinity,
  });
  const toggle = () => {
    setOn((v) => {
      try {
        localStorage.setItem("geoeyes.rain", v ? "0" : "1");
      } catch {
        /* storage unavailable */
      }
      return !v;
    });
  };
  return (
    <div className="mt-1">
      <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-muted">
        <input type="checkbox" className="accent-[#4cc2ff]" checked={on} onChange={toggle} /> monthly rainfall (CHIRPS)
      </label>
      {on && q.isLoading && <div className="py-2 text-[11.5px] text-[#7cd2ff]">Reading CHIRPS…</div>}
      {on && q.error && <div className="text-[11.5px] text-bad">{(q.error as Error).message}</div>}
      {on && q.data && <RainBars months={q.data.months} from={meta.dates[0]} to={meta.dates[meta.dates.length - 1]} />}
    </div>
  );
}

export function Legend({ meta, title, label = "LOS velocity" }: { meta: Pick<LayerMeta, "classes" | "vel_min" | "vel_max">; title: string; label?: string }) {
  const total = meta.classes.reduce((a, c) => a + c.count, 0) || 1;
  const step = meta.classes.length > 2 ? meta.classes[1].hi - meta.classes[1].lo : 1;
  const d = step >= 5 ? 0 : 1;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-semibold">{label}</span>
        <span className="text-[11px] text-muted">mm/yr</span>
      </div>
      <div className="mt-0.5 truncate text-[11px] text-muted" title={title}>
        {title}
      </div>
      <div className="mt-2 space-y-[3px]">
        {[...meta.classes].reverse().map((c) => (
          <div key={c.lo} className="flex items-center gap-2 text-[12px]">
            <span className="h-3 w-3 flex-none rounded-full" style={{ background: `rgb(${c.color.join(",")})` }} />
            <span className="w-[92px] font-mono text-[11.5px] text-ink-2">
              {c.lo.toFixed(d)} … {c.hi.toFixed(d)}
            </span>
            <span className="h-1.5 flex-1 overflow-hidden rounded bg-[#1a2740]">
              <span className="block h-full rounded bg-[#5b7397]" style={{ width: `${Math.max(1, (100 * c.count) / total)}%` }} />
            </span>
            <span className="w-11 text-right font-mono text-[11px] text-muted">{((100 * c.count) / total).toFixed(1)}%</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-muted">
        <span>
          min <span className="font-mono text-ink-2">{fmt.vel(meta.vel_min)}</span>
        </span>
        <span>
          max <span className="font-mono text-ink-2">{fmt.vel(meta.vel_max)}</span>
        </span>
      </div>
      <div className="mt-1.5 text-[11px] leading-snug text-faint">+ toward the satellite, − away (e.g. subsidence)</div>
    </div>
  );
}

export function Explorer({ ws }: { ws: Workspace | undefined }) {
  const { layers, setOpacity, setMode, toggleLayer, removeLayer, focus, setFocus, selection, select, go, showProduct } = useApp();
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const [base, setBase] = useState<Base>("dark");
  const [drawing, setDrawing] = useState(false);
  const [ring, setRing] = useState<[number, number][]>([]);
  const [area, setArea] = useState<{ layer: string; info: AreaInfo } | null>(null);
  const [areaBusy, setAreaBusy] = useState(false);
  const [cmp, setCmp] = useState<Compare>({ mode: "off", a: "", b: "", cell: 50, align: true });
  const [finder, setFinder] = useState<{ busy: boolean; rows: CatalogProduct[] | null; error?: string } | null>(null);
  const findHere = () => {
    const m = map.current;
    if (!m) return;
    const b = m.getBounds();
    setFinder({ busy: true, rows: null });
    api
      .catalogSearch([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], { vel_below: -10 })
      .then((r) => setFinder({ busy: false, rows: r.products }))
      .catch((e: Error) => setFinder({ busy: false, rows: null, error: e.message }));
  };
  const [split, setSplit] = useState(0.5);
  const [viewTick, setViewTick] = useState(0);
  const comparing = cmp.mode !== "off" && !!cmp.a && !!cmp.b && cmp.a !== cmp.b;
  const diff = useQuery({
    queryKey: ["diff", cmp.a, cmp.b, cmp.cell, cmp.align],
    queryFn: async () => {
      const meta: CompareMeta = await api.compare(cmp.a, cmp.b, cmp.cell, cmp.align);
      const buf = meta.n ? await api.compareBin(cmp.a, cmp.b, cmp.cell, cmp.align) : new Float32Array();
      return { meta, buf, colors: meta.classes ? colorize(buf, 5, 2, meta.classes) : new Uint8Array() };
    },
    enabled: comparing && cmp.mode === "diff",
    staleTime: Infinity,
  });

  const data = useQueries({
    queries: layers.map((l) => ({
      queryKey: ["layer", l.key, l.mode ?? "auto"],
      queryFn: () => loadLayer(l.project, l.product, l.mode ?? "auto"),
      staleTime: Infinity,
      gcTime: 10 * 60_000,
    })),
  });
  const byKey = useMemo(() => {
    const m: Record<string, LayerData | undefined> = {};
    layers.forEach((l, i) => (m[l.key] = data[i]?.data));
    return m;
  }, [layers, data]);
  const top = layers.find((l) => l.visible && byKey[l.key]);

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

  // zoom to a layer when it is shown from the tree
  useEffect(() => {
    if (!focus) return;
    const d = byKey[focus];
    if (d && map.current) {
      const [w, s, e, n] = d.meta.bounds;
      map.current.fitBounds([w, s, e, n], { padding: 60, duration: 600 });
      setFocus(null);
    }
  }, [focus, byKey, setFocus]);

  // swipe: the split longitude follows the map
  useEffect(() => {
    const m = map.current;
    if (!m || cmp.mode !== "swipe") return;
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setViewTick((t) => t + 1));
    };
    m.on("move", on);
    m.on("resize", on);
    return () => {
      m.off("move", on);
      m.off("resize", on);
      cancelAnimationFrame(raf);
    };
  }, [cmp.mode]);

  // map clicks while drawing an area
  useEffect(() => {
    const m = map.current;
    if (!m || !drawing) return;
    m.doubleClickZoom.disable();
    m.getCanvas().style.cursor = "crosshair";
    const click = (e: maplibregl.MapMouseEvent) => setRing((r) => [...r, [e.lngLat.lng, e.lngLat.lat]]);
    const dbl = (e: maplibregl.MapMouseEvent) => (e.preventDefault(), setDrawing(false));
    m.on("click", click);
    m.on("dblclick", dbl);
    return () => {
      m.off("click", click);
      m.off("dblclick", dbl);
      m.getCanvas().style.cursor = "";
      setTimeout(() => m.doubleClickZoom.enable(), 0);
    };
  }, [drawing]);

  // area finished: mean series of the top layer
  useEffect(() => {
    if (drawing || ring.length < 3 || !top) return;
    setAreaBusy(true);
    api
      .area(top.project, top.product, ring)
      .then((info) => setArea({ layer: top.key, info }))
      .finally(() => setAreaBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawing]);

  // ------------------------------------------------------------ selected point
  const selLayer = selection ? layers.find((l) => l.key === selection.layer) : undefined;
  const point = useQuery({
    queryKey: ["point", selection?.layer, selection?.index],
    queryFn: () => api.point(selLayer!.project, selLayer!.product, selection!.index),
    enabled: !!selLayer,
  });

  // ------------------------------------------------------------ deck layers
  useEffect(() => {
    const ov = overlay.current;
    if (!ov) return;
    const deckLayers: unknown[] = [];
    const m = map.current;
    let splitLon = 0;
    if (comparing && cmp.mode === "swipe" && m) {
      const c = m.getCanvas();
      splitLon = m.unproject([split * c.clientWidth, c.clientHeight / 2]).lng;
    }
    if (comparing && cmp.mode === "diff" && diff.data?.meta.n && diff.data.meta.origin) {
      const dm = diff.data.meta;
      deckLayers.push(
        new ScatterplotLayer({
          id: "diff",
          data: {
            length: dm.n,
            attributes: {
              getPosition: { value: diff.data.buf, size: 2, stride: 20, offset: 0 },
              getFillColor: { value: diff.data.colors, size: 3, normalized: true },
            },
          } as unknown as ScatterplotLayerProps["data"],
          coordinateSystem: COORDINATE_SYSTEM.LNGLAT_OFFSETS,
          coordinateOrigin: [dm.origin![0], dm.origin![1], 0],
          radiusUnits: "meters",
          getRadius: dm.cell_m * 0.5,
          radiusMinPixels: 1.5,
          stroked: false,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 255],
        }),
      );
    }
    [...layers].reverse().forEach((l) => {
      const d = byKey[l.key];
      if (!d || !l.visible) return;
      if (comparing && cmp.mode === "diff") return;
      if (comparing && cmp.mode === "swipe" && l.key !== cmp.a && l.key !== cmp.b) return;
      const swipe = comparing && cmp.mode === "swipe";
      deckLayers.push(
        productLayer(l, d, {
          pickable: !drawing,
          onPick: (index) => {
            select({ layer: l.key, index });
            setArea(null);
          },
          clipLon: swipe ? (l.key === cmp.a ? [-180, splitLon] : [splitLon, 180]) : null,
        }),
      );
    });
    if (selection && point.data && point.data.index === selection.index) {
      deckLayers.push(
        new ScatterplotLayer({
          id: "selected",
          data: [[point.data.lon, point.data.lat]],
          getPosition: (p: number[]) => [p[0], p[1]],
          getRadius: 9,
          radiusUnits: "pixels",
          stroked: true,
          filled: false,
          getLineColor: [255, 255, 255],
          lineWidthMinPixels: 2.5,
        }),
      );
    }
    if (ring.length) {
      const closed = drawing ? ring : [...ring, ring[0]];
      if (!drawing && ring.length >= 3)
        deckLayers.push(
          new SolidPolygonLayer<[number, number][]>({
            id: "area-fill",
            data: [ring],
            getPolygon: (r) => r as never,
            getFillColor: [255, 255, 255, 30],
          }),
        );
      deckLayers.push(
        new PathLayer<[number, number][]>({
          id: "area-line",
          data: [closed],
          getPath: (r) => r as never,
          getColor: [255, 255, 255],
          getWidth: 2.5,
          widthUnits: "pixels",
        }),
      );
    }
    ov.setProps({
      layers: deckLayers as never,
      getTooltip: ({ index, layer, object }: { index: number; layer?: { id: string } | null; object?: unknown }) => {
        const style = { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" };
        if (!layer) return null;
        if (layer.id === "diff" && diff.data && index >= 0) {
          const b = diff.data.buf;
          return { text: `B − A ${fmt.vel(b[index * 5 + 2])} mm/yr\nA ${fmt.vel(b[index * 5 + 3])} · B ${fmt.vel(b[index * 5 + 4])}`, style };
        }
        const key = Object.keys(byKey).find((k) => layer.id.startsWith(`pts-${k}`));
        const d = key ? byKey[key] : undefined;
        const v = d ? pickedVelocity(d, index, object) : null;
        return v == null ? null : { text: `${fmt.vel(v)} mm/yr`, style };
      },
    });
  }, [layers, byKey, selection, point.data, ring, drawing, select, comparing, cmp, diff.data, split, viewTick]);

  const pointScn = useMemo(
    () => (point.data?.disp_scn_mm ? { values: point.data.disp_scn_mm, label: "residual atmosphere (SCN) removed" } : null),
    [point.data],
  );
  const areaScn = useMemo(
    () => (area?.info.mean_scn_mm ? { values: area.info.mean_scn_mm, label: "residual atmosphere (SCN) removed" } : null),
    [area],
  );
  const selMeta = selection ? byKey[selection.layer]?.meta : undefined;
  const areaMeta = area ? byKey[area.layer]?.meta : undefined;

  const summary = (l: MapLayer) => ws?.projects[l.project]?.tracks.find((t) => t.product?.id === l.product);
  const loading = data.some((q) => q.isLoading);
  const errors = data.map((q, i) => (q.error ? `${layers[i]?.product}: ${(q.error as Error).message}` : null)).filter(Boolean);

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* maplibre-gl.css sets the map container to position: relative, hence the wrapper */}
      <div className="absolute inset-0">
        <div ref={mapEl} className="h-full w-full" />
      </div>

      {/* toolbar */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-line-2 bg-panel/95 p-0.5 shadow-lg shadow-black/30 backdrop-blur">
          {(["dark", "light", "satellite"] as Base[]).map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => setBase(b)}
              aria-pressed={base === b}
              className={`h-8 rounded-md px-3 text-[12.5px] capitalize ${base === b ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
            >
              {b}
            </button>
          ))}
        </div>
        <Button
          className="bg-panel/95 shadow-lg shadow-black/30 backdrop-blur"
          disabled={!top}
          aria-pressed={drawing}
          onClick={() => {
            if (drawing) setDrawing(false);
            else {
              setRing([]);
              setArea(null);
              select(null);
              setDrawing(true);
            }
          }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
            <path d="M2 12 5 3l7 2 2 7-8 2z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          </svg>
          {drawing ? `Finish area (${ring.length} pts)` : "Draw area"}
        </Button>
        <Button
          className="bg-panel/95 shadow-lg shadow-black/30 backdrop-blur"
          disabled={layers.length < 2}
          aria-pressed={cmp.mode !== "off"}
          title={layers.length < 2 ? "Show two products on the map to compare them" : "Compare two products"}
          onClick={() =>
            setCmp((c) =>
              c.mode !== "off"
                ? { ...c, mode: "off" }
                : { ...c, mode: "swipe", a: c.a && layers.some((l) => l.key === c.a) ? c.a : layers[1]?.key ?? "", b: c.b && layers.some((l) => l.key === c.b) ? c.b : layers[0]?.key ?? "" },
            )
          }
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
            <path d="M8 1.5v13M2 4h4v8H2zM10 4h4v8h-4z" fill="none" stroke="currentColor" strokeWidth="1.4" />
          </svg>
          {cmp.mode !== "off" ? "Stop comparing" : "Compare"}
        </Button>
        <Button className="bg-panel/95 shadow-lg shadow-black/30 backdrop-blur" onClick={findHere} title="Products of every project over the current view (workspace catalog)">
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
            <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <path d="m10.5 10.5 3.5 3.5" stroke="currentColor" strokeWidth="1.4" />
          </svg>
          Products here
        </Button>
        {(ring.length > 0 || area) && !drawing && (
          <Button className="bg-panel/95 backdrop-blur" onClick={() => (setRing([]), setArea(null))}>
            Clear area
          </Button>
        )}
        {drawing && <span className="rounded-md bg-[#0b1220]/85 px-2.5 py-1.5 text-[12px] text-ink-2">Click to add vertices · double-click to finish</span>}
        {loading && <span className="rounded-md bg-[#0b1220]/85 px-2.5 py-1.5 text-[12px] text-[#7cd2ff]">Loading points…</span>}
      </div>

      {finder && (
        <div className="absolute top-16 left-3 z-10 max-h-[calc(100%-120px)] w-[min(380px,calc(100%-24px))] overflow-y-auto rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">PRODUCTS IN THIS VIEW</span>
            <button type="button" className="ml-auto text-faint hover:text-ink" onClick={() => setFinder(null)} aria-label="Close">
              ×
            </button>
          </div>
          {finder.busy && <div className="py-3 text-[12.5px] text-[#7cd2ff]">Searching the catalog…</div>}
          {finder.error && <div className="py-2 text-[12.5px] text-bad">{finder.error}</div>}
          {finder.rows && finder.rows.length === 0 && <div className="py-3 text-[12.5px] text-muted">No product covers this view.</div>}
          {finder.rows?.map((r) => {
            const shown = layers.some((l) => l.key === `${r.project}/${r.id}`);
            return (
              <div key={r.id} className="mt-2 rounded-lg border border-line bg-panel-2 px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[12.5px]">{r.project}</span>
                  <span className="text-[11.5px] text-muted">v{r.id.split("_v").pop()}</span>
                  <button
                    type="button"
                    disabled={shown}
                    onClick={() => showProduct(r.project, r.id)}
                    className="ml-auto text-[12px] text-accent hover:underline disabled:text-faint disabled:no-underline"
                  >
                    {shown ? "on the map" : "show"}
                  </button>
                </div>
                <div className="mt-0.5 text-[11.5px] text-muted">
                  {fmt.sensor(r.sensor)} · {r.first_date} → {r.last_date}
                  {r.confidence ? ` · ${r.confidence} confidence` : ""}
                </div>
                {r.in_area && (
                  <div className="mt-1 text-[12px] text-ink-2">
                    {fmt.int(r.in_area.n)} points here · median <span className="font-mono">{fmt.vel(r.in_area.vel_median)}</span>, range{" "}
                    <span className="font-mono">
                      {fmt.vel(r.in_area.vel_min)} … {fmt.vel(r.in_area.vel_max)}
                    </span>{" "}
                    mm/yr{r.in_area.n_below ? ` · ${fmt.int(r.in_area.n_below)} faster than −10 away` : ""}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {comparing && cmp.mode === "swipe" && (
        <div
          className="absolute top-0 bottom-0 z-[5] w-6 -translate-x-1/2 cursor-ew-resize"
          style={{ left: `${split * 100}%` }}
          role="slider"
          aria-label="Swipe position"
          aria-valuenow={Math.round(split * 100)}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setSplit((s) => Math.max(0.02, s - 0.02));
            if (e.key === "ArrowRight") setSplit((s) => Math.min(0.98, s + 0.02));
          }}
          onPointerDown={(e) => {
            const parent = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect();
            e.currentTarget.setPointerCapture(e.pointerId);
            const move = (ev: PointerEvent) => setSplit(Math.min(0.98, Math.max(0.02, (ev.clientX - parent.left) / parent.width)));
            const up = () => (removeEventListener("pointermove", move), removeEventListener("pointerup", up));
            addEventListener("pointermove", move);
            addEventListener("pointerup", up);
          }}
        >
          <div className="mx-auto h-full w-[2px] bg-white/90 shadow-[0_0_6px_rgba(0,0,0,0.6)]" />
          <div className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-[13px] font-bold text-[#0b1220] shadow-lg">⇆</div>
          <div className="absolute top-16 right-5 rounded bg-[#0b1220]/85 px-2 py-0.5 text-[11.5px] whitespace-nowrap text-ink-2">A</div>
          <div className="absolute top-16 left-5 rounded bg-[#0b1220]/85 px-2 py-0.5 text-[11.5px] whitespace-nowrap text-ink-2">B</div>
        </div>
      )}

      {layers.length === 0 && (
        <div className="absolute top-1/2 left-1/2 z-10 w-[min(420px,90%)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line-2 bg-panel/95 p-6 text-center shadow-2xl backdrop-blur">
          <div className="text-[15px] font-semibold">No product on the map</div>
          <p className="mt-2 text-[13px] leading-relaxed text-muted">
            Click the eye next to a product in the project tree (or the product name) to show its points here, like a layer in QGIS.
          </p>
          <Button className="mt-4" onClick={() => go({ page: "overview" })}>
            Go to the overview
          </Button>
        </div>
      )}

      {/* right panel */}
      {layers.length > 0 && (
        <div className="pointer-events-none absolute top-3 right-3 bottom-3 z-10 flex w-[min(360px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto">
          {cmp.mode !== "off" && (
            <div className="rounded-xl border border-[#2f6fb0] bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">COMPARE</span>
                <div className="ml-auto flex rounded-md border border-line-2 p-0.5">
                  {(["swipe", "diff"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      aria-pressed={cmp.mode === m}
                      onClick={() => setCmp((c) => ({ ...c, mode: m }))}
                      className={`h-6 rounded px-2.5 text-[12px] ${cmp.mode === m ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
                    >
                      {m === "swipe" ? "Swipe" : "Difference"}
                    </button>
                  ))}
                </div>
              </div>
              {(["a", "b"] as const).map((k) => (
                <label key={k} className="mt-1.5 flex items-center gap-2 text-[12px]">
                  <span className="w-5 font-semibold text-muted">{k.toUpperCase()}</span>
                  <select
                    value={cmp[k]}
                    onChange={(e) => setCmp((c) => ({ ...c, [k]: e.target.value }))}
                    className="h-7 min-w-0 flex-1 rounded-md border border-line-2 bg-[#0a1322] px-1.5 text-[12px] text-ink"
                  >
                    {layers.map((l) => (
                      <option key={l.key} value={l.key}>
                        {l.project} v{l.product.split("_v").pop()}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              {cmp.a === cmp.b && <div className="mt-2 text-[12px] text-warn">Choose two different products.</div>}
              {comparing && (() => {
                const ta = summary(layers.find((l) => l.key === cmp.a)!);
                const tb = summary(layers.find((l) => l.key === cmp.b)!);
                return ta && tb && ta.track_id !== tb.track_id ? (
                  <div className="mt-2 rounded-md bg-[#2a2110] px-2 py-1.5 text-[11.5px] leading-snug text-[#f5d08b]">
                    Different tracks ({ta.track_id} / {tb.track_id}): each measures along its own line of sight, so a difference also contains geometry, not
                    only motion.
                  </div>
                ) : null;
              })()}
              {cmp.mode === "swipe" && comparing && <div className="mt-2 text-[11.5px] text-faint">A left of the handle, B right. Drag the handle or use ← →.</div>}
              {cmp.mode === "diff" && comparing && (
                <>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px]">
                    <label className="flex items-center gap-1.5">
                      Cell
                      <select
                        value={cmp.cell}
                        onChange={(e) => setCmp((c) => ({ ...c, cell: Number(e.target.value) }))}
                        className="h-7 rounded-md border border-line-2 bg-[#0a1322] px-1.5 text-[12px]"
                      >
                        {[20, 50, 100, 200, 500].map((v) => (
                          <option key={v} value={v}>
                            {v} m
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-1.5" title="Each product has its own reference area: remove the median difference">
                      <input type="checkbox" className="accent-[#4cc2ff]" checked={cmp.align} onChange={(e) => setCmp((c) => ({ ...c, align: e.target.checked }))} />
                      remove median offset
                    </label>
                  </div>
                  {diff.isFetching && <div className="mt-2 text-[12px] text-[#7cd2ff]">Computing…</div>}
                  {diff.error && <div className="mt-2 text-[12px] text-bad">{(diff.error as Error).message}</div>}
                  {diff.data && diff.data.meta.n === 0 && <div className="mt-2 text-[12px] text-muted">The two products have no cell in common.</div>}
                  {diff.data?.meta.stats && (
                    <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
                      {[
                        ["Common cells", fmt.int(diff.data.meta.n)],
                        ["Correlation A/B", fmt.num(diff.data.meta.stats.corr, 2)],
                        ["Offset removed", `${fmt.vel(diff.data.meta.align ? diff.data.meta.offset : 0)} mm/yr`],
                        ["Std of B − A", `${fmt.num(diff.data.meta.stats.std)} mm/yr`],
                        ["P5 … P95", `${fmt.vel(diff.data.meta.stats.p05)} … ${fmt.vel(diff.data.meta.stats.p95)}`],
                        ["RMSE", `${fmt.num(diff.data.meta.stats.rmse)} mm/yr`],
                      ].map(([k, v]) => (
                        <div key={k} className="contents">
                          <span className="text-muted">{k}</span>
                          <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {cmp.mode === "diff" && comparing && diff.data?.meta.classes && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
              <Legend
                meta={{ classes: diff.data.meta.classes, vel_min: diff.data.meta.vel_min!, vel_max: diff.data.meta.vel_max! }}
                title={`median per ${diff.data.meta.cell_m} m cell`}
                label="B − A velocity"
              />
            </div>
          )}

          <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
            <div className="mb-2 text-[11px] font-semibold tracking-[1.2px] text-muted">LAYERS</div>
            <div className="space-y-2">
              {layers.map((l) => {
                const t = summary(l);
                const d = byKey[l.key];
                return (
                  <div key={l.key} className="rounded-lg border border-line bg-panel-2 px-2.5 py-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={l.visible}
                        onChange={() => toggleLayer(l.key)}
                        aria-label={`Show ${l.product}`}
                        className="h-4 w-4 accent-[#4cc2ff]"
                      />
                      <button type="button" onClick={() => setFocus(l.key)} className="min-w-0 flex-1 truncate text-left text-[12.5px] hover:text-accent" title="Zoom to layer">
                        <span className="font-mono">{l.project}</span>{" "}
                        <span className="text-muted">v{l.product.split("_v").pop()}</span>
                      </button>
                      <button type="button" onClick={() => removeLayer(l.key)} title="Remove from the map" className="text-faint hover:text-bad">
                        ×
                      </button>
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 pl-6 text-[11px] text-muted">
                      <span className="truncate">
                        {t ? `${fmt.sensor(t.sensor)} ${t.direction}` : ""} · {d ? `${fmt.int(d.meta.n)} pts` : "…"}
                      </span>
                      <select
                        value={l.mode ?? "auto"}
                        onChange={(e) => setMode(l.key, e.target.value as MapLayer["mode"])}
                        aria-label="Rendering"
                        title="Points: the whole product at once. Tiles: PMTiles vector tiles, read as you pan (auto: above 2.5 M points)"
                        className="h-6 rounded border border-line-2 bg-[#0a1322] px-1 text-[11px] text-ink-2"
                      >
                        <option value="auto">auto{d ? ` (${d.kind})` : ""}</option>
                        <option value="points">points</option>
                        <option value="tiles">tiles</option>
                      </select>
                      <input
                        type="range"
                        min={0.1}
                        max={1}
                        step={0.05}
                        value={l.opacity}
                        onChange={(e) => setOpacity(l.key, Number(e.target.value))}
                        aria-label="Opacity"
                        className="ml-auto w-20 accent-[#4cc2ff]"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            {errors.length > 0 && <div className="mt-2 text-[12px] text-bad">{errors.join(" · ")}</div>}
          </div>

          {top && byKey[top.key] && !(cmp.mode === "diff" && comparing) && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
              <Legend meta={byKey[top.key]!.meta} title={top.product} />
              <div className="mt-2">
                <Confidence level={summary(top)?.product?.confidence} />
              </div>
            </div>
          )}

          {selection && selMeta && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-semibold">Point #{selection.index}</span>
                <button type="button" className="text-faint hover:text-ink" onClick={() => select(null)} aria-label="Close">
                  ×
                </button>
              </div>
              {point.data ? (
                <>
                  <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
                    {[
                      ["Velocity", `${fmt.vel(point.data.vel)} ± ${fmt.num(point.data.vel_std_mm_yr)} mm/yr`],
                      ["Coherence", fmt.num(point.data.temporal_coherence, 2)],
                      ["Height", `${fmt.num(point.data.height_m)} m`],
                      ["Seasonal amp.", `${fmt.num(point.data.seasonal_amp_mm)} mm`],
                      ["Lon / lat", `${point.data.lon.toFixed(5)}, ${point.data.lat.toFixed(5)}`],
                    ].map(([k, v]) => (
                      <div key={k} className="contents">
                        <span className="text-muted">{k}</span>
                        <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2">
                    <TimeSeries dates={selMeta.dates} values={point.data.disp_mm} extra={pointScn} />
                    <Rain layer={selLayer} meta={selMeta} />
                  </div>
                  <div className="text-[11px] text-faint">Displacement along the line of sight, relative to the reference area and date</div>
                </>
              ) : (
                <div className="py-6 text-center text-[12px] text-muted">{point.error ? (point.error as Error).message : "Loading…"}</div>
              )}
            </div>
          )}

          {(area || areaBusy) && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
              <div className="text-[13px] font-semibold">Area mean</div>
              {areaBusy && <div className="py-4 text-[12px] text-muted">Computing…</div>}
              {area && area.info.n === 0 && <div className="py-3 text-[12px] text-muted">No point inside the area.</div>}
              {area && area.info.n > 0 && areaMeta && (
                <>
                  <div className="mt-1 text-[12px] text-ink-2">
                    {fmt.int(area.info.n)} points · mean <span className="font-mono">{fmt.vel(area.info.vel_mean)}</span> mm/yr (min{" "}
                    <span className="font-mono">{fmt.vel(area.info.vel_min)}</span>, max <span className="font-mono">{fmt.vel(area.info.vel_max)}</span>)
                  </div>
                  <div className="mt-2">
                    <TimeSeries dates={areaMeta.dates} values={area.info.mean_mm!} spread={area.info.std_mm!} extra={areaScn} />
                    <Rain layer={layers.find((l) => l.key === area.layer)} meta={areaMeta} />
                  </div>
                  <div className="text-[11px] text-faint">Mean of the points inside the area, band = ±1 standard deviation</div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
