// Open-data hub: every repeat-pass stack of the open SAR STAC catalogs (ICEYE, Capella, Umbra), listed by place and
// drawn on the map without searching (the server indexes the catalogs by itself); choose one, adjust the proposed area
// if needed, and a project on it is created (its acquire phase downloads the scenes, ICEYE: only the area).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type OpenDataStack, type Workspace } from "../api";
import { BasemapPicker } from "../components/BasemapPicker";
import { t, ts } from "../i18n";
import { baseSource, DEFAULT_BASE, switchBase, type Base } from "../map";
import { useApp } from "../state";
import { Button, Panel } from "../ui";

const fieldSm = "h-9 rounded-md border border-line-2 bg-sunken px-2.5 text-[13px] text-ink focus:border-accent focus:outline-none";
const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const COLOR: Record<string, string> = { iceye: "#1f7fd6", capella: "#e08a00", umbra: "#9b59d0" };
const FP = "stacks";
const PTS = "stack-points";
const SEL = "selected";
const AOI = "aoi";

const ring = (r: [number, number][]) => ({ type: "Polygon" as const, coordinates: [r] });
const rect = (b: number[]): [number, number][] => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]];
const fc = (features: unknown[]) => ({ type: "FeatureCollection" as const, features }) as GeoJSON.FeatureCollection;
const centre = (s: OpenDataStack): [number, number] => [(s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2];
const r5 = (v: number) => Math.round(v * 1e5) / 1e5;

function inside(b: number[] | null, s: OpenDataStack): boolean {
  return !!b && b[0] >= s.bbox[0] && b[1] >= s.bbox[1] && b[2] <= s.bbox[2] && b[3] <= s.bbox[3];
}

/** Proposed area, cut on download: ICEYE ~3 km, Umbra (0.15 m pixels) ~150 m around the centre; Capella (whole
 * scenes downloaded) most of the footprint. */
const HALF_DEG: Record<string, number> = { iceye: 0.015, umbra: 0.0008 };
function defaultAoi(s: OpenDataStack): number[] {
  const [w, so, e, n] = s.bbox;
  const [cx, cy] = centre(s);
  const shrink = 0.1;
  const inner = [w + (e - w) * shrink, so + (n - so) * shrink, e - (e - w) * shrink, n - (n - so) * shrink];
  const half = HALF_DEG[s.source];
  if (!half) return inner.map(r5);
  const hx = half / Math.cos((cy * Math.PI) / 180);
  return [Math.max(inner[0], cx - hx), Math.max(inner[1], cy - half), Math.min(inner[2], cx + hx), Math.min(inner[3], cy + half)].map(r5);
}

/** Megabytes per date of a cut: ground area with the default margin, slant-range pixels. ICEYE: 1.5 x 0.9 m,
 * amplitude + phase uint16 (~0.9 after compression), 500 m margin; Umbra: ~0.155 x 0.137 m, complex float32, 50 m. */
const CUT: Record<string, { margin: number; az: number; rg: number; bytes: number }> = {
  iceye: { margin: 500, az: 1.5, rg: 0.9, bytes: 4 * 0.9 },
  umbra: { margin: 50, az: 0.155, rg: 0.137, bytes: 8 },
};
function cutMb(b: number[], s: OpenDataStack): number | null {
  const c = CUT[s.source];
  if (!c) return null;
  const lat = ((b[1] + b[3]) / 2) * (Math.PI / 180);
  const ns = (b[3] - b[1]) * 111e3 + 2 * c.margin;
  const ew = (b[2] - b[0]) * 111e3 * Math.cos(lat) + 2 * c.margin;
  const inc = (((s.incidence?.[0] ?? 30) + (s.incidence?.[1] ?? 30)) / 2) * (Math.PI / 180);
  return ((ns / c.az) * ((ew * Math.sin(inc)) / c.rg) * c.bytes) / 1e6;
}
const LITE = new Set(["capella", "umbra"]);                    // short spotlight stacks: ps_lite (ADR-020)

function slug(s: OpenDataStack): string {
  const place = (s.place ?? "").split(",")[0].normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const head = place.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
  return `${head || s.source}_${s.source}`.replace(/^_/, "");
}

function where(s: OpenDataStack): string {
  const [x, y] = centre(s);
  return `${Math.abs(y).toFixed(2)}°${y >= 0 ? "N" : "S"} ${Math.abs(x).toFixed(2)}°${x >= 0 ? "E" : "W"}`;
}

function Timeline({ s }: { s: OpenDataStack }) {
  const t0 = Date.parse(s.first);
  const span = Math.max(Date.parse(s.last) - t0, 86400e3);
  return (
    <div className="relative mt-2 h-5 rounded bg-sunken" role="img" aria-label={t("{n} acquisition dates", { n: s.n_dates })}>
      {s.scenes.map((x) => (
        <span
          key={x.id}
          title={`${x.date} · ${x.platform}${x.incidence != null ? ` · ${x.incidence.toFixed(1)}°` : ""}`}
          className="absolute top-1 h-3 w-[3px] rounded-sm"
          style={{ left: `calc(${((Date.parse(x.date) - t0) / span) * 100}% - 1px)`, background: COLOR[s.source] ?? "#93a4bf" }}
        />
      ))}
    </div>
  );
}

export function OpenData({ ws }: { ws: Workspace | undefined }) {
  const { go } = useApp();
  const qc = useQueryClient();
  const [base, setBase] = useState<Base>(DEFAULT_BASE);
  const [filter, setFilter] = useState("");
  const [source, setSource] = useState("");
  const [mode, setMode] = useState("");
  const [area, setArea] = useState<number[] | null>(null);       // optional search area
  const [supported, setSupported] = useState(true);
  const [sel, setSel] = useState<string | null>(null);
  const [aoi, setAoi] = useState<number[] | null>(null);         // project area of the selected stack
  const [drawing, setDrawing] = useState<"" | "aoi" | "area">("");
  const [name, setName] = useState("");
  const [method, setMethod] = useState("psi");
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const corner = useRef<maplibregl.LngLat | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // the server indexes the catalogs by itself (first visit, then daily): poll while it does
  const sources = useQuery({
    queryKey: ["opendata-sources"],
    queryFn: api.opendataSources,
    refetchInterval: (q) => (q.state.data?.sync.running ? 2000 : false),
  });
  const syncing = sources.data?.sync.running ?? false;
  const wasSyncing = useRef(false);
  useEffect(() => {
    if (wasSyncing.current && !syncing) qc.invalidateQueries({ queryKey: ["opendata-stacks"] });
    wasSyncing.current = syncing;
  }, [syncing, qc]);
  const sync = useMutation({
    mutationFn: () => api.opendataSync(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["opendata-sources"] }),
  });
  const indexed = (sources.data?.sources ?? []).some((s) => s.scenes > 0);
  const q = { bbox: area, source, mode, min_scenes: 3, supported };
  const stacks = useQuery({
    queryKey: ["opendata-stacks", q],
    queryFn: () => api.opendataStacks(q),
    enabled: indexed,
    refetchInterval: syncing ? 8000 : false,                      // place names arrive after the scenes
  });
  const all = stacks.data?.stacks ?? [];
  const list = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return f ? all.filter((s) => `${s.place ?? ""} ${s.id} ${s.platforms.join(" ")}`.toLowerCase().includes(f)) : all;
  }, [all, filter]);
  const chosen = all.find((s) => s.id === sel) ?? null;
  const exists = !!ws?.projects[name];
  const nameOk = NAME_RE.test(name) && !exists;

  const choose = (id: string | null) => {
    setSel(id);
    const s = all.find((x) => x.id === id);
    if (!s) return;
    setAoi(defaultAoi(s));
    let n = slug(s);
    for (let k = 2; ws?.projects[n]; k++) n = `${slug(s)}_${k}`;
    setName(n);
    setTimeout(() => cardRefs.current[s.id]?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 50);
  };

  const create = useMutation({
    mutationFn: (s: OpenDataStack) =>
      api.createProject({
        name,
        description: `${s.place || where(s)}: ${t("open-data stack")} ${s.id} (${s.first}..${s.last})`,
        method: LITE.has(s.sensor ?? "") ? "ps_lite" : method,
        track: { sensor: s.sensor!, direction: s.orbit_state },
        bbox: aoi,
        opendata: s.id,
        atmosphere: "none",
      }),
    onSuccess: ({ name }) => {
      qc.invalidateQueries({ queryKey: ["workspace"] });
      go({ page: "project", name, tab: "pipeline" });
    },
  });

  // ------------------------------------------------------------ map
  useEffect(() => {
    if (!mapEl.current) return;
    const m = new maplibregl.Map({
      container: mapEl.current,
      style: {
        version: 8,
        sources: {
          base: baseSource(DEFAULT_BASE),
          [FP]: { type: "geojson", data: fc([]) },
          [PTS]: { type: "geojson", data: fc([]) },
          [SEL]: { type: "geojson", data: fc([]) },
          [AOI]: { type: "geojson", data: fc([]) },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#d9dde3" } },
          { id: "base", type: "raster", source: "base" },
          { id: "fp-fill", type: "fill", source: FP, minzoom: 6, paint: { "fill-color": ["get", "color"], "fill-opacity": 0.15 } },
          { id: "fp-line", type: "line", source: FP, minzoom: 6, paint: { "line-color": ["get", "color"], "line-width": 1.2 } },
          { id: "sel-line", type: "line", source: SEL, paint: { "line-color": "#d62828", "line-width": 2.5 } },
          {
            id: "pts",
            type: "circle",
            source: PTS,
            paint: {
              "circle-color": ["get", "color"],
              "circle-radius": ["interpolate", ["linear"], ["get", "n"], 3, 5, 20, 8, 100, 12],
              "circle-stroke-color": ["case", ["get", "on"], "#d62828", "#ffffff"],
              "circle-stroke-width": ["case", ["get", "on"], 3, 1.5],
              "circle-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.95, 11, 0.25],
              "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 8, 1, 11, 0.3],
            },
          },
          { id: "aoi-fill", type: "fill", source: AOI, paint: { "fill-color": "#d62828", "fill-opacity": 0.12 } },
          { id: "aoi-line", type: "line", source: AOI, paint: { "line-color": "#d62828", "line-width": 1.8, "line-dasharray": [2, 1] } },
        ],
      },
      center: [0, 20],
      zoom: 1.3,
      dragRotate: false,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    m.on("load", () => setMapReady(true));
    for (const layer of ["pts", "fp-fill"]) {
      m.on("mouseenter", layer, () => m.getCanvas().style.cursor !== "crosshair" && (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", layer, () => m.getCanvas().style.cursor !== "crosshair" && (m.getCanvas().style.cursor = ""));
    }
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (m && mapReady) switchBase(m, base);
  }, [base, mapReady]);

  // click on a stack (point or footprint), unless an area is being drawn
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady) return;
    const click = (e: maplibregl.MapLayerMouseEvent) => {
      if (drawing) return;
      const id = e.features?.[0]?.properties?.id;
      if (id) choose(String(id));
    };
    m.on("click", "pts", click);
    m.on("click", "fp-fill", click);
    return () => {
      m.off("click", "pts", click);
      m.off("click", "fp-fill", click);
    };
  }); // re-bound each render: `choose` reads the current list

  // first view: all the stacks listed
  const fitted = useRef(false);
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady || fitted.current || !all.length) return;
    fitted.current = true;
    const xs = all.map((s) => centre(s)[0]);
    const ys = all.map((s) => centre(s)[1]);
    m.resize();                                                  // the panel may have settled after the map
    m.fitBounds([Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)], { padding: 60, maxZoom: 6, duration: 0 });
  }, [all, mapReady]);

  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady) return;
    (m.getSource(FP) as maplibregl.GeoJSONSource).setData(
      fc(list.map((s) => ({ type: "Feature", properties: { id: s.id, color: COLOR[s.source] ?? "#93a4bf" }, geometry: ring(s.footprint) }))),
    );
    (m.getSource(PTS) as maplibregl.GeoJSONSource).setData(
      fc(
        list.map((s) => ({
          type: "Feature",
          properties: { id: s.id, color: COLOR[s.source] ?? "#93a4bf", n: s.n_dates, on: s.id === sel },
          geometry: { type: "Point", coordinates: centre(s) },
        })),
      ),
    );
  }, [list, sel, mapReady]);

  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady) return;
    (m.getSource(SEL) as maplibregl.GeoJSONSource).setData(fc(chosen ? [{ type: "Feature", properties: {}, geometry: ring(chosen.footprint) }] : []));
    if (chosen) m.fitBounds(chosen.bbox as [number, number, number, number], { padding: 80, maxZoom: 12, duration: 700 });
  }, [chosen?.id, mapReady]); // eslint-disable-line react-hooks/exhaustive-deps

  const drawBox = (b: number[] | null) =>
    (map.current?.getSource(AOI) as maplibregl.GeoJSONSource | undefined)?.setData(fc(b ? [{ type: "Feature", properties: {}, geometry: ring(rect(b)) }] : []));
  const shown = chosen ? aoi : area;
  useEffect(() => {
    if (mapReady) drawBox(shown);
  }, [shown, mapReady]);

  useEffect(() => {
    const m = map.current;
    if (!m || !drawing) return;
    m.getCanvas().style.cursor = "crosshair";
    corner.current = null;
    const box = (a: maplibregl.LngLat, b: maplibregl.LngLat) =>
      [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)].map(r5);
    const click = (e: maplibregl.MapMouseEvent) => {
      if (!corner.current) corner.current = e.lngLat;
      else {
        const b = box(corner.current, e.lngLat);
        if (drawing === "aoi") setAoi(b);
        else setArea(b);
        corner.current = null;
        setDrawing("");
      }
    };
    const move = (e: maplibregl.MapMouseEvent) => corner.current && drawBox(box(corner.current, e.lngLat));
    m.on("click", click);
    m.on("mousemove", move);
    return () => {
      m.off("click", click);
      m.off("mousemove", move);
      m.getCanvas().style.cursor = "";
    };
  }, [drawing]);

  const log = sources.data?.sync.log ?? [];
  const syncError = sync.error ? (sync.error as Error).message : sources.data?.sync.error;
  const counts = useMemo(() => Object.fromEntries((sources.data?.sources ?? []).map((s) => [s.source, s])), [sources.data]);

  return (
    <div className="flex h-full min-h-0 flex-wrap">
      <div className="flex h-full min-w-0 flex-[1_1_460px] flex-col">
        <div className="flex-none border-b border-line p-4">
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="text-[20px] font-semibold">{t("Open data")}</h1>
            <span className="text-[12.5px] text-muted">
              {indexed ? t("{n} stack(s) ready to process", { n: all.filter((s) => s.supported).length }) : ""}
            </span>
            <button
              type="button"
              className="ml-auto text-[12px] text-muted hover:text-ink disabled:opacity-50"
              disabled={syncing || sync.isPending}
              onClick={() => sync.mutate()}
              title={t("Read the catalogs again (done by itself once a day)")}
            >
              {syncing ? t("Updating the list…") : t("Refresh the list")}
            </button>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-faint">
            {(sources.data?.sources ?? []).map((s) => (
              <a key={s.source} href={s.homepage} target="_blank" rel="noopener" className="text-faint no-underline hover:text-ink">
                <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: COLOR[s.source] }} aria-hidden />
                {s.title} · {t("{n} scenes", { n: s.scenes })}
                {!s.sensor && ` · ${t("search only")}`}
              </a>
            ))}
            {sources.data?.sources[0]?.synced && <span>{t("updated {date}", { date: sources.data.sources[0].synced.slice(0, 16).replace("T", " ") })}</span>}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input className={`${fieldSm} w-48`} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("Place, satellite…")} aria-label={t("Filter")} />
            <select className={fieldSm} value={source} onChange={(e) => setSource(e.target.value)} aria-label={t("Source")}>
              <option value="">{t("All sources")}</option>
              {(sources.data?.sources ?? []).map((s) => (
                <option key={s.source} value={s.source}>
                  {s.title}
                </option>
              ))}
            </select>
            <select className={fieldSm} value={mode} onChange={(e) => setMode(e.target.value)} aria-label={t("Mode")}>
              <option value="">{t("All modes")}</option>
              {["stripmap", "spotlight", "sliding_spotlight"].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <Button variant={drawing === "area" ? "primary" : "ghost"} onClick={() => (setSel(null), setDrawing((d) => (d === "area" ? "" : "area")))}>
              {area ? t("Other area") : t("Only over an area")}
            </Button>
            {area && (
              <button type="button" className="text-[12px] text-muted hover:text-ink" onClick={() => setArea(null)}>
                {t("whole world")}
              </button>
            )}
            <label className="flex items-center gap-1.5 text-[12px] text-ink-2">
              <input type="checkbox" checked={supported} onChange={(e) => setSupported(e.target.checked)} />
              {t("Only stacks GeoEyes can process")}
            </label>
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
          {!indexed && (
            <Panel className="p-4">
              <div className="text-[13.5px] font-medium">{syncing ? t("Fetching the list of open data…") : t("No open data listed yet.")}</div>
              <div className="mt-1 text-[12.5px] text-muted">{t("GeoEyes reads the ICEYE, Capella and Umbra catalogs (about two minutes the first time).")}</div>
              {log.length > 0 && <pre className="mt-3 max-h-40 overflow-y-auto rounded bg-sunken p-2 font-mono text-[11px] text-ink-2">{log.slice(-10).join("\n")}</pre>}
            </Panel>
          )}
          {syncError && <div className="text-[12px] text-bad">{ts(syncError)}</div>}
          {stacks.error && <div className="text-[12px] text-bad">{ts((stacks.error as Error).message)}</div>}
          {indexed && list.length === 0 && !stacks.isFetching && <div className="text-[13px] text-muted">{t("No stack matches these filters.")}</div>}
          {list.map((s) => {
            const on = s.id === sel;
            const mb = on && aoi ? cutMb(aoi, s) : null;
            return (
              <div
                key={s.id}
                ref={(el) => (cardRefs.current[s.id] = el)}
                className={`rounded-lg border p-3 ${on ? "border-accent bg-accent-bg" : "border-line bg-panel hover:bg-panel-3"}`}
              >
                <button type="button" className="w-full text-left" onClick={() => (on ? setSel(null) : choose(s.id))} aria-expanded={on}>
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: COLOR[s.source] }} aria-hidden />
                    <span className="text-[14px] font-semibold text-ink">{s.place || where(s)}</span>
                    <span className="text-[12px] text-muted">
                      {counts[s.source]?.title ?? s.source} · {s.platforms.map((p) => p.toUpperCase()).join(", ")}
                    </span>
                    <span className="ml-auto text-[13px] font-semibold">{t("{n} dates", { n: s.n_dates })}</span>
                  </div>
                  <div className="mt-1 text-[12px] text-ink-2">
                    {s.first} → {s.last} · {t("every {d} d", { d: s.median_gap_days ?? "–" })} · {s.mode} · {t(s.orbit_state)} · {t(`${s.look}-looking`)}
                    {s.incidence && ` · ${s.incidence[0].toFixed(0)}–${s.incidence[1].toFixed(0)}°`}
                    {!s.supported && ` · ${t("search only ({product})", { product: s.product })}`}
                  </div>
                  <Timeline s={s} />
                </button>
                {on && s.supported && (
                  <div className="mt-3 space-y-2 border-t border-line pt-3">
                    <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
                      <span className="text-ink-2">{t("Area to process")}:</span>
                      <span className="font-mono text-[11.5px] text-muted">{aoi?.map((v) => v.toFixed(4)).join(", ")}</span>
                      <Button className="h-7 px-2.5 text-[12px]" variant={drawing === "aoi" ? "primary" : "ghost"} onClick={() => setDrawing((d) => (d === "aoi" ? "" : "aoi"))}>
                        {drawing === "aoi" ? t("Click two corners on the map…") : t("Draw another area")}
                      </Button>
                    </div>
                    {!inside(aoi, s) && <div className="text-[12px] text-warn">{t("The area must lie inside the red outline (covered by every date).")}</div>}
                    {s.source === "umbra" && <div className="text-[12px] text-muted">{t("Choose structures on land (buildings, roads, quays): water and container yards change between dates and lose coherence.")}</div>}
                    <div className="text-[12px] text-muted">
                      {mb != null
                        ? t("Download: only the area, about {mb} MB per date ({total} MB in all).", { mb: Math.max(1, Math.round(mb)), total: Math.round(mb * s.n_dates) })
                        : t("Download: the {n} whole scenes (about 0.3–1.5 GB each).", { n: s.n_dates })}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <input className={`${fieldSm} w-56`} value={name} onChange={(e) => setName(e.target.value.toLowerCase())} aria-label={t("Project name")} aria-invalid={!!name && !nameOk} />
                      {!LITE.has(s.sensor ?? "") ? (
                        <select className={`${fieldSm} w-28`} value={method} onChange={(e) => setMethod(e.target.value)} aria-label={t("Method")}>
                          <option value="psi">psi</option>
                          <option value="psds">psds</option>
                        </select>
                      ) : (
                        <span className="text-[12px] text-faint">ps_lite</span>
                      )}
                      <Button variant="primary" disabled={!nameOk || !inside(aoi, s) || create.isPending} onClick={() => create.mutate(s)}>
                        {create.isPending ? t("Creating…") : t("Process this stack")}
                      </Button>
                    </div>
                    {name && !nameOk && <div className="text-[11.5px] text-bad">{exists ? t("A project with this name exists.") : t("Use a-z, 0-9, _ or -, starting with a letter or digit.")}</div>}
                    {create.error && <div className="text-[12px] text-bad">{ts((create.error as Error).message)}</div>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div className="relative min-h-[360px] flex-[1_1_520px]">
        <div className="absolute inset-0">
          <div ref={mapEl} className="h-full w-full" />
        </div>
        <BasemapPicker map={map} base={base} onChange={setBase} />
        {drawing && <div className="absolute top-3 left-3 z-10 rounded-md bg-bg/85 px-3 py-1.5 text-[12.5px] text-ink-2">{t("Click a first corner, then the opposite corner")}</div>}
      </div>
    </div>
  );
}
