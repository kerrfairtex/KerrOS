# ADR-089: Soft Trace SIEM Export

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-087 persisted traces locally. Operators asked for Soft export bundles
compatible with simple SIEM ingest (JSON or CEF-ish lines).

## Decision

1. Add **`gateway/channels/export.py`** with `export_trace(format=json|cef)`.
2. Expose `gateway channel trace-export [json|cef]`.
3. Writes under `data/channel_trace_export_*`.

## Consequences

**Positive:** Offline Soft SIEM handoff without vendors.

**Negative:** Not a live syslog/HEC push.

## Revisit when

Live SIEM push adapters are funded.
