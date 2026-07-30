"""
runtime/acme_jose.py
====================
ACME JOSE/JWS + soft order foundation (ADR-033).

Default-off. Provides base64url helpers and a JWS-flattened signer.
Uses a deterministic ``FakeJoseSigner`` for CI; optional soft
``cryptography`` ES256 when installed and ``allow_crypto`` is set.
Does **not** complete a full Let's Encrypt issuance flow.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from runtime.acme_account import _truthy
from runtime.acme_new_account import (
    AcmeDirectoryTransport,
    FakeAcmeDirectoryTransport,
)


class AcmeJoseError(RuntimeError):
    """JOSE / order helper failed."""


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_json(obj: Any) -> str:
    raw = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return b64url(raw)


@runtime_checkable
class JoseSigner(Protocol):
    def alg(self) -> str: ...

    def jwk(self) -> dict[str, Any]: ...

    def sign(self, signing_input: bytes) -> bytes: ...


@dataclass
class FakeJoseSigner:
    """HMAC-SHA256 stand-in (not ACME-valid; CI only)."""

    secret: bytes = b"kerros-fake-jose"
    kid: str = "fake-kid"

    def alg(self) -> str:
        return "HS256"

    def jwk(self) -> dict[str, Any]:
        return {
            "kty": "oct",
            "kid": self.kid,
            "k": b64url(self.secret),
        }

    def sign(self, signing_input: bytes) -> bytes:
        return hmac.new(self.secret, signing_input, hashlib.sha256).digest()


def cryptography_available() -> bool:
    try:
        import cryptography  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class SoftEs256Signer:
    """
    Soft ES256 signer via cryptography when available.
    Falls back construction error if missing — callers should use Fake.
    """

    private_key: Any
    kid: str = ""

    def alg(self) -> str:
        return "ES256"

    def jwk(self) -> dict[str, Any]:
        from cryptography.hazmat.primitives.asymmetric import ec

        pub = self.private_key.public_key().public_numbers()
        x = pub.x.to_bytes(32, "big")
        y = pub.y.to_bytes(32, "big")
        out = {"kty": "EC", "crv": "P-256", "x": b64url(x), "y": b64url(y)}
        if self.kid:
            out["kid"] = self.kid
        return out

    def sign(self, signing_input: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils

        sig = self.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(sig)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def build_signer(*, allow_crypto: bool = False, kid: str = "") -> JoseSigner:
    if allow_crypto and cryptography_available():
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        return SoftEs256Signer(private_key=key, kid=kid or f"ec-{uuid.uuid4().hex[:8]}")
    return FakeJoseSigner(kid=kid or "fake-kid")


def jws_flattened(
    payload: Mapping[str, Any],
    *,
    signer: JoseSigner,
    protected_extra: Optional[Mapping[str, Any]] = None,
    url: str = "",
    nonce: str = "",
    kid: str = "",
) -> dict[str, str]:
    """Build a flattened JWS object (RFC 7515 §7.2.2 style)."""
    protected: dict[str, Any] = {"alg": signer.alg()}
    if kid:
        protected["kid"] = kid
    else:
        protected["jwk"] = signer.jwk()
    if url:
        protected["url"] = url
    if nonce:
        protected["nonce"] = nonce
    if protected_extra:
        protected.update(dict(protected_extra))
    prot_b64 = b64url_json(protected)
    pay_b64 = b64url_json(dict(payload))
    signing_input = f"{prot_b64}.{pay_b64}".encode("ascii")
    sig = b64url(signer.sign(signing_input))
    return {"protected": prot_b64, "payload": pay_b64, "signature": sig}


@dataclass
class AcmeJoseConfig:
    enabled: bool = False
    allow_crypto: bool = False
    allow_live: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeJoseConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_JOSE")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        allow_crypto = data.get("allow_crypto", False)
        env_c = os.environ.get("KERROS_ACTOR_MESH_ACME_JOSE_CRYPTO")
        if env_c is not None:
            allow_crypto = _truthy(env_c)
        else:
            allow_crypto = _truthy(allow_crypto)

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_JOSE_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        return cls(
            enabled=bool(enabled),
            allow_crypto=bool(allow_crypto),
            allow_live=bool(allow_live),
        )


@dataclass
class AcmeOrderClient:
    """Soft newOrder helper over an ACME directory transport."""

    cfg: AcmeJoseConfig
    signer: JoseSigner = field(default_factory=FakeJoseSigner)
    transport: AcmeDirectoryTransport = field(default_factory=FakeAcmeDirectoryTransport)
    directory_url: str = "https://acme-staging-v02.api.letsencrypt.org/directory"
    _orders: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def create_order(self, domains: list[str]) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AcmeJoseError("ACME JOSE/order client disabled")
        idents = [{"type": "dns", "value": d} for d in domains if str(d).strip()]
        if not idents:
            raise AcmeJoseError("at least one domain required")
        payload = {"identifiers": idents}
        directory = self.transport.fetch_directory(self.directory_url)
        new_order = str(directory.get("newOrder") or "")
        nonce = f"nonce-{uuid.uuid4().hex[:12]}"
        jws = jws_flattened(
            payload,
            signer=self.signer,
            url=new_order,
            nonce=nonce,
        )
        # Fake transport: accept order locally. Live HTTP without full ACME
        # protocol is opt-in and expected to soft-fail against real LE.
        order_url = f"https://acme.test/acme/order/{uuid.uuid4().hex[:12]}"
        if self.cfg.allow_live and not isinstance(
            self.transport, FakeAcmeDirectoryTransport
        ):
            # Soft: record intent only (full ACME POST-as-GET loop out of scope).
            result = {
                "ok": False,
                "skipped_live": True,
                "error": "live newOrder requires full ACME client; intent recorded",
                "jws": jws,
                "payload": payload,
            }
        else:
            result = {
                "ok": True,
                "status": "pending",
                "order_url": order_url,
                "identifiers": idents,
                "authorizations": [f"{order_url}/authz/0"],
                "finalize": f"{order_url}/finalize",
                "jws": jws,
                "created_at": time.time(),
            }
        with self._lock:
            self._orders.append(dict(result))
        return result

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "allow_crypto": self.cfg.allow_crypto,
                "allow_live": self.cfg.allow_live,
                "alg": self.signer.alg(),
                "cryptography": cryptography_available(),
                "orders": len(self._orders),
            }


def build_acme_order_client(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    transport: AcmeDirectoryTransport | None = None,
    signer: JoseSigner | None = None,
    directory_url: str = "",
) -> AcmeOrderClient | None:
    jose_cfg = AcmeJoseConfig.from_mapping(cfg)
    if not jose_cfg.enabled:
        return None
    return AcmeOrderClient(
        cfg=jose_cfg,
        signer=signer or build_signer(allow_crypto=jose_cfg.allow_crypto),
        transport=transport or FakeAcmeDirectoryTransport(),
        directory_url=directory_url
        or "https://acme-staging-v02.api.letsencrypt.org/directory",
    )
