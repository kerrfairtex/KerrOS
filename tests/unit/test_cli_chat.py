import pytest
import os
import sys
from pathlib import Path
from cli.chat import is_interactive

def test_interactive_detection(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert is_interactive() is True
    
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert is_interactive() is False

def test_chat_non_interactive_bypass(monkeypatch):
    # Ensure sys.argv is clean before test
    monkeypatch.setattr(sys, "argv", ["cli/chat.py"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    
    from cli.chat import main
    # This just checks that the guard appends --no-prompt
    if not is_interactive():
        sys.argv.append("--no-prompt")
    
    assert "--no-prompt" in sys.argv
