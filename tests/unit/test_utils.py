import pytest
from core.utils import safe_abs_path

def test_safe_abs_path_within_base(tmp_path):
    base = str(tmp_path)
    result = safe_abs_path("model.gguf", base)
    assert str(result) == str(tmp_path / "model.gguf")

def test_safe_abs_path_escape(tmp_path):
    base = str(tmp_path)
    with pytest.raises(ValueError, match="escapes base directory"):
        safe_abs_path("../etc/passwd", base)

def test_safe_abs_path_absolute_within_base(tmp_path):
    base = str(tmp_path)
    target = tmp_path / "subdir" / "model.gguf"
    result = safe_abs_path(str(target), base)
    assert str(result) == str(target.resolve())

def test_safe_abs_path_absolute_escape(tmp_path):
    base = str(tmp_path)
    with pytest.raises(ValueError, match="escapes base directory"):
        safe_abs_path("/etc/passwd", base)

def test_safe_abs_path_nonexistent_parent(tmp_path):
    base = str(tmp_path)
    result = safe_abs_path("nonexistent/model.gguf", base)
    assert result.parent == (tmp_path / "nonexistent").resolve()
