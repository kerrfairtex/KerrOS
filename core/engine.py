"""
core/engine.py
==============
Thin orchestration wrapper over models/engine/loader + generator.

Priority order: ONLINE first (fallback_chain in api_config.yaml, cloud
providers only), LOCAL llama.cpp last (only if every cloud provider is
missing a key or fails).
"""

import requests
import logging
from models.engine.loader import ModelLoader, load_api_config, resolve_provider
from models.engine.generator import Generator, build_chatml_prompt
from core.thinking import needs_thinking


from prompts.system import SYSTEM_PROMPT

DEFAULT_SYSTEM = SYSTEM_PROMPT

_SPECIAL_HANDLERS = {}

logger = logging.getLogger(__name__)


class LLMEngine:
    def __init__(self, prefer_light: bool = False, system: str = DEFAULT_SYSTEM):
        self.loader = ModelLoader(prefer_light=prefer_light)
        self.loader.validate()
        self.generator = None
        self.system = system
        self.api_cfg = load_api_config()

    def _call_openai_compat(self, provider_name, messages):
        entry = resolve_provider(provider_name)
        if not entry:
            logger.warning(f"[engine] Provider '{provider_name}' not found in config")
            return None
        api_key = entry.get("value")
        base_url = entry.get("base_url")
        model_name = entry.get("model", "auto")
        
        logger.debug(f"[engine] Attempting {provider_name} with model '{model_name}' at {base_url}")
        
        if not api_key or not base_url:
            logger.warning(f"[engine] {provider_name} missing api_key or base_url")
            return None
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": 512,
                },
                timeout=20,
            )
            
            logger.debug(f"[engine] {provider_name} response status: {resp.status_code}")
            
            # Log raw response for debugging (first 500 chars)
            raw_text = resp.text[:500] if resp.text else ""
            logger.debug(f"[engine] {provider_name} raw response: {raw_text}")
            
            resp.raise_for_status()
            data = resp.json()
            
            # Check if 'choices' is in response
            if "choices" not in data or not data["choices"]:
                error_msg = data.get("error", {}).get("message", "No choices in response")
                logger.error(f"[engine] {provider_name} API error: {error_msg}")
                raise ValueError(f"API Error ({provider_name}): {error_msg}")
            
            content = data["choices"][0]["message"]["content"]
            logger.debug(f"[engine] {provider_name} returned content length: {len(content) if content else 0}")
            return content
            
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = resp.json().get("error", {}).get("message", str(e))
            except:
                error_detail = str(e)
            logger.error(f"[engine] {provider_name} HTTP error: {error_detail}")
            raise ValueError(f"API Error ({provider_name}): {error_detail}")
        except Exception as e:
            logger.error(f"[engine] {provider_name} failed: {e}")
            raise

    def _call_anthropic(self, messages):
        entry = resolve_provider("anthropic")
        if not entry or not entry.get("value"):
            logger.warning("[engine] anthropic not configured")
            return None
        api_key = entry["value"]
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), self.system)
        turns = [m for m in messages if m["role"] != "system"]
        
        logger.debug(f"[engine] Attempting anthropic with model '{entry.get('model', 'claude-sonnet-4-6')}'")
        
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
            
            logger.debug(f"[engine] anthropic response status: {resp.status_code}")
            raw_text = resp.text[:500] if resp.text else ""
            logger.debug(f"[engine] anthropic raw response: {raw_text}")
            
            resp.raise_for_status()
            data = resp.json()
            
            if "content" not in data or not data["content"]:
                error_msg = data.get("error", {}).get("message", "No content in response")
                logger.error(f"[engine] anthropic API error: {error_msg}")
                raise ValueError(f"API Error (anthropic): {error_msg}")
            
            content = data["content"][0]["text"]
            logger.debug(f"[engine] anthropic returned content length: {len(content) if content else 0}")
            return content
            
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = resp.json().get("error", {}).get("message", str(e))
            except:
                error_detail = str(e)
            logger.error(f"[engine] anthropic HTTP error: {error_detail}")
            raise ValueError(f"API Error (anthropic): {error_detail}")
        except ValueError:
            raise  # Re-raise our own ValueErrors
        except Exception as e:
            logger.error(f"[engine] anthropic failed: {e}")
            raise

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
        
        logger.debug(f"[engine] _call_local - model: {self.loader.model}")
        logger.debug(f"[engine] _call_local - thinking: {use_thinking}, stream: {stream}")
        
        if use_thinking:
            return self.generator.generate_with_thinking(
                system=active_system, history=history, user_message=user_message,
            )
        prompt = build_chatml_prompt(system=active_system, history=history, user_message=user_message)
        
        logger.debug(f"[engine] Prompt length: {len(prompt)} chars")
        logger.debug(f"[engine] Prompt (first 200): {repr(prompt[:200])}")
        
        if stream:
            print("AI: ", end="", flush=True)
        # Pass the full chatml text prompt directly to the generator — which
        # already constructs the llama.cpp command. The generator's
        # _extract_reply() expects to find the <|im_start|>assistant marker in
        # the output, so we must not suppress the prompt echo.
        result = self.generator.generate(prompt, stream=stream)
        
        logger.debug(f"[engine] Local generation result: {len(result) if result else 0} chars")
        if result:
            logger.debug(f"[engine] Result (first 200): {repr(result[:200])}")
        
        return result

    def _has_cloud_key(self, name: str) -> bool:
        """Return True if the provider has a real (non-empty) key configured."""
        entry = resolve_provider(name)
        if not entry:
            return False
        val = entry.get("value")
        return bool(val) and val != "" and val != "default"

    def chat(self, user_message, history=None, stream=True, force_thinking=False, system=None, force_local=False):
        history = history or []
        active_system = system or self.system
        messages = (
            [{"role": "system", "content": active_system}]
            + history
            + [{"role": "user", "content": user_message}]
        )

        logger.debug(f"[engine] chat() called - user_message: {repr(user_message[:100])}")
        logger.debug(f"[engine] history turns: {len(history)}, stream: {stream}, force_local: {force_local}")

        # If force_local (offline mode), skip cloud providers entirely
        if force_local:
            logger.debug("[engine] force_local=True - skipping cloud providers")
            return self._call_local(user_message, history, stream, force_thinking, active_system)

        # Only iterate the cloud chain if at least one provider has a key;
        # otherwise skip straight to local mode to avoid timeout.
        cloud_names = set(self.api_cfg.get("llm_cloud", {}).keys())
        chain = self.api_cfg.get("fallback_chain", [])
        cloud_available = any(self._has_cloud_key(n) for n in chain if n in cloud_names)

        logger.debug(f"[engine] cloud_available: {cloud_available}, chain: {chain}")

        if cloud_available:
            last_error = None
            for name in chain:
                if name not in cloud_names:
                    continue
                try:
                    logger.debug(f"[engine] Trying cloud provider: {name}")
                    reply = self._call_cloud_provider(name, messages)
                    if reply:
                        logger.debug(f"[engine] Cloud provider {name} returned: {len(reply)} chars")
                        return reply
                    else:
                        logger.warning(f"[engine] Cloud provider {name} returned empty/None")
                except Exception as e:
                    last_error = e
                    logger.warning(f"[engine] Cloud provider {name} failed: {e}")
                    continue
            
            # All cloud providers failed
            if last_error:
                raise ValueError(f"All cloud providers failed. Last error: {last_error}")

        # Fall back to local mode
        logger.debug("[engine] Falling back to local generation")
        return self._call_local(user_message, history, stream, force_thinking, active_system)

    def generate_raw(self, prompt: str, stream: bool = False) -> str:
        self._ensure_local()
        return self.generator.generate(prompt, stream=stream)
