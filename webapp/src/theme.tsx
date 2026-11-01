// Colour theme of the interface (index.css: the --c-* variables of each [data-theme]). Data colours (velocity
// scales, viridis, categories) do not change with the theme. Canvas drawings and uPlot cannot read CSS variables:
// they take the colour with themeColor() when they draw, and the whole app is re-mounted (key) when the theme changes.
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { t } from "./i18n";

export const THEMES = [
  { id: "ocean", label: "Ocean", swatch: ["#0a1a1f", "#2ee6c5"] },
  { id: "night", label: "Night", swatch: ["#0b1220", "#4cc2ff"] },
  { id: "light", label: "Light", swatch: ["#f3f6fa", "#0b84c6"] },
] as const;
export type Theme = (typeof THEMES)[number]["id"];
const KEY = "geoeyes.theme";

function initial(): Theme {
  try {
    const s = localStorage.getItem(KEY);
    if (THEMES.some((x) => x.id === s)) return s as Theme;
  } catch {
    /* storage unavailable */
  }
  return "ocean";
}

let current: Theme = initial();
document.documentElement.dataset.theme = current;

export function theme(): Theme {
  return current;
}

/** The value of a theme colour (e.g. "muted", "accent"), for canvas and uPlot. */
export function themeColor(token: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--c-${token}`).trim() || "#888";
}

const Ctx = createContext<{ theme: Theme; setTheme: (v: Theme) => void }>({ theme: current, setTheme: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [th, setTh] = useState<Theme>(current);
  const setTheme = useCallback((v: Theme) => {
    current = v;
    try {
      localStorage.setItem(KEY, v);
    } catch {
      /* storage unavailable */
    }
    document.documentElement.dataset.theme = v;
    setTh(v);
  }, []);
  return (
    <Ctx.Provider value={{ theme: th, setTheme }}>
      <div key={th} className="contents">
        {children}
      </div>
    </Ctx.Provider>
  );
}

export function ThemeSwitch() {
  const { theme: th, setTheme } = useContext(Ctx);
  return (
    <div className="flex rounded-md border border-line-2 p-0.5" role="group" aria-label={t("Theme")}>
      {THEMES.map((x) => (
        <button
          key={x.id}
          type="button"
          onClick={() => setTheme(x.id)}
          aria-pressed={th === x.id}
          title={t(x.label)}
          className={`flex h-6 w-7 items-center justify-center rounded ${th === x.id ? "bg-raised" : "hover:bg-raised/60"}`}
        >
          <span
            aria-hidden
            className="h-3.5 w-3.5 rounded-full border border-line-3"
            style={{ background: `linear-gradient(135deg, ${x.swatch[0]} 50%, ${x.swatch[1]} 50%)` }}
          />
        </button>
      ))}
    </div>
  );
}
