// Weather models of a project (Atmosphere tab): which models cover a product (area, dates, resolution, automatic
// or ordered by hand), their APS tried on the product without running it again (geoeyes atmosphere), per
// interferogram and as maps, and the chosen model applied to the project ([atmosphere] method, then a run).
// Method: geoeyes.validation.atmosphere; models: geoeyes.processing.atmosphere.models.
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AtmosphereSummary, type WeatherModel } from "../api";
import { t } from "../i18n";
import { baseSource, DEFAULT_BASE } from "../map";
import { ask, Button, fmt, Panel } from "../ui";

const MODEL_COLOR: Record<string, string> = { none: "#9aa3ad", linear: "#f5b84b", era5: "#3b82c4", cerra: "#2a9d8f", gacos: "#9b5de5" };
const label = (k: string) => ({ none: t("no APS"), linear: t("linear (height)"), era5: "ERA5", cerra: "CERRA", gacos: "GACOS" })[k] ?? k;

/** Blue (negative) … grey … red (positive) for v in [-1, 1]. */
function diverging(v: number): [number, number, number] {
  const x = Math.max(-1, Math.min(1, v));
  const mix = (a: number[], b: number[], f: number) => a.map((c, i) => Math.round(c + (b[i] - c) * f));
  return (x < 0 ? mix([235, 237, 240], [33, 102, 172], -x) : mix([235, 237, 240], [178, 24, 43], x)) as [number, number, number];
}

function Yes({ v }: { v: boolean | null }) {
  if (v === null) return <span className="text-faint">?</span>;
  return v ? <span className="text-good">✓</span> : <span className="text-bad">✗</span>;
}

/** Where the regional models stop: the CERRA domain and the product. */
function CoverageMap({ bbox, outlines }: { bbox: number[]; outlines: Record<string, [number, number][]> }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const [w, s, e, n] = bbox;
    const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });
    const poly = (ring: number[][], props: Record<string, string>): GeoJSON.Feature => ({ type: "Feature", properties: props, geometry: { type: "Polygon", coordinates: [ring] } });
    const m = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        sources: {
          base: baseSource(DEFAULT_BASE),
          dom: { type: "geojson", data: fc(Object.entries(outlines).map(([k, r]) => poly(r, { k }))) },
          aoi: { type: "geojson", data: fc([poly([[w, s], [e, s], [e, n], [w, n], [w, s]], {})]) },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#d9dde3" } },
          { id: "base", type: "raster", source: "base" },
          { id: "dom-fill", type: "fill", source: "dom", paint: { "fill-color": MODEL_COLOR.cerra, "fill-opacity": 0.1 } },
          { id: "dom-line", type: "line", source: "dom", paint: { "line-color": MODEL_COLOR.cerra, "line-width": 1.5 } },
          { id: "aoi", type: "circle", source: "aoi", paint: { "circle-radius": 0 } },
          { id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#d62828", "line-width": 2 } },
        ],
      },
      center: [(w + e) / 2, (s + n) / 2],
      zoom: 1.6,
      dragRotate: false,
      attributionControl: { compact: true },
    });
    const mk = new maplibregl.Marker({ color: "#d62828", scale: 0.6 }).setLngLat([(w + e) / 2, (s + n) / 2]).addTo(m);
    return () => {
      mk.remove();
      m.remove();
    };
  }, [bbox, outlines]);
  return <div ref={el} className="h-56 w-full overflow-hidden rounded-lg border border-line" />;
}

