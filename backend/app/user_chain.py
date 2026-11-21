"""Per-user tamper-evident logs: one SHA-256 hash chain per signed-in user, Merkle roots over it, Quai anchors.

Every function takes the user id from the VERIFIED access token (never from a request body) and every query is
filtered by it, so a user can only read or change their own chain even though the backend connects to Postgres
as the table owner (RLS is the second line of defence for direct Supabase API access).

Algorithms are the existing ones: compute_user_log_hash uses the same SHA-256(prev || canonical_json) construction
as the shared chain, verify_chain is the shared verifier, merkle_root is the shared Merkle tree.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from backend.app.anchor_service import ServiceError
from backend.app.context import AppContext
from backend.blockchain.quai_service import AlreadyAnchored, AnchorError, AnchorPending, explorer_tx_url
from backend.crypto.hashing import GENESIS_PREV_HASH, compute_user_log_hash
from backend.crypto.verifier import verify_chain
from backend.database.repo import now_iso
from backend.merkle.tree import merkle_root

PENDING_RETRY_AFTER = timedelta(minutes=2)  # a pending anchor may be retried after this (recovers via the contract)


def _uid(user_id: str | None) -> str:
    try:
        return str(uuid.UUID(str(user_id)))
    except (ValueError, TypeError):
        raise ServiceError(401, "This action needs a signed-in user account") from None


def _rows(result) -> list[dict]:
    return [dict(r._mapping) for r in result]


def onchain_id_for(merkle_root_id: str) -> int:
    """uint256 key for the LogAnchor contract, unique per Merkle root (namespaced, cannot collide with shared batches)."""
    return int(hashlib.sha256(f"silent:user-merkle-root:{merkle_root_id}".encode()).hexdigest(), 16)


# ----------------------------------------------------------------------------------------------- logs
def append_log(c: AppContext, user_id: str, message: str) -> dict:
    uid = _uid(user_id)
    with c.chain_lock, c.engine.begin() as conn:  # lock => strictly sequential seq + correct prev_hash
        last = conn.execute(text("SELECT seq, hash FROM logs WHERE user_id=:u ORDER BY seq DESC LIMIT 1"), {"u": uid}).first()
        seq, prev = (last[0] + 1, last[1]) if last else (1, GENESIS_PREV_HASH)
        row = {"id": str(uuid.uuid4()), "user_id": uid, "seq": seq, "message": message, "prev_hash": prev,
               "created_at": now_iso()}
        row["hash"] = compute_user_log_hash(prev, row)
        conn.execute(text("INSERT INTO logs(id, user_id, seq, message, prev_hash, hash, created_at)"
                          " VALUES (:id,:user_id,:seq,:message,:prev_hash,:hash,:created_at)"), row)
    c.note_ingest()
    return row


def list_logs(c: AppContext, user_id: str, page: int = 1, page_size: int = 50) -> dict:
    uid = _uid(user_id)
    with c.engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM logs WHERE user_id=:u"), {"u": uid}).scalar()
        items = _rows(conn.execute(text(
            "SELECT id, seq, message, prev_hash, hash, created_at FROM logs WHERE user_id=:u"
            " ORDER BY seq DESC LIMIT :lim OFFSET :off"), {"u": uid, "lim": page_size, "off": (page - 1) * page_size}))
    for i in items:
        i["id"] = str(i["id"])
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def _chain_rows(conn, uid: str, from_seq: int | None = None, to_seq: int | None = None) -> list[dict]:
    sql, p = "SELECT seq, user_id, message, prev_hash, hash, created_at FROM logs WHERE user_id=:u", {"u": uid}
    if from_seq is not None:
        sql, p["f"] = sql + " AND seq >= :f", from_seq
    if to_seq is not None:
        sql, p["t"] = sql + " AND seq <= :t", to_seq
    rows = _rows(conn.execute(text(sql + " ORDER BY seq"), p))
    for r in rows:  # shape expected by the shared verifier
        r["seq_id"], r["curr_hash"], r["user_id"] = r["seq"], r["hash"], str(r["user_id"])
    return rows


def verify_user_chain(c: AppContext, user_id: str) -> dict:
    uid = _uid(user_id)
    with c.engine.connect() as conn:
        rows = _chain_rows(conn, uid)
    report = verify_chain(rows, hash_fn=compute_user_log_hash)
    report["verified_at"] = now_iso()
    if report["result"] == "FAIL":
        c.alert_once(f"user-chain:{uid}:{report['issues'][0]['type']}:{report['issues'][0]['seq_id']}",
                     f"Tamper detected in user {uid[:8]}… log chain: {report['issues'][0]['type'].upper()} at seq "
                     f"{report['issues'][0]['seq_id']} ({len(report['issues'])} issue(s))")
    return report


# ----------------------------------------------------------------------------------------------- merkle
def build_root(c: AppContext, user_id: str) -> dict:
    uid = _uid(user_id)
    with c.chain_lock, c.engine.begin() as conn:
        last_to = conn.execute(text("SELECT max(to_seq) FROM merkle_roots WHERE user_id=:u"), {"u": uid}).scalar() or 0
        rows = _chain_rows(conn, uid, from_seq=last_to + 1)
        if not rows:
            raise ServiceError(400, "No new logs since the last Merkle root: add logs first (POST /logs)")
        rec = {"id": str(uuid.uuid4()), "user_id": uid, "root": merkle_root([r["hash"] for r in rows]),
               "leaf_count": len(rows), "from_seq": rows[0]["seq"], "to_seq": rows[-1]["seq"], "created_at": now_iso()}
        conn.execute(text("INSERT INTO merkle_roots(id, user_id, root, leaf_count, from_seq, to_seq, created_at)"
                          " VALUES (:id,:user_id,:root,:leaf_count,:from_seq,:to_seq,:created_at)"), rec)
    return {k: v for k, v in rec.items() if k != "user_id"}


def list_roots(c: AppContext, user_id: str) -> dict:
    uid = _uid(user_id)
    with c.engine.connect() as conn:
        items = _rows(conn.execute(text(
            "SELECT m.id, m.root, m.leaf_count, m.from_seq, m.to_seq, m.created_at, a.id AS anchor_id, a.status AS anchor_status,"
            " a.tx_hash FROM merkle_roots m LEFT JOIN anchors a ON a.merkle_root_id = m.id"
            " WHERE m.user_id=:u ORDER BY m.to_seq DESC"), {"u": uid}))
    for i in items:
        i["id"], i["anchor_id"] = str(i["id"]), (str(i["anchor_id"]) if i["anchor_id"] else None)
    return {"items": items}


# ----------------------------------------------------------------------------------------------- anchors
def _anchor_out(row: dict) -> dict:
    out = dict(row)
    for k in ("id", "merkle_root_id"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    return out


ANCHOR_SELECT = ("SELECT a.id, a.merkle_root_id, m.root, m.leaf_count, m.from_seq, m.to_seq, a.onchain_id, a.tx_hash,"
                 " a.chain_id, a.status, a.block_number, a.explorer_url, a.error, a.created_at, a.updated_at"
                 " FROM anchors a JOIN merkle_roots m ON m.id = a.merkle_root_id WHERE m.user_id=:u")


def list_anchors(c: AppContext, user_id: str) -> dict:
    uid = _uid(user_id)
    with c.engine.connect() as conn:
        return {"items": [_anchor_out(r) for r in _rows(conn.execute(text(ANCHOR_SELECT + " ORDER BY m.to_seq DESC"), {"u": uid}))]}


def anchor_root(c: AppContext, user_id: str, merkle_root_id: str | None = None) -> dict:
    """Anchor one of the user's Merkle roots on Quai (default: the newest root not yet confirmed)."""
    uid = _uid(user_id)
    a = c.anchorer
    with c.engine.connect() as conn:
        if merkle_root_id:
            m = conn.execute(text("SELECT id, root FROM merkle_roots WHERE id=:id AND user_id=:u"),
                             {"id": _uid(merkle_root_id) if _is_uuid(merkle_root_id) else None, "u": uid}).first()
            if not m:
                raise ServiceError(404, "Merkle root not found")
        else:
            m = conn.execute(text(
                "SELECT m.id, m.root FROM merkle_roots m LEFT JOIN anchors a ON a.merkle_root_id = m.id"
                " WHERE m.user_id=:u AND (a.id IS NULL OR a.status <> 'confirmed') ORDER BY m.to_seq DESC LIMIT 1"),
                {"u": uid}).first()
            if not m:
                raise ServiceError(400, "No un-anchored Merkle root: build one first (POST /merkle/build)")
        mid, root = str(m[0]), m[1]
        existing = conn.execute(text("SELECT id, status, updated_at FROM anchors WHERE merkle_root_id=:m"), {"m": mid}).first()
    key = onchain_id_for(mid)

    if not getattr(a, "can_anchor", True):  # NOT CONFIGURED / READ-ONLY: explain, store nothing
        try:
            a.anchor(root, key)
        except AnchorError as exc:
            raise ServiceError(503, str(exc))
    if existing and existing[1] == "confirmed":
        raise ServiceError(409, "This Merkle root is already anchored")
    if existing and existing[1] == "pending" and _age(existing[2]) < PENDING_RETRY_AFTER:
        raise ServiceError(409, "Anchoring of this root is already in progress; try again in a few minutes")

    now = now_iso()
    with c.engine.begin() as conn:
        if existing:
            anchor_id = str(existing[0])
            conn.execute(text("UPDATE anchors SET status='pending', error=NULL, updated_at=:t WHERE id=:id"),
                         {"t": now, "id": anchor_id})
        else:
            anchor_id = str(uuid.uuid4())
            conn.execute(text("INSERT INTO anchors(id, merkle_root_id, onchain_id, chain_id, status, created_at, updated_at)"
                              " VALUES (:id,:m,:k,:ch,'pending',:t,:t)"),
                         {"id": anchor_id, "m": mid, "k": str(key), "ch": a.chain_id, "t": now})

    status, http_error, res, err = "confirmed", None, None, None
    try:
        res = a.anchor(root, key)
    except AlreadyAnchored as exc:  # an earlier attempt was mined but not saved: recover it from the contract
        try:
            res = a.find_anchor_tx(key)
        except AnchorError:
            res = None
        if not res or res.get("root") != root:
            status, http_error, err = "failed", 409, f"{exc}; the on-chain root does not match this Merkle root"
    except AnchorPending as exc:
        status, http_error, err = "pending", 202, str(exc)
    except AnchorError as exc:
        status, http_error, err = "failed", 503, str(exc)

    tx = res["tx_hash"] if res and status == "confirmed" else None
    explorer = (res.get("explorer_url") or explorer_tx_url(a.chain_id, tx)) if tx and a.mode == "REAL" else None
    with c.engine.begin() as conn:
        conn.execute(text("UPDATE anchors SET status=:s, tx_hash=:tx, block_number=:b, explorer_url=:e, error=:err,"
                          " updated_at=:t WHERE id=:id"),
                     {"s": status, "tx": tx, "b": res.get("block_number") if tx else None, "e": explorer, "err": err,
                      "t": now_iso(), "id": anchor_id})
        row = _anchor_out(dict(conn.execute(text(ANCHOR_SELECT + " AND a.id=:id"), {"u": uid, "id": anchor_id}).first()._mapping))

    if status == "confirmed":
        c.alerter.send(f"Quai anchor confirmed: user {uid[:8]}… root {root[:16]}… ({row['leaf_count']} logs) "
                       f"tx {tx}" + (f" {explorer}" if explorer else ""))
        c.hub.broadcast_from_thread("anchor", {"merkle_root_id": mid, "tx_hash": tx, "mode": a.mode})
        return row
    c.alerter.send(f"Quai anchoring {status.upper()}: user {uid[:8]}… root {root[:16]}…: {err}")
    raise ServiceError(http_error, err, extra={"anchor": row})


