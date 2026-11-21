"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { AnchorVerify, BlockchainStatus, MerkleRootItem, UserAnchor } from "@/lib/types";
import { blockchainBadgeLabel, chainName } from "@/lib/quai";
import { Card, Empty, ErrorState, fmtTime, Hash, Loading, Pill } from "@/components/ui";

/** Your Merkle roots anchored on Quai Orchard Cyprus-1: tx hash, status, explorer link, on-chain verification. */
export default function MyAnchorsPage() {
  const [refresh, setRefresh] = useState(0);
  const anchors = useApi<{ items: UserAnchor[] }>("/anchors", { refreshKey: refresh });
  const roots = useApi<{ items: MerkleRootItem[] }>("/merkle/roots", { refreshKey: refresh });
  const chain = useApi<BlockchainStatus>("/api/blockchain/status", { intervalMs: 30000 });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, AnchorVerify>>({});

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); setRefresh((r) => r + 1); }
  }

  const unanchored = (roots.data?.items ?? []).filter((r) => r.anchor_status !== "confirmed");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">My Anchors</h1>
      <p className="text-sm text-soc-muted">An anchor proves only that the anchored Merkle root has not changed since anchoring; it does not prove that an event happened.</p>
      {err && <ErrorState message={err} />}

      <Card title="Network">
        {chain.error ? <ErrorState message={chain.error} onRetry={chain.reload} /> : !chain.data ? <Loading /> : (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Pill value={chain.data.mode} label={blockchainBadgeLabel(chain.data.mode, chain.data.chain_id)} />
            <span>{chainName(chain.data.chain_id)}</span>
            <span>connected: {chain.data.connected ? "yes" : "no"}</span>
            <span>latest block: {chain.data.latest_block ?? "—"}</span>
            {chain.data.rpc_error && <span className="text-amber-200">{chain.data.rpc_error}</span>}
          </div>
        )}
      </Card>

      <Card title="Merkle roots waiting for an anchor">
        {roots.error ? <ErrorState message={roots.error} onRetry={roots.reload} /> : !roots.data ? <Loading /> :
          !unanchored.length ? <Empty>Nothing to anchor. Build a Merkle root on My Dashboard first.</Empty> : (
            <ul className="space-y-2 text-sm">{unanchored.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <Hash value={r.root} n={16} /> <span>{r.leaf_count} logs (#{r.from_seq}–#{r.to_seq})</span>
                {r.anchor_status && <Pill value={r.anchor_status} />}
                <button data-testid={`me-anchor-${r.id}`} className="btn-primary" disabled={!!busy}
                  onClick={() => run(r.id, async () => { await post<UserAnchor>("/anchor", { merkle_root_id: r.id }); })}>
                  {busy === r.id ? "Anchoring…" : "Anchor on Quai"}
                </button>
              </li>
            ))}</ul>
          )}
      </Card>

      <Card title="Anchors">
        {anchors.error ? <ErrorState message={anchors.error} onRetry={anchors.reload} /> : anchors.loading && !anchors.data ? <Loading /> :
          !anchors.data?.items.length ? <Empty>No anchors yet.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="me-anchors">
                <thead><tr><th>Merkle root</th><th>Logs</th><th>Transaction</th><th>Chain</th><th>Status</th><th>Updated</th><th>Check</th></tr></thead>
                <tbody>{anchors.data.items.map((a) => {
                  const chk = checks[a.id];
                  return (
                    <tr key={a.id}>
                      <td><Hash value={a.root} /></td>
                      <td>#{a.from_seq}–#{a.to_seq}</td>
                      <td>{a.tx_hash ? (a.explorer_url
                        ? <a className="font-mono text-xs text-sky-400 underline" href={a.explorer_url} target="_blank" rel="noreferrer">{a.tx_hash.slice(0, 14)}… ↗</a>
                        : <Hash value={a.tx_hash} />) : <span className="text-soc-muted">{a.error ?? "—"}</span>}</td>
                      <td>{a.chain_id}</td>
                      <td><Pill value={a.status} /></td>
                      <td>{fmtTime(a.updated_at)}</td>
                      <td className="whitespace-nowrap">
                        <button data-testid={`me-verify-anchor-${a.id}`} className="btn-secondary" disabled={!!busy}
                          onClick={() => run(`v-${a.id}`, async () => {
                            const v = await post<AnchorVerify>(`/anchors/${a.id}/verify`);
                            setChecks((x) => ({ ...x, [a.id]: v }));
                          })}>{busy === `v-${a.id}` ? "Checking…" : "Verify"}</button>
                        {chk && <span className="ml-2" title={chk.problems.join("; ")}><Pill value={chk.result} /></span>}
                      </td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </div>
          )}
      </Card>
    </div>
  );
}
