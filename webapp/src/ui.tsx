// Small shared pieces: status chips (colour + icon + label, never colour alone), buttons, number formatting.
import { useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { Status } from "./api";
import { t } from "./i18n";

export const STATUS: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  done: { label: "Done", color: "#3ecf8e", bg: "#0f2a1f", icon: "✓" },
  running: { label: "Running", color: "#7cd2ff", bg: "#102033", icon: "●" },
  failed: { label: "Failed", color: "#ff8a8a", bg: "#2a1414", icon: "!" },
  interrupted: { label: "Interrupted", color: "#f5b84b", bg: "#2a2110", icon: "■" },
  idle: { label: "Not finished", color: "#93a4bf", bg: "#161f30", icon: "○" },
  new: { label: "Not run", color: "#93a4bf", bg: "#161f30", icon: "○" },
  invalid: { label: "Invalid config", color: "#ff8a8a", bg: "#2a1414", icon: "!" },
  "up-to-date": { label: "up to date", color: "#3ecf8e", bg: "#0f2a1f", icon: "✓" },
  run: { label: "will run", color: "#7cd2ff", bg: "#102033", icon: "▶" },
  disabled: { label: "off", color: "#6f7f99", bg: "#161f30", icon: "–" },
  blocked: { label: "blocked", color: "#ff8a8a", bg: "#2a1414", icon: "!" },
  skipped: { label: "skipped", color: "#6f7f99", bg: "#161f30", icon: "–" },
  ok: { label: "ok", color: "#3ecf8e", bg: "#0f2a1f", icon: "✓" },
};

export function StatusDot({ status, size = 8 }: { status: Status | string; size?: number }) {
  const s = STATUS[status] ?? STATUS.idle;
  return (
    <span
      title={t(s.label)}
      className={status === "running" ? "animate-pulse" : ""}
      style={{ width: size, height: size, borderRadius: 999, background: s.color, flex: "none", display: "inline-block" }}
    />
  );
}

export function Chip({ status, label }: { status: string; label?: string }) {
  const s = STATUS[status] ?? STATUS.idle;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold whitespace-nowrap"
      style={{ background: s.bg, color: s.color }}
    >
      <span aria-hidden>{s.icon}</span>
      {label ?? t(s.label)}
    </span>
  );
}

const CONF: Record<string, { color: string; bg: string; icon: string }> = {
  high: { color: "#3ecf8e", bg: "#0f2a1f", icon: "✓" },
  medium: { color: "#f5b84b", bg: "#2a2110", icon: "◐" },
  low: { color: "#ff8a8a", bg: "#2a1414", icon: "!" },
};

export function Confidence({ level }: { level?: string | null }) {
  if (!level) return null;
  const c = CONF[level] ?? CONF.medium;
  return (
    <span
      title={t("Confidence level of the product, from its report")}
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold"
      style={{ background: c.bg, color: c.color }}
    >
      <span aria-hidden>{c.icon}</span>
      {level === "high" ? t("high confidence") : level === "medium" ? t("medium confidence") : level === "low" ? t("low confidence") : `${level} confidence`}
    </span>
  );
}

type Variant = "primary" | "ghost" | "danger";

export function Button({
  variant = "ghost",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  const v = {
    primary: "bg-accent-2 hover:bg-[#4b9dff] text-white border-transparent",
    ghost: "bg-[#121d31] hover:bg-raised text-ink border-line-2",
    danger: "bg-[#2a1414] hover:bg-[#3a1a1a] text-[#ffb3b3] border-[#5c2424]",
  }[variant];
  return (
    <button
      type="button"
      className={`inline-flex h-9 items-center gap-2 rounded-lg border px-3.5 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${v} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Panel({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-xl border border-line bg-panel ${className}`}>{children}</div>;
}

export const fmt = {
  int: (v?: number | null) => (v == null ? "–" : v.toLocaleString("en-US")),
  num: (v?: number | null, d = 1) => (v == null ? "–" : v.toFixed(d)),
  vel: (v?: number | null) => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(1)}`),
  secs: (s?: number | null) =>
    s == null ? "" : s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${(s / 60).toFixed(1)} min` : `${(s / 3600).toFixed(1)} h`,
  runTime: (id: string) => id.replace(/^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)$/, "$1-$2-$3 $4:$5"),
  sensor: (s: string) =>
    ({ sentinel1: "Sentinel-1", cosmo_skymed: "COSMO-SkyMed", capella: "Capella", terrasar_x: "TerraSAR-X" })[s] ?? s,
};

/** A boolean kept in the browser (per viewer): folded panels, hidden columns. */
export function usePersisted(key: string, initial: boolean): [boolean, (v: boolean | ((x: boolean) => boolean)) => void] {
  const [v, setV] = useState<boolean>(() => {
    try {
      const s = localStorage.getItem(`geoeyes.ui.${key}`);
      return s == null ? initial : s === "1";
    } catch {
      return initial;
    }
  });
  const set = (x: boolean | ((y: boolean) => boolean)) =>
    setV((old) => {
      const next = typeof x === "function" ? x(old) : x;
      try {
        localStorage.setItem(`geoeyes.ui.${key}`, next ? "1" : "0");
      } catch {
        /* storage unavailable */
      }
      return next;
    });
  return [v, set];
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className={`transition-transform ${open ? "" : "-rotate-90"}`}>
      <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A floating map panel with a title bar that folds it (the state is remembered under `id`). */
export function Fold({ id, title, extra, children, className = "", defaultOpen = true }: { id: string; title: ReactNode; extra?: ReactNode; children: ReactNode; className?: string; defaultOpen?: boolean }) {
  const [open, setOpen] = usePersisted(`fold.${id}`, defaultOpen);
  return (
    <div className={`rounded-xl border border-line-2 bg-panel/95 shadow-xl shadow-black/30 backdrop-blur ${open ? "p-3" : "px-3 py-2"} ${className}`}>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[11px] font-semibold tracking-[1.2px] text-muted hover:text-ink">
          <Chevron open={open} />
          <span className="truncate">{title}</span>
        </button>
        {extra}
      </div>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

/** Button that hides / shows a whole column of map panels. */
export function ColumnToggle({ open, onClick, side, label }: { open: boolean; onClick: () => void; side: "left" | "right"; label: string }) {
  const arrow = (side === "right") === open ? "M6 3l5 5-5 5" : "M10 3 5 8l5 5";
  return (
    <button
      type="button"
      onClick={onClick}
      title={open ? t("Hide the {label} panels", { label }) : t("Show the {label} panels", { label })}
      aria-label={open ? t("Hide the {label} panels", { label }) : t("Show the {label} panels", { label })}
      aria-expanded={open}
      className="flex h-8 items-center gap-1.5 rounded-lg border border-line-2 bg-panel/95 px-2.5 text-[12px] text-muted shadow-lg shadow-black/30 backdrop-blur hover:text-ink"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
        <path d={arrow} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {!open && label}
    </button>
  );
}
