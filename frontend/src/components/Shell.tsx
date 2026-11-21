"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { hasSession, signOut } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { Health, IntegrityStatus } from "@/lib/types";
import { blockchainBadgeLabel } from "@/lib/quai";
import { ModeBadge, StatusDot } from "./ui";

export const NAV = [
  { href: "/me", label: "My Dashboard" },
  { href: "/me/verify", label: "My Verify" },
  { href: "/me/anchors", label: "My Anchors" },
  { href: "/", label: "Overview" },
  { href: "/logs", label: "Live Logs" },
  { href: "/agents", label: "Agent Monitoring" },
  { href: "/chain", label: "Hash-Chain" },
  { href: "/integrity", label: "Integrity Verification" },
  { href: "/alerts", label: "Tamper Alerts" },
  { href: "/merkle", label: "Merkle Tree" },
  { href: "/blockchain", label: "Blockchain Explorer" },
  { href: "/timeline", label: "Incident Timeline" },
  { href: "/evidence", label: "Evidence Portal" },
];

const LABEL = { green: "INTEGRITY OK", yellow: "ATTENTION", red: "TAMPER DETECTED" } as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const live = useLive();
  const [ready, setReady] = useState(false);
  const [menu, setMenu] = useState(false);
  const health = useApi<Health>(ready ? "/api/health" : null, { intervalMs: 15000 });
  const integrity = useApi<IntegrityStatus>(ready ? "/api/integrity/status" : null,
    { intervalMs: 10000, refreshKey: live.last?.type === "integrity" || live.last?.type === "incident" ? live.counter : 0 });

  useEffect(() => {  // protected routes: no session -> /login
    let active = true;
    hasSession().then((ok) => {
      if (!active) return;
      if (ok) setReady(true);
      else router.replace("/login");
    });
    return () => { active = false; };
  }, [router]);

  useEffect(() => setMenu(false), [pathname]);

  if (!ready) return null;
  const st = integrity.data?.status;

  return (
    <div className="min-h-screen md:flex">
      <aside className={`${menu ? "block" : "hidden"} border-b border-soc-border bg-soc-panel md:block md:min-h-screen md:w-60 md:shrink-0 md:border-b-0 md:border-r`}>
        <div className="hidden px-4 py-5 md:block">
          <div className="text-sm font-bold tracking-wide text-slate-100">LOGS THE ATTACKER</div>
          <div className="text-sm font-bold tracking-wide text-sky-400">CAN&apos;T ERASE</div>
        </div>
        <nav className="flex flex-col p-2">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}
              className={`rounded px-3 py-2 text-sm ${pathname === n.href ? "bg-sky-500/15 text-sky-300" : "text-slate-300 hover:bg-white/5"}`}>
              {n.label}
            </Link>
          ))}
          <button data-testid="sign-out" onClick={async () => { await signOut(); router.replace("/login"); }}
            className="mt-4 rounded px-3 py-2 text-left text-sm text-soc-muted hover:bg-white/5">Sign out</button>
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-soc-border bg-soc-bg/95 px-4 py-3 backdrop-blur">
          <button className="btn-secondary md:hidden" onClick={() => setMenu((m) => !m)} aria-label="Toggle menu">☰</button>
          <div data-testid="integrity-indicator" data-status={st ?? "unknown"}
            className={`flex items-center gap-2 rounded px-2 py-1 text-xs font-bold ${
              st === "red" ? "bg-red-500/20 text-red-300" : st === "green" ? "bg-emerald-500/15 text-emerald-300"
                : "bg-amber-500/15 text-amber-300"}`}>
            <StatusDot status={st ?? "yellow"} pulse={st === "red"} />
            {st ? LABEL[st] : integrity.error ? "STATUS UNAVAILABLE" : "CHECKING…"}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {health.data && Object.entries(health.data.integrations).map(([k, v]) => (
              <ModeBadge key={k} name={k.replace("windows_event_log", "winlog")} mode={v}
                label={k === "blockchain" ? blockchainBadgeLabel(v) : undefined} />
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs text-soc-muted">
            <StatusDot status={live.connected ? "online" : "offline"} />
            {live.connected ? "live" : "disconnected"}
          </div>
        </header>
        {health.data?.dev_api_key_in_use && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-200">
            The built-in development API key is in use. Set MODE=real, API_KEY and JWT_SECRET in .env.
          </div>
        )}
        <main className="mx-auto max-w-7xl p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
