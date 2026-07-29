#!/usr/bin/env python3
"""Static §6 OmniRoute security audit guards (bind / AES docs / promptfoo fixtures)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "omniroute" / "docker-compose.yml"
ENV_EXAMPLE = ROOT / "deploy" / "omniroute" / ".env.example"
AUDIT_DOC = ROOT / "docs" / "OMNIROUTE_SECURITY_AUDIT.md"
PROMPTFOO_DIR = ROOT / "eval" / "omniroute_rag_promptfoo"
FIXTURES = PROMPTFOO_DIR / "fixtures" / "rag_injected_prompts.json"
PROMPTFOO_CFG = PROMPTFOO_DIR / "promptfooconfig.yaml"
RUN_SCRIPT = ROOT / "scripts" / "run_omniroute_rag_promptfoo.sh"

REQUIRED_SECRET_KEYS = (
    "STORAGE_ENCRYPTION_KEY",
    "JWT_SECRET",
    "API_KEY_SECRET",
)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def check_loopback_compose() -> None:
    if not COMPOSE.is_file():
        _fail(f"missing {COMPOSE}")
    text = COMPOSE.read_text(encoding="utf-8")
    in_ports = False
    found = False
    for line in text.splitlines():
        if re.match(r"^\s*ports:\s*$", line):
            in_ports = True
            continue
        if in_ports:
            if re.match(r"^\s*[A-Za-z0-9_]+:\s*", line) and not line.strip().startswith("-"):
                in_ports = False
                continue
            m = re.match(r'^\s*-\s*["\']?([^"\'#]+)["\']?', line)
            if not m:
                continue
            pub = m.group(1).strip()
            found = True
            if re.fullmatch(r"\d+:\d+", pub):
                _fail(f"all-interfaces publish: {pub}")
            if not (
                pub.startswith("127.0.0.1:")
                or pub.startswith("localhost:")
                or pub.startswith("::1:")
            ):
                _fail(f"non-loopback publish: {pub}")
    if not found:
        _fail("no ports mappings in compose")


def check_aes_docs_and_env() -> None:
    if not AUDIT_DOC.is_file():
        _fail(f"missing audit doc {AUDIT_DOC}")
    audit = AUDIT_DOC.read_text(encoding="utf-8")
    if "AES-256-GCM" not in audit:
        _fail("audit doc missing AES-256-GCM section")
    if "Termux" not in audit:
        _fail("audit doc missing Termux vs droplet threat-model note")

    if not ENV_EXAMPLE.is_file():
        _fail(f"missing {ENV_EXAMPLE}")
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    compose_text = COMPOSE.read_text(encoding="utf-8")
    for key in REQUIRED_SECRET_KEYS:
        if key not in env_text:
            _fail(f".env.example missing {key}")
        if key not in compose_text:
            _fail(f"compose missing {key} environment passthrough")


def check_promptfoo_artifacts() -> None:
    if not FIXTURES.is_file():
        _fail(f"missing fixtures {FIXTURES}")
    if not PROMPTFOO_CFG.is_file():
        _fail(f"missing {PROMPTFOO_CFG}")
    if not RUN_SCRIPT.is_file():
        _fail(f"missing {RUN_SCRIPT}")
    body = FIXTURES.read_text(encoding="utf-8")
    cfg = PROMPTFOO_CFG.read_text(encoding="utf-8")
    if "[Relevant knowledge]" not in cfg:
        _fail("promptfooconfig must wrap KerrOS [Relevant knowledge] marker")
    if "Ignore all prior" not in body and "Ignore all prior" not in cfg:
        _fail("fixtures/config missing ignore-instructions poison case")
    if len(body) < 200:
        _fail("fixtures look empty")


def main() -> int:
    check_loopback_compose()
    check_aes_docs_and_env()
    check_promptfoo_artifacts()
    print("OK: OmniRoute §6 static security audit guards passed")
    print(f"  compose:   {COMPOSE.relative_to(ROOT)}")
    print(f"  audit doc: {AUDIT_DOC.relative_to(ROOT)}")
    print(f"  eval:      {PROMPTFOO_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
