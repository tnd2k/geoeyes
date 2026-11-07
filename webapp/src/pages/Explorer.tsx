// Explorer: the map of the products shown in the tree (eye toggles), coloured like QGIS and the reports
// (Pretty Breaks over the full min–max, jet_r); click a point for its series, draw an area for the mean series.
import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer, SolidPolygonLayer, type ScatterplotLayerProps } from "@deck.gl/layers";
import { keepPreviousData, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type AreaInfo, type CalibrationBrief, type CatalogProduct, type CompareMeta, type FloodFeature, type LayerMeta, type VelKind, type Workspace } from "../api";
import { MapCanvas, useBaseMap, useFitTo } from "../components/MapBase";
import { calibrationSource } from "../components/Calibration";
import { FloodHub, LEVEL_COLOR } from "../components/FloodHub";
import { floodBounds, floodFeatures, floodLayers, floodTooltip } from "../components/FloodReports";
import { ProfileChart } from "../components/Profile";
import { TimeBar } from "../components/TimeBar";
import { TimeSeries } from "../components/TimeSeries";
import { loadTheme, ThemeCard, ThemeDetail, themeLayers, themeTooltip, THEME_LABEL, useAvailable, useThemes, type ThemeData, type ThemeKind, type ThemeSel } from "../components/ThemeLayers";
import { t, ts } from "../i18n";
import { binaryData, colorize, colorizeFrame, hexLayer, hexSize, loadLayer, pickedVelocity, pointAlong, productLayer, segmentLengths, TERRAIN, TERRAIN_ATTRIBUTION, terrainLayer, terrainProfile, withRange, type LayerData } from "../map";
import { useApp, type MapLayer } from "../state";
import { Button, ColumnToggle, Confidence, fmt, Fold, usePersisted } from "../ui";

type CompareMode = "off" | "swipe" | "diff";

interface Compare {
  mode: CompareMode;
  a: string;
  b: string;
  cell: number;
  align: boolean;
}

/** Monthly rain (CHIRPS) over a layer's extent and period, for the displacement chart; a switch remembered by the
 * browser (shown unless turned off). */
function useRain(layer: MapLayer | undefined) {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem("geoeyes.rain") !== "0";
    } catch {
      return true;
    }
  });
  const q = useQuery({
    queryKey: ["rain", layer?.key],
    queryFn: () => api.rainfall(layer!.project, layer!.product),
    enabled: on && !!layer,
    staleTime: Infinity,
  });
  const toggle = () =>
    setOn((v) => {
      try {
        localStorage.setItem("geoeyes.rain", v ? "0" : "1");
      } catch {
        /* storage unavailable */
      }
      return !v;
    });
  const series = on && q.data ? { months: q.data.months, label: `${t("monthly rainfall")} · ${ts(q.data.source).split(" (")[0]}` } : null;
  const control = (
    <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-muted">
      <input type="checkbox" className="accent-accent" checked={on} onChange={toggle} /> {t("monthly rainfall")}
      {on && q.isLoading && <span className="text-accent-ink">· {t("Reading the rainfall…")}</span>}
      {on && q.error && <span className="text-bad">· {ts((q.error as Error).message)}</span>}
    </label>
  );
  return { series, control };
}

export function Legend({ meta, title, label }: { meta: Pick<LayerMeta, "classes" | "vel_min" | "vel_max"> & { range?: [number, number] }; title: string; label?: string }) {
  label ??= t("LOS velocity");
  // count -1: not known (a chosen range over tiles, whose values stay on the server)
  const counted = meta.classes.every((c) => c.count >= 0);
  const total = meta.classes.reduce((a, c) => a + Math.max(0, c.count), 0) || 1;
  const step = meta.classes.length > 2 ? meta.classes[1].hi - meta.classes[1].lo : 1;
  const d = step >= 5 ? 0 : 1;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-semibold">{label}</span>
        <span className="text-[11px] text-muted">mm/yr</span>
      </div>
      {title && (
        <div className="mt-0.5 truncate text-[11px] text-muted" title={title}>
          {title}
        </div>
      )}
      <div className="mt-2 space-y-[3px]">
        {[...meta.classes].reverse().map((c) => (
          <div key={c.lo} className="flex items-center gap-2 text-[12px]">
            <span className="h-3 w-3 flex-none rounded-full" style={{ background: `rgb(${c.color.join(",")})` }} />
            <span className="w-[92px] font-mono text-[11.5px] text-ink-2">
              {c.lo.toFixed(d)} … {c.hi.toFixed(d)}
            </span>
            {counted && (
              <>
                <span className="h-1.5 flex-1 overflow-hidden rounded bg-chip">
                  <span className="block h-full rounded bg-faint" style={{ width: `${Math.max(1, (100 * c.count) / total)}%` }} />
                </span>
                <span className="w-11 text-right font-mono text-[11px] text-muted">{((100 * c.count) / total).toFixed(1)}%</span>
              </>
            )}
          </div>
        ))}
      </div>
      {"range" in meta && meta.range && (
        <div className="mt-1.5 text-[11px] text-warn-ink">
          {t("Chosen colour range: values beyond it take the end colours.")}
        </div>
      )}
      <div className="mt-2 flex justify-between text-[11px] text-muted">
        <span>
          {t("min")} <span className="font-mono text-ink-2">{fmt.vel(meta.vel_min)}</span>
        </span>
        <span>
          {t("max")} <span className="font-mono text-ink-2">{fmt.vel(meta.vel_max)}</span>
        </span>
      </div>
      <div className="mt-1.5 text-[11px] leading-snug text-faint">{t("+ toward the satellite, − away (e.g. subsidence)")}</div>
    </div>
  );
}

