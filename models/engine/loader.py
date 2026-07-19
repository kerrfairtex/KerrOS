"""
models/engine/loader.py
=======================
Single source of truth for resolving the llama.cpp binary and model path.
Reads from .env (via python-dotenv) with fallback to config.json.

Install dep once in Termux:
    pip install python-dotenv
"""

import os
import sys
import json
from pathlib import Path

# ── Project root (offline_ai/) ────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[2]   # models/engine/ → models/ → offline_ai/
ENV_FILE = BASE / ".env"
CONFIG_FILE = BASE / "config.json"

# ── Try to load .env ──────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


def _load_config() -> dict:
    """Load config.json as fallback values."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _resolve_binary() -> str:
    """
    Resolve llama.cpp binary path.
    Priority: LLAMA_BIN env var → config.json llama_bin → auto-detect common paths.
    """
    # 1. From .env
    env_bin = os.environ.get("LLAMA_BIN", "").strip()
    if env_bin and Path(env_bin).exists():
        return env_bin

    # 2. From config.json (bin name only, search common dirs)
    cfg = _load_config()
    bin_name = cfg.get("llama_bin", "")

    # 3. Config.json bin takes priority, then auto-detect
    candidates = [
        f"~/llama.cpp/build/bin/{bin_name}" if bin_name else "",
        f"~/llama.cpp/build/bin/llama-simple-chat",
        f"~/llama.cpp/build/bin/llama-cli",
        f"~/llama.cpp/build/bin/llama-simple",
    ]

    for c in candidates:
        if not c:
            continue
        resolved = Path(c).expanduser()
        if resolved.exists():
            return str(resolved)

    return ""   # Not found — caller must handle


def _resolve_model(prefer_light: bool = False) -> str:
    """
    Resolve model .gguf path.
    Priority: env var → config.json model_path.
    Set prefer_light=True to use the smaller/faster model.
    """
    cfg = _load_config()

    if prefer_light:
        env_key = "MODEL_LIGHT_PATH"
    else:
        env_key = "MODEL_PATH"

    env_path = os.environ.get(env_key, "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return str(p)

    # Fallback to config.json model_path
    cfg_path = cfg.get("model_path", "")
    if cfg_path:
        p = (BASE / cfg_path).expanduser()
        if p.exists():
            return str(p)

    return ""   # Not found


def _resolve_int(env_key: str, config_key: str, default: int) -> int:
    val = os.environ.get(env_key, "").strip()
    if val.isdigit():
        return int(val)
    cfg = _load_config()
    return int(cfg.get(config_key, default))


def _resolve_float(env_key: str, config_key: str, default: float) -> float:
    val = os.environ.get(env_key, "").strip()
    try:
        return float(val)
    except (ValueError, TypeError):
        cfg = _load_config()
        try:
            return float(cfg.get(config_key, default))
        except (ValueError, TypeError):
            return default


# ── Public API ────────────────────────────────────────────────────────────────

class ModelLoader:
    """
    Resolves and validates all paths and inference parameters.
    Raises clear errors so engine.py never runs with broken config.

    Usage:
        from models.engine.loader import ModelLoader
        loader = ModelLoader()
        loader.validate()           # call once at startup
        print(loader.binary)
        print(loader.model)
    """

    def __init__(self, prefer_light: bool = False):
        self.binary: str = _resolve_binary()
        self.model: str = _resolve_model(prefer_light=prefer_light)

        # Inference params
        self.threads: int       = _resolve_int("THREADS",       "threads",       4)
        self.context_size: int  = _resolve_int("CONTEXT_SIZE",  "context_size",  2048)
        self.max_tokens: int    = _resolve_int("MAX_TOKENS",    "max_tokens",    256)
        self.temperature: float = _resolve_float("TEMPERATURE", "temperature",   0.7)
        self.repeat_penalty: float = _resolve_float(
            "REPEAT_PENALTY", "repeat_penalty", 1.1
        )
        self.repeat_last_n: int = _resolve_int(
            "REPEAT_LAST_N", "repeat_last_n", 64
        )

        # Safe commands for shell passthrough
        cfg = _load_config()
        self.safe_commands: list = cfg.get("safe_commands", [])

        # Online fallback
        self.groq_api_key: str  = os.environ.get("GROQ_API_KEY", "")
        self.online_model: str  = os.environ.get("ONLINE_MODEL",
                                    cfg.get("online_model", "llama-3.3-70b-versatile"))

    def validate(self) -> None:
        """
        Hard-fail with a clear message if binary or model is missing.
        Call this once at startup before any inference.
        """
        errors = []

        if not self.binary:
            errors.append(
                "[Loader] llama.cpp binary not found.\n"
                "  → Set LLAMA_BIN in .env, e.g.:\n"
                "    LLAMA_BIN=~/llama.cpp/build/bin/llama-simple-chat\n"
                "  → Or build llama.cpp:\n"
                "    cd ~/llama.cpp && cmake -B build && cmake --build build -j4"
            )
        elif not Path(self.binary).exists():
            errors.append(
                f"[Loader] Binary path set but file missing: {self.binary}\n"
                "  → Check LLAMA_BIN in .env"
            )

        if not self.model:
            errors.append(
                "[Loader] Model .gguf not found.\n"
                "  → Set MODEL_PATH in .env, e.g.:\n"
                "    MODEL_PATH=~/offline_ai/models/model.gguf"
            )
        elif not Path(self.model).exists():
            errors.append(
                f"[Loader] Model path set but file missing: {self.model}\n"
                "  → Check MODEL_PATH in .env"
            )

        if errors:
            print("\n".join(errors), file=sys.stderr)
            sys.exit(1)

    def status(self) -> dict:
        """Return a dict summary for debugging."""
        return {
            "binary":        self.binary or "NOT FOUND",
            "model":         self.model  or "NOT FOUND",
            "threads":       self.threads,
            "context_size":  self.context_size,
            "max_tokens":    self.max_tokens,
            "temperature":   self.temperature,
            "repeat_penalty":self.repeat_penalty,
            "groq_configured": bool(self.groq_api_key),
            "dotenv_loaded": _DOTENV_AVAILABLE,
        }


# ── Quick CLI check ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    loader = ModelLoader()
    print("=== ModelLoader Status ===")
    for k, v in loader.status().items():
        print(f"  {k:<20} {v}")
    loader.validate()
    print("\n[OK] All paths resolved. Ready for inference.")


# ── Cloud/remote API provider registry (api_config.yaml) ──────────────────────
API_CONFIG_FILE = BASE / "api_config.yaml"


def load_api_config() -> dict:
    """Load cloud/remote provider registry (api_config.yaml)."""
    import yaml
    if API_CONFIG_FILE.exists():
        with open(API_CONFIG_FILE) as f:
            return yaml.safe_load(f)
    return {}


def resolve_provider(name: str) -> dict:
    """Get {env, base_url, value} for one provider, reading the key from os.environ."""
    cfg = load_api_config()
    for category in ("llm_cloud", "llm_local"):
        if name in cfg.get(category, {}):
            entry = dict(cfg[category][name])
            key_or_endpoint = os.environ.get(entry.get("env"), entry.get("default"))
            entry["value"] = key_or_endpoint
            return entry
    return {}
