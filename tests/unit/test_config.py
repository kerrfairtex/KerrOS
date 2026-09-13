import pytest
from pathlib import Path
from core.config import safe_abs_path

def test_safe_abs_path_blocks_escape(tmp_path):
    with pytest.raises(ValueError, match="escapes base directory"):
        safe_abs_path("../etc/passwd", str(tmp_path))

def test_safe_abs_path_allows_relative_within_base(tmp_path):
    result = safe_abs_path("model.gguf", str(tmp_path))
    assert result == str((tmp_path / "model.gguf").resolve())

def test_safe_abs_path_allows_absolute_within_base(tmp_path):
    target = tmp_path / "data" / "model.gguf"
    result = safe_abs_path(str(target), str(tmp_path))
    assert result == str(target.resolve())

def test_safe_abs_path_blocks_absolute_outside(tmp_path):
    with pytest.raises(ValueError, match="escapes base directory"):
        safe_abs_path("/etc/passwd", str(tmp_path))

def test_safe_abs_path_nonexistent_path(tmp_path):
    result = safe_abs_path("nonexistent/file.gguf", str(tmp_path))
    assert result == str((tmp_path / "nonexistent" / "file.gguf").resolve())
