# ADR-086: WhatsApp Multi-WABA Soft Routing

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-076 assumed a single phone number id. Operators with multiple WABAs
need Soft routing by `metadata.phone_number_id`.

## Decision

1. Add `KERROS_WHATSAPP_WABAS` JSON map of phone_id → token/label.
2. Webhook Soft inject sets active phone id from metadata.
3. Status lists configured WABAs.

## Consequences

**Positive:** Multi-number Soft demos without schema changes.

**Negative:** Live token rotation UI still deferred.

## Revisit when

Hosted WABA credential vault is funded.
