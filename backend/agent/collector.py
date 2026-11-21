"""Event collector: Windows Security Event Log (pywin32), read-only.

The collector only READS the Security log (ReadEventLog). It never clears, writes or backs up system
logs. There is no synthetic event generator: logs come from Windows or from the ingest API.
"""
from __future__ import annotations

import ipaddress
import random
import socket
from datetime import datetime, timezone
from typing import Iterator, Protocol

MONITORED_EVENTS: dict[int, tuple[str, str, str]] = {
    4624: ("logon", "info", "An account was successfully logged on"),
    4634: ("logoff", "info", "An account was logged off"),
    4672: ("special_privileges", "warning", "Special privileges assigned to new logon"),
    4673: ("privileged_service", "warning", "A privileged service was called"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def windows_collector_available() -> bool:
    """True only on Windows with pywin32 importable."""
    try:
        import win32evtlog  # noqa: F401  (pywin32)
    except Exception:
        return False
    return True


class Collector(Protocol):
    mode: str

    def collect(self, max_events: int = 10) -> list[dict]: ...


class WindowsEventLogCollector:  # pragma: no cover - requires Windows + pywin32
    """Reads new events from the Windows 'Security' log (read-only). Needs admin rights."""

    mode = "windows"

    def __init__(self) -> None:
        import win32evtlog  # pywin32

        self._ev = win32evtlog
        self.hostname = socket.gethostname()
        self._handle = win32evtlog.OpenEventLog(None, "Security")
        self._last_record = self._newest_record()

    def _newest_record(self) -> int:
        oldest = self._ev.GetOldestEventLogRecord(self._handle)
        total = self._ev.GetNumberOfEventLogRecords(self._handle)
        return oldest + total - 1

    def collect(self, max_events: int = 10) -> list[dict]:
        flags = self._ev.EVENTLOG_FORWARDS_READ | self._ev.EVENTLOG_SEEK_READ
        out: list[dict] = []
        try:
            records = self._ev.ReadEventLog(self._handle, flags, self._last_record + 1)
        except Exception:
            return out
        for rec in records or []:
            self._last_record = max(self._last_record, rec.RecordNumber)
            event_id = rec.EventID & 0xFFFF
            if event_id not in MONITORED_EVENTS:
                continue
            etype, severity, msg = MONITORED_EVENTS[event_id]
            inserts = list(rec.StringInserts or [])
            out.append({
                "event_id": event_id,
                "event_type": etype,
                "severity": severity,
                "source_host": rec.ComputerName or self.hostname,
                "username": inserts[5] if len(inserts) > 5 else None,
                "source_ip": inserts[18] if event_id == 4624 and len(inserts) > 18 else None,
                "message": msg,
                "event_time": rec.TimeGenerated.Format("%Y-%m-%dT%H:%M:%SZ"),
            })
            if len(out) >= max_events:
                break
        return out

    @staticmethod
    def field_names() -> list[str]:
        """Names of the PyEVENTLOGRECORD attributes read (names only, no content)."""
        return ["RecordNumber", "EventID", "ComputerName", "TimeGenerated", "StringInserts"]


class CollectorUnavailable(Exception):
    """Raised when real Windows Security events cannot be read on this machine."""


def make_collector(prefer: str = "auto") -> Collector:
    """Return the real Windows Security Event Log collector. There is no synthetic fallback: on machines without
    pywin32, or without the rights to read the Security log, CollectorUnavailable explains what is missing."""
    if not windows_collector_available():
        raise CollectorUnavailable("pywin32 / Windows Event Log not available on this machine (Windows only)")
    try:
        return WindowsEventLogCollector()
    except Exception as exc:  # e.g. not elevated: "Access is denied"
        raise CollectorUnavailable(f"cannot read the Windows Security log ({type(exc).__name__}); "
                                   "run PowerShell as Administrator") from None
