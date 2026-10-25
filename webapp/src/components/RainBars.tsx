// Monthly rainfall bars (CHIRPS) on the same time span as the displacement chart above it: a separate chart, one
// axis each, so motion and rain are read side by side, not on a shared scale.
import { useEffect, useRef } from "react";
import uPlot from "uplot";

export function RainBars({ months, from, to, height = 74 }: { months: { month: string; mm: number | null }[]; from: string; to: string; height?: number }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const x = months.map((m) => Date.parse(`${m.month}-15`) / 1000);
    const y = months.map((m) => m.mm);
    const bars = uPlot.paths.bars!({ size: [0.75, 18] });
    const axis = { stroke: "#93a4bf", grid: { stroke: "#1a2740", width: 1 }, ticks: { stroke: "#22324d", width: 1 }, font: "10px Inter, system-ui, sans-serif" };
    const plot = new uPlot(
      {
        width: el.clientWidth,
        height,
        padding: [4, 8, 0, 0],
        legend: { show: false },
        cursor: { drag: { x: false, y: false }, points: { show: false } },
        scales: { x: { time: true, range: [Date.parse(from) / 1000, Date.parse(to) / 1000] }, y: { range: (_u, _min, max) => [0, Math.max(50, max)] } },
        axes: [
          { ...axis, show: false },
          { ...axis, size: 48, label: "mm/month", labelSize: 12, labelFont: "10px Inter, sans-serif", values: (_u, t) => t.map((v) => `${v}`) },
        ],
        series: [{}, { stroke: "#5b9bd5", fill: "rgba(91,155,213,0.55)", width: 0, paths: bars, points: { show: false } }],
      },
      [x, y],
      el,
    );
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [months, from, to, height]);
  return <div ref={box} className="w-full" />;
}
