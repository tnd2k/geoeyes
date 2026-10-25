import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import { ProjectTree } from "./components/ProjectTree";
import { Explorer } from "./pages/Explorer";
import { Compose } from "./pages/Compose";
import { Hazard } from "./pages/Hazard";
import { NewProject } from "./pages/NewProject";
import { Overview } from "./pages/Overview";
import { Project } from "./pages/Project";
import { LangSwitch, t, ts } from "./i18n";
import { ActivityWatcher, Bell } from "./notify";
import { href, useApp } from "./state";

function Logo() {
  return (
    <svg width="24" height="24" viewBox="0 0 26 26" fill="none" stroke="#4cc2ff" strokeWidth="1.8" aria-hidden>
      <circle cx="13" cy="13" r="11" />
      <ellipse cx="13" cy="13" rx="5" ry="11" />
      <path d="M2 13h22" />
    </svg>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.login(token.trim());
      onDone();
    } catch (err) {
      setError(ts((err as Error).message));
    }
  };
  return (
    <div className="flex h-full items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-line-2 bg-panel p-6 shadow-2xl">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="text-[17px] font-bold">GeoEyes</span>
        </div>
        <p className="mt-3 text-[13px] text-muted">{t("This server is open to the network. Enter the login token printed by")} <span className="font-mono">geoeyes serve</span>.</p>
        <input
          type="password"
          autoFocus
          value={token}
          onChange={(e) => setToken(e.target.value)}
          aria-label={t("Login token")}
          className="mt-4 h-10 w-full rounded-md border border-line-2 bg-[#0a1322] px-3 font-mono text-[13px] focus:border-accent focus:outline-none"
        />
        {error && <div className="mt-2 text-[12.5px] text-bad">{error}</div>}
        <button type="submit" className="mt-4 h-10 w-full rounded-lg bg-accent-2 text-[14px] font-semibold text-white hover:bg-[#4b9dff]">
          {t("Sign in")}
        </button>
      </form>
    </div>
  );
}

export function App() {
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: Infinity, retry: 2 });
  useEffect(() => {
    const on = () => qc.invalidateQueries({ queryKey: ["health"] });
    addEventListener("geoeyes:login", on);
    return () => removeEventListener("geoeyes:login", on);
  }, [qc]);
  if (health.data && health.data.auth_required && !health.data.authenticated) {
    return <Login onDone={() => qc.invalidateQueries()} />;
  }
  return <Shell />;
}

function Shell() {
  const { route } = useApp();
  const [treeOpen, setTreeOpen] = useState(true);
  const ws = useQuery({
    queryKey: ["workspace"],
    queryFn: api.workspace,
    refetchInterval: (q) => (Object.values(q.state.data?.projects ?? {}).some((p) => p.running) ? 4000 : 20000),
  });
  const lastProject =
    route.page === "project" ? route.name : Object.values(ws.data?.projects ?? {}).find((p) => p.status === "running")?.name;
  const nav = [
    { label: t("Overview"), to: href({ page: "overview" }), on: route.page === "overview" },
    { label: t("Explorer"), to: href({ page: "explorer" }), on: route.page === "explorer" },
    { label: t("Hazard"), to: href({ page: "hazard" }), on: route.page === "hazard" },
    { label: t("Map image"), to: href({ page: "compose" }), on: route.page === "compose" },
    ...(lastProject ? [{ label: t("Project"), to: href({ page: "project", name: lastProject }), on: route.page === "project" }] : []),
  ];

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-[52px] flex-none items-center gap-4 border-b border-line bg-panel-2 px-4">
        <button
          type="button"
          onClick={() => setTreeOpen((v) => !v)}
          title={treeOpen ? t("Hide the project tree") : t("Show the project tree")}
          aria-pressed={treeOpen}
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-raised hover:text-ink"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
            <rect x="1.5" y="2.5" width="13" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
            <path d="M6 2.5v11" stroke="currentColor" strokeWidth="1.3" />
          </svg>
        </button>
        <a href="#/" className="flex items-center gap-2.5 text-ink no-underline">
          <Logo />
          <span className="text-[16px] font-bold tracking-tight">GeoEyes</span>
        </a>
        <nav className="flex gap-1" aria-label={t("Main")}>
          {nav.map((n) => (
            <a
              key={n.label}
              href={n.to}
              className={`rounded-lg px-3.5 py-1.5 text-[13.5px] no-underline ${n.on ? "bg-raised font-semibold text-ink" : "text-muted hover:text-ink"}`}
            >
              {n.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-[12px] text-faint">
          {ws.error ? <span className="text-bad">{t("API unreachable: {msg}", { msg: (ws.error as Error).message })}</span> : <span className="hidden xl:inline">{ws.data?.root}</span>}
          <a href="/api/docs" target="_blank" rel="noopener" className="text-muted hover:text-ink">
            API
          </a>
          <LangSwitch />
          <Bell />
          <ActivityWatcher ws={ws.data} />
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        {treeOpen && (
          <aside className="w-[290px] flex-none border-r border-line bg-panel-2 max-md:absolute max-md:top-[52px] max-md:bottom-0 max-md:z-30 max-md:shadow-2xl">
            <ProjectTree ws={ws.data} />
          </aside>
        )}
        <main className="min-w-0 flex-1">
          {route.page === "overview" && <Overview ws={ws.data} />}
          {route.page === "explorer" && <Explorer ws={ws.data} />}
          {route.page === "project" && <Project name={route.name} tab={route.tab} />}
          {route.page === "new" && <NewProject ws={ws.data} />}
          {route.page === "compose" && <Compose ws={ws.data} />}
          {route.page === "hazard" && <Hazard ws={ws.data} project={route.name} product={route.product} cell={route.cell} />}
        </main>
      </div>
    </div>
  );
}
