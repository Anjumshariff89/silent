"""Incident alerts: Telegram Bot API (REAL) with console fallback (SIMULATED).

The bot token is used only inside the request URL and is never logged or included in errors.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("lace.alerts")


class Alerter:
    def __init__(self, bot_token: str = "", chat_id: str = "", transport: httpx.BaseTransport | None = None):
        self._token = bot_token
        self._chat_id = chat_id
        self._transport = transport
        self.sent: list[str] = []  # in-memory record of console alerts (useful for demo/tests)

    @property
    def real(self) -> bool:
        return bool(self._token and self._chat_id)

    def _console(self, text: str) -> tuple[str, bool]:
        line = f"[ALERT][console] {text}"
        print(line, flush=True)
        self.sent.append(text)
        return "console", True

    def send(self, text: str) -> tuple[str, bool]:
        """Return (channel, delivered)."""
        if not self.real:
            return self._console(text)
        try:
            with httpx.Client(timeout=10.0, transport=self._transport) as client:
                r = client.post(f"https://api.telegram.org/bot{self._token}/sendMessage",
                                json={"chat_id": self._chat_id, "text": f"🚨 {text}"})
            if r.status_code == 200 and r.json().get("ok"):
                return "telegram", True
            log.warning("Telegram alert rejected (HTTP %s); falling back to console", r.status_code)
        except Exception as exc:  # never include exc text: it can contain the URL (with token)
            log.warning("Telegram alert failed (%s); falling back to console", type(exc).__name__)
        channel, ok = self._console(text)
        return "console(telegram-failed)", ok
