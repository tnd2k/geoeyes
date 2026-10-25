// Displacement time series (uPlot): one point, or the mean of an area with a ±1σ band; optionally a second,
// dashed series (the same with the spatially correlated noise removed).
import { useEffect, useRef } from "react";
import uPlot from "uplot";

export function TimeSeries({
  dates,
  values,
  spread,
  extra,
  color = "#4cc2ff",
  height = 200,
}: {
  dates: string[];
  values: (number | null)[];
  spread?: (number | null)[];
  extra?: { values: (number | null)[]; label: string; color?: string } | null;
  color?: string;
  height?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const x = dates.map((d) => Date.parse(d) / 1000);
    const extraColor = extra?.color ?? "#f5b84b";
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
      stroke: "#93a4bf",
      grid: { stroke: "#1a2740", width: 1 },
      ticks: { stroke: "#22324d", width: 1 },
      font: "11px Inter, system-ui, sans-serif",
    };
    const opts: uPlot.Options = {
      width: el.clientWidth,
      height,
      padding: [8, 8, 0, 0],
      legend: { show: false },
      cursor: { points: { size: 8 }, drag: { x: false, y: false } },
      scales: { x: { time: true } },
      axes: [
        { ...axis, values: (_u, ticks) => ticks.map((t) => new Date(t * 1000).toISOString().slice(0, 7)) },
        { ...axis, size: 48, label: "mm (LOS)", labelSize: 14, labelFont: "11px Inter, sans-serif" },
      ],
      series: [
        {},
        {
          stroke: color,
          width: 2,
          points: { show: true, size: 6, fill: color, stroke: "#0b1220", width: 1.5 },
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
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            const t = tip.current;
            if (!t) return;
            if (i == null || values[i] == null) {
              t.style.opacity = "0";
              return;
            }
            const s = spread?.[i];
            const e = extra?.values[i];
            t.textContent = `${dates[i]}  ${(values[i] as number).toFixed(1)} mm${s != null ? ` ± ${s.toFixed(1)}` : ""}${
              e != null ? ` · ${e.toFixed(1)}` : ""
            }`;
            t.style.opacity = "1";
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
  }, [dates, values, spread, extra, color, height]);

  return (
    <div className="relative">
      <div ref={box} className="w-full" />
      <div
        ref={tip}
        className="pointer-events-none absolute top-1 right-2 rounded bg-[#0b1220]/90 px-2 py-0.5 font-mono text-[11px] text-ink opacity-0 transition-opacity"
      />
      {extra && (
        <div className="mt-1 flex gap-3 text-[11px] text-muted">
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4" style={{ background: color }} /> displacement
          </span>
          <span className="flex items-center gap-1">
            <span className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: extra.color ?? "#f5b84b" }} /> {extra.label}
          </span>
        </div>
      )}
    </div>
  );
}
