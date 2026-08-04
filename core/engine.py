"""
core/engine.py
==============
Thin orchestration wrapper over models/engine/loader + generator.

Priority order: ONLINE first (fallback_chain in api_config.yaml, cloud
providers only), LOCAL llama.cpp last (only if every cloud provider is
missing a key or fails).
"""

import requests
from models.engine.loader import ModelLoader, load_api_config, resolve_provider
from models.engine.generator import Generator, build_chatml_prompt
from core.thinking import needs_thinking


DEFAULT_SYSTEM = (
    "You are an offline AI assistant specialized in cybersecurity, networking, "
    "hardware diagnostics, and technical research. You run fully offline on an "
    "Android device via Termux. Be concise, accurate, and practical. "
    "When executing tools, always confirm the action before running."
)

_SPECIAL_HANDLERS = {}


class LLMEngine:
    def __init__(self, prefer_light: bool = False, system: str = DEFAULT_SYSTEM):
        self.loader = ModelLoader(prefer_light=prefer_light)
        self.generator = None
        self.system = system
        self.api_cfg = load_api_config()

    def _call_openai_compat(self, provider_name, messages):
        entry = resolve_provider(provider_name)
        if not entry:
            return None
        api_key = entry.get("value")
        base_url = entry.get("base_url")
        if not api_key or not base_url:
            return None
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": entry.get("model", "auto"),
                    "messages": messages,
                    "max_tokens": 512,
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
#              print(f"[engine] {provider_name} failed: {e}", file=__import__("sys").stderr)
            return None

    def _call_anthropic(self, messages):
        entry = resolve_provider("anthropic")
        if not entry or not entry.get("value"):
            return None
        api_key = entry["value"]
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), self.system)
        turns = [m for m in messages if m["role"] != "system"]
        try:
            resp = requests.post(
                f"{entry['base_url']}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": entry.get("model", "claude-sonnet-4-6"),
                    "max_tokens": 512,
                    "system": sys_msg,
                    "messages": turns,
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]
        except Exception as e:
#              print(f"[engine] anthropic failed: {e}", file=__import__("sys").stderr)
            return None

    def _call_cloud_provider(self, provider_name, messages):
        if provider_name == "anthropic":
            return self._call_anthropic(messages)
        if provider_name in _SPECIAL_HANDLERS:
            return _SPECIAL_HANDLERS[provider_name](self, messages)
        return self._call_openai_compat(provider_name, messages)

    def _ensure_local(self):
        if self.generator is None:
            self.loader.validate()
            self.generator = Generator(self.loader)

    def _call_local(self, user_message, history, stream, force_thinking, system=None):
        self._ensure_local()
        active_system = system or self.system
        use_thinking = force_thinking or needs_thinking(user_message)
        if use_thinking:
            return self.generator.generate_with_thinking(
                system=active_system, history=history, user_message=user_message,
            )
        prompt = build_chatml_prompt(system=active_system, history=history, user_message=user_message)
        if stream:
            print("AI: ", end="", flush=True)
        return self.generator.generate(prompt, stream=stream)

    def chat(self, user_message, history=None, stream=True, force_thinking=False, system=None):
        history = history or []
        active_system = system or self.system
        messages = (
            [{"role": "system", "content": active_system}]
            + history
            + [{"role": "user", "content": user_message}]
        )

        cloud_names = set(self.api_cfg.get("llm_cloud", {}).keys())
        for name in self.api_cfg.get("fallback_chain", []):
            if name not in cloud_names:
                continue
            reply = self._call_cloud_provider(name, messages)
            if reply:
                return reply

        return self._call_local(user_message, history, stream, force_thinking, active_system)

    def generate_raw(self, prompt: str, stream: bool = False) -> str:
        self._ensure_local()
        return self.generator.generate(prompt, stream=stream)
