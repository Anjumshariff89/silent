"""Central configuration.

Keys are loaded from `.env` with python-dotenv. Key *values* are never logged, printed or
returned by any endpoint: only whether each integration is REAL or which fallback it uses (NOT CONFIGURED/SQLITE/CONSOLE/UNAVAILABLE).
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# Non-secret default used ONLY when MODE=simulator and API_KEY is empty, so the local demo works
# out of the box. MODE=real refuses to start without a real API_KEY and JWT_SECRET.
DEV_API_KEY = "dev-local-api-key"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass
class Settings:
    mode: str = "simulator"
    api_key: str = field(default="", repr=False)
    jwt_secret: str = field(default="", repr=False)
    database_url: str = "sqlite:///./local.db"
    # Quai Orchard Cyprus-1 testnet (used only by the Node.js quai-service; Python never signs)
    rpc_url: str = field(default="", repr=False)
    cyprus1_pk: str = field(default="", repr=False)
    contract_address: str = ""
    chain_id: int = 15000
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id: str = field(default="", repr=False)
    # Supabase Auth (dashboard users). The backend only VERIFIES access tokens; it never needs the service key.
    supabase_url: str = ""
    supabase_jwt_secret: str = field(default="", repr=False)
    frontend_origin: str = ""  # extra CORS origin(s), comma-separated
    # Optional tuning (not secrets, not in .env.example; sensible defaults).
    heartbeat_online_s: float = 20.0
    heartbeat_offline_s: float = 60.0
    monitor_interval_s: float = 5.0
    using_dev_api_key: bool = False

    # ---- integration modes (drive the dashboard badges) ----
    @property
    def blockchain_real(self) -> bool:
        return bool(self.rpc_url and self.cyprus1_pk and self.contract_address)

    @property
    def supabase_auth(self) -> bool:
        """Dashboard sign-in through Supabase Auth instead of the local admin/API_KEY login."""
        return bool(self.supabase_url or self.supabase_jwt_secret)

    @property
    def cors_origins(self) -> list[str]:
        extra = [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()]
        return list(dict.fromkeys(["http://localhost:3000", "http://127.0.0.1:3000", *extra]))

    @property
    def database_real(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgresql+psycopg2://", "postgres://"))

    @property
    def telegram_real(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def integration_modes(self) -> dict[str, str]:
        """Truthful status per integration (no simulated modes).

        blockchain: REAL | READ-ONLY | NOT CONFIGURED   database: SUPABASE | SQLITE
        telegram:   REAL | CONSOLE          windows_event_log: REAL | UNAVAILABLE
        auth:       SUPABASE | LOCAL
        """
        from backend.agent.collector import windows_collector_available  # local import: avoid cycle

        return {
            "blockchain": "REAL" if self.blockchain_real else "READ-ONLY" if self.rpc_url else "NOT CONFIGURED",
            "database": "SUPABASE" if self.database_real else "SQLITE",
            "telegram": "REAL" if self.telegram_real else "CONSOLE",
            "windows_event_log": "REAL" if windows_collector_available() else "UNAVAILABLE",
            "auth": "SUPABASE" if self.supabase_auth else "LOCAL",
        }


def load_settings(env_file: str | os.PathLike | None = None) -> Settings:
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    mode = _env("MODE", "simulator").lower()
    api_key = _env("API_KEY")
    jwt_secret = _env("JWT_SECRET")
    if mode == "real" and (not api_key or not jwt_secret):
        raise RuntimeError("MODE=real requires API_KEY and JWT_SECRET to be set in .env")
    using_dev = False
    if not api_key:
        api_key, using_dev = DEV_API_KEY, True
    if not jwt_secret:
        jwt_secret = secrets.token_urlsafe(48)  # per-process; tokens expire on restart
    db_url = _env("DATABASE_URL", "sqlite:///./local.db")
    if db_url.startswith("sqlite:///./"):
        # Resolve relative SQLite paths against the project root, not the CWD.
        db_url = "sqlite:///" + str((PROJECT_ROOT / db_url[len("sqlite:///./"):]).as_posix())
    return Settings(
        mode=mode,
        api_key=api_key,
        jwt_secret=jwt_secret,
        database_url=db_url,
        rpc_url=_env("RPC_URL") or _env("QUAI_RPC_URL"),          # QUAI_* names are accepted aliases
        cyprus1_pk=_env("CYPRUS1_PK") or _env("QUAI_PRIVATE_KEY"),  # presence check only; Node signs
        contract_address=_env("CONTRACT_ADDRESS"),
        chain_id=int(_env("CHAIN_ID", "15000")),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        supabase_url=_env("SUPABASE_URL").rstrip("/"),
        supabase_jwt_secret=_env("SUPABASE_JWT_SECRET"),
        frontend_origin=_env("FRONTEND_ORIGIN"),
        heartbeat_online_s=float(_env("HEARTBEAT_ONLINE_SECONDS", "20")),
        heartbeat_offline_s=float(_env("HEARTBEAT_OFFLINE_SECONDS", "60")),
        monitor_interval_s=float(_env("MONITOR_INTERVAL_SECONDS", "5")),
        using_dev_api_key=using_dev,
    )
