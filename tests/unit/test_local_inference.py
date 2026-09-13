"""Regression tests for the local llama.cpp inference path."""

from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from models.engine.generator import Generator


ROOT = Path(__file__).resolve().parents[2]


def _loader() -> SimpleNamespace:
    return SimpleNamespace(
        binary="llama-cli",
        model="model.gguf",
        threads=1,
        context_size=128,
        max_tokens=16,
        temperature=0.2,
        repeat_penalty=1.1,
        repeat_last_n=64,
    )


def test_llama_cli_command_does_not_use_unsupported_stop_flags() -> None:
    cmd = Generator(_loader())._build_cmd("test prompt")

    assert "--stop" not in cmd
    assert "--no-display-prompt" in cmd
    assert "--single-turn" in cmd
    assert cmd[-2:] == ["-p", "test prompt"]


def test_llama_cli_nonzero_exit_is_not_silently_treated_as_empty_reply() -> None:
    proc = Mock()
    proc.communicate.return_value = ("", "error: invalid argument: --stop")
    generator = Generator(_loader())

    with patch("models.engine.generator.subprocess.Popen", return_value=proc):
        result = generator.generate("test prompt", stream=False)

    assert "exited with code 1" in result
    assert "invalid argument: --stop" in result


def test_dotenv_load_has_no_parse_warnings() -> None:
    from dotenv import load_dotenv

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_dotenv(ROOT / ".env")

    parse_warnings = [
        item for item in caught
        if "python-dotenv could not parse" in str(item.message)
    ]
    assert parse_warnings == []


def test_direct_chat_script_imports_before_prompt() -> None:
    env = os.environ.copy()
    env["CI"] = "1"
    result = subprocess.run(
        [sys.executable, "cli/chat.py"],
        cwd=ROOT,
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
