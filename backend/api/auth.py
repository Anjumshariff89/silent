"""Auth: X-API-Key for agents; bearer tokens for the dashboard.

Dashboard tokens are either
- Supabase Auth access tokens (when SUPABASE_URL / SUPABASE_JWT_SECRET are set): verified with the project's
  legacy JWT secret (HS256) or its public signing keys (JWKS, ES256/RS256); aud must be "authenticated" and the
  role "authenticated", so the anon / service_role keys are rejected; or
- local tokens from POST /api/auth/login (admin + API_KEY), only when Supabase Auth is not configured.
"""
from __future__ import annotations

import hmac
import threading
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


_jwks_clients: dict[str, jwt.PyJWKClient] = {}
_jwks_lock = threading.Lock()


def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    with _jwks_lock:
        if url not in _jwks_clients:
            _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=10)
        return _jwks_clients[url]


def verify_supabase_token(settings, token: str) -> dict:
    """Verify a Supabase Auth access token. Raises jwt.PyJWTError on any problem."""
    alg = jwt.get_unverified_header(token).get("alg")
    opts = {"require": ["exp", "sub", "aud"]}
    issuer = f"{settings.supabase_url}/auth/v1" if settings.supabase_url else None
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not set")
        key = settings.supabase_jwt_secret
    elif alg in ("ES256", "RS256"):
        if not settings.supabase_url:
            raise jwt.InvalidTokenError(f"{alg} token but SUPABASE_URL is not set (needed for the JWKS keys)")
        try:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientError as exc:
            raise jwt.InvalidTokenError(f"cannot load Supabase signing keys: {exc}") from None
    else:
        raise jwt.InvalidAlgorithmError(f"unsupported token algorithm {alg!r}")
    claims = jwt.decode(token, key, algorithms=[alg], audience="authenticated", issuer=issuer, options=opts)
    if claims.get("role") != "authenticated":
        raise jwt.InvalidTokenError("not a signed-in user token")
    return {**claims, "user_id": claims["sub"], "auth": "supabase"}


def verify_bearer(settings, token: str) -> dict:
    """The one place dashboard tokens are checked (HTTP routes and the WebSocket)."""
    if settings.supabase_auth:
        return verify_supabase_token(settings, token)
    claims = decode_token(settings.jwt_secret, token)
    return {**claims, "user_id": claims.get("sub"), "auth": "local"}


def require_jwt(request: Request, authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        user = verify_bearer(ctx(request).settings, authorization.split(" ", 1)[1])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    request.state.user = user
    return user


def require_api_key_or_jwt(request: Request, x_api_key: str | None = Header(default=None),
                           authorization: str | None = Header(default=None)) -> dict:
    """Ingest from an agent (X-API-Key) or from a signed-in user (bearer token)."""
    if x_api_key:
        require_api_key(request, x_api_key)
        return {"user_id": None, "auth": "api_key"}
    return require_jwt(request, authorization)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
def login(body: LoginIn, request: Request) -> dict:
    """Local login: username `admin`, password = the API_KEY value from .env. Disabled when Supabase Auth is on."""
    s = ctx(request).settings
    if s.supabase_auth:
        raise HTTPException(status_code=403, detail="Local login is disabled: sign in with your Supabase account")
    ok_user = hmac.compare_digest(body.username.encode(), b"admin")
    ok_pass = hmac.compare_digest(body.password.encode(), s.api_key.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_token(s.jwt_secret), "token_type": "bearer", "expires_in": int(JWT_TTL.total_seconds())}


ApiKey = Depends(require_api_key)
Jwt = Depends(require_jwt)
ApiKeyOrJwt = Depends(require_api_key_or_jwt)
