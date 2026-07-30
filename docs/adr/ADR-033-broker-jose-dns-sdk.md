# ADR-033: Broker Lifecycle + ACME JOSE + Cloud DNS SDK Facades

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-032 shipped a Supercluster control-plane and soft ACME newAccount /
webhook DNS bridges. Remaining mesh deferred work was broker *process*
lifecycle, full ACME JOSE/order helpers, and native cloud DNS SDK
facades — without hard-requiring `nats-server`, `cryptography`, or
`boto3` in CI.

## Decision

1. **`runtime/nats_broker_lifecycle.py`** — start/stop/status for
   `nats-server` via memory backend (CI) or soft subprocess when
   `allow_spawn`
2. **`runtime/acme_jose.py`** — base64url JWS flattened builder,
   `FakeJoseSigner` / soft ES256 via cryptography, soft `newOrder` client
3. **`runtime/acme_cloud_dns_sdk.py`** — soft Route53 (boto3) +
   Cloudflare HTTP facades with dry-run shadow records
4. Config: `actor_mesh.supercluster.broker`, `actor_mesh.acme.jose`,
   `actor_mesh.acme.dns01.sdk` (all default off)

Out of scope: multi-broker orchestration fleet, complete ACME issuance
against production LE, mandatory cloud credentials, hardware WORM / IdP
(ADR-034).

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Always spawn nats-server in tests | Breaks slim CI / Termux |
| Hard-require josepy / acme | Dep weight; FakeJoseSigner enough for plumbing |
| Require boto3 always | Soft import + dry-run shadow is enough |

## Consequences

**Positive:** Operators can manage a broker process, exercise JWS order
intents, and dry-run Route53/Cloudflare DNS-01 without credentials.

**Negative:** Live LE issuance still needs a full ACME client; live DNS
SDK calls remain opt-in.

## Revisit when

~~Multi-broker fleets / ACME issuance~~ — **ADR-035.**
A funded deploy needs remote fleet orchestration or packaged production
ACME automation against Let's Encrypt.
