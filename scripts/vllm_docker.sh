#!/usr/bin/env bash
# KerrOS local LLM (vLLM) helper — C-19 / ADR-048.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/vllm"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
HOST_PORT="${VLLM_HOST_PORT:-8000}"
PROFILE="vllm"

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
  (cd "$COMPOSE_DIR" && docker compose --profile "$PROFILE" "$@")
}

cmd_up() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --cpu) PROFILE="cpu"; shift ;;
      --gpu|--) shift; break ;;
      *) break ;;
    esac
  done
  check_loopback
  compose up -d "$@"
  echo "vllm up (profile=${PROFILE}) — http://127.0.0.1:${HOST_PORT}/v1"
}

cmd_down() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --cpu) PROFILE="cpu"; shift ;;
      *) break ;;
    esac
  done
  compose down "$@"
}

cmd_status() {
  need_docker
  (cd "$COMPOSE_DIR" && docker compose --profile vllm --profile cpu ps)
}

cmd_check() { check_loopback; }

cmd_probe() {
  python3 - "$HOST_PORT" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
url = f"http://127.0.0.1:{port}/v1/models"
with urllib.request.urlopen(url, timeout=5) as resp:
    data = json.loads(resp.read().decode())
print(json.dumps(data, indent=2)[:800])
PY
  KERROS_LOCAL_LLM=1 KERROS_VLLM_ENABLED=1 python3 - <<'PY'
import json
from adapters.llm.local_llm_probe import probe_vllm
print("probe_vllm:", json.dumps(probe_vllm(), indent=2, sort_keys=True))
PY
}

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  up [--cpu]   Start vLLM (default GPU profile; --cpu experimental)
  down [--cpu] Stop
  status       compose ps (both profiles)
  check        Loopback port guard
  probe        GET /v1/models + probe_vllm
EOF
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    up) cmd_up "$@" ;;
    down) cmd_down "$@" ;;
    status) cmd_status ;;
    check) cmd_check ;;
    probe) cmd_probe ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
