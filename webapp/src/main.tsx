import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
// fonts bundled with the app (no Google Fonts request: offline-safe, one font for every Vietnamese glyph)
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/lexend";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { LangProvider } from "./i18n";
import "./index.css";
import { NotifyProvider } from "./notify";
import { AppProvider } from "./state";
import { ThemeProvider } from "./theme";

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, gcTime: 24 * 3600_000 } } });

// small, slow-to-compute JSON answers survive a page reload: shown at once from the browser, refreshed when stale.
// Large binary layers stay out (they are cached by HTTP).
const KEEP = new Set(["floods", "floodStats", "floodOutlook", "rain"]);
let storage: Storage | undefined;
try {
  storage = window.localStorage;
} catch {
  storage = undefined; // private mode, blocked storage: no persistence
}
const persister = createSyncStoragePersister({ storage, key: "geoeyes.queries", throttleTime: 2000 });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PersistQueryClientProvider
      client={client}
      persistOptions={{
        persister,
        maxAge: 24 * 3600_000,
        buster: "1",
        dehydrateOptions: { shouldDehydrateQuery: (q) => q.state.status === "success" && KEEP.has(String(q.queryKey[0])) },
      }}
    >
      <LangProvider>
        <ThemeProvider>
          <NotifyProvider>
            <AppProvider>
              <App />
            </AppProvider>
          </NotifyProvider>
        </ThemeProvider>
      </LangProvider>
    </PersistQueryClientProvider>
  </StrictMode>,
);
