"use client";

import { useState } from "react";
import Link from "next/link";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Agent, MerkleRootItem, Page, UserAnchor, UserLog, UserVerify } from "@/lib/types";
import { Card, Empty, ErrorState, fmtTime, Hash, Loading, Pill, Stat } from "@/components/ui";

/** Your own tamper-evident log: add entries, see chain status, latest Merkle root and anchor. */
export default function MyDashboardPage() {
  const [refresh, setRefresh] = useState(0);
  const logs = useApi<Page<UserLog>>("/logs?page_size=10", { refreshKey: refresh });
  const verify = useApi<UserVerify>("/verify", { refreshKey: refresh });
  const roots = useApi<{ items: MerkleRootItem[] }>("/merkle/roots", { refreshKey: refresh });
  const anchors = useApi<{ items: UserAnchor[] }>("/anchors", { refreshKey: refresh });
  const agents = useApi<{ items: Agent[] }>("/api/agents", { intervalMs: 15000 });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<string>) {
    setBusy(label); setErr(null); setNote(null);
    try { setNote(await fn()); setRefresh((r) => r + 1); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }

  const latestRoot = roots.data?.items[0];
  const latestAnchor = anchors.data?.items[0];
  const v = verify.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">My Dashboard</h1>
      <p className="text-sm text-soc-muted">Your own hash chain: every entry is SHA-256 linked to your previous one. Other users cannot see it.</p>
      {err && <ErrorState message={err} />}
      {note && <p data-testid="me-note" className="text-sm text-emerald-300">{note}</p>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total logs" value={logs.data ? logs.data.total : "—"} />
        <Stat label="Hash chain" value={v ? v.result : verify.error ? "error" : "…"} tone={v ? v.result : undefined} />
        <Stat label="Latest Merkle root" value={latestRoot ? <Hash value={latestRoot.root} n={10} /> : "none"} />
        <Stat label="Latest anchor" value={latestAnchor ? <Pill value={latestAnchor.status} /> : "none"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Add a log entry" className="lg:col-span-2">
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => {
            e.preventDefault();
            run("add", async () => {
              const r = await post<UserLog>("/logs", { message });
              setMessage("");
              return `Saved as #${r.seq}, hash ${r.hash.slice(0, 16)}…`;
            });
          }}>
            <input data-testid="me-message" className="input flex-1" value={message} maxLength={4000} required
              placeholder="e.g. Rotated the admin password on server-01" onChange={(e) => setMessage(e.target.value)} />
            <button data-testid="me-add" className="btn-primary" disabled={!!busy || !message.trim()}>{busy === "add" ? "Saving…" : "Add"}</button>
          </form>
        </Card>
        <Card title="Actions">
          <div className="flex flex-wrap gap-2">
            <button data-testid="me-build" className="btn-secondary" disabled={!!busy}
              onClick={() => run("build", async () => {
                const r = await post<MerkleRootItem>("/merkle/build");
                return `Merkle root over ${r.leaf_count} log(s): ${r.root.slice(0, 16)}…`;
              })}>{busy === "build" ? "Building…" : "Build Merkle root"}</button>
            <Link href="/me/verify" className="btn-secondary">Verify</Link>
            <Link href="/me/anchors" className="btn-secondary">Anchors</Link>
          </div>
        </Card>
      </div>

      <Card title="Recent logs">
        {logs.error ? <ErrorState message={logs.error} onRetry={logs.reload} /> : logs.loading && !logs.data ? <Loading /> :
          !logs.data?.items.length ? <Empty>No logs yet: add your first entry above.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="me-logs">
                <thead><tr><th>#</th><th>Message</th><th>Hash</th><th>Prev hash</th><th>Time</th></tr></thead>
                <tbody>{logs.data.items.map((l) => (
                  <tr key={l.id}><td>{l.seq}</td><td className="max-w-md truncate">{l.message}</td><td><Hash value={l.hash} /></td>
                    <td><Hash value={l.prev_hash} /></td><td>{fmtTime(l.created_at)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
      </Card>

      <Card title="Agent heartbeats (shared SOC agents)">
        {agents.error ? <ErrorState message={agents.error} onRetry={agents.reload} /> : !agents.data ? <Loading /> :
          !agents.data.items.length ? <Empty>No agents have reported yet.</Empty> : (
            <ul className="space-y-1 text-sm">{agents.data.items.map((a) => (
              <li key={a.agent_id}><Pill value={a.status} /> {a.agent_id} ({a.hostname}) · last heartbeat {fmtTime(a.last_heartbeat)}</li>
            ))}</ul>
          )}
      </Card>
    </div>
  );
}
