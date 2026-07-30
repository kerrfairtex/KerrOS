# KerrOS local LLM (C-19) — vLLM sidecar

Soft GPU on-ramp behind existing `VLLMAdapter` / `probe_vllm`
([ADR-048](../../docs/adr/ADR-048-vllm-ops-kit.md), extends
[ADR-016](../../docs/adr/ADR-016-local-llm-ops.md)).

Ollama (CPU-friendly) remains the default local kit:
[`deploy/ollama/`](../ollama/).

## Quickstart (GPU host)

```bash
./scripts/vllm_docker.sh check
./scripts/vllm_docker.sh up
./scripts/vllm_docker.sh probe

export KERROS_LOCAL_LLM=1
export KERROS_VLLM_ENABLED=1
export VLLM_ENDPOINT=http://127.0.0.1:8000/v1
export VLLM_MODEL=meta-llama/Llama-3.2-3B-Instruct
python3 cli/chat.py   # /llm shows vllm availability
```

CPU experimental smoke: `./scripts/vllm_docker.sh up --cpu` (small model).

## Security / ops

- Host publish is `127.0.0.1:8000` only — do not expose without auth/proxy.
- Compose uses profiles (`vllm` / `cpu`) so bare `docker compose up` is a no-op.
- Model weights download into `kerros-vllm-cache` — operator-owned / HF token.
- NVIDIA Container Toolkit required for the GPU profile.
