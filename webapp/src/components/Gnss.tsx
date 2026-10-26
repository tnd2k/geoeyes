// GNSS of a project (Validation tab): the NGL stations inside a product, InSAR around each antenna against the
// GNSS in the line of sight, and the GNSS calibration with its leave-one-out check (geoeyes gnss).
// Method and sources: docs/en/research/gnss-insar-calibration.md.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import { api, type GnssSeries, type GnssStation } from "../api";
import { t, ts } from "../i18n";
import { useWarnings } from "../notify";
import { Button, Chip, fmt, Panel } from "../ui";

type Mode = "vertical" | "full";

function StationChart({ s, mode }: { s: GnssSeries; mode: Mode }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    // one time axis: the InSAR epochs and the GNSS days merged
    const tm = Array.from(new Set([...s.dates, ...s.day])).sort();
    const ix = new Map(tm.map((d, i) => [d, i]));
    const col = (dates: string[], v: (number | null)[]) => {
      const out: (number | null)[] = tm.map(() => null);
      dates.forEach((d, i) => (out[ix.get(d)!] = v[i]));
      return out;
    };
    const insar = mode === "vertical" ? s.insar_vertical_mm : s.insar_full_mm;
    const axis = { stroke: "#93a4bf", grid: { stroke: "#1a2740", width: 1 }, ticks: { stroke: "#22324d", width: 1 }, font: "11px Inter, system-ui, sans-serif" };
    const plot = new uPlot(
      {
        width: el.clientWidth,
        height: 220,
        padding: [8, 8, 0, 0],
        legend: { show: false },
        cursor: { drag: { x: false, y: false } },
        scales: { x: { time: true } },
        axes: [
          { ...axis, values: (_u, v) => v.map((x) => new Date(x * 1000).toISOString().slice(0, 7)) },
          { ...axis, size: 48, label: t("mm (LOS, + toward the satellite)"), labelSize: 14, labelFont: "11px Inter, sans-serif" },
        ],
        series: [
          {},
          { stroke: "rgba(245,184,75,0.35)", width: 1, points: { show: false }, spanGaps: false },
          { stroke: "#f5b84b", width: 0, points: { show: true, size: 7, fill: "#0b1220", stroke: "#f5b84b", width: 2 } },
          { stroke: "#4cc2ff", width: 1.8, points: { show: true, size: 6, fill: "#4cc2ff", stroke: "#0b1220" }, spanGaps: true },
        ],
      },
      [tm.map((d) => Date.parse(d) / 1000), col(s.day, s[mode].daily_mm), col(s.dates, s[mode].gnss_mm), col(s.dates, insar)] as uPlot.AlignedData,
      el,
    );
    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height: 220 }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.destroy();
    };
  }, [s, mode]);
  return (
    <div>
      <div ref={box} className="w-full" />
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-[#4cc2ff]" /> {t("InSAR, median of the points around the antenna")}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full border-2 border-[#f5b84b]" /> {t("GNSS at the InSAR epochs (± window)")}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-[rgba(245,184,75,0.35)]" /> {t("GNSS daily")}
        </span>
      </div>
    </div>
  );
}

const PARAMS: { key: string; label: string; options: (number | string)[]; hint: string }[] = [
  { key: "radius_m", label: "Radius", options: [50, 100, 200, 300], hint: "InSAR points around the antenna (m)" },
  { key: "los_mode", label: "GNSS → LOS", options: ["vertical", "full"], hint: "vertical: u·l_u (plate motion cancels with the InSAR reference); full: every component" },
  { key: "calibration", label: "Calibration", options: ["offset", "plane", "epoch"], hint: "offset: one rate; plane: a ramp (≥ 3 stations); epoch: a correction per date" },
  { key: "gnss_rate", label: "GNSS rate", options: ["window", "midas"], hint: "window: over the InSAR period; midas: NGL long-term robust rate" },
];

