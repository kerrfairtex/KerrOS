"""
gateway/channels/discord_gateway.py
===================================
Discord Gateway Soft event bus + optional live websocket (ADR-075).

Default Soft: inject DISPATCH events (e.g. MESSAGE_CREATE) for CI.
Live path (KERROS_DISCORD_GATEWAY_LIVE=1 + token) uses an optional
websocket client library when installed; otherwise stays Soft.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

from gateway.channels.base import InboundMessage

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class DiscordGateway:
    """Soft-first Discord Gateway event source."""

    def __init__(self) -> None:
        self._running = False
        self._soft_events: list[dict[str, Any]] = []
        self._inbox: list[InboundMessage] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._live_error: Optional[str] = None
        self._seq: Optional[int] = None

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_DISCORD_GATEWAY")) or _truthy(
            os.environ.get("KERROS_DISCORD")
        )

    def _live(self) -> bool:
        return _truthy(os.environ.get("KERROS_DISCORD_GATEWAY_LIVE")) and bool(
            os.environ.get("KERROS_DISCORD_TOKEN")
        )

    def _token(self) -> str:
        return (os.environ.get("KERROS_DISCORD_TOKEN") or "").strip()

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "component": "discord_gateway",
            "enabled": self._enabled(),
            "live": self._live(),
            "running": self._running,
            "mode": "live" if self._live() and not self._live_error else "soft",
            "queued_events": len(self._soft_events),
            "inbox": len(self._inbox),
            "live_error": self._live_error,
            "note": None
            if self._live()
            else "inject via soft_dispatch; live needs KERROS_DISCORD_GATEWAY_LIVE=1",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {
                "ok": False,
                "error": "discord gateway disabled — set KERROS_DISCORD_GATEWAY=1",
            }
        self._running = True
        self._stop.clear()
        self._live_error = None
        if self._live():
            self._thread = threading.Thread(
                target=self._live_loop, name="kerros-discord-gw", daemon=True
            )
            self._thread.start()
            return {"ok": True, "mode": "live", "note": "websocket thread started"}
        return {"ok": True, "mode": "soft"}

    def stop(self) -> dict[str, Any]:
        self._running = False
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2)
        self._thread = None
        return {"ok": True, "stopped": True}

    def soft_dispatch(self, event_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Inject a Soft Gateway DISPATCH payload (CI / demos)."""
        evt = {"t": event_name, "d": data or {}, "op": 0, "soft": True}
        self._soft_events.append(evt)
        extra = self._consume_dispatch(event_name, data or {})
        out = {"ok": True, "event": event_name, "inbox": len(self._inbox)}
        if extra:
            out["slash"] = extra
        return out

    def _consume_dispatch(self, event_name: str, data: dict[str, Any]) -> Optional[dict]:
        if event_name == "INTERACTION_CREATE":
            try:
                from gateway.channels.slash import soft_interaction_create

                return soft_interaction_create(data or {})
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        if event_name != "MESSAGE_CREATE":
            return None
        if data.get("author", {}).get("bot"):
            return None
        text = str(data.get("content") or "").strip()
        if not text:
            return None
        author = data.get("author") or {}
        self._inbox.append(
            InboundMessage(
                channel="discord",
                sender=str(author.get("username") or author.get("id") or "unknown"),
                text=text[:4000],
                chat_id=str(data.get("channel_id") or ""),
                raw={"gateway": True, "event": event_name, "data": data},
            )
        )
        return None

    def poll_messages(self) -> list[InboundMessage]:
        if not self._running:
            return []
        # Drain Soft event queue leftovers (already consumed into inbox)
        self._soft_events.clear()
        out = list(self._inbox)
        self._inbox.clear()
        return out

    def _live_loop(self) -> None:
        """Best-effort live Gateway; Soft-safe if websocket stack missing."""
        try:
            self._run_live_websocket()
        except Exception as exc:
            self._live_error = str(exc)

    def _run_live_websocket(self) -> None:
        token = self._token()
        if not token:
            self._live_error = "missing KERROS_DISCORD_TOKEN"
            return
        # Prefer websocket-client if present
        try:
            import websocket  # type: ignore
        except Exception:
            self._live_error = (
                "websocket-client not installed — Soft gateway only "
                "(pip install websocket-client)"
            )
            return

        def on_message(_ws, message: str) -> None:
            try:
                payload = json.loads(message)
            except Exception:
                return
            op = payload.get("op")
            if payload.get("s") is not None:
                self._seq = payload.get("s")
            if op == 10:  # Hello
                # Identify
                identify = {
                    "op": 2,
                    "d": {
                        "token": token,
                        "intents": 513,  # GUILDS + GUILD_MESSAGES
                        "properties": {
                            "os": "linux",
                            "browser": "kerros",
                            "device": "kerros",
                        },
                    },
                }
                _ws.send(json.dumps(identify))
                interval = float((payload.get("d") or {}).get("heartbeat_interval", 41250)) / 1000.0

                def heartbeat() -> None:
                    while self._running and not self._stop.is_set():
                        try:
                            _ws.send(json.dumps({"op": 1, "d": self._seq}))
                        except Exception:
                            break
                        time.sleep(max(5.0, interval))

                threading.Thread(target=heartbeat, daemon=True).start()
            elif op == 0:
                self._consume_dispatch(str(payload.get("t") or ""), payload.get("d") or {})

        def on_error(_ws, error: Exception) -> None:
            self._live_error = str(error)

        ws = websocket.WebSocketApp(
            GATEWAY_URL,
            on_message=on_message,
            on_error=on_error,
        )
        while self._running and not self._stop.is_set():
            try:
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:
                self._live_error = str(exc)
            if self._stop.wait(3):
                break


_GATEWAY: Optional[DiscordGateway] = None
_lock = threading.RLock()


def get_discord_gateway() -> DiscordGateway:
    global _GATEWAY
    with _lock:
        if _GATEWAY is None:
            _GATEWAY = DiscordGateway()
        return _GATEWAY


def reset_discord_gateway() -> None:
    global _GATEWAY
    with _lock:
        if _GATEWAY is not None:
            try:
                _GATEWAY.stop()
            except Exception:
                pass
        _GATEWAY = None
