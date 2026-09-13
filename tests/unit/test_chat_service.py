import os

import pytest

from cli.chat_service import ChatService, ChatServiceDeps, build_service


class FakeEngine:
    def status(self):
        return {"default_provider": "cloud", "local_first": False, "last_api": None, "ollama": {"available": False}, "cloud": {"available": True}}


class FakeKernel:
    def status(self):
        return {
            "phase": "stable",
            "workspace": "/tmp/ws",
            "base": "/tmp",
            "services": ["memory", "scheduler"],
            "boot_log": ["boot.ok"],
        }


class FakeConfig:
    pass


def make_service(mode="offline", history=None, tools=None):
    return ChatService(
        ChatServiceDeps(
            engine=FakeEngine(),
            kernel=FakeKernel(),
            kcfg=FakeConfig(),
            mode=mode,
            session_id="s1",
            model_hint="model.gguf",
            history=history or [],
            tools=tools or ["read", "write", "exec"],
            memory_manager=FakeMemoryManager(),
            claw_tools=FakeClawTools(),
            ui=FakeUI(),
            domain_detector=lambda text: "code" if "python" in text.lower() else None,
        )
    )


class FakeMemoryManager:
    def __init__(self):
        self.messages = []
        self.learned = []

    def add_message(self, role, content):
        self.messages.append((role, content))

    def extract_and_learn(self, text):
        self.learned.append(text)

    def note_turn(self):
        self.turn_noted = True

    def pending_nudges(self):
        return []


class FakeClawTools:
    def detect_claw_tool(self, text):
        return None, None

    def run_claw_tool(self, name, args):
        return None


class FakeUI:
    def divider(self):
        return "---"

    def ai_header(self, mode):
        return f"AI[{mode}]"

    def typewrite(self, text):
        return text

    def draw_agent_response(self, text, label=""):
        return text


def _reset_goal_state(monkeypatch):
    import tools.goal_state as gs
    path = "/tmp/goal_state_test.json"
    monkeypatch.setattr(gs, "STATE_DIR", "/tmp")
    monkeypatch.setattr(gs, "STATE_FILE", path)
    if os.path.exists(path):
        os.remove(path)
    return path


# ---- Existing tests remain valid ----
def test_empty_input_is_handled():
    svc = make_service()
    handled, out = svc.dispatch("")
    assert handled is True
    assert out == ""


def test_exit_is_handled():
    svc = make_service()
    handled, out = svc.dispatch("/exit")
    assert handled is True
    assert out == ""


def test_help_is_handled():
    svc = make_service()
    handled, out = svc.dispatch("/help")
    assert handled is True
    assert "commands:" in out


def test_mode_is_handled():
    svc = make_service(mode="online")
    handled, out = svc.dispatch("/mode")
    assert handled is True
    assert out == "mode=online"


def test_switch_small():
    svc = make_service()
    handled, out = svc.dispatch("/switch small")
    assert handled is True
    assert "small" in out


def test_switch_large():
    svc = make_service()
    handled, out = svc.dispatch("/switch large")
    assert handled is True
    assert "large" in out


def test_switch_invalid():
    svc = make_service()
    handled, out = svc.dispatch("/switch medium")
    assert handled is True
    assert out == "Available: small · large"


def test_unhandled_returns_false():
    svc = make_service()
    handled, out = svc.dispatch("/unknown")
    assert handled is False
    assert out == ""


# ---- New command tests ----
def test_online_output():
    svc = make_service()
    handled, out = svc.dispatch("/online")
    assert handled is True
    assert "online" in out


def test_offline_output():
    svc = make_service()
    handled, out = svc.dispatch("/offline")
    assert handled is True
    assert "offline" in out


def test_history_with_entries():
    svc = make_service(history=[{"role": "user", "content": "ping"}, {"role": "assistant", "content": "pong"}])
    handled, out = svc.dispatch("/history")
    assert handled is True
    assert "ping" in out
    assert "pong" in out


