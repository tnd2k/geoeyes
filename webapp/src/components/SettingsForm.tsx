// Settings of a project: a form described by the API from the configuration schema (values set in project.toml
// are marked; "reset" removes them so the preset / default applies again), and the raw project.toml.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type FieldSpec, type SettingsSpec } from "../api";
import { t, ts } from "../i18n";
import { Button, Panel } from "../ui";

type Draft = Record<string, unknown>; // "section.key" -> new value (null = back to default)

const input =
  "h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 text-[13px] text-ink focus:border-accent focus:outline-none";

function show(v: unknown): string {
  if (v == null) return "–";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function same(a: unknown, b: unknown) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function num(s: string, int: boolean): number | null {
  if (s.trim() === "") return null;
  const v = int ? parseInt(s, 10) : parseFloat(s);
  return Number.isFinite(v) ? v : null;
}

function Widget({ f, value, onChange, id }: { f: FieldSpec; value: unknown; onChange: (v: unknown) => void; id: string }) {
  switch (f.kind) {
    case "bool":
      return (
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={!!value}
          onClick={() => onChange(!value)}
          className={`relative h-6 w-11 rounded-full transition-colors ${value ? "bg-accent-2" : "bg-[#22324d]"}`}
        >
          <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${value ? "left-[22px]" : "left-0.5"}`} />
        </button>
      );
    case "enum":
      return (
        <select id={id} className={input} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {(f.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );
    case "int":
    case "number":
      return (
        <input
          id={id}
          type="number"
          step={f.kind === "int" ? 1 : "any"}
          min={f.min ?? undefined}
          max={f.max ?? undefined}
          className={input}
          value={value == null ? "" : String(value)}
          onChange={(e) => onChange(num(e.target.value, f.kind === "int"))}
        />
      );
    case "multi": {
      const cur = new Set((value as string[]) ?? []);
      return (
        <div className="flex flex-wrap gap-3 pt-1">
          {(f.options ?? []).map((o) => (
            <label key={o} className="flex items-center gap-1.5 text-[13px]">
              <input
                type="checkbox"
                className="accent-[#4cc2ff]"
                checked={cur.has(o)}
                onChange={(e) => {
                  const n = new Set(cur);
                  if (e.target.checked) n.add(o);
                  else n.delete(o);
                  onChange((f.options ?? []).filter((x) => n.has(x)));
                }}
              />
              {o}
            </label>
          ))}
        </div>
      );
    }
    case "daterange": {
      const v = (value as string[] | null) ?? ["", ""];
      return (
        <div className="flex items-center gap-2">
          <input id={id} type="date" className={input} value={v[0] ?? ""} onChange={(e) => onChange([e.target.value, v[1] ?? ""])} />
          <span className="text-muted">→</span>
          <input type="date" className={input} value={v[1] ?? ""} onChange={(e) => onChange([v[0] ?? "", e.target.value])} />
        </div>
      );
    }
    case "pair":
    case "bbox": {
      const n = f.kind === "bbox" ? 4 : 2;
      const v = ((value as number[] | null) ?? Array(n).fill(null)).slice(0, n);
      const labels = f.kind === "bbox" ? ["W", "S", "E", "N"] : ["", ""];
      return (
        <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}>
          {v.map((x, i) => (
            <input
              key={i}
              id={i === 0 ? id : undefined}
              type="number"
              step="any"
              placeholder={labels[i]}
              aria-label={labels[i] || t("value {n}", { n: i + 1 })}
              className={input}
              value={x == null ? "" : String(x)}
              onChange={(e) => {
                const c = [...v];
                c[i] = num(e.target.value, false);
                onChange(c);
              }}
            />
          ))}
        </div>
      );
    }
    case "list":
      return (
        <input
          id={id}
          className={input}
          value={Array.isArray(value) ? value.join(", ") : String(value ?? "")}
          onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
        />
      );
    default:
      return (
        <>
          <input id={id} className={input} list={f.suggest ? `${id}-s` : undefined} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
          {f.suggest && (
            <datalist id={`${id}-s`}>
              {f.suggest.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          )}
        </>
      );
  }
}

export function SettingsForm({ name, running }: { name: string; running: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings", name], queryFn: () => api.settings(name) });
  const [draft, setDraft] = useState<Draft>({});
  const [mode, setMode] = useState<"form" | "toml">("form");
  const [toml, setToml] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set(["project", "aoi", "acquire", "network", "stack", "atmosphere"]));
  const [filter, setFilter] = useState("");
  const done = (s: SettingsSpec) => {
    qc.setQueryData(["settings", name], s);
    qc.invalidateQueries({ queryKey: ["project", name] });
    qc.invalidateQueries({ queryKey: ["workspace"] });
    qc.removeQueries({ queryKey: ["plan", name] });
    setDraft({});
    setToml(s.toml);
  };
  const save = useMutation({ mutationFn: () => api.patchSettings(name, draft), onSuccess: done });
  const saveToml = useMutation({ mutationFn: () => api.putToml(name, toml), onSuccess: done });
  useEffect(() => {
    if (q.data) setToml(q.data.toml);
  }, [q.data]);
  useEffect(() => setDraft({}), [name]);

  const changed = Object.keys(draft).length;
  const sections = useMemo(() => {
    const s = filter.trim().toLowerCase();
    return (q.data?.sections ?? [])
      .map((sec) => ({ ...sec, fields: sec.fields.filter((f) => !s || `${sec.name}.${f.key} ${f.help}`.toLowerCase().includes(s)) }))
      .filter((sec) => sec.fields.length);
  }, [q.data, filter]);

  if (q.error) return <div className="text-bad">{(q.error as Error).message}</div>;
  if (!q.data) return <div className="text-muted">{t("Loading…")}</div>;
  const error = (save.error || saveToml.error) as Error | null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-line-2 bg-panel p-0.5">
          {(["form", "toml"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              className={`h-7 rounded-md px-3 text-[12.5px] ${mode === m ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
            >
              {m === "form" ? t("Form") : "project.toml"}
            </button>
          ))}
        </div>
        {mode === "form" && (
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("Filter parameters…")} aria-label={t("Filter parameters")} className={`${input} max-w-60`} />
        )}
        <div className="ml-auto flex items-center gap-2">
          {running && <span className="text-[12px] text-warn">{t("A run is in progress: changes apply to the next run.")}</span>}
          {mode === "form" ? (
            <>
              {changed > 0 && (
                <Button onClick={() => setDraft({})} disabled={save.isPending}>
                  {t("Discard")}
                </Button>
              )}
              <Button variant="primary" disabled={!changed || save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? t("Saving…") : changed ? (changed > 1 ? t("Save {n} changes", { n: changed }) : t("Save 1 change")) : t("No change")}
              </Button>
            </>
          ) : (
            <Button variant="primary" disabled={toml === q.data.toml || saveToml.isPending} onClick={() => saveToml.mutate()}>
              {saveToml.isPending ? t("Saving…") : t("Save project.toml")}
            </Button>
          )}
        </div>
      </div>
      {error && <div className="rounded-lg bg-[#2a1414] px-3 py-2 text-[13px] whitespace-pre-wrap text-bad">{error.message}</div>}
      {(save.isSuccess || saveToml.isSuccess) && !changed && !error && (
        <div className="rounded-lg bg-[#0f2a1f] px-3 py-2 text-[13px] text-good">
          {t("Saved (previous file kept in .state/). Check the plan to see which phases the change re-runs.")}
        </div>
      )}

      {mode === "toml" ? (
        <Panel className="p-0">
          <textarea
            value={toml}
            onChange={(e) => setToml(e.target.value)}
            spellCheck={false}
            aria-label="project.toml"
            className="block h-[60vh] w-full resize-y rounded-xl bg-transparent p-4 font-mono text-[12.5px] leading-relaxed text-ink-2 focus:outline-none"
          />
        </Panel>
      ) : (
        sections.map((sec) => {
          const isOpen = open.has(sec.name) || !!filter;
          const own = sec.fields.filter((f) => f.own).length;
          return (
            <Panel key={sec.name}>
              <button
                type="button"
                onClick={() => setOpen((s) => (s.has(sec.name) ? new Set([...s].filter((x) => x !== sec.name)) : new Set([...s, sec.name])))}
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
                aria-expanded={isOpen}
              >
                <span className="text-[14px] font-semibold">{ts(sec.title)}</span>
                <span className="font-mono text-[11.5px] text-faint">[{sec.name}]</span>
                {own > 0 && <span className="text-[11.5px] text-[#7cd2ff]">{t("{n} set in project.toml", { n: own })}</span>}
                <span className="ml-auto text-muted">{isOpen ? "–" : "+"}</span>
              </button>
              {isOpen && (
                <div className="grid gap-x-6 gap-y-4 border-t border-line px-4 py-4 md:grid-cols-2">
                  {sec.fields.map((f) => {
                    const k = `${sec.name}.${f.key}`;
                    const has = k in draft;
                    const value = has ? (draft[k] === null ? f.default : draft[k]) : f.value;
                    const own = has ? draft[k] !== null : f.own;
                    const id = `f-${k.replace(/\./g, "-")}`;
                    return (
                      <div key={k} className={`rounded-lg ${has ? "bg-[#102033] ring-1 ring-[#2f6fb0]" : ""} -m-1.5 p-1.5`}>
                        <div className="mb-1 flex items-center gap-2">
                          <label htmlFor={id} className="font-mono text-[12.5px] text-ink-2">
                            {f.key}
                          </label>
                          <span className={`text-[11px] ${own ? "text-[#7cd2ff]" : "text-faint"}`}>{own ? "project.toml" : t("preset / default")}</span>
                          {own && !same(value, f.default) && (
                            <button
                              type="button"
                              className="ml-auto text-[11px] text-muted hover:text-ink"
                              title={t("Back to the preset / default: {v}", { v: show(f.default) })}
                              onClick={() => setDraft((d) => (f.own ? { ...d, [k]: null } : Object.fromEntries(Object.entries(d).filter(([x]) => x !== k))))}
                            >
                              {t("reset")}
                            </button>
                          )}
                        </div>
                        <Widget
                          f={f}
                          id={id}
                          value={value}
                          onChange={(v) =>
                            setDraft((d) => {
                              const n = { ...d };
                              if (same(v, f.value)) delete n[k];
                              else n[k] = v;
                              return n;
                            })
                          }
                        />
                        {f.help && <div className="mt-1 text-[11.5px] leading-snug text-faint">{ts(f.help)}</div>}
                        {!own && f.default != null && <div className="sr-only">{t("default {v}", { v: show(f.default) })}</div>}
                      </div>
                    );
                  })}
                </div>
              )}
            </Panel>
          );
        })
      )}
    </div>
  );
}
