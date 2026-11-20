"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, getToken, USE_MOCK, wsUrl } from "./api";
import type { LiveMessage } from "./types";

export interface Query<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch `path` (re-fetches when path changes, on `refreshKey` change, and every `intervalMs`). */
export function useApi<T>(path: string | null, opts: { intervalMs?: number; refreshKey?: unknown } = {}): Query<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading((prev) => prev || data === null);
    api<T>(path)
      .then((d) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, opts.refreshKey]);

  useEffect(() => {
    if (!opts.intervalMs) return;
    const id = setInterval(reload, opts.intervalMs);
    return () => clearInterval(id);
  }, [opts.intervalMs, reload]);

  return { data, error, loading, reload };
}

interface LiveState {
  connected: boolean;
  last: LiveMessage | null;
  counter: number; // increments on every message, use as refreshKey
  recentLogs: LiveMessage[];
}

const LiveContext = createContext<LiveState>({ connected: false, last: null, counter: 0, recentLogs: [] });

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<LiveState>({ connected: false, last: null, counter: 0, recentLogs: [] });
  const retry = useRef(0);

  useEffect(() => {
    if (USE_MOCK || !getToken()) return;
    let ws: WebSocket | null = null;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => { retry.current = 0; setState((s) => ({ ...s, connected: true })); };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as LiveMessage;
          setState((s) => ({
            connected: true, last: msg, counter: s.counter + 1,
            recentLogs: msg.type === "log" ? [msg, ...s.recentLogs].slice(0, 50) : s.recentLogs,
          }));
        } catch { /* ignore malformed */ }
      };
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!stopped) timer = setTimeout(connect, Math.min(10000, 1000 * 2 ** retry.current++));
      };
    };
    connect();
    return () => { stopped = true; clearTimeout(timer); ws?.close(); };
  }, []);

  return <LiveContext.Provider value={state}>{children}</LiveContext.Provider>;
}

export const useLive = () => useContext(LiveContext);
