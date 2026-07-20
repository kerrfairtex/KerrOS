# ADR-003: scope_gate — Fail-Closed Default with Time-Limited Arm/Disarm

**Status:** DRAFT — built from your own account of `tools/scope_gate.py`. Verify `arm_deploy()`'s exact default window/behavior against the live code before committing, since the specifics (default minutes, confirmation wording) aren't confirmed here.

**Date:** 2026-07-20

## Context
KerrOS's tool dispatch spans two categories that can cause real, hard-to-reverse effects: offensive/security tools (OSINT, pentest, recon-style actions) and deploy tools (GitHub, Vercel, Netlify, Railway, Cloudflare, Stripe — real credentials, real infrastructure). This runs conversationally, on a personal device, where a misread instruction or an overeager agent action could trigger something destructive with no undo. A safety layer was needed that assumes deny by default, not one that logs and allows.

## Decision
`tools/scope_gate.py` is fail-closed: any offensive or deploy-tool action is denied unless explicitly authorized, through three mechanisms layered together:
1. **Explicit-command gating** — all tool dispatch (not just offensive tools) requires explicit command phrasing ("execute/build/create/generate now"), not conversational language, to trigger.
2. **Inline y/n confirmation** — offensive tools get an interactive confirm step before running.
3. **Time-limited arm/disarm windows for deploy tools** — `arm_deploy(minutes)` opens a window that auto-expires; outside that window, deploy tools are disarmed by default. `/scope arm-deploy <minutes>` is the chat-facing command for this, with its own confirmation flow.

## Alternatives considered
- **Fail-open with logging only** — record what happened after the fact instead of blocking it. Rejected: doesn't prevent the irreversible action, just documents it once it's too late.
- **Permanent allowlist** — arm a target/tool once, stays armed indefinitely. Rejected for deploy tools specifically: leaving deploy credentials permanently live is a standing risk that outlives the work session that needed it.
- **Manual per-call force flag** — e.g. requiring `--force` on every risky call. Rejected as more friction than the explicit-command + confirm pattern, and a worse fit for a conversational interface than for a traditional CLI.

## Consequences
Every offensive or deploy action costs a deliberate confirmation step — that friction is the point, not a bug to optimize away. The fail-closed default means if `scope_gate.py` itself errors or crashes, the safe outcome is denial, not silent pass-through; this is the exact property KOS-011's watchdog must preserve on restart (default to disarmed, never resume a last-known-armed state). Time-limited arm windows add a bit of bookkeeping (tracking expiry) versus a plain boolean flag, but avoid the more dangerous failure mode of a forgotten, permanently-armed deploy path.

## Revisit when
- KOS-012 (Code Agent subprocess isolation) changes how tool dispatch is routed — confirm scope_gate checks still apply identically once dispatch crosses a process boundary, not just within the main process
- Arm-window friction becomes a real workflow problem in practice — if so, the fix is better UX around confirmation, not loosening the fail-closed default
- 
