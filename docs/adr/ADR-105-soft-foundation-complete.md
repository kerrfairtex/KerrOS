# ADR-105: Soft Foundation Complete

**Status:** Accepted  
**Date:** 2026-07-31

## Context

KerrOS Soft surfaces through ADR-104 (channels, REPL/TUI, offline combo A–E,
mesh/LGU Soft on-ramps) are in-tree. Operators asked to “finish the project”
without implying infinite live-cloud/GPU work.

## Decision

1. Declare **Soft foundation complete** in
   [`docs/PROJECT_COMPLETE.md`](../PROJECT_COMPLETE.md).
2. Treat remaining live container verification and production seals as
   **operator-owned / contract-gated**, not missing Soft product.
3. Land unmerged agent-capability Soft work (ADR-068…104 + Termux fix) on
   the mainline finish branch.

## Consequences

**Positive:** Clear done-line for Soft KerrOS; Termux/offline chat path stable.

**Negative:** Live GGUF gateway still needs an operator host to verify.

## Revisit when

A funded production deploy (TLS, HA, accreditation) is specified.
