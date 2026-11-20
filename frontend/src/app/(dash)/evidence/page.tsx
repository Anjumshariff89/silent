"use client";

import { useEffect, useState } from "react";
import { api, download } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { MerkleBatchSummary } from "@/lib/types";
import { Card, Empty, ErrorState, Loading, Pill } from "@/components/ui";

interface Bundle {
  batch: { batch_id: number; merkle_root: string; leaf_count: number };
  anchor: { mode: string; tx_hash: string; explorer_url: string | null } | null;
  verification: { result: string };
  disclaimer: string;
  logs: unknown[];
}

export default function EvidencePage() {
  const batches = useApi<{ items: MerkleBatchSummary[] }>("/api/merkle/batches");
  const [selected, setSelected] = useState<number | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (selected == null && batches.data?.items.length) setSelected(batches.data.items[0].batch_id);
  }, [batches.data, selected]);

  useEffect(() => {
    if (selected == null) return;
    setLoading(true); setErr(null);
    api<Bundle>(`/api/evidence/${selected}/json`).then(setBundle).catch((e) => { setBundle(null); setErr(e instanceof Error ? e.message : String(e)); })
      .finally(() => setLoading(false));
  }, [selected]);

  const dl = async (kind: "json" | "pdf") => {
    try { await download(`/api/evidence/${selected}/${kind}`, `evidence_batch_${selected}.${kind}`); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Evidence Portal</h1>
      {err && <ErrorState message={err} />}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Batches">
          {batches.error ? <ErrorState message={batches.error} onRetry={batches.reload} /> : batches.loading && !batches.data ? <Loading /> :
            !batches.data?.items.length ? <Empty>No batches yet.</Empty> : (
            <select className="input w-full" value={selected ?? ""} onChange={(e) => setSelected(Number(e.target.value))} aria-label="Batch">
              {batches.data.items.map((b) => <option key={b.batch_id} value={b.batch_id}>Batch #{b.batch_id} (seq {b.from_seq}–{b.to_seq}){b.tx_hash ? " · anchored" : ""}</option>)}
            </select>
          )}
          <div className="mt-4 flex flex-col gap-2">
            <button className="btn-primary" disabled={!selected} onClick={() => dl("json")} data-testid="dl-json">Export JSON bundle</button>
            <button className="btn-secondary" disabled={!selected} onClick={() => dl("pdf")} data-testid="dl-pdf">Download PDF certificate</button>
          </div>
          <p className="mt-3 text-xs text-soc-muted">Verify offline: <code>python -m backend.crypto.offline_verify evidence_batch_N.json</code></p>
        </Card>
        <Card title="Bundle preview" className="lg:col-span-2">
          {loading ? <Loading /> : !bundle ? <Empty>Select a batch.</Empty> : (
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">Verification: <Pill value={bundle.verification.result} />
                Anchor: {bundle.anchor ? <Pill value={bundle.anchor.mode} /> : <Pill value="NOT_ANCHORED" label="not anchored" />}
                <span className="text-soc-muted">{bundle.logs.length} logs</span></div>
              <p className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-200">{bundle.disclaimer}</p>
              <pre className="max-h-96 overflow-auto rounded bg-black/40 p-3 font-mono text-[11px] text-slate-300">{JSON.stringify(bundle, null, 2).slice(0, 6000)}</pre>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
