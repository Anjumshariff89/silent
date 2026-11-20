"""Evidence bundle (JSON) and certificate (PDF)."""
from __future__ import annotations

import io
import json

from sqlalchemy import text

from backend.app.anchor_service import ServiceError, get_anchor_row, verify_batch
from backend.app.context import AppContext
from backend.blockchain.anchor import explorer_address_url
from backend.crypto.hashing import HASHED_FIELDS
from backend.database import repo
from backend.merkle.tree import inclusion_proof

SCHEMA_VERSION = "1.0"
DISCLAIMER = ("Blockchain anchoring proves only that this Merkle root has not changed since it was anchored. "
              "It does not prove that the logged events occurred, that the log source was honest, or that logs "
              "were accurate or complete before anchoring.")
NETWORK_NAMES = {15000: "Quai Orchard Cyprus-1 (testnet)", 9: "Quai Mainnet Cyprus-1"}
REQUIRED_FIELDS = ("schema_version", "generated_at", "batch", "logs", "hash_algorithm", "canonicalization",
                   "merkle", "proofs", "anchor", "verification", "disclaimer")


def build_bundle(c: AppContext, batch_id: int) -> dict:
    with c.engine.connect() as conn:
        b = conn.execute(text("SELECT * FROM merkle_batches WHERE batch_id=:b"), {"b": batch_id}).first()
        if not b:
            raise ServiceError(404, f"Merkle batch {batch_id} not found")
        b = dict(b._mapping)
        rows = repo.fetch_chain_rows(conn, b["from_seq"], b["to_seq"])
        anchor = get_anchor_row(conn, batch_id)
        prev_of_first = repo.get_log(conn, b["from_seq"] - 1) if b["from_seq"] > 1 else None
    levels = json.loads(b["levels_json"])
    verification = verify_batch(c, batch_id, record=True)
    logs = [{k: r[k] for k in ("seq_id", *HASHED_FIELDS, "prev_hash", "curr_hash")} for r in rows]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": repo.now_iso(),
        "batch": {"batch_id": batch_id, "from_seq": b["from_seq"], "to_seq": b["to_seq"],
                  "leaf_count": b["leaf_count"], "merkle_root": b["root"], "created_at": b["created_at"],
                  "prev_batch_tail_hash": prev_of_first["curr_hash"] if prev_of_first else "0" * 64},
        "logs": logs,
        "hash_algorithm": "SHA-256",
        "canonicalization": "curr_hash = SHA-256(prev_hash_hex + JSON(hashed_fields, sorted keys, separators=(',',':'),"
                            " ensure_ascii=False)) as UTF-8",
        "hashed_fields": list(HASHED_FIELDS),
        "merkle": {"leaf": "SHA-256(0x00 || bytes(curr_hash))", "node": "SHA-256(0x01 || left || right)",
                   "odd_node": "paired with itself"},
        "proofs": {str(r["seq_id"]): inclusion_proof(levels, i) for i, r in enumerate(rows)},
        "anchor": None if not anchor else {
            "network": NETWORK_NAMES.get(anchor["chain_id"], f"chain {anchor['chain_id']}"),
            "mode": anchor["mode"], "chain_id": anchor["chain_id"], "contract_address": anchor["contract_address"],
            "contract_explorer_url": explorer_address_url(anchor["chain_id"], anchor["contract_address"]),
            "onchain_batch_id": anchor["onchain_batch_id"], "anchored_root": anchor["root"],
            "tx_hash": anchor["tx_hash"], "block_number": anchor["block_number"],
            "block_timestamp": anchor["block_timestamp"], "explorer_url": anchor["explorer_url"],
            "how_to_check_onchain": (
                "Open explorer_url on Orchard QuaiScan to see the anchoring transaction and its RootAnchored event "
                "(batchId = onchain_batch_id, root = anchored_root). Or call getAnchor(onchain_batch_id) on the "
                "contract with any quais/JSON-RPC client and compare the returned root with merkle_root. "
                "Contract source is not verified on QuaiScan (metadata is not published to IPFS)."
                if anchor["mode"] == "REAL" else "SIMULATED anchor: not on a public blockchain; nothing to check on-chain."),
            "explorer_status": ("transaction and event visible on Orchard QuaiScan; contract source not verified"
                                if anchor["mode"] == "REAL" else "not applicable (simulated)")},
        "verification": {k: verification.get(k) for k in ("result", "local_root", "anchored_root", "logs_found",
                                                         "problems", "verified_at")},
        "disclaimer": DISCLAIMER,
    }


