import logging
"""
core/multi_api.py
=================
E.U.T Multi-API Engine — KerrOS v2.0
Smart routing across 8 APIs with fallback chain.

Routing:
  coding/math  → DeepSeek → NVIDIA → Groq
  research     → NVIDIA Llama-405B → OpenRouter → Groq
  reasoning    → Cohere → OpenRouter → Groq
  teaching     → HuggingFace → Groq
  chat         → Groq (fastest)
  offline      → Local Qwen
"""

import os, requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    def load_dotenv(*args, **kwargs):
        return False

BASE = os.path.expanduser("~/offline_ai")
load_dotenv(f"{BASE}/.env")

GROQ_KEY       = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_KEY   = os.getenv("DEEPSEEK_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
NVIDIA_KEY     = os.getenv("NVIDIA_API_KEY", "")
HF_KEY         = os.getenv("HUGGINGFACE_API_KEY", "")
COHERE_KEY     = os.getenv("COHERE_API_KEY", "")

# ── Task Detection ────────────────────────────────────────
def detect_task(text):
    lower = text.lower()
    if any(k in lower for k in ["code","script","python","bash","function",
            "debug","implement","fix this","program","error"]):
        return "coding"
    if any(k in lower for k in ["calculate","math","equation","solve","formula"]):
        return "math"
    if any(k in lower for k in ["research","history of","explain in detail",
            "deep dive","full explanation","compare","analyze","what is the",
            "complete answer","comprehensive","in depth","thorough"]):
        return "research"
    if any(k in lower for k in ["teach","learn","tutorial","how to","step by step",
            "explain","course","lesson","guide"]):
        return "teaching"
    if any(k in lower for k in ["reason","logic","argument","pros and cons",
            "should i","best way","recommend","opinion","think"]):
        return "reasoning"
    return "chat"

# ── API Callers ───────────────────────────────────────────

def call_groq(messages, model="llama-3.3-70b-versatile", max_tokens=1024):
    if not GROQ_KEY: return None, "No key"
    try:
        from groq import Groq
        r = Groq(api_key=GROQ_KEY).chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens)
        return r.choices[0].message.content, None
    except Exception as e: return None, str(e)

def call_nvidia(messages, model="meta/llama-3.1-8b-instruct", max_tokens=1024):
    if not NVIDIA_KEY: return None, "No key"
    try:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {NVIDIA_KEY}",
                   "Content-Type": "application/json"}
        body = {"model": model, "messages": messages,
                "max_tokens": max_tokens, "temperature": 0.7,
                "stream": False}
        r = requests.post(url, headers=headers, json=body, timeout=30)
        data = r.json()
        if "choices" not in data: return None, str(data)
        return data["choices"][0]["message"]["content"], None
    except Exception as e: return None, str(e)

def call_deepseek(messages, max_tokens=1024):
    if not DEEPSEEK_KEY: return None, "No key"
    try:
        url = "https://api.deepseek.com/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}",
                   "Content-Type": "application/json"}
        body = {"model": "deepseek-chat", "messages": messages,
                "max_tokens": max_tokens}
        r = requests.post(url, headers=headers, json=body, timeout=30)
        data = r.json()
        if "choices" not in data: return None, str(data)
        return data["choices"][0]["message"]["content"], None
    except Exception as e: return None, str(e)

def call_cohere(messages, max_tokens=1024):
    if not COHERE_KEY: return None, "No key"
    try:
        # Convert messages to Cohere format
        chat_history = []
        user_msg = ""
        for m in messages:
            if m["role"] == "system":
                continue
            elif m["role"] == "user":
                user_msg = m["content"]
            elif m["role"] == "assistant":
                chat_history.append({"role": "CHATBOT", "message": m["content"]})

        url = "https://api.cohere.com/v1/chat"
        headers = {"Authorization": f"Bearer {COHERE_KEY}",
                   "Content-Type": "application/json"}
        body = {"model": "command-r-plus",
                "message": user_msg,
                "chat_history": chat_history,
                "max_tokens": max_tokens}
        r = requests.post(url, headers=headers, json=body, timeout=30)
        data = r.json()
        if "text" not in data: return None, str(data)
        return data["text"], None
    except Exception as e: return None, str(e)

def call_huggingface(messages, model="mistralai/Mistral-7B-Instruct-v0.3", max_tokens=512):
    if not HF_KEY: return None, "No key"
    try:
        # Build prompt from messages
        prompt = ""
        for m in messages:
            if m["role"] == "system":
                prompt += f"<s>[INST] {m['content']} [/INST]</s>\n"
            elif m["role"] == "user":
                prompt += f"[INST] {m['content']} [/INST]"
            elif m["role"] == "assistant":
                prompt += f"{m['content']}</s>\n"

        url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {HF_KEY}"}
        body = {"inputs": prompt,
                "parameters": {"max_new_tokens": max_tokens, "temperature": 0.7}}
        r = requests.post(url, headers=headers, json=body, timeout=60)
        data = r.json()
        if isinstance(data, list):
            return data[0].get("generated_text", "").replace(prompt, "").strip(), None
        return None, str(data)
    except Exception as e: return None, str(e)

def call_openrouter(messages, model="meta-llama/llama-3.3-70b-instruct:free", max_tokens=1024):
    if not OPENROUTER_KEY: return None, "No key"
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENROUTER_KEY}",
                   "Content-Type": "application/json",
                   "HTTP-Referer": "https://kerros.local",
                   "X-Title": "KerrOS E.U.T Agent"}
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        r = requests.post(url, headers=headers, json=body, timeout=30)
        data = r.json()
        if "choices" not in data: return None, str(data)
        return data["choices"][0]["message"]["content"], None
    except Exception as e: return None, str(e)