def verify_anchor(c: AppContext, user_id: str, anchor_id: str) -> dict:
    """Transaction check: the root stored on-chain must equal the stored root AND the root recomputed from the logs."""
    uid = _uid(user_id)
    if not _is_uuid(anchor_id):
        raise ServiceError(404, "Anchor not found")
    with c.engine.connect() as conn:
        r = conn.execute(text(ANCHOR_SELECT + " AND a.id=:id"), {"u": uid, "id": str(uuid.UUID(anchor_id))}).first()
        if not r:
            raise ServiceError(404, "Anchor not found")
        a = dict(r._mapping)
        rows = _chain_rows(conn, uid, a["from_seq"], a["to_seq"])
    expected = a["to_seq"] - a["from_seq"] + 1
    # Leaves are RECOMPUTED from the current content (as the shared verifier does), so editing a message changes
    # the local root even if the attacker left the stored hash untouched.
    local = merkle_root([compute_user_log_hash(x["prev_hash"], x) for x in rows]) if rows else None
    problems = []
    if len(rows) != expected:
        problems.append(f"{expected - len(rows)} log(s) of this root are missing from the database")
    chain = verify_chain(rows, expected_first_seq=a["from_seq"], expected_first_prev=rows[0]["prev_hash"] if rows else GENESIS_PREV_HASH,
                         hash_fn=compute_user_log_hash)
    problems += [f"{i['type']} at seq {i['seq_id']}" for i in chain["issues"]]
    if local != a["root"]:
        problems.append("root recomputed from the current logs differs from the stored Merkle root")
    if a["status"] != "confirmed":
        return {"anchor_id": anchor_id, "result": "NOT_ANCHORED", "status": a["status"], "stored_root": a["root"],
                "local_root": local, "onchain_root": None, "problems": problems, "verified_at": now_iso()}
    try:
        onchain = c.anchorer.get_anchor(int(a["onchain_id"]))
    except AnchorError as exc:
        raise ServiceError(503, f"cannot read the anchor from Quai: {exc}")
    onchain_root = onchain["root"] if onchain else None
    if onchain_root is None:
        problems.append("no anchor found on-chain for this root")
    elif onchain_root != a["root"]:
        problems.append("on-chain root differs from the stored Merkle root")
    return {"anchor_id": anchor_id, "result": "MATCH" if not problems else "MISMATCH", "status": a["status"],
            "tx_hash": a["tx_hash"], "stored_root": a["root"], "local_root": local, "onchain_root": onchain_root,
            "problems": problems, "verified_at": now_iso()}


def _is_uuid(v) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except ValueError:
        return False


def _age(iso: str) -> timedelta:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return timedelta.max
