// Map composer: frame the products shown on the map on a sheet (title, legend, scale bar, north arrow, product
// details, credits) and export it as PNG or PDF at print resolution.
import { MapboxOverlay } from "@deck.gl/mapbox";
import { useQueries, useQuery } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, type Workspace } from "../api";
import { degLabel, drawSheet, graticuleStep, layout, metresPerPixel, PAPERS, pdfFromJpeg, type Options, type SheetData } from "../compose";
import { floodFeatures, floodLayers } from "../components/FloodReports";
import { HYDRO_CREDIT, hydroLayers, useHydro } from "../components/Hydro";
import { COMPOSE_SUBJECT, loadTheme, themeLayers, themeLegendSpec, themeTitle, useThemes, type ThemeData } from "../components/ThemeLayers";
import { BASES, loadLayer, mapStyle, productLayer, withRange, type Base, type LayerData } from "../map";
import { t, ts } from "../i18n";
import { layerRange, useApp } from "../state";
import { Button, fmt, Panel, usePersisted } from "../ui";

const field = "h-8 w-full rounded-md border border-line-2 bg-sunken px-2 text-[13px] text-ink focus:border-accent focus:outline-none";

function Toggle({ label, on, set }: { label: string; on: boolean; set: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-2">
      <input type="checkbox" className="h-4 w-4 accent-accent" checked={on} onChange={(e) => set(e.target.checked)} />
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

const CONFIDENCE: Record<string, () => string> = { high: () => t("high"), medium: () => t("medium"), low: () => t("low") };

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
      const timer = setTimeout(() => reject(new Error(t("The map took too long to render"))), 240_000);
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
  const { layers, go, toggleLayer, fixedRange } = useApp();
  const visible = layers.filter((l) => l.visible);
  // every output on the results map: the products, their thematic layers (analyses, machine learning), the reported
  // flood locations; one of them is the map's subject (title and legend)
  const th = useThemes();
  const themesOn = th.themes.filter((x) => x.visible);
  const themeQ = useQueries({
    queries: th.themes.map((x) => ({ queryKey: ["theme", x.key], queryFn: () => loadTheme(x), staleTime: 5 * 60_000, gcTime: 10 * 60_000 })),
  });
  const themeData: Record<string, ThemeData | undefined> = {};
  th.themes.forEach((x, i) => (themeData[x.key] = themeQ[i]?.data));
  const hazardQ = useQueries({
    queries: themesOn
      .filter((x) => x.kind === "hazard")
      .map((x) => ({ queryKey: ["avail-hazard", x.project, x.product], queryFn: () => api.hazard(x.project, x.product), staleTime: 60_000 })),
  });
  const [floodsOn, setFloodsOn] = usePersisted("explorer.floods", false);
  const floodsQ = useQuery({ queryKey: ["floods"], queryFn: api.floods, enabled: floodsOn, staleTime: 60_000 });
  const floodShown = useMemo(() => (floodsOn ? floodFeatures(floodsQ.data, false) : []), [floodsOn, floodsQ.data]);
  // river network and watersheds under the products (the same switch as on the results map)
  const [hydroOn, setHydroOn] = usePersisted("explorer.hydro", false);
  const [subjectKey, setSubjectKey] = useState(() => {
    try {
      return sessionStorage.getItem(COMPOSE_SUBJECT) ?? "";
    } catch {
      return "";
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem(COMPOSE_SUBJECT, subjectKey);
    } catch {
      /* storage unavailable */
    }
  }, [subjectKey]);
  const subjectTheme = themesOn.find((x) => x.key === subjectKey) ?? null;
  const subjectProduct = subjectTheme ? null : (visible.find((l) => l.key === subjectKey) ?? visible[0] ?? null);
  // the details and credits follow the subject's product
  const first = subjectProduct ?? (subjectTheme ? { key: `${subjectTheme.project}/${subjectTheme.product}`, project: subjectTheme.project, product: subjectTheme.product } : visible[0]);
  const summary = first ? ws?.projects[first.project]?.tracks.find((t) => t.product?.id === first.product) : undefined;
  const [paperId, setPaperId] = useState("a4l");
  const [dpi, setDpi] = useState(300);
  const [base, setBase] = useState<Base>("light");
  // the title follows the subject until it is edited
  const autoTitle = subjectTheme ? `${themeTitle(subjectTheme)} — ${subjectTheme.project}` : first ? t("Ground motion — {project}", { project: first.project }) : t("Ground motion");
  const [o, setO] = useState<Options>({
    title: autoTitle,
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
  const lastAuto = useRef(autoTitle);
  useEffect(() => {
    setO((x) => (x.title === lastAuto.current ? { ...x, title: autoTitle } : x));
    lastAuto.current = autoTitle;
  }, [autoTitle]);
  const paper = PAPERS.find((p) => p.id === paperId)!;
  const L = useMemo(() => layout(paper, o), [paper, o]);

  const data = useQueries({
    queries: visible.map((l) => ({
      // the velocity kind chosen on the results map (same cache entry as there, uncalibrated)
      queryKey: ["layer", l.key, l.mode ?? "auto", { cal: false, vel: l.vel === undefined ? "default" : l.vel }],
      queryFn: () => loadLayer(l.project, l.product, l.mode ?? "auto", false, l.vel),
      staleTime: Infinity,
      gcTime: 10 * 60_000,
    })),
  });
  const byKey = useMemo(() => {
    const m: Record<string, LayerData | undefined> = {};
    // the colour range chosen on the results map
    visible.forEach((l, i) => {
      const d = data[i]?.data;
      m[l.key] = d && withRange(d, layerRange(l, fixedRange));
    });
    return m;
  }, [visible, data, fixedRange]);
  const firstData = first ? byKey[first.key] : undefined;

  // the subtitle (sensor, period) follows the subject's product until it is edited; a thematic subject: no "LOS velocity"
  const autoSub = (() => {
    const p = summary?.product;
    if (!summary || !p) return "";
    const dir = summary.direction === "ascending" ? t("ascending") : summary.direction === "descending" ? t("descending") : summary.direction;
    const v = { sensor: fmt.sensor(summary.sensor), direction: dir, first: p.first, last: p.last, n: p.epochs };
    return subjectTheme
      ? t("{sensor} {direction} · {first} → {last} ({n} acquisitions)", v)
      : t("{sensor} {direction} · LOS velocity {first} → {last} ({n} acquisitions)", v);
  })();
  const lastSub = useRef("");
  useEffect(() => {
    setO((x) => (!x.subtitle || x.subtitle === lastSub.current ? { ...x, subtitle: autoSub } : x));
    lastSub.current = autoSub;
  }, [autoSub]);

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
  const hydro = useHydro(map, tick > 0, hydroOn);
  const hydroShown = hydroOn && !!(hydro.rivers?.features.length || hydro.basins?.features.length);
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
    const bs = [
      ...(Object.values(byKey).filter(Boolean) as LayerData[]).map((d) => d.meta.bounds),
      ...themesOn.map((x) => themeData[x.key]?.bounds).filter((b): b is [number, number, number, number] => !!b),
    ];
    if (!bs.length) return;
    const b = bs.reduce((a, c) => [Math.min(a[0], c[0]), Math.min(a[1], c[1]), Math.max(a[2], c[2]), Math.max(a[3], c[3])], [180, 90, -180, -90]);
    map.current.resize();
    map.current.fitBounds([b[0], b[1], b[2], b[3]], { padding: 24, duration: 0 });
    fitted.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [byKey, themeQ.map((q) => q.dataUpdatedAt).join()]);

  const deckLayers = useCallback(
    (pixelScale = 1) =>
      [
        // rivers and watersheds at the bottom, under the points
        ...(hydroShown
          ? hydroLayers(hydro.rivers?.features ?? [], hydro.basins?.features ?? [], { three: false, extensions: [], pixelScale, idPrefix: `c${pixelScale}-` })
          : []),
        ...[...visible].reverse().flatMap((l) => {
          const d = byKey[l.key];
          return d ? [productLayer(l, d, { pickable: false, pixelScale, idPrefix: `c${pixelScale}-` })] : [];
        }),
        // the thematic layers over the points, as on the results map; the flood reports on top
        ...themeLayers(themesOn, themeData, null, () => {}),
        ...(floodShown.length ? floodLayers(floodShown, { selected: null, onPick: () => {}, three: false, extensions: [] }) : []),
      ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visible, byKey, themesOn.map((x) => `${x.key}${x.view}${x.horizon}${x.opacity}`).join(), themeQ.map((q) => q.dataUpdatedAt).join(), floodShown, hydroShown, hydro.rivers, hydro.basins],
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
          [t("Project"), first.project],
          ...(summary ? ([[t("Sensor · track"), `${fmt.sensor(summary.sensor)} · ${summary.track_id}`]] as [string, string][]) : []),
          ...(prod
            ? ([
                [t("Period"), t("{first} → {last} ({n} dates)", { first: prod.first, last: prod.last, n: prod.epochs })],
                [t("Points"), fmt.int(prod.n_points)],
                [t("Confidence"), prod.confidence ? (CONFIDENCE[prod.confidence]?.() ?? prod.confidence) : "–"],
                [t("Product"), `v${prod.version} (${prod.engine ?? ""})`],
              ] as [string, string][])
            : []),
          ...(subjectTheme ? ([[t("Layer"), themeTitle(subjectTheme)]] as [string, string][]) : []),
          ...(() => {
            const others = [
              ...visible.filter((l) => l.key !== subjectProduct?.key).map((l) => `${t("LOS velocity")} · ${l.project}`),
              ...themesOn.filter((x) => x.key !== subjectTheme?.key).map((x) => `${themeTitle(x)} · ${x.project}`),
              ...(floodShown.length ? [t("{n} reported flood locations", { n: floodShown.length })] : []),
              ...(hydroShown ? [t("rivers and watersheds")] : []),
            ];
            return others.length ? ([[t("Also shown"), others.join(", ")]] as [string, string][]) : [];
          })(),
        ]
      : [];
    const hz = subjectTheme?.kind === "hazard" ? hazardQ[themesOn.filter((x) => x.kind === "hazard").findIndex((x) => x.key === subjectTheme.key)]?.data?.summary : undefined;
    const sd = subjectTheme ? themeData[subjectTheme.key] : undefined;
    const spec = subjectTheme && sd ? themeLegendSpec(subjectTheme, sd, hz ?? undefined) : null;
    const year = summary?.product?.last?.slice(0, 4) ?? "";
    const basemap = base === "none" ? "" : ` · ${t("Base map: {attribution}", { attribution: BASES[base].attribution })}`;
    const credit = summary ? `${SENSOR_CREDIT[summary.sensor] ? t(SENSOR_CREDIT[summary.sensor]) : ""} ${summary.sensor === "sentinel1" ? year : ""}`.trim() : "";
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
        ? { heading: fm.heading_deg, look: fm.look_azimuth_deg ?? null, pass: (summary.direction === "ascending" ? t("ascending") : summary.direction === "descending" ? t("descending") : summary.direction).toUpperCase() }
        : null;
    return {
      legend: firstData && !subjectTheme ? firstData.meta : null,
      legendTitle: t("LOS velocity"),
      spec,
      ticks,
      geometry,
      meta,
      credits: `GeoEyes · ${new Date().toISOString().slice(0, 10)}${credit ? ` · ${credit}` : ""}${basemap}${hydroShown ? ` · ${t(HYDRO_CREDIT)}` : ""}`,
      metresPerUnit,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [L, sp, summary, first?.key, visible, base, firstData, o.frame, subjectTheme?.key, subjectTheme?.view, subjectTheme?.horizon, themeQ.map((q) => q.dataUpdatedAt).join(), hazardQ.map((q) => q.dataUpdatedAt).join(), floodShown.length, themesOn.length, hydroShown]);

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
      if (L.map.w * s > 8192 || L.map.h * s > 8192) throw new Error(t("Too large for the graphics card: choose a lower resolution"));
      shot = await renderMap(m, L.map.w * s, L.map.h * s, L.map.w * sp, mapStyle(base, o.theme === "light" ? "#f3f4f6" : "#0b1220"), deckLayers);
      const out = document.createElement("canvas");
      out.width = outW;
      out.height = outH;
      const ctx = out.getContext("2d")!;
      drawSheet(ctx, s, L, o, sheetData(), shot.canvas);
      const name = `${(first?.project ?? "map").replace(/[^\w-]+/g, "_")}_${paper.id}${paper.screen ? "" : `_${dpi}dpi`}`;
      if (kind === "png") {
        const blob = await new Promise<Blob | null>((r) => out.toBlob(r, "image/png"));
        if (!blob) throw new Error(t("PNG encoding failed"));
        download(blob, `${name}.png`);
      } else {
        const blob = await new Promise<Blob | null>((r) => out.toBlob(r, "image/jpeg", 0.93));
        if (!blob) throw new Error(t("JPEG encoding failed"));
        const jpeg = new Uint8Array(await blob.arrayBuffer());
        const pt = (mm: number) => (mm / 25.4) * 72;
        const [wPt, hPt] = paper.screen ? [outW * 0.75, outH * 0.75] : [pt(paper.w), pt(paper.h)];
        download(pdfFromJpeg(jpeg, outW, outH, wPt, hPt), `${name}.pdf`);
      }
    } catch (e) {
      setError(ts((e as Error).message));
    } finally {
      shot?.done();
      setBusy("");
    }
  };

  if (!visible.length && !themesOn.length) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Panel className="max-w-md p-6 text-center">
          <div className="text-[15px] font-semibold">{t("Nothing to put on the map")}</div>
          <p className="mt-2 text-[13px] text-muted">{t("Show one or more products in the Explorer (eye in the project tree), then come back here.")}</p>
          <Button className="mt-4" onClick={() => go({ page: "explorer" })}>
            {t("Go to the Explorer")}
          </Button>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="w-[300px] flex-none space-y-4 overflow-y-auto border-r border-line bg-panel-2 p-4">
        <div>
          <h1 className="text-[17px] font-semibold">{t("Map export")}</h1>
          <p className="mt-1 text-[12px] text-muted">{t("Pan and zoom the map inside the sheet, then export.")}</p>
        </div>
        <div className="space-y-2">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("SHEET")}</div>
          <select className={field} value={paperId} onChange={(e) => setPaperId(e.target.value)} aria-label={t("Format")}>
            {PAPERS.map((p) => (
              <option key={p.id} value={p.id}>
                {t(p.label)}
              </option>
            ))}
          </select>
          {!paper.screen && (
            <select className={field} value={dpi} onChange={(e) => setDpi(Number(e.target.value))} aria-label={t("Resolution")}>
              {[150, 200, 300].map((v) => (
                <option key={v} value={v}>
                  {v} dpi
                </option>
              ))}
            </select>
          )}
          <div className="text-[11.5px] text-faint">
            {t("Export {w} × {h} px", { w: outW, h: outH })}
          </div>
          <div className="flex gap-1.5">
            {(["light", "dark"] as const).map((th) => (
              <button
                key={th}
                type="button"
                aria-pressed={o.theme === th}
                onClick={() => set("theme", th)}
                className={`h-7 flex-1 rounded-md border text-[12px] first-letter:uppercase ${o.theme === th ? "border-accent bg-raised text-ink" : "border-line-2 text-muted"}`}
              >
                {th === "light" ? t("light sheet") : t("dark sheet")}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1.5">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("LAYERS")}</div>
          <p className="text-[11.5px] leading-snug text-faint">{t("The layers of the results map. ◉ is the map's subject: its legend and title go on the sheet.")}</p>
          {[
            ...layers.map((l) => ({ key: l.key, label: `${t("LOS velocity")} · ${l.project}`, on: l.visible, toggle: () => toggleLayer(l.key), subject: l.visible })),
            ...th.themes.map((x) => ({ key: x.key, label: `${themeTitle(x)} · ${x.project}`, on: x.visible, toggle: () => th.update(x.key, { visible: !x.visible }), subject: x.visible })),
          ].map((r) => {
            const isSubject = r.key === (subjectTheme?.key ?? subjectProduct?.key);
            return (
              <div key={r.key} className="flex items-center gap-2 text-[12.5px]">
                <input type="checkbox" className="h-4 w-4 flex-none accent-accent" checked={r.on} onChange={r.toggle} aria-label={r.label} />
                <span className={`min-w-0 flex-1 truncate ${r.on ? "text-ink-2" : "text-faint"}`} title={r.label}>
                  {r.label}
                </span>
                <button
                  type="button"
                  disabled={!r.subject}
                  aria-pressed={isSubject}
                  title={t("Map subject: its legend and title")}
                  onClick={() => setSubjectKey(r.key)}
                  className={`flex-none text-[14px] leading-none ${isSubject ? "text-accent" : "text-faint hover:text-ink"} disabled:opacity-30`}
                >
                  {isSubject ? "◉" : "○"}
                </button>
              </div>
            );
          })}
          <Toggle label={t("Reported flood locations")} on={floodsOn} set={setFloodsOn} />
          <Toggle label={t("Rivers and watersheds")} on={hydroOn} set={setHydroOn} />
          {hydroOn && (hydro.loading || hydro.error || hydro.tooWide) && (
            <div className={`text-[11px] ${hydro.error ? "text-bad" : "text-muted"}`}>
              {hydro.tooWide ? t("Zoom in: rivers and watersheds are shown over views up to 6°") : hydro.error ? ts(hydro.error.message) : t("Reading the rivers and watersheds of the view… (a minute the first time)")}
            </div>
          )}
          <button type="button" className="text-[12px] text-accent hover:underline" onClick={() => go({ page: "explorer" })}>
            {t("Add layers on the results map")} →
          </button>
        </div>
        <div className="space-y-2">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("TEXT")}</div>
          <input className={field} value={o.title} onChange={(e) => set("title", e.target.value)} placeholder={t("Title (empty: none)")} aria-label={t("Title")} />
          <input className={field} value={o.subtitle} onChange={(e) => set("subtitle", e.target.value)} placeholder={t("Subtitle")} aria-label={t("Subtitle")} />
        </div>
        <div className="space-y-2">
          <div className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("MAP")}</div>
          <select className={field} value={base} onChange={(e) => setBase(e.target.value as Base)} aria-label={t("Base map")}>
            {(["light", "dark", "satellite", "none"] as Base[]).map((b) => (
              <option key={b} value={b}>
                {b === "none" ? t("No base map") : t("{label} base map", { label: t(BASES[b].label) })}
              </option>
            ))}
          </select>
          <select className={field} value={o.legend} onChange={(e) => set("legend", e.target.value as Options["legend"])} aria-label={t("Legend")}>
            <option value="right">{t("Legend beside the map")}</option>
            <option value="inside">{t("Legend inside the map")}</option>
            <option value="none">{t("No legend")}</option>
          </select>
          <Toggle label={t("Scale bar")} on={o.scale} set={(v) => set("scale", v)} />
          <Toggle label={t("North arrow")} on={o.north} set={(v) => set("north", v)} />
          <Toggle label={t("Coordinate frame (lon / lat)")} on={o.frame} set={(v) => set("frame", v)} />
          <Toggle label={t("Satellite flight / look direction")} on={o.geometry} set={(v) => set("geometry", v)} />
          <Toggle label={t("Product details")} on={o.meta} set={(v) => set("meta", v)} />
          <Toggle label={t("Credits line")} on={o.credits} set={(v) => set("credits", v)} />
        </div>
        <div className="space-y-2 border-t border-line pt-4">
          <Button variant="primary" className="w-full justify-center" disabled={!!busy} onClick={() => exportAs("png")}>
            {busy === "PNG" ? t("Rendering…") : t("Download PNG")}
          </Button>
          <Button className="w-full justify-center" disabled={!!busy} onClick={() => exportAs("pdf")}>
            {busy === "PDF" ? t("Rendering…") : t("Download PDF")}
          </Button>
          {error && <div className="text-[12px] text-bad">{error}</div>}
          <div className="text-[11.5px] leading-snug text-faint">
            {t("Colours and classes as on the results map, in QGIS and in the reports.")} {visible.length + themesOn.length > 1 ? t("The legend is that of the map's subject (◉).") : ""}
          </div>
        </div>
      </div>
      <div ref={area} className="flex min-w-0 flex-1 items-center justify-center overflow-hidden bg-deep">
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
