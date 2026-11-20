"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { post, setToken, USE_MOCK } from "@/lib/api";
import { ErrorState } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
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
    <main className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-lg border border-soc-border bg-soc-panel p-6">
        <div>
          <h1 className="text-lg font-bold">Logs the Attacker Can&apos;t Erase</h1>
          <p className="text-sm text-soc-muted">SOC dashboard sign-in</p>
        </div>
        <label className="block text-sm">
          <span className="text-soc-muted">Username</span>
          <input className="input mt-1 w-full" value="admin" readOnly />
        </label>
        <label className="block text-sm">
          <span className="text-soc-muted">Password (your API_KEY from .env)</span>
          <input data-testid="password" type="password" className="input mt-1 w-full" value={password}
            onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required={!USE_MOCK} />
        </label>
        <p className="text-xs text-soc-muted">
          Simulator mode with an empty API_KEY uses the development key <code className="text-sky-300">dev-local-api-key</code>.
        </p>
        {error && <ErrorState message={error} />}
        <button data-testid="login" className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {USE_MOCK && <button type="button" className="btn-secondary w-full" onClick={() => router.push("/")}>Continue with mock data</button>}
      </form>
    </main>
  );
}
