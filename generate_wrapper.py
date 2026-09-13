#!/usr/bin/env python3
"""
Generate wrapper modules that expose the unified `execute()` / `help()` interface
for every legacy tool in adapters/tools/ and tools/.
"""

import importlib.util
import os
import sys
import textwrap
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_DIR = Path('/data/data/com.termux/files/home/offline_ai')
LEGACY_DIRS = [
    BASE_DIR / "adapters" / "tools",
    BASE_DIR / "tools",
]
WRAPPER_DIR = BASE_DIR / "wrapped_tools"
WRAPPER_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def load_module(path: Path):
    """Return a module object for the given .py file, or None on failure."""
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        print(f"[!] Cannot load spec for {path}", file=sys.stderr)
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"[!] Error loading {path}: {e}", file=sys.stderr)
        return None
    return module


def make_execute_call(module, path: Path):
    """Return a string of Python code that calls the original tool."""
    if hasattr(module, "run") and callable(module.run):
        return "return module.run(*args, **kwargs)"
    if hasattr(module, "main") and callable(module.main):
        return "return module.main(*args, **kwargs)"

    script = str(path.resolve())
    return textwrap.dedent(
        f"""
        import subprocess
        cmd = ['{sys.executable}', '{script}'] + list(map(str, args))
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
        """
    ).strip()


def make_help(module):
    """Return a string that yields a helpful description."""
    doc = getattr(module, "__doc__", None)
    return f"return {repr(doc) if doc else 'No help available'}"


def write_wrapper(tool_path: Path):
    """Create a wrapper module for the given tool."""
    module = load_module(tool_path)
    if module is None:
        return

    wrapper_name = f"{tool_path.stem}_wrapper"
    wrapper_file = WRAPPER_DIR / f"{wrapper_name}.py"

    # Generate function bodies with explicit indentation
    exec_body = textwrap.indent(textwrap.dedent(make_execute_call(module, tool_path)), '    ')
    help_body = textwrap.indent(textwrap.dedent(make_help(module)), '    ')

    wrapper_src = f"""
# Auto-generated wrapper for {tool_path.name}
# Original module: {tool_path}

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("{tool_path.stem}", "{tool_path.resolve()}")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: {tool_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
{exec_body}

def help():
{help_body}
    """

    with open(wrapper_file, "w", encoding="utf-8") as f:
        f.write(wrapper_src.strip() + "\n")

    print(f"[✓] Wrapper created: {wrapper_file}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for d in LEGACY_DIRS:
        if not d.exists():
            continue
        for file in d.glob("*.py"):
            if file.name == "__init__.py":
                continue
            write_wrapper(file)

    print("✅ All wrappers generated.")
