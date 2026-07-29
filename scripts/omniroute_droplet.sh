#!/usr/bin/env bash
# OmniRoute loopback deploy helper (README §7 #2 / docs/DROPLET_RUNBOOK.md).
# Manages deploy/omniroute/docker-compose.yml and probes the gateway.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/omniroute"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
ENV_FILE="${COMPOSE_DIR}/.env"
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
ports = re.findall(r'^\s*-\s*["\']?([^"\'#\n]+)["\']?', text, flags=re.M)
published = []
for raw in ports:
    s = raw.strip()
    if s.count(":") < 1:
        continue
    parts = s.split(":")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        published.append(s)
    elif len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        published.append(s)

if not published:
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
        bad.append(p)
    elif len(parts) >= 3 and parts[0] in ("127.0.0.1", "localhost", "::1"):
        ok.append(p)
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
  echo "Next: $0 probe   then   $0 doctor / verify"
  echo "Runbook: docs/DROPLET_RUNBOOK.md"
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
# KerrOS ↔ OmniRoute (loopback) — docs/DROPLET_RUNBOOK.md
export OMNIROUTE_ENDPOINT=${ENDPOINT}
export KERROS_USE_OMNIROUTE=1
# optional: export KERROS_OMNIROUTE_MODEL=gpt-4o-mini
# optional: export KERROS_OMNIROUTE_API_KEY=...
EOF
}

check_secrets_env() {
  python3 - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
required = ("STORAGE_ENCRYPTION_KEY", "JWT_SECRET", "API_KEY_SECRET")
if not path.is_file():
    print(f"WARN: missing {path} — copy .env.example and set secrets (prod)")
    sys.exit(0)

vals = {}
for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    vals[k.strip()] = v.strip().strip("'").strip('"')

missing = [k for k in required if not vals.get(k)]
if missing:
    print("FAIL: empty/missing secrets in .env:", ", ".join(missing))
    print("See docs/DROPLET_RUNBOOK.md §3")
    sys.exit(2)
print("secrets OK:", ", ".join(required))
PY
}

check_host_listen() {
  if ! command -v ss >/dev/null 2>&1; then
    echo "WARN: ss not found — skip host listen check"
    return 0
  fi
  local lines
  lines="$(ss -lntp 2>/dev/null | grep -E ":${HOST_PORT}\\b" || true)"
  if [[ -z "$lines" ]]; then
    echo "WARN: nothing listening on :${HOST_PORT} yet (is the container up?)"
    return 0
  fi
  if echo "$lines" | grep -E "0\\.0\\.0\\.0:${HOST_PORT}|\\*:${HOST_PORT}|:::${HOST_PORT}" >/dev/null; then
    echo "FAIL: port ${HOST_PORT} appears bound on all interfaces:" >&2
    echo "$lines" >&2
    exit 2
  fi
  if echo "$lines" | grep -E "127\\.0\\.0\\.1:${HOST_PORT}|\\[::1\\]:${HOST_PORT}" >/dev/null; then
    echo "listen OK (loopback):"
    echo "$lines"
    return 0
  fi
  echo "WARN: unexpected listen lines for :${HOST_PORT}:"
  echo "$lines"
}

cmd_doctor() {
  echo "== droplet doctor (docs/DROPLET_RUNBOOK.md) =="
  check_loopback
  if [[ -f "$ENV_FILE" ]]; then
    check_secrets_env
  else
    echo "WARN: no deploy/omniroute/.env yet — cp .env.example .env and set secrets"
  fi
  if command -v docker >/dev/null 2>&1; then
    compose ps || true
  else
    echo "WARN: docker not installed on this host"
  fi
  check_host_listen || true
  echo "doctor done — run '$0 verify' for fail-closed acceptance"
}

cmd_verify() {
  echo "== droplet verify (fail-closed) =="
  check_loopback
  [[ -f "$ENV_FILE" ]] || die "missing ${ENV_FILE} — copy .env.example and set secrets"
  check_secrets_env
  need_docker
  cmd_probe >/dev/null
  echo "probe OK: ${ENDPOINT%/}/models"
  check_host_listen
  # Static repo guards (always available without OmniRoute process if scripts exist)
  python3 "${ROOT}/scripts/check_omniroute_security.py"
  python3 "${ROOT}/scripts/check_memory_separation.py"
  echo "VERIFY OK — OmniRoute loopback deploy meets DROPLET_RUNBOOK acceptance"
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <up|down|status|probe|env|check|doctor|verify>

  up       Validate loopback publish, then docker compose up -d
  down     docker compose down
  status   docker compose ps
  probe    GET {endpoint}/models
  env      Print KerrOS environment exports
  check    Static loopback-only port check (no Docker required)
  doctor   Host checklist (warnings allowed)
  verify   Fail-closed acceptance (secrets + probe + loopback + static guards)

Compose dir: ${COMPOSE_DIR}
Endpoint:    ${ENDPOINT}
Runbook:     ${ROOT}/docs/DROPLET_RUNBOOK.md
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
    doctor) cmd_doctor ;;
    verify) cmd_verify ;;
    -h|--help|help|"") usage; [[ -n "$cmd" ]] || exit 1 ;;
    *) die "unknown command: $cmd (try --help)" ;;
  esac
}

main "$@"
