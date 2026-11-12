// Project: pipeline status and plan (what would run and why), Run / Stop, live log, data, runs, settings.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type LogLine, type PlanStep, type ProjectDetail, type ReportDate, type Track } from "../api";
import { Monitor } from "../components/Monitor";
import { SettingsForm } from "../components/SettingsForm";
import { Atmosphere } from "../components/Atmosphere";
import { CorridorEditor } from "../components/CorridorEditor";
import { Gnss } from "../components/Gnss";
import { StackQc } from "../components/StackQc";
import { Validation } from "../components/Validation";
import { t, ts } from "../i18n";
import { openStream } from "../live";
import { useApp } from "../state";
import { ask, Button, Chip, Confidence, fmt, PageSkeleton, Panel } from "../ui";

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
  ["stack", "Stack"],
  ["runs", "Runs"],
  ["monitoring", "Monitoring"],
  ["validation", "Validation"],
  ["atmosphere", "Atmosphere"],
  ["area", "Processing area"],
  ["settings", "Settings"],
] as const;

/** The project's live state: its detail and ps checkpoints (into the query cache) and the log of `runId`, pushed by
 *  the server's project stream; `live`: the run is going (its log grows). While the stream is down (an older server,
 *  a hidden tab), `onUp(false)` and the log is polled as before. */
