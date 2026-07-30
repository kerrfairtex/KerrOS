#!/usr/bin/env bash
# KerrOS local LLM (Ollama) helper — C-19 / ADR-016 / ADR-049.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/ollama"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
HOST_PORT="${OLLAMA_HOST_PORT:-11434}"
USE_PROXY=0

die() { echo "error: $*" >&2; exit 1; }

need_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found"
  docker compose version >/dev/null 2>&1 || die "docker compose plugin required"
}

check_loopback() {
  [[ -f "$COMPOSE_FILE" ]] || die "missing $COMPOSE_FILE"
  python3 - "$COMPOSE_FILE" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
ports, in_ports = [], False
for line in text.splitlines():
    if re.match(r"^\s*ports:\s*$", line):
        in_ports = True
        continue
    if in_ports:
        if re.match(r"^\s*[a-zA-Z0-9_]+:\s*", line) and not line.strip().startswith("-"):
            in_ports = False
            continue
        m = re.match(r'^\s*-\s*["\']?([^"\'#]+)["\']?', line)
        if m:
            ports.append(m.group(1).strip())
bad, ok = [], []
for p in ports:
    parts = p.split(":")
    if len(parts) == 2 and parts[0].isdigit():
        bad.append(p)
    elif len(parts) >= 3 and parts[0] in ("127.0.0.1", "localhost", "::1"):
        ok.append(p)
    else:
        bad.append(p)
if bad:
    print("REFUSED: non-loopback:", ", ".join(bad), file=sys.stderr)
    sys.exit(2)
if not ok:
    print("REFUSED: no loopback ports", file=sys.stderr)
    sys.exit(2)
print("loopback OK:", ", ".join(ok))
PY
}

compose() {
  need_docker
  if [[ "$USE_PROXY" == "1" ]]; then
    (cd "$COMPOSE_DIR" && docker compose --profile proxy "$@")
  else
    (cd "$COMPOSE_DIR" && docker compose "$@")
  fi
}

cmd_up() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --proxy) USE_PROXY=1; shift ;;
      *) break ;;
    esac
  done
  check_loopback
  compose up -d "$@"
  echo "ollama up — http://127.0.0.1:${HOST_PORT}  (OpenAI compat: …/v1)"
  if [[ "$USE_PROXY" == "1" ]]; then
    echo "proxy up — https://127.0.0.1:${LOCAL_LLM_PROXY_HOST_PORT:-8443} (ADR-049 soft edge)"
  fi
}

cmd_down() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --proxy) USE_PROXY=1; shift ;;
      *) break ;;
    esac
  done
  USE_PROXY=1
  compose down "$@"
}
cmd_status() { (cd "$COMPOSE_DIR" && docker compose --profile proxy ps); }
cmd_check() { check_loopback; }

cmd_pull() {
  local model="${1:-llama3.2}"
  # ADR-049: record Fake intent, then soft docker-exec when container is up.
  KERROS_MODEL_PULL=1 python3 - "$model" <<'PY' || true
import json, sys
from adapters.llm.model_pull import ModelPullConfig, ModelPullService
model = sys.argv[1]
svc = ModelPullService(
    cfg=ModelPullConfig(enabled=True, backend="fake", models=[model])
)
print(json.dumps(svc.plan(model), indent=2, sort_keys=True))
PY
  need_docker
  docker exec kerros-ollama ollama pull "$model"
}

cmd_probe() {
  python3 - "$HOST_PORT" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
url = f"http://127.0.0.1:{port}/v1/models"
with urllib.request.urlopen(url, timeout=5) as resp:
    data = json.loads(resp.read().decode())
print(json.dumps(data, indent=2)[:800])
PY
  KERROS_LOCAL_LLM=1 python3 - <<'PY'
import json
from adapters.llm.local_llm_probe import probe_ollama, probe_vllm
print("probe_ollama:", json.dumps(probe_ollama(), indent=2, sort_keys=True))
print("probe_vllm:", json.dumps(probe_vllm(), indent=2, sort_keys=True))
PY
}

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  up [--proxy]  Start Ollama (loopback; --proxy soft Caddy edge)
  down          Stop (includes proxy profile)
  status        compose ps
  check         Loopback port guard
  pull [model]  Fake plan + docker exec ollama pull (default llama3.2)
  probe         GET /v1/models + probe_ollama/probe_vllm
EOF
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    up) cmd_up "$@" ;;
    down) cmd_down "$@" ;;
    status) cmd_status "$@" ;;
    check) cmd_check ;;
    pull) cmd_pull "$@" ;;
    probe) cmd_probe ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
