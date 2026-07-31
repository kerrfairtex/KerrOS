"""
cli/tui.py
==========
Light full-screen terminal UI for KerrOS (ADR-078 / ADR-083 / ADR-099).

Uses prompt_toolkit Application: conversation + status/trace + channel ops
panes + input bar. Soft-safe without an LLM.

Launch:
  python3 -m cli.tui
  KERROS_TUI=1 python3 cli/tui.py
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable, List, Optional

TAGLINE = "SECURE BY DESIGN. BUILT FOR CONTROL."


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class KerrTUI:
    """Full-screen REPL with conversation, status/trace, and channel ops panes."""

    def __init__(
        self,
        *,
        reply_fn: Optional[Callable[[str], str]] = None,
        title: str = "KerrOS",
    ) -> None:
        self.reply_fn = reply_fn or self._soft_echo
        self.title = title
        self.lines: List[str] = [
            f"{title}  —  {TAGLINE}",
            "Type a message and press Enter. /exit or Ctrl-C to quit. /help for commands.",
            "",
        ]
        self.trace: List[str] = []
        self.channel_ops: List[str] = ["(channel ops — /channel soft-reply)"]
        self.show_ops = True
        self._started = time.strftime("%H:%M:%S")
        self.trace_event("boot", f"tui ready at {self._started}")

    @staticmethod
    def _soft_echo(text: str) -> str:
        return f"[soft] {text}"

    def trace_event(self, kind: str, detail: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.trace.append(f"{stamp} · {kind} · {detail}"[:120])
        if len(self.trace) > 80:
            self.trace = self.trace[-60:]
        try:
            from gateway.channels.trace import append_trace

            append_trace(f"tui:{kind}", {"detail": detail[:200]})
        except Exception:
            pass

    def status_text(self) -> str:
        mode = "llm" if _truthy(os.environ.get("KERROS_TUI_LLM")) else "soft"
        header = [
            f"STATUS  mode={mode}",
            f"trace={len(self.trace)}  lines={len(self.lines)}",
            "─" * 28,
        ]
        body = self.trace[-10:] or ["(no events yet)"]
        return "\n".join(header + body)

    def ops_text(self) -> str:
        header = ["CHANNEL OPS", "soft-reply · pump · trace", "─" * 28]
        body = self.channel_ops[-12:] or ["(empty)"]
        return "\n".join(header + body)

    def _record_ops(self, action: str, snippet: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.channel_ops.append(f"{stamp} › {action}")
        for line in str(snippet).splitlines()[:4]:
            self.channel_ops.append(f"  {line[:90]}")
        if len(self.channel_ops) > 60:
            self.channel_ops = self.channel_ops[-40:]

    def handle(self, user: str) -> Optional[str]:
        text = (user or "").strip()
        if not text:
            return None
        if text in ("/exit", "/quit", ":q"):
            self.trace_event("exit", "user quit")
            return "__EXIT__"
        if text == "/help":
            help_txt = (
                "Commands: /help /clear /trace /status /ops /channel /exit — "
                "otherwise Soft-echo (or bound LLM)."
            )
            self.lines.append(f"KerrOS › {help_txt}")
            self.lines.append("")
            self.trace_event("help", "shown")
            return None
        if text == "/clear":
            self.lines = [f"{self.title}  —  {TAGLINE}", ""]
            self.trace_event("clear", "conversation cleared")
            return None
        if text == "/trace":
            self.lines.append("KerrOS › recent trace:")
            for row in self.trace[-8:]:
                self.lines.append(f"  {row}")
            self.lines.append("")
            return None
        if text == "/status":
            self.lines.append(f"KerrOS › {self.status_text().splitlines()[0]}")
            self.lines.append("")
            self.trace_event("status", "shown")
            return None
        if text == "/ops":
            self.show_ops = not self.show_ops
            self.lines.append(
                f"KerrOS › channel ops pane {'on' if self.show_ops else 'off'}"
            )
            self.lines.append("")
            self.trace_event("ops", "toggled")
            return None
        if text == "/channel" or text.startswith("/channel "):
            arg = text[len("/channel") :].strip() or "soft-reply"
            try:
                from gateway.channels.registry import channels_cmd

                raw = channels_cmd(arg.split()[0], " ".join(arg.split()[1:]))
                snippet = str(raw)[:500]
                self.lines.append(f"KerrOS › channel {arg}:")
                self.lines.append(snippet[:240])
                self.lines.append("")
                self._record_ops(arg, snippet)
                self.trace_event("channel", arg[:60])
            except Exception as exc:
                self.lines.append(f"KerrOS › [channel error] {exc}")
                self.lines.append("")
                self.trace_event("error", str(exc)[:60])
            return None
        self.lines.append(f"You › {text}")
        self.trace_event("user", text[:60])
        try:
            reply = self.reply_fn(text)
        except Exception as exc:
            reply = f"[error] {exc}"
            self.trace_event("error", str(exc)[:60])
        else:
            self.trace_event("assistant", str(reply)[:60])
        self.lines.append(f"KerrOS › {reply}")
        self.lines.append("")
        if len(self.lines) > 400:
            self.lines = self.lines[-300:]
        return None

    def run(self) -> int:
        try:
            from prompt_toolkit.application import Application
            from prompt_toolkit.buffer import Buffer
            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
            from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
            from prompt_toolkit.styles import Style
        except Exception as exc:
            print(f"[tui] prompt_toolkit required: {exc}", file=sys.stderr)
            print("[tui] falling back to line mode", file=sys.stderr)
            return self._line_fallback()

        output_control = FormattedTextControl(lambda: "\n".join(self.lines[-80:]))
        status_control = FormattedTextControl(self.status_text)
        ops_control = FormattedTextControl(self.ops_text)
        input_buffer = Buffer()

        def refresh() -> None:
            app.invalidate()

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-d")
        def _(event) -> None:
            event.app.exit(result=0)

        @kb.add("enter")
        def _(event) -> None:
            text = input_buffer.text
            input_buffer.reset()
            code = self.handle(text)
            if code == "__EXIT__":
                event.app.exit(result=0)
                return
            refresh()

        right = VSplit(
            [
                Window(content=status_control, width=30, wrap_lines=True),
                Window(width=1, char="│"),
                Window(content=ops_control, width=34, wrap_lines=True),
            ]
        )
        panes = VSplit(
            [
                Window(content=output_control, wrap_lines=True),
                Window(width=1, char="│"),
                right,
            ]
        )
        body = HSplit(
            [
                panes,
                Window(height=1, char="─"),
                Window(BufferControl(buffer=input_buffer), height=1),
            ]
        )
        style = Style.from_dict({"": "#d4a843", "frame": "#b03030"})
        app = Application(
            layout=Layout(body, focused_element=input_buffer),
            key_bindings=kb,
            full_screen=True,
            style=style,
        )
        try:
            app.run()
        except (EOFError, KeyboardInterrupt):
            return 0
        return 0

    def _line_fallback(self) -> int:
        print(f"{self.title} — {TAGLINE} (line mode)")
        while True:
            try:
                user = input("⚔ You › ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            code = self.handle(user)
            if code == "__EXIT__":
                return 0
            for line in self.lines[-3:]:
                if line.startswith("KerrOS"):
                    print(line)
        return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    reply_fn = None
    if "--llm" in argv or _truthy(os.environ.get("KERROS_TUI_LLM")):
        try:
            from core.adaptive_engine import AdaptiveEngine
            from core.complete import generate_complete

            engine = AdaptiveEngine()
            try:
                engine.init_offline()
            except Exception:
                pass
            reply_fn = lambda t: str(
                generate_complete(engine, t, stream=False) or ""
            )[:2000]
        except Exception:
            reply_fn = None
    return KerrTUI(reply_fn=reply_fn).run()


if __name__ == "__main__":
    raise SystemExit(main())
