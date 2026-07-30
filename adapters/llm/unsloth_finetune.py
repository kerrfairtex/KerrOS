"""
adapters/llm/unsloth_finetune.py
================================
Unsloth LoRA → merge → GGUF Q4_K_M export foundation (Phase D / ADR-053).

Default-off. Fake-plans train/export envelopes for CI. Soft Unsloth /
llama-quantize only when ``allow_train`` and tools are present.
``provisioned_production`` stays False — weights remain operator-owned.
Never downloads Unsloth or runs GPU in default CI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    import unsloth  # noqa: F401

    HAS_UNSLOTH = True
except ImportError:
    HAS_UNSLOTH = False


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class UnslothFinetuneError(RuntimeError):
    """Finetune / export planning failed."""


def llama_quantize_available() -> bool:
    for name in ("llama-quantize", "quantize"):
        if shutil.which(name):
            return True
    # Common llama.cpp build location
    home = Path.home() / "llama.cpp" / "build" / "bin" / "llama-quantize"
    return home.is_file()


def resolve_llama_quantize() -> str:
    for name in ("llama-quantize", "quantize"):
        found = shutil.which(name)
        if found:
            return found
    home = Path.home() / "llama.cpp" / "build" / "bin" / "llama-quantize"
    return str(home) if home.is_file() else ""


@dataclass
class UnslothFinetuneConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | unsloth
    method: str = "lora"
    base_model: str = "unsloth/Qwen2.5-0.5B-Instruct"
    dataset_path: str = "data/finetune/dataset.jsonl"
    output_dir: str = "data/finetune/lora_out"
    gguf_out: str = "models/qwen0.5b-q4.gguf"
    quant: str = "Q4_K_M"
    allow_train: bool = False
    allow_export: bool = False
    max_steps: int = 10

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "UnslothFinetuneConfig":
        data = dict(raw or {})
        # Merge offline profile finetune block when active.
        try:
            from adapters.llm.offline_profile import (
                is_offline_profile_active,
                load_offline_profile,
            )

            if is_offline_profile_active(data):
                profile = load_offline_profile(cfg=data)
                ft = profile.get("finetune") if isinstance(profile, dict) else None
                if isinstance(ft, dict):
                    merged = dict(ft)
                    merged.update({k: v for k, v in data.items() if v not in (None, "")})
                    data = merged
        except Exception:
            pass

        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_FINETUNE")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_FINETUNE_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or data.get("method") or "fake")
        if backend == "lora":
            backend = "unsloth"

        base_model = os.environ.get("KERROS_FINETUNE_BASE")
        if base_model is None:
            base_model = str(
                data.get("base_model") or "unsloth/Qwen2.5-0.5B-Instruct"
            )

        dataset = os.environ.get("KERROS_FINETUNE_DATASET")
        if dataset is None:
            dataset = str(data.get("dataset_path") or "data/finetune/dataset.jsonl")

        output_dir = os.environ.get("KERROS_FINETUNE_OUT")
        if output_dir is None:
            output_dir = str(data.get("output_dir") or "data/finetune/lora_out")

        gguf_out = os.environ.get("KERROS_FINETUNE_GGUF")
        if gguf_out is None:
            gguf_out = str(data.get("gguf_out") or data.get("gguf") or "models/qwen0.5b-q4.gguf")

        quant = os.environ.get("KERROS_FINETUNE_QUANT")
        if quant is None:
            quant = str(data.get("quant") or "Q4_K_M")

        allow_train = data.get("allow_train", False)
        env_t = os.environ.get("KERROS_FINETUNE_ALLOW_TRAIN")
        if env_t is not None:
            allow_train = _truthy(env_t)
        else:
            allow_train = _truthy(allow_train)

        allow_export = data.get("allow_export", False)
        env_e = os.environ.get("KERROS_FINETUNE_ALLOW_EXPORT")
        if env_e is not None:
            allow_export = _truthy(env_e)
        else:
            allow_export = _truthy(allow_export)

        max_steps = data.get("max_steps", 10)
        env_s = os.environ.get("KERROS_FINETUNE_MAX_STEPS")
        if env_s is not None:
            try:
                max_steps = int(env_s)
            except ValueError:
                max_steps = 10
        else:
            try:
                max_steps = int(max_steps)
            except (TypeError, ValueError):
                max_steps = 10

        def _abs(p: str) -> str:
            path = Path(p).expanduser()
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            return str(path)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            method=str(data.get("method") or "lora"),
            base_model=str(base_model).strip(),
            dataset_path=_abs(dataset),
            output_dir=_abs(output_dir),
            gguf_out=_abs(gguf_out),
            quant=str(quant).strip() or "Q4_K_M",
            allow_train=bool(allow_train),
            allow_export=bool(allow_export),
            max_steps=max(1, int(max_steps)),
        )


@dataclass
class UnslothFinetuneService:
    """Plan or soft-execute Unsloth LoRA train + GGUF export."""

    cfg: UnslothFinetuneConfig
    _ops: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def plan(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise UnslothFinetuneError("finetune disabled")
        out = {
            "ok": True,
            "backend": self.cfg.backend,
            "method": self.cfg.method,
            "base_model": self.cfg.base_model,
            "dataset_path": self.cfg.dataset_path,
            "output_dir": self.cfg.output_dir,
            "gguf_out": self.cfg.gguf_out,
            "quant": self.cfg.quant,
            "max_steps": self.cfg.max_steps,
            "status": "planned",
            "steps": [
                "load_base",
                "attach_lora",
                "train",
                "merge",
                f"quantize_{self.cfg.quant}",
                "write_gguf",
            ],
            "has_unsloth": HAS_UNSLOTH,
            "has_llama_quantize": llama_quantize_available(),
            "provisioned_production": False,
            "dry_run": True,
            "note": "Fake finetune plan — no GPU train / no GGUF write",
            "at": time.time(),
        }
        with self._lock:
            self._ops += 1
            self._last = dict(out)
        return out

    def train(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise UnslothFinetuneError("finetune disabled")
        if (
            not self.cfg.allow_train
            or self.cfg.backend == "fake"
            or not HAS_UNSLOTH
        ):
            out = {
                "ok": True,
                "backend": self.cfg.backend,
                "status": "planned",
                "provisioned_production": False,
                "dry_run": True,
                "has_unsloth": HAS_UNSLOTH,
                "note": (
                    "Train gated/Fake — set allow_train + backend=unsloth "
                    "and install unsloth on a GPU host"
                ),
                "at": time.time(),
            }
            with self._lock:
                self._ops += 1
                self._last = dict(out)
            return out

        # Soft live path: write a marker + intent only unless a real trainer
        # hook is injected later. Avoid silent GPU jobs from CI misconfig.
        out_dir = Path(self.cfg.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        marker = out_dir / "TRAIN_INTENT.json"
        marker.write_text(
            json.dumps(
                {
                    "base_model": self.cfg.base_model,
                    "dataset_path": self.cfg.dataset_path,
                    "max_steps": self.cfg.max_steps,
                    "note": "soft train intent — operator must run Unsloth notebook/script",
                    "at": time.time(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        out = {
            "ok": True,
            "backend": "unsloth",
            "status": "soft_intent",
            "output_dir": str(out_dir),
            "marker": str(marker),
            "provisioned_production": False,
            "dry_run": False,
            "note": (
                "Soft Unsloth train intent written — full SFT loop stays "
                "operator-owned (notebook / funded GPU)"
            ),
            "at": time.time(),
        }
        with self._lock:
            self._ops += 1
            self._last = dict(out)
        return out

    def export(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise UnslothFinetuneError("finetune disabled")
        if not self.cfg.allow_export or self.cfg.backend == "fake":
            out = {
                "ok": True,
                "backend": self.cfg.backend,
                "status": "planned",
                "gguf_out": self.cfg.gguf_out,
                "quant": self.cfg.quant,
                "provisioned_production": False,
                "dry_run": True,
                "has_llama_quantize": llama_quantize_available(),
                "note": (
                    "Export gated/Fake — set allow_export + provide merged "
                    "weights / llama-quantize on operator host"
                ),
                "at": time.time(),
            }
            with self._lock:
                self._ops += 1
                self._last = dict(out)
            return out

        quant_bin = resolve_llama_quantize()
        gguf = Path(self.cfg.gguf_out)
        gguf.parent.mkdir(parents=True, exist_ok=True)
        if not quant_bin:
            # Soft: write export intent envelope instead of failing hard.
            intent = gguf.with_suffix(".export_intent.json")
            intent.write_text(
                json.dumps(
                    {
                        "gguf_out": str(gguf),
                        "quant": self.cfg.quant,
                        "note": "llama-quantize not found — intent only",
                        "at": time.time(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            out = {
                "ok": True,
                "backend": "soft",
                "status": "soft_intent",
                "intent": str(intent),
                "gguf_out": str(gguf),
                "provisioned_production": False,
                "dry_run": False,
                "note": "Export intent only — install llama-quantize to write GGUF",
                "at": time.time(),
            }
            with self._lock:
                self._ops += 1
                self._last = dict(out)
            return out

        # Soft quantize: only if an f16/source gguf already exists beside output.
        src_candidates = [
            Path(self.cfg.output_dir) / "merged-f16.gguf",
            Path(self.cfg.output_dir) / "model-f16.gguf",
        ]
        src = next((p for p in src_candidates if p.is_file()), None)
        if src is None:
            out = {
                "ok": True,
                "backend": "soft",
                "status": "awaiting_merged_f16",
                "gguf_out": str(gguf),
                "provisioned_production": False,
                "dry_run": False,
                "note": (
                    f"Place merged F16 GGUF at {src_candidates[0]} then re-run export"
                ),
                "at": time.time(),
            }
            with self._lock:
                self._ops += 1
                self._last = dict(out)
            return out

        try:
            proc = subprocess.run(
                [quant_bin, str(src), str(gguf), self.cfg.quant],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            out = {
                "ok": proc.returncode == 0 and gguf.is_file(),
                "backend": "llama-quantize",
                "status": "soft_exported" if proc.returncode == 0 else "failed",
                "gguf_out": str(gguf),
                "quant": self.cfg.quant,
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-400:],
                "provisioned_production": False,
                "dry_run": False,
                "note": (
                    "Soft GGUF write — provisioned_production stays False "
                    "(operator-owned weights / contract gate)"
                ),
                "at": time.time(),
            }
        except subprocess.TimeoutExpired as exc:
            raise UnslothFinetuneError("quantize timed out") from exc
        with self._lock:
            self._ops += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "method": self.cfg.method,
                "base_model": self.cfg.base_model,
                "gguf_out": self.cfg.gguf_out,
                "quant": self.cfg.quant,
                "allow_train": self.cfg.allow_train,
                "allow_export": self.cfg.allow_export,
                "has_unsloth": HAS_UNSLOTH,
                "has_llama_quantize": llama_quantize_available(),
                "ops": self._ops,
                "last": dict(self._last),
            }


def build_unsloth_finetune(
    cfg: Optional[Mapping[str, Any] | UnslothFinetuneConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[UnslothFinetuneService]:
    if isinstance(cfg, UnslothFinetuneConfig):
        resolved = cfg
    else:
        resolved = UnslothFinetuneConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return UnslothFinetuneService(cfg=resolved)
