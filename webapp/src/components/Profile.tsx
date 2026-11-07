// Profile along a line drawn on the map (pages/Explorer.tsx): the ground height (Terrarium tiles) above, the
// velocity of the points within the half width below, with its median in bins; hovering marks the place on the map.
import { useMemo, useRef } from "react";
import type { ProfileData, VelClass } from "../api";
import { t } from "../i18n";
import { classColor } from "../map";

const W = 900;
const L = 52;
const R = 12;
const TOP = { y: 8, h: 80 };
const BOT = { y: 108, h: 150 };
const H = BOT.y + BOT.h + 26;

function ticks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo || 1;
  const step = 10 ** Math.floor(Math.log10(span / n));
  const m = [1, 2, 5, 10].find((k) => span / (k * step) <= n) ?? 10;
  const s = m * step;
  const out: number[] = [];
  for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-9; v += s) out.push(Number(v.toFixed(6)));
  return out;
}

export function ProfileChart({
  data,
  terrain,
  classes,
  hover,
  onHover,
}: {
  data: ProfileData;
  terrain: [number, number | null][] | null;
  classes: VelClass[];
  hover: number | null;
  onHover: (d: number | null) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const len = Math.max(1, data.length_m);
  const X = (d: number) => L + ((W - L - R) * d) / len;
  const [hLo, hHi] = useMemo(() => {
    const hs = [...(terrain ?? []).map((p) => p[1]), ...(data.height_m ?? [])].filter((v): v is number => v != null && Number.isFinite(v));
    if (!hs.length) return [0, 1];
    const lo = Math.min(...hs);
    const hi = Math.max(...hs);
    const pad = Math.max(1, (hi - lo) * 0.1);
    return [lo - pad, hi + pad];
  }, [terrain, data.height_m]);
  const [vLo, vHi] = useMemo(() => {
    if (!data.vel.length) return [-1, 1];
    const lo = Math.min(0, ...data.vel);
    const hi = Math.max(0, ...data.vel);
    const pad = Math.max(0.5, (hi - lo) * 0.05);
    return [lo - pad, hi + pad];
  }, [data.vel]);
  const YH = (h: number) => TOP.y + (TOP.h * (hHi - h)) / (hHi - hLo);
  const YV = (v: number) => BOT.y + (BOT.h * (vHi - v)) / (vHi - vLo);
  const ground = (terrain ?? []).filter((p): p is [number, number] => p[1] != null);
  const groundPath = ground.length > 1 ? `M${X(ground[0][0])},${TOP.y + TOP.h} ` + ground.map(([d, h]) => `L${X(d)},${YH(h)}`).join(" ") + ` L${X(ground[ground.length - 1][0])},${TOP.y + TOP.h} Z` : "";
  const median = data.median.filter((m) => m[2] >= 3);
  const move = (e: React.MouseEvent) => {
    const el = svg.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    onHover(x < L || x > W - R ? null : ((x - L) / (W - L - R)) * len);
  };
  const km = len >= 2000;
  const fmtD = (d: number) => (km ? (d / 1000).toFixed(d < 10_000 ? 1 : 0) : d.toFixed(0));
  return (
    <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full select-none" onMouseMove={move} onMouseLeave={() => onHover(null)}>
      {/* ground */}
      {ticks(hLo, hHi, 3).map((h) => (
        <g key={`h${h}`}>
          <line x1={L} x2={W - R} y1={YH(h)} y2={YH(h)} stroke="var(--c-line-2)" strokeDasharray="3 3" />
          <text x={L - 6} y={YH(h) + 4} fill="var(--c-muted)" fontSize="10.5" textAnchor="end">{h}</text>
        </g>
      ))}
      {groundPath && <path d={groundPath} fill="var(--c-line-3)" fillOpacity={0.55} stroke="var(--c-muted)" strokeWidth="1.2" />}
      {data.height_m &&
        data.dist_m.map((d, i) =>
          data.height_m![i] != null && i % Math.max(1, Math.floor(data.dist_m.length / 1500)) === 0 ? (
            <circle key={`p${i}`} cx={X(d)} cy={YH(data.height_m![i]!)} r={1.1} fill="var(--c-ink)" fillOpacity={0.35} />
          ) : null,
        )}
      <text x={8} y={TOP.y + TOP.h / 2} fill="var(--c-muted)" fontSize="10.5" transform={`rotate(-90 8 ${TOP.y + TOP.h / 2})`} textAnchor="middle">
        {t("height, m")}
      </text>
      {/* velocity */}
      {ticks(vLo, vHi, 4).map((v) => (
        <g key={`v${v}`}>
          <line x1={L} x2={W - R} y1={YV(v)} y2={YV(v)} stroke={v === 0 ? "var(--c-muted)" : "var(--c-line-2)"} strokeDasharray={v === 0 ? undefined : "3 3"} />
          <text x={L - 6} y={YV(v) + 4} fill="var(--c-muted)" fontSize="10.5" textAnchor="end">{v}</text>
        </g>
      ))}
      {data.dist_m.map((d, i) => {
        const c = classColor(classes, data.vel[i]);
        return <circle key={i} cx={X(d)} cy={YV(data.vel[i])} r={1.6} fill={`rgb(${c.join(",")})`} fillOpacity={0.7} />;
      })}
      {median.length > 1 && <path d={median.map((m, i) => `${i ? "L" : "M"}${X(m[0])},${YV(m[1])}`).join(" ")} fill="none" stroke="#ffffff" strokeWidth="2" />}
      <text x={8} y={BOT.y + BOT.h / 2} fill="var(--c-muted)" fontSize="10.5" transform={`rotate(-90 8 ${BOT.y + BOT.h / 2})`} textAnchor="middle">
        {t("velocity, mm/yr")}
      </text>
      {/* distance axis */}
      {ticks(0, len / (km ? 1000 : 1), 6).map((d) => (
        <text key={`d${d}`} x={X(d * (km ? 1000 : 1))} y={H - 8} fill="var(--c-muted)" fontSize="10.5" textAnchor="middle">{d}</text>
      ))}
      <text x={W - R} y={H - 8} fill="var(--c-muted)" fontSize="10.5" textAnchor="end">{km ? "km" : "m"}</text>
      {hover != null && (
        <g pointerEvents="none">
          <line x1={X(hover)} x2={X(hover)} y1={TOP.y} y2={BOT.y + BOT.h} stroke="#ffd166" strokeWidth="1.2" />
          <text x={Math.min(X(hover) + 6, W - 120)} y={BOT.y + 12} fill="#ffd166" fontSize="11">
            {fmtD(hover)} {km ? "km" : "m"}
            {(() => {
              const m = median.reduce<[number, number, number] | null>((b, x) => (!b || Math.abs(x[0] - hover) < Math.abs(b[0] - hover) ? x : b), null);
              return m ? ` · ${m[1].toFixed(1)} mm/yr` : "";
            })()}
          </text>
        </g>
      )}
    </svg>
  );
}
