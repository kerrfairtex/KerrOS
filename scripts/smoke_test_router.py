#!/usr/bin/env python3
"""
scripts/smoke_test_router.py
=============================
Run this after placing the 5 patch files + the new adaptive_engine.py to
confirm the wiring actually works before trusting it in the REPL.

Usage:
    cd ~/offline_ai   # repo root
    python3 scripts/smoke_test_router.py
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/offline_ai"))

def check(label, fn):
    try:
        fn()
        print(f"  [ OK ] {label}")
        return True
    except Exception as e:
        print(f"  [FAIL] {label}: {e}")
        return False

ok = True

ok &= check("import core.router.Router", lambda: __import__("core.router", fromlist=["Router"]))
ok &= check("import adapters.llm.openrouter_adapter", lambda: __import__("adapters.llm.openrouter_adapter", fromlist=["OpenRouterAdapter"]))
ok &= check("import core.context_builder", lambda: __import__("core.context_builder", fromlist=["ContextBuilder"]))
ok &= check("config/openrouter_tiers.yaml parses", lambda: __import__("yaml").safe_load(open(os.path.expanduser("~/offline_ai/config/openrouter_tiers.yaml"))))

def _key_check():
    from adapters.llm.openrouter_adapter import OpenRouterAdapter
    a = OpenRouterAdapter()
    if not a.available():
        raise RuntimeError("OPENROUTER_API_KEY not set or empty — see .env")
ok &= check("OPENROUTER_API_KEY present", _key_check)

def _live_call():
    from core.router import Router
    r = Router()
    reply = r.generate("Reply with just the word OK.", max_tokens=10)
    print(f"         provider used: {r.last_provider}")
    print(f"         reply: {reply[:120]!r}")
    if not reply or reply.startswith("[router]"):
        raise RuntimeError(f"no usable reply: {reply}")
ok &= check("live end-to-end generate()", _live_call)

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED — see [FAIL] lines above")
sys.exit(0 if ok else 1)
