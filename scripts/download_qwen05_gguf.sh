#!/usr/bin/env bash
# Download Qwen2.5-0.5B-Instruct GGUF Q4_K_M for the offline profile (ADR-050).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT}/models"
OUT_FILE="${OUT_DIR}/qwen0.5b-q4.gguf"
REPO="${HF_REPO:-Qwen/Qwen2.5-0.5B-Instruct-GGUF}"
# Common filename variants across community GGUF repos
CANDIDATES=(
  "qwen2.5-0.5b-instruct-q4_k_m.gguf"
  "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
  "qwen2.5-0_5b-instruct-q4_k_m.gguf"
)
FILE="${HF_FILE:-${CANDIDATES[0]}}"

die() { echo "error: $*" >&2; exit 1; }

mkdir -p "$OUT_DIR"

if [[ -f "$OUT_FILE" ]]; then
  echo "already present: $OUT_FILE"
  ls -lh "$OUT_FILE"
  exit 0
fi

if command -v huggingface-cli >/dev/null 2>&1; then
  DL=(huggingface-cli download)
elif command -v hf >/dev/null 2>&1; then
  DL=(hf download)
else
  die "huggingface-cli (or hf) not found — pip install -U huggingface_hub"
fi

echo "Downloading ${REPO} → ${OUT_FILE}"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

downloaded=""
for candidate in "$FILE" "${CANDIDATES[@]}"; do
  echo "trying: $candidate"
  if "${DL[@]}" "$REPO" "$candidate" --local-dir "$tmpdir" 2>/tmp/kerros-hf-dl.err; then
    src="$(find "$tmpdir" -type f -name "*.gguf" | head -n1 || true)"
    if [[ -n "$src" ]]; then
      downloaded="$src"
      break
    fi
  fi
done

if [[ -z "$downloaded" ]]; then
  cat /tmp/kerros-hf-dl.err >&2 || true
  die "could not download GGUF from ${REPO} (override HF_REPO / HF_FILE)"
fi

mv "$downloaded" "$OUT_FILE"
ls -lh "$OUT_FILE"
echo "Done. Set MODEL_PATH=${OUT_FILE} or KERROS_OFFLINE_PROFILE=offline_qwen05"
echo "Also set LLAMA_BIN to your llama.cpp binary, then: python3 cli/chat.py"