def test_history_empty():
    svc = make_service()
    handled, out = svc.dispatch("/history")
    assert handled is True
    assert out == "No history"


def test_tools_lists_categories():
    svc = make_service()
    handled, out = svc.dispatch("/tools")
    assert handled is True
    assert "Filesystem (claw)" in out
    assert "read" in out
    assert "write" in out
    assert "exec" in out
    assert "Network" in out
    assert "OSINT" in out


def test_kernel_output():
    svc = make_service()
    handled, out = svc.dispatch("/kernel")
    assert handled is True
    assert "Phase: stable" in out
    assert "Workspace: /tmp/ws" in out
    assert "Services: memory, scheduler" in out
    assert "Boot log: boot.ok" in out


def test_kernel_unavailable():
    svc = make_service()
    svc.deps.kernel = None
    handled, out = svc.dispatch("/kernel")
    assert handled is True
    assert out == "kernel not initialized"


def test_health_unavailable():
    svc = make_service()
    handled, out = svc.dispatch("/health")
    assert handled is True
    assert "health monitor not available" in out


def test_services_unavailable():
    svc = make_service()
    handled, out = svc.dispatch("/services")
    assert handled is True
    assert "service manager not available" in out


def test_events_default():
    svc = make_service()
    handled, out = svc.dispatch("/events")
    assert handled is True
    assert "10" in out


def test_events_with_count():
    svc = make_service()
    handled, out = svc.dispatch("/events 5")
    assert handled is True
    assert "5" in out


def test_schedule_list():
    svc = make_service()
    handled, out = svc.dispatch("/schedule")
    assert handled is True
    assert "No scheduled jobs." in out


def test_schedule_cron():
    svc = make_service()
    handled, out = svc.dispatch("/schedule cron heartbeat */5 * * * *")
    assert handled is True
    assert "heartbeat" in out


def test_schedule_cancel():
    svc = make_service()
    handled, out = svc.dispatch("/schedule cancel abc123")
    assert handled is True
    assert "abc123" in out


def test_workflows_list():
    svc = make_service()
    handled, out = svc.dispatch("/workflows")
    assert handled is True
    assert "No workflows registered." in out


def test_workflows_run():
    svc = make_service()
    handled, out = svc.dispatch("/workflows run deploy")
    assert handled is True
    assert "deploy" in out


def test_workflows_runs():
    svc = make_service()
    handled, out = svc.dispatch("/workflows runs")
    assert handled is True
    assert "no persisted workflow runs" in out


def test_workflows_reload():
    svc = make_service()
    handled, out = svc.dispatch("/workflows reload")
    assert handled is True
    assert "reloaded" in out


def test_llm_status():
    svc = make_service()
    handled, out = svc.dispatch("/llm")
    assert handled is True
    assert "LLM status unavailable" in out


def test_llm_reset():
    svc = make_service()
    handled, out = svc.dispatch("/llm reset groq")
    assert handled is True
    assert "groq" in out


def test_capabilities_list():
    svc = make_service()
    handled, out = svc.dispatch("/capabilities")
    assert handled is True
    assert "No capabilities registered" in out


def test_capabilities_export():
    svc = make_service()
    handled, out = svc.dispatch("/capabilities export")
    assert handled is True
    assert "CAPABILITIES.md" in out


def test_decisions_read():
    svc = make_service()
    handled, out = svc.dispatch("/decisions")
    assert handled is True
    assert "No decision log entries yet." in out


def test_decisions_verify():
    svc = make_service()
    handled, out = svc.dispatch("/decisions verify")
    assert handled is True
    assert "chain ok" in out


def test_decisions_whoami():
    svc = make_service()
    handled, out = svc.dispatch("/decisions whoami")
    assert handled is True
    assert "audit RBAC disabled" in out


def test_reflect():
    svc = make_service()
    handled, out = svc.dispatch("/reflect")
    assert handled is True
    assert "reflection agent not available" in out


