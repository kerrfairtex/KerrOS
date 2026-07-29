#!/usr/bin/env bash
# Run KerrOS RAG injection promptfoo suite against loopback OmniRoute.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVAL_DIR="${ROOT}/eval/omniroute_rag_promptfoo"
ENDPOINT="${OMNIROUTE_ENDPOINT:-http://127.0.0.1:20128/v1}"

die() { echo "error: $*" >&2; exit 1; }

command -v npx >/dev/null 2>&1 || die "npx not found — install Node.js to run promptfoo"
[[ -f "${EVAL_DIR}/promptfooconfig.yaml" ]] || die "missing promptfooconfig.yaml"

echo "Preflight: GET ${ENDPOINT%/}/models"
if command -v curl >/dev/null 2>&1; then
  curl -fsS --max-time 5 "${ENDPOINT%/}/models" >/dev/null \
    || die "OmniRoute not reachable at ${ENDPOINT} — run scripts/omniroute_droplet.sh up"
else
  python3 - "$ENDPOINT" <<'PY' || die "OmniRoute not reachable"
import sys, urllib.request
url = sys.argv[1].rstrip("/") + "/models"
urllib.request.urlopen(url, timeout=5)
PY
fi

export OMNIROUTE_ENDPOINT="$ENDPOINT"
cd "$EVAL_DIR"
echo "Running promptfoo eval (KerrOS RAG fixtures)…"
npx --yes promptfoo@0.103.0 eval -c promptfooconfig.yaml "$@"
