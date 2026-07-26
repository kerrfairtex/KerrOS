"""
tools/skill_tools.py
====================
Hermes-style Progressive Disclosure skill system for KerrOS.

Three-level architecture:
  Level 0 — skills_list()    : compact index injected at session start (~3 k tokens)
  Level 1 — skill_view()     : full skill doc loaded on demand (zero cost until called)
  Level 2 — skill_manage()   : agents write/update/delete their own skills (self-evolution)

Skill files live under  <WORKSPACE>/skills/<category>/<name>.md
The first line of each file (beginning with #) is the title.
The second non-blank line is used as the short description in the index.

YAML tool catalogs from tools/registry/*.yaml are also surfaced as read-only skills
under the synthetic category "tool_catalog".
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any

from tools.claw_tools import ToolResult, get_workspace

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _skills_root() -> Path:
    root = get_workspace() / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _registry_root() -> Path:
    return get_workspace() / "tools" / "registry"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_meta(path: Path) -> tuple[str, str]:
    """Return (title, description) from a skill file.

    For .md files: title = first '# …' heading, description = next non-blank line.
    For .yaml files: title = collection field or filename, description = first tool note.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return path.stem, ""

    if path.suffix == ".yaml":
        title = path.stem
        desc = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("collection:"):
                title = line.split(":", 1)[1].strip()
            if line.startswith("notes:"):
                desc = line.split(":", 1)[1].strip().strip('"')
                break
        return title, desc

    # .md
    title = path.stem.replace("_", " ").title()
    description = ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            # next non-blank line is description
            for follow in lines[i + 1 :]:
                if follow.strip():
                    description = follow.strip()[:160]
                    break
            break
        else:
            description = stripped[:160]
            break

    return title, description


def _iter_skills() -> list[dict[str, str]]:
    """Return all skills as compact dicts: {name, category, title, description, path}."""
    items: list[dict[str, str]] = []

    # 1. Native skills: skills/<category>/<name>.md
    root = _skills_root()
    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir():
            continue
        category = cat_dir.name
        for skill_file in sorted(cat_dir.glob("*.md")):
            title, desc = _extract_meta(skill_file)
            items.append(
                {
                    "name": skill_file.stem,
                    "category": category,
                    "title": title,
                    "description": desc,
                    "path": str(skill_file.relative_to(get_workspace())),
                }
            )

    # 2. Tool catalogs: tools/registry/*.yaml  (read-only, category = tool_catalog)
    reg = _registry_root()
    if reg.exists():
        for yaml_file in sorted(reg.glob("*.yaml")):
            title, desc = _extract_meta(yaml_file)
            items.append(
                {
                    "name": yaml_file.stem,
                    "category": "tool_catalog",
                    "title": title,
                    "description": desc or "Curated tool registry catalog.",
                    "path": str(yaml_file.relative_to(get_workspace())),
                }
            )

    return items


def _find_skill(name: str) -> dict[str, str] | None:
    """Locate a skill by exact stem name (case-insensitive)."""
    name_lc = name.lower().strip()
    for skill in _iter_skills():
        if skill["name"].lower() == name_lc:
            return skill
    return None


# ---------------------------------------------------------------------------
# Public API — called by tools/registry.py dispatch
# ---------------------------------------------------------------------------

def skills_list(category: str | None = None) -> ToolResult:
    """Return a compact index of all skills, optionally filtered by category.

    Designed to be injected at session start (Level 0).
    Returns one line per skill: [category] name — description
    """
    try:
        skills = _iter_skills()
        if category:
            cat_lc = category.lower()
            skills = [s for s in skills if s["category"].lower() == cat_lc]

        if not skills:
            msg = f"No skills found" + (f" in category '{category}'" if category else "") + "."
            return ToolResult(True, "skills_list", output=msg, data={"skills": []})

        # Group by category for readability
        by_cat: dict[str, list[dict]] = {}
        for s in skills:
            by_cat.setdefault(s["category"], []).append(s)

        lines: list[str] = []
        for cat, entries in sorted(by_cat.items()):
            lines.append(f"\n[{cat}]")
            for e in entries:
                desc = f" — {e['description']}" if e["description"] else ""
                lines.append(f"  {e['name']}{desc}")

        output = f"Available skills ({len(skills)} total):" + "\n".join(lines)
        return ToolResult(
            True,
            "skills_list",
            output=output,
            data={"skills": skills, "total": len(skills)},
        )
    except Exception as e:
        return ToolResult(False, "skills_list", error=str(e))