/** Scatter of the residual phase per interferogram, one bar per model. */
function Bars({ s }: { s: AtmosphereSummary }) {
  const models = Object.keys(s.models);
  const n = s.ifg_dates.length;
  const W = 900;
  const H = 200;
  const top = Math.max(...models.flatMap((k) => s.models[k].std_mm)) * 1.08 || 1;
  const gx = (W - 50) / n;
  const bw = Math.max(2, (gx * 0.8) / models.length);
  const Y = (v: number) => H - 24 - ((H - 34) * v) / top;
  const ticks = [0, top / 2, top].map((v) => Math.round(v * 10) / 10);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={t("Residual phase scatter per interferogram")}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={40} x2={W} y1={Y(v)} y2={Y(v)} stroke="var(--c-chip)" />
          <text x={34} y={Y(v) + 4} textAnchor="end" fontSize={11} fill="var(--c-muted)">
            {v}
          </text>
        </g>
      ))}
      {s.ifg_dates.map((d, i) => (
        <g key={d}>
          {models.map((k, j) => (
            <rect key={k} x={46 + i * gx + j * bw} y={Y(s.models[k].std_mm[i])} width={bw - 0.5} height={H - 24 - Y(s.models[k].std_mm[i])} fill={MODEL_COLOR[k] ?? "#888"}>
              <title>{`${d} · ${label(k)}: ${fmt.num(s.models[k].std_mm[i])} mm`}</title>
            </rect>
          ))}
          <text x={46 + i * gx + (bw * models.length) / 2} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--c-muted)">
            {d.slice(5)}
          </text>
        </g>
      ))}
      <text x={4} y={12} fontSize={11} fill="var(--c-muted)">
        mm
      </text>
    </svg>
  );
}

function GridCanvas({ data, size, lim }: { data: Float32Array | undefined; size: number; lim: number }) {
  const cv = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = cv.current;
    if (!el || !data) return;
    el.width = size;
    el.height = size;
    const ctx = el.getContext("2d")!;
    const img = ctx.createImageData(size, size);
    data.forEach((v, i) => {
      if (!Number.isFinite(v)) return;                       // transparent: no point in that cell
      const [r, g, b] = diverging(v / lim);
      img.data.set([r, g, b, 255], i * 4);
    });
    ctx.putImageData(img, 0, 0);
  }, [data, size, lim]);
  return <canvas ref={cv} className="block aspect-square h-auto w-full rounded-lg border border-line bg-sunken [image-rendering:pixelated]" />;
}

