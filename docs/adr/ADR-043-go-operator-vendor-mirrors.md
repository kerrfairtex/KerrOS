# ADR-043: Go Operator Binaries + Certified Vendor Partnerships + Remote Mirrors

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-042 shipped Python controller-runtime facades, soft vendor SDKs, and
local apt/yum staging. Remaining mesh packaging residuals were Go
operator binary packaging, certified vendor partnership evidence, and
remote apt/yum mirror push — without shipping production binaries or
claiming real vendor certifications in CI.

## Decision

1. **`runtime/k8s_go_operator.py`** + **`deploy/k8s/operator/go/`** —
   render `main.go` / `go.mod` / Dockerfile / Makefile; Fake build
   artifact; soft `go build` / `docker build` when gated
2. **`runtime/cmdb_vendor_cert.py`** — partnership program registry +
   foundation evidence envelopes; Fake / soft HTTP probe; `certified`
   always False unless a future contract flips it explicitly
3. **`runtime/distro_remote_mirror.py`** — Fake remote push; soft
   rsync / HTTP PUT when `allow_remote`
4. Config: `supercluster.go_operator`, `supercluster.vendor_cert`,
   `actor_mesh.remote_mirror` (default off)

Out of scope: publishing operator images to public registries, real
vendor-issued certificates, unattended pushes to public apt/yum mirrors.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Require Go/Docker in CI | Breaks default checkout |
| Auto-claim vendor certification from probe | Misleading |
| Skip — declare arc complete | Explicit residual from ADR-042 |

## Consequences

**Positive:** Go stubs, partnership evidence, and remote push intents
are CI-testable with Fake backends.

**Negative:** Not a shipped Go binary, vendor certificate, or public
mirror; live tools remain opt-in.

## Revisit when

~~Mesh / LGU foundation arc complete~~ — **ADR-046.**
A funded contract specifies shipped Go/Helm images, vendor-issued
partnership certificates, or public apt/yum mirror publish.
