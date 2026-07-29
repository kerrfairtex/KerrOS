#!/usr/bin/env bash
# KerrOS Qdrant sidecar helper (C-18 / ADR-015).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/qdrant"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
HOST_PORT="${QDRANT_HOST_PORT:-6333}"

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
    print("REFUSED: non-loopback port publish(es):", ", ".join(bad), file=sys.stderr)
    sys.exit(2)
if not ok:
    print("REFUSED: no loopback port mappings found", file=sys.stderr)
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
  compose up -d "$@"
  echo "qdrant up — http://127.0.0.1:${HOST_PORT}"
}

cmd_down() { compose down "$@"; }
cmd_status() { compose ps; }
cmd_check() { check_loopback; }

cmd_probe() {
  python3 - "$HOST_PORT" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
url = f"http://127.0.0.1:{port}/readyz"
try:
    with urllib.request.urlopen(url, timeout=3) as resp:
        body = resp.read().decode()
        print(f"readyz HTTP {resp.status}: {body[:200]!r}")
except Exception:
    # older images
    url = f"http://127.0.0.1:{port}/collections"
    with urllib.request.urlopen(url, timeout=3) as resp:
        data = json.loads(resp.read().decode())
        print(json.dumps(data, indent=2)[:500])
PY
  python3 - <<'PY'
from adapters.memory.qdrant_vector_store import probe_qdrant
import json
print(json.dumps(probe_qdrant(), indent=2, sort_keys=True))
PY
}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  up      Start Qdrant (loopback check first)
  down    Stop containers
  status  docker compose ps
  check   Static loopback port guard
  probe   GET /readyz + probe_qdrant()
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
    probe) cmd_probe ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
