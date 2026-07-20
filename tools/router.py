"""
Deprecation shim — kernel/router.py is now the canonical location (KOS-004).
Re-exports the same names so existing `from tools.router import ...` call
sites keep working without changes. New code should import from
kernel.router directly.
"""
from kernel.router import detect_tool, run_tool, detect_domain
