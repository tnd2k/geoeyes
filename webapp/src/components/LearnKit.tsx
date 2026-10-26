// Shared parts of the chapters of the Principles page (pages/Learn.tsx, pages/LearnHazard.tsx): the chapter switch,
// the numbered list of steps, and the boxes of explanations.
import type { ReactNode } from "react";
import { t } from "../i18n";
import { href } from "../state";

export const CHAPTERS = [
  { id: "pair", title: "One interferometric pair", sub: "From two single scenes to a velocity" },
  { id: "hazard", title: "Hazard zoning", sub: "From InSAR cells to a hazard map, with rainfall and groundwater" },
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
                href={c.id === "hazard" ? href({ page: "learn", chapter: "hazard", step: 0 }) : href({ page: "learn" })}
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
                          className={`mt-px flex h-5 w-5 flex-none items-center justify-center rounded-full text-[10.5px] ${i < step ? "bg-[#1f4d36] text-[#8fe3b0]" : i === step ? "bg-accent-2 text-white" : "bg-[#1a2740] text-faint"}`}
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
