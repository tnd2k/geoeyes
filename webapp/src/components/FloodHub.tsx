// Flood outlook hub over the results map: the next 24 hours at the selected reported location (or the city): forecast
// rain, tide, a transparent score and, with a product, the subsidence around it. A reference, not a flood forecast.
import type { FloodAssessment, FloodFeature, FloodLevel, FloodOutlook, FloodTide } from "../api";
import { t } from "../i18n";
import { causeLabel, locatedLabel } from "./FloodReports";

export const LEVEL_COLOR: Record<FloodLevel, [number, number, number]> = {
  low: [34, 197, 94],
  watch: [234, 179, 8],
  high: [249, 115, 22],
  very_high: [220, 38, 38],
};
const LEVEL_LABEL: Record<FloodLevel, string> = { low: "Low", watch: "Watch", high: "High", very_high: "Very high" };
const DEPTH_LABEL = { unlikely: "Flooding unlikely", lt20: "Possibly under 20 cm", "20_40": "Possibly 20–40 cm", gt40: "Possibly over 40 cm" };

const hhmm = (s: string | null | undefined) => (s ? s.slice(11, 16) : "–");
const ddmm = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}`;
const rgb = (c: number[], a = 1) => `rgba(${c.join(",")},${a})`;

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-panel-2 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[12px] font-medium text-muted">
        <span className="text-ink-2">{icon}</span>
        {label}
      </div>
      <div className="mt-1 text-[16px] font-bold tracking-tight">{value}</div>
    </div>
  );
}

const Cloud = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden>
    <path d="M4.5 10.5a3 3 0 1 1 .6-5.9A3.8 3.8 0 0 1 12.3 6a2.3 2.3 0 0 1-.3 4.5z" strokeLinejoin="round" />
    <path d="M6 12.5 5.5 14M9 12.5 8.5 14M12 12.5l-.5 1.5" strokeLinecap="round" />
  </svg>
);
const Waves = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" aria-hidden>
    <path d="M1.5 5.5c1.6-1.2 3-1.2 4.4 0s2.8 1.2 4.4 0 3-1.2 4.2 0M1.5 9c1.6-1.2 3-1.2 4.4 0s2.8 1.2 4.4 0 3-1.2 4.2 0M1.5 12.5c1.6-1.2 3-1.2 4.4 0s2.8 1.2 4.4 0 3-1.2 4.2 0" />
  </svg>
);
const Ground = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" aria-hidden>
    <path d="M1.5 11.5h13M3 14h10M8 2v6.5M5.5 6 8 8.5 10.5 6" />
  </svg>
);

/** Rain bars and the tide curve over the next 24 hours. */
function Chart({ a, tide }: { a: FloodAssessment; tide: FloodTide | null }) {
  const W = 300;
  const H = 86;
  const n = a.hours.time.length;
  if (!n) return null;
  const bw = W / n;
  const maxMm = Math.max(5, ...a.hours.mm);
  const tl = (tide?.level ?? []).map((v) => (v == null ? NaN : v));
  const lo = Math.min(...tl.filter(Number.isFinite), 0);
  const hi = Math.max(tide?.highest ?? 1, ...tl.filter(Number.isFinite));
  const ty = (v: number) => 8 + (H - 22) * (1 - (v - lo) / (hi - lo || 1));
  const tx = (k: number) => (k + 0.5) * (W / Math.max(1, tl.length));
  const path = tl.map((v, k) => (Number.isFinite(v) ? `${k === 0 || !Number.isFinite(tl[k - 1]) ? "M" : "L"}${tx(k).toFixed(1)},${ty(v).toFixed(1)}` : "")).join("");
  const alert = tide ? tide.median_daily_high + 0.6 * (tide.highest - tide.median_daily_high) : NaN;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("Rain and tide over the next 24 hours")}>
      {a.hours.mm.map((v, k) => {
        const h = ((H - 22) * v) / maxMm;
        return <rect key={k} x={k * bw + 1} y={H - 14 - h} width={Math.max(1, bw - 2)} height={h} rx={1.5} fill={rgb([37, 99, 235], 0.35 + (0.6 * a.hours.prob[k]) / 100)} />;
      })}
      {tide && <line x1={0} x2={W} y1={ty(alert)} y2={ty(alert)} stroke={rgb([168, 85, 247], 0.6)} strokeDasharray="3 3" strokeWidth={1} />}
      {tide && <path d={path} fill="none" stroke="rgb(168,85,247)" strokeWidth={2} strokeLinejoin="round" />}
      {a.hours.time.map((s, k) =>
        k % 6 === 0 ? (
          <text key={s} x={k * bw + 1} y={H - 2} fontSize={9.5} fill="var(--c-muted)">
            {hhmm(s)}
          </text>
        ) : null,
      )}
    </svg>
  );
}

export function FloodHub({ outlook, area, feature, loading, error }: { outlook: FloodOutlook | undefined; area: string | null; feature: FloodFeature | null; loading: boolean; error: string | null }) {
  if (error) return <div className="text-[12.5px] text-bad">{error}</div>;
  const ar = outlook && area ? outlook.areas[area] : undefined;
  if (!outlook || !ar) return <div className="text-[12.5px] text-accent-ink">{loading ? t("Reading the forecast…") : ""}</div>;
  const own = !!(feature && outlook.rows[feature.id]);
  const a = own ? outlook.rows[feature!.id] : ar.city;
  const col = LEVEL_COLOR[a.level];
  const cause = own ? feature!.properties.cause : ar.tide ? "rain_tide" : "rain";
  const tide = ar.tide;
  return (
    <div className="space-y-2.5">
      <div className="text-[14px] leading-snug font-semibold">{own ? feature!.properties.text : t("{name} — the whole area", { name: t(ar.name) })}</div>
      {own && (
        <div className="-mt-1.5 text-[11.5px] leading-snug text-muted">
          {causeLabel(feature!.properties.cause)} · {feature!.properties.reported} · {feature!.properties.source}
          {feature!.properties.notes ? ` · ${feature!.properties.notes}` : ""}
          <br />
          {locatedLabel(feature!.properties.located)}
          {feature!.properties.url && (
            <a href={feature!.properties.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-accent hover:underline">
              {t("Source")} ↗
            </a>
          )}
        </div>
      )}

      <div className="rounded-xl border border-warn-line bg-warn-bg px-3 py-2.5">
        <div className="flex items-center gap-2 text-[13.5px] font-bold text-warn-ink">
          <span className="flex h-5 w-5 flex-none items-center justify-center rounded-full border-2 border-current text-[11px]">!</span>
          {own ? t("Reported flood spot, not a confirmed flood now") : t("Outlook for the whole area")}
        </div>
        <div className="mt-1 pl-7 text-[12.5px] leading-snug text-ink-2">{tide ? t("A reference from forecast rain and tide models; it may not flood.") : t("A reference from the forecast rain model; it may not flood.")}</div>
      </div>

      <div className="rounded-xl border border-[rgba(168,85,247,0.35)] bg-[rgba(168,85,247,0.08)] px-3 py-2.5">
        <div className="text-[13.5px] font-bold text-[rgb(168,85,247)]">
          △{" "}
          {!a.window
            ? t("No risk hour in the next 24 hours")
            : a.window[0] === a.window[1]
              ? t("Risk around {a}", { a: hhmm(a.window[0]) })
              : t("Risk between {a} and {b}", { a: hhmm(a.window[0]), b: hhmm(a.window[1]) })}
        </div>
        <div className="mt-1 text-[12.5px] leading-relaxed text-ink-2">
          {t("Forecast rain {mm} mm/24 h, highest rain probability {p}%", { mm: a.rain_24h_mm.toFixed(1), p: a.rain_prob_max })}
          {a.tide_peak_m != null && a.tide_peak_time ? `; ${t("tide peak {m} m at {h} {d}", { m: a.tide_peak_m.toFixed(2), h: hhmm(a.tide_peak_time), d: ddmm(a.tide_peak_time) })}` : ""}.{" "}
          {own ? t("Weighted for this spot's cause ({cause})", { cause: causeLabel(cause) }) : ar.tide ? t("Rain and tide weighted equally") : t("Rain only (inland city)")}
          {a.parts.subsidence_bonus ? ` ${t("and its subsidence (InSAR)")}` : ""}. {t("For reference only.")}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-line bg-panel-2 px-3 py-2.5">
          <div className="flex items-start justify-between gap-1">
            <span className="text-[11px] leading-tight font-bold tracking-[0.8px] text-muted uppercase">{t("Risk score")}</span>
            <span className="text-[24px] leading-none font-extrabold">
              {a.score}
              <span className="text-[13px] font-semibold text-muted">/100</span>
            </span>
          </div>
          <div className="relative mt-2.5 h-2 rounded-full bg-[linear-gradient(90deg,#22c55e,#eab308_40%,#f97316_65%,#dc2626)]">
            <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow" style={{ left: `${a.score}%`, background: rgb(col) }} />
          </div>
          <div className="mt-2 text-[13px] font-bold" style={{ color: rgb(col) }}>
            {t(LEVEL_LABEL[a.level])}
          </div>
        </div>
        <div className="rounded-xl border border-line bg-panel-2 px-3 py-2.5">
          <div className="flex items-center justify-between gap-1">
            <span className="text-[11px] leading-tight font-bold tracking-[0.8px] text-muted uppercase">{t("Estimated depth")}</span>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" className="text-accent-ink" aria-hidden>
              <path d="M6 2.5S3 6 3 8a3 3 0 0 0 6 0c0-2-3-5.5-3-5.5zM11.5 6.5S9.8 8.6 9.8 9.7a1.7 1.7 0 0 0 3.4 0c0-1.1-1.7-3.2-1.7-3.2z" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="mt-1.5 text-[16px] leading-snug font-extrabold">{t(DEPTH_LABEL[a.depth])}</div>
          <div className="mt-1 text-[11.5px] text-muted">{t("Rough class from the score, no hydraulic model")}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat icon={<Cloud />} label={t("Rain 24 h")} value={`${a.rain_24h_mm.toFixed(1)} mm`} />
        <Stat icon={<Cloud />} label={t("Heaviest hour")} value={`${a.rain_max_mm_h.toFixed(1)} mm`} />
        <Stat icon={<Cloud />} label={t("Rain probability")} value={`${a.rain_prob_max}%`} />
        <Stat icon={<Waves />} label={t("Tide peak")} value={tide && a.tide_peak_m != null ? `${a.tide_peak_m.toFixed(2)} m · ${hhmm(a.tide_peak_time)}` : t("no tide (inland)")} />
        {a.velocity_mm_yr != null && (
          <div className="col-span-2">
            <Stat
              icon={<Ground />}
              label={
                own || !ar.subsidence
                  ? t("Ground motion around (InSAR, LOS)")
                  : t("Ground motion at the {n} reported flood spots on the product (median; {k} sink > 5 mm/yr)", { n: ar.subsidence.locations, k: ar.subsidence.sinking_over_5 })
              }
              value={
                <span>
                  {a.velocity_mm_yr.toFixed(1)} mm/{t("yr")}
                  {a.parts.subsidence_bonus ? <span className="ml-2 text-[12px] font-semibold text-warn">+{a.parts.subsidence_bonus} {t("points")}</span> : null}
                </span>
              }
            />
          </div>
        )}
      </div>

      <div className="rounded-xl border border-line bg-panel-2 px-3 pt-2 pb-1">
        <div className="flex items-center gap-3 text-[11.5px] text-muted">
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm bg-[rgb(37,99,235)]" /> {t("rain, mm/h")}
          </span>
          {tide && (
            <span className="flex items-center gap-1">
              <span className="h-0.5 w-3 bg-[rgb(168,85,247)]" /> {t("sea level, m")}
            </span>
          )}
          <span className="ml-auto">24 h</span>
        </div>
        <Chart a={a} tide={tide} />
      </div>

      <div className="text-[11px] leading-snug text-faint">
        {tide
          ? t("Rain: {rain}. Tide: {tide}, off the river mouth ({lat}, {lon}). Updated {at}.", {
              rain: outlook.sources.rain,
              tide: tide.source,
              lat: tide.point[1].toFixed(2),
              lon: tide.point[0].toFixed(2),
              at: outlook.generated.replace("T", " "),
            })
          : t("Rain: {rain}. Updated {at}.", { rain: outlook.sources.rain, at: outlook.generated.replace("T", " ") })}
      </div>
    </div>
  );
}
