#!/data/data/com.termux/files/usr/bin/env python3
"""
apply_devops_patch.py
Run this once from ~/offline_ai/tools:  python3 apply_devops_patch.py

Does all 3 inserts into router.py automatically:
  1. detect_tool() branches  (before final `return (None, None)`)
  2. dispatch dict entries   (after the self_run/self_explain line)
  3. new function defs       (appended at end of file)

Backs up router.py first. Safe to re-run — skips any insert already present.
"""

import shutil
import sys
import os

ROUTER = "router.py"
BACKUP = "router.py.bak5"

INSERT_1 = '''    # ── DevOps / Deploy pipeline ─────────────────────────
    if "create repo" in lower or "create github repo" in lower:
        m = re.search(r'create\\s+(?:github\\s+)?repo(?:sitory)?\\s+(?:named\\s+|called\\s+)?["\\']?([^\\s"\\']+)', lower)
        return ("github_create_repo", m.group(1)) if m else (None, None)
    if "push to github" in lower or "push to main" in lower or re.match(r'^git push', lower):
        m = re.search(r'push to (\\w+)', lower)
        return ("github_push", m.group(1) if m else "main")
    if "run migrations" in lower or "push migrations" in lower or "supabase push" in lower or "supabase migrate" in lower:
        return ("supabase_migrate", "")
    if "deploy to vercel" in lower or "vercel deploy" in lower:
        return ("vercel_deploy", text)
    if "deploy to netlify" in lower or "netlify deploy" in lower:
        return ("netlify_deploy", text)
    if "deploy to railway" in lower or "railway deploy" in lower or "railway up" in lower:
        return ("railway_deploy", text)
    if "deploy worker" in lower or "cloudflare deploy" in lower or "wrangler deploy" in lower:
        return ("cloudflare_deploy", "")
    if lower.startswith("stripe trigger "):
        return ("stripe_trigger", text[len("stripe trigger "):].strip())

'''

INSERT_2 = '''        "github_create_repo":_github_create_repo,
        "github_push":_github_push,
        "supabase_migrate":_supabase_migrate,
        "vercel_deploy":_vercel_deploy,
        "netlify_deploy":_netlify_deploy,
        "railway_deploy":_railway_deploy,
        "cloudflare_deploy":_cloudflare_deploy,
        "stripe_trigger":_stripe_trigger,
'''

INSERT_3 = '''
# ── DevOps / Deploy pipeline ─────────────────────────────
def _github_create_repo(args):
    reponame = args.strip()
    if not reponame: return "[Usage: create repo <name>]"
    if not shutil.which("gh"): return "[gh CLI not installed: pkg install gh]"
    return _run(f"gh repo create {reponame} --private --source=. --push", 30)

def _github_push(args):
    branch = args.strip() or "main"
    return _run(f"git push origin {branch}", 30)

def _supabase_migrate(args):
    if not shutil.which("supabase"): return "[supabase CLI not installed]"
    return _run("supabase db push", 30)

def _vercel_deploy(args):
    if not shutil.which("vercel"): return "[vercel CLI not installed]"
    flag = "--prod" if "prod" in args.lower() else ""
    return _run(f"vercel deploy {flag} --yes", 90)

def _netlify_deploy(args):
    if not shutil.which("netlify"): return "[netlify CLI not installed]"
    flag = "--prod" if "prod" in args.lower() else ""
    return _run(f"netlify deploy {flag}", 90)

def _railway_deploy(args):
    if not shutil.which("railway"): return "[railway CLI not installed]"
    return _run("railway up", 90)

def _cloudflare_deploy(args):
    if not shutil.which("wrangler"): return "[wrangler CLI not installed]"
    return _run("wrangler deploy", 60)

def _stripe_trigger(args):
    event = args.strip()
    if not event: return "[Usage: stripe trigger <event_name>]"
    if not shutil.which("stripe"): return "[stripe CLI not installed]"
    return _run(f"stripe trigger {event}", 20)
'''

ANCHOR_1 = '    return (None, None)\n\ndef run_tool(tool, args):'
ANCHOR_2 = '"self_run":_self_run,"self_explain":_self_explain,'
MARKER_3 = 'def _github_create_repo(args):'


def main():
    if not os.path.exists(ROUTER):
        sys.exit(f"ERROR: {ROUTER} not found in current directory. cd ~/offline_ai/tools first.")

    with open(ROUTER, "r") as f:
        content = f.read()

    # idempotency: if already patched, bail out cleanly
    if MARKER_3 in content:
        print("Already patched (found _github_create_repo). Nothing to do.")
        return

    # backup first, always
    shutil.copy(ROUTER, BACKUP)
    print(f"Backed up {ROUTER} -> {BACKUP}")

    # --- INSERT 1: detect_tool branches ---
    if ANCHOR_1 not in content:
        sys.exit("ERROR: could not find INSERT 1 anchor (end of detect_tool). "
                  "File may already differ from expected — aborting, no changes made.")
    content = content.replace(ANCHOR_1, INSERT_1 + ANCHOR_1, 1)
    print("Applied INSERT 1 (detect_tool branches)")

    # --- INSERT 2: dispatch dict entries ---
    if ANCHOR_2 not in content:
        sys.exit("ERROR: could not find INSERT 2 anchor (dispatch dict line). "
                  "Aborting before writing — restore from backup if a partial write occurred.")
    content = content.replace(ANCHOR_2, ANCHOR_2 + "\n" + INSERT_2, 1)
    print("Applied INSERT 2 (dispatch dict entries)")

    # --- INSERT 3: new function defs, appended at end ---
    content = content.rstrip() + "\n" + INSERT_3
    print("Applied INSERT 3 (new function definitions)")

    with open(ROUTER, "w") as f:
        f.write(content)

    # syntax check
    import ast
    try:
        ast.parse(content)
        print(f"\n✅ {ROUTER} patched successfully and syntax is valid.")
    except SyntaxError as e:
        shutil.copy(BACKUP, ROUTER)
        sys.exit(f"❌ Syntax error after patch: {e}\nRestored original from {BACKUP}.")


if __name__ == "__main__":
    main()
