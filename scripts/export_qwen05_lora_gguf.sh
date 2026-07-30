#!/usr/bin/env bash
# Phase D / ADR-053 — plan or soft-export Unsloth LoRA → GGUF Q4_K_M.
#
# Default is Fake plan (safe for CI). On a GPU host:
#   KERROS_FINETUNE=1 KERROS_FINETUNE_ALLOW_TRAIN=1 KERROS_FINETUNE_BACKEND=unsloth \
#     ./scripts/export_qwen05_lora_gguf.sh train
#   KERROS_FINETUNE=1 KERROS_FINETUNE_ALLOW_EXPORT=1 \
#     ./scripts/export_qwen05_lora_gguf.sh export
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CMD="${1:-plan}"
export KERROS_FINETUNE="${KERROS_FINETUNE:-1}"
export KERROS_FINETUNE_BACKEND="${KERROS_FINETUNE_BACKEND:-fake}"
export KERROS_FINETUNE_GGUF="${KERROS_FINETUNE_GGUF:-$ROOT/models/qwen0.5b-q4.gguf}"
export KERROS_FINETUNE_QUANT="${KERROS_FINETUNE_QUANT:-Q4_K_M}"

python3 - "$CMD" <<'PY'
import json, os, sys
from pathlib import Path
from adapters.llm.unsloth_finetune import (
    UnslothFinetuneConfig,
    UnslothFinetuneService,
)

cmd = sys.argv[1]
root = Path(".").resolve()
cfg = UnslothFinetuneConfig.from_mapping(
    {
        "enabled": True,
        "backend": os.environ.get("KERROS_FINETUNE_BACKEND", "fake"),
        "allow_train": os.environ.get("KERROS_FINETUNE_ALLOW_TRAIN", "0"),
        "allow_export": os.environ.get("KERROS_FINETUNE_ALLOW_EXPORT", "0"),
        "gguf_out": os.environ.get("KERROS_FINETUNE_GGUF", "models/qwen0.5b-q4.gguf"),
        "quant": os.environ.get("KERROS_FINETUNE_QUANT", "Q4_K_M"),
        "dataset_path": os.environ.get(
            "KERROS_FINETUNE_DATASET", "data/finetune/dataset.jsonl"
        ),
        "output_dir": os.environ.get(
            "KERROS_FINETUNE_OUT", "data/finetune/lora_out"
        ),
    },
    base=root,
)
svc = UnslothFinetuneService(cfg=cfg)
if cmd == "plan":
    out = svc.plan()
elif cmd == "train":
    out = svc.train()
elif cmd == "export":
    out = svc.export()
elif cmd == "stats":
    out = svc.stats()
else:
    print(f"unknown command: {cmd}", file=sys.stderr)
    sys.exit(2)
print(json.dumps(out, indent=2, sort_keys=True))
PY
