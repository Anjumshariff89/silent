"""SHA-256 Merkle tree with inclusion proofs.

leaf  = SHA-256(0x00 || bytes.fromhex(curr_hash))
node  = SHA-256(0x01 || left || right)
Odd node at a level is paired with itself (duplicated).

Domain separation (0x00 / 0x01) prevents an internal node from being passed off as a leaf
(second-preimage attack). Because duplicated pairing lets [a,b,c] and [a,b,c,c] share a root
(CVE-2012-2459 class), verification also checks leaf_count and seq range stored per batch,
and seq_id is UNIQUE so a log cannot appear twice.
"""
from __future__ import annotations

import hashlib
from typing import Sequence

LEAF_PREFIX, NODE_PREFIX = b"\x00", b"\x01"


def _h(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(curr_hash_hex: str) -> bytes:
    return _h(LEAF_PREFIX + bytes.fromhex(curr_hash_hex))


def node_hash(left: bytes, right: bytes) -> bytes:
    return _h(NODE_PREFIX + left + right)


def build_levels(leaf_hex_hashes: Sequence[str]) -> list[list[str]]:
    """Return all levels as hex, levels[0] = hashed leaves, levels[-1] = [root]."""
    if not leaf_hex_hashes:
        raise ValueError("cannot build a Merkle tree with no leaves")
    level = [leaf_hash(h) for h in leaf_hex_hashes]
    levels = [level]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(node_hash(left, right))
        level = nxt
        levels.append(level)
    return [[b.hex() for b in lvl] for lvl in levels]


def merkle_root(leaf_hex_hashes: Sequence[str]) -> str:
    return build_levels(leaf_hex_hashes)[-1][0]


def inclusion_proof(levels: list[list[str]], index: int) -> list[dict]:
    if not 0 <= index < len(levels[0]):
        raise IndexError("leaf index out of range")
    proof = []
    for level in levels[:-1]:
        sibling = index ^ 1
        if sibling >= len(level):
            sibling = index  # duplicated odd node
        proof.append({"position": "right" if index % 2 == 0 else "left", "hash": level[sibling]})
        index //= 2
    return proof


def verify_proof(curr_hash_hex: str, proof: list[dict], root_hex: str) -> bool:
    try:
        acc = leaf_hash(curr_hash_hex)
        for step in proof:
            sib = bytes.fromhex(step["hash"])
            if step["position"] == "right":
                acc = node_hash(acc, sib)
            elif step["position"] == "left":
                acc = node_hash(sib, acc)
            else:
                return False
        return acc.hex() == root_hex
    except (ValueError, KeyError, TypeError):
        return False
