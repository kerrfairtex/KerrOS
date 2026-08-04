"""
models/engine/generator.py
==========================
Handles ChatML prompt formatting and llama.cpp subprocess execution.
"""

import subprocess
import sys
from typing import Optional, Callable
from models.engine.loader import ModelLoader


def build_chatml_prompt(system, history, user_message):
    parts = [f"<|im_start|>system\n{system}<|im_end|>"]
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            continue  # skip compressed memory markers
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    parts.append(f"<|im_start|>user\n{user_message}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


def _extract_reply(raw: str) -> str:
    """
    llama-simple echoes the full prompt then generates.
    Extract only the final assistant reply after the last marker.
    """
    marker = "<|im_start|>assistant"
    if marker in raw:
        # Take everything after the LAST assistant marker
        reply = raw.split(marker)[-1]
        # Strip the leading newline
        reply = reply.lstrip("\n")
        # Strip end token
        reply = reply.replace("<|im_end|>", "")
        reply = reply.replace("<|endoftext|>", "")
        # Strip any trailing role leaks
        for stop in ["<|im_start|>", "user\n", "assistant\n"]:
            if stop in reply:
                reply = reply.split(stop)[0]
        return reply.strip()
    return raw.strip()


class Generator:
    def __init__(self, loader: ModelLoader):
        self.loader = loader

    def _build_cmd(self, prompt: str) -> list:
        l = self.loader
        return [
            l.binary,
            "-m",   l.model,
            "-t",   str(l.threads),
            "-c",   str(l.context_size),
            "-n",   str(l.max_tokens),
            "--temp",          str(l.temperature),
            "--repeat-penalty", str(l.repeat_penalty),
            "--repeat-last-n", str(l.repeat_last_n),
            "-no-cnv",
            "--no-display-prompt",
            "-p",   prompt,
        ]

    def generate(
        self,
        prompt: str,
        stream: bool = True,
        on_token: Optional[Callable[[str], None]] = None,
        timeout: int = 120,
    ) -> str:
        cmd = self._build_cmd(prompt)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            # Collect full output first, then extract reply
            full_output = proc.stdout.read()

            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

            reply = _extract_reply(full_output)

            if stream and reply:
                print(reply)

            return reply

        except KeyboardInterrupt:
            try: proc.terminate()
            except: pass
            print("\n[Generation interrupted]")
            return ""

        except FileNotFoundError:
            return f"[Generator] Binary not found: {self.loader.binary}"

        except Exception as e:
            return f"[Generator error: {e}]"

    def generate_with_thinking(self, system, history, user_message):
        think_prompt = build_chatml_prompt(
            system=system,
            history=history,
            user_message=user_message + "\n\nThink through this step by step:"
        )
        original_max = self.loader.max_tokens
        self.loader.max_tokens = min(original_max, 200)
        thought = self.generate(think_prompt, stream=False)
        self.loader.max_tokens = original_max

        final_user = (
            f"{user_message}\n\n"
            f"[Reasoning: {thought[:300]}]\n\n"
            f"Final answer:"
        )
        final_prompt = build_chatml_prompt(
            system=system, history=history, user_message=final_user
        )
        return self.generate(final_prompt, stream=False)
