"""
runtime/acme_new_account.py
===========================
ACME ``newAccount`` client foundation (ADR-032).

Default-off. Builds a newAccount intent payload and submits via an
injectable transport. Dry-run / fake transports are CI-safe; live POST
is opt-in and soft (no JOSE signing — real LE still needs certbot/acme).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.acme_account import (
    AcmeAccountConfig,
    AcmeAccountRegistry,
    DEFAULT_STAGING_DIRECTORY,
    _truthy,
    probe_acme_directory,
)


class AcmeNewAccountError(RuntimeError):
    """newAccount client failed."""


@runtime_checkable
class AcmeDirectoryTransport(Protocol):
    def fetch_directory(self, directory_url: str) -> dict[str, Any]: ...

    def new_account(self, new_account_url: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class FakeAcmeDirectoryTransport:
    """In-memory ACME directory + newAccount for CI."""

    directory_url: str = DEFAULT_STAGING_DIRECTORY
    _accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def fetch_directory(self, directory_url: str) -> dict[str, Any]:
        base = str(directory_url or self.directory_url).rstrip("/")
        return {
            "ok": True,
            "newAccount": f"{base}/acme/new-acct",
            "newNonce": f"{base}/acme/new-nonce",
            "newOrder": f"{base}/acme/new-order",
            "keys": ["newAccount", "newNonce", "newOrder"],
        }

    def new_account(self, new_account_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        kid = f"https://acme.test/acme/acct/{uuid.uuid4().hex[:12]}"
        record = {
            "ok": True,
            "status": 201,
            "kid": kid,
            "body": {
                "status": "valid",
                "contact": list(payload.get("contact") or []),
                "orders": f"{kid}/orders",
            },
            "url": new_account_url,
        }
        with self._lock:
            self._accounts[kid] = dict(record)
        return record


@dataclass
class SoftHttpAcmeTransport:
    """
    Soft urllib transport. Live newAccount without JWS will not succeed
    against real LE; used for directory fetch + soft attempt when allow_live.
    """

    timeout_s: float = 5.0

    def fetch_directory(self, directory_url: str) -> dict[str, Any]:
        return probe_acme_directory(directory_url, timeout_s=self.timeout_s)

    def new_account(self, new_account_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(new_account_url or "").strip()
        if not url:
            return {"ok": False, "error": "newAccount URL required"}
        body = json.dumps(payload).encode("utf-8")
        try:
            req = Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/jose+json",
                    "User-Agent": "kerros-acme-new-account/1",
                },
            )
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                raw = resp.read(65536)
                kid = resp.headers.get("Location") or ""
                return {
                    "ok": True,
                    "status": getattr(resp, "status", 200),
                    "kid": kid,
                    "body": raw.decode("utf-8", errors="replace")[:2000],
                }
        except HTTPError as exc:
            return {
                "ok": False,
                "status": exc.code,
                "error": str(exc),
                "body": (exc.read() or b"").decode("utf-8", errors="replace")[:2000],
            }
        except (URLError, OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


@dataclass
class AcmeNewAccountConfig:
    enabled: bool = False
    allow_live: bool = False
    transport: str = "fake"  # fake | http
    terms_of_service_agreed: bool = True
    timeout_s: float = 5.0

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeNewAccountConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_NEW_ACCOUNT")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_NEW_ACCOUNT_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        transport = os.environ.get("KERROS_ACTOR_MESH_ACME_NEW_ACCOUNT_TRANSPORT")
        if transport is None:
            transport = str(data.get("transport") or "fake")

        tos = data.get("terms_of_service_agreed", True)
        env_t = os.environ.get("KERROS_ACTOR_MESH_ACME_TOS")
        if env_t is not None:
            tos = _truthy(env_t)
        elif not isinstance(tos, bool):
            tos = _truthy(tos)

        timeout = data.get("timeout_s", 5.0)
        env_to = os.environ.get("KERROS_ACTOR_MESH_ACME_NEW_ACCOUNT_TIMEOUT")
        if env_to is not None:
            timeout = float(env_to)

        return cls(
            enabled=bool(enabled),
            allow_live=bool(allow_live),
            transport=str(transport or "fake").strip().lower() or "fake",
            terms_of_service_agreed=bool(tos),
            timeout_s=max(0.5, float(timeout or 5.0)),
        )


@dataclass
class AcmeNewAccountClient:
    """Prepare + submit ACME newAccount intents."""

    cfg: AcmeNewAccountConfig
    account: AcmeAccountRegistry | None = None
    account_cfg: AcmeAccountConfig | None = None
    transport: AcmeDirectoryTransport = field(default_factory=FakeAcmeDirectoryTransport)
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _directory_url(self) -> str:
        if self.account is not None:
            return self.account.cfg.directory_url
        if self.account_cfg is not None:
            return self.account_cfg.directory_url
        return DEFAULT_STAGING_DIRECTORY

    def _contact_email(self) -> str:
        if self.account is not None:
            return self.account.cfg.contact_email
        if self.account_cfg is not None:
            return self.account_cfg.contact_email
        return ""

    def prepare(self) -> dict[str, Any]:
        email = self._contact_email()
        contact = [f"mailto:{email}"] if email else []
        return {
            "termsOfServiceAgreed": bool(self.cfg.terms_of_service_agreed),
            "contact": contact,
            "directory_url": self._directory_url(),
            "prepared_at": time.time(),
            "note": "intent only — JOSE/JWS signing out of scope",
        }

    def submit(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AcmeNewAccountError("ACME newAccount client disabled")
        payload = self.prepare()
        if not self.cfg.allow_live and not isinstance(
            self.transport, FakeAcmeDirectoryTransport
        ):
            # Dry path: record intent without network.
            out = {
                "ok": True,
                "dry_run": True,
                "status": "intent_recorded",
                "payload": payload,
                "kid": f"intent:{uuid.uuid4().hex}",
            }
            self._persist_kid(out["kid"], dry_run=True)
            with self._lock:
                self._last = dict(out)
            return out

        directory = self.transport.fetch_directory(self._directory_url())
        new_url = ""
        if isinstance(directory, dict):
            new_url = str(directory.get("newAccount") or "")
        if not new_url and directory.get("ok") is False:
            out = {"ok": False, "error": "directory fetch failed", "directory": directory}
            with self._lock:
                self._last = dict(out)
            return out

        result = self.transport.new_account(new_url, payload)
        kid = str(result.get("kid") or "")
        if result.get("ok") and kid:
            self._persist_kid(kid, dry_run=isinstance(self.transport, FakeAcmeDirectoryTransport))
        out = {"ok": bool(result.get("ok")), "payload": payload, "directory": directory, **result}
        with self._lock:
            self._last = dict(out)
        return out

    def _persist_kid(self, kid: str, *, dry_run: bool) -> None:
        if self.account is None:
            return
        path = Path(self.account.cfg.account_dir) / "account.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "kid": kid,
            "status": "registered",
            "dry_run": dry_run,
            "directory_url": self.account.cfg.directory_url,
            "contact_email": self.account.cfg.contact_email,
            "created_at": time.time(),
            "note": "via AcmeNewAccountClient",
        }
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self.account._lock:  # noqa: SLF001
            self.account._record = dict(record)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "allow_live": self.cfg.allow_live,
                "transport": self.cfg.transport,
                "last": dict(self._last),
            }


def build_acme_new_account_client(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    account: AcmeAccountRegistry | None = None,
    account_cfg: Optional[Mapping[str, Any]] = None,
    transport: AcmeDirectoryTransport | None = None,
) -> AcmeNewAccountClient | None:
    na_cfg = AcmeNewAccountConfig.from_mapping(cfg)
    if not na_cfg.enabled:
        return None
    if transport is not None:
        tr = transport
    elif na_cfg.transport in ("http", "live", "urllib") and na_cfg.allow_live:
        tr = SoftHttpAcmeTransport(timeout_s=na_cfg.timeout_s)
    else:
        tr = FakeAcmeDirectoryTransport()
    acfg = AcmeAccountConfig.from_mapping(account_cfg) if account_cfg else None
    return AcmeNewAccountClient(
        cfg=na_cfg,
        account=account,
        account_cfg=acfg,
        transport=tr,
    )
