"""
agents/code.py
Code Agent — generates code for a task, saves it, runs it, and attempts
one self-correction pass if execution fails.
"""
import os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete
from tools.code_saver import save_code_blocks, run_and_verify
from prompts.system import SYSTEM_PROMPT

R="\033[0m"; GO="\033[33m"; GR="\033[92m"; BL="\033[94m"; CY="\033[96m"; GY="\033[90m"; YL="\033[93m"; RE="\033[91m"

CODE_PROMPT = (
    "Write complete, working code for the following task. "
    "Output ONLY a single fenced code block with the full file content, no explanation.\n\n"
    "Task: {task}"
)

FIX_PROMPT = (
    "This code failed when run. Fix it. Output ONLY a corrected fenced code block, no explanation.\n\n"
    "Original task: {task}\n\nCode:\n{code}\n\nError:\n{error}"
)

class CodeAgent:
    def __init__(self, engine):
        self.engine = engine

    def run(self, task, folder=None, stream=True):
        if stream:
            print(f"\n  {YL}💻 Code Agent{R}\n  {GY}Task: {task}{R}\n")

        # Code needs more headroom than a short Q&A answer — temporarily
        # bump the offline model's max_tokens for this generation only.
        bumped = False
        try:
            if getattr(self.engine, "_offline", None) and self.engine._offline:
                loader = self.engine._offline.loader
                self._orig_max = loader.max_tokens
                loader.max_tokens = max(self._orig_max, 900)
                bumped = True
        except Exception:
            pass

        response = generate_complete(
            self.engine,
            user_message=CODE_PROMPT.format(task=task),
            system=SYSTEM_PROMPT, history=[], stream=False,
        )

        if bumped:
            try:
                loader.max_tokens = self._orig_max
            except Exception:
                pass

        folder = folder or ("codeagent_" + __import__("time").strftime("%Y%m%d_%H%M%S"))
        saved = save_code_blocks(response, folder=folder)
        if not saved:
            if stream: print(f"  {RE}No code block found in response.{R}")
            return response

        results = []
        for f in saved:
            if stream: print(f"  {GR}[saved]{R} {f}")
            result = run_and_verify(f)
            results.append((f, result))

            if not result.get("ran"):
                if stream: print(f"  {GY}[skip: not runnable]{R} {f}")
                continue

            if result["ok"]:
                if stream: print(f"  {GR}[PASS]{R} {f}")
            else:
                if stream: print(f"  {RE}[FAIL]{R} {f} — attempting fix")
                with open(f) as fh:
                    original_code = fh.read()
                fix_response = generate_complete(self.engine, 
                    user_message=FIX_PROMPT.format(
                        task=task, code=original_code[:1500], error=result.get("stderr","")[:500]
                    ),
                    system=SYSTEM_PROMPT, history=[], stream=False,
                )
                fixed_saved = save_code_blocks(fix_response, folder=folder)
                if fixed_saved:
                    fixed_result = run_and_verify(fixed_saved[0])
                    status = "PASS" if fixed_result.get("ok") else "FAIL"
                    if stream: print(f"  {GO}[retry:{status}]{R} {fixed_saved[0]}")
                    results.append((fixed_saved[0], fixed_result))

        summary = f"Code Agent completed. {len(saved)} file(s) generated in {folder}/\n"
        for f, r in results:
            status = "PASS" if r.get("ok") else ("FAIL" if r.get("ran") else "not run")
            summary += f"  {f}: {status}\n"

        if stream: print(f"\n  {CY}{summary}{R}")
        return summary
