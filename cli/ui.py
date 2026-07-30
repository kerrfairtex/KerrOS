"""
cli/ui.py
=========
Professional REPL presentation for KerrOS.

Keeps the angel + sword brand identity; upgrades structure to a clean
welcome panel, status line, and conversation chrome.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional

# ── ANSI ─────────────────────────────────────────────────
R = "\033[0m"
BOL = "\033[1m"
DIM = "\033[2m"
ITA = "\033[3m"
CY = "\033[96m"
YL = "\033[93m"
GR = "\033[92m"
RE = "\033[91m"
BL = "\033[94m"
PU = "\033[95m"
WH = "\033[97m"
GY = "\033[90m"
GO = "\033[33m"
RD = "\033[31m"
# Truecolor accents (gold / steel) — degrade fine on basic terminals
GOLD = "\033[1;38;2;212;168;67m"
STEEL = "\033[38;2;180;190;200m"
CRIMSON = "\033[1;38;2;176;48;48m"

VERSION = "1.0"

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
{CRIMSON}{BOL}  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
"""

# Backward-compatible alias used by older chat.py snippets
ANGEL_LOGO = ANGEL_MARK + WORDMARK + f"""
{GOLD}           ────────────────────────────────
{GOLD}{BOL}                     v {VERSION}
{GOLD}           ────────────────────────────────
"""


def _assets_dir() -> Path:
    return Path(os.path.expanduser("~/offline_ai")) / "assets"


def clear_screen() -> None:
    os.system("clear" if os.name != "nt" else "cls")


def render_boot_art(*, cols: int = 72, rows: int = 22) -> bool:
    """Render heraldic boot image via chafa when available; else ASCII mark.

    Returns True when an image (already carrying the KerrOS wordmark) was shown.
    """
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


class Spinner:
    """Brand spinner — sword travels the activity line."""

    FRAMES = ["⚔····", "·⚔···", "··⚔··", "···⚔·", "····⚔", "···⚔·", "··⚔··", "·⚔···"]

    def __init__(self, label: str = "Working"):
        self.label = label
        self._stop = False
        self._t: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop = False
        self._t = threading.Thread(target=self._spin, daemon=True)
        self._t.start()

    def _spin(self) -> None:
        i = 0
        while not self._stop:
            frame = self.FRAMES[i % len(self.FRAMES)]
            print(
                f"\r  {DIM}{self.label}{R}  {GOLD}{frame}{R}   ",
                end="",
                flush=True,
            )
            time.sleep(0.10)
            i += 1

    def stop(self) -> None:
        self._stop = True
        if self._t:
            self._t.join(timeout=1.0)
        print("\r" + " " * 56 + "\r", end="", flush=True)


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
    print(f"  {GY}{'─' * width}{R}")


def hairline(width: int = 56) -> None:
    print(f"  {DIM}{GY}{'·' * width}{R}")


def mode_badge(mode: str) -> str:
    if mode == "online":
        return f"{GR}{BOL}ONLINE{R}"
    return f"{BL}{BOL}OFFLINE{R}"


def status_line(
    *,
    mode: str,
    workspace: str = "",
    session_id: str = "",
    phase: str = "",
) -> None:
    """Compact status strip under the brand."""
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
    """Welcome panel: brand retained with a clean session info layout."""
    divider(56)
    status_line(mode=mode, workspace=workspace, session_id=session_id, phase=phase)
    if model_hint:
        print(f"  {GY}model{R}     {STEEL}{model_hint}{R}")
    print(f"  {GY}commands{R}  {YL}/help{R}  {DIM}· slash tools · claw fs · agents{R}")
    print(f"  {GY}brand{R}     {GOLD}angel · sword{R}  {DIM}— stay sharp{R}")
    divider(56)
    print(f"\n  {BOL}Ready.{R}  {DIM}Ask anything, or lead with /{R}\n")


def ai_header(mode: str) -> None:
    tag = f"{GR}net{R}" if mode == "online" else f"{BL}local{R}"
    print(f"\n  {GOLD}⚔{R} {CY}{BOL}KerrOS{R} {DIM}[{tag}]{R} {GOLD}›{R} ", end="")


def prompt_input() -> str:
    return input(f"\n  {GOLD}⚔{R} {YL}{BOL}You{R}  {GOLD}›{R} ").strip()


def ask_online_prompt() -> str:
    return input(
        f"\n  {GOLD}⚔{R} {YL}Connect online?{R} {DIM}[y/n]{R} "
    ).strip().lower()


def info_ok(msg: str) -> None:
    print(f"  {GR}✓{R}  {msg}")


def info_warn(msg: str) -> None:
    print(f"  {YL}!{R}  {msg}")


def info_mode(msg: str) -> None:
    print(f"  {BL}⚔{R}  {msg}")


def session_end() -> None:
    print(f"\n\n  {GOLD}⚔{R}  {GR}Session closed.{R}  {DIM}Stay sharp.{R}\n")


def boot_sequence() -> None:
    clear_screen()
    used_image = render_boot_art()
    if not used_image:
        # ASCII path already includes mark + KerrOS wordmark
        print()
    else:
        # Image carries KerrOS — keep a slim version line only
        print(f"{GOLD}           ────────────────────────────────{R}")
        print(f"{GOLD}{BOL}                     v {VERSION}{R}")
        print(f"{GOLD}           ────────────────────────────────{R}")
        print()
    time.sleep(0.15)
