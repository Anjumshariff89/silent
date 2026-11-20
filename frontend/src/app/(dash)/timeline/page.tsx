"use client";

import { useApi, useLive } from "@/lib/hooks";
import type { Incident, Page } from "@/lib/types";
import { Card, Empty, ErrorState, fmtTime, Loading, Pill, StatusDot } from "@/components/ui";

export default function TimelinePage() {
  const live = useLive();
  const inc = useApi<Page<Incident>>("/api/incidents?page_size=200", { refreshKey: live.last?.type === "incident" ? live.counter : 0 });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Incident Timeline</h1>
      <Card>
        {inc.error ? <ErrorState message={inc.error} onRetry={inc.reload} /> : inc.loading && !inc.data ? <Loading /> :
          !inc.data?.items.length ? <Empty>No incidents recorded.</Empty> : (
          <ol className="relative ml-2 border-l border-soc-border">
            {inc.data.items.map((i) => (
              <li key={i.id} className="mb-5 ml-5">
                <span className="absolute -left-[5px] mt-1.5"><StatusDot status={i.status === "resolved" ? "slate" : i.severity} /></span>
                <time className="text-xs text-soc-muted">{fmtTime(i.created_at)}</time>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-semibold uppercase">{i.type}</span><Pill value={i.status} /><Pill value={i.target} />
                  {i.seq_id != null && <span className="text-soc-muted">seq {i.seq_id}</span>}
                  {i.agent_id && <span className="text-soc-muted">{i.agent_id}</span>}
                </div>
                <p className="text-sm text-slate-300">{i.description}</p>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
