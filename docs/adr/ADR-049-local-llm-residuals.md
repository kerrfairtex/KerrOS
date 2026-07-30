# ADR-049: Soft Local LLM Residuals (Auth Proxy / Multi-Node / Model Pull)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-016](ADR-016-local-llm-ops.md) + [ADR-048](ADR-048-vllm-ops-kit.md)
shipped Ollama and soft vLLM ops kits. Remaining C-19 residuals were
explicitly contract-gated: auth/TLS edge proxy, multi-node vLLM, and
automated model pull. Operators requested ADR-047-style soft on-ramps
so funded deploys have CI-safe stubs without claiming production seals.

## Decision

1. **`adapters/llm/local_llm_proxy.py`** — Fake edge plan; soft
   caddy/nginx/openssl probes; `production_tls` / `public_bind_ok`
   stay False without explicit gates + live confirm
2. **`adapters/llm/vllm_multinode.py`** — Fake tensor-parallel / node
   envelopes; `cluster_ready` stays False without live nodes
3. **`adapters/llm/model_pull.py`** — Fake pull intent; soft
   `ollama` / `huggingface-cli` only with `allow_pull`;
   `provisioned_production` stays False
4. Compose profiles **`proxy`** (Caddy templates under
   `deploy/{ollama,vllm}/proxy/`) and **`multi`** (two loopback vLLM
   node stubs) — default-off
5. Config slots `local_llm_proxy` / `vllm_multinode` / `model_pull`
   (default off)

Out of scope: public bind without auth, production CA/ACME for the LLM
edge, Ray/NCCL HA, bundling model weights, silent auto-pull in CI.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Refuse because ADR-048 deferred them | Operator explicitly requested on-ramps |
| Auto-set production_tls / cluster_ready | Compliance / ops risk |
| Require GPU / HF / caddy in CI | Soft Fake backends required |

## Consequences

**Positive:** Funded GPU hosts can flip gates without inventing stubs.

**Negative:** Still not production seals; toolkit + weights + edge certs
remain operator-owned.

## Revisit when

A funded contract turns on public LLM edge TLS, multi-node HA, or
automated weight provisioning for a named deploy.
