#!/usr/bin/env bash
# KerrOS local LLM (vLLM) helper — C-19 / ADR-048 / ADR-049.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/vllm"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
HOST_PORT="${VLLM_HOST_PORT:-8000}"
PROFILES=("vllm")

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
      --cpu) PROFILES+=("cpu"); shift ;;
      --proxy) PROFILES+=("proxy"); shift ;;
      --multi) PROFILES+=("multi"); shift ;;
      --gpu) PROFILES+=("vllm"); shift ;;
      --) shift; break ;;
      *) break ;;
    esac
  done
  if [[ ${#PROFILES[@]} -eq 0 ]]; then
    PROFILES=("vllm")
  fi
  REMAINING=("$@")
}

cmd_up() {
  _parse_profiles "$@"
  check_loopback
  compose up -d "${REMAINING[@]}"
  echo "vllm up (profiles=${PROFILES[*]}) — http://127.0.0.1:${HOST_PORT}/v1"
}

cmd_down() {
  _parse_profiles "$@"
  # Tear down all soft profiles so orphans don't linger.
  PROFILES=("vllm" "cpu" "proxy" "multi")
  compose down "${REMAINING[@]}"
}

cmd_status() {
  need_docker
  (cd "$COMPOSE_DIR" && docker compose --profile vllm --profile cpu --profile proxy --profile multi ps)
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

cmd_pull() {
  local model="${1:-${VLLM_MODEL:-meta-llama/Llama-3.2-3B-Instruct}}"
  KERROS_MODEL_PULL=1 python3 - "$model" <<'PY'
import json, sys
from adapters.llm.model_pull import ModelPullConfig, ModelPullService
model = sys.argv[1]
svc = ModelPullService(
    cfg=ModelPullConfig(enabled=True, backend="fake", models=[model], allow_pull=False)
)
print(json.dumps(svc.pull(model), indent=2, sort_keys=True))
print("note: Fake pull intent only — set KERROS_MODEL_PULL_ALLOW=1 + backend=hf for soft HF", file=sys.stderr)
PY
}

cmd_plan() {
  python3 - <<'PY'
import json
from adapters.llm.local_llm_proxy import LocalLlmProxyConfig, LocalLlmProxyPlanner
from adapters.llm.vllm_multinode import VllmMultinodeConfig, VllmMultinodePlanner
from adapters.llm.model_pull import ModelPullConfig, ModelPullService
print("proxy:", json.dumps(LocalLlmProxyPlanner(cfg=LocalLlmProxyConfig(enabled=True)).plan(), indent=2, sort_keys=True))
print("multi:", json.dumps(VllmMultinodePlanner(cfg=VllmMultinodeConfig(enabled=True)).plan(), indent=2, sort_keys=True))
print("pull:", json.dumps(ModelPullService(cfg=ModelPullConfig(enabled=True)).plan(), indent=2, sort_keys=True))
PY
}

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  up [--cpu|--proxy|--multi]  Start vLLM (default GPU profile)
  down                        Stop (all soft profiles)
  status                      compose ps (all profiles)
  check                       Loopback port guard
  probe                       GET /v1/models + probe_vllm
  pull [model]                Fake/soft model pull intent (ADR-049)
  plan                        Print Fake proxy/multi/pull plans (ADR-049)
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
    pull) cmd_pull "$@" ;;
    plan) cmd_plan ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
