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
        # ADR-034: hardware WORM appliance mirror (off by default).
        "audit_hardware_worm": {
            "enabled": False,
            "backend": "fake",  # fake | http
            "allow_live": False,
            "endpoint_url": "",
            "token": "",
            "prefix": "kerros/audit_worm/",
            "strict": False,
        },
        # ADR-034: sealed-cold crypto-shred DEK store (off by default).
        "audit_crypto_shred": {
            "enabled": False,
            "db_path": "data/crypto_shred_keys.db",
            "allow_shred": False,
        },
        # ADR-034: IdP / data-subject portal facade (off by default).
        "idp_portal": {
            "enabled": False,
            "backend": "fake",  # fake | oidc_probe
            "issuer": "",
            "allow_discovery_probe": False,
            "session_ttl_s": 3600.0,
        },
        # ADR-036: OIDC relying party (off by default).
        "oidc_rp": {
            "enabled": False,
            "client_id": "kerros",
            "client_secret": "",
            "redirect_uri": "http://127.0.0.1:8080/oidc/callback",
            "issuer": "https://idp.test",
            "scopes": ["openid", "profile", "email"],
            "allow_live": False,
            "allow_discovery_probe": False,
        },
        # ADR-036: SoA draft foundation (off by default).
        "compliance_soa": {
            "enabled": False,
            "org_name": "KerrOS",
            "output_dir": "data/soa",
            "allow_write": False,
        },
        # ADR-041: auditor-signed SoA foundation (off by default).
        "soa_audit": {
            "enabled": False,
            "backend": "fake",  # fake | openssl
            "allow_live": False,
            "allow_write": False,
            "key_path": "",
            "signer_id": "auditor@kerros.test",
            "output_dir": "data/soa",
        },
        # ADR-041: SAML SP foundation (off by default).
        "saml_sp": {
            "enabled": False,
            "entity_id": "https://kerros.local/saml/sp",
            "acs_url": "http://127.0.0.1:8080/saml/acs",
            "idp_entity_id": "https://idp.test/saml",
            "idp_sso_url": "https://idp.test/saml/sso",
            "allow_live": False,
        },
        # ADR-044: auditor evidence packs (off by default).
        "soa_evidence": {
            "enabled": False,
            "org_name": "KerrOS",
            "output_dir": "data/soa/evidence",
            "allow_write": False,
            "allow_zip": False,
            "allow_live": False,
            "signer_backend": "fake",  # fake | openssl
            "key_path": "",
            "signer_id": "auditor@kerros.test",
        },
        # ADR-044: production SAML federation (off by default).
        "saml_federation": {
            "enabled": False,
            "entity_id": "https://kerros.local/saml/sp",
            "acs_url": "http://127.0.0.1:8080/saml/acs",
            "allow_live": False,
            "require_signed_assertions": True,
            "allow_encrypted_assertions": False,
            "default_idp": "",
            "idps": [],
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
            # ADR-029..032: ACME watch / solvers / account / cloud DNS (off by default).
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
                "account": {
                    "enabled": False,
                    "directory_url": "https://acme-staging-v02.api.letsencrypt.org/directory",
                    "contact_email": "",
                    "account_dir": "data/acme_account",
                    "dry_run": True,
                    "allow_directory_probe": False,
                },
                "new_account": {
                    "enabled": False,
                    "allow_live": False,
                    "transport": "fake",
                    "terms_of_service_agreed": True,
                },
                "jose": {
                    "enabled": False,
                    "allow_crypto": False,
                    "allow_live": False,
                },
                "issuance": {
                    "enabled": False,
                    "allow_live": False,
                    "challenge": "dns-01",
                    "allow_crypto": False,
                },
                "production": {
                    "enabled": False,
                    "tool": "fake",  # fake | certbot | acme.sh
                    "allow_live": False,
                    "staging": True,
                    "domains": [],
                    "email": "",
                    "live_dir": "data/acme_live",
                    "auto_issue": False,
                },
                "renewal": {
                    "enabled": False,
                    "interval_s": 3600.0,
                    "allow_live": False,
                    "use_certbot_renew": False,
                    "autostart": False,
                },
                "dns01": {
                    "enabled": False,
                    "provider": "memory",
                    "webhook_url": "",
                    "webhook_token": "",
                    "cloud": {
                        "enabled": False,
                        "provider": "fake",
                        "allow_live": False,
                        "webhook_url": "",
                        "webhook_token": "",
                        "zone": "",
                    },
                    "sdk": {
                        "enabled": False,
                        "provider": "route53",  # route53 | cloudflare
                        "allow_live": False,
                        "hosted_zone_id": "",
                        "region": "us-east-1",
                        "api_token": "",
                        "zone_id": "",
                    },
                },
            },
            # ADR-030..033: Supercluster topology / ops / control-plane / broker (off by default).
            "supercluster": {
                "enabled": False,
                "name": "kerros",
                "clusters": [],
                "gateways": [],
                "leafnodes": [],
                "ops": {
                    "enabled": False,
                    "probe_timeout_s": 1.0,
                    "allow_probe": False,
                },
                "control_plane": {
                    "enabled": False,
                    "config_dir": "data/supercluster_cp",
                    "allow_write": False,
                    "allow_monitor_probe": False,
                    "monitor_urls": [],
                    "allow_signal_reload": False,
                    "backend": "memory",
                },
                "broker": {
                    "enabled": False,
                    "backend": "memory",  # memory | subprocess
                    "bin_name": "nats-server",
                    "config_path": "",
                    "allow_spawn": False,
                    "autostart": False,
                    "extra_args": [],
                },
                "broker_fleet": {
                    "enabled": False,
                    "backend": "memory",
                    "allow_spawn": False,
                    "autostart": False,
                    "members": [],
                },
                "remote_fleet": {
                    "enabled": False,
                    "transport": "fake",  # fake | http | ssh
                    "allow_live": False,
                    "http_base_url": "",
                    "http_token": "",
                    "ssh_bin": "ssh",
                    "hosts": [],
                },
                "inventory": {
                    "enabled": False,
                    "store_path": "data/fleet_inventory.json",
                    "allow_persist": False,
                    "hosts": [],
                },
                "k8s_operator": {
                    "enabled": False,
                    "backend": "fake",  # fake | kubectl
                    "allow_live": False,
                    "namespace": "kerros",
                    "kubectl_bin": "kubectl",
                },
                "k8s_incluster": {
                    "enabled": False,
                    "reconcile_interval_s": 5.0,
                    "autostart": False,
                    "require_in_cluster": False,
                    "namespace": "kerros",
                    "desired": [],
                },
                "cmdb": {
                    "enabled": False,
                    "backend": "fake",  # fake | http
                    "allow_live": False,
                    "url": "",
                    "token": "",
                    "auto_sync": False,
                    "hosts": [],
                },
                # ADR-040: CRD / operator-sdk-style facade.
                "k8s_crd": {
                    "enabled": False,
                    "backend": "fake",  # fake | kubectl
                    "allow_live": False,
                    "kubectl_bin": "kubectl",
                    "namespace": "kerros",
                    "crd_path": "deploy/k8s/crds/natsbroker.yaml",
                },
                # ADR-040: commercial CMDB connectors.
                "cmdb_commercial": {
                    "enabled": False,
                    "vendor": "servicenow",  # servicenow | device42 | generic
                    "backend": "fake",  # fake | http
                    "allow_live": False,
                    "url": "",
                    "token": "",
                    "auto_sync": False,
                },
                # ADR-042: live operator-sdk / controller-runtime facade.
                "operator_sdk": {
                    "enabled": False,
                    "backend": "fake",  # fake | kubectl
                    "allow_live": False,
                    "allow_write": False,
                    "namespace": "kerros",
                    "kubectl_bin": "kubectl",
                    "project_dir": "deploy/k8s/operator",
                    "reconcile_interval_s": 5.0,
                    "leader_identity": "kerros-controller-0",
                    "autostart": False,
                    "desired": [],
                },
                # ADR-042: deep vendor CMDB SDKs.
                "cmdb_vendor_sdk": {
                    "enabled": False,
                    "vendor": "servicenow",  # servicenow | device42
                    "backend": "fake",  # fake | pysnow | device42
                    "allow_live": False,
                    "instance": "",
                    "base_url": "",
                    "username": "",
                    "password": "",
                    "token": "",
                    "table": "cmdb_ci_server",
                    "auto_sync": False,
                },
                # ADR-043: Go operator binary packaging.
                "go_operator": {
                    "enabled": False,
                    "module_path": "github.com/kerros/nats-operator",
                    "project_dir": "deploy/k8s/operator/go",
                    "binary_name": "kerros-nats-operator",
                    "image": "kerros/nats-operator:dev",
                    "allow_write": False,
                    "allow_build": False,
                    "allow_image": False,
                },
                # ADR-043: certified vendor partnership facade.
                "vendor_cert": {
                    "enabled": False,
                    "backend": "fake",  # fake | http
                    "allow_live": False,
                    "allow_write": False,
                    "output_dir": "data/vendor_cert",
                    "url_template": "",
                    "token": "",
                    "org_name": "KerrOS",
                },
            },
            # ADR-039: systemd timer packaging (off by default; under actor_mesh root).
            "systemd_timers": {
                "enabled": False,
                "org_name": "KerrOS",
                "workdir": "",
                "exec_start": "python3 -c \"print('kerros-acme-renew')\"",
                "tool": "fake",
                "on_calendar": "daily",
                "random_delay": "15m",
                "units_dir": "deploy/systemd",
                "allow_write": False,
                "allow_install": False,
                "install_root": "",
                "unit_basename": "kerros-acme-renew",
            },
            # ADR-040: distro package stubs (.deb/.rpm metadata).
            "distro_packages": {
                "enabled": False,
                "formats": ["deb", "rpm"],
                "package_name": "kerros",
                "version": "0.1.0",
                "maintainer": "KerrOS <ops@kerros.local>",
                "description": "KerrOS offline AI assistant and actor mesh",
                "output_dir": "deploy/packaging",
                "allow_write": False,
                "allow_install": False,
            },
            # ADR-042: apt/yum repo publish foundation.
            "distro_publish": {
                "enabled": False,
                "backend": "fake",  # fake | reprepro | createrepo | auto
                "formats": ["deb", "rpm"],
                "staging_dir": "deploy/packaging/repos",
                "package_name": "kerros",
                "version": "0.1.0",
                "allow_write": False,
                "allow_publish": False,
                "allow_remote": False,
                "remote_url": "",
            },
            # ADR-043: remote apt/yum mirror push.
            "remote_mirror": {
                "enabled": False,
                "backend": "fake",  # fake | rsync | http
                "staging_dir": "deploy/packaging/repos",
                "remote_url": "",
                "token": "",
                "allow_remote": False,
                "allow_write": False,
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
