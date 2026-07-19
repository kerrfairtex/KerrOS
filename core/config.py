"""
core/config.py
==============
Single source of truth for all configuration.
Loads .env first, then config.json, env vars win.
"""
import os, json
from pathlib import Path

BASE = Path(os.path.expanduser("~/offline_ai"))

def load():
    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE / ".env")
    except ImportError:
        pass

    # Load config.json as base
    cfg_path = BASE / "config.json"
    with open(cfg_path) as f:
        c = json.load(f)

    # .env overrides config.json
    overrides = {
        "llama_bin":      os.getenv("LLAMA_BIN"),
        "model_path":     os.getenv("MODEL_PATH"),
        "model_light":    os.getenv("MODEL_LIGHT_PATH"),
        "threads":        os.getenv("THREADS"),
        "context_size":   os.getenv("CONTEXT_SIZE"),
        "max_tokens":     os.getenv("MAX_TOKENS"),
        "temperature":    os.getenv("TEMPERATURE"),
        "groq_api_key":   os.getenv("GROQ_API_KEY"),
        "online_model":   os.getenv("ONLINE_MODEL"),
        "fallback_model": os.getenv("FALLBACK_MODEL"),
    }
    for k,v in overrides.items():
        if v: c[k] = int(v) if k in ("threads","context_size","max_tokens") else v

    return c

# Singleton
_cfg = None
def cfg():
    global _cfg
    if _cfg is None: _cfg = load()
    return _cfg