def render_pdf(bundle: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Evidence certificate - batch {bundle['batch']['batch_id']}",
                            leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    ss = getSampleStyleSheet()
    mono = ParagraphStyle("mono", parent=ss["BodyText"], fontName="Courier", fontSize=7.5, leading=9)
    body = ss["BodyText"]
    b, a, v = bundle["batch"], bundle["anchor"] or {}, bundle["verification"]
    result_color = {"MATCH": colors.HexColor("#15803d"), "MISMATCH": colors.HexColor("#b91c1c")}.get(
        v["result"], colors.HexColor("#a16207"))

    def P(t, st=body):
        return Paragraph(str(t) if t is not None else "-", st)

    story = [
        Paragraph("Tamper-Evidence Certificate", ss["Title"]),
        Paragraph("Logs the Attacker Can't Erase", ss["Heading3"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Verification result: <font color='{result_color.hexval()}'><b>{v['result']}</b></font>",
                  ss["Heading2"]),
    ]
    rows = [
        ["Batch ID", P(b["batch_id"])], ["Sequence range", P(f"{b['from_seq']} - {b['to_seq']} ({b['leaf_count']} logs)")],
        ["Merkle root", P(b["merkle_root"], mono)], ["Root recomputed now", P(v["local_root"], mono)],
        ["Anchored root", P(v["anchored_root"], mono)], ["Anchor mode", P(a.get("mode", "NOT ANCHORED"))],
        ["Network", P(a.get("network", "-"))], ["Chain ID", P(a.get("chain_id"))],
        ["Contract", P(a.get("contract_address"), mono)],
        ["On-chain batch key", P(a.get("onchain_batch_id"), mono)], ["Transaction", P(a.get("tx_hash"), mono)],
        ["Block / time", P(f"{a.get('block_number', '-')} / {a.get('block_timestamp', '-')}")],
        ["Explorer", P(a.get("explorer_url") or "n/a (simulated anchor)", mono)],
        ["Explorer status", P(a.get("explorer_status", "-"))],
        ["Verified at", P(v.get("verified_at"))], ["Generated at", P(bundle["generated_at"])],
    ]
    if v.get("problems"):
        rows.append(["Problems", P("; ".join(v["problems"]))])
    t = Table(rows, colWidths=[38 * mm, None])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                           ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
    story += [t, Spacer(1, 5 * mm), Paragraph("What this does and does not prove", ss["Heading3"]),
              P(f"<b>Disclaimer:</b> {bundle['disclaimer']}"), Spacer(1, 2 * mm),
              P("MATCH means the logs listed in the accompanying JSON bundle, re-hashed at verification time, produce "
                "exactly the Merkle root that was anchored. Anyone can repeat the check offline from the JSON bundle "
                "alone (python -m backend.crypto.offline_verify bundle.json)."),
              Spacer(1, 4 * mm), Paragraph("First logs in batch", ss["Heading3"])]
    preview = [["seq", "event", "user", "curr_hash"]] + [
        [l["seq_id"], l["event_type"], l["username"] or "-", P(l["curr_hash"][:32] + "...", mono)]
        for l in bundle["logs"][:15]]
    pt = Table(preview, colWidths=[12 * mm, 34 * mm, 34 * mm, None])
    pt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
    story.append(pt)
    doc.build(story)
    return buf.getvalue()
