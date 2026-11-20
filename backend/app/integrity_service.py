"""Runs verification, persists results, creates incidents and sends alerts."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.context import AppContext
from backend.crypto.hashing import GENESIS_PREV_HASH
from backend.crypto.verifier import verify_chain
from backend.database import repo


def run_chain_verification(c: AppContext, *, source: Engine | None = None, target: str = "live",
                           from_seq: int | None = None, to_seq: int | None = None) -> dict:
    """Verify `source` (default: the live DB) and record result/incidents in the LIVE DB."""
    source = source or c.engine
    with source.connect() as conn:
        rows = repo.fetch_chain_rows(conn, from_seq, to_seq)
        first_prev, first_seq = GENESIS_PREV_HASH, 1
        if from_seq and from_seq > 1:
            prev = repo.get_log(conn, from_seq - 1)
            first_prev, first_seq = (prev["curr_hash"] if prev else None), from_seq
    report = verify_chain(rows, expected_first_seq=first_seq, expected_first_prev=first_prev)
    incidents = []
    with c.engine.begin() as conn:
        v = repo.record_verification(conn, kind="chain", result=report["result"], target=target,
                                     checked_count=report["checked_count"], issues=report["issues"])
        for issue in report["issues"]:
            prefix = "[SANDBOX DEMO] " if target == "sandbox" else ""
            text_ = f"{prefix}Tamper detected: {issue['type'].upper()} at seq {issue['seq_id']} - {issue['detail']}"
            channel, sent = c.alerter.send(text_)
            incidents.append(repo.create_incident(conn, type=issue["type"], severity="critical", seq_id=issue["seq_id"],
                                                  verification_id=v["id"], target=target, description=issue["detail"],
                                                  alert_channel=channel, alert_sent=sent))
    out = {"verification_id": v["id"], "target": target, **report,
           "incidents_created": [i["id"] for i in incidents], "verified_at": v["verified_at"]}
    c.hub.broadcast_from_thread("integrity", {"status": "green" if report["result"] == "PASS" else "red",
                                              "last_result": report["result"], "target": target})
    for i in incidents:
        c.hub.broadcast_from_thread("incident", i)
    return out


def integrity_status(c: AppContext) -> dict:
    with c.engine.connect() as conn:
        last = repo.last_verification(conn, "chain")
        _, open_total = repo.list_incidents(conn, status="open", type=None, page=1, page_size=1)
        open_critical = sum(1 for i in repo.list_incidents(conn, status="open", type=None, page=1, page_size=1000)[0]
                            if i["severity"] == "critical")
        total = repo.count_logs(conn)
        last_anchor = conn.execute(text("SELECT max(batch_id) FROM blockchain_anchors")).scalar()
    if last and (last["result"] == "FAIL" or open_critical):
        status = "red"
    elif last and last["result"] == "PASS" and open_total == 0:
        status = "green"
    else:
        status = "yellow"  # never verified, or only non-critical open incidents (e.g. agent timeout)
    return {"status": status, "last_result": last["result"] if last else None,
            "last_target": last["target"] if last else None,
            "last_verified_at": last["verified_at"] if last else None,
            "last_issues": json.loads(last["issues_json"]) if last else [],
            "total_logs": total, "open_incidents": open_total, "open_critical_incidents": open_critical,
            "last_anchored_batch_id": last_anchor}
