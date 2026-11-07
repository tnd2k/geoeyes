// What the maps share with the machine-learning page: the diverging colour ramp and the forecast chart of a cell
// (here, so that the thematic layers of every map do not load the whole page).
import { useEffect, useRef } from "react";
import uPlot from "uplot";
import { type ForecastCell } from "../api";
import { t } from "../i18n";
import { themeColor } from "../theme";

type RGB = [number, number, number];

export const DIVERGING: RGB[] = [[178, 24, 43], [214, 96, 77], [244, 165, 130], [127, 139, 160], [146, 197, 222], [67, 147, 195], [33, 102, 172]];

export function ramp(colors: RGB[], x: number): RGB {
  const v = Math.min(1, Math.max(0, x)) * (colors.length - 1);
  const i = Math.min(colors.length - 2, Math.floor(v));
  const f = v - i;
  return [0, 1, 2].map((k) => Math.round(colors[i][k] * (1 - f) + colors[i + 1][k] * f)) as RGB;
}

export function ForecastChart({ c }: { c: ForecastCell }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const dates = [...c.dates, ...c.forecast.map((f) => f.date)];
    const x = dates.map((d) => Date.parse(d) / 1000);
    const nH = c.dates.length;
    const pad = (arr: (number | null)[], before: number) => [...Array(before).fill(null), ...arr];
    const last = c.series_mm[nH - 1];
    const fcm = [last, ...c.forecast.map((f) => f.change_mm)];
    const lo80 = [last, ...c.forecast.map((f) => f.lo80)];
    const hi80 = [last, ...c.forecast.map((f) => f.hi80)];
    const lo95 = [last, ...c.forecast.map((f) => f.lo95)];
    const hi95 = [last, ...c.forecast.map((f) => f.hi95)];
    const data = [
      x,
      [...c.series_mm, ...c.forecast.map(() => null)],
      pad(fcm, nH - 1),
      pad(hi95, nH - 1),
      pad(lo95, nH - 1),
      pad(hi80, nH - 1),
      pad(lo80, nH - 1),
    ] as uPlot.AlignedData;
    const axis = { stroke: themeColor("muted"), grid: { stroke: themeColor("chip"), width: 1 }, ticks: { stroke: themeColor("line-2"), width: 1 }, font: "11px 'Lexend Variable', system-ui, sans-serif" };
    const plot = new uPlot(
      {
        width: el.clientWidth,
        height: 190,
        padding: [8, 8, 0, 0],
        legend: { show: false },
        cursor: { drag: { x: false, y: false } },
        scales: { x: { time: true } },
        axes: [
          { ...axis, values: (_u, v) => v.map((s) => new Date(s * 1000).toISOString().slice(0, 7)) },
          { ...axis, size: 48, label: t("mm (LOS)"), labelSize: 14, labelFont: "11px 'Lexend Variable', sans-serif" },
        ],
        series: [
          {},
          { stroke: themeColor("accent"), width: 1.6, points: { show: true, size: 5, fill: themeColor("accent"), stroke: themeColor("bg") }, spanGaps: true },
          { stroke: themeColor("warn"), width: 2, dash: [6, 4], points: { show: true, size: 5, fill: themeColor("warn") } },
          { stroke: "transparent", points: { show: false } },
          { stroke: "transparent", points: { show: false } },
          { stroke: "transparent", points: { show: false } },
          { stroke: "transparent", points: { show: false } },
        ],
        bands: [
          { series: [3, 4], fill: "rgba(245,184,75,0.12)" },
          { series: [5, 6], fill: "rgba(245,184,75,0.25)" },
        ],
      },
      data,
      el,
    );
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height: 190 }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [c]);
  return (
    <div>
      <div ref={box} className="w-full" />
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-accent" /> {t("observed (cell median, 0 at the first date)")}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-4 border-t-2 border-dashed border-warn" /> {t("forecast")}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-4 bg-[rgba(245,184,75,0.35)]" /> {t("80 % / 95 % interval")}
        </span>
      </div>
    </div>
  );
}
