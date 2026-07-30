"""
adapters/audit/crypto_shred.py
==============================
Sealed-cold *crypto-shred* foundation (ADR-034).

Default-off. Maintains a DEK (data-encryption-key) store keyed by
subject/segment. ``shred()`` destroys the DEK so ciphertext becomes
unreadable **without mutating sealed WORM bytes**. Soft Fernet when
``cryptography`` is installed; otherwise a XOR stand-in for CI.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class CryptoShredError(RuntimeError):
    """Crypto-shred operation failed."""


def cryptography_fernet_available() -> bool:
    try:
        from cryptography.fernet import Fernet  # noqa: F401

        return True
    except ImportError:
        return False


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    if not key:
        raise CryptoShredError("empty key")
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


@dataclass
class CryptoShredConfig:
    enabled: bool = False
    db_path: str = "data/crypto_shred_keys.db"
    allow_shred: bool = False  # explicit gate — shred is irreversible

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "CryptoShredConfig":
        data = dict(raw or {})
        nested = (
            data.get("audit_crypto_shred")
            if isinstance(data.get("audit_crypto_shred"), dict)
            else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_AUDIT_CRYPTO_SHRED")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        db_path = os.environ.get("KERROS_AUDIT_CRYPTO_SHRED_DB")
        if db_path is None:
            db_path = str(nested.get("db_path") or "data/crypto_shred_keys.db")
        path = Path(db_path)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        allow = nested.get("allow_shred", False)
        env_a = os.environ.get("KERROS_AUDIT_CRYPTO_SHRED_ALLOW")
        if env_a is not None:
            allow = _truthy(env_a)
        else:
            allow = _truthy(allow)

        return cls(
            enabled=bool(enabled),
            db_path=str(path),
            allow_shred=bool(allow),
        )


@dataclass
class CryptoShredKeyStore:
    """SQLite DEK registry + shred ledger."""

    cfg: CryptoShredConfig
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _connect(self) -> sqlite3.Connection:
        Path(self.cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cfg.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deks (
                key_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                dek_b64 TEXT,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                shredded_at REAL,
                note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shred_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                at REAL NOT NULL,
                actor TEXT,
                note TEXT
            )
            """
        )
        conn.commit()
        return conn

    def mint_dek(self, subject_id: str, *, note: str = "") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise CryptoShredError("crypto-shred disabled")
        sid = str(subject_id or "").strip()
        if not sid:
            raise CryptoShredError("subject_id required")
        if cryptography_fernet_available():
            from cryptography.fernet import Fernet

            dek = Fernet.generate_key()
        else:
            dek = base64.urlsafe_b64encode(secrets.token_bytes(32))
        key_id = f"dek:{hashlib.sha256(sid.encode() + dek).hexdigest()[:16]}"
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO deks(key_id, subject_id, dek_b64, status, created_at, note) "
                    "VALUES(?,?,?,?,?,?)",
                    (key_id, sid, dek.decode("ascii"), "active", now, note),
                )
                conn.commit()
            finally:
                conn.close()
        return {"key_id": key_id, "subject_id": sid, "status": "active"}

    def get_dek(self, key_id: str) -> bytes | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT dek_b64, status FROM deks WHERE key_id=?",
                    (str(key_id),),
                ).fetchone()
            finally:
                conn.close()
        if not row or row["status"] != "active" or not row["dek_b64"]:
            return None
        return str(row["dek_b64"]).encode("ascii")

    def encrypt(self, key_id: str, plaintext: bytes) -> bytes:
        dek = self.get_dek(key_id)
        if dek is None:
            raise CryptoShredError("DEK missing or shredded")
        if cryptography_fernet_available():
            from cryptography.fernet import Fernet

            return Fernet(dek).encrypt(plaintext)
        return _xor_crypt(plaintext, hashlib.sha256(dek).digest())

    def decrypt(self, key_id: str, ciphertext: bytes) -> bytes:
        dek = self.get_dek(key_id)
        if dek is None:
            raise CryptoShredError("DEK missing or shredded")
        if cryptography_fernet_available():
            from cryptography.fernet import Fernet

            return Fernet(dek).decrypt(ciphertext)
        return _xor_crypt(ciphertext, hashlib.sha256(dek).digest())

    def shred(
        self, key_id: str, *, actor: str = "", note: str = ""
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise CryptoShredError("crypto-shred disabled")
        if not self.cfg.allow_shred:
            raise CryptoShredError("shred not allowed (set allow_shred)")
        kid = str(key_id or "").strip()
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT subject_id, status FROM deks WHERE key_id=?", (kid,)
                ).fetchone()
                if not row:
                    raise CryptoShredError(f"unknown key_id: {kid}")
                if row["status"] == "shredded":
                    return {"ok": True, "already": True, "key_id": kid}
                conn.execute(
                    "UPDATE deks SET dek_b64=NULL, status='shredded', shredded_at=? WHERE key_id=?",
                    (now, kid),
                )
                conn.execute(
                    "INSERT INTO shred_events(key_id, subject_id, at, actor, note) VALUES(?,?,?,?,?)",
                    (kid, row["subject_id"], now, actor, note),
                )
                conn.commit()
                subject = row["subject_id"]
            finally:
                conn.close()
        return {
            "ok": True,
            "key_id": kid,
            "subject_id": subject,
            "status": "shredded",
            "shredded_at": now,
            "worm_untouched": True,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                active = conn.execute(
                    "SELECT COUNT(*) AS c FROM deks WHERE status='active'"
                ).fetchone()["c"]
                shredded = conn.execute(
                    "SELECT COUNT(*) AS c FROM deks WHERE status='shredded'"
                ).fetchone()["c"]
                events = conn.execute(
                    "SELECT COUNT(*) AS c FROM shred_events"
                ).fetchone()["c"]
            finally:
                conn.close()
        return {
            "enabled": self.cfg.enabled,
            "allow_shred": self.cfg.allow_shred,
            "db_path": self.cfg.db_path,
            "active_deks": int(active),
            "shredded_deks": int(shredded),
            "shred_events": int(events),
            "fernet": cryptography_fernet_available(),
        }


def build_crypto_shred_store(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> CryptoShredKeyStore | None:
    c = CryptoShredConfig.from_mapping(cfg, base=base)
    if not c.enabled:
        return None
    return CryptoShredKeyStore(cfg=c)
