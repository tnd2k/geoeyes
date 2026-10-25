// Map composer: frame the products shown on the map on a sheet (title, legend, scale bar, north arrow, product
// details, credits) and export it as PNG or PDF at print resolution.
import { MapboxOverlay } from "@deck.gl/mapbox";
import { useQueries } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Workspace } from "../api";
import { degLabel, drawSheet, graticuleStep, layout, metresPerPixel, PAPERS, pdfFromJpeg, type Options, type SheetData } from "../compose";
import { BASES, loadLayer, mapStyle, productLayer, type Base, type LayerData } from "../map";
import { useApp } from "../state";
import { Button, fmt, Panel } from "../ui";

const field = "h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[13px] text-ink focus:border-accent focus:outline-none";

function Toggle({ label, on, set }: { label: string; on: boolean; set: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-2">
      <input type="checkbox" className="h-4 w-4 accent-[#4cc2ff]" checked={on} onChange={(e) => set(e.target.checked)} />
      {label}
    </label>
  );
}

const SENSOR_CREDIT: Record<string, string> = {
  sentinel1: "Contains modified Copernicus Sentinel data",
  cosmo_skymed: "COSMO-SkyMed® Product © ASI",
  capella: "Capella Space data",
  terrasar_x: "TerraSAR-X data © DLR",
};

/** The preview map's view rendered off screen at `wPx` × `hPx` device pixels: a second map of that size (CSS size
 *  = pixels / devicePixelRatio, so MapLibre and deck.gl agree on the pixel ratio) with the zoom raised so the
 *  ground extent is that of the preview; screen-pixel point sizes are scaled the same way. */
async function renderMap(
  preview: maplibregl.Map,
  wPx: number,
  hPx: number,
  previewCssW: number,
  style: maplibregl.StyleSpecification,
  deckLayers: (pixelScale: number) => unknown[],
): Promise<{ canvas: HTMLCanvasElement; done: () => void }> {
  const dpr = window.devicePixelRatio || 1;
  const cssW = wPx / dpr;
  const cssH = hPx / dpr;
  const k = cssW / previewCssW;
  const host = document.createElement("div");
  host.style.cssText = `position:fixed;left:-${Math.ceil(cssW) + 100}px;top:0;width:${cssW}px;height:${cssH}px;`;
  document.body.appendChild(host);
  const m = new maplibregl.Map({
    container: host,
    style,
    center: preview.getCenter(),
    zoom: preview.getZoom() + Math.log2(k),
    interactive: false,
    attributionControl: false,
    preserveDrawingBuffer: true,
    fadeDuration: 0,
  } as maplibregl.MapOptions);
  const ov = new MapboxOverlay({ interleaved: true, layers: deckLayers(k) as never });
  m.addControl(ov as unknown as maplibregl.IControl);
  const done = () => {
    m.remove();
    host.remove();
  };
  try {
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("The map took too long to render")), 240_000);
      m.once("idle", () => {
        clearTimeout(timer);
        resolve();
      });
    });
    // vector-tile layers load after the base map: wait until the map stays idle
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 400));
      if (m.loaded() && m.areTilesLoaded()) break;
    }
    m.triggerRepaint();
    await new Promise<void>((resolve) => m.once("render", () => resolve()));
    return { canvas: m.getCanvas(), done };
  } catch (e) {
    done();
    throw e;
  }
}

