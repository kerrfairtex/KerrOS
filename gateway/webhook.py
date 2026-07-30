"""
gateway/webhook.py
==================
Minimal HTTP webhook channel gateway (ADR-064).

Default-off. Enable with KERROS_GATEWAY=1.
Accepts JSON POSTs at /v1/message and optionally runs a reply callback.
No third-party messaging SDKs required — operators can front Telegram/Discord
with their own bridge that posts here.

Safety:
  - loopback bind by default (127.0.0.1)
  - optional shared token (KERROS_GATEWAY_TOKEN)
  - never prints secrets
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

ReplyFn = Callable[[str, dict[str, Any]], str]

_server: Optional[ThreadingHTTPServer] = None
_thread: Optional[threading.Thread] = None
_reply_fn: Optional[ReplyFn] = None
_inbox: list[dict[str, Any]] = []
_lock = threading.RLock()


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def is_gateway_enabled(cfg: Optional[dict] = None) -> bool:
    env = os.environ.get("KERROS_GATEWAY")
    if env is not None:
        return _truthy(env)
    block = (cfg or {}).get("gateway") if isinstance((cfg or {}).get("gateway"), dict) else {}
    return _truthy(block.get("enabled", False))


def set_reply_handler(fn: Optional[ReplyFn]) -> None:
    global _reply_fn
    _reply_fn = fn


def inbox_snapshot(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        return list(_inbox[-max(1, min(int(limit), 100)) :])


def clear_inbox() -> None:
    with _lock:
        _inbox.clear()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return  # quiet

    def _auth_ok(self) -> bool:
        token = os.environ.get("KERROS_GATEWAY_TOKEN") or ""
        if not token:
            return True
        got = self.headers.get("Authorization") or self.headers.get("X-Kerros-Token") or ""
        if got.startswith("Bearer "):
            got = got[7:]
        return got == token

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/v1/health"):
            self._json(200, {"ok": True, "service": "kerros-gateway"})
            return
        if self.path.startswith("/v1/inbox"):
            if not self._auth_ok():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            self._json(200, {"ok": True, "messages": inbox_snapshot()})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/v1/message", "/message"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._auth_ok():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(max(0, min(length, 100_000)))
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "error": "json object required"})
            return
        text = str(payload.get("text") or payload.get("message") or "").strip()
        channel = str(payload.get("channel") or "webhook")
        sender = str(payload.get("sender") or "unknown")
        if not text:
            self._json(400, {"ok": False, "error": "text required"})
            return
        msg = {"channel": channel, "sender": sender, "text": text[:4000]}
        with _lock:
            _inbox.append(msg)
            if len(_inbox) > 500:
                del _inbox[:-500]
        reply = ""
        if _reply_fn is not None:
            try:
                reply = str(_reply_fn(text, msg) or "")[:4000]
            except Exception as exc:
                reply = f"[gateway reply error] {exc}"
        self._json(200, {"ok": True, "received": msg, "reply": reply})

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_gateway(
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    reply_fn: Optional[ReplyFn] = None,
) -> dict[str, Any]:
    global _server, _thread, _reply_fn
    if not is_gateway_enabled():
        return {"ok": False, "error": "gateway disabled — set KERROS_GATEWAY=1"}
    if reply_fn is not None:
        _reply_fn = reply_fn
    host = host or os.environ.get("KERROS_GATEWAY_HOST") or "127.0.0.1"
    # Refuse non-loopback unless explicitly allowed
    if host not in ("127.0.0.1", "localhost", "::1") and not _truthy(
        os.environ.get("KERROS_GATEWAY_ALLOW_NON_LOOPBACK")
    ):
        return {"ok": False, "error": "refusing non-loopback bind; set KERROS_GATEWAY_ALLOW_NON_LOOPBACK=1"}
    port = int(port or os.environ.get("KERROS_GATEWAY_PORT") or 8788)
    with _lock:
        if _server is not None:
            return {"ok": True, "already_running": True, "host": host, "port": port}
        _server = ThreadingHTTPServer((host, port), _Handler)
        _thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _thread.start()
    return {"ok": True, "host": host, "port": port, "endpoints": ["/health", "/v1/message", "/v1/inbox"]}


def stop_gateway() -> dict[str, Any]:
    global _server, _thread
    with _lock:
        if _server is None:
            return {"ok": True, "stopped": False}
        try:
            _server.shutdown()
        except Exception:
            pass
        _server = None
        _thread = None
    return {"ok": True, "stopped": True}


def gateway_status() -> dict[str, Any]:
    with _lock:
        running = _server is not None
        n = len(_inbox)
    return {
        "ok": True,
        "enabled": is_gateway_enabled(),
        "running": running,
        "inbox_count": n,
    }


def gateway_cmd(action: str, raw: str = "") -> str:
    action = (action or "status").strip().lower()
    if action == "start":
        return json.dumps(start_gateway(), indent=2)
    if action == "stop":
        return json.dumps(stop_gateway(), indent=2)
    if action == "status":
        return json.dumps(gateway_status(), indent=2)
    if action == "inbox":
        return json.dumps({"ok": True, "messages": inbox_snapshot()}, indent=2)
    if action in ("channel", "channels"):
        from gateway.channels.registry import channels_cmd

        parts = (raw or "").strip().split(None, 1)
        sub = parts[0] if parts else "list"
        rest = parts[1] if len(parts) > 1 else ""
        return channels_cmd(sub, rest)
    return "[gateway] actions: start|stop|status|inbox|channel …"
