# ADR-076: Live WhatsApp Cloud API + Signal Daemon Bridge

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-070/071 shipped WhatsApp and Signal Soft adapters. Operators need opt-in
live send/receive without changing the KerrOS channel protocol.

## Decision

1. **WhatsApp** live Cloud API send behind `KERROS_WHATSAPP_LIVE=1` +
   `KERROS_WHATSAPP_TOKEN` + `KERROS_WHATSAPP_PHONE_ID` (inbound remains
   webhook / Soft inject).
2. **Signal** live `signal-cli` bridge behind `KERROS_SIGNAL_LIVE=1` when the
   binary is on PATH (`KERROS_SIGNAL_CLI`, `KERROS_SIGNAL_ACCOUNT`).
3. Soft remains default; live failures Soft-fall where safe.

## Consequences

**Positive:** Protocol-stable Soft + live paths for both channels.

**Negative:** WhatsApp live inbound still webhook-shaped; Signal depends on
local daemon install.

## Revisit when

Hosted Signal relay or WhatsApp multi-WABA routing is required.
