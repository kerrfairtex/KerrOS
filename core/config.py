"""
core/config.py
==============
Single source of truth for local configuration.

The local agent does not require a .env file. Paths and runtime settings come
from config.json; already-exported environment variables remain available as
overrides. Optional provider integrations may load .env themselves.
"""
import os
import json
import argparse
from pathlib import Path

def _detect_base():
    env_base = os.environ.get("KERROS_BASE") or os.environ.get("OFFLINE_AI_BASE")
    if env_base:
        return Path(env_base).expanduser().resolve()
    repo = Path(__file__).resolve().parent.parent
    if (repo / "config.json").exists():
        return repo.resolve()
    raise RuntimeError(
        "Cannot detect KerrOS project base. Set KERROS_BASE or OFFLINE_AI_BASE, "
        "or run from a directory containing config.json."
    )

BASE = _detect_base()

def load():
    cfg_path = BASE / "config.json"
    with open(cfg_path) as f:
        c = json.load(f)

    overrides = {
        "llama_bin": os.getenv("LLAMA_BIN"),
        "model_path": os.getenv("MODEL_PATH"),
        "model_light": os.getenv("MODEL_LIGHT_PATH"),
        "threads": os.getenv("THREADS"),
        "context_size": os.getenv("CONTEXT_SIZE"),
        "max_tokens": os.getenv("MAX_TOKENS"),
        "temperature": os.getenv("TEMPERATURE"),
        "groq_api_key": os.getenv("GROQ_API_KEY"),
        "online_model": os.getenv("ONLINE_MODEL"),
        "fallback_model": os.getenv("FALLBACK_MODEL"),
    }
    for k, v in overrides.items():
        if v:
            c[k] = int(v) if k in ("threads", "context_size", "max_tokens") else v

    return c

def load_cli(argv=None):
    """Load config with CLI argument overrides."""
    cfg = load()
    
    parser = argparse.ArgumentParser(description="Offline AI chat")
    parser.add_argument("--model-path", help="Path to .gguf model")
    parser.add_argument("--binary-path", help="Path to llama.cpp binary")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--log-level", default=None, help="Log level: DEBUG, INFO, WARNING")
    parser.add_argument("--db-path", help="Path to SQLite database")
    parser.add_argument("--allowed-base-dir", help="Allowed base directory for file operations")
    
    args, _ = parser.parse_known_args(argv)
    
    if args.model_path:
        cfg["model_path"] = args.model_path
    if args.binary_path:
        cfg["llama_bin"] = args.binary_path
    if args.debug:
        cfg["debug"] = True
    if args.log_level:
        cfg["log_level"] = args.log_level.upper()
    if args.db_path:
        cfg["db_path"] = args.db_path
    if args.allowed_base_dir:
        cfg["allowed_base_dir"] = args.allowed_base_dir
    
    return cfg

_cfg = None
def cfg():
    global _cfg
    if _cfg is None:
        _cfg = load()
    return _cfg

def safe_abs_path(path: str, base_dir: str | None = None) -> str:
    """
    Resolve a path to an absolute, canonical form.
    If base_dir is provided, ensure the path is within base_dir.
    If the path is a symlink to a non-existent location,
    raise an informative error.
    """
    from core.utils import safe_abs_path as _safe_abs_path
    
    if base_dir is not None:
        return str(_safe_abs_path(path, base_dir))
    
    abs_path = Path(path).expanduser().resolve()
    if not abs_path.exists():
        raise FileNotFoundError(f"Required path does not exist: {abs_path}")
    return str(abs_path)
