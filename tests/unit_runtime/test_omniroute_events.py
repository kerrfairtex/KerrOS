"""OmniRoute X-OmniRoute-* cost/usage → EventBus (P3)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from adapters.llm.omniroute_telemetry import (
    OMNIROUTE_USAGE_TOPIC,
    has_omniroute_headers,
    parse_omniroute_headers,
    publish_omniroute_usage,
)
from adapters.llm.openai_compat import OpenAICompatClient
from kernel.boot import boot, shutdown
from runtime.event_bus import EventBus


SAMPLE_HEADERS = {
    "X-OmniRoute-Response-Cost": "0.0001234500",
    "X-OmniRoute-Tokens-In": "42",
    "X-OmniRoute-Tokens-Out": "7",
    "X-OmniRoute-Model": "gpt-4o-mini",
    "X-OmniRoute-Provider": "groq",
    "X-OmniRoute-Latency-Ms": "123.4",
    "X-OmniRoute-Cache-Hit": "false",
    "X-OmniRoute-Request-Id": "req-abc",
    "X-OmniRoute-Version": "3.8.49",
    "X-OmniRoute-Fallback-Attempts": "1",
}


class ParseHeadersTest(unittest.TestCase):
    def test_has_omniroute_headers(self):
        self.assertTrue(has_omniroute_headers(SAMPLE_HEADERS))
        self.assertFalse(has_omniroute_headers({"Content-Type": "application/json"}))

    def test_parse_typed_fields(self):
        payload = parse_omniroute_headers(SAMPLE_HEADERS)
        self.assertAlmostEqual(payload["cost_usd"], 0.00012345)
        self.assertEqual(payload["tokens_in"], 42)
        self.assertEqual(payload["tokens_out"], 7)
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["upstream_provider"], "groq")
        self.assertAlmostEqual(payload["latency_ms"], 123.4)
        self.assertFalse(payload["cache_hit"])
        self.assertEqual(payload["request_id"], "req-abc")
        self.assertEqual(payload["version"], "3.8.49")
        self.assertEqual(payload["fallback_attempts"], 1)

    def test_cache_hit_and_cost_saved(self):
        headers = {
            "X-OmniRoute-Response-Cost": "0.0000000000",
            "X-OmniRoute-Cache-Hit": "true",
            "X-OmniRoute-Cost-Saved": "0.0010000000",
            "X-OmniRoute-Cache": "HIT",
        }
        payload = parse_omniroute_headers(headers)
        self.assertTrue(payload["cache_hit"])
        self.assertAlmostEqual(payload["cost_saved_usd"], 0.001)
        self.assertEqual(payload["cache"], "HIT")

    def test_case_insensitive(self):
        payload = parse_omniroute_headers(
            {"x-omniroute-tokens-in": "10", "X-OMNIROUTE-TOKENS-OUT": "2"}
        )
        self.assertEqual(payload["tokens_in"], 10)
        self.assertEqual(payload["tokens_out"], 2)

    def test_extra_headers_preserved(self):
        headers = {
            "X-OmniRoute-Tokens-In": "1",
            "X-OmniRoute-Custom-Flag": "yes",
        }
        payload = parse_omniroute_headers(headers)
        self.assertEqual(payload["extra"]["custom-flag"], "yes")

    def test_publish_to_bus(self):
        bus = EventBus()
        seen = []
        bus.subscribe(OMNIROUTE_USAGE_TOPIC, lambda e: seen.append(e))
        payload = publish_omniroute_usage(SAMPLE_HEADERS, bus=bus)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].topic, OMNIROUTE_USAGE_TOPIC)
        self.assertEqual(seen[0].source, "omniroute")
        self.assertEqual(payload["tokens_in"], 42)

    def test_publish_noop_without_headers(self):
        bus = EventBus()
        self.assertIsNone(publish_omniroute_usage({}, bus=bus))
        self.assertEqual(bus.stats()["events"], 0)


class OpenAICompatOmniRouteEventsTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        boot()

    def tearDown(self):
        shutdown()

    @patch("adapters.llm.openai_compat.requests.post")
    def test_complete_publishes_omniroute_usage(self, mock_post):
        from kernel.boot import resolve

        bus = resolve("event_bus")
        seen = []
        bus.subscribe(OMNIROUTE_USAGE_TOPIC, lambda e: seen.append(e.payload))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hello"}}]
        }
        mock_resp.headers = SAMPLE_HEADERS
        mock_post.return_value = mock_resp

        client = OpenAICompatClient(
            base_url="http://127.0.0.1:20128/v1",
            model="gpt-4o-mini",
            provider_name="omniroute",
        )
        text = client.complete("hi")
        self.assertEqual(text, "hello")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["tokens_in"], 42)
        self.assertEqual(seen[0]["requested_model"], "gpt-4o-mini")
        self.assertEqual(client.last_usage["cost_usd"], 0.00012345)

    @patch("adapters.llm.openai_compat.requests.post")
    def test_complete_skips_events_without_omniroute_headers(self, mock_post):
        from kernel.boot import resolve

        bus = resolve("event_bus")
        before = bus.stats()["events"]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_post.return_value = mock_resp

        client = OpenAICompatClient(
            base_url="http://127.0.0.1:11434/v1",
            model="llama3.2",
            provider_name="ollama",
        )
        self.assertEqual(client.complete("hi"), "ok")
        self.assertEqual(bus.stats()["events"], before)
        self.assertEqual(client.last_usage, {})


if __name__ == "__main__":
    unittest.main()
