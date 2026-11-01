// Displacement time series (uPlot): one point, or the mean of an area with a ±1σ band; optionally a second,
// dashed series (the same with the spatially correlated noise removed) and the monthly rain as bars behind them,
// each bar spanning its month, on its own axis (right).
import { useEffect, useRef } from "react";
import uPlot from "uplot";
import { t } from "../i18n";
import { themeColor } from "../theme";

export function TimeSeries({
  dates,
  values,
  spread,
  extra,
  color = themeColor("accent"),
  height = 200,
  rain,
}: {
  dates: string[];
  values: (number | null)[];
  spread?: (number | null)[];
  extra?: { values: (number | null)[]; label: string; color?: string } | null;
  color?: string;
  height?: number;
  rain?: { months: { month: string; mm: number | null }[]; label: string } | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const x = dates.map((d) => Date.parse(d) / 1000);
    const extraColor = extra?.color ?? themeColor("warn");
    const data: uPlot.AlignedData = [
      x,
      values,
      ...(spread
        ? [
            values.map((v, i) => (v == null || spread[i] == null ? null : v + (spread[i] as number))),
            values.map((v, i) => (v == null || spread[i] == null ? null : v - (spread[i] as number))),
          ]
        : []),
      ...(extra ? [extra.values] : []),
    ];
    const axis = {
      stroke: themeColor("muted"),
      grid: { stroke: themeColor("chip"), width: 1 },
      ticks: { stroke: themeColor("line-2"), width: 1 },
      font: "11px 'Lexend Variable', system-ui, sans-serif",
    };
    // rain: one bar per month, from its first to its last day
    const months = (rain?.months ?? []).filter((m) => m.mm != null);
    const rainMax = Math.max(50, ...months.map((m) => m.mm as number)) * 1.15;
    const monthSpan = (m: string): [number, number] => {
      const [y, mo] = m.split("-").map(Number);
      return [Date.UTC(y, mo - 1, 1) / 1000, Date.UTC(y, mo, 1) / 1000];
    };
    const rainFill = "rgba(91,155,213,0.32)";
    const opts: uPlot.Options = {
      width: el.clientWidth,
      height,
      padding: [8, rain ? 0 : 24, 0, 0], // right: room for the last date label (the rain axis gives it)
      legend: { show: false },
      cursor: { points: { size: 8 }, drag: { x: false, y: false } },
      scales: { x: { time: true }, ...(rain ? { rain: { auto: false, range: [0, rainMax] as [number, number] } } : {}) },
      axes: [
        { ...axis, values: (_u, ticks) => ticks.map((tk) => new Date(tk * 1000).toISOString().slice(0, 7)) },
        { ...axis, size: 48, label: "mm (LOS)", labelSize: 14, labelFont: "11px 'Lexend Variable', sans-serif" },
        ...(rain
          ? [
              {
                ...axis,
                scale: "rain",
                side: 1,
                size: 52,
                grid: { show: false },
                label: t("rain, mm/month"),
                labelSize: 14,
                labelFont: "11px 'Lexend Variable', sans-serif",
                stroke: "#5b9bd5",
              } as uPlot.Axis,
            ]
          : []),
      ],
      series: [
        {},
        {
          stroke: color,
          width: 2,
          points: { show: true, size: 6, fill: color, stroke: themeColor("bg"), width: 1.5 },
          spanGaps: true,
        },
        ...(spread
          ? [
              { stroke: "transparent", points: { show: false } },
              { stroke: "transparent", points: { show: false } },
            ]
          : []),
        ...(extra ? [{ stroke: extraColor, width: 1.6, dash: [5, 4], points: { show: true, size: 4, fill: extraColor }, spanGaps: true }] : []),
      ],
      bands: spread ? [{ series: [2, 3], fill: "rgba(76,194,255,0.14)" }] : undefined,
      hooks: {
        // after the axes and grid, before the series: the bars stay behind the displacement
        drawAxes: [
          (u) => {
            if (!months.length) return;
            const c = u.ctx;
            const { left, top, width, height: h } = u.bbox;
            c.save();
            c.beginPath();
            c.rect(left, top, width, h);
            c.clip();
            c.fillStyle = rainFill;
            const y0 = u.valToPos(0, "rain", true);
            for (const m of months) {
              const [a, b] = monthSpan(m.month);
              const x0 = u.valToPos(a, "x", true);
              const x1 = u.valToPos(b, "x", true);
              const y1 = u.valToPos(m.mm as number, "rain", true);
              const gap = Math.min(2 * devicePixelRatio, (x1 - x0) * 0.12);
              c.fillRect(x0 + gap, y1, Math.max(1, x1 - x0 - 2 * gap), y0 - y1);
            }
            c.restore();
          },
        ],
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            const el = tip.current;
            if (!el) return;
            if (i == null || values[i] == null) {
              el.style.opacity = "0";
              return;
            }
            const s = spread?.[i];
            const e = extra?.values[i];
            const r = rain?.months.find((m) => m.month === dates[i].slice(0, 7))?.mm;
            el.textContent = `${dates[i]}  ${(values[i] as number).toFixed(1)} mm${s != null ? ` ± ${s.toFixed(1)}` : ""}${
              e != null ? ` · ${e.toFixed(1)}` : ""
            }${r != null ? ` · ${t("rain {mm} mm/month", { mm: Math.round(r) })}` : ""}`;
            el.style.opacity = "1";
          },
        ],
      },
    };
    const plot = new uPlot(opts, data, el);
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [dates, values, spread, extra, color, height, rain]);

  return (
    <div className="relative">
      <div ref={box} className="w-full" />
      <div
        ref={tip}
        className="pointer-events-none absolute top-1 right-2 rounded bg-bg/90 px-2 py-0.5 font-mono text-[11px] text-ink opacity-0 transition-opacity"
      />
      {(extra || rain) && (
        <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4" style={{ background: color }} /> {t("displacement")}
          </span>
          {extra && (
            <span className="flex items-center gap-1">
              <span className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: extra.color ?? "var(--c-warn)" }} /> {extra.label}
            </span>
          )}
          {rain && (
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-3 rounded-sm" style={{ background: "rgba(91,155,213,0.55)" }} /> {rain.label}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
