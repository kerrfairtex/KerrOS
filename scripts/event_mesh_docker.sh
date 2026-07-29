#!/usr/bin/env bash
# KerrOS Docker event-mesh helper (C-17 / ADR-011).
# Manages deploy/event_mesh/docker-compose.yml and probes the two nodes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/event_mesh"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
PORT_A="${MESH_HOST_PORT_A:-8787}"
PORT_B="${MESH_HOST_PORT_B:-8788}"
MESH_TOKEN="${KERROS_EVENT_MESH_TOKEN:-kerros-mesh-dev-token}"

die() { echo "error: $*" >&2; exit 1; }

need_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Engine + Compose"
  docker compose version >/dev/null 2>&1 || die "docker compose plugin required"
}

# Fail closed if any published port is not loopback-bound.
check_loopback() {
  [[ -f "$COMPOSE_FILE" ]] || die "missing $COMPOSE_FILE"
  python3 - "$COMPOSE_FILE" <<'PY'
import re, sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
ports = []
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
  compose up -d --build "$@"
  echo "mesh up — node-a http://127.0.0.1:${PORT_A}  node-b http://127.0.0.1:${PORT_B}"
}

cmd_down() {
  compose down "$@"
}

cmd_status() {
  compose ps
}

cmd_check() {
  check_loopback
}

cmd_probe() {
  local port="${1:-$PORT_A}"
  python3 - "$port" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
url = f"http://127.0.0.1:{port}/health"
with urllib.request.urlopen(url, timeout=3) as resp:
    data = json.loads(resp.read().decode())
print(json.dumps(data, indent=2, sort_keys=True))
if not data.get("ok"):
    raise SystemExit(1)
PY
}

cmd_verify() {
  check_loopback
  need_docker
  # Wait for health on both host ports; publish with shared mesh token (ADR-014).
  python3 - "$PORT_A" "$PORT_B" "$MESH_TOKEN" <<'PY'
import json, sys, time, urllib.error, urllib.request

ports = [sys.argv[1], sys.argv[2]]
token = sys.argv[3]
deadline = time.time() + 60
for port in ports:
    url = f"http://127.0.0.1:{port}/health"
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = json.loads(resp.read().decode())
            if data.get("ok"):
                print(f"health OK :{port} node_id={data.get('node_id')} auth={data.get('auth')}")
                break
        except Exception as exc:
            if time.time() > deadline:
                print(f"TIMEOUT waiting for {url}: {exc}", file=sys.stderr)
                raise SystemExit(1)
            time.sleep(1)

# Reject unauthenticated publish when token is configured.
bad = urllib.request.Request(
    f"http://127.0.0.1:{ports[0]}/mesh/publish",
    data=json.dumps({"topic": "mesh.verify.deny", "payload": {}}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    urllib.request.urlopen(bad, timeout=3)
    print("FAIL: unauthenticated publish succeeded", file=sys.stderr)
    raise SystemExit(1)
except urllib.error.HTTPError as exc:
    if exc.code != 401:
        print(f"FAIL: expected 401, got {exc.code}", file=sys.stderr)
        raise SystemExit(1)
    print("auth reject OK (401 without token)")

topic = "mesh.verify.ping"
payload = json.dumps({"topic": topic, "payload": {"from": "verify"}}).encode()
req = urllib.request.Request(
    f"http://127.0.0.1:{ports[0]}/mesh/publish",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Kerros-Mesh-Token": token,
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=5) as resp:
    pub = json.loads(resp.read().decode())
print("published on node-a:", pub)

time.sleep(0.5)
with urllib.request.urlopen(f"http://127.0.0.1:{ports[1]}/health", timeout=3) as resp:
    health_b = json.loads(resp.read().decode())
stats = health_b.get("stats") or {}
ingested = int(stats.get("ingested") or 0)
if ingested < 1:
    print("FAIL: node-b ingested=0 after publish from node-a", file=sys.stderr)
    print(json.dumps(health_b, indent=2), file=sys.stderr)
    raise SystemExit(1)
print(f"VERIFY OK — node-b ingested={ingested}")
PY
}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  up        Build/start node-a + node-b (loopback check first)
  down      Stop and remove containers
  status    docker compose ps
  check     Static loopback port guard
  probe [port]  GET /health on loopback port (default ${PORT_A})
  verify    Health both nodes + publish A→B ingest smoke
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
    probe) cmd_probe "$@" ;;
    verify) cmd_verify ;;
    -h|--help|help|"") usage ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
