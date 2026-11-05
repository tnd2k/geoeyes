// Stack tab of a project: the coregistered stack before any PS processing (processing.stack.qc). Per date against
// the reference: amplitude, wrapped interferogram, coherence, and the offset left by the coregistration.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type StackQcDate } from "../api";
import { t, ts } from "../i18n";
import { Button, fmt, Panel } from "../ui";

/** good / review / bad of one figure, for the table colours. */
function grade(r: StackQcDate): { offset: string; coh: string } {
  const off = Math.max(Math.abs(r.offset_lines ?? 0), Math.abs(r.offset_samples ?? 0));
  return {
    offset: off <= 0.1 ? "text-good" : off <= 1 ? "text-warn" : "text-bad",
    coh: (r.coherence_mean ?? 0) >= 0.4 ? "text-good" : (r.coherence_mean ?? 0) >= 0.2 ? "text-warn" : "text-bad",
  };
}

function Ramp({ kind }: { kind: "phase" | "coh" }) {
  const g =
    kind === "phase"
      ? "linear-gradient(90deg,#e2d9e2,#9e7dbf,#3b2f80,#2f1436,#7a1e2e,#c46a3e,#e2d9e2)"
      : "linear-gradient(90deg,#000004,#51127c,#b73779,#fc8961,#fcfdbf)";
  return (
    <div className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted">
      <span>{kind === "phase" ? "−π" : "0"}</span>
      <span className="h-2 flex-1 rounded" style={{ background: g }} />
      <span>{kind === "phase" ? "+π" : "1"}</span>
    </div>
  );
}