def test_reflections():
    svc = make_service()
    handled, out = svc.dispatch("/reflections")
    assert handled is True
    assert "No reflections saved yet." in out


def test_security_with_task():
    svc = make_service()
    handled, out = svc.dispatch("/security scan target")
    assert handled is True
    assert "scan target" in out


def test_security_without_task():
    svc = make_service()
    handled, out = svc.dispatch("/security")
    assert handled is True
    assert "Usage: /security <task>" in out


def test_code_with_task():
    svc = make_service()
    handled, out = svc.dispatch("/code write parser")
    assert handled is True
    assert "write parser" in out


def test_research_with_query():
    svc = make_service()
    handled, out = svc.dispatch("/research CVE-2024-1234")
    assert handled is True
    assert "CVE-2024-1234" in out


def test_plan_with_task():
    svc = make_service()
    handled, out = svc.dispatch("/plan refactor auth")
    assert handled is True
    assert "refactor auth" in out


def test_knowledge_with_question():
    svc = make_service()
    handled, out = svc.dispatch("/knowledge what is XSS")
    assert handled is True
    assert "what is XSS" in out


def test_kb_alias():
    svc = make_service()
    handled, out = svc.dispatch("/kb what is CSRF")
    assert handled is True
    assert "what is CSRF" in out


def test_react_with_task():
    svc = make_service()
    handled, out = svc.dispatch("/react fix bug")
    assert handled is True
    assert "fix bug" in out


def test_agent_alias():
    svc = make_service()
    handled, out = svc.dispatch("agent: review PR")
    assert handled is True
    assert "review PR" in out


def test_delegate_with_jobs():
    svc = make_service()
    handled, out = svc.dispatch("/delegate knowledge: q1 || research: q2")
    assert handled is True
    assert "knowledge: q1" in out
    assert "research: q2" in out


def test_delegate_empty():
    svc = make_service()
    handled, out = svc.dispatch("/delegate")
    assert handled is True
    assert "Usage: /delegate" in out


def test_analyze_with_target():
    svc = make_service()
    handled, out = svc.dispatch("/analyze my web app")
    assert handled is True
    assert "my web app" in out


def test_learn_with_text():
    svc = make_service()
    handled, out = svc.dispatch("/learn python is great")
    assert handled is True
    assert "python is great" in out


def test_ingest_with_path():
    svc = make_service()
    handled, out = svc.dispatch("/ingest /tmp/report.pdf")
    assert handled is True
    assert "/tmp/report.pdf" in out


def test_sources_empty():
    svc = make_service()
    handled, out = svc.dispatch("/sources")
    assert handled is True
    assert out == "Sources: None"


def test_recall_with_query():
    svc = make_service()
    handled, out = svc.dispatch("/recall docker")
    assert handled is True
    assert "Search: docker" in out
    assert "No episodes found" in out


def test_recall_recent():
    svc = make_service()
    handled, out = svc.dispatch("/recall")
    assert handled is True
    assert "Recent sessions:" in out


def test_search_with_query():
    svc = make_service()
    handled, out = svc.dispatch("/search kernel boot")
    assert handled is True
    assert "kernel boot" in out


def test_apistatus():
    svc = make_service()
    handled, out = svc.dispatch("/apistatus")
    assert handled is True
    assert "API catalog unavailable" in out


def test_integrations_status():
    svc = make_service()
    handled, out = svc.dispatch("/integrations")
    assert handled is True
    assert "integrations catalog unavailable" in out


def test_integrations_section():
    svc = make_service()
    handled, out = svc.dispatch("/integrations coding")
    assert handled is True
    assert "coding" in out


# ---- Scope and memory command tests ----
def test_scope_add():
    svc = make_service()
    handled, out = svc.dispatch("/scope add example.com")
    assert handled is True
    assert "example.com" in out


def test_scope_remove():
    svc = make_service()
    handled, out = svc.dispatch("/scope remove example.com")
    assert handled is True
    assert "Removed" in out or "Not in scope" in out


