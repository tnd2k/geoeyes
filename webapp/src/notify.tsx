// Notifications: a list kept in the browser (bell in the header), toasts, and desktop notifications (browser
// Notification API, after the viewer allows them). Finished runs and analyses are detected by polling the
// workspace (runs) and /api/activity (hazard, GNSS); analysis warnings are filed here instead of filling panels.
import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type Workspace } from "./api";
import { t, ts } from "./i18n";

export type Level = "info" | "success" | "warning" | "error";

export interface Note {
  id: string;              // stable key: the same event is filed once
  level: Level;
  title: string;
  body?: string;
  href?: string;
  time: number;
  read: boolean;
}

interface NotifyState {
  notes: Note[];
  notify: (n: Omit<Note, "time" | "read">, opts?: { toast?: boolean; desktop?: boolean }) => void;
  markRead: () => void;
  clear: () => void;
}

const Ctx = createContext<NotifyState | null>(null);
const STORE = "geoeyes.notes";
const SEEN = "geoeyes.notes.seen";
const MAX = 150;

function load<T>(key: string, fallback: T): T {
  try {
    const v = JSON.parse(localStorage.getItem(key) ?? "null");
    return v ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* storage unavailable */
  }
}

export const LEVEL: Record<Level, { color: string; bg: string; icon: string }> = {
  info: { color: "#7cd2ff", bg: "#102033", icon: "i" },
  success: { color: "#3ecf8e", bg: "#0f2a1f", icon: "✓" },
  warning: { color: "#f5b84b", bg: "#2a2110", icon: "!" },
  error: { color: "#ff8a8a", bg: "#2a1414", icon: "×" },
};

export function NotifyProvider({ children }: { children: ReactNode }) {
  const [notes, setNotes] = useState<Note[]>(() => load<Note[]>(STORE, []));
  const [toasts, setToasts] = useState<Note[]>([]);
  useEffect(() => save(STORE, notes.slice(0, MAX)), [notes]);

  const ids = useRef(new Set(notes.map((n) => n.id)));
  const notify = useCallback<NotifyState["notify"]>((n, opts = {}) => {
    if (ids.current.has(n.id)) return;                  // the same event is filed once
    ids.current.add(n.id);
    setNotes((ns) => [{ ...n, time: Date.now(), read: false }, ...ns].slice(0, MAX));
    if (opts.toast !== false) {
      const note = { ...n, time: Date.now(), read: false };
      setToasts((x) => [note, ...x].slice(0, 4));
      setTimeout(() => setToasts((x) => x.filter((y) => y.id !== n.id)), n.level === "error" ? 12000 : 7000);
    }
    if (opts.desktop && typeof Notification !== "undefined" && Notification.permission === "granted") {
      try {
        const d = new Notification(`GeoEyes · ${n.title}`, { body: n.body ?? "", tag: n.id });
        d.onclick = () => {
          window.focus();
          if (n.href) location.hash = n.href;
        };
      } catch {
        /* notifications unavailable */
      }
    }
  }, []);

  const value = useMemo<NotifyState>(
    () => ({ notes, notify, markRead: () => setNotes((ns) => ns.map((x) => ({ ...x, read: true }))), clear: () => (ids.current.clear(), setNotes([])) }),
    [notes, notify],
  );
  return (
    <Ctx.Provider value={value}>
      {children}
      <Toasts toasts={toasts} onClose={(id) => setToasts((x) => x.filter((y) => y.id !== id))} />
    </Ctx.Provider>
  );
}

export function useNotify(): NotifyState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useNotify outside NotifyProvider");
  return v;
}

