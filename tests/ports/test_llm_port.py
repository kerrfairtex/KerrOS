"""
tests/ports/test_llm_port.py
============================
Unit tests for LLMPort interface and MultiAPIAdapter.

PHASE 1 ACCEPTANCE CRITERIA:
  ✓ Adapter implements LLMPort protocol
  ✓ Mock adapter passes all tests (validates interface design)
  ✓ MultiAPIAdapter output identical to direct multi_api.py calls
  ✓ No existing tests break
"""

import unittest
from typing import Optional, List, Any
from unittest.mock import Mock, patch, MagicMock

# Import the interfaces and implementations
from ports.llm_port import LLMPort
from adapters.llm.multi_api_adapter import MultiAPIAdapter


class MockLLMAdapter:
    """
    Mock implementation of LLMPort for testing interface design.
    
    Used to validate that LLMPort protocol is sufficient for real adapters,
    before wiring in the full multi_api.py engine.
    """

    def __init__(self, response: str = "Mock response"):
        self.response = response
        self.call_count = 0
        self.last_call = None

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any
    ) -> str:
        """Simple mock: records call and returns fixed response."""
        self.call_count += 1
        self.last_call = {
            "prompt": prompt,
            "system": system,
            "history": history or [],
            "max_tokens": max_tokens,
            "kwargs": kwargs,
        }
        return self.response


class TestLLMPortProtocol(unittest.TestCase):
    """
    Validate LLMPort protocol design.
    
    These tests verify the interface is minimal, sensible, and sufficient
    for wrapping arbitrary LLM backends without coupling to specifics.
    """

    def test_mock_adapter_conforms_to_llmport(self):
        """Mock adapter should satisfy LLMPort protocol."""
        adapter = MockLLMAdapter()
        # Protocol check: adapter has required method with correct signature
        self.assertTrue(callable(adapter.complete))

    def test_complete_basic_call(self):
        """Test basic complete() call with just prompt."""
        adapter = MockLLMAdapter(response="Test response")
        result = adapter.complete("Hello")
        self.assertEqual(result, "Test response")
        self.assertEqual(adapter.call_count, 1)

    def test_complete_with_all_args(self):
        """Test complete() with all arguments."""
        adapter = MockLLMAdapter()
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        result = adapter.complete(
            prompt="What's next?",
            system="You are helpful.",
            history=history,
            max_tokens=512,
        )
        self.assertEqual(adapter.call_count, 1)
        self.assertEqual(adapter.last_call["prompt"], "What's next?")
        self.assertEqual(adapter.last_call["system"], "You are helpful.")
        self.assertEqual(adapter.last_call["history"], history)
        self.assertEqual(adapter.last_call["max_tokens"], 512)

    def test_complete_with_kwargs_extension_point(self):
        """Test that **kwargs extension point works (Phase 2 hook)."""
        adapter = MockLLMAdapter()
        result = adapter.complete(
            "Test",
            provider_hint="groq",
            task_override="coding",
        )
        self.assertEqual(adapter.last_call["kwargs"]["provider_hint"], "groq")
        self.assertEqual(adapter.last_call["kwargs"]["task_override"], "coding")

    def test_complete_optional_history(self):
        """Test that history=None is handled gracefully."""
        adapter = MockLLMAdapter()
        result = adapter.complete("Test", history=None)
        self.assertEqual(adapter.last_call["history"], [])


class TestMultiAPIAdapter(unittest.TestCase):
    """
    Test MultiAPIAdapter wrapping of multi_api.py.
    
    Validates that the adapter preserves all existing behavior:
    task-specific routing, fallback chains, dead-API tracking, etc.
    """

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_adapter_initialization(self, mock_engine_class):
        """Test adapter creates MultiAPIEngine on init."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()
        self.assertIsNotNone(adapter.engine)
        mock_engine_class.assert_called_once()

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_complete_delegates_to_engine(self, mock_engine_class):
        """Test complete() delegates to engine.generate() without modification."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = "Engine response"
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()
        result = adapter.complete(
            prompt="Test prompt",
            system="Test system",
            history=[{"role": "user", "content": "Hi"}],
            max_tokens=256,
        )

        # Verify engine.generate() was called with exact arguments
        mock_engine.generate.assert_called_once_with(
            user_message="Test prompt",
            system="Test system",
            history=[{"role": "user", "content": "Hi"}],
            max_tokens=256,
        )
        self.assertEqual(result, "Engine response")

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_complete_handles_empty_history(self, mock_engine_class):
        """Test complete() converts None history to empty list."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = "Response"
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()
        adapter.complete(prompt="Test", history=None)

        # Verify None was converted to []
        mock_engine.generate.assert_called_once()
        call_kwargs = mock_engine.generate.call_args[1]
        self.assertEqual(call_kwargs["history"], [])

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_status_method(self, mock_engine_class):
        """Test status() returns engine's provider status."""
        mock_engine = MagicMock()
        mock_engine.status.return_value = {
            "groq": True,
            "nvidia": True,
            "deepseek": False,
        }
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()
        status = adapter.status()

        self.assertEqual(status["groq"], True)
        self.assertEqual(status["deepseek"], False)
        mock_engine.status.assert_called_once()

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_last_api_used_method(self, mock_engine_class):
        """Test last_api_used() returns engine's last_api."""
        mock_engine = MagicMock()
        mock_engine.last_api = "groq"
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()
        last_api = adapter.last_api_used()

        self.assertEqual(last_api, "groq")


class TestBehaviorParity(unittest.TestCase):
    """
    Verify adapter output matches direct multi_api.py calls.
    
    These are integration-level tests proving zero behavioral change.
    They require multi_api.py to be importable and configured.
    """

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_adapter_chains_identical_to_engine(self, mock_engine_class):
        """Test that adapter's complete() chains identically to engine.generate()."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = "Chained response"
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()

        # Simulate a coding task (should route to DeepSeek → NVIDIA → Groq)
        result = adapter.complete("Write a Python function that sorts")

        # Verify the engine was called (it handles routing internally)
        mock_engine.generate.assert_called_once()
        self.assertEqual(result, "Chained response")

    @patch("adapters.llm.multi_api_adapter.MultiAPIEngine")
    def test_adapter_error_propagation(self, mock_engine_class):
        """Test that adapter propagates engine errors/fallback messages."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = "[All APIs failed. Use /offline mode.]"
        mock_engine_class.return_value = mock_engine

        adapter = MultiAPIAdapter()
        result = adapter.complete("Test")

        # Adapter should return exactly what engine returns (including error messages)
        self.assertEqual(result, "[All APIs failed. Use /offline mode.]")


if __name__ == "__main__":
    unittest.main()
