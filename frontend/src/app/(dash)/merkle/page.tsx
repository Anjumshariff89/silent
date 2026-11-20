"use client";

import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { MerkleBatch, MerkleBatchSummary, MerkleProof } from "@/lib/types";
import { Card, Empty, ErrorState, fmtTime, Hash, Loading, Pill } from "@/components/ui";

const MAX_NODES_SHOWN = 16;

export default function MerklePage() {
  const batches = useApi<{ items: MerkleBatchSummary[] }>("/api/merkle/batches");
  const [selected, setSelected] = useState<number | null>(null);
  const batch = useApi<MerkleBatch>(selected ? `/api/merkle/${selected}` : null);
  const [seq, setSeq] = useState("");
  const [proof, setProof] = useState<MerkleProof | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (selected == null && batches.data?.items.length) setSelected(batches.data.items[0].batch_id);
  }, [batches.data, selected]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Merkle Tree View</h1>
        <button className="btn-primary" disabled={busy} data-testid="build-batch" onClick={async () => {
          setBusy(true); setErr(null);
          try { const b = await post<MerkleBatchSummary>("/api/merkle/build"); batches.reload(); setSelected(b.batch_id); }
          catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
        }}>{busy ? "Building…" : "Build batch from unbatched logs"}</button>
      </div>
      {err && <ErrorState message={err} />}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Batches">
          {batches.error ? <ErrorState message={batches.error} onRetry={batches.reload} /> : batches.loading && !batches.data ? <Loading /> :
            !batches.data?.items.length ? <Empty>No batches yet.</Empty> : (
            <ul className="space-y-1">{batches.data.items.map((b) => (
              <li key={b.batch_id}>
                <button onClick={() => { setSelected(b.batch_id); setProof(null); }}
                  className={`w-full rounded px-2 py-1.5 text-left text-sm ${selected === b.batch_id ? "bg-sky-500/15" : "hover:bg-white/5"}`}>
                  <div className="flex justify-between"><span>Batch #{b.batch_id}</span>{b.tx_hash ? <Pill value="MATCH" label="anchored" /> : <Pill value="NOT_ANCHORED" label="not anchored" />}</div>
                  <div className="text-xs text-soc-muted">seq {b.from_seq}–{b.to_seq} · {b.leaf_count} leaves</div>
                </button>
              </li>
            ))}</ul>
          )}
        </Card>
        <Card title={selected ? `Batch #${selected}` : "Tree"} className="lg:col-span-2">
          {!selected ? <Empty>Select a batch.</Empty> : batch.error ? <ErrorState message={batch.error} onRetry={batch.reload} /> :
            !batch.data ? <Loading /> : (
            <div className="space-y-4">
              <div className="text-sm">Root: <code className="break-all font-mono text-xs text-emerald-300">{batch.data.root}</code></div>
              <div className="text-xs text-soc-muted">Created {fmtTime(batch.data.created_at)} · leaf = SHA-256(0x00‖curr_hash), node = SHA-256(0x01‖L‖R)</div>
              <div className="space-y-2 overflow-x-auto" data-testid="merkle-tree">
                {[...batch.data.levels].reverse().map((lvl, depth) => (
                  <div key={depth} className="flex justify-center gap-1">
                    {lvl.slice(0, MAX_NODES_SHOWN).map((h, i) => (
                      <span key={i} title={h} className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${depth === 0 ? "bg-emerald-500/20 text-emerald-200" : "bg-white/5 text-sky-300"}`}>{h.slice(0, 6)}</span>
                    ))}
                    {lvl.length > MAX_NODES_SHOWN && <span className="text-xs text-soc-muted">+{lvl.length - MAX_NODES_SHOWN}</span>}
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input className="input w-28" type="number" placeholder="seq id" value={seq} onChange={(e) => setSeq(e.target.value)} aria-label="Seq ID for proof" />
                <button className="btn-secondary" disabled={!seq} onClick={async () => {
                  setErr(null);
                  try { setProof(await (await import("@/lib/api")).api<MerkleProof>(`/api/merkle/${selected}/proof/${seq}`)); }
                  catch (e) { setProof(null); setErr(e instanceof Error ? e.message : String(e)); }
                }}>Get inclusion proof</button>
              </div>
              {proof && (
                <div className="rounded border border-soc-border p-3 text-xs">
                  <div>Leaf (seq {proof.seq_id}, index {proof.leaf_index}): <Hash value={proof.leaf} n={24} /></div>
                  <ol className="mt-1 list-decimal pl-5">{proof.proof.map((p, i) => <li key={i}>{p.position} sibling <Hash value={p.hash} n={24} /></li>)}</ol>
                  <div className="mt-1">→ root <Hash value={proof.root} n={24} /></div>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
