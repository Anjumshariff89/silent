"use client";

import { useState } from "react";
import { post } from "@/lib/api";

interface TamperResponse {
  attack: string;
  original_unchanged: boolean;
  verification: { result: string; issues: { type: string; seq_id: number; detail: string }[] };
}

/** Demo: attacks a SANDBOX COPY of the data on the server; the live logs are never modified. */
export function TamperButton({ seqId, kind = "modify", onDone }: {
  seqId: number; kind?: "modify" | "delete" | "reorder"; onDone?: (r: TamperResponse) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <span className="inline-flex items-center gap-2">
      <button data-testid={`tamper-${seqId}`} disabled={busy}
        title="Demo: tampers a sandbox copy of the data, then runs verification on it"
        onClick={async () => {
          setBusy(true); setErr(null);
          try { onDone?.(await post<TamperResponse>("/api/demo/tamper", { seq_id: seqId, kind })); }
          catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
          finally { setBusy(false); }
        }}
        className="whitespace-nowrap rounded border border-red-500/50 px-2 py-0.5 text-xs text-red-300 hover:bg-red-500/15 disabled:opacity-50">
        {busy ? "…" : "Tamper this log"}
      </button>
      {err && <span className="text-xs text-red-300">{err}</span>}
    </span>
  );
}

export type { TamperResponse };