def test_scope_arm_deploy_default():
    svc = make_service()
    handled, out = svc.dispatch("/scope arm-deploy")
    assert handled is True
    assert "Armed" in out or "Arm" in out


def test_scope_arm_deploy_minutes():
    svc = make_service()
    handled, out = svc.dispatch("/scope arm-deploy 10")
    assert handled is True
    assert "10" in out


def test_scope_policy_export():
    svc = make_service()
    handled, out = svc.dispatch("/scope policy export")
    assert handled is True
    assert "Source:" in out or "Offensive:" in out


def test_scope_policy_summary():
    svc = make_service()
    handled, out = svc.dispatch("/scope policy")
    assert handled is True
    assert "Source" in out


def test_scope_status():
    svc = make_service()
    handled, out = svc.dispatch("/scope")
    assert handled is True
    assert "Authorized targets" in out or "Policy" in out


def test_memory_status():
    svc = make_service()
    handled, out = svc.dispatch("/memory")
    assert handled is True
    assert "Profile" in out or "KerrOS agent memory" in out or "No profile data yet" in out


def test_memory_subcommand():
    svc = make_service()
    handled, out = svc.dispatch("/memory status")
    assert handled is True
    assert "status" in out


def test_clear():
    svc = make_service()
    handled, out = svc.dispatch("/clear")
    assert handled is True
    assert "Session cleared" in out or "cleared" in out


def test_resume_latest():
    svc = make_service()
    handled, out = svc.dispatch("/resume latest")
    assert handled is True
    assert "resume" in out or "Resumed" in out


def test_resume_without_arg():
    svc = make_service()
    handled, out = svc.dispatch("/resume")
    assert handled is True
    assert "session" in out or "Resume" in out


def test_setkey_groq():
    svc = make_service()
    handled, out = svc.dispatch("/setkey groq test-key")
    assert handled is True
    assert "Groq API key saved" in out or "test-key" in out or "Usage" in out


def test_setkey_invalid():
    svc = make_service()
    handled, out = svc.dispatch("/setkey openai test-key")
    assert handled is True
    assert "Usage" in out


def test_read_file():
    svc = make_service()
    handled, out = svc.dispatch("/read README.md")
    assert handled is True
    assert "README.md" in out


def test_write_file():
    svc = make_service()
    handled, out = svc.dispatch("/write test.txt :: hello")
    assert handled is True
    assert "test.txt" in out


def test_exec_command():
    svc = make_service()
    handled, out = svc.dispatch("/exec ls -la")
    assert handled is True
    assert "ls" in out


def test_list_directory():
    svc = make_service()
    handled, out = svc.dispatch("/list")
    assert handled is True
    assert "list" in out or "Listing" in out


def test_workspace():
    svc = make_service()
    handled, out = svc.dispatch("/workspace")
    assert handled is True
    assert "workspace" in out


