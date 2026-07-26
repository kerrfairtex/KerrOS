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
    def __init__(self):
        self.c = cfg()
        self.mode = "offline"
        self._llm_port = None
        self._offline = None

    def init_online(self):
        try:
            from kernel.access import get_llm_port
            port = get_llm_port()
            self._llm_port = port
            test = port.complete("hi", max_tokens=5)
            if not test or "All APIs failed" in test:
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
        from kernel.access import get_llm_port

        if not self._llm_port:
            self._llm_port = get_llm_port()

        # Filter corrupted history
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

        result = self._llm_port.complete(
            user_message,
            system=system,
            history=clean_hist,
            max_tokens=4096  # online models handle long answers natively, no RAM ceiling like offline
        )
        # Show which API was used
        last_api = self._llm_port.last_api_used() if hasattr(self._llm_port, "last_api_used") else None
        if last_api:
            print(f"  \033[90m[{last_api}]\033[0m", end=" ", flush=True)
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
