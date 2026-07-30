"""
gateway/channels/signal.py
==========================
Signal channel adapter (ADR-071 / ADR-076).

Default Soft. Live local daemon bridge behind:
  KERROS_SIGNAL=1
  KERROS_SIGNAL_LIVE=1
  KERROS_SIGNAL_CLI=signal-cli   # optional path; defaults to PATH lookup
  KERROS_SIGNAL_ACCOUNT=+E164    # required for live send
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Optional

from gateway.channels.base import InboundMessage, OutboundMessage


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class SignalAdapter:
    name = "signal"

    def __init__(self) -> None:
        self._running = False
        self._soft_inbox: list[InboundMessage] = []
        self._soft_outbox: list[OutboundMessage] = []

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_SIGNAL"))

    def _cli(self) -> Optional[str]:
        configured = (os.environ.get("KERROS_SIGNAL_CLI") or "signal-cli").strip()
        return shutil.which(configured) or (
            configured if os.path.isfile(configured) else None
        )

    def _live(self) -> bool:
        return _truthy(os.environ.get("KERROS_SIGNAL_LIVE")) and bool(self._cli())

    def _account(self) -> str:
        return (os.environ.get("KERROS_SIGNAL_ACCOUNT") or "").strip()

    def status(self) -> dict[str, Any]:
        cli = self._cli()
        return {
            "ok": True,
            "channel": self.name,
            "enabled": self._enabled(),
            "live": self._live(),
            "running": self._running,
            "mode": "live" if self._live() else "soft",
            "cli": cli,
            "account": self._account() or None,
            "soft_inbox": len(self._soft_inbox),
            "soft_outbox": len(self._soft_outbox),
            "note": None
            if self._live()
            else "live daemon behind KERROS_SIGNAL_LIVE=1 + signal-cli on PATH",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "signal disabled — set KERROS_SIGNAL=1"}
        self._running = True
        if self._live():
            return {"ok": True, "mode": "live", "cli": self._cli()}
        return {
            "ok": True,
            "mode": "soft",
            "note": "inject via soft_push; install signal-cli for live",
        }

    def stop(self) -> dict[str, Any]:
        self._running = False
        return {"ok": True, "stopped": True}

    def soft_push(
        self, text: str, *, sender: str = "user", chat_id: str = "soft"
    ) -> InboundMessage:
        msg = InboundMessage(
            channel=self.name,
            sender=sender,
            text=text,
            chat_id=chat_id,
            raw={"soft": True},
        )
        self._soft_inbox.append(msg)
        return msg

    def poll(self) -> list[InboundMessage]:
        if not self._running:
            return []
        if not self._live():
            out = list(self._soft_inbox)
            self._soft_inbox.clear()
            return out
        # Live receive: best-effort `signal-cli receive` JSON lines (Soft-safe on failure)
        cli = self._cli()
        account = self._account()
        if not cli or not account:
            out = list(self._soft_inbox)
            self._soft_inbox.clear()
            return out
        messages: list[InboundMessage] = []
        try:
            proc = subprocess.run(
                [cli, "-a", account, "receive", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    import json

                    payload = json.loads(line)
                except Exception:
                    continue
                env = payload.get("envelope") or {}
                data_msg = env.get("dataMessage") or {}
                text = str(data_msg.get("message") or "").strip()
                if not text:
                    continue
                sender = str(env.get("source") or env.get("sourceNumber") or "unknown")
                messages.append(
                    InboundMessage(
                        channel=self.name,
                        sender=sender,
                        text=text[:4000],
                        chat_id=sender,
                        raw={"live": True, "envelope": env},
                    )
                )
        except Exception:
            pass
        soft = list(self._soft_inbox)
        self._soft_inbox.clear()
        return soft + messages

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        if not self._live():
            self._soft_outbox.append(msg)
            return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
        cli = self._cli()
        account = self._account()
        to = (msg.chat_id or "").strip()
        if not cli or not account or not to:
            self._soft_outbox.append(msg)
            return {
                "ok": False,
                "mode": "soft",
                "error": "live send needs cli + KERROS_SIGNAL_ACCOUNT + chat_id",
                "queued": len(self._soft_outbox),
            }
        try:
            proc = subprocess.run(
                [cli, "-a", account, "send", "-m", (msg.text or "")[:4000], to],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            ok = proc.returncode == 0
            return {
                "ok": ok,
                "mode": "live",
                "stdout": (proc.stdout or "")[:500],
                "stderr": (proc.stderr or "")[:500],
                "error": None if ok else (proc.stderr or f"exit {proc.returncode}"),
            }
        except Exception as exc:
            return {"ok": False, "mode": "live", "error": str(exc)}
