"""Event collectors: Windows Security Event Log (pywin32) with automatic simulator fallback.

The Windows collector only READS the Security log (EvtQuery / ReadEventLog). It never clears,
writes or backs up system logs. The simulator produces synthetic data only.
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


class SimulatorCollector:
    """Generates synthetic security events. No real users, hosts or IPs."""

    mode = "simulator"

    def __init__(self, hostname: str = "WIN-SYNTH-01", seed: int | None = None):
        self.hostname = hostname
        self.rng = random.Random(seed)

    def _event(self) -> dict:
        event_id = self.rng.choices(list(MONITORED_EVENTS), weights=[50, 35, 10, 5])[0]
        etype, severity, msg = MONITORED_EVENTS[event_id]
        user = f"synthetic.user{self.rng.randint(1, 8)}"
        ip = str(ipaddress.IPv4Address(int(ipaddress.IPv4Address("10.0.0.0")) + self.rng.randint(2, 250)))
        return {
            "event_id": event_id,
            "event_type": etype,
            "severity": severity,
            "source_host": self.hostname,
            "username": user,
            "source_ip": ip,
            "message": f"{msg} (synthetic)",
            "event_time": _now(),
        }

    def collect(self, max_events: int = 10) -> list[dict]:
        return [self._event() for _ in range(self.rng.randint(1, max(1, max_events)))]


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


def make_collector(prefer: str = "auto", hostname: str = "WIN-SYNTH-01") -> Collector:
    """Return the Windows collector when possible, else fall back to the simulator."""
    if prefer in ("auto", "windows") and windows_collector_available():
        try:
            return WindowsEventLogCollector()
        except Exception as exc:  # e.g. not elevated: Access is denied
            print(f"[agent] Windows collector unavailable ({type(exc).__name__}); falling back to simulator")
            return SimulatorCollector(hostname)
    if prefer == "windows":
        print("[agent] pywin32 not available on this host; falling back to simulator")
    return SimulatorCollector(hostname)
