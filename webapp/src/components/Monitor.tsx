// Monitoring of a project: next Sentinel-1 acquisitions, a scheduled run, deformation alerts on the latest product.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type AlertRule } from "../api";
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
  if (!q.data) return <div className="text-muted">Loading…</div>;
  const m = q.data;
  const s = m.schedule;
  const dirty = JSON.stringify(rules) !== JSON.stringify(m.rules);
  const upd = (i: number, patch: Partial<AlertRule>) => setRules((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel className="p-4">
          <div className="text-[14px] font-semibold">Next Sentinel-1 acquisitions</div>
          <div className="mt-0.5 text-[12px] text-muted">
            12-day repeat of each satellite's last acquisition in the archive, checked against ESA's published acquisition plan
          </div>
          {m.next.length === 0 && <div className="mt-3 text-[13px] text-muted">No Sentinel-1 track in this project.</div>}
          {m.next.map((t) => (
            <div key={t.track} className="mt-3">
              <div className="font-mono text-[12.5px] text-ink-2">{t.track}</div>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {t.next.map((n) => (
                  <span
                    key={n.date + n.platform}
                    title={n.status === "planned" ? `ESA plan: ${n.mode ?? ""} ${n.polarisation ?? ""} at ${n.time ?? ""}` : n.status === "not planned" ? "Not in ESA's plan: the satellite passes but does not acquire" : "Beyond the published plan: repeat-cycle forecast"}
                    className={`rounded-md border px-2.5 py-1 text-[12.5px] ${
                      n.status === "planned" ? "border-[#1f5c45] bg-[#0f2a1f]" : n.status === "not planned" ? "border-line bg-panel-2 text-faint line-through" : "border-line bg-panel-2"
                    }`}
                  >
                    <span className="font-mono">{n.date}</span> <span className="text-muted">{n.platform}</span>
                    {n.status === "planned" && <span className="ml-1 text-[11px] text-good">✓ planned{n.time ? ` ${n.time}` : ""}</span>}
                    {n.status === "predicted" && <span className="ml-1 text-[11px] text-faint">forecast</span>}
                  </span>
                ))}
                {t.next.length === 0 && <span className="text-[12.5px] text-muted">no satellite seen in the last 60 days</span>}
              </div>
              <div className="mt-1 text-[11.5px] text-faint">
                last: {Object.entries(t.last).map(([p, d]) => `${p} ${d}`).join(" · ") || "–"}
                {Object.keys(t.plan_until).length > 0 && ` · ESA plan published until ${Object.entries(t.plan_until).map(([p, d]) => `${p} ${d}`).join(", ")}`}
              </div>
              {t.note && <div className="mt-1 text-[11.5px] text-warn">{t.note}</div>}
            </div>
          ))}
        </Panel>

        <Panel className="p-4">
          <div className="text-[14px] font-semibold">Scheduled run</div>
          <div className="mt-0.5 text-[12px] text-muted">
            Runs <span className="font-mono">geoeyes run {name}</span> on this machine (Windows Task Scheduler, while you are logged on): new acquisitions are
            downloaded and only what changed is processed.
          </div>
          {!s.supported ? (
            <div className="mt-3 text-[13px] text-muted">Not available on this system (use cron).</div>
          ) : (
            <>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <select className={field} value={freq} onChange={(e) => setFreq(e.target.value)} aria-label="Frequency">
                  <option value="off">off</option>
                  <option value="daily">every day</option>
                  <option value="weekly">every week</option>
                </select>
                {freq === "weekly" && (
                  <select className={field} value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day">
                    {DAYS.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                )}
                {freq !== "off" && <input type="time" className={field} value={time} onChange={(e) => setTime(e.target.value)} aria-label="Time" />}
                <Button variant="primary" disabled={sched.isPending} onClick={() => sched.mutate()}>
                  {sched.isPending ? "Saving…" : "Save"}
                </Button>
              </div>
              {sched.error && <div className="mt-2 text-[12px] text-bad">{(sched.error as Error).message}</div>}
              <div className="mt-3 text-[12.5px] text-ink-2">
                {s.enabled ? (
                  <>
                    <Chip status="ok" label={`scheduled · ${s.schedule ?? ""}`} /> next run <span className="font-mono">{s.next_run}</span>
                    {s.last_run && !s.last_run.startsWith("N/A") && s.last_run !== "11/30/1999 12:00:00 AM" && (
                      <> · last <span className="font-mono">{s.last_run}</span> (result {s.last_result})</>
                    )}
                  </>
                ) : (
                  <span className="text-muted">No scheduled run.</span>
                )}
              </div>
            </>
          )}
        </Panel>
      </div>

      <Panel className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="text-[14px] font-semibold">Deformation alerts</div>
            <div className="mt-0.5 text-[12px] text-muted">Checked on the latest product of each track (after every run, and here). Saved in project.toml [postprocess.alerts].</div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button onClick={() => setRules((rs) => [...rs, { name: `rule ${rs.length + 1}`, kind: "velocity_below", threshold: -20, min_points: 20 }])}>
              + Rule
            </Button>
            <Button variant="primary" disabled={!dirty || saveRules.isPending} onClick={() => saveRules.mutate()}>
              {saveRules.isPending ? "Saving…" : "Save rules"}
            </Button>
          </div>
        </div>
        {saveRules.error && <div className="mt-2 text-[12px] text-bad">{(saveRules.error as Error).message}</div>}
        {rules.length === 0 ? (
          <div className="mt-3 text-[13px] text-muted">No rule. Example: points moving away from the satellite faster than 20 mm/yr, at least 20 of them.</div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[820px] text-[12.5px]">
              <thead>
                <tr className="text-left text-muted">
                  {["Name", "Condition", "mm/yr", "Min. points", "Area (W, S, E, N; empty = all)", "Latest product", ""].map((h) => (
                    <th key={h} className="px-2 py-1.5 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rules.map((r, i) => {
                  const res = m.alerts.filter((a) => a.name === r.name);
                  return (
                    <tr key={i} className="border-t border-line align-top">
                      <td className="px-2 py-2"><input className={`${field} w-44`} value={r.name} onChange={(e) => upd(i, { name: e.target.value })} aria-label="Rule name" /></td>
                      <td className="px-2 py-2">
                        <select className={field} value={r.kind} onChange={(e) => upd(i, { kind: e.target.value as AlertRule["kind"] })} aria-label="Condition">
                          <option value="velocity_below">velocity ≤ (away)</option>
                          <option value="velocity_above">velocity ≥ (toward)</option>
                        </select>
                      </td>
                      <td className="px-2 py-2"><input type="number" step="any" className={`${field} w-20`} value={r.threshold} onChange={(e) => upd(i, { threshold: Number(e.target.value) })} aria-label="Threshold" /></td>
                      <td className="px-2 py-2"><input type="number" min={1} className={`${field} w-20`} value={r.min_points} onChange={(e) => upd(i, { min_points: Number(e.target.value) })} aria-label="Minimum points" /></td>
                      <td className="px-2 py-2">
                        <input
                          className={`${field} w-56`}
                          placeholder="whole product"
                          defaultValue={r.bbox?.join(", ") ?? ""}
                          onBlur={(e) => {
                            const v = e.target.value.split(",").map((x) => parseFloat(x)).filter(Number.isFinite);
                            upd(i, { bbox: v.length === 4 ? v : undefined });
                          }}
                          aria-label="Area"
                        />
                      </td>
                      <td className="px-2 py-2">
                        {res.length === 0 && <span className="text-faint">save to check</span>}
                        {res.map((a) => (
                          <div key={a.track} className="flex flex-wrap items-center gap-2">
                            <Chip status={a.triggered ? "failed" : "ok"} label={a.triggered ? "triggered" : "quiet"} />
                            <span className="text-ink-2">
                              {fmt.int(a.n)} of {fmt.int(a.of)} pts{a.worst != null ? ` · worst ${fmt.vel(a.worst)}` : ""}
                            </span>
                            {a.triggered && a.lon != null && (
                              <button type="button" className="text-accent hover:underline" onClick={() => showProduct(name, a.product, { open: true })}>
                                map
                              </button>
                            )}
                          </div>
                        ))}
                      </td>
                      <td className="px-2 py-2">
                        <button type="button" className="text-faint hover:text-bad" onClick={() => setRules((rs) => rs.filter((_, k) => k !== i))} aria-label="Remove rule">
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
