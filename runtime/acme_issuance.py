"""
runtime/acme_issuance.py
========================
Production-shaped ACME *issuance* pipeline foundation (ADR-035).

Default-off. Fake end-to-end path: newOrder → challenge → finalize →
cert PEM stub. Live mode remains soft (records intent; does not speak
full ACME to Let's Encrypt without an external client).
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from runtime.acme_account import _truthy
from runtime.acme_jose import (
    AcmeJoseConfig,
    AcmeOrderClient,
    FakeJoseSigner,
    JoseSigner,
    build_acme_order_client,
    build_signer,
)
from runtime.acme_new_account import FakeAcmeDirectoryTransport


class AcmeIssuanceError(RuntimeError):
    """ACME issuance pipeline failed."""


@runtime_checkable
class ChallengeSolver(Protocol):
    def put_challenge(self, token_or_domain: str, key_authorization: str) -> Any: ...

    def clear_challenge(self, token_or_domain: str) -> None: ...


@dataclass
class FakeChallengeSolver:
    """In-memory challenge sink for CI."""

    kind: str = "dns-01"
    _items: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def put_challenge(self, token_or_domain: str, key_authorization: str) -> dict[str, str]:
        with self._lock:
            self._items[str(token_or_domain)] = str(key_authorization)
        return {"name": str(token_or_domain), "value": str(key_authorization)}

    def clear_challenge(self, token_or_domain: str) -> None:
        with self._lock:
            self._items.pop(str(token_or_domain), None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"kind": self.kind, "active": len(self._items)}


@dataclass
class AcmeIssuanceConfig:
    enabled: bool = False
    allow_live: bool = False
    challenge: str = "dns-01"  # dns-01 | http-01
    allow_crypto: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeIssuanceConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_ISSUANCE")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_ISSUANCE_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        challenge = os.environ.get("KERROS_ACTOR_MESH_ACME_ISSUANCE_CHALLENGE")
        if challenge is None:
            challenge = str(data.get("challenge") or "dns-01")

        allow_crypto = data.get("allow_crypto", False)
        env_c = os.environ.get("KERROS_ACTOR_MESH_ACME_ISSUANCE_CRYPTO")
        if env_c is not None:
            allow_crypto = _truthy(env_c)
        else:
            allow_crypto = _truthy(allow_crypto)

        return cls(
            enabled=bool(enabled),
            allow_live=bool(allow_live),
            challenge=str(challenge or "dns-01").strip().lower() or "dns-01",
            allow_crypto=bool(allow_crypto),
        )


@dataclass
class AcmeIssuanceClient:
    """Fake/soft certificate issuance orchestrator."""

    cfg: AcmeIssuanceConfig
    order_client: AcmeOrderClient
    solver: ChallengeSolver = field(default_factory=FakeChallengeSolver)
    _certs: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def issue(self, domains: list[str]) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AcmeIssuanceError("ACME issuance disabled")
        names = [str(d).strip() for d in domains if str(d).strip()]
        if not names:
            raise AcmeIssuanceError("at least one domain required")

        if self.cfg.allow_live:
            # Soft: full LE issuance still requires external ACME client.
            out = {
                "ok": False,
                "skipped_live": True,
                "error": "live issuance requires external ACME client; use fake path",
                "domains": names,
            }
            with self._lock:
                self._certs.append(dict(out))
            return out

        order = self.order_client.create_order(names)
        if not order.get("ok"):
            return {"ok": False, "error": "order failed", "order": order}

        challenges: list[dict[str, Any]] = []
        for domain in names:
            token = f"tok-{uuid.uuid4().hex[:10]}"
            key_auth = f"{token}.fake-thumbprint"
            put = self.solver.put_challenge(
                domain if self.cfg.challenge.startswith("dns") else token,
                key_auth,
            )
            challenges.append(
                {
                    "domain": domain,
                    "type": self.cfg.challenge,
                    "token": token,
                    "key_authorization": key_auth,
                    "solver": put,
                    "status": "valid",
                }
            )

        # Fake finalize → cert PEM stub (not a real X.509).
        cert_id = uuid.uuid4().hex[:12]
        pem = (
            "-----BEGIN CERTIFICATE-----\n"
            f"KERROS-FAKE-CERT-{cert_id}\n"
            "-----END CERTIFICATE-----\n"
        )
        result = {
            "ok": True,
            "status": "valid",
            "domains": names,
            "order": order,
            "challenges": challenges,
            "certificate_pem": pem,
            "cert_id": cert_id,
            "issued_at": time.time(),
            "fake": True,
        }
        for ch in challenges:
            try:
                target = (
                    ch["domain"]
                    if self.cfg.challenge.startswith("dns")
                    else ch["token"]
                )
                self.solver.clear_challenge(target)
            except Exception:
                pass
        with self._lock:
            self._certs.append({k: v for k, v in result.items() if k != "certificate_pem"})
        return result

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "allow_live": self.cfg.allow_live,
                "challenge": self.cfg.challenge,
                "issued": len(self._certs),
                "order_client": self.order_client.stats(),
                "solver": self.solver.stats() if hasattr(self.solver, "stats") else {},
            }


def build_acme_issuance_client(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    order_client: AcmeOrderClient | None = None,
    solver: ChallengeSolver | None = None,
    directory_url: str = "",
    signer: JoseSigner | None = None,
) -> AcmeIssuanceClient | None:
    iss_cfg = AcmeIssuanceConfig.from_mapping(cfg)
    if not iss_cfg.enabled:
        return None
    jose_raw = {
        "enabled": True,
        "allow_crypto": iss_cfg.allow_crypto,
        "allow_live": False,
    }
    orders = order_client or build_acme_order_client(
        jose_raw,
        transport=FakeAcmeDirectoryTransport(),
        signer=signer or build_signer(allow_crypto=iss_cfg.allow_crypto),
        directory_url=directory_url,
    )
    if orders is None:
        # Force-enable order client for issuance path.
        orders = AcmeOrderClient(
            cfg=AcmeJoseConfig(enabled=True, allow_crypto=iss_cfg.allow_crypto),
            signer=signer or FakeJoseSigner(),
            transport=FakeAcmeDirectoryTransport(),
            directory_url=directory_url
            or "https://acme-staging-v02.api.letsencrypt.org/directory",
        )
    return AcmeIssuanceClient(
        cfg=iss_cfg,
        order_client=orders,
        solver=solver or FakeChallengeSolver(kind=iss_cfg.challenge),
    )
