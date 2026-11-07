// Source Cooperative (source.coop): search its whole catalog (the server indexes it by itself, daily) and see the open
// layers GeoEyes reads over a project area — flood (surface water, GloFAS depth, daily rainfall) and exposure
// (population, building heights). Every product is public: its data URL is copied as is into QGIS, GDAL or DuckDB.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type CoopProduct } from "../api";
import { t, ts } from "../i18n";
import { Panel } from "../ui";

const field = "h-9 rounded-md border border-line-2 bg-sunken px-2.5 text-[13px] text-ink focus:border-accent focus:outline-none";
const TOPIC: Record<string, string> = { flood: "#1f7fd6", exposure: "#e08a00" };

function useDebounced<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const h = setTimeout(() => setD(v), ms);
    return () => clearTimeout(h);
  }, [v, ms]);
  return d;
}

function Product({ p, layerTitle }: { p: CoopProduct; layerTitle?: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const long = p.description.length > 260;
  return (
    <div className="rounded-lg border border-line bg-panel p-3 hover:bg-panel-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <a href={p.url} target="_blank" rel="noopener" className="text-[14px] font-semibold text-ink no-underline hover:underline">
          {p.title || p.product}
        </a>
        {p.layer && (
          <span className="rounded bg-accent-bg px-1.5 py-0.5 text-[11px] font-medium text-accent" title={layerTitle}>
            {t("read by GeoEyes")}
          </span>
        )}
        <span className="ml-auto text-[11.5px] text-faint">{p.updated}</span>
      </div>
      <div className="mt-0.5 font-mono text-[11.5px] text-muted">{p.id}</div>
      {p.description && (
        <div className="mt-1.5 text-[12.5px] whitespace-pre-line text-ink-2">
          {open || !long ? p.description : `${p.description.slice(0, 260)}…`}
          {long && (
            <button type="button" className="ml-1 text-[12px] text-accent hover:underline" onClick={() => setOpen((o) => !o)}>
              {open ? t("less") : t("more")}
            </button>
          )}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px]">
        {p.tags.slice(0, 8).map((g) => (
          <span key={g} className="rounded bg-sunken px-1.5 py-0.5 text-muted">
            {g}
          </span>
        ))}
        <button
          type="button"
          className="ml-auto text-[12px] text-muted hover:text-ink"
          title={p.data}
          onClick={() => navigator.clipboard?.writeText(p.data).then(() => (setCopied(true), setTimeout(() => setCopied(false), 1500)))}
        >
          {copied ? t("Copied") : t("Copy data URL")}
        </button>
      </div>
    </div>
  );
}

export function Coop() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [layersOnly, setLayersOnly] = useState(false);
  const q = useDebounced(query.trim(), 250);

  const status = useQuery({
    queryKey: ["coop"],
    queryFn: api.coop,
    refetchInterval: (s) => (s.state.data?.sync.running ? 1500 : false),
  });
  const syncing = status.data?.sync.running ?? false;
  const wasSyncing = useRef(false);
  useEffect(() => {
    if (wasSyncing.current && !syncing) qc.invalidateQueries({ queryKey: ["coop-search"] });
    wasSyncing.current = syncing;
  }, [syncing, qc]);
  const sync = useMutation({ mutationFn: api.coopSync, onSuccess: () => qc.invalidateQueries({ queryKey: ["coop"] }) });
  const indexed = (status.data?.products ?? 0) > 0;
  const found = useQuery({
    queryKey: ["coop-search", q, layersOnly],
    queryFn: () => api.coopSearch(q, layersOnly),
    enabled: indexed,
    placeholderData: (prev) => prev,
  });
  const layers = status.data?.layers ?? [];
  const title = Object.fromEntries(layers.map((l) => [l.key, l.title]));
  const err = sync.error ? (sync.error as Error).message : status.data?.sync.error;

  return (
    <div className="flex h-full min-h-0 flex-wrap">
      <div className="flex h-full min-w-0 flex-[1_1_560px] flex-col">
        <div className="flex-none border-b border-line p-4">
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="text-[20px] font-semibold">Source Cooperative</h1>
            <span className="text-[12.5px] text-muted">
              {indexed ? t("{n} open products", { n: status.data?.products ?? 0 }) : ""}
              {status.data?.synced && ` · ${t("updated {date}", { date: status.data.synced.slice(0, 16).replace("T", " ") })}`}
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
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              className={`${field} w-80 max-w-full`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("flood, population, building height, rainfall…")}
              aria-label={t("Search the catalog")}
              autoFocus
            />
            <label className="flex items-center gap-1.5 text-[12px] text-ink-2">
              <input type="checkbox" checked={layersOnly} onChange={(e) => setLayersOnly(e.target.checked)} />
              {t("Only the layers GeoEyes reads")}
            </label>
            {found.data && <span className="text-[12px] text-faint">{t("{n} result(s)", { n: found.data.total })}</span>}
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
          {!indexed && (
            <Panel className="p-4">
              <div className="text-[13.5px] font-medium">{syncing ? t("Fetching the list of open data…") : t("No open data listed yet.")}</div>
              <div className="mt-1 text-[12.5px] text-muted">{t("GeoEyes reads the Source Cooperative catalog (a few seconds).")}</div>
            </Panel>
          )}
          {err && <div className="text-[12px] text-bad">{ts(err)}</div>}
          {found.error && <div className="text-[12px] text-bad">{ts((found.error as Error).message)}</div>}
          {indexed && found.data?.total === 0 && <div className="text-[13px] text-muted">{t("No product matches these words.")}</div>}
          {(found.data?.products ?? []).map((p) => (
            <Product key={p.id} p={p} layerTitle={p.layer ? title[p.layer] : undefined} />
          ))}
        </div>
      </div>
      <aside className="h-full min-w-0 flex-[1_1_340px] overflow-y-auto border-l border-line bg-panel-2 p-4">
        <h2 className="text-[15px] font-semibold">{t("Layers GeoEyes reads")}</h2>
        <p className="mt-1 text-[12.5px] text-muted">
          {t("Only the project area is read (cloud-optimized files), then kept in the workspace cache.")}
        </p>
        <div className="mt-3 space-y-2">
          {layers.map((l) => (
            <div key={l.key} className="rounded-lg border border-line bg-panel p-3">
              <div className="flex items-baseline gap-2">
                <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: TOPIC[l.topic] }} aria-hidden />
                <a href={l.url} target="_blank" rel="noopener" className="text-[13px] font-semibold text-ink no-underline hover:underline">
                  {l.title}
                </a>
              </div>
              <div className="mt-1 text-[12px] text-ink-2">{t(l.use)}</div>
              <div className="mt-1 text-[11px] text-faint">
                {t(l.topic === "flood" ? "Flood" : "Exposure")} · {l.license} · {l.credit}
              </div>
            </div>
          ))}
        </div>
        <h3 className="mt-5 text-[13px] font-semibold">{t("Use them")}</h3>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-[12.5px] text-ink-2">
          <li>{t("Risk to buildings: heights missing in Overture are taken from GlobalBuildingAtlas.")}</li>
          <li>
            {t("Exposure of a product: people and buildings per subsidence class, and in the flood of a month:")}{" "}
            <code className="font-mono text-[11.5px]">geoeyes exposure &lt;project&gt; --set flood_month=2024-09</code>
          </li>
          <li>
            {t("One layer over an area:")} <code className="font-mono text-[11.5px]">geoeyes coop get gsw-monthly --bbox … --month 2024-09</code>
          </li>
        </ul>
      </aside>
    </div>
  );
}
