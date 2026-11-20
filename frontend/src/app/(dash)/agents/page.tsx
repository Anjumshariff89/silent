"use client";

import { useApi, useLive } from "@/lib/hooks";
import type { Agent } from "@/lib/types";
import { Card, Empty, ErrorState, fmtTime, Loading, Pill, StatusDot } from "@/components/ui";

interface Heartbeat { id: number; agent_id: string; collector_mode: string; received_at: string }

export default function AgentsPage() {
  const live = useLive();
  const agents = useApi<{ items: Agent[] }>("/api/agents", { intervalMs: 5000, refreshKey: live.last?.type === "agent_status" ? live.counter : 0 });
  const hbs = useApi<{ items: Heartbeat[] }>("/api/heartbeats?limit=20", { intervalMs: 10000 });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Agent Monitoring</h1>
      <p className="text-sm text-soc-muted">Agents send a heartbeat every 10 s. Online ≤ 20 s, delayed ≤ 60 s, offline after that (incident + alert).</p>
      <Card title="Agents">
        {agents.error ? <ErrorState message={agents.error} onRetry={agents.reload} /> : agents.loading && !agents.data ? <Loading /> :
          !agents.data?.items.length ? <Empty>No agents registered yet. Start the agent.</Empty> : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {agents.data.items.map((a) => (
              <div key={a.agent_id} data-testid={`agent-${a.agent_id}`} className="rounded border border-soc-border p-3">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 font-medium"><StatusDot status={a.status} pulse={a.status === "online"} />{a.agent_id}</span>
                  <Pill value={a.status} />
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-1 text-xs text-soc-muted">
                  <dt>Host</dt><dd className="text-slate-300">{a.hostname}</dd>
                  <dt>Collector</dt><dd className="text-slate-300">{a.collector_mode}</dd>
                  <dt>Version</dt><dd className="text-slate-300">{a.agent_version}</dd>
                  <dt>Last heartbeat</dt><dd className="text-slate-300">{a.seconds_since_heartbeat == null ? "never" : `${a.seconds_since_heartbeat}s ago`}</dd>
                </dl>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Recent heartbeats">
        {hbs.error ? <ErrorState message={hbs.error} onRetry={hbs.reload} /> : hbs.loading && !hbs.data ? <Loading /> :
          !hbs.data?.items.length ? <Empty>No heartbeats yet.</Empty> : (
          <table className="tbl"><thead><tr><th>#</th><th>Agent</th><th>Collector</th><th>Received</th></tr></thead>
            <tbody>{hbs.data.items.map((h) => (<tr key={h.id}><td>{h.id}</td><td>{h.agent_id}</td><td>{h.collector_mode}</td><td>{fmtTime(h.received_at)}</td></tr>))}</tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
