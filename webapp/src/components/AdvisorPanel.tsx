// The site advisor (geoeyes/advisor, `geoeyes advise`): what the area is like, which rules apply and the values they
// suggest, each with its reason. Plain rules on measured site properties; nothing here calls a language model.
import { useState } from "react";
import type { Advice, AdviceSuggestion } from "../api";
import { lang, t } from "../i18n";
import { Button } from "../ui";

export function showValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

/** One suggestion under a form field: the value, the rule and why; "use" puts it in the draft. */
export function FieldSuggestion({ s, matches, onUse }: { s: AdviceSuggestion; matches: boolean; onUse: () => void }) {
  const why = lang() === "vi" ? s.why.vi : s.why.en;
  return (
    <div className={`mt-1 text-[11.5px] leading-snug ${matches ? "text-good" : "text-warn"}`} title={why}>
      {matches ? "✓ " : ""}
      {t("Advisor: {v}", { v: showValue(s.value) })} <span className="font-mono text-faint">[{s.rule}]</span>
      {!matches && (
        <button type="button" className="ml-2 text-accent-ink hover:underline" onClick={onUse}>
          {t("use")}
        </button>
      )}
      <div className="text-faint">{why}</div>
    </div>
  );
}

/** The advisor panel: site summary, suggested changes (use one / use all), notes, values no rule explains. */
export function AdvisorPanel({
  advice,
  loading,
  error,
  onUse,
  onUseAll,
  onRefresh,
}: {
  advice?: Advice;
  loading: boolean;
  error?: Error | null;
  onUse?: (path: string, value: unknown) => void;
  onUseAll?: (changes: Record<string, unknown>) => void;
  onRefresh?: () => void;
}) {
  const [open, setOpen] = useState(true);
  const vi = lang() === "vi";
  const cmp = advice?.compare ?? null;
  const changes = cmp?.changes ?? [];
  const why = (rule: string) => {
    const m = advice?.matched.find((x) => x.id === rule);
    return m ? (vi ? m.why.vi : m.why.en) : "";
  };
  return (
    <div className="rounded-xl border border-line bg-panel">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-4 py-3 text-left" aria-expanded={open}>
        <span className="text-[14px] font-semibold">{t("Site advisor")}</span>
        <span className="text-[11.5px] text-faint">{t("rules on the measured site, no AI")}</span>
        {cmp && (
          <span className={`text-[12px] ${changes.length ? "text-warn" : "text-good"}`}>
            {changes.length ? t("{n} suggested change(s)", { n: changes.length }) : t("settings already as the rules say")}
          </span>
        )}
        <span className="ml-auto text-muted">{open ? "–" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-line px-4 py-3 text-[12.5px]">
          {loading && <div className="text-muted">{t("Measuring the site (relief, land cover, geology, climate)… the first time takes about 10 s.")}</div>}
          {error && <div className="text-bad">{error.message}</div>}
          {advice && (
            <>
              <pre className="whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-ink-2">{(vi ? advice.summary.vi : advice.summary.en).join("\n")}</pre>

              {cmp ? (
                changes.length > 0 && (
                  <div>
                    <div className="mb-1 flex items-center gap-2 font-medium">
                      {t("Suggested changes")}
                      {onUseAll && (
                        <Button onClick={() => onUseAll(Object.fromEntries(changes.map((c) => [c.path, c.suggested])))}>{t("Put all in the form")}</Button>
                      )}
                    </div>
                    <table className="w-full text-[12px]">
                      <tbody>
                        {changes.map((c) => (
                          <tr key={c.path} className="border-t border-line align-top">
                            <td className="py-1 pr-3 font-mono text-ink-2">{c.path}</td>
                            <td className="py-1 pr-3 whitespace-nowrap">
                              <span className="text-faint">{showValue(c.current)}</span> → <span className="font-medium text-warn">{showValue(c.suggested)}</span>
                            </td>
                            <td className="py-1 pr-3 text-faint">
                              <span className="font-mono">[{c.rule}]</span> {why(c.rule)}
                            </td>
                            <td className="py-1 text-right">
                              {onUse && (
                                <button type="button" className="text-accent-ink hover:underline" onClick={() => onUse(c.path, c.suggested)}>
                                  {t("use")}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              ) : (
                advice.recipe.length > 0 && (
                  <div>
                    <div className="mb-1 font-medium">{t("Suggested values")}</div>
                    <table className="w-full text-[12px]">
                      <tbody>
                        {advice.recipe.map((s) => (
                          <tr key={s.path} className="border-t border-line align-top">
                            <td className="py-1 pr-3 font-mono text-ink-2">{s.path}</td>
                            <td className="py-1 pr-3 font-medium">{showValue(s.value)}</td>
                            <td className="py-1 text-faint">
                              <span className="font-mono">[{s.rule}]</span> {vi ? s.why.vi : s.why.en}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              )}

              {cmp && cmp.agree.length > 0 && (
                <div className="text-good">
                  {t("Already as the rules say:")} <span className="font-mono text-[11.5px]">{cmp.agree.map((a) => a.path).join(", ")}</span>
                </div>
              )}

              {advice.notes.length > 0 && (
                <div>
                  <div className="mb-1 font-medium">{t("Notes")}</div>
                  <ul className="list-disc space-y-1 pl-5 text-ink-2">
                    {advice.notes.map((n) => (
                      <li key={n.rule}>
                        <span className="font-mono text-[11.5px] text-faint">[{n.rule}]</span> {vi ? n.text.vi : n.text.en}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {cmp && (cmp.ignored ?? []).length > 0 && (
                <div className="text-bad">
                  {t("Not read by the engine (ignored; move or remove):")}{" "}
                  <span className="font-mono text-[11.5px]">
                    {(cmp.ignored ?? []).map((i) => `[ps] ${i.path.slice(3)} = ${showValue(i.value)}${i.did_you_mean ? ` → ${i.did_you_mean}?` : ""}`).join("; ")}
                  </span>
                </div>
              )}

              {cmp && cmp.unexplained.length > 0 && (
                <div className="text-faint">
                  {t("Set in project.toml, no rule (project-specific, or a rule to write):")}{" "}
                  <span className="font-mono text-[11.5px]">{cmp.unexplained.map((u) => `${u.path} = ${showValue(u.value)}`).join("; ")}</span>
                </div>
              )}

              {Object.keys(advice.skipped).length > 0 && (
                <div className="text-faint">
                  {t("Not evaluated (no value in the profile):")} <span className="font-mono text-[11.5px]">{Object.keys(advice.skipped).join(", ")}</span>
                </div>
              )}

              {onRefresh && (
                <div>
                  <button type="button" className="text-[11.5px] text-muted hover:text-ink" onClick={onRefresh}>
                    {t("Measure the site again")}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
