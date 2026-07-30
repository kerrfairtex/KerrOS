#!/usr/bin/env bash
# KerrOS offline llama.cpp + LiteLLM helper — Phase E / ADR-054.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/llama_cpp"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
LLAMA_PORT="${LLAMA_CPP_HOST_PORT:-8080}"
LITELLM_PORT="${LITELLM_HOST_PORT:-4000}"
PROFILES=("llama_cpp")

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
  local args=()
  local p
  for p in "${PROFILES[@]}"; do
    args+=(--profile "$p")
  done
  (cd "$COMPOSE_DIR" && docker compose "${args[@]}" "$@")
}

_parse_profiles() {
  PROFILES=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --litellm|--gateway) PROFILES+=("litellm"); shift ;;
      --proxy) PROFILES+=("proxy"); shift ;;
      --llama|--llama-cpp) PROFILES+=("llama_cpp"); shift ;;
      --) shift; break ;;
      *) break ;;
    esac
  done
  if [[ ${#PROFILES[@]} -eq 0 ]]; then
    PROFILES=("llama_cpp")
  fi
  REMAINING=("$@")
}

cmd_up() {
  _parse_profiles "$@"
  check_loopback
  compose up -d "${REMAINING[@]}"
  echo "llama.cpp up (profiles=${PROFILES[*]}) — http://127.0.0.1:${LLAMA_PORT}/v1"
  if [[ " ${PROFILES[*]} " == *" litellm "* ]]; then
    echo "litellm up — http://127.0.0.1:${LITELLM_PORT}/v1"
  fi
}

cmd_down() {
  PROFILES=("llama_cpp" "litellm" "proxy")
  compose down "$@"
}

cmd_status() {
  need_docker
  (cd "$COMPOSE_DIR" && docker compose --profile llama_cpp --profile litellm --profile proxy ps)
}

cmd_check() { check_loopback; }

cmd_probe() {
  python3 - "$LLAMA_PORT" "$LITELLM_PORT" <<'PY'
import json, sys, urllib.request
llama_port, litellm_port = sys.argv[1], sys.argv[2]
for name, port in (("llama_cpp", llama_port), ("litellm", litellm_port)):
    url = f"http://127.0.0.1:{port}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        print(f"{name}:", json.dumps(data, indent=2)[:500])
    except Exception as exc:
        print(f"{name}: unreachable ({exc})", file=sys.stderr)
PY
  KERROS_LOCAL_LLM=1 KERROS_LLAMA_CPP_ENABLED=1 python3 - <<'PY'
import json
from adapters.llm.local_llm_probe import probe_llama_cpp, probe_litellm
print("probe_llama_cpp:", json.dumps(probe_llama_cpp(), indent=2, sort_keys=True))
print("probe_litellm:", json.dumps(probe_litellm(), indent=2, sort_keys=True))
PY
}

cmd_plan() {
  python3 - <<'PY'
import json
from adapters.llm.offline_gateway import OfflineGatewayConfig, OfflineGatewayPlanner
print(json.dumps(OfflineGatewayPlanner(cfg=OfflineGatewayConfig(enabled=True)).plan(), indent=2, sort_keys=True))
PY
}

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  up [--litellm|--proxy]  Start llama.cpp (add LiteLLM gateway / soft proxy)
  down                    Stop (all soft profiles)
  status                  compose ps
  check                   Loopback port guard
  probe                   GET /v1/models + probes
  plan                    Fake gateway plan (ADR-054; no Docker)
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
    plan) cmd_plan ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
