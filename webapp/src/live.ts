// Server-sent events: the server pushes the workspace, the activity and the open project's state and log when they
// change, over one connection each, in place of several polls. While a stream is down (an older server, a lost
// connection, a hidden tab) the pages poll as before: the `up` state of a stream switches their polling off.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

type Handlers = Record<string, (data: never) => void>;

/** Opens the stream at `url()` (called again at each connection: the URL may carry a cursor) while the tab is
 *  visible. Reconnects by itself: soon after a stream that worked, slowly when it never opened (an older server
 *  without it). Returns `close` and `reopen` (a cursor got out of step). */
export function openStream(url: () => string, on: Handlers, state: (up: boolean) => void) {
  let es: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;
  let worked = false;
  let up = false;
  const set = (u: boolean) => {
    if (u !== up) state((up = u));
  };
  const drop = () => {
    es?.close();
    es = null;
    clearTimeout(timer);
  };
  const connect = () => {
    drop();
    if (closed || document.hidden) return;
    // the native reconnection would reuse the first URL (its cursor): reconnect here instead
    const s = (es = new EventSource(url()));
    s.onopen = () => {
      worked = true;
      set(true);
    };
    s.onerror = () => {
      if (es !== s) return;
      drop();
      set(false);
      timer = setTimeout(connect, worked ? 1500 : 30_000);
    };
    for (const [event, fn] of Object.entries(on))
      s.addEventListener(event, (e) => {
        try {
          fn(JSON.parse((e as MessageEvent<string>).data) as never);
        } catch {
          /* a malformed message: the next one replaces it */
        }
      });
  };
  const onVisibility = () => {
    if (document.hidden) {
      drop();
      set(false);
    } else if (!es) connect();
  };
  document.addEventListener("visibilitychange", onVisibility);
  connect();
  return {
    close: () => {
      closed = true;
      drop();
      document.removeEventListener("visibilitychange", onVisibility);
    },
    reopen: connect,
  };
}

// ------------------------------------------------------------------ workspace stream (one for the app)
let wsUp = false;
const listeners = new Set<() => void>();
const subscribe = (f: () => void) => (listeners.add(f), () => void listeners.delete(f));

/** True while the workspace stream is up: the workspace and activity polls stay off. */
export function useWorkspaceLive(): boolean {
  return useSyncExternalStore(subscribe, () => wsUp);
}

/** Opens the workspace stream (`workspace`, `activity` into the query cache). Called once, by the app shell. */
export function useWorkspaceStream() {
  const qc = useQueryClient();
  useEffect(() => {
    const s = openStream(
      () => "/api/events",
      {
        workspace: (d: never) => qc.setQueryData(["workspace"], d),
        activity: (d: never) => qc.setQueryData(["activity"], d),
      },
      (up) => {
        wsUp = up;
        listeners.forEach((f) => f());
      },
    );
    return () => {
      s.close();
      wsUp = false;
      listeners.forEach((f) => f());
    };
  }, [qc]);
}
