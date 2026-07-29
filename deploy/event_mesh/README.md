# KerrOS Docker event mesh (C-17)

Two-node HTTP event mesh on a private Compose network. Host publishes stay on
`127.0.0.1` (same policy as [`deploy/omniroute/`](../omniroute/)).

**ADRs:** [`ADR-011`](../../docs/adr/ADR-011-docker-event-mesh.md),
[`ADR-014`](../../docs/adr/ADR-014-authenticated-mesh.md)

## Requirements

- Docker Engine + Compose plugin
- Build context is the KerrOS repo root

## Quickstart

```bash
# from repo root
cp deploy/event_mesh/.env.example deploy/event_mesh/.env  # set KERROS_EVENT_MESH_TOKEN
./scripts/event_mesh_docker.sh up
./scripts/event_mesh_docker.sh verify
./scripts/event_mesh_docker.sh down
```

## Endpoints (per node)

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Node id + mesh stats (open) |
| `/mesh/ingest` | POST | Peer delivery — **requires token** when configured |
| `/mesh/publish` | POST | Local publish — **requires token** when configured |

Auth headers (either):

- `Authorization: Bearer <token>`
- `X-Kerros-Mesh-Token: <token>`

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
| `KERROS_EVENT_MESH_TOKEN` | Shared secret (ADR-014); compose default is a lab token |
| `KERROS_EVENT_MESH_AUTH_REQUIRED` | If `1`, refuse start when token empty |

## Security

- Do **not** change host port mappings to `0.0.0.0` / bare `8787:8787` on a
  public host. Loopback publish + private Docker network + shared secret is
  the supported posture.
- Change `KERROS_EVENT_MESH_TOKEN` before any non-lab use. Shared secret is
  not a substitute for TLS on a public edge — put a reverse proxy in front
  for WAN exposure.