function useProjectLive(project: string, runId: string | null | undefined, live: boolean, onUp: (up: boolean) => void) {
  const qc = useQueryClient();
  const [lines, setLines] = useState<LogLine[]>([]);
  const next = useRef(0);
  useEffect(() => {
    setLines([]);
    next.current = 0;
    let stop = false;
    let up = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stream: ReturnType<typeof openStream> | null = null;
    // a batch continues the cursor or is dropped (a poll and the stream crossed): true when taken
    const add = (r: { lines: LogLine[]; next: number }, after: number) => {
      if (stop || after !== next.current) return false;
      next.current = r.next;
      if (r.lines.length) setLines((l) => [...l, ...r.lines].slice(-1500));
      return true;
    };
    const pull = async () => {
      clearTimeout(timer);
      if (stop || up || !runId || document.hidden) return; // the stream carries the log; a hidden tab waits
      const after = next.current;
      try {
        add(await api.log(project, runId, after), after);
      } catch {
        /* run folder not there yet */
      }
      if (!stop && !up && live) timer = setTimeout(pull, 2000);
    };
    const onShow = () => {
      if (!document.hidden && !up) pull();
    };
    document.addEventListener("visibilitychange", onShow);
    (async () => {
      await pull(); // the log so far, then the stream from its end
      if (stop) return;
      stream = openStream(
        () => `/api/projects/${encodeURIComponent(project)}/events${runId && live ? `?run=${encodeURIComponent(runId)}&after=${next.current}` : ""}`,
        {
          project: (d: never) => qc.setQueryData(["project", project], d),
          "ps-steps": (d: never) => qc.setQueryData(["ps-steps", project], d),
          log: (d: { lines: LogLine[]; next: number; after: number }) => {
            if (!add(d, d.after)) stream?.reopen(); // out of step: reconnect from our cursor
          },
        },
        (u) => {
          up = u;
          onUp(u);
          if (!u && live) timer = setTimeout(pull, 2000);
        },
      );
    })();
    return () => {
      stop = true;
      clearTimeout(timer);
      stream?.close();
      document.removeEventListener("visibilitychange", onShow);
      onUp(false);
    };
  }, [project, runId, live, qc, onUp]);
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
    <div className="rounded-xl border border-line bg-deep">
      <div className="border-b border-line px-4 py-2 text-[12px] font-semibold text-muted">{title}</div>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="h-72 overflow-auto px-4 py-2 font-mono text-[11.5px] leading-[1.65] text-ink-3"
      >
        {lines.length === 0 && <div className="text-faint">{t("No log lines.")}</div>}
        {lines.map((l, i) => (
          <div
            key={i}
            className={`whitespace-pre-wrap ${l.level === "ERROR" || l.level === "CRITICAL" ? "text-bad" : l.level === "WARNING" ? "text-warn" : l.event === "phase_end" ? "text-good" : ""}`}
          >
            <span className="text-faint">{new Date(l.ts).toLocaleTimeString("en-GB")}</span>{" "}
            {l.phase && <span className="text-muted">{l.phase.padEnd(13)}</span>} {l.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

/** One wave crest path over two periods of 200 units (the layer slides by one period and loops). */
function wavePath(amp: number, phase: number) {
  let d = `M0 ${20 + amp * Math.sin(phase)}`;
  for (let x = 5; x <= 400; x += 5) d += ` L${x} ${(20 + amp * Math.sin((x / 200) * 2 * Math.PI + phase)).toFixed(2)}`;
  return `${d} L400 60 L0 60 Z`;
}

/** Water filling the card of a running phase: its level follows the phase's progress events when it sends any
 * (else a low level), two wave layers drift at different speeds. */
function WaterWave({ progress }: { progress: number | null }) {
  const level = progress == null ? 0.22 : 0.12 + 0.8 * Math.min(1, Math.max(0, progress));
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden rounded-xl">
      <div className="absolute inset-x-0 bottom-0 transition-[height] duration-1000 ease-out" style={{ height: `${level * 100}%` }}>
        <div className="wave-bob absolute inset-x-0 -top-5 h-7">
          <svg viewBox="0 0 200 60" preserveAspectRatio="none" className="wave-layer absolute top-0 left-0 h-full w-[200%]" style={{ animationDuration: "7s" }}>
            <path d={wavePath(5, 1.3)} fill="var(--c-accent-2)" fillOpacity="0.16" />
          </svg>
          <svg viewBox="0 0 200 60" preserveAspectRatio="none" className="wave-layer absolute top-1 left-0 h-full w-[200%]" style={{ animationDuration: "4.5s", animationDirection: "reverse" }}>
            <path d={wavePath(4, 0)} fill="var(--c-accent-2)" fillOpacity="0.22" />
          </svg>
        </div>
        <div className="absolute inset-x-0 top-2 bottom-0 bg-gradient-to-b from-accent-2/20 to-accent-line/30" />
      </div>
    </div>
  );
}

type PsRange = { from?: number; to?: number };

/** The 8 steps of the ps engine in its card: the saved checkpoints (a run resumes after the last one), the step
 * running, and the range of the next run (compute again from / stop after). */
function PsSteps({ steps, running, done, range, onRange }: { steps: { step: number; name: string; saved: string | null }[]; running: number | null; done?: string; range: PsRange; onRange: (r: PsRange) => void }) {
  // step 8 (velocity, SCN, outputs) has no checkpoint: its output is the run itself, done when the phase is
  steps = steps.map((s) => (s.step === 8 && !s.saved && done ? { ...s, saved: done } : s));
  const sel = "h-6 w-full min-w-0 truncate rounded border border-line-2 bg-sunken px-1 text-[11px] text-ink-2";
  return (
    <div className="space-y-1.5">
      <div className="flex gap-0.5">
        {steps.map((s) => {
          const redo = range.from != null && s.step >= range.from;
          const cut = range.to != null && s.step > range.to;
          return (
            <span
              key={s.step}
              title={`${s.step}. ${t(s.name)} — ${s.saved ? t("saved {when}", { when: s.saved }) : t("not saved")}${redo ? ` · ${t("computed again")}` : ""}${cut ? ` · ${t("not run (stops before)")}` : ""}`}
              className={`flex h-5 flex-1 items-center justify-center rounded font-mono text-[10.5px] ${
                running === s.step ? "animate-pulse bg-accent text-white" : s.saved && !redo ? "bg-good-bg text-good" : "bg-idle-bg text-faint"
              } ${cut ? "opacity-40" : ""}`}
            >
              {s.step}
            </span>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-1.5 text-[10.5px] text-muted">
        <label className="min-w-0">
          <span className="mb-0.5 block">{t("from step")}</span>
          <select className={sel} value={range.from ?? ""} onChange={(e) => onRange({ ...range, from: e.target.value ? Number(e.target.value) : undefined })}>
            <option value="">{t("resume")}</option>
            {steps.map((s) => (
              <option key={s.step} value={s.step}>
                {s.step}. {t(s.name)}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className="mb-0.5 block">{t("stop after")}</span>
          <select className={sel} value={range.to ?? ""} onChange={(e) => onRange({ ...range, to: e.target.value ? Number(e.target.value) : undefined })}>
            <option value="">{t("the end")}</option>
            {steps.slice(0, -1).map((s) => (
              <option key={s.step} value={s.step}>
                {s.step}. {t(s.name)}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

function PhaseCard({ tr, phase, step, progress, onMenu, skipped, onSkip, children }: { tr: Track; phase: (typeof PHASES)[number]; step?: PlanStep; progress?: number | null; onMenu?: (x: number, y: number) => void; skipped?: boolean; onSkip?: (skip: boolean) => void; children?: ReactNode }) {
  const rec = tr.phases[phase.name];
  const status = rec?.status ?? (step?.action === "disabled" ? "disabled" : "new");
  const border = { running: "var(--c-accent-line)", failed: "var(--c-bad-line)", interrupted: "var(--c-warn-line)" }[status] ?? "var(--c-line)";
  const running = status === "running";
  return (
    <div
      className={`relative flex min-h-[138px] flex-col gap-2 overflow-hidden rounded-xl border bg-panel p-3.5 [&>*:not([aria-hidden])]:relative ${skipped && !running ? "border-dashed opacity-60" : ""}`}
      style={{ borderColor: border }}
      onContextMenu={(e) => {
        if (!onMenu) return;
        e.preventDefault();
        onMenu(e.clientX, e.clientY);
      }}
      title={onMenu ? t("Right-click: run this step") : undefined}
    >
      {running && <WaterWave progress={progress ?? null} />}
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13.5px] font-semibold">{t(phase.label)}</span>
        <span className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-muted">
            {running && progress != null ? `${Math.round(100 * progress)} %` : fmt.secs(rec?.seconds)}
          </span>
          {onSkip && step?.action !== "disabled" && (
            <button
              type="button"
              role="switch"
              aria-checked={!skipped}
              aria-label={skipped ? t("Skipped in the next run: click to include") : t("Included in the next run: click to skip")}
              title={skipped ? t("Skipped in the next run: click to include") : t("Included in the next run: click to skip")}
              onClick={() => onSkip(!skipped)}
              className={`relative h-[18px] w-8 shrink-0 rounded-full transition-colors ${skipped ? "bg-line-3" : "bg-accent"}`}
            >
              <span className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-[left] ${skipped ? "left-[2px]" : "left-[16px]"}`} />
            </button>
          )}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Chip status={status === "done" ? "ok" : status} label={status === "done" ? t("done") : status === "new" ? t("not run") : undefined} />
        {skipped && !running ? <Chip status="skipped" /> : step && step.action !== "disabled" && <Chip status={step.action} />}
      </div>
      <div className="text-[12px] leading-snug text-ink-3">
        {rec?.error ? <span className={status === "paused" ? "text-warn" : "text-bad"}>{ts(rec.error)}</span> : step?.reason && step.action !== "up-to-date" ? ts(step.reason) : t(phase.what)}
      </div>
      {children}
      {rec?.updated && <div className="mt-auto text-[11px] text-faint">{new Date(rec.updated).toLocaleString("en-GB")}</div>}
    </div>
  );
}

/** Right-click menu of a phase card: run that phase alone, or from it to the end, on its track (forced: it runs even
 * when up to date). */
function PhaseMenu({ at, track, label, busy, onRun, onClose }: { at: { x: number; y: number }; track: string; label: string; busy: boolean; onRun: (mode: "only" | "from") => void; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) onClose();
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    window.addEventListener("scroll", onClose, true);
    window.addEventListener("resize", onClose);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
      window.removeEventListener("scroll", onClose, true);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose]);
  const x = Math.min(at.x, window.innerWidth - 260);
  const y = Math.min(at.y, window.innerHeight - 130);
  const item = "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-ink hover:bg-raised disabled:text-faint disabled:hover:bg-transparent";
  return (
    <div ref={box} role="menu" className="fixed z-50 w-[250px] rounded-lg border border-line-2 bg-panel p-1 shadow-lg" style={{ left: x, top: y }}>
      <div className="px-3 pt-1.5 pb-1 text-[11px] tracking-[0.6px] text-muted uppercase">
        {track} · {t(label)}
      </div>
      <button role="menuitem" type="button" className={item} disabled={busy} onClick={() => onRun("only")}>
        ▶ {t("Run this step")}
      </button>
      <button role="menuitem" type="button" className={item} disabled={busy} onClick={() => onRun("from")}>
        ⏩ {t("Run from this step to the end")}
      </button>
      {busy && <div className="px-3 pb-1.5 text-[11.5px] text-warn">{t("A run is in progress")}</div>}
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
            <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke={v === 0 ? "var(--c-line-3)" : "var(--c-chip)"} />
            <text x={L - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--c-muted)" fontFamily="'JetBrains Mono Variable', monospace">
              {Math.round(v)} m
            </text>
          </g>
        ))}
        {years
          .filter((y) => y >= t0 && y <= t1)
          .map((y) => (
            <text key={y} x={X(y)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--c-muted)" fontFamily="'JetBrains Mono Variable', monospace">
              {new Date(y).getUTCFullYear()}
            </text>
          ))}
        <text x={L} y={H - 8} fontSize="11" fill="var(--c-faint)" fontFamily="'JetBrains Mono Variable', monospace">{pts[0].date}</text>
        <text x={W - R} y={H - 8} textAnchor="end" fontSize="11" fill="var(--c-faint)" fontFamily="'JetBrains Mono Variable', monospace">{pts[pts.length - 1].date}</text>
        {ref >= 0 &&
          pts.map((d, i) => (i === ref ? null : <line key={d.date} x1={X(tm[ref])} y1={Y(b[ref])} x2={X(tm[i])} y2={Y(b[i])} stroke="var(--c-line-2)" />))}
        {pts.map((d, i) => (
          <circle
            key={d.date}
            cx={X(tm[i])}
            cy={Y(b[i])}
            r={i === hover ? 7 : 5}
            fill={d.used === false ? "var(--c-faint)" : "var(--c-accent-2)"}
            stroke="var(--c-bg)"
            strokeWidth="1.5"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        {ref >= 0 && <circle cx={X(tm[ref])} cy={Y(b[ref])} r="9" fill="none" stroke="#fff" strokeWidth="2" />}
      </svg>
      {hover != null && (
        <div className="pointer-events-none absolute top-1 right-2 rounded bg-bg px-2 py-1 font-mono text-[11.5px]">
          {pts[hover].date} · {b[hover].toFixed(0)} m{pts[hover].reference ? ` · ${t("reference")}` : ""}
        </div>
      )}
    </div>
  );
}

export function Project({ name, tab = "pipeline" }: { name: string; tab?: string }) {
  const { go, showProduct } = useApp();
  const qc = useQueryClient();
  // from the click until the server sees the run (it first searches the data servers for new scenes)
  const [starting, setStarting] = useState(false);
  // the project stream is up: it pushes the detail, the checkpoints and the log (no polls then)
  const [streamUp, setStreamUp] = useState(false);
  const q = useQuery({
    queryKey: ["project", name],
    queryFn: () => api.project(name),
    refetchInterval: (query) => (streamUp ? false : (query.state.data as ProjectDetail | undefined)?.running || starting ? 2000 : 15000),
  });
  // phases switched off for the runs started here ("track/phase"), remembered per project in this browser
  const skipKey = `geoeyes.skip.${name}`;
  const [skip, setSkipState] = useState<string[]>([]);
  useEffect(() => {
    try {
      setSkipState(JSON.parse(localStorage.getItem(skipKey) ?? "[]"));
    } catch {
      setSkipState([]);
    }
  }, [skipKey]);
  const setSkip = (k: string, on: boolean) =>
    setSkipState((cur) => {
      const next = on ? [...new Set([...cur, k])] : cur.filter((x) => x !== k);
      try {
        localStorage.setItem(skipKey, JSON.stringify(next));
      } catch {
        /* private mode: kept for this page only */
      }
      return next;
    });
  // the steps of the ps engine for the next run (compute again from / stop after), remembered like the skips
  const rangeKey = `geoeyes.psrange.${name}`;
  const [psRange, setPsRangeState] = useState<PsRange>({});
  useEffect(() => {
    try {
      setPsRangeState(JSON.parse(localStorage.getItem(rangeKey) ?? "{}"));
    } catch {
      setPsRangeState({});
    }
  }, [rangeKey]);
  const setPsRange = (r: PsRange) => {
    setPsRangeState(r);
    try {
      localStorage.setItem(rangeKey, JSON.stringify(r));
    } catch {
      /* private mode */
    }
  };
  const runBody = () => ({ ...(skip.length ? { skip } : {}), ...(psRange.from ? { ps_from: psRange.from } : {}), ...(psRange.to ? { ps_to: psRange.to } : {}) });
  const [planOn, setPlanOn] = useState(false);
  const plan = useQuery({ queryKey: ["plan", name, skip.join()], queryFn: () => api.plan(name, [], skip), enabled: planOn, staleTime: 30_000 });
  const [logRun, setLogRun] = useState<string | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; track: string; phase: string; label: string } | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
  const run = useMutation({
    mutationFn: (body: Parameters<typeof api.run>[1] = {}) => (setStarting(true), api.run(name, body)),
    onSuccess: () => {
      setPlanOn(false);
      qc.invalidateQueries({ queryKey: ["project", name] });
      qc.invalidateQueries({ queryKey: ["workspace"] });
    },
    onError: () => setStarting(false),
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
  const psSteps = useQuery({ queryKey: ["ps-steps", name], queryFn: () => api.psSteps(name), refetchInterval: streamUp ? false : p?.running ? 5000 : 30_000 });
  useEffect(() => {
    if (!starting) return;
    if (p?.running) return setStarting(false);
    const timer = setTimeout(() => setStarting(false), 30_000);         // the process died at once: stop waiting
    return () => clearTimeout(timer);
  }, [starting, p?.running]);
  const liveRun = p?.running?.run_id ?? null;
  const shownRun = logRun ?? liveRun ?? p?.runs[0]?.id ?? null;
  const lines = useProjectLive(name, shownRun, !!liveRun && shownRun === liveRun, setStreamUp);
  // latest progress (done / total) of each phase of the live run: the water level of its card
  const progress: Record<string, number> = {};
  if (liveRun && shownRun === liveRun)
    for (const l of lines)
      if (l.event === "progress" && l.total && l.phase && l.track) progress[`${l.track}/${l.phase}`] = (l.done ?? 0) / l.total;
  const product = p?.tracks.find((t) => t.product)?.product;
  const report = useQuery({
    queryKey: ["report", name, product?.id],
    queryFn: () => api.product(name, product!.id),
    enabled: !!product && tab === "data",
  });

  if (q.error) return <div className="p-8 text-bad">{(q.error as Error).message}</div>;
  if (!p) return <PageSkeleton tiles={0} panels={3} />;
  const toRun = plan.data?.steps.filter((s) => s.action === "run").length ?? null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1280px] px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-mono text-[22px] font-medium">{p.name}</h1>
              <Chip
                status={starting && !p.running ? "running" : p.status}
                label={
                  starting && !p.running
                    ? t("Starting…")
                    : p.running?.stage === "planning"
                      ? `${t("Running")} · ${t("checking the inputs")}`
                      : p.status === "running"
                        ? `${t("Running")}${p.tracks.flatMap((t) => Object.entries(t.phases)).find(([, r]) => r.status === "running")?.[0] ? ` · ${p.tracks.flatMap((t) => Object.entries(t.phases)).find(([, r]) => r.status === "running")![0]}` : ""}`
                        : undefined
                }
              />
              {p.running && p.net && p.net.bytes > 0 && (
                <span
                  className="rounded-full bg-chip px-2.5 py-0.5 font-mono text-[12px] text-ink-2"
                  title={t("Download rate over the last seconds; {total} downloaded in this run", { total: fmt.bytes(p.net.bytes) })}
                >
                  ↓ {p.net.age_s < 15 ? `${fmt.bytes(p.net.rate_bps)}/s` : t("waiting")} · {fmt.bytes(p.net.bytes)}
                </span>
              )}
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
              <Button variant="danger" onClick={async () => (await ask(t("Stop the run of {name}?", { name: p.name }), { ok: t("Stop run"), danger: true })) && stop.mutate()} disabled={stop.isPending}>
                {t("Stop run")}
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={() => run.mutate(runBody())}
                disabled={run.isPending || starting}
                title={skip.length ? t("Skipped: {list}", { list: skip.join(", ") }) : undefined}
              >
                {run.isPending || starting ? t("Starting…") : skip.length ? `▶ ${t("Run")} (${t("{n} skipped", { n: skip.length })})` : `▶ ${t("Run")}`}
              </Button>
            )}
          </div>
        </div>
        {(run.error || stop.error) && <div className="mt-3 rounded-lg bg-bad-bg px-3 py-2 text-[13px] text-bad">{((run.error || stop.error) as Error).message}</div>}
        {menu && (
          <PhaseMenu
            at={menu}
            track={menu.track}
            label={menu.label}
            busy={!!p.running || starting || run.isPending}
            onClose={closeMenu}
            onRun={(mode) => {
              const m = menu;
              setMenu(null);
              run.mutate(mode === "only" ? { tracks: [m.track], only: m.phase, force: [m.phase] } : { tracks: [m.track], from: m.phase, force: [m.phase] });
            }}
          />
        )}

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
                {plan.isFetching && <span className="text-accent-ink">{t("Checking the archive and the parameters (may query ASF)…")}</span>}
                {plan.error && <span className="text-bad">{(plan.error as Error).message}</span>}
                {plan.data && !plan.isFetching && (
                  <span className={toRun ? "text-accent-ink" : "text-good"}>
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
                    <PhaseCard
                      key={ph.name}
                      tr={t}
                      phase={ph}
                      step={plan.data?.steps.find((s) => s.track === t.track_id && s.phase === ph.name)}
                      progress={progress[`${t.track_id}/${ph.name}`] ?? null}
                      onMenu={(x, y) => setMenu({ x, y, track: t.track_id, phase: ph.name, label: ph.label })}
                      skipped={skip.includes(`${t.track_id}/${ph.name}`)}
                      onSkip={(on) => setSkip(`${t.track_id}/${ph.name}`, on)}
                    >
                      {ph.name === "ps" && p.method !== "ps_lite" && psSteps.data?.[t.track_id] && (
                        <PsSteps
                          steps={psSteps.data[t.track_id]}
                          running={t.phases.ps?.status === "running" ? Math.min(8, Math.max(1, Math.round((progress[`${t.track_id}/ps`] ?? 0) * 9))) : null}
                          done={t.phases.ps?.status === "done" ? new Date(t.phases.ps.updated ?? "").toLocaleString("en-GB") : undefined}
                          range={psRange}
                          onRange={setPsRange}
                        />
                      )}
                    </PhaseCard>
                  ))}
                </div>
              </div>
            ))}
            <LogView lines={lines} title={shownRun ? `${shownRun === liveRun ? t("LIVE LOG") : t("LOG")} · ${t("run {time}", { time: fmt.runTime(shownRun) })}` : t("LOG")} />
            {p.web_run_log.length > 0 && !p.running && p.status === "failed" && (
              <details className="text-[12px] text-muted">
                <summary className="cursor-pointer">{t("Output of the last run started from the web app")}</summary>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-deep p-3 font-mono text-[11.5px] text-ink-3">{p.web_run_log.join("\n")}</pre>
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
                    <div key={s} className="mt-2 rounded-lg bg-warn-bg px-3 py-2 text-[12.5px] text-warn-ink">{ts(s)}</div>
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
                    <tr key={r.id} onClick={() => setLogRun(r.id)} className={`cursor-pointer border-t border-line hover:bg-panel-3 ${shownRun === r.id ? "bg-panel-3" : ""}`}>
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

        {tab === "stack" && <StackQc name={name} />}
        {tab === "monitoring" && <Monitor name={name} />}

        {tab === "validation" && (
          <>
            <Gnss name={name} />
            <Validation name={name} />
          </>
        )}

        {tab === "atmosphere" && <Atmosphere name={name} />}
        {tab === "area" && <CorridorEditor name={name} running={!!p.running} />}
        {tab === "settings" && <SettingsForm name={name} running={!!p.running} />}
      </div>
    </div>
  );
}