function Toasts({ toasts, onClose }: { toasts: Note[]; onClose: (id: string) => void }) {
  return (
    <div className="pointer-events-none fixed top-[60px] right-3 z-50 flex w-[min(360px,calc(100%-24px))] flex-col gap-2" aria-live="polite">
      {toasts.map((n) => {
        const l = LEVEL[n.level];
        return (
          <div key={n.id} className="pointer-events-auto flex gap-2.5 rounded-xl border border-line-2 bg-panel/95 p-3 shadow-2xl shadow-black/40 backdrop-blur">
            <span className="flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] font-bold" style={{ background: l.bg, color: l.color }}>
              {l.icon}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold">{n.title}</div>
              {n.body && <div className="mt-0.5 text-[12px] leading-snug text-muted">{n.body}</div>}
              {n.href && (
                <a href={n.href} className="mt-1 inline-block text-[12px] text-accent hover:underline" onClick={() => onClose(n.id)}>
                  {t("Open")}
                </a>
              )}
            </div>
            <button type="button" className="self-start text-faint hover:text-ink" onClick={() => onClose(n.id)} aria-label={t("Dismiss")}>
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}

function ago(ms: number): string {
  const m = Math.round((Date.now() - ms) / 60000);
  if (m < 1) return t("just now");
  if (m < 90) return t("{n} min ago", { n: m });
  return t("{n} h ago", { n: Math.round(m / 60) });
}

export function Bell() {
  const { notes, markRead, clear } = useNotify();
  const [open, setOpen] = useState(false);
  const [perm, setPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "denied");
  const box = useRef<HTMLDivElement>(null);
  const unread = notes.filter((n) => !n.read).length;
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    addEventListener("mousedown", close);
    return () => removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => (setOpen((o) => !o), unread && setTimeout(markRead, 1500))}
        aria-label={t("Notifications")}
        aria-expanded={open}
        title={t("Notifications")}
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-raised hover:text-ink"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
          <path d="M8 2a4 4 0 0 0-4 4v2.5L2.8 11h10.4L12 8.5V6a4 4 0 0 0-4-4ZM6.5 13a1.5 1.5 0 0 0 3 0" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-[#ff6b6b] px-1 text-center text-[10px] leading-4 font-bold text-white">{unread > 99 ? "99+" : unread}</span>
        )}
      </button>
      {open && (
        <div className="absolute top-10 right-0 z-50 w-[min(400px,calc(100vw-24px))] rounded-xl border border-line-2 bg-panel shadow-2xl shadow-black/50">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            <span className="text-[11px] font-semibold tracking-[1.2px] text-muted uppercase">{t("Notifications")}</span>
            <button type="button" className="ml-auto text-[12px] text-muted hover:text-ink" onClick={markRead}>
              {t("Mark all as read")}
            </button>
            <button type="button" className="text-[12px] text-muted hover:text-bad" onClick={clear}>
              {t("Clear")}
            </button>
          </div>
          {perm === "default" && (
            <button
              type="button"
              className="w-full border-b border-line px-3 py-2 text-left text-[12px] text-accent hover:bg-raised"
              onClick={() => Notification.requestPermission().then(setPerm)}
            >
              🔔 {t("Enable desktop notifications")}
            </button>
          )}
          {perm === "denied" && typeof Notification !== "undefined" && (
            <div className="border-b border-line px-3 py-2 text-[11.5px] text-faint">{t("Desktop notifications are blocked by the browser")}</div>
          )}
          <div className="max-h-[60vh] overflow-y-auto">
            {notes.length === 0 && <div className="px-3 py-6 text-center text-[12.5px] text-muted">{t("No notification.")}</div>}
            {notes.map((n) => {
              const l = LEVEL[n.level];
              return (
                <div key={n.id} className={`flex gap-2.5 border-b border-line/60 px-3 py-2.5 ${n.read ? "" : "bg-[#0f1a2e]"}`}>
                  <span className="mt-0.5 flex h-4.5 w-4.5 flex-none items-center justify-center rounded-full text-[10px] font-bold" style={{ background: l.bg, color: l.color }}>
                    {l.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] font-semibold">{n.title}</div>
                    {n.body && <div className="mt-0.5 text-[12px] leading-snug text-muted">{n.body}</div>}
                    <div className="mt-1 flex gap-3 text-[11px] text-faint">
                      <span>{ago(n.time)}</span>
                      {n.href && (
                        <a href={n.href} className="text-accent hover:underline" onClick={() => setOpen(false)}>
                          {t("Open")}
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/** Files the warnings of an analysis (once per product and text) instead of listing them in a panel. */
export function useWarnings(scope: string, title: string, warnings: string[] | undefined, href?: string) {
  const { notify } = useNotify();
  useEffect(() => {
    (warnings ?? []).forEach((w) =>
      notify({ id: `${scope}:${w}`, level: "warning", title, body: ts(w), href }, { toast: false }),
    );
  }, [scope, title, warnings, href, notify]);
}

/** Watches runs (workspace) and analyses (/api/activity) and notifies when one ends. */
export function ActivityWatcher({ ws }: { ws: Workspace | undefined }) {
  const { notify } = useNotify();
  const running = useRef<Record<string, boolean> | null>(null);
  const seen = useRef<Record<string, string>>(load(SEEN, {}));
  const act = useQuery({ queryKey: ["activity"], queryFn: api.activity, refetchInterval: 5000 });

  // runs: a project that was running and is not any more
  useEffect(() => {
    if (!ws) return;
    const now: Record<string, boolean> = {};
    Object.values(ws.projects).forEach((p) => (now[p.name] = !!p.running));
    const before = running.current;
    running.current = now;
    if (!before) return;
    Object.values(ws.projects).forEach((p) => {
      if (before[p.name] && !now[p.name]) {
        const ok = p.last_run?.status === "ok" || p.status === "done";
        const href = `#/project/${encodeURIComponent(p.name)}/runs`;
        notify(
          {
            id: `run:${p.name}:${p.last_run?.id ?? Date.now()}`,
            level: ok ? "success" : "error",
            title: t(ok ? "Run finished: {project}" : "Run failed: {project}", { project: p.name }),
            body: p.last_run?.error ? ts(p.last_run.error) : undefined,
            href,
          },
          { desktop: true },
        );
      }
    });
  }, [ws, notify]);

  // analyses: a job state that became done / failed since last seen (kept across reloads)
  useEffect(() => {
    const jobs = act.data?.jobs ?? [];
    let changed = false;
    jobs.forEach((j) => {
      const key = `${j.project}:${j.kind}`;
      const stamp = `${j.started}:${j.state}`;
      if (j.state === "running" || seen.current[key] === stamp) return;
      const first = !(key in seen.current);
      seen.current[key] = stamp;
      changed = true;
      if (first) return;                               // already finished before this browser watched it
      const ok = j.state === "done";
      const what = j.kind === "hazard" ? "Hazard zoning" : "GNSS comparison";
      const href = j.kind === "hazard" ? `#/hazard/${encodeURIComponent(j.project)}/${encodeURIComponent(j.product)}` : `#/project/${encodeURIComponent(j.project)}/validation`;
      notify(
        { id: `${j.kind}:${j.project}:${j.started}`, level: ok ? "success" : "error", title: t(`${what} ${ok ? "finished" : "failed"}: {project}`, { project: j.project }), body: j.product, href },
        { desktop: true },
      );
    });
    if (changed) save(SEEN, seen.current);
  }, [act.data, notify]);
  return null;
}
