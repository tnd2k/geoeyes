// New project: name and folder, area drawn on the map, track (Sentinel-1 tracks over the area found on ASF),
// dates, preview of the acquisitions the acquire phase would download, then project.toml is written.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AsfPreview, type AsfTrack, type Folder, type Workspace } from "../api";
import { t, ts } from "../i18n";
import { useApp } from "../state";
import { Button, Panel } from "../ui";

const field = "h-9 w-full rounded-md border border-line-2 bg-[#0a1322] px-2.5 text-[13px] text-ink focus:border-accent focus:outline-none";
const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

function folderPaths(list: Folder[], prefix = ""): string[] {
  return list.flatMap((f) => {
    const p = prefix ? `${prefix}/${f.name}` : f.name;
    return [p, ...folderPaths(f.folders, p)];
  });
}

function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-1 flex items-baseline gap-2">
      <span className="text-[12.5px] font-medium text-ink-2">{children}</span>
      {hint && <span className="text-[11.5px] text-faint">{hint}</span>}
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <Panel className="p-4">
      <div className="mb-3 flex items-center gap-2.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-raised text-[12px] font-semibold text-accent">{n}</span>
        <span className="text-[14px] font-semibold">{title}</span>
      </div>
      {children}
    </Panel>
  );
}

const RECT = "aoi";

function rectFeature(b: number[]) {
  const [w, s, e, n] = b;
  return {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "Polygon" as const, coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
  };
}

