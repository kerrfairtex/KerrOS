"""
adapters/audit/siem_forwarder.py
================================
Best-effort SIEM forwarder for decision_log events (ADR-021).

Default-off. Failures never raise into ``record()`` / seal paths.
Transports: ``webhook`` (HTTP POST JSON) or ``syslog`` (UDP JSON line).
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.parse import urlparse


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class SiemForwarder:
    enabled: bool = False
    transport: str = "webhook"  # webhook | syslog
    url: str = ""
    timeout_s: float = 2.0
    token: str = ""
    forward_on_record: bool = True
    forward_on_seal: bool = True
    _sent: int = field(default=0, init=False, repr=False)
    _errors: int = field(default=0, init=False, repr=False)

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "transport": self.transport,
            "sent": self._sent,
            "errors": self._errors,
        }

    def forward(self, event: str, payload: Mapping[str, Any]) -> bool:
        if not self.enabled or not self.url:
            return False
        body = {
            "event": str(event),
            **dict(payload),
        }
        try:
            if self.transport == "syslog":
                self._send_syslog(body)
            else:
                self._send_webhook(body)
            self._sent += 1
            return True
        except Exception:
            self._errors += 1
            return False

    def forward_record(self, payload: Mapping[str, Any]) -> bool:
        if not self.forward_on_record:
            return False
        return self.forward("decision_record", payload)

    def forward_seal(self, payload: Mapping[str, Any]) -> bool:
        if not self.forward_on_seal:
            return False
        return self.forward("worm_seal", payload)

    def _send_webhook(self, body: dict[str, Any]) -> None:
        data = json.dumps(body, sort_keys=True).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            self.url, data=data, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            # Drain body; ignore content.
            resp.read(256)

    def _send_syslog(self, body: dict[str, Any]) -> None:
        # url forms: udp://host:514 or host:514
        text = self.url.strip()
        if text.startswith("udp://"):
            text = text[len("udp://") :]
        elif text.startswith("syslog://"):
            text = text[len("syslog://") :]
        host, _, port_s = text.rpartition(":")
        if not host:
            parsed = urlparse(self.url)
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 514)
        else:
            port = int(port_s or 514)
        line = json.dumps(body, sort_keys=True).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self.timeout_s)
            sock.sendto(line, (host, port))
        finally:
            sock.close()


_forwarder: SiemForwarder | None = None


def siem_from_config(cfg: Optional[Mapping[str, Any]] = None) -> SiemForwarder:
    data = dict(cfg or {})
    raw = dict(data.get("audit_siem") or {})
    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_SIEM")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    url = os.environ.get("KERROS_AUDIT_SIEM_URL")
    if url is None:
        url = str(raw.get("url") or "")
    transport = os.environ.get("KERROS_AUDIT_SIEM_TRANSPORT")
    if transport is None:
        transport = str(raw.get("transport") or "webhook")
    token = os.environ.get("KERROS_AUDIT_SIEM_TOKEN")
    if token is None:
        token = str(raw.get("token") or "")
    timeout = float(raw.get("timeout_s", 2.0))
    return SiemForwarder(
        enabled=bool(enabled),
        transport=str(transport or "webhook").strip().lower(),
        url=str(url or "").strip(),
        timeout_s=max(0.1, timeout),
        token=str(token or "").strip(),
        forward_on_record=_truthy(raw.get("forward_on_record", True)),
        forward_on_seal=_truthy(raw.get("forward_on_seal", True)),
    )


def get_siem_forwarder(cfg: Optional[Mapping[str, Any]] = None) -> SiemForwarder:
    global _forwarder
    if cfg is not None:
        return siem_from_config(cfg)
    if _forwarder is None:
        try:
            from kernel.config import load_config

            _forwarder = siem_from_config(load_config().values)
        except Exception:
            _forwarder = SiemForwarder()
    return _forwarder


def reset_siem_forwarder() -> None:
    global _forwarder
    _forwarder = None