/** An icon tool of the map rail: its name (and what it does) appears under it on hover or focus. */
function Tool({ label, hint, icon, active, disabled, onClick }: { label: string; hint?: string; icon: ReactNode; active?: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <span className="group relative">
      <button
        type="button"
        aria-label={label}
        aria-pressed={active}
        disabled={disabled}
        onClick={onClick}
        className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
          active ? "bg-accent-bg text-accent-ink ring-1 ring-accent/60" : "text-ink-2 hover:bg-raised hover:text-ink"
        }`}
      >
        {icon}
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute top-full left-0 z-20 mt-2 w-max max-w-[260px] rounded-lg border border-line-2 bg-panel px-2.5 py-1.5 text-[12px] leading-snug text-ink opacity-0 shadow-xl shadow-black/30 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      >
        <span className="block font-semibold">{label}</span>
        {hint && <span className="mt-0.5 block text-[11.5px] text-muted">{hint}</span>}
      </span>
    </span>
  );
}

/** A layer card's legend: the velocity classes (and, zoomed out, what the hexagons show), folded but for the top
 * layer. */
function LayerLegend({
  meta,
  hex,
  confidence,
  defaultOpen,
  onRange,
}: {
  meta: LayerMeta;
  hex?: number;
  confidence?: string | null;
  defaultOpen: boolean;
  onRange: (r: [number, number] | null) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-2 border-t border-line pt-1.5 pl-6">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-1 text-left text-[11px] font-semibold tracking-[0.8px] text-muted uppercase hover:text-ink">
        <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden className={`transition-transform ${open ? "" : "-rotate-90"}`}>
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {t("Legend")}
        {hex ? <span className="ml-auto font-normal tracking-normal normal-case">{t("hexagons {s} m · median", { s: hex })}</span> : null}
      </button>
      {open && (
        <div className="mt-1.5">
          <Legend meta={meta} title="" />
          <RangeEditor meta={meta} onRange={onRange} />
          {meta.calibration && (
            <div className="mt-1 text-[11px] text-warn-ink">
              {t("Calibrated velocities")}: {calibrationSource(meta.calibration)}, {fmt.vel(meta.calibration.rate_offset_mm_yr)} mm/yr
            </div>
          )}
          {confidence !== undefined && (
            <div className="mt-2">
              <Confidence level={confidence ?? undefined} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** The colour range of a layer: the product's full min-max (default) or two values the user types. */
function RangeEditor({ meta, onRange }: { meta: LayerMeta; onRange: (r: [number, number] | null) => void }) {
  const cur = meta.range ?? [meta.vel_min, meta.vel_max];
  const show = (v: number) => String(Math.round(v * 10) / 10);
  const [lo, setLo] = useState(show(cur[0]));
  const [hi, setHi] = useState(show(cur[1]));
  useEffect(() => {
    setLo(show(cur[0]));
    setHi(show(cur[1]));
  }, [cur[0], cur[1]]);
  const a = Number(lo);
  const b = Number(hi);
  const valid = lo.trim() !== "" && hi.trim() !== "" && Number.isFinite(a) && Number.isFinite(b) && b > a;
  // unchanged (a blur without an edit): keep the full range exact rather than its rounded display
  const apply = () => valid && (lo !== show(cur[0]) || hi !== show(cur[1])) && onRange([a, b]);
  const m = Math.max(Math.abs(a), Math.abs(b));
  const input = "h-6 w-[62px] rounded border bg-sunken px-1 font-mono text-[11px] focus:border-accent focus:outline-none";
  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-muted"
      onSubmit={(e) => {
        e.preventDefault();
        apply();
      }}
    >
      <span>{t("Colour range")}</span>
      <input value={lo} onChange={(e) => setLo(e.target.value)} onBlur={apply} inputMode="decimal" aria-label={t("Lowest value of the colour range (mm/yr)")} className={`${input} ${valid ? "border-line-2" : "border-bad"}`} />
      <span>…</span>
      <input value={hi} onChange={(e) => setHi(e.target.value)} onBlur={apply} inputMode="decimal" aria-label={t("Highest value of the colour range (mm/yr)")} className={`${input} ${valid ? "border-line-2" : "border-bad"}`} />
      <span>mm/yr</span>
      <button type="button" disabled={!valid || !(m > 0)} onClick={() => onRange([-m, m])} title={t("The same range on both sides of zero")} className="text-accent hover:underline disabled:opacity-40">
        ±{show(m)}
      </button>
      {meta.range && (
        <button type="button" onClick={() => onRange(null)} title={t("Back to the product's min–max")} className="text-accent hover:underline">
          {t("full range")}
        </button>
      )}
    </form>
  );
}

/** The layer request of a map layer: calibrated or not, and the velocity kind chosen (`undefined`: none chosen,
 * the default v-do when the product has it). */
function layerReq(l: MapLayer): { cal: boolean; vel: VelKind | null | "default" } {
  return { cal: !!l.calibrated, vel: l.vel === undefined ? "default" : l.vel };
}

// the StaMPS velocity kinds: what is removed from the phase before the fit
const VEL_KINDS: Record<VelKind, string> = {
  do: "DEM error and orbit ramps removed",
  dao: "DEM error, atmosphere (APS) and orbit ramps removed",
  dso: "DEM error, spatially correlated noise (SCN) and orbit ramps removed",
};

/** The velocity a layer shows: the product's, or another StaMPS kind the product carries (ps engine). */
function VelocityKind({ meta, value, onChange }: { meta: LayerMeta; value: VelKind | null; onChange: (v: VelKind | null) => void }) {
  const kinds = meta.velocity_kinds ?? [];
  if (!kinds.length) return null;
  const pk = meta.product_kind ?? null;
  // always the three kinds; the product's own one is the product velocity (value null), a kind the product does not
  // carry is shown greyed
  const ORDER: VelKind[] = ["dao", "dso", "do"];
  const hint = [
    ...kinds.map((k) => `v-${k}: ${t(VEL_KINDS[k])}`),
    meta.legacy_dso ? t("v-dso of this run also has the APS removed when the run removed it (written before the kinds).") : "",
    t("Another kind is read as points, not tiles."),
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <label className="mt-1 flex items-center gap-2 pl-6 text-[11px] text-muted" title={hint}>
      {t("Velocity")}
      <select
        value={meta.velocity_kind ?? value ?? pk ?? ""}
        onChange={(e) => {
          const v = (e.target.value || null) as VelKind | null;
          onChange(v === pk ? null : v);
        }}
        className="h-6 min-w-0 flex-1 rounded border border-line-2 bg-sunken px-1 text-[11px] text-ink-2"
      >
        {/* the product velocity of an older run, whose kind is not known */}
        {!pk && <option value="">{t("product")}</option>}
        {ORDER.map((k) => (
          <option key={k} value={k} disabled={k !== pk && !kinds.includes(k)}>
            v-{k} · {t(VEL_KINDS[k])}
            {k !== pk && !kinds.includes(k) ? ` (${t("not in this product")})` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Calibrated view of a layer: the product's velocities and series plus its calibration (GNSS, else a tie). */
function CalibrationToggle({ cal, on, onChange }: { cal: CalibrationBrief; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label
      className="mt-1 flex cursor-pointer items-center gap-2 pl-6 text-[11px] text-ink-2"
      title={t("Velocities and series with the calibration added (the product files are unchanged); points only")}
    >
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} className="h-3.5 w-3.5 accent-accent" />
      <span className="truncate">
        {t("Calibrated")} · {calibrationSource(cal)} · <span className="font-mono">{fmt.vel(cal.rate_offset_mm_yr)} mm/yr</span>
      </span>
    </label>
  );
}

/** The thematic layers a product can show (its analyses that ran), as buttons of its card. */
function ThemeChips({ project, product, on, toggle }: { project: string; product: string; on: (k: ThemeKind) => boolean; toggle: (k: ThemeKind) => void }) {
  const kinds = useAvailable(project, product);
  if (!kinds.length) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-line pt-1.5 pl-6 text-[11px]">
      <span className="text-muted">{t("Thematic layers")}:</span>
      {kinds.map((k) => (
        <button
          key={k}
          type="button"
          aria-pressed={on(k)}
          onClick={() => toggle(k)}
          className={`rounded-full border px-2 py-0.5 ${on(k) ? "border-accent bg-accent-bg text-accent-ink" : "border-line-2 text-ink-2 hover:bg-raised"}`}
        >
          {on(k) ? "✓ " : "+ "}
          {t(THEME_LABEL[k])}
        </button>
      ))}
    </div>
  );
}

export function Explorer({ ws }: { ws: Workspace | undefined }) {
  const { layers, setOpacity, setMode, setCalibrated, setRange, setVel, toggleLayer, removeLayer, focus, setFocus, selection, select, go, showProduct } = useApp();
  // 3D view: terrain draped with the base map, the points on it; heights exaggerated (flat deltas)
  const [three, setThree] = usePersisted("explorer.3d", false);
  // in 3D the base map is the texture of the terrain (deck.gl), MapLibre only draws the background
  const shell = useBaseMap({ override: three ? "none" : undefined, rotate: three, pitch: three ? 55 : 0 });
  const { map, overlay, base } = shell;
  const mapReady = shell.ready;
  const [exag, setExagState] = useState(() => {
    try {
      return Number(localStorage.getItem("geoeyes.ui.explorer.3d.exaggeration")) || 3;
    } catch {
      return 3;
    }
  });
  const setExag = (v: number) => {
    setExagState(v);
    try {
      localStorage.setItem("geoeyes.ui.explorer.3d.exaggeration", String(v));
    } catch {
      /* private window */
    }
  };
  const terrainOn = three ? [TERRAIN] : [];
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
      .catch((e: Error) => setFinder({ busy: false, rows: null, error: ts(e.message) }));
  };
  const [split, setSplit] = useState(0.5);
  // time animation: the cumulative displacement of the top layer at one date
  const qc = useQueryClient();
  const [timeOn, setTimeOn] = useState(false);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  // profile: a line drawn on the map, the points within a half width of it
  const [profiling, setProfiling] = useState(false);
  const [line, setLine] = useState<[number, number][]>([]);
  const [halfWidth, setHalfWidth] = useState(50);
  const [hoverDist, setHoverDist] = useState<number | null>(null);
  const [panelsOpen, setPanelsOpen] = usePersisted("explorer.panels", true);
  const [dockOpen, setDockOpen] = usePersisted("explorer.dock", true);
  const dockEl = useRef<HTMLDivElement>(null);
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
      queryKey: ["layer", l.key, l.mode ?? "auto", layerReq(l)],
      queryFn: () => loadLayer(l.project, l.product, l.mode ?? "auto", !!l.calibrated, l.vel),
      staleTime: Infinity,
      gcTime: 10 * 60_000,
    })),
  });
  const byKey = useMemo(() => {
    const m: Record<string, LayerData | undefined> = {};
    // a range chosen on the layer card: its classes and colours everywhere (map, hexagons, legend, profile)
    layers.forEach((l, i) => {
      const d = data[i]?.data;
      m[l.key] = d && withRange(d, l.range);
    });
    return m;
  }, [layers, data]);
  // the view of a layer the other requests (hexagons, point, area, profile, animation) ask for: the velocity kind the
  // layer was loaded with
  const lv = (l: MapLayer | undefined): { cal: boolean; vel: VelKind | null } => ({
    cal: !!l?.calibrated,
    vel: (l && byKey[l.key]?.meta.velocity_kind) ?? null,
  });
  const top = layers.find((l) => l.visible && byKey[l.key]);

  // reported flood locations over the products
  const [floodsOn, setFloodsOn] = usePersisted("explorer.floods", false);
  const [floodSel, setFloodSel] = useState<string | null>(null);
  const floodRadius = 100; // m: the points counted around a reported location
  const floodsQ = useQuery({ queryKey: ["floods"], queryFn: api.floods, enabled: floodsOn, staleTime: 60_000 });
  const floodStats = useQuery({
    queryKey: ["floodStats", top?.key, floodRadius],
    queryFn: () => api.productFloods(top!.project, top!.product, floodRadius),
    enabled: floodsOn && !!top && !!floodsQ.data?.features.length,
    staleTime: Infinity,
  });
  const [floodRiskColors, setFloodRiskColors] = usePersisted("explorer.floods.risk", true);
  const outlookQ = useQuery({
    queryKey: ["floodOutlook", top?.key ?? null],
    queryFn: () => api.floodOutlook(top?.project, top?.product),
    enabled: floodsOn && !!floodsQ.data?.features.length,
    staleTime: 15 * 60_000,
    refetchInterval: 30 * 60_000,
  });
  // the hub's area: the selected location's region, else the region nearest the map centre
  const [mapCentre, setMapCentre] = useState<[number, number] | null>(null);
  useEffect(() => {
    const m = map.current;
    if (!m || !floodsOn) return;
    const on = () => setMapCentre([m.getCenter().lng, m.getCenter().lat]);
    on();
    m.on("moveend", on);
    return () => void m.off("moveend", on);
  }, [floodsOn, mapReady]);
  const floodArea = useMemo(() => {
    const areas = outlookQ.data?.areas;
    if (!areas) return null;
    const sel = floodSel ? floodsQ.data?.features.find((f) => f.id === floodSel)?.properties.region : undefined;
    if (sel && areas[sel]) return sel;
    const c = mapCentre ?? [106.7, 10.78];
    return Object.entries(areas).sort(([, a], [, b]) => Math.hypot(a.centre[0] - c[0], a.centre[1] - c[1]) - Math.hypot(b.centre[0] - c[0], b.centre[1] - c[1]))[0]?.[0] ?? null;
  }, [outlookQ.data, floodSel, floodsQ.data, mapCentre]);
  const floodShown = useMemo(() => (floodsOn ? floodFeatures(floodsQ.data, false) : []), [floodsOn, floodsQ.data]);
  const pickFlood = (id: string, fly = false) => {
    setFloodSel(id);
    setDockOpen(false);
    const f = floodsQ.data?.features.find((x) => x.id === id);
    const b = f && floodBounds(f);
    if (fly && b && map.current) map.current.fitBounds([b[0], b[1], b[2], b[3]], { padding: 120, maxZoom: 16, duration: 600 });
  };

  // ------------------------------------------------------------ time animation (points layers only)
  const anim = timeOn && top && byKey[top.key]?.kind === "points" ? top : undefined;

  // zoomed out: hexagons of the median velocity (binned once on the server), zoomed in: the points
  const [hexOn, setHexOn] = usePersisted("explorer.hex", true);
  const [zoom, setZoom] = useState(10);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const on = () => setZoom(Math.round(m.getZoom() * 4) / 4);
    on();
    m.on("zoomend", on);
    return () => void m.off("zoomend", on);
  }, [mapReady]);
  const hexFor = (l: MapLayer): number | null => {
    const d = byKey[l.key];
    if (!hexOn || !d || !l.visible || three || anim || comparing) return null;
    return hexSize(d.meta.hex_sizes, zoom, d.meta.origin[1]);
  };
  const hexQueries = useQueries({
    queries: layers.map((l) => {
      const size = hexFor(l);
      return {
        queryKey: ["hex", l.key, size, lv(l)],
        queryFn: () => api.layerHex(l.project, l.product, size!, lv(l)),
        enabled: size != null,
        staleTime: Infinity,
        gcTime: 10 * 60_000,
      };
    }),
  });
  // thematic layers of the products (hazard zoning, deformation forecast), under their points
  const th = useThemes();
  const themeQueries = useQueries({
    queries: th.themes.map((x) => ({ queryKey: ["theme", x.key], queryFn: () => loadTheme(x), staleTime: 5 * 60_000, gcTime: 10 * 60_000 })),
  });
  const themeData: Record<string, ThemeData | undefined> = {};
  const themeErr: Record<string, string | undefined> = {};
  th.themes.forEach((x, i) => {
    themeData[x.key] = themeQueries[i]?.data;
    if (themeQueries[i]?.error) themeErr[x.key] = ts((themeQueries[i].error as Error).message);
  });
  // the clicked cell / building / line of a thematic layer: its detail where the dock is (a point selection closes it)
  const [themeSel, setThemeSel] = useState<ThemeSel | null>(null);
  useEffect(() => {
    if (selection) setThemeSel(null);
  }, [selection]);
  const pickTheme = (key: string, i: number) => {
    select(null);
    setRing([]);
    setArea(null);
    setLine([]);
    setThemeSel({ key, i });
  };

  const hexByKey: Record<string, { size: number; buf: Float32Array } | undefined> = {};
  layers.forEach((l, i) => {
    const size = hexFor(l);
    const buf = hexQueries[i]?.data;
    if (size != null && buf) hexByKey[l.key] = { size, buf };
  });
  const disp = useQuery({
    queryKey: ["disp", anim?.key, lv(anim)],
    queryFn: () => api.layerDisp(anim!.project, anim!.product, lv(anim)),
    enabled: !!anim,
    staleTime: Infinity,
  });
  const frameKey = (k: number) => ["disp-frame", anim?.key, lv(anim), k];
  const frameFetch = (k: number) => () => api.layerDispFrame(anim!.project, anim!.product, k, lv(anim));
  const frameQ = useQuery({
    queryKey: frameKey(frame),
    queryFn: frameFetch(frame),
    enabled: !!anim && !!disp.data,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
  const frameColors = useMemo(
    () => (frameQ.data && disp.data ? colorizeFrame(frameQ.data, disp.data.scale, disp.data.classes) : undefined),
    [frameQ.data, disp.data],
  );
  useEffect(() => {
    if (!anim || !disp.data) return;
    const n = disp.data.dates.length;
    if (frame >= n) setFrame(n - 1);
    qc.prefetchQuery({ queryKey: frameKey((frame + 1) % n), queryFn: frameFetch((frame + 1) % n), staleTime: Infinity });
    if (!playing || frameQ.isPlaceholderData || frameQ.isFetching) return;
    const id = window.setTimeout(() => setFrame((f) => (f + 1) % n), (frame === n - 1 ? 1600 : 700) / speed);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anim?.key, disp.data, frame, playing, speed, frameQ.isPlaceholderData, frameQ.isFetching]);

  // ------------------------------------------------------------ profile
  const profile = useQuery({
    queryKey: ["profile", top?.key, line, halfWidth, lv(top)],
    queryFn: () => api.layerProfile(top!.project, top!.product, line, halfWidth, lv(top)),
    enabled: !!top && !profiling && line.length >= 2,
    staleTime: Infinity,
  });
  const lineLength = useMemo(() => segmentLengths(line).reduce((a, b) => a + b, 0), [line]);
  const terrainQ = useQuery({
    queryKey: ["terrain-profile", line],
    queryFn: () => terrainProfile(line, Math.max(10, lineLength / 400)),
    enabled: !profiling && line.length >= 2,
    staleTime: Infinity,
  });

  // ------------------------------------------------------------ map

  // 3D: a compass (drag it to turn and tilt, click it for north up) next to the zoom buttons
  useEffect(() => {
    const m = map.current;
    if (!three || !m) return;
    const compass = new maplibregl.NavigationControl({ showZoom: false, showCompass: true, visualizePitch: true });
    m.addControl(compass, "bottom-left");
    return () => {
      m.removeControl(compass);
    };
  }, [three, mapReady, map]);
  const turn = (deg: number) => {
    const m = map.current;
    if (m) m.easeTo({ bearing: m.getBearing() + deg, duration: 500 });
  };

  const firstThree = useRef(true);
  useEffect(() => {
    const m = map.current;
    if (firstThree.current || !m) {
      firstThree.current = false;
      return;
    }
    if (three) {
      m.dragRotate.enable();
      m.touchZoomRotate.enableRotation();
      m.easeTo({ pitch: 55, duration: 700 });
    } else {
      m.dragRotate.disable();
      m.touchZoomRotate.disableRotation();
      m.easeTo({ pitch: 0, bearing: 0, duration: 500 });
    }
  }, [three]);

  // the view shows none of the visible layers (page opened with layers already listed, the last layer over the
  // view removed or hidden): go to them, once per set of visible layers (a layer picked in the tree has its own zoom)
  const shown = layers.filter((l) => l.visible && byKey[l.key]);
  const shownKey = focus ? null : shown.map((l) => l.key).join("|") || null;
  const shownBounds = useMemo(() => {
    const bs = shown.map((l) => byKey[l.key]!.meta.bounds);
    return bs.length ? [Math.min(...bs.map((b) => b[0])), Math.min(...bs.map((b) => b[1])), Math.max(...bs.map((b) => b[2])), Math.max(...bs.map((b) => b[3]))] : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownKey, byKey]);
  useFitTo(shell, shownBounds, shownKey, true);

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

  // map clicks while drawing a profile line
  useEffect(() => {
    const m = map.current;
    if (!m || !profiling) return;
    m.doubleClickZoom.disable();
    m.getCanvas().style.cursor = "crosshair";
    const click = (e: maplibregl.MapMouseEvent) => setLine((r) => [...r, [e.lngLat.lng, e.lngLat.lat]]);
    const dbl = (e: maplibregl.MapMouseEvent) => (e.preventDefault(), setProfiling(false));
    m.on("click", click);
    m.on("dblclick", dbl);
    return () => {
      m.off("click", click);
      m.off("dblclick", dbl);
      m.getCanvas().style.cursor = "";
      setTimeout(() => m.doubleClickZoom.enable(), 0);
    };
  }, [profiling]);

  // area finished: mean series of the top layer
  useEffect(() => {
    if (drawing || ring.length < 3 || !top) return;
    setAreaBusy(true);
    api
      .area(top.project, top.product, ring, lv(top))
      .then((info) => setArea({ layer: top.key, info }))
      .finally(() => setAreaBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawing]);

  // ------------------------------------------------------------ selected point
  const selLayer = selection ? layers.find((l) => l.key === selection.layer) : undefined;
  const point = useQuery({
    queryKey: ["point", selection?.layer, selection?.index, lv(selLayer)],
    queryFn: () => api.point(selLayer!.project, selLayer!.product, selection!.index, lv(selLayer)),
    enabled: !!selLayer,
  });

  // ------------------------------------------------------------ deck layers
  useEffect(() => {
    const ov = overlay.current;
    if (!ov) return;
    const deckLayers: unknown[] = three ? [terrainLayer(base, exag)] : [];
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
          id: three ? "diff-3d" : "diff",
          extensions: terrainOn,
          data: binaryData(diff.data.buf, diff.data.colors, () => ({
            length: dm.n,
            attributes: {
              getPosition: { value: diff.data!.buf, size: 2, stride: 20, offset: 0 },
              getFillColor: { value: diff.data!.colors, size: 3, normalized: true },
            },
          })) as unknown as ScatterplotLayerProps["data"],
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
      const hx = hexByKey[l.key];
      if (hx) {
        deckLayers.push(hexLayer(l, d.meta, hx.buf, hx.size, { terrain: three, onPick: (lon, lat) => map.current?.flyTo({ center: [lon, lat], zoom: Math.min(zoom + 2, 16), duration: 600 }) }));
        return;
      }
      deckLayers.push(
        productLayer(l, d, {
          pickable: !drawing && !profiling,
          colors: anim && l.key === anim.key && d.kind === "points" && frameColors?.length === d.meta.n * 3 ? frameColors : undefined,
          onPick: (index) => {
            select({ layer: l.key, index });
            setArea(null);
          },
          clipLon: swipe ? (l.key === cmp.a ? [-180, splitLon] : [splitLon, 180]) : null,
          terrain: three,
        }),
      );
    });
    // thematic layers over the points: an analysis switched on is what the user wants to read
    if (!(comparing && cmp.mode === "diff")) deckLayers.push(...themeLayers(th.themes, themeData, themeSel, pickTheme));
    if (floodShown.length)
      deckLayers.push(
        ...floodLayers(floodShown, {
          selected: floodSel,
          onPick: (id) => pickFlood(id),
          three,
          extensions: terrainOn,
          colorKey: floodRiskColors && outlookQ.data ? `risk-${outlookQ.data.generated}` : "cause",
          colorOf: floodRiskColors && outlookQ.data ? (f) => (outlookQ.data!.rows[f.id] ? LEVEL_COLOR[outlookQ.data!.rows[f.id].level] : undefined) : undefined,
        }),
      );
    if (line.length) {
      if (!profiling && line.length >= 2)
        deckLayers.push(
          new PathLayer<[number, number][]>({
            id: three ? "profile-band-3d" : "profile-band",
            extensions: terrainOn,
            data: [line],
            getPath: (r) => r as never,
            getColor: [255, 209, 102, 45],
            getWidth: 2 * halfWidth,
            widthUnits: "meters",
          }),
        );
      deckLayers.push(
        new PathLayer<[number, number][]>({
          id: three ? "profile-line-3d" : "profile-line",
          extensions: terrainOn,
          data: [line],
          getPath: (r) => r as never,
          getColor: [255, 209, 102],
          getWidth: 2,
          widthUnits: "pixels",
        }),
      );
      if (hoverDist != null && line.length >= 2)
        deckLayers.push(
          new ScatterplotLayer({
            id: three ? "profile-hover-3d" : "profile-hover",
            extensions: terrainOn,
            data: [pointAlong(line, hoverDist)],
            getPosition: (p: number[]) => [p[0], p[1]],
            getRadius: 7,
            radiusUnits: "pixels",
            getFillColor: [255, 209, 102],
            stroked: true,
            getLineColor: [11, 18, 32],
            lineWidthMinPixels: 2,
          }),
        );
    }
    if (selection && point.data && point.data.index === selection.index) {
      deckLayers.push(
        new ScatterplotLayer({
          id: three ? "selected-3d" : "selected",
          extensions: terrainOn,
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
            id: three ? "area-fill-3d" : "area-fill",
            extensions: terrainOn,
            data: [ring],
            getPolygon: (r) => r as never,
            getFillColor: [255, 255, 255, 30],
          }),
        );
      deckLayers.push(
        new PathLayer<[number, number][]>({
          id: three ? "area-line-3d" : "area-line",
          extensions: terrainOn,
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
        const style = { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" };
        if (!layer) return null;
        if (layer.id.startsWith("flood") && object) {
          const f = (object as { f?: FloodFeature }).f ?? (object as FloodFeature);
          return { text: floodTooltip(f, floodStats.data), style: { ...style, fontFamily: "var(--font-sans)", maxWidth: "360px", whiteSpace: "pre-wrap" } };
        }
        if (layer.id.startsWith("diff") && diff.data && index >= 0) {
          const b = diff.data.buf;
          return { text: `B − A ${fmt.vel(b[index * 5 + 2])} mm/yr\nA ${fmt.vel(b[index * 5 + 3])} · B ${fmt.vel(b[index * 5 + 4])}`, style };
        }
        if (layer.id.startsWith("theme-")) {
          const text = themeTooltip(th.themes, themeData, layer.id, index);
          return text ? { text, style: { ...style, fontFamily: "var(--font-sans)", whiteSpace: "pre-wrap" } } : null;
        }
        if (layer.id.startsWith("hex-") && index >= 0) {
          const hx = Object.entries(hexByKey).find(([k]) => layer.id.startsWith(`hex-${k}-`))?.[1];
          if (hx) return { text: `${fmt.vel(hx.buf[index * 4 + 2])} mm/yr · ${t("median of {n} points", { n: fmt.int(hx.buf[index * 4 + 3]) })}\n${t("click to zoom in")}`, style };
        }
        const key = Object.keys(byKey).find((k) => layer.id.startsWith(`pts-${k}`));
        const d = key ? byKey[key] : undefined;
        const v = d ? pickedVelocity(d, index, object) : null;
        if (v != null && key === anim?.key && frameQ.data && disp.data && index >= 0 && frameQ.data[index] !== -32768)
          return { text: `${(frameQ.data[index] / disp.data.scale).toFixed(1)} mm · ${disp.data.dates[frame]}\n${fmt.vel(v)} mm/yr`, style };
        return v == null ? null : { text: `${fmt.vel(v)} mm/yr`, style };
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers, byKey, selection, point.data, ring, drawing, select, comparing, cmp, diff.data, split, viewTick, three, exag, base, anim?.key, frameColors, frameQ.data, disp.data, frame, line, profiling, halfWidth, hoverDist, floodShown, floodSel, floodStats.data, floodRiskColors, outlookQ.data, hexQueries.map((q) => q.dataUpdatedAt).join(), zoom, hexOn, th.themes, themeQueries.map((q) => q.dataUpdatedAt).join(), themeSel]);

  // the time-series panel shows the series with the residual atmosphere (SCN) removed (StaMPS v-dso, as SARPROZ's
  // APS-corrected series); products without it fall back to the raw series. The map keeps its velocity-kind choice.
  const pointSeries = point.data ? (point.data.disp_scn_mm ?? point.data.disp_mm) : null;
  const areaSeries = area?.info.mean_scn_mm ?? area?.info.mean_mm;
  const areaSpread = area?.info.mean_scn_mm ? area.info.std_scn_mm : area?.info.std_mm;
  const selMeta = selection ? byKey[selection.layer]?.meta : undefined;
  const pointRain = useRain(selLayer);
  const areaRain = useRain(area ? layers.find((l) => l.key === area.layer) : undefined);
  const areaMeta = area ? byKey[area.layer]?.meta : undefined;
  const showProfile = !selection && !area && !areaBusy && !profiling && line.length >= 2;
  const docked = !!((selection && selMeta) || area || areaBusy || showProfile);
  // a new point, area or profile opens the dock (it may have been folded for the flood hub)
  useEffect(() => {
    if (selection || area || areaBusy || showProfile) setDockOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection?.layer, selection?.index, area, areaBusy, showProfile]);
  // the dock's height: the right panel ends above it
  const [dockH, setDockH] = useState(0);
  useEffect(() => {
    const el = dockEl.current;
    if (!docked || !el) return setDockH(0);
    const place = () => setDockH(el.offsetHeight);
    place();
    const ro = new ResizeObserver(place);
    ro.observe(el);
    return () => ro.disconnect();
  }, [docked, dockOpen]);


  const summary = (l: MapLayer) => ws?.projects[l.project]?.tracks.find((tr) => tr.product?.id === l.product);
  const loading = data.some((q) => q.isLoading);
  const errors = data.map((q, i) => (q.error ? `${layers[i]?.product}: ${ts((q.error as Error).message)}` : null)).filter(Boolean);

  return (
    <div className="relative h-full w-full overflow-hidden">
      <MapCanvas m={shell} />

      {/* toolbar: one compact rail of icon tools in three groups (draw / view / data); the name shows on hover, the
          state of a running tool (drawing, comparing) beside the rail */}
      <div className="absolute top-3 left-3 z-20 flex max-w-[calc(100%-24px)] flex-wrap items-center gap-2">
        <div role="toolbar" aria-label={t("Map tools")} className="flex items-center gap-0.5 rounded-xl border border-line-2 bg-panel/95 p-1 shadow-lg shadow-black/30 backdrop-blur">
          <Tool
            label={t("Draw area")}
            hint={t("Draw an area: the mean series of the points inside")}
            active={drawing}
            disabled={!top}
            onClick={() => {
              if (drawing) setDrawing(false);
              else {
                setRing([]);
                setArea(null);
                select(null);
                setProfiling(false);
                setLine([]);
                setDrawing(true);
              }
            }}
            icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M2 12 5 3l7 2 2 7-8 2z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /></svg>}
          />
          <Tool
            label={t("Profile")}
            hint={t("Draw a line: the ground height and the velocity of the points along it")}
            active={profiling}
            disabled={!top}
            onClick={() => {
              if (profiling) setProfiling(false);
              else {
                setLine([]);
                setRing([]);
                setArea(null);
                setDrawing(false);
                select(null);
                setHoverDist(null);
                setProfiling(true);
              }
            }}
            icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M1.5 12.5 6 6l3.5 3 5-6.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M1.5 14.5h13" stroke="currentColor" strokeWidth="1" opacity="0.6" /></svg>}
          />
          <span className="mx-1 h-5 w-px bg-line-2" aria-hidden />
          <Tool
            label={t("Compare")}
            hint={layers.length < 2 ? t("Show two products on the map to compare them") : t("Compare two products")}
            active={cmp.mode !== "off"}
            disabled={layers.length < 2}
            onClick={() =>
              setCmp((c) =>
                c.mode !== "off"
                  ? { ...c, mode: "off" }
                  : { ...c, mode: "swipe", a: c.a && layers.some((l) => l.key === c.a) ? c.a : layers[1]?.key ?? "", b: c.b && layers.some((l) => l.key === c.b) ? c.b : layers[0]?.key ?? "" },
              )
            }
            icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M8 1.5v13M2 4h4v8H2zM10 4h4v8h-4z" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>}
          />
          <Tool
            label={t("Time-lapse")}
            hint={top && byKey[top.key]?.kind !== "points" ? t("The time animation needs the product as points (layer mode)") : t("Play the displacement through the dates")}
            active={timeOn}
            disabled={!top || byKey[top.key]?.kind !== "points"}
            onClick={() => {
              setPlaying(false);
              setTimeOn(!timeOn);
            }}
            icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M8 4.5V8l2.5 1.8" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>}
          />
          <Tool label="3D" hint={t("Terrain in 3D, the points on it; right-drag, Ctrl+drag or the compass to tilt and turn")} active={three} onClick={() => setThree(!three)} icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="m1 13 4.5-7 3 4 2-2.5L15 13z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /></svg>} />
          <span className="mx-1 h-5 w-px bg-line-2" aria-hidden />
          <Tool label={t("Products here")} hint={t("Products of every project over the current view (workspace catalog)")} active={!!finder} onClick={() => (finder ? setFinder(null) : findHere())} icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="m10.5 10.5 3.5 3.5" stroke="currentColor" strokeWidth="1.4" /></svg>} />
          <Tool
            label={t("Reported floods")}
            hint={t("Reported flood locations (workspace inventory) over the products")}
            active={floodsOn}
            onClick={() => (setFloodsOn((v) => !v), setFloodSel(null))}
            icon={<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M8 2.5S4 7 4 9.5a4 4 0 0 0 8 0C12 7 8 2.5 8 2.5z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /></svg>}
          />
        </div>
        {drawing && (
          <Button className="h-8 bg-accent-bg/95 text-accent-ink shadow-lg shadow-black/30 backdrop-blur" onClick={() => setDrawing(false)}>
            {t("Finish area ({n} pts)", { n: ring.length })}
          </Button>
        )}
        {profiling && (
          <Button className="h-8 bg-accent-bg/95 text-accent-ink shadow-lg shadow-black/30 backdrop-blur" onClick={() => setProfiling(false)}>
            {t("Finish profile ({n} pts)", { n: line.length })}
          </Button>
        )}
        {cmp.mode !== "off" && (
          <Button className="h-8 bg-panel/95 shadow-lg shadow-black/30 backdrop-blur" onClick={() => setCmp((c) => ({ ...c, mode: "off" }))}>
            {t("Stop comparing")}
          </Button>
        )}
        {three && (
          <label className="flex h-8 items-center gap-1.5 rounded-lg border border-line-2 bg-panel/95 px-2 text-[12px] text-ink-2 shadow-lg shadow-black/30 backdrop-blur" title={t(TERRAIN_ATTRIBUTION)}>
            {t("Relief")}
            <select value={exag} onChange={(e) => setExag(Number(e.target.value))} className="h-6 rounded border border-line-2 bg-sunken px-1 font-mono text-[12px] text-ink">
              {[1, 2, 3, 5, 10, 20].map((v) => (
                <option key={v} value={v}>
                  ×{v}
                </option>
              ))}
            </select>
          </label>
        )}
        {three && (
          <div className="flex h-8 items-center gap-0.5 rounded-lg border border-line-2 bg-panel/95 px-1 text-ink-2 shadow-lg shadow-black/30 backdrop-blur">
            <button type="button" title={t("Turn left 45°")} onClick={() => turn(-45)} className="grid h-6 w-6 place-items-center rounded hover:bg-sunken hover:text-ink">
              <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><path d="M3 8a5 5 0 1 0 1.5-3.6M3 2.5v2.8h2.8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
            <button type="button" title={t("North up")} onClick={() => map.current?.easeTo({ bearing: 0, duration: 500 })} className="grid h-6 min-w-6 place-items-center rounded px-1 font-mono text-[12px] hover:bg-sunken hover:text-ink">
              N
            </button>
            <button type="button" title={t("Turn right 45°")} onClick={() => turn(45)} className="grid h-6 w-6 place-items-center rounded hover:bg-sunken hover:text-ink">
              <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><path d="M13 8a5 5 0 1 1-1.5-3.6M13 2.5v2.8h-2.8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </div>
        )}
        {(ring.length > 0 || area) && !drawing && (
          <Button className="h-8 bg-panel/95 shadow-lg shadow-black/30 backdrop-blur" onClick={() => (setRing([]), setArea(null))}>
            {t("Clear area")}
          </Button>
        )}
        {(drawing || profiling) && <span className="rounded-md bg-bg/85 px-2.5 py-1.5 text-[12px] text-ink-2">{t("Click to add vertices · double-click to finish")}</span>}
        {loading && <span className="rounded-md bg-bg/85 px-2.5 py-1.5 text-[12px] text-accent-ink">{t("Loading points…")}</span>}
      </div>

      {anim && disp.data && (
        <div className="absolute top-16 left-3 z-10">
          <TimeBar
            meta={disp.data}
            frame={Math.min(frame, disp.data.dates.length - 1)}
            onFrame={setFrame}
            playing={playing}
            onPlay={setPlaying}
            speed={speed}
            onSpeed={setSpeed}
            loading={frameQ.isFetching}
            onClose={() => (setPlaying(false), setTimeOn(false))}
          />
        </div>
      )}

      {finder && (
        <div className="absolute top-16 left-3 z-10 max-h-[calc(100%-120px)] w-[min(380px,calc(100%-24px))] overflow-y-auto rounded-xl border border-line-2 bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("PRODUCTS IN THIS VIEW")}</span>
            <button type="button" className="ml-auto text-faint hover:text-ink" onClick={() => setFinder(null)} aria-label={t("Close")}>
              ×
            </button>
          </div>
          {finder.busy && <div className="py-3 text-[12.5px] text-accent-ink">{t("Searching the catalog…")}</div>}
          {finder.error && <div className="py-2 text-[12.5px] text-bad">{finder.error}</div>}
          {finder.rows && finder.rows.length === 0 && <div className="py-3 text-[12.5px] text-muted">{t("No product covers this view.")}</div>}
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
                    {shown ? t("on the map") : t("show")}
                  </button>
                </div>
                <div className="mt-0.5 text-[11.5px] text-muted">
                  {fmt.sensor(r.sensor)} · {r.first_date} → {r.last_date}
                  {r.confidence ? ` · ${t("{level} confidence", { level: t(r.confidence) })}` : ""}
                </div>
                {r.in_area && (
                  <div className="mt-1 text-[12px] text-ink-2">
                    {t("{n} points here", { n: fmt.int(r.in_area.n) })} · {t("median")} <span className="font-mono">{fmt.vel(r.in_area.vel_median)}</span>, {t("range")}{" "}
                    <span className="font-mono">
                      {fmt.vel(r.in_area.vel_min)} … {fmt.vel(r.in_area.vel_max)}
                    </span>{" "}
                    mm/yr{r.in_area.n_below ? ` · ${t("{n} faster than −10 away", { n: fmt.int(r.in_area.n_below) })}` : ""}
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
          aria-label={t("Swipe position")}
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
          <div className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-[13px] font-bold text-on-accent shadow-lg">⇆</div>
          <div className="absolute top-16 right-5 rounded bg-bg/85 px-2 py-0.5 text-[11.5px] whitespace-nowrap text-ink-2">A</div>
          <div className="absolute top-16 left-5 rounded bg-bg/85 px-2 py-0.5 text-[11.5px] whitespace-nowrap text-ink-2">B</div>
        </div>
      )}

      {floodsOn && !finder && !!floodsQ.data?.features.length && (
        <div className="absolute top-16 left-3 z-10 max-h-[calc(100%-200px)] w-[min(360px,calc(100%-24px))] overflow-y-auto rounded-xl">
          <Fold
            id="explorer.floodhub"
            collapse={(docked && dockOpen) || !!themeSel}
            expand={!!floodSel}
            title={t("FLOOD OUTLOOK · 24 H")}
            extra={
              floodSel ? (
                <button type="button" className="text-[11.5px] text-accent hover:underline" onClick={() => setFloodSel(null)}>
                  {t("whole area")}
                </button>
              ) : undefined
            }
          >
            <FloodHub
              outlook={outlookQ.data}
              area={floodArea}
              feature={floodSel ? (floodsQ.data?.features.find((f) => f.id === floodSel) ?? null) : null}
              loading={outlookQ.isFetching}
              error={outlookQ.error ? ts((outlookQ.error as Error).message) : null}
            />
            <label className="mt-2.5 flex items-center gap-1.5 text-[11.5px] text-muted">
              <input type="checkbox" className="accent-accent" checked={floodRiskColors} onChange={(e) => setFloodRiskColors(e.target.checked)} />
              {t("colour the spots by today's risk (else by cause)")}
            </label>
            {floodRiskColors && (
              <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 pl-5 text-[11.5px] text-ink-2">
                {(["low", "watch", "high", "very_high"] as const).map((l) => (
                  <span key={l} className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: `rgb(${LEVEL_COLOR[l].join(",")})` }} />
                    {t({ low: "Low", watch: "Watch", high: "High", very_high: "Very high" }[l])}
                  </span>
                ))}
              </div>
            )}
          </Fold>
        </div>
      )}
      {layers.length === 0 && !floodsOn && (
        <div className="absolute top-1/2 left-1/2 z-10 w-[min(420px,90%)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line-2 bg-panel/95 p-6 text-center shadow-2xl backdrop-blur">
          <div className="text-[15px] font-semibold">{t("No product on the map")}</div>
          <p className="mt-2 text-[13px] leading-relaxed text-muted">
            {t("Click the eye next to a product in the project tree (or the product name) to show its points here, like a layer in QGIS.")}
          </p>
          <Button className="mt-4" onClick={() => go({ page: "overview" })}>
            {t("Go to the overview")}
          </Button>
        </div>
      )}

      {/* right panel */}
      {layers.length > 0 && !panelsOpen && (
        <div className="absolute top-3 right-3 z-10">
          <ColumnToggle open={false} side="right" label={t("Layers · {n}", { n: layers.length })} onClick={() => setPanelsOpen(true)} />
        </div>
      )}
      {layers.length > 0 && panelsOpen && (
        <div
          className="pointer-events-none absolute top-3 right-3 z-10 flex w-[min(360px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto"
          style={{ bottom: docked ? dockH + 24 : 12 }}
        >
          <div className="flex justify-end !pointer-events-none [&>*]:pointer-events-auto">
            <ColumnToggle open side="right" label={t("layer")} onClick={() => setPanelsOpen(false)} />
          </div>
          {cmp.mode !== "off" && (
            <div className="rounded-xl border border-accent-line bg-panel/95 p-3 shadow-xl shadow-black/30 backdrop-blur">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("COMPARE")}</span>
                <div className="ml-auto flex rounded-md border border-line-2 p-0.5">
                  {(["swipe", "diff"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      aria-pressed={cmp.mode === m}
                      onClick={() => setCmp((c) => ({ ...c, mode: m }))}
                      className={`h-6 rounded px-2.5 text-[12px] ${cmp.mode === m ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
                    >
                      {m === "swipe" ? t("Swipe") : t("Difference")}
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
                    className="h-7 min-w-0 flex-1 rounded-md border border-line-2 bg-sunken px-1.5 text-[12px] text-ink"
                  >
                    {layers.map((l) => (
                      <option key={l.key} value={l.key}>
                        {l.project} v{l.product.split("_v").pop()}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              {cmp.a === cmp.b && <div className="mt-2 text-[12px] text-warn">{t("Choose two different products.")}</div>}
              {comparing && (() => {
                const ta = summary(layers.find((l) => l.key === cmp.a)!);
                const tb = summary(layers.find((l) => l.key === cmp.b)!);
                return ta && tb && ta.track_id !== tb.track_id ? (
                  <div className="mt-2 rounded-md bg-warn-bg px-2 py-1.5 text-[11.5px] leading-snug text-warn-ink">
                    {t("Different tracks ({a} / {b}): each measures along its own line of sight, so a difference also contains geometry, not only motion.", {
                      a: ta.track_id,
                      b: tb.track_id,
                    })}
                  </div>
                ) : null;
              })()}
              {cmp.mode === "swipe" && comparing && <div className="mt-2 text-[11.5px] text-faint">{t("A left of the handle, B right. Drag the handle or use ← →.")}</div>}
              {cmp.mode === "diff" && comparing && (
                <>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px]">
                    <label className="flex items-center gap-1.5">
                      {t("Cell")}
                      <select
                        value={cmp.cell}
                        onChange={(e) => setCmp((c) => ({ ...c, cell: Number(e.target.value) }))}
                        className="h-7 rounded-md border border-line-2 bg-sunken px-1.5 text-[12px]"
                      >
                        {[20, 50, 100, 200, 500].map((v) => (
                          <option key={v} value={v}>
                            {v} m
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-1.5" title={t("Each product has its own reference area: remove the median difference")}>
                      <input type="checkbox" className="accent-accent" checked={cmp.align} onChange={(e) => setCmp((c) => ({ ...c, align: e.target.checked }))} />
                      {t("remove median offset")}
                    </label>
                  </div>
                  {diff.isFetching && <div className="mt-2 text-[12px] text-accent-ink">{t("Computing…")}</div>}
                  {diff.error && <div className="mt-2 text-[12px] text-bad">{ts((diff.error as Error).message)}</div>}
                  {diff.data && diff.data.meta.n === 0 && <div className="mt-2 text-[12px] text-muted">{t("The two products have no cell in common.")}</div>}
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
                          <span className="text-muted">{t(k)}</span>
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
                title={t("median per {cell} m cell", { cell: diff.data.meta.cell_m })}
                label={t("B − A velocity")}
              />
            </div>
          )}

          <Fold
            id="explorer.layers"
            title={t("LAYERS · {n}", { n: layers.length })}
            extra={
              <label className="flex items-center gap-1 text-[11px] text-muted" title={t("Zoomed out, the median velocity in hexagons; zoomed in, the points")}>
                <input type="checkbox" className="accent-accent" checked={hexOn} onChange={(e) => setHexOn(e.target.checked)} />
                {t("hexagons")}
              </label>
            }
          >
            <div className="space-y-2">
              {layers.map((l) => {
                const tr = summary(l);
                const d = byKey[l.key];
                return (
                  <div key={l.key} className="rounded-lg border border-line bg-panel-2 px-2.5 py-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={l.visible}
                        onChange={() => toggleLayer(l.key)}
                        aria-label={t("Show {product}", { product: l.product })}
                        className="h-4 w-4 accent-accent"
                      />
                      <button type="button" onClick={() => setFocus(l.key)} className="min-w-0 flex-1 truncate text-left text-[12.5px] hover:text-accent" title={t("Zoom to layer")}>
                        <span className="font-mono">{l.project}</span>{" "}
                        <span className="text-muted">v{l.product.split("_v").pop()}</span>
                      </button>
                      <button type="button" onClick={() => (removeLayer(l.key), th.dropProduct(l.project, l.product))} title={t("Remove from the map")} className="text-faint hover:text-bad">
                        ×
                      </button>
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 pl-6 text-[11px] text-muted">
                      <span className="truncate">
                        {tr ? `${fmt.sensor(tr.sensor)} ${t(tr.direction)}` : ""} · {d ? t("{n} pts", { n: fmt.int(d.meta.n) }) : "…"}
                      </span>
                      <select
                        value={l.mode ?? "auto"}
                        onChange={(e) => setMode(l.key, e.target.value as MapLayer["mode"])}
                        aria-label={t("Rendering")}
                        title={t("Points: the whole product at once. Tiles: PMTiles vector tiles, read as you pan (auto: above 2.5 M points)")}
                        className="h-6 rounded border border-line-2 bg-sunken px-1 text-[11px] text-ink-2"
                      >
                        <option value="auto">{t("auto")}{d ? ` (${t(d.kind)})` : ""}</option>
                        <option value="points">{t("points")}</option>
                        <option value="tiles">{t("tiles")}</option>
                      </select>
                      <input
                        type="range"
                        min={0.1}
                        max={1}
                        step={0.05}
                        value={l.opacity}
                        onChange={(e) => setOpacity(l.key, Number(e.target.value))}
                        aria-label={t("Opacity")}
                        className="ml-auto w-20 accent-accent"
                      />
                    </div>
                    {d && <VelocityKind meta={d.meta} value={l.vel ?? null} onChange={(v) => setVel(l.key, v)} />}
                    {d?.meta.calibration_available && (
                      <CalibrationToggle cal={d.meta.calibration_available} on={!!l.calibrated} onChange={(on) => setCalibrated(l.key, on)} />
                    )}
                    {d && l.visible && !(cmp.mode === "diff" && comparing) && (
                      <LayerLegend meta={d.meta} hex={hexByKey[l.key]?.size} confidence={tr?.product?.confidence} defaultOpen={l.key === top?.key} onRange={(r) => setRange(l.key, r)} />
                    )}
                    <ThemeChips project={l.project} product={l.product} on={(k) => th.themes.some((x) => x.key === `${l.project}/${l.product}#${k}`)} toggle={(k) => th.toggle(l.project, l.product, k)} />
                    {th.themes
                      .filter((x) => x.project === l.project && x.product === l.product)
                      .map((x) => (
                        <div key={x.key} className="pl-6">
                          <ThemeCard th={x} d={themeData[x.key]} error={themeErr[x.key]} onToggle={() => th.toggle(x.project, x.product, x.kind)} onUpdate={(patch) => th.update(x.key, patch)} />
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
            {errors.length > 0 && <div className="mt-2 text-[12px] text-bad">{errors.join(" · ")}</div>}
          </Fold>

        </div>
      )}

      {/* the clicked thematic object: the panel of its analysis page */}
      {themeSel && !docked && (() => {
        const x = th.themes.find((y) => y.key === themeSel.key);
        const d = x && themeData[x.key];
        return x && d ? (
          <div className="absolute bottom-3 left-[92px] z-20 max-h-[60%] w-[min(560px,calc(100%-104px))] overflow-y-auto max-md:left-3 max-md:w-[calc(100%-24px)]">
            <ThemeDetail th={x} d={d} i={themeSel.i} onClose={() => setThemeSel(null)} />
          </div>
        ) : null;
      })()}

      {/* bottom dock: the selected point or the drawn area, with its series and rainfall */}
      {docked && (
        <div
          ref={dockEl}
          className="absolute right-3 bottom-3 left-[92px] z-20 max-md:left-3"
        >
          <div className="rounded-xl border border-line-2 bg-panel/95 shadow-xl shadow-black/30 backdrop-blur">
            <div className="flex items-center gap-2 px-3 py-2">
              <button type="button" onClick={() => setDockOpen((o) => !o)} aria-expanded={dockOpen} className="flex min-w-0 flex-1 items-center gap-2 text-left hover:text-accent">
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className={`flex-none text-muted transition-transform ${dockOpen ? "" : "rotate-180"}`}>
                  <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {selection && selMeta ? (
                  <span className="truncate text-[13px]">
                    <span className="font-semibold">{t("Point #{n}", { n: selection.index })}</span>
                    {point.data && (
                      <span className="text-muted">
                        {" "}· <span className="font-mono text-ink-2">{fmt.vel(point.data.vel)}</span> mm/yr · {selLayer?.project}
                      </span>
                    )}
                  </span>
                ) : showProfile ? (
                  <span className="truncate text-[13px]">
                    <span className="font-semibold">{t("Profile")}</span>
                    <span className="text-muted">
                      {" "}· {(lineLength / 1000).toFixed(2)} km
                      {profile.data && <> · {t("{n} points", { n: fmt.int(profile.data.n) })}</>} · {top?.project}
                    </span>
                  </span>
                ) : (
                  <span className="truncate text-[13px]">
                    <span className="font-semibold">{t("Area mean")}</span>
                    {area && area.info.n > 0 && (
                      <span className="text-muted">
                        {" "}· {t("{n} points", { n: fmt.int(area.info.n) })} · {t("mean")} <span className="font-mono text-ink-2">{fmt.vel(area.info.vel_mean)}</span> mm/yr
                      </span>
                    )}
                  </span>
                )}
              </button>
              <button
                type="button"
                className="text-faint hover:text-ink"
                onClick={() => (selection ? select(null) : showProfile ? (setLine([]), setHoverDist(null)) : (setRing([]), setArea(null)))}
                aria-label={t("Close")}
              >
                ×
              </button>
            </div>
            {dockOpen && selection && selMeta && (
              <div className="flex gap-4 px-3 pb-3 max-md:flex-col">
                <div className="w-[220px] flex-none">
                  {point.data ? (
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
                      {[
                        ["Velocity", `${fmt.vel(point.data.vel)} ± ${fmt.num(point.data.vel_std_mm_yr)}`],
                        ["Coherence", fmt.num(point.data.temporal_coherence, 2)],
                        ["Height", `${fmt.num(point.data.height_m)} m`],
                        ["Seasonal amp.", `${fmt.num(point.data.seasonal_amp_mm)} mm`],
                        ["Lon", point.data.lon.toFixed(5)],
                        ["Lat", point.data.lat.toFixed(5)],
                      ].map(([k, v]) => (
                        <div key={k} className="contents">
                          <span className="text-muted">{t(k)}</span>
                          <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-6 text-center text-[12px] text-muted">{point.error ? ts((point.error as Error).message) : t("Loading…")}</div>
                  )}
                  <div className="mt-2 text-[11px] leading-snug text-faint">{t("Velocity in mm/yr; displacement along the line of sight, relative to the reference area, 0 at the first date")}</div>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex justify-end">{pointRain.control}</div>
                  {pointSeries && <TimeSeries dates={selMeta.dates} values={pointSeries} rain={pointRain.series} height={240} />}
                </div>
              </div>
            )}
            {dockOpen && showProfile && (
              <div className="flex gap-4 px-3 pb-3 max-md:flex-col">
                <div className="w-[220px] flex-none text-[12px]">
                  <label className="flex items-center justify-between gap-2 text-muted">
                    {t("Half width")}
                    <select value={halfWidth} onChange={(e) => setHalfWidth(Number(e.target.value))} className="h-7 rounded border border-line-2 bg-sunken px-1 font-mono text-[12px] text-ink">
                      {[10, 25, 50, 100, 250, 500].map((w) => (
                        <option key={w} value={w}>
                          {w} m
                        </option>
                      ))}
                    </select>
                  </label>
                  {profile.data && (
                    <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
                      {[
                        ["Length", `${(profile.data.length_m / 1000).toFixed(2)} km`],
                        ["Points", fmt.int(profile.data.n)],
                        ["Min", profile.data.vel.length ? fmt.vel(Math.min(...profile.data.vel)) : "–"],
                        ["Max", profile.data.vel.length ? fmt.vel(Math.max(...profile.data.vel)) : "–"],
                      ].map(([k, v]) => (
                        <div key={k} className="contents">
                          <span className="text-muted">{t(k)}</span>
                          <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 text-[11px] leading-snug text-faint">
                    {t("Above: ground height (Mapzen Terrain Tiles) and the height of the points; below: their velocity in mm/yr, white = median every {m} m", { m: profile.data ? fmt.int(profile.data.bin_m) : "–" })}
                    {profile.data && profile.data.shown < profile.data.n ? ` · ${t("{n} shown", { n: fmt.int(profile.data.shown) })}` : ""}
                  </div>
                </div>
                <div className="min-w-0 flex-1">
                  {profile.data && top && byKey[top.key] ? (
                    <ProfileChart data={profile.data} terrain={terrainQ.data ?? null} classes={byKey[top.key]!.meta.classes} hover={hoverDist} onHover={setHoverDist} />
                  ) : (
                    <div className="py-6 text-center text-[12px] text-muted">{profile.error ? ts((profile.error as Error).message) : t("Computing…")}</div>
                  )}
                </div>
              </div>
            )}
            {dockOpen && !selection && (area || areaBusy) && (
              <div className="flex gap-4 px-3 pb-3 max-md:flex-col">
                <div className="w-[220px] flex-none text-[12px]">
                  {areaBusy && <div className="py-4 text-muted">{t("Computing…")}</div>}
                  {area && area.info.n === 0 && <div className="py-3 text-muted">{t("No point inside the area.")}</div>}
                  {area && area.info.n > 0 && (
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                      {[
                        ["Points", fmt.int(area.info.n)],
                        ["Mean", fmt.vel(area.info.vel_mean)],
                        ["Min", fmt.vel(area.info.vel_min)],
                        ["Max", fmt.vel(area.info.vel_max)],
                      ].map(([k, v]) => (
                        <div key={k} className="contents">
                          <span className="text-muted">{t(k)}</span>
                          <span className="text-right font-mono text-[11.5px] text-ink-2">{v}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 text-[11px] leading-snug text-faint">{t("Velocities in mm/yr; mean series of the points inside the area (each 0 at the first date), band = ±1 standard deviation")}</div>
                </div>
                <div className="min-w-0 flex-1">
                  {area && area.info.n > 0 && areaMeta && (
                    <>
                      <div className="mb-1 flex justify-end">{areaRain.control}</div>
                      <TimeSeries dates={areaMeta.dates} values={areaSeries!} spread={areaSpread ?? undefined} rain={areaRain.series} height={240} />
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
