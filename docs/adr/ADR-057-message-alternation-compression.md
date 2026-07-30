# ADR-057: Message Role Alternation + Context Compression Trigger

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Hermes enforces strict `user ↔ assistant` alternation (with tool-call
nesting as the only exception) and compresses context when conversation
size exceeds ~50% of the model window. KerrOS has had silent prompt
corruption bugs and runs on constrained RAM; `core/context.build` budgets
string prompts, but `build_chat` + REPL history assembly do not validate
roles or trigger early compression.

## Decision

1. Add **`core/message_policy.py`** with:
   - `validate_alternation(messages)` — repair or flag bad role sequences
   - `should_compress(messages, context_size, max_tokens)` — ~50% window
   - `compress_messages(...)` — fold older turns into a short system summary
2. Apply validation/compression when assembling chat history in
   `cli/chat.py` and expose helpers for `build` / `build_chat`.
3. No new dependencies; token estimate remains `len//4` (existing heuristic).

## Consequences

**Positive:** Catches malformed histories before LLM calls; frees RAM sooner.

**Negative:** Aggressive compression may drop nuance — keep last N turns raw.

## Revisit when

A real tokenizer is available or multimodal roles are introduced.
