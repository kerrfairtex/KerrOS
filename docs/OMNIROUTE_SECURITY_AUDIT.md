# OmniRoute security audit (README §6)

KerrOS-side evidence for the three OmniRoute checklist items. This closes the
items as **documented + statically enforced** in-repo; live promptfoo against a
droplet remains an operator step (script provided).

| §6 item | Status | Evidence |
|---------|--------|----------|
| Never bind beyond `127.0.0.1` without a reverse proxy | Enforced | [`deploy/omniroute/docker-compose.yml`](../deploy/omniroute/docker-compose.yml), [`scripts/omniroute_droplet.sh`](../scripts/omniroute_droplet.sh) `check`, [`tests/unit_deploy/test_omniroute_compose.py`](../tests/unit_deploy/test_omniroute_compose.py) |
| AES-256-GCM key storage matches threat model | Documented + env-wired | § below + [`deploy/omniroute/.env.example`](../deploy/omniroute/.env.example) |
| promptfoo red-team vs **KerrOS** RAG prompts | Fixture + runbook | [`eval/omniroute_rag_promptfoo/`](../eval/omniroute_rag_promptfoo/) |

Static CI guard: `python3 scripts/check_omniroute_security.py`

Operator droplet flow: [`DROPLET_RUNBOOK.md`](DROPLET_RUNBOOK.md) (`scripts/omniroute_droplet.sh verify`).

---

## 1. Bind / reverse proxy

**Policy:** On a public droplet, Docker host publish must be `127.0.0.1:<port>:<container>`. Publishing `0.0.0.0` (or bare `20128:20128`) exposes the dashboard and MITM/TPROXY CA installer.

**Exception:** Non-loopback publish is allowed only behind a TLS reverse proxy with auth (not part of this kit). Document that exception in the droplet runbook before changing compose.

**Verify:**

```bash
scripts/omniroute_droplet.sh check
ss -lntp | grep 20128   # expect 127.0.0.1 only
```

In-container `OMNIROUTE_SERVER_HOST=0.0.0.0` is intentional; isolation is the Docker port mapping.

---

## 2. AES-256-GCM / at-rest secrets (threat model)

OmniRoute encrypts local storage with **AES-256-GCM** when `STORAGE_ENCRYPTION_KEY` is set. Empty key → plaintext passthrough (upstream default).

| Environment | Disk / process assumption | Required action |
|-------------|---------------------------|-----------------|
| **DigitalOcean droplet** (this kit) | Full-disk or volume encryption optional; process memory readable by root | Set `STORAGE_ENCRYPTION_KEY` (32-byte secret, base64 or OmniRoute-documented format) + `JWT_SECRET` / `API_KEY_SECRET`; back up the key offline — loss = unreadable data |
| **Termux / Android** | Weaker at-rest guarantees; shared-user devices | Same env vars, but treat stolen device as key compromise; prefer shorter session secrets and do not sync droplet keys to phone |

**Also set (auth, not storage crypto):** `JWT_SECRET`, `API_KEY_SECRET`.

Do **not** confuse KerrOS root `.env` `ENCRYPTION_KEY` with OmniRoute’s `STORAGE_ENCRYPTION_KEY` — different products.

Generate (example):

```bash
python3 -c 'import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

Put values in `deploy/omniroute/.env` (gitignored), never in git.

---

## 3. promptfoo vs KerrOS RAG injection

OmniRoute’s upstream red-team suite exercises **their** injection surface. KerrOS agents wrap retrieved chunks as:

```text
[Relevant knowledge]:
<chunks>

Question: ...
```

and ground answers with `prompts/system.py` (`SYSTEM_PROMPT`). Poisoned RAG must not override system policy (exfil secrets, disarm scope_gate, ignore instructions).

**Artifacts:**

- Fixtures: `eval/omniroute_rag_promptfoo/fixtures/rag_injected_prompts.json`
- promptfoo stub: `eval/omniroute_rag_promptfoo/promptfooconfig.yaml`
- Run: `scripts/run_omniroute_rag_promptfoo.sh` (requires Node/`npx` + OmniRoute on loopback)

Operator on droplet (after `omniroute_droplet.sh up`):

```bash
export OMNIROUTE_ENDPOINT=http://127.0.0.1:20128/v1
scripts/run_omniroute_rag_promptfoo.sh
```

Optional: also run OmniRoute’s own `promptfoo` suite from their repo — useful, but **not** a substitute for the KerrOS fixtures above.
