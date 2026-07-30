# ADR-070: WhatsApp Soft Channel Adapter

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-066/069 covered Telegram and Discord. Operators still asked for a
WhatsApp ingress path that shares the same KerrOS channel protocol and
webhook inbox pump, without taking a live Cloud API dependency yet.

## Decision

1. Add **`gateway/channels/whatsapp.py`** Soft adapter (`start` / `stop` /
   `poll` / `send` / `soft_push`).
2. Accept Cloud-API-shaped Soft payloads via `soft_push_webhook` and
   `gateway channel soft-webhook whatsapp <json>`.
3. Register under `whatsapp`; enable with `KERROS_WHATSAPP=1`.
4. Live Cloud API (`KERROS_WHATSAPP_LIVE`) stays deferred.

## Consequences

**Positive:** Protocol-complete Soft demos and CI coverage for WhatsApp.

**Negative:** No live send/receive until Cloud API credentials + ADR.

## Revisit when

Meta Cloud API live path or Signal Soft adapter is funded.
