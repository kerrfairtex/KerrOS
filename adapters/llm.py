"""
adapters/llm.py
===============
Shim: proposed future path for LLM adapter namespace.
Current implementation: adapters/llm/composite_adapter.py and related modules.
"""

from adapters.llm.composite_adapter import CompositeLLMAdapter
from adapters.llm.ollama_adapter import OllamaAdapter
from adapters.llm.llama_cpp_adapter import LlamaCppAdapter
from adapters.llm.vllm_adapter import VLLMAdapter
from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.llm.omniroute_adapter import OmniRouteAdapter
from adapters.llm.resilience import ResilienceConfig
from adapters.llm.multi_api_adapter import MultiAPIAdapter
from adapters.llm.offline_gateway import OfflineGateway
from adapters.llm.offline_profile import OfflineProfile
from adapters.llm.openai_compat import OpenAICompatAdapter
from adapters.llm.openrouter_adapter import OpenRouterAdapter
from adapters.llm.unsloth_adapter import UnslothAdapter
from adapters.llm.unsloth_finetune import UnslothFinetune
from adapters.llm.model_pull import ModelPull
from adapters.llm.local_llm_probe import LocalLLMProbe
from adapters.llm.local_llm_proxy import LocalLLMProxy

__all__ = [
    "CompositeLLMAdapter",
    "OllamaAdapter",
    "LlamaCppAdapter",
    "VLLMAdapter",
    "LiteLLMAdapter",
    "OmniRouteAdapter",
    "ResilienceConfig",
    "MultiAPIAdapter",
    "OfflineGateway",
    "OfflineProfile",
    "OpenAICompatAdapter",
    "OpenRouterAdapter",
    "UnslothAdapter",
    "UnslothFinetune",
    "ModelPull",
    "LocalLLMProbe",
    "LocalLLMProxy",
]
