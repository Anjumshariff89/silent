"use client";

import { useState, type ReactNode } from "react";
import { IconAlert, IconCheck, IconCopy, IconInbox } from "./icons";

export function Card({ title, actions, children, className = "", icon }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; icon?: ReactNode;
}) {
  return (
    <section className={`rounded-xl border border-soc-border bg-gradient-to-b from-soc-panel2/70 to-soc-panel p-4 shadow-card sm:p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
              {icon && <span className="text-sky-400">{icon}</span>}
              {title}
            </h2>
          )}
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
    <span className="relative inline-flex h-2.5 w-2.5 shrink-0" aria-hidden>
      {pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${DOT[status] ?? "bg-slate-500"}`} />}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ring-2 ring-black/20 ${DOT[status] ?? "bg-slate-500"}`} />
    </span>
  );
}

const PILL: Record<string, string> = {
  green: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30",
  yellow: "bg-amber-500/10 text-amber-300 ring-amber-500/30",
  red: "bg-red-500/10 text-red-300 ring-red-500/35",
  slate: "bg-slate-500/10 text-slate-300 ring-slate-500/30",
  sky: "bg-sky-500/10 text-sky-300 ring-sky-500/30",
};
const PILL_DOT: Record<string, string> = {
  green: "bg-emerald-400", yellow: "bg-amber-400", red: "bg-red-400", slate: "bg-slate-400", sky: "bg-sky-400",
};
const TONE: Record<string, string> = {
  green: "green", online: "green", PASS: "green", MATCH: "green", REAL: "green", resolved: "slate", info: "sky",
  yellow: "yellow", delayed: "yellow", NOT_ANCHORED: "yellow", warning: "yellow", SIMULATED: "yellow", "NOT CONFIGURED": "yellow", UNAVAILABLE: "yellow", CONSOLE: "yellow", sandbox: "yellow",
  SQLITE: "sky", SUPABASE: "green", confirmed: "green", pending: "yellow", failed: "red", "READ-ONLY": "yellow",
  red: "red", offline: "red", FAIL: "red", MISMATCH: "red", critical: "red", open: "red", live: "sky",
};

export function Pill({ value, label }: { value: string; label?: ReactNode }) {
  const tone = TONE[value] ?? "slate";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${PILL[tone]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${PILL_DOT[tone]}`} aria-hidden />
      {label ?? value}
    </span>
  );
}

export function ModeBadge({ name, mode, label }: { name: string; mode: string; label?: string }) {
  const tone = mode === "REAL" || mode === "SUPABASE" ? "green" : mode === "SQLITE" ? "sky" : "yellow";
  return (
    <span title={`${name}: ${label ?? mode}`} data-testid={`badge-${name}`} data-mode={mode}
      className={`inline-flex max-w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-[11px] font-semibold ring-1 ring-inset ${PILL[tone]}`}>
      <span className="font-normal capitalize text-slate-400">{name}</span> <span className="truncate">{label ?? mode}</span>
    </span>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-2.5 py-3">
      <span className="sr-only">{label}</span>
      {[92, 76, 84].map((w, i) => (
        <div key={i} style={{ width: `${w}%` }}
          className="h-3 animate-shimmer rounded bg-[linear-gradient(90deg,rgba(255,255,255,0.04)_0%,rgba(255,255,255,0.09)_50%,rgba(255,255,255,0.04)_100%)] bg-[length:200%_100%]" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" data-testid="error-state"
      className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/[0.07] p-3 text-sm text-red-200">
      <span className="flex min-w-0 items-start gap-2">
        <IconAlert size={16} className="mt-0.5 shrink-0 text-red-400" />
        <span className="min-w-0 break-words"><strong className="font-semibold">Error:</strong> {message}</span>
      </span>
      {onRetry && <button onClick={onRetry} className="btn-secondary py-1">Retry</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-soc-muted">
      <span className="rounded-full border border-soc-border bg-white/[0.02] p-2.5 text-slate-500"><IconInbox size={20} /></span>
      <p>{children}</p>
    </div>
  );
}

/** Shortened hash with the full value on hover and a copy button. */
export function Hash({ value, n = 12 }: { value: string | null | undefined; n?: number }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="text-soc-muted">—</span>;
  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch { /* clipboard not available (e.g. insecure context): the full value is still in the tooltip */ }
  };
  return (
    <span className="group inline-flex items-center gap-1 align-middle">
      <code title={value} className="font-mono text-xs text-sky-300">{value.slice(0, n)}…</code>
      <button type="button" onClick={copy} aria-label={copied ? "Copied" : "Copy full hash"} title={copied ? "Copied" : "Copy"}
        className="rounded p-0.5 text-slate-500 opacity-60 transition hover:bg-white/10 hover:text-slate-200 group-hover:opacity-100">
        {copied ? <IconCheck size={13} className="text-emerald-400" /> : <IconCopy size={13} />}
      </button>
    </span>
  );
}

export function fmtTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

const STAT_ACCENT: Record<string, string> = {
  green: "from-emerald-400/70", yellow: "from-amber-400/70", red: "from-red-400/80", sky: "from-sky-400/70", slate: "from-slate-500/40",
};

export function Stat({ label, value, tone, icon }: { label: string; value: ReactNode; tone?: string; icon?: ReactNode }) {
  const accent = STAT_ACCENT[TONE[tone ?? ""] ?? (tone ? "slate" : "sky")];
  return (
    <div className="group relative overflow-hidden rounded-xl border border-soc-border bg-gradient-to-b from-soc-panel2/70 to-soc-panel p-4 shadow-card transition hover:-translate-y-0.5 hover:border-slate-600/70">
      <div className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${accent} to-transparent`} aria-hidden />
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-medium uppercase tracking-[0.1em] text-soc-muted">{label}</div>
        {icon && <span className="rounded-lg border border-soc-border bg-white/[0.03] p-1.5 text-slate-400 transition group-hover:text-sky-300">{icon}</span>}
      </div>
      <div className="mt-2 flex min-w-0 items-center gap-2 text-2xl font-semibold tracking-tight text-slate-50">
        {tone && <StatusDot status={tone} />}
        <span className="min-w-0 truncate">{value}</span>
      </div>
    </div>
  );
}
