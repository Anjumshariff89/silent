"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { hasSession, signOut } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { Health, IntegrityStatus } from "@/lib/types";
import { blockchainBadgeLabel } from "@/lib/quai";
import { useAuth } from "./AuthProvider";
import {
  IconActivity, IconAnchor, IconBell, IconCheckCircle, IconClock, IconCpu, IconCube, IconFile, IconGrid, IconHome,
  IconLink, IconList, IconLogout, IconMenu, IconShieldCheck, IconTree, IconUser, IconX, Logo,
} from "./icons";
import { ModeBadge, StatusDot } from "./ui";

export const NAV = [
  { href: "/me", label: "My Dashboard", group: "My workspace", icon: IconHome },
  { href: "/me/verify", label: "My Verify", group: "My workspace", icon: IconCheckCircle },
  { href: "/me/anchors", label: "My Anchors", group: "My workspace", icon: IconAnchor },
  { href: "/", label: "Overview", group: "SOC monitoring", icon: IconGrid },
  { href: "/logs", label: "Live Logs", group: "SOC monitoring", icon: IconList },
  { href: "/agents", label: "Agent Monitoring", group: "SOC monitoring", icon: IconCpu },
  { href: "/chain", label: "Hash-Chain", group: "SOC monitoring", icon: IconLink },
  { href: "/integrity", label: "Integrity Verification", group: "SOC monitoring", icon: IconShieldCheck },
  { href: "/alerts", label: "Tamper Alerts", group: "SOC monitoring", icon: IconBell },
  { href: "/merkle", label: "Merkle Tree", group: "Proof & evidence", icon: IconTree },
  { href: "/blockchain", label: "Blockchain Explorer", group: "Proof & evidence", icon: IconCube },
  { href: "/timeline", label: "Incident Timeline", group: "Proof & evidence", icon: IconClock },
  { href: "/evidence", label: "Evidence Portal", group: "Proof & evidence", icon: IconFile },
];
const GROUPS = Array.from(new Set(NAV.map((n) => n.group)));

const LABEL = { green: "INTEGRITY OK", yellow: "ATTENTION", red: "TAMPER DETECTED" } as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const live = useLive();
  const { email } = useAuth();
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

  useEffect(() => {  // close the mobile drawer with Escape
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu]);

  if (!ready) return null;
  const st = integrity.data?.status;
  const current = NAV.find((n) => n.href === pathname);

  return (
    <div className="min-h-screen lg:flex">
      {/* mobile drawer backdrop */}
      <div onClick={() => setMenu(false)} aria-hidden
        className={`fixed inset-0 z-30 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden ${menu ? "opacity-100" : "pointer-events-none opacity-0"}`} />

      <aside aria-label="Main navigation"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 max-w-[85vw] flex-col border-r border-soc-border bg-soc-panel/95 backdrop-blur transition-transform duration-200
          lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:max-w-none lg:translate-x-0 ${menu ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between gap-3 border-b border-soc-border px-4 py-4">
          <Link href="/me" className="flex items-center gap-3">
            <Logo size={34} />
            <span className="leading-tight">
              <span className="block text-sm font-semibold tracking-wide text-slate-100">SilentWitness</span>
              <span className="block text-[11px] text-soc-muted">Logs the attacker can&apos;t erase</span>
            </span>
          </Link>
          <button className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 lg:hidden" onClick={() => setMenu(false)} aria-label="Close menu">
            <IconX size={18} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {GROUPS.map((g) => (
            <div key={g}>
              <div className="nav-section">{g}</div>
              {NAV.filter((n) => n.group === g).map((n) => {
                const active = pathname === n.href;
                const Icon = n.icon;
                return (
                  <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                    className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                      active ? "bg-sky-500/10 font-medium text-sky-200" : "text-slate-300 hover:bg-white/[0.04] hover:text-slate-100"}`}>
                    {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-sky-400" aria-hidden />}
                    <Icon size={17} className={active ? "text-sky-300" : "text-slate-500 transition group-hover:text-slate-300"} />
                    {n.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="space-y-3 border-t border-soc-border p-3">
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <IconActivity size={12} /> Integrations
            </div>
            <div className="grid grid-cols-1 gap-1">
              {health.data ? Object.entries(health.data.integrations).map(([k, v]) => (
                <ModeBadge key={k} name={k.replace("windows_event_log", "winlog")} mode={v}
                  label={k === "blockchain" ? blockchainBadgeLabel(v) : undefined} />
              )) : <span className="px-1 text-xs text-soc-muted">{health.error ? "status unavailable" : "checking…"}</span>}
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-soc-border bg-white/[0.02] p-2">
            <span className="rounded-full bg-sky-500/15 p-1.5 text-sky-300"><IconUser size={15} /></span>
            <span className="min-w-0 flex-1 truncate text-xs text-slate-300" title={email ?? "Local admin"}>{email ?? "Local admin"}</span>
            <button data-testid="sign-out" onClick={async () => { await signOut(); router.replace("/login"); }}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-soc-muted transition hover:bg-white/10 hover:text-slate-100"
              title="Sign out">
              <IconLogout size={14} /> Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-soc-border bg-soc-bg/80 px-4 py-3 backdrop-blur-md sm:px-6">
          <button className="btn-secondary px-2 py-1.5 lg:hidden" onClick={() => setMenu((m) => !m)} aria-label="Toggle menu" aria-expanded={menu}>
            <IconMenu size={18} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[11px] uppercase tracking-[0.12em] text-slate-500">{current?.group ?? "SilentWitness"}</div>
            <div className="truncate text-sm font-medium text-slate-200">{current?.label ?? ""}</div>
          </div>
          <div data-testid="integrity-indicator" data-status={st ?? "unknown"}
            className={`flex shrink-0 items-center gap-2 rounded-full px-3 py-1 text-[11px] font-bold tracking-wide ring-1 ring-inset ${
              st === "red" ? "bg-red-500/15 text-red-300 ring-red-500/40" : st === "green" ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"
                : "bg-amber-500/10 text-amber-300 ring-amber-500/30"}`}>
            <StatusDot status={st ?? "yellow"} pulse={st === "red"} />
            {st ? LABEL[st] : integrity.error ? "STATUS UNAVAILABLE" : "CHECKING…"}
          </div>
          <div className="hidden shrink-0 items-center gap-2 text-xs text-soc-muted sm:flex" title="Live event stream">
            <StatusDot status={live.connected ? "online" : "offline"} pulse={live.connected} />
            {live.connected ? "live" : "disconnected"}
          </div>
        </header>
        {health.data?.dev_api_key_in_use && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-200 sm:px-6">
            The built-in development API key is in use. Set MODE=real, API_KEY and JWT_SECRET in .env.
          </div>
        )}
        <main key={pathname} className="mx-auto max-w-7xl animate-fade-up px-4 py-5 sm:px-6 sm:py-6">{children}</main>
      </div>
    </div>
  );
}
