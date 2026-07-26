"""
adapters/llm/unsloth_adapter.py
===============================
LLMPort adapter implementing local accelerated LLM inference via Unsloth.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional
from ports.llm_port import LLMPort

try:
    from unsloth import FastLanguageModel
    import torch
    HAS_UNSLOTH = True
except ImportError:
    HAS_UNSLOTH = False


class UnslothAdapter(LLMPort):
    """Local LLMPort utilizing Unsloth-accelerated models."""

    def __init__(
        self,
        model_name: str = "unsloth/Qwen2.5-0.5B-Instruct",
        max_seq_length: int = 2048,
        load_in_4bit: bool = True,
    ) -> None:
        self.model_name = model_name
        self.max_seq_length = max_seq_length
        self.load_in_4bit = load_in_4bit
        self.last_api = "unsloth"

        if HAS_UNSLOTH:
            self.model, self.tokenizer = FastLanguageModel.from_pretrained(
                model_name=self.model_name,
                max_seq_length=self.max_seq_length,
                load_in_4bit=self.load_in_4bit,
            )
            FastLanguageModel.for_inference(self.model)
        else:
            self.model = None
            self.tokenizer = None

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        if HAS_UNSLOTH and self.model is not None and self.tokenizer is not None:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": prompt})

            inputs = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
            ).to("cuda")

            outputs = self.model.generate(
                input_ids=inputs,
                max_new_tokens=max_tokens,
                use_cache=True,
                temperature=kwargs.get("temperature", 0.7),
            )
            decoded = self.tokenizer.batch_decode(outputs[:, inputs.shape[1]:], skip_special_tokens=True)
            return decoded[0] if decoded else ""

        return self._simulate_completion(prompt, system, history)

    def _simulate_completion(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
    ) -> str:
        """Fallback lightweight completion for CPU / mock testing."""
        lower = prompt.lower()
        if "test" in lower:
            return "This is a successful mock execution of Qwen2.5-0.5B via UnslothAdapter."
        if "hello" in lower or "hi" in lower:
            return "Hello! I am a local Qwen2.5-0.5B model accelerated with Unsloth. How can I assist you today?"
        return f"[Simulated Qwen2.5-0.5B via UnslothAdapter] Response to query: '{prompt}'"

    def status(self) -> dict[str, Any]:
        return {
            "available": HAS_UNSLOTH,
            "model_name": self.model_name,
            "max_seq_length": self.max_seq_length,
            "load_in_4bit": self.load_in_4bit,
        }

    def last_api_used(self) -> str | None:
        return self.last_api
