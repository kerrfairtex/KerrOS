#!/usr/bin/env bash
set -euo pipefail
SRC="${1:-.env}"
OUT="${2:-.env.example}"
if [ ! -f "$SRC" ]; then
    echo "No $SRC found — nothing to do."
    exit 0
fi
grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$SRC" | sed -E 's/^([A-Za-z_][A-Za-z0-9_]*)=.*/\1=/' > "$OUT"
echo "Wrote $OUT:"
cat "$OUT"
