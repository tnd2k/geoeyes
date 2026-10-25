// Small shared pieces: status chips (colour + icon + label, never colour alone), buttons, number formatting.
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Status } from "./api";

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
      title={s.label}
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
      {label ?? s.label}
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
      title="Confidence level of the product, from its report"
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold"
      style={{ background: c.bg, color: c.color }}
    >
      <span aria-hidden>{c.icon}</span>
      {level} confidence
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
