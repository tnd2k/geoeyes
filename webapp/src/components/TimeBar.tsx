// Time animation of the map (pages/Explorer.tsx): the cumulative displacement of every point at one date, played
// through the dates; colours: Pretty Breaks over the full range of all dates (as the velocity classes).
import type { DispMeta } from "../api";
import { t } from "../i18n";

export function TimeBar({
  meta,
  frame,
  onFrame,
  playing,
  onPlay,
  speed,
  onSpeed,
  loading,
  onClose,
}: {
  meta: DispMeta;
  frame: number;
  onFrame: (k: number) => void;
  playing: boolean;
  onPlay: (p: boolean) => void;
  speed: number;
  onSpeed: (s: number) => void;
  loading: boolean;
  onClose: () => void;
}) {
  const n = meta.dates.length;
  return (
    <div className="w-[min(560px,calc(100vw-420px))] max-md:w-[calc(100vw-24px)] rounded-xl border border-line-2 bg-panel/95 px-3 py-2 shadow-xl shadow-black/30 backdrop-blur">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPlay(!playing)}
          className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-accent-2 text-white hover:brightness-110"
          aria-label={playing ? t("Pause") : t("Play")}
        >
          {playing ? (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><path d="M3 2h2v8H3zM7 2h2v8H7z" fill="currentColor" /></svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><path d="M3 1.5v9l7.5-4.5z" fill="currentColor" /></svg>
          )}
        </button>
        <input
          type="range"
          min={0}
          max={n - 1}
          value={frame}
          onChange={(e) => (onPlay(false), onFrame(Number(e.target.value)))}
          className="min-w-0 flex-1 accent-[var(--color-accent)]"
          aria-label={t("Date")}
        />
        <span className="w-[86px] flex-none text-right font-mono text-[12.5px] text-ink">{meta.dates[frame]}</span>
        <select value={speed} onChange={(e) => onSpeed(Number(e.target.value))} className="h-7 flex-none rounded border border-line-2 bg-sunken px-1 font-mono text-[11.5px] text-ink" aria-label={t("Speed")}>
          {[0.5, 1, 2, 4].map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
        <button type="button" onClick={onClose} className="flex-none px-1 text-faint hover:text-ink" aria-label={t("Close")}>
          ×
        </button>
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted">
        <span className="flex-none">{t("Displacement since {d}", { d: meta.dates[0] })}</span>
        <div className="flex h-2.5 min-w-0 flex-1 overflow-hidden rounded-sm">
          {meta.classes.map((c) => (
            <span key={c.hi} className="h-full flex-1" style={{ background: `rgb(${c.color.join(",")})` }} title={`${c.lo.toFixed(0)} … ${c.hi.toFixed(0)} mm`} />
          ))}
        </div>
        <span className="flex-none font-mono text-ink-2">
          {meta.min.toFixed(0)} … {meta.max.toFixed(0)} mm
        </span>
        {loading && <span className="flex-none text-accent-ink">{t("loading…")}</span>}
      </div>
      <div className="mt-0.5 text-[10.5px] text-faint">{t("Line of sight, relative to the reference area: + toward the satellite, − away (e.g. subsidence)")}</div>
    </div>
  );
}
