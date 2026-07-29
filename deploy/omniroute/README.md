# OmniRoute droplet deploy (loopback)

Reproducible Docker deploy for README §7 #2 and §6 (never bind OmniRoute beyond `127.0.0.1` without a reverse proxy).

This kit does **not** provision DigitalOcean itself — run it on the droplet (or any Linux host with Docker) after the VM exists.

## Prerequisites

- Docker Engine + Compose plugin (`docker compose`)
- Outbound pull access to Docker Hub (`diegosouzapw/omniroute`)

## Quick start

```bash
cd deploy/omniroute
cp .env.example .env   # optional
../../scripts/omniroute_droplet.sh up
../../scripts/omniroute_droplet.sh probe
../../scripts/omniroute_droplet.sh env
```

Default endpoint for KerrOS:

```text
http://127.0.0.1:20128/v1
```

Wire KerrOS (same shell or `config.json`):

```bash
export OMNIROUTE_ENDPOINT=http://127.0.0.1:20128/v1
export KERROS_USE_OMNIROUTE=1
python3 cli/chat.py
# then /health — expect components.omniroute status=ok when enabled
```

## Script commands

| Command | Action |
|---------|--------|
| `up` | Validate loopback ports, then `docker compose up -d` |
| `down` | Stop and remove the stack |
| `status` | `docker compose ps` |
| `probe` | `GET /v1/models` on the loopback endpoint |
| `env` | Print KerrOS env exports |
| `check` | Static check that compose publishes only `127.0.0.1` |

## Security notes

Full checklist: [`docs/OMNIROUTE_SECURITY_AUDIT.md`](../../docs/OMNIROUTE_SECURITY_AUDIT.md).

- Host publish is `127.0.0.1:20128` only. Changing compose to `20128:20128` exposes the dashboard/API on all interfaces — forbidden without a TLS reverse proxy in front (§6).
- Inside the container OmniRoute binds `0.0.0.0` (`OMNIROUTE_SERVER_HOST`); isolation is the Docker port mapping, not the in-container bind.
- Set `STORAGE_ENCRYPTION_KEY` (AES-256-GCM), `JWT_SECRET`, and `API_KEY_SECRET` in `.env` before production use — empty storage key means plaintext.
- Keep OmniRoute memory separate from KerrOS RAG — [`docs/MEMORY_SEPARATION.md`](../../docs/MEMORY_SEPARATION.md) (P5).
- Prefer a pinned image tag (`3.8.49`) over `latest` on production droplets.
- After gateway is up: `scripts/run_omniroute_rag_promptfoo.sh` (KerrOS RAG injection eval).

## Droplet checklist

1. Create/re-provision DigitalOcean droplet (Ubuntu LTS, Docker installed).
2. Clone KerrOS; copy `.env.example` → `.env` and set encryption/auth secrets.
3. Run this kit on the droplet (`omniroute_droplet.sh up`).
4. Confirm `ss -lntp | grep 20128` shows `127.0.0.1` only.
5. Point KerrOS `OMNIROUTE_ENDPOINT` / `omniroute_url` at loopback `/v1`.
6. `/health` or `python3 -m runtime.kerrd health` shows `omniroute` ok when enabled.
7. Run `scripts/check_omniroute_security.py` and (optional) RAG promptfoo eval.
