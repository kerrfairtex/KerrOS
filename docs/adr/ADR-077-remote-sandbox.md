# ADR-077: Remote Sandbox Soft Backend

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-064 process backends cover local / fake / docker Soft. Operators still
need a KerrOS-native Soft facade for remote sandbox fleets (HTTP exec
workers) without hard-coding a vendor SDK.

## Decision

1. Add **`RemoteSandboxBackend`** (`KERROS_BG_BACKEND=remote`).
2. Soft plan by default; live POST when `KERROS_REMOTE_SANDBOX=1` and
   `KERROS_REMOTE_SANDBOX_URL` is set (optional bearer token).
3. Expected JSON: `{ok, output, exit_code}`.

## Consequences

**Positive:** Pluggable remote exec Soft for CI + operator fleets.

**Negative:** No native vendor SDK integrations in-tree.

## Revisit when

A specific fleet contract (image pinning, filesystem mounts) is funded.
