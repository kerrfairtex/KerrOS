"""
tools/skills_hub.py
===================
Local skills hub: install / uninstall / lockfile / quarantine (ADR-064).

Install sources (default Soft):
  - local path (file or directory of markdown)
  - optional http(s) URL when KERROS_SKILLS_HUB_LIVE=1

Installed skills land under skills/<category>/<name>.md.
Quarantined copies go to data/skills_hub/quarantine/.
Provenance lock: data/skills_hub/lock.json
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from tools.claw_tools import get_workspace
from tools.skills_guard import scan_skill, should_allow_install

NAME_RE = re.compile(r"^[a-z0-9_][a-z0-9_\-]{0,63}$")


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def hub_dir() -> Path:
    d = Path(os.path.expanduser("~/offline_ai")) / "data" / "skills_hub"
    d.mkdir(parents=True, exist_ok=True)
    return d


def quarantine_dir() -> Path:
    d = hub_dir() / "quarantine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lock_path() -> Path:
    return hub_dir() / "lock.json"


def skills_root() -> Path:
    root = get_workspace() / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_lock() -> dict[str, Any]:
    p = lock_path()
    if not p.is_file():
        return {"version": 1, "installed": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "installed": {}}
        data.setdefault("installed", {})
        return data
    except Exception:
        return {"version": 1, "installed": {}}


def _save_lock(data: dict[str, Any]) -> None:
    p = lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _safe_name(name: str) -> str:
    n = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not NAME_RE.match(n):
        raise ValueError(f"invalid skill name: {name!r}")
    return n


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def list_installed() -> list[dict[str, Any]]:
    data = _load_lock()
    return [{"name": k, **v} for k, v in (data.get("installed") or {}).items()]


def install_local(
    source: str,
    *,
    category: str = "imported",
    name: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Install a skill from a local .md file or directory."""
    src = Path(os.path.expanduser(source)).resolve()
    if not src.exists():
        return {"ok": False, "error": f"source not found: {src}"}

    # Stay inside workspace or /tmp for CI fixtures
    try:
        ws = get_workspace().resolve()
        if not (str(src).startswith(str(ws)) or str(src).startswith("/tmp")):
            return {"ok": False, "error": "source must be under workspace or /tmp"}
    except Exception:
        pass

    scan = scan_skill(src, name=name or src.stem)
    allow, reason = should_allow_install(scan, force=force)
    if not allow:
        # quarantine copy of text if file
        qdir = quarantine_dir() / (name or src.stem)
        qdir.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(src, qdir / src.name)
        else:
            # shallow copy md files only
            for md in list(src.rglob("*.md"))[:50]:
                dest = qdir / md.name
                shutil.copy2(md, dest)
        return {
            "ok": False,
            "error": reason,
            "scan": scan.to_dict(),
            "quarantine": str(qdir),
        }

    skill_name = _safe_name(name or src.stem)
    cat = _safe_name(category) if category else "imported"
    # Read markdown body
    if src.is_file():
        body = src.read_text(encoding="utf-8", errors="replace")
    else:
        # prefer SKILL.md then first md
        skill_md = src / "SKILL.md"
        if skill_md.is_file():
            body = skill_md.read_text(encoding="utf-8", errors="replace")
        else:
            mds = sorted(src.glob("*.md"))
            if not mds:
                return {"ok": False, "error": "no markdown skill content"}
            body = mds[0].read_text(encoding="utf-8", errors="replace")

    if not body.lstrip().startswith("#"):
        body = f"# {skill_name.replace('_', ' ').title()}\n\n{body}"

    dest_dir = skills_root() / cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{skill_name}.md"
    dest.write_text(body, encoding="utf-8")

    data = _load_lock()
    data["installed"][skill_name] = {
        "source": "local",
        "identifier": str(src),
        "category": cat,
        "install_path": str(dest.relative_to(get_workspace())),
        "content_hash": _content_hash(body),
        "scan_verdict": scan.verdict,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "write_origin": __import__(
            "tools.skill_provenance", fromlist=["get_current_write_origin"]
        ).get_current_write_origin(),
    }
    _save_lock(data)
    return {"ok": True, "skill": skill_name, "path": str(dest), "scan": scan.to_dict()}


def install_url(url: str, *, category: str = "imported", name: Optional[str] = None, force: bool = False) -> dict[str, Any]:
    if not _truthy(os.environ.get("KERROS_SKILLS_HUB_LIVE")):
        return {
            "ok": False,
            "error": "URL installs disabled — set KERROS_SKILLS_HUB_LIVE=1",
        }
    if not str(url).startswith(("http://", "https://")):
        return {"ok": False, "error": "only http(s) URLs allowed"}
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "error": f"fetch failed: {exc}"}
    tmp = hub_dir() / "tmp_fetch.md"
    tmp.write_text(body, encoding="utf-8")
    try:
        return install_local(str(tmp), category=category, name=name, force=force)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def uninstall(name: str) -> dict[str, Any]:
    skill_name = _safe_name(name)
    data = _load_lock()
    entry = (data.get("installed") or {}).get(skill_name)
    if not entry:
        return {"ok": False, "error": "not in lockfile"}
    rel = entry.get("install_path") or ""
    target = (get_workspace() / rel).resolve()
    root = skills_root().resolve()
    if not str(target).startswith(str(root)):
        return {"ok": False, "error": "install_path escapes skills root"}
    if target.is_file():
        target.unlink()
    data["installed"].pop(skill_name, None)
    _save_lock(data)
    return {"ok": True, "removed": skill_name}


def skills_hub(action: str, raw: str = "") -> str:
    """Router helper: list|install|uninstall|scan."""
    action = (action or "list").strip().lower()
    parts = [p.strip() for p in (raw or "").split("::")]
    if action == "list":
        items = list_installed()
        if not items:
            return "[skills_hub] no hub-installed skills"
        lines = ["[skills_hub] installed:"]
        for it in items:
            lines.append(f"- {it['name']} ({it.get('category')}) {it.get('install_path')}")
        return "\n".join(lines)
    if action == "install":
        src = parts[0] if parts else ""
        category = parts[1] if len(parts) > 1 else "imported"
        name = parts[2] if len(parts) > 2 else None
        force = _truthy(parts[3]) if len(parts) > 3 else False
        if not src:
            return "[skills_hub] usage: skills hub install :: <path|url> [:: category [:: name]]"
        if src.startswith("http://") or src.startswith("https://"):
            return json.dumps(install_url(src, category=category, name=name, force=force), indent=2)
        return json.dumps(install_local(src, category=category, name=name, force=force), indent=2)
    if action == "uninstall" and parts:
        return json.dumps(uninstall(parts[0]), indent=2)
    if action == "scan" and parts:
        return json.dumps(scan_skill(Path(os.path.expanduser(parts[0]))).to_dict(), indent=2)
    return "[skills_hub] actions: list|install|uninstall|scan"
