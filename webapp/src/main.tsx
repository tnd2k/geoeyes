import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { LangProvider } from "./i18n";
import "./index.css";
import { NotifyProvider } from "./notify";
import { AppProvider } from "./state";

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <LangProvider>
        <NotifyProvider>
          <AppProvider>
            <App />
          </AppProvider>
        </NotifyProvider>
      </LangProvider>
    </QueryClientProvider>
  </StrictMode>,
);
