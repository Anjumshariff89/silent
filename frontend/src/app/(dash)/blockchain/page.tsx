"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { BlockchainStatus, MerkleBatchSummary, ProofVerify } from "@/lib/types";
import { Card, Empty, ErrorState, Hash, Loading, Pill } from "@/components/ui";
import { blockchainBadgeLabel, chainName, explorerAddress, explorerTx } from "@/lib/quai";

export default function BlockchainPage() {
  const live = useLive();
  const status = useApi<BlockchainStatus>("/api/blockchain/status", { refreshKey: live.last?.type === "anchor" ? live.counter : 0 });
  const batches = useApi<{ items: MerkleBatchSummary[] }>("/api/merkle/batches", { refreshKey: live.last?.type === "anchor" ? live.counter : 0 });
  const [results, setResults] = useState<Record<number, ProofVerify>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const s = status.data;
  // Explorer links only for anchors that were themselves REAL: a batch anchored earlier by the simulator keeps
  // its fake tx hash even after switching to REAL mode, and must never be linked to the explorer.
  const txLink = (tx: string | null, anchorMode: string | null) =>
    (anchorMode === "REAL" && s ? explorerTx(s.chain_id, tx) : null);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Blockchain Explorer</h1>
      <p className="text-sm text-soc-muted">Anchors are written to Quai Orchard (Cyprus-1, chain 15000) and can be checked on{" "}
        <a className="text-sky-400 underline" href="https://orchard.quaiscan.io" target="_blank" rel="noreferrer">Orchard QuaiScan</a>.
        A MATCH proves the batch&apos;s logs still hash to the root anchored on-chain. It does not prove that the events happened.</p>
      {err && <ErrorState message={err} />}
      <Card title="Network">
        {status.error ? <ErrorState message={status.error} onRetry={status.reload} /> : !s ? <Loading /> : (
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <div><dt className="text-soc-muted">Mode</dt><dd data-testid="chain-mode"><Pill value={s.mode} label={blockchainBadgeLabel(s.mode, s.chain_id)} /></dd></div>
            <div><dt className="text-soc-muted">Chain</dt><dd data-testid="chain-name">{chainName(s.chain_id)}</dd></div>
            <div><dt className="text-soc-muted">Connected</dt><dd><Pill value={s.connected ? "online" : "offline"} label={s.connected ? "yes" : "no"} /></dd></div>
            <div><dt className="text-soc-muted">Latest block</dt><dd data-testid="latest-block">{s.latest_block ?? "—"}</dd></div>
            {s.rpc_error && <div className="col-span-2 sm:col-span-4"><dt className="text-soc-muted">RPC error</dt><dd data-testid="rpc-error" className="text-xs text-amber-200">{s.rpc_error}</dd></div>}
            <div className="col-span-2"><dt className="text-soc-muted">Contract</dt><dd>{s.contract_address ? (
              explorerAddress(s.chain_id, s.contract_address)
                ? <a className="font-mono text-xs text-sky-400 underline" target="_blank" rel="noreferrer" href={explorerAddress(s.chain_id, s.contract_address)!}>{s.contract_address} ↗</a>
                : <code className="font-mono text-xs">{s.contract_address}</code>) : "not configured (set CONTRACT_ADDRESS in .env)"}</dd></div>
            <div className="col-span-2"><dt className="text-soc-muted">Anchor wallet</dt><dd className="font-mono text-xs">{s.anchor_wallet ?? "—"}</dd></div>
          </dl>
        )}
      </Card>
      <Card title="Batches">
        {batches.error ? <ErrorState message={batches.error} onRetry={batches.reload} /> : batches.loading && !batches.data ? <Loading /> :
          !batches.data?.items.length ? <Empty>No Merkle batches yet. Build one on the Merkle Tree page.</Empty> : (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Batch</th><th>Seq</th><th>Root</th><th>Anchor tx</th><th>Action</th><th>Proof check</th></tr></thead>
              <tbody>{batches.data.items.map((b) => {
                const r = results[b.batch_id];
                const link = txLink(b.tx_hash, b.mode);
                return (
                  <tr key={b.batch_id}>
                    <td>#{b.batch_id}</td><td>{b.from_seq}–{b.to_seq}</td><td><Hash value={b.root} /></td>
                    <td>{b.tx_hash ? (link ? <a href={link} target="_blank" rel="noreferrer" className="font-mono text-xs text-sky-400 underline">{b.tx_hash.slice(0, 14)}… ↗</a> : <span><Hash value={b.tx_hash} /> <Pill value={b.mode ?? "unknown"} /></span>) : <span className="text-soc-muted">not anchored</span>}</td>
                    <td className="space-x-1 whitespace-nowrap">
                      {!b.tx_hash && <button className="btn-primary" disabled={busy !== null} data-testid={`anchor-${b.batch_id}`} onClick={async () => {
                        setBusy(b.batch_id); setErr(null);
                        try { await post("/api/blockchain/anchor", { batch_id: b.batch_id }); batches.reload(); status.reload(); }
                        catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
                      }}>{busy === b.batch_id ? "Anchoring…" : "Anchor"}</button>}
                      <button className="btn-secondary" disabled={busy !== null} data-testid={`verify-${b.batch_id}`} onClick={async () => {
                        setBusy(b.batch_id); setErr(null);
                        try { const v = await post<ProofVerify>("/api/proof/verify", { batch_id: b.batch_id }); setResults((x) => ({ ...x, [b.batch_id]: v })); }
                        catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
                      }}>Verify</button>
                    </td>
                    <td>{r ? <span title={r.problems.join("; ")}><Pill value={r.result} /></span> : "—"}</td>
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
