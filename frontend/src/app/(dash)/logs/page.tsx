"use client";

import { useMemo, useState } from "react";
import { useApi, useLive } from "@/lib/hooks";
import type { Page, SecurityLog } from "@/lib/types";
import { TamperButton } from "@/components/TamperButton";
import { Card, Empty, ErrorState, fmtTime, Hash, Loading, Pill } from "@/components/ui";

const PAGE_SIZE = 25;

export default function LogsPage() {
  const live = useLive();
  const [q, setQ] = useState("");
  const [eventId, setEventId] = useState("");
  const [severity, setSeverity] = useState("");
  const [agent, setAgent] = useState("");
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState<string | null>(null);

  const path = useMemo(() => {
    const p = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (q) p.set("q", q);
    if (eventId) p.set("event_id", eventId);
    if (severity) p.set("severity", severity);
    if (agent) p.set("agent_id", agent);
    return `/api/logs?${p}`;
  }, [q, eventId, severity, agent, page]);
  const logs = useApi<Page<SecurityLog>>(path, { refreshKey: live.last?.type === "log" ? live.counter : 0 });
  const pages = Math.max(1, Math.ceil((logs.data?.total ?? 0) / PAGE_SIZE));

  function exportJson() {
    const blob = new Blob([JSON.stringify(logs.data?.items ?? [], null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `logs_page_${page}.json`; a.click(); URL.revokeObjectURL(a.href);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Live Logs</h1>
        <span className="text-xs text-soc-muted">{live.connected ? "Streaming new logs via WebSocket" : "Live stream disconnected"}</span>
      </div>
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <input className="input min-w-[12rem] flex-1" placeholder="Search message, user, host…" value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1); }} data-testid="search" />
          <select className="input" value={eventId} onChange={(e) => { setEventId(e.target.value); setPage(1); }} aria-label="Event ID">
            <option value="">All events</option><option value="4624">4624 logon</option><option value="4634">4634 logoff</option>
            <option value="4672">4672 special privileges</option><option value="4673">4673 privileged service</option>
          </select>
          <select className="input" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }} aria-label="Severity">
            <option value="">All severities</option><option value="info">info</option><option value="warning">warning</option><option value="critical">critical</option>
          </select>
          <input className="input w-40" placeholder="Agent ID" value={agent} onChange={(e) => { setAgent(e.target.value); setPage(1); }} />
          <button className="btn-secondary" onClick={exportJson} disabled={!logs.data?.items.length}>Export JSON</button>
        </div>
        {notice && <div className="mb-3 rounded border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-200" data-testid="tamper-notice">{notice}</div>}
        {logs.error ? <ErrorState message={logs.error} onRetry={logs.reload} /> : logs.loading && !logs.data ? <Loading /> :
          !logs.data?.items.length ? <Empty>No logs match these filters.</Empty> : (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Seq</th><th>Time</th><th>Agent</th><th>Event</th><th>Severity</th><th>User</th><th>Source IP</th><th>Message</th><th>Hash</th><th>Demo</th></tr></thead>
              <tbody>{logs.data.items.map((l) => (
                <tr key={l.seq_id}>
                  <td className="font-mono">{l.seq_id}</td><td className="whitespace-nowrap text-xs">{fmtTime(l.event_time)}</td>
                  <td className="whitespace-nowrap">{l.agent_id}</td><td className="whitespace-nowrap">{l.event_id} <span className="text-soc-muted">{l.event_type}</span></td>
                  <td><Pill value={l.severity} /></td><td>{l.username ?? "—"}</td><td className="font-mono text-xs">{l.source_ip ?? "—"}</td>
                  <td className="max-w-[14rem] truncate" title={l.message}>{l.message}</td><td><Hash value={l.curr_hash} /></td>
                  <td className="whitespace-nowrap"><TamperButton seqId={l.seq_id} onDone={(r) => setNotice(
                    `${r.attack} → verification ${r.verification.result} (${r.verification.issues.map((i) => `${i.type} @ ${i.seq_id}`).join(", ")}). ` +
                    `Original data unchanged: ${r.original_unchanged}.`)} /></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <div className="mt-3 flex items-center justify-between text-sm text-soc-muted">
          <span>{logs.data?.total ?? 0} logs</span>
          <div className="flex items-center gap-2">
            <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
            <span>Page {page} / {pages}</span>
            <button className="btn-secondary" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        </div>
      </Card>
    </div>
  );
}
