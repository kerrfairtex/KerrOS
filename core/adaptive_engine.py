import os, json, socket
from core.config import cfg
from core.task_completion import task_manager

def check_internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except: return False

class AdaptiveEngine:
    """
    Online path uses core.router.Router (README_INTEGRATION.md):
      OpenRouter free (task tiers) → MultiAPI keyed providers → local → paid (opt-in)
    """

    def __init__(self):
        self.c = cfg()
        self.mode = "offline"
        self._router = None
        self._offline = None

    @property
    def _multi(self):
        """Compat for /apistatus — MultiAPIEngine behind the zero-cost router."""
        r = self._router
        return getattr(r, "multi_api", None) if r else None

    def init_online(self):
        try:
            from core.router import Router

            self._router = Router()
            test = self._router.generate("hi", max_tokens=5)
            if not test or str(test).startswith("[router]"):
                return False, test or "router returned nothing"
            if "All APIs failed" in str(test):
                return False, "All APIs failed"
            self.mode = "online"
            return True, "online"
        except Exception as e:
            return False, str(e)

    def init_offline(self):
        from core.engine import LLMEngine
        self._offline = LLMEngine()
        self.mode = "offline"

    def generate(self, user_message, system=None, history=None, stream=False):
        task = task_manager.start(user_message)
        task_manager.complete_checkpoint(task.id, "Understand objective", evidence="prompt_received")

        try:
            if self.mode == "online":
                result = self._online_generate(user_message, system, history, stream)
            else:
                result = self._offline_generate(user_message, system, history, stream)

            task_manager.complete_checkpoint(task.id, "Produce complete answer", evidence=str(result)[:1000])
            return result
        except Exception:
            raise

    def _online_generate(self, user_message, system, history, stream):
        # Router.generate is non-streaming today; `stream` kept for signature compat.
        from core.router import Router

        if not self._router:
            self._router = Router(system=system)

        bad = ["[Online error","<|im_start|>","[Tool output]",
               "User: ","Assistant: ","Analyze the tool output"]
        clean_hist = []
        for m in (history or []):
            role = m.get("role","")
            content = m.get("content","").strip()
            if role not in ("user","assistant"): continue
            if not content or len(content) < 3: continue
            if any(b in content for b in bad): continue
            clean_hist.append({"role": role, "content": content})

        result = self._router.generate(
            user_message,
            system=system,
            history=clean_hist,
            max_tokens=4096,
            allow_paid=False,
        )
        provider = self._router.last_provider
        if provider:
            print(f"  \033[90m[{provider}]\033[0m", end=" ", flush=True)
        return result

    def _offline_generate(self, user_message, system, history, stream):
        if not self._offline:
            self.init_offline()
        return self._offline.chat(
            user_message=user_message,
            history=history or [],
            stream=stream,
            system=system,
        )

    def switch_online(self):
        return self.init_online()

    def switch_offline(self):
        self.mode = "offline"
        self.init_offline()
        return True, "offline"

    @property
    def current_mode(self):
        return self.mode

    def check_ready(self):
        if self.mode == "offline":
            if not self._offline:
                self.init_offline()
