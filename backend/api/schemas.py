"""Request validation models (Pydantic v2). Unknown fields are rejected."""
from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVENT_TYPES = {4624: "logon", 4634: "logoff", 4672: "special_privileges", 4673: "privileged_service"}
AgentId = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IngestIn(Strict):
    agent_id: str = AgentId
    event_id: Literal[4624, 4634, 4672, 4673]
    event_type: Literal["logon", "logoff", "special_privileges", "privileged_service"]
    severity: Literal["info", "warning", "critical"] = "info"
    source_host: str = Field(min_length=1, max_length=255)
    username: Optional[str] = Field(default=None, max_length=256)
    source_ip: Optional[str] = Field(default=None, max_length=45)
    message: str = Field(min_length=1, max_length=4000)
    event_time: datetime

    @field_validator("source_ip")
    @classmethod
    def _ip(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, "", "-"):
            return None
        return str(ip_address(v))

    @model_validator(mode="after")
    def _type_matches_id(self):
        if EVENT_TYPES[self.event_id] != self.event_type:
            raise ValueError(f"event_type for {self.event_id} must be {EVENT_TYPES[self.event_id]}")
        return self

    def to_record(self) -> dict:
        t = self.event_time if self.event_time.tzinfo else self.event_time.replace(tzinfo=timezone.utc)
        d = self.model_dump()
        d["event_time"] = t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return d


class HeartbeatIn(Strict):
    agent_id: str = AgentId
    hostname: str = Field(min_length=1, max_length=255)
    agent_version: str = Field(default="0.0.0", max_length=32)
    collector_mode: Literal["windows", "simulator"] = "windows"  # "simulator" kept only for rows written by older versions
    sent_at: Optional[datetime] = None


class RangeIn(Strict):
    from_seq: Optional[int] = Field(default=None, ge=1)
    to_seq: Optional[int] = Field(default=None, ge=1)
