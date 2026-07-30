# KerrOS local LLM (C-19) — Ollama sidecar

Self-hosted models behind `LLMPort` via existing `OllamaAdapter` / `VLLMAdapter`.
This kit runs **Ollama** on loopback. vLLM usually needs a GPU host — see
[`ADR-016`](../../docs/adr/ADR-016-local-llm-ops.md) for probe/env only.

## Quickstart

```bash
./scripts/local_llm_docker.sh up
./scripts/local_llm_docker.sh pull llama3.2
./scripts/local_llm_docker.sh probe

export KERROS_LOCAL_LLM=1
export OLLAMA_ENDPOINT=http://127.0.0.1:11434/v1
export OLLAMA_MODEL=llama3.2
python3 cli/chat.py   # /llm shows ollama availability
```

## Security

- Host publish is `127.0.0.1:11434` only — do not expose Ollama on a public
  interface without auth / reverse proxy.
- Models are large; volume `kerros-ollama-data` holds pulled weights.
