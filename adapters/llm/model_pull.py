"""
adapters/llm/model_pull.py
==========================
Automated local-LLM model pull foundation (C-19 / ADR-049).

Default-off. Fake-records pull intent envelopes. Soft ``ollama pull`` /
``huggingface-cli`` only when ``allow_pull`` and the tool is present.
``provisioned_production`` stays False — weights remain operator-owned.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class ModelPullError(RuntimeError):
    """Model pull planning / soft pull failed."""


def ollama_available() -> bool:
    return bool(shutil.which("ollama"))


def huggingface_cli_available() -> bool:
    return bool(shutil.which("huggingface-cli"))


@dataclass
class ModelPullConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | ollama | hf
    models: list[str] = field(default_factory=lambda: ["llama3.2"])
    allow_pull: bool = False
    timeout_s: float = 120.0

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "ModelPullConfig":
        _ = base
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_MODEL_PULL")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_MODEL_PULL_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        models_raw = data.get("models")
        env_m = os.environ.get("KERROS_MODEL_PULL_MODELS")
        if env_m is not None:
            models = [m.strip() for m in env_m.split(",") if m.strip()]
        elif isinstance(models_raw, Sequence) and not isinstance(
            models_raw, (str, bytes)
        ):
            models = [str(m).strip() for m in models_raw if str(m).strip()]
        else:
            models = ["llama3.2"]

        allow_pull = data.get("allow_pull", False)
        env_p = os.environ.get("KERROS_MODEL_PULL_ALLOW")
        if env_p is not None:
            allow_pull = _truthy(env_p)
        else:
            allow_pull = _truthy(allow_pull)

        timeout_s = data.get("timeout_s", 120.0)
        env_t = os.environ.get("KERROS_MODEL_PULL_TIMEOUT")
        if env_t is not None:
            try:
                timeout_s = float(env_t)
            except ValueError:
                timeout_s = 120.0
        else:
            try:
                timeout_s = float(timeout_s)
            except (TypeError, ValueError):
                timeout_s = 120.0

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            models=list(models) or ["llama3.2"],
            allow_pull=bool(allow_pull),
            timeout_s=max(1.0, float(timeout_s)),
        )


@dataclass
class ModelPullService:
    """Plan or soft-execute local LLM model pulls."""

    cfg: ModelPullConfig
    _pulls: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def plan(self, model: Optional[str] = None) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise ModelPullError("model pull disabled")
        targets = [model] if model else list(self.cfg.models)
        targets = [t for t in targets if t]
        out = {
            "ok": True,
            "backend": self.cfg.backend,
            "models": targets,
            "status": "planned",
            "provisioned_production": False,
            "dry_run": True,
            "note": "Fake pull intent — weights not downloaded",
            "at": time.time(),
        }
        with self._lock:
            self._pulls += 1
            self._last = dict(out)
        return out

    def pull(self, model: Optional[str] = None) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise ModelPullError("model pull disabled")
        targets = [model] if model else list(self.cfg.models)
        targets = [t for t in targets if t]
        if not self.cfg.allow_pull or self.cfg.backend == "fake":
            out = {
                "ok": True,
                "backend": self.cfg.backend,
                "models": targets,
                "status": "planned",
                "provisioned_production": False,
                "dry_run": True,
                "note": "Pull gated/Fake — set allow_pull + backend=ollama|hf",
                "at": time.time(),
            }
            with self._lock:
                self._pulls += 1
                self._last = dict(out)
            return out

        results: list[dict[str, Any]] = []
        for target in targets:
            if self.cfg.backend == "ollama":
                if not ollama_available():
                    raise ModelPullError("ollama binary not found")
                cmd = ["ollama", "pull", target]
            elif self.cfg.backend == "hf":
                if not huggingface_cli_available():
                    raise ModelPullError("huggingface-cli not found")
                cmd = ["huggingface-cli", "download", target]
            else:
                raise ModelPullError(f"unknown backend: {self.cfg.backend}")
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.cfg.timeout_s,
                    check=False,
                )
                results.append(
                    {
                        "model": target,
                        "ok": proc.returncode == 0,
                        "returncode": proc.returncode,
                        "stdout_tail": (proc.stdout or "")[-400:],
                        "stderr_tail": (proc.stderr or "")[-400:],
                    }
                )
            except subprocess.TimeoutExpired as exc:
                raise ModelPullError(f"pull timed out: {target}") from exc

        out = {
            "ok": all(r.get("ok") for r in results),
            "backend": self.cfg.backend,
            "models": targets,
            "status": "soft_pulled" if results else "empty",
            "results": results,
            "provisioned_production": False,
            "dry_run": False,
            "note": (
                "Soft pull executed — provisioned_production stays False "
                "(operator-owned weights / contract gate)"
            ),
            "at": time.time(),
        }
        with self._lock:
            self._pulls += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "models": list(self.cfg.models),
                "allow_pull": self.cfg.allow_pull,
                "ollama": ollama_available(),
                "huggingface_cli": huggingface_cli_available(),
                "pulls": self._pulls,
                "last": dict(self._last),
            }


def build_model_pull(
    cfg: Optional[Mapping[str, Any] | ModelPullConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[ModelPullService]:
    if isinstance(cfg, ModelPullConfig):
        resolved = cfg
    else:
        resolved = ModelPullConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return ModelPullService(cfg=resolved)
