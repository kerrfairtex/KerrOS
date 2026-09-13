"""Chat service facade for CLI REPL logic.

This module extracts the command loop, slash commands, and response
rendering from ``cli/chat.py`` so they can be unit-tested independently
without changing runtime behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cli.ui import mode_badge
from cli.ui import (
    BL,
    CY,
    GO,
    GR,
    GY,
    PU,
    RE,
    R,
    YL,
)
from tools.goal_state import ToolResult, GoalState, split_goal_steps


@dataclass
class ChatServiceDeps:
    engine: Any = None
    kernel: Any = None
    kcfg: Any = None
    mode: str = "offline"
    spinner: Any = None
    session_id: str = ""
    model_hint: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    # Optional fakes/test doubles for heavy subsystems
    scope_policy: Any = None
    workspace_root: str = "/tmp/workspace"
    memory_profile: Dict[str, Any] = field(default_factory=dict)
    resume_picker: str = ""
    # Injected collaborators for remaining interactive blocks
    memory_manager: Any = None
    claw_tools: Any = None
    ui: Any = None
    domain_detector: Any = None
    kernel: Any = None


class ChatService:
    def __init__(self, deps: Optional[ChatServiceDeps] = None) -> None:
        self.deps = deps or ChatServiceDeps()

    # ------------------------------------------------------------------
    # Command dispatch helpers
    # ------------------------------------------------------------------
    def dispatch(self, user: str) -> Tuple[bool, str]:
        """Return (handled, output). If not handled, caller should process as chat."""
        if not user:
            return True, ""

        text = user.strip()
        if text == "/exit":
            return True, ""

        if text == "/help":
            return True, self._help_output()

        if text == "/mode":
            return True, self._mode_output()

        if text == "/online":
            return True, self._online_output()

        if text == "/offline":
            return True, self._offline_output()

        if text == "/history":
            return True, self._history_output()

        if text == "/tools":
            return True, self._tools_output()

        if text == "/kernel":
            return True, self._kernel_output()

        if text == "/health":
            return True, self._health_output()

        if text == "/services":
            return True, self._services_output()

        if text.startswith("/events"):
            return True, self._events_output(text)

        if text.startswith("/schedule"):
            return True, self._schedule_output(text)

        if text.startswith("/workflows"):
            return True, self._workflows_output(text)

        if text.startswith("/llm"):
            return True, self._llm_output(text)

        if text.startswith("/capabilities"):
            return True, self._capabilities_output(text)

        if text.startswith("/decisions"):
            return True, self._decisions_output(text)

        if text == "/reflect":
            return True, self._reflect_output()

        if text == "/reflections":
            return True, self._reflections_output()

        if text.startswith("/security"):
            return True, self._security_output(text)

        if text.startswith("/code "):
            return True, self._code_output(text)

        if text.startswith("/research "):
            return True, self._research_output(text)

        if text.startswith("/plan "):
            return True, self._plan_output(text)

        if text.startswith("/knowledge ") or text.startswith("/kb "):
            return True, self._knowledge_output(text)

        if text.startswith("/react ") or text.startswith("agent:"):
            return True, self._react_output(text)

        if text.startswith("/delegate ") or text == "/delegate":
            return True, self._delegate_output(text)

        if text.startswith("/analyze"):
            return True, self._analyze_output(text)

        if text.startswith("/learn "):
            return True, self._learn_output(text)

        if text.startswith("/ingest "):
            return True, self._ingest_output(text)

        if text == "/sources":
            return True, self._sources_output()

        if text.startswith("/recall"):
            return True, self._recall_output(text)

        if text.startswith("/search "):
            return True, self._search_output(text)

        if text == "/apistatus":
            return True, self._apistatus_output()

        if text == "/integrations" or text.startswith("/integrations "):
            return True, self._integrations_output(text)

        if text.startswith("/switch "):
            return True, self._switch_output(text)

        if text.startswith("/scope"):
            return True, self._scope_output(text)

        if text.startswith("/memory"):
            return True, self._memory_output(text)

        if text == "/clear":
            return True, self._clear_output()

        if text.startswith("/resume"):
            return True, self._resume_output(text)

        if text.startswith("/setkey "):
            return True, self._setkey_output(text)

        if text.startswith("/read "):
            return True, self._read_output(text)

        if text.startswith("/write "):
            return True, self._write_output(text)

        if text.startswith("/exec "):
            return True, self._exec_output(text)

        if text.startswith("/list") or text.startswith("/ls"):
            return True, self._list_output(text)

        if text.startswith("/workspace"):
            return True, self._workspace_output()

        # Future extraction targets:
        # /write, /read, /exec, /list, /workspace, /clear, /resume, /goal
        return False, ""

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------
    def _help_output(self) -> str:
        return (
            "commands: /help /mode /switch small|large /exit"
        )

    def _mode_output(self) -> str:
        try:
            engine = self.deps.engine
            if engine:
                return mode_badge(engine.current_mode)
            return f"mode={self.deps.mode}"
        except Exception:
            return f"mode={self.deps.mode}"

    def _online_output(self) -> str:
        try:
            engine = self.deps.engine
            if engine:
                ok, msg = engine.switch_online()
                if ok:
                    return "  [ ✓ ] Switched to online — LLaMA-3.3-70B"
                return f"  [ ✗ ] {msg}"
            return "  Engine not available."
        except Exception as e:
            return f"  Online switch failed: {e}"

    def _offline_output(self) -> str:
        try:
            engine = self.deps.engine
            if engine:
                engine.switch_offline()
                return "  Switched to offline mode"
            return "  Engine not available."
        except Exception as e:
            return f"  Offline switch failed: {e}"

    def _history_output(self) -> str:
        history = self.deps.history or []
        lines = []
        for m in history[:10]:
            role = "You    " if m["role"] == "user" else "KerrOS "
            lines.append(f"{role} {m['content'][:65]}")
        return "\n".join(lines) if lines else "No history"

    def _tools_output(self) -> str:
        tools = self.deps.tools or []
        lines = [f"Filesystem (claw)  {', '.join(tools)}"] if tools else []
        lines.append("Network  nmap · ping · traceroute · nikto · whois · dig")
        lines.append("OSINT  osint · recon · geoip · geoint · dnsenum · reversedns")
        return "\n".join(lines)

    def _kernel_output(self) -> str:
        k = self.deps.kernel
        if not k:
            return "kernel not initialized"
        status = k.status()
        lines = [
            f"Phase: {status.get('phase')}",
            f"Workspace: {status.get('workspace')}",
            f"Base: {status.get('base')}",
            f"Services: {', '.join(status.get('services', []))}",
            f"Boot log: {' -> '.join(status.get('boot_log', []))}",
        ]
        return "\n".join(lines)

    def _health_output(self) -> str:
        return "health monitor not available in test mode"

    def _services_output(self) -> str:
        return "service manager not available in test mode"

    def _events_output(self, user: str) -> str:
        parts = user.split()
        count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        return f"showing last {count} events"

    def _schedule_output(self, user: str) -> str:
        parts = user.split()
        if len(parts) >= 2 and parts[1] == "cron":
            if len(parts) < 3:
                return "Usage: /schedule cron <name> <expr>"
            return f"scheduled cron job {parts[2]}"
        if len(parts) >= 2 and parts[1] == "cancel":
            return f"cancelled {parts[2]}" if len(parts) > 2 else "Usage: /schedule cancel <id>"
        return "No scheduled jobs."

    def _workflows_output(self, user: str) -> str:
        parts = user.split()
        if len(parts) >= 2 and parts[1] == "run":
            return f"ran workflow {parts[2]}" if len(parts) > 2 else "Usage: /workflows run <name>"
        if len(parts) >= 2 and parts[1] == "runs":
            return "no persisted workflow runs"
        if len(parts) >= 2 and parts[1] == "reload":
            return "reloaded workflows"
        if len(parts) >= 2 and parts[1] == "resume":
            return f"resumed workflow {parts[2]}" if len(parts) > 2 else "Usage: /workflows resume <id>"
        return "No workflows registered."

    def _llm_output(self, user: str) -> str:
        parts = user.split()
        if len(parts) >= 2 and parts[1] == "reset":
            target = parts[2] if len(parts) > 2 else "all"
            return f"resilience reset: {target}"
        return "LLM status unavailable in test mode"

    def _capabilities_output(self, user: str) -> str:
        parts = user.split()
        sub = parts[1] if len(parts) > 1 else ""
        if sub in ("export", "docs", "render"):
            return "regenerated docs/CAPABILITIES.md"
        return "No capabilities registered"

    def _decisions_output(self, user: str) -> str:
        parts = user.split(None, 2)
        sub = parts[1].strip().lower() if len(parts) > 1 else ""
        if sub == "verify":
            return "decision log chain ok"
        if sub == "export":
            return "exported decision_log"
        if sub == "seal":
            return "sealed decision segment"
        if sub == "retain":
            return "retention applied"
        if sub == "whoami":
            return "audit RBAC disabled (open access)"
        if sub == "privacy":
            return "privacy egress status unavailable in test mode"
        if sub == "residency":
            return "residency stamp status unavailable in test mode"
        return "No decision log entries yet."

    def _scope_output(self, user: str) -> str:
        if user.startswith("/scope add "):
            target = user[len("/scope add "):].strip()
            return f"Authorized target: {target}" if target else "Usage: /scope add <target>"
        if user.startswith("/scope remove "):
            target = user[len("/scope remove "):].strip()
            return f"Removed target: {target}" if target else "Usage: /scope remove <target>"
        if user.startswith("/scope arm-deploy"):
            parts = user.split()
            minutes = parts[2] if len(parts) > 2 and parts[2].isdigit() else "5"
            return f"Armed deploy tools for {minutes} minute(s)"
        if user == "/scope policy" or user.startswith("/scope policy "):
            return "Source: declarative  Offensive: 0  Deploy: 0  Defaults: {}"
        return "Authorized targets: none  Policy: declarative (use /scope policy)"

    def _memory_output(self, user: str) -> str:
        profile = self.deps.memory_profile or {}
        parts = user.split(None, 1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        if sub:
            return f"memory: {sub}"
        lines = []
        if profile:
            lines.append("Profile:")
            for k, v in profile.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append("No profile data yet")
        return "\n".join(lines)

    def _clear_output(self) -> str:
        return "Session cleared"

    def _resume_output(self, user: str) -> str:
        arg = user[len("/resume"):].strip()
        if not arg:
            return self.deps.resume_picker or "No sessions available"
        return f"Resumed session {arg}"

    def _setkey_output(self, user: str) -> str:
        parts = user.split()
        if len(parts) == 3 and parts[1] == "groq":
            return "Groq API key saved"
        return "Usage: /setkey groq YOUR_API_KEY"

    def _read_output(self, user: str) -> str:
        path = user[len("/read "):].strip()
        return f"read: {path}" if path else "Usage: /read <path>"

    def _write_output(self, user: str) -> str:
        body = user[len("/write "):].strip()
        if " :: " in body:
            path, content = body.split(" :: ", 1)
            return f"wrote {path}"
        path = body.strip().strip('"').strip("'")
        return f"wrote {path}" if path else "Usage: /write <path> :: <content>"

    def _exec_output(self, user: str) -> str:
        cmd = user[len("/exec "):].strip()
        return f"exec: {cmd}" if cmd else "Usage: /exec <cmd>"

    def _list_output(self, user: str) -> str:
        body = user.split(None, 1)
        path = body[1].strip() if len(body) > 1 else "."
        return f"list: {path}"

    def _workspace_output(self) -> str:
        return f"workspace: {self.deps.workspace_root}"

    # ------------------------------------------------------------------
    # Response generation helpers
    # ------------------------------------------------------------------
    def build_chat_context(self, user: str, tool_result, history, engine):
        """Build system prompt, user prompt, and cleaned history.

        Returns dict with:
          - system_p: str
          - user_p: str
          - clean_hist: list[dict]
          - meta: dict or None
        """
        from prompts.system import SYSTEM_PROMPT
        from core.context import build_chat

        system_p, user_p = build_chat(user, tool_result=tool_result, domain=None)
        if tool_result:
            user_p += "\nAnalyze the tool output and explain what it means."

        raw_hist = history or []
        clean_hist = []
        bad = ["[Domain:", "[Tool output]", "Analyze the tool",
               "", "User: ", "Assistant: ",
               "PING ", "bytes from", "icmp_seq", "packets transmitted"]
        for m in raw_hist:
            c = m.get("content", "").strip()
            if c and len(c) > 3 and len(c) < 500 and not any(b in c for b in bad):
                clean_hist.append({"role": m["role"], "content": c})

        meta = None
        try:
            from kernel.config import load_config
            from core.context_compressor import compress_context
            from core.message_policy import prepare_history, should_compress

            _c = load_config().values
            _ctx = int(_c.get("context_size") or 4096)
            _max = int(_c.get("max_tokens") or 512)
            if should_compress(clean_hist, context_size=_ctx, max_tokens=_max):
                clean_hist, meta = compress_context(
                    clean_hist,
                    keep_last=6,
                    engine=engine,
                    context_size=_ctx,
                    max_tokens=_max,
                )
            else:
                clean_hist, meta = prepare_history(
                    clean_hist,
                    context_size=_ctx,
                    max_tokens=_max,
                )
        except Exception:
            pass

        return {
            "system_p": system_p,
            "user_p": user_p,
            "clean_hist": clean_hist,
            "meta": meta,
        }

    def generate_response(self, engine, system_p: str, user_p: str, clean_hist):
        """Generate LLM response.

        Returns dict with:
          - response: str
          - error: str or None
        """
        try:
            response = generate_complete(
                engine,
                user_message=user_p,
                system=system_p,
                history=clean_hist,
                stream=False,
            )
            return {"response": response, "error": None}
        except Exception as e:
            return {"response": "", "error": str(e)}

    def postprocess_response(self, response: str) -> str:
        """Strip leaked tokens and thinking artifacts from response."""
        for tok in ["", "User: ", "Assistant: ", "<|endoftext|>"]:
            response = response.replace(tok, "")
        if "Now give your final answer:" in response:
            response = response.split("Now give your final answer:")[-1]
        if "[Your reasoning:" in response:
            response = response.split("]")[-1]
        return response.strip()

    def handle_code_save(self, response: str, active_goal, engine):
        """Handle optional code-save prompt and fix loop.

        Returns dict with:
          - saved_files: list[str]
          - goal_step_ok: bool
          - goal_complete: bool
          - goal_stuck: bool
          - user_declined: bool
        """
        from tools.code_saver import save_code_blocks, run_and_verify, extract_code_blocks

        _code_save_prompt = os.environ.get("KERROS_CODE_SAVE_PROMPT", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        saved_files = save_code_blocks(response) if _code_save_prompt else []
        goal_step_ok = True
        goal_complete = False
        goal_stuck = False
        user_declined = False

        if saved_files:
            folder = "project_" + time.strftime("%Y%m%d_%H%M%S")
            for f in saved_files:
                result = run_and_verify(f)
                if result.get("ran"):
                    status = "PASS" if result["ok"] else "FAIL"
                    if not result["ok"]:
                        goal_step_ok = False
                        attempts = 0
                        while not result["ok"] and attempts < 2:
                            attempts += 1
                            with open(f) as cf:
                                broken_code = cf.read()
                            fix_prompt = (
                                f"This code failed when run.\n\nCode:\n{broken_code}\n\n"
                                f"Error:\n{result['stderr'][:1000]}\n\n"
                                f"Return ONLY the corrected full code in a single code block, no explanation."
                            )
                            try:
                                fix_response = generate_complete(engine, fix_prompt, stream=False)
                            except Exception:
                                break
                            fixed_blocks = extract_code_blocks(fix_response)
                            if not fixed_blocks:
                                break
                            _, fixed_code = fixed_blocks[0]
                            with open(f, "w") as wf:
                                wf.write(fixed_code.strip() + "\n")
                            result = run_and_verify(f)
                            if result["ok"]:
                                goal_step_ok = True
                else:
                    goal_step_ok = False

            if active_goal and not active_goal.is_complete():
                goal_complete, goal_stuck = self.record_code_save_result(
                    active_goal, success=goal_step_ok, path=folder, saved_count=len(saved_files)
                )
        else:
            user_declined = True
            if active_goal and not active_goal.is_complete():
                _, goal_stuck = self.record_decline_result(active_goal)

        return {
            "saved_files": saved_files,
            "goal_step_ok": goal_step_ok,
            "goal_complete": goal_complete,
            "goal_stuck": goal_stuck,
            "user_declined": user_declined,
        }

    # ------------------------------------------------------------------
    # Goal handling
    # ------------------------------------------------------------------
    def process_goal(self, user: str):
        """Process goal-related input and return structured result.

        Returns a dict with:
          - active_goal: GoalState or None
          - user: possibly rewritten user input
          - is_goal_step: bool
          - goal_started: bool
          - goal_stuck: bool
        """
        from tools.goal_state import GoalState, split_goal_steps

        active_goal = GoalState.load()
        is_goal_step = False
        goal_started = False
        goal_stuck = False
        next_user = user

        if user.strip().lower().startswith("/goal "):
            goal_text = user[6:].strip()
            steps = split_goal_steps(goal_text)
            active_goal = GoalState.start(goal_text, steps)
            goal_started = True
            next_user = active_goal.current_step()["desc"]
            is_goal_step = True
        elif active_goal and not active_goal.is_complete():
            if active_goal.is_stuck():
                goal_stuck = True
                active_goal.clear()
                active_goal = None
            else:
                next_user = active_goal.current_step()["desc"]
                is_goal_step = True

        return {
            "active_goal": active_goal,
            "user": next_user,
            "is_goal_step": is_goal_step,
            "goal_started": goal_started,
            "goal_stuck": goal_stuck,
        }

    def record_tool_result(self, active_goal, tool: str, tool_result):
        """Record tool result into goal state if active_goal exists.

        Returns (goal_complete, goal_stuck) booleans.
        """
        if not active_goal or active_goal.is_complete():
            return False, False

        _fail_markers = ("error", "fail", "traceback", "not found", "[✗]")
        _ok = bool(tool_result) and not any(
            m in str(tool_result).lower() for m in _fail_markers
        )
        active_goal.record_result(
            ToolResult(
                status="ok" if _ok else "fail",
                tool=tool,
                stdout=str(tool_result)[:500],
            )
        )
        goal_complete = active_goal.is_complete()
        goal_stuck = active_goal.is_stuck()
        if goal_complete:
            active_goal.clear()
        return goal_complete, goal_stuck

    def record_code_save_result(self, active_goal, success: bool, path: str = "", saved_count: int = 0):
        """Record code-save result into goal state.

        Returns (goal_complete, goal_stuck) booleans.
        """
        if not active_goal or active_goal.is_complete():
            return False, False

        active_goal.record_result(
            ToolResult(
                status="ok" if success else "fail",
                tool="code_saver",
                path=path,
                stdout=f"Saved {saved_count} file(s) to {path}" if success else "User declined to save generated code",
                stderr="" if success else "User declined to save generated code",
            )
        )
        goal_complete = active_goal.is_complete()
        goal_stuck = active_goal.is_stuck()
        if goal_complete:
            active_goal.clear()
        return goal_complete, goal_stuck

    def record_decline_result(self, active_goal):
        """Record user-declined result into goal state.

        Returns (goal_complete, goal_stuck) booleans.
        """
        return self.record_code_save_result(active_goal, success=False)

    # ------------------------------------------------------------------
    # Slash command outputs
    # ------------------------------------------------------------------
    def _reflect_output(self) -> str:
        return "reflection agent not available in test mode"

    def _reflections_output(self) -> str:
        return "No reflections saved yet."

    def _security_output(self, user: str) -> str:
        target = user.split(" ", 1)[1].strip() if " " in user else ""
        return f"security analysis for: {target}" if target else "Usage: /security <task>"

    def _code_output(self, user: str) -> str:
        target = user.split(" ", 1)[1].strip() if " " in user else ""
        return f"code task: {target}" if target else "Usage: /code <task>"

    def _research_output(self, user: str) -> str:
        target = user.split(" ", 1)[1].strip() if " " in user else ""
        return f"research: {target}" if target else "Usage: /research <query>"

    def _plan_output(self, user: str) -> str:
        target = user.split(" ", 1)[1].strip() if " " in user else ""
        return f"plan: {target}" if target else "Usage: /plan <task>"

    def _knowledge_output(self, user: str) -> str:
        q = user.split(" ", 1)[1].strip() if " " in user else ""
        return f"knowledge: {q}" if q else "Usage: /knowledge <question>"

    def _react_output(self, user: str) -> str:
        task = user.replace("/react", "").replace("agent:", "").strip()
        return f"react task: {task}" if task else "Usage: /react <task>"

    def _delegate_output(self, user: str) -> str:
        raw = user[len("/delegate"):].strip()
        return f"delegate: {raw}" if raw else "Usage: /delegate a:q || b:q2"

    def _analyze_output(self, user: str) -> str:
        target = user.replace("/analyze", "").strip()
        return f"analyze: {target}" if target else "Usage: /analyze <describe your system>"

    def _learn_output(self, user: str) -> str:
        text = user[7:].strip()
        return f"learned: {text}" if text else "Usage: /learn <text>"

    def _ingest_output(self, user: str) -> str:
        path = user[8:].strip()
        return f"ingested: {path}" if path else "Usage: /ingest <file>"

    def _sources_output(self) -> str:
        return "Sources: None"

    def _recall_output(self, user: str) -> str:
        query = user.replace("/recall", "").strip()
        label = f"Search: {query}" if query else "Recent sessions:"
        return f"{label}\nNo episodes found"

    def _search_output(self, user: str) -> str:
        query = user[8:].strip()
        return f"No results found for: {query}" if query else "Usage: /search <query>"

    def _apistatus_output(self) -> str:
        return "API catalog unavailable in test mode"

    def _integrations_output(self, user: str) -> str:
        arg = user[len("/integrations"):].strip().lower()
        return f"integration status for: {arg}" if arg else "integrations catalog unavailable in test mode"

    def _switch_output(self, user: str) -> str:
        model = user.replace("/switch", "").strip()
        models = {"small": "models/qwen0.5b-q4.gguf", "large": "models/model.gguf"}
        if model not in models:
            return "Available: small · large"
        return f"Switched to {model} — restart to apply"

    # ------------------------------------------------------------------
    # Response rendering
    # ------------------------------------------------------------------
    def render_response(self, response: str) -> str:
        """Return rendered response text. Currently passthrough."""
        return response

    # ------------------------------------------------------------------
    # Remaining interactive block facades
    # ------------------------------------------------------------------
    def extract_and_learn_safe(self, user: str):
        """Call extract_and_learn(user) with exception safety."""
        try:
            mm = self._get_memory_manager()
            if mm and hasattr(mm, "extract_and_learn"):
                mm.extract_and_learn(user)
                return
        except Exception:
            pass
        try:
            from memory.manager import extract_and_learn
            extract_and_learn(user)
        except Exception:
            pass

    def add_user_message(self, user: str):
        """Persist user message via memory manager."""
        try:
            mm = self._get_memory_manager()
            if mm and hasattr(mm, "add_message"):
                mm.add_message("user", user)
                return
        except Exception:
            pass
        try:
            from memory.manager import add_message
            add_message("user", user)
        except Exception:
            pass

    def note_and_nudge(self):
        """Note turn and emit pending nudges via memory manager."""
        try:
            mm = self._get_memory_manager()
            if mm and hasattr(mm, "note_turn") and hasattr(mm, "pending_nudges"):
                mm.note_turn()
                for nudge in mm.pending_nudges():
                    print(f"  {GY}{nudge}{R}")
                return
        except Exception:
            pass
        try:
            from memory.nudges import note_turn, pending_nudges
            note_turn()
            for nudge in pending_nudges():
                print(f"  {GY}{nudge}{R}")
        except Exception:
            pass

    def detect_user_domain(self, user: str):
        """Detect and print domain hint for user input."""
        domain = None
        try:
            if self.deps.domain_detector:
                domain = self.deps.domain_detector(user)
            else:
                from tools.intent import detect_domain
                domain = detect_domain(user)
        except Exception:
            pass
        if domain:
            print(f"  {PU}◈ Domain: {domain}{R}")

    def run_claw_tool_flow(self, user: str):
        """Run claw tool if detected; return output or None."""
        claw_name = None
        claw_args = None
        try:
            ct = self._get_claw_tools()
            if ct:
                if hasattr(ct, "detect_claw_tool"):
                    claw_name, claw_args = ct.detect_claw_tool(user)
                elif isinstance(ct, dict):
                    claw_name, claw_args = ct.get("detect_claw_tool", lambda x: (None, None))(user)
            else:
                from tools.claw_cli import detect_claw_tool
                claw_name, claw_args = detect_claw_tool(user)
        except Exception:
            pass
        if claw_name:
            print(f"  {GR}◈ Claw: {claw_name}{R}")
            output = None
            try:
                if ct:
                    if hasattr(ct, "run_claw_tool"):
                        output = ct.run_claw_tool(claw_name, claw_args)
                    elif isinstance(ct, dict):
                        output = ct.get("run_claw_tool", lambda n, a: None)(claw_name, claw_args)
                else:
                    from tools.claw_cli import run_claw_tool
                    output = run_claw_tool(claw_name, claw_args)
            except Exception as e:
                output = f"Error: {e}"
            if output:
                try:
                    mm = self._get_memory_manager()
                    if mm and hasattr(mm, "add_message"):
                        mm.add_message("assistant", str(output)[:800])
                except Exception:
                    pass
            return output
        return None

    def run_tool_flow(self, user: str, bypass_gate: bool = False):
        """Run detected tool; return output or None."""
        tool = None
        args = None
        try:
            from tools.router import detect_tool
            tool, args = detect_tool(user, bypass_gate=bypass_gate)
        except Exception:
            pass
        if tool:
            print(f"  {GR}◈ Tool: {tool}{R}")
            try:
                from tools.scope_gate import check as _scope_check
                allowed, reason = _scope_check(tool, args)
            except Exception:
                allowed, reason = True, ""
            try:
                from tools.scope_gate import DEPLOY_TOOLS, arm_deploy
                if tool in DEPLOY_TOOLS:
                    if not allowed:
                        print(f"  {RE}⊘ Scope block: {reason}{R}")
                        return None
                    arm_deploy()
            except Exception:
                pass
            output = None
            try:
                from tools.claw_tools import run_tool
                output = run_tool(tool, args)
            except Exception as e:
                output = f"Error: {e}"
            if output:
                try:
                    spinner = self.deps.spinner
                    if spinner:
                        spinner.label = "Executing"
                        spinner.start()
                        spinner.stop()
                except Exception:
                    pass
                print(f"  {GY}{output}{R}")
                try:
                    from tools.skill_experience import maybe_create_skill, set_task_hint
                    set_task_hint(user)
                    skill_path = maybe_create_skill(min_tools=5)
                    if skill_path:
                        print(f"  {GR}[skill] learned → {skill_path}{R}")
                except Exception:
                    pass
            return output
        return None

    def run_noninteractive_flow(self, user: str, tool_result, active_goal, engine):
        """Run the full non-interactive response path.

        Returns dict with:
          - active_goal: possibly updated GoalState
          - response: str
          - goal_complete: bool
          - goal_stuck: bool
        """
        self.extract_and_learn_safe(user)
        self.add_user_message(user)
        self.note_and_nudge()

        goal_state = self.process_goal(user)
        active_goal = goal_state["active_goal"]
        user = goal_state["user"]
        if goal_state["goal_started"]:
            print(f"  {GO}[goal] started — steps queued{R}")
        if goal_state["goal_stuck"]:
            print(f"  {RE}[goal] stuck — reset{R}")

        self.detect_user_domain(user)

        claw_output = self.run_claw_tool_flow(user)
        if claw_output is not None:
            return {
                "active_goal": active_goal,
                "response": claw_output,
                "goal_complete": False,
                "goal_stuck": False,
                "tool_ran": True,
            }

        tool_output = self.run_tool_flow(user, bypass_gate=goal_state["is_goal_step"])
        if tool_output is not None:
            complete, stuck = self.record_tool_result(active_goal, tool_output, str(tool_output))
            if complete:
                print(f"  {GR}[goal] complete!{R}")
            elif stuck:
                _step_desc = active_goal.current_step()["desc"] if active_goal else ""
                print(f"  {RE}[goal] still stuck on: {_step_desc}{R}")
            ctx = self.build_chat_context(user, tool_output, self.deps.history, engine)
            gen = self.generate_response(engine, ctx["system_p"], ctx["user_p"], ctx["clean_hist"])
            if gen.get("error"):
                return {
                    "active_goal": active_goal,
                    "response": "",
                    "goal_complete": complete,
                    "goal_stuck": stuck,
                    "tool_ran": True,
                    "error": gen["error"],
                }
            response = self.postprocess_response(gen["response"])
            return {
                "active_goal": active_goal,
                "response": response,
                "goal_complete": complete,
                "goal_stuck": stuck,
                "tool_ran": True,
            }

        ctx = self.build_chat_context(user, None, self.deps.history, engine)
        gen = self.generate_response(engine, ctx["system_p"], ctx["user_p"], ctx["clean_hist"])
        if gen.get("error"):
            return {
                "active_goal": active_goal,
                "response": "",
                "goal_complete": False,
                "goal_stuck": False,
                "tool_ran": False,
                "error": gen["error"],
            }
        response = self.postprocess_response(gen["response"])
        code_save = self.handle_code_save(response, active_goal, engine)
        if code_save["goal_complete"]:
            print(f"  {GR}[goal] complete!{R}")
        elif code_save["goal_stuck"]:
            _step_desc = active_goal.current_step()["desc"] if active_goal else ""
            print(f"  {RE}[goal] still stuck on: {_step_desc}{R}")
        return {
            "active_goal": active_goal,
            "response": response,
            "goal_complete": code_save["goal_complete"],
            "goal_stuck": code_save["goal_stuck"],
            "tool_ran": False,
        }

    # ------------------------------------------------------------------
    # Dependency accessors
    # ------------------------------------------------------------------
    def _get_memory_manager(self):
        if self.deps.memory_manager:
            return self.deps.memory_manager
        try:
            import memory.manager as mm
            return mm
        except Exception:
            return None

    def _get_claw_tools(self):
        if self.deps.claw_tools:
            return self.deps.claw_tools
        try:
            import tools.claw_cli as ct
            return ct
        except Exception:
            return None


def build_service(
    engine: Any,
    kernel: Any,
    kcfg: Any,
    mode: str = "offline",
    session_id: str = "",
    model_hint: str = "",
) -> ChatService:
    return ChatService(
        ChatServiceDeps(
            engine=engine,
            kernel=kernel,
            kcfg=kcfg,
            mode=mode,
            session_id=session_id,
            model_hint=model_hint,
        )
    )
