"use client";

import Link from "next/link";
import { useState } from "react";
import { post } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { Agent, BlockchainStatus, IntegrityStatus, Page, SecurityLog, VerifyResult } from "@/lib/types";
import { IconAnchor, IconBell, IconCpu, IconList, IconShieldCheck } from "@/components/icons";
import { Card, ErrorState, fmtTime, Hash, Loading, Pill, Stat } from "@/components/ui";
import { blockchainBadgeLabel, chainName } from "@/lib/quai";

export default function OverviewPage() {
  const live = useLive();
  const integrity = useApi<IntegrityStatus>("/api/integrity/status", { refreshKey: live.counter });
  const agents = useApi<{ items: Agent[] }>("/api/agents", { intervalMs: 10000 });
  const chain = useApi<BlockchainStatus>("/api/blockchain/status");
  const logs = useApi<Page<SecurityLog>>("/api/logs?page_size=8", { refreshKey: live.counter });
  const [verifying, setVerifying] = useState(false);
  const [verifyErr, setVerifyErr] = useState<string | null>(null);

  const online = agents.data?.items.filter((a) => a.status === "online").length ?? 0;
  const err = integrity.error || agents.error || chain.error;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Overview</h1>
        <button className="btn-primary" disabled={verifying} data-testid="verify-now" onClick={async () => {
          setVerifying(true); setVerifyErr(null);
          try { await post<VerifyResult>("/api/verify"); integrity.reload(); }
          catch (e) { setVerifyErr(e instanceof Error ? e.message : String(e)); }
          finally { setVerifying(false); }
        }}>{verifying ? "Verifying…" : "Verify chain now"}</button>
      </div>
      {err && <ErrorState message={err} onRetry={() => { integrity.reload(); agents.reload(); chain.reload(); }} />}
      {verifyErr && <ErrorState message={verifyErr} />}
      {integrity.loading && !integrity.data ? <Loading /> : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat icon={<IconShieldCheck size={16} />} label="Integrity" tone={integrity.data?.status} value={integrity.data?.last_result ?? "—"} />
          <Stat icon={<IconList size={16} />} label="Total logs" value={integrity.data?.total_logs ?? "—"} />
          <Stat icon={<IconCpu size={16} />} label="Agents online" tone={online ? "online" : "offline"} value={`${online}/${agents.data?.items.length ?? 0}`} />
          <Stat icon={<IconBell size={16} />} label="Open incidents" tone={integrity.data?.open_incidents ? "red" : "green"} value={integrity.data?.open_incidents ?? "—"} />
          <Stat icon={<IconAnchor size={16} />} label="Anchored batches" value={chain.data?.anchored_batches ?? "—"} />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Latest logs" className="lg:col-span-2" actions={<Link className="text-xs text-sky-400" href="/logs">All logs →</Link>}>
          {logs.error ? <ErrorState message={logs.error} onRetry={logs.reload} /> : logs.loading && !logs.data ? <Loading /> : (
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead><tr><th>Seq</th><th>Event</th><th>User</th><th>Severity</th><th>Hash</th><th>Received</th></tr></thead>
                <tbody>{logs.data?.items.map((l) => (
                  <tr key={l.seq_id}><td>{l.seq_id}</td><td>{l.event_id} {l.event_type}</td><td>{l.username}</td>
                    <td><Pill value={l.severity} /></td><td><Hash value={l.curr_hash} /></td><td className="text-xs">{fmtTime(l.received_at)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Blockchain anchoring">
          {chain.loading && !chain.data ? <Loading /> : chain.data && (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-soc-muted">Mode</dt><dd><Pill value={chain.data.mode} label={blockchainBadgeLabel(chain.data.mode, chain.data.chain_id)} /></dd></div>
              <div className="flex justify-between"><dt className="text-soc-muted">Network</dt><dd>{chainName(chain.data.chain_id)}</dd></div>
              <div className="flex justify-between"><dt className="text-soc-muted">Connected</dt><dd><Pill value={chain.data.connected ? "online" : "offline"} label={chain.data.connected ? "yes" : "no"} /></dd></div>
              <div className="flex justify-between"><dt className="text-soc-muted">Last anchor tx</dt><dd><Hash value={chain.data.last_anchor?.tx_hash} /></dd></div>
              <p className="pt-2 text-xs text-soc-muted">Anchoring proves a batch root is unchanged since anchoring. It does not prove events happened.</p>
            </dl>
          )}
        </Card>
      </div>
    </div>
  );
}