export function NewProject({ ws }: { ws: Workspace | undefined }) {
  const { go } = useApp();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [description, setDescription] = useState("");
  const [method, setMethod] = useState("psi");
  const [sensor, setSensor] = useState("sentinel1");
  const [direction, setDirection] = useState("descending");
  const [orbit, setOrbit] = useState<string>("");
  const [bbox, setBbox] = useState<number[] | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [start, setStart] = useState(() => new Date(Date.now() - 365 * 86400e3).toISOString().slice(0, 10));
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [perMonth, setPerMonth] = useState(3);
  const [atmosphere, setAtmosphere] = useState("era5");
  const [archive, setArchive] = useState("");
  const [tracks, setTracks] = useState<AsfTrack[] | null>(null);
  const [preview, setPreview] = useState<AsfPreview | null>(null);
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const corner = useRef<maplibregl.LngLat | null>(null);
  const s1 = sensor === "sentinel1";
  const folders = useMemo(() => folderPaths(ws?.tree.folders ?? []), [ws]);
  const exists = !!ws?.projects[name];
  const nameOk = NAME_RE.test(name) && !exists;

  // ------------------------------------------------------------ map
  useEffect(() => {
    if (!mapEl.current) return;
    const m = new maplibregl.Map({
      container: mapEl.current,
      style: {
        version: 8,
        sources: {
          sat: {
            type: "raster",
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            tileSize: 256,
            maxzoom: 19,
            attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
          },
          [RECT]: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
        },
        layers: [
          { id: "sat", type: "raster", source: "sat", paint: { "raster-saturation": -0.3, "raster-brightness-max": 0.85 } },
          { id: "aoi-fill", type: "fill", source: RECT, paint: { "fill-color": "#4cc2ff", "fill-opacity": 0.15 } },
          { id: "aoi-line", type: "line", source: RECT, paint: { "line-color": "#ffffff", "line-width": 2 } },
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

  const drawRect = (b: number[] | null) => {
    const src = map.current?.getSource(RECT) as maplibregl.GeoJSONSource | undefined;
    src?.setData({ type: "FeatureCollection", features: b ? [rectFeature(b)] : [] });
  };
  useEffect(() => drawRect(bbox), [bbox]);

  useEffect(() => {
    const m = map.current;
    if (!m || !drawing) return;
    m.getCanvas().style.cursor = "crosshair";
    corner.current = null;
    const box = (a: maplibregl.LngLat, b: maplibregl.LngLat) =>
      [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)].map((v) => Math.round(v * 1e5) / 1e5);
    const click = (e: maplibregl.MapMouseEvent) => {
      if (!corner.current) corner.current = e.lngLat;
      else {
        setBbox(box(corner.current, e.lngLat));
        setTracks(null);
        setPreview(null);
        setDrawing(false);
      }
    };
    const move = (e: maplibregl.MapMouseEvent) => corner.current && drawRect(box(corner.current, e.lngLat));
    m.on("click", click);
    m.on("mousemove", move);
    return () => {
      m.off("click", click);
      m.off("mousemove", move);
      m.getCanvas().style.cursor = "";
    };
  }, [drawing]);

  // ------------------------------------------------------------ ASF
  const findTracks = useMutation({ mutationFn: () => api.asfTracks(bbox!), onSuccess: (r) => setTracks(r.tracks) });
  const doPreview = useMutation({
    mutationFn: () =>
      api.asfPreview({ bbox: bbox!, direction, relative_orbit: Number(orbit), date_range: [start, end], max_per_month: perMonth }),
    onSuccess: setPreview,
  });
  const create = useMutation({
    mutationFn: () =>
      api.createProject({
        name,
        folder: folder || undefined,
        description: description || undefined,
        method,
        track: { sensor, direction, relative_orbit: s1 && orbit ? Number(orbit) : null },
        bbox,
        date_range: s1 && !archive ? [start, end] : null,
        max_per_month: s1 && !archive ? perMonth : 0,
        archive: archive || undefined,
        atmosphere,
      }),
    onSuccess: ({ name }) => {
      qc.invalidateQueries({ queryKey: ["workspace"] });
      go({ page: "project", name, tab: "pipeline" });
    },
  });
  const ready = nameOk && !!bbox && (!s1 || !!orbit || !!archive) && (s1 || !!archive);
  const maxMonth = preview ? Math.max(1, ...Object.values(preview.months)) : 1;

  return (
    <div className="flex h-full min-h-0 flex-wrap">
      <div className="h-full min-w-0 flex-[1_1_440px] overflow-y-auto p-5">
        <h1 className="text-[22px] font-semibold">{t("New project")}</h1>
        <p className="mt-1 text-[13px] text-muted">
          {t("Writes a minimal")} <span className="font-mono">project.toml</span>{t(": everything else comes from the sensor preset and can be changed later in Settings.")}
        </p>
        <div className="mt-5 space-y-4">
          <Step n={1} title={t("Project")}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label hint={t("a-z, 0-9, _ and -")}>{t("Name")}</Label>
                <input className={field} value={name} onChange={(e) => setName(e.target.value.toLowerCase())} placeholder="hanoi_s1_asc" aria-invalid={!!name && !nameOk} />
                {name && !nameOk && <div className="mt-1 text-[11.5px] text-bad">{exists ? t("A project with this name exists.") : t("Use a-z, 0-9, _ or -, starting with a letter or digit.")}</div>}
              </div>
              <div>
                <Label hint={t("in the project tree")}>{t("Folder")}</Label>
                <input className={field} list="folders" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="Vietnam/Hanoi" />
                <datalist id="folders">
                  {folders.map((f) => (
                    <option key={f} value={f} />
                  ))}
                </datalist>
              </div>
              <div className="sm:col-span-2">
                <Label>{t("Description")}</Label>
                <input className={field} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("Hanoi city centre, Sentinel-1 ascending")} />
              </div>
              <div>
                <Label>{t("Method")}</Label>
                <select className={field} value={method} onChange={(e) => setMethod(e.target.value)}>
                  <option value="psi">{t("psi — persistent scatterers")}</option>
                  <option value="psds">{t("psds — PS + distributed scatterers")}</option>
                  <option value="ps_lite">{t("ps_lite — fast PS (Capella)")}</option>
                </select>
              </div>
              <div>
                <Label>{t("Sensor")}</Label>
                <select className={field} value={sensor} onChange={(e) => (setSensor(e.target.value), setTracks(null), setPreview(null))}>
                  <option value="sentinel1">{t("Sentinel-1 (downloaded from ASF)")}</option>
                  <option value="cosmo_skymed">COSMO-SkyMed</option>
                  <option value="capella">Capella</option>
                  <option value="terrasar_x">TerraSAR-X</option>
                </select>
              </div>
            </div>
          </Step>

          <Step n={2} title={t("Area of interest")}>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant={drawing ? "primary" : "ghost"} onClick={() => setDrawing((d) => !d)}>
                {drawing ? t("Click two opposite corners on the map…") : bbox ? t("Redraw on the map") : t("Draw on the map")}
              </Button>
              {bbox && <span className="font-mono text-[12px] text-ink-2">{bbox.map((v) => v.toFixed(4)).join(", ")}</span>}
            </div>
            <div className="mt-3 grid grid-cols-4 gap-2">
              {["West", "South", "East", "North"].map((l, i) => (
                <input
                  key={l}
                  type="number"
                  step="any"
                  aria-label={t(l)}
                  placeholder={t(l)}
                  className={field}
                  value={bbox?.[i] ?? ""}
                  onChange={(e) => {
                    const b = [...(bbox ?? [0, 0, 0, 0])];
                    b[i] = parseFloat(e.target.value);
                    setBbox(b.every(Number.isFinite) ? b : null);
                    setTracks(null);
                    setPreview(null);
                  }}
                />
              ))}
            </div>
          </Step>

          <Step n={3} title={s1 ? t("Track and dates") : t("Track and data")}>
            {s1 ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Button disabled={!bbox || findTracks.isPending} onClick={() => findTracks.mutate()}>
                    {findTracks.isPending ? t("Searching ASF…") : t("Find Sentinel-1 tracks over the area")}
                  </Button>
                  {findTracks.error && <span className="text-[12px] text-bad">{ts((findTracks.error as Error).message)}</span>}
                </div>
                {tracks && (
                  <div className="mt-3 space-y-1.5">
                    {tracks.length === 0 && <div className="text-[13px] text-muted">{t("No Sentinel-1 burst over this area in the last 24 days.")}</div>}
                    {tracks.map((x) => {
                      const on = String(x.relative_orbit) === orbit && x.direction === direction;
                      return (
                        <button
                          key={x.track_id}
                          type="button"
                          onClick={() => (setOrbit(String(x.relative_orbit)), setDirection(x.direction), setPreview(null))}
                          className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-[13px] ${on ? "border-accent bg-[#102033]" : "border-line hover:bg-[#131f35]"}`}
                        >
                          <span className="font-mono">{x.track_id}</span>
                          <span className="text-muted">{x.subswaths.join(", ")}</span>
                          <span className="ml-auto text-[12px] text-ink-2">{x.coverage != null ? t("{pct}% of the area", { pct: Math.round(x.coverage * 100) }) : ""}</span>
                          <span className="text-[11.5px] text-faint">{t("last {date}", { date: x.last })}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="mt-3 grid gap-3 sm:grid-cols-4">
                  <div>
                    <Label>{t("Direction")}</Label>
                    <select className={field} value={direction} onChange={(e) => (setDirection(e.target.value), setPreview(null))}>
                      <option value="ascending">{t("ascending")}</option>
                      <option value="descending">{t("descending")}</option>
                    </select>
                  </div>
                  <div>
                    <Label>{t("Relative orbit")}</Label>
                    <input className={field} type="number" min={1} max={175} value={orbit} onChange={(e) => (setOrbit(e.target.value), setPreview(null))} />
                  </div>
                  <div>
                    <Label>{t("From")}</Label>
                    <input className={field} type="date" value={start} onChange={(e) => (setStart(e.target.value), setPreview(null))} />
                  </div>
                  <div>
                    <Label>{t("To")}</Label>
                    <input className={field} type="date" value={end} onChange={(e) => (setEnd(e.target.value), setPreview(null))} />
                  </div>
                  <div>
                    <Label hint={t("0 = all")}>{t("Per month")}</Label>
                    <input className={field} type="number" min={0} value={perMonth} onChange={(e) => (setPerMonth(Number(e.target.value)), setPreview(null))} />
                  </div>
                  <div>
                    <Label>{t("Atmosphere")}</Label>
                    <select className={field} value={atmosphere} onChange={(e) => setAtmosphere(e.target.value)}>
                      <option value="era5">ERA5</option>
                      <option value="gacos">GACOS</option>
                      <option value="none">{t("none")}</option>
                    </select>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button disabled={!bbox || !orbit || doPreview.isPending} onClick={() => doPreview.mutate()}>
                    {doPreview.isPending ? t("Asking ASF…") : t("Preview acquisitions")}
                  </Button>
                  {doPreview.error && <span className="text-[12px] text-bad">{ts((doPreview.error as Error).message)}</span>}
                </div>
                {preview && (
                  <div className="mt-3 rounded-lg border border-line bg-panel-2 p-3 text-[13px]">
                    <div>
                      <span className="font-semibold">{preview.acquisitions}</span> {t("acquisitions")} · {t("{n} bursts ({ids})", { n: preview.bursts, ids: preview.burst_ids.join(", ") })} · {t("about")}{" "}
                      <span className="font-semibold">{preview.gb} GB</span> {t("to download")} · {preview.platforms.join(", ")}
                    </div>
                    <div className="mt-3 flex h-20 items-end gap-1" role="img" aria-label={t("Acquisitions per month")}>
                      {Object.entries(preview.months).map(([m, n]) => (
                        <div key={m} className="flex flex-1 flex-col items-center gap-1" title={`${m}: ${n}`}>
                          <div className="w-full rounded-t bg-[#4c8dff]" style={{ height: `${(56 * n) / maxMonth}px` }} />
                          <span className="font-mono text-[9.5px] text-faint">{m.slice(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <Label hint={t("folder of the raw scenes (commercial data are not downloaded)")}>{t("Archive")}</Label>
                  <input className={field} value={archive} onChange={(e) => setArchive(e.target.value)} placeholder="D:\projects\geoeyes_workspace\archive\capella\capella-asc" />
                </div>
                <div>
                  <Label>{t("Direction")}</Label>
                  <select className={field} value={direction} onChange={(e) => setDirection(e.target.value)}>
                    <option value="ascending">{t("ascending")}</option>
                    <option value="descending">{t("descending")}</option>
                  </select>
                </div>
                <div>
                  <Label>{t("Atmosphere")}</Label>
                  <select className={field} value={atmosphere} onChange={(e) => setAtmosphere(e.target.value)}>
                    <option value="none">{t("none")}</option>
                    <option value="era5">ERA5</option>
                    <option value="gacos">GACOS</option>
                  </select>
                </div>
              </div>
            )}
          </Step>

          <div className="flex flex-wrap items-center gap-3 pb-6">
            <Button variant="primary" disabled={!ready || create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? t("Creating…") : t("Create project")}
            </Button>
            {!ready && <span className="text-[12px] text-faint">{s1 ? t("Name, area and track (relative orbit) are needed.") : t("Name, area and archive folder are needed.")}</span>}
            {create.error && <span className="text-[12px] text-bad">{ts((create.error as Error).message)}</span>}
          </div>
        </div>
      </div>
      <div className="relative min-h-[360px] flex-[1_1_480px]">
        <div className="absolute inset-0">
          <div ref={mapEl} className="h-full w-full" />
        </div>
        {drawing && (
          <div className="absolute top-3 left-3 z-10 rounded-md bg-[#0b1220]/85 px-3 py-1.5 text-[12.5px] text-ink-2">{t("Click a first corner, then the opposite corner")}</div>
        )}
      </div>
    </div>
  );
}
