"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { Incident, Page } from "@/lib/types";
import { Card, Empty, ErrorState, fmtTime, Loading, Pill } from "@/components/ui";

export default function AlertsPage() {
  const live = useLive();
  const [type, setType] = useState("");
  const [target, setTarget] = useState("");
  const qs = new URLSearchParams({ status: "open", page_size: "100" });
  if (type) qs.set("type", type);
  if (target) qs.set("target", target);
  const inc = useApi<Page<Incident>>(`/api/incidents?${qs}`, { refreshKey: live.last?.type === "incident" ? live.counter : 0 });
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Tamper Alerts</h1>
        <button className="btn-secondary" onClick={async () => {
          try { await post(`/api/incidents/resolve${target ? `?target=${target}` : ""}`); inc.reload(); }
          catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
        }}>Acknowledge all shown</button>
      </div>
      {err && <ErrorState message={err} />}
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <select className="input" value={type} onChange={(e) => setType(e.target.value)} aria-label="Type">
            <option value="">All types</option>{["modified", "missing", "reordered", "merkle_mismatch", "heartbeat_timeout"].map((t) => <option key={t}>{t}</option>)}
          </select>
          <select className="input" value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Target">
            <option value="">Live + sandbox</option><option value="live">Live only</option><option value="sandbox">Sandbox demo only</option>
          </select>
        </div>
        {inc.error ? <ErrorState message={inc.error} onRetry={inc.reload} /> : inc.loading && !inc.data ? <Loading /> :
          !inc.data?.items.length ? <Empty>No open alerts. 🎉</Empty> : (
          <div className="space-y-2">{inc.data.items.map((i) => (
            <div key={i.id} className={`rounded border p-3 ${i.severity === "critical" ? "border-red-500/50 bg-red-500/5" : "border-amber-500/40 bg-amber-500/5"}`}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Pill value={i.severity} /><span className="font-semibold uppercase">{i.type}</span>
                {i.seq_id != null && <span className="text-soc-muted">seq {i.seq_id}</span>}
                {i.agent_id && <span className="text-soc-muted">agent {i.agent_id}</span>}
                {i.batch_id != null && <span className="text-soc-muted">batch {i.batch_id}</span>}
                <Pill value={i.target} />
                <span className="ml-auto text-xs text-soc-muted">#{i.id} · {fmtTime(i.created_at)} · alert via {i.alert_channel ?? "—"}</span>
              </div>
              <p className="mt-1 text-sm text-slate-300">{i.description}</p>
            </div>
          ))}</div>
        )}
      </Card>
    </div>
  );
}
