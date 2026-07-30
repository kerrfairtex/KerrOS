"""
adapters/tools/router_adapter.py
================================
Tool dispatch adapter wrapping kernel/router.py (KOS-007).
"""

from __future__ import annotations

from typing import Any

from kernel import router as kernel_router


class RouterAdapter:
    """
    Wraps kernel tool dispatch behind a stable dispatch(intent, payload) API.

    Intents:
        detect_tool — payload is user text (str) or {text, bypass_gate}
        run_tool    — payload is (tool, args) or {tool, args}
        detect_domain — payload is user text (str)
    """

    def dispatch(self, intent: str, payload: Any = None) -> Any:
        intent = (intent or "").strip().lower()
        if intent == "detect_tool":
            if isinstance(payload, dict):
                return kernel_router.detect_tool(
                    payload.get("text", ""),
                    bypass_gate=bool(payload.get("bypass_gate", False)),
                )
            return kernel_router.detect_tool(str(payload or ""))
        if intent == "run_tool":
            if isinstance(payload, dict):
                return self.run_tool(payload.get("tool"), payload.get("args"))
            if isinstance(payload, (list, tuple)) and len(payload) == 2:
                return self.run_tool(payload[0], payload[1])
            raise ValueError("run_tool payload must be {tool, args} or (tool, args)")
        if intent == "detect_domain":
            return kernel_router.detect_domain(str(payload or ""))
        raise ValueError(f"unknown dispatch intent: {intent}")

    def detect_tool(self, text: str, *, bypass_gate: bool = False):
        return kernel_router.detect_tool(text, bypass_gate=bypass_gate)

    def run_tool(self, tool: str, args: Any):
        # ADR-017: ToolPort audit for elevated dispatch (best-effort).
        try:
            from kernel.decision_log import record_decision

            record_decision(
                "tool_port",
                "run_tool",
                f"tool:{tool}",
                "dispatched",
                "",
            )
        except Exception:
            pass
        return kernel_router.run_tool(tool, args)

    def detect_domain(self, text: str):
        return kernel_router.detect_domain(text)
