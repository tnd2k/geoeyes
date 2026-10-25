// Monitoring of a project: next Sentinel-1 acquisitions, a scheduled run, deformation alerts on the latest product.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type AlertRule } from "../api";
import { t, ts } from "../i18n";
import { useApp } from "../state";
import { Button, Chip, fmt, Panel } from "../ui";

const field = "h-8 rounded-md border border-line-2 bg-[#0a1322] px-2 text-[13px] text-ink focus:border-accent focus:outline-none";
const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

export function Monitor({ name }: { name: string }) {
  const qc = useQueryClient();
  const { showProduct } = useApp();
  const q = useQuery({ queryKey: ["monitor", name], queryFn: () => api.monitor(name) });
  const [freq, setFreq] = useState("off");
  const [time, setTime] = useState("02:00");
  const [day, setDay] = useState("MON");
  const [rules, setRules] = useState<AlertRule[]>([]);
  useEffect(() => {
    if (!q.data) return;
    setRules(q.data.rules);
    const s = q.data.schedule;
    if (s.enabled) {
      setFreq((s.schedule ?? "").toLowerCase().includes("weekly") ? "weekly" : "daily");
      if (s.time) setTime(s.time.slice(0, 5));
      const d = DAYS.find((x) => (s.days ?? "").toUpperCase().includes(x));
      if (d) setDay(d);
    }
  }, [q.data]);
  const sched = useMutation({
    mutationFn: () => api.setSchedule(name, { frequency: freq, time, day }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["monitor", name] }),
  });
  const saveRules = useMutation({
    mutationFn: () => api.setAlerts(name, rules),
    onSuccess: () => (qc.invalidateQueries({ queryKey: ["monitor", name] }), qc.invalidateQueries({ queryKey: ["workspace"] })),
  });
  if (q.error) return <div className="text-bad">{(q.error as Error).message}</div>;
  if (!q.data) return <div className="text-muted">{t("Loading…")}</div>;
  const m = q.data;
  const s = m.schedule;
  const dirty = JSON.stringify(rules) !== JSON.stringify(m.rules);
  const runText = t(
    "Runs {cmd} on this machine (Windows Task Scheduler, while you are logged on): new acquisitions are downloaded and only what changed is processed.",
  ).split("{cmd}");
  const upd = (i: number, patch: Partial<AlertRule>) => setRules((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel className="p-4">
          <div className="text-[14px] font-semibold">{t("Next Sentinel-1 acquisitions")}</div>
          <div className="mt-0.5 text-[12px] text-muted">
            {t("12-day repeat of each satellite's last acquisition in the archive, checked against ESA's published acquisition plan")}
          </div>
          {m.next.length === 0 && <div className="mt-3 text-[13px] text-muted">{t("No Sentinel-1 track in this project.")}</div>}
          {m.next.map((tk) => (
            <div key={tk.track} className="mt-3">
              <div className="font-mono text-[12.5px] text-ink-2">{tk.track}</div>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {tk.next.map((n) => (
                  <span
                    key={n.date + n.platform}
                    title={n.status === "planned" ? t("ESA plan: {mode} {pol} at {time}", { mode: n.mode ?? "", pol: n.polarisation ?? "", time: n.time ?? "" }) : n.status === "not planned" ? t("Not in ESA's plan: the satellite passes but does not acquire") : t("Beyond the published plan: repeat-cycle forecast")}
                    className={`rounded-md border px-2.5 py-1 text-[12.5px] ${
                      n.status === "planned" ? "border-[#1f5c45] bg-[#0f2a1f]" : n.status === "not planned" ? "border-line bg-panel-2 text-faint line-through" : "border-line bg-panel-2"
                    }`}
                  >
                    <span className="font-mono">{n.date}</span> <span className="text-muted">{n.platform}</span>
                    {n.status === "planned" && <span className="ml-1 text-[11px] text-good">✓ {t("planned")}{n.time ? ` ${n.time}` : ""}</span>}
                    {n.status === "predicted" && <span className="ml-1 text-[11px] text-faint">{t("forecast")}</span>}
                  </span>
                ))}
                {tk.next.length === 0 && <span className="text-[12.5px] text-muted">{t("no satellite seen in the last 60 days")}</span>}
              </div>
              <div className="mt-1 text-[11.5px] text-faint">
                {t("last:")} {Object.entries(tk.last).map(([p, d]) => `${p} ${d}`).join(" · ") || "–"}
                {Object.keys(tk.plan_until).length > 0 && ` · ${t("ESA plan published until {dates}", { dates: Object.entries(tk.plan_until).map(([p, d]) => `${p} ${d}`).join(", ") })}`}
              </div>
              {tk.note && <div className="mt-1 text-[11.5px] text-warn">{ts(tk.note)}</div>}
            </div>
          ))}
        </Panel>

        <Panel className="p-4">
          <div className="text-[14px] font-semibold">{t("Scheduled run")}</div>
          <div className="mt-0.5 text-[12px] text-muted">
            {runText[0]}
            <span className="font-mono">geoeyes run {name}</span>
            {runText[1]}
          </div>
          {!s.supported ? (
            <div className="mt-3 text-[13px] text-muted">{t("Not available on this system (use cron).")}</div>
          ) : (
            <>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <select className={field} value={freq} onChange={(e) => setFreq(e.target.value)} aria-label={t("Frequency")}>
                  <option value="off">{t("off")}</option>
                  <option value="daily">{t("every day")}</option>
                  <option value="weekly">{t("every week")}</option>
                </select>
                {freq === "weekly" && (
                  <select className={field} value={day} onChange={(e) => setDay(e.target.value)} aria-label={t("Day")}>
                    {DAYS.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                )}
                {freq !== "off" && <input type="time" className={field} value={time} onChange={(e) => setTime(e.target.value)} aria-label={t("Time")} />}
                <Button variant="primary" disabled={sched.isPending} onClick={() => sched.mutate()}>
                  {sched.isPending ? t("Saving…") : t("Save")}
                </Button>
              </div>
              {sched.error && <div className="mt-2 text-[12px] text-bad">{(sched.error as Error).message}</div>}
              <div className="mt-3 text-[12.5px] text-ink-2">
                {s.enabled ? (
                  <>
                    <Chip status="ok" label={`${t("scheduled")} · ${s.schedule ?? ""}`} /> {t("next run")} <span className="font-mono">{s.next_run}</span>
                    {s.last_run && !s.last_run.startsWith("N/A") && s.last_run !== "11/30/1999 12:00:00 AM" && (
                      <> · {t("last")} <span className="font-mono">{s.last_run}</span> ({t("result {r}", { r: s.last_result })})</>
                    )}
                  </>
                ) : (
                  <span className="text-muted">{t("No scheduled run.")}</span>
                )}
              </div>
            </>
          )}
        </Panel>
      </div>

      <Panel className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="text-[14px] font-semibold">{t("Deformation alerts")}</div>
            <div className="mt-0.5 text-[12px] text-muted">{t("Checked on the latest product of each track (after every run, and here). Saved in project.toml [postprocess.alerts].")}</div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button onClick={() => setRules((rs) => [...rs, { name: `rule ${rs.length + 1}`, kind: "velocity_below", threshold: -20, min_points: 20 }])}>
              + {t("Rule")}
            </Button>
            <Button variant="primary" disabled={!dirty || saveRules.isPending} onClick={() => saveRules.mutate()}>
              {saveRules.isPending ? t("Saving…") : t("Save rules")}
            </Button>
          </div>
        </div>
        {saveRules.error && <div className="mt-2 text-[12px] text-bad">{(saveRules.error as Error).message}</div>}
        {rules.length === 0 ? (
          <div className="mt-3 text-[13px] text-muted">{t("No rule. Example: points moving away from the satellite faster than 20 mm/yr, at least 20 of them.")}</div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[820px] text-[12.5px]">
              <thead>
                <tr className="text-left text-muted">
                  {["Name", "Condition", "mm/yr", "Min. points", "Area (W, S, E, N; empty = all)", "Latest product", ""].map((h) => (
                    <th key={h} className="px-2 py-1.5 font-medium">{h && h !== "mm/yr" ? t(h) : h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rules.map((r, i) => {
                  const res = m.alerts.filter((a) => a.name === r.name);
                  return (
                    <tr key={i} className="border-t border-line align-top">
                      <td className="px-2 py-2"><input className={`${field} w-44`} value={r.name} onChange={(e) => upd(i, { name: e.target.value })} aria-label={t("Rule name")} /></td>
                      <td className="px-2 py-2">
                        <select className={field} value={r.kind} onChange={(e) => upd(i, { kind: e.target.value as AlertRule["kind"] })} aria-label={t("Condition")}>
                          <option value="velocity_below">{t("velocity ≤ (away)")}</option>
                          <option value="velocity_above">{t("velocity ≥ (toward)")}</option>
                        </select>
                      </td>
                      <td className="px-2 py-2"><input type="number" step="any" className={`${field} w-20`} value={r.threshold} onChange={(e) => upd(i, { threshold: Number(e.target.value) })} aria-label={t("Threshold")} /></td>
                      <td className="px-2 py-2"><input type="number" min={1} className={`${field} w-20`} value={r.min_points} onChange={(e) => upd(i, { min_points: Number(e.target.value) })} aria-label={t("Minimum points")} /></td>
                      <td className="px-2 py-2">
                        <input
                          className={`${field} w-56`}
                          placeholder={t("whole product")}
                          defaultValue={r.bbox?.join(", ") ?? ""}
                          onBlur={(e) => {
                            const v = e.target.value.split(",").map((x) => parseFloat(x)).filter(Number.isFinite);
                            upd(i, { bbox: v.length === 4 ? v : undefined });
                          }}
                          aria-label={t("Area")}
                        />
                      </td>
                      <td className="px-2 py-2">
                        {res.length === 0 && <span className="text-faint">{t("save to check")}</span>}
                        {res.map((a) => (
                          <div key={a.track} className="flex flex-wrap items-center gap-2">
                            <Chip status={a.triggered ? "failed" : "ok"} label={a.triggered ? t("triggered") : t("quiet")} />
                            <span className="text-ink-2">
                              {t("{n} of {of} pts", { n: fmt.int(a.n), of: fmt.int(a.of) })}{a.worst != null ? ` · ${t("worst {v}", { v: fmt.vel(a.worst) })}` : ""}
                            </span>
                            {a.triggered && a.lon != null && (
                              <button type="button" className="text-accent hover:underline" onClick={() => showProduct(name, a.product, { open: true })}>
                                {t("map")}
                              </button>
                            )}
                          </div>
                        ))}
                      </td>
                      <td className="px-2 py-2">
                        <button type="button" className="text-faint hover:text-bad" onClick={() => setRules((rs) => rs.filter((_, k) => k !== i))} aria-label={t("Remove rule")}>
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
