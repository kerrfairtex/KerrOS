"""
adapters/llm/offline_gateway.py
================================
Offline LiteLLM + llama.cpp gateway planner (Phase E / ADR-054).

Default-off Fake plan for CI. Documents loopback compose intent without
starting containers. Soft probe only when ``allow_live``.
``production_gateway`` stays False.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from adapters.llm.openai_compat import OpenAICompatClient


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class OfflineGatewayError(RuntimeError):
    """Offline gateway planning failed."""


@dataclass
class OfflineGatewayConfig:
    enabled: bool = False
    llama_cpp_url: str = "http://127.0.0.1:8080/v1"
    litellm_url: str = "http://127.0.0.1:4000/v1"
    model: str = "qwen0.5b-q4"
    compose_dir: str = "deploy/llama_cpp"
    allow_live: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "OfflineGatewayConfig":
        data = dict(raw or {})
        # Merge offline profile litellm block when active.
        try:
            from adapters.llm.offline_profile import (
                is_offline_profile_active,
                load_offline_profile,
            )

            if is_offline_profile_active(data):
                profile = load_offline_profile(cfg=data)
                litellm = profile.get("litellm") if isinstance(profile, dict) else None
                if isinstance(litellm, dict):
                    merged = dict(litellm)
                    merged.update({k: v for k, v in data.items() if v not in (None, "")})
                    data = merged
        except Exception:
            pass

        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_OFFLINE_GATEWAY")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        llama_url = os.environ.get("LLAMA_CPP_SERVER_ENDPOINT") or str(
            data.get("llama_cpp_url") or "http://127.0.0.1:8080/v1"
        )
        litellm_url = os.environ.get("LITELLM_ENDPOINT") or str(
            data.get("litellm_url")
            or data.get("endpoint")
            or "http://127.0.0.1:4000/v1"
        )
        model = os.environ.get("LITELLM_MODEL") or str(
            data.get("model") or "qwen0.5b-q4"
        )
        compose_dir = str(data.get("compose_dir") or "deploy/llama_cpp")
        path = Path(compose_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_OFFLINE_GATEWAY_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        return cls(
            enabled=bool(enabled),
            llama_cpp_url=str(llama_url).rstrip("/"),
            litellm_url=str(litellm_url).rstrip("/"),
            model=str(model).strip() or "qwen0.5b-q4",
            compose_dir=str(path),
            allow_live=bool(allow_live),
        )


@dataclass
class OfflineGatewayPlanner:
    """Plan (and optionally soft-probe) the offline OpenAI gateway."""

    cfg: OfflineGatewayConfig
    _plans: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def plan(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise OfflineGatewayError("offline gateway disabled")
        out: dict[str, Any] = {
            "ok": True,
            "compose_dir": self.cfg.compose_dir,
            "profiles": ["llama_cpp", "litellm", "proxy"],
            "llama_cpp_url": self.cfg.llama_cpp_url,
            "litellm_url": self.cfg.litellm_url,
            "model": self.cfg.model,
            "loopback": True,
            "production_gateway": False,
            "dry_run": True,
            "note": "Fake gateway plan — no containers started",
            "client_env": {
                "LLAMA_CPP_SERVER_ENDPOINT": self.cfg.llama_cpp_url,
                "LITELLM_ENDPOINT": self.cfg.litellm_url,
                "LITELLM_MODEL": self.cfg.model,
                "KERROS_LLM_PROVIDER": "litellm",
            },
            "at": time.time(),
        }
        if self.cfg.allow_live:
            llama_ok = OpenAICompatClient(
                base_url=self.cfg.llama_cpp_url,
                model=self.cfg.model,
                provider_name="llama_cpp",
            ).available()
            litellm_ok = OpenAICompatClient(
                base_url=self.cfg.litellm_url,
                model=self.cfg.model,
                provider_name="litellm",
            ).available()
            out["dry_run"] = False
            out["live"] = {"llama_cpp": llama_ok, "litellm": litellm_ok}
            out["production_gateway"] = False
            out["note"] = (
                "Soft live probe — production_gateway stays False without "
                "contract-funded edge"
            )
        with self._lock:
            self._plans += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "llama_cpp_url": self.cfg.llama_cpp_url,
                "litellm_url": self.cfg.litellm_url,
                "model": self.cfg.model,
                "allow_live": self.cfg.allow_live,
                "plans": self._plans,
                "last": dict(self._last),
            }


def build_offline_gateway(
    cfg: Optional[Mapping[str, Any] | OfflineGatewayConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[OfflineGatewayPlanner]:
    if isinstance(cfg, OfflineGatewayConfig):
        resolved = cfg
    else:
        resolved = OfflineGatewayConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return OfflineGatewayPlanner(cfg=resolved)
