"use client";

import { useState } from "react";
import { post, setToken } from "@/lib/api";
import { ErrorState } from "@/components/ui";
import { SUPABASE_ENABLED, supabase } from "@/lib/supabase";

export default function LoginPage() {
  return SUPABASE_ENABLED ? <SupabaseLogin /> : <LocalLogin />;
}

function Card({ subtitle, children, onSubmit }: { subtitle: string; children: React.ReactNode; onSubmit: (e: React.FormEvent) => void }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border border-soc-border bg-soc-panel p-6">
        <div>
          <h1 className="text-lg font-bold">Logs the Attacker Can&apos;t Erase</h1>
          <p className="text-sm text-soc-muted">{subtitle}</p>
        </div>
        {children}
      </form>
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
