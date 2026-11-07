// Hazard: ground-motion hazard zoning of a product with rainfall (geoeyes hazard). Cells of the analysis grid
// coloured by hazard level or by one of its ingredients (InSAR intensity, angular distortion / slope, rainfall
// coupling); click a cell for its series in the motion direction, the rainfall of its pixel and the fitted models.
// Method and sources: docs/en/research/rainfall-insar-hazard.md.
import { LineLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type AnalysisKind, type Workspace } from "../api";
import { MapCanvas, useBaseMap, useFitTo } from "../components/MapBase";
import { addTheme, composeTheme, type ThemeKind } from "../components/ThemeLayers";
import { t, ts } from "../i18n";
import { useWarnings } from "../notify";
import { href, useApp } from "../state";
import { Button, ColumnToggle, fmt, Fold, usePersisted } from "../ui";
import { About, Behaviour, BehaviourLegend, CellPanel, Cells, Consolidation, EAST_RGB, EXP_F, ExpMode, Geology, LEVELS, LEVEL_RGB, LINE_RGB, Legend, LinePanel, MOTION_BREAKS, MethodLink, NA_RGB, PARAMS, RATE_RGB, RiskPanel, VIEWS, VIEW_GROUPS, View, bin, cellColor, expColor, rgb } from "../components/hazardKit";

/** The thematic layer (and its view) of the results map that shows a view of this page. */
function themeOfView(v: View): [ThemeKind, View | undefined] {
  if (v === "behaviour" || v === "change") return ["behaviour", v];
  if (v === "up" || v === "east") return ["decompose", v];
  if (v === "soft_soil") return ["geology", undefined];
  if (v === "consolidation" || v === "risk" || v === "lines") return [v, undefined];
  return ["hazard", v];
}

