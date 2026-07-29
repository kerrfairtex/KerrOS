#!/usr/bin/env bash
# OmniRoute loopback deploy helper (README §7 #2).
# Manages deploy/omniroute/docker-compose.yml and probes the gateway.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/omniroute"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
HOST_PORT="${OMNIROUTE_HOST_PORT:-20128}"
ENDPOINT="${OMNIROUTE_ENDPOINT:-http://127.0.0.1:${HOST_PORT}/v1}"

die() { echo "error: $*" >&2; exit 1; }

need_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Engine + Compose on the droplet"
  docker compose version >/dev/null 2>&1 || die "docker compose plugin required"
}

# Fail closed if any published port is not loopback-bound.
check_loopback() {
  [[ -f "$COMPOSE_FILE" ]] || die "missing $COMPOSE_FILE"
  python3 - "$COMPOSE_FILE" <<'PY'
import re, sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
# Match compose port lines like: - "127.0.0.1:20128:20128"
ports = re.findall(r'^\s*-\s*["\']?([^"\'#\n]+)["\']?', text, flags=re.M)
published = []
for raw in ports:
    s = raw.strip()
    # skip non-port mappings (volume-like paths with single colon are rare in ports:)
    if s.count(":") < 1:
        continue
    # host:container or ip:host:container
    parts = s.split(":")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        published.append(s)
    elif len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        published.append(s)

if not published:
    # Fallback: look under a ports: block only
    in_ports = False
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
                published.append(m.group(1).strip())

bad = []
ok = []
for p in published:
    parts = p.split(":")
    if len(parts) == 2 and parts[0].isdigit():
        bad.append(p)  # "20128:20128" binds all interfaces
    elif len(parts) >= 3 and parts[0] in ("127.0.0.1", "localhost", "::1"):
        ok.append(p)
    elif len(parts) >= 3:
        bad.append(p)
    else:
        bad.append(p)

if bad:
    print("REFUSED: non-loopback port publish(es):", ", ".join(bad), file=sys.stderr)
    print("Host mapping must be 127.0.0.1:<port>:<container_port> (README §6).", file=sys.stderr)
    sys.exit(2)
if not ok:
    print("REFUSED: no loopback port mappings found in compose file", file=sys.stderr)
    sys.exit(2)
print("loopback OK:", ", ".join(ok))
PY
}

compose() {
  need_docker
  (cd "$COMPOSE_DIR" && docker compose "$@")
}

cmd_up() {
  check_loopback
  compose up -d
  echo "OmniRoute starting on ${ENDPOINT}"
  echo "Next: $0 probe   then   $0 env"
}

cmd_down() {
  need_docker
  compose down
}

cmd_status() {
  need_docker
  compose ps
}

cmd_probe() {
  local url="${ENDPOINT%/}/models"
  echo "GET ${url}"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 5 "${url}" | head -c 400
    echo
  else
    python3 - "$url" <<'PY'
import sys, urllib.request
url = sys.argv[1]
with urllib.request.urlopen(url, timeout=5) as r:
    print(r.status, r.read()[:400].decode("utf-8", "replace"))
PY
  fi
}

cmd_env() {
  cat <<EOF
# KerrOS ↔ OmniRoute (loopback)
export OMNIROUTE_ENDPOINT=${ENDPOINT}
export KERROS_USE_OMNIROUTE=1
# optional: export KERROS_OMNIROUTE_MODEL=gpt-4o-mini
EOF
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <up|down|status|probe|env|check>

  up       Validate loopback publish, then docker compose up -d
  down     docker compose down
  status   docker compose ps
  probe    GET {endpoint}/models
  env      Print KerrOS environment exports
  check    Static loopback-only port check (no Docker required)

Compose dir: ${COMPOSE_DIR}
Endpoint:    ${ENDPOINT}
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    up) check_loopback; cmd_up ;;
    down) cmd_down ;;
    status) cmd_status ;;
    probe) cmd_probe ;;
    env) cmd_env ;;
    check) check_loopback ;;
    -h|--help|help|"") usage; [[ -n "$cmd" ]] || exit 1 ;;
    *) die "unknown command: $cmd (try --help)" ;;
  esac
}

main "$@"
