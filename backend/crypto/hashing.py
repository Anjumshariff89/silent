"""SHA-256 hash chain primitives.

curr_hash = SHA-256( prev_hash_hex || canonical_json(hashed_fields) ), lowercase hex.
canonical_json = JSON with sorted keys, no whitespace, UTF-8, non-ASCII kept as-is.
Genesis (seq_id 1) uses prev_hash = "0" * 64.

seq_id is intentionally NOT part of the hashed content: position is bound by prev_hash linkage,
which lets the verifier tell a *reordered* log (self-consistent but linked to the wrong
predecessor) apart from a *modified* one (content no longer matches its own hash).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

GENESIS_PREV_HASH = "0" * 64
HASHED_FIELDS = (
    "agent_id", "event_id", "event_type", "severity", "source_host",
    "username", "source_ip", "message", "event_time", "received_at",
)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hashed_content(log: Mapping[str, Any]) -> dict:
    return {k: log.get(k) for k in HASHED_FIELDS}


def compute_log_hash(prev_hash: str, log: Mapping[str, Any]) -> str:
    if len(prev_hash) != 64:
        raise ValueError("prev_hash must be 64 hex chars")
    return sha256_hex(prev_hash + canonical_json(hashed_content(log)))
