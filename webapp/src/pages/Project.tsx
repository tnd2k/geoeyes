// Project: pipeline status and plan (what would run and why), Run / Stop, live log, data, runs, settings.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type LogLine, type PlanStep, type ProjectDetail, type ReportDate, type Track } from "../api";
import { Monitor } from "../components/Monitor";
import { SettingsForm } from "../components/SettingsForm";
import { Gnss } from "../components/Gnss";
import { Validation } from "../components/Validation";
import { t, ts } from "../i18n";
import { useApp } from "../state";
import { Button, Chip, Confidence, fmt, Panel } from "../ui";

const PHASES: { name: string; label: string; what: string }[] = [
  { name: "acquire", label: "Acquire", what: "Sentinel-1 bursts from ASF into the archive" },
  { name: "build_stack", label: "Stack", what: "Coregistered SLC stack on the reference date" },
  { name: "phase_linking", label: "Phase linking", what: "Distributed scatterers (PS-DS)" },
  { name: "ps", label: "Point engine", what: "Selection, unwrapping, atmosphere, velocity" },
  { name: "build_product", label: "Product", what: "Immutable versioned point product" },
  { name: "export", label: "Export", what: "GeoPackage styled for QGIS" },
  { name: "report", label: "Report", what: "PDF report and confidence level" },
];

const TABS = [
  ["pipeline", "Pipeline"],
  ["data", "Data"],
  ["runs", "Runs"],
  ["monitoring", "Monitoring"],
  ["validation", "Validation"],
  ["settings", "Settings"],
] as const;