export function StackQc({ name }: { name: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["stacks", name], queryFn: () => api.stacks(name) });
  const stacks = q.data?.stacks ?? [];
  const [sid, setSid] = useState("");
  const stack = stacks.find((s) => s.stack_id === sid) ?? stacks[stacks.length - 1];
  const r = stack?.qc ?? null;
  const [pick, setPick] = useState("");
  const rows = r?.dates ?? [];
  const sel = rows.find((x) => x.date === pick && !x.reference) ?? rows.find((x) => !x.reference);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const run = async () => {
    if (!stack) return;
    setErr("");
    setBusy(true);
    try {
      await api.stackQcRun(name, stack.stack_id);
      await qc.invalidateQueries({ queryKey: ["stacks", name] });
    } catch (e) {
      setErr(ts((e as Error).message));
    } finally {
      setBusy(false);
    }
  };
  // which phase the panels show: the stack's own ("raw"), or the phase-linked one, the point engine's input then
  const [view, setView] = useState<"raw" | "linked">("linked");
  const lk = !!r?.linked && view === "linked";
  const img = (kind: "amp" | "ifg" | "coh", date: string) =>
    api.stackQcUrl(name, stack!.stack_id, `${kind}${lk && kind !== "amp" ? "L" : ""}_${date}.png`, r?.created);
  const uw = stack?.unwrap_qc ?? null;
  const uwRow = uw && sel ? uw.dates.find((x) => x.date === sel.date) : undefined;

  return (
    <div className="mb-6 space-y-4">
      <Panel className="px-4 py-3 text-[13px]">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{t("Stack quality check")}</div>
            <div className="mt-0.5 text-muted">
              {t(
                "Every date against the reference before any PS processing: amplitude, wrapped interferogram (geometric phase removed) and coherence, and the offset left by the coregistration. A good stack: offsets below 0.1 pixel, amplitude correlations close to the best pair, fringes or a smooth phase where the coherence is high.",
              )}
            </div>
          </div>
          {stacks.length > 1 && (
            <select value={stack?.stack_id ?? ""} onChange={(e) => setSid(e.target.value)} aria-label={t("Stack")} className="h-8 rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink">
              {stacks.map((s) => (
                <option key={s.stack_id} value={s.stack_id}>
                  {s.stack_id}
                </option>
              ))}
            </select>
          )}
          <Button variant="primary" disabled={!stack || busy} onClick={run}>
            {busy ? t("Checking… (a minute or two)") : r ? t("Check again") : t("Check the stack")}
          </Button>
        </div>
        {!stack && !q.isLoading && <div className="mt-2 text-muted">{t("No stack yet: run the project up to build_stack.")}</div>}
        {err && <div className="mt-2 text-[12.5px] text-bad">{err}</div>}
        {r && stack && new Date(r.created).getTime() / 1000 < stack.modified - 60 && (
          <div className="mt-2 rounded-md bg-warn-bg px-2 py-1 text-[12.5px] text-warn-ink">{t("The stack was rebuilt after this check: check it again.")}</div>
        )}
      </Panel>

      {r && stack && (
        <>
          <Panel className="overflow-x-auto p-0">
            <table className="w-full min-w-[760px] text-[12.5px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] tracking-[0.8px] text-muted uppercase">
                  {["Date", "Days", "Bperp", "Height of ambiguity", "Coherence (mean / p90)", "Offset left (lines / samples)", "Amplitude corr."].map((h) => (
                    <th key={h} className="px-3 py-2 font-semibold">
                      {t(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((x) => {
                  const g = grade(x);
                  return (
                    <tr
                      key={x.date}
                      onClick={() => !x.reference && setPick(x.date)}
                      className={`border-b border-line/60 ${x.reference ? "" : "cursor-pointer hover:bg-panel-3"} ${sel?.date === x.date ? "bg-raised" : ""}`}
                    >
                      <td className="px-3 py-2 font-mono">{x.date}</td>
                      <td className="px-3 py-2 font-mono">{x.days}</td>
                      {x.reference ? (
                        <td colSpan={5} className="px-3 py-2 text-muted">
                          {t("reference")}
                        </td>
                      ) : (
                        <>
                          <td className="px-3 py-2 font-mono">{fmt.int(Math.round(x.bperp_m))} m</td>
                          <td className="px-3 py-2 font-mono">{x.height_of_ambiguity_m != null ? `${fmt.num(x.height_of_ambiguity_m, 2)} m` : "–"}</td>
                          <td className={`px-3 py-2 font-mono ${g.coh}`}>
                            {fmt.num(x.coherence_mean, 2)} / {fmt.num(x.coherence_p90, 2)}
                            {x.coherence_linked_mean != null && <span className="text-muted"> · {t("linked")} {fmt.num(x.coherence_linked_mean, 2)}</span>}
                          </td>
                          <td className={`px-3 py-2 font-mono ${g.offset}`}>
                            {fmt.num(x.offset_lines, 2)} / {fmt.num(x.offset_samples, 2)}
                          </td>
                          <td className="px-3 py-2 font-mono">{fmt.num(x.amplitude_corr, 2)}</td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="px-3 py-2 text-[11px] text-faint">
              {t("Looks {ly} × {lx} of {ny} × {nx} pixels; offsets and amplitude correlation on the central crop at full resolution. {o}", {
                ly: r.looks[0],
                lx: r.looks[1],
                ny: fmt.int(r.shape[0]),
                nx: fmt.int(r.shape[1]),
                o: ts(r.orientation),
              })}
            </div>
          </Panel>

          {sel && (
            <Panel className="px-4 py-3 text-[13px]">
              {r.linked && (
                <div className="mb-2 flex w-fit rounded-md border border-line-2 p-0.5">
                  {(["raw", "linked"] as const).map((v) => (
                    <button
                      key={v}
                      type="button"
                      aria-pressed={view === v}
                      onClick={() => setView(v)}
                      className={`h-6 rounded px-2.5 text-[12px] ${view === v ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
                    >
                      {v === "raw" ? t("Raw phase") : t("After phase linking (input of the point engine)")}
                    </button>
                  ))}
                </div>
              )}
              <div className="mb-2 font-semibold">
                {r.reference_date} × {sel.date}
                <span className="ml-2 font-normal text-muted">
                  Bperp {fmt.int(Math.round(sel.bperp_m))} m · {t("{d} days", { d: Math.abs(sel.days - (rows.find((x) => x.reference)?.days ?? 0)) })}
                </span>
              </div>
              <div className={`grid gap-3 ${uwRow ? "md:grid-cols-2 xl:grid-cols-4" : "md:grid-cols-3"}`}>
                {(
                  [
                    ["amp", t("Amplitude ({d})", { d: sel.date })],
                    ["ifg", t("Interferogram (wrapped, Gaussian-smoothed)")],
                    ["coh", t("Coherence")],
                  ] as const
                ).map(([k, label]) => (
                  <figure key={k} className="min-w-0">
                    <figcaption className="mb-1 text-[12px] text-muted">{label}</figcaption>
                    <a href={img(k, sel.date)} target="_blank" rel="noreferrer">
                      <img src={img(k, sel.date)} alt={label} className="w-full rounded border border-line bg-deep" style={{ imageRendering: "pixelated" }} />
                    </a>
                    {k === "ifg" && <Ramp kind="phase" />}
                    {k === "coh" && <Ramp kind="coh" />}
                  </figure>
                ))}
                {uwRow && uw && (
                  <figure className="min-w-0">
                    <figcaption className="mb-1 text-[12px] text-muted" title={t("The filtered phase of the cells holding selected points, on the unwrapping grid: exactly what the unwrapping receives ({label})", { label: uw.label })}>
                      {t("Wrapped phase before unwrapping")}
                      {uwRow.jump_frac != null && <span className={uwRow.jump_frac <= 0.15 ? "text-good" : uwRow.jump_frac <= 0.3 ? "text-warn" : "text-bad"}> · {t("jumps {p} %", { p: Math.round(uwRow.jump_frac * 100) })}</span>}
                    </figcaption>
                    <a href={api.psrunQcUrl(name, stack.ps_run, `uw_${sel.date}.png`, uw.created)} target="_blank" rel="noreferrer">
                      <img src={api.psrunQcUrl(name, stack.ps_run, `uw_${sel.date}.png`, uw.created)} alt={t("Wrapped phase before unwrapping")} className="w-full rounded border border-line bg-deep" style={{ imageRendering: "pixelated" }} />
                    </a>
                    <Ramp kind="phase" />
                  </figure>
                )}
              </div>
              {sel && !uwRow && (
                <div className="mt-2 text-[11px] text-faint">{t("The wrapped phase that the unwrapping receives appears here after a run of the ps phase.")}</div>
              )}
              {uw && uwRow && (
                <div className="mt-1 text-[11px] text-faint">
                  {t("Unwrapping grid of the last ps run: {cells} cells ({label}), north up; jumps = neighbouring cells whose phase differs by more than π/2 (noise ≈ 50 %).", { cells: fmt.int(uw.cells), label: uw.label })}
                </div>
              )}
              <div className="mt-2 text-[11px] text-faint">{t("Click an image to open it at full size.")}</div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
