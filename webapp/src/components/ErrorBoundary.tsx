// A page or panel that throws while rendering (a malformed layer, an unexpected API answer) shows its error and a
// retry in place, instead of unmounting the whole app into a blank screen.
import { Component, type ErrorInfo, type ReactNode } from "react";
import { t } from "../i18n";

type Props = { children: ReactNode; /** a change (the route) clears the error */ resetKey?: string; compact?: boolean };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("GeoEyes UI error:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className={`flex items-center justify-center p-6 ${this.props.compact ? "" : "h-full"}`} role="alert">
        <div className="max-w-lg rounded-xl border border-line-2 bg-panel p-5">
          <div className="text-[14px] font-semibold text-bad">{t("This view stopped on an error")}</div>
          <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-sunken p-2 font-mono text-[11.5px] whitespace-pre-wrap text-ink-3">{error.message}</pre>
          <p className="mt-2 text-[12.5px] text-muted">{t("The rest of the app still works. Retry, or reload the page if it happens again.")}</p>
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => this.setState({ error: null })} className="h-8 rounded-lg bg-accent-2 px-3 text-[13px] font-semibold text-white hover:brightness-110">
              {t("Retry")}
            </button>
            <button type="button" onClick={() => location.reload()} className="h-8 rounded-lg border border-line-2 px-3 text-[13px] text-muted hover:text-ink">
              {t("Reload the page")}
            </button>
          </div>
        </div>
      </div>
    );
  }
}