function Maps({ name, product, s }: { name: string; product: string; s: AtmosphereSummary }) {
  const models = s.tried;
  const [k, setK] = useState(0);
  const [model, setModel] = useState(models.find((m) => m !== "linear") ?? models[0]);
  const layers = ["obs", `aps:${model}`, `res:${model}`];
  const grids = useQueries({
    queries: layers.map((layer) => ({
      queryKey: ["atm-grid", name, product, s.created, layer, k],
      queryFn: () => api.atmosphereGrid(name, product, layer, k),
      staleTime: Infinity,
    })),
  });
  // one scale for the three maps, the full range of the values (never clipped)
  const lim = useMemo(() => Math.max(0.1, ...grids.flatMap((g) => (g.data ? [Math.abs(g.data.meta.min), Math.abs(g.data.meta.max)] : []))), [grids]);
  const titles = [t("Observed: unwrapped phase − motion − DEM error"), t("{model} APS", { model: label(model) }), t("After {model}", { model: label(model) })];
  const std = (key: string) => s.models[key]?.std_mm[k];
  return (
    <Panel className="px-4 py-3 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{t("Maps")}</span>
        <select value={k} onChange={(e) => setK(Number(e.target.value))} className="h-8 rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink">
          {s.ifg_dates.map((d, i) => (
            <option key={d} value={i}>
              {s.reference_date} → {d}
            </option>
          ))}
        </select>
        <div className="flex rounded-md border border-line-2 p-0.5">
          {models.map((m) => (
            <button key={m} type="button" aria-pressed={model === m} onClick={() => setModel(m)} className={`h-7 rounded px-2.5 text-[12px] ${model === m ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}>
              {label(m)}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {layers.map((layer, i) => (
          <div key={layer}>
            <div className="mb-1 text-[12px] text-muted">
              {titles[i]}
              {i !== 1 && std(i === 0 ? "none" : model) !== undefined ? ` · σ ${fmt.num(std(i === 0 ? "none" : model)!)} mm` : ""}
            </div>
            <GridCanvas data={grids[i].data?.data} size={s.grid.size} lim={lim} />
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2 text-[11.5px] text-muted">
        <span className="font-mono">−{fmt.num(lim)}</span>
        <span className="h-2.5 w-48 rounded" style={{ background: "linear-gradient(90deg, rgb(33,102,172), rgb(235,237,240), rgb(178,24,43))" }} />
        <span className="font-mono">+{fmt.num(lim)} mm</span>
        <span>{t("line of sight, one scale for the three maps (full range); north up")}</span>
      </div>
    </Panel>
  );
}

export function Atmosphere({ name }: { name: string }) {
  const qc = useQueryClient();
  const proj = useQuery({ queryKey: ["project", name], queryFn: () => api.project(name) });
  const products = (proj.data?.tracks ?? []).flatMap((x) => (x.product ? [{ id: x.product.id, label: `${x.track_id} v${x.product.version}` }] : []));
  const [pid, setPid] = useState("");
  const product = pid || products[0]?.id || "";
  const q = useQuery({
    queryKey: ["atmosphere", name, product],
    queryFn: () => api.atmosphere(name, product),
    enabled: !!product,
    refetchInterval: (x) => (x.state.data?.running ? 2000 : false),
  });
  const s = q.data?.summary ?? null;
  const [err, setErr] = useState("");
  const [applied, setApplied] = useState("");
  const current = String(q.data?.current_method ?? "none").toLowerCase();

  const run = async () => {
    setErr("");
    try {
      await api.atmosphereRun(name, product, {});
      await qc.invalidateQueries({ queryKey: ["atmosphere", name, product] });
    } catch (e) {
      const m = (e as Error).message;
      setErr(/method not allowed|not found/i.test(m) ? t("{msg}: the running server predates this page, restart geoeyes serve", { msg: m }) : m);
    }
  };
  const apply = async (method: string) => {
    if (!(await ask(t("Use {model} for this project and run it again from the point engine?", { model: label(method === "none" ? "linear" : method) }), { ok: t("Use") }))) return;
    setErr("");
    try {
      await api.patchSettings(name, { "atmosphere.method": method });
      await api.run(name, {});
      setApplied(method);
      await qc.invalidateQueries({ queryKey: ["project", name] });
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const best = s ? Object.entries(s.models).filter(([k]) => k !== "none").sort((a, b) => a[1].median_std_mm - b[1].median_std_mm)[0]?.[0] : undefined;
  const cat = q.data?.catalogue ?? [];
  const reason = (m: WeatherModel) =>
    m.access === "planned"
      ? t("not supported yet")
      : m.access === "manual"
        ? t("ordered on the website, then read from a folder")
        : !m.covers_area
          ? t("outside its area")
          : !m.covers_dates
            ? t("dates not published yet")
            : t("downloaded by GeoEyes");

  return (
    <div className="mb-6 space-y-4">
      <Panel className="px-4 py-3 text-[13px]">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{t("Tropospheric correction: weather models")}</div>
            <div className="mt-0.5 text-muted">
              {t(
                "Each model's delay at the points is compared with the unwrapped phase of the product, without running it again: the smaller the scatter left, the better the model explains the atmosphere of these dates.",
              )}
            </div>
          </div>
          <select value={product} onChange={(e) => setPid(e.target.value)} aria-label={t("Product")} className="h-8 rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink">
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <Button variant="primary" disabled={!product || q.data?.running} onClick={run}>
            {q.data?.running ? t("Trying the models…") : s ? t("Try again") : t("Try the models")}
          </Button>
        </div>
        {err && <div className="mt-2 text-[12.5px] text-bad">{err}</div>}
        {applied && <div className="mt-2 text-[12.5px] text-good">{t("[atmosphere] method = {m}: the project is running again (Pipeline tab).", { m: applied })}</div>}
        {(q.data?.running || q.data?.failed) && (q.data?.log.length ?? 0) > 0 && (
          <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-line bg-deep p-2 font-mono text-[11.5px] text-ink-3">{q.data!.log.join("\n")}</pre>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <Panel className="overflow-x-auto p-0">
          <table className="w-full min-w-[640px] text-[12.5px]">
            <thead>
              <tr className="border-b border-line text-left text-[11px] tracking-[0.8px] text-muted uppercase">
                {["Model", "Grid", "Every", "Area", "Dates", "Access", ""].map((h) => (
                  <th key={h} className="px-3 py-2 font-semibold">
                    {t(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cat.map((m) => (
                <tr key={m.key} className="border-b border-line/60" title={m.note}>
                  <td className="px-3 py-2">
                    <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: MODEL_COLOR[m.key] ?? "#ccc" }} />
                    <span className="font-semibold">{m.name}</span> <span className="text-muted">{m.provider}</span>
                    {current === m.key && <span className="ml-1.5 rounded bg-accent-bg px-1.5 text-[11px] text-accent-ink">{t("in use")}</span>}
                  </td>
                  <td className="px-3 py-2 font-mono">{m.resolution_km} km</td>
                  <td className="px-3 py-2 font-mono">{m.step_h} h</td>
                  <td className="px-3 py-2">
                    <Yes v={m.covers_area} />
                  </td>
                  <td className="px-3 py-2">
                    <Yes v={m.covers_dates} />
                  </td>
                  <td className={`px-3 py-2 ${m.usable ? "text-ink-2" : "text-muted"}`}>{reason(m)}</td>
                  <td className="px-3 py-2 text-right">
                    {m.usable && current !== m.key && (
                      <Button onClick={() => apply(m.key)} disabled={q.data?.running}>
                        {t("Use")}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3 py-2 text-[11px] text-faint">
            {t("Outside Europe, no free model finer than ERA5 can be downloaded automatically for past dates; GACOS (9 km) is ordered by e-mail.")}
          </div>
        </Panel>
        {q.data && <CoverageMap bbox={q.data.bbox} outlines={q.data.outlines} />}
      </div>

      {s && (
        <>
          {s.span_days < 90 && (
            <div className="rounded-lg bg-warn-bg px-3 py-2 text-[12.5px] text-warn-ink">
              {t("The stack spans {d} days: a few mm of atmosphere become tens of mm/yr once divided by so short a time, and slow slope motion stays below the noise.", { d: s.span_days })}
            </div>
          )}
          <Panel className="overflow-x-auto p-0">
            <table className="w-full min-w-[640px] text-[12.5px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] tracking-[0.8px] text-muted uppercase">
                  {["APS removed", "Scatter left (median)", "Variance removed", "Best on", "Model data", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-semibold">
                      {t(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(s.models).map(([k, m]) => (
                  <tr key={k} className={`border-b border-line/60 ${k === best ? "bg-raised" : ""}`}>
                    <td className="px-3 py-2">
                      <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: MODEL_COLOR[k] ?? "#888" }} />
                      {label(k)}
                      {k === best && <span className="ml-1.5 text-[11px] text-good">{t("best")}</span>}
                    </td>
                    <td className="px-3 py-2 font-mono">{fmt.num(m.median_std_mm)} mm</td>
                    <td className="px-3 py-2 font-mono">{k === "none" ? "–" : `${m.reduction_pct > 0 ? "+" : ""}${fmt.num(m.reduction_pct, 0)} %`}</td>
                    <td className="px-3 py-2 font-mono">{t("{n} of {m} interferograms", { n: m.best_ifgs, m: s.ifg_dates.length })}</td>
                    <td className="px-3 py-2 font-mono">{m.coverage == null ? "–" : `${fmt.num(100 * m.coverage, 0)} %`}</td>
                    <td className="px-3 py-2 text-right">
                      {k !== "none" && k !== current && !(k === "linear" && current === "none") && (k === "linear" || cat.find((c) => c.key === k)?.usable) && (
                        <Button onClick={() => apply(k === "linear" ? "none" : k)} disabled={q.data?.running}>
                          {t("Use")}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-3 py-2 text-[11px] text-faint">
              {t("{n} of {total} points, phase left after a linear motion and a DEM error per point; each APS centred per interferogram as in the engine. Errors: {e}", {
                n: s.points.toLocaleString(),
                total: s.points_total.toLocaleString(),
                e: Object.keys(s.errors).length ? Object.entries(s.errors).map(([k, v]) => `${k}: ${v}`).join("; ") : t("none"),
              })}
            </div>
          </Panel>
          <Panel className="px-4 py-3 text-[13px]">
            <div className="mb-1 flex flex-wrap items-center gap-3">
              <span className="font-semibold">{t("Residual phase scatter per interferogram")}</span>
              {Object.keys(s.models).map((k) => (
                <span key={k} className="flex items-center gap-1 text-[11.5px] text-muted">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: MODEL_COLOR[k] ?? "#888" }} />
                  {label(k)}
                </span>
              ))}
            </div>
            <Bars s={s} />
          </Panel>
          <Maps name={name} product={product} s={s} />
        </>
      )}
    </div>
  );
}
