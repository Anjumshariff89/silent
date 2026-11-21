"""Standalone verifier + anchoring process, separate from the log agent (and from the API process).

Loop: verify the hash chain -> build a Merkle batch when enough unbatched logs exist -> anchor it
-> re-verify every anchored batch against the Quai contract.

    .\\.venv\\Scripts\\python.exe -m backend.verifier_service            # loop every 60 s
    .\\.venv\\Scripts\\python.exe -m backend.verifier_service --once     # single pass
"""
from __future__ import annotations

import argparse
import time

from sqlalchemy import text

from backend.app.anchor_service import ServiceError, anchor_batch, verify_batch
from backend.app.config import load_settings
from backend.app.factory import build_context
from backend.app.integrity_service import run_chain_verification


def run_once(c, min_batch: int = 10) -> dict:
    report = {"chain": run_chain_verification(c)["result"], "built": None, "anchored": None, "batches": {}}
    with c.engine.connect() as conn:
        unbatched = conn.execute(text("SELECT count(*) FROM security_logs WHERE merkle_batch_id IS NULL")).scalar()
    if unbatched >= min_batch:
        from backend.api.merkle_routes import build_batch
        b = build_batch(c.engine)
        report["built"] = b["batch_id"]
        try:
            report["anchored"] = anchor_batch(c, b["batch_id"])["tx_hash"]
        except ServiceError as exc:
            report["anchored"] = f"error: {exc.detail}"
    with c.engine.connect() as conn:
        anchored = [r[0] for r in conn.execute(text("SELECT batch_id FROM blockchain_anchors ORDER BY batch_id"))]
    for bid in anchored:
        report["batches"][bid] = verify_batch(c, bid)["result"]
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--min-batch", type=int, default=10)
    args = ap.parse_args()
    c = build_context(load_settings())
    print(f"[verifier] started (blockchain={c.anchorer.mode}, db={c.engine.dialect.name})", flush=True)
    while True:
        print(f"[verifier] {run_once(c, args.min_batch)}", flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