function download(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

export function Compose({ ws }: { ws: Workspace | undefined }) {
  const { layers, go } = useApp();
  const visible = layers.filter((l) => l.visible);
  const first = visible[0];
  const summary = first ? ws?.projects[first.project]?.tracks.find((t) => t.product?.id === first.product) : undefined;
  const [paperId, setPaperId] = useState("a4l");
  const [dpi, setDpi] = useState(300);
  const [base, setBase] = useState<Base>("light");
  const [o, setO] = useState<Options>({
    title: first ? `Ground motion — ${first.project}` : "Ground motion",
    subtitle: "",
    legend: "right",
    scale: true,
    north: true,
    meta: true,
    credits: true,
    frame: true,
    geometry: true,
    theme: "light",
  });
  const set = <K extends keyof Options>(k: K, v: Options[K]) => setO((x) => ({ ...x, [k]: v }));
  const paper = PAPERS.find((p) => p.id === paperId)!;
  const L = useMemo(() => layout(paper, o), [paper, o]);

  const data = useQueries({
    queries: visible.map((l) => ({
      queryKey: ["layer", l.key, l.mode ?? "auto"],
      queryFn: () => loadLayer(l.project, l.product, l.mode ?? "auto"),
      staleTime: Infinity,
      gcTime: 10 * 60_000,
    })),
  });
  const byKey = useMemo(() => {
    const m: Record<string, LayerData | undefined> = {};
    visible.forEach((l, i) => (m[l.key] = data[i]?.data));
    return m;
  }, [visible, data]);
  const firstData = first ? byKey[first.key] : undefined;

  useEffect(() => {
    if (summary?.product && !o.subtitle) {
      const p = summary.product;
      set("subtitle", `${fmt.sensor(summary.sensor)} ${summary.direction} · LOS velocity ${p.first} → ${p.last} (${p.epochs} acquisitions)`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary?.product?.id]);

  // ------------------------------------------------------------ preview sheet size
  const area = useRef<HTMLDivElement>(null);
  const [areaSize, setAreaSize] = useState({ w: 800, h: 600 });
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setAreaSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const sp = Math.max(0.2, Math.min((areaSize.w - 32) / L.W, (areaSize.h - 32) / L.H));   // preview px per unit

  // ------------------------------------------------------------ live map
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!mapEl.current) return;
    const m = new maplibregl.Map({
      container: mapEl.current,
      style: mapStyle(base, o.theme === "light" ? "#f3f4f6" : "#0b1220"),
      center: [105.82, 21.02],
      zoom: 10,
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: false,
      preserveDrawingBuffer: true,
    } as maplibregl.MapOptions);
    const ov = new MapboxOverlay({ interleaved: true, layers: [] });
    m.addControl(ov as unknown as maplibregl.IControl);
    m.on("move", () => setTick((t) => t + 1));
    map.current = m;
    overlay.current = ov;
    return () => {
      m.remove();
      map.current = null;
      overlay.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    map.current?.setStyle(mapStyle(base, o.theme === "light" ? "#f3f4f6" : "#0b1220"));
  }, [base, o.theme]);
  useEffect(() => {
    map.current?.resize();
  }, [sp, L]);
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || !map.current) return;
    const ds = Object.values(byKey).filter(Boolean) as LayerData[];
    if (!ds.length) return;
    const b = ds.reduce(
      (a, d) => [Math.min(a[0], d.meta.bounds[0]), Math.min(a[1], d.meta.bounds[1]), Math.max(a[2], d.meta.bounds[2]), Math.max(a[3], d.meta.bounds[3])],
      [180, 90, -180, -90],
    );
    map.current.resize();
    map.current.fitBounds([b[0], b[1], b[2], b[3]], { padding: 24, duration: 0 });
    fitted.current = true;
  }, [byKey]);

  const deckLayers = useCallback(
    (pixelScale = 1) =>
      [...visible].reverse().flatMap((l) => {
        const d = byKey[l.key];
        return d ? [productLayer(l, d, { pickable: false, pixelScale, idPrefix: `c${pixelScale}-` })] : [];
      }),
    [visible, byKey],
  );
  useEffect(() => {
    overlay.current?.setProps({ layers: deckLayers() as never });
  }, [deckLayers]);

  // ------------------------------------------------------------ sheet content
  const sheetData = useCallback((): SheetData => {
    const m = map.current;
    const metresPerUnit = m ? (metresPerPixel(m.getCenter().lat, m.getZoom()) * (L.map.w * sp)) / L.map.w : null;
    const prod = summary?.product;
    const meta: [string, string][] = first
      ? [
          ["Project", first.project],
          ...(summary ? ([["Sensor · track", `${fmt.sensor(summary.sensor)} · ${summary.track_id}`]] as [string, string][]) : []),
          ...(prod
            ? ([
                ["Period", `${prod.first} → ${prod.last} (${prod.epochs} dates)`],
                ["Points", fmt.int(prod.n_points)],
                ["Confidence", prod.confidence ?? "–"],
                ["Product", `v${prod.version} (${prod.engine ?? ""})`],
              ] as [string, string][])
            : []),
          ...(visible.length > 1 ? ([["Also shown", visible.slice(1).map((l) => l.project).join(", ")]] as [string, string][]) : []),
        ]
      : [];
    const year = summary?.product?.last?.slice(0, 4) ?? "";
    const basemap = base === "none" ? "" : ` · Base map: ${BASES[base].attribution}`;
    const credit = summary ? `${SENSOR_CREDIT[summary.sensor] ?? ""} ${summary.sensor === "sentinel1" ? year : ""}`.trim() : "";
    // graticule: lines at nice degrees, placed with the map projection (exact in Web Mercator), in sheet units
    let ticks: SheetData["ticks"] = null;
    if (m && o.frame) {
      const b = m.getBounds();
      const step = graticuleStep(Math.max(b.getEast() - b.getWest(), b.getNorth() - b.getSouth()));
      const toX = (lon: number) => m.project([lon, b.getCenter().lat]).x / sp + L.map.x;
      const toY = (lat: number) => m.project([b.getCenter().lng, lat]).y / sp + L.map.y;
      const range = (a: number, z: number) => {
        const out: number[] = [];
        for (let v = Math.ceil(a / step) * step; v <= z + 1e-9; v += step) out.push(+v.toFixed(8));
        return out;
      };
      const inside = (u: number, lo: number, len: number) => u > lo + 6 && u < lo + len - 6;
      ticks = {
        lon: range(b.getWest(), b.getEast()).map((v) => ({ at: toX(v), label: degLabel(v, step, "E", "W") })).filter((k) => inside(k.at, L.map.x, L.map.w)),
        lat: range(b.getSouth(), b.getNorth()).map((v) => ({ at: toY(v), label: degLabel(v, step, "N", "S") })).filter((k) => inside(k.at, L.map.y, L.map.h)),
      };
    }
    const fm = firstData?.meta;
    const geometry =
      fm?.heading_deg != null && summary
        ? { heading: fm.heading_deg, look: fm.look_azimuth_deg ?? null, pass: summary.direction.toUpperCase() }
        : null;
    return {
      legend: firstData ? firstData.meta : null,
      legendTitle: "LOS velocity",
      ticks,
      geometry,
      meta,
      credits: `GeoEyes · ${new Date().toISOString().slice(0, 10)}${credit ? ` · ${credit}` : ""}${basemap}`,
      metresPerUnit,
    };
  }, [L, sp, summary, first, visible, base, firstData, o.frame]);

  // preview canvas over the live map (map rectangle transparent)
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.round(L.W * sp * dpr);
    c.height = Math.round(L.H * sp * dpr);
    const ctx = c.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawSheet(ctx, sp, L, o, sheetData(), null);
  }, [L, sp, o, sheetData, tick]);
  useEffect(() => {
    document.fonts?.ready.then(() => setTick((t) => t + 1));
  }, []);

  // ------------------------------------------------------------ export
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const outW = paper.screen ? paper.w : Math.round((paper.w / 25.4) * dpi);
  const outH = Math.round((outW * L.H) / L.W);
  const exportAs = async (kind: "png" | "pdf") => {
    const m = map.current;
    if (!m) return;
    setError("");
    setBusy(kind.toUpperCase());
    const s = outW / L.W;
    let shot: { canvas: HTMLCanvasElement; done: () => void } | null = null;
    try {
      if (L.map.w * s > 8192 || L.map.h * s > 8192) throw new Error("Too large for the graphics card: choose a lower resolution");
      shot = await renderMap(m, L.map.w * s, L.map.h * s, L.map.w * sp, mapStyle(base, o.theme === "light" ? "#f3f4f6" : "#0b1220"), deckLayers);
      const out = document.createElement("canvas");
      out.width = outW;
      out.height = outH;
      const ctx = out.getContext("2d")!;
      drawSheet(ctx, s, L, o, sheetData(), shot.canvas);
      const name = `${(first?.project ?? "map").replace(/[^\w-]+/g, "_")}_${paper.id}${paper.screen ? "" : `_${dpi}dpi`}`;
      if (kind === "png") {
        const blob = await new Promise<Blob | null>((r) => out.toBlob(r, "image/png"));
        if (!blob) throw new Error("PNG encoding failed");
        download(blob, `${name}.png`);
      } else {
        const blob = await new Promise<Blob | null>((r) => out.toBlob(r, "image/jpeg", 0.93));
        if (!blob) throw new Error("JPEG encoding failed");
        const jpeg = new Uint8Array(await blob.arrayBuffer());
        const pt = (mm: number) => (mm / 25.4) * 72;
        const [wPt, hPt] = paper.screen ? [outW * 0.75, outH * 0.75] : [pt(paper.w), pt(paper.h)];
        download(pdfFromJpeg(jpeg, outW, outH, wPt, hPt), `${name}.pdf`);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      shot?.done();
      setBusy("");
    }
  };

  if (!visible.length) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Panel className="max-w-md p-6 text-center">
          <div className="text-[15px] font-semibold">Nothing to put on the map</div>
          <p className="mt-2 text-[13px] text-muted">Show one or more products in the Explorer (eye in the project tree), then come back here.</p>
          <Button className="mt-4" onClick={() => go({ page: "explorer" })}>
            Go to the Explorer
          </Button>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="w-[300px] flex-none space-y-4 overflow-y-auto border-r border-line bg-panel-2 p-4">
        <div>
          <h1 className="text-[17px] font-semibold">Map image</h1>
          <p className="mt-1 text-[12px] text-muted">Pan and zoom the map inside the sheet, then export.</p>
        </div>
        <div className="space-y-2">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">SHEET</div>
          <select className={field} value={paperId} onChange={(e) => setPaperId(e.target.value)} aria-label="Format">
            {PAPERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          {!paper.screen && (
            <select className={field} value={dpi} onChange={(e) => setDpi(Number(e.target.value))} aria-label="Resolution">
              {[150, 200, 300].map((v) => (
                <option key={v} value={v}>
                  {v} dpi
                </option>
              ))}
            </select>
          )}
          <div className="text-[11.5px] text-faint">
            Export {outW} × {outH} px
          </div>
          <div className="flex gap-1.5">
            {(["light", "dark"] as const).map((th) => (
              <button
                key={th}
                type="button"
                aria-pressed={o.theme === th}
                onClick={() => set("theme", th)}
                className={`h-7 flex-1 rounded-md border text-[12px] capitalize ${o.theme === th ? "border-accent bg-raised text-ink" : "border-line-2 text-muted"}`}
              >
                {th} sheet
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">TEXT</div>
          <input className={field} value={o.title} onChange={(e) => set("title", e.target.value)} placeholder="Title (empty: none)" aria-label="Title" />
          <input className={field} value={o.subtitle} onChange={(e) => set("subtitle", e.target.value)} placeholder="Subtitle" aria-label="Subtitle" />
        </div>
        <div className="space-y-2">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">MAP</div>
          <select className={field} value={base} onChange={(e) => setBase(e.target.value as Base)} aria-label="Base map">
            {(["light", "dark", "satellite", "none"] as Base[]).map((b) => (
              <option key={b} value={b}>
                {b === "none" ? "No base map" : `${BASES[b].label} base map`}
              </option>
            ))}
          </select>
          <select className={field} value={o.legend} onChange={(e) => set("legend", e.target.value as Options["legend"])} aria-label="Legend">
            <option value="right">Legend beside the map</option>
            <option value="inside">Legend inside the map</option>
            <option value="none">No legend</option>
          </select>
          <Toggle label="Scale bar" on={o.scale} set={(v) => set("scale", v)} />
          <Toggle label="North arrow" on={o.north} set={(v) => set("north", v)} />
          <Toggle label="Coordinate frame (lon / lat)" on={o.frame} set={(v) => set("frame", v)} />
          <Toggle label="Satellite flight / look direction" on={o.geometry} set={(v) => set("geometry", v)} />
          <Toggle label="Product details" on={o.meta} set={(v) => set("meta", v)} />
          <Toggle label="Credits line" on={o.credits} set={(v) => set("credits", v)} />
        </div>
        <div className="space-y-2 border-t border-line pt-4">
          <Button variant="primary" className="w-full justify-center" disabled={!!busy} onClick={() => exportAs("png")}>
            {busy === "PNG" ? "Rendering…" : "Download PNG"}
          </Button>
          <Button className="w-full justify-center" disabled={!!busy} onClick={() => exportAs("pdf")}>
            {busy === "PDF" ? "Rendering…" : "Download PDF"}
          </Button>
          {error && <div className="text-[12px] text-bad">{error}</div>}
          <div className="text-[11.5px] leading-snug text-faint">
            Colours and classes as in QGIS and the reports. {visible.length > 1 ? "The legend is that of the first layer." : ""}
          </div>
        </div>
      </div>
      <div ref={area} className="flex min-w-0 flex-1 items-center justify-center overflow-hidden bg-[#070c16]">
        <div className="relative shadow-2xl shadow-black/60" style={{ width: L.W * sp, height: L.H * sp }}>
          <div className="absolute" style={{ left: L.map.x * sp, top: L.map.y * sp, width: L.map.w * sp, height: L.map.h * sp }}>
            <div ref={mapEl} className="h-full w-full" />
          </div>
          <canvas ref={canvas} className="pointer-events-none absolute inset-0" style={{ width: L.W * sp, height: L.H * sp }} />
        </div>
      </div>
    </div>
  );
}