function Stats({ st, mode }: { st: GnssStation; mode: Mode }) {
  const v = st[mode];
  if (!v) return null;
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px] sm:grid-cols-4">
      {[
        [t("InSAR rate"), `${fmt.vel(v.rate_insar_mm_yr)} ± ${fmt.num(v.rate_insar_se)}`],
        [t("GNSS rate (LOS)"), `${fmt.vel(v.rate_gnss_mm_yr)} ± ${fmt.num(v.rate_gnss_se)}`],
        ["GNSS − InSAR", `${fmt.vel(v.rate_diff_mm_yr)} mm/yr`],
        [t("vs MIDAS"), v.rate_diff_midas_mm_yr != null ? `${fmt.vel(v.rate_diff_midas_mm_yr)} mm/yr` : "–"],
        ["RMSE", `${fmt.num(v.rmse_mm)} mm`],
        [t("RMSE, trend removed"), `${fmt.num(v.rmse_detrended_mm)} mm`],
        [t("Correlation"), fmt.num(v.corr, 2)],
        [t("Epochs"), String(v.n_epochs)],
      ].map(([k, x]) => (
        <div key={k} className="contents">
          <span className="text-muted">{k}</span>
          <span className="text-right font-mono text-[11.5px] text-ink-2 sm:text-left">{x}</span>
        </div>
      ))}
    </div>
  );
}

