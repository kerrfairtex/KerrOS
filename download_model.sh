#!/usr/bin/env bash
# Legacy 1.5B download — prefer Phase A 0.5B profile:
#   ./scripts/download_qwen05_gguf.sh
#   docs/adr/ADR-050-offline-qwen05-profile.md
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
huggingface-cli download \
  Qwen/Qwen2.5-1.5B-Instruct-GGUF \
  qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --local-dir models/
mv models/qwen2.5-1.5b-instruct-q4_k_m.gguf models/model.gguf 2>/dev/null || true
echo "Done (1.5B → models/model.gguf). For 0.5B offline profile use: ./scripts/download_qwen05_gguf.sh"
echo "Run: bash run.sh"
