"use client";

import { useState } from "react";
import { post, setToken } from "@/lib/api";
import { ErrorState } from "@/components/ui";
import { SUPABASE_ENABLED, supabase } from "@/lib/supabase";
import { Logo } from "@/components/icons";

export default function LoginPage() {
  return SUPABASE_ENABLED ? <SupabaseLogin /> : <LocalLogin />;
}

/** Decorative: logs -> SHA-256 links -> Merkle root -> anchored on Quai. */
function ChainIllustration() {
  const blocks = [0, 1, 2, 3];
  return (
    <svg viewBox="0 0 360 170" className="w-full max-w-md" aria-hidden>
      <defs>
        <linearGradient id="sw-login-blk" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#0f2a44" /><stop offset="1" stopColor="#0b1a2c" /></linearGradient>
        <linearGradient id="sw-login-ln" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#38bdf8" /><stop offset="1" stopColor="#10b981" /></linearGradient>
      </defs>
      {blocks.map((i) => (
        <g key={i} transform={`translate(${10 + i * 88}, 104)`}>
          <rect width="64" height="44" rx="9" fill="url(#sw-login-blk)" stroke="#1f4b6e" />
          <rect x="10" y="11" width="30" height="4" rx="2" fill="#38bdf8" opacity="0.8" />
          <rect x="10" y="20" width="44" height="3" rx="1.5" fill="#64748b" opacity="0.6" />
          <rect x="10" y="28" width="36" height="3" rx="1.5" fill="#64748b" opacity="0.45" />
          {i < 3 && <path d="M64 22h24" stroke="url(#sw-login-ln)" strokeWidth="2" strokeDasharray="4 3" />}
          <path d={`M32 0 L${32 + (1.5 - i) * 44} -36`} stroke="#1f4b6e" strokeWidth="1.2" />
        </g>
      ))}
      <g transform="translate(150, 30)">
        <rect width="60" height="38" rx="10" fill="#0b2a26" stroke="#10b981" />
        <text x="30" y="16" textAnchor="middle" fontSize="8" fill="#6ee7b7" fontFamily="ui-monospace, monospace">MERKLE</text>
        <text x="30" y="28" textAnchor="middle" fontSize="8" fill="#6ee7b7" fontFamily="ui-monospace, monospace">ROOT</text>
      </g>
      <path d="M210 49 C 260 49, 270 20, 312 20" stroke="url(#sw-login-ln)" strokeWidth="1.6" fill="none" />
      <g transform="translate(312, 6)">
        <circle cx="16" cy="14" r="14" fill="#0b1a2c" stroke="#38bdf8" />
        <path d="M16 7v14M10 15a6 6 0 0012 0M13 11h6" stroke="#7dd3fc" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  );
}

function Card({ subtitle, children, onSubmit }: { subtitle: string; children: React.ReactNode; onSubmit: (e: React.FormEvent) => void }) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden border-r border-soc-border bg-gradient-to-br from-[#0b1730] via-soc-bg to-[#06151a] p-10 lg:flex">
        <div className="flex items-center gap-3">
          <Logo size={40} />
          <div>
            <div className="text-base font-semibold tracking-wide text-slate-100">SilentWitness</div>
            <div className="text-xs text-soc-muted">Tamper-evident security logging</div>
          </div>
        </div>
        <div className="space-y-8">
          <h2 className="max-w-md text-3xl font-semibold leading-tight tracking-tight text-slate-50">
            Logs the attacker <span className="bg-gradient-to-r from-sky-300 to-emerald-300 bg-clip-text text-transparent">can&apos;t erase</span>.
          </h2>
          <ChainIllustration />
          <ul className="grid max-w-md gap-3 text-sm text-slate-300">
            <li className="flex gap-3"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />Every log is SHA-256 linked to the previous one: any edit breaks the chain.</li>
            <li className="flex gap-3"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />Merkle roots commit to whole batches with compact inclusion proofs.</li>
            <li className="flex gap-3"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />Roots are anchored on Quai Orchard (Cyprus-1) for an independent check.</li>
          </ul>
        </div>
        <p className="text-xs text-slate-500">An anchor proves a commitment is unchanged since anchoring; it does not prove that an event happened.</p>
      </section>
      <section className="flex items-center justify-center p-4 sm:p-8">
        <form onSubmit={onSubmit}
          className="w-full max-w-sm space-y-4 rounded-2xl border border-soc-border bg-gradient-to-b from-soc-panel2/80 to-soc-panel p-6 shadow-card sm:p-7">
          <div className="space-y-3">
            <div className="flex items-center gap-2 lg:hidden"><Logo size={30} /><span className="text-sm font-semibold text-slate-100">SilentWitness</span></div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-slate-50">Logs the Attacker Can&apos;t Erase</h1>
              <p className="mt-1 text-sm text-soc-muted">{subtitle}</p>
            </div>
          </div>
          {children}
        </form>
      </section>
    </main>
  );
}

/** Supabase Auth: email + password sign in / sign up. */
function SupabaseLogin() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const sb = supabase();
    if (!sb) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      if (mode === "signup") {
        const { data, error: err } = await sb.auth.signUp({ email, password });
        if (err) throw err;
        if (!data.session) {
          setNotice("Account created. Confirm the link sent to your email, then sign in.");
          setMode("signin");
          return;
        }
      } else {
        const { error: err } = await sb.auth.signInWithPassword({ email, password });
        if (err) throw err;
      }
      window.location.href = "/";  // full navigation so the live WebSocket connects with the new session
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card subtitle={mode === "signin" ? "Sign in to the SOC dashboard" : "Create your SOC dashboard account"} onSubmit={submit}>
      <label className="block text-sm">
        <span className="text-soc-muted">Email</span>
        <input data-testid="email" type="email" className="input mt-1 w-full" value={email}
          onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
      </label>
      <label className="block text-sm">
        <span className="text-soc-muted">Password{mode === "signup" ? " (at least 6 characters)" : ""}</span>
        <input data-testid="password" type="password" className="input mt-1 w-full" value={password} minLength={6}
          onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "signin" ? "current-password" : "new-password"} required />
      </label>
      {notice && <p data-testid="auth-notice" className="text-xs text-emerald-300">{notice}</p>}
      {error && <ErrorState message={error} />}
      <button data-testid="login" className="btn-primary w-full" disabled={busy}>
        {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
      </button>
      <button type="button" data-testid="toggle-mode" className="w-full text-xs text-sky-400 underline"
        onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); setNotice(null); }}>
        {mode === "signin" ? "No account yet? Create one" : "Already have an account? Sign in"}
      </button>
    </Card>
  );
}

/** Local mode (no Supabase configured): username admin, password = API_KEY from .env. */
function LocalLogin() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await post<{ access_token: string }>("/api/auth/login", { username: "admin", password });
      setToken(r.access_token);
      // full navigation so the live WebSocket connects with the new token
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card subtitle="SOC dashboard sign-in" onSubmit={submit}>
      <label className="block text-sm">
        <span className="text-soc-muted">Username</span>
        <input className="input mt-1 w-full" value="admin" readOnly />
      </label>
      <label className="block text-sm">
        <span className="text-soc-muted">Password (your API_KEY from .env)</span>
        <input data-testid="password" type="password" className="input mt-1 w-full" value={password}
          onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
      </label>
      <p className="text-xs text-soc-muted">
        Username <code className="text-sky-300">admin</code>, password = the <code className="text-sky-300">API_KEY</code> value in your <code className="text-sky-300">.env</code>.
      </p>
      {error && <ErrorState message={error} />}
      <button data-testid="login" className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </Card>
  );
}
