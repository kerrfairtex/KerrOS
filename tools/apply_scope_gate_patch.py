#!/data/data/com.termux/files/usr/bin/env python3
"""
apply_scope_gate_patch.py
Run from ~/offline_ai/tools: python3 apply_scope_gate_patch.py

Adds gating for deploy/devops tools (github_push, vercel_deploy, etc.)
to scope_gate.py. These are NOT network-target tools, so they don't fit
the existing authorized_targets/CIDR model — instead they require an
explicit, time-limited "arm" before they'll execute.

Default state: BLOCKED. Human must run arm_deploy() (wire this to a
/scope arm-deploy <minutes> chat command) to open a short window.
"""
import shutil, sys, os, ast

FILE = "scope_gate.py"
BACKUP = "scope_gate.py.bak1"

MARKER = "DEPLOY_TOOLS = {"

INSERT_IMPORTS = "import os, json, ipaddress, re, time\n"
OLD_IMPORTS = "import os, json, ipaddress, re\n"

INSERT_AFTER_OFFENSIVE = '''
# Tools that mutate remote infra/repos/payments — never network-recon,
# so they don't fit the target-allowlist model above. Blocked by default;
# require a short explicit arm window instead.
DEPLOY_TOOLS = {
    "github_create_repo", "github_push", "supabase_migrate",
    "vercel_deploy", "netlify_deploy", "railway_deploy",
    "cloudflare_deploy", "stripe_trigger",
}


def _arm_status():
    scope = _load_scope()
    until = scope.get("deploy_armed_until", 0)
    return until, time.time() < until


def arm_deploy(minutes=5):
    """Opens a time-limited window during which DEPLOY_TOOLS will run.
    Call this only from an explicit human-issued command, never
    automatically from agent reasoning."""
    scope = _load_scope()
    scope["deploy_armed_until"] = time.time() + (minutes * 60)
    _save_scope(scope)
    return minutes


def disarm_deploy():
    scope = _load_scope()
    scope["deploy_armed_until"] = 0
    _save_scope(scope)
'''

OLD_CHECK_BODY = '''def check(tool, args):
    """
    Main gate entry point. Returns (allowed: bool, reason: str).
    Call this BEFORE run_tool() for any offensive tool.
    """
    if not requires_gate(tool):
        return True, "passive tool, no gate required"

    target = _extract_target(args)
    if is_authorized(target):
        return True, "authorized"

    return False, (
        f"BLOCKED: '{target}' is not in the authorized scope. "
        f"Use /scope add {target} to explicitly authorize it first."
    )'''

NEW_CHECK_BODY = '''def check(tool, args):
    """
    Main gate entry point. Returns (allowed: bool, reason: str).
    Call this BEFORE run_tool() for any offensive OR deploy tool.
    """
    if tool in DEPLOY_TOOLS:
        until, armed = _arm_status()
        if armed:
            remaining = int(until - time.time())
            return True, f"deploy armed, {remaining}s remaining"
        return False, (
            f"BLOCKED: '{tool}' requires an armed deploy window. "
            f"Use /scope arm-deploy <minutes> to authorize, then retry."
        )

    if not requires_gate(tool):
        return True, "passive tool, no gate required"

    target = _extract_target(args)
    if is_authorized(target):
        return True, "authorized"

    return False, (
        f"BLOCKED: '{target}' is not in the authorized scope. "
        f"Use /scope add {target} to explicitly authorize it first."
    )'''


def main():
    if not os.path.exists(FILE):
        sys.exit(f"ERROR: {FILE} not found. cd ~/offline_ai/tools first.")

    with open(FILE) as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (found DEPLOY_TOOLS). Nothing to do.")
        return

    shutil.copy(FILE, BACKUP)
    print(f"Backed up {FILE} -> {BACKUP}")

    if OLD_IMPORTS not in content:
        sys.exit("ERROR: import line doesn't match expected. Aborting, no changes made.")
    content = content.replace(OLD_IMPORTS, INSERT_IMPORTS, 1)

    anchor = 'OFFENSIVE_TOOLS = {\n    "nmap", "nikto", "osint", "recon", "geoip", "geoint",\n    "dnsenum", "reversedns", "email_osint", "sigint",\n    "headers", "cert", "whois", "dig", "ping", "traceroute",\n}'
    if anchor not in content:
        sys.exit("ERROR: OFFENSIVE_TOOLS block doesn't match expected text. Aborting.")
    content = content.replace(anchor, anchor + "\n" + INSERT_AFTER_OFFENSIVE, 1)

    if OLD_CHECK_BODY not in content:
        sys.exit("ERROR: check() function doesn't match expected text. Aborting before write.")
    content = content.replace(OLD_CHECK_BODY, NEW_CHECK_BODY, 1)

    with open(FILE, "w") as f:
        f.write(content)

    try:
        ast.parse(content)
        print(f"\n✅ {FILE} patched successfully. Deploy tools now BLOCKED by default.")
        print("   Arm with: python3 -c \"from tools.scope_gate import arm_deploy; arm_deploy(5)\"")
    except SyntaxError as e:
        shutil.copy(BACKUP, FILE)
        sys.exit(f"❌ Syntax error after patch: {e}\nRestored original from {BACKUP}.")


if __name__ == "__main__":
    main()
