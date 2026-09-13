import pytest
import json
import logging
import io
import sys
from core.logger import init_logging, get_logger

def test_json_logging(capsys):
    init_logging(debug=True)
    logger = get_logger("test_module")
    
    # Test capture
    test_msg = "test log message"
    logger.info(test_msg)
    
    captured = capsys.readouterr()
    log_json = json.loads(captured.out)
    
    assert log_json["message"] == test_msg
    assert log_json["level"] == "INFO"
    assert "timestamp" in log_json

def test_debug_level(capsys):
    init_logging(debug=True)
    logger = get_logger("debug_test")
    logger.debug("debug_message")
    
    captured = capsys.readouterr()
    log_json = json.loads(captured.out)
    assert log_json["level"] == "DEBUG"

def test_extra_fields(capsys):
    init_logging(debug=True)
    logger = get_logger("extra_test")
    logger.info("message", extra={"extra": {"key": "value"}})
    
    captured = capsys.readouterr()
    log_json = json.loads(captured.out)
    assert log_json["extra"]["key"] == "value"
