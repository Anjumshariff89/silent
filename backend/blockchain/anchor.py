"""Blockchain anchoring: Quai Orchard Cyprus-1 via the local Node.js quai-service (REAL) or a local
simulated chain (SIMULATED).

Quai is not plain Ethereum (zone-specific addresses, quais SDK), so Python never builds, signs or
broadcasts Quai transactions and never sees CYPRUS1_PK. It only calls the quai-service over
loopback HTTP (backend/blockchain/quai-service, default http://127.0.0.1:8787).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

QUAI_ORCHARD_CHAIN_ID = 15000
QUAI_MAINNET_CHAIN_ID = 9
DEFAULT_QUAI_SERVICE_URL = "http://127.0.0.1:8787"


class AnchorError(Exception):
    pass


class AlreadyAnchored(AnchorError):
    pass


def _explorer_base(chain_id: int) -> str | None:
    return {QUAI_ORCHARD_CHAIN_ID: "https://orchard.quaiscan.io", QUAI_MAINNET_CHAIN_ID: "https://quaiscan.io"}.get(chain_id)


def explorer_tx_url(chain_id: int, tx_hash: str) -> str | None:
    base = _explorer_base(chain_id)
    return f"{base}/tx/{tx_hash}" if base else None


def explorer_address_url(chain_id: int, address: str | None) -> str | None:
    base = _explorer_base(chain_id)
    return f"{base}/address/{address}" if base and address else None


def _iso(ts: int | float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class SimulatedChain:
    """Local stand-in for the LogAnchor contract: a hash-linked JSON ledger of blocks.

    Same semantics as the contract (write-once per batch_id). It is NOT a blockchain: anyone with
    file access can edit it. It exists so the full pipeline runs without keys.
    """

    mode = "SIMULATED"
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


class QuaiServiceAnchorer:
    """REAL anchoring on Quai Orchard through the local quai-service (Node.js + quais SDK)."""

    mode = "REAL"

    def __init__(self, contract_address: str, chain_id: int = QUAI_ORCHARD_CHAIN_ID,
                 base_url: str | None = None, timeout: float = 180.0, transport: httpx.BaseTransport | None = None):
        self.contract_address = contract_address
        self.chain_id = chain_id
        self.base_url = (base_url or os.getenv("QUAI_SERVICE_URL") or DEFAULT_QUAI_SERVICE_URL).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport, trust_env=False)
        self.address = None  # wallet address, filled from /status

    def __repr__(self) -> str:
        return f"QuaiServiceAnchorer(service={self.base_url}, chain_id={self.chain_id}, contract={self.contract_address})"

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise AnchorError(f"quai-service unreachable at {self.base_url} ({type(exc).__name__})") from None

    @staticmethod
    def _detail(r: httpx.Response) -> str:
        try:
            return str(r.json().get("detail", r.text))[:300]
        except ValueError:
            return r.text[:300]

    def status(self) -> dict | None:
        try:
            r = self._request("GET", "/status")
        except AnchorError:
            return None
        if r.status_code != 200:
            return None
        st = r.json()
        self.address = st.get("wallet_address")
        return st

    def connected(self) -> bool:
        st = self.status()
        return bool(st and st.get("mode") == "REAL" and st.get("connected") and st.get("chain_id") == self.chain_id)

    def latest_block(self) -> int | None:
        st = self.status()
        return st.get("latest_block") if st else None

    def anchor(self, root_hex: str, batch_id: int) -> dict:
        r = self._request("POST", "/anchor", json={"root": root_hex, "batch_id": str(batch_id)})
        if r.status_code == 409:
            raise AlreadyAnchored(self._detail(r))
        if r.status_code != 200:
            raise AnchorError(f"quai-service anchor failed (HTTP {r.status_code}): {self._detail(r)}")
        d = r.json()
        return {"tx_hash": d["tx_hash"], "block_number": d["block_number"], "block_timestamp": d["block_timestamp"],
                "explorer_url": d.get("explorer_url")}

    def get_anchor(self, batch_id: int) -> dict | None:
        r = self._request("GET", f"/anchor/{batch_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise AnchorError(f"quai-service lookup failed (HTTP {r.status_code}): {self._detail(r)}")
        d = r.json()
        return {"root": d["root"], "block_timestamp": d["block_timestamp"]}

    def find_anchor_tx(self, batch_id: int) -> dict | None:
        r = self._request("GET", f"/anchor/{batch_id}/tx")
        if r.status_code != 200:
            return None
        d = r.json()
        return {"root": d["root"], "tx_hash": d["tx_hash"], "block_number": d["block_number"],
                "block_timestamp": d["block_timestamp"]}


def make_anchorer(settings, ledger_path: str | Path):
    """REAL (quai-service) when RPC_URL, CYPRUS1_PK and CONTRACT_ADDRESS are all set, else the simulator.

    Python only checks that the keys are configured; it never reads or forwards CYPRUS1_PK.
    """
    if settings.blockchain_real:
        return QuaiServiceAnchorer(settings.contract_address, settings.chain_id)
    return SimulatedChain(ledger_path, settings.chain_id)
