#!/data/data/com.termux/files/usr/bin/env python3
"""
apply_chat_devops_patch.py
Run from ~/offline_ai: python3 apply_chat_devops_patch.py

Fix 1: adds "/scope arm-deploy <minutes>" as a proper slash command,
       matching the existing /scope add|remove pattern (explicit y/n).

Fix 2: the generic tool-detection fallback currently treats EVERY scope
       gate rejection as "target not authorized, add it?" — wrong model
       for deploy tools (there's no target to allowlist, and _scope_add()
       does nothing to arm the deploy window). This patch inserts a
       self-contained branch for DEPLOY_TOOLS that prompts to arm, runs
       the tool via run_tool() directly, and continues — bypassing the
       target-allowlist flow entirely for these tools, without needing
       to touch or assume anything about the unseen code further down.
"""
import shutil, sys, os, ast

FILE = "chat.py"
BACKUP = "chat.py.bak1"

MARKER = "tool in DEPLOY_TOOLS"

ANCHOR_1 = '''        elif user.startswith("/scope remove "):
            from tools.scope_gate import remove_target
            t = user.replace("/scope remove ","").strip()
            removed = remove_target(t)
            print(f"  {GR}[ ✓ ] Removed{R}" if removed else f"  {GY}Not in scope.{R}")

        elif user=="/scope":'''

NEW_1 = '''        elif user.startswith("/scope remove "):
            from tools.scope_gate import remove_target
            t = user.replace("/scope remove ","").strip()
            removed = remove_target(t)
            print(f"  {GR}[ ✓ ] Removed{R}" if removed else f"  {GY}Not in scope.{R}")

        elif user.startswith("/scope arm-deploy"):
            from tools.scope_gate import arm_deploy
            parts = user.split()
            minutes = 5
            if len(parts) >= 3:
                try:
                    minutes = int(parts[2])
                except ValueError:
                    print(f"  {GY}Usage: /scope arm-deploy <minutes>{R}")
                    minutes = None
            if minutes:
                confirm = input(f"  {YL}Arm deploy tools (github/vercel/netlify/railway/cloudflare/stripe/supabase) for {minutes} minute(s)? [y/n]{R} ").strip().lower()
                if confirm == "y":
                    arm_deploy(minutes)
                    print(f"  {GR}[ ✓ ] Deploy armed for {minutes} minute(s){R}")
                else:
                    print(f"  {GY}Cancelled.{R}")

        elif user=="/scope":'''

ANCHOR_2 = '''                from tools.scope_gate import check as _scope_check, add_target as _scope_add
                allowed, reason = _scope_check(tool, args)
                if not allowed:'''

NEW_2 = '''                from tools.scope_gate import check as _scope_check, add_target as _scope_add
                allowed, reason = _scope_check(tool, args)

                from tools.scope_gate import DEPLOY_TOOLS, arm_deploy
                if tool in DEPLOY_TOOLS:
                    if not allowed:
                        print(f"  {RE}◈ Scope: {reason}{R}")
                        proceed = input(f"  {YL}Arm deploy tools for 5 minutes and run '{tool}' now? [y/n]{R} ").strip().lower()
                        if proceed == "y":
                            arm_deploy(5)
                            print(f"  {GR}[ ✓ ] Deploy armed for 5 minute(s){R}")
                        else:
                            print(f"  {GY}Cancelled.{R}")
                            continue
                    from tools.router import run_tool as _run_devops_tool
                    tool_result = _run_devops_tool(tool, args)
                    divider(); ai_header(mode); typewrite(tool_result); divider()
                    add_message("assistant", tool_result)
                    continue

                if not allowed:'''


def main():
    if not os.path.exists(FILE):
        sys.exit(f"ERROR: {FILE} not found. Run this from ~/offline_ai (or wherever chat.py lives).")

    with open(FILE) as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (found DEPLOY_TOOLS branch). Nothing to do.")
        return

    shutil.copy(FILE, BACKUP)
    print(f"Backed up {FILE} -> {BACKUP}")

    if ANCHOR_1 not in content:
        sys.exit("ERROR: could not find /scope command anchor. File may differ from expected — aborting, no changes made.")
    content = content.replace(ANCHOR_1, NEW_1, 1)
    print("Applied fix 1 (/scope arm-deploy command)")

    if ANCHOR_2 not in content:
        sys.exit("ERROR: could not find fallback-block anchor. Restore from backup if a partial write occurred — no write happened yet though.")
    content = content.replace(ANCHOR_2, NEW_2, 1)
    print("Applied fix 2 (DEPLOY_TOOLS fallback branch)")

    with open(FILE, "w") as f:
        f.write(content)

    try:
        ast.parse(content)
        print(f"\n✅ {FILE} patched successfully and syntax is valid.")
    except SyntaxError as e:
        shutil.copy(BACKUP, FILE)
        sys.exit(f"❌ Syntax error after patch: {e}\nRestored original from {BACKUP}.")


if __name__ == "__main__":
    main()
