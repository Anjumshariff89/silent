"""quai_service: the ONE Python module for Quai Orchard Cyprus-1 (chain 15000) anchoring.

All anchoring (/anchor, /api/blockchain/anchor, proof verification) goes through the classes here, which call
the local Node.js quai-service (backend/blockchain/quai-service). Without Quai keys the anchorer is
NOT CONFIGURED (or READ-ONLY with only RPC_URL) and every anchoring call fails clearly (no simulated chain).
Connection failures to the quai-service are retried; nothing here can crash the API (errors -> AnchorError).

Quai is not plain Ethereum (zone-specific addresses, quais SDK), so Python never builds, signs or
broadcasts Quai transactions and never sees CYPRUS1_PK. It only calls the quai-service over
loopback HTTP (backend/blockchain/quai-service, default http://127.0.0.1:8787).
"""
from __future__ import annotations

import json
import os
import time
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


class AnchorPending(AnchorError):
    """The anchor request was sent but no answer arrived in time: the transaction may still be mined."""


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


class UnconfiguredAnchorer:
    """Used when RPC_URL is missing. Nothing is simulated: anchoring and on-chain
    reads fail with a clear message (HTTP 503) until the Quai keys are set in .env."""

    mode = "NOT CONFIGURED"
    can_anchor = False
    contract_address = None
    address = None
    MESSAGE = ("Quai anchoring is not configured: set RPC_URL, CYPRUS1_PK and CONTRACT_ADDRESS in .env "
               "and start the quai-service (start.ps1 does this)")

    def __init__(self, chain_id: int = QUAI_ORCHARD_CHAIN_ID):
        self.chain_id = chain_id

    def connected(self) -> bool:
        return False

    def latest_block(self) -> None:
        return None

    def anchor(self, root_hex: str, batch_id: int) -> dict:
        raise AnchorError(self.MESSAGE)

    def get_anchor(self, batch_id: int) -> dict | None:
        raise AnchorError(self.MESSAGE)

    def find_anchor_tx(self, batch_id: int) -> dict | None:
        return None

    def rpc_error(self) -> str:
        return "RPC_URL is not set in .env"


class QuaiServiceAnchorer:
    """REAL anchoring on Quai Orchard through the local quai-service (Node.js + quais SDK)."""

    mode = "REAL"
    can_anchor = True
    RETRIES = 3  # connection-level retries (the request never reached the quai-service)

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
        # Retry only when the connection could not be made (nothing was sent). A timeout after sending is NOT
        # retried here: the transaction may be in flight; re-anchoring later hits the write-once contract
        # (409 AlreadyAnchored) and the existing tx is recovered with find_anchor_tx.
        for attempt in range(1, self.RETRIES + 1):
            try:
                return self._client.request(method, path, **kw)
            except httpx.ConnectError:
                if attempt == self.RETRIES:
                    raise AnchorError(f"quai-service unreachable at {self.base_url} (ConnectError after "
                                      f"{self.RETRIES} attempts)") from None
                time.sleep(0.3 * attempt)
            except httpx.TimeoutException as exc:
                if method == "POST":
                    raise AnchorPending(f"no answer from the quai-service within the timeout ({type(exc).__name__}): "
                                        "the transaction may still be mined; anchor again later to recover it") from None
                raise AnchorError(f"quai-service timed out at {self.base_url} ({type(exc).__name__})") from None
            except httpx.HTTPError as exc:
                raise AnchorError(f"quai-service request failed at {self.base_url} ({type(exc).__name__})") from None
        raise AnchorError("unreachable")  # pragma: no cover

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
        # connected only when the quai-service verified the RPC's chain id itself
        return bool(st and st.get("mode") == self.mode and st.get("connected") and st.get("rpc_chain_id") == self.chain_id)

    def rpc_error(self) -> str | None:
        st = self.status()
        return st.get("rpc_error") if st else f"quai-service unreachable at {self.base_url}"

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


class ReadOnlyQuaiAnchorer(QuaiServiceAnchorer):
    """RPC_URL set but no wallet key and/or contract: live network status from the quai-service, no anchoring."""

    mode = "READ-ONLY"
    can_anchor = False

    def __init__(self, missing: list[str], *a, **kw):
        super().__init__(*a, **kw)
        self.missing = missing

    def anchor(self, root_hex: str, batch_id: int) -> dict:
        raise AnchorError(f"Quai is connected read-only: set {', '.join(self.missing)} in .env to anchor "
                          "(deploy LogAnchor first for CONTRACT_ADDRESS)")

    def get_anchor(self, batch_id: int) -> dict | None:
        if not self.contract_address:
            raise AnchorError("CONTRACT_ADDRESS is not set: there is no contract to read anchors from")
        return super().get_anchor(batch_id)

    def find_anchor_tx(self, batch_id: int) -> dict | None:
        return super().find_anchor_tx(batch_id) if self.contract_address else None


def make_anchorer(settings, ledger_path: str | Path | None = None):
    """REAL when RPC_URL, CYPRUS1_PK and CONTRACT_ADDRESS are all set; READ-ONLY (live status, no anchoring)
    when only RPC_URL is set; else NOT CONFIGURED.

    Python only checks that the keys are configured; it never reads or forwards CYPRUS1_PK.
    """
    if settings.blockchain_real:
        return QuaiServiceAnchorer(settings.contract_address, settings.chain_id)
    if settings.rpc_url:
        missing = [n for n, v in (("CYPRUS1_PK", settings.cyprus1_pk), ("CONTRACT_ADDRESS", settings.contract_address)) if not v]
        return ReadOnlyQuaiAnchorer(missing, settings.contract_address or None, settings.chain_id)
    return UnconfiguredAnchorer(settings.chain_id)
