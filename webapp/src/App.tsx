import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "./api";
import { ProjectTree } from "./components/ProjectTree";
import { LangSwitch, t, ts } from "./i18n";
import { ActivityWatcher, Bell } from "./notify";
import { useWorkspaceLive, useWorkspaceStream } from "./live";
import { href, useApp } from "./state";
import { ThemeSwitch } from "./theme";
import { AskHost, PageSkeleton } from "./ui";
import { PageTabs } from "./components/PageTabs";
import { ErrorBoundary } from "./components/ErrorBoundary";
import type { Route } from "./state";

// each page in its own chunk: the first load no longer parses the map engine, the charts and every Learn chapter
const Explorer = lazy(() => import("./pages/Explorer").then((m) => ({ default: m.Explorer })));
const Compose = lazy(() => import("./pages/Compose").then((m) => ({ default: m.Compose })));
const Ai = lazy(() => import("./pages/Ai").then((m) => ({ default: m.Ai })));
const Hazard = lazy(() => import("./pages/Hazard").then((m) => ({ default: m.Hazard })));
const Learn = lazy(() => import("./pages/Learn").then((m) => ({ default: m.Learn })));
const NewProject = lazy(() => import("./pages/NewProject").then((m) => ({ default: m.NewProject })));
const Coop = lazy(() => import("./pages/Coop").then((m) => ({ default: m.Coop })));
const OpenData = lazy(() => import("./pages/OpenData").then((m) => ({ default: m.OpenData })));
const Overview = lazy(() => import("./pages/Overview").then((m) => ({ default: m.Overview })));
const Project = lazy(() => import("./pages/Project").then((m) => ({ default: m.Project })));

// the tabs of the Projects page and of the In-depth analysis page
const PROJECT_TABS: [Route["page"], string][] = [
  ["overview", "My projects"],
  ["opendata", "Open data"],
  ["coop", "Source Cooperative"],
];
const INSIGHT_TABS: [Route["page"], string][] = [
  ["hazard", "Thematic analysis"],
  ["ai", "Machine learning research"],
  ["learn", "Principles"],
];

function Logo() {
  return (
    <svg width="24" height="24" viewBox="0 0 26 26" fill="none" stroke="var(--c-accent)" strokeWidth="1.8" aria-hidden>
      <circle cx="13" cy="13" r="11" />
      <ellipse cx="13" cy="13" rx="5" ry="11" />
      <path d="M2 13h22" />
    </svg>
  );
}

const LAST_PROJECT = "geoeyes.lastProject";
function rememberProject(name: string) {
  try {
    if (localStorage.getItem(LAST_PROJECT) !== name) localStorage.setItem(LAST_PROJECT, name);
  } catch {
    /* storage blocked: the item then only shows while a project is open or running */
  }
}
function recalledProject(): string | null {
  try {
    return localStorage.getItem(LAST_PROJECT);
  } catch {
    return null;
  }
}

// a page's code chunk loading: its skeleton, the same as while its data loads
function PageLoading() {
  return <PageSkeleton />;
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
          className="mt-4 h-10 w-full rounded-md border border-line-2 bg-sunken px-3 font-mono text-[13px] focus:border-accent focus:outline-none"
        />
        {error && <div className="mt-2 text-[12.5px] text-bad">{error}</div>}
        <button type="submit" className="mt-4 h-10 w-full rounded-lg bg-accent-2 text-[14px] font-semibold text-white hover:brightness-110">
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
  // a narrow window opens without the tree (it covers the page there); below md it also closes after each navigation
  const [treeOpen, setTreeOpen] = useState(() => window.innerWidth >= 1024);
  useEffect(() => {
    if (window.innerWidth < 768) setTreeOpen(false);
  }, [route]);
  // pushed by the server while its event stream is up; polled otherwise
  useWorkspaceStream();
  const live = useWorkspaceLive();
  const ws = useQuery({
    queryKey: ["workspace"],
    queryFn: api.workspace,
    refetchInterval: (q) => (live ? false : Object.values(q.state.data?.projects ?? {}).some((p) => p.running) ? 4000 : 20000),
  });
  // "Processing" stays in the bar: the open project, else a running one, else the last one opened (remembered)
  const projects = ws.data?.projects ?? {};
  if (route.page === "project") rememberProject(route.name);
  const remembered = recalledProject();
  const lastProject =
    route.page === "project"
      ? route.name
      : (Object.values(projects).find((p) => p.status === "running")?.name ?? (remembered && projects[remembered] ? remembered : undefined));
  const nav: { label: string; to: string | null; on: boolean; title?: string }[] = [
    // the open data (stacks to start a project from) is a tab of the Projects page
    { label: t("Projects"), to: href({ page: "overview" }), on: route.page === "overview" || route.page === "opendata" || route.page === "coop" },
    {
      label: t("Processing"),
      to: lastProject ? href({ page: "project", name: lastProject }) : null,
      on: route.page === "project",
      title: lastProject ?? t("Open a project from the tree first"),
    },
    { label: t("Results"), to: href({ page: "explorer" }), on: route.page === "explorer" },
    // thematic analysis, machine learning and principles are the tabs of one page
    { label: t("In-depth analysis"), to: href({ page: "hazard" }), on: INSIGHT_TABS.some(([p]) => p === route.page) },
    { label: t("Map export"), to: href({ page: "compose" }), on: route.page === "compose" },
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
          {nav.map((n) =>
            n.to === null ? (
              <span key={n.label} title={n.title} aria-disabled className="cursor-default rounded-lg px-3.5 py-1.5 text-[13.5px] text-faint">
                {n.label}
              </span>
            ) : (
              <a
                key={n.label}
                href={n.to}
                title={n.title}
                className={`rounded-lg px-3.5 py-1.5 text-[13.5px] no-underline ${n.on ? "bg-raised font-semibold text-ink" : "text-muted hover:text-ink"}`}
              >
                {n.label}
              </a>
            ),
          )}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-[12px] text-faint">
          {ws.error ? <span className="text-bad">{t("API unreachable: {msg}", { msg: (ws.error as Error).message })}</span> : <span className="hidden xl:inline">{ws.data?.root}</span>}
          <a href="/api/docs" target="_blank" rel="noopener" className="text-muted hover:text-ink">
            API
          </a>
          <ThemeSwitch />
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
          <ErrorBoundary resetKey={location.hash}>
            <Suspense fallback={<PageLoading />}>
              {PROJECT_TABS.some(([p]) => p === route.page) && (
                <PageTabs tabs={PROJECT_TABS} route={route}>
                  {route.page === "overview" ? <Overview ws={ws.data} /> : route.page === "coop" ? <Coop /> : <OpenData ws={ws.data} />}
                </PageTabs>
              )}
              {route.page === "explorer" && <Explorer ws={ws.data} />}
              {route.page === "project" && <Project name={route.name} tab={route.tab} />}
              {route.page === "new" && <NewProject ws={ws.data} />}
              {route.page === "compose" && <Compose ws={ws.data} />}
              {INSIGHT_TABS.some(([p]) => p === route.page) && (
                <PageTabs tabs={INSIGHT_TABS} route={route}>
                  {route.page === "hazard" && <Hazard ws={ws.data} project={route.name} product={route.product} cell={route.cell} layer={route.view} />}
                  {route.page === "ai" && <Ai ws={ws.data} project={route.name} product={route.product} tab={route.tab} />}
                  {route.page === "learn" && <Learn ws={ws.data} project={route.name} stack={route.stack} step={route.step} chapter={route.chapter} />}
                </PageTabs>
              )}
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <AskHost />
    </div>
  );
}
