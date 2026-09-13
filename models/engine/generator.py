"""
models/engine/generator.py
=========================
Handles ChatML prompt formatting and llama.cpp subprocess execution.
"""

import subprocess
import sys
import logging
import os
from pathlib import Path
from typing import Optional, Callable
from models.engine.loader import ModelLoader

logger = logging.getLogger(__name__)


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


def _strip_ansi(text: str) -> str:
    """Remove spinner animation while preserving all other content."""
    # The spinner animation is: "|\b-\b\\b|\b/\b-\b\\b|\b/\b-\b \b"
    # Strategy: remove all backspace characters and the spinner chars before them
    result = []
    for ch in text:
        if ch == '\x08':  # backspace - remove previous char if it was a spinner char
            if result and result[-1] in '|-\\/':
                result.pop()
        elif ch == '\x1b':  # ESC
            continue
        elif ord(ch) < 0x20 and ch not in '\n\t ':
            continue
        else:
            result.append(ch)
    return ''.join(result)


def _extract_reply(raw: str) -> str:
    """
    Extract the model's response from llama-cli output.
    The response comes after the LAST <|im_start|>assistant marker.
    """
    import re
    
    # Strip ANSI codes
    raw = _strip_ansi(raw)
    
    # Strip timing stats
    raw = re.sub(r'\[\s*Prompt:.*?\]', '', raw)
    raw = re.sub(r'\bExiting\.\.\.\s*', '', raw)
    
    # Find the LAST <|im_start|>assistant marker
    marker = "<|im_start|>assistant"
    last_pos = raw.rfind(marker)
    if last_pos != -1:
        reply = raw[last_pos + len(marker):].strip()
        return reply
    
    return raw.strip()


class Generator:
    def __init__(self, loader: ModelLoader):
        self.loader = loader
        # Set up library path for subprocess
        self._lib_dir = self._find_lib_dir()
    
    def _find_lib_dir(self) -> str:
        """Find the directory containing shared libraries."""
        binary = Path(self.loader.binary)
        # Check if binary is a symlink and resolve it
        if binary.is_symlink():
            binary = binary.resolve()
        # Library directory is typically the same as the binary
        return str(binary.parent)

    def _build_cmd(self, prompt: str) -> list:
        l = self.loader
        cmd = [
            l.binary,
            "-m",   l.model,
            "-t",   str(l.threads),
            "-c",   str(l.context_size),
            "-n",   str(l.max_tokens),
            "--temp",          str(l.temperature),
            "--top-p",         str(getattr(l, 'top_p', 0.9)),
            "--repeat-penalty", str(l.repeat_penalty),
            "--repeat-last-n", str(l.repeat_last_n),
            "--no-display-prompt",
            "--single-turn",
        ]
        cmd.extend(["-p", prompt])
        return cmd
    
    def _get_env(self) -> dict:
        """Get environment with LD_LIBRARY_PATH set for shared libraries."""
        env = os.environ.copy()
        lib_dir = self._lib_dir
        current_ld = env.get("LD_LIBRARY_PATH", "")
        if current_ld:
            env["LD_LIBRARY_PATH"] = f"{lib_dir}:{current_ld}"
        else:
            env["LD_LIBRARY_PATH"] = lib_dir
        return env

    def generate(
        self,
        prompt: str,
        stream: bool = True,
        on_token: Optional[Callable[[str], None]] = None,
        timeout: int = 300,
    ) -> str:
        cmd = self._build_cmd(prompt)

        logger.debug(f"[generator] Command: {' '.join(cmd[:10])}... (truncated)")
        logger.debug(f"[generator] Binary: {self.loader.binary}")
        logger.debug(f"[generator] Model: {self.loader.model}")
        logger.debug(f"[generator] Timeout: {timeout}s")

        try:
            env = self._get_env()
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                
                logger.debug(f"[generator] Subprocess return code: {proc.returncode}")
                logger.debug(f"[generator] stdout length: {len(stdout) if stdout else 0}")
                logger.debug(f"[generator] stderr: {stderr[:300] if stderr else ''}")
                
                if proc.returncode != 0:
                    logger.error(f"[generator] Subprocess failed with code {proc.returncode}")
                    logger.error(f"[generator] stderr: {stderr[:500] if stderr else 'empty'}")
                    raise RuntimeError(f"llama.cpp exited with code {proc.returncode}: {stderr[:200]}")
                    
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                logger.error(f"[generator] Generation timed out after {timeout}s")
                if stream:
                    print("\n[Generation timed out]", flush=True)
                raise TimeoutError(f"Generation timed out after {timeout}s")

            reply = _extract_reply(stdout)
            
            logger.debug(f"[generator] Extracted reply length: {len(reply) if reply else 0}")
            logger.debug(f"[generator] Reply (first 200): {repr(reply[:200]) if reply else 'EMPTY'}")

            if stream and reply:
                print(reply)

            return reply

        except KeyboardInterrupt:
            try:
                if 'proc' in locals():
                    proc.terminate()
            except: pass
            print("\n[Generation interrupted]")
            raise

        except FileNotFoundError:
            logger.error(f"[generator] Binary not found: {self.loader.binary}")
            raise RuntimeError(f"Binary not found: {self.loader.binary}")

        except Exception as e:
            logger.error(f"[generator] Unexpected error: {e}")
            raise

    def generate_with_thinking(self, system, history, user_message, timeout: int = 20):
        think_prompt = build_chatml_prompt(
            system=system,
            history=history,
            user_message=user_message + "\n\nThink through this step by step:"
        )
        original_max = self.loader.max_tokens
        self.loader.max_tokens = min(original_max, 200)
        try:
            thought = self.generate(think_prompt, stream=False, timeout=timeout)
        finally:
            self.loader.max_tokens = original_max
        if thought is None or thought == "":
            return "[Thinking timed out — no output]"

        final_user = (
            f"{user_message}\n\n"
            f"[Reasoning: {thought[:300]}]\n\n"
            f"Final answer:"
        )
        final_prompt = build_chatml_prompt(
            system=system, history=history, user_message=final_user
        )
        return self.generate(final_prompt, stream=False)
