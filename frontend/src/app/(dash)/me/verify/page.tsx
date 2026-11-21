"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { UserVerify } from "@/lib/types";
import { Card, ErrorState, fmtTime, Pill, StatusDot } from "@/components/ui";

/** Recompute every hash and link of your chain; any edit, deletion or reordering makes it FAIL. */
export default function MyVerifyPage() {
  const [result, setResult] = useState<UserVerify | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function verify() {
    setBusy(true); setErr(null);
    try { setResult(await api<UserVerify>("/verify")); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  const ok = result?.result === "PASS";
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">My Verify</h1>
      <Card title="Hash-chain verification" actions={
        <button data-testid="me-verify" className="btn-primary" disabled={busy} onClick={verify}>{busy ? "Verifying…" : "Verify my chain"}</button>}>
        {err && <ErrorState message={err} onRetry={verify} />}
        {!result && !err && <p className="text-sm text-soc-muted">Recomputes SHA-256(prev_hash + content) for every one of your logs and checks every link.</p>}
        {result && (
          <div className="space-y-3">
            <div data-testid="me-verify-result" data-result={result.result}
              className={`flex items-center gap-3 rounded p-3 text-lg font-bold ${ok ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
              <StatusDot status={result.result} pulse={!ok} /> {ok ? "PASS: no tampering detected" : "FAIL: tampering detected"}
            </div>
            <dl className="grid grid-cols-2 gap-1 text-sm">
              <dt className="text-soc-muted">Verified records</dt><dd data-testid="me-verify-count">{result.checked_count}</dd>
              <dt className="text-soc-muted">Issues</dt><dd>{result.issues.length}</dd>
              <dt className="text-soc-muted">Verified at</dt><dd>{fmtTime(result.verified_at)}</dd>
            </dl>
            {result.issues.length > 0 && (
              <ul className="space-y-1 text-sm">{result.issues.map((i, k) => (
                <li key={k} className="rounded bg-red-500/10 px-2 py-1"><Pill value="critical" label={i.type} /> seq {i.seq_id}: {i.detail}</li>
              ))}</ul>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
