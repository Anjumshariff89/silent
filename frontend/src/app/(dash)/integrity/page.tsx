"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { IntegrityStatus, VerifyResult } from "@/lib/types";
import { Card, ErrorState, fmtTime, Loading, Pill, StatusDot } from "@/components/ui";

export default function IntegrityPage() {
  const live = useLive();
  const status = useApi<IntegrityStatus>("/api/integrity/status", { refreshKey: live.counter });
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [seq, setSeq] = useState("2");
  const [kind, setKind] = useState<"modify" | "delete" | "reorder">("modify");

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label); setErr(null);
    try { await fn(); status.reload(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  }

  const s = status.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Integrity Verification</h1>
      {err && <ErrorState message={err} />}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Current status">
          {status.error ? <ErrorState message={status.error} onRetry={status.reload} /> : !s ? <Loading /> : (
            <div className="space-y-3">
              <div className={`flex items-center gap-3 rounded p-3 text-lg font-bold ${s.status === "red" ? "bg-red-500/15 text-red-300" : s.status === "green" ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"}`}
                data-testid="integrity-status" data-status={s.status}>
                <StatusDot status={s.status} pulse={s.status === "red"} /> {s.status.toUpperCase()}
              </div>
              <dl className="grid grid-cols-2 gap-1 text-sm">
                <dt className="text-soc-muted">Last result</dt><dd>{s.last_result ? <Pill value={s.last_result} /> : "never verified"}</dd>
                <dt className="text-soc-muted">Target</dt><dd>{s.last_target ? <Pill value={s.last_target} /> : "—"}</dd>
                <dt className="text-soc-muted">Verified at</dt><dd>{fmtTime(s.last_verified_at)}</dd>
                <dt className="text-soc-muted">Logs</dt><dd>{s.total_logs}</dd>
                <dt className="text-soc-muted">Open incidents</dt><dd>{s.open_incidents} ({s.open_critical_incidents} critical)</dd>
              </dl>
              {s.last_issues.length > 0 && (
                <ul className="space-y-1 text-sm">{s.last_issues.map((i, k) => (
                  <li key={k} className="rounded bg-red-500/10 px-2 py-1"><Pill value="critical" label={i.type} /> seq {i.seq_id}: {i.detail}</li>
                ))}</ul>
              )}
            </div>
          )}
        </Card>
        <Card title="Actions">
          <div className="space-y-4">
            <div>
              <button className="btn-primary" disabled={!!busy} data-testid="run-verify"
                onClick={() => run("verify", async () => setResult(await post<VerifyResult>("/api/verify")))}>
                {busy === "verify" ? "Verifying…" : "Verify full chain (live data)"}
              </button>
              {result && <p className="mt-2 text-sm">Result: <Pill value={result.result} /> — checked {result.checked_count} logs, {result.issues.length} issue(s).</p>}
            </div>
            <div className="rounded border border-red-500/30 p-3">
              <h3 className="mb-2 text-sm font-semibold text-red-300">Tamper demo (sandbox copy only)</h3>
              <p className="mb-2 text-xs text-soc-muted">The server copies all logs to a sandbox database, applies the attack there and verifies it. Live logs are never changed.</p>
              <div className="flex flex-wrap gap-2">
                <select className="input" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="Attack">
                  <option value="modify">Modify a log</option><option value="delete">Delete a log</option><option value="reorder">Reorder two logs</option>
                </select>
                <input className="input w-24" type="number" min={1} value={seq} onChange={(e) => setSeq(e.target.value)} aria-label="Seq ID" />
                <button className="btn-danger" disabled={!!busy} data-testid="run-tamper"
                  onClick={() => run("tamper", async () => { await post("/api/demo/tamper", { seq_id: Number(seq), kind }); })}>
                  {busy === "tamper" ? "Attacking…" : "Run attack"}
                </button>
                <button className="btn-secondary" disabled={!!busy} data-testid="reset-demo"
                  onClick={() => run("reset", async () => { await post("/api/demo/reset"); })}>Reset demo</button>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