export function Gnss({ name }: { name: string }) {
  const qc = useQueryClient();
  const proj = useQuery({ queryKey: ["project", name], queryFn: () => api.project(name) });
  const products = (proj.data?.tracks ?? []).flatMap((t) => (t.product ? [{ id: t.product.id, label: `${t.track_id} v${t.product.version}` }] : []));
  const [pid, setPid] = useState("");
  const product = pid || products[0]?.id || "";
  const q = useQuery({
    queryKey: ["gnss", name, product],
    queryFn: () => api.gnss(name, product),
    enabled: !!product,
    refetchInterval: (x) => (x.state.data?.running ? 2000 : false),
  });
  const s = q.data?.summary ?? null;
  useWarnings(`gnss:${name}/${product}:${s?.created}`, `GNSS · ${name}`, s?.warnings, `#/project/${encodeURIComponent(name)}/validation`);
  const [params, setParams] = useState<Record<string, string | number>>({});
  useEffect(() => {
    if (s) setParams(Object.fromEntries(PARAMS.map((p) => [p.key, s.params[p.key as keyof typeof s.params] as string | number])));
  }, [s]);
  const used = s?.stations.filter((x) => x.used) ?? [];
  const [site, setSite] = useState("");
  const pick = used.find((x) => x.site === site) ?? used[0];
  const mode: Mode = (s?.calibration?.los_mode ?? (params.los_mode as Mode)) || "vertical";
  const [view, setView] = useState<Mode | null>(null);
  const shown: Mode = view ?? mode;
  const series = useQuery({
    queryKey: ["gnss-station", name, product, s?.created, pick?.site],
    queryFn: () => api.gnssStation(name, product, pick!.site),
    enabled: !!pick,
  });
  const [err, setErr] = useState("");
  const run = async () => {
    setErr("");
    try {
      await api.gnssRun(name, product, params);
      await qc.invalidateQueries({ queryKey: ["gnss", name, product] });
    } catch (e) {
      const m = (e as Error).message;
      setErr(/method not allowed|not found/i.test(m) ? t("{msg}: the running server predates this page, restart geoeyes serve", { msg: m }) : m);
    }
  };
  const c = s?.calibration;

  return (
    <div className="mb-6 space-y-4">
      <Panel className="px-4 py-3 text-[13px]">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{t("GNSS (Nevada Geodetic Laboratory)")}</div>
            <div className="mt-0.5 text-muted">
              {t(
                'Daily NGL stations inside the product (IGS20), compared with the InSAR points around each antenna; the GNSS can tie the InSAR reference (used by the Thematic analysis page as "GNSS tie").',
              )}
            </div>
          </div>
          <select
            value={product}
            onChange={(e) => setPid(e.target.value)}
            aria-label={t("Product")}
            className="h-8 rounded-md border border-line-2 bg-[#0a1322] px-2 text-[12.5px] text-ink"
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <Button variant="primary" disabled={!product || q.data?.running} onClick={run}>
            {q.data?.running ? t("Comparing…") : s ? t("Compare again") : t("Compare with GNSS")}
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
          {PARAMS.map((p) => (
            <label key={p.key} className="flex items-center gap-1.5 text-[12px] text-muted" title={t(p.hint)}>
              {t(p.label)}
              <select
                value={String(params[p.key] ?? p.options[p.key === "radius_m" ? 1 : 0])}
                onChange={(e) => setParams((v) => ({ ...v, [p.key]: typeof p.options[0] === "number" ? Number(e.target.value) : e.target.value }))}
                className="h-7 rounded-md border border-line-2 bg-[#0a1322] px-1.5 text-[12px] text-ink"
              >
                {p.options.map((o) => (
                  <option key={o} value={String(o)}>
                    {o}
                    {p.key === "radius_m" ? " m" : ""}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        {err && <div className="mt-2 text-[12.5px] text-bad">{err}</div>}
        {(q.data?.running || q.data?.failed) && q.data.log.length > 0 && (
          <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-line bg-[#070c16] p-2 font-mono text-[11.5px] text-[#a9b8cf]">{q.data.log.join("\n")}</pre>
        )}
      </Panel>

      {s && (
        <>
          {s.warnings.length > 0 && (
            <div className="rounded-lg bg-[#2a2110] px-3 py-2 text-[12.5px] text-[#f5d08b]">{t("{n} warning(s): see the notifications", { n: s.warnings.length })}</div>
          )}
          <Panel className="overflow-x-auto p-0">
            <table className="w-full min-w-[720px] text-[12.5px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] tracking-[0.8px] text-muted uppercase">
                  {["Station", "Status", "Points", "Epochs", "InSAR", "GNSS (LOS)", "GNSS − InSAR", "RMSE detr.", "Corr."].map((h) => (
                    <th key={h} className="px-3 py-2 font-semibold">
                      {t(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {s.stations.map((st) => {
                  const v = st[mode];
                  return (
                    <tr
                      key={st.site}
                      onClick={() => st.used && setSite(st.site)}
                      className={`border-b border-line/60 ${st.used ? "cursor-pointer hover:bg-[#131f35]" : ""} ${pick?.site === st.site ? "bg-raised" : ""}`}
                    >
                      <td className="px-3 py-2 font-mono">{st.site}</td>
                      <td className="px-3 py-2">{st.used ? <Chip status="ok" label={t("compared")} /> : <span className="text-muted">{ts(st.reason ?? "")}</span>}</td>
                      <td className="px-3 py-2 font-mono">{st.n_points ?? "–"}</td>
                      <td className="px-3 py-2 font-mono">{st.n_epochs ?? "–"}</td>
                      <td className="px-3 py-2 font-mono">{v ? fmt.vel(v.rate_insar_mm_yr) : "–"}</td>
                      <td className="px-3 py-2 font-mono">{v ? fmt.vel(v.rate_gnss_mm_yr) : "–"}</td>
                      <td className="px-3 py-2 font-mono">{v ? fmt.vel(v.rate_diff_mm_yr) : "–"}</td>
                      <td className="px-3 py-2 font-mono">{v ? `${fmt.num(v.rmse_detrended_mm)} mm` : "–"}</td>
                      <td className="px-3 py-2 font-mono">{v ? fmt.num(v.corr, 2) : "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="px-3 py-2 text-[11px] text-faint">
              {t("Rates in mm/yr along the line of sight ({mode} GNSS projection), over the product period.", { mode })} {ts(s.source)}.
            </div>
          </Panel>

          {c && (
            <Panel className="px-4 py-3 text-[13px]">
              <div className="font-semibold">{t("Calibration")}</div>
              <div className="mt-1 text-ink-2">
                {t("{kind} from {stations} ({mode}, GNSS rate {rate}):", { kind: c.kind, stations: c.stations.join(", "), mode: c.los_mode, rate: c.gnss_rate })}{" "}
                <span className="font-mono">{fmt.vel(c.rate_offset_mm_yr)} mm/yr</span> {t("added to every point along the line of sight")}
                {c.rate_coef.length === 3
                  ? ` ${t("+ ramp {e} / {n} mm/yr per km (east / north)", { e: fmt.num(c.rate_coef[1], 3), n: fmt.num(c.rate_coef[2], 3) })}`
                  : ""}
                .
              </div>
              {c.leave_one_out ? (
                <div className="mt-2">
                  <div className="text-muted">
                    {t("Leave one out (each station predicted without it): RMS of GNSS − InSAR")}{" "}
                    <span className="font-mono text-ink-2">{fmt.num(c.loo_rms_before_mm_yr)}</span> {t("mm/yr before,")}{" "}
                    <span className="font-mono text-ink-2">{fmt.num(c.loo_rms_after_mm_yr)}</span> {t("mm/yr after —")}{" "}
                    {c.loo_rms_after_mm_yr! < 0.8 * c.loo_rms_before_mm_yr! ? (
                      <span className="text-good">{t("the calibration improves the InSAR away from the stations")}</span>
                    ) : (
                      <span className="text-warn">{t("no clear improvement away from the stations")}</span>
                    )}
                    {c.stations.length < 4 ? ` ${t("(only {n} stations: a weak check)", { n: c.stations.length })}` : ""}.
                  </div>
                </div>
              ) : (
                <div className="mt-2 text-muted">{t("One station: the reference is tied to it, but the tie cannot be checked independently.")}</div>
              )}
            </Panel>
          )}

          {pick && (
            <Panel className="px-4 py-3 text-[13px]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-semibold">{pick.site}</span>
                <span className="text-muted">
                  {t("{n} points within {r} m (median {d} m)", { n: pick.n_points, r: s.params.radius_m, d: pick.median_distance_m })} · GNSS ENU{" "}
                  {pick.gnss_rate_enu_mm_yr?.map((v) => fmt.vel(v)).join(" / ")} {t("mm/yr over the period")}
                  {pick.midas ? ` · MIDAS ${pick.midas.enu_mm_yr.map((v) => fmt.vel(v)).join(" / ")} mm/yr (${fmt.num(pick.midas.years)} yr)` : ""}
                </span>
                <div className="ml-auto flex rounded-md border border-line-2 p-0.5">
                  {(["vertical", "full"] as Mode[]).map((m) => (
                    <button
                      key={m}
                      type="button"
                      aria-pressed={shown === m}
                      onClick={() => setView(m)}
                      className={`h-6 rounded px-2.5 text-[12px] ${shown === m ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
                    >
                      {m === "vertical" ? t("GNSS vertical") : t("GNSS 3-D")}
                    </button>
                  ))}
                </div>
              </div>
              {(pick.notes ?? []).concat(pick.midas?.note ? [pick.midas.note] : []).map((n) => (
                <div key={n} className="mt-1 text-[12px] text-warn">
                  {ts(n)}
                </div>
              ))}
              <div className="mt-2">
                <Stats st={pick} mode={shown} />
              </div>
              <div className="mt-3">{series.data ? <StationChart s={series.data} mode={shown} /> : <div className="py-6 text-center text-muted">{t("Loading…")}</div>}</div>
              <div className="mt-1 text-[11px] text-faint">{t("Both series zero at their first shared date; the statistics compare rates and shapes (offsets removed by their means).")}</div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
