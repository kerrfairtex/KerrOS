import os
import re
import subprocess

SAVE_DIR = os.path.expanduser("~/offline_ai/generated_code")

TREE_CHARS = set("├└│─")
ASCII_TREE_MARKERS = ("|--", "|-", "`--", "+--")


def extract_code_blocks(text):
    """
    Finds ```lang\ncode``` blocks in a response.
    Returns list of (language, code) tuples.
    """
    pattern = r"```(\w*)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches
    # Fallback: opening fence with no closing fence (truncated generation) —
    # treat rest of text as the code block.
    open_pattern = r"```(\w*)\n(.*)"
    m = re.search(open_pattern, text, re.DOTALL)
    if m:
        return [(m.group(1), m.group(2))]
    return []


EXT_MAP = {
    "python": "py", "py": "py",
    "javascript": "js", "js": "js",
    "html": "html", "css": "css",
    "bash": "sh", "sh": "sh",
    "json": "json", "java": "java",
    "c": "c", "cpp": "cpp",
}


def _looks_like_tree_diagram(code: str) -> bool:
    """Detect ASCII/Unicode tree output (e.g. from `tree` command) mistakenly
    fenced as ```bash — these are illustrative, not executable."""
    lines = [l for l in code.split("\n") if l.strip()]
    if not lines:
        return False
    tree_lines = sum(
        1 for l in lines
        if any(c in l for c in TREE_CHARS) or any(m in l for m in ASCII_TREE_MARKERS)
    )
    return (tree_lines / len(lines)) > 0.25


def _contains_placeholder_path(code: str) -> bool:
    """Detect illustrative example commands with unfilled placeholder
    paths (e.g. '/path/to/...', '<name>') — these are explanatory text,
    not real commands, and must never be auto-executed."""
    placeholder_patterns = [r'/path/to/', r'<[\w\-]+>', r'\byour[_\-]?\w*\b.*\.(sh|py|js|txt)']
    return any(re.search(p, code, re.IGNORECASE) for p in placeholder_patterns)


def _harden_bash_script(code: str) -> str:
    """Insert `mkdir -p` ahead of every touch/redirect target so a script
    can never fail with 'No such file or directory' on a nested path."""
    touch_re = re.compile(r'^\s*touch\s+(.+)$')
    redirect_re = re.compile(r'.*>\s*"?\'?([^\s">\']+)"?\'?\s*$')
    out = []
    for line in code.split("\n"):
        m = touch_re.match(line)
        if m:
            for t in m.group(1).split():
                t_clean = t.strip('"\'')
                if "/" in t_clean:
                    out.append(f'mkdir -p "$(dirname "{t_clean}")"')
        else:
            m2 = redirect_re.match(line)
            if m2:
                t_clean = m2.group(1).strip('"\'')
                if "/" in t_clean and not t_clean.startswith(("&", "/dev/")):
                    out.append(f'mkdir -p "$(dirname "{t_clean}")"')
        out.append(line)
    return "\n".join(out)


def save_code_blocks(text, base_name="kerros_output", folder=None):
    """
    Extracts code blocks from text and saves each to a file
    inside SAVE_DIR/folder (folder is project-specific).
    Returns list of saved file paths.
    """
    blocks = extract_code_blocks(text)
    if not blocks:
        return []

    target_dir = os.path.join(SAVE_DIR, folder) if folder else SAVE_DIR
    os.makedirs(target_dir, exist_ok=True)
    saved = []
    for i, (lang, code) in enumerate(blocks):
        ext = EXT_MAP.get(lang.lower(), "txt")
        code_body = code.strip()

        if ext == "sh":
            if _looks_like_tree_diagram(code_body):
                ext = "txt"
            elif _contains_placeholder_path(code_body):
                ext = "txt"
            else:
                code_body = _harden_bash_script(code_body)

        suffix = f"_{i}" if len(blocks) > 1 else ""
        filename = f"{base_name}{suffix}.{ext}"
        path = os.path.join(target_dir, filename)
        with open(path, "w") as f:
            f.write(code_body + "\n")
        saved.append(path)

    return saved


RUNNABLE = {"py": ["python3"], "sh": ["bash"], "js": ["node"]}


def run_and_verify(path):
    ext = path.rsplit(".", 1)[-1]
    cmd = RUNNABLE.get(ext)
    if not cmd:
        return {"ran": False, "reason": f"no runner for .{ext}"}
    try:
        r = subprocess.run(cmd + [path], capture_output=True, text=True, timeout=20)
        return {
            "ran": True,
            "ok": r.returncode == 0,
            "stdout": r.stdout.strip()[:1500],
            "stderr": r.stderr.strip()[:1500],
            "returncode": r.returncode
        }
    except subprocess.TimeoutExpired:
        return {"ran": True, "ok": False, "stdout": "", "stderr": "[Timeout after 20s]", "returncode": None}
    except Exception as e:
        return {"ran": False, "reason": str(e)}
