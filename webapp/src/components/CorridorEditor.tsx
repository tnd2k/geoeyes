// A project's processing corridor: its own map with the brush, the saved corridor reopened from its strokes, Save
// (corridor.geojson + [aoi] corridor and bbox) and Remove. The project's rectangle ([aoi] bbox) is drawn as a dashed
// outline for reference.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { api, type CorridorDraft } from "../api";
import { t, ts } from "../i18n";
import { baseSource, DEFAULT_BASE, switchBase, type Base } from "../map";
import { ask, Button, Panel } from "../ui";
import { BasemapPicker } from "./BasemapPicker";
import { BrushHint, CorridorTools, bboxKm2, emptyDraft, useCorridorBrush, type BrushMode } from "./CorridorBrush";

const BOX = "project-bbox";

function boxFC(b: number[] | null | undefined) {
  if (!b) return { type: "FeatureCollection" as const, features: [] };
  const [w, s, e, n] = b;
  return {
    type: "FeatureCollection" as const,
    features: [{ type: "Feature" as const, properties: {}, geometry: { type: "Polygon" as const, coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } }],
  };
}

export function CorridorEditor({ name, running }: { name: string; running: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["corridor", name], queryFn: () => api.projectCorridor(name) });
  const settings = useQuery({ queryKey: ["settings", name], queryFn: () => api.settings(name) });
  const bboxNow =
    (settings.data?.sections.find((s) => s.name === "aoi")?.fields.find((f) => f.key === "bbox")?.value as number[] | null | undefined) ?? null;
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [base, setBase] = useState<Base>(DEFAULT_BASE);
  const [on, setOn] = useState(false);
  const [mode, setMode] = useState<BrushMode>("brush");
  const [width, setWidth] = useState(1000);
  const brush = useCorridorBrush(map, { active: on, mode, width });
  const saved = q.data?.corridor;

  useEffect(() => {
    if (!mapEl.current) return;
    const m = new maplibregl.Map({
      container: mapEl.current,
      style: {
        version: 8,
        sources: { base: baseSource(DEFAULT_BASE), [BOX]: { type: "geojson", data: boxFC(null) } },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#d9dde3" } },
          { id: "base", type: "raster", source: "base" },
          { id: "project-bbox", type: "line", source: BOX, paint: { "line-color": "#64748b", "line-width": 1.5, "line-dasharray": [3, 2] } },
        ],
      },
      center: [105.85, 21.02],
      zoom: 9,
      dragRotate: false,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => switchBase(m, base);
    if (m.isStyleLoaded()) apply();
    else m.once("load", apply);
  }, [base]);

  // the rectangle, and the view on it once
  const fitted = useRef(false);
  useEffect(() => {
    const m = map.current;
    if (!m || !bboxNow) return;
    const set = () => (m.getSource(BOX) as maplibregl.GeoJSONSource | undefined)?.setData(boxFC(bboxNow));
    if (m.isStyleLoaded()) set();
    else m.once("load", set);
    if (!fitted.current) {
      fitted.current = true;
      m.fitBounds([bboxNow[0], bboxNow[1], bboxNow[2], bboxNow[3]], { padding: 40, duration: 0 });
    }
  }, [bboxNow]);

  // reopen the saved corridor from its strokes (a file import without strokes keeps its polygon only)
  const loaded = useRef(false);
  const { reset } = brush;
  useEffect(() => {
    if (loaded.current || !q.data) return;
    loaded.current = true;
    const src = saved?.info?.source;
    if (src && (src.strokes?.length || src.polygons?.length)) {
      const w = Number(src.width_m ?? saved?.info?.width_m ?? 1000);
      setWidth(w);
      reset({ strokes: src.strokes ?? [], erase: src.erase ?? [], polygons: src.polygons ?? [], width_m: w } as CorridorDraft);
    } else if (saved?.geometry) {
      reset({ ...emptyDraft(saved.info?.width_m ?? 1000), polygons: [saved.geometry] });
    }
  }, [q.data, saved, reset]);

  const after = () => {
    qc.invalidateQueries({ queryKey: ["corridor", name] });
    qc.invalidateQueries({ queryKey: ["settings", name] });
    qc.invalidateQueries({ queryKey: ["plan", name] });
  };
  const save = useMutation({ mutationFn: () => api.saveCorridor(name, brush.draft), onSuccess: after });
  const remove = useMutation({ mutationFn: () => api.clearCorridor(name), onSuccess: after });

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(360px,440px)_1fr]">
      <Panel className="space-y-3 p-4">
        <div className="text-[14px] font-semibold">{t("Processing corridor")}</div>
        <div className="text-[12.5px] leading-snug text-muted">
          {t("Paint the area to process along the route. Only the Sentinel-1 bursts the corridor touches are kept; the stack is still cut to the rectangle around it until the sparse stack (plan step K3).")}
        </div>
        {saved ? (
          <div className="rounded-lg border border-line bg-panel-2 px-3 py-2 text-[12.5px]">
            {t("Saved: {len} km, {area} km², width {w} m", { len: (saved.info.length_km ?? 0).toFixed(1), area: (saved.info.area_km2 ?? 0).toFixed(1), w: saved.info.width_m })}
            {saved.problem && <div className="mt-1 text-bad">{ts(saved.problem)}</div>}
          </div>
        ) : (
          q.data && <div className="text-[12.5px] text-faint">{t("No corridor: the whole rectangle ([aoi] bbox) is processed.")}</div>
        )}
        <CorridorTools brush={brush} active={on} onActive={setOn} mode={mode} onMode={setMode} width={width} onWidth={setWidth} bboxArea={bboxKm2(brush.preview?.bbox)} />
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <Button variant="primary" disabled={brush.empty || save.isPending || running || !brush.preview?.geometry} onClick={() => save.mutate()}>
            {save.isPending ? t("Saving…") : t("Save the corridor")}
          </Button>
          {saved && (
            <Button
              variant="danger"
              disabled={remove.isPending || running}
              onClick={async () => {
                if (await ask(t("Remove the corridor? The whole rectangle will be processed again (the bbox stays)."))) remove.mutate();
              }}
            >
              {t("Remove the corridor")}
            </Button>
          )}
          {running && <span className="text-[12px] text-warn">{t("A run is going: save after it ends.")}</span>}
        </div>
        {save.isSuccess && <div className="text-[12px] text-good">{t("Saved: [aoi] corridor and bbox updated. The next run downloads and builds only what changed.")}</div>}
        {(save.error || remove.error) && <div className="text-[12px] text-bad">{ts(((save.error || remove.error) as Error).message)}</div>}
      </Panel>
      <div className="relative min-h-[520px] overflow-hidden rounded-xl border border-line">
        <div className="absolute inset-0">
          <div ref={mapEl} className="h-full w-full" />
        </div>
        <BasemapPicker map={map} base={base} onChange={setBase} />
        {on && <BrushHint mode={mode} />}
      </div>
    </div>
  );
}
