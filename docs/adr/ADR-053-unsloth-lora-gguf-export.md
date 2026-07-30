# ADR-053: Unsloth LoRA → GGUF Export (Phase D)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-050](ADR-050-offline-qwen05-profile.md) through
[ADR-052](ADR-052-offline-coding-index.md) shipped offline LLM, RAG, and
coding index. Phase D adds the **fine-tune → GGUF** path for the Offline
Combo: Unsloth LoRA on Qwen2.5-0.5B-Instruct, merge, quantize to
**Q4_K_M**, write `models/qwen0.5b-q4.gguf`.

CI must not download Unsloth or run GPU jobs.

## Decision

1. Add **`adapters/llm/unsloth_finetune.py`** — Fake `plan()` /
   gated `train()` / `export()`; `provisioned_production` always False
2. Soft path: Unsloth present + `allow_train` writes train intent;
   `llama-quantize` + merged F16 + `allow_export` may write GGUF
3. Operator script **`scripts/export_qwen05_lora_gguf.sh`**
4. Claw tools **`finetune_plan`** / **`finetune_export`** (+
   `/finetune-plan`, `/finetune-export`)
5. Profile `finetune:` block + `finetune_export` config defaults
6. Sample dataset stub: `data/finetune/dataset.jsonl.example`

Out of scope: bundling Unsloth in core deps, silent GPU SFT in CI,
LiteLLM gateway (Phase E), automated HF dataset download.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Full SFT in-process by default | Breaks CI / cloud VMs without GPU |
| Require Unsloth in requirements.txt | Heavy CUDA stack |
| Auto-set provisioned_production | Compliance / ops risk |

## Consequences

**Positive:** Funded GPU hosts have a documented LoRA→GGUF on-ramp.

**Negative:** Real train/merge still operator-owned notebooks/scripts.

## Revisit when

Phase E (LiteLLM + llama.cpp server), or a funded deploy that turns on
`allow_train` / `allow_export` for a named model.
