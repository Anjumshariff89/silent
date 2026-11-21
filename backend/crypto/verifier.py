"""Hash-chain verifier: detects modified, missing and reordered logs.

Input: rows ordered by seq_id, each with log fields + prev_hash + curr_hash.

Classification per row (first match wins):
  missing    - seq_id gap before this row (e.g. 244 -> 246), or the row's hash link is absent,
               or prev_hash points to a hash that is not in the data set (deleted + renumbered).
  modified   - content no longer hashes to the stored curr_hash.
  reordered  - content is self-consistent but prev_hash points to a *different existing* row
               than its predecessor (rows were moved).

Limitation: deleting the newest logs (tail truncation) leaves a valid shorter chain. That case is
caught by Merkle anchoring (anchored root MISMATCH), not by the chain alone.
"""
from __future__ import annotations

from typing import Callable, Iterable

from backend.crypto.hashing import GENESIS_PREV_HASH, compute_log_hash


def verify_chain(rows: Iterable[dict], expected_first_seq: int = 1,
                 expected_first_prev: str = GENESIS_PREV_HASH,
                 hash_fn: Callable[[str, dict], str] = compute_log_hash) -> dict:
    rows = list(rows)
    issues: list[dict] = []
    by_curr = {r["curr_hash"]: r["seq_id"] for r in rows if r.get("curr_hash")}
    expected_seq, expected_prev = expected_first_seq, expected_first_prev

    for r in rows:
        seq = r["seq_id"]
        if seq > expected_seq:
            missing = list(range(expected_seq, seq))
            span = f"{missing[0]}" if len(missing) == 1 else f"{missing[0]}-{missing[-1]}"
            issues.append({"type": "missing", "seq_id": missing[0], "missing_seq_ids": missing,
                           "detail": f"sequence gap: {expected_seq - 1} -> {seq} (missing {span})"})
            # after a gap we cannot know the true predecessor hash; resume from this row
            expected_prev = r.get("prev_hash")
        if not r.get("curr_hash") or not r.get("prev_hash"):
            issues.append({"type": "missing", "seq_id": seq, "detail": "hash_chain entry missing for this log"})
            expected_seq, expected_prev = seq + 1, None
            continue

        recomputed = hash_fn(r["prev_hash"], r)
        if recomputed != r["curr_hash"]:
            issues.append({"type": "modified", "seq_id": seq,
                           "detail": f"curr_hash mismatch: stored {r['curr_hash'][:12]}…, recomputed {recomputed[:12]}…"})
        elif expected_prev is not None and r["prev_hash"] != expected_prev:
            target = by_curr.get(r["prev_hash"])
            if target is not None:
                issues.append({"type": "reordered", "seq_id": seq,
                               "detail": f"prev_hash links to seq {target}, not to its predecessor seq {seq - 1}"})
            elif r["prev_hash"] == GENESIS_PREV_HASH:
                issues.append({"type": "reordered", "seq_id": seq,
                               "detail": "genesis log found out of position"})
            else:
                issues.append({"type": "missing", "seq_id": seq,
                               "detail": f"prev_hash {r['prev_hash'][:12]}… matches no log: predecessor deleted"})
        expected_seq, expected_prev = seq + 1, r["curr_hash"]

    return {"result": "PASS" if not issues else "FAIL", "checked_count": len(rows), "issues": issues}
