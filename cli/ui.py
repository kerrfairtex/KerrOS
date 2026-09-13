"""
cli/ui.py
=========
Professional REPL presentation for KerrOS — Hermes-style boxed panels.

Layout:
1. Header panel: ┌─ # KerrOS | {mode} | {model} ─────────────────────┐
2. Each agent response in its own bordered box (╭─ KerrOS ─╮ ... ╰─╯)
3. Persistent status bar: model, tokens, context-fill %, cost, session duration
4. User input with bullet marker, agent responses with distinct marker
5. Slash-command palette (triggered by "/")
6. Loading spinner animation (blinking "Thinking" text)
7. Colors: Gold borders, Soft gold labels, Bright white text, Red alerts
8. ASCII fallback for terminals without Unicode box-drawing support

Dark Theme Colors:
- GOLD (#FFD700): Borders and highlights
- WHITE_BRIGHT: Main text (#FFFFFF)
- SUCCESS_GREEN (#32CD32): Positive feedback
- ALERT_RED (#DC143C): Errors and warnings
"""

from __future__ import annotations

import os
import shutil
import threading
import time
import sys
from pathlib import Path
from typing import Any, Optional, List, Dict

from core.config import BASE

# ── Terminal capability detection ──────────────────────────
def _supports_box_drawing() -> bool:
    """Check if terminal supports Unicode box-drawing characters."""
    # Can be overridden by env var
    if os.environ.get("KERROS_ASCII_UI"):
        return False
    # Most modern terminals support it, but some SSH/Termux configs don't
    term = os.environ.get("TERM", "")
    if "xterm" in term or "screen" in term or "tmux" in term or "vt" in term:
        return True
    # Default to True for local Termux/Android
    return True

USE_UNICODE_BOX = _supports_box_drawing()

# Box-drawing characters (Unicode + ASCII fallback)
if USE_UNICODE_BOX:
    TL = "╭"  # top-left
    TR = "╮"  # top-right
    BL = "╰"  # bottom-left
    BR = "╯"  # bottom-right
    H  = "─"  # horizontal
    V  = "│"  # vertical
    TL_BOLD = "╭"
    TR_BOLD = "╮"
else:
    TL = "+"
    TR = "+"
    BL = "+"
    BR = "+"
    H  = "-"
    V  = "|"
    TL_BOLD = "+"
    TR_BOLD = "+"

# ── ANSI Colors ────────────────────────────────────────────
# Dark theme: Background dark gray/black, headers yellow/gold, main text white

# Standard reset
R = "\033[0m"
# Text styles
BOL = "\033[1m"
DIM = "\033[2m"
ITA = "\033[3m"
BLINK = "\033[5m"  # Blink mode for animated text

# Standard ANSI colors (bright for visibility on dark)
CY = "\033[96m"  # Bright Cyan
YL = "\033[93m"  # Bright Yellow (headers & accents)
GR = "\033[92m"  # Bright Green
RE = "\033[91m"  # Bright Red
BL = "\033[94m"  # Bright Blue
PU = "\033[95m"  # Bright Magenta
WH = "\033[97m"  # Bright White (main text)
GY = "\033[90m"  # Dark Gray (for separators/subtle elements)
GO = "\033[33m"  # Standard Yellow
RD = "\033[31m"  # Standard Red

# Truecolor accents for dark theme
# Gold/Yellow (#FFD700) - bright accent color for borders and highlights
GOLD = "\033[1;38;2;255;215;0m"
# Soft Yellow/Gold for headers - slightly desaturated for dark backgrounds
GOLD_SOFT = "\033[38;2;255;215;0m"
# Bright White for main text (more readable than standard white)
WHITE_BRIGHT = "\033[97m"
# Light Gray for secondary/subtle text
GRAY_LIGHT = "\033[38;2;200;200;200m"
# Teal for soft highlights
TEAL = "\033[38;2;0;150;150m"
# Deep Blue for cool elements
BLUE_DEEP = "\033[38;2;0;120;215m"
# Solid Red (#DC143C) for alerts - more visible on dark
ALERT_RED = "\033[38;2;220;20;60m"
# Success Green for positive feedback
SUCCESS_GREEN = "\033[38;2;50;205;50m"
# Steel for secondary text (kept for compatibility)
STEEL = "\033[38;2;180;190;200m"
CRIMSON = "\033[1;38;2;220;20;60m"

