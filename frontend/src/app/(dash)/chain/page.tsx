"use client";

import { useApi, useLive } from "@/lib/hooks";
import type { ChainLink } from "@/lib/types";
import { Card, Empty, ErrorState, Hash, Loading } from "@/components/ui";

export default function ChainPage() {
  const live = useLive();
  const chain = useApi<{ genesis_prev_hash: string; links: ChainLink[] }>("/api/chain?limit=24",
    { refreshKey: live.last?.type === "log" ? live.counter : 0 });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Hash-Chain Visualization</h1>
      <p className="text-sm text-soc-muted">
        Each block stores <code>curr_hash = SHA-256(prev_hash ‖ log)</code>. The first log links to the genesis value 0×64.
        Green = hash recomputes and links to its predecessor.
      </p>
      <Card title="Most recent links">
        {chain.error ? <ErrorState message={chain.error} onRetry={chain.reload} /> : chain.loading && !chain.data ? <Loading /> :
          !chain.data?.links.length ? <Empty>No logs yet.</Empty> : (
          <div className="flex flex-wrap items-stretch gap-2">
            {chain.data.links.map((l, i) => {
              const ok = l.hash_valid && l.link_valid;
              return (
                <div key={l.seq_id} className="flex items-center gap-2">
                  {i > 0 && <span className={ok ? "text-emerald-500" : "text-red-500"} aria-hidden>→</span>}
                  <div data-testid={`block-${l.seq_id}`} className={`w-44 rounded border p-2 text-xs ${ok ? "border-emerald-600/50 bg-emerald-500/5" : "border-red-500 bg-red-500/10"}`}>
                    <div className="flex justify-between font-semibold"><span>#{l.seq_id}</span><span className="text-soc-muted">{l.event_type}</span></div>
                    <div className="mt-1 text-soc-muted">prev <Hash value={l.prev_hash} n={10} /></div>
                    <div className="text-soc-muted">curr <Hash value={l.curr_hash} n={10} /></div>
                    {!ok && <div className="mt-1 text-red-300">{!l.hash_valid ? "hash mismatch" : "broken link"}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