export function Hazard({ ws, project, product, cell: linked, layer }: { ws: Workspace | undefined; project?: string; product?: string; cell?: number; layer?: string }) {
  const { go, layers, showProduct } = useApp();
  const qc = useQueryClient();
  const shell = useBaseMap();
  const { overlay } = shell;
  const asView = (v?: string): View => (VIEWS.some((x) => x.id === v) ? (v as View) : "hazard");
  const [view, setViewState] = useState<View>(asView(layer));
  useEffect(() => setViewState(asView(layer)), [layer]); // eslint-disable-line react-hooks/exhaustive-deps
  // the layer is part of the link (#/hazard/<project>/<product>/<layer>): the Principles page opens the one it explains
  const setView = (v: View) => {
    setViewState(v);
    if (project && product) window.history.replaceState(null, "", href({ page: "hazard", name: project, product, view: v === "hazard" ? undefined : v }));
  };
  const [sel, setSel] = useState<number | null>(null);
  const [params, setParams] = useState<Record<string, number | string>>({});
  const [busy, setBusy] = useState("");
  const [refBox, setRefBox] = useState("");
  const [leftOpen, setLeftOpen] = usePersisted("hazard.left", true);
  const [rightOpen, setRightOpen] = usePersisted("hazard.right", true);
  const [tie, setTie] = useState(false);
  const [expMode, setExpMode] = useState<ExpMode>("subsidence");

  // products that can be zoned: the latest product of each track
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
    if (pick) go({ page: "hazard", name: pick.project, product: pick.product });
  }, [project, product, layers, choices, go]);

  const status = useQuery({
    queryKey: ["hazard", project, product],
    queryFn: () => api.hazard(project!, product!),
    enabled: !!project && !!product,
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
  });
  const s = status.data?.summary ?? null;
  useWarnings(`hazard:${project}/${product}:${s?.created}`, `${t("Hazard zoning")} · ${project}`, s?.warnings, project && product ? `#/hazard/${encodeURIComponent(project)}/${encodeURIComponent(product)}` : undefined);
  const cells = useQuery({
    queryKey: ["hazard-cells", project, product, s?.created],
    queryFn: async (): Promise<Cells> => {
      const { meta, buf } = await api.hazardCells(project!, product!);
      return { meta, buf, f: Object.fromEntries(meta.fields.map((n, i) => [n, i])) };
    },
    enabled: !!s,
    staleTime: Infinity,
  });
  // GNSS comparison of the product (geoeyes gnss): its stations on the map, and the "GNSS tie" of the run
  const gnss = useQuery({
    queryKey: ["gnss", project, product],
    queryFn: () => api.gnss(project!, product!),
    enabled: !!project && !!product,
  });
  const calib = gnss.data?.summary?.calibration ?? null;
  const stations = gnss.data?.summary?.stations ?? [];
  const cell = useQuery({
    queryKey: ["hazard-cell", project, product, s?.created, sel],
    queryFn: () => api.hazardCell(project!, product!, sel!),
    enabled: !!s && sel != null,
  });
  // kinds of motion and risk to buildings (geoeyes behaviour / risk)
  const [selB, setSelB] = useState<number | null>(null);
  const behStatus = useQuery({
    queryKey: ["behaviour", project, product],
    queryFn: () => api.behaviour(project!, product!),
    enabled: !!project && !!product,
    refetchInterval: (q) => {
      const d = q.state.data;
      return d && Object.values(d).some((x) => typeof x === "object" && x?.running) ? 2000 : false;
    },
  });
  const behSummary = behStatus.data?.behaviour.summary ?? null;
  const riskSummary = behStatus.data?.risk.summary ?? null;
  const behCells = useQuery({
    queryKey: ["behaviour-cells", project, product, behSummary?.created],
    queryFn: async (): Promise<Behaviour & { first: string; last: string }> => {
      const { meta, buf } = await api.behaviourCells(project!, product!);
      return { buf, span: (Date.parse(meta.last_date) - Date.parse(meta.first_date)) / 86400000, first: meta.first_date, last: meta.last_date };
    },
    enabled: !!behSummary && !!s,
    staleTime: Infinity,
  });
  const behCell = useQuery({
    queryKey: ["behaviour-cell", project, product, behSummary?.created, sel],
    queryFn: () => api.behaviourCell(project!, product!, sel!),
    enabled: !!behSummary && sel != null,
  });
  const riskData = useQuery({
    queryKey: ["risk-buildings", project, product, riskSummary?.created],
    queryFn: async () => {
      const { meta, view: dv } = await api.riskBuildings(project!, product!);
      const n = meta.n;
      const pos = new Float32Array(n * 2);
      const col = new Uint8Array(n * 4);
      const rad = new Float32Array(n);
      const risk = new Int8Array(n);
      for (let i = 0; i < n; i++) {
        const o = i * meta.record;
        pos[i * 2] = meta.origin[0] + dv.getFloat32(o, true);
        pos[i * 2 + 1] = meta.origin[1] + dv.getFloat32(o + 4, true);
        const r = dv.getUint8(o + 8) - 1;
        risk[i] = r;
        const c = r >= 0 ? LEVEL_RGB[r] : NA_RGB;
        col.set([c[0], c[1], c[2], r >= 0 ? 235 : 120], i * 4);
        rad[i] = dv.getUint8(o + 11) / 2;
      }
      return { n, pos, col, rad, risk };
    },
    enabled: !!riskSummary && view === "risk",
    staleTime: Infinity,
  });
  const building = useQuery({
    queryKey: ["risk-building", project, product, riskSummary?.created, selB],
    queryFn: () => api.riskBuilding(project!, product!, selB!),
    enabled: !!riskSummary && selB != null,
  });
  const linesSummary = behStatus.data?.lines.summary ?? null;
  const consSummary = behStatus.data?.consolidation.summary ?? null;
  const [selLine, setSelLine] = useState<number | null>(null);
  const linesData = useQuery({
    queryKey: ["line-segments", project, product, linesSummary?.created],
    queryFn: async () => {
      const { meta, buf } = await api.lineSegments(project!, product!);
      const n = meta.n;
      const src = new Float32Array(n * 2);
      const dst = new Float32Array(n * 2);
      const col = new Uint8Array(n * 4);
      const wid = new Float32Array(n);
      const line = new Int32Array(n);
      for (let i = 0; i < n; i++) {
        const o = i * 6;
        src.set([buf[o], buf[o + 1]], i * 2);
        dst.set([buf[o + 2], buf[o + 3]], i * 2);
        const k = buf[o + 4];
        const c = k >= 0 ? LINE_RGB[k] : NA_RGB;
        col.set([c[0], c[1], c[2], k >= 0 ? 255 : 150], i * 4);
        wid[i] = k >= 1 ? 5 : k === 0 ? 3 : 2;
        line[i] = buf[o + 5];
      }
      return { n, src, dst, col, wid, line };
    },
    enabled: !!linesSummary && view === "lines",
    staleTime: Infinity,
  });
  const lineProfile = useQuery({
    queryKey: ["line-profile", project, product, linesSummary?.created, selLine],
    queryFn: () => api.lineProfile(project!, product!, selLine!),
    enabled: !!linesSummary && selLine != null,
  });
  const consCells = useQuery({
    queryKey: ["consolidation-cells", project, product, consSummary?.created],
    queryFn: async (): Promise<Consolidation> => {
      const { meta, buf } = await api.consolidationCells(project!, product!);
      return { buf, max: meta.summary.remaining_mm?.p90 ?? 1 };
    },
    enabled: !!consSummary && !!s,
    staleTime: Infinity,
  });
  const consCell = useQuery({
    queryKey: ["consolidation-cell", project, product, consSummary?.created, sel],
    queryFn: () => api.consolidationCell(project!, product!, sel!),
    enabled: !!consSummary && sel != null,
  });
  const decSummary = behStatus.data?.decompose.summary ?? null;
  const geoSummary = behStatus.data?.geology.summary ?? null;
  const decData = useQuery({
    queryKey: ["decompose-cells", project, product, decSummary?.created],
    queryFn: async () => {
      const { meta, buf } = await api.decomposeCells(project!, product!);
      const F = meta.fields.length;
      const f = Object.fromEntries(meta.fields.map((n, i) => [n, i]));
      const hx = meta.dlon / 2;
      const hy = meta.dlat / 2;
      const polys = Array.from({ length: meta.n }, (_, i) => {
        const x = buf[i * F];
        const y = buf[i * F + 1];
        return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
      });
      return { meta, buf, F, f, polys };
    },
    enabled: !!decSummary && (view === "up" || view === "east"),
    staleTime: Infinity,
  });
  const geoCells = useQuery({
    queryKey: ["geology-cells", project, product, geoSummary?.created],
    queryFn: async (): Promise<Geology> => {
      const { meta, buf } = await api.geologyCells(project!, product!);
      const th = meta.summary.thickness_m;
      return { buf, min: th?.min ?? 0, max: th?.max ?? 1 };
    },
    enabled: !!geoSummary && view === "soft_soil",
    staleTime: Infinity,
  });
  const expSummary = behStatus.data?.exposure?.summary ?? null;
  const expData = useQuery({
    queryKey: ["exposure-cells", project, product, expSummary?.created],
    queryFn: async () => {
      const { meta, buf } = await api.exposureCells(project!, product!);
      const h = meta.cell_deg / 2;
      const polys = Array.from({ length: meta.n }, (_, i) => {
        const x = buf[i * 8];
        const y = buf[i * 8 + 1];
        return { i, ring: [[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h]] };
      });
      return { buf, polys };
    },
    enabled: !!expSummary && view === "exposure",
    staleTime: Infinity,
  });
  const runAnalysis = async (kind: AnalysisKind, params: Record<string, unknown> = {}) => {
    if (!project || !product) return;
    try {
      await api.analysisRun(project, product, kind, params);
      await qc.invalidateQueries({ queryKey: ["behaviour", project, product] });
    } catch (e) {
      setBusy(ts((e as Error).message));
    }
  };

  useEffect(() => {
    if (s) setParams(Object.fromEntries(PARAMS.map((p) => [p.key, s.params[p.key] as number | string])));
    setRefBox(s && Array.isArray(s.params.reference_bbox) ? (s.params.reference_bbox as number[]).join(", ") : "");
    setTie(!!s?.params.gnss_tie);
    setSel(linked ?? null);
  }, [s]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------ map
  useFitTo(shell, s?.bounds, s ? `${s.product_id}|${s.created}` : null);

  const polys = useMemo(() => {
    const c = cells.data;
    if (!c) return null;
    const F = c.meta.fields.length;
    const hx = (0.5 * c.meta.cell_m) / (111320 * Math.cos((c.meta.lat0 * Math.PI) / 180));
    const hy = (0.5 * c.meta.cell_m) / 110540;
    const [lon0, lat0] = c.meta.origin;
    return Array.from({ length: c.meta.n }, (_, i) => {
      const x = lon0 + c.buf[i * F];
      const y = lat0 + c.buf[i * F + 1];
      return { i, ring: [[x - hx, y - hy], [x + hx, y - hy], [x + hx, y + hy], [x - hx, y + hy]] };
    });
  }, [cells.data]);

  useEffect(() => {
    const ov = overlay.current;
    const c = cells.data;
    if (!ov) return;
    if (!c || !polys) {
      ov.setProps({ layers: [] });
      return;
    }
    ov.setProps({
      layers: [
        ...(stations.length
          ? [
              new ScatterplotLayer<(typeof stations)[number]>({
                id: "gnss-stations",
                data: stations,
                getPosition: (d) => [d.lon, d.lat],
                getRadius: 7,
                radiusUnits: "pixels",
                getFillColor: (d) => (d.used ? [255, 255, 255, 255] : [140, 150, 170, 200]),
                getLineColor: [11, 18, 32, 255],
                lineWidthMinPixels: 2,
                stroked: true,
                pickable: true,
              }),
              new TextLayer<(typeof stations)[number]>({
                id: "gnss-labels",
                data: stations,
                getPosition: (d) => [d.lon, d.lat],
                getText: (d) => d.site,
                getSize: 12,
                getColor: [255, 255, 255, 255],
                getPixelOffset: [12, 0],
                getTextAnchor: "start",
                getAlignmentBaseline: "center",
                fontFamily: "'JetBrains Mono Variable', monospace",
                outlineWidth: 3,
                outlineColor: [11, 18, 32, 255],
                fontSettings: { sdf: true },
              }),
            ]
          : []),
        ...(view === "lines" && linesData.data
          ? [
              new LineLayer({
                id: "infrastructure-lines",
                data: {
                  length: linesData.data.n,
                  attributes: {
                    getSourcePosition: { value: linesData.data.src, size: 2 },
                    getTargetPosition: { value: linesData.data.dst, size: 2 },
                    getColor: { value: linesData.data.col, size: 4, normalized: true },
                    getWidth: { value: linesData.data.wid, size: 1 },
                  },
                },
                widthUnits: "pixels",
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 200],
                onClick: (info: { index: number }) => {
                  if (info.index >= 0) {
                    setSelLine(linesData.data!.line[info.index]);
                    setSel(null);
                    setSelB(null);
                  }
                },
              }),
            ]
          : []),
        ...((view === "up" || view === "east") && decData.data
          ? [
              new SolidPolygonLayer<{ i: number; ring: number[][] }>({
                id: "decompose-cells",
                data: decData.data.polys,
                getPolygon: (d) => d.ring as never,
                getFillColor: (d) => {
                  const D = decData.data!;
                  const v = D.buf[d.i * D.F + D.f[view]];
                  // the same classes as the rate: red sinking, blue rising; green east, purple west
                  return [...(view === "up" ? RATE_RGB[bin(-v, MOTION_BREAKS)] : EAST_RGB[bin(v, MOTION_BREAKS)]), 225] as never;
                },
                updateTriggers: { getFillColor: [view] },
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 120],
              }),
            ]
          : []),
        ...(view === "exposure" && expData.data
          ? [
              new SolidPolygonLayer<{ i: number; ring: number[][] }>({
                id: "exposure-cells",
                data: expData.data.polys,
                getPolygon: (d) => d.ring as never,
                getFillColor: (d) => expColor(expData.data!.buf, d.i, expMode),
                updateTriggers: { getFillColor: [expMode] },
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 120],
              }),
            ]
          : []),
        ...(view === "risk" && riskData.data
          ? [
              new ScatterplotLayer({
                id: "risk-buildings",
                data: {
                  length: riskData.data.n,
                  attributes: {
                    getPosition: { value: riskData.data.pos, size: 2 },
                    getFillColor: { value: riskData.data.col, size: 4, normalized: true },
                    getRadius: { value: riskData.data.rad, size: 1 },
                  },
                },
                radiusUnits: "meters",
                radiusMinPixels: 1.2,
                pickable: true,
                onClick: (info: { index: number }) => {
                  if (info.index >= 0) {
                    setSelB(info.index);
                    setSel(null);
                  }
                },
              }),
            ]
          : []),
        new SolidPolygonLayer<{ i: number; ring: number[][] }>({
          id: `hazard-${view}`,
          data: polys,
          getPolygon: (d) => d.ring as never,
          getFillColor: (d) => (d.i === sel ? [255, 255, 255, 255] : cellColor(c, d.i, view, behCells.data, consCells.data, geoCells.data)),
          updateTriggers: { getFillColor: [view, sel, behCells.data, consCells.data, geoCells.data] },
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 120],
          onClick: (info) => {
            if (info.object) {
              setSel(info.object.i);
              setSelB(null);
              setSelLine(null);
            }
          },
        }),
      ].reverse() as never,
      getTooltip: ({ object, layer, index }: { object?: { i: number } & Partial<(typeof stations)[number]>; layer?: { id: string } | null; index: number }) => {
        if (layer?.id === "decompose-cells" && decData.data && object) {
          const D = decData.data;
          const g = (n: string) => D.buf[object.i * D.F + D.f[n]];
          const prods = D.meta.summary.products;
          return {
            text: [
              `${t("vertical")} ${fmt.vel(g("up"))} ± ${g("sigma_up").toFixed(1)} mm/yr`,
              `${t("east-west")} ${fmt.vel(g("east"))} ± ${g("sigma_east").toFixed(1)} mm/yr`,
              ...prods.map((p, k) => `${t("{track} alone", { track: p.track })}: ${fmt.vel(g(`vert_only_${k}`))} mm/yr`),
            ].join("\n"),
            style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" },
          };
        }
        if (layer?.id === "exposure-cells" && expData.data && object) {
          const b = expData.data.buf;
          const g = (k: keyof typeof EXP_F) => b[object.i * 8 + EXP_F[k]];
          const lines = [t("{n} people", { n: fmt.int(g("people")) }), g("points") >= 3 ? `${fmt.vel(g("v"))} mm/yr · ${t("{n} points", { n: g("points") })}` : t("not observed")];
          if (g("flooded") > 0) lines.push(t("{p} flooded", { p: `${Math.round(g("flooded") * 100)} %` }));
          if (g("depth") > 0) lines.push(`GloFAS ${g("depth").toFixed(1)} m`);
          return { text: lines.join("\n"), style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" } };
        }
        if (layer?.id === "infrastructure-lines" && linesData.data && index >= 0) {
          return {
            text: t("Click for the profile along the line"),
            style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" },
          };
        }
        if (layer?.id === "risk-buildings" && riskData.data && index >= 0) {
          const r = riskData.data.risk[index];
          return {
            text: r >= 0 ? t("{level} risk", { level: t(LEVELS[r]) }) : t("not assessed"),
            style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" },
          };
        }
        if (!object) return null;
        if (layer?.id === "gnss-stations") {
          const st = object as (typeof stations)[number];
          const v = st.vertical;
          return {
            text: `GNSS ${st.site}${st.used && v ? `
GNSS − InSAR ${fmt.vel(v.rate_diff_mm_yr)} mm/yr (LOS)` : `
${ts(st.reason ?? "")}`}`,
            style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" },
          };
        }
        const F = c.meta.fields.length;
        const g = (n: string) => c.buf[object.i * F + c.f[n]];
        const lv = g("hazard");
        const h = view === "soft_soil" && geoCells.data ? geoCells.data.buf[object.i * 2] : NaN;
        if (Number.isFinite(h))
          return {
            text: `${t("soft soil")} ${h.toFixed(0)} m\n${fmt.vel(g("rate_mm_yr"))} mm/yr`,
            style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" },
          };
        return {
          text: `${lv >= 0 ? t(LEVELS[lv]) : t("not assessed")} · I${g("intensity")} S${Math.max(0, g("secondary"))}\n${fmt.vel(g("rate_mm_yr"))} mm/yr${g("rain_coupled") > 0 ? ` · ${t("rain r {r}, lag {n} mo", { r: g("rain_r").toFixed(2), n: g("rain_lag_months") })}` : ""}`,
          style: { background: "var(--c-bg)", color: "var(--c-ink)", fontSize: "12px", borderRadius: "6px", padding: "4px 8px", fontFamily: "var(--font-mono)" },
        };
      },
    });
  }, [cells.data, polys, view, sel, stations, behCells.data, riskData.data, linesData.data, consCells.data, decData.data, geoCells.data, expData.data, expMode]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async () => {
    if (!project || !product) return;
    setBusy("");
    const box = refBox.split(/[\s,]+/).filter(Boolean).map(Number);
    if (box.length !== 0 && (box.length !== 4 || box.some((v) => !Number.isFinite(v)))) {
      setBusy(t("Reference area: west, south, east, north (degrees)"));
      return;
    }
    try {
      await api.hazardRun(project, product, { ...params, reference_bbox: box, gnss_tie: tie });
      await qc.invalidateQueries({ queryKey: ["hazard", project, product] });
    } catch (e) {
      const msg = (e as Error).message;
      // the page is newer than the running server (built files are read from disk, the API code is not)
      setBusy(/method not allowed|not found/i.test(msg) ? t("{msg}: the running server predates this page, restart geoeyes serve", { msg: ts(msg) }) : ts(msg));
    }
  };

  const running = !!status.data?.running;
  const by = s?.by_level;
  const km2 = (mode: "subsidence" | "landslide", lv: string) => (by?.[mode]?.[lv] as { km2: number } | undefined)?.km2 ?? 0;
  const total = s ? LEVELS.reduce((a, l) => a + km2("subsidence", l.toLowerCase()) + km2("landslide", l.toLowerCase()), 0) || 1 : 1;
  const climate = s?.rain.pixels.find((p) => p.annual)?.annual;

  return (
    <div className="relative h-full w-full overflow-hidden">
      <MapCanvas m={shell} />

      {/* left: product, run, summary */}
      {!leftOpen && (
        <div className="absolute top-3 left-3 z-10">
          <ColumnToggle open={false} side="left" label={t("Hazard zoning")} onClick={() => setLeftOpen(true)} />
        </div>
      )}
      {leftOpen && (
        <div className="pointer-events-none absolute top-3 bottom-[184px] left-3 z-10 flex w-[min(350px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto">
          <Fold id="hazard.run" title={t("HAZARD ZONING")} extra={<ColumnToggle open side="left" label={t("zoning")} onClick={() => setLeftOpen(false)} />}>
            <select
              value={project && product ? `${project}/${product}` : ""}
              onChange={(e) => {
                const [n, ...rest] = e.target.value.split("/");
                go({ page: "hazard", name: n, product: rest.join("/") });
              }}
              aria-label={t("Product")}
              className="mt-2 h-8 w-full rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink"
            >
              {choices.length === 0 && <option value="">{t("No product in the workspace")}</option>}
              {choices.map((c) => (
                <option key={`${c.project}/${c.product}`} value={`${c.project}/${c.product}`}>
                  {c.label}
                </option>
              ))}
            </select>
            <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
              {PARAMS.map((p) => (
                <label key={p.key} className="flex items-center gap-1.5 text-[12px] text-muted">
                  <span className="w-[76px] flex-none truncate" title={t(p.label)}>{t(p.label)}</span>
                  <select
                    value={String(params[p.key] ?? (p.key === "cell_m" ? 100 : p.key === "horizon_yr" ? 10 : p.key === "max_lag_months" ? 6 : p.key === "alpha" ? 0.05 : "auto"))}
                    onChange={(e) => setParams((v) => ({ ...v, [p.key]: typeof p.options[0] === "number" ? Number(e.target.value) : e.target.value }))}
                    className="h-7 min-w-0 flex-1 rounded-md border border-line-2 bg-sunken px-1 text-[12px] text-ink"
                  >
                    {p.options.map((o) => (
                      <option key={o} value={String(o)}>
                        {o}
                        {p.unit ? ` ${t(p.unit)}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <label
              className="mt-1.5 flex items-center gap-1.5 text-[12px] text-muted"
              title={t("Stable ground (e.g. bedrock, a GNSS station): the series are re-referenced to the median of its cells. Empty = the product's reference")}
            >
              <span className="w-[76px] flex-none truncate">{t("Stable")}</span>
              <input
                value={refBox}
                onChange={(e) => setRefBox(e.target.value)}
                placeholder={t("reference area: W, S, E, N (optional)")}
                className="h-7 min-w-0 flex-1 rounded-md border border-line-2 bg-sunken px-2 font-mono text-[11.5px] text-ink placeholder:font-sans placeholder:text-faint"
              />
            </label>
            <label
              className={`mt-1.5 flex items-center gap-1.5 text-[12px] ${calib ? "text-muted" : "text-faint"}`}
              title={t(
                "Add the GNSS calibration of this product (Project → Validation → GNSS) to the series before rating them: rates relative to the GNSS frame instead of the product's reference",
              )}
            >
              <span className="w-[76px] flex-none">GNSS</span>
              <input type="checkbox" className="ml-0.5 flex-none accent-accent" disabled={!calib} checked={tie && !!calib} onChange={(e) => setTie(e.target.checked)} />
              <span className="flex-none whitespace-nowrap">{t("tie")}</span>
              <span className="min-w-0 truncate">
                {calib
                  ? `· ${calib.stations.join(", ")} (${fmt.vel(calib.rate_offset_mm_yr)} mm/yr${calib.loo_rms_after_mm_yr != null ? `, LOO ±${fmt.num(calib.loo_rms_after_mm_yr)}` : `, ${t("1 station")}`})`
                  : gnss.error
                    ? `· ${t("GNSS unavailable: restart geoeyes serve (the server predates this page)")}`
                    : `· ${t("no GNSS comparison of this product yet (Project → Validation → GNSS)")}`}
              </span>
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-2 [&>button]:whitespace-nowrap">
              <Button variant="primary" disabled={!product || running} onClick={run}>
                {running ? t("Running…") : s ? t("Run again") : t("Run hazard zoning")}
              </Button>
              {s && (
                <>
                  <Button onClick={() => (addTheme(project!, product!, ...themeOfView(view)), showProduct(project!, product!, { open: true }))}>{t("View on the results map")}</Button>
                  <Button onClick={() => (composeTheme(project!, product!, ...themeOfView(view)), showProduct(project!, product!), go({ page: "compose" }))}>{t("Make a map")}</Button>
                </>
              )}
              {s && (
                <a className="text-[12px] text-accent hover:underline" href={api.hazardFile(project!, product!, "hazard.gpkg")}>
                  GeoPackage
                </a>
              )}
              {s && (
                <a className="text-[12px] text-accent hover:underline" href={api.hazardFile(project!, product!, "cells.parquet")}>
                  Parquet
                </a>
              )}
            </div>
            {busy && <div className="mt-2 text-[12px] text-bad">{busy}</div>}
            {(running || status.data?.failed) && status.data!.log.length > 0 && (
              <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-line bg-deep p-2 font-mono text-[11px] text-ink-3">
                {status.data!.log.join("\n")}
              </pre>
            )}
            {!s && !running && product && (
              <p className="mt-2 text-[12px] leading-snug text-muted">
                {t(
                  "Not zoned yet. The run reads the DEM and the rainfall (CHIRPS, cached; the first time takes a minute) and writes the cells under analyses/hazard of the project.",
                )}
              </p>
            )}
          </Fold>

          {s && (
            <Fold id="hazard.summary" title={t("SUMMARY")}>
              <div className="mt-1 text-[12px] text-ink-2">
                {t("{n} cells of {m} m · {p} points · {d0} → {d1} ({k} months)", {
                  n: fmt.int(s.n_cells),
                  m: String(s.params.cell_m),
                  p: fmt.int(s.n_points),
                  d0: s.dates[0],
                  d1: s.dates[s.dates.length - 1],
                  k: s.span_months,
                })}
              </div>
              <div className="mt-2 flex h-3 overflow-hidden rounded">
                {[...LEVELS].map((l, i) => {
                  const a = km2("subsidence", l.toLowerCase()) + km2("landslide", l.toLowerCase());
                  return a > 0 ? <span key={l} title={`${t(l)}: ${a.toFixed(2)} km²`} style={{ width: `${(100 * a) / total}%`, background: rgb(LEVEL_RGB[i]) }} /> : null;
                })}
              </div>
              <div className="mt-2 grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-0.5 text-[12px]">
                <span className="text-[11px] text-faint">{t("level")}</span>
                <span className="text-right text-[11px] text-faint">{t("subsidence")}</span>
                <span className="text-right text-[11px] text-faint">{t("landslide")}</span>
                {[...LEVELS].reverse().map((l) => (
                  <div key={l} className="contents">
                    <span className="text-muted">{t(l)}</span>
                    <span className="text-right font-mono text-[11.5px] text-ink-2">{km2("subsidence", l.toLowerCase()).toFixed(2)} km²</span>
                    <span className="text-right font-mono text-[11.5px] text-ink-2">{km2("landslide", l.toLowerCase()).toFixed(2)} km²</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 rounded-lg border border-line bg-panel-2 px-2.5 py-2 text-[12px] leading-snug">
                <div className="text-[11px] font-semibold tracking-[1px] text-muted">{t("RAINFALL")}</div>
                <div className="mt-1 text-ink-2">{ts(s.rain.source).split(" (")[0]}</div>
                {climate && (
                  <div className="text-muted">
                    {t("Annual {a}–{b}: dry year (P10)", { a: s.rain.climate_years[0], b: s.rain.climate_years[1] })} <span className="font-mono text-ink-2">{climate.p10}</span>,{" "}
                    {t("median")} <span className="font-mono text-ink-2">{climate.p50}</span>, {t("wet year (P90)")} <span className="font-mono text-ink-2">{climate.p90}</span> mm
                  </div>
                )}
                <div className="mt-1 text-muted">
                  {s.coupling.assessed ? (
                    <>
                      {t("Coupling tested in {n} cells:", { n: fmt.int(s.coupling.cells_tested) })}{" "}
                      <span className="text-ink-2">{t("{n} significant", { n: fmt.int(s.coupling.cells_significant) })}</span>{" "}
                      {t("at FDR {a} ({k} below p {a} before the map-wide correction)", { a: String(s.params.alpha), k: fmt.int(s.coupling.cells_p_below_alpha) })}
                      {s.coupling.lag_months_median != null ? t("; median lag {n} months", { n: s.coupling.lag_months_median }) : ""}.
                    </>
                  ) : (
                    t("Coupling not assessed: the series is shorter than a seasonal cycle.")
                  )}
                </div>
                {s.accelerating_cells > 0 && <div className="mt-1 text-muted">{t("{n} cells accelerate significantly.", { n: fmt.int(s.accelerating_cells) })}</div>}
              </div>
              <div className="mt-2 text-[12px] leading-snug text-muted">
                {t("Reference:")}{" "}
                <span className="text-ink-2">
                  {s.reference.kind === "gnss"
                    ? `GNSS ${s.reference.stations?.join(", ")} (${ts(s.reference.calibration ?? "")}, ${fmt.vel(s.reference.rate_offset_mm_yr)} mm/yr)`
                    : s.reference.kind === "reference_bbox"
                    ? t("stable area {b} ({n} cells)", { b: s.reference.bbox?.join(", "), n: s.reference.cells })
                    : s.reference.kind === "point"
                      ? t("product reference point {lon}, {lat}", { lon: fmt.num(s.reference.lon, 4), lat: fmt.num(s.reference.lat, 4) })
                      : t("product ({kind})", { kind: ts(s.reference.kind) })}
                </span>
                {s.opposite_motion_cells > 0 &&
                  ` · ${t("{n} cells move against the hazard direction (uplift / upslope), flagged, not rated", { n: fmt.int(s.opposite_motion_cells) })}`}
              </div>
              {s.warnings.length > 0 && (
                <div className="mt-2 flex items-center gap-1.5 rounded-md bg-warn-bg px-2 py-1 text-[11.5px] text-warn-ink">
                  <span aria-hidden>!</span> {t("{n} warning(s): see the notifications", { n: s.warnings.length })}
                </div>
              )}
            </Fold>
          )}
          <MethodLink />
        </div>
      )}

      {/* right: view, legend, cell */}
      {s && !rightOpen && (
        <div className="absolute top-3 right-3 z-10">
          <ColumnToggle open={false} side="right" label={t("Legend & cell")} onClick={() => setRightOpen(true)} />
        </div>
      )}
      {s && rightOpen && (
        <div className="pointer-events-none absolute top-3 right-3 bottom-3 z-10 flex w-[min(370px,calc(100%-24px))] flex-col gap-3 overflow-y-auto pb-1 [&>*]:pointer-events-auto max-md:top-auto max-md:max-h-[45%]">
          <Fold id="hazard.legend" title={t("LAYERS")} extra={<ColumnToggle open side="right" label={t("legend")} onClick={() => setRightOpen(false)} />}>
            <select value={view} onChange={(e) => setView(e.target.value as View)} aria-label={t("Map layer")} className="h-8 w-full rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink">
              {VIEW_GROUPS.map(([grp, ids]) => (
                <optgroup key={grp} label={t(grp)}>
                  {ids.map((id) => (
                    <option key={id} value={id}>
                      {t(VIEWS.find((v) => v.id === id)!.label)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <Legend view={view} s={s} />
            {(view === "behaviour" || view === "change" || view === "risk" || view === "lines" || view === "consolidation" || view === "up" || view === "east" || view === "soft_soil" || view === "exposure") && (
              <BehaviourLegend view={view} st={behStatus.data} first={behCells.data?.first} last={behCells.data?.last} onRun={runAnalysis} expMode={expMode} setExpMode={setExpMode} />
            )}
            <About view={view} />
            {cells.isLoading && <div className="mt-2 text-[12px] text-accent-ink">{t("Loading cells…")}</div>}
          </Fold>
          {sel != null && cell.data && <CellPanel c={cell.data} beh={behCell.data} cons={consCell.data} onClose={() => setSel(null)} />}
          {selLine != null && lineProfile.data && <LinePanel p={lineProfile.data} onClose={() => setSelLine(null)} />}
          {selB != null && building.data && <RiskPanel b={building.data} onClose={() => setSelB(null)} />}
          {sel != null && cell.isLoading && <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Loading cell…")}</div>}
          {sel == null && (
            <div className="rounded-xl border border-line-2 bg-panel/95 p-3 text-[12px] text-muted">{t("Click a cell for its series, rainfall and the reasons of its level.")}</div>
          )}
        </div>
      )}
    </div>
  );
}
