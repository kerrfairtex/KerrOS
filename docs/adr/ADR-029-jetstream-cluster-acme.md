# ADR-029: JetStream Cluster Failover + ACME Cert Watch

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-028 shipped a soft JetStream client, local OTP tree, and PEM mtime
TLS reload. PHASE2 still deferred JetStream *cluster* HA and ACME
automation. Operators need client-side multi-URL failover and a Let's
Encrypt live-dir watcher that drives TLS reload — without running a
Supercluster or hard-requiring certbot.

## Decision

1. **`runtime/nats_jetstream_cluster.py`** — `JetStreamClusterClient`
   with ordered `servers` list + publish failover; in-memory cluster for CI
2. **`runtime/acme_reload.py`** — `AcmeCertWatcher` on
   `live/<domain>/{fullchain,privkey}.pem`; binds `ReloadingTlsHolder`;
   optional soft `certbot renew --dry-run` probe (default off)
3. Config: `actor_mesh.nats.jetstream.cluster` and `actor_mesh.acme`
   (both default off)

Out of scope: NATS Supercluster / leafnode topology management, ACME
account registration / HTTP-01 solvers, production certbot timers.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Embed full NATS server cluster in-repo | Ops weight; Termux unfit |
| Hard-require certbot / acme.sh | Breaks slim CI; probe is enough |
| Replace ADR-028 single-URL client | Keep both; cluster is opt-in |

## Consequences

**Positive:** Publish survives primary outage when a secondary URL works;
ACME renewals can reload mesh TLS without process restart.

**Negative:** Failover is client-side only (not broker HA); ACME watcher
does not issue certs — only watches / optionally probes renew.

## Revisit when

~~Supercluster topology / ACME HTTP-01 solvers~~ — **ADR-030.**
A funded deploy needs Supercluster topology ops, ACME account+DNS-01
automation, or IdP / hardware WORM workstreams.
