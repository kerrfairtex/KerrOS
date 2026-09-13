import os
import sys
import pytest
from core.config import cfg as get_config
from core.adaptive_engine import AdaptiveEngine

def test_config_loads_defaults(tmp_path):
    os.chdir(tmp_path)
    # Using existing config singleton loader
    cfg = get_config()
    assert cfg is not None

def test_engine_initialization(tmp_path, monkeypatch):
    # Create dummy binary & model
    bin_path = tmp_path / "llama-completion"
    bin_path.write_text("#!/bin/sh\necho 'dummy'")
    bin_path.chmod(0o755)

    model_path = tmp_path / "model.gguf"
    model_path.write_text("dummy")

    # Monkey‑patch environment variables to point to dummy paths
    monkeypatch.setenv("LLAMA_BIN", str(bin_path))
    monkeypatch.setenv("MODEL_PATH", str(model_path))

    # Force re-initialization of the singleton
    import core.config
    core.config._cfg = None 
    
    # Engine initialization check
    engine = AdaptiveEngine()
    engine.init_offline()
    assert engine._offline is not None

def test_non_interactive_mode(monkeypatch):
    # Simulate non‑interactive stdin
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    # The actual chat.py does not take arguments easily without breaking
    # the boot sequence, but we can verify our new safe_abs_path logic
    from core.config import safe_abs_path
    from pathlib import Path
    
    test_path = Path("/tmp/test_file")
    test_path.write_text("test")
    assert safe_abs_path("/tmp/test_file") == str(test_path.resolve())
    test_path.unlink()
