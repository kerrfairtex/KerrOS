"""
kernel/config.py
================
Kernel configuration system — typed, validated access to runtime settings.

Loads .env + config.json (via core/config.py) and adds kernel-specific
paths (base, workspace, scope). This is the only supported way for kernel
code and boot to read configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _detect_base() -> Path:
    env_base = os.environ.get("KERROS_BASE") or os.environ.get("OFFLINE_AI_BASE")
    if env_base:
        return Path(env_base).expanduser().resolve()

    termux = Path("/data/data/com.termux/files/home/offline_ai")
    if termux.exists():
        return termux.resolve()

    # Repo / workspace root fallback (cloud dev, local clone).
    repo = Path(__file__).resolve().parent.parent
    if (repo / "config.json").exists():
        return repo.resolve()

    return Path(os.path.expanduser("~/offline_ai")).resolve()


@dataclass
class KernelConfig:
    """Validated kernel configuration snapshot."""

    base: Path
    workspace: Path
    scope_path: Path
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.values:
            raise KeyError(f"required config key missing: {key}")
        return self.values[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": str(self.base),
            "workspace": str(self.workspace),
            "scope_path": str(self.scope_path),
            **self.values,
        }


def _load_raw(base: Path) -> dict[str, Any]:
    """Load config using core/config when available, else direct JSON."""
    try:
        import core.config as legacy

        legacy.BASE = base
        legacy._cfg = None  # reset singleton for new base
        return legacy.load()
    except Exception:
        cfg_path = base / "config.json"
        if not cfg_path.exists():
            return {}
        with open(cfg_path) as f:
            return json.load(f)


def load_config(*, base: Path | None = None) -> KernelConfig:
    """Load and validate kernel configuration."""
    root = (base or _detect_base()).expanduser().resolve()
    raw = _load_raw(root)

    workspace = Path(
        os.environ.get(
            "KERROS_WORKSPACE",
            os.environ.get("KERROS_PROJECT_ROOT", str(root)),
        )
    ).expanduser().resolve()

    scope = root / "config" / "scope.json"
    # Do not fall back to the repo scope.json when KERROS_BASE/OFFLINE_AI_BASE
    # (or an explicit base=) isolates the runtime — that would leak arm/allow
    # state across test sandboxes and alternate installs.
    if not scope.exists() and base is None and not (
        os.environ.get("KERROS_BASE") or os.environ.get("OFFLINE_AI_BASE")
    ):
        scope = Path(__file__).resolve().parent.parent / "config" / "scope.json"

    defaults = {
        "llm_route_policy": "legacy_fallback",
        "llm_provider_default": "cloud",
        "use_omniroute": False,
        "omniroute_url": "http://127.0.0.1:20128/v1",
        "qdrant_enabled": False,
        "qdrant_url": "http://127.0.0.1:6333",
        # KerrOS-only collection — do not reuse OmniRoute vector namespaces (P5).
        "qdrant_collection": "kerros_memory",
        # C-19: self-hosted LLMs — off by default; also via KERROS_LOCAL_LLM / KERROS_*_ENABLED.
        "ollama_enabled": False,
        "vllm_enabled": False,
        "local_llm": False,
        # P6: composite provider circuit breaker / cooldown / lockout.
        "llm_resilience": {
            "enabled": True,
            "failure_threshold": 3,
            "cooldown_s": 30,
            "lockout_opens": 3,
            "lockout_s": 300,
        },
        # P3/C-16 event mesh — off by default; nng/Docker multi-node still deferred.
        "event_mesh": {
            "enabled": False,
            "node_id": "local",
            "transport": "null",  # null | file | http | durable
            "file_dir": "data/event_mesh",
            "http_peers": [],
            "http_listen": None,  # e.g. "0.0.0.0:8787" (Docker / ADR-011)
            "http_timeout_s": 2.0,
            "broker_db": "data/event_mesh/broker.db",
            "discovery": None,  # None=auto for durable; file | none
            "discovery_dir": "data/event_mesh/peers",
            "discovery_ttl_s": 60,
            # ADR-014: shared secret (env KERROS_EVENT_MESH_TOKEN preferred).
            "auth_token": "",
            "auth_required": False,
        },
        # P3: declarative workflow YAML directory (loaded at boot).
        "workflow_yaml_dir": "config/workflows",
        # ADR-013: gate YAML llm/tool actions (tool allowlist; scope_gate still applies).
        "workflow_actions": {
            "allow_llm": True,
            "allowed_tools": None,  # None → DEFAULT_ALLOWED_TOOLS; ["*"] → all
            "allow_all_tools": False,
        },
        # ADR-019: software-WORM + retention for decision_log (off by default).
        "audit_retention": {
            "enabled": False,
            "retain_days": 90,
            "action": "archive",  # archive | purge
            "worm_dir": "data/audit_worm",
            "allow_purge": False,
        },
        # ADR-021: evidence RBAC + SIEM forwarder (off by default).
        "audit_rbac": {
            "enabled": False,
            "tokens": {},  # token → reader|operator|admin
        },
        "audit_siem": {
            "enabled": False,
            "transport": "webhook",  # webhook | syslog
            "url": "",
            "timeout_s": 2.0,
            "token": "",
            "forward_on_record": True,
            "forward_on_seal": True,
        },
        # ADR-022: optional Object Lock / compliance mirror (off by default).
        "audit_object_lock": {
            "enabled": False,
            "backend": "local_mirror",  # local_mirror | s3_object_lock
            "strict": False,
            "mirror_dir": "data/audit_worm/object_lock_mirror",
            "endpoint_url": "",
            "bucket": "",
            "prefix": "kerros/audit_worm/",
            "region": "us-east-1",
            "object_lock_mode": "GOVERNANCE",
            "retain_days": 365,
            "legal_hold": False,
        },
        # ADR-024: jurisdiction privacy — egress redaction/hash (off by default).
        "audit_privacy": {
            "enabled": False,
            "mode": "hash",  # hash | redact
            "fields": ["input_summary", "reason", "actor"],
            "apply_on": ["export", "siem", "cli_read"],
            "salt": "",  # prefer KERROS_AUDIT_PRIVACY_SALT
        },
        # ADR-025: residency stamp + erasure request ledger (off by default).
        "audit_residency": {
            "enabled": False,
            "region": "",
            "stamp_on_export": True,
            "stamp_on_siem": True,
            "stamp_on_cli_read": True,
        },
        "audit_erasure": {
            "enabled": False,
            "db_path": "data/erasure_requests.db",
            "worm_dir": "data/audit_worm",
        },
        # ADR-026/027: cross-border transfer intent + optional execute pipeline.
        "audit_transfers": {
            "enabled": False,
            "db_path": "data/transfer_requests.db",
            "default_from_region": "",  # falls back to audit_residency.region
            "execute_enabled": False,
            "backend": "local_copy",  # local_copy | http_put
            "dest_dir": "data/transfer_outbox",
            "http_url": "",
            "http_token": "",
            "http_timeout_s": 5.0,
            "sources": ["sealed_segments"],  # + export_jsonl
        },
        # C-16 actor mesh — off by default (socket always; nng if pynng installed).
        "actor_mesh": {
            "enabled": False,
            "node_id": "local",
            "backend": "socket",  # socket | nng
            "listen": None,  # e.g. "tcp://127.0.0.1:9091"
            "peers": [],
            # ADR-018: actor_name → node_id (or KERROS_ACTOR_MESH_ROUTES=a=node-b,b=node-a)
            "routes": {},
            "auth_token": "",  # env KERROS_ACTOR_MESH_TOKEN
            "auth_required": False,
            # When True, non-loopback listen refuses empty token (WAN-safe).
            "auth_required_non_loopback": False,
            # ADR-020: local actor liveness (off by default).
            # ADR-023: remote_restart + process_map under supervision.
            "supervision": {
                "enabled": False,
                "heartbeat_interval_s": 0,
                "ttl_s": 30.0,
                "suspect_after_s": 15.0,
                "ping_timeout_s": 2.0,
                "auto_register_ping": True,
                "remote_restart": False,
                "process_map": {},  # actor_name → ServiceManager service name
                # ADR-028: local OTP-style tree (off by default).
                "tree": {"enabled": False, "strategy": "one_for_one"},
            },
            # ADR-023/028: optional TLS/mTLS + CA reload for socket backend.
            "tls": {
                "enabled": False,
                "ca_file": "",
                "cert_file": "",
                "key_file": "",
                "require_client_cert": False,
                "check_hostname": False,
                "reload": False,
                "reload_interval_s": 0,
            },
            # ADR-023/028: nats backend + optional JetStream soft client.
            "nats": {
                "url": "nats://127.0.0.1:4222",
                "subject_prefix": "kerros.actor",
                "jetstream": {
                    "enabled": False,
                    "stream": "kerros",
                    "durable": "",
                    # ADR-029: client-side multi-URL failover (off by default).
                    "cluster": {
                        "enabled": False,
                        "servers": [],  # e.g. ["nats://a:4222","nats://b:4222"]
                        "failover_retries": 2,
                        "connect_timeout_s": 2.0,
                    },
                },
            },
            # ADR-029/030: ACME live-dir watch + optional HTTP-01 solver (off by default).
            "acme": {
                "enabled": False,
                "live_dir": "",
                "domain": "",
                "watch_interval_s": 60.0,
                "allow_certbot_probe": False,
                "http01": {
                    "enabled": False,
                    "bind": "127.0.0.1",
                    "port": 0,
                    "path_prefix": "/.well-known/acme-challenge",
                },
            },
            # ADR-030: Supercluster / gateway / leafnode topology registry (off by default).
            "supercluster": {
                "enabled": False,
                "name": "kerros",
                "clusters": [],
                "gateways": [],
                "leafnodes": [],
            },
        },
    }
    merged = {**defaults, **raw}

    return KernelConfig(
        base=root,
        workspace=workspace,
        scope_path=scope.resolve(),
        values=merged,
    )


def reload_config(*, base: Path | None = None) -> KernelConfig:
    """Force reload configuration (clears core/config singleton)."""
    try:
        import core.config as legacy

        legacy._cfg = None
    except Exception:
        pass
    return load_config(base=base)