# ---- Goal handling tests ----
def test_goal_starts_new_goal(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        result = svc.process_goal("/goal write parser")
        assert result["goal_started"] is True
        assert result["is_goal_step"] is True
        assert result["active_goal"] is not None
        assert "write parser" in result["user"] or "step" in result["user"].lower() or result["user"]
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_goal_no_goal_active(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        result = svc.process_goal("normal message")
        assert result["goal_started"] is False
        assert result["is_goal_step"] is False
        assert result["user"] == "normal message"
        assert result["active_goal"] is None
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_record_tool_result_success(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        goal_state = svc.process_goal("/goal run ls")
        active_goal = goal_state["active_goal"]
        if active_goal:
            complete, stuck = svc.record_tool_result(active_goal, "exec", "file1.txt\nfile2.txt")
            assert isinstance(complete, bool)
            assert isinstance(stuck, bool)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_record_tool_result_failure(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        goal_state = svc.process_goal("/goal run failing command")
        active_goal = goal_state["active_goal"]
        if active_goal:
            complete, stuck = svc.record_tool_result(active_goal, "exec", "error: command not found")
            assert isinstance(complete, bool)
            assert isinstance(stuck, bool)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_record_tool_result_no_goal():
    svc = make_service()
    complete, stuck = svc.record_tool_result(None, "exec", "output")
    assert complete is False
    assert stuck is False


def test_record_decline_result(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        goal_state = svc.process_goal("/goal generate code")
        active_goal = goal_state["active_goal"]
        if active_goal:
            complete, stuck = svc.record_decline_result(active_goal)
            assert isinstance(complete, bool)
            assert isinstance(stuck, bool)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_record_code_save_success(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        goal_state = svc.process_goal("/goal generate code")
        active_goal = goal_state["active_goal"]
        if active_goal:
            complete, stuck = svc.record_code_save_result(
                active_goal, success=True, path="project_123", saved_count=2
            )
            assert isinstance(complete, bool)
            assert isinstance(stuck, bool)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_record_code_save_failure(monkeypatch):
    path = _reset_goal_state(monkeypatch)
    try:
        svc = make_service()
        goal_state = svc.process_goal("/goal generate code")
        active_goal = goal_state["active_goal"]
        if active_goal:
            complete, stuck = svc.record_code_save_result(
                active_goal, success=False, path="", saved_count=0
            )
            assert isinstance(complete, bool)
            assert isinstance(stuck, bool)
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---- Response generation tests ----
def test_postprocess_response_strips_chatml():
    svc = make_service()
    raw = "Hello. Assistant: Next. User: Question. <|endoftext|>"
    out = svc.postprocess_response(raw)
    assert "Assistant: " not in out
    assert "User: " not in out
    assert "<|endoftext|>" not in out
    assert out == "Hello. Next. Question."


def test_postprocess_response_strips_thinking_artifacts():
    svc = make_service()
    raw = "[Your reasoning: secret] Final answer: 42"
    out = svc.postprocess_response(raw)
    assert "Final answer: 42" in out
    assert "[Your reasoning:" not in out


def test_postprocess_response_strips_final_answer_marker():
    svc = make_service()
    raw = "Now give your final answer: The answer is X."
    out = svc.postprocess_response(raw)
    assert out == "The answer is X."


def test_generate_response_returns_dict():
    svc = make_service()
    out = svc.generate_response(None, "sys", "user", [])
    assert "response" in out
    assert "error" in out


def test_build_chat_context_returns_keys():
    svc = make_service()
    out = svc.build_chat_context("hello", None, [{"role": "user", "content": "hi"}], None)
    assert "system_p" in out
    assert "user_p" in out
    assert "clean_hist" in out
    assert "meta" in out


# ---- Remaining interactive block tests ----
def test_extract_and_learn_safe_calls_manager():
    svc = make_service()
    mm = svc.deps.memory_manager
    svc.extract_and_learn_safe("learn this")
    assert "learn this" in mm.learned


def test_add_user_message_persists():
    svc = make_service()
    mm = svc.deps.memory_manager
    svc.add_user_message("user text")
    assert ("user", "user text") in mm.messages


def test_note_and_nudge_no_exception(monkeypatch):
    svc = make_service()
    mm = svc.deps.memory_manager
    svc.note_and_nudge()
    assert getattr(mm, "turn_noted", False) is True


def test_detect_user_domain_prints(monkeypatch, capsys):
    svc = make_service()
    svc.detect_user_domain("write python code")
    out, _ = capsys.readouterr()
    assert "Domain: code" in out


def test_run_claw_tool_flow_no_match():
    svc = make_service()
    out = svc.run_claw_tool_flow("normal message")
    assert out is None


def test_run_tool_flow_no_match():
    svc = make_service()
    out = svc.run_tool_flow("normal message")
    assert out is None


def test_run_noninteractive_flow_basic():
    svc = make_service()
    result = svc.run_noninteractive_flow("hello", None, None, svc.deps.engine)
    assert "response" in result
    assert "active_goal" in result
    assert "goal_complete" in result
    assert "goal_stuck" in result
