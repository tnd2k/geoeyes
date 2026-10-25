// Overview: every project at a glance — what needs attention, what is running, the latest products.
import { useState } from "react";
import type { ProjectSummary, Workspace } from "../api";
import { useApp } from "../state";
import { Chip, Confidence, fmt, Panel } from "../ui";

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Panel className="px-4 py-3.5">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="mt-1 text-[26px] leading-tight font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[11.5px] text-faint">{hint}</div>}
    </Panel>
  );
}

function VelBar({ min, max }: { min?: number; max?: number }) {
  if (min == null || max == null) return null;
  const span = Math.max(Math.abs(min), Math.abs(max)) || 1;
  const x = (v: number) => 50 + (50 * v) / span;
  return (
    <div className="mt-1" title="LOS velocity range of the latest product (min to max), 0 in the middle">
      <div className="relative h-2 rounded-full bg-[#1a2740]">
        <div
          className="absolute top-0 h-2 rounded-full"
          style={{
            left: `${x(min)}%`,
            width: `${x(max) - x(min)}%`,
            background: "linear-gradient(90deg, #800000, #ff1400, #ffd400, #7cff79, #00b8ff, #0010ff, #000080)",
          }}
        />
        <div className="absolute top-[-2px] h-3 w-px bg-ink" style={{ left: "50%" }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[11px] text-muted">
        <span>{fmt.vel(min)}</span>
        <span>mm/yr</span>
        <span>{fmt.vel(max)}</span>
      </div>
    </div>
  );
}

function Card({ p }: { p: ProjectSummary }) {
  const { go, showProduct } = useApp();
  const t = p.tracks.find((x) => x.product) ?? p.tracks[0];
  const prod = t?.product;
  return (
    <Panel className="flex flex-col p-4 transition-colors hover:border-line-2">
      <div className="flex items-start justify-between gap-2">
        <button type="button" onClick={() => go({ page: "project", name: p.name })} className="min-w-0 text-left">
          <div className="truncate font-mono text-[14px] hover:text-accent">{p.name}</div>
          <div className="mt-0.5 truncate text-[12px] text-muted">
            {p.tracks.map((x) => `${fmt.sensor(x.sensor)} ${x.direction}`).join(" · ") || "no track"} · {p.method?.toUpperCase()}
          </div>
        </button>
        <Chip status={p.status} />
      </div>
      {prod ? (
        <div className="mt-3 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-2">
            <span className="font-mono">v{prod.version}</span>
            <span className="text-muted">·</span>
            <span>{fmt.int(prod.n_points)} points</span>
            <span className="text-muted">·</span>
            <span>
              {prod.epochs} dates, {prod.first} → {prod.last}
            </span>
          </div>
          <VelBar min={prod.vel_min} max={prod.vel_max} />
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <Confidence level={prod.confidence} />
            {(p.alerts ?? 0) > 0 && (
              <button type="button" onClick={() => go({ page: "project", name: p.name, tab: "monitoring" })}>
                <Chip status="failed" label={`${p.alerts} alert${p.alerts! > 1 ? "s" : ""}`} />
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-3 flex-1 text-[12.5px] text-muted">{p.error ?? "No product yet."}</div>
      )}
      <div className="mt-3 flex gap-2 border-t border-line pt-3">
        {prod && (
          <button type="button" className="text-[12.5px] text-accent hover:underline" onClick={() => showProduct(p.name, prod.id, { open: true })}>
            Open map
          </button>
        )}
        <button type="button" className="text-[12.5px] text-muted hover:text-ink" onClick={() => go({ page: "project", name: p.name })}>
          Pipeline
        </button>
        {p.last_run && <span className="ml-auto text-[11.5px] text-faint">last run {fmt.runTime(p.last_run.id)}</span>}
      </div>
    </Panel>
  );
}

export function Overview({ ws }: { ws: Workspace | undefined }) {
  const { go } = useApp();
  const [filter, setFilter] = useState<"all" | "attention" | "running">("all");
  if (!ws) return <div className="p-8 text-muted">Loading…</div>;
  const all = Object.values(ws.projects);
  const products = all.flatMap((p) => p.tracks.map((t) => t.product).filter(Boolean));
  const attention = all.filter((p) => ["failed", "interrupted", "invalid"].includes(p.status) || (p.alerts ?? 0) > 0);
  const running = all.filter((p) => p.status === "running");
  const shown = filter === "attention" ? attention : filter === "running" ? running : all;
  const points = products.reduce((a, p) => a + (p?.n_points ?? 0), 0);
  const runs = all
    .filter((p) => p.last_run)
    .map((p) => ({ project: p.name, run: p.last_run! }))
    .sort((a, b) => b.run.id.localeCompare(a.run.id));

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1280px] px-6 py-6">
        <h1 className="text-[22px] font-semibold">Overview</h1>
        <p className="mt-1 text-[13px] text-muted">
          Workspace <span className="font-mono text-ink-2">{ws.root}</span>
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="Projects" value={String(all.length)} hint={`${products.length} with a product`} />
          <Kpi label="Running" value={String(running.length)} hint={running.map((p) => p.name).join(", ") || "nothing running"} />
          <Kpi label="Need attention" value={String(attention.length)} hint={attention.length ? "failed runs or triggered alerts" : "all good"} />
          <Kpi label="Measured points" value={points >= 1e6 ? `${(points / 1e6).toFixed(2)} M` : fmt.int(points)} hint="in the latest products" />
        </div>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <h2 className="text-[15px] font-semibold">Projects</h2>
          <div className="flex rounded-lg border border-line-2 bg-panel p-0.5">
            {(
              [
                ["all", `All ${all.length}`],
                ["attention", `Need attention ${attention.length}`],
                ["running", `Running ${running.length}`],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                aria-pressed={filter === k}
                onClick={() => setFilter(k)}
                className={`h-7 rounded-md px-3 text-[12.5px] ${filter === k ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((p) => (
            <Card key={p.name} p={p} />
          ))}
          {shown.length === 0 && <div className="text-[13px] text-muted">Nothing here.</div>}
        </div>

        <h2 className="mt-8 text-[15px] font-semibold">Latest runs</h2>
        <Panel className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-[13px]">
            <thead>
              <tr className="text-left text-muted">
                {["Project", "Run", "Duration", "Status"].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map(({ project, run }) => (
                <tr key={project} className="cursor-pointer border-t border-line hover:bg-[#131f35]" onClick={() => go({ page: "project", name: project, tab: "runs" })}>
                  <td className="px-4 py-2.5 font-mono">{project}</td>
                  <td className="px-4 py-2.5 font-mono text-ink-2">{fmt.runTime(run.id)}</td>
                  <td className="px-4 py-2.5 text-ink-2">{fmt.secs(run.seconds) || "–"}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <Chip status={run.status} />
                      {run.error && <span className="truncate text-[12px] text-bad">{run.error}</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
