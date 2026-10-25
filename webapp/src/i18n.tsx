// Interface language (English / Vietnamese). The English text is the key: t("Run again") returns the Vietnamese
// translation when the language is "vi" and one exists, else the English text. Variables: t("{n} points", { n }).
// Server messages (warnings, reasons) are translated by patterns (i18n/vi/server.ts).
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { VI, VI_PATTERNS } from "./i18n/vi";

export type Lang = "en" | "vi";
const KEY = "geoeyes.lang";

function initial(): Lang {
  try {
    const s = localStorage.getItem(KEY);
    if (s === "en" || s === "vi") return s;
  } catch {
    /* storage unavailable */
  }
  return typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("vi") ? "vi" : "en";
}

let current: Lang = initial();

function fill(s: string, vars?: Record<string, string | number | null | undefined>): string {
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? m : String(vars[k]))) : s;
}

/** Translation of an interface text (the English text is the key). */
export function t(en: string, vars?: Record<string, string | number | null | undefined>): string {
  return fill(current === "vi" ? (VI[en] ?? en) : en, vars);
}

/** Translation of a message from the server (English sentences with values in them), by patterns. */
export function ts(msg: string): string {
  if (current !== "vi" || !msg) return msg;
  if (VI[msg]) return VI[msg];
  for (const [re, out] of VI_PATTERNS) {
    if (re.test(msg)) return msg.replace(re, out);
  }
  return msg;
}

export function lang(): Lang {
  return current;
}

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: current, setLang: () => {} });

/** Re-renders the whole app (key) when the language changes. */
export function LangProvider({ children }: { children: ReactNode }) {
  const [l, setL] = useState<Lang>(current);
  const setLang = useCallback((v: Lang) => {
    current = v;
    try {
      localStorage.setItem(KEY, v);
    } catch {
      /* storage unavailable */
    }
    document.documentElement.lang = v;
    setL(v);
  }, []);
  return (
    <Ctx.Provider value={{ lang: l, setLang }}>
      <div key={l} className="contents">
        {children}
      </div>
    </Ctx.Provider>
  );
}

export function useLang() {
  return useContext(Ctx);
}

export function LangSwitch() {
  const { lang: l, setLang } = useLang();
  return (
    <div className="flex rounded-md border border-line-2 p-0.5" role="group" aria-label="Language / Ngôn ngữ">
      {(["vi", "en"] as Lang[]).map((v) => (
        <button
          key={v}
          type="button"
          onClick={() => setLang(v)}
          aria-pressed={l === v}
          className={`h-6 rounded px-2 text-[11.5px] font-semibold uppercase ${l === v ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
        >
          {v}
        </button>
      ))}
    </div>
  );
}
