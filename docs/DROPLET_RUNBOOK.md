# DigitalOcean droplet runbook — OmniRoute + KerrOS

Operator guide for README §7 #2: **re-provision a droplet and run OmniRoute
loopback-only**, then wire KerrOS to `http://127.0.0.1:20128/v1`.

This document does **not** create the droplet for you (needs your DO account).
It is the checklist to run **on** the droplet after the VM exists.

Related:

- Deploy kit: [`deploy/omniroute/`](../deploy/omniroute/)
- Helper: [`scripts/omniroute_droplet.sh`](../scripts/omniroute_droplet.sh)
- Security: [`OMNIROUTE_SECURITY_AUDIT.md`](OMNIROUTE_SECURITY_AUDIT.md)
- Memory boundary: [`MEMORY_SEPARATION.md`](MEMORY_SEPARATION.md)

---

## 0. Target shape

| Item | Value |
|------|-------|
| Host OS | Ubuntu LTS |
| OmniRoute image | pinned `diegosouzapw/omniroute:3.8.49` (see compose) |
| Host bind | `127.0.0.1:20128` **only** |
| KerrOS endpoint | `OMNIROUTE_ENDPOINT=http://127.0.0.1:20128/v1` |
| OmniRoute data | Docker volume `kerros-omniroute-data` → `/app/data` (not KerrOS `data/`) |

---

## 1. Re-provision the droplet (DigitalOcean console / `doctl`)

1. Create or rebuild an Ubuntu LTS droplet (1 vCPU / 1–2 GB is enough for the gateway; size up if you co-host KerrOS + models).
2. Prefer a **new** droplet over in-place upgrade when rotating secrets or changing bind policy.
3. Attach a firewall: allow SSH from your IP only; **do not** open `20128` publicly.
4. SSH in as a sudo-capable user.

Optional `doctl` sketch (adjust size/region/SSH key):

```bash
doctl compute droplet create kerros-omniroute \
  --image ubuntu-24-04-x64 \
  --size s-1vcpu-2gb \
  --region nyc3 \
  --ssh-keys <KEY_ID>
```

---

## 2. Install Docker on the droplet

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# log out/in so docker group applies
docker compose version
```

---

## 3. Clone KerrOS and configure OmniRoute secrets

```bash
git clone https://github.com/kerrfairtex/KerrOS.git
cd KerrOS
ln -sfn "$PWD" "$HOME/offline_ai"   # KerrOS path assumption

cd deploy/omniroute
cp .env.example .env
```

Edit `.env` **before** first production `up`:

| Variable | Required | Notes |
|----------|----------|-------|
| `STORAGE_ENCRYPTION_KEY` | yes (prod) | AES-256-GCM; empty = plaintext — back up offline |
| `JWT_SECRET` | yes (prod) | Auth |
| `API_KEY_SECRET` | yes (prod) | Auth |
| `OMNIROUTE_IMAGE` | optional | Keep pinned tag; avoid `latest` on prod |
| `OMNIROUTE_HOST_PORT` | optional | Default `20128` |

Generate a storage key:

```bash
python3 -c 'import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

---

## 4. Start OmniRoute (loopback)

From repo root:

```bash
scripts/omniroute_droplet.sh check    # compose must publish 127.0.0.1 only
scripts/omniroute_droplet.sh up
scripts/omniroute_droplet.sh probe    # GET /v1/models
scripts/omniroute_droplet.sh doctor   # host-side checklist (ss, env, secrets present)
```

Expect:

```bash
ss -lntp | grep 20128
# something like: 127.0.0.1:20128 ...
# NOT 0.0.0.0:20128
```

---

## 5. Wire KerrOS on the same host

```bash
eval "$(scripts/omniroute_droplet.sh env)"
# or:
# export OMNIROUTE_ENDPOINT=http://127.0.0.1:20128/v1
# export KERROS_USE_OMNIROUTE=1

python3 -m pip install -r requirements.txt --user
python3 cli/chat.py
```

In chat:

- `/health` — `omniroute` should be `ok` when enabled and up
- `/llm` — provider + resilience status
- `/events` — after a completion, look for `omniroute.usage`

Or without the REPL:

```bash
python3 -m runtime.kerrd health
```

---

## 6. Post-deploy verification (acceptance)

Run from repo root on the droplet:

```bash
scripts/omniroute_droplet.sh verify
```

`verify` fails closed unless:

1. Compose loopback check passes  
2. `.env` documents/sets encryption + auth secret keys (non-empty in `.env` when present)  
3. `GET {endpoint}/models` succeeds  
4. Host listen address for the port is loopback-only (when `ss` is available)  
5. Static security + memory-separation scripts pass  

Optional RAG red-team (needs Node/`npx`):

```bash
scripts/run_omniroute_rag_promptfoo.sh
```

---

## 7. Re-provision / rotate (destructive)

When rebuilding:

1. `scripts/omniroute_droplet.sh down`
2. Back up or destroy volume `kerros-omniroute-data` only if you intend to wipe OmniRoute state (**not** KerrOS `data/rag_store.db`)
3. Rotate `STORAGE_ENCRYPTION_KEY` / JWT / API secrets in `.env` (old ciphertext unreadable if key changes)
4. Rebuild droplet or re-run §2–§6 on the new host
5. Never copy OmniRoute volume data into KerrOS RAG paths ([`MEMORY_SEPARATION.md`](MEMORY_SEPARATION.md))

---

## 8. Troubleshooting

| Symptom | Check |
|---------|--------|
| `probe` connection refused | `status`; wait for healthcheck; `docker logs kerros-omniroute` |
| `/health` omniroute unavailable while enabled | endpoint URL includes `/v1`; firewall not needed for loopback |
| Port on `0.0.0.0` | restore compose to `127.0.0.1:…`; `check` must pass before `up` |
| Empty models / auth errors | set `API_KEY_SECRET` / gateway key; pass `KERROS_OMNIROUTE_API_KEY` if required |
| Confused AES vs KerrOS `ENCRYPTION_KEY` | OmniRoute uses `STORAGE_ENCRYPTION_KEY` only |

---

## 9. Done criteria (closes README §7 #2)

- [ ] Droplet exists; SSH works; Docker Compose available  
- [ ] OmniRoute up on **loopback only**  
- [ ] Secrets set for prod; keys backed up offline  
- [ ] KerrOS points at `OMNIROUTE_ENDPOINT` and `/health` shows omniroute ok when enabled  
- [ ] `scripts/omniroute_droplet.sh verify` exits 0  
