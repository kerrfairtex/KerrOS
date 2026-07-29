# KerrOS Docker event mesh (C-17)

Two-node HTTP event mesh on a private Compose network. Host publishes stay on
`127.0.0.1` (same policy as [`deploy/omniroute/`](../omniroute/)).

**ADR:** [`docs/adr/ADR-011-docker-event-mesh.md`](../../docs/adr/ADR-011-docker-event-mesh.md)

## Requirements

- Docker Engine + Compose plugin
- Build context is the KerrOS repo root

## Quickstart

```bash
# from repo root
./scripts/event_mesh_docker.sh up
./scripts/event_mesh_docker.sh verify
./scripts/event_mesh_docker.sh down
```

## Endpoints (per node)

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Node id + mesh stats |
| `/mesh/ingest` | POST | Peer delivery `{"origin_node","event"}` |
| `/mesh/publish` | POST | Local publish `{"topic","payload"}` (forwards to peers) |

Host smoke URLs (loopback):

- node-a: `http://127.0.0.1:8787`
- node-b: `http://127.0.0.1:8788`

## Config (env)

| Variable | Meaning |
|----------|---------|
| `KERROS_NODE_ID` | Mesh node identity |
| `KERROS_EVENT_MESH=1` | Enable mesh |
| `KERROS_EVENT_MESH_TRANSPORT=http` | Use HTTP transport |
| `KERROS_EVENT_MESH_LISTEN` | Bind address (`0.0.0.0:8787`) |
| `KERROS_EVENT_MESH_HTTP_PEERS` | Comma-separated peer ingest URLs |

## Security

- Do **not** change host port mappings to `0.0.0.0` / bare `8787:8787` on a
  public host — mesh ingest has no auth. Loopback publish + private Docker
  network is the supported posture.
- This is a foundation kit, not a WAN mesh. Prefer a reverse proxy + auth
  before exposing beyond the host.