VERSION = "1.0"
TAGLINE = "SECURE BY DESIGN. BUILT FOR CONTROL."

# Heraldic angel wings + sword tip (brand) — refined geometry, not cartoon.
ANGEL_MARK = f"""
{CRIMSON}{BOL}              ╲╲___                ___╱╱
{CRIMSON}{BOL}             ╲╲╲╲╲___          ___╱╱╱╱╱
{GOLD}{BOL}            ╲╲╲╲╲╲╲╲__      __╱╱╱╱╱╱╱╱
{GOLD}{BOL}             ╲╲╲╲╲╲  ╲    ╱  ╱╱╱╱╱╱
{STEEL}{BOL}                ╲╲╲╲  │  │  ╱╱╱╱
{STEEL}{BOL}                   ╲  │⚔│  ╱
{GOLD}{BOL}                      ││
{STEEL}                      ││
{CRIMSON}                      ▔▔
"""

WORDMARK = f"""
{GOLD}{BOL}  ██╗  ██╗███████╗██████╗ ██████╗  ██████╗ ███████╗
{GOLD}{BOL}  ██║ ██╔╝██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔════╝
{GOLD}{BOL}  █████╔╝ █████╗  ██████╔╝██████╔╝██║   ██║███████╗
{CRIMSON}{BOL}  ██╔═██╗ ██╔══╝  ██╔══██╗██╔══██╗██║   ██║╚════██║
{CRIMSON}{BOL}  ██║  ██╗███████╗██║  ██║██║  ██║╚██████╔╝███████║
{CRIMSON}{BOL}  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚══════╝
"""

# Backward-compatible alias used by older chat.py snippets
ANGEL_LOGO = ANGEL_MARK + WORDMARK + f"""
{GOLD}           ────────────────────────────────
{GOLD}{BOL}                     v {VERSION}
{STEEL}{DIM}      {TAGLINE}
{GOLD}           ────────────────────────────────
"""


