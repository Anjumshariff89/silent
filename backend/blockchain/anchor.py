"""Blockchain anchoring: Polygon Amoy via web3.py (REAL) or a local simulated chain (SIMULATED).

The private key is held only inside the eth_account LocalAccount object. It is never logged,
printed, returned, or included in error messages.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

ABI_PATH = Path(__file__).resolve().parent / "LogAnchor.abi.json"
AMOY_CHAIN_ID = 80002
AMOY_MIN_PRIORITY_FEE_WEI = 25_000_000_000  # Amoy rejects tips below 25 gwei


class AnchorError(Exception):
    pass


class AlreadyAnchored(AnchorError):
    pass


def explorer_tx_url(chain_id: int, tx_hash: str) -> str | None:
    return f"https://amoy.polygonscan.com/tx/{tx_hash}" if chain_id == AMOY_CHAIN_ID else None


def explorer_address_url(chain_id: int, address: str | None) -> str | None:
    return f"https://amoy.polygonscan.com/address/{address}" if chain_id == AMOY_CHAIN_ID and address else None


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

    def __init__(self, ledger_path: str | Path, chain_id: int = AMOY_CHAIN_ID):
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


class Web3Anchorer:
    """Real anchoring through the deployed LogAnchor contract (Polygon Amoy, chainId 80002)."""

    mode = "REAL"

    def __init__(self, rpc_url: str, private_key: str, contract_address: str, chain_id: int = AMOY_CHAIN_ID,
                 timeout: int = 180):
        from eth_account import Account
        from web3 import Web3

        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        self._account = Account.from_key(private_key)  # key stays inside this object
        self.address = self._account.address
        self.chain_id = chain_id
        self.timeout = timeout
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract = self.w3.eth.contract(address=self.contract_address,
                                             abi=json.loads(ABI_PATH.read_text(encoding="utf-8")))

    def __repr__(self) -> str:  # never expose the key via repr
        return f"Web3Anchorer(address={self.address}, chain_id={self.chain_id}, contract={self.contract_address})"

    def connected(self) -> bool:
        try:
            return self.w3.is_connected() and self.w3.eth.chain_id == self.chain_id
        except Exception:
            return False

    def latest_block(self) -> int | None:
        try:
            return self.w3.eth.block_number
        except Exception:
            return None

    def _check_chain(self) -> None:
        try:
            actual = self.w3.eth.chain_id
        except Exception as exc:
            raise AnchorError(f"RPC unreachable ({type(exc).__name__})") from None
        if actual != self.chain_id:
            raise AnchorError(f"RPC chain_id {actual} != configured CHAIN_ID {self.chain_id}")

    def anchor(self, root_hex: str, batch_id: int) -> dict:
        self._check_chain()
        if self.contract.functions.isAnchored(batch_id).call():
            raise AlreadyAnchored(f"batch {batch_id} already anchored on-chain")
        try:
            tx = self.contract.functions.anchorRoot(bytes.fromhex(root_hex), batch_id).build_transaction({
                "from": self.address,
                "nonce": self.w3.eth.get_transaction_count(self.address, "pending"),
                "chainId": self.chain_id,
            })
            if self.chain_id == AMOY_CHAIN_ID and tx.get("maxPriorityFeePerGas", 0) < AMOY_MIN_PRIORITY_FEE_WEI:
                bump = AMOY_MIN_PRIORITY_FEE_WEI - tx["maxPriorityFeePerGas"]
                tx["maxPriorityFeePerGas"] = AMOY_MIN_PRIORITY_FEE_WEI
                tx["maxFeePerGas"] = tx["maxFeePerGas"] + bump
            signed = self._account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self.timeout)
        except AnchorError:
            raise
        except Exception as exc:  # message deliberately excludes key material
            raise AnchorError(f"anchoring transaction failed ({type(exc).__name__}: {str(exc)[:160]})") from None
        if receipt["status"] != 1:
            raise AnchorError(f"anchoring transaction reverted: {receipt['transactionHash'].hex()}")
        block = self.w3.eth.get_block(receipt["blockNumber"])
        h = receipt["transactionHash"].hex()
        return {"tx_hash": h if h.startswith("0x") else "0x" + h, "block_number": receipt["blockNumber"],
                "block_timestamp": _iso(block["timestamp"])}

    def find_anchor_tx(self, batch_id: int, window: int = 10_000, max_windows: int = 50) -> dict | None:
        """Search RootAnchored events (newest first, in RPC-friendly block windows) for this batch key."""
        self._check_chain()
        latest = self.w3.eth.block_number
        end = latest
        for _ in range(max_windows):
            start = max(0, end - window + 1)
            try:
                logs = self.contract.events.RootAnchored.get_logs(from_block=start, to_block=end,
                                                                 argument_filters={"batchId": batch_id})
            except Exception:
                return None
            if logs:
                ev = logs[-1]
                h = ev["transactionHash"].hex()
                return {"root": ev["args"]["root"].hex().removeprefix("0x"),
                        "tx_hash": h if h.startswith("0x") else "0x" + h, "block_number": ev["blockNumber"],
                        "block_timestamp": _iso(ev["args"]["timestamp"])}
            if start == 0:
                break
            end = start - 1
        return None

    def get_anchor(self, batch_id: int) -> dict | None:
        self._check_chain()
        root, ts, _submitter = self.contract.functions.getAnchor(batch_id).call()
        if ts == 0:
            return None
        return {"root": root.hex().removeprefix("0x"), "block_timestamp": _iso(ts)}


def make_anchorer(settings, ledger_path: str | Path):
    if settings.blockchain_real:
        return Web3Anchorer(settings.amoy_rpc_url, settings.anchor_private_key, settings.contract_address,
                            settings.chain_id)
    return SimulatedChain(ledger_path, settings.chain_id)
