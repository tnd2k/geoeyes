// Tabs of a top-level page that groups several pages (Projects: projects / open data; In-depth analysis: thematic
// analysis / machine learning / principles). Each tab reopens where it was left (its last route in this session).
import { Suspense, type ReactNode } from "react";
import { t } from "../i18n";
import { PageSkeleton } from "../ui";
import { ErrorBoundary } from "./ErrorBoundary";
import { href, type Route } from "../state";

const last: Record<string, Route> = {};

export function PageTabs({ tabs, route, children }: { tabs: [Route["page"], string][]; route: Route; children: ReactNode }) {
  last[route.page] = route;
  return (
    <div className="flex h-full flex-col">
      <div role="tablist" className="flex flex-none gap-1 overflow-x-auto border-b border-line bg-panel-2 px-6">
        {tabs.map(([page, label]) => (
          <a
            key={page}
            role="tab"
            aria-selected={route.page === page}
            href={href(last[page] ?? ({ page } as Route))}
            className={`-mb-px flex h-10 items-center border-b-2 px-4 text-[14px] whitespace-nowrap no-underline ${route.page === page ? "border-accent font-semibold text-ink" : "border-transparent text-muted hover:text-ink"}`}
          >
            {t(label)}
          </a>
        ))}
      </div>
      {/* the tab bar stays while a tab's page chunk loads */}
      <div className="min-h-0 flex-1">
        <ErrorBoundary resetKey={route.page}>
        <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
        </ErrorBoundary>
      </div>
    </div>
  );
}
