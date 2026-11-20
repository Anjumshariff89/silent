"""Auth: X-API-Key for agents, JWT (HS256) for the dashboard."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])
JWT_TTL = timedelta(minutes=60)


def ctx(request: Request):
    return request.app.state.ctx


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected = ctx(request).settings.api_key
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def create_token(secret: str, subject: str = "admin") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": subject, "iat": now, "exp": now + JWT_TTL}, secret, algorithm="HS256")


def decode_token(secret: str, token: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])


def require_jwt(request: Request, authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return decode_token(ctx(request).settings.jwt_secret, authorization.split(" ", 1)[1])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
def login(body: LoginIn, request: Request) -> dict:
    """Demo login: username `admin`, password = the API_KEY value from .env (see README)."""
    s = ctx(request).settings
    ok_user = hmac.compare_digest(body.username.encode(), b"admin")
    ok_pass = hmac.compare_digest(body.password.encode(), s.api_key.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_token(s.jwt_secret), "token_type": "bearer", "expires_in": int(JWT_TTL.total_seconds())}


ApiKey = Depends(require_api_key)
Jwt = Depends(require_jwt)