def call_gemini(messages, max_tokens=1024):
    if not GEMINI_KEY: return None, "No key"
    try:
        # Build prompt
        prompt = "\n".join([f"{m['role'].title()}: {m['content']}" for m in messages])
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens}}
        r = requests.post(url, json=body, timeout=30)
        data = r.json()
        if "candidates" not in data: return None, str(data)
        return data["candidates"][0]["content"]["parts"][0]["text"], None
    except Exception as e: return None, str(e)

# ── Main Engine ───────────────────────────────────────────

class MultiAPIEngine:
    def __init__(self):
        self.last_api = None
        self.dead_apis = set()  # APIs that failed with auth/permanent errors this session
        self.health = {}        # api_name -> "ok" | "failed" | "unknown"

    ALL_APIS = [
        ("Groq",             lambda messages, mt: call_groq(messages, max_tokens=mt)),
        ("Anthropic",        lambda messages, mt: call_anthropic(messages, max_tokens=mt)),
        ("NVIDIA-Llama405B", lambda messages, mt: call_nvidia(messages, max_tokens=mt)),
        ("DeepSeek",         lambda messages, mt: call_deepseek(messages, mt)),
        ("Cohere",           lambda messages, mt: call_cohere(messages, mt)),
        ("OpenRouter",       lambda messages, mt: call_openrouter(messages, max_tokens=mt)),
        ("HuggingFace",      lambda messages, mt: call_huggingface(messages, max_tokens=mt)),
        ("Gemini",           lambda messages, mt: call_gemini(messages, mt)),
    ]

    def _is_permanent_error(self, err):
        if not err: return False
        e = err.lower()
        return any(s in e for s in ["authentication", "auth fail", "invalid api key",
                                     "unauthorized", "401", "403", "no key",
                                     "404", "not found", "does not exist",
                                     "model_not_found", "invalid model"])

    def _try_api(self, name, caller, messages, max_tokens, retry_on_network=True):
        if name in self.dead_apis:
            return None, "skipped (marked dead this session)"

        result, err = caller(messages, max_tokens)

        if not result and err and not self._is_permanent_error(err) and retry_on_network:
            # Likely transient network blip — retry once
            result, err = caller(messages, max_tokens)

        if result:
            self.health[name] = "ok"
            return result, None

        if self._is_permanent_error(err):
            self.dead_apis.add(name)
            self.health[name] = "dead (auth)"
        else:
            self.health[name] = "failed (network)"

        return None, err

    def generate(self, user_message, system=None, history=None, max_tokens=1024):
        history = history or []
        task = detect_task(user_message)

        # Build messages
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        for m in history:
            if m.get("role") in ("user", "assistant"):
                messages.append(m)
        messages.append({"role": "user", "content": user_message})

        # ── Routing ──────────────────────────────────────
        chain = []

        if task in ("coding", "math"):
            chain = [
                ("DeepSeek",         lambda: call_deepseek(messages, max_tokens)),
                ("NVIDIA-Llama405B", lambda: call_nvidia(messages, max_tokens=max_tokens)),
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
            ]
        elif task == "research":
            chain = [
                ("NVIDIA-Llama405B", lambda: call_nvidia(messages, max_tokens=max_tokens)),
                ("OpenRouter",       lambda: call_openrouter(messages, max_tokens=max_tokens)),
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
            ]
        elif task == "teaching":
            chain = [
                ("HuggingFace",      lambda: call_huggingface(messages, max_tokens=max_tokens)),
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
            ]
        elif task == "reasoning":
            chain = [
                ("Anthropic",        lambda: call_anthropic(messages, max_tokens=max_tokens)),
                ("Cohere",           lambda: call_cohere(messages, max_tokens)),
                ("OpenRouter",       lambda: call_openrouter(messages, max_tokens=max_tokens)),
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
            ]
        else:  # chat
            chain = [
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
                ("OpenRouter",       lambda: call_openrouter(messages, max_tokens=max_tokens)),
            ]

        # Convert task-specific chain (closures) into (name, caller) using shared retry/health logic
        tried = set()
        for api_name, caller in chain:
            result, err = caller()
            if not result and err and not self._is_permanent_error(err):
                result, err = caller()  # one retry on transient network error
            tried.add(api_name)
            if result:
                self.last_api = api_name
                self.health[api_name] = "ok"
                return result
            if self._is_permanent_error(err):
                self.dead_apis.add(api_name)
                self.health[api_name] = "dead (auth)"
            else:
                self.health[api_name] = "failed (network)"
            logging.debug(f"{api_name} failed: {str(err)[:120]}")

        # Powerhouse fallback: task-specific chain exhausted — try every
        # remaining configured API not already attempted, before giving up.
        for name, fn in self.ALL_APIS:
            if name in tried or name in self.dead_apis:
                continue
            result, err = self._try_api(name, fn, messages, max_tokens)
            if result:
                self.last_api = name
                return result
            logging.debug(f"{name} failed: {str(err)[:120]}")

        self.last_api = None
        return "[All APIs failed. Use /offline mode.]"

    def status(self):
        return {
            "groq":       bool(GROQ_KEY),
            "nvidia":     bool(NVIDIA_KEY),
            "deepseek":   bool(DEEPSEEK_KEY),
            "cohere":     bool(COHERE_KEY),
            "huggingface":bool(HF_KEY),
            "openrouter": bool(OPENROUTER_KEY),
            "anthropic":  bool(ANTHROPIC_KEY),
            "gemini":     bool(GEMINI_KEY),
        }
