// Shared parts of the chapters of the Principles page (pages/Learn.tsx, pages/LearnHazard.tsx): the chapter switch,
// the numbered list of steps, and the boxes of explanations.
import type { ReactNode } from "react";
import { t } from "../i18n";
import { href } from "../state";

export const CHAPTERS = [
  { id: "pair", title: "One interferometric pair", sub: "From two single scenes to a velocity" },
  { id: "hazard", title: "Hazard zoning", sub: "From InSAR cells to a hazard map, with rainfall and groundwater" },
  { id: "behaviour", title: "Kinds of motion and risk", sub: "How each place moves, and what it means for the buildings" },
  { id: "lines", title: "Infrastructure and consolidation", sub: "Profiles along dykes, railways and roads; settlement still to come" },
  { id: "geometry", title: "Two geometries and soft soil", sub: "Vertical and east-west motion; the soft layer that sinks" },
  { id: "ionosphere", title: "Ionosphere", sub: "Recognise its ramps, remove them by split-spectrum, and the subswath seams" },
] as const;
export type ChapterId = (typeof CHAPTERS)[number]["id"];

/** The chapters, the current one open with its steps. */
export function ChapterNav({ current, steps, step, onStep, children }: { current: ChapterId; steps: string[]; step: number; onStep: (i: number) => void; children?: ReactNode }) {
  return (
    <nav className="w-[260px] flex-none overflow-y-auto border-r border-line bg-panel-2 p-3" aria-label={t("InSAR principles")}>
      <div className="text-[10.5px] font-semibold tracking-[1.2px] text-muted uppercase">{t("InSAR principles")}</div>
      <ol className="mt-2 space-y-2">
        {CHAPTERS.map((c, ci) => {
          const on = c.id === current;
          return (
            <li key={c.id}>
              <a
                href={c.id === "pair" ? href({ page: "learn" }) : href({ page: "learn", chapter: c.id, step: 0 })}
                className={`block rounded-lg border px-2.5 py-2 no-underline ${on ? "border-line-2 bg-raised" : "border-transparent hover:bg-raised/60"}`}
              >
                <span className={`text-[12.5px] font-semibold ${on ? "text-ink" : "text-muted"}`}>
                  {t("Chapter {n}", { n: ci + 1 })} · {t(c.title)}
                </span>
                <span className="mt-0.5 block text-[11.5px] leading-snug text-faint">{t(c.sub)}</span>
              </a>
              {on && (
                <ol className="mt-1.5 space-y-0.5 pl-1">
                  {steps.map((s, i) => (
                    <li key={s}>
                      <button
                        type="button"
                        onClick={() => onStep(i)}
                        className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] ${i === step ? "bg-raised font-semibold text-ink" : "text-muted hover:bg-raised/60 hover:text-ink"}`}
                      >
                        <span
                          className={`mt-px flex h-5 w-5 flex-none items-center justify-center rounded-full text-[10.5px] ${i < step ? "bg-good-bg text-good-ink" : i === step ? "bg-accent-2 text-white" : "bg-chip text-faint"}`}
                        >
                          {i}
                        </span>
                        <span>{t(s)}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </li>
          );
        })}
      </ol>
      {children}
    </nav>
  );
}

/** A numbered section of a lesson. */
function LessonPart({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="mt-7">
      <h2 className="m-0 flex items-center gap-2.5 text-[16px] font-semibold text-ink">
        <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-chip font-mono text-[12px] text-accent-ink">{n}</span>
        {t(title)}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** One step of a chapter of the Principles page, in the order a newcomer learns it: the goal, the idea in words,
 * what it looks like on real data, the formula and its symbols, what to check, and the deeper material folded away.
 * ``sidebar``: data choice, controls and numbers (sticky beside the lesson on wide screens). */
export function Lesson({
  chapter,
  step,
  total,
  title,
  goal,
  status,
  idea,
  figures,
  formula,
  symbols,
  look,
  lookExtra,
  deeper,
  doc,
  titles,
  onStep,
  sidebar,
}: {
  chapter: number;
  step: number;
  total: number;
  title: string;
  goal: string;
  status?: ReactNode;
  idea: string[];
  figures?: ReactNode;
  formula?: string[];
  symbols?: [string, string, string][];
  look: string[];
  lookExtra?: ReactNode;
  deeper?: ReactNode;
  doc?: ReactNode;
  titles: string[];
  onStep: (i: number) => void;
  sidebar?: ReactNode;
}) {
  let n = 0;
  const part = () => (n += 1);
  return (
    <article className="mx-auto max-w-[1240px] px-6 py-5">
      <div className="flex items-center gap-3 text-[12px] text-faint">
        <span>{t("Chapter {c} · step {i} of {n}", { c: chapter, i: step, n: total - 1 })}</span>
        <div className="h-1.5 w-40 overflow-hidden rounded-full bg-chip" aria-hidden>
          <div className="h-full rounded-full bg-accent-2" style={{ width: `${(100 * (step + 1)) / total}%` }} />
        </div>
        {status}
      </div>
      <h1 className="m-0 mt-1.5 text-[26px] font-bold tracking-tight">{t(title)}</h1>
      <div className="mt-3 max-w-[860px] rounded-lg border-l-4 border-accent bg-accent-bg px-4 py-2.5">
        <div className="text-[10.5px] font-semibold tracking-[1.2px] text-accent-ink uppercase">{t("Goal of this step")}</div>
        <p className="m-0 mt-0.5 text-[14.5px] leading-relaxed text-ink">{t(goal)}</p>
      </div>
      <div className="grid gap-x-8 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <LessonPart n={part()} title="The idea">
            <div className="flex max-w-[820px] flex-col gap-3 text-[14.5px] leading-relaxed text-ink-2">
              {idea.map((w) => (
                <p key={w} className="m-0">
                  {t(w)}
                </p>
              ))}
            </div>
          </LessonPart>
          {figures && (
            <LessonPart n={part()} title="See it on real data">
              {figures}
            </LessonPart>
          )}
          {formula && formula.length > 0 && (
            <LessonPart n={part()} title="The formula">
              <div className="max-w-[860px] rounded-lg border-l-4 border-accent bg-panel px-4 py-3 font-mono text-[14px] leading-loose whitespace-pre-wrap text-ink">
                {formula.map((f) => (
                  <div key={f}>{t(f)}</div>
                ))}
              </div>
              {symbols && symbols.length > 0 && (
                <div className="mt-3 max-w-[860px] overflow-x-auto">
                  <div className="mb-1 text-[11px] font-semibold tracking-[1.2px] text-muted uppercase">{t("Reading the formula")}</div>
                  <table className="w-full border-collapse text-[12.5px]">
                    <tbody>
                      {symbols.map((r) => (
                        <tr key={r[0]} className="align-top">
                          <td className="border-b border-line py-1.5 pr-3 font-mono whitespace-nowrap text-ink">{r[0]}</td>
                          <td className="border-b border-line py-1.5 pr-3 text-ink-2">{t(r[1])}</td>
                          <td className="border-b border-line py-1.5 text-muted">{t(r[2])}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </LessonPart>
          )}
          <LessonPart n={part()} title="Check yourself">
            <div className="max-w-[860px] rounded-lg border border-accent-line bg-accent-bg px-4 py-3">
              <ul className="m-0 list-none space-y-1.5 p-0 text-[14px] leading-relaxed text-ink-2">
                {look.map((w) => (
                  <li key={w} className="flex gap-2.5">
                    <span aria-hidden className="mt-[3px] flex h-4 w-4 flex-none items-center justify-center rounded border border-accent-line text-[10px] text-accent-ink">✓</span>
                    <span>{t(w)}</span>
                  </li>
                ))}
              </ul>
              {lookExtra}
            </div>
          </LessonPart>
          {deeper && (
            <details className="group mt-7">
              <summary className="flex cursor-pointer list-none items-center gap-2.5 text-[16px] font-semibold text-ink [&::-webkit-details-marker]:hidden">
                <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-chip font-mono text-[12px] text-accent-ink">{part()}</span>
                {t("Going deeper")}
                <span className="text-[12.5px] font-normal text-muted">{t("derivation, assumptions, parameters, literature")}</span>
                <span className="ml-auto text-muted transition-transform group-open:rotate-90">›</span>
              </summary>
              <div className="mt-3">{deeper}</div>
            </details>
          )}
          {doc && <div className="mt-7 text-[12px] text-faint">{doc}</div>}
          <nav className="mt-5 mb-8 grid gap-2 border-t border-line pt-4 sm:grid-cols-2">
            {step > 0 ? (
              <button type="button" onClick={() => onStep(step - 1)} className="rounded-lg border border-line px-4 py-2.5 text-left hover:border-line-2 hover:bg-panel">
                <div className="text-[11px] text-faint">← {t("Previous")}</div>
                <div className="text-[13.5px] font-semibold text-ink-2">{t(titles[step - 1])}</div>
              </button>
            ) : (
              <span />
            )}
            {step < total - 1 && (
              <button type="button" onClick={() => onStep(step + 1)} className="rounded-lg border border-accent-line bg-accent-bg px-4 py-2.5 text-right hover:bg-accent-bg-2">
                <div className="text-[11px] text-accent-ink">{t("Next")} →</div>
                <div className="text-[13.5px] font-semibold text-ink">{t(titles[step + 1])}</div>
              </button>
            )}
          </nav>
        </div>
        {sidebar && <aside className="mt-7 space-y-3 xl:sticky xl:top-4 xl:self-start">{sidebar}</aside>}
      </div>
    </article>
  );
}

export function Box({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-panel p-3">
      <h3 className="m-0 text-[10.5px] font-semibold tracking-[1.2px] text-muted uppercase">{t(title)}</h3>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

/** The explanation column of a step: what happens, the formula, what to look for. */
export function Explain({ what, formula, look, extra }: { what: string[]; formula?: string[]; look: string[]; extra?: ReactNode }) {
  return (
    <aside className="space-y-3">
      <Box title="What happens">
        <ul className="m-0 list-disc space-y-1 pl-4 text-[12.5px] leading-snug text-ink-2">
          {what.map((w) => (
            <li key={w}>{t(w)}</li>
          ))}
        </ul>
      </Box>
      {formula && (
        <Box title="Formula">
          <div className="space-y-1 font-mono text-[12.5px] text-ink">
            {formula.map((f) => (
              <div key={f}>{t(f)}</div>
            ))}
          </div>
        </Box>
      )}
      <Box title="What to look for">
        <ul className="m-0 list-disc space-y-1 pl-4 text-[12.5px] leading-snug text-ink-2">
          {look.map((w) => (
            <li key={w}>{t(w)}</li>
          ))}
        </ul>
      </Box>
      {extra}
    </aside>
  );
}
