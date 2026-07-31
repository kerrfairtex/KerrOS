"""
gateway/channels/signal_relay.py
================================
Soft Signal HTTP relay (ADR-091).

Accepts JSON posts shaped like signal-cli receive envelopes and injects
them into the Signal Soft adapter — so hosted/local bridges can forward
without embedding signal-cli inside KerrOS.
"""

from __future__ import annotations

from typing import Any


def ingest_signal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Soft ingest:
      {"sender":"+1…","text":"hi","chat_id":"+1…"}
    or envelope-ish:
      {"envelope":{"source":"+1","dataMessage":{"message":"hi"}}}
    """
    from gateway.channels.registry import get_adapter, start_channel

    start = start_channel("signal")
    if not start.get("ok") and "disabled" in str(start.get("error") or ""):
        return {"ok": False, "error": start.get("error")}
    ad = get_adapter("signal")
    if not ad or not hasattr(ad, "soft_push"):
        return {"ok": False, "error": "signal adapter unavailable"}

    msgs: list[dict[str, str]] = []
    if not isinstance(payload, dict):
        return {"ok": False, "error": "json object required"}

    if payload.get("text") or payload.get("message"):
        msgs.append(
            {
                "sender": str(payload.get("sender") or payload.get("source") or "unknown"),
                "text": str(payload.get("text") or payload.get("message") or ""),
                "chat_id": str(payload.get("chat_id") or payload.get("sender") or "soft"),
            }
        )
    env = payload.get("envelope")
    if isinstance(env, dict):
        data = env.get("dataMessage") or {}
        text = str((data.get("message") if isinstance(data, dict) else "") or "").strip()
        if text:
            sender = str(env.get("source") or env.get("sourceNumber") or "unknown")
            msgs.append({"sender": sender, "text": text, "chat_id": sender})
    # batch list
    for item in payload.get("messages") or []:
        if isinstance(item, dict) and (item.get("text") or item.get("message")):
            msgs.append(
                {
                    "sender": str(item.get("sender") or item.get("source") or "unknown"),
                    "text": str(item.get("text") or item.get("message") or ""),
                    "chat_id": str(item.get("chat_id") or item.get("sender") or "soft"),
                }
            )

    enqueued = []
    for m in msgs:
        text = (m.get("text") or "").strip()
        if not text:
            continue
        msg = ad.soft_push(text, sender=m["sender"], chat_id=m.get("chat_id") or "soft")
        enqueued.append({"sender": msg.sender, "text": msg.text, "chat_id": msg.chat_id})
    return {"ok": True, "enqueued": len(enqueued), "messages": enqueued}
