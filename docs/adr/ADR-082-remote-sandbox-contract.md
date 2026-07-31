# ADR-082: Remote Sandbox Image + Mount Contract

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-077 Soft remote exec lacked image pinning and filesystem mount specs
needed for fleet operators.

## Decision

1. Extend `RemoteSandboxBackend` Soft/live payload with:
   - `KERROS_REMOTE_SANDBOX_IMAGE`
   - `KERROS_REMOTE_SANDBOX_MOUNTS` (JSON list or `src:tgt[:mode],…`)
2. Soft plan output includes image/mount counts; live POST sends contract.

## Consequences

**Positive:** Vendor-neutral fleet contract without in-tree SDKs.

**Negative:** Mount enforcement is remote-side responsibility.

## Revisit when

A signed policy bundle or image allowlist UI is funded.
