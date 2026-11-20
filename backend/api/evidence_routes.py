"""Evidence downloads: JSON bundle and PDF certificate."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.api.auth import Jwt, ctx
from backend.app.anchor_service import ServiceError
from backend.app.evidence import build_bundle, render_pdf

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def _bundle(request: Request, batch_id: int) -> dict:
    try:
        return build_bundle(ctx(request), batch_id)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/{batch_id}/json", dependencies=[Jwt])
def evidence_json(batch_id: int, request: Request) -> Response:
    body = json.dumps(_bundle(request, batch_id), indent=2, ensure_ascii=False)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=evidence_batch_{batch_id}.json"})


@router.get("/{batch_id}/pdf", dependencies=[Jwt])
def evidence_pdf(batch_id: int, request: Request) -> Response:
    return Response(render_pdf(_bundle(request, batch_id)), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=evidence_batch_{batch_id}.pdf"})