# ── Box rendering utilities ────────────────────────────────
def _get_terminal_width() -> int:
    """Get current terminal width, default 80."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80

def _wrap_text(text: str, width: int) -> List[str]:
    """Wrap text to fit within width, handling ANSI codes."""
    import re
    lines = []
    for line in text.split("\n"):
        if len(line) <= width:
            lines.append(line)
        else:
            # Simple word wrap
            words = line.split(" ")
            current = ""
            for word in words:
                if len(current) + len(word) + 1 <= width:
                    current += (" " if current else "") + word
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
    return lines if lines else [""]

def draw_box(
    content: str,
    label: str = "",
    width: Optional[int] = None,
    color: str = GOLD,
    label_color: str = GOLD_SOFT,  # Bright gold for labels on dark bg
    content_color: str = "",
    is_error: bool = False
) -> str:
    """
    Draw a bordered box around content.
    
    Args:
        content: Text content (may contain newlines)
        label: Short label for top border (e.g., "KerrOS", "local")
        width: Box width (auto-detect terminal if None)
        color: Border color
        label_color: Label text color
        content_color: Override for content color
        is_error: Use alert red for borders/content
    """
    if width is None:
        width = _get_terminal_width()
    
    # Usable content width = box width - 2 (side borders) - 2 (padding)
    content_width = max(10, width - 4)
    
    if is_error:
        border_color = ALERT_RED
        label_color = ALERT_RED
    else:
        border_color = color
    
    content_lines = _wrap_text(content, content_width)
    
    # Build top border with label
    if label:
        label_str = f" {label} "
        label_display = f"{label_color}{label_str}{R}{border_color}"
        remaining = width - 2 - len(label_str)  # -2 for TL/TR
        if remaining < 0:
            remaining = 0
        top = f"{border_color}{TL}{H * len(label_str)}{label_display}{H * remaining}{TR}{R}"
    else:
        top = f"{border_color}{TL}{H * (width - 2)}{TR}{R}"
    
    # Build middle lines
    middle_lines = []
    for line in content_lines:
        # Strip ANSI for length calculation
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', line)
        padding = content_width - len(plain)
        if padding < 0:
            padding = 0
        content_display = f"{content_color or ''}{line}{R}" if content_color else line
        middle_lines.append(f"{border_color}{V}{R} {content_display}{' ' * padding} {border_color}{V}{R}")
    
    # Build bottom border
    bottom = f"{border_color}{BL}{H * (width - 2)}{BR}{R}"
    
    return "\n".join([top] + middle_lines + [bottom])

def draw_header_panel(
    model: str = "offline",
    mode: str = "offline",
    version: str = VERSION,
    width: Optional[int] = None
) -> str:
    """Draw the main header boxed panel with simple format.
    
    Format: ┌─ # KerrOS | {mode} | {model} ─────────────────────┐
    Uses bright yellow/gold borders with white text on dark background.
    """
    if width is None:
        width = _get_terminal_width()
    
    # Build the header text
    # Format: # KerrOS | {mode} | {model}
    title = f"# KerrOS | {mode} | {model}"
    
    # Calculate spacer width: total width - len(prefix + title + trailing)
    prefix = "┌─ "
    trailing = " ─┐"
    spacer_len = max(0, width - len(prefix) - len(title) - len(trailing))
    
    # Build the top border line
    top = f"{GOLD}{prefix}{GOLD}{title}{GOLD}{'─' * spacer_len}{trailing}{R}"
    
    return top

def draw_status_bar(
    model: str = "offline",
    tokens: int = 0,
    context_pct: float = 0.0,
    cost: float = 0.0,
    session_duration: str = "0s",
    width: Optional[int] = None
) -> str:
    """Draw persistent status bar above input line."""
    if width is None:
        width = _get_terminal_width()
    
    parts = [
        f"{GOLD}Model:{R} {CY}{model}{R}",
        f"{GOLD}Tokens:{R} {WH}{tokens}{R}",
        f"{GOLD}Context:{R} {WH}{context_pct:.0f}%{R}",
        f"{GOLD}Cost:{R} {WH}${cost:.4f}{R}",
        f"{GOLD}Session:{R} {WH}{session_duration}{R}",
    ]
    
    # Join with separators, truncate if too long
    bar = "  ".join(parts)
    import re
    plain_len = len(re.sub(r'\033\[[0-9;]*m', '', bar))
    if plain_len > width:
        # Drop less critical parts
        bar = "  ".join(parts[:3])
    
    return f"{GY}{'─' * width}{R}\n{bar}"

def draw_agent_response(
    content: str,
    label: str = "KerrOS",
    is_error: bool = False,
    width: Optional[int] = None
) -> str:
    """Draw a single agent response in a bordered box."""
    return draw_box(
        content,
        label=label,
        width=width,
        is_error=is_error
    )

def draw_user_input_line(prompt: str = "") -> str:
    """Draw user input line with bullet marker."""
    return f"\n  {GOLD}●{R} {WH}{prompt}{R} "

# ── Slash Command Palette ──────────────────────────────────
SLASH_COMMANDS: Dict[str, str] = {
    "/help": "Show this help",
    "/mode": "Show current mode (online/offline)",
    "/online": "Switch to online mode",
    "/offline": "Switch to offline mode",
    "/model": "Show/switch model",
    "/clear": "Clear conversation history",
    "/memory": "Memory commands (add/list/recall)",
    "/history": "Show conversation history",
    "/tools": "List available tools",
    "/kernel": "Kernel status",
    "/health": "Health check",
    "/services": "List services",
    "/events": "Event log",
    "/schedule": "Scheduled tasks",
    "/workflows": "Workflow management",
    "/llm": "LLM provider status",
    "/capabilities": "Agent capabilities",
    "/security": "Security tools",
    "/code": "Code generation/saving",
    "/research": "Research mode",
    "/plan": "Planning mode",
    "/knowledge": "Knowledge base",
    "/react": "ReAct agent",
    "/delegate": "Delegate to subagent",
    "/analyze": "Analyze code/file",
    "/switch": "Switch model",
    "/learn": "Learn from input",
    "/ingest": "Ingest file to memory",
    "/sources": "Memory sources",
    "/recall": "Recall from memory",
    "/search": "Search memory",
    "/scope": "Scope management",
    "/apistatus": "API key status",
    "/setkey": "Set API key",
    "/exit": "Exit KerrOS",
}

def show_command_palette(partial: str = "") -> List[str]:
    """Return filtered slash commands matching partial input."""
    matches = []
    for cmd, desc in SLASH_COMMANDS.items():
        if cmd.startswith(partial):
            matches.append(f"  {CY}{cmd}{R}  {GY}{desc}{R}")
    return matches

def render_command_palette(partial: str = "") -> str:
    """Render the slash-command palette as a box."""
    matches = show_command_palette(partial)
    if not matches:
        return ""
    content = "\n".join(matches)
    return draw_box(content, label=" Commands ", width=_get_terminal_width())

# ── Loading Spinner (blinking text animation) ────────────────────────
class SwordSpinner:
    """Animated loading spinner using blinking text.
    
    Displays a blinking "Thinking" text with braille spinner animation
    before the label, that alternates between visible and dimmed states,
    creating a subtle animation that works well in dark themes.
    """
    
    # Braille spinner frames: ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, label: str = "Thinking", color: str = GY):
        self.label = label
        self.color = color  # Default to gray for "Thinking"
        self._stop = False
        self._t: Optional[threading.Thread] = None
        self._visible = True
        self._frame_idx = 0
    
    def start(self) -> None:
        """Start the spinner animation in a background thread."""
        self._stop = False
        self._frame_idx = 0
        self._t = threading.Thread(target=self._spin, daemon=True)
        self._t.start()
    
    def _spin(self) -> None:
        """Internal: run the blinking animation loop."""
        while not self._stop:
            # Alternate between normal color and dimmed
            style = self.color if self._visible else f"{DIM}{self.color}"
            spinner_frame = self.SPINNER_FRAMES[self._frame_idx % len(self.SPINNER_FRAMES)]
            sys.stdout.write(f"\r  {spinner_frame} {style}{self.label}{R}   ")
            sys.stdout.flush()
            self._visible = not self._visible
            self._frame_idx += 1
            time.sleep(0.12)  # 120ms total cycle
    
    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        self._stop = True
        if self._t:
            self._t.join(timeout=1.0)
        # Clear the spinner line completely
        sys.stdout.write("\r  " + " " * 50 + "\r")
        sys.stdout.flush()
    
    def set_label(self, label: str) -> None:
        """Update the spinner label."""
        self.label = label


# Backward-compatible alias
Spinner = SwordSpinner

# ── Existing functions (preserved for compatibility) ───────
def _assets_dir() -> Path:
    return BASE / "assets"

def clear_screen() -> None:
    os.system("clear" if os.name != "nt" else "cls")

def render_boot_art(*, cols: int = 72, rows: int = 22) -> bool:
    assets = _assets_dir()
    candidates = [assets / "boot_banner.png", assets / "boot_logo.png"]
    chafa = shutil.which("chafa")
    if chafa:
        for path in candidates:
            if not path.is_file():
                continue
            cmd = (
                f'{chafa} --size={cols}x{rows} --symbols=block '
                f'--colors=full "{path}"'
            )
            rc = os.system(cmd)
            if rc == 0:
                return True
    print(ANGEL_LOGO)
    return False

def typewrite(text: str, color: str = CY, delay: float = 0.008) -> None:
    for ch in text:
        print(f"{color}{ch}{R}", end="", flush=True)
        if ch in ".!?":
            time.sleep(0.05)
        elif ch == ",":
            time.sleep(0.02)
        else:
            time.sleep(delay)
    print()

def divider(width: int = 56) -> None:
    w = _get_terminal_width()
    print(f"  {GY}{H * (w - 4)}{R}")

def hairline(width: int = 56) -> None:
    w = _get_terminal_width()
    print(f"  {DIM}{GY}{H * (w - 4)}{R}")

def mode_badge(mode: str) -> str:
    if mode == "online":
        return f"{GR}{BOL}ONLINE{R}"
    return f"{GY}{BOL}OFFLINE{R}"

def status_line(
    *,
    mode: str,
    workspace: str = "",
    session_id: str = "",
    phase: str = "",
) -> None:
    ws = workspace or os.getcwd()
    if len(ws) > 42:
        ws = "…" + ws[-41:]
    bits = [
        f"{GOLD}⚔{R} {BOL}KerrOS{R}",
        mode_badge(mode),
    ]
    if phase:
        bits.append(f"{GY}kernel:{R}{CY}{phase}{R}")
    if session_id:
        bits.append(f"{GY}session:{R}{STEEL}{session_id[:16]}{R}")
    bits.append(f"{GY}{ws}{R}")
    print("  " + f"  {DIM}│{R}  ".join(bits))

def print_welcome_banner(
    *,
    mode: str,
    workspace: str = "",
    session_id: str = "",
    phase: str = "",
    model_hint: str = "",
) -> None:
    """Welcome panel: boxed header + status."""
    w = _get_terminal_width()
    # Header box
    print(draw_header_panel(model=model_hint or "offline", mode=mode, width=w))
    print()
    print(f"  {BOL}Ready.{R}  {DIM}Ask anything, or lead with /{R}\n")

def ai_header(mode: str) -> None:
    tag = f"{GR}net{R}" if mode == "online" else f"{BL}local{R}"
    print(f"\n  {GOLD}⚔{R} {CY}{BOL}KerrOS{R} {DIM}[{tag}]{R} {GOLD}›{R} ", end="")

def prompt_input() -> str:
    from cli.repl_input import prompt_line
    return prompt_line(f"\n  {GOLD}●{R} {YL}{BOL}You{R}  {GOLD}›{R} ")

def ask_online_prompt() -> str:
    return input(
        f"\n  {GOLD}⚔{R} {YL}Connect online?{R} {DIM}[y/n]{R} "
    ).strip().lower()

def info_ok(msg: str) -> None:
    """Print a success/info message in green."""
    print(f"  {SUCCESS_GREEN}✓{R}  {msg}")

def info_warn(msg: str) -> None:
    """Print a warning message in yellow."""
    print(f"  {YL}!{R}  {msg}")

def info_mode(msg: str) -> None:
    """Print a mode/status message in teal."""
    print(f"  {TEAL}⚔{R}  {msg}")

def info_error(msg: str) -> None:
    """Print an error message in red."""
    print(f"  {ALERT_RED}✗{R}  {msg}")

def session_end() -> None:
    print(f"\n\n  {GOLD}⚔{R}  {SUCCESS_GREEN}Session closed.{R}  {DIM}Stay sharp.{R}\n")

def boot_sequence() -> None:
    clear_screen()
    used_image = render_boot_art()
    if not used_image:
        print()
    time.sleep(0.15)
