"use client";

import type { ReactNode } from "react";

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-lg border border-soc-border bg-soc-panel p-4 ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

const DOT: Record<string, string> = {
  green: "bg-emerald-500", online: "bg-emerald-500", PASS: "bg-emerald-500", MATCH: "bg-emerald-500",
  yellow: "bg-amber-400", delayed: "bg-amber-400", NOT_ANCHORED: "bg-amber-400", warning: "bg-amber-400",
  red: "bg-red-500", offline: "bg-red-500", FAIL: "bg-red-500", MISMATCH: "bg-red-500", critical: "bg-red-500",
  info: "bg-sky-500",
};

export function StatusDot({ status, pulse = false }: { status: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2.5 w-2.5" aria-hidden>
      {pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${DOT[status] ?? "bg-slate-500"}`} />}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${DOT[status] ?? "bg-slate-500"}`} />
    </span>
  );
}

const PILL: Record<string, string> = {
  green: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  yellow: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  red: "bg-red-500/15 text-red-300 ring-red-500/40",
  slate: "bg-slate-500/15 text-slate-300 ring-slate-500/40",
  sky: "bg-sky-500/15 text-sky-300 ring-sky-500/40",
};
const TONE: Record<string, string> = {
  green: "green", online: "green", PASS: "green", MATCH: "green", REAL: "green", resolved: "slate", info: "sky",
  yellow: "yellow", delayed: "yellow", NOT_ANCHORED: "yellow", warning: "yellow", SIMULATED: "yellow", "NOT CONFIGURED": "yellow", UNAVAILABLE: "yellow", CONSOLE: "yellow", sandbox: "yellow",
  SQLITE: "sky", SUPABASE: "green",
  red: "red", offline: "red", FAIL: "red", MISMATCH: "red", critical: "red", open: "red", live: "sky",
};

export function Pill({ value, label }: { value: string; label?: ReactNode }) {
  const tone = TONE[value] ?? "slate";
  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${PILL[tone]}`}>
      {label ?? value}
    </span>
  );
}

export function ModeBadge({ name, mode, label }: { name: string; mode: string; label?: string }) {
  return (
    <span title={`${name}: ${label ?? mode}`} data-testid={`badge-${name}`} data-mode={mode}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold ring-1 ring-inset ${
        mode === "REAL" || mode === "SUPABASE" ? PILL.green : mode === "SQLITE" ? PILL.sky : PILL.yellow}`}>
      <span className="font-normal opacity-80">{name}</span> {label ?? mode}
    </span>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-sm text-soc-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" data-testid="error-state"
      className="flex flex-wrap items-center justify-between gap-3 rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
      <span><strong className="font-semibold">Error:</strong> {message}</span>
      {onRetry && <button onClick={onRetry} className="btn-secondary">Retry</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-soc-muted">{children}</p>;
}

export function Hash({ value, n = 12 }: { value: string | null | undefined; n?: number }) {
  if (!value) return <span className="text-soc-muted">—</span>;
  return <code title={value} className="font-mono text-xs text-sky-300">{value.slice(0, n)}…</code>;
}

export function fmtTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="rounded-lg border border-soc-border bg-soc-panel p-4">
      <div className="text-xs uppercase tracking-wide text-soc-muted">{label}</div>
      <div className="mt-1 flex items-center gap-2 text-2xl font-semibold">
        {tone && <StatusDot status={tone} />}
        {value}
      </div>
    </div>
  );
}
