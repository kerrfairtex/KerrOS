"""
gateway/channels/whatsapp.py
============================
WhatsApp channel adapter (ADR-070 / ADR-076).

Default Soft. Live Cloud API behind:
  KERROS_WHATSAPP=1
  KERROS_WHATSAPP_LIVE=1
  KERROS_WHATSAPP_TOKEN=<access token>
  KERROS_WHATSAPP_PHONE_ID=<phone number id>
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from gateway.channels.base import InboundMessage, OutboundMessage

GRAPH_BASE = "https://graph.facebook.com/v19.0"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def load_waba_map() -> dict[str, dict[str, str]]:
    """
    ADR-086 multi-WABA Soft map.

    KERROS_WHATSAPP_WABAS JSON:
      {"phoneA": {"token":"…","label":"sales"}, "phoneB": {"token":"…"}}
    Falls back to single KERROS_WHATSAPP_PHONE_ID / TOKEN.
    """
    raw = (os.environ.get("KERROS_WHATSAPP_WABAS") or "").strip()
    out: dict[str, dict[str, str]] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for phone_id, meta in parsed.items():
                    if isinstance(meta, dict):
                        out[str(phone_id)] = {
                            "token": str(meta.get("token") or ""),
                            "label": str(meta.get("label") or phone_id),
                        }
                    elif isinstance(meta, str):
                        out[str(phone_id)] = {"token": meta, "label": str(phone_id)}
        except Exception:
            out = {}
    default_phone = (os.environ.get("KERROS_WHATSAPP_PHONE_ID") or "").strip()
    default_token = (os.environ.get("KERROS_WHATSAPP_TOKEN") or "").strip()
    if default_phone and default_phone not in out:
        out[default_phone] = {"token": default_token, "label": "default"}
    return out


class WhatsAppAdapter:
    name = "whatsapp"

    def __init__(self) -> None:
        self._running = False
        self._soft_inbox: list[InboundMessage] = []
        self._soft_outbox: list[OutboundMessage] = []
        self._active_phone_id = ""

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_WHATSAPP"))

    def _wabas(self) -> dict[str, dict[str, str]]:
        return load_waba_map()

    def _live(self) -> bool:
        wabas = self._wabas()
        if not _truthy(os.environ.get("KERROS_WHATSAPP_LIVE")):
            return False
        if not wabas:
            return False
        return any(bool(v.get("token")) for v in wabas.values())

    def _token(self, phone_id: Optional[str] = None) -> str:
        wabas = self._wabas()
        pid = (phone_id or self._active_phone_id or self._phone_id()).strip()
        if pid and pid in wabas and wabas[pid].get("token"):
            return wabas[pid]["token"]
        return (os.environ.get("KERROS_WHATSAPP_TOKEN") or "").strip()

    def _phone_id(self) -> str:
        if self._active_phone_id:
            return self._active_phone_id
        wabas = self._wabas()
        if wabas:
            return next(iter(wabas.keys()))
        return (os.environ.get("KERROS_WHATSAPP_PHONE_ID") or "").strip()

    def _api(self, path: str, body: Optional[dict] = None) -> dict[str, Any]:
        token = self._token(self._active_phone_id or self._phone_id())
        if not token:
            return {"ok": False, "error": "missing WhatsApp token for active phone id"}
        url = f"{GRAPH_BASE}{path}"
        data = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "KerrOS-WhatsAppAdapter (ADR-076/086)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw.strip() else {}
            if isinstance(parsed, dict) and parsed.get("error"):
                err = parsed.get("error") or {}
                return {
                    "ok": False,
                    "error": err.get("message") if isinstance(err, dict) else str(err),
                }
            return {"ok": True, "result": parsed}
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            return {"ok": False, "error": detail or str(exc)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def status(self) -> dict[str, Any]:
        wabas = self._wabas()
        return {
            "ok": True,
            "channel": self.name,
            "enabled": self._enabled(),
            "live": self._live(),
            "running": self._running,
            "mode": "live" if self._live() else "soft",
            "wabas": [
                {"phone_id": k, "label": v.get("label"), "has_token": bool(v.get("token"))}
                for k, v in wabas.items()
            ],
            "active_phone_id": self._phone_id() or None,
            "soft_inbox": len(self._soft_inbox),
            "soft_outbox": len(self._soft_outbox),
            "note": None
            if self._live()
            else "live Cloud API behind KERROS_WHATSAPP_LIVE=1 + token/phone id (multi-WABA: KERROS_WHATSAPP_WABAS)",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "whatsapp disabled — set KERROS_WHATSAPP=1"}
        self._running = True
        if self._live():
            return {"ok": True, "mode": "live", "phone_id": self._phone_id()}
        return {"ok": True, "mode": "soft", "note": "inject via soft_push or soft_push_webhook"}

    def stop(self) -> dict[str, Any]:
        self._running = False
        return {"ok": True, "stopped": True}

    def soft_push(
        self,
        text: str,
        *,
        sender: str = "user",
        chat_id: str = "soft",
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

    def soft_push_webhook(self, payload: dict[str, Any]) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        if not isinstance(payload, dict):
            return out
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value") or {}
                if not isinstance(value, dict):
                    continue
                meta = value.get("metadata") or {}
                phone_number_id = ""
                if isinstance(meta, dict):
                    phone_number_id = str(meta.get("phone_number_id") or "")
                if phone_number_id:
                    self._active_phone_id = phone_number_id
                waba = self._wabas().get(phone_number_id) if phone_number_id else None
                label = (waba or {}).get("label") if waba else phone_number_id or "default"
                for m in value.get("messages") or []:
                    if not isinstance(m, dict):
                        continue
                    body = ""
                    text = m.get("text") or {}
                    if isinstance(text, dict):
                        body = str(text.get("body") or "").strip()
                    if not body:
                        continue
                    sender = str(m.get("from") or "unknown")
                    msg = InboundMessage(
                        channel=self.name,
                        sender=sender,
                        text=body[:4000],
                        chat_id=sender,
                        raw={
                            "soft": True,
                            "message": m,
                            "phone_number_id": phone_number_id,
                            "waba_label": label,
                        },
                    )
                    self._soft_inbox.append(msg)
                    out.append(msg)
        return out

    def poll(self) -> list[InboundMessage]:
        if not self._running:
            return []
        # Live inbound is webhook-driven; Soft inbox covers CI + local inject
        out = list(self._soft_inbox)
        self._soft_inbox.clear()
        return out

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        if not self._live():
            self._soft_outbox.append(msg)
            return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
        to = (msg.chat_id or "").strip()
        if not to:
            return {"ok": False, "mode": "live", "error": "missing chat_id (E.164)"}
        phone_id = self._phone_id()
        # Prefer phone id from meta when present
        if isinstance(msg.meta, dict) and msg.meta.get("phone_number_id"):
            phone_id = str(msg.meta.get("phone_number_id"))
            self._active_phone_id = phone_id
        res = self._api(
            f"/{phone_id}/messages",
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": (msg.text or "")[:4096]},
            },
        )
        # _api uses default token; swap Authorization via temporary env is messy —
        # re-call with explicit token header by patching through _token(phone_id)
        if not res.get("ok") and self._token(phone_id):
            # retry path already uses _token(); ensure active phone set
            self._active_phone_id = phone_id
            res = self._api(
                f"/{phone_id}/messages",
                {
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": (msg.text or "")[:4096]},
                },
            )
        return {
            "ok": bool(res.get("ok")),
            "mode": "live",
            "phone_id": phone_id,
            "result": res.get("result"),
            "error": res.get("error"),
        }
