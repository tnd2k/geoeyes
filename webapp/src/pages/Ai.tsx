// Machine learning research (route #/ai): statistical and machine-learning models on the analysis grid of a product.
// - Susceptibility: thematic layers (terrain, land cover, buildings, soil) combined by logistic regression, random
//   forest and gradient boosting to explain where InSAR sees the ground move, judged by spatial cross-validation.
// - Forecast: deformation change ahead, the global model only where it beats simple baselines in a backtest.
// Method and sources: docs/en/research/ai-susceptibility.md, docs/en/research/ai-forecasting.md.
import { SolidPolygonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import { api, type ForecastCell, type GridMeta, type SusceptibilitySummary, type Workspace } from "../api";
import { lang, t, ts } from "../i18n";
import { BasemapPicker } from "../components/BasemapPicker";
import { mapStyle, type Base } from "../map";
import { useWarnings } from "../notify";
import { useApp } from "../state";
import { Button, ColumnToggle, fmt, Fold, usePersisted } from "../ui";

type RGB = [number, number, number];
type Tab = "susceptibility" | "forecast";

const LEVEL_RGB: RGB[] = [[26, 152, 80], [145, 207, 96], [254, 224, 139], [252, 141, 89], [215, 48, 39]];
const LEVELS = ["Very low", "Low", "Moderate", "High", "Very high"];
const NA_RGB: RGB = [75, 90, 115];
const VIRIDIS: RGB[] = [[68, 1, 84], [70, 51, 127], [54, 92, 141], [39, 127, 142], [31, 161, 135], [74, 194, 109], [159, 218, 58], [253, 231, 37]];
const DIVERGING: RGB[] = [[178, 24, 43], [214, 96, 77], [244, 165, 130], [127, 139, 160], [146, 197, 222], [67, 147, 195], [33, 102, 172]];
const MODEL_LABEL: Record<string, string> = {
  logistic: "Logistic regression",
  random_forest: "Random forest",
  gradient_boosting: "Gradient boosting",
  last: "No change (last value)",
  linear: "Linear trend",
  seasonal: "Trend + annual",
  gbm: "Global gradient boosting",
};

// what each map of the susceptibility tab shows
const SUSC_VIEWS: Record<string, { what: string; read: string[] }> = {
  probability: {
    what: "Probability that a cell moves faster than the threshold, predicted from the thematic layers only (not from InSAR): also where InSAR has no points.",
    read: [
      "Red: the layers there look like the places where InSAR measured fast motion.",
      "Read it as an association, not a cause: groundwater pumping, the main driver of subsidence, is not among the layers.",
      "Hatched cells are outside the range of the training data: the model extrapolates.",
    ],
  },
  label: {
    what: "What InSAR observed: the cells used to train and test the models.",
    read: ["Red: moving at or above the threshold. Green: below it. Grey: no InSAR points (no label)."],
  },
  outside: {
    what: "Cells where at least one layer lies outside the 1–99 % range of the cells with InSAR: predictions there are extrapolations.",
    read: ["Orange: extrapolation. Most often vegetation, water or the edges of the scene, where InSAR has no points."],
  },
};
const GROUP_TEXT: Record<string, string> = {
  terrain: "From the DEM of the project (a surface model: buildings are included).",
  "land cover": "From ESA WorldCover 10 m (2021): share of the cell in each class, and distance to permanent water.",
  buildings: "From Overture Maps buildings (OpenStreetMap, Google and Microsoft footprints): count, roof cover, height where known.",
  soil: "From SoilGrids 2.0 (250 m): clay content of the top soil (g/kg).",
  climate: "From the rainfall of the hazard analysis (coarse grid: not used as a predictor by default).",
};

function rgb(c: RGB, a = 1) {
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`;
}

function ramp(colors: RGB[], x: number): RGB {
  const v = Math.min(1, Math.max(0, x)) * (colors.length - 1);
  const i = Math.min(colors.length - 2, Math.floor(v));
  const f = v - i;
  return [0, 1, 2].map((k) => Math.round(colors[i][k] * (1 - f) + colors[i + 1][k] * f)) as RGB;
}

interface Grid {
  meta: GridMeta;
  buf: Float32Array;
  f: Record<string, number>;
}

function value(g: Grid, i: number, name: string): number {
  return g.buf[i * g.meta.fields.length + g.f[name]];
}

function GradientLegend({ colors, lo, hi, unit, left, right }: { colors: RGB[]; lo: number; hi: number; unit: string; left?: string; right?: string }) {
  return (
    <div className="mt-2">
      <div className="h-3 rounded" style={{ background: `linear-gradient(90deg, ${colors.map((c) => rgb(c)).join(",")})` }} />
      <div className="mt-1 flex justify-between font-mono text-[11px] text-ink-2">
        <span>{fmt.num(lo, Math.abs(hi - lo) < 5 ? 2 : 0)}</span>
        <span className="font-sans text-faint">{unit}</span>
        <span>{fmt.num(hi, Math.abs(hi - lo) < 5 ? 2 : 0)}</span>
      </div>
      {(left || right) && (
        <div className="flex justify-between text-[11px] text-muted">
          <span>{left}</span>
          <span>{right}</span>
        </div>
      )}
    </div>
  );
}

function Swatches({ items }: { items: { color: RGB; label: string; alpha?: number }[] }) {
  return (
    <div className="mt-2 space-y-[3px]">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-2 text-[12px]">
          <span className="h-3 w-3 flex-none rounded-[3px]" style={{ background: rgb(it.color, it.alpha ?? 1) }} />
          <span className="text-ink-2">{it.label}</span>
        </div>
      ))}
    </div>
  );
}

function About({ what, read }: { what: string; read: string[] }) {
  return (
    <div className="mt-3 rounded-lg border border-line bg-panel-2 px-2.5 py-2">
      <div className="text-[10.5px] font-semibold tracking-[1px] text-muted uppercase">{t("What this map shows")}</div>
      <p className="mt-1 text-[12px] leading-snug text-ink-2">{t(what)}</p>
      {read.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11.5px] leading-snug text-muted">
          {read.map((r) => (
            <li key={r}>{t(r)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ImportanceBars({ imp, layers }: { imp: Record<string, number>; layers: SusceptibilitySummary["layers"] }) {
  const rows = Object.entries(imp)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  const max = rows[0]?.[1] || 1;
  return (
    <div className="mt-2 space-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[112px_1fr_44px] items-center gap-2 text-[11.5px]">
          <span className="truncate text-ink-2" title={t(layers[k]?.label ?? k)}>
            {t(layers[k]?.label ?? k)}
          </span>
          <span className="h-2 rounded bg-[#1a2740]">
            <span className="block h-full rounded bg-accent" style={{ width: `${(100 * v) / max}%` }} />
          </span>
          <span className="text-right font-mono text-[11px] text-muted">{v.toFixed(3)}</span>
        </div>
      ))}
    </div>
  );
}

function ForecastChart({ c }: { c: ForecastCell }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const dates = [...c.dates, ...c.forecast.map((f) => f.date)];
    const x = dates.map((d) => Date.parse(d) / 1000);
    const nH = c.dates.length;
    const pad = (arr: (number | null)[], before: number) => [...Array(before).fill(null), ...arr];
    const last = c.series_mm[nH - 1];
    const fcm = [last, ...c.forecast.map((f) => f.change_mm)];
    const lo80 = [last, ...c.forecast.map((f) => f.lo80)];
    const hi80 = [last, ...c.forecast.map((f) => f.hi80)];
    const lo95 = [last, ...c.forecast.map((f) => f.lo95)];
    const hi95 = [last, ...c.forecast.map((f) => f.hi95)];
    const data = [
      x,
      [...c.series_mm, ...c.forecast.map(() => null)],
      pad(fcm, nH - 1),
      pad(hi95, nH - 1),
      pad(lo95, nH - 1),
      pad(hi80, nH - 1),
      pad(lo80, nH - 1),
    ] as uPlot.AlignedData;
    const axis = { stroke: "#93a4bf", grid: { stroke: "#1a2740", width: 1 }, ticks: { stroke: "#22324d", width: 1 }, font: "11px Inter, system-ui, sans-serif" };
    const plot = new uPlot(
      {
        width: el.clientWidth,
        height: 190,
        padding: [8, 8, 0, 0],
        legend: { show: false },
        cursor: { drag: { x: false, y: false } },
        scales: { x: { time: true } },
        axes: [
          { ...axis, values: (_u, v) => v.map((s) => new Date(s * 1000).toISOString().slice(0, 7)) },
          { ...axis, size: 48, label: t("mm (LOS)"), labelSize: 14, labelFont: "11px Inter, sans-serif" },
        ],
        series: [
          {},
          { stroke: "#4cc2ff", width: 1.6, points: { show: true, size: 5, fill: "#4cc2ff", stroke: "#0b1220" }, spanGaps: true },
          { stroke: "#f5b84b", width: 2, dash: [6, 4], points: { show: true, size: 5, fill: "#f5b84b" } },
          { stroke: "transparent", points: { show: false } },
          { stroke: "transparent", points: { show: false } },
          { stroke: "transparent", points: { show: false } },
          { stroke: "transparent", points: { show: false } },
        ],
        bands: [
          { series: [3, 4], fill: "rgba(245,184,75,0.12)" },
          { series: [5, 6], fill: "rgba(245,184,75,0.25)" },
        ],
      },
      data,
      el,
    );
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height: 190 }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [c]);
  return (
    <div>
      <div ref={box} className="w-full" />
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-[#4cc2ff]" /> {t("observed (cell median, 0 at the first date)")}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-4 border-t-2 border-dashed border-[#f5b84b]" /> {t("forecast")}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-4 bg-[rgba(245,184,75,0.35)]" /> {t("80 % / 95 % interval")}
        </span>
      </div>
    </div>
  );
}

export function Ai({ ws, project, product, tab: routeTab }: { ws: Workspace | undefined; project?: string; product?: string; tab?: string }) {
  const { go, layers } = useApp();
  const qc = useQueryClient();
  const tab: Tab = routeTab === "forecast" ? "forecast" : "susceptibility";
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const [base, setBase] = useState<Base>("dark");
  const [view, setView] = useState("probability");
  const [horizon, setHorizon] = useState<number | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [labelRate, setLabelRate] = useState("");
  const [blockM, setBlockM] = useState(1000);
  const [busy, setBusy] = useState("");
  const [leftOpen, setLeftOpen] = usePersisted("ai.left", true);
  const [rightOpen, setRightOpen] = usePersisted("ai.right", true);

  const choices = useMemo(() => {
    const out: { project: string; product: string; label: string }[] = [];
    Object.values(ws?.projects ?? {}).forEach((p) =>
      p.tracks.forEach((tr) => tr.product && out.push({ project: p.name, product: tr.product.id, label: `${p.name} · ${fmt.sensor(tr.sensor)} ${t(tr.direction)} v${tr.product.version}` })),
    );
    return out;
  }, [ws]);
  useEffect(() => {
    if (project && product) return;
    const shown = layers.find((l) => l.visible && choices.some((c) => c.product === l.product));
    const pick = shown ? { project: shown.project, product: shown.product } : choices[0];
    if (pick) go({ page: "ai", name: pick.project, product: pick.product, tab });
  }, [project, product, layers, choices, go, tab]);

  const status = useQuery({
    queryKey: ["ai", project, product],
    queryFn: () => api.ai(project!, product!),
    enabled: !!project && !!product,
    refetchInterval: (q) => (q.state.data?.susceptibility.running || q.state.data?.forecast.running ? 2500 : false),
  });
  const susc = status.data?.susceptibility.summary ?? null;
  const fc = status.data?.forecast.summary ?? null;
  const job = status.data?.[tab];
  useWarnings(`susceptibility:${project}/${product}:${susc?.created}`, `AI · ${project}`, susc?.warnings, project && product ? `#/ai/${encodeURIComponent(project)}/${encodeURIComponent(product)}` : undefined);

  const grid = useQuery({
    queryKey: ["ai-grid", project, product, tab, tab === "susceptibility" ? susc?.created : fc?.created],
    queryFn: async (): Promise<Grid> => {
      const { meta, buf } = await api.aiGrid(project!, product!, tab === "susceptibility" ? "susceptibility/grid" : "forecast/cells");
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: tab === "susceptibility" ? !!susc : !!fc,
    staleTime: Infinity,
  });
  const fcell = useQuery({
    queryKey: ["ai-fcell", project, product, fc?.created, sel],
    queryFn: () => api.aiForecastCell(project!, product!, sel!),
    enabled: tab === "forecast" && !!fc && sel != null,
  });
  useEffect(() => setSel(null), [tab, susc?.created, fc?.created]);
  useEffect(() => {
    if (susc && !labelRate) setLabelRate(String(susc.params.label_rate));
  }, [susc, labelRate]);
  const h = horizon ?? fc?.horizons_days[fc.horizons_days.length - 1] ?? null;
  useEffect(() => {
    if (tab === "forecast" && view !== "change" && view !== "width") setView(fc?.chosen === "last" ? "width" : "change");
    if (tab === "susceptibility" && (view === "change" || view === "width")) setView("probability");
  }, [tab, view, fc?.chosen]);

  // ------------------------------------------------------------ map
  useEffect(() => {
    if (!mapEl.current) return;
    const m = new maplibregl.Map({ container: mapEl.current, style: mapStyle("dark"), center: [105.82, 21.02], zoom: 10, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false });
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
  const bounds = susc?.grid.bounds;
  useEffect(() => {
    if (bounds && map.current) map.current.fitBounds(bounds as [number, number, number, number], { padding: 60, duration: 600 });
  }, [bounds?.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const polys = useMemo(() => {
    const g = grid.data;
    if (!g) return null;
    const hx = (0.5 * g.meta.cell_m) / (111320 * Math.cos(((g.meta.lat0 ?? g.meta.origin[1]) * Math.PI) / 180));
    const hy = (0.5 * g.meta.cell_m) / 110540;
    const [lon0, lat0] = g.meta.origin;
    return Array.from({ length: g.meta.n }, (_, i) => {
      const x = lon0 + value(g, i, "dlon");
      const y = lat0 + value(g, i, "dlat");
      return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
    });
  }, [grid.data]);

  // forecast colour scale (mm): ±P98 of |change|, or 0..P98 of the interval width
  const fcLim = useMemo(() => {
    const g = grid.data;
    if (!g || tab !== "forecast" || !h || g.f[`c${h}`] == null) return 1;
    const vals: number[] = [];
    for (let i = 0; i < g.meta.n; i += 3) {
      const v = view === "width" ? value(g, i, `u${h}`) - value(g, i, `l${h}`) : Math.abs(value(g, i, `c${h}`));
      if (Number.isFinite(v)) vals.push(v);
    }
    vals.sort((a, b) => a - b);
    return vals[Math.floor(vals.length * 0.98)] || 1;
  }, [grid.data, tab, h, view]);

  // colour of a cell for the current view
  const colorOf = useMemo(() => {
    const g = grid.data;
    if (!g) return null;
    if (tab === "forecast") {
      if (!h || g.f[`c${h}`] == null) return null;
      const key = view === "width" ? null : `c${h}`;
      const lim = fcLim;
      return (i: number): [number, number, number, number] => {
        if (key) {
          const v = value(g, i, key);
          if (!Number.isFinite(v)) return [...NA_RGB, 60];
          return [...ramp(DIVERGING, 0.5 + v / (2 * lim)), 220];
        }
        const w = value(g, i, `u${h}`) - value(g, i, `l${h}`);
        return Number.isFinite(w) ? [...ramp(VIRIDIS, w / lim), 220] : [...NA_RGB, 60];
      };
    }
    if (view === "probability")
      return (i: number): [number, number, number, number] => {
        const p = value(g, i, "probability");
        if (!Number.isFinite(p)) return [...NA_RGB, 40];
        const c = LEVEL_RGB[Math.min(4, Math.max(0, value(g, i, "class")))];
        return [...c, value(g, i, "outside") > 0 ? 90 : 215];
      };
    if (view === "label")
      return (i: number): [number, number, number, number] => {
        const l = value(g, i, "label");
        return Number.isFinite(l) ? [...(l > 0 ? LEVEL_RGB[4] : LEVEL_RGB[0]), 215] : [...NA_RGB, 40];
      };
    if (view === "outside") return (i: number): [number, number, number, number] => (value(g, i, "outside") > 0 ? [245, 150, 60, 200] : [...NA_RGB, 50]);
    const st = g.meta.stats?.[view];
    const lo = st?.p02 ?? 0;
    const hi = st?.p98 ?? 1;
    return (i: number): [number, number, number, number] => {
      const v = value(g, i, view);
      return Number.isFinite(v) ? [...ramp(VIRIDIS, (v - lo) / (hi - lo || 1)), 215] : [...NA_RGB, 40];
    };
  }, [grid.data, view, tab, h, fcLim]);

  useEffect(() => {
    const ov = overlay.current;
    if (!ov) return;
    const g = grid.data;
    if (!g || !polys || !colorOf) {
      ov.setProps({ layers: [] });
      return;
    }
    ov.setProps({
      layers: [
        new SolidPolygonLayer<{ i: number; ring: number[][] }>({
          id: `ai-${tab}-${view}-${h}`,
          data: polys,
          getPolygon: (d) => d.ring as never,
          getFillColor: (d) => (d.i === sel ? [255, 255, 255, 255] : colorOf(d.i)),
          updateTriggers: { getFillColor: [view, sel, h, tab] },
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 110],
          onClick: (info) => info.object && setSel(info.object.i),
        }),
      ] as never,
      getTooltip: ({ object }: { object?: { i: number } }) => {
        if (!object) return null;
        const style = { background: "#0b1220", color: "#e6edf7", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "JetBrains Mono, monospace" };
        if (tab === "forecast" && h) return { text: `${fmt.vel(value(g, object.i, `c${h}`))} mm · ${h} ${t("days")}`, style };
        const p = value(g, object.i, "probability");
        const lab = value(g, object.i, "label");
        return { text: `p = ${Number.isFinite(p) ? p.toFixed(2) : "–"}${Number.isFinite(lab) ? ` · InSAR ${fmt.vel(value(g, object.i, "rate_mm_yr"))} mm/yr` : ""}`, style };
      },
    });
  }, [grid.data, polys, colorOf, sel, view, h, tab]);

  const run = async () => {
    if (!project || !product) return;
    setBusy("");
    try {
      const params: Record<string, unknown> = tab === "susceptibility" ? { label_rate: Number(labelRate) || 5, block_m: blockM } : {};
      await api.aiRun(project, product, tab, params);
      await qc.invalidateQueries({ queryKey: ["ai", project, product] });
    } catch (e) {
      const msg = (e as Error).message;
      setBusy(/method not allowed|not found/i.test(msg) ? `${msg}: ${t("the running server predates this page, restart geoeyes serve")}` : ts(msg));
    }
  };

  const groups = useMemo(() => {
    const out: Record<string, string[]> = {};
    Object.entries(susc?.layers ?? {}).forEach(([k, v]) => {
      if (grid.data?.meta.stats?.[k]) (out[v.group] ??= []).push(k);
    });
    return out;
  }, [susc, grid.data]);
  const g = grid.data;

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div className="absolute inset-0">
        <div ref={mapEl} className="h-full w-full" />
      </div>

      {!leftOpen && (
        <div className="absolute top-3 left-3 z-10">
          <ColumnToggle open={false} side="left" label={t("Machine learning research")} onClick={() => setLeftOpen(true)} />
        </div>
      )}
      {leftOpen && (
        <div className="pointer-events-none absolute top-3 bottom-[184px] left-3 z-10 flex w-[min(370px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto">
          <Fold id="ai.run" title={t("MACHINE LEARNING RESEARCH")} extra={<ColumnToggle open side="left" label={t("Machine learning research")} onClick={() => setLeftOpen(false)} />}>
            <select
              value={project && product ? `${project}/${product}` : ""}
              onChange={(e) => {
                const [n, ...rest] = e.target.value.split("/");
                go({ page: "ai", name: n, product: rest.join("/"), tab });
              }}
              aria-label={t("Product")}
              className="h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink"
            >
              {choices.map((c) => (
                <option key={`${c.project}/${c.product}`} value={`${c.project}/${c.product}`}>
                  {c.label}
                </option>
              ))}
            </select>
            <div className="mt-2 flex rounded-lg border border-line-2 p-0.5">
              {(["susceptibility", "forecast"] as Tab[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={tab === k}
                  onClick={() => (setView(k === "forecast" ? "change" : "probability"), go({ page: "ai", name: project, product, tab: k }))}
                  className={`h-7 flex-1 rounded-md text-[12.5px] ${tab === k ? "bg-raised font-semibold text-ink" : "text-muted hover:text-ink"}`}
                >
                  {k === "susceptibility" ? t("Susceptibility from thematic layers") : t("Deformation forecast")}
                </button>
              ))}
            </div>
            {tab === "susceptibility" ? (
              <>
                <p className="mt-2 text-[12px] leading-snug text-muted">
                  {t("Combines thematic layers (terrain, land cover, buildings, soil) with statistical and machine-learning models to explain where InSAR sees the ground move.")}
                </p>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px] text-muted">
                  <label className="flex items-center gap-1.5" title={t("Cells moving at or above this rate (mm/yr, sinking or downslope) are labelled as moving")}>
                    <span className="w-20 flex-none">{t("Threshold")}</span>
                    <input value={labelRate} onChange={(e) => setLabelRate(e.target.value)} placeholder="5" className="h-7 w-full min-w-0 rounded-md border border-line-2 bg-[#0a1322] px-2 font-mono text-[12px] text-ink" />
                  </label>
                  <label className="flex items-center gap-1.5" title={t("Size of the spatial cross-validation blocks")}>
                    <span className="w-20 flex-none">{t("CV blocks")}</span>
                    <select value={blockM} onChange={(e) => setBlockM(Number(e.target.value))} className="h-7 w-full min-w-0 rounded-md border border-line-2 bg-[#0a1322] px-1 text-[12px] text-ink">
                      {[500, 1000, 2000, 5000].map((v) => (
                        <option key={v} value={v}>
                          {v} m
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {!status.data?.hazard && <div className="mt-2 rounded-md bg-[#2a2110] px-2 py-1 text-[11.5px] text-[#f5d08b]">{t("Run the hazard zoning of this product first: its cells are the labels.")}</div>}
              </>
            ) : (
              <p className="mt-2 text-[12px] leading-snug text-muted">
                {t("Forecasts the change of displacement of every cell; the machine-learning model is used only where it beats simple baselines in a backtest on the past.")}
              </p>
            )}
            <div className="mt-3 flex items-center gap-2">
              <Button variant="primary" disabled={!product || job?.running || (tab === "susceptibility" && !status.data?.hazard)} onClick={run}>
                {job?.running ? t("Running…") : (tab === "susceptibility" ? susc : fc) ? t("Run again") : t("Run")}
              </Button>
            </div>
            {busy && <div className="mt-2 text-[12px] text-bad">{busy}</div>}
            {(job?.running || job?.failed) && job.log.length > 0 && (
              <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-line bg-[#070c16] p-2 font-mono text-[11px] text-[#a9b8cf]">{job.log.join("\n")}</pre>
            )}
          </Fold>

          {tab === "susceptibility" && susc && (
            <Fold id="ai.models" title={t("MODELS")}>
              <div className="text-[12px] text-ink-2">
                {t("{n} cells with InSAR, {m} moving (≥ {r} mm/yr)", { n: fmt.int(susc.labels.cells), m: fmt.int(susc.labels.moving), r: susc.params.label_rate })}
              </div>
              <table className="mt-2 w-full text-[12px]">
                <thead>
                  <tr className="text-left text-[10.5px] tracking-[0.8px] text-muted uppercase">
                    <th className="py-1 font-semibold">{t("Model")}</th>
                    <th className="py-1 text-right font-semibold" title={t("Area under the ROC curve on held-out spatial blocks")}>
                      AUC
                    </th>
                    <th className="py-1 text-right font-semibold" title={t("Average precision on held-out spatial blocks")}>
                      AP
                    </th>
                    <th className="py-1 text-right font-semibold" title={t("AUC with random folds: inflated by spatial autocorrelation")}>
                      {t("random")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(susc.models).map(([m, v]) => (
                    <tr key={m} className={m === susc.chosen ? "text-ink" : "text-muted"}>
                      <td className="py-0.5">
                        {m === susc.chosen ? "▸ " : ""}
                        {t(MODEL_LABEL[m] ?? m)}
                      </td>
                      <td className="py-0.5 text-right font-mono">{fmt.num(v.spatial_cv.auc, 2)}</td>
                      <td className="py-0.5 text-right font-mono">{fmt.num(v.spatial_cv.ap, 2)}</td>
                      <td className="py-0.5 text-right font-mono text-faint">{fmt.num(v.random_cv.auc, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1.5 text-[11px] leading-snug text-faint">
                {t("AUC 0.5 = no skill, 1 = perfect. Spatial blocks of {b} m keep neighbours apart, so the score is honest for new areas.", { b: susc.params.block_m })}
              </p>
              <div className="mt-3 text-[10.5px] font-semibold tracking-[1px] text-muted uppercase">{t("What explains the motion")}</div>
              <ImportanceBars imp={susc.models[susc.chosen].importance} layers={susc.layers} />
              <p className="mt-1.5 text-[11px] leading-snug text-faint">
                {t("Loss of AUC when a layer is shuffled (permutation importance, {m}). An association, not a cause.", { m: t(MODEL_LABEL[susc.chosen]) })}
              </p>
              <div className="mt-2 text-[11px] text-faint">{susc.sources.map(ts).join(" · ")}</div>
            </Fold>
          )}

          {tab === "forecast" && fc && (
            <Fold id="ai.backtest" title={t("BACKTEST")}>
              <div className="text-[12px] text-ink-2">
                {t("{n} cells, last date {d}; error on the past, by horizon (mm):", { n: fmt.int(fc.n_cells), d: fc.last_date })}
              </div>
              <table className="mt-2 w-full text-[12px]">
                <thead>
                  <tr className="text-left text-[10.5px] tracking-[0.8px] text-muted uppercase">
                    <th className="py-1 font-semibold">{t("Model")}</th>
                    {fc.horizons_days.map((d) => (
                      <th key={d} className="py-1 text-right font-semibold">
                        {d} {t("d")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(fc.backtest.mae_mm).map(([m, v]) => (
                    <tr key={m} className={m === fc.chosen ? "text-ink" : "text-muted"}>
                      <td className="py-0.5">
                        {m === fc.chosen ? "▸ " : ""}
                        {t(MODEL_LABEL[m] ?? m)}
                      </td>
                      {fc.horizons_days.map((d) => (
                        <td key={d} className="py-0.5 text-right font-mono">
                          {fmt.num(v[String(d)], 1)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1.5 text-[11.5px] leading-snug text-ink-2">
                {fc.chosen === "gbm"
                  ? t("The machine-learning model beats the simple baselines on the past: it makes the forecast.")
                  : t("The machine-learning model does not beat the simple baselines on these series: the forecast uses “{m}”, as published studies of short InSAR series also find.", { m: t(MODEL_LABEL[fc.chosen]) })}
              </p>
              <div className="mt-2 text-[11px] leading-snug text-faint">
                {t("80 % interval coverage on the latest check:")}{" "}
                {fc.horizons_days.map((d) => `${d} ${t("d")} ${fc.backtest.coverage[String(d)]?.["0.8"] == null ? "–" : `${Math.round(100 * fc.backtest.coverage[String(d)]["0.8"]!)}%`}`).join(" · ")}
              </div>
            </Fold>
          )}

          <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[11px] text-faint shadow-xl shadow-black/30 backdrop-blur">
            {t("Method and sources:")} docs/{lang()}/research/{tab === "susceptibility" ? "ai-susceptibility" : "ai-forecasting"}.md
          </div>
        </div>
      )}

      <BasemapPicker map={map} base={base} onChange={setBase} />

      {g && !rightOpen && (
        <div className="absolute top-3 right-3 z-10">
          <ColumnToggle open={false} side="right" label={t("Layers")} onClick={() => setRightOpen(true)} />
        </div>
      )}
      {g && rightOpen && (
        <div className="pointer-events-none absolute top-3 right-3 bottom-3 z-10 flex w-[min(360px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto">
          <Fold id="ai.layers" title={t("LAYERS")} extra={<ColumnToggle open side="right" label={t("Layers")} onClick={() => setRightOpen(false)} />}>
            {tab === "susceptibility" && susc ? (
              <select value={view} onChange={(e) => setView(e.target.value)} aria-label={t("Map layer")} className="h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink">
                <optgroup label={t("Model results")}>
                  {(["probability", "label", "outside"] as const).map((k) => (
                    <option key={k} value={k}>
                      {k === "probability" ? t("Susceptibility") : k === "label" ? t("Observed (InSAR)") : t("Extrapolation")}
                    </option>
                  ))}
                </optgroup>
                {Object.entries(groups).map(([grp, keys]) => (
                  <optgroup key={grp} label={`${t("Thematic layers")}: ${t(grp)}`}>
                    {keys.map((k) => (
                      <option key={k} value={k}>
                        {t(susc.layers[k].label)}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            ) : (
              fc && (
                <div className="space-y-2">
                  <select value={view} onChange={(e) => setView(e.target.value)} aria-label={t("Map layer")} className="h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink">
                    {(["change", "width"] as const).map((k) => (
                      <option key={k} value={k}>
                        {k === "change" ? t("Forecast change") : t("Uncertainty (80 % width)")}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-center gap-2 text-[12px] text-muted">
                    {t("Forecast horizon")}
                    <select value={h ?? ""} onChange={(e) => setHorizon(Number(e.target.value))} className="h-7 rounded-md border border-line-2 bg-[#0a1322] px-1.5 text-[12px] text-ink">
                      {fc.horizons_days.map((d) => (
                        <option key={d} value={d}>
                          {d} {t("days")}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )
            )}
          </Fold>

          <Fold id="ai.legend" title={t("LEGEND")}>
            {tab === "susceptibility" && susc && g ? (
              view === "probability" ? (
                <>
                  <Swatches
                    items={[...LEVELS.map((l, i) => ({ color: LEVEL_RGB[i], label: `${t(l)} · ${i === 0 ? "<" : "≥"} ${i === 0 ? susc.classes[0] : susc.classes[i - 1]}` })).reverse(), { color: NA_RGB, label: t("no data") }]}
                  />
                  <About what={SUSC_VIEWS.probability.what} read={SUSC_VIEWS.probability.read} />
                </>
              ) : view === "label" ? (
                <>
                  <Swatches items={[{ color: LEVEL_RGB[4], label: t("moving (≥ {r} mm/yr)", { r: susc.params.label_rate }) }, { color: LEVEL_RGB[0], label: t("below the threshold") }, { color: NA_RGB, label: t("no InSAR points") }]} />
                  <About what={SUSC_VIEWS.label.what} read={SUSC_VIEWS.label.read} />
                </>
              ) : view === "outside" ? (
                <>
                  <Swatches items={[{ color: [245, 150, 60], label: t("extrapolation") }, { color: NA_RGB, label: t("within the training range") }]} />
                  <About what={SUSC_VIEWS.outside.what} read={SUSC_VIEWS.outside.read} />
                </>
              ) : (
                <>
                  <div className="text-[13px] font-semibold">{t(susc.layers[view]?.label ?? view)}</div>
                  <GradientLegend colors={VIRIDIS} lo={g.meta.stats?.[view]?.p02 ?? 0} hi={g.meta.stats?.[view]?.p98 ?? 1} unit={t(susc.layers[view]?.unit ?? "")} />
                  <div className="mt-1 text-[11px] text-faint">{t("Colour stretched over 2–98 % of the cells; full range {lo} … {hi}", { lo: fmt.num(g.meta.stats?.[view]?.min, 1), hi: fmt.num(g.meta.stats?.[view]?.max, 1) })}</div>
                  <About
                    what={GROUP_TEXT[susc.layers[view]?.group ?? ""] ?? ""}
                    read={[
                      susc.predictors.includes(view)
                        ? t("Used by the model: importance {v}.", { v: (susc.models[susc.chosen].importance[view] ?? 0).toFixed(3) })
                        : t("Not used by the model."),
                    ]}
                  />
                </>
              )
            ) : (
              fc &&
              g && (
                <>
                  {view === "change" ? (
                    <GradientLegend colors={DIVERGING} lo={-fcLim} hi={fcLim} unit="mm" left={t("away from the satellite (e.g. sinking)")} right={t("toward the satellite")} />
                  ) : (
                    <GradientLegend colors={VIRIDIS} lo={0} hi={fcLim} unit="mm" left={t("narrow")} right={t("wide")} />
                  )}
                  {fc.chosen === "last" && (
                    <div className="mt-2 rounded-md bg-[#2a2110] px-2 py-1 text-[11.5px] leading-snug text-[#f5d08b]">
                      {t("The best model on the past is “no change”: the forecast change is 0 everywhere, only its uncertainty varies.")}
                    </div>
                  )}
                  <About
                    what={view === "change" ? "Forecast change of displacement along the line of sight from the last date to the chosen horizon." : "Width of the 80 % interval: how uncertain the forecast is."}
                    read={["The colour scale is symmetric around zero and stretched over 98 % of the cells; click a cell for its values and chart."]}
                  />
                </>
              )
            )}
          </Fold>

          {sel != null && g && tab === "susceptibility" && susc && (
            <Fold id="ai.cell" title={t("CELL")} extra={<button type="button" className="text-faint hover:text-ink" onClick={() => setSel(null)} aria-label={t("Close")}>×</button>}>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
                <span className="text-muted">{t("Susceptibility")}</span>
                <span className="text-right font-mono text-ink-2">{fmt.num(value(g, sel, "probability"), 2)}</span>
                <span className="text-muted">{t("InSAR rate")}</span>
                <span className="text-right font-mono text-ink-2">{Number.isFinite(value(g, sel, "rate_mm_yr")) ? `${fmt.vel(value(g, sel, "rate_mm_yr"))} mm/yr` : "–"}</span>
                {["p_logistic", "p_random_forest", "p_gradient_boosting"].map((k) => (
                  <div key={k} className="contents">
                    <span className="text-muted">{t(MODEL_LABEL[k.slice(2)])}</span>
                    <span className="text-right font-mono text-[11.5px] text-ink-2">{fmt.num(value(g, sel, k), 2)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-line pt-2 text-[12px]">
                {Object.keys(susc.layers)
                  .filter((k) => g.f[k] != null && Number.isFinite(value(g, sel, k)))
                  .map((k) => (
                    <div key={k} className="contents">
                      <span className="truncate text-muted">{t(susc.layers[k].label)}</span>
                      <span className="text-right font-mono text-[11.5px] text-ink-2">
                        {fmt.num(value(g, sel, k), susc.layers[k].unit === "fraction" ? 2 : 1)} {susc.layers[k].unit === "fraction" ? "" : t(susc.layers[k].unit)}
                      </span>
                    </div>
                  ))}
              </div>
            </Fold>
          )}
          {sel != null && tab === "forecast" && (
            <Fold id="ai.cell" title={t("CELL")} extra={<button type="button" className="text-faint hover:text-ink" onClick={() => setSel(null)} aria-label={t("Close")}>×</button>}>
              {fcell.data ? (
                <>
                  <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-0.5 text-[12px]">
                    <span className="text-[10.5px] text-faint uppercase">{t("date")}</span>
                    <span className="text-right text-[10.5px] text-faint uppercase">{t("forecast")}</span>
                    <span className="text-right text-[10.5px] text-faint uppercase">80 %</span>
                    {fcell.data.forecast.map((f) => (
                      <div key={f.date} className="contents">
                        <span className="text-muted">
                          {f.date} <span className="text-faint">(+{f.horizon_days} {t("d")})</span>
                        </span>
                        <span className="text-right font-mono text-ink-2">{fmt.vel(f.change_mm)} mm</span>
                        <span className="text-right font-mono text-[11px] text-muted">
                          {fmt.vel(f.lo80)} … {fmt.vel(f.hi80)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2">
                    <ForecastChart c={fcell.data} />
                  </div>
                </>
              ) : (
                <div className="py-4 text-center text-[12px] text-muted">{t("Loading…")}</div>
              )}
            </Fold>
          )}
          {sel == null && <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Click a cell for its values.")}</div>}
        </div>
      )}
    </div>
  );
}