def skill_view(name: str, file_path: str | None = None) -> ToolResult:
    """Load and return the full content of a skill (Level 1 / Level 2).

    Args:
        name:       Skill stem name (e.g. "auth_patterns").
        file_path:  Optional explicit path relative to workspace to override lookup.
    """
    try:
        ws = get_workspace()

        if file_path:
            target = (ws / file_path).resolve()
            try:
                target.relative_to(ws)
            except ValueError:
                return ToolResult(False, "skill_view", error=f"file_path escapes workspace: {file_path}")
            if not target.exists():
                return ToolResult(False, "skill_view", error=f"not found: {file_path}")
        else:
            skill = _find_skill(name)
            if not skill:
                # Helpful error: suggest similar names
                all_names = [s["name"] for s in _iter_skills()]
                similar = [n for n in all_names if name.lower() in n.lower() or n.lower() in name.lower()]
                hint = f" Did you mean: {', '.join(similar[:5])}?" if similar else ""
                return ToolResult(False, "skill_view", error=f"skill '{name}' not found.{hint}")
            target = ws / skill["path"]

        content = target.read_text(encoding="utf-8", errors="replace")
        rel = str(target.relative_to(ws))
        return ToolResult(
            True,
            "skill_view",
            output=content,
            data={"skill": name, "path": rel, "bytes": len(content.encode())},
        )
    except Exception as e:
        return ToolResult(False, "skill_view", error=str(e))


def skill_manage(
    action: str,
    name: str,
    content: str | None = None,
    category: str | None = None,
    description: str | None = None,
) -> ToolResult:
    """Create, update, or delete a skill (Level 2 — Dynamic Evolution).

    Actions:
        save    — write (or overwrite) skills/<category>/<name>.md with content.
                  category defaults to "custom" if not supplied.
        delete  — remove skills/<category>/<name>.md
        rename  — rename a skill file (requires new_name in category field as workaround)

    Args:
        action:      "save" | "delete"
        name:        Skill stem name (no extension).
        content:     Markdown content for the skill (required for save).
        category:    Subdirectory category. Defaults to "custom".
        description: One-line description (prepended as subtitle if saving new skill).
    """
    try:
        action = action.lower().strip()
        name = name.strip().replace(" ", "_").lower()
        if not name:
            return ToolResult(False, "skill_manage", error="name is required")

        ws = get_workspace()
        skills_root = _skills_root()
        cat = (category or "custom").strip().replace(" ", "_").lower()

        # Prevent writes into tool_catalog (YAML files are read-only)
        if cat == "tool_catalog":
            return ToolResult(False, "skill_manage", error="tool_catalog skills are read-only.")

        skill_dir = skills_root / cat
        skill_path = skill_dir / f"{name}.md"

        if action == "save":
            if not content or not content.strip():
                return ToolResult(False, "skill_manage", error="content is required for save")

            # Auto-prepend a heading if missing
            body = content.strip()
            if not body.startswith("#"):
                title_line = f"# {name.replace('_', ' ').title()}"
                if description:
                    body = f"{title_line}\n{description}\n\n{body}"
                else:
                    body = f"{title_line}\n\n{body}"
            elif description and "\n" not in body.split("\n")[0]:
                lines = body.splitlines()
                body = lines[0] + f"\n{description}\n" + "\n".join(lines[1:])

            skill_dir.mkdir(parents=True, exist_ok=True)
            is_new = not skill_path.exists()
            skill_path.write_text(body + "\n", encoding="utf-8")
            verb = "created" if is_new else "updated"
            return ToolResult(
                True,
                "skill_manage",
                output=f"Skill '{name}' {verb} at {skill_path.relative_to(ws)}",
                data={"action": "save", "path": str(skill_path.relative_to(ws)), "category": cat},
            )

        elif action == "delete":
            skill = _find_skill(name)
            if skill:
                target = ws / skill["path"]
            elif skill_path.exists():
                target = skill_path
            else:
                return ToolResult(False, "skill_manage", error=f"skill '{name}' not found")

            # Safety: never delete tool_catalog entries
            if "tools/registry" in str(target):
                return ToolResult(False, "skill_manage", error="tool_catalog skills are read-only.")

            target.unlink()
            return ToolResult(
                True,
                "skill_manage",
                output=f"Skill '{name}' deleted.",
                data={"action": "delete", "path": str(target.relative_to(ws))},
            )

        else:
            return ToolResult(False, "skill_manage", error=f"unknown action '{action}' — use save or delete")

    except Exception as e:
        return ToolResult(False, "skill_manage", error=str(e))
