# KerrOS offline LLM gateway (Phase E / ADR-054) — llama.cpp + LiteLLM

Soft OpenAI-compatible gateway for the offline Qwen 0.5B profile.
Weights stay on the host (`models/qwen0.5b-q4.gguf`). Compose profiles are
default-off so bare `docker compose up` is a no-op.

**Status:** Fake `plan` + compose are shipped; the gateway is **not live**
until you start containers (`up --litellm`) and `probe` succeeds. See
ADR-054 “Pending — until live containers.”

Related: [`ADR-050`](../../docs/adr/ADR-050-offline-qwen05-profile.md),
[`ADR-054`](../../docs/adr/ADR-054-offline-litellm-llamacpp.md),
[`deploy/ollama/`](../ollama/), [`deploy/vllm/`](../vllm/).

## Quickstart

```bash
# Ensure GGUF exists:
./scripts/download_qwen05_gguf.sh

./scripts/llama_cpp_docker.sh check
./scripts/llama_cpp_docker.sh up                 # llama.cpp :8080
./scripts/llama_cpp_docker.sh up --litellm       # + LiteLLM :4000
./scripts/llama_cpp_docker.sh probe

export KERROS_OFFLINE_PROFILE=offline_qwen05
export LLAMA_CPP_SERVER_ENDPOINT=http://127.0.0.1:8080/v1
export LITELLM_ENDPOINT=http://127.0.0.1:4000/v1
export LITELLM_MODEL=qwen0.5b-q4
export KERROS_LLM_PROVIDER=litellm
python3 cli/chat.py   # /llm shows litellm / llama_cpp
```

Soft proxy edge: `./scripts/llama_cpp_docker.sh up --proxy`

## Security / ops

- Host publish is loopback-only (`127.0.0.1:8080` / `:4000`).
- Profiles: `llama_cpp`, `litellm`, `proxy`.
- GGUF is bind-mounted read-only from `models/` — not bundled in the image.
- Not a production TLS/auth seal (see ADR-049 soft proxy).
