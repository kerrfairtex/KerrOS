"""
tools/skills_guard.py
=====================
Pre-install skill content scanner (ADR-064).

Scans markdown/skill trees for injection and destructive-command patterns.
Returns allow/deny with findings. Does not print secrets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCANNABLE = {".md", ".txt", ".py", ".sh", ".yml", ".yaml", ".json", ".toml"}

THREAT_PATTERNS: list[tuple[str, str, str]] = [
    (r"ignore\s+(?:previous|all|above|prior)\s+instructions", "prompt_injection", "critical"),
    (r"system\s+prompt\s+override", "sys_prompt_override", "critical"),
    (r"disregard\s+(?:your|all)\s+(?:instructions|rules)", "disregard_rules", "critical"),
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide", "high"),
    (r"rm\s+-[^\s]*rf\s+/", "destructive_rm_root", "critical"),
    (r"curl\s+[^\n]*\|\s*(?:ba)?sh", "pipe_curl_shell", "high"),
    (r"wget\s+[^\n]*\|\s*(?:ba)?sh", "pipe_wget_shell", "high"),
    (r"cat\s+[^\n]*(?:\.env|credentials|\.netrc)", "read_secrets", "high"),
    (r"authorized_keys", "ssh_backdoor", "high"),
]

_COMPILED = [(re.compile(p, re.I), pid, sev) for p, pid, sev in THREAT_PATTERNS]


@dataclass
class Finding:
    pattern_id: str
    severity: str
    file: str
    line: int
    match: str


@dataclass
class ScanResult:
    name: str
    verdict: str  # allow | quarantine | deny
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "findings": [
                {
                    "pattern_id": f.pattern_id,
                    "severity": f.severity,
                    "file": f.file,
                    "line": f.line,
                    "match": f.match[:120],
                }
                for f in self.findings
            ],
        }


def scan_text(content: str, rel_path: str = "inline") -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate((content or "").splitlines(), 1):
        for rx, pid, sev in _COMPILED:
            if rx.search(line):
                findings.append(
                    Finding(pid, sev, rel_path, i, line.strip()[:120])
                )
                break
    return findings


def scan_skill(path: Path, *, name: str = "") -> ScanResult:
    root = Path(path)
    skill_name = name or root.stem if root.is_file() else root.name
    findings: list[Finding] = []
    files: list[Path] = []
    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = [p for p in root.rglob("*") if p.is_file()]
    else:
        return ScanResult(skill_name, "deny", [Finding("missing", "critical", str(path), 0, "path not found")])

    # structural limits
    if len(files) > 200:
        findings.append(Finding("too_many_files", "high", str(root), 0, f"{len(files)} files"))
    total = 0
    for fp in files:
        if fp.is_symlink():
            findings.append(Finding("symlink", "high", str(fp), 0, "symlink rejected"))
            continue
        try:
            total += fp.stat().st_size
        except OSError:
            continue
        if fp.suffix.lower() not in SCANNABLE and fp.name not in ("SKILL.md",):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(fp.relative_to(root)) if root.is_dir() and fp != root else fp.name
        findings.extend(scan_text(text, rel))
    if total > 5_000_000:
        findings.append(Finding("too_large", "high", str(root), 0, f"{total} bytes"))

    critical = [f for f in findings if f.severity == "critical"]
    high = [f for f in findings if f.severity == "high"]
    if critical:
        verdict = "deny"
    elif high:
        verdict = "quarantine"
    else:
        verdict = "allow"
    return ScanResult(skill_name, verdict, findings)


def should_allow_install(result: ScanResult, *, force: bool = False) -> tuple[bool, str]:
    if result.verdict == "allow":
        return True, "ok"
    if result.verdict == "quarantine" and force:
        return True, "forced despite quarantine findings"
    if result.verdict == "quarantine":
        return False, "quarantine — review findings or pass force=1"
    return False, "denied — critical findings"