function useRunLog(project: string, runId: string | null | undefined, live: boolean) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const next = useRef(0);
  useEffect(() => {
    setLines([]);
    next.current = 0;
    if (!runId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const pull = async () => {
      try {
        const r = await api.log(project, runId, next.current);
        if (stop) return;
        next.current = r.next;
        if (r.lines.length) setLines((l) => [...l, ...r.lines].slice(-1500));
      } catch {
        /* run folder not there yet */
      }
      if (!stop && live) timer = setTimeout(pull, 2000);
    };
    pull();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [project, runId, live]);
  return lines;
}

function LogView({ lines, title }: { lines: LogLine[]; title: string }) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [lines]);
  return (
    <div className="rounded-xl border border-line bg-[#070c16]">
      <div className="border-b border-line px-4 py-2 text-[12px] font-semibold text-muted">{title}</div>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="h-72 overflow-auto px-4 py-2 font-mono text-[11.5px] leading-[1.65] text-[#a9b8cf]"
      >
        {lines.length === 0 && <div className="text-faint">{t("No log lines.")}</div>}
        {lines.map((l, i) => (
          <div
            key={i}
            className={`whitespace-pre-wrap ${l.level === "ERROR" || l.level === "CRITICAL" ? "text-bad" : l.level === "WARNING" ? "text-warn" : l.event === "phase_end" ? "text-good" : ""}`}
          >
            <span className="text-faint">{new Date(l.ts).toLocaleTimeString("en-GB")}</span>{" "}
            {l.phase && <span className="text-[#7f93b3]">{l.phase.padEnd(13)}</span>} {l.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

function PhaseCard({ tr, phase, step }: { tr: Track; phase: (typeof PHASES)[number]; step?: PlanStep }) {
  const rec = tr.phases[phase.name];
  const status = rec?.status ?? (step?.action === "disabled" ? "disabled" : "new");
  const border = { running: "#2f6fb0", failed: "#5c2424", interrupted: "#5c4a24" }[status] ?? "#1d2a42";
  return (
    <div className="flex min-h-[138px] flex-col gap-2 rounded-xl border bg-panel p-3.5" style={{ borderColor: border }}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13.5px] font-semibold">{t(phase.label)}</span>
        <span className="font-mono text-[11px] text-muted">{fmt.secs(rec?.seconds)}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Chip status={status === "done" ? "ok" : status} label={status === "done" ? t("done") : status === "new" ? t("not run") : undefined} />
        {step && step.action !== "disabled" && <Chip status={step.action} />}
      </div>
      <div className="text-[12px] leading-snug text-[#a9b8cf]">
        {rec?.error ? <span className="text-bad">{ts(rec.error)}</span> : step?.reason && step.action !== "up-to-date" ? ts(step.reason) : t(phase.what)}
      </div>
      {rec?.updated && <div className="mt-auto text-[11px] text-faint">{new Date(rec.updated).toLocaleString("en-GB")}</div>}
    </div>
  );
}

function Baselines({ dates }: { dates: ReportDate[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = dates.filter((d) => d.bperp_m != null);
  if (pts.length < 2) return <div className="text-[13px] text-muted">{t("No baseline information in the product report.")}</div>;
  const tm = pts.map((d) => Date.parse(d.date));
  const b = pts.map((d) => d.bperp_m as number);
  const t0 = Math.min(...tm), t1 = Math.max(...tm);
  const bmax = Math.max(50, ...b.map(Math.abs)) * 1.1;
  const W = 640, H = 240, L = 52, R = 12, T = 12, B = 28;
  const X = (v: number) => L + ((v - t0) / (t1 - t0 || 1)) * (W - L - R);
  const Y = (v: number) => T + ((bmax - v) / (2 * bmax)) * (H - T - B);
  const ref = pts.findIndex((d) => d.reference);
  const years: number[] = [];
  for (let y = new Date(t0).getUTCFullYear(); y <= new Date(t1).getUTCFullYear() + 1; y++) years.push(Date.UTC(y, 0, 1));
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={t("Perpendicular baseline of each acquisition against time")}>
        {[-bmax / 1.1, 0, bmax / 1.1].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke={v === 0 ? "#2b3c5c" : "#1a2740"} />
            <text x={L - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="#93a4bf" fontFamily="JetBrains Mono">
              {Math.round(v)} m
            </text>
          </g>
        ))}
        {years
          .filter((y) => y >= t0 && y <= t1)
          .map((y) => (
            <text key={y} x={X(y)} y={H - 8} textAnchor="middle" fontSize="11" fill="#93a4bf" fontFamily="JetBrains Mono">
              {new Date(y).getUTCFullYear()}
            </text>
          ))}
        <text x={L} y={H - 8} fontSize="11" fill="#6f7f99" fontFamily="JetBrains Mono">{pts[0].date}</text>
        <text x={W - R} y={H - 8} textAnchor="end" fontSize="11" fill="#6f7f99" fontFamily="JetBrains Mono">{pts[pts.length - 1].date}</text>
        {ref >= 0 &&
          pts.map((d, i) => (i === ref ? null : <line key={d.date} x1={X(tm[ref])} y1={Y(b[ref])} x2={X(tm[i])} y2={Y(b[i])} stroke="#22324d" />))}
        {pts.map((d, i) => (
          <circle
            key={d.date}
            cx={X(tm[i])}
            cy={Y(b[i])}
            r={i === hover ? 7 : 5}
            fill={d.used === false ? "#6f7f99" : "#4c8dff"}
            stroke="#0b1220"
            strokeWidth="1.5"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        {ref >= 0 && <circle cx={X(tm[ref])} cy={Y(b[ref])} r="9" fill="none" stroke="#fff" strokeWidth="2" />}
      </svg>
      {hover != null && (
        <div className="pointer-events-none absolute top-1 right-2 rounded bg-[#0b1220] px-2 py-1 font-mono text-[11.5px]">
          {pts[hover].date} · {b[hover].toFixed(0)} m{pts[hover].reference ? ` · ${t("reference")}` : ""}
        </div>
      )}
    </div>
  );
}

export function Project({ name, tab = "pipeline" }: { name: string; tab?: string }) {
  const { go, showProduct } = useApp();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["project", name],
    queryFn: () => api.project(name),
    refetchInterval: (query) => ((query.state.data as ProjectDetail | undefined)?.running ? 3000 : 15000),
  });
  const [planOn, setPlanOn] = useState(false);
  const plan = useQuery({ queryKey: ["plan", name], queryFn: () => api.plan(name), enabled: planOn, staleTime: 30_000 });
  const [logRun, setLogRun] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api.run(name),
    onSuccess: () => {
      setPlanOn(false);
      setTimeout(() => qc.invalidateQueries({ queryKey: ["project", name] }), 1500);
      qc.invalidateQueries({ queryKey: ["workspace"] });
    },
  });
  const stop = useMutation({
    mutationFn: () => api.stop(name),
    onSettled: () => (qc.invalidateQueries({ queryKey: ["project", name] }), qc.invalidateQueries({ queryKey: ["workspace"] })),
  });
  useEffect(() => {
    setPlanOn(false);
    setLogRun(null);
  }, [name]);

  const p = q.data;
  const liveRun = p?.running?.run_id ?? null;
  const shownRun = logRun ?? liveRun ?? p?.runs[0]?.id ?? null;
  const lines = useRunLog(name, shownRun, !!liveRun && shownRun === liveRun);
  const product = p?.tracks.find((t) => t.product)?.product;
  const report = useQuery({
    queryKey: ["report", name, product?.id],
    queryFn: () => api.product(name, product!.id),
    enabled: !!product && tab === "data",
  });

  if (q.error) return <div className="p-8 text-bad">{(q.error as Error).message}</div>;
  if (!p) return <div className="p-8 text-muted">{t("Loading…")}</div>;
  const toRun = plan.data?.steps.filter((s) => s.action === "run").length ?? null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1280px] px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-mono text-[22px] font-medium">{p.name}</h1>
              <Chip status={p.status} label={p.status === "running" ? `${t("Running")}${p.tracks.flatMap((t) => Object.entries(t.phases)).find(([, r]) => r.status === "running")?.[0] ? ` · ${p.tracks.flatMap((t) => Object.entries(t.phases)).find(([, r]) => r.status === "running")![0]}` : ""}` : undefined} />
              {product && <Confidence level={product.confidence} />}
            </div>
            <p className="mt-1.5 text-[13.5px] text-muted">
              {p.description ? `${p.description} · ` : ""}
              {p.tracks.map((t) => `${fmt.sensor(t.sensor)} ${t.direction}${t.relative_orbit != null ? ` ${String(t.relative_orbit).padStart(3, "0")}` : ""}${t.subswaths.length ? ` ${t.subswaths.join(",")}` : ""}`).join(" · ")}
              {p.date_range ? ` · ${p.date_range[0]} → ${p.date_range[1]}` : ""} · {p.method?.toUpperCase()}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {product && (
              <Button onClick={() => showProduct(p.name, product.id, { open: true })}>{t("View results")}</Button>
            )}
            {product?.report && (
              <Button onClick={() => window.open(api.fileUrl(p.name, product.id, "report.pdf"), "_blank", "noopener")}>{t("Report PDF")}</Button>
            )}
            <Button onClick={() => (setPlanOn(true), plan.refetch(), go({ page: "project", name, tab: "pipeline" }))} disabled={plan.isFetching}>
              {plan.isFetching ? t("Checking…") : t("Check plan")}
            </Button>
            {p.running ? (
              <Button variant="danger" onClick={() => confirm(t("Stop the run of {name}?", { name: p.name })) && stop.mutate()} disabled={stop.isPending}>
                {t("Stop run")}
              </Button>
            ) : (
              <Button variant="primary" onClick={() => run.mutate()} disabled={run.isPending}>
                ▶ {t("Run")}
              </Button>
            )}
          </div>
        </div>
        {(run.error || stop.error) && <div className="mt-3 rounded-lg bg-[#2a1414] px-3 py-2 text-[13px] text-bad">{((run.error || stop.error) as Error).message}</div>}

        <div role="tablist" className="mt-5 mb-5 flex flex-wrap gap-1 border-b border-line">
          {TABS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={tab === k}
              onClick={() => go({ page: "project", name, tab: k })}
              className={`-mb-px h-10 border-b-2 px-4 text-[14px] ${tab === k ? "border-accent font-semibold text-ink" : "border-transparent text-muted hover:text-ink"}`}
            >
              {t(label)}
            </button>
          ))}
        </div>

        {tab === "pipeline" && (
          <div className="space-y-6">
            {planOn && (
              <Panel className="px-4 py-3 text-[13px]">
                {plan.isFetching && <span className="text-[#7cd2ff]">{t("Checking the archive and the parameters (may query ASF)…")}</span>}
                {plan.error && <span className="text-bad">{(plan.error as Error).message}</span>}
                {plan.data && !plan.isFetching && (
                  <span className={toRun ? "text-[#7cd2ff]" : "text-good"}>
                    {toRun ? t("{n} phase(s) would run — reasons on the cards below.", { n: toRun }) : t("Everything is up to date: nothing would run.")}
                  </span>
                )}
              </Panel>
            )}
            {p.tracks.map((t) => (
              <div key={t.track_id}>
                <div className="mb-2.5 flex items-center gap-2 text-[13px]">
                  <span className="font-mono text-ink-2">{t.track_id}</span>
                </div>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
                  {PHASES.map((ph) => (
                    <PhaseCard key={ph.name} tr={t} phase={ph} step={plan.data?.steps.find((s) => s.track === t.track_id && s.phase === ph.name)} />
                  ))}
                </div>
              </div>
            ))}
            <LogView lines={lines} title={shownRun ? `${shownRun === liveRun ? t("LIVE LOG") : t("LOG")} · ${t("run {time}", { time: fmt.runTime(shownRun) })}` : t("LOG")} />
            {p.web_run_log.length > 0 && !p.running && p.status === "failed" && (
              <details className="text-[12px] text-muted">
                <summary className="cursor-pointer">{t("Output of the last run started from the web app")}</summary>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-[#070c16] p-3 font-mono text-[11.5px] text-[#a9b8cf]">{p.web_run_log.join("\n")}</pre>
              </details>
            )}
          </div>
        )}

        {tab === "data" && (
          <div className="flex flex-wrap gap-4">
            <Panel className="min-w-0 flex-[999_1_520px] p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-[14px] font-semibold">{t("Perpendicular baselines")}</span>
                <span className="text-[12px] text-muted">
                  {report.data?.report.dates?.find((d) => d.reference)?.date ? `${t("reference {date}", { date: report.data.report.dates.find((d) => d.reference)!.date })} · ` : ""}
                  {t("{n} acquisitions", { n: report.data?.report.dates?.length ?? 0 })}
                </span>
              </div>
              <div className="mt-3">
                {!product && <div className="text-[13px] text-muted">{t("Run the project to get a product first.")}</div>}
                {report.data?.report.dates && <Baselines dates={report.data.report.dates} />}
              </div>
            </Panel>
            <Panel className="min-w-[260px] flex-[1_1_300px] p-4 text-[13px]">
              <div className="font-semibold">{t("Latest product")}</div>
              {product ? (
                <div className="mt-2 space-y-1 text-ink-2">
                  <div className="font-mono text-[12px] break-all text-muted">{product.id}</div>
                  <div>{t("{n} points · {d} dates", { n: fmt.int(product.n_points), d: product.epochs })}</div>
                  <div>{product.first} → {product.last}</div>
                  <div>
                    {t("LOS velocity")} <span className="font-mono">{fmt.vel(product.vel_min)}</span> … <span className="font-mono">{fmt.vel(product.vel_max)}</span> mm/yr
                  </div>
                  {product.issues.map((s) => (
                    <div key={s} className="mt-2 rounded-lg bg-[#2a2110] px-3 py-2 text-[12.5px] text-[#f5d08b]">{ts(s)}</div>
                  ))}
                  <div className="pt-3 font-semibold text-ink">{t("Downloads")}</div>
                  {Object.entries(p.exports)
                    .filter(([pid]) => pid === product.id)
                    .flatMap(([pid, files]) => files.map((f) => (
                      <a key={f} href={api.exportUrl(p.name, pid, f)} className="block truncate text-accent hover:underline">{f}</a>
                    )))}
                  {product.report && <a href={api.fileUrl(p.name, product.id, "report.pdf")} target="_blank" rel="noopener" className="block text-accent hover:underline">report.pdf</a>}
                </div>
              ) : (
                <div className="mt-2 text-muted">{t("No product yet.")}</div>
              )}
              {p.products.length > 1 && (
                <>
                  <div className="pt-4 font-semibold">{t("All versions")}</div>
                  {p.products.map((v) => (
                    <button key={v.id} type="button" onClick={() => showProduct(p.name, v.id, { open: true })} className="mt-1 block w-full truncate text-left text-[12.5px] text-ink-2 hover:text-accent">
                      v{v.version} · {t("{n} pts", { n: fmt.int(v.n_points) })} · {v.first} → {v.last}
                    </button>
                  ))}
                </>
              )}
            </Panel>
          </div>
        )}

        {tab === "runs" && (
          <div className="space-y-4">
            <Panel className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-[13px]">
                <thead>
                  <tr className="text-left text-muted">
                    {["Run", "Phases", "Duration", "Status"].map((h) => (
                      <th key={h} className="px-4 py-2.5 font-medium">{t(h)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {p.runs.map((r) => (
                    <tr key={r.id} onClick={() => setLogRun(r.id)} className={`cursor-pointer border-t border-line hover:bg-[#131f35] ${shownRun === r.id ? "bg-[#131f35]" : ""}`}>
                      <td className="px-4 py-2.5 font-mono">{fmt.runTime(r.id)}</td>
                      <td className="px-4 py-2.5 text-ink-2">
                        {r.phases.filter((x) => x.status !== "skipped").map((x) => x.phase).join(" → ") || "–"}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-ink-2">{fmt.secs(r.seconds) || (r.status === "running" ? t("running") : "–")}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <Chip status={r.status} />
                          {r.error && <span className="truncate text-[12px] text-bad">{ts(r.error)}</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {p.runs.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-4 text-muted">{t("No run yet.")}</td></tr>
                  )}
                </tbody>
              </table>
            </Panel>
            {shownRun && <LogView lines={lines} title={`${t("LOG")} · ${t("run {time}", { time: fmt.runTime(shownRun) })}`} />}
          </div>
        )}

        {tab === "monitoring" && <Monitor name={name} />}

        {tab === "validation" && (
          <>
            <Gnss name={name} />
            <Validation name={name} />
          </>
        )}

        {tab === "settings" && <SettingsForm name={name} running={!!p.running} />}
      </div>
    </div>
  );
}
