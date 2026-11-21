"""Test-only stand-in for the LogAnchor contract (NOT used by the application).

The application never simulates anchoring: without Quai keys it reports "NOT CONFIGURED". Tests need a chain
that behaves like the contract (write-once per key), so this in-memory/JSON ledger lives here, under tests/.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.blockchain.anchor import QUAI_ORCHARD_CHAIN_ID, AlreadyAnchored, _iso


class FakeChain:
    """Local stand-in for the LogAnchor contract: a hash-linked JSON ledger of blocks.

    Same semantics as the contract (write-once per batch_id). It is NOT a blockchain: anyone with
    file access can edit it. It exists so the full pipeline runs without keys.
    """

    mode = "SIMULATED"  # test double; the app itself has no simulated mode
    contract_address = None
    GENESIS_BLOCK = 1_000_000

    def __init__(self, ledger_path: str | Path, chain_id: int = QUAI_ORCHARD_CHAIN_ID):
        self.path = Path(ledger_path)
        self.chain_id = chain_id
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"blocks": []})

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def connected(self) -> bool:
        return True

    def latest_block(self) -> int:
        blocks = self._load()["blocks"]
        return blocks[-1]["number"] if blocks else self.GENESIS_BLOCK

    def anchor(self, root_hex: str, batch_id: int) -> dict:
        with self._lock:
            data = self._load()
            if any(b["batch_id"] == batch_id for b in data["blocks"]):
                raise AlreadyAnchored(f"batch {batch_id} already anchored")
            prev = data["blocks"][-1]["block_hash"] if data["blocks"] else "0" * 64
            number = (data["blocks"][-1]["number"] if data["blocks"] else self.GENESIS_BLOCK) + 1
            ts = int(datetime.now(timezone.utc).timestamp())
            tx_hash = "0x" + hashlib.sha256(f"tx|{batch_id}|{root_hex}|{ts}|{prev}".encode()).hexdigest()
            block_hash = hashlib.sha256(f"{prev}|{number}|{tx_hash}".encode()).hexdigest()
            data["blocks"].append({"number": number, "timestamp": ts, "batch_id": batch_id, "root": root_hex,
                                   "tx_hash": tx_hash, "prev_block_hash": prev, "block_hash": block_hash})
            self._save(data)
        return {"tx_hash": tx_hash, "block_number": number, "block_timestamp": _iso(ts)}

    def find_anchor_tx(self, batch_id: int) -> dict | None:
        """Recover tx details of an existing anchor (used if the DB write after anchoring failed)."""
        for b in self._load()["blocks"]:
            if b["batch_id"] == batch_id:
                return {"root": b["root"], "tx_hash": b["tx_hash"], "block_number": b["number"],
                        "block_timestamp": _iso(b["timestamp"])}
        return None

    def get_anchor(self, batch_id: int) -> dict | None:
        for b in self._load()["blocks"]:
            if b["batch_id"] == batch_id:
                return {"root": b["root"], "block_timestamp": _iso(b["timestamp"])}
        return None


