import pytest
import subprocess
from execution.executor import SandboxExecutor, restricted_run


def test_safe_ls():
    executor = SandboxExecutor()
    output = executor.run(["ls", "-la"])
    assert output is not None


def test_blocked_command():
    executor = SandboxExecutor()
    with pytest.raises(ValueError, match="not in allowlist"):
        executor.run(["rm", "-rf", "/"])


def test_timeout():
    executor = SandboxExecutor(timeout=1)
    with pytest.raises(RuntimeError, match="timed out"):
        executor.run(["sleep", "5"])


def test_empty_command():
    executor = SandboxExecutor()
    with pytest.raises(ValueError):
        executor.run([])


def test_non_string_command_rejected():
    executor = SandboxExecutor()
    with pytest.raises((TypeError, ValueError)):
        executor.run(None)


def test_restricted_run_blocked():
    result = restricted_run(["rm", "-rf", "/"])
    assert result["code"] == 2
    assert "allowlist" in result.get("error", "").lower() or "blocked" in result.get("error", "").lower() or "not" in result.get("error", "").lower()


def test_restricted_run_timeout():
    result = restricted_run(["sleep", "5"], timeout=1)
    assert result["code"] == 1
    assert "timed out" in result.get("error", "").lower() or "timeout" in result.get("error", "").lower()
