// Corner reflector reports of a project: run one, read the result (expected vs measured RCS, position, coherence).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { t, ts } from "../i18n";
import { Button, Chip, fmt, Panel } from "../ui";

export function Validation({ name }: { name: string }) {
  const qc = useQueryClient();
  const [polling, setPolling] = useState(false);
  const q = useQuery({
    queryKey: ["validation", name],
    queryFn: () => api.validation(name),
    refetchInterval: polling ? 4000 : false,
  });
  const run = useMutation({
    mutationFn: () => api.crReport(name),
    onSuccess: () => {
      setPolling(true);
      setTimeout(() => setPolling(false), 15 * 60_000);
      setTimeout(() => qc.invalidateQueries({ queryKey: ["validation", name] }), 2000);
    },
  });
  const [sel, setSel] = useState<string | null>(null);
  if (q.error) return <div className="text-bad">{(q.error as Error).message}</div>;
  if (!q.data) return <div className="text-muted">{t("Loading…")}</div>;
  const v = q.data;
  const rep = v.reports.find((r) => r.id === sel) ?? v.reports[0];

  return (
    <div className="space-y-4">
      <Panel className="flex flex-wrap items-center gap-3 px-4 py-3 text-[13px]">
        <div className="min-w-0 flex-1">
          <div className="font-semibold">{t("Corner reflectors")}</div>
          <div className="mt-0.5 text-muted">
            {v.configured ? (
              <>
                {t("Reflectors")} <span className="font-mono text-ink-2">{String(v.config.points)}</span>
                {v.config.setup ? (
                  <>
                    {" "}· {t("set-up log")} <span className="font-mono text-ink-2">{String(v.config.setup)}</span>
                  </>
                ) : null}
                {" "}· {t("identification from the Sentinel-1 bursts in the archive")}
              </>
            ) : (
              <>
                {t("Not configured: add")} <span className="font-mono">[validation.corner_reflector] points = "geom/points.csv"</span>{" "}
                {t("to project.toml (Settings → project.toml).")}
              </>
            )}
          </div>
        </div>
        <Button variant="primary" disabled={!v.configured || run.isPending || polling} onClick={() => run.mutate()}>
          {polling ? t("Report running…") : t("Build CR report")}
        </Button>
      </Panel>
      {run.error && <div className="rounded-lg bg-[#2a1414] px-3 py-2 text-[13px] text-bad">{(run.error as Error).message}</div>}
      {polling && v.log.length > 0 && (
        <pre className="max-h-48 overflow-auto rounded-xl border border-line bg-[#070c16] p-3 font-mono text-[11.5px] text-[#a9b8cf]">{v.log.join("\n")}</pre>
      )}

      {v.reports.length === 0 ? (
        <div className="text-[13px] text-muted">{t("No corner reflector report yet.")}</div>
      ) : (
        <div className="flex flex-wrap gap-4">
          <Panel className="w-full max-w-[260px] flex-none p-2">
            {v.reports.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setSel(r.id)}
                className={`block w-full rounded-md px-3 py-2 text-left text-[12.5px] ${rep?.id === r.id ? "bg-raised" : "hover:bg-[#131f35]"}`}
              >
                <div className="font-mono">{r.id.split("_")[0]}</div>
                <div className="text-muted">{r.id.split("_").slice(1).join("_")}</div>
              </button>
            ))}
          </Panel>
          {rep && (
            <div className="min-w-0 flex-[999_1_560px] space-y-4">
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-muted">
                  {t("{r} reflector(s) · {a} acquisition(s) · tolerance ±{tol} dB · generated {at}", {
                    r: rep.report.reflectors.length,
                    a: rep.report.acquisitions.length,
                    tol: rep.report.tolerance_db,
                    at: rep.report.generated_at,
                  })}
                </span>
                {rep.pdf && (
                  <a className="ml-auto text-accent hover:underline" href={api.validationFile(name, rep.id, "cr_report.pdf")} target="_blank" rel="noopener">
                    {t("Open PDF")} ↗
                  </a>
                )}
              </div>
              {rep.report.warnings.map((w) => (
                <div key={w} className="rounded-lg bg-[#2a2110] px-3 py-2 text-[12.5px] text-[#f5d08b]">{ts(w)}</div>
              ))}
              <Panel className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-[12.5px]">
                  <thead>
                    <tr className="text-left text-muted">
                      {["Reflector", "Date", "Expected dBsm", "Measured dBsm", "Difference", "SCR dB", "Offset", ""].map((h) => (
                        <th key={h} className="px-3 py-2 font-medium">{t(h)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rep.report.observations.map((o, i) => (
                      <tr key={i} className="border-t border-line" title={ts(o.setup_note ?? "")}>
                        <td className="px-3 py-2 font-mono">{o.reflector}</td>
                        <td className="px-3 py-2 font-mono">{o.date}</td>
                        <td className="px-3 py-2 font-mono">{fmt.num(o.expected_dbsm)}</td>
                        <td className="px-3 py-2 font-mono">{fmt.num(o.measured_dbsm)}</td>
                        <td className="px-3 py-2 font-mono">{fmt.vel(o.difference_db)} dB</td>
                        <td className="px-3 py-2 font-mono">{fmt.num(o.scr_db)}</td>
                        <td className="px-3 py-2 font-mono">{fmt.num(o.offset_m)} m</td>
                        <td className="px-3 py-2">
                          <Chip status={o.within_tolerance ? "ok" : "failed"} label={o.within_tolerance ? t("within tolerance") : t("outside")} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
              {rep.report.coherence.length > 0 && (
                <Panel className="overflow-x-auto">
                  <table className="w-full min-w-[520px] text-[12.5px]">
                    <thead>
                      <tr className="text-left text-muted">
                        {["Reflector", "Pair", "Coherence at the reflector", "Area median"].map((h) => (
                          <th key={h} className="px-3 py-2 font-medium">{t(h)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rep.report.coherence.map((c, i) => (
                        <tr key={i} className="border-t border-line">
                          <td className="px-3 py-2 font-mono">{c.reflector}</td>
                          <td className="px-3 py-2 font-mono">{c.date_1} → {c.date_2}</td>
                          <td className="px-3 py-2 font-mono">{fmt.num(c.at_reflector, 2)}</td>
                          <td className="px-3 py-2 font-mono">{fmt.num(c.area_median, 2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Panel>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                {rep.files
                  .filter((f) => f.endsWith(".png"))
                  .map((f) => (
                    <Panel key={f} className="overflow-hidden">
                      <img src={api.validationFile(name, rep.id, f)} alt={f.replace(".png", "").replace(/_/g, " ")} className="block w-full bg-white" />
                      <div className="px-3 py-1.5 text-[11.5px] text-muted">{f}</div>
                    </Panel>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
