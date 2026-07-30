"""
cli/tui.py
==========
Light full-screen terminal UI for KerrOS (ADR-078).

Uses prompt_toolkit Application: conversation pane + input bar.
Brand chrome kept minimal (wordmark line). Soft-safe without an LLM —
type text to echo locally; bind an engine later for live chat.

Launch:
  python3 -m cli.tui
  KERROS_TUI=1 python3 cli/tui.py
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, List, Optional

TAGLINE = "SECURE BY DESIGN. BUILT FOR CONTROL."


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class KerrTUI:
    """Minimal full-screen REPL shell."""

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

    @staticmethod
    def _soft_echo(text: str) -> str:
        return f"[soft] {text}"

    def handle(self, user: str) -> Optional[str]:
        text = (user or "").strip()
        if not text:
            return None
        if text in ("/exit", "/quit", ":q"):
            return "__EXIT__"
        if text == "/help":
            return "Commands: /help /clear /exit — otherwise Soft-echo (or bound LLM)."
        if text == "/clear":
            self.lines = [f"{self.title}  —  {TAGLINE}", ""]
            return None
        self.lines.append(f"You › {text}")
        try:
            reply = self.reply_fn(text)
        except Exception as exc:
            reply = f"[error] {exc}"
        self.lines.append(f"KerrOS › {reply}")
        self.lines.append("")
        # Cap buffer
        if len(self.lines) > 400:
            self.lines = self.lines[-300:]
        return None

    def run(self) -> int:
        try:
            from prompt_toolkit.application import Application
            from prompt_toolkit.buffer import Buffer
            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.layout import HSplit, Layout, Window
            from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
            from prompt_toolkit.styles import Style
        except Exception as exc:
            print(f"[tui] prompt_toolkit required: {exc}", file=sys.stderr)
            print("[tui] falling back to line mode", file=sys.stderr)
            return self._line_fallback()

        output_control = FormattedTextControl(lambda: "\n".join(self.lines[-80:]))
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

        body = HSplit(
            [
                Window(content=output_control, wrap_lines=True),
                Window(height=1, char="─"),
                Window(BufferControl(buffer=input_buffer), height=1),
            ]
        )
        style = Style.from_dict(
            {
                "": "#d4a843",
                "frame": "#b03030",
            }
        )
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
            # Print last kerr line
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
